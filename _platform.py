"""Detect cluster capabilities that change how the app behaves.

Two facts matter to the frontend: whether this is OpenShift (so a Route can be
offered and ``openshift-*`` namespaces flagged) and whether the metrics API is
installed (so usage-based sizing is available instead of request-only).
"""

from __future__ import annotations

import logging

from kubernetes.client.exceptions import ApiException

from _k8s_client import ClusterClients
from _models import Platform

logger = logging.getLogger(__name__)

_OPENSHIFT_GROUPS = frozenset({"route.openshift.io", "apps.openshift.io"})
_METRICS_GROUP = "metrics.k8s.io"


def detect(clients: ClusterClients) -> Platform:
    """Probe API discovery once and summarise the cluster's capabilities."""
    groups = _api_group_names(clients)
    kind = "openshift" if groups & _OPENSHIFT_GROUPS else "kubernetes"
    return Platform(
        kind=kind,
        metrics_available=_METRICS_GROUP in groups,
        server_version=_server_version(clients),
    )


def _api_group_names(clients: ClusterClients) -> set[str]:
    try:
        groups = clients.dynamic.client.call_api(
            "/apis", "GET", auth_settings=["BearerToken"],
            response_type="V1APIGroupList", _return_http_data_only=True,
        )
        return {group.name for group in groups.groups}
    except ApiException as exc:
        logger.warning("API group discovery failed: %s", exc)
        return set()


def _server_version(clients: ClusterClients) -> str:
    try:
        info = clients.version.get_code()
        return info.git_version or ""
    except ApiException as exc:
        logger.warning("Server version lookup failed: %s", exc)
        return ""
