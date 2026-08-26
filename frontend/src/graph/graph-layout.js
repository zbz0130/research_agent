export function hasCompleteSavedPositions(graph) {
  const nodes = graph?.nodes || [];
  return nodes.length > 0 && nodes.every((node) => {
    const x = node?.visual?.x;
    const y = node?.visual?.y;
    return x !== null && x !== undefined && x !== ""
      && y !== null && y !== undefined && y !== ""
      && Number.isFinite(Number(x)) && Number.isFinite(Number(y));
  });
}

export function graphLayoutOptions(graph, kind = graph?.graph_kind) {
  const hasSavedPositions = hasCompleteSavedPositions(graph);
  if (hasSavedPositions || graph?.layout_algorithm === "preset") {
    return { name: "preset", fit: true, padding: 52, animate: false };
  }
  if (kind === "research_direction") {
    const rootSelector = graph?.root_id
      ? `#${typeof CSS !== "undefined" && CSS.escape ? CSS.escape(String(graph.root_id)) : String(graph.root_id).replace(/[^a-zA-Z0-9_-]/g, "\\$&")}`
      : undefined;
    return {
      name: "breadthfirst",
      directed: true,
      roots: rootSelector,
      circle: false,
      grid: false,
      spacingFactor: 1.7,
      avoidOverlap: true,
      nodeDimensionsIncludeLabels: true,
      padding: 54,
      animate: false,
    };
  }
  return {
    name: "cose",
    idealEdgeLength: 155,
    nodeOverlap: 30,
    componentSpacing: 96,
    nodeRepulsion: 720000,
    edgeElasticity: 120,
    nestingFactor: 1.15,
    gravity: 55,
    numIter: 1000,
    initialTemp: 180,
    coolingFactor: 0.96,
    minTemp: 1,
    padding: 52,
    animate: false,
    randomize: true,
  };
}
