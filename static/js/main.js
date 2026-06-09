"use strict";

import * as api from "./api.js";
import { renderTreemap, groupKey } from "./treemap.js";
import { renderExplorer } from "./explorer.js";
import * as actions from "./actions.js";
import * as ui from "./ui.js";

const METRIC_OPTIONS = [
  { value: "cpuUsage", label: "CPU usage", usage: true, axis: "cpu" },
  { value: "memUsage", label: "Memory usage", usage: true, axis: "mem" },
  { value: "cpuRequest", label: "CPU request", usage: false, axis: "cpu" },
  { value: "memRequest", label: "Memory request", usage: false, axis: "mem" },
];

const PALETTE = ["#4f9cf9", "#22c1a4", "#f4a261", "#e76f8a", "#a78bfa", "#34d399",
  "#fbbf24", "#60a5fa", "#f472b6", "#2dd4bf", "#fb923c", "#818cf8", "#f87171", "#38bdf8"];

const state = {
  group: "owner",
  metric: "cpuUsage",
  colorMode: "group",
  view: "treemap",
  exMode: "tree",
  expanded: new Set(),
  metricsAvailable: false,
  root: null,
  focus: null,
  selectedKey: null,
  autoTimer: null,
};

const ctx = { onChanged: () => loadTree(true) };
const groupColor = d3.scaleOrdinal(PALETTE);
const kindColor = d3.scaleOrdinal(d3.schemeTableau10);
const svg = d3.select("#treemap");

const dom = {
  metric: document.getElementById("metric"),
  color: document.getElementById("color"),
  group: document.getElementById("group"),
  tabs: document.getElementById("tabs"),
  exmode: document.getElementById("exmode"),
  refresh: document.getElementById("refresh"),
  autorefresh: document.getElementById("autorefresh"),
  badge: document.getElementById("platform-badge"),
  banner: document.getElementById("banner"),
  loading: document.getElementById("loading"),
  username: document.getElementById("username"),
  logout: document.getElementById("logout"),
  login: document.getElementById("login"),
  loginForm: document.getElementById("login-form"),
  loginToken: document.getElementById("login-token"),
  loginError: document.getElementById("login-error"),
  stageTreemap: document.getElementById("stage-treemap"),
  stageExplorer: document.getElementById("stage-explorer"),
  explorerTable: document.getElementById("explorer-table"),
};

let controlsWired = false;
bootstrap();

async function bootstrap() {
  dom.loginForm.addEventListener("submit", onLoginSubmit);
  dom.logout.addEventListener("click", onLogout);
  try {
    const { user } = await api.whoami();
    enter(user);
  } catch {
    showLogin();
  }
}

function showLogin() {
  dom.login.classList.remove("hidden");
  dom.loginToken.focus();
}

async function onLoginSubmit(event) {
  event.preventDefault();
  dom.loginError.classList.add("hidden");
  try {
    const { user } = await api.login(dom.loginToken.value);
    dom.loginToken.value = "";
    dom.login.classList.add("hidden");
    enter(user);
  } catch (err) {
    dom.loginError.textContent = err.message;
    dom.loginError.classList.remove("hidden");
  }
}

async function onLogout() {
  await api.logout().catch(() => {});
  location.reload();
}

function enter(user) {
  dom.username.textContent = user || "";
  if (!controlsWired) wireControls();
  controlsWired = true;
  loadHealth().then(() => loadTree());
}

function wireControls() {
  METRIC_OPTIONS.forEach((opt) => {
    const node = document.createElement("option");
    node.value = opt.value;
    node.textContent = opt.label;
    dom.metric.appendChild(node);
  });
  dom.metric.addEventListener("change", () => { state.metric = dom.metric.value; render(); });
  dom.color.addEventListener("change", () => { state.colorMode = dom.color.value; render(); });
  dom.refresh.addEventListener("click", () => loadTree(true));
  dom.autorefresh.addEventListener("change", toggleAuto);
  dom.group.querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => setGroup(btn.dataset.value)));
  dom.tabs.querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => setView(btn.dataset.tab)));
  dom.exmode.querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => setExMode(btn.dataset.value)));
  if (location.hash === "#explorer") { state.view = "explorer"; toggleButtons(dom.tabs, "tab", "explorer"); }
  window.addEventListener("resize", render);
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menuClosed() && state.focus && state.focus.parent) zoom(state.focus.parent);
  });
}

function menuClosed() {
  return document.getElementById("ctxmenu").classList.contains("hidden");
}

function setGroup(group) {
  if (group === state.group) return;
  state.group = group;
  toggleButtons(dom.group, "value", group);
  loadTree();
}

function setView(view) {
  if (view === state.view) return;
  state.view = view;
  toggleButtons(dom.tabs, "tab", view);
  render();
}

function setExMode(mode) {
  if (mode === state.exMode) return;
  state.exMode = mode;
  toggleButtons(dom.exmode, "value", mode);
  render();
}

function toggleButtons(container, attr, value) {
  container.querySelectorAll("button").forEach((b) =>
    b.classList.toggle("active", b.dataset[attr] === value));
}

async function loadHealth() {
  try {
    const health = await api.getHealth();
    dom.badge.textContent = health.platform || "disconnected";
    state.metricsAvailable = !!health.metricsAvailable;
  } catch {
    dom.badge.textContent = "error";
  }
  applyMetrics();
}

