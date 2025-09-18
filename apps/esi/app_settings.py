from django.conf import settings

ESI_CACHE_BACKEND_NAME = getattr(settings, 'ESI_CACHE_BACKEND_NAME', 'esi')

# General Settings
ESI_OAUTH_URL = getattr(
    settings, 'ESI_SSO_BASE_URL', 'https://login.eveonline.com/v2/oauth'
)
"""The base URL for EVE SSO OAuth2 authentication."""
ESI_OAUTH_LOGIN_URL = getattr(
    settings, 'ESI_SSO_LOGIN_URL', ESI_OAUTH_URL + '/authorize/'
)
ESI_TOKEN_URL = getattr(settings, 'ESI_CODE_EXCHANGE_URL', ESI_OAUTH_URL + '/token')
"""The URL to redirect users to for EVE SSO login."""

ESI_OPENAPI_URL = getattr(
    settings, 'ESI_OPENAPI_URL', 'https://esi.evetech.net/meta/openapi.json'
)
ESI_API_URL = getattr(settings, 'ESI_API_URL', 'https://esi.evetech.net/')
"""The URL to the ESI OpenAPI specification."""
ESI_SPEC_CACHE_DURATION = int(getattr(settings, 'ESI_SPEC_CACHE_DURATION', 3600))
"""The duration, in seconds, to cache the ESI OpenAPI specification."""
ESI_CLIENT_TENANT = getattr(settings, 'ESI_CLIENT_TENANT', 'tranquility')
"""The ESI client tenant to use for requests."""
ESI_COMPATIBILITY_DATE = getattr(settings, 'ESI_COMPATIBILITY_DATE', '2025-08-26')
"""The ESI compatibility date to use for requests."""

# Client Settings
ESI_CLIENT_CONNECT_TIMEOUT = getattr(settings, 'ESI_CLIENT_CONNECT_TIMEOUT', 5.0)
"""Default connect timeout settings for the HTTPX client used to interact with the ESI API."""
ESI_CLIENT_READ_TIMEOUT = getattr(settings, 'ESI_CLIENT_READ_TIMEOUT', 10.0)
"""Default read timeout settings for the HTTPX client used to interact with the ESI API."""
ESI_CLIENT_WRITE_TIMEOUT = getattr(settings, 'ESI_CLIENT_WRITE_TIMEOUT', 10.0)
"""Default write timeout settings for the HTTPX client used to interact with the ESI API."""
ESI_CLIENT_POOL_TIMEOUT = getattr(settings, 'ESI_CLIENT_POOL_TIMEOUT', 5.0)
"""Default pool timeout settings for the HTTPX client used to interact with the ESI API."""
ESI_CONNECTION_ERROR_MAX_RETRIES = getattr(
    settings, 'ESI_CONNECTION_ERROR_MAX_RETRIES', 3
)
"""Max retries on failed connections."""
ESI_SERVER_ERROR_MAX_RETRIES = getattr(settings, 'ESI_SERVER_ERROR_MAX_RETRIES', 3)
"""Max retries on server errors."""
ESI_SERVER_ERROR_BACKOFF_FACTOR = getattr(
    settings, 'ESI_SERVER_ERROR_BACKOFF_FACTOR', 0.2
)
"""Backoff factor for retries on server error."""
ESI_CONNECTION_POOL_MAXSIZE = getattr(settings, 'ESI_CONNECTION_POOL_MAXSIZE', 10)
"""Max size of the connection pool.

Increase this setting if you hav more parallel
threads connected to ESI at the same time.
"""

# User-Agent Settings
ESI_APP_UA_NAME = getattr(settings, 'ESI_APP_UA_NAME', 'Voidlink')
"""The name of the application to use in the User-Agent header."""
ESI_APP_UA_VERSION = getattr(settings, 'ESI_APP_UA_VERSION', '0.0.1')
"""The version of the application to use in the User-Agent header."""
ESI_APP_UA_URL = getattr(settings, 'ESI_APP_UA_URL', None)
"""The URL of the application to use in the User-Agent header."""
ESI_APP_UA_EMAIL = getattr(settings, 'ESI_APP_UA_EMAIL', None)
"""The email of the application to use in the User-Agent header."""

# Token Settings
ESI_TOKEN_VALID_DURATION = getattr(settings, 'ESI_TOKEN_VALID_DURATION', 1170)
"""The duration, in seconds, that an ESI token is considered valid."""
ESI_TOKEN_VERIFY_URL = getattr(
    settings, 'ESI_TOKEN_EXCHANGE_URL', ESI_OAUTH_URL + '/verify'
)
ESI_ALWAYS_CREATE_TOKEN = getattr(settings, 'ESI_ALWAYS_CREATE_TOKEN', False)
# JWT Settings
ESI_TOKEN_JWT_AUDIENCE = str(getattr(settings, 'ESI_TOKEN_JWT_AUDIENCE', 'EVE Online'))
"""The audience to use when validating JWT tokens."""
ESI_TOKEN_JWK_SET_URL = 'https://login.eveonline.com/oauth/jwks'
"""The URL to fetch the JWK set for validating JWT tokens."""

ESI_JWKS_METADATA_URL = (
    'https://login.eveonline.com/.well-known/oauth-authorization-server'
)

ESI_JWKS_ACCEPTED_ISSUERS = ('logineveonline.com', 'https://login.eveonline.com')
"""The accepted issuers to use when validating JWT tokens."""
ESI_JWKS_METADATA_CACHE_TIME = 300

# Cache Settings
ESI_CACHE_RESPONSE = getattr(settings, 'ESI_CACHE_RESPONSE', True)
"""Disable to stop caching endpoint responses."""
