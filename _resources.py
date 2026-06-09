"""Cascade-delete a resource by letting Kubernetes garbage-collect its children.

Foreground propagation removes owned objects before the parent, so deleting a
Deployment (or DeploymentConfig, StatefulSet, or operator CRD) also removes its
ReplicaSets/Pods. No manual recursion is needed — ownerReferences drive it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kubernetes.dynamic.exceptions import DynamicApiError, NotFoundError, ResourceNotFoundError

from _k8s_client import ClusterClients

logger = logging.getLogger(__name__)

_FOREGROUND = "Foreground"


class DeleteError(RuntimeError):
    """Raised when a delete request cannot be served."""


@dataclass(frozen=True)
class DeleteTarget:
    api_version: str
    kind: str
    name: str
    namespace: str | None = None


def delete_resource(clients: ClusterClients, target: DeleteTarget) -> None:
    """Delete ``target`` with foreground cascade so owned children go with it."""
    try:
        resource = clients.dynamic.resources.get(
            api_version=target.api_version, kind=target.kind
        )
    except ResourceNotFoundError as exc:
        raise DeleteError(f"Unknown resource {target.api_version}/{target.kind}") from exc

    body = {"propagationPolicy": _FOREGROUND}
    try:
        resource.delete(name=target.name, namespace=target.namespace, body=body)
    except NotFoundError as exc:
        raise DeleteError(f"{target.kind} {target.name} not found") from exc
    except DynamicApiError as exc:
        raise DeleteError(exc.summary()) from exc

    logger.info("Deleted %s %s (ns=%s)", target.kind, target.name, target.namespace)
