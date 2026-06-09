"use strict";

export const KIND_ICON = {
  Cluster: "🌐",
  Node: "🖥️",
  Namespace: "📁",
  Deployment: "🚀",
  StatefulSet: "🗄️",
  DaemonSet: "🛡️",
  ReplicaSet: "🧩",
  ReplicationController: "🧩",
  DeploymentConfig: "🚀",
  Job: "⚙️",
  CronJob: "⏰",
  Pod: "📦",
  Container: "▪️",
};

export function kindIcon(kind) {
  return KIND_ICON[kind] || "🔷";
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
