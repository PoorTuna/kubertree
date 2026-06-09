"use strict";

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || response.statusText);
  }
  return response.json();
}

const qs = (params) =>
  Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");

export function getHealth() {
  return fetchJson("/api/health");
}

export function getTree(group) {
  return fetchJson(`/api/tree?group=${encodeURIComponent(group)}`);
}

export function deleteResource(target) {
  return fetchJson("/api/delete", { method: "POST", body: JSON.stringify(target) });
}

export function whoami() {
  return fetchJson("/api/whoami");
}

export function login(token) {
  return fetchJson("/api/login", { method: "POST", body: JSON.stringify({ token }) });
}

export function logout() {
  return fetchJson("/api/logout", { method: "POST" });
}

export function getCapabilities({ apiVersion, kind, name, namespace }) {
  return fetchJson(`/api/capabilities?${qs({ apiVersion, kind, name, namespace })}`);
}

export function getLogs({ namespace, pod, container, tail = 200, previous = false }) {
  return fetchJson(`/api/logs?${qs({ namespace, pod, container, tail, previous })}`);
}

export function getManifest({ apiVersion, kind, name, namespace }) {
  return fetchJson(`/api/manifest?${qs({ apiVersion, kind, name, namespace })}`);
}

export function getEvents({ namespace, name }) {
  return fetchJson(`/api/events?${qs({ namespace, name })}`);
}

export function scale(target, replicas) {
  return fetchJson("/api/scale", { method: "POST", body: JSON.stringify({ ...target, replicas }) });
}

export function restart(target) {
  return fetchJson("/api/restart", { method: "POST", body: JSON.stringify(target) });
}

export function rolloutUndo(target) {
  return fetchJson("/api/rollout-undo", { method: "POST", body: JSON.stringify(target) });
}

export function cordon(name, on) {
  return fetchJson("/api/cordon", { method: "POST", body: JSON.stringify({ name, on }) });
}

export function drain(name) {
  return fetchJson("/api/drain", { method: "POST", body: JSON.stringify({ name }) });
}

export function execUrl({ namespace, pod, container }) {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/api/exec?${qs({ namespace, pod, container })}`;
}
