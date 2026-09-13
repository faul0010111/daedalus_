/* DAEDALUS research console.
   Reads the substrate's state and renders it. It never tells the agent what to do:
   the only commands are run, pause, step, speed and reset. */

const $ = (sel) => document.querySelector(sel);
const SVG = "http://www.w3.org/2000/svg";

const KIND_COLOR = {
  advance_goal: "var(--goal)",
  explore: "var(--world)",
  resolve_contradiction: "var(--alert)",
  validate: "var(--attention)",
  exploit_opportunity: "var(--good)",
  mitigate_risk: "var(--alert)",
  reflect: "var(--memory)",
  adapt_strategy: "var(--memory)",
  consolidate_memory: "var(--memory)",
  reorganize: "var(--goal)",
};

const state = { running: false, last: null, previous: {}, tab: "world", eventRows: [] };

/* ------------------------------------------------------------------ helpers */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  children.flat().forEach((c) => node.append(c?.nodeType ? c : document.createTextNode(String(c))));
  return node;
}

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) node.setAttribute(k, v);
  children.flat().forEach((c) => node.append(c?.nodeType ? c : document.createTextNode(String(c))));
  return node;
}

const num = (v, d = 2) => (typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(d)) : v ?? "—");
const clear = (node) => { while (node.firstChild) node.firstChild.remove(); return node; };

async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

/* ------------------------------------------------------------------ readouts */
function readout(container, entries) {
  const node = clear(container);
  for (const [label, value] of entries) {
    const key = container.id + label;
    const changed = state.previous[key] !== undefined && state.previous[key] !== value;
    state.previous[key] = value;
    node.append(el("div", {}, label), el("b", { class: changed ? "changed" : "" }, value));
  }
}

function renderRail(s) {
  const m = s.metrics;
  readout($("#autonomy"), [
    ["self-initiated", `${m.self_initiated_actions} (${(m.self_initiated_ratio * 100).toFixed(0)}%)`],
    ["emergent goals", m.emergent_goals],
    ["gaps resolved", m.knowledge_gaps_resolved],
    ["contradictions closed", m.contradictions_resolved],
    ["strategy adaptations", `${m.strategy_adaptations}/${m.strategy_trials}`],
    ["topology changes", m.agent_topology_changes],
    ["reflections", m.reflection_events],
    ["uncertainty removed", num(m.uncertainty_reduction, 1)],
    ["goal progress /100t", num(m.goal_progress_rate, 2)],
    ["preemptions", m.preemptions],
  ]);

  const drives = clear($("#drives"));
  for (const [name, value] of Object.entries(s.meta.drives ?? {})) {
    drives.append(el("div", { class: "drive" },
      el("span", {}, name),
      el("div", { class: "track" }, el("div", { class: "fill", style: `width:${Math.round(value * 100)}%` }))));
  }

  const diag = clear($("#diagnoses"));
  const items = s.meta.diagnoses ?? [];
  if (!items.length) diag.append(el("p", { class: "empty" }, "Nothing reported."));
  items.forEach((d) => diag.append(el("div", { class: "diagnosis" },
    el("b", {}, d.message),
    el("small", {}, `${d.code} · severity ${num(d.severity)}`))));

  const t = s.task;
  readout($("#task"), [
    ["threads returned", t.threads_recovered],
    ["relic value banked", t.relic_value_banked],
    ["energy", num(t.energy, 0)],
    ["integrity", num(t.integrity, 0)],
    ["collapses", t.collapses],
    ["epoch", t.epoch],
    ["scanner noise", num(s.world.sources?.scan?.estimate, 2)],
  ]);
}

