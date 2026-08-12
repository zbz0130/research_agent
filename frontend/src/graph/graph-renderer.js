import { graphLayoutOptions } from "./graph-layout.js";
import { compactNodeLabel, nodeAppearance } from "./graph-metrics.js";

function confidenceOpacity(confidence) {
  return confidence === "low" ? 0.4 : confidence === "medium" ? 0.68 : 0.9;
}

function edgeLineStyle(sourceKind) {
  return sourceKind === "model_inference" ? "dashed" : "solid";
}

function graphElements(graph) {
  const nodes = (graph?.nodes || []).map((node) => {
    const appearance = nodeAppearance(node, graph);
    return {
      group: "nodes",
      data: {
        id: String(node.id),
        label: compactNodeLabel(node.label, appearance.role === "paper" ? 42 : 26),
        fullLabel: node.label,
        role: appearance.role,
        width: appearance.width,
        height: appearance.height,
        background: appearance.background,
        foreground: appearance.foreground,
        border: appearance.border,
        heat: appearance.heat,
        recency: appearance.recency,
        raw: node,
      },
      position: Number.isFinite(Number(node?.visual?.x)) && Number.isFinite(Number(node?.visual?.y))
        && node?.visual?.x !== null && node?.visual?.x !== undefined && node?.visual?.x !== ""
        && node?.visual?.y !== null && node?.visual?.y !== undefined && node?.visual?.y !== ""
        ? { x: Number(node.visual.x), y: Number(node.visual.y) }
        : undefined,
    };
  });
  const edges = (graph?.edges || []).map((edge, index) => ({
    group: "edges",
    data: {
      id: String(edge.id || `edge-${index}-${edge.source}-${edge.target}`),
      source: String(edge.source),
      target: String(edge.target),
      relation: edge.relation || "related_to",
      sourceKind: edge.source_kind || "model_inference",
      lineStyle: edgeLineStyle(edge.source_kind),
      opacity: confidenceOpacity(edge.confidence),
      weight: Math.max(1, Math.min(5, Number(edge.weight) || 1)),
      raw: edge,
    },
  }));
  return [...nodes, ...edges];
}

function normalizeFilterValue(value) {
  return String(value || "").trim().toLocaleLowerCase();
}

export function graphNodeMatchesFilter(raw = {}, role = "", { query = "", roles = [] } = {}) {
  const normalizedQuery = normalizeFilterValue(query);
  const allowedRoles = new Set((roles || []).map(normalizeFilterValue).filter(Boolean));
  const searchable = [
    raw.label,
    raw.explanation,
    raw.summary,
    raw.problem_summary,
    raw.method_summary,
    raw.how_it_works,
  ].map(normalizeFilterValue).join(" ");
  const matchesQuery = !normalizedQuery || searchable.includes(normalizedQuery);
  const matchesRole = !allowedRoles.size || allowedRoles.has(normalizeFilterValue(role));
  return matchesQuery && matchesRole;
}

export function graphEdgeVisible({
  confidence = "low",
  endpointsVisible = true,
  lowConfidenceVisible = true,
} = {}) {
  return Boolean(endpointsVisible) && (Boolean(lowConfidenceVisible) || confidence !== "low");
}

function nodeMatchesFilter(node, filterState) {
  return graphNodeMatchesFilter(node.data("raw") || {}, node.data("role"), {
    query: filterState.query,
    roles: [...filterState.roles],
  });
}

