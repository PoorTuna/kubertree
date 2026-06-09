"""kubertree — a WizTree-style treemap for Kubernetes and OpenShift.

Run locally with ``python app.py`` (uses ~/.kube/config) or in-cluster via the
Helm chart. Serves the D3 frontend and a small JSON API over the cluster.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import _platform
from _inventory import OwnerResolver, list_pods
from _k8s_client import ClusterClients, ClusterConnectionError, load_clients
from _metrics import fetch_pod_usage
from _models import Platform
from _resources import DeleteError, DeleteTarget, delete_resource
from _tree import build_tree

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kubertree")

_STATIC_DIR = Path(__file__).parent / "static"


class _State:
    clients: ClusterClients | None = None
    platform: Platform | None = None


state = _State()


class DeleteRequest(BaseModel):
    apiVersion: str
    kind: str
    name: str
    namespace: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state.clients = load_clients()
        state.platform = _platform.detect(state.clients)
        logger.info("Connected: %s, metrics=%s", state.platform.kind, state.platform.metrics_available)
    except ClusterConnectionError as exc:
        logger.error("No cluster connection: %s", exc)
    yield


app = FastAPI(title="kubertree", lifespan=lifespan)


def _require_clients() -> ClusterClients:
    if state.clients is None:
        raise HTTPException(status_code=503, detail="No cluster connection")
    return state.clients


@app.get("/api/health")
def health() -> dict:
    if state.clients is None or state.platform is None:
        return {"reachable": False, "platform": None, "metricsAvailable": False, "version": ""}
    return {
        "reachable": True,
        "platform": state.platform.kind,
        "metricsAvailable": state.platform.metrics_available,
        "version": state.platform.server_version,
    }


@app.get("/api/tree")
def tree() -> dict:
    clients = _require_clients()
    platform = state.platform
    usage = fetch_pod_usage(clients) if platform and platform.metrics_available else {}
    resolver = OwnerResolver(clients)
    root = build_tree(list_pods(clients), usage, resolver.resolve_chain)
    return {
        "platform": platform.kind if platform else "kubernetes",
        "metricsAvailable": bool(platform and platform.metrics_available),
        "tree": root.to_dict(),
    }


@app.post("/api/delete")
def delete(request: DeleteRequest) -> dict:
    clients = _require_clients()
    target = DeleteTarget(
        api_version=request.apiVersion,
        kind=request.kind,
        name=request.name,
        namespace=request.namespace,
    )
    try:
        delete_resource(clients, target)
    except DeleteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True, "kind": request.kind, "name": request.name}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def main() -> None:
    host = os.environ.get("KUBERTREE_HOST", "127.0.0.1")
    port = int(os.environ.get("KUBERTREE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
