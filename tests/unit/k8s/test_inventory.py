"""Owner resolution: chain ordering, UID caching, and graceful stops."""

from kubernetes.client.models import V1ObjectMeta, V1OwnerReference, V1Pod

from kubertree.k8s._inventory import OwnerResolver, _controller_ref
from kubertree.k8s._models import OwnerRef


def pod_owned_by(kind, name, uid, controller=True):
    owner = V1OwnerReference(
        api_version="apps/v1",
        kind=kind,
        name=name,
        uid=uid,
        controller=controller,
        block_owner_deletion=False,
    )
    return V1Pod(
        metadata=V1ObjectMeta(
            name="p", namespace="default", uid="pod-uid", owner_references=[owner]
        )
    )


def test_controller_ref_prefers_controlling_owner():
    refs = [
        V1OwnerReference(api_version="v1", kind="Foo", name="foo", uid="foo-uid", controller=False),
        V1OwnerReference(
            api_version="apps/v1", kind="ReplicaSet", name="rs", uid="rs-uid", controller=True
        ),
    ]
    chosen = _controller_ref(refs, "default")
    assert chosen.kind == "ReplicaSet"
    assert chosen.uid == "rs-uid"


def test_controller_ref_none_when_no_owners():
    assert _controller_ref(None, "default") is None
    assert _controller_ref([], "default") is None


def test_resolve_chain_is_root_first(monkeypatch):
    resolver = OwnerResolver(clients=None)
    parents = {
        "rs-uid": OwnerRef("apps/v1", "Deployment", "web", "deploy-uid", "default"),
        "deploy-uid": None,
    }
    monkeypatch.setattr(resolver, "_fetch_parent", lambda ref: parents[ref.uid])

    chain = resolver.resolve_chain(pod_owned_by("ReplicaSet", "web-rs", "rs-uid"))

    assert [link.kind for link in chain] == ["Deployment", "ReplicaSet"]


def test_owner_object_fetched_once_across_pods(monkeypatch):
    resolver = OwnerResolver(clients=None)
    calls = {"count": 0}

    def fake_fetch(ref):
        calls["count"] += 1
        return None

    monkeypatch.setattr(resolver, "_fetch_parent", fake_fetch)
    resolver.resolve_chain(pod_owned_by("ReplicaSet", "web-rs", "rs-uid"))
    resolver.resolve_chain(pod_owned_by("ReplicaSet", "web-rs", "rs-uid"))

    assert calls["count"] == 1


def test_missing_owner_stops_chain(monkeypatch):
    resolver = OwnerResolver(clients=None)
    monkeypatch.setattr(resolver, "_fetch_parent", lambda ref: None)

    chain = resolver.resolve_chain(pod_owned_by("StatefulSet", "cassandra", "sts-uid"))

    assert [link.kind for link in chain] == ["StatefulSet"]
