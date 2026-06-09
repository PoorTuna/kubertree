"""Cascade-delete a resource by letting Kubernetes garbage-collect its children.

Foreground propagation removes owned objects before the parent, so deleting a
Deployment (or DeploymentConfig, StatefulSet, or operator CRD) also removes its
ReplicaSets/Pods. No manual recursion is needed — ownerReferences drive it.
"""

from __future__ import annotations

import logging

from kubernetes.dynamic.exceptions import DynamicApiError, NotFoundError

from _k8s_client import ClusterClients
from _target import ResourceError, ResourceTarget, get_resource

logger = logging.getLogger(__name__)

_FOREGROUND = "Foreground"


def delete_resource(clients: ClusterClients, target: ResourceTarget) -> None:
    """Delete ``target`` with foreground cascade so owned children go with it."""
    resource = get_resource(clients, target)
    body = {"propagationPolicy": _FOREGROUND}
    try:
        resource.delete(name=target.name, namespace=target.namespace, body=body)
    except NotFoundError as exc:
        raise ResourceError(f"{target.kind} {target.name} not found") from exc
    except DynamicApiError as exc:
        raise ResourceError(exc.summary()) from exc

    logger.info("Deleted %s %s (ns=%s)", target.kind, target.name, target.namespace)
