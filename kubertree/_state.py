"""Process-wide facts shared by the app and its API routers.

Only the cluster's detected capabilities live here (probed once at startup).
Cluster access itself is per-user — see :mod:`_auth` — so no shared client is
held here.
"""

from __future__ import annotations

from kubertree.k8s._models import Platform


class AppState:
    """Holder for the detected platform and whether a cluster is reachable."""

    platform: Platform | None = None
    reachable: bool = False


state = AppState()
