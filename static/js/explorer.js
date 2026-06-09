"use strict";

import { fmtAxis, kindIcon, efficiencyText, escapeHtml } from "./format.js";

// WizTree-style table over the same hierarchy as the treemap. Tree mode draws an
// indented, expand/collapse drilldown; flat mode lists every leaf container by
// full path, sorted by the selected metric. Mutates `container`; returns nothing.
export function renderExplorer(container, focus, opts) {
  container.innerHTML = "";
  container.appendChild(headerRow(opts));
  const rows = opts.mode === "flat" ? flatRows(focus, opts) : treeRows(focus, opts);
  rows.forEach((row) => container.appendChild(row));
}

function headerRow(opts) {
  const head = document.createElement("div");
  head.className = "exrow exhead";
  head.innerHTML = `
    <div class="ex-name">${opts.mode === "flat" ? "Path" : "Name"}</div>
    <div class="ex-size">${opts.axis === "cpu" ? "CPU" : "Memory"}</div>
    <div class="ex-pct">% of ${opts.mode === "flat" ? "view" : "parent"}</div>
    <div class="ex-eff">Eff.</div>`;
  return head;
}

function treeRows(focus, opts) {
  const rows = [];
  const walk = (node, depth) => {
    rows.push(makeRow(node, opts, focus, depth));
    if (node.children && opts.expanded.has(opts.keyOf(node))) {
      childrenByMetric(node, opts).forEach((child) => walk(child, depth + 1));
    }
  };
  walk(focus, 0);
  return rows;
}

function flatRows(focus, opts) {
  const leaves = focus.descendants().filter((node) => !node.children && node !== focus);
  leaves.sort((a, b) => value(b, opts) - value(a, opts));
  return leaves.map((leaf) => makeRow(leaf, opts, focus, 0));
}

function makeRow(node, opts, focus, depth) {
  const own = value(node, opts);
  const base = opts.mode === "flat" ? value(focus, opts) : parentValue(node, opts);
  const pct = base > 0 ? (own / base) * 100 : 0;
  const hasChildren = !!node.children;
  const expanded = hasChildren && opts.expanded.has(opts.keyOf(node));
  const caret = hasChildren ? (expanded ? "▾" : "▸") : "";
  const indent = opts.mode === "flat" ? 4 : depth * 16 + 4;
  const label = opts.mode === "flat" ? opts.pathOf(node, focus) : node.data.name;

  const row = document.createElement("div");
  row.className = "exrow";
  if (node === focus) row.classList.add("root");
  if (opts.selectedKey && opts.keyOf(node) === opts.selectedKey) row.classList.add("selected");
  row.innerHTML = `
    <div class="ex-name" style="padding-left:${indent}px">
      <span class="ex-caret">${caret}</span>
      <span class="ex-icon">${kindIcon(node.data.kind)}</span>
      <span class="ex-text">${escapeHtml(label)}</span>
    </div>
    <div class="ex-size">${fmtAxis(opts.axis, own)}</div>
    <div class="ex-pct">
      <div class="exbar"><span style="width:${Math.min(pct, 100)}%"></span></div>
      <span class="ex-pctnum">${pct.toFixed(pct < 10 ? 1 : 0)}%</span>
    </div>
    <div class="ex-eff">${efficiencyText(
      node.agg[opts.axis + "Usage"], node.agg[opts.axis + "Request"], opts.metricsAvailable)}</div>`;

  row.addEventListener("click", () => opts.onActivate(node));
  row.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    opts.onContext(event, node);
  });
  if (hasChildren) {
    row.querySelector(".ex-caret").addEventListener("click", (event) => {
      event.stopPropagation();
      opts.onToggle(node);
    });
  }
  return row;
}

function childrenByMetric(node, opts) {
  return [...node.children].sort((a, b) => value(b, opts) - value(a, opts));
}

function value(node, opts) {
  return node.agg[opts.metric] || 0;
}

function parentValue(node, opts) {
  return node.parent ? value(node.parent, opts) : value(node, opts);
}
