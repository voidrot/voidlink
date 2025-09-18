import logging
import warnings
from datetime import UTC
from datetime import datetime
from hashlib import blake2b
from typing import Any

from aiopenapi3 import OpenAPI
from aiopenapi3._types import ResponseDataType
from aiopenapi3._types import ResponseHeadersType
from aiopenapi3.errors import HTTPClientError as base_HTTPClientError
from aiopenapi3.errors import HTTPServerError as base_HTTPServerError
from aiopenapi3.request import OperationIndex
from aiopenapi3.request import RequestBase
from django.core.cache import CacheHandler
from django.core.cache import caches
from httpx import Client
from httpx import HTTPStatusError
from httpx import RequestError
from httpx import Response
from httpx import Timeout
from tenacity import Retrying
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_combine
from tenacity import wait_exponential

from apps.esi.client_stubs import ESIClientStub
from apps.esi.exceptions import ESIErrorLimitExceptionError
from apps.esi.exceptions import HTTPClientError
from apps.esi.exceptions import HTTPNotModified
from apps.esi.exceptions import HTTPServerError
from apps.esi.plugins import Add304ContentType
from apps.esi.plugins import PatchCompatibilityDatePlugin
from apps.esi.plugins import Trim204ContentType

from .app_settings import ESI_APP_UA_EMAIL
from .app_settings import ESI_APP_UA_NAME
from .app_settings import ESI_APP_UA_URL
from .app_settings import ESI_APP_UA_VERSION
from .app_settings import ESI_CACHE_BACKEND_NAME
from .app_settings import ESI_CACHE_RESPONSE
from .app_settings import ESI_CLIENT_CONNECT_TIMEOUT
from .app_settings import ESI_CLIENT_POOL_TIMEOUT
from .app_settings import ESI_CLIENT_READ_TIMEOUT
from .app_settings import ESI_CLIENT_TENANT
from .app_settings import ESI_CLIENT_WRITE_TIMEOUT
from .app_settings import ESI_COMPATIBILITY_DATE
from .app_settings import ESI_OPENAPI_URL
from .models import Token

# import pickle

logger = logging.getLogger(__name__)


def _build_user_agent() -> str:
    """
    Build a User-Agent string for ESI requests.
    """
    return (
        f'{ESI_APP_UA_NAME}/{ESI_APP_UA_VERSION} '
        f'({ESI_APP_UA_EMAIL}{f"; +{ESI_APP_UA_URL})" if ESI_APP_UA_URL else ")"} '
    )


def _time_to_expire(expires_header: str) -> int:
    """
    Calculate cache TTL from an HTTP Expires header.
    """
    try:
        expires_dt = datetime.strptime(str(expires_header), '%a, %d %b %Y %H:%M:%S %Z')
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=UTC)
        return max(int((expires_dt - datetime.now(tz=UTC)).total_seconds()), 0)
    except ValueError:
        return 0


def _retry_exceptions(exc: BaseException) -> bool:
    """
    Determine if a request should be retried based on the exception raised.
    """
    if isinstance(exc, ESIErrorLimitExceptionError):
        return False
    if isinstance(exc, RequestError):
        return True
    if (  # noqa: SIM103
        isinstance(exc, HTTPStatusError)
        and getattr(exc.response, 'status_code', None) in {502, 503, 504}
    ):
        return True
    # TODO: Add more conditions as needed
    return False


def _request_retry() -> Retrying:
    """
    Configure a Retrying object for request retries.
    """
    return Retrying(
        retry=retry_if_exception(_retry_exceptions),
        wait=wait_combine(
            wait_exponential(multiplier=1, min=4, max=10),
        ),
        stop=stop_after_attempt(3),
        reraise=True,
    )


def _load_openapi_client() -> OpenAPI:
    """
    Load the OpenAPI specification and create an instance of OpenAPI client.
    """
    headers = {
        'User-Agent': _build_user_agent(),
        'X-Tenant': ESI_CLIENT_TENANT,
        'X-Compatibility-Date': ESI_COMPATIBILITY_DATE,
    }

    def session_factory(**kwargs) -> Client:
        kwargs.pop('headers', None)
        return Client(
            headers=headers,
            timeout=Timeout(
                connect=ESI_CLIENT_CONNECT_TIMEOUT,
                read=ESI_CLIENT_READ_TIMEOUT,
                write=ESI_CLIENT_WRITE_TIMEOUT,
                pool=ESI_CLIENT_POOL_TIMEOUT,
            ),
            http2=True,
            **kwargs,
        )

    return OpenAPI.load_sync(
        url=ESI_OPENAPI_URL,
        session_factory=session_factory,
        use_operation_tags=True,
        plugins=[
            PatchCompatibilityDatePlugin(),
            Trim204ContentType(),
            Add304ContentType(),
        ],
    )


