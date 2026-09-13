/* Renders the console against a real captured /api/state payload, in every tab,
   and fails loudly on any DOM or JS error. Run: node tests/console_render.js */

const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "..");
const state = JSON.parse(fs.readFileSync(process.argv[2] || "/tmp/state.json", "utf8"));
const html = fs.readFileSync(path.join(root, "frontend/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "frontend/console.js"), "utf8");

const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;

const errors = [];
window.addEventListener("error", (e) => errors.push(`window error: ${e.message}`));
window.fetch = async (url) => ({
  json: async () => (url.includes("/api/state") ? { ...state, running: true } : { ok: true }),
});
window.WebSocket = function () { this.close = () => {}; };
window.setInterval = () => 0;
window.setTimeout = (fn) => fn && 0;

async function main() {
try {
  window.eval(js);
} catch (err) {
  errors.push(`script load: ${err.stack}`);
}

// the console fetches its first state asynchronously; let those promises settle
for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r));

const tabs = [...window.document.querySelectorAll(".tab")];
const results = [];
for (const tab of tabs) {
  try {
    tab.click();
    const panel = window.document.querySelector(`#panel-${tab.dataset.panel}.active`);
    const nodes = panel ? panel.querySelectorAll("*").length : 0;
    const text = panel ? panel.textContent.replace(/\s+/g, " ").trim().length : 0;
    results.push({ tab: tab.dataset.panel, nodes, text });
    if (!panel) errors.push(`panel for ${tab.dataset.panel} did not activate`);
    if (nodes < 12) errors.push(`panel ${tab.dataset.panel} rendered only ${nodes} nodes`);
  } catch (err) {
    errors.push(`tab ${tab.dataset.panel}: ${err.stack}`);
  }
}

const checks = {
  tick: window.document.querySelector("#tick").textContent,
  focal: window.document.querySelector("#focal").textContent,
  contenders: window.document.querySelectorAll(".contender").length,
  autonomy_rows: window.document.querySelectorAll("#autonomy b").length,
  drives: window.document.querySelectorAll(".drive").length,
  world_nodes: window.document.querySelectorAll("#world-map rect.chamber").length,
  goal_nodes: window.document.querySelectorAll("#goal-graph g").length,
  attention_bars: window.document.querySelectorAll("#attention-chart rect").length,
};

console.table(results);
console.log(checks);
if (Number(checks.tick) !== state.tick) errors.push("tick not rendered");
if (checks.contenders === 0) errors.push("no intention contenders rendered");
if (checks.world_nodes === 0) errors.push("world map rendered no chambers");

if (errors.length) {
  console.error("\nFAILURES:\n" + errors.join("\n"));
  process.exit(1);
}
console.log("\nconsole renders cleanly in every tab");
}

main();
