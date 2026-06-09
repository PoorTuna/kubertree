"""Quantity parsing: Kubernetes resource strings to numeric millicores/bytes."""

import pytest

from _metrics import cpu_to_milli, memory_to_bytes


@pytest.mark.parametrize(
    "quantity, expected_milli",
    [("100m", 100.0), ("1", 1000.0), ("250m", 250.0), ("1500m", 1500.0), ("0", 0.0)],
)
def test_cpu_to_milli(quantity, expected_milli):
    assert cpu_to_milli(quantity) == expected_milli


@pytest.mark.parametrize(
    "quantity, expected_bytes",
    [
        ("131072Ki", 131072 * 1024),
        ("128Mi", 128 * 1024 * 1024),
        ("1Gi", 1024 ** 3),
        ("0", 0),
    ],
)
def test_memory_to_bytes(quantity, expected_bytes):
    assert memory_to_bytes(quantity) == expected_bytes
