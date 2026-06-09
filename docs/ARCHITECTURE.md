# Architecture

kubertree is a FastAPI backend that serves a static D3 frontend and a small JSON
API over a Kubernetes or OpenShift cluster. Every cluster call is made with the
calling user's credentials; the app holds no standing cluster powers.

## Package layout

```
kubertree/
  main.py            FastAPI app, lifespan, /api/health, /api/tree, router wiring
  _state.py          detected platform (probed once at startup)
  _platform.py       OpenShift / metrics-API detection
  auth/
    _auth.py         token -> per-user client, TTL cache, header/cookie extraction
    _access.py       SelfSubjectAccessReview capability checks
  k8s/
    _client.py       client bundle + in-cluster/kubeconfig bootstrap
    _models.py       TreeNode and value objects
    _metrics.py      metrics.k8s.io usage + quantity parsing
    _inventory.py    user-scoped pod listing + generic owner-reference climb
    _tree.py         hierarchy assembly (ownership / node grouping)
    _target.py       dynamic resource resolution
  tools/
    _inspect.py      logs, manifest (YAML), events
    _workload.py     scale, restart, rollout undo
    _nodeops.py      cordon / uncordon / drain
    _resources.py    cascade delete
    _exec.py         container shell stream
  api/
    _auth.py         /api/login, /api/logout, /api/whoami
    _inspect.py      /api/capabilities, /api/logs, /api/manifest, /api/events
    _actions.py      /api/delete, /api/scale, /api/restart, /api/rollout-undo, /api/cordon, /api/drain
    _exec.py         /api/exec (WebSocket)
  static/            D3 + vendored libraries, ES-module frontend
```

## Request flow

1. The browser loads `index.html`; `main.js` calls `/api/whoami`. Locally the
   kubeconfig identity is used and no login is shown; in-cluster a missing token
   yields 401 and the token-paste login appears (or oauth-proxy supplies it).
2. `/api/tree?group=owner|node` builds the hierarchy. `_inventory.list_pods`
   lists pods cluster-wide, falling back to per-namespace (or OpenShift projects)
   when the user lacks cluster-wide read. `_tree.build_tree` climbs each pod's
   ownerReference chain via the dynamic client and nests
   namespace → owner(s) → pod → container, merging metrics usage onto containers.
3. The frontend renders the same hierarchy two ways: a nested D3 treemap and a
   WizTree-style Explorer table (tree + flat).

## Auth flow

`auth/_auth.py` builds a `ClusterClients` from the user's bearer token (forwarded
header or session cookie), cloning the ambient API-server address and CA and
swapping only the credential. Built clients are cached by token hash with a short
TTL because constructing a `DynamicClient` performs API discovery. Before showing
a tool, the frontend calls `/api/capabilities`, which runs a
SelfSubjectAccessReview per relevant verb so disallowed actions are hidden.
