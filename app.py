"""kubertree — a WizTree-style treemap for Kubernetes and OpenShift.

Run locally with ``python app.py`` (uses ~/.kube/config) or in-cluster via the
Helm chart. Serves the D3 frontend and a small JSON API over the cluster.

Every cluster call is made as the requesting user (see :mod:`_auth`); the app
itself holds no standing cluster powers. Only capability discovery at startup
uses the ambient config, and only for read-only API discovery.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import _api_actions
import _api_auth
import _api_exec
import _api_inspect
import _platform
from _auth import ambient_clients, require_user_clients
from _inventory import OwnerResolver, list_node_capacity, list_pods
from _k8s_client import ClusterClients, ClusterConnectionError
from _metrics import fetch_pod_usage
from _state import state
from _tree import build_tree

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kubertree")

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state.platform = _platform.detect(ambient_clients())
        state.reachable = True
        logger.info("Connected: %s, metrics=%s", state.platform.kind, state.platform.metrics_available)
    except ClusterConnectionError as exc:
        logger.error("No ambient cluster config for capability probe: %s", exc)
    yield


app = FastAPI(title="kubertree", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    if state.platform is None:
        return {"reachable": False, "platform": None, "metricsAvailable": False, "version": ""}
    return {
        "reachable": state.reachable,
        "platform": state.platform.kind,
        "metricsAvailable": state.platform.metrics_available,
        "version": state.platform.server_version,
    }


@app.get("/api/tree")
def tree(group: str = "owner", clients: ClusterClients = Depends(require_user_clients)) -> dict:
    if group not in ("owner", "node"):
        raise HTTPException(status_code=400, detail="group must be 'owner' or 'node'")
    platform = state.platform
    usage = fetch_pod_usage(clients) if platform and platform.metrics_available else {}
    resolver = OwnerResolver(clients)
    root = build_tree(list_pods(clients), usage, resolver.resolve_chain, group_by=group)
    capacity = {name: {"cpu": cpu, "mem": mem} for name, (cpu, mem) in list_node_capacity(clients).items()}
    return {
        "platform": platform.kind if platform else "kubernetes",
        "metricsAvailable": bool(platform and platform.metrics_available),
        "group": group,
        "nodeCapacity": capacity,
        "tree": root.to_dict(),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


app.include_router(_api_auth.router)
app.include_router(_api_inspect.router)
app.include_router(_api_actions.router)
app.include_router(_api_exec.router)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def main() -> None:
    host = os.environ.get("KUBERTREE_HOST", "127.0.0.1")
    port = int(os.environ.get("KUBERTREE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
