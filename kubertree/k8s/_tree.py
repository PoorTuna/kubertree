"""Assemble pods, usage and ownership into the hierarchy sent to the client.

The resolver is injected as a callable so the builder can be unit-tested with
synthetic chains and without a cluster.
"""

from __future__ import annotations

from collections.abc import Callable

from kubernetes.client.models import V1Container, V1Pod

from kubertree.k8s._metrics import PodUsage, cpu_to_milli, memory_to_bytes
from kubertree.k8s._models import OwnerRef, Requests, TreeNode, Usage

ChainResolver = Callable[[V1Pod], list[OwnerRef]]


def build_tree(
    pods: list[V1Pod],
    usage: PodUsage,
    resolve_chain: ChainResolver,
    group_by: str = "owner",
) -> TreeNode:
    """Build the resource hierarchy, grouped by ownership or by physical node.

    ``group_by="owner"``: cluster -> namespace -> owner chain -> pod -> container.
    ``group_by="node"``: cluster -> node -> (the same namespace/owner subtree).
    """
    root = TreeNode(name="cluster", kind="Cluster")
    for pod in pods:
        start = _group_root(root, pod, group_by)
        pod_node = _place_pod(start, pod, resolve_chain)
        _add_containers(pod_node, pod, usage.get((pod.metadata.namespace, pod.metadata.name), {}))
    return root


def _group_root(root: TreeNode, pod: V1Pod, group_by: str) -> TreeNode:
    if group_by != "node":
        return root
    node_name = pod.spec.node_name or "(unscheduled)"
    return root.child(node_name, lambda: TreeNode(name=node_name, kind="Node"))


def _place_pod(start: TreeNode, pod: V1Pod, resolve_chain: ChainResolver) -> TreeNode:
    namespace = pod.metadata.namespace
    parent = start.child(
        namespace,
        lambda: TreeNode(name=namespace, kind="Namespace", namespace=namespace, deletable=True),
    )
    for ref in resolve_chain(pod):
        parent = parent.child(ref.uid, _owner_factory(ref))
    return parent.child(pod.metadata.uid, _pod_factory(pod))


def _owner_factory(ref: OwnerRef) -> Callable[[], TreeNode]:
    return lambda: TreeNode(
        name=ref.name,
        kind=ref.kind,
        namespace=ref.namespace,
        uid=ref.uid,
        api_version=ref.api_version,
        deletable=True,
    )


def _pod_factory(pod: V1Pod) -> Callable[[], TreeNode]:
    return lambda: TreeNode(
        name=pod.metadata.name,
        kind="Pod",
        namespace=pod.metadata.namespace,
        uid=pod.metadata.uid,
        api_version="v1",
        deletable=True,
    )


def _add_containers(pod_node: TreeNode, pod: V1Pod, container_usage: dict[str, Usage]) -> None:
    requests = {container.name: _container_requests(container) for container in pod.spec.containers}
    for name in requests.keys() | container_usage.keys():
        used = container_usage.get(name, Usage())
        requested = requests.get(name, Requests())
        pod_node.children[name] = TreeNode(
            name=name,
            kind="Container",
            namespace=pod_node.namespace,
            cpu_usage=used.cpu_milli,
            mem_usage=used.mem_bytes,
            cpu_request=requested.cpu_milli,
            mem_request=requested.mem_bytes,
        )


def _container_requests(container: V1Container) -> Requests:
    resources = getattr(container, "resources", None)
    requested = getattr(resources, "requests", None) or {}
    return Requests(
        cpu_milli=cpu_to_milli(requested["cpu"]) if "cpu" in requested else 0.0,
        mem_bytes=memory_to_bytes(requested["memory"]) if "memory" in requested else 0.0,
    )
