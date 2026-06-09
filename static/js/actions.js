"use strict";

import * as api from "./api.js";
import { closeSheet, onSheetClosed, openConfirm, openSheet, showToast } from "./ui.js";
import { escapeHtml, kindIcon } from "./format.js";

const SCALABLE = new Set(["Deployment", "StatefulSet", "ReplicaSet", "ReplicationController", "DeploymentConfig"]);
const RESTARTABLE = new Set(["Deployment", "StatefulSet", "DaemonSet", "DeploymentConfig"]);
const UNDOABLE = new Set(["Deployment"]);
const PROTECTED = ["kube-system", "kube-public", "kube-node-lease"];

const ctxmenu = document.getElementById("ctxmenu");
document.addEventListener("click", () => closeMenu());
window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

// Fetch the user's allowed verbs for a node, so the UI only offers actions the
// cluster would actually permit. Returns {} on any failure (nothing shown).
export async function capabilitiesFor(node) {
  const target = capTarget(node);
  if (!target) return {};
  try {
    return await api.getCapabilities(target);
  } catch {
    return {};
  }
}

export function renderPanelActions(container, node, caps, ctx) {
  container.innerHTML = "";
  const actions = actionsFor(node, caps, ctx);
  for (const action of actions) {
    const button = document.createElement("button");
    button.className = "btn action" + (action.danger ? " btn-danger" : "");
    button.innerHTML = `${action.icon} ${escapeHtml(action.label)}`;
    button.addEventListener("click", action.run);
    container.appendChild(button);
  }
}

export function openContextMenu(event, node, caps, ctx) {
  const actions = actionsFor(node, caps, ctx);
  if (!actions.length) return closeMenu();
  ctxmenu.innerHTML = "";
  for (const action of actions) {
    const item = document.createElement("div");
    item.className = "ctxitem" + (action.danger ? " danger" : "");
    item.innerHTML = `<span>${action.icon}</span>${escapeHtml(action.label)}`;
    item.addEventListener("click", (e) => { e.stopPropagation(); closeMenu(); action.run(); });
    ctxmenu.appendChild(item);
  }
  ctxmenu.style.left = `${event.clientX}px`;
  ctxmenu.style.top = `${event.clientY}px`;
  ctxmenu.classList.remove("hidden");
}

export function closeMenu() {
  ctxmenu.classList.add("hidden");
}

function actionsFor(node, caps, ctx) {
  const kind = node.data.kind;
  const actions = [];
  const add = (allowed, action) => { if (allowed) actions.push(action); };

  if (kind === "Pod" || kind === "Container") {
    add(caps.logs, { label: "Logs", icon: "📜", run: () => showLogs(node) });
    add(caps.exec, { label: "Exec shell", icon: "⌨️", run: () => openExec(node) });
  }
  add(SCALABLE.has(kind) && caps.patch, { label: "Scale…", icon: "🔢", run: () => promptScale(node, ctx) });
  add(RESTARTABLE.has(kind) && caps.patch, { label: "Restart", icon: "🔄", run: () => doRestart(node, ctx) });
  add(UNDOABLE.has(kind) && caps.patch, { label: "Rollout undo", icon: "↩️", run: () => doUndo(node, ctx) });
  if (kind === "Node") {
    add(caps.cordon, { label: "Cordon", icon: "🚧", run: () => doCordon(node, ctx, true) });
    add(caps.cordon, { label: "Uncordon", icon: "✅", run: () => doCordon(node, ctx, false) });
    add(caps.drain, { label: "Drain", icon: "🪣", danger: true, run: () => doDrain(node, ctx) });
  }
  add(kind !== "Cluster" && kind !== "Container" && caps.manifest,
    { label: "View YAML", icon: "📄", run: () => showYaml(node) });
  add(caps.events && (node.data.namespace || kind === "Namespace"),
    { label: "Events", icon: "📰", run: () => showEvents(node) });
  add(node.data.deletable && caps.delete,
    { label: "Delete (cascade)", icon: "🗑️", danger: true, run: () => confirmDelete(node, ctx) });
  return actions;
}

async function showLogs(node) {
  const pod = podContext(node);
  const { body, tools } = openSheet(`Logs · ${pod.pod}${pod.container ? " / " + pod.container : ""}`);
  const pre = document.createElement("pre");
  pre.className = "sheet-pre";
  body.appendChild(pre);
  const follow = document.createElement("label");
  follow.className = "control toggle";
  follow.innerHTML = `<input type="checkbox" id="log-follow" />Follow`;
  tools.appendChild(follow);

  const load = async () => {
    try {
      const { logs } = await api.getLogs(pod);
      pre.textContent = logs || "(no log output)";
      pre.scrollTop = pre.scrollHeight;
    } catch (err) {
      pre.textContent = `Failed to read logs: ${err.message}`;
    }
  };
  await load();
  const timer = setInterval(() => { if (follow.querySelector("input").checked) load(); }, 3000);
  onSheetClosed(() => clearInterval(timer));
}

async function showYaml(node) {
  const { body } = openSheet(`YAML · ${node.data.kind}/${node.data.name}`);
  const pre = document.createElement("pre");
  pre.className = "sheet-pre";
  pre.textContent = "Loading…";
  body.appendChild(pre);
  try {
    const { yaml } = await api.getManifest(target(node));
    pre.textContent = yaml;
  } catch (err) {
    pre.textContent = `Failed to read manifest: ${err.message}`;
  }
}

