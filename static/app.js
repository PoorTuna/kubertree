"use strict";

const METRIC_OPTIONS = [
  { value: "cpuUsage", label: "CPU usage", usage: true, axis: "cpu" },
  { value: "memUsage", label: "Memory usage", usage: true, axis: "mem" },
  { value: "cpuRequest", label: "CPU request", usage: false, axis: "cpu" },
  { value: "memRequest", label: "Memory request", usage: false, axis: "mem" },
];

const state = {
  root: null,        // d3.hierarchy of full tree
  focus: null,       // currently zoomed node
  metric: "cpuUsage",
  colorMode: "efficiency",
  metricsAvailable: false,
  autoTimer: null,
};

const els = {
  svg: d3.select("#treemap"),
  metric: document.getElementById("metric"),
  color: document.getElementById("color"),
  refresh: document.getElementById("refresh"),
  autorefresh: document.getElementById("autorefresh"),
  badge: document.getElementById("platform-badge"),
  banner: document.getElementById("banner"),
  breadcrumb: document.getElementById("breadcrumb"),
  tooltip: document.getElementById("tooltip"),
  panel: document.getElementById("panel"),
  modal: document.getElementById("modal"),
  modalBody: document.getElementById("modal-body"),
  modalConfirm: document.getElementById("modal-confirm"),
  modalCancel: document.getElementById("modal-cancel"),
  toast: document.getElementById("toast"),
};

const nsColor = d3.scaleOrdinal(d3.schemeTableau10);

init();

async function init() {
  populateMetricSelect();
  els.metric.value = state.metric;
  els.color.value = state.colorMode;
  els.refresh.addEventListener("click", loadTree);
  els.metric.addEventListener("change", () => { state.metric = els.metric.value; render(); });
  els.color.addEventListener("change", () => { state.colorMode = els.color.value; render(); });
  els.autorefresh.addEventListener("change", toggleAutoRefresh);
  els.modalCancel.addEventListener("click", () => els.modal.classList.add("hidden"));
  window.addEventListener("resize", render);
  await loadHealth();
  await loadTree();
}

function populateMetricSelect() {
  els.metric.innerHTML = "";
  for (const opt of METRIC_OPTIONS) {
    const node = document.createElement("option");
    node.value = opt.value;
    node.textContent = opt.label;
    els.metric.appendChild(node);
  }
}

async function loadHealth() {
  try {
    const health = await fetchJson("/api/health");
    els.badge.textContent = health.platform || "disconnected";
    state.metricsAvailable = !!health.metricsAvailable;
  } catch (err) {
    els.badge.textContent = "error";
  }
  applyMetricsAvailability();
}

function applyMetricsAvailability() {
  for (const option of els.metric.options) {
    const meta = METRIC_OPTIONS.find((m) => m.value === option.value);
    option.disabled = meta.usage && !state.metricsAvailable;
  }
  if (!state.metricsAvailable) {
    state.metric = "memRequest";
    els.metric.value = state.metric;
    els.banner.textContent = "Metrics API unavailable — showing requested resources. Install metrics-server for live usage.";
    els.banner.classList.remove("hidden");
  } else {
    els.banner.classList.add("hidden");
  }
}

async function loadTree() {
  try {
    const data = await fetchJson("/api/tree");
    state.metricsAvailable = !!data.metricsAvailable;
    applyMetricsAvailability();
    state.root = d3.hierarchy(data.tree);
    aggregate(state.root);
    state.focus = state.root;
    render();
  } catch (err) {
    showToast(`Failed to load tree: ${err.message}`, true);
  }
}

// Post-order: store summed usage/request on every node for coloring.
function aggregate(root) {
  root.eachAfter((node) => {
    const d = node.data;
    if (node.children) {
      node.agg = node.children.reduce(
        (acc, c) => ({
          cpuUsage: acc.cpuUsage + c.agg.cpuUsage,
          memUsage: acc.memUsage + c.agg.memUsage,
          cpuRequest: acc.cpuRequest + c.agg.cpuRequest,
          memRequest: acc.memRequest + c.agg.memRequest,
        }),
        { cpuUsage: 0, memUsage: 0, cpuRequest: 0, memRequest: 0 }
      );
    } else {
      node.agg = {
        cpuUsage: d.cpuUsage || 0,
        memUsage: d.memUsage || 0,
        cpuRequest: d.cpuRequest || 0,
        memRequest: d.memRequest || 0,
      };
    }
  });
}

