"""Per-user authentication: build a Kubernetes client from the caller's token.

kubertree never acts as a shared admin. Each request carries the user's bearer
token — forwarded by the OpenShift ``oauth-proxy`` sidecar as
``X-Forwarded-Access-Token`` or, on vanilla Kubernetes, stored in an httpOnly
session cookie after a token-paste login. The cluster's own RBAC is the guard.

The base API server address and CA come from the ambient config (in-cluster SA
or local kubeconfig); only the credential is swapped per user. Built clients are
cached briefly because constructing a ``DynamicClient`` performs API discovery.
"""

from __future__ import annotations

import copy
import hashlib
import time
from collections import OrderedDict

from fastapi import HTTPException, Request
from kubernetes import client, config
from kubernetes.client import ApiClient, CoreV1Api, CustomObjectsApi, VersionApi
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException
from kubernetes.dynamic import DynamicClient

from kubertree.k8s._client import ClusterClients, ClusterConnectionError

SESSION_COOKIE = "kubertree_token"
_FORWARDED_TOKEN_HEADER = "x-forwarded-access-token"
_CACHE_TTL_SECONDS = 600
_CACHE_MAX_ENTRIES = 128

_base_config: client.Configuration | None = None
_local_mode = False
_clients_cache: OrderedDict[str, tuple[float, ClusterClients]] = OrderedDict()


class AuthError(RuntimeError):
    """Raised when a token is missing, invalid, or expired."""


def token_from_request(request: Request) -> str | None:
    """Return the caller's bearer token from the proxy header or session cookie."""
    forwarded = request.headers.get(_FORWARDED_TOKEN_HEADER)
    if forwarded:
        return forwarded.strip()
    cookie = request.cookies.get(SESSION_COOKIE)
    return cookie.strip() if cookie else None


def require_user_clients(request: Request) -> ClusterClients:
    """FastAPI dependency: per-request clients acting as the calling user.

    A forwarded/cookie token always wins. When running locally against a
    kubeconfig there is no separate login — the developer's own kubeconfig
    identity is used. In-cluster we never fall back to the pod ServiceAccount,
    so a real deployment is always per-user.
    """
    token = token_from_request(request)
    if token:
        return clients_for_token(token)
    if is_local_mode():
        return ambient_clients()
    raise HTTPException(status_code=401, detail="Not authenticated")


def is_local_mode() -> bool:
    """True when bound to a local kubeconfig rather than an in-cluster SA."""
    _ensure_base_config()
    return _local_mode


def clients_for_token(token: str) -> ClusterClients:
    """Return cached clients bound to ``token``, building them on first use."""
    key = hashlib.sha256(token.encode()).hexdigest()
    cached = _clients_cache.get(key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        _clients_cache.move_to_end(key)
        return cached[1]
    clients = _build_clients(_user_config(token))
    _clients_cache[key] = (time.monotonic(), clients)
    _clients_cache.move_to_end(key)
    while len(_clients_cache) > _CACHE_MAX_ENTRIES:
        _clients_cache.popitem(last=False)
    return clients


def ambient_clients() -> ClusterClients:
    """Clients from the ambient config — used only for startup capability probes."""
    return _build_clients(copy.deepcopy(_ensure_base_config()))


def validate_token(clients: ClusterClients) -> None:
    """Confirm a token is accepted by the API server, raising :class:`AuthError`.

    A SelfSubjectAccessReview is allowed for any authenticated identity, so a
    200/403 means the token is valid; only 401 means it is not.
    """
    try:
        client.AuthorizationV1Api(clients.api_client).create_self_subject_access_review(
            body=_access_review("get", "", "namespaces")
        )
    except ApiException as exc:
        if exc.status == 401:
            raise AuthError("Invalid or expired token") from exc
        raise AuthError(exc.reason or "Authentication check failed") from exc


def current_username(clients: ClusterClients) -> str:
    """Best-effort display name for the authenticated user."""
    try:
        review = client.AuthenticationV1Api(clients.api_client).create_self_subject_review(
            body=client.V1SelfSubjectReview()
        )
        return review.status.user_info.username or "authenticated"
    except (ApiException, AttributeError):
        return "authenticated"


def _user_config(token: str) -> client.Configuration:
    cfg = copy.deepcopy(_ensure_base_config())
    cfg.api_key = {"authorization": f"Bearer {token}"}
    cfg.api_key_prefix = {}
    cfg.cert_file = None
    cfg.key_file = None
    return cfg


def _ensure_base_config() -> client.Configuration:
    global _base_config, _local_mode
    if _base_config is None:
        try:
            config.load_incluster_config()
        except ConfigException:
            try:
                config.load_kube_config()
                _local_mode = True
            except ConfigException as exc:
                raise ClusterConnectionError(
                    "No in-cluster config and no usable ~/.kube/config found"
                ) from exc
        _base_config = client.Configuration.get_default_copy()
    return _base_config


def _build_clients(cfg: client.Configuration) -> ClusterClients:
    api_client = ApiClient(cfg)
    return ClusterClients(
        api_client=api_client,
        core=CoreV1Api(api_client),
        custom_objects=CustomObjectsApi(api_client),
        dynamic=DynamicClient(api_client),
        version=VersionApi(api_client),
    )


def _access_review(verb: str, group: str, resource: str) -> client.V1SelfSubjectAccessReview:
    attributes = client.V1ResourceAttributes(verb=verb, group=group, resource=resource)
    return client.V1SelfSubjectAccessReview(
        spec=client.V1SelfSubjectAccessReviewSpec(resource_attributes=attributes)
    )
