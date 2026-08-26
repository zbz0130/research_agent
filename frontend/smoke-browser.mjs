import puppeteer from "puppeteer-core";

const baseUrl = process.env.WISHFORGE_SMOKE_URL || "http://127.0.0.1:8765";
const executablePath = process.env.WISHFORGE_CHROME_PATH
  || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const expectedOverviewId = process.env.WISHFORGE_OVERVIEW_ID || "";
const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
});

const page = await browser.newPage();
const consoleErrors = [];
const pageErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("response", (response) => {
  if (response.status() >= 400) consoleErrors.push(`HTTP ${response.status()} ${response.url()}`);
});
page.on("pageerror", (error) => pageErrors.push(error.message));

try {
  await page.goto(`${baseUrl}/#research-overview`, { waitUntil: "networkidle0" });
  await page.waitForFunction(
    (overviewId) => {
      const canvas = document.querySelector("#overview-canvas");
      const selector = document.querySelector("#overview-history-select");
      const idMatches = !overviewId || selector?.value === overviewId;
      return idMatches && canvas?.querySelector("canvas") && window.WishForgeGraph?.createGraphRenderer;
    },
    { timeout: 20_000 },
    expectedOverviewId,
  );

  const initial = await page.evaluate(() => ({
    route: location.hash,
    state: document.querySelector("#overview-state-tag")?.textContent?.trim(),
    stage: document.querySelector("#overview-stage-title")?.textContent?.trim(),
    historyValue: document.querySelector("#overview-history-select")?.value,
    canvases: document.querySelectorAll("#overview-canvas canvas").length,
    graphNodes: window.WishForgeSmoke?.overviewNodePositions?.().length || 0,
    legendVisible: !document.querySelector("#overview-legend")?.classList.contains("hidden"),
    fitEnabled: !document.querySelector("#overview-fit")?.disabled,
  }));

  const canvasBounds = await page.$eval("#overview-canvas", (element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  });
  const firstNode = await page.evaluate(() => {
    return window.WishForgeSmoke?.overviewNodePositions?.()[0] || null;
  });
  if (!firstNode) throw new Error("Overview renderer exposed no visible Cytoscape nodes");
  const nodePositions = await page.evaluate(() => window.WishForgeSmoke.overviewNodePositions());
  const distinctPositions = new Set(nodePositions.map((node) => `${Math.round(node.x)},${Math.round(node.y)}`));
  if (distinctPositions.size !== nodePositions.length) {
    throw new Error("Overview layout placed multiple graph nodes at the same coordinates");
  }
  await page.$eval("#overview-canvas", (element) => element.scrollIntoView({ block: "center" }));
  const scrolledCanvasBounds = await page.$eval("#overview-canvas", (element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  });
  await page.mouse.click(scrolledCanvasBounds.left + firstNode.x, scrolledCanvasBounds.top + firstNode.y);
  await new Promise((resolve) => setTimeout(resolve, 250));
  const inspectorText = await page.$eval("#overview-inspector", (element) => element.textContent.trim());
  if (!inspectorText || inspectorText.includes("点击图中的节点")) {
    throw new Error("Overview canvas rendered but hit-tested node selection did not open the Inspector");
  }
  await page.focus("#overview-canvas");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  const keyboardInspectorText = await page.$eval(
    "#overview-inspector",
    (element) => element.textContent.trim(),
  );
  if (!keyboardInspectorText || keyboardInspectorText.includes("点击图中的节点")) {
    throw new Error("Keyboard node selection did not open the Overview Inspector");
  }

  await page.click("#overview-fit");
  await page.click("#overview-toggle-edges");
  const edgeToggle = await page.$eval("#overview-toggle-edges", (element) => ({
    pressed: element.getAttribute("aria-pressed"),
    text: element.textContent.trim(),
  }));
  if (process.env.WISHFORGE_SMOKE_SCREENSHOT) {
    await page.screenshot({ path: process.env.WISHFORGE_SMOKE_SCREENSHOT, fullPage: true });
  }

  await page.click('a[href="#workspace"]');
  await page.type("#concept", "Attention Mechanism");
  await page.select("#analysis-level", "literature");
  await page.click("#analysis-submit");
  await page.waitForSelector("#graph-save-dialog[open]", { timeout: 20_000 });
  const saveDialog = await page.evaluate(() => ({
    focusedId: document.activeElement?.id,
    overviewButtonVisible: !document.querySelector("#analysis-overview-actions")?.classList.contains("hidden"),
    conceptGraphCanvases: document.querySelectorAll("#graph canvas").length,
  }));
  await page.click("#save-graph-dialog-later");
  await page.waitForSelector("#graph-save-dialog:not([open])", { timeout: 5_000 });
  const transientState = await page.$eval(
    "#analysis-graph-save-status",
    (element) => element.textContent.trim(),
  );

  const result = {
    initial,
    inspectorText: inspectorText.slice(0, 240),
    keyboardInspectorText: keyboardInspectorText.slice(0, 160),
    edgeToggle,
    saveDialog,
    transientState,
    consoleErrors,
    pageErrors,
  };
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  const materialConsoleErrors = consoleErrors.filter(
    (message) => !message.includes("favicon.ico"),
  );
  if (materialConsoleErrors.length || pageErrors.length) process.exitCode = 1;
} finally {
  await browser.close();
}
