"""Resolve an arbitrary cluster object through the dynamic client.

Delete, scale, restart, rollout-undo, and manifest read all begin the same way:
name a single object (apiVersion/kind/name/namespace) and look up its dynamic
``Resource``. Sharing that step keeps the action modules small and consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from kubernetes.dynamic import Resource
from kubernetes.dynamic.exceptions import ResourceNotFoundError

from kubertree.k8s._client import ClusterClients


class ResourceError(RuntimeError):
    """Raised when a named resource cannot be resolved or mutated."""


@dataclass(frozen=True)
class ResourceTarget:
    """Identifies a single Kubernetes object to act on."""

    api_version: str
    kind: str
    name: str
    namespace: str | None = None


def get_resource(clients: ClusterClients, target: ResourceTarget) -> Resource:
    """Return the dynamic ``Resource`` for ``target`` or raise :class:`ResourceError`."""
    try:
        return clients.dynamic.resources.get(api_version=target.api_version, kind=target.kind)
    except ResourceNotFoundError as exc:
        raise ResourceError(f"Unknown resource {target.api_version}/{target.kind}") from exc
