"""Bind-port parsing."""

import kubertree.main as main


def test_bind_port_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("KUBERTREE_BIND_PORT", raising=False)
    assert main._bind_port() == 8000


def test_bind_port_reads_numeric_value(monkeypatch):
    monkeypatch.setenv("KUBERTREE_BIND_PORT", "9000")
    assert main._bind_port() == 9000


def test_bind_port_tolerates_non_numeric_value(monkeypatch):
    monkeypatch.setenv("KUBERTREE_BIND_PORT", "tcp://172.30.0.1:80")
    assert main._bind_port() == 8000
