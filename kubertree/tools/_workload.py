"""Workload mutations: scale replicas, rollout restart, rollout undo.

Scale and restart are merge patches. Undo is best-effort: it re-applies the pod
template of the previous ReplicaSet, mirroring ``kubectl rollout undo`` for
Deployments. All failures surface as :class:`ResourceError`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from kubernetes.dynamic.exceptions import DynamicApiError, NotFoundError

from kubertree.k8s._client import ClusterClients
from kubertree.k8s._target import ResourceError, ResourceTarget, get_resource

_MERGE_PATCH = "application/merge-patch+json"
_RESTART_ANNOTATION = "kubertree.io/restartedAt"
_REVISION_ANNOTATION = "deployment.kubernetes.io/revision"
_TEMPLATE_HASH_LABEL = "pod-template-hash"

SCALABLE_KINDS = frozenset(
    {"Deployment", "StatefulSet", "ReplicaSet", "ReplicationController", "DeploymentConfig"}
)
RESTARTABLE_KINDS = frozenset({"Deployment", "StatefulSet", "DaemonSet", "DeploymentConfig"})


def scale(clients: ClusterClients, target: ResourceTarget, replicas: int) -> None:
    """Set ``target``'s replica count."""
    if target.kind not in SCALABLE_KINDS:
        raise ResourceError(f"{target.kind} cannot be scaled")
    if replicas < 0:
        raise ResourceError("replicas must be >= 0")
    _patch(clients, target, {"spec": {"replicas": replicas}})


def restart(clients: ClusterClients, target: ResourceTarget) -> None:
    """Trigger a rolling restart by bumping a pod-template annotation."""
    if target.kind not in RESTARTABLE_KINDS:
        raise ResourceError(f"{target.kind} cannot be restarted")
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    annotation = {_RESTART_ANNOTATION: stamp}
    _patch(clients, target, {"spec": {"template": {"metadata": {"annotations": annotation}}}})


def rollout_undo(clients: ClusterClients, target: ResourceTarget) -> None:
    """Roll a Deployment back to its previous revision's pod template."""
    if target.kind != "Deployment":
        raise ResourceError("Rollout undo is only supported for Deployments")
    deployment = _fetch(clients, target)
    template = _previous_template(clients, target, deployment)
    if template is None:
        raise ResourceError("No previous revision to roll back to")
    _patch(clients, target, {"spec": {"template": template}})


def _previous_template(
    clients: ClusterClients, target: ResourceTarget, deployment: dict
) -> dict | None:
    owner_uid = deployment["metadata"]["uid"]
    revisions = _owned_replicaset_revisions(clients, target.namespace, owner_uid)
    if len(revisions) < 2:
        return None
    revisions.sort(key=lambda item: item[0], reverse=True)
    return _without_template_hash(revisions[1][1]["spec"]["template"])


def _owned_replicaset_revisions(
    clients: ClusterClients, namespace: str | None, owner_uid: str
) -> list[tuple[int, dict]]:
    resource = clients.dynamic.resources.get(api_version="apps/v1", kind="ReplicaSet")
    items = resource.get(namespace=namespace).to_dict()["items"]
    revisions: list[tuple[int, dict]] = []
    for replica_set in items:
        if not _owned_by(replica_set, owner_uid):
            continue
        revision = (replica_set["metadata"].get("annotations") or {}).get(_REVISION_ANNOTATION)
        if revision is not None:
            revisions.append((int(revision), replica_set))
    return revisions


def _without_template_hash(template: dict) -> dict:
    labels = template.get("metadata", {}).get("labels")
    if labels:
        labels.pop(_TEMPLATE_HASH_LABEL, None)
    return template


def _owned_by(obj: dict, owner_uid: str) -> bool:
    refs = obj["metadata"].get("ownerReferences") or []
    return any(ref.get("uid") == owner_uid for ref in refs)


def _fetch(clients: ClusterClients, target: ResourceTarget) -> dict:
    resource = get_resource(clients, target)
    try:
        return resource.get(name=target.name, namespace=target.namespace).to_dict()
    except NotFoundError as exc:
        raise ResourceError(f"{target.kind} {target.name} not found") from exc
    except DynamicApiError as exc:
        raise ResourceError(exc.summary()) from exc


def _patch(clients: ClusterClients, target: ResourceTarget, body: dict) -> None:
    resource = get_resource(clients, target)
    try:
        resource.patch(
            body=body,
            name=target.name,
            namespace=target.namespace,
            content_type=_MERGE_PATCH,
        )
    except NotFoundError as exc:
        raise ResourceError(f"{target.kind} {target.name} not found") from exc
    except DynamicApiError as exc:
        raise ResourceError(exc.summary()) from exc
