"""Answer "can the current user do X?" via SelfSubjectAccessReview.

The frontend calls :func:`capabilities` for a selected resource and shows only
the actions the cluster would actually permit, so users never see buttons that
would 403. Reviews run as the calling user's token.
"""

from __future__ import annotations

from kubernetes import client
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic.exceptions import ResourceNotFoundError

from _k8s_client import ClusterClients
from _target import ResourceTarget

_POD_KINDS = frozenset({"Pod", "Container"})


def capabilities(clients: ClusterClients, target: ResourceTarget) -> dict[str, bool]:
    """Return a verb→allowed map for the tools that apply to ``target``."""
    group, resource = _group_resource(clients, target)
    namespace = target.namespace
    caps = {
        "manifest": _allowed(clients, "get", group, resource, namespace),
        "events": _allowed(clients, "get", "", "events", namespace),
        "delete": _allowed(clients, "delete", group, resource, namespace),
        "patch": _allowed(clients, "patch", group, resource, namespace),
    }
    if target.kind in _POD_KINDS:
        caps["logs"] = _allowed(clients, "get", "", "pods", namespace, "log")
        caps["exec"] = _allowed(clients, "create", "", "pods", namespace, "exec")
    if target.kind == "Node":
        caps["cordon"] = _allowed(clients, "patch", "", "nodes", None)
        caps["drain"] = caps["cordon"] and _allowed(
            clients, "create", "", "pods", None, "eviction"
        )
    return caps


def _allowed(
    clients: ClusterClients,
    verb: str,
    group: str,
    resource: str,
    namespace: str | None,
    subresource: str | None = None,
) -> bool:
    attributes = client.V1ResourceAttributes(
        verb=verb, group=group, resource=resource,
        namespace=namespace, subresource=subresource,
    )
    review = client.V1SelfSubjectAccessReview(
        spec=client.V1SelfSubjectAccessReviewSpec(resource_attributes=attributes)
    )
    try:
        result = client.AuthorizationV1Api(
            clients.api_client
        ).create_self_subject_access_review(body=review)
    except ApiException:
        return False
    return bool(result.status.allowed)


def _group_resource(clients: ClusterClients, target: ResourceTarget) -> tuple[str, str]:
    api_version = "v1" if target.kind == "Container" else target.api_version
    kind = "Pod" if target.kind == "Container" else target.kind
    try:
        resource = clients.dynamic.resources.get(api_version=api_version, kind=kind)
    except (ResourceNotFoundError, ValueError):
        return "", f"{kind.lower()}s"
    return resource.group or "", resource.name
