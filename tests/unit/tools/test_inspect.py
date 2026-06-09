"""Read-only inspection: log params, manifest scrubbing, event filtering."""

import copy
from datetime import UTC, datetime
from types import SimpleNamespace

from kubertree.k8s._target import ResourceTarget
from kubertree.tools._inspect import list_events, read_logs, read_manifest


class FakeCore:
    def __init__(self, events=None):
        self._events = events or []
        self.log_args = None
        self.event_args = None

    def read_namespaced_pod_log(self, name, namespace, container, tail_lines, previous):
        self.log_args = {
            "name": name,
            "namespace": namespace,
            "container": container,
            "tail_lines": tail_lines,
            "previous": previous,
        }
        return "log-text"

    def list_namespaced_event(self, namespace, field_selector):
        self.event_args = {"namespace": namespace, "field_selector": field_selector}
        return SimpleNamespace(items=self._events)


class _Obj:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return copy.deepcopy(self._data)


class FakeResource:
    namespaced = True

    def __init__(self, data):
        self._data = data

    def get(self, name=None, namespace=None):
        return _Obj(self._data)


class FakeClients:
    def __init__(self, resource):
        self.dynamic = type(
            "D",
            (),
            {"resources": type("R", (), {"get": lambda self_, api_version, kind: resource})()},
        )()


def test_read_logs_passes_parameters_through():
    core = FakeCore()
    out = read_logs(SimpleNamespace(core=core), "default", "web-pod", "app", tail=50, previous=True)

    assert out == "log-text"
    assert core.log_args == {
        "name": "web-pod",
        "namespace": "default",
        "container": "app",
        "tail_lines": 50,
        "previous": True,
    }


def test_read_manifest_strips_managed_fields_and_emits_yaml():
    obj = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "p", "managedFields": [{"manager": "kubelet"}]},
    }
    clients = FakeClients(FakeResource(obj))

    text = read_manifest(clients, ResourceTarget("v1", "Pod", "p", "default"))

    assert "managedFields" not in text
    assert "name: p" in text


def test_list_events_filters_by_involved_object():
    event = SimpleNamespace(
        type="Warning",
        reason="BackOff",
        message="boom",
        count=3,
        last_timestamp=datetime(2026, 6, 1, tzinfo=UTC),
        event_time=None,
    )
    core = FakeCore([event])

    events = list_events(SimpleNamespace(core=core), "default", "web-pod")

    assert core.event_args["field_selector"] == "involvedObject.name=web-pod"
    assert events[0]["reason"] == "BackOff"
    assert events[0]["lastTimestamp"].startswith("2026-06-01")
