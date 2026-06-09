"""Node operations: cordon/uncordon and drain.

Drain cordons the node, then evicts every pod on it except DaemonSet-managed and
static (mirror) pods, which a drain cannot meaningfully move.
"""

from __future__ import annotations

from kubernetes.client import V1DeleteOptions, V1Eviction, V1ObjectMeta
from kubernetes.client.exceptions import ApiException

from _k8s_client import ClusterClients
from _target import ResourceError

_MIRROR_ANNOTATION = "kubernetes.io/config.mirror"


def set_cordon(clients: ClusterClients, node: str, on: bool) -> None:
    """Mark ``node`` (un)schedulable."""
    try:
        clients.core.patch_node(node, {"spec": {"unschedulable": on}})
    except ApiException as exc:
        raise ResourceError(_reason(exc, "patch node failed")) from exc


def drain(clients: ClusterClients, node: str) -> list[str]:
    """Cordon ``node`` and evict its movable pods; return the evicted pod names."""
    set_cordon(clients, node, True)
    evicted: list[str] = []
    for pod in _pods_on_node(clients, node):
        if _is_unmovable(pod):
            continue
        _evict(clients, pod)
        evicted.append(pod.metadata.name)
    return evicted


def _pods_on_node(clients: ClusterClients, node: str):
    pods = clients.core.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node}")
    return pods.items


def _is_unmovable(pod) -> bool:
    if any(ref.kind == "DaemonSet" for ref in (pod.metadata.owner_references or [])):
        return True
    return _MIRROR_ANNOTATION in (pod.metadata.annotations or {})


def _evict(clients: ClusterClients, pod) -> None:
    eviction = V1Eviction(
        metadata=V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace),
        delete_options=V1DeleteOptions(),
    )
    try:
        clients.core.create_namespaced_pod_eviction(
            name=pod.metadata.name, namespace=pod.metadata.namespace, body=eviction
        )
    except ApiException as exc:
        raise ResourceError(_reason(exc, "eviction failed")) from exc


def _reason(exc: ApiException, fallback: str) -> str:
    return exc.reason or fallback
