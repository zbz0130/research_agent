function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}

function safeLink(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (error) {
    return null;
  }
}

function detailBlock(label, value) {
  if (!String(value || "").trim()) return "";
  return `<section class="graph-inspector-section"><p>${esc(label)}</p><div>${esc(value)}</div></section>`;
}

const ROLE_LABELS = {
  root: "研究主题",
  problem: "核心问题",
  method: "方法路线",
  direction: "研究方向",
  paper: "论文证据",
  concept: "概念",
  idea: "研究想法",
  note: "注释",
};

const RELATION_LABELS = {
  is_a: "属于",
  part_of: "组成",
  related_to: "相关",
  supports: "论文证据",
  contradicts: "反驳",
  has_problem: "核心问题",
  improves: "改进",
  uses: "方法路线",
  inspired_by: "启发自",
};

function evidenceMarkup(items = []) {
  const evidence = items.filter((item) => item && (item.excerpt || item.claim)).slice(0, 8);
  if (!evidence.length) return "";
  return `<section class="graph-inspector-section graph-inspector-evidence"><p>证据摘录</p><ul>${evidence.map((item) => `
    <li><blockquote>${esc(item.excerpt || item.claim)}</blockquote>${item.location ? `<small>${esc(item.location)}</small>` : ""}</li>
  `).join("")}</ul></section>`;
}

function papersMarkup(items = []) {
  const papers = items.filter((item) => item && item.title).slice(0, 8);
  if (!papers.length) return "";
  return `<section class="graph-inspector-section"><p>来源论文</p><ul>${papers.map((paper) => {
    const url = safeLink(paper.url);
    const title = esc(paper.title);
    return `<li>${url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer noopener">${title}</a>` : title}${paper.year ? `<small>${esc(paper.year)}</small>` : ""}</li>`;
  }).join("")}</ul></section>`;
}

export function inspectorMarkup(node, relatedEdges = [], options = {}) {
  if (!node) {
    return '<div class="graph-inspector-empty"><span>◎</span><p>点击图中的节点，在这里查看解释、论文证据和关系。</p></div>';
  }
  const role = node.role || node.node_type || "concept";
  const sourceUrl = safeLink(node.source_url);
  const visual = node.visual || {};
  const evidenceRange = node.summary_level === "arxiv_sections"
    ? "已解析开放 arXiv 章节"
    : node.summary_level === "abstract_only"
      ? "仅基于摘要与元数据"
      : "模型推断，未直接对应论文事实";
  const sourceSections = (node.source_sections || []).join(" · ");
  const heatSources = (visual.heat_source || []).join(" · ");
  const paperIds = [node.paper_id, ...(node.paper_ids || [])].filter(Boolean);
  return `
    <div class="graph-inspector-heading">
      <div>
        <p class="section-label">${esc(ROLE_LABELS[role] || role)}</p>
        <h3>${esc(node.label || "未命名节点")}</h3>
      </div>
      <span class="tag">${esc(node.confidence || "low")} confidence</span>
    </div>
    <p class="graph-inspector-scope">${esc(evidenceRange)}</p>
    ${detailBlock("易懂解释", node.explanation || node.summary)}
    ${detailBlock("解决什么问题", node.problem_summary)}
    ${detailBlock("提出什么方法", node.method_summary)}
    ${detailBlock("大概怎么做", node.how_it_works)}
    ${detailBlock("局限", node.limitations_summary)}
    ${detailBlock("来源章节", sourceSections)}
    ${evidenceMarkup(node.evidence_cards || [])}
    ${papersMarkup(node.source_papers || [])}
    ${(node.inspector_warnings || []).length ? `<section class="graph-inspector-section warning-box"><p>范围提示</p><ul>${node.inspector_warnings.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></section>` : ""}
    ${paperIds.length ? detailBlock("来源论文 ID", [...new Set(paperIds)].join(" · ")) : ""}
    ${Number.isFinite(Number(node.year)) || Number.isFinite(Number(node.citation_count)) ? `
      <dl class="graph-inspector-meta">
        ${Number.isFinite(Number(node.year)) ? `<div><dt>年份</dt><dd>${esc(node.year)}</dd></div>` : ""}
        ${Number.isFinite(Number(node.citation_count)) ? `<div><dt>引用数</dt><dd>${esc(node.citation_count)}</dd></div>` : ""}
      </dl>
    ` : ""}
    ${["problem", "method", "direction"].includes(role) ? `
      <section class="graph-inspector-section graph-inspector-metric">
        <p>范围内活跃度</p>
        <div class="metric-bar"><span style="width:${Math.round((Number(visual.heat_score) || 0) * 100)}%"></span></div>
        <small>${esc(heatSources || "依据当前分支论文数量、新论文比例等可用项计算")}</small>
      </section>
    ` : ""}
    ${relatedEdges.length ? `
      <section class="graph-inspector-section">
        <p>相关关系</p>
        <ul class="graph-inspector-relations">${relatedEdges.slice(0, 12).map((edge) => `
          <li>${esc(edge.source)} <strong>${esc(RELATION_LABELS[edge.relation] || edge.relation || "相关")}</strong> ${esc(edge.target)}</li>
        `).join("")}</ul>
      </section>
    ` : ""}
    ${sourceUrl ? `<a class="graph-source-button" href="${esc(sourceUrl)}" target="_blank" rel="noreferrer noopener">打开论文来源 ↗</a>` : ""}
    ${["method", "direction"].includes(role) && options.allowExpand ? `<button type="button" class="secondary graph-expand-button" data-overview-expand-node>${role === "method" ? "继续细化这条方法路线" : "继续调研这个方向"}</button>` : ""}
  `;
}
