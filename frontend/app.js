/* AI Learning Academy — plain JS frontend. Talks to the backend via fetch() only. */

const EXAMPLE =
  "Create an AI upskilling programme for 1,000 software engineers across India, " +
  "covering GenAI, RAG, AI agents and responsible AI.";

const AGENTS = [
  ["learner_analysis", "Learner Analysis Agent", "Extracts cohorts, levels and skill gaps"],
  ["curriculum", "Curriculum Agent", "Designs modules, objectives and sequencing"],
  ["content", "Content Agent", "RAG over the material library; flags content gaps"],
  ["assessment", "Assessment Agent", "Quizzes, coding exercises, rubrics"],
  ["quality", "Quality Agent", "Adversarial review; can reject and route back"],
];

const POLL_MS = 1500;
const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let runId = null;
let timer = null;
let lastRenderedStatus = null;

/* ------------------------------------------------------------------ setup */
document.addEventListener("DOMContentLoaded", () => {
  buildAgentList();
  loadHealth();
  $("#useExample").onclick = () => ($("#request").value = EXAMPLE);
  $("#submit").onclick = submit;
  $("#approve").onclick = approve;
  $("#reject").onclick = reject;
  $("#tabs").onclick = (e) => {
    if (e.target.dataset.tab) showTab(e.target.dataset.tab);
  };
});

async function loadHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    $("#health").innerHTML =
      `${h.api_key_configured ? "&#9679; API key loaded" : "&#9679; <b>no API key</b>"} &middot; ` +
      `${esc(h.models.large)} / ${esc(h.models.small)} &middot; ` +
      `${h.vector_store.chunks} chunk(s) in "${esc(h.vector_store.collection)}" &middot; ` +
      `max ${h.max_revisions} revisions`;
    if (!h.api_key_configured) {
      $("#submitHint").textContent = "MISTRAL_API_KEY missing in .env";
      $("#submit").disabled = true;
    } else if (h.vector_store.chunks === 0) {
      $("#submitHint").textContent =
        "Vector store empty — run: python -m backend.rag.seed_content";
    }
  } catch {
    $("#health").textContent = "backend unreachable";
  }
}

function buildAgentList() {
  const list = $("#agentList");
  list.innerHTML = "";
  AGENTS.forEach(([key, name, desc]) => {
    const li = el("li", "pending");
    li.id = `agent-${key}`;
    li.appendChild(el("span", "dot"));
    li.appendChild(el("span", "name", `${esc(name)}<span class="desc">${esc(desc)}</span>`));
    li.appendChild(el("span", "state", "pending"));
    list.appendChild(li);
  });
}

