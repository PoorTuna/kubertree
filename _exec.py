"""Open an interactive shell stream into a container via the exec subresource.

Returns the raw (non-preloaded) WebSocket client from the Kubernetes library;
the API layer bridges it to the browser's WebSocket. ``/bin/bash`` is preferred
with a fallback to ``/bin/sh`` for minimal images.
"""

from __future__ import annotations

from kubernetes.stream import stream

from _k8s_client import ClusterClients

_SHELL_COMMAND = ["/bin/sh", "-c", "exec /bin/bash 2>/dev/null || exec /bin/sh"]


def open_shell(clients: ClusterClients, namespace: str, pod: str, container: str | None):
    """Return an open, non-preloaded exec WebSocket client for ``pod``."""
    return stream(
        clients.core.connect_get_namespaced_pod_exec,
        pod,
        namespace,
        container=container,
        command=_SHELL_COMMAND,
        stderr=True,
        stdin=True,
        stdout=True,
        tty=True,
        _preload_content=False,
    )
