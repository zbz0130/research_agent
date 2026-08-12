import "../runtime-config.js";
import { createGraphRenderer } from "./graph/graph-renderer.js";
import { inspectorMarkup } from "./graph/graph-inspector.js";
import { nodeAppearance, scoreLegendStops } from "./graph/graph-metrics.js";

let cytoscapeModule = null;
try {
  // Vite bundles this local dependency. In a raw FastAPI checkout without
  // node_modules, the rest of the research workbench still opens and shows a
  // clear graph-renderer fallback instead of failing the entire page.
  cytoscapeModule = await import("cytoscape");
} catch (error) {
  console.warn("WishForge graph renderer is unavailable until npm dependencies are installed.", error);
}

window.WishForgeGraph = Object.freeze({
  createGraphRenderer: cytoscapeModule
    ? (container, options = {}) => createGraphRenderer(cytoscapeModule.default || cytoscapeModule, container, options)
    : null,
  inspectorMarkup,
  nodeAppearance,
  scoreLegendStops,
});

await import("../app.js");