function render() {
  if (!state.focus) return;
  const stage = els.svg.node().getBoundingClientRect();
  const width = stage.width;
  const height = stage.height;
  els.svg.attr("viewBox", `0 0 ${width} ${height}`);

  const focus = state.focus;
  focus.sum((d) => (d.children ? 0 : d[state.metric] || 0));
  focus.sort((a, b) => b.value - a.value);
  d3.treemap().size([width, height]).paddingInner(3).round(true)(focus);

  const cells = focus.children || [];
  renderBreadcrumb();

  const join = els.svg.selectAll("g.cell").data(cells, (d) => d.data.uid || d.data.name);
  join.exit().remove();
  const enter = join.enter().append("g").attr("class", "cell");
  enter.append("rect");
  enter.append("text").attr("class", "cell-name").attr("x", 6).attr("y", 18);
  enter.append("text").attr("class", "cell-kind").attr("x", 6).attr("y", 32);

  const merged = enter.merge(join);
  merged
    .on("mousemove", showTooltip)
    .on("mouseleave", hideTooltip)
    .on("click", onCellClick);
  merged.transition().duration(500)
    .attr("transform", (d) => `translate(${d.x0},${d.y0})`);
  merged.select("rect").transition().duration(500)
    .attr("width", (d) => Math.max(0, d.x1 - d.x0))
    .attr("height", (d) => Math.max(0, d.y1 - d.y0))
    .attr("fill", colorOf);
  merged.select(".cell-name").text((d) => labelFit(d, d.data.name));
  merged.select(".cell-kind").text((d) => labelFit(d, kindLabel(d)));
}

function labelFit(d, text) {
  return d.x1 - d.x0 > 60 && d.y1 - d.y0 > 34 ? text : "";
}

function kindLabel(d) {
  return `${d.data.kind} · ${formatMetric(d.value)}`;
}

function colorOf(d) {
  if (state.colorMode === "namespace") {
    return nsColor(d.data.namespace || d.data.name);
  }
  const axis = activeAxis();
  const usage = d.agg[axis + "Usage"];
  const request = d.agg[axis + "Request"];
  if (!state.metricsAvailable || request <= 0) return "#3a4150";
  const ratio = Math.min(usage / request, 1);
  return d3.interpolateRdYlGn(ratio);
}

function activeAxis() {
  return METRIC_OPTIONS.find((m) => m.value === state.metric).axis;
}

function onCellClick(event, d) {
  if (d.children) {
    state.focus = d;
    render();
  } else {
    showPanel(d);
  }
}

function renderBreadcrumb() {
  const trail = state.focus.ancestors().reverse();
  els.breadcrumb.innerHTML = "";
  trail.forEach((node, index) => {
    if (index > 0) {
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "›";
      els.breadcrumb.appendChild(sep);
    }
    const crumb = document.createElement("span");
    const isCurrent = node === state.focus;
    crumb.className = "crumb" + (isCurrent ? " current" : "");
    crumb.textContent = node.data.name;
    if (!isCurrent) crumb.addEventListener("click", () => { state.focus = node; render(); });
    els.breadcrumb.appendChild(crumb);
  });
}

function showTooltip(event, d) {
  const axis = activeAxis();
  const usage = d.agg[axis + "Usage"];
  const request = d.agg[axis + "Request"];
  const pct = state.focus.value ? ((d.value / state.focus.value) * 100).toFixed(1) : "0";
  els.tooltip.innerHTML = `
    <h4>${escapeHtml(d.data.name)}</h4>
    <div class="row"><span>Kind</span><b>${escapeHtml(d.data.kind)}</b></div>
    <div class="row"><span>Namespace</span><b>${escapeHtml(d.data.namespace || "—")}</b></div>
    <div class="row"><span>CPU usage</span><b>${fmtCpu(d.agg.cpuUsage)}</b></div>
    <div class="row"><span>Mem usage</span><b>${fmtMem(d.agg.memUsage)}</b></div>
    <div class="row"><span>${axis.toUpperCase()} req</span><b>${formatAxis(axis, request)}</b></div>
    <div class="row"><span>Efficiency</span><b>${efficiencyText(usage, request)}</b></div>
    <div class="row"><span>% of parent</span><b>${pct}%</b></div>`;
  els.tooltip.classList.remove("hidden");
  const pad = 14;
  els.tooltip.style.left = `${event.clientX + pad}px`;
  els.tooltip.style.top = `${event.clientY + pad}px`;
}