/* ------------------------------------------------------------------ submit */
async function submit() {
  const text = $("#request").value.trim();
  if (text.length < 10) {
    $("#submitHint").textContent = "Describe the programme you need (10+ characters).";
    return;
  }
  $("#submit").disabled = true;
  $("#submitHint").textContent = "starting agents…";
  ["#progressCard", "#costCard"].forEach((s) => $(s).classList.remove("hidden"));
  ["#resultCard", "#errorCard", "#approvedBox", "#approvalBox", "#revisionBanner"].forEach((s) =>
    $(s).classList.add("hidden")
  );
  buildAgentList();
  lastRenderedStatus = null;

  try {
    const res = await fetch("/api/programmes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manager_request: text }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    runId = (await res.json()).run_id;
    $("#submitHint").innerHTML = `run <code>${esc(runId)}</code>`;
    startPolling();
  } catch (e) {
    $("#submit").disabled = false;
    showError(String(e.message || e));
  }
}

function startPolling() {
  clearInterval(timer);
  poll();
  timer = setInterval(poll, POLL_MS);
}

async function poll() {
  if (!runId) return;
  try {
    const state = await (await fetch(`/api/programmes/${runId}`)).json();
    renderProgress(state);
    renderCost();
    renderTrace();

    const terminal = ["awaiting_approval", "approved", "failed"].includes(state.status);
    if (terminal) {
      clearInterval(timer);
      $("#submit").disabled = false;
      renderResult(state);
    }
  } catch (e) {
    console.error(e);
  }
}

/* ---------------------------------------------------------------- progress */
function renderProgress(state) {
  const badge = $("#statusBadge");
  badge.textContent = state.status.replace(/_/g, " ");
  badge.className =
    "badge " +
    ({ approved: "ok", awaiting_approval: "warn", failed: "bad" }[state.status] || "live");

  AGENTS.forEach(([key]) => {
    const li = $(`#agent-${key}`);
    const s = (state.agent_status || {})[key] || "pending";
    li.className = s;
    li.querySelector(".state").textContent = s;
  });

  const banner = $("#revisionBanner");
  const humanLaps = state.human_revision_count || 0;
  const inRevision = state.revision_count > 0 || humanLaps > 0;
  if (inRevision && state.status !== "approved") {
    const target = state.revision_target || "curriculum";
    const feedback = state.revision_feedback || [];
    const list = feedback.length
      ? `<ul>${feedback.slice(0, 6).map((f) => `<li>${esc(f)}</li>`).join("")}</ul>`
      : "";
    const who =
      state.revision_count > 0
        ? `<b>Revision ${state.revision_count} of ${state.max_revisions}</b> &mdash; ` +
          `Quality Agent rejected the draft`
        : `<b>Human rejection ${humanLaps} of ${state.max_human_rejections}</b> &mdash; ` +
          `the reviewer sent the draft back`;
    banner.classList.remove("hidden");
    banner.innerHTML =
      `${who} and routed it to the <b>${esc(target)}</b> agent. ` +
      `Everything downstream re-runs.` +
      list;
  } else {
    banner.classList.add("hidden");
  }

  if (state.status === "failed") showError(state.error || "unknown error");
  else $("#errorCard").classList.add("hidden");
}

async function renderTrace() {
  try {
    const { history } = await (await fetch(`/api/programmes/${runId}/history`)).json();
    $("#traceCount").textContent = `(${history.length} events)`;
    $("#trace").innerHTML = history
      .slice()
      .reverse()
      .map(
        (h) =>
          `<li><span class="muted">r${h.revision}</span>` +
          `<span>${esc(h.agent)}</span>` +
          `<span class="ev">${esc(h.event)}</span>` +
          `<span class="muted">${esc(h.detail)}</span></li>`
      )
      .join("");
  } catch {}
}

/* -------------------------------------------------------------------- cost */
async function renderCost() {
  try {
    const c = await (await fetch(`/api/programmes/${runId}/cost`)).json();
    $("#costTotal").textContent = `$${c.total.cost_usd.toFixed(5)} · ${c.total.total_tokens.toLocaleString()} tokens`;

    const rowsByAgentModel = {};
    c.calls.forEach((k) => {
      const key = `${k.agent}|${k.model}`;
      const r = (rowsByAgentModel[key] ||= {
        agent: k.agent, model: k.model, calls: 0, p: 0, comp: 0, cost: 0,
      });
      r.calls += 1;
      r.p += k.prompt_tokens;
      r.comp += k.completion_tokens;
      r.cost += k.cost_usd;
    });

    $("#costTable").querySelector("tbody").innerHTML =
      Object.values(rowsByAgentModel)
        .map(
          (r) =>
            `<tr><td>${esc(r.agent)}</td><td class="muted">${esc(r.model)}</td>` +
            `<td>${r.calls}</td><td>${r.p.toLocaleString()}</td>` +
            `<td>${r.comp.toLocaleString()}</td><td>$${r.cost.toFixed(5)}</td></tr>`
        )
        .join("") +
      `<tr><td><b>Total</b></td><td></td><td><b>${c.total.calls}</b></td>` +
      `<td><b>${c.total.prompt_tokens.toLocaleString()}</b></td>` +
      `<td><b>${c.total.completion_tokens.toLocaleString()}</b></td>` +
      `<td><b>$${c.total.cost_usd.toFixed(5)}</b></td></tr>`;

    const revTable = $("#revTable");
    if (c.by_revision.length > 1) {
      revTable.classList.remove("hidden");
      revTable.querySelector("tbody").innerHTML = c.by_revision
        .map(
          (r) =>
            `<tr><td>${r.revision === 0 ? "initial draft" : `revision ${r.revision}`}</td>` +
            `<td>${r.calls}</td><td>${r.total_tokens.toLocaleString()}</td>` +
            `<td>$${r.cost_usd.toFixed(5)}</td></tr>`
        )
        .join("");
    } else {
      revTable.classList.add("hidden");
    }
  } catch {}
}

/* ------------------------------------------------------------------ result */
function renderResult(state) {
  if (lastRenderedStatus === state.status && state.status !== "awaiting_approval") return;
  lastRenderedStatus = state.status;

  const q = state.quality_review || {};
  if (!state.curriculum && !q.verdict) return;

  $("#resultCard").classList.remove("hidden");
  const vb = $("#verdictBadge");
  vb.textContent = q.verdict ? `quality: ${q.verdict}` : state.status.replace(/_/g, " ");
  vb.className = "badge " + (q.verdict === "approved" ? "ok" : "bad");

  paneQuality(q, state);
  paneLearners(state.learner_analysis);
  paneCurriculum(state.curriculum);
  paneContent(state.content_plan);
  paneAssessments(state.assessments, state.curriculum);

  const canDecide = state.status === "awaiting_approval";
  $("#approvalBox").classList.toggle("hidden", !canDecide);
  $("#approvedBox").classList.toggle("hidden", state.status !== "approved");

  // Reject has its own budget; disable it once spent so the button can't 409.
  const rejectsLeft = (state.max_human_rejections || 0) - (state.human_revision_count || 0);
  $("#reject").disabled = rejectsLeft <= 0;
  $("#reject").title =
    rejectsLeft <= 0 ? "Human rejection cap reached — needs manual redesign" : "";
}

function pane(name) {
  return document.querySelector(`.pane[data-pane="${name}"]`);
}

function showTab(name) {
  document.querySelectorAll("#tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name)
  );
  document.querySelectorAll(".pane").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.pane !== name)
  );
}

