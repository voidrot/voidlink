import base64
import datetime
import logging
from typing import Any
from typing import ClassVar

import httpx
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.esi.app_settings import ESI_OAUTH_URL
from apps.esi.app_settings import ESI_TOKEN_VALID_DURATION
from apps.esi.exceptions import TokenError
from apps.esi.exceptions import TokenExpiredError
from apps.esi.exceptions import TokenNotRefreshableError
from apps.esi.managers import TokenManager

logger = logging.getLogger(__name__)


class Scope(models.Model):
    """
    Valid ESI scopes that can be assigned to Tokens.
    """

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()

    def __str__(self) -> str:
        return self.name


class Token(models.Model):
    """
    An EVE SSO token, associated with a character.
    """

    TOKEN_TYPE_CHOICES = [
        ('character', 'Character'),
        ('corporation', 'Corporation'),
    ]

    character_id = models.IntegerField(db_index=True)
    character_name = models.CharField(max_length=100, db_index=True)
    token_type = models.CharField(
        max_length=20, choices=TOKEN_TYPE_CHOICES, db_index=True
    )
    user = models.ForeignKey(  # This should not ever be null so we are not setting null=True
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)
    access_token = models.TextField(editable=False)
    refresh_token = models.TextField(editable=False)
    character_owner_hash = models.CharField(max_length=255, db_index=True)
    scopes = models.ManyToManyField(Scope)

    objects: ClassVar[TokenManager] = TokenManager()  # pyright: ignore[reportIncompatibleVariableOverride]

    def __str__(self) -> str:
        try:
            scopes = sorted(s.name for s in self.scopes.all())
        except ValueError:
            scopes = []
        return f'{self.character_name} - {", ".join(scopes)}'

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}(id={self.pk}): {self.character_id}, {self.character_name}>'

    @property
    def can_refresh(self) -> bool:
        """Return True if the token has a refresh token."""
        return bool(self.refresh_token)

    @property
    def expires_at(self) -> datetime.datetime:
        """Return the datetime the token expires."""
        return self.created + datetime.timedelta(seconds=ESI_TOKEN_VALID_DURATION)

    @property
    def is_expired(self) -> bool:
        """Determine if the token is expired."""
        return self.expires_at < timezone.now()

    def valid_access_token(self) -> str:
        """
        Refresh and return a valid access token.
        """
        if self.is_expired:
            if self.can_refresh:
                self.refresh()
            else:
                raise TokenExpiredError
        return self.access_token

    def refresh(self):
        """
        Refresh the access token using the refresh token.
        """
        if not self.can_refresh:
            raise TokenNotRefreshableError

        auth_str = f'{settings.ESI_SSO_CLIENT_ID}:{settings.ESI_SSO_CLIENT_SECRET}'
        auth = base64.b64encode(auth_str.encode()).decode()
        response = httpx.post(
            ESI_OAUTH_URL + '/token',
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {auth}',
            },
            data={
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
            },
        )
        if response.status_code in {400, 401}:
            raise TokenNotRefreshableError
            # TODO: Check this better so we can confidently delete the token if it's invalid
        token_data = response.json()

        decoded_token_data = Token.get_token_data(token_data.get('access_token'))

        logger.debug('Token refresh response: %s', decoded_token_data)

        if token_data is not None and decoded_token_data is not None:
            if self.character_owner_hash != decoded_token_data.get('owner'):
                logger.warning(
                    'Owner hash mismatch for token %s: %s != %s',
                    self.pk,
                    self.character_owner_hash,
                    decoded_token_data.get('owner'),
                )
                raise TokenNotRefreshableError

        self.access_token = token_data['access_token']
        self.refresh_token = token_data['refresh_token']
        self.created = timezone.now()
        self.save()

    def refresh_or_delete(self):
        """
        Attempt to refresh the token, or delete it if it cannot be refreshed.
        """
        try:
            self.refresh()
        except TokenError:
            logger.info(
                'Deleting token for character (ID: %s) %s',
                self.character_id,
                self.character_name,
            )
            self.delete()
        else:
            logger.info(
                'Refreshed token for character (ID: %s) %s',
                self.character_id,
                self.character_name,
            )

    @classmethod
    def get_token_data(cls, access_token: str) -> dict[str, Any] | None:
        """
        Get token data from ESI using the provided access token.
        """
        return TokenManager.validate_access_token(access_token)

    @classmethod
    def get_token(cls, character_id: int, scopes: list) -> 'Token':
        """
        Get a token for the given character ID and scopes.
        """
        token = (
            Token.objects.filter(character_id=character_id)
            .require_scopes(scopes)
            .first()
        )
        if not token:
            msg = 'No token found for character with required scopes'
            raise TokenError(msg)
        return token


class CallbackRedirect(models.Model):
    """
    Store state values for EVE SSO callback redirects.
    """

    created = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=128)
    session_key = models.CharField(max_length=255, unique=True)
    url = models.CharField(max_length=255)
    token = models.ForeignKey(Token, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.session_key}: {self.url}'
