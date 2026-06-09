"""List pods and resolve their full ownerReference chains generically.

The climb uses the dynamic client so it is agnostic to the owner kind: a chain
may be Pod->ReplicaSet->Deployment on Kubernetes, Pod->ReplicationController->
DeploymentConfig on OpenShift, or Pod->StatefulSet->CassandraDatacenter for an
operator CRD. Each owner object is fetched at most once (cached by UID).
"""

from __future__ import annotations

import logging

from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1OwnerReference, V1Pod
from kubernetes.dynamic.exceptions import DynamicApiError, ResourceNotFoundError

from kubertree.k8s._client import ClusterClients
from kubertree.k8s._models import OwnerRef

logger = logging.getLogger(__name__)

_FORBIDDEN = 403
_PROJECT_API = "project.openshift.io/v1"


def list_pods(clients: ClusterClients) -> list[V1Pod]:
    """Return the pods the user can read, cluster-wide or per visible namespace.

    A cluster-admin lists every pod in one call; a namespaced user, denied the
    cluster-wide list, gets only the pods in the namespaces they can read.
    """
    try:
        return clients.core.list_pod_for_all_namespaces().items
    except ApiException as exc:
        if exc.status != _FORBIDDEN:
            raise
    pods: list[V1Pod] = []
    for namespace in _readable_namespaces(clients):
        try:
            pods.extend(clients.core.list_namespaced_pod(namespace).items)
        except ApiException as exc:
            logger.debug("Skipping namespace %s: %s", namespace, exc)
    return pods


def list_node_capacity(clients: ClusterClients) -> dict[str, tuple[float, float]]:
    """Return allocatable ``(cpu_milli, mem_bytes)`` per node name the user can see."""
    from kubertree.k8s._metrics import cpu_to_milli, memory_to_bytes

    try:
        nodes = clients.core.list_node().items
    except ApiException as exc:
        logger.debug("Node capacity unavailable: %s", exc)
        return {}
    capacity: dict[str, tuple[float, float]] = {}
    for node in nodes:
        allocatable = node.status.allocatable or {}
        capacity[node.metadata.name] = (
            cpu_to_milli(allocatable["cpu"]) if "cpu" in allocatable else 0.0,
            memory_to_bytes(allocatable["memory"]) if "memory" in allocatable else 0.0,
        )
    return capacity


def _readable_namespaces(clients: ClusterClients) -> list[str]:
    try:
        return [ns.metadata.name for ns in clients.core.list_namespace().items]
    except ApiException as exc:
        logger.debug("Namespace list denied, trying OpenShift projects: %s", exc)
        return _openshift_projects(clients)


def _openshift_projects(clients: ClusterClients) -> list[str]:
    try:
        resource = clients.dynamic.resources.get(api_version=_PROJECT_API, kind="Project")
        return [item["metadata"]["name"] for item in resource.get().to_dict()["items"]]
    except (ResourceNotFoundError, DynamicApiError) as exc:
        logger.debug("Project discovery failed: %s", exc)
        return []


class OwnerResolver:
    """Resolves a pod to its ancestor chain, root first, caching by owner UID."""

    def __init__(self, clients: ClusterClients) -> None:
        self._clients = clients
        self._parent_by_uid: dict[str, OwnerRef | None] = {}

    def resolve_chain(self, pod: V1Pod) -> list[OwnerRef]:
        namespace = pod.metadata.namespace
        chain: list[OwnerRef] = []
        seen: set[str] = set()
        current = _controller_ref(pod.metadata.owner_references, namespace)
        while current is not None and current.uid not in seen:
            seen.add(current.uid)
            chain.append(current)
            current = self._parent_of(current)
        chain.reverse()
        return chain

    def _parent_of(self, ref: OwnerRef) -> OwnerRef | None:
        if ref.uid in self._parent_by_uid:
            return self._parent_by_uid[ref.uid]
        parent = self._fetch_parent(ref)
        self._parent_by_uid[ref.uid] = parent
        return parent

    def _fetch_parent(self, ref: OwnerRef) -> OwnerRef | None:
        try:
            resource = self._clients.dynamic.resources.get(
                api_version=ref.api_version, kind=ref.kind
            )
            obj = (
                resource.get(name=ref.name, namespace=ref.namespace)
                if resource.namespaced
                else resource.get(name=ref.name)
            )
        except (ResourceNotFoundError, DynamicApiError) as exc:
            logger.debug("Owner %s/%s unresolved: %s", ref.kind, ref.name, exc)
            return None
        return _dynamic_controller_ref(
            getattr(obj.metadata, "ownerReferences", None), ref.namespace
        )


def _controller_ref(refs: list[V1OwnerReference] | None, namespace: str | None) -> OwnerRef | None:
    """Pick the controlling owner (or first) from a typed pod's references."""
    if not refs:
        return None
    chosen = next((ref for ref in refs if ref.controller), refs[0])
    return OwnerRef(
        api_version=chosen.api_version,
        kind=chosen.kind,
        name=chosen.name,
        uid=chosen.uid,
        namespace=namespace,
    )


def _dynamic_controller_ref(refs, namespace: str | None) -> OwnerRef | None:
    """Pick the controlling owner from a dynamic object's references."""
    if not refs:
        return None
    chosen = next((ref for ref in refs if getattr(ref, "controller", False)), refs[0])
    return OwnerRef(
        api_version=chosen.apiVersion,
        kind=chosen.kind,
        name=chosen.name,
        uid=chosen.uid,
        namespace=namespace,
    )