async function showEvents(node) {
  const { body } = openSheet(`Events · ${node.data.name}`);
  try {
    const { events } = await api.getEvents({ namespace: node.data.namespace, name: node.data.name });
    if (!events.length) { body.innerHTML = `<p class="sheet-empty">No recent events.</p>`; return; }
    body.innerHTML = events.map((e) => `
      <div class="event ${e.type === "Warning" ? "warn" : ""}">
        <span class="event-reason">${escapeHtml(e.reason || "")}</span>
        <span class="event-msg">${escapeHtml(e.message || "")}</span>
        <span class="event-meta">×${e.count || 1} · ${escapeHtml(e.lastTimestamp || "")}</span>
      </div>`).join("");
  } catch (err) {
    body.innerHTML = `<p class="sheet-empty">Failed to read events: ${escapeHtml(err.message)}</p>`;
  }
}

function promptScale(node, ctx) {
  openConfirm({
    title: `Scale ${node.data.name}`,
    bodyHtml: `<p>Set the desired replica count.</p>
      <input type="number" id="scale-input" min="0" value="1" class="num-input" />`,
    confirmLabel: "Scale",
    danger: false,
    onConfirm: async (body) => {
      const replicas = parseInt(body.querySelector("#scale-input").value, 10);
      await guard(() => api.scale(target(node), replicas), `Scaled ${node.data.name} to ${replicas}`, ctx);
    },
  });
}

function doRestart(node, ctx) {
  openConfirm({
    title: `Restart ${node.data.name}`,
    bodyHtml: `<p>Trigger a rolling restart of <b>${escapeHtml(node.data.name)}</b>?</p>`,
    confirmLabel: "Restart", danger: false,
    onConfirm: () => guard(() => api.restart(target(node)), `Restarting ${node.data.name}`, ctx),
  });
}

function doUndo(node, ctx) {
  openConfirm({
    title: `Roll back ${node.data.name}`,
    bodyHtml: `<p>Roll <b>${escapeHtml(node.data.name)}</b> back to its previous revision?</p>`,
    confirmLabel: "Roll back", danger: false,
    onConfirm: () => guard(() => api.rolloutUndo(target(node)), `Rolled back ${node.data.name}`, ctx),
  });
}

function doCordon(node, ctx, on) {
  guard(() => api.cordon(node.data.name, on), `${on ? "Cordoned" : "Uncordoned"} ${node.data.name}`, ctx);
}

function doDrain(node, ctx) {
  openConfirm({
    title: `Drain ${node.data.name}`,
    bodyHtml: `<p>Cordon and evict all movable pods from <b>${escapeHtml(node.data.name)}</b>?</p>
      <p class="modal-warn">⚠ Evicted pods reschedule elsewhere; this can disrupt workloads.</p>`,
    confirmLabel: "Drain",
    onConfirm: async () => {
      try {
        const { evicted } = await api.drain(node.data.name);
        showToast(`Draining ${node.data.name} — evicted ${evicted.length} pod(s)`);
        ctx.onChanged();
      } catch (err) {
        showToast(`Drain failed: ${err.message}`, true);
      }
    },
  });
}

function confirmDelete(node, ctx) {
  const ns = node.data.namespace || "";
  const risky = PROTECTED.includes(ns) || ns.startsWith("openshift");
  const childCount = node.descendants().length - 1;
  openConfirm({
    title: "Delete resource",
    bodyHtml: `
      <p>Cascades to all owned children (${childCount} descendant${childCount === 1 ? "" : "s"}).</p>
      <div class="modal-target">${escapeHtml(node.data.kind)} / ${escapeHtml(node.data.name)}${
        ns ? " @ " + escapeHtml(ns) : ""}</div>
      ${risky ? '<p class="modal-warn">⚠ System namespace — deleting can break the cluster.</p>' : ""}`,
    confirmLabel: "Delete",
    onConfirm: () => guard(() => api.deleteResource(target(node)), `Deleted ${node.data.kind} ${node.data.name}`, ctx),
  });
}

function openExec(node) {
  const pod = podContext(node);
  const { body } = openSheet(`Exec · ${pod.pod}${pod.container ? " / " + pod.container : ""}`);
  const host = document.createElement("div");
  host.className = "term-host";
  body.appendChild(host);

  const term = new window.Terminal({ cursorBlink: true, fontSize: 13, theme: { background: "#0a0e14" } });
  const fit = new window.FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(host);
  fit.fit();

  const socket = new WebSocket(api.execUrl(pod));
  socket.onmessage = (event) => term.write(event.data);
  socket.onclose = () => term.write("\r\n\x1b[31m[session closed]\x1b[0m\r\n");
  term.onData((data) => { if (socket.readyState === WebSocket.OPEN) socket.send(data); });
  const onResize = () => fit.fit();
  window.addEventListener("resize", onResize);
  onSheetClosed(() => { window.removeEventListener("resize", onResize); socket.close(); term.dispose(); });
}

async function guard(call, successMessage, ctx) {
  try {
    await call();
    showToast(successMessage);
    ctx.onChanged();
  } catch (err) {
    showToast(`${err.message}`, true);
  }
}

function target(node) {
  return {
    apiVersion: node.data.apiVersion || "v1",
    kind: node.data.kind,
    name: node.data.name,
    namespace: node.data.namespace,
  };
}

function capTarget(node) {
  const kind = node.data.kind;
  if (kind === "Cluster") return null;
  if (kind === "Container") {
    const pod = node.parent;
    return { apiVersion: "v1", kind: "Pod", name: pod.data.name, namespace: pod.data.namespace };
  }
  return target(node);
}

function podContext(node) {
  if (node.data.kind === "Container") {
    const pod = node.parent;
    return { namespace: pod.data.namespace, pod: pod.data.name, container: node.data.name };
  }
  const firstContainer = node.children && node.children[0];
  return {
    namespace: node.data.namespace,
    pod: node.data.name,
    container: firstContainer ? firstContainer.data.name : undefined,
  };
}
