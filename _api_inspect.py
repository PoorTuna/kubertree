"""Read-only endpoints: capabilities, logs, manifest, events."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from _access import capabilities
from _auth import require_user_clients
from _inspect import list_events, read_logs, read_manifest
from _k8s_client import ClusterClients
from _target import ResourceError, ResourceTarget

router = APIRouter(prefix="/api")


@router.get("/capabilities")
def get_capabilities(
    apiVersion: str,
    kind: str,
    name: str = "",
    namespace: str | None = None,
    clients: ClusterClients = Depends(require_user_clients),
) -> dict:
    target = ResourceTarget(apiVersion, kind, name, namespace)
    return capabilities(clients, target)


@router.get("/logs")
def logs(
    namespace: str,
    pod: str,
    container: str | None = None,
    tail: int = 200,
    previous: bool = False,
    clients: ClusterClients = Depends(require_user_clients),
) -> dict:
    try:
        text = read_logs(clients, namespace, pod, container, tail, previous)
    except ResourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"logs": text}


@router.get("/manifest")
def manifest(
    apiVersion: str,
    kind: str,
    name: str,
    namespace: str | None = None,
    clients: ClusterClients = Depends(require_user_clients),
) -> dict:
    target = ResourceTarget(apiVersion, kind, name, namespace)
    try:
        return {"yaml": read_manifest(clients, target)}
    except ResourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/events")
def events(
    namespace: str,
    name: str,
    clients: ClusterClients = Depends(require_user_clients),
) -> dict:
    try:
        return {"events": list_events(clients, namespace, name)}
    except ResourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
