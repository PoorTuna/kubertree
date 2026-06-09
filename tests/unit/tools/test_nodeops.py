"""Node operations: cordon patch body and drain pod filtering."""

from types import SimpleNamespace

from kubernetes.client.models import V1ObjectMeta, V1OwnerReference, V1Pod

from kubertree.tools._nodeops import drain, set_cordon


class FakeCore:
    def __init__(self, pods=None):
        self._pods = pods or []
        self.patched = []
        self.evicted = []

    def patch_node(self, name, body):
        self.patched.append((name, body))

    def list_pod_for_all_namespaces(self, field_selector=None):
        return SimpleNamespace(items=self._pods)

    def create_namespaced_pod_eviction(self, name, namespace, body):
        self.evicted.append(name)


def _pod(name, owner_kind=None, mirror=False):
    owners = None
    if owner_kind:
        owners = [
            V1OwnerReference(
                api_version="apps/v1", kind=owner_kind, name="o", uid="u", controller=True
            )
        ]
    annotations = {"kubernetes.io/config.mirror": "x"} if mirror else None
    return V1Pod(
        metadata=V1ObjectMeta(
            name=name, namespace="default", owner_references=owners, annotations=annotations
        )
    )


def test_set_cordon_patches_unschedulable_true():
    core = FakeCore()
    set_cordon(SimpleNamespace(core=core), "node-1", True)

    assert core.patched == [("node-1", {"spec": {"unschedulable": True}})]


def test_set_uncordon_patches_unschedulable_false():
    core = FakeCore()
    set_cordon(SimpleNamespace(core=core), "node-1", False)

    assert core.patched == [("node-1", {"spec": {"unschedulable": False}})]


def test_drain_cordons_then_evicts_movable_pods_only():
    pods = [_pod("app"), _pod("ds", owner_kind="DaemonSet"), _pod("static", mirror=True)]
    core = FakeCore(pods)

    evicted = drain(SimpleNamespace(core=core), "node-1")

    assert evicted == ["app"]
    assert core.evicted == ["app"]
    assert ("node-1", {"spec": {"unschedulable": True}}) in core.patched
