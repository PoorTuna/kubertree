"""Live container usage from the metrics API and quantity parsing helpers.

Sizing falls back to requested resources when the metrics API is absent, so
fetching usage is best-effort: failures yield an empty map rather than raising.
"""

from __future__ import annotations

import logging

from kubernetes.client.exceptions import ApiException
from kubernetes.utils.quantity import parse_quantity

from _k8s_client import ClusterClients
from _models import Usage

logger = logging.getLogger(__name__)

_METRICS_GROUP = "metrics.k8s.io"
_METRICS_VERSION = "v1beta1"
_MILLI_PER_CORE = 1000

ContainerUsage = dict[str, Usage]
PodUsage = dict[tuple[str, str], ContainerUsage]


def cpu_to_milli(quantity: str) -> float:
    """Convert a CPU quantity string (e.g. ``"250m"``, ``"1"``) to millicores."""
    return float(parse_quantity(quantity)) * _MILLI_PER_CORE


def memory_to_bytes(quantity: str) -> float:
    """Convert a memory quantity string (e.g. ``"128Mi"``, ``"1Gi"``) to bytes."""
    return float(parse_quantity(quantity))


def fetch_pod_usage(clients: ClusterClients) -> PodUsage:
    """Return per-container usage keyed by ``(namespace, pod_name)``.

    Returns an empty map when the metrics API is unavailable or errors.
    """
    try:
        response = clients.custom_objects.list_cluster_custom_object(
            _METRICS_GROUP, _METRICS_VERSION, "pods"
        )
    except ApiException as exc:
        logger.warning("Metrics API unavailable: %s", exc)
        return {}

    usage: PodUsage = {}
    for item in response.get("items", []):
        metadata = item.get("metadata", {})
        key = (metadata.get("namespace", ""), metadata.get("name", ""))
        usage[key] = {
            container["name"]: _container_usage(container)
            for container in item.get("containers", [])
        }
    return usage


def _container_usage(container: dict) -> Usage:
    resources = container.get("usage", {})
    return Usage(
        cpu_milli=cpu_to_milli(resources.get("cpu", "0")),
        mem_bytes=memory_to_bytes(resources.get("memory", "0")),
    )
