"use strict";

import { fmtAxis, kindIcon } from "./format.js";

const HEADER = 20;

// Render the focus subtree as a nested treemap: every descendant level is drawn
// at once (header bar for groups, filled cell for leaves), so the ownership
// grouping is visible without drilling. Returns nothing; mutates the SVG.
export function renderTreemap(svg, focus, opts) {
  const { width, height } = svg.node().getBoundingClientRect();
  svg.attr("viewBox", `0 0 ${width} ${height}`);

  focus.sum((d) => (d.children ? 0 : d[opts.metric] || 0));
  if (!focus.value) focus.sum((d) => (d.children ? 0 : 1)); // idle subtree → equal cells
  focus.sort((a, b) => b.value - a.value);
  d3.treemap().size([width, height]).paddingTop(HEADER).paddingInner(2).round(true)(focus);

  const nodes = focus.descendants();
  const join = svg.selectAll("g.node").data(nodes, (d) => d.__id);
  join.exit().transition().duration(300).style("opacity", 0).remove();

  const enter = join.enter().append("g").attr("class", "node").style("opacity", 0);
  enter.append("rect");
  enter.append("text").attr("class", "label");

  const merged = enter.merge(join);
  merged
    .style("cursor", (d) => (d === focus ? "default" : "pointer"))
    .on("mousemove", (e, d) => opts.onHover(e, d))
    .on("mouseleave", () => opts.onLeave())
    .on("click", (e, d) => onClick(e, d, focus, opts))
    .on("contextmenu", (e, d) => { e.preventDefault(); opts.onContext(e, d); });

  merged.transition().duration(650).style("opacity", 1)
    .attr("transform", (d) => `translate(${d.x0},${d.y0})`);

  merged.select("rect")
    .classed("leaf", (d) => !d.children)
    .classed("selected", (d) => d.data.uid && d.data.uid === opts.selectedUid)
    .transition().duration(650)
    .attr("width", (d) => Math.max(0, d.x1 - d.x0))
    .attr("height", (d) => Math.max(0, d.y1 - d.y0))
    .attr("fill", (d) => fillOf(d, focus, opts))
    .attr("fill-opacity", (d) => (d.children ? 0.16 + 0.05 * (d.depth - focus.depth) : 1));

  merged.select("text.label")
    .attr("x", 7)
    .attr("y", (d) => (d.children ? 14 : 16))
    .attr("class", (d) => (d.children ? "label group" : "label"))
    .text((d) => labelFor(d, focus));

  merged.order();
}

function onClick(event, node, focus, opts) {
  event.stopPropagation();
  if (node === focus) return;
  opts.onActivate(node);
}

function labelFor(node, focus) {
  if (node === focus) return "";
  const w = node.x1 - node.x0;
  const h = node.y1 - node.y0;
  if (w < 46 || h < 16) return "";
  const chars = Math.floor((w - 14) / 7);
  if (node.children) {
    const head = `${kindIcon(node.data.kind)} ${node.data.name}`;
    return head.length > chars ? head.slice(0, Math.max(1, chars - 1)) + "…" : head;
  }
  return node.data.name.length > chars
    ? node.data.name.slice(0, Math.max(1, chars - 1)) + "…"
    : node.data.name;
}

function fillOf(node, focus, opts) {
  if (node.children) return opts.groupColor(groupKey(node));
  if (opts.colorMode === "kind") return opts.kindColor(node.data.kind);
  if (opts.colorMode === "efficiency") return efficiencyColor(node, opts);
  return opts.groupColor(groupKey(node));
}

function efficiencyColor(node, opts) {
  const usage = node.agg[opts.axis + "Usage"];
  const request = node.agg[opts.axis + "Request"];
  if (!opts.metricsAvailable || request <= 0) return "#3a4150";
  return d3.interpolateRdYlGn(Math.min(usage / request, 1));
}

export function groupKey(node) {
  return node.data.namespace || node.data.name;
}

export { HEADER, fmtAxis };
