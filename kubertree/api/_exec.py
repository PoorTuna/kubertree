"""WebSocket endpoint bridging the browser terminal to a container shell.

The Kubernetes exec client is synchronous, so its blocking reads/writes run in a
thread executor while two coroutines pump bytes in each direction. Either side
closing tears the bridge down.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from kubernetes.client.exceptions import ApiException

from kubertree.auth._auth import (
    ambient_clients,
    clients_for_token,
    is_local_mode,
    token_from_request,
)
from kubertree.tools._exec import open_shell

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_READ_TIMEOUT = 1.0


@router.websocket("/exec")
async def exec_shell(
    websocket: WebSocket, namespace: str, pod: str, container: str | None = None
) -> None:
    await websocket.accept()
    token = token_from_request(websocket)
    if token:
        clients = clients_for_token(token)
    elif is_local_mode():
        clients = ambient_clients()
    else:
        await websocket.close(code=1008, reason="Not authenticated")
        return
    try:
        shell = open_shell(clients, namespace, pod, container)
    except ApiException as exc:
        await websocket.send_text(f"\r\nexec failed: {exc.reason}\r\n")
        await websocket.close()
        return
    await _bridge(websocket, shell)


async def _bridge(websocket: WebSocket, shell) -> None:
    loop = asyncio.get_event_loop()
    browser_to_pod = asyncio.create_task(_browser_to_pod(websocket, shell, loop))
    pod_to_browser = asyncio.create_task(_pod_to_browser(websocket, shell, loop))
    _, pending = await asyncio.wait(
        {browser_to_pod, pod_to_browser}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    shell.close()


async def _browser_to_pod(websocket: WebSocket, shell, loop) -> None:
    try:
        while True:
            data = await websocket.receive_text()
            await loop.run_in_executor(None, shell.write_stdin, data)
    except WebSocketDisconnect:
        pass


async def _pod_to_browser(websocket: WebSocket, shell, loop) -> None:
    while shell.is_open():
        await loop.run_in_executor(None, shell.update, _READ_TIMEOUT)
        if shell.peek_stdout():
            await websocket.send_text(shell.read_stdout())
        if shell.peek_stderr():
            await websocket.send_text(shell.read_stderr())
    await websocket.close()