function paneQuality(q, state) {
  if (!q.verdict) {
    pane("quality").innerHTML = `<p class="muted">No quality review recorded.</p>`;
    return;
  }
  const issues = (q.issues || [])
    .map(
      (i) =>
        `<div class="issue ${esc(i.severity)}">` +
        `<div class="sev">${esc(i.severity)} &middot; owner: ${esc(i.owner)}</div>` +
        `<div>${esc(i.issue)}</div>` +
        `<div class="fix">Fix: ${esc(i.required_fix)}</div></div>`
    )
    .join("");
  pane("quality").innerHTML =
    `<h3>Verdict: ${esc(q.verdict)}${q.target_agent ? ` &rarr; ${esc(q.target_agent)} agent` : ""}</h3>` +
    `<p>${esc(q.reviewer_notes)}</p>` +
    `<p class="muted small">Automated revisions used: ${state.revision_count} of ${state.max_revisions}` +
    ` &middot; human rejections: ${state.human_revision_count || 0} of ${state.max_human_rejections}</p>` +
    (state.human_feedback
      ? `<p class="muted small">Standing human requirement: &ldquo;${esc(state.human_feedback)}&rdquo;</p>`
      : "") +
    (issues ? `<h3>Issues raised (${(q.issues || []).length})</h3>${issues}` : `<p class="muted">No issues raised.</p>`);
}

function paneLearners(la) {
  if (!la) return (pane("learners").innerHTML = `<p class="muted">Not produced.</p>`);
  pane("learners").innerHTML =
    `<p>${esc(la.summary)}</p>` +
    `<p class="muted small">Total learners: <b>${esc(la.total_learners)}</b> &middot; Region: <b>${esc(la.region)}</b></p>` +
    `<h3>Cohorts</h3>` +
    (la.roles || [])
      .map(
        (r) =>
          `<div class="mod"><div class="mhead"><div><b>${esc(r.role)}</b></div>` +
          `<span class="meta">${esc(r.current_level)} &middot; ~${esc(r.headcount_estimate)} learners</span></div>` +
          `<ul>${(r.skill_gaps || []).map((g) => `<li>${esc(g)}</li>`).join("")}</ul></div>`
      )
      .join("") +
    `<h3>Overall skill gaps</h3><ul>${(la.overall_skill_gaps || []).map((g) => `<li>${esc(g)}</li>`).join("")}</ul>` +
    `<h3>Constraints</h3><ul>${(la.key_constraints || []).map((g) => `<li>${esc(g)}</li>`).join("")}</ul>`;
}

function paneCurriculum(c) {
  if (!c) return (pane("curriculum").innerHTML = `<p class="muted">Not produced.</p>`);
  const pathways = Object.entries(c.pathways || {});
  const pathHtml = pathways.length
    ? `<h3>Learner pathways</h3>` +
      pathways
        .map(
          ([name, ids]) =>
            `<div class="qa"><b>${esc(name)}</b>: ` +
            `<span class="muted">${(ids || []).map(esc).join(" &rarr; ")}</span></div>`
        )
        .join("")
    : "";
  pane("curriculum").innerHTML =
    `<h3>${esc(c.programme_title)}</h3>` +
    `<p class="muted small">${(c.modules || []).length} modules &middot; ${esc(c.total_duration_hours)} hours total</p>` +
    `<p>${esc(c.sequencing_rationale)}</p>` +
    pathHtml +
    `<h3>Modules</h3>` +
    (c.modules || [])
      .map(
        (m) =>
          `<div class="mod"><div class="mhead"><div><span class="mid">${esc(m.module_id)}</span><b>${esc(m.title)}</b></div>` +
          `<span class="meta">${esc(m.duration_hours)}h &middot; ${esc(m.target_level)} &middot; ${esc(m.delivery_mode)}</span></div>` +
          `<ul>${(m.learning_objectives || []).map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` +
          `<div class="tagrow"><span class="tag">topic: ${esc(m.topic)}</span>` +
          `<span class="tag">pathway: ${esc(m.pathway || "all")}</span>` +
          `<span class="tag">prereq: ${(m.prerequisites || []).join(", ") || "none"}</span></div></div>`
      )
      .join("");
}

