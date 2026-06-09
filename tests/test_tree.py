"""Hierarchy assembly: owner chains, bare pods, and metric/request placement."""

from kubernetes.client.models import (
    V1Container,
    V1ObjectMeta,
    V1Pod,
    V1PodSpec,
    V1ResourceRequirements,
)

from _models import OwnerRef, Usage
from _tree import build_tree


def make_pod(name, namespace, uid, requests=None, containers=("app",)):
    spec_containers = [
        V1Container(
            name=container,
            resources=V1ResourceRequirements(requests=requests) if requests else None,
        )
        for container in containers
    ]
    return V1Pod(
        metadata=V1ObjectMeta(name=name, namespace=namespace, uid=uid),
        spec=V1PodSpec(containers=spec_containers),
    )


def deployment_chain(uid="deploy-uid"):
    return [
        OwnerRef(api_version="apps/v1", kind="Deployment", name="web", uid=uid, namespace="default")
    ]


def test_deployment_chain_nests_under_namespace_and_owner():
    pod = make_pod("web-abc", "default", "pod-uid")
    root = build_tree([pod], {}, lambda _p: deployment_chain())

    namespace = root.children["default"]
    deployment = namespace.children["deploy-uid"]
    pod_node = deployment.children["pod-uid"]

    assert namespace.kind == "Namespace"
    assert deployment.kind == "Deployment"
    assert pod_node.kind == "Pod"
    assert "app" in pod_node.children


def test_openshift_deploymentconfig_chain_nests():
    chain = [
        OwnerRef("apps.openshift.io/v1", "DeploymentConfig", "router", "dc-uid", "default"),
    ]
    pod = make_pod("router-1", "default", "pod-uid")
    root = build_tree([pod], {}, lambda _p: chain)

    assert root.children["default"].children["dc-uid"].kind == "DeploymentConfig"


def test_bare_pod_sits_directly_under_namespace():
    pod = make_pod("loner", "default", "pod-uid")
    root = build_tree([pod], {}, lambda _p: [])

    assert "pod-uid" in root.children["default"].children


def test_requests_populate_leaf_when_metrics_absent():
    pod = make_pod("web", "default", "pod-uid", requests={"cpu": "250m", "memory": "128Mi"})
    root = build_tree([pod], {}, lambda _p: [])

    container = root.children["default"].children["pod-uid"].children["app"]
    assert container.cpu_request == 250.0
    assert container.mem_request == 128 * 1024 * 1024
    assert container.cpu_usage == 0.0


def test_usage_merges_onto_container_leaf():
    pod = make_pod("web", "default", "pod-uid")
    usage = {("default", "web"): {"app": Usage(cpu_milli=42.0, mem_bytes=2048.0)}}
    root = build_tree([pod], usage, lambda _p: [])

    container = root.children["default"].children["pod-uid"].children["app"]
    assert container.cpu_usage == 42.0
    assert container.mem_usage == 2048.0


def test_to_dict_emits_children_for_internal_and_values_for_leaf():
    pod = make_pod("web", "default", "pod-uid", requests={"cpu": "100m"})
    root = build_tree([pod], {}, lambda _p: [])
    payload = root.to_dict()

    namespace = payload["children"][0]
    assert namespace["kind"] == "Namespace"
    leaf = namespace["children"][0]["children"][0]
    assert leaf["cpuRequest"] == 100.0
    assert "children" not in leaf