/* ------------------------------------------------------- intention economy */
function renderEconomy(s) {
  const box = clear($("#contenders"));
  const live = s.intentions.live;
  $("#candidate-count").textContent = `${live.length} competing`;
  if (!live.length) { box.append(el("p", { class: "empty" }, "No intentions proposed yet.")); return; }

  const trace = s.intentions.decision;
  const byKey = new Map((trace?.ranking ?? []).map((r) => [r.key, r]));

  live.slice(0, 14).forEach((it) => {
    const detail = byKey.get(it.key);
    const card = el("div", {
      class: `contender${it.key === s.intentions.focal ? " focal" : ""}${it.internal ? " internal" : ""}`,
    });
    card.style.borderLeftColor = it.key === s.intentions.focal ? "var(--attention)" : (KIND_COLOR[it.kind] ?? "var(--rule)");
    card.append(el("header", {},
      el("span", { class: "desc" }, it.description),
      el("span", { class: "score" }, num(it.score, 2))));
    card.append(el("div", { class: "kind" },
      `${it.kind.replace(/_/g, " ")} · from ${it.sources.join(", ")}${it.support > 1 ? ` · ${it.support} backers` : ""}`));

    const positives = Object.entries(detail?.base?.contributions ?? {}).filter(([, v]) => v > 0);
    const total = positives.reduce((a, [, v]) => a + v, 0) || 1;
    const bars = el("div", { class: "bars" });
    positives.forEach(([k, v]) => {
      const bar = el("i", { title: `${k} +${num(v)}` });
      bar.style.width = `${(v / total) * 100}%`;
      bar.style.background = k === "risk" || k === "resource_cost" ? "var(--alert)" : (KIND_COLOR[it.kind] ?? "var(--attention)");
      bars.append(bar);
    });
    card.append(bars);

    if (detail) {
      const dl = el("dl");
      const rows = { ...detail.base.contributions, ...detail.adjustments };
      Object.entries(rows).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).forEach(([k, v]) => {
        dl.append(el("dt", {}, k.replace(/_/g, " ")),
          el("dd", { class: v >= 0 ? "pos" : "neg" }, (v >= 0 ? "+" : "") + num(v)));
      });
      const mods = Object.entries(detail.base.modulation ?? {});
      if (mods.length) {
        dl.append(el("dt", {}, "— weights modulated by drives"), el("dd", {}, ""));
        mods.forEach(([k, v]) => dl.append(el("dt", {}, k.replace(/_/g, " ")), el("dd", {}, `×${num(v)}`)));
      }
      card.append(el("details", {}, el("summary", {}, "why this score"), dl));
    }
    box.append(card);
  });
}

