# Changelog

## [Unreleased]

---

## 0.2.0

### Added
- **Explorer tab** — a WizTree-style table over the same hierarchy as the
  treemap, with a Tree view (expand/collapse, % of parent, efficiency) and a Flat
  view (every container by full path, sorted by size).
- **Functional tools** — logs, exec shell, scale, restart, rollout undo,
  cordon/uncordon, drain, and cascade delete, surfaced from the detail panel and a
  right-click context menu. Each is shown only if the user is allowed to run it
  (SelfSubjectAccessReview).
- **Per-user authentication** — the kubeconfig identity is used locally, a
  pasted bearer token (httpOnly session cookie) on vanilla Kubernetes, and the
  OpenShift `oauth-proxy` sidecar for SSO. In-cluster requests never fall back to
  the pod ServiceAccount.

### Changed
- Source moved into a `kubertree/` package (`auth`, `k8s`, `tools`, `api`).
- Reads are user-scoped: cluster-wide with a per-namespace / OpenShift-projects
  fallback.
- Helm chart moved to `helm/kubertree` with a `values.schema.json`; the broad
  ClusterRole was removed in favour of the oauth-proxy `system:auth-delegator`
  binding.
- Images now publish to Docker Hub.

### Tooling
- Added `pyproject.toml`, ruff, mypy, pre-commit, and CI (lint, tests, helm).

---

## 0.1.0
- Initial release: nested resource treemap for Kubernetes and OpenShift with
  ownership/node grouping, usage/request sizing, efficiency colouring, and cascade
  delete.
