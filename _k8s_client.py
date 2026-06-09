"""Kubernetes client construction and connection bootstrap.

Works both in-cluster (Helm-deployed pod with a ServiceAccount) and locally
against ``~/.kube/config``. All other modules depend on the abstract
:class:`ClusterClients` holder rather than on how config was loaded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kubernetes import client, config
from kubernetes.client import ApiClient, CoreV1Api, CustomObjectsApi, VersionApi
from kubernetes.config.config_exception import ConfigException
from kubernetes.dynamic import DynamicClient

logger = logging.getLogger(__name__)


class ClusterConnectionError(RuntimeError):
    """Raised when neither in-cluster nor kubeconfig credentials are usable."""


@dataclass(frozen=True)
class ClusterClients:
    """Bundle of the Kubernetes API clients the backend needs."""

    api_client: ApiClient
    core: CoreV1Api
    custom_objects: CustomObjectsApi
    dynamic: DynamicClient
    version: VersionApi


def load_clients() -> ClusterClients:
    """Build API clients, preferring in-cluster config over a local kubeconfig."""
    _load_config()
    api_client = ApiClient()
    return ClusterClients(
        api_client=api_client,
        core=CoreV1Api(api_client),
        custom_objects=CustomObjectsApi(api_client),
        dynamic=DynamicClient(api_client),
        version=VersionApi(api_client),
    )


def _load_config() -> None:
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
        return
    except ConfigException:
        pass

    try:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")
    except ConfigException as exc:
        raise ClusterConnectionError(
            "No in-cluster config and no usable ~/.kube/config found"
        ) from exc