def _client_factory(**kwargs):
    """
    Factory function to create an ESI API client.
    """
    return _load_openapi_client()


class BaseESIClientOperation:
    def __init__(self, operation, api) -> None:
        self.method, self.url, self.operation, self.extra = operation
        self.api: OpenAPI = api
        self.token: Token | None = None
        self._args: list[Any] = []  # Added type annotation for _args
        self._kwargs: dict[str, Any] = {}
        # self._cache: Redis = Redis().from_url(settings.ESI_REDIS_URL)
        self._cache: CacheHandler = caches[ESI_CACHE_BACKEND_NAME]

    def __call__(self, *args, **kwargs) -> 'BaseESIClientOperation':
        self._args = args
        self._kwargs = kwargs
        return self

    def _reverse_normalize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Reverse the normalization of parameters to match the original operation signature.
        """
        # This is a placeholder implementation. The actual implementation would depend
        # on how parameters were normalized in the aiopenapi3 library.
        try:
            spec_param_names = [
                p.name for p in getattr(self.operation, 'parameters', [])
            ]
        except Exception:
            spec_param_names = []

        spec_param_set = set(spec_param_names)
        spec_param_map_ci = {name.lower(): name for name in spec_param_names}

        normalized: dict[str, Any] = {}
        for k, v in params.items():
            # Check for exact match
            if k in spec_param_set:
                normalized[k] = v
                continue

            # Check for hyphen variant
            k_dash = k.replace('_', '-')
            if k_dash in spec_param_set:
                normalized[k_dash] = v
                continue

            # Check for case-insensitive match
            k_lower = k.lower()
            if k_lower in spec_param_map_ci:
                k_dash_lower = k_dash.lower()
                normalized[spec_param_map_ci[k_dash_lower]] = v
                continue

            # Unknown in spec, let aiopenapi3 validate
            normalized[k] = v
        return normalized

    def _cache_key(self) -> str:
        """
        Generate a cache key based on the operation and its parameters.
        """
        ignore_keys = [
            'token',
        ]
        _kwargs = {
            key: value for key, value in self._kwargs.items() if key not in ignore_keys
        }
        data = (self.method + self.url + str(self._args) + str(_kwargs)).encode('utf-8')
        hash_str = blake2b(data, digest_size=24).hexdigest()
        return f'esi:{hash_str}'

    def _extract_body_param(self) -> Token | None:
        """Pop the request body from parameters to be able to check the param validity
        Returns:
            Any | None: the request body
        """
        _body = self._kwargs.pop('body', None)
        if _body and not getattr(self.operation, 'requestBody', False):
            msg = 'Request Body provided on endpoint with no request body paramater.'
            raise ValueError(msg)
        return _body

    def _get_cache(
        self, cache_key: str, etag: str | None
    ) -> tuple[ResponseHeadersType | None, Any, Response | None]:
        """
        Retrieve a cached response if available and validate its freshness.
        """
        try:
            # cached_response = pickle.loads(self._cache.get(f'{cache_key}:data'))
            cached_response = self._cache.get(f'{cache_key}:data')
        except Exception as e:
            logger.error(
                'Error retrieving cache for key %s:data : %s',
                cache_key,
                e,
                exc_info=True,
            )
            return None, None, None

        if cached_response:
            logger.debug('Cache hit for key %s', cache_key)
            # check if etag is same before building models from cache
            if etag:
                if cached_response.headers.get('etag', None) != etag:
                    logger.error(
                        'ETag mismatch for cache key %s: cached etag %s, provided etag %s',
                        cache_key,
                        cached_response.headers.get('etag', None),
                        etag,
                    )
                    return None, None, None
            headers, data = self.parse_cached_request(cached_response)
            return headers, data, cached_response
        return None, None, None

    def _store_cache(self, cache_key: str, response: Response) -> None:
        """
        Store a response in the cache with an ETag and appropriate TTL.
        """
        if 'etag' in response.headers:
            # Setting ETag to 3x the Expires time to allow for some leeway and to make sure that we dont keep a bunch
            # of useless etags around if we are not making the requests
            self._cache.set(f'{cache_key}:etag', response.headers.get('etag'))

        try:
            # self._cache.set(f'{cache_key}:data', pickle.dumps(response))
            self._cache.set(f'{cache_key}:data', response)
            # Set a timestamp for when this was stored so that we can cleanup later
            # while still ensuring that we can respect 304 responses
            # self._cache.set(f'{cache_key}:stored', pickle.dumps(datetime.now(tz=UTC)))
            self._cache.set(f'{cache_key}:stored', datetime.now(tz=UTC))
        except Exception:
            logger.exception('Error storing cache for key %s', cache_key)

    def _extract_token_param(self) -> Token | None:
        """
        Extract the token from parameters or use the client wide token if it has been set.
        """
        _token = self._kwargs.pop('token', None)
        if _token and not getattr(self.operation, 'security', None):
            msg = 'Token provided on public endpoint'
            raise ValueError(msg)
        return self.token or _token

    def _has_pages(self) -> bool:
        """
        Determine if the operation supports pagination.
        """
        return any(p.name == 'page' for p in self.operation.parameters)

    def _has_cursor(self) -> bool:
        """
        Determine if the operation supports cursor-based pagination.
        """
        return any(p.name in {'before', 'after'} for p in self.operation.parameters)

    def _validate_token_scopes(self, token: Token) -> None:
        """
        Validate that the provided token has the required scopes for this operation.
        """
        token_scopes = set(token.scopes.all().values_list('name', flat=True))
        try:
            required_scopes = set(
                getattr(getattr(self.operation, 'security', [])[0], 'root', {}).get(
                    'OAuth2', []
                )
            )
        except KeyError:
            required_scopes = []
        missing_scopes = [x for x in required_scopes if x not in token_scopes]
        if len(missing_scopes) > 0:
            msg = f'Token missing required scopes: {", ".join(missing_scopes)}'
            raise ValueError(
                msg
            )  # TODO: Should we add a custom exception for missing scopes

    def parse_cached_request(
        self, cached_response: Response
    ) -> tuple[ResponseHeadersType, ResponseDataType]:
        """
        Parse a cached Response object to extract headers and data.
        """
        req = self.api.createRequest(
            f'{self.operation.tags[0]}.{self.operation.operationId}'
        )
        return req._process_request(cached_response)


class ESIClientOperation(BaseESIClientOperation):
    def _make_request(
        self, parameters: dict[str, Any], etag: str | None = None
    ) -> RequestBase.Response:
        reset = self._cache.get('esi_rate_limit:error_limit_reset')
        if reset is not None:
            # Hard stop if there is still an active error limit
            raise ESIErrorLimitExceptionError(reset=reset)

        retry = _request_retry()

        def __func():
            req = self.api.createRequest(
                f'{self.operation.tags[0]}.{self.operation.operationId}'
            )
            if self.token:
                self.api.authenticate(OAuth2=True)
                if isinstance(self.token, str):
                    req.req.headers['Authorization'] = f'Bearer {self.token}'
                    warnings.warn(
                        'Passing an Access Token string directly is deprecated.'
                        'Doing so will Skip Validation of Scopes'
                        'Please use a Token object instead.',
                        DeprecationWarning,
                        stacklevel=2,
                    )
                else:
                    self._validate_token_scopes(self.token)
                    req.req.headers['Authorization'] = (
                        f'Bearer {self.token.valid_access_token()}'
                    )
            if etag:
                req.req.headers['If-None-Match'] = etag
            return req.request(
                data=self.body, parameters=self._reverse_normalize_params(parameters)
            )

        return retry(__func)

    def result(
        self,
        etag: str | None = None,
        return_response: bool = False,
        use_cache: bool = True,
        is_retry: bool = False,
        disable_etag: bool = False,
        **extra,
    ) -> tuple[Any, Response] | Any:
        self.token = self._extract_token_param()
        self.body = self._extract_body_param()
        parameters = self._kwargs | extra
        cache_key_base = self._cache_key()
        cache_key = f'{cache_key_base}'
        etag_key = f'{cache_key_base}:etag'

        # make sure that we have an etag if we are using the cache
        if not etag and not disable_etag and ESI_CACHE_RESPONSE:
            # etag = self._cache.get(etag_key).decode('ascii') if self._cache.get(etag_key) else None
            etag = self._cache.get(etag_key) if self._cache.get(etag_key) else None

        # always make the request, if we get a 304 we will use the cache
        try:
            headers, data, response = self._make_request(parameters, etag)
            # make sure that we hard stop on 420 since we are error limited
            if response.status_code == 420:
                reset = response.headers.get('X-RateLimit-Reset', None)
                self._cache.set('esi_error_limit_reset', reset, timeout=reset)
                raise ESIErrorLimitExceptionError(reset=reset)
        except base_HTTPServerError as e:
            raise HTTPServerError(
                status_code=e.status_code, headers=e.headers, data=e.data
            ) from e
        except base_HTTPClientError as e:
            raise HTTPClientError(
                status_code=e.status_code, headers=e.headers, data=e.data
            ) from e
        if response.status_code == 304:
            # Not modified, use cached data
            logger.debug('Received 304 Not Modified, using cached data')
            headers, data, response = self._get_cache(cache_key, etag=etag)
            if not response and not is_retry:
                logger.debug(
                    'Received 304 but no cached response found, forcing refetch without ETag'
                )
                return self.result(
                    etag=None,
                    return_response=return_response,
                    use_cache=use_cache,
                    is_retry=True,
                    disable_etag=True,
                    **extra,
                )
            if not response and is_retry:
                logger.debug(
                    'Received 304 but no cached response found on retry, raising 304'
                )
                raise HTTPNotModified(
                    status_code=304,
                    headers=response.headers,
                )
        if response and use_cache and ESI_CACHE_RESPONSE:
            self._store_cache(cache_key, response)

        return (data, response) if return_response else data

    def result_localized(self):
        # If we do implement localization, we need to insert the 'Accept-Language' header
        raise NotImplementedError

    def results(
        self,
        etag: str | None = None,
        return_response: bool = False,
        use_cache: bool = True,
        **extra,
    ) -> tuple[list[Any], Response | Any | None] | list[Any]:
        all_results: list[Any] = []
        last_response: Response | None = None

        if self._has_pages():
            current_page = 1
            total_pages = 1
            while current_page <= total_pages:
                self._kwargs['page'] = current_page
                data, response = self.result(
                    etag=etag, return_response=True, use_cache=use_cache, **extra
                )
                last_response = response
                all_results.extend(data if isinstance(data, list) else [data])
                total_pages = int(response.headers.get('X-Pages', '1'))
                logger.debug(
                    f'ESI Page Fetched {self.url} - {current_page}/{total_pages}'
                )
                current_page += 1
        else:
            data, response = self.result(
                etag=etag, return_response=True, use_cache=use_cache, **extra
            )
            all_results.extend(data if isinstance(data, list) else [data])
            last_response = response

        return (all_results, last_response) if return_response else all_results

    def results_localized(self):
        # If we do implement localization, we need to insert the 'Accept-Language' header
        raise NotImplementedError

    def required_scopes(self) -> list[str]:
        """
        Return a list of scopes required for this operation.
        """
        try:
            if not getattr(self.operation, 'security', None):
                return []  # No required scopes for this operation
            return list(
                getattr(getattr(self.operation, 'security', [])[0], 'root', {}).get(
                    'OAuth2', []
                )
            )
        except (IndexError, KeyError):
            return []


class ESITag:
    """
    API Tag wrapper to provide access to operations under a specific tag.
    """

    def __init__(self, operation, api) -> None:
        self._op_index = operation._oi
        self._operations = operation._operations
        self.api = api

    def __getattr__(self, name: str) -> ESIClientOperation:
        if name not in self._operations:
            msg = (
                f"Operation '{name}' not found in tag. ",
                f'Available operations: {", ".join(sorted(self._operations.keys()))}',
            )
            raise AttributeError(msg)
        return ESIClientOperation(self._operations[name], self.api)


class ESIClient(ESIClientStub):
    def __init__(self, api: OpenAPI) -> None:
        self.api: OpenAPI = api
        self._tags = set(api._operationindex._tags.keys())

    def __getattr__(self, tag: str) -> ESITag | OperationIndex:
        # underscore returns the raw aiopenapi3 client

        # TODO: check if this is needed
        if '_' in tag:
            tag = tag.replace('_', ' ')

        if tag == '_':
            return self.api._operationindex

        if tag in set(self.api._operationindex._tags.keys()):
            return ESITag(self.api._operationindex._tags[tag], self.api)

        msg = (
            f"Tag '{tag}' not found. ",
            f'Available tags: {", ".join(sorted(self._tags))}',
        )
        raise AttributeError(msg)


class ESIClientProvider:
    """
    Class to provide a single point of access to the ESI API client.
    """

    def __init__(self, **kwargs) -> None:
        self._kwargs = kwargs
        self._client: ESIClient | None = None

    @property
    def client(self) -> ESIClient:
        if self._client is None:
            api = _client_factory(**self._kwargs)
            self._client = ESIClient(api)
        return self._client

    def __str__(self) -> str:
        return 'ESIClientProvider'
