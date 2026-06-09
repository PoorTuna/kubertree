"""Workload mutations: scale patch, restart annotation, rollout-undo template."""

import pytest

from _target import ResourceError, ResourceTarget
from _workload import restart, rollout_undo, scale

_REVISION = "deployment.kubernetes.io/revision"


class _Obj:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class FakeResource:
    namespaced = True

    def __init__(self, data=None):
        self._data = data
        self.patches = []

    def get(self, name=None, namespace=None):
        return _Obj(self._data)

    def patch(self, body, name, namespace, content_type):
        self.patches.append({"body": body, "content_type": content_type})


class FakeResources:
    def __init__(self, by_kind):
        self._by_kind = by_kind

    def get(self, api_version, kind):
        return self._by_kind[kind]


class FakeClients:
    def __init__(self, **by_kind):
        self.dynamic = type("D", (), {"resources": FakeResources(by_kind)})()


def _deployment(kind="Deployment"):
    return ResourceTarget("apps/v1", kind, "web", "default")


def test_scale_patches_replicas_with_merge_patch():
    resource = FakeResource()
    scale(FakeClients(Deployment=resource), _deployment(), 3)

    assert resource.patches[0]["body"] == {"spec": {"replicas": 3}}
    assert resource.patches[0]["content_type"] == "application/merge-patch+json"


def test_scale_rejects_unscalable_kind():
    with pytest.raises(ResourceError):
        scale(FakeClients(Pod=FakeResource()), ResourceTarget("v1", "Pod", "p", "default"), 1)


def test_scale_rejects_negative_replicas():
    with pytest.raises(ResourceError):
        scale(FakeClients(Deployment=FakeResource()), _deployment(), -1)


def test_restart_stamps_pod_template_annotation():
    resource = FakeResource()
    restart(FakeClients(Deployment=resource), _deployment())

    annotations = resource.patches[0]["body"]["spec"]["template"]["metadata"]["annotations"]
    assert "kubertree.io/restartedAt" in annotations


def test_restart_rejects_unrestartable_kind():
    with pytest.raises(ResourceError):
        restart(FakeClients(Pod=FakeResource()), ResourceTarget("v1", "Pod", "p", "default"))


def _replicaset(uid, revision, hash_label, marker):
    return {
        "metadata": {
            "uid": uid,
            "annotations": {_REVISION: revision},
            "ownerReferences": [{"uid": "dep-uid"}],
        },
        "spec": {
            "template": {
                "metadata": {"labels": {"app": "web", "pod-template-hash": hash_label}},
                "spec": {"marker": marker},
            }
        },
    }


def test_rollout_undo_applies_previous_revision_without_template_hash():
    deployment = FakeResource({"metadata": {"uid": "dep-uid"}})
    replicasets = FakeResource()
    replicasets._data = {
        "items": [
            _replicaset("rs1", "1", "old", "previous"),
            _replicaset("rs2", "2", "new", "current"),
        ]
    }
    rollout_undo(FakeClients(Deployment=deployment, ReplicaSet=replicasets), _deployment())

    template = deployment.patches[0]["body"]["spec"]["template"]
    assert template["spec"] == {"marker": "previous"}
    assert "pod-template-hash" not in template["metadata"]["labels"]


def test_rollout_undo_without_history_raises():
    deployment = FakeResource({"metadata": {"uid": "dep-uid"}})
    replicasets = FakeResource()
    replicasets._data = {"items": [_replicaset("rs1", "1", "only", "current")]}

    with pytest.raises(ResourceError):
        rollout_undo(FakeClients(Deployment=deployment, ReplicaSet=replicasets), _deployment())


def test_rollout_undo_rejects_non_deployment():
    with pytest.raises(ResourceError):
        rollout_undo(FakeClients(StatefulSet=FakeResource()), _deployment("StatefulSet"))
