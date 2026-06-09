"""Domain data containers shared across the backend.

These are plain value objects with no Kubernetes-client knowledge so the tree
builder and tests can construct them without a live cluster.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PlatformKind = Literal["openshift", "kubernetes"]


@dataclass(frozen=True)
class Usage:
    """Observed resource consumption of a container (from metrics.k8s.io)."""

    cpu_milli: float = 0.0
    mem_bytes: float = 0.0


@dataclass(frozen=True)
class Requests:
    """Requested resources of a container (from the pod spec)."""

    cpu_milli: float = 0.0
    mem_bytes: float = 0.0


@dataclass(frozen=True)
class OwnerRef:
    """A single link in a Kubernetes ownerReference chain."""

    api_version: str
    kind: str
    name: str
    uid: str
    namespace: str | None = None


@dataclass(frozen=True)
class Platform:
    """Capabilities of the connected cluster, detected once at startup."""

    kind: PlatformKind
    metrics_available: bool
    server_version: str = ""

    @property
    def is_openshift(self) -> bool:
        return self.kind == "openshift"


@dataclass
class TreeNode:
    """A node in the resource hierarchy emitted to the frontend.

    Leaves are containers carrying usage/request values; intermediate nodes
    (namespace, owners, pod) carry metadata only and let the client sum leaves.
    """

    name: str
    kind: str
    namespace: str | None = None
    uid: str | None = None
    api_version: str | None = None
    cpu_usage: float = 0.0
    mem_usage: float = 0.0
    cpu_request: float = 0.0
    mem_request: float = 0.0
    deletable: bool = False
    children: dict[str, "TreeNode"] = field(default_factory=dict)

    def child(self, key: str, factory) -> "TreeNode":
        """Return the child stored under ``key``, creating it via ``factory`` once."""
        node = self.children.get(key)
        if node is None:
            node = factory()
            self.children[key] = node
        return node

    def to_dict(self) -> dict:
        node: dict = {
            "name": self.name,
            "kind": self.kind,
            "namespace": self.namespace,
            "uid": self.uid,
            "apiVersion": self.api_version,
            "deletable": self.deletable,
        }
        if self.children:
            node["children"] = [child.to_dict() for child in self.children.values()]
        else:
            node["cpuUsage"] = self.cpu_usage
            node["memUsage"] = self.mem_usage
            node["cpuRequest"] = self.cpu_request
            node["memRequest"] = self.mem_request
        return node
