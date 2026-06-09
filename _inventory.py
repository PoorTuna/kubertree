"""List pods and resolve their full ownerReference chains generically.

The climb uses the dynamic client so it is agnostic to the owner kind: a chain
may be Pod->ReplicaSet->Deployment on Kubernetes, Pod->ReplicationController->
DeploymentConfig on OpenShift, or Pod->StatefulSet->CassandraDatacenter for an
operator CRD. Each owner object is fetched at most once (cached by UID).
"""

from __future__ import annotations

import logging

from kubernetes.client.models import V1OwnerReference, V1Pod
from kubernetes.dynamic.exceptions import DynamicApiError, ResourceNotFoundError

from _k8s_client import ClusterClients
from _models import OwnerRef

logger = logging.getLogger(__name__)


def list_pods(clients: ClusterClients) -> list[V1Pod]:
    """Return every pod in the cluster in a single API call."""
    return clients.core.list_pod_for_all_namespaces().items


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
        return _dynamic_controller_ref(getattr(obj.metadata, "ownerReferences", None), ref.namespace)


def _controller_ref(
    refs: list[V1OwnerReference] | None, namespace: str | None
) -> OwnerRef | None:
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