function hideTooltip() { els.tooltip.classList.add("hidden"); }

function showPanel(d) {
  const axis = activeAxis();
  els.panel.innerHTML = `
    <span class="panel-close">✕</span>
    <span class="kind-tag">${escapeHtml(d.data.kind)}</span>
    <h3>${escapeHtml(d.data.name)}</h3>
    <dl>
      <dt>Namespace</dt><dd>${escapeHtml(d.data.namespace || "—")}</dd>
      <dt>CPU usage</dt><dd>${fmtCpu(d.agg.cpuUsage)}</dd>
      <dt>Mem usage</dt><dd>${fmtMem(d.agg.memUsage)}</dd>
      <dt>CPU request</dt><dd>${fmtCpu(d.agg.cpuRequest)}</dd>
      <dt>Mem request</dt><dd>${fmtMem(d.agg.memRequest)}</dd>
      <dt>Efficiency</dt><dd>${efficiencyText(d.agg[axis + "Usage"], d.agg[axis + "Request"])}</dd>
    </dl>`;
  els.panel.querySelector(".panel-close").addEventListener("click", () => els.panel.classList.add("hidden"));
  if (d.data.deletable) {
    const btn = document.createElement("button");
    btn.className = "btn btn-danger";
    btn.textContent = "Delete (cascade)";
    btn.style.width = "100%";
    btn.addEventListener("click", () => openDeleteModal(d));
    els.panel.appendChild(btn);
  }
  els.panel.classList.remove("hidden");
}

const PROTECTED = ["kube-system", "kube-public", "kube-node-lease"];

function openDeleteModal(d) {
  const target = {
    apiVersion: d.data.apiVersion,
    kind: d.data.kind,
    name: d.data.name,
    namespace: d.data.namespace,
  };
  const protectedNs = PROTECTED.includes(d.data.namespace) ||
    (d.data.namespace || "").startsWith("openshift");
  const childCount = d.descendants().length - 1;
  els.modalBody.innerHTML = `
    <p>This deletes the resource and cascades to all owned children
       (${childCount} descendant object${childCount === 1 ? "" : "s"}).</p>
    <div class="modal-body-target">${escapeHtml(target.kind)} / ${escapeHtml(target.name)}
      ${target.namespace ? "@ " + escapeHtml(target.namespace) : ""}</div>
    ${protectedNs ? '<p class="modal-warn">⚠ System namespace — deleting here can break the cluster.</p>' : ""}`;
  els.modalConfirm.onclick = () => confirmDelete(target);
  els.modal.classList.remove("hidden");
}

async function confirmDelete(target) {
  els.modal.classList.add("hidden");
  try {
    await fetchJson("/api/delete", { method: "POST", body: JSON.stringify(target) });
    showToast(`Deleted ${target.kind} ${target.name}`);
    els.panel.classList.add("hidden");
    await loadTree();
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, true);
  }
}

function toggleAutoRefresh() {
  if (els.autorefresh.checked) {
    state.autoTimer = setInterval(loadTree, 15000);
  } else {
    clearInterval(state.autoTimer);
    state.autoTimer = null;
  }
}

// --- formatting helpers ---

function formatMetric(value) {
  return activeAxis() === "cpu" ? fmtCpu(value) : fmtMem(value);
}

function formatAxis(axis, value) {
  return axis === "cpu" ? fmtCpu(value) : fmtMem(value);
}

function fmtCpu(milli) {
  if (!milli) return "0";
  return milli < 1000 ? `${Math.round(milli)}m` : `${(milli / 1000).toFixed(2)} cores`;
}

function fmtMem(bytes) {
  if (!bytes) return "0";
  const units = ["B", "Ki", "Mi", "Gi", "Ti"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

function efficiencyText(usage, request) {
  if (!state.metricsAvailable || request <= 0) return "—";
  return `${Math.round((usage / request) * 100)}%`;
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function showToast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.className = "toast" + (isError ? " error" : "");
  setTimeout(() => els.toast.classList.add("hidden"), 4000);
}

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