export function createGraphRenderer(cytoscape, container, options = {}) {
  if (!container) throw new Error("Graph container is required");
  if (!container.hasAttribute("tabindex")) container.tabIndex = 0;
  container.setAttribute("role", "application");
  container.setAttribute(
    "aria-description",
    "使用方向键选择节点，按 Enter 查看节点详情；鼠标可缩放、平移和拖拽。",
  );
  let graph = options.graph || { nodes: [], edges: [] };
  let nodeHandler = typeof options.onNodeSelect === "function" ? options.onNodeSelect : () => {};
  let lowConfidenceVisible = true;
  let destroyed = false;
  let keyboardHandler = null;
  const filterState = { query: "", roles: new Set() };
  const cy = cytoscape({
    container,
    elements: graphElements(graph),
    minZoom: 0.18,
    maxZoom: 3.5,
    wheelSensitivity: 0.18,
    boxSelectionEnabled: false,
    autoungrabify: false,
    style: [
      {
        selector: "node",
        style: {
          shape: "ellipse",
          width: "data(width)",
          height: "data(height)",
          "background-color": "data(background)",
          "border-width": 2,
          "border-color": "data(border)",
          label: "data(label)",
          color: "data(foreground)",
          "font-family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          "font-size": 11,
          "font-weight": 650,
          "text-wrap": "wrap",
          "text-max-width": 104,
          "text-valign": "center",
          "text-halign": "center",
          "overlay-opacity": 0,
          "shadow-color": "#0b2033",
          "shadow-blur": 14,
          "shadow-opacity": 0.14,
          "shadow-offset-y": 5,
        },
      },
      {
        selector: "node[role = 'root']",
        style: {
          shape: "ellipse",
          "font-size": 14,
          "font-weight": 800,
          "text-max-width": 126,
          "border-width": 3,
        },
      },
      {
        selector: "node[role = 'paper']",
        style: {
          shape: "ellipse",
          "font-size": 10,
          "text-max-width": 104,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-width": 5,
          "border-color": "#0a84ff",
          "shadow-color": "#0a84ff",
          "shadow-opacity": 0.35,
          "shadow-blur": 22,
        },
      },
      {
        selector: "edge",
        style: {
          width: "data(weight)",
          opacity: "data(opacity)",
          "line-color": "#7895b2",
          "target-arrow-color": "#7895b2",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "line-style": "data(lineStyle)",
          label: "data(relation)",
          color: "#60758a",
          "font-size": 8,
          "text-rotation": "autorotate",
          "text-background-color": "#f5f7fa",
          "text-background-opacity": 0.82,
          "text-background-padding": 2,
          "text-margin-y": -7,
          "arrow-scale": 0.8,
        },
      },
      {
        selector: "edge[sourceKind = 'citation']",
        style: { "line-color": "#477aa9", "target-arrow-color": "#477aa9" },
      },
      {
        selector: "edge[sourceKind = 'user']",
        style: { "line-color": "#0a84ff", "target-arrow-color": "#0a84ff", width: 3 },
      },
      {
        selector: ".is-muted",
        style: { opacity: 0.09 },
      },
    ],
    layout: graphLayoutOptions(graph, options.kind),
  });

  cy.on("tap", "node", (event) => {
    const node = event.target;
    const raw = node.data("raw");
    const relatedEdges = node.connectedEdges().map((edge) => edge.data("raw"));
    nodeHandler(raw, relatedEdges, node);
  });

  cy.on("mouseover", "node", (event) => {
    const node = event.target;
    cy.elements().addClass("is-muted");
    node.closedNeighborhood().removeClass("is-muted");
  });
  cy.on("mouseout", "node", () => cy.elements().removeClass("is-muted"));

  const visibleNodes = () => cy.nodes(":visible").sort((left, right) => {
    const yDelta = left.position("y") - right.position("y");
    return Math.abs(yDelta) > 1 ? yDelta : left.position("x") - right.position("x");
  });
  const selectByOffset = (offset) => {
    const nodes = visibleNodes();
    if (!nodes.length) return;
    const selected = cy.$("node:selected").first();
    const currentIndex = selected.length ? nodes.indexOf(selected) : -1;
    const nextIndex = currentIndex < 0
      ? 0
      : (currentIndex + offset + nodes.length) % nodes.length;
    const next = nodes[nextIndex];
    cy.$("node:selected").unselect();
    next.select();
    cy.animate({ center: { eles: next }, duration: 120 });
  };
  const openSelectedNode = () => {
    const selected = cy.$("node:selected").first();
    if (!selected.length) return;
    nodeHandler(
      selected.data("raw"),
      selected.connectedEdges().map((edge) => edge.data("raw")),
      selected,
    );
  };
  keyboardHandler = (event) => {
    if (["ArrowRight", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      selectByOffset(1);
    } else if (["ArrowLeft", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      selectByOffset(-1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!cy.$("node:selected").length) selectByOffset(1);
      openSelectedNode();
    }
  };
  container.addEventListener("keydown", keyboardHandler);

  cy.on("dragfree", "node", () => {
    if (typeof options.onPositionChange === "function") {
      options.onPositionChange(cy.nodes().map((node) => ({
        id: node.id(),
        x: Number(node.position("x")),
        y: Number(node.position("y")),
      })));
    }
  });

  const applyVisibility = () => {
    cy.nodes().forEach((node) => {
      node.style("display", nodeMatchesFilter(node, filterState) ? "element" : "none");
    });
    cy.edges().forEach((edge) => {
      const confidence = edge.data("raw")?.confidence || "low";
      const endpointsVisible = edge.source().style("display") !== "none"
        && edge.target().style("display") !== "none";
      edge.style("display", graphEdgeVisible({
        confidence,
        endpointsVisible,
        lowConfidenceVisible,
      }) ? "element" : "none");
    });
  };

  return {
    instance: cy,
    fit: () => {
      cy.resize();
      cy.fit(undefined, 42);
    },
    resize: () => cy.resize(),
    visibleNodeScreenPositions: () => cy.nodes(":visible").map((node) => ({
      id: node.id(),
      x: Number(node.renderedPosition("x")),
      y: Number(node.renderedPosition("y")),
    })),
    destroy: () => {
      if (destroyed) return;
      destroyed = true;
      if (keyboardHandler) container.removeEventListener("keydown", keyboardHandler);
      cy.destroy();
    },
    selectNode: (nodeId) => {
      const element = cy.$id(String(nodeId));
      if (element.length) {
        cy.$("node:selected").unselect();
        element.select();
        cy.animate({ center: { eles: element }, duration: 180 });
      }
    },
    setNodeHandler: (handler) => {
      nodeHandler = typeof handler === "function" ? handler : () => {};
    },
    update: (nextGraph, updateOptions = {}) => {
      graph = nextGraph;
      cy.elements().remove();
      cy.add(graphElements(nextGraph));
      const layout = graphLayoutOptions(nextGraph, updateOptions.kind || options.kind);
      cy.layout(layout).run();
      applyVisibility();
      cy.resize();
      cy.fit(undefined, 42);
    },
    setLowConfidenceVisible: (visible) => {
      lowConfidenceVisible = Boolean(visible);
      applyVisibility();
    },
    filter: ({ query = "", roles = [] } = {}) => {
      filterState.query = normalizeFilterValue(query);
      filterState.roles = new Set((roles || []).map(normalizeFilterValue).filter(Boolean));
      applyVisibility();
    },
    focusMatches: ({ query = "", roles = [] } = {}) => {
      const normalizedQuery = normalizeFilterValue(query);
      const allowedRoles = new Set((roles || []).map(normalizeFilterValue).filter(Boolean));
      const matches = cy.nodes().filter((node) => {
        return graphNodeMatchesFilter(node.data("raw") || {}, node.data("role"), {
          query: normalizedQuery,
          roles: [...allowedRoles],
        });
      });
      if (matches.length) cy.fit(matches.union(matches.connectedEdges()), 72);
      return matches.length;
    },
    savePositions: () => cy.nodes().map((node) => ({
      id: node.id(),
      x: Number(node.position("x")),
      y: Number(node.position("y")),
    })),
  };
}
