"use strict";

import { escapeHtml, fmtCpu, fmtMem, kindBadge, efficiencyText } from "./format.js";

const els = {
  breadcrumb: document.getElementById("breadcrumb"),
  tooltip: document.getElementById("tooltip"),
  panel: document.getElementById("panel"),
  legend: document.getElementById("legend"),
  modal: document.getElementById("modal"),
  modalTitle: document.getElementById("modal-title"),
  modalBody: document.getElementById("modal-body"),
  modalConfirm: document.getElementById("modal-confirm"),
  modalCancel: document.getElementById("modal-cancel"),
  sheet: document.getElementById("sheet"),
  sheetTitle: document.getElementById("sheet-title"),
  sheetTools: document.getElementById("sheet-tools"),
  sheetBody: document.getElementById("sheet-body"),
  sheetClose: document.getElementById("sheet-close"),
  toast: document.getElementById("toast"),
};

els.modalCancel.addEventListener("click", closeModal);
els.sheetClose.addEventListener("click", closeSheet);

export function renderBreadcrumb(focus, onCrumb) {
  const trail = focus.ancestors().reverse();
  els.breadcrumb.innerHTML = "";
  trail.forEach((node, index) => {
    if (index > 0) {
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "›";
      els.breadcrumb.appendChild(sep);
    }
    const crumb = document.createElement("span");
    const current = node === focus;
    crumb.className = "crumb" + (current ? " current" : "");
    crumb.textContent = `${kindBadge(node.data.kind)}  ${node.data.name}`;
    if (!current) crumb.addEventListener("click", () => onCrumb(node));
    els.breadcrumb.appendChild(crumb);
  });
}

export function renderLegend(items) {
  els.legend.innerHTML = "";
  for (const { label, color } of items) {
    const chip = document.createElement("span");
    chip.className = "legend-item";
    chip.innerHTML = `<i style="background:${color}"></i>${escapeHtml(label)}`;
    els.legend.appendChild(chip);
  }
}

export function showTooltip(event, node, opts) {
  const { axis, metricsAvailable } = opts;
  const usage = node.agg[axis + "Usage"];
  const request = node.agg[axis + "Request"];
  els.tooltip.innerHTML = `
    <h4>${escapeHtml(node.data.name)}</h4>
    <div class="row"><span>Kind</span><b>${escapeHtml(node.data.kind)}</b></div>
    <div class="row"><span>Namespace</span><b>${escapeHtml(node.data.namespace || "—")}</b></div>
    <div class="row"><span>CPU</span><b>${fmtCpu(node.agg.cpuUsage)} / ${fmtCpu(node.agg.cpuRequest)} req</b></div>
    <div class="row"><span>Mem</span><b>${fmtMem(node.agg.memUsage)} / ${fmtMem(node.agg.memRequest)} req</b></div>
    <div class="row"><span>Efficiency</span><b>${efficiencyText(usage, request, metricsAvailable)}</b></div>`;
  els.tooltip.classList.remove("hidden");
  els.tooltip.style.left = `${event.clientX + 14}px`;
  els.tooltip.style.top = `${event.clientY + 14}px`;
}

export function hideTooltip() {
  els.tooltip.classList.add("hidden");
}

// Render the info panel. Action buttons are filled into #panel-actions by the
// caller (actions.js) so this module stays free of any tool logic.
export function showPanel(node) {
  const bar = (usage, request) => {
    const pct = request > 0 ? Math.min((usage / request) * 100, 100) : 0;
    return `<div class="meter"><span style="width:${pct}%"></span></div>`;
  };
  els.panel.innerHTML = `
    <span class="panel-close">✕</span>
    <span class="kind-tag">${escapeHtml(node.data.kind)}</span>
    <h3>${escapeHtml(node.data.name)}</h3>
    <dl>
      <dt>Namespace</dt><dd>${escapeHtml(node.data.namespace || "—")}</dd>
      <dt>CPU</dt><dd>${fmtCpu(node.agg.cpuUsage)} / ${fmtCpu(node.agg.cpuRequest)}</dd>
    </dl>
    ${bar(node.agg.cpuUsage, node.agg.cpuRequest)}
    <dl><dt>Mem</dt><dd>${fmtMem(node.agg.memUsage)} / ${fmtMem(node.agg.memRequest)}</dd></dl>
    ${bar(node.agg.memUsage, node.agg.memRequest)}
    <div class="panel-actions" id="panel-actions"></div>`;
  els.panel.querySelector(".panel-close").addEventListener("click", hidePanel);
  els.panel.classList.remove("hidden");
  return els.panel.querySelector("#panel-actions");
}

export function hidePanel() {
  els.panel.classList.add("hidden");
}

export function openConfirm({ title, bodyHtml, confirmLabel = "Confirm", danger = true, onConfirm }) {
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = bodyHtml;
  els.modalConfirm.textContent = confirmLabel;
  els.modalConfirm.className = "btn " + (danger ? "btn-danger" : "btn-accent");
  els.modalConfirm.onclick = async () => {
    closeModal();
    await onConfirm(els.modalBody);
  };
  els.modal.classList.remove("hidden");
  const input = els.modalBody.querySelector("input");
  if (input) input.focus();
}

export function closeModal() {
  els.modal.classList.add("hidden");
  els.modalConfirm.onclick = null;
}

export function openSheet(title) {
  els.sheetTitle.textContent = title;
  els.sheetTools.innerHTML = "";
  els.sheetBody.innerHTML = "";
  els.sheet.classList.remove("hidden");
  return { body: els.sheetBody, tools: els.sheetTools };
}

export function closeSheet() {
  els.sheet.classList.add("hidden");
  els.sheetBody.innerHTML = "";
  els.sheet.dispatchEvent(new CustomEvent("sheet-closed"));
}

export function onSheetClosed(handler) {
  els.sheet.addEventListener("sheet-closed", handler, { once: true });
}

export function showToast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.className = "toast" + (isError ? " error" : "");
  setTimeout(() => els.toast.classList.add("hidden"), 4000);
}
