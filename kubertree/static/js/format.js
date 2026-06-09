"use strict";

// Short, monochrome type codes used across the UI in place of icons —
// neutral and readable, mirroring the abbreviations used by k9s / Lens.
export const KIND_BADGE = {
  Cluster: "CLU",
  Node: "NOD",
  Namespace: "NS",
  Deployment: "DEP",
  DeploymentConfig: "DC",
  StatefulSet: "STS",
  DaemonSet: "DS",
  ReplicaSet: "RS",
  ReplicationController: "RC",
  Job: "JOB",
  CronJob: "CJN",
  Pod: "POD",
  Container: "CON",
};

export function kindBadge(kind) {
  return KIND_BADGE[kind] || kind.slice(0, 3).toUpperCase();
}

export function fmtCpu(milli) {
  if (!milli) return "0";
  return milli < 1000 ? `${Math.round(milli)}m` : `${(milli / 1000).toFixed(2)} cores`;
}

export function fmtMem(bytes) {
  if (!bytes) return "0";
  const units = ["B", "Ki", "Mi", "Gi", "Ti"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

export function fmtAxis(axis, value) {
  return axis === "cpu" ? fmtCpu(value) : fmtMem(value);
}

export function efficiencyText(usage, request, metricsAvailable) {
  if (!metricsAvailable || request <= 0) return "—";
  return `${Math.round((usage / request) * 100)}%`;
}

export function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