/* ------------------------------------------------------------- world panel */
function renderWorld(s) {
  const w = s.world;
  const map = clear($("#world-map"));
  const pts = w.entities.filter((e) => e.xy);
  if (!pts.length) { map.append(svg("text", { x: 20, y: 30 }, "The world model is still empty.")); return; }

  const xs = pts.map((e) => e.xy[0]), ys = pts.map((e) => e.xy[1]);
  const spanX = Math.max(...xs) - Math.min(...xs) || 1, spanY = Math.max(...ys) - Math.min(...ys) || 1;
  const pad = 40, W = 600, H = 480;
  const px = (e) => pad + ((e.xy[0] - Math.min(...xs)) / spanX) * (W - 2 * pad);
  const py = (e) => H - pad - ((e.xy[1] - Math.min(...ys)) / spanY) * (H - 2 * pad);
  const pos = new Map(pts.map((e) => [e.id, [px(e), py(e)]]));

  const gEdges = svg("g"), gTrail = svg("g"), gRoute = svg("g"), gNodes = svg("g");
  w.edges.forEach((edge) => {
    const a = pos.get(edge.a), b = pos.get(edge.b);
    if (!a || !b) return;
    gEdges.append(svg("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: `passage${edge.blocked ? " blocked" : ""}` }));
  });

  const line = (ids, cls) => {
    const d = ids.map((id) => pos.get(id)).filter(Boolean)
      .map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
    return d ? svg("path", { d, class: cls }) : null;
  };
  const trail = line(w.trail, "trail"); if (trail) gTrail.append(trail);
  const route = line([w.agent, ...(w.path ?? [])], "route"); if (route) gRoute.append(route);

  w.entities.forEach((e) => {
    const p = pos.get(e.id); if (!p) return;
    const cls = ["chamber"];
    if (!e.covered) cls.push("unknown"); else cls.push("visited");
    if (e.here) cls.push("here");
    if (e.atrium) cls.push("atrium");
    const g = svg("g");
    g.append(svg("rect", { x: p[0] - 21, y: p[1] - 15, width: 42, height: 30, rx: 3, class: cls.join(" ") }));

    const high = e.hazard?.high ?? 0, low = e.hazard?.low ?? 0;
    if (high > 0.15 || low > 0.15) {
      g.append(svg("rect", {
        x: p[0] - 21, y: p[1] + 11, width: 42 * Math.min(1, high + low * 0.4), height: 4,
        fill: "var(--alert)", opacity: 0.25 + 0.7 * high,
      }));
    }
    const items = (e.contains ?? []).filter((c) => c.confidence > 0.35);
    items.slice(0, 4).forEach((c, i) => {
      const glyph = c.item.startsWith("relic") ? "◆" : c.item.startsWith("oil") ? "▲" : c.item.startsWith("key") ? "✦" : "◈";
      g.append(svg("text", {
        x: p[0] - 16 + i * 11, y: p[1] + 5, "font-size": 11,
        fill: c.item === "thread" ? "var(--attention)" : "var(--world)",
        opacity: 0.35 + 0.65 * c.confidence,
      }, glyph));
    });
    if (!e.covered) {
      g.append(svg("text", { x: p[0], y: p[1] + 4, "text-anchor": "middle", opacity: 0.5 }, "?"));
    }
    g.append(svg("title", {}, `${e.id} · deficit ${num(e.deficit)} · ${e.covered ? "examined" : "never examined"}` +
      (items.length ? ` · believes it holds ${items.map((c) => `${c.item} (${num(c.confidence)})`).join(", ")}` : "")));
    gNodes.append(g);
  });

  if (w.agent && pos.get(w.agent)) {
    const p = pos.get(w.agent);
    gNodes.append(svg("circle", { cx: p[0], cy: p[1] - 22, r: 5, fill: "var(--attention)" }));
  }
  map.append(gEdges, gTrail, gRoute, gNodes);

  const tbody = clear($("#belief-table").querySelector("tbody"));
  tbody.append(el("tr", {}, ["fact", "conf", "status"].map((h) => el("th", {}, h))));
  const rows = [...(w.entities.flatMap((e) => (e.contains ?? []).map((c) => ({
    fact: `${e.id} contains ${c.item}`, confidence: c.confidence, status: c.status,
  }))))].sort((a, b) => b.confidence - a.confidence).slice(0, 18);
  rows.forEach((r) => tbody.append(el("tr", {},
    el("td", {}, r.fact), el("td", { class: "num" }, num(r.confidence)),
    el("td", {}, el("span", { class: "chip" }, r.status.replace(/_/g, " "))))));

  const cont = clear($("#contradictions"));
  if (!w.contradictions.length) cont.append(el("p", { class: "empty" }, "None open."));
  w.contradictions.forEach((c) => cont.append(el("div", { class: "diagnosis" },
    el("b", {}, c.key.join(" ")),
    el("small", {}, `t${c.tick} · ${num(c.prior)} → ${num(c.new)} · reported by ${c.source}`))));

  const src = clear($("#sources").querySelector("tbody"));
  src.append(el("tr", {}, ["source", "claimed", "learned", "checks"].map((h) => el("th", {}, h))));
  Object.entries(w.sources ?? {}).forEach(([name, v]) => src.append(el("tr", {},
    el("td", {}, name), el("td", { class: "num" }, num(v.nominal)),
    el("td", { class: "num" }, num(v.estimate)), el("td", { class: "num" }, `${v.verified}/${v.verified + v.refuted}`))));

  const hyp = clear($("#hypotheses"));
  if (!w.hypotheses?.length) hyp.append(el("p", { class: "empty" }, "None formed."));
  (w.hypotheses ?? []).forEach((h) => hyp.append(el("div", { class: "diagnosis", style: "border-left-color:var(--memory);background:rgba(213,138,196,.08)" },
    el("b", { style: "color:var(--memory)" }, h.statement),
    el("small", {}, `${h.status} · support ${h.support} · refuted ${h.refutations} · test: ${h.test}`))));
}

/* -------------------------------------------------------------- goal graph */
function renderGoals(s) {
  const g = s.goals;
  const view = clear($("#goal-graph"));
  const byDepth = new Map();
  g.goals.forEach((goal) => {
    const d = goal.depth ?? 0;
    if (!byDepth.has(d)) byDepth.set(d, []);
    byDepth.get(d).push(goal);
  });
  const pos = new Map();
  const depths = [...byDepth.keys()].sort((a, b) => a - b);
  depths.forEach((d, di) => {
    const row = byDepth.get(d);
    row.forEach((goal, i) => pos.set(goal.id, [
      (600 / (row.length + 1)) * (i + 1),
      50 + di * (380 / Math.max(1, depths.length - 1 || 1)),
    ]));
  });
  const edges = svg("g"), nodes = svg("g");
  g.edges.forEach((e) => {
    const a = pos.get(e.child), b = pos.get(e.parent);
    if (!a || !b) return;
    edges.append(svg("path", {
      d: `M${b[0]},${b[1] + 14} C${b[0]},${(a[1] + b[1]) / 2} ${a[0]},${(a[1] + b[1]) / 2} ${a[0]},${a[1] - 14}`,
      fill: "none", stroke: e.kind === "merged_into" ? "var(--memory)" : "var(--rule)",
      "stroke-width": 1.2, "stroke-dasharray": e.kind === "depends_on" ? "3 3" : null,
    }));
  });
  const statusColor = {
    active: "var(--good)", achieved: "var(--good)", blocked: "var(--alert)",
    abandoned: "var(--ink-faint)", suspended: "var(--attention)", proposed: "var(--attention)",
    merged: "var(--memory)",
  };
  g.goals.forEach((goal) => {
    const p = pos.get(goal.id); if (!p) return;
    const node = svg("g");
    node.append(svg("rect", {
      x: p[0] - 58, y: p[1] - 14, width: 116, height: 28, rx: 3,
      fill: goal.status === "achieved" ? "rgba(88,211,162,.13)" : "var(--panel)",
      stroke: statusColor[goal.status] ?? "var(--rule)",
      "stroke-width": goal.origin === "developer" ? 1.8 : 1,
      "stroke-dasharray": goal.origin.startsWith("emergent") ? "4 2" : null,
    }));
    const label = goal.description.length > 20 ? goal.description.slice(0, 19) + "…" : goal.description;
    node.append(svg("text", { x: p[0], y: p[1] + 3, "text-anchor": "middle", fill: "var(--ink)" }, label));
    node.append(svg("title", {}, `${goal.id} · ${goal.status} · ${goal.origin}\n${goal.description}` +
      (goal.block_reason ? `\nblocked: ${goal.block_reason}` : "")));
    nodes.append(node);
  });
  view.append(edges, nodes);

  const tbody = clear($("#goal-table").querySelector("tbody"));
  tbody.append(el("tr", {}, ["goal", "status", "origin", "value"].map((h) => el("th", {}, h))));
  g.goals.forEach((goal) => tbody.append(el("tr", {},
    el("td", {}, goal.description),
    el("td", {}, el("span", { class: `chip ${goal.status}` }, goal.status)),
    el("td", {}, el("span", { class: `chip ${goal.origin.startsWith("emergent") ? "emergent" : ""}` },
      goal.origin.replace("emergent:", ""))),
    el("td", { class: "num" }, num(goal.value)))));

  const trans = clear($("#goal-transitions"));
  g.transitions.slice(-18).reverse().forEach((t) => trans.append(el("div", { class: "row", style: "font-size:11.5px;color:var(--ink-dim)" },
    `t${t.tick} · ${t.goal} → ${t.to} · ${t.reason}`)));
}

/* ---------------------------------------------------------------- topology */
function renderAgents(s) {
  const view = clear($("#topology"));
  const { nodes, edges } = s.agents;
  const rings = { core: [], process: [], unit: [], goal: [] };
  nodes.forEach((n) => (rings[n.type] ?? rings.goal).push(n));
  const pos = new Map();
  pos.set("daedalus", [300, 240]);
  const place = (list, radius, offset = 0) => list.forEach((n, i) => {
    const a = offset + (i / Math.max(1, list.length)) * Math.PI * 2;
    pos.set(n.id, [300 + Math.cos(a) * radius, 240 + Math.sin(a) * radius * 0.82]);
  });
  place(rings.process, 120, -Math.PI / 2);
  place(rings.unit, 195, -Math.PI / 3);
  place(rings.goal, 205, Math.PI / 2);

  const gE = svg("g"), gN = svg("g");
  edges.forEach((e) => {
    const a = pos.get(e.from), b = pos.get(e.to);
    if (!a || !b) return;
    gE.append(svg("line", {
      x1: a[0], y1: a[1], x2: b[0], y2: b[1],
      stroke: e.kind === "spawned" ? "var(--goal)" : "var(--rule)", "stroke-width": 1,
      "stroke-dasharray": e.kind === "purpose" ? "3 3" : null,
    }));
  });
  nodes.forEach((n) => {
    const p = pos.get(n.id); if (!p) return;
    const r = n.type === "core" ? 26 : n.type === "unit" ? 17 : 12;
    const fill = { core: "var(--attention)", process: "var(--panel-2)", unit: "var(--goal)", goal: "var(--panel)" }[n.type];
    const g = svg("g");
    g.append(svg("circle", {
      cx: p[0], cy: p[1], r, fill,
      stroke: n.type === "process" ? "var(--rule)" : "none",
      opacity: n.type === "process" ? 0.5 + Math.min(0.5, (n.pressure ?? 0)) : 1,
    }));
    g.append(svg("text", {
      x: p[0], y: p[1] + (n.type === "core" ? 4 : r + 12), "text-anchor": "middle",
      fill: n.type === "core" ? "#221703" : "var(--ink-dim)",
    }, (n.label ?? n.id).slice(0, 18)));
    g.append(svg("title", {}, JSON.stringify(n)));
    gN.append(g);
  });
  view.append(gE, gN);

  const hist = clear($("#agent-history"));
  const history = s.agents.history ?? [];
  if (!history.length) hist.append(el("p", { class: "empty" }, "No temporary units have been formed."));
  history.slice(-14).reverse().forEach((h) => hist.append(el("div", { style: "font-size:11.5px;color:var(--ink-dim);padding:1px 0" },
    `t${h.tick} · ${h.event} ${h.role} for ${h.purpose} — ${h.reason ?? h.rationale ?? ""}`)));

  const procs = clear($("#processes").querySelector("tbody"));
  procs.append(el("tr", {}, ["process", "every", "runs", "pressure"].map((h) => el("th", {}, h))));
  s.meta.processes.forEach((p) => procs.append(el("tr", {},
    el("td", {}, p.name), el("td", { class: "num" }, p.period),
    el("td", { class: "num" }, p.runs), el("td", { class: "num" }, num(p.pressure)))));
}

/* ------------------------------------------------------------------ memory */
function renderMemory(s) {
  const m = s.memory;
  const sem = clear($("#semantic").querySelector("tbody"));
  sem.append(el("tr", {}, ["what the agent has concluded", "kind", "conf"].map((h) => el("th", {}, h))));
  m.semantic.forEach((k) => sem.append(el("tr", {},
    el("td", {}, k.statement), el("td", {}, el("span", { class: "chip" }, k.kind)),
    el("td", { class: "num" }, num(k.confidence)))));

  const ins = clear($("#insights"));
  if (!m.insights?.length) ins.append(el("p", { class: "empty" }, "Nothing reflected on yet."));
  (m.insights ?? []).slice().reverse().forEach((i) => ins.append(el("div", { style: "font-size:11.5px;color:var(--ink-dim);padding:2px 0;border-bottom:1px solid var(--rule-soft)" },
    `t${i.tick} · ${i.type}: ${Object.entries(i).filter(([k]) => !["tick", "type"].includes(k)).map(([k, v]) => `${k}=${typeof v === "number" ? num(v) : v}`).join(" ")}`)));

  const work = clear($("#working").querySelector("tbody"));
  work.append(el("tr", {}, ["t", "kind", "content"].map((h) => el("th", {}, h))));
  m.working.slice().reverse().forEach((w) => work.append(el("tr", {},
    el("td", { class: "num" }, w.tick), el("td", {}, w.kind),
    el("td", {}, Object.entries(w).filter(([k]) => !["tick", "kind"].includes(k)).map(([k, v]) => `${k}=${v}`).join(" ")))));

  const eps = clear($("#episodes").querySelector("tbody"));
  eps.append(el("tr", {}, ["t", "action", "reward", "surprise"].map((h) => el("th", {}, h))));
  m.episodes.slice().reverse().forEach((e) => eps.append(el("tr", {},
    el("td", { class: "num" }, e.tick),
    el("td", {}, `${e.tool} ${Object.values(e.args).join(" ")}${e.success ? "" : " ✕"}`),
    el("td", { class: "num" }, num(e.reward)), el("td", { class: "num" }, num(e.surprise)))));

  const fails = clear($("#failures").querySelector("tbody"));
  fails.append(el("tr", {}, ["t", "tool", "reason", "diagnosed"].map((h) => el("th", {}, h))));
  m.failures.slice().reverse().forEach((f) => fails.append(el("tr", {},
    el("td", { class: "num" }, f.tick), el("td", {}, f.tool), el("td", {}, f.reason),
    el("td", {}, f.diagnosed_cause || "—"))));
}

/* ---------------------------------------------------------------- strategy */
function renderStrategy(s) {
  const points = clear($("#strategy-points").querySelector("tbody"));
  points.append(el("tr", {}, ["decision point", "in use", "alternatives", "evidence"].map((h) => el("th", {}, h))));
  s.meta.strategies.points.forEach((p) => {
    const stats = p.stats.map((st) => `${st.variant} ${st.mean >= 0 ? "+" : ""}${num(st.mean, 3)} (n=${st.n})`).join("  ");
    points.append(el("tr", {},
      el("td", {}, p.description),
      el("td", {}, el("span", { class: "chip active" }, p.active)),
      el("td", {}, p.variants.filter((v) => v !== p.incumbent).join(", ")),
      el("td", {}, stats || "—")));
  });

  const audit = clear($("#strategy-audit").querySelector("tbody"));
  audit.append(el("tr", {}, ["t", "point", "decision", "why"].map((h) => el("th", {}, h))));
  s.meta.strategies.audit.slice().reverse().forEach((a) => audit.append(el("tr", {},
    el("td", { class: "num" }, a.tick), el("td", {}, `${a.point}: ${a.incumbent} → ${a.candidate}`),
    el("td", {}, el("span", { class: `chip ${a.decision === "adopted" ? "achieved" : a.decision === "rejected" ? "blocked" : "suspended"}` }, a.decision)),
    el("td", {}, `${a.rationale}${a.candidate_score !== null ? ` · ${num(a.candidate_score, 3)} vs ${num(a.incumbent_score, 3)}` : ""}`))));

  const chart = clear($("#policy-chart"));
  const policy = s.meta.policy;
  const table = clear($("#policy-table").querySelector("tbody"));
  if (!policy) { chart.append(svg("text", { x: 10, y: 20 }, "Attention learning is disabled in this run.")); return; }
  const entries = Object.entries(policy.bias).filter(([, v]) => Math.abs(v) > 0.0001)
    .sort((a, b) => b[1] - a[1]);
  const max = Math.max(0.1, ...entries.map(([, v]) => Math.abs(v)));
  const mid = 160;
  entries.forEach(([kind, v], i) => {
    const y = 14 + i * 18;
    chart.append(svg("rect", {
      x: v >= 0 ? mid : mid + (v / max) * 140, y: y - 7,
      width: Math.abs((v / max) * 140), height: 11,
      fill: v >= 0 ? "var(--good)" : "var(--alert)", opacity: 0.75,
    }));
    chart.append(svg("text", { x: 4, y, fill: "var(--ink-dim)" }, kind.replace(/_/g, " ")));
    chart.append(svg("text", { x: 314, y, "text-anchor": "end", fill: "var(--ink)" }, num(v, 3)));
  });
  chart.append(svg("line", { x1: mid, y1: 4, x2: mid, y2: 4 + entries.length * 18, stroke: "var(--rule)" }));
  table.append(el("tr", {}, el("th", {}, "policy updates"), el("th", { class: "num" }, policy.updates)));
}

/* ----------------------------------------------------------------- metrics */
function lineChart(node, series, keys, colors, width = 640, height = 200) {
  const view = clear(node);
  if (series.length < 2) { view.append(svg("text", { x: 8, y: 20 }, "Not enough samples yet.")); return; }
  const xs = series.map((p) => p.tick);
  const x = (t) => ((t - xs[0]) / Math.max(1, xs[xs.length - 1] - xs[0])) * (width - 60) + 46;
  keys.forEach((key, ki) => {
    const values = series.map((p) => p[key] ?? 0);
    const max = Math.max(...values, 1), min = Math.min(...values, 0);
    const y = (v) => height - 20 - ((v - min) / Math.max(1e-6, max - min)) * (height - 42);
    const d = series.map((p, i) => `${i ? "L" : "M"}${x(p.tick).toFixed(1)},${y(values[i]).toFixed(1)}`).join(" ");
    view.append(svg("path", { d, fill: "none", stroke: colors[ki], "stroke-width": 1.6 }));
    view.append(svg("text", { x: 46 + ki * 150, y: 12, fill: colors[ki] }, `${key.replace(/_/g, " ")} (max ${num(max, 1)})`));
  });
  view.append(svg("line", { x1: 46, y1: height - 20, x2: width - 14, y2: height - 20, stroke: "var(--rule)" }));
  view.append(svg("text", { x: 46, y: height - 6 }, `t${xs[0]}`));
  view.append(svg("text", { x: width - 14, y: height - 6, "text-anchor": "end" }, `t${xs[xs.length - 1]}`));
}

function renderMetrics(s) {
  const series = s.metrics.series ?? [];
  lineChart($("#uncertainty-chart"), series, ["uncertainty", "beliefs"], ["var(--world)", "var(--memory)"]);
  lineChart($("#autonomy-chart"), series, ["emergent_goals", "self_initiated_actions", "reflection_events"],
    ["var(--goal)", "var(--attention)", "var(--memory)"]);
  readout($("#performance"), Object.entries(s.meta.performance).map(([k, v]) => [
    k.replace(/_/g, " "), typeof v === "object" && v !== null
      ? Object.entries(v).map(([kk, vv]) => `${kk} ${num(vv)}`).join("  ") : num(v),
  ]));
}

/* ---------------------------------------------------------------- timeline */
const EVENT_COLOR = (type) => type.startsWith("goal") ? "var(--goal)"
  : type.startsWith("world") ? "var(--world)"
  : type.startsWith("attention") || type.startsWith("intention") ? "var(--attention)"
  : type.startsWith("meta") || type.startsWith("adaptation") ? "var(--alert)"
  : type.startsWith("agent") ? "var(--goal)"
  : type.startsWith("reflection") || type.startsWith("memory") ? "var(--memory)"
  : "var(--ink-faint)";

function summarizeEvent(e) {
  const p = e.payload ?? {};
  if (e.type === "goal.created") return `${p.id} ${p.description} (${p.reason ?? ""})`;
  if (e.type === "goal.status") return `${p.goal} ${p.from} → ${p.to}: ${p.reason}`;
  if (e.type === "world.contradiction.detected") return `${(p.key ?? []).join(" ")} — ${num(p.prior)} vs ${num(p.new)} from ${p.source}`;
  if (e.type === "reflection.insight") return `${p.count} insight(s): ${(p.insights ?? []).map((i) => i.type).join(", ")}`;
  if (e.type === "meta.diagnosis") return `${p.message} (${num(p.severity)})`;
  if (e.type.startsWith("adaptation")) return `${p.point}: ${p.incumbent} → ${p.candidate} ${p.rationale ?? ""}`;
  if (e.type.startsWith("agent.")) return `${p.role} for ${p.purpose} — ${p.rationale ?? p.reason ?? ""}`;
  if (e.type === "intention.preempted") return `${p.preempted} yielded to ${p.by}`;
  if (e.type === "environment.dynamics") return Object.entries(p).map(([k, v]) => `${k}=${v}`).join(" ");
  if (e.type === "memory.consolidated") return `${p.episodes} episodes → ${p.signatures} statistics`;
  return Object.entries(p).slice(0, 4).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v).slice(0, 40) : v}`).join(" ");
}

function pushEvents(events) {
  const stream = $("#stream");
  events.forEach((e) => {
    const row = el("div", { class: "row" },
      el("span", { class: "t" }, `t${e.tick}`),
      el("span", { class: "type" }, e.type),
      el("span", { class: "body" }, summarizeEvent(e)));
    row.querySelector(".type").style.color = EVENT_COLOR(e.type);
    stream.prepend(row);
  });
  while (stream.children.length > 220) stream.lastChild.remove();
}

function renderAttentionStrip(s) {
  const view = clear($("#attention-chart"));
  const hist = (s.history ?? []).slice(-120);
  if (!hist.length) return;
  const kinds = [...new Set(hist.map((h) => h.kind).filter(Boolean))];
  const w = 240 / Math.max(1, hist.length);
  hist.forEach((h, i) => {
    if (!h.kind) return;
    const row = kinds.indexOf(h.kind);
    view.append(svg("rect", {
      x: i * w, y: 4 + row * (64 / Math.max(1, kinds.length)), width: Math.max(1, w),
      height: 64 / Math.max(1, kinds.length) - 2,
      fill: KIND_COLOR[h.kind] ?? "var(--rule)", opacity: h.success === false ? 0.35 : 0.9,
    }));
  });
  kinds.forEach((k, i) => view.append(svg("text", {
    x: 2, y: 4 + i * (64 / kinds.length) + (64 / kinds.length) / 2 + 2,
    "font-size": 7, fill: "var(--ink)",
  }, k.replace(/_/g, " "))));
}

/* -------------------------------------------------------------- main cycle */
function render(s) {
  state.last = s;
  $("#tick").textContent = s.tick;
  $("#focal").textContent = s.intentions.focal ?? "—";
  $("#pulse").classList.toggle("live", !!s.running);
  $("#play").textContent = s.running ? "Pause" : "Start";
  $("#play").dataset.running = String(!!s.running);
  const err = $("#error");
  err.hidden = !s.error;
  err.textContent = s.error ?? "";

  renderRail(s);
  renderEconomy(s);
  renderAttentionStrip(s);
  ({ world: renderWorld, goals: renderGoals, agents: renderAgents, memory: renderMemory,
     strategy: renderStrategy, metrics: renderMetrics }[state.tab])(s);
}

async function refresh() {
  try { render(await api("/api/state")); } catch (e) { /* the server may be mid-reset */ }
}

function connectStream() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${location.host}/ws/events`);
  const quiet = new Set(["world.belief.created", "intention.proposed", "perception.change",
    "deliberation.plan", "evaluation.outcome", "action.executed", "attention.allocated"]);
  socket.onmessage = (msg) => {
    const e = JSON.parse(msg.data);
    if (e.type === "hello" || quiet.has(e.type)) return;
    pushEvents([e]);
  };
  socket.onclose = () => setTimeout(connectStream, 2000);
}

/* ------------------------------------------------------------------ wiring */
document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  state.tab = tab.dataset.panel;
  $(`#panel-${state.tab}`).classList.add("active");
  if (state.last) render(state.last);
}));

$("#play").addEventListener("click", async () => {
  const running = $("#play").dataset.running === "true";
  await api(running ? "/api/control/pause" : "/api/control/play", "POST");
  refresh();
});
$("#step").addEventListener("click", async () => { await api("/api/control/step", "POST", { ticks: 1 }); refresh(); });
$("#step10").addEventListener("click", async () => { await api("/api/control/step", "POST", { ticks: 10 }); refresh(); });
$("#speed").addEventListener("change", (e) => api("/api/control/speed", "POST", { ticks_per_second: Number(e.target.value) }));
$("#reset").addEventListener("click", async () => {
  await api("/api/control/reset", "POST", { preset: $("#preset").value, seed: Number($("#seed").value) });
  clear($("#stream"));
  state.previous = {};
  refresh();
});

connectStream();
refresh();
setInterval(refresh, 900);
