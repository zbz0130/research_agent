const clamp = (value, minimum = 0, maximum = 1) => (
  Math.min(maximum, Math.max(minimum, Number.isFinite(Number(value)) ? Number(value) : minimum))
);

function mixChannel(start, end, amount) {
  return Math.round(start + ((end - start) * clamp(amount)));
}

function mixColor(start, end, amount) {
  const value = clamp(amount);
  return `rgb(${mixChannel(start[0], end[0], value)}, ${mixChannel(start[1], end[1], value)}, ${mixChannel(start[2], end[2], value)})`;
}

export function scoreLegendStops() {
  return {
    recency: [
      { score: 0, color: mixColor([196, 219, 247], [31, 78, 196], 0) },
      { score: 0.5, color: mixColor([196, 219, 247], [31, 78, 196], 0.5) },
      { score: 1, color: mixColor([196, 219, 247], [31, 78, 196], 1) },
    ],
    heat: [
      { score: 0, size: 56 },
      { score: 0.5, size: 78 },
      { score: 1, size: 104 },
    ],
  };
}

export function nodeRole(node, rootId) {
  if (node?.id === rootId) return "root";
  return node?.role || node?.node_type || "concept";
}

export function nodeAppearance(node, graph) {
  const role = nodeRole(node, graph?.root_id);
  const visual = node?.visual || {};
  const recency = clamp(visual.recency_score, 0, 1);
  const heat = clamp(visual.heat_score ?? visual.activity_score, 0, 1);
  const backendRadius = Number(visual.radius);
  let width = 76;
  let height = 76;
  let background = "#b9d4ee";
  let foreground = "#111827";
  let border = "#6f9fc8";

  if (role === "root") {
    width = 146;
    height = 82;
    background = "#b7d6ef";
    border = "#5a8fbc";
  } else if (role === "direction") {
    const diameter = Number.isFinite(backendRadius)
      ? clamp(backendRadius * 2, 56, 128)
      : 56 + (48 * Math.sqrt(heat));
    width = diameter;
    height = diameter;
    background = mixColor([201, 224, 244], [129, 176, 219], heat);
    border = "#6699c7";
  } else if (role === "paper") {
    const diameter = Number.isFinite(backendRadius)
      ? clamp(backendRadius * 2, 34, 70)
      : 34 + (16 * recency);
    // Keep every paper as a true circular leaf.  The inspector carries the
    // complete title and the "problem / method / how" explanation, while the
    // canvas intentionally uses a compact label to preserve Connected-Papers
    // style visual scanning instead of reverting to stacked text cards.
    width = clamp(diameter, 42, 74);
    height = width;
    background = node?.year == null
      ? "#c9d2dc"
      : mixColor([220, 234, 248], [133, 179, 223], recency);
    border = recency > 0.55 ? "#5c91c5" : "#9abadd";
  } else if (role === "problem") {
    const diameter = Number.isFinite(backendRadius)
      ? clamp(backendRadius * 2, 64, 132)
      : 64 + (56 * Math.sqrt(heat));
    width = diameter;
    height = diameter;
    background = "#e6b1b5";
    border = "#b9626a";
  } else if (role === "method") {
    const diameter = Number.isFinite(backendRadius)
      ? clamp(backendRadius * 2, 54, 116)
      : 54 + (46 * Math.sqrt(heat));
    width = diameter;
    height = diameter;
    background = "#c6b9ee";
    border = "#8071bc";
  } else if (role === "idea") {
    background = "#ead39b";
    border = "#b58a32";
  }

  return {
    role,
    width,
    height,
    background,
    foreground,
    border,
    recency,
    heat,
  };
}

export function compactNodeLabel(value, maximum = 38) {
  const text = String(value || "未命名节点").trim();
  return text.length > maximum ? `${text.slice(0, maximum - 1)}…` : text;
}