function applyMetrics() {
  for (const option of dom.metric.options) {
    const meta = METRIC_OPTIONS.find((m) => m.value === option.value);
    option.disabled = meta.usage && !state.metricsAvailable;
  }
  if (!state.metricsAvailable) {
    state.metric = "memRequest";
    dom.metric.value = state.metric;
    dom.banner.textContent = "Metrics API unavailable — showing requested resources.";
    dom.banner.classList.remove("hidden");
  } else {
    dom.banner.classList.add("hidden");
  }
}

async function loadTree(keepFocus = false) {
  const previousKey = keepFocus && state.focus ? nodeKey(state.focus) : null;
  dom.loading.classList.remove("hidden");
  try {
    const data = await api.getTree(state.group);
    state.metricsAvailable = !!data.metricsAvailable;
    applyMetrics();
    state.root = d3.hierarchy(data.tree);
    aggregate(state.root);
    let counter = 0;
    state.root.each((node) => { node.__id = ++counter; });
    state.focus = (previousKey && find(state.root, previousKey)) || state.root;
    seedExpanded();
    render();
  } catch (err) {
    if (err.message && err.message.includes("authenticat")) return showLogin();
    ui.showToast(`Failed to load: ${err.message}`, true);
  } finally {
    dom.loading.classList.add("hidden");
  }
}

function seedExpanded() {
  if (state.expanded.size) return;
  state.expanded.add(nodeKey(state.root));
  (state.root.children || []).forEach((child) => state.expanded.add(nodeKey(child)));
}

function render() {
  if (!state.focus) return;
  const axis = METRIC_OPTIONS.find((m) => m.value === state.metric).axis;
  const explorer = state.view === "explorer";
  dom.stageTreemap.classList.toggle("hidden", explorer);
  dom.stageExplorer.classList.toggle("hidden", !explorer);

  if (explorer) {
    renderExplorer(dom.explorerTable, state.focus, {
      mode: state.exMode, metric: state.metric, axis,
      metricsAvailable: state.metricsAvailable,
      expanded: state.expanded, selectedKey: state.selectedKey,
      keyOf: nodeKey, pathOf,
      onActivate: activate, onContext: onContext, onToggle: onToggle,
    });
  } else {
    groupColor.domain(state.root.descendants().map(groupKey));
    renderTreemap(svg, state.focus, {
      metric: state.metric, axis, colorMode: state.colorMode,
      metricsAvailable: state.metricsAvailable, groupColor, kindColor,
      selectedUid: state.selectedKey,
      onActivate: activate,
      onHover: (e, node) => ui.showTooltip(e, node, { axis, metricsAvailable: state.metricsAvailable }),
      onLeave: ui.hideTooltip,
      onContext,
    });
  }
  ui.renderBreadcrumb(state.focus, zoom);
  renderLegend(explorer);
}

function renderLegend(explorer) {
  if (explorer) return ui.renderLegend([]);
  if (state.colorMode === "efficiency") {
    ui.renderLegend([
      { label: "wasteful", color: d3.interpolateRdYlGn(0.1) },
      { label: "ok", color: d3.interpolateRdYlGn(0.6) },
      { label: "tight", color: d3.interpolateRdYlGn(1) },
      { label: "no request", color: "#3a4150" },
    ]);
    return;
  }
  const scale = state.colorMode === "kind" ? kindColor : groupColor;
  const keys = state.colorMode === "kind"
    ? [...new Set(state.focus.descendants().filter((n) => !n.children).map((n) => n.data.kind))]
    : [...new Set(state.focus.children?.map(groupKey) || [])];
  ui.renderLegend(keys.slice(0, 8).map((k) => ({ label: k, color: scale(k) })));
}

function zoom(node) {
  state.focus = node;
  render();
}

function onToggle(node) {
  const key = nodeKey(node);
  if (state.expanded.has(key)) state.expanded.delete(key);
  else state.expanded.add(key);
  render();
}

function activate(node) {
  state.selectedKey = nodeKey(node);
  if (node.children) {
    state.focus = node;
    state.expanded.add(state.selectedKey);
  }
  render();
  showPanelFor(node);
}

async function showPanelFor(node) {
  const container = ui.showPanel(node);
  const caps = await actions.capabilitiesFor(node);
  actions.renderPanelActions(container, node, caps, ctx);
}

async function onContext(event, node) {
  const caps = await actions.capabilitiesFor(node);
  actions.openContextMenu(event, node, caps, ctx);
}

function toggleAuto() {
  if (dom.autorefresh.checked) state.autoTimer = setInterval(() => loadTree(true), 15000);
  else { clearInterval(state.autoTimer); state.autoTimer = null; }
}

function aggregate(root) {
  root.eachAfter((node) => {
    const d = node.data;
    node.agg = node.children
      ? node.children.reduce((a, c) => ({
          cpuUsage: a.cpuUsage + c.agg.cpuUsage, memUsage: a.memUsage + c.agg.memUsage,
          cpuRequest: a.cpuRequest + c.agg.cpuRequest, memRequest: a.memRequest + c.agg.memRequest,
        }), { cpuUsage: 0, memUsage: 0, cpuRequest: 0, memRequest: 0 })
      : { cpuUsage: d.cpuUsage || 0, memUsage: d.memUsage || 0,
          cpuRequest: d.cpuRequest || 0, memRequest: d.memRequest || 0 };
  });
}

function nodeKey(node) {
  return node.data.uid || `${node.data.kind}:${node.data.namespace || ""}:${node.data.name}`;
}

function pathOf(node, focus) {
  const segments = [];
  let current = node;
  while (current && current !== focus) {
    segments.unshift(current.data.name);
    current = current.parent;
  }
  return segments.join(" / ");
}

function find(root, key) {
  return root.descendants().find((n) => nodeKey(n) === key) || null;
}
