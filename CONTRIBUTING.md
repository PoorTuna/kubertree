# Contributing

## Setup

```bash
git clone https://github.com/PoorTuna/kubertree.git
cd kubertree
pip install -e ".[dev]"
pre-commit install
```

Run locally against your kubeconfig:

```bash
python -m kubertree     # http://127.0.0.1:8000
```

## Code

- Python 3.11+, checked by ruff and mypy.
- Modules stay under ~300 lines; split by responsibility when they grow.
- Entry points get clean names; internal modules are `_`-prefixed.
- Package layout: `kubertree/{auth,k8s,tools,api}` — see `docs/ARCHITECTURE.md`.
- Tests live in `tests/unit/<area>/` mirroring the source tree.

## Checks

```bash
ruff check . && ruff format --check .
mypy kubertree/
pytest tests/unit
helm lint helm/kubertree
```

## Frontend

Vanilla ES modules under `kubertree/static/js`; D3 and xterm.js are vendored in
`kubertree/static/vendor` (no CDN, airgap-friendly). No build step.
