import "../runtime-config.js";
import { desktopBridgeReady } from "./desktop-bridge.js";
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

// The desktop bridge resolves the ephemeral localhost sidecar address before
// application requests begin. In a normal browser it resolves to a no-op
// bridge, so Vite/FastAPI development keeps exactly the same fallback.
await desktopBridgeReady;

await import("../app.js");