function paneContent(cp) {
  if (!cp) return (pane("content").innerHTML = `<p class="muted">Not produced.</p>`);
  pane("content").innerHTML =
    `<p>${esc(cp.reuse_summary)}</p>` +
    `<p class="muted small">Searched ${esc(cp.library_chunks_searched ?? "?")} library chunk(s), top-k = ${esc(cp.top_k ?? "?")}</p>` +
    (cp.modules || [])
      .map((m) => {
        const mats = m.recommended_materials || [];
        const matList = mats.length
          ? `<ul>${mats
              .map(
                (r) =>
                  `<li><b>${esc(r.source)}</b> <span class="muted">(${esc(r.topic)} / ${esc(r.level)})</span><br>` +
                  `<span class="muted small">${esc(r.why_relevant)}</span></li>`
              )
              .join("")}</ul>`
          : "";
        const note = m.gap_note ? `<p class="muted small">${esc(m.gap_note)}</p>` : "";
        return (
          `<div class="mod"><div class="mhead"><div><span class="mid">${esc(m.module_id)}</span><b>${esc(m.module_title)}</b></div>` +
          `<span class="tag ${m.gap ? "gap" : "reuse"}">${m.gap ? "content gap" : "reuse existing"}</span></div>` +
          matList +
          note +
          `</div>`
        );
      })
      .join("") +
    `<h3>Content gaps for the L&amp;D backlog</h3>` +
    `<ul>${(cp.content_gaps || []).map((g) => `<li>${esc(g)}</li>`).join("") || "<li class='muted'>none</li>"}</ul>`;
}

function paneAssessments(a, c) {
  if (!a) return (pane("assessments").innerHTML = `<p class="muted">Not produced.</p>`);
  const titles = {};
  (c?.modules || []).forEach((m) => (titles[m.module_id] = m.title));
  pane("assessments").innerHTML =
    `<p class="muted small">${esc(a.certification_note)}</p>` +
    (a.per_module || [])
      .map((m) => {
        const quiz = (m.quiz || [])
          .map(
            (q) =>
              `<div class="qa"><b>${esc(q.question)}</b><br>` +
              `<span class="opt">${(q.options || []).map(esc).join(" &middot; ")}</span><br>` +
              `<span class="ans">answer: ${esc(q.answer)}</span></div>`
          )
          .join("");
        const ex = m.coding_exercise
          ? `<h3>Coding exercise</h3><div class="qa"><b>${esc(m.coding_exercise.title)}</b><br>` +
            `${esc(m.coding_exercise.brief)}<br><span class="muted small">` +
            `${(m.coding_exercise.acceptance_criteria || []).map(esc).join(" | ")}</span></div>`
          : "";
        const rub = (m.practical_rubric || [])
          .map(
            (r) =>
              `<div class="qa"><b>${esc(r.criterion)}</b><br>` +
              Object.entries(r.levels || {})
                .map(([k, v]) => `<span class="muted small">${esc(k)}: ${esc(v)}</span>`)
                .join("<br>") +
              `</div>`
          )
          .join("");
        return (
          `<div class="mod"><div class="mhead"><div><span class="mid">${esc(m.module_id)}</span>` +
          `<b>${esc(titles[m.module_id] || "")}</b></div></div>` +
          (quiz ? `<h3>Quiz</h3>${quiz}` : "") +
          ex +
          (rub ? `<h3>Rubric</h3>${rub}` : "") +
          `</div>`
        );
      })
      .join("");
}

function showError(msg) {
  $("#errorCard").classList.remove("hidden");
  $("#errorText").textContent = msg;
}

/* ----------------------------------------------------------- human gate */
async function approve() {
  $("#approve").disabled = true;
  try {
    const res = await fetch(`/api/programmes/${runId}/approve`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail);
    lastRenderedStatus = null;
    await poll();
  } catch (e) {
    showError(String(e.message || e));
  } finally {
    $("#approve").disabled = false;
  }
}

async function reject() {
  const feedback = $("#rejectFeedback").value.trim();
  if (!feedback) {
    $("#rejectFeedback").placeholder = "Tell the agents what to change before rejecting.";
    return;
  }
  $("#reject").disabled = true;
  try {
    const res = await fetch(`/api/programmes/${runId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback, target_agent: $("#rejectTarget").value }),
    });
    if (!res.ok) throw new Error((await res.json()).detail);
    $("#approvalBox").classList.add("hidden");
    lastRenderedStatus = null;
    startPolling();
  } catch (e) {
    showError(String(e.message || e));
  } finally {
    $("#reject").disabled = false;
  }
}
