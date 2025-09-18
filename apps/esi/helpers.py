import base64
import logging
import secrets
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.core.cache import cache
from jose import jwt
from jose.exceptions import ExpiredSignatureError
from jose.exceptions import JWTError

from .app_settings import ESI_JWKS_ACCEPTED_ISSUERS
from .app_settings import ESI_JWKS_METADATA_CACHE_TIME
from .app_settings import ESI_JWKS_METADATA_URL
from .app_settings import ESI_OAUTH_URL
from .app_settings import ESI_TOKEN_JWT_AUDIENCE

logger = logging.getLogger(__name__)


def generate_sso_redirect(scopes: str | list[str], return_to: str) -> tuple[str, str]:
    if isinstance(scopes, list):
        scopes = ' '.join(scopes)
    state = secrets.token_urlsafe(16)
    params = {
        'response_type': 'code',
        'redirect_uri': settings.ESI_SSO_CALLBACK_URL,
        'client_id': settings.ESI_SSO_CLIENT_ID,
        'scope': scopes,
        'state': state,
    }
    query_string = urlencode(params)
    return (f'{ESI_OAUTH_URL}/authorize?{query_string}', state)


def fetch_jwks_metadata():
    """
    Fetches the JWKS metadata from the SSO server.

    :returns: The JWKS metadata
    """
    jwks_metadata = cache.get('esi:jwks:metadata')

    if jwks_metadata is None:
        resp = httpx.get(ESI_JWKS_METADATA_URL, timeout=10)
        resp.raise_for_status()
        metadata = resp.json()

        jkws_uri = metadata.get('jwks_uri')

        resp = httpx.get(jkws_uri, timeout=10)
        resp.raise_for_status()

        jwks_metadata = resp.json()
        cache.set(
            'esi:jwks:metadata', jwks_metadata, timeout=ESI_JWKS_METADATA_CACHE_TIME
        )

    return jwks_metadata


def validate_jwt_token(token: str):
    """
    Validates a JWT token using the JWKS metadata.

    :param token: The JWT token to validate
    :returns: The decoded token if valid, None otherwise
    """
    metadata = fetch_jwks_metadata()
    keys = metadata.get('keys', [])
    header = jwt.get_unverified_header(token)
    key = [
        item
        for item in keys
        if item['kid'] == header['kid'] and item['alg'] == header['alg']
    ].pop()
    decoded_jwt = jwt.decode(
        token,
        key=key,
        algorithms=header['alg'],
        issuer=ESI_JWKS_ACCEPTED_ISSUERS,
        audience=ESI_TOKEN_JWT_AUDIENCE,
    )
    logger.debug('Decoded JWT: %s', decoded_jwt)
    return decoded_jwt


def is_token_valid(token: str) -> bool:
    try:
        claims = validate_jwt_token(token)
        # If our client_id is in the audience list, the token is valid, otherwise, we got a token for another client.
        return 'client_id' in claims['aud']
    except ExpiredSignatureError:
        # The token has expired
        return False
    except JWTError:
        # The token is invalid
        return False
    except Exception:
        # Something went wrong
        return False


def exchange_code_for_token(code: str) -> dict:
    """
    Exchanges an authorization code for an access token.

    :param code: The authorization code
    :returns: The token response
    """
    basic_auth = base64.urlsafe_b64encode(
        f'{settings.ESI_SSO_CLIENT_ID}:{settings.ESI_SSO_CLIENT_SECRET}'.encode()
    ).decode()
    data = {
        'grant_type': 'authorization_code',
        'code': code,
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {basic_auth}',
    }
    resp = httpx.post(f'{ESI_OAUTH_URL}/token', data=data, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()
