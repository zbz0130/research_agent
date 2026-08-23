const EDITABLE_NODE_TYPES = new Set(["problem", "method", "direction", "concept", "note"]);
const EDITABLE_RELATIONS = new Set(["related_to", "has_problem", "uses", "improves", "supports", "is_a"]);

function requiredText(value, label) {
  const normalized = String(value || "").trim();
  if (!normalized) throw new Error(`${label}不能为空`);
  return normalized;
}

export function buildAddNodeOperations({ id, edgeId, label, nodeType, parentId }) {
  const nodeId = requiredText(id, "节点 ID");
  const connectionId = requiredText(edgeId, "连线 ID");
  const name = requiredText(label, "节点名称");
  const parent = requiredText(parentId, "父节点");
  const type = EDITABLE_NODE_TYPES.has(nodeType) ? nodeType : "note";
  if (nodeId === parent) throw new Error("节点不能连接到自身");
  return [
    {
      op: "add_node",
      node: {
        id: nodeId,
        label: name,
        summary: `用户添加的${type}节点：${name}`,
        node_type: type,
        evidence_ids: [],
        editable: true,
      },
    },
    {
      op: "add_edge",
      edge: {
        id: connectionId,
        source: parent,
        target: nodeId,
        relation: "related_to",
        evidence_ids: [],
        source_kind: "user",
      },
    },
  ];
}

export function buildAddEdgeOperation({ id, sourceId, targetId, relation }) {
  const edgeId = requiredText(id, "连线 ID");
  const source = requiredText(sourceId, "起点");
  const target = requiredText(targetId, "终点");
  if (source === target) throw new Error("请选择两个不同的节点");
  return {
    op: "add_edge",
    edge: {
      id: edgeId,
      source,
      target,
      relation: EDITABLE_RELATIONS.has(relation) ? relation : "related_to",
      evidence_ids: [],
      source_kind: "user",
    },
  };
}

export function buildRemoveNodeOperation(graph, nodeId) {
  const selectedId = requiredText(nodeId, "选中节点");
  const node = graph?.nodes?.find((item) => item.id === selectedId);
  if (!node) throw new Error("选中节点不存在");
  if (selectedId === graph?.root_id) throw new Error("根节点不能删除");
  if (node.editable === false) throw new Error("该节点受证据保护，不能直接删除");
  return { op: "remove_node", node_id: selectedId };
}

export function buildRemoveEdgeOperation(graph, edgeId) {
  const selectedId = requiredText(edgeId, "连线");
  if (!graph?.edges?.some((edge) => edge.id === selectedId)) throw new Error("当前连线不存在");
  return { op: "remove_edge", node_id: selectedId };
}
