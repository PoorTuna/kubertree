"""Mutating endpoints: delete, scale, restart, rollout-undo, cordon, drain.

Every handler acts as the calling user (per-request clients), so the cluster's
RBAC — not the app — decides whether the action is allowed.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kubertree.auth._auth import require_user_clients
from kubertree.k8s._client import ClusterClients
from kubertree.k8s._target import ResourceError, ResourceTarget
from kubertree.tools._nodeops import drain, set_cordon
from kubertree.tools._resources import delete_resource
from kubertree.tools._workload import restart, rollout_undo, scale

router = APIRouter(prefix="/api")


class TargetRequest(BaseModel):
    apiVersion: str
    kind: str
    name: str
    namespace: str | None = None

    def target(self) -> ResourceTarget:
        return ResourceTarget(self.apiVersion, self.kind, self.name, self.namespace)


class ScaleRequest(TargetRequest):
    replicas: int


class NodeRequest(BaseModel):
    name: str


class CordonRequest(NodeRequest):
    on: bool = True


def _run(action: Callable[[], None]) -> None:
    try:
        action()
    except ResourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/delete")
def delete(request: TargetRequest, clients: ClusterClients = Depends(require_user_clients)) -> dict:
    _run(lambda: delete_resource(clients, request.target()))
    return {"deleted": True, "kind": request.kind, "name": request.name}


@router.post("/scale")
def scale_workload(
    request: ScaleRequest, clients: ClusterClients = Depends(require_user_clients)
) -> dict:
    _run(lambda: scale(clients, request.target(), request.replicas))
    return {"scaled": True, "name": request.name, "replicas": request.replicas}


@router.post("/restart")
def restart_workload(
    request: TargetRequest, clients: ClusterClients = Depends(require_user_clients)
) -> dict:
    _run(lambda: restart(clients, request.target()))
    return {"restarted": True, "name": request.name}


@router.post("/rollout-undo")
def undo_workload(
    request: TargetRequest, clients: ClusterClients = Depends(require_user_clients)
) -> dict:
    _run(lambda: rollout_undo(clients, request.target()))
    return {"undone": True, "name": request.name}


@router.post("/cordon")
def cordon_node(
    request: CordonRequest, clients: ClusterClients = Depends(require_user_clients)
) -> dict:
    _run(lambda: set_cordon(clients, request.name, request.on))
    return {"cordoned": request.on, "name": request.name}


@router.post("/drain")
def drain_node(
    request: NodeRequest, clients: ClusterClients = Depends(require_user_clients)
) -> dict:
    evicted: list[str] = []
    _run(lambda: evicted.extend(drain(clients, request.name)))
    return {"drained": True, "name": request.name, "evicted": evicted}
