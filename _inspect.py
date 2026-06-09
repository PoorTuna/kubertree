"""Read-only inspection: container logs, object manifest (YAML), recent events.

These never mutate the cluster; they back the Logs / YAML / Events tools in the
UI. All failures surface as :class:`ResourceError` so the routers map them to a
single 400 response shape.
"""

from __future__ import annotations

import yaml
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic.exceptions import DynamicApiError, NotFoundError

from _k8s_client import ClusterClients
from _target import ResourceError, ResourceTarget, get_resource

_DROPPED_METADATA = ("managedFields",)


def read_logs(
    clients: ClusterClients,
    namespace: str,
    pod: str,
    container: str | None = None,
    tail: int = 200,
    previous: bool = False,
) -> str:
    """Return the tail of a container's log as plain text."""
    try:
        return clients.core.read_namespaced_pod_log(
            name=pod,
            namespace=namespace,
            container=container,
            tail_lines=tail,
            previous=previous,
        )
    except ApiException as exc:
        raise ResourceError(_reason(exc)) from exc


def read_manifest(clients: ClusterClients, target: ResourceTarget) -> str:
    """Return ``target``'s live manifest as YAML, minus noisy ``managedFields``."""
    resource = get_resource(clients, target)
    try:
        obj = (
            resource.get(name=target.name, namespace=target.namespace)
            if resource.namespaced
            else resource.get(name=target.name)
        )
    except NotFoundError as exc:
        raise ResourceError(f"{target.kind} {target.name} not found") from exc
    except DynamicApiError as exc:
        raise ResourceError(exc.summary()) from exc
    return yaml.safe_dump(_strip_noise(obj.to_dict()), sort_keys=False)


def list_events(clients: ClusterClients, namespace: str, name: str) -> list[dict]:
    """Return events whose involvedObject matches ``name`` in ``namespace``."""
    try:
        events = clients.core.list_namespaced_event(
            namespace=namespace, field_selector=f"involvedObject.name={name}"
        )
    except ApiException as exc:
        raise ResourceError(_reason(exc)) from exc
    return [_event_dict(event) for event in events.items]


def _strip_noise(obj: dict) -> dict:
    metadata = obj.get("metadata")
    if isinstance(metadata, dict):
        for key in _DROPPED_METADATA:
            metadata.pop(key, None)
    return obj


def _event_dict(event) -> dict:
    timestamp = event.last_timestamp or event.event_time
    return {
        "type": event.type,
        "reason": event.reason,
        "message": event.message,
        "count": event.count,
        "lastTimestamp": timestamp.isoformat() if timestamp else None,
    }


def _reason(exc: ApiException) -> str:
    return exc.reason or "Kubernetes API error"
