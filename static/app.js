"use strict";
const $ = (s, r = document) => r.querySelector(s);
const view = $("#view");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const STATUS = { draft: "Draft", in_review: "In review", approved: "Approved", changes_requested: "Changes requested", rejected: "Rejected" };
const CAT = { terminology: "Terminology", tone: "Tone", claims: "Claims", facts: "Facts", messaging: "Messaging", accessibility: "Accessibility", visual: "Visual" };
let USERS = [], ME = null;
try { ME = localStorage.getItem("bl_user"); } catch (e) { }

function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toast.h); toast.h = setTimeout(() => t.className = "", err ? 5000 : 2500);
}
async function api(path, opt = {}) {
  const o = { method: opt.method || "GET", headers: { "X-User": ME || "" } };
  if (opt.json !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opt.json); }
  if (opt.form) o.body = opt.form;
  const r = await fetch("/api" + path, o);
  let data = null; try { data = await r.json(); } catch (e) { }
  if (!r.ok) { const m = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : "Something went wrong."; throw new Error(m); }
  return data;
}
async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg); return r; } catch (e) { toast(e.message, true); return null; }
}
const me = () => USERS.find(u => u.id === ME) || {};

/* ------------------------------------------------------------ router */
async function init() {
  USERS = await (await fetch("/api/users")).json();
  if (!USERS.find(u => u.id === ME)) ME = USERS[0].id;
  const sel = $("#user");
  sel.innerHTML = USERS.map(u => `<option value="${u.id}">${esc(u.name)}</option>`).join("");
  sel.value = ME;
  sel.onchange = () => { ME = sel.value; try { localStorage.setItem("bl_user", ME); } catch (e) { } route(); };
  window.addEventListener("hashchange", route);
  if (!location.hash) location.hash = "#/new";
  route();
}
async function route() {
  const h = location.hash.replace(/^#\/?/, "").split("/");
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("on", a.dataset.nav === (h[0] === "content" ? "queue" : h[0])));
  view.innerHTML = '<p class="muted">Loading…</p>';
  try {
    if (h[0] === "new") return newView();
    if (h[0] === "queue") return queueView();
    if (h[0] === "content") return contentView(+h[1]);
    if (h[0] === "library") return libraryView();
    if (h[0] === "insights") return insightsView();
    if (h[0] === "about") return aboutView();
    location.hash = "#/new";
  } catch (e) { view.innerHTML = `<div class="card"><b>Could not load.</b> ${esc(e.message)}</div>`; }
}

/* ----------------------------------------------------------- new view */
const SAMPLES = {
  messy: { title: "Weekend promo post", kind: "post", channel: "Instagram",
    body: "HURRY!!! Our lumora Hub is the BEST way to light your home! Our cheap bulbs make users smile, guaranteed! Spring Sale: 20% off all bulbs. Better than Philips Hue. Click here to shop." },
  facts: { title: "Warranty and energy ad", kind: "advertisement", channel: "Google Ads",
    body: "Lumora Smart Bulbs use up to 90% less energy and come with a 5-year warranty. The Lumora Hub connects up to 100 bulbs. Lumora was founded in 2015. Free delivery on orders over $30." },
  clean: { title: "Hub setup email", kind: "email", channel: "Email",
    body: "Hello! Your Lumora Hub is ready. It connects up to 64 bulbs, so you can light every room. Follow the [Lumora Hub setup guide](https://example.com/setup) to get started." },
};
function newView() {
  view.innerHTML = `
  <h1>Check content before it is published</h1>
  <p class="sub">Paste or upload a post, advertisement, email, document or image. BrandLoom checks it against the approved guidelines, facts, terminology and palette, explains every issue and suggests a fix. You decide what changes.</p>
  <div class="card">
    <div class="tabs" role="tablist"><button class="on" data-t="text" role="tab">Text or document</button><button data-t="image" role="tab">Image</button></div>
    <div id="pane"></div>
  </div>`;
  const pane = $("#pane");
  const show = t => {
    document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === t));
    t === "text" ? textForm(pane) : imageForm(pane);
  };
  document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => show(b.dataset.t));
  show("text");
}
function textForm(p) {
  p.innerHTML = `
  <div class="row small" style="margin-bottom:10px">Try a sample:
    <button class="btn sec sm" data-s="messy">Messy social post</button>
    <button class="btn sec sm" data-s="facts">Ad with wrong facts</button>
    <button class="btn sec sm" data-s="clean">Clean email</button></div>
  <div class="row"><label class="f" style="flex:2;min-width:220px">Title<input type="text" id="title" maxlength="120"></label>
  <label class="f" style="flex:1;min-width:150px">Type<select id="kind"><option value="post">Social post</option><option value="advertisement">Advertisement</option><option value="email">Email</option><option value="document">Document</option></select></label>
  <label class="f" style="flex:1;min-width:150px">Channel (optional)<input type="text" id="channel" placeholder="e.g. Instagram"></label></div>
  <label class="f">Content (plain text, Markdown or HTML)<textarea id="body" rows="10" placeholder="Paste your copy here, or upload a file below."></textarea></label>
  <div class="row"><label class="btn sec sm" style="cursor:pointer">Upload .txt, .docx or .pdf<input type="file" id="file" accept=".txt,.md,.html,.htm,.docx,.pdf" hidden></label>
  <span class="muted small" id="fname"></span></div>
  <details><summary>Design colours used (optional): checks contrast and palette</summary>
  <div class="row" style="margin-top:8px"><label class="f">Text colour <input type="color" id="fg" value="#14213d"></label>
  <label class="f">Background colour <input type="color" id="bg" value="#fff8ec"></label>
  <label class="small"><input type="checkbox" id="usecol"> Include in check</label></div></details>
  <div class="row" style="margin-top:12px"><button class="btn" id="go">Check content</button></div>`;
  p.querySelectorAll("[data-s]").forEach(b => b.onclick = () => { const s = SAMPLES[b.dataset.s]; $("#title").value = s.title; $("#kind").value = s.kind; $("#channel").value = s.channel; $("#body").value = s.body; });
  $("#file").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    const r = await act(() => api("/extract", { method: "POST", form: fd }));
    if (r) { $("#body").value = r.text; $("#fname").textContent = r.filename; if (!$("#title").value) $("#title").value = r.filename.replace(/\.[^.]+$/, ""); }
  };
  $("#go").onclick = async () => {
    const use = $("#usecol").checked;
    const r = await act(() => api("/content", { method: "POST", json: { title: $("#title").value, kind: $("#kind").value, channel: $("#channel").value, body: $("#body").value, fg: use ? $("#fg").value : "", bg: use ? $("#bg").value : "" } }));
    if (r) location.hash = "#/content/" + r.id;
  };
}
function imageForm(p) {
  p.innerHTML = `
  <div class="row"><label class="f" style="flex:2;min-width:220px">Title<input type="text" id="ititle"></label>
  <label class="f" style="flex:1;min-width:150px">Channel (optional)<input type="text" id="ichan"></label></div>
  <label class="f">Image (PNG, JPG or WebP)<input type="file" id="ifile" accept="image/*"></label>
  <label class="f">Alt text (describe what the image shows)<input type="text" id="alt" placeholder="Leave empty to see the accessibility finding"></label>
  <p class="muted small">The image is checked for alt text, colours outside the approved palette and resolution.</p>
  <button class="btn" id="igo">Check image</button>`;
  $("#igo").onclick = async () => {
    const f = $("#ifile").files[0]; if (!f) return toast("Choose an image first.", true);
    const fd = new FormData(); fd.append("title", $("#ititle").value || f.name); fd.append("alt_text", $("#alt").value); fd.append("channel", $("#ichan").value); fd.append("file", f);
    const r = await act(() => api("/content/image", { method: "POST", form: fd }));
    if (r) location.hash = "#/content/" + r.id;
  };
}

/* --------------------------------------------------------- queue view */
async function queueView(filter = "") {
  const rows = await api("/content" + (filter ? "?status=" + filter : ""));
  view.innerHTML = `<div class="row sp"><div><h1>Review queue</h1><p class="sub">Everything submitted for checking, with its approval status.</p></div>
  <label class="small">Status <select id="flt" style="width:auto"><option value="">All</option>${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === filter ? "selected" : ""}>${v}</option>`).join("")}</select></label></div>
  <div class="card" style="padding:0;overflow:auto"><table><thead><tr><th>Title</th><th>Type</th><th>Author</th><th>Status</th><th>Open findings</th><th>Revisions</th><th>Updated</th></tr></thead><tbody>
  ${rows.map(r => `<tr class="click" tabindex="0" data-id="${r.id}"><td><b>${esc(r.title)}</b></td><td>${esc(r.kind)}</td><td>${esc(r.author_name)}</td><td><span class="badge ${r.status}">${STATUS[r.status]}</span></td><td>${r.open_findings}</td><td>${r.revisions}</td><td class="muted small">${esc(r.updated_at)}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">Nothing here yet.</td></tr>`}
  </tbody></table></div>`;
  $("#flt").onchange = e => queueView(e.target.value);
  view.querySelectorAll("tr.click").forEach(tr => { tr.onclick = () => location.hash = "#/content/" + tr.dataset.id; tr.onkeydown = e => { if (e.key === "Enter") tr.onclick(); }; });
}

/* ------------------------------------------------------- content view */
let D = null, SEL = null, SHOW_RESOLVED = false;
async function contentView(id) { D = await api("/content/" + id); SEL = null; renderContent(); }

function wordDiff(a, b) {
  const x = a.split(/(\s+)/), y = b.split(/(\s+)/), n = x.length, m = y.length;
  if (n * m > 400000) return `<del>${esc(a)}</del> <ins>${esc(b)}</ins>`;
  const L = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0, out = "";
  while (i < n && j < m) {
    if (x[i] === y[j]) { out += esc(x[i]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) { out += `<del>${esc(x[i])}</del>`; i++; }
    else { out += `<ins>${esc(y[j])}</ins>`; j++; }
  }
  while (i < n) out += `<del>${esc(x[i++])}</del>`;
  while (j < m) out += `<ins>${esc(y[j++])}</ins>`;
  return out;
}
function highlighted(body, findings) {
  const spans = findings.filter(f => f.start != null && f.end > f.start && f.state !== "superseded")
    .sort((a, b) => a.start - b.start || b.end - a.end);
  let pos = 0, out = "";
  for (const f of spans) {
    if (f.start < pos) continue;
    out += esc(body.slice(pos, f.start));
    const cls = f.state === "open" ? f.severity : "done";
    out += `<mark class="${cls} ${SEL === f.id ? "sel" : ""}" data-f="${f.id}" tabindex="0" title="${esc(f.rule_id + ": " + f.rule_title)}">${esc(body.slice(f.start, f.end))}</mark>`;
    pos = f.end;
  }
  return out + esc(body.slice(pos));
}
function ratio(fg, bg) {
  const p = h => { h = h.replace("#", ""); if (h.length === 3) h = h.split("").map(c => c + c).join(""); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); };
  const L = c => { const v = c.map(x => { x /= 255; return x <= .03928 ? x / 12.92 : Math.pow((x + .055) / 1.055, 2.4); }); return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]; };
  const a = L(p(fg)), b = L(p(bg)); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}
function renderContent() {
  const { content: c, revision: rev, findings, perms, revisions, comments, audit } = D;
  const open = findings.filter(f => f.state === "open");
  const count = s => open.filter(f => f.severity === s).length;
  const shown = findings.filter(f => SHOW_RESOLVED || f.state === "open");
  const stepIdx = { draft: 0, changes_requested: 0, in_review: 1, approved: 2, rejected: 2 }[c.status];
  const isImg = c.has_image;
  view.innerHTML = `
  <div class="row sp"><div><h1>${esc(c.title)}</h1>
  <p class="sub"><span class="badge ${c.status}">${STATUS[c.status]}</span> &nbsp;${esc(c.kind)}${c.channel ? " · " + esc(c.channel) : ""} · by ${esc(c.author_name)} · revision ${rev.n}</p></div>
  <div class="row"><span><span class="sev high"></span>${count("high")} high</span><span><span class="sev medium"></span>${count("medium")} medium</span><span><span class="sev low"></span>${count("low")} low</span></div></div>
  <div class="grid2">
   <div>
    <div class="card"><div class="row sp"><h2>${isImg ? "Image and alt text" : "Content"}</h2>
      ${perms.can_edit ? `<div class="row"><button class="btn sec sm" id="edit">Edit text</button><button class="btn sec sm" id="recheck" title="Re-run all checks with the current library">Re-check</button></div>` : ""}</div>
      ${isImg ? `<img class="up" alt="${esc(rev.body || "Uploaded image without alt text")}" src="" id="img"><p class="small"><b>Alt text:</b> ${esc(rev.body) || '<span class="muted">(none)</span>'}</p>` : ""}
      ${isImg ? "" : `<div class="doc" id="doc">${highlighted(rev.body, findings)}</div>`}
      <div id="editor" hidden><textarea id="ebody" rows="9">${esc(rev.body)}</textarea>
        <input type="text" id="enote" placeholder="What did you change? (optional)" style="margin-top:6px">
        <div class="row" style="margin-top:6px"><button class="btn" id="esave">Save as new revision</button><button class="btn sec" id="ecancel">Cancel</button></div></div>
      ${(c.fg || c.bg || !isImg && perms.can_edit) ? designBox(c, perms) : ""}
    </div>
    <div class="card"><h2>Approval workflow</h2>
      <div class="steps"><span class="${stepIdx === 0 ? "on" : "done"}">1 Draft and fix</span><span class="${stepIdx === 1 ? "on" : stepIdx > 1 ? "done" : ""}">2 In review</span><span class="${stepIdx === 2 ? "on" : ""}">3 ${c.status === "rejected" ? "Rejected" : "Approved"}</span></div>
      ${perms.blockers.map(b => `<div class="note">⚠ ${esc(b)}</div>`).join("")}${perms.warnings.map(b => `<div class="note">ℹ ${esc(b)}. You can still submit.</div>`).join("")}
      ${perms.requires_reviewer ? `<div class="note">This content has claim or fact findings, so it needs a <b>Compliance Reviewer</b> to approve.</div>` : ""}
      ${["draft", "changes_requested"].includes(c.status) ? `<button class="btn" id="submit" ${perms.can_submit ? "" : "disabled"}>Submit for approval</button>` : ""}
      ${c.status === "in_review" ? overrides(findings) + decisionBox(perms) : ""}
      ${c.status === "approved" ? `<p class="small">✔ Approved by a person. Nothing is published automatically.</p>` : ""}
    </div>
    <div class="card"><h2>Comments</h2>
      ${comments.map(m => `<div class="comment"><b>${esc(m.author)}</b> <span class="muted small">${esc(m.created_at)}</span><br>${esc(m.body)}</div>`).join("") || '<p class="muted small">No comments yet.</p>'}
      <div class="row" style="margin-top:8px"><input type="text" id="cmt" placeholder="Write a comment" style="flex:1"><button class="btn sm" id="cpost">Post</button></div></div>
    <div class="card"><h2>Revision history</h2>
      ${revisions.slice().reverse().map((r, i, arr) => { const prev = arr[i + 1]; return `<details><summary>Revision ${r.n} · ${esc(r.author)} · ${esc(r.note)} <span class="muted small">${esc(r.created_at)}</span></summary>${prev ? `<div class="diffbox">${wordDiff(prev.body, r.body)}</div>` : `<div class="diffbox">${esc(r.body)}</div>`}</details>`; }).join("")}
      <details><summary>Audit log (${audit.length})</summary>${audit.map(a => `<div class="small"><span class="muted">${esc(a.created_at)}</span> · <b>${esc(a.actor)}</b> · ${esc(a.action.replace(/_/g, " "))} ${a.detail ? "· " + esc(a.detail) : ""}</div>`).join("")}</details></div>
   </div>
   <div>
    <div class="row sp"><h2>Findings (${open.length} open)</h2><label class="small"><input type="checkbox" id="showres" ${SHOW_RESOLVED ? "checked" : ""}> show resolved</label></div>
    ${shown.map(findingCard).join("") || `<div class="card"><b>No open findings.</b><p class="muted small">Everything checked against the approved library passes. A person still has to approve.</p></div>`}
   </div>
  </div>`;
  wire();
}
function designBox(c, perms) {
  const has = c.fg && c.bg;
  return `<details ${has ? "open" : ""}><summary>Design colours</summary><div class="row" style="margin-top:8px">
  <label class="small">Text <input type="color" id="dfg" value="${c.fg || "#14213d"}" ${perms.can_edit ? "" : "disabled"}></label>
  <label class="small">Background <input type="color" id="dbg" value="${c.bg || "#fff8ec"}" ${perms.can_edit ? "" : "disabled"}></label>
  ${has ? `<span class="preview" style="color:${c.fg};background:${c.bg}">Aa ${ratio(c.fg, c.bg).toFixed(1)}:1</span>` : ""}
  ${perms.can_edit ? `<button class="btn sec sm" id="dsave">Apply colours</button>` : ""}</div></details>`;
}
function overrides(fs) {
  const d = fs.filter(f => f.state === "dismissed" && (f.needs_human || f.severity === "high"));
  if (!d.length) return "";
  return `<div class="note"><b>Overrides to confirm</b>${d.map(f => `<div class="small" style="margin-top:4px">${esc(f.rule_id)} “${esc(f.text)}”: ${esc(f.reason || "no reason")}</div>`).join("")}</div>`;
}
function decisionBox(p) {
  if (!p.can_decide) return `<p class="small muted">${esc(p.decide_note || "Waiting for a Manager or Compliance Reviewer to decide. You cannot approve your own content.")}</p>`;
  return `<label class="f">Decision comment<textarea id="dcomment" rows="2" placeholder="Required when requesting changes or rejecting"></textarea></label>
  <div class="row"><button class="btn ok" data-d="approve">Approve</button><button class="btn sec" data-d="changes">Request changes</button><button class="btn bad" data-d="reject">Reject</button></div>`;
}
function findingCard(f) {
  const resolved = f.state !== "open";
  let sugg = "";
  if (f.fix && f.fix.op === "replace") sugg = `<div class="sugg"><b>Suggested fix:</b> <del>${esc(f.text)}</del> <ins>${esc(f.fix.text)}</ins></div>`;
  else if (f.fix) sugg = `<div class="sugg"><b>Suggested fix:</b> add <ins>${esc(f.fix.text.trim())}</ins> at the end</div>`;
  const canEdit = D.perms.can_edit;
  return `<div class="finding ${f.severity} ${resolved ? "resolved" : ""} ${SEL === f.id ? "sel" : ""}" data-fid="${f.id}">
   <div class="meta"><span class="sev ${f.severity}"></span><b>${esc(CAT[f.category] || f.category)}</b><span class="chip">${esc(f.rule_id)}</span><span>${f.severity} severity</span>
   <span title="Confidence of this deterministic match"><span class="conf"><i style="width:${Math.round(f.confidence * 100)}%"></i></span> ${Math.round(f.confidence * 100)}%</span>${f.needs_human ? '<span class="tag">Reviewer must confirm</span>' : ""}</div>
   <h3 style="margin-top:6px">${esc(f.rule_title)}</h3>
   ${f.text ? `<div class="small">Flagged: <span class="chip">${esc(f.text.length > 90 ? f.text.slice(0, 90) + "…" : f.text)}</span></div>` : ""}
   <p class="small" style="margin:6px 0"><b>Why:</b> ${esc(f.why)}</p>
   <div class="quote"><b>Source ${esc(f.rule_id)}:</b> “${esc(f.source_quote)}”</div>
   ${f.fix || !resolved ? sugg || `<div class="sugg"><b>Suggestion:</b> ${esc(f.suggestion)}</div>` : ""}
   ${f.fix ? `<div class="small muted">${esc(f.suggestion)}</div>` : ""}
   ${resolved ? `<div class="small"><b>${f.state === "accepted" ? "Accepted" : "Dismissed"}</b>${f.reason ? ": " + esc(f.reason) : ""}</div>` :
      canEdit ? `<div class="row" style="margin-top:8px">${f.fix ? `<button class="btn sm" data-acc="${f.id}">Accept fix</button><button class="btn sec sm" data-custom="${f.id}">Accept with my wording</button>` : ""}
      <button class="btn sec sm" data-dis="${f.id}">Dismiss with reason</button></div><div data-disbox="${f.id}"></div>` : ""}
  </div>`;
}
function wire() {
  const c = D.content;
  if (c.has_image) { const im = $("#img"); fetch("/api/content/" + c.id + "/image", { headers: { "X-User": ME } }).then(r => r.blob()).then(b => im.src = URL.createObjectURL(b)); }
  const reload = async (msg) => { D = await api("/content/" + c.id); renderContent(); if (msg) toast(msg); };
  const pick = id => { SEL = id; renderContent(); const el = $(`.finding[data-fid="${id}"]`); el && el.scrollIntoView({ block: "center", behavior: "smooth" }); };
  view.querySelectorAll("mark").forEach(m => { m.onclick = () => pick(+m.dataset.f); m.onkeydown = e => { if (e.key === "Enter") pick(+m.dataset.f); }; });
  view.querySelectorAll(".finding").forEach(el => el.onclick = e => { if (e.target.closest("button,input,textarea")) return; SEL = +el.dataset.fid; renderContent(); const m = $(`mark[data-f="${SEL}"]`); m && m.scrollIntoView({ block: "center" }); });
  $("#showres").onchange = e => { SHOW_RESOLVED = e.target.checked; renderContent(); };
  const edit = $("#edit");
  if (edit) {
    edit.onclick = () => { $("#editor").hidden = false; $("#doc") && ($("#doc").hidden = true); edit.hidden = true; };
    $("#ecancel").onclick = () => renderContent();
    $("#esave").onclick = async () => { if (await act(() => api(`/content/${c.id}/body`, { method: "PUT", json: { body: $("#ebody").value, note: $("#enote").value } }))) reload("Saved as a new revision and re-checked."); };
    $("#recheck").onclick = async () => { if (await act(() => api(`/content/${c.id}/recheck`, { method: "POST" }))) reload("Re-checked."); };
  }
  const ds = $("#dsave"); if (ds) ds.onclick = async () => { if (await act(() => api(`/content/${c.id}/meta`, { method: "PUT", json: { fg: $("#dfg").value, bg: $("#dbg").value } }))) reload("Colours updated and re-checked."); };
  view.querySelectorAll("[data-acc]").forEach(b => b.onclick = async () => { if (await act(() => api(`/findings/${b.dataset.acc}/accept`, { method: "POST", json: {} }))) reload("Fix applied as a new revision."); });
  view.querySelectorAll("[data-custom]").forEach(b => b.onclick = async () => {
    const f = D.findings.find(x => x.id == b.dataset.custom); const v = prompt("Replace “" + f.text + "” with:", f.fix && f.fix.text || ""); if (v === null) return;
    if (await act(() => api(`/findings/${f.id}/accept`, { method: "POST", json: { replacement: v } }))) reload("Your wording was applied.");
  });
  view.querySelectorAll("[data-dis]").forEach(b => b.onclick = () => {
    const box = $(`[data-disbox="${b.dataset.dis}"]`);
    box.innerHTML = `<div class="row" style="margin-top:6px"><input type="text" placeholder="Why is this acceptable? (required)" style="flex:1" id="r${b.dataset.dis}"><button class="btn sm" id="ok${b.dataset.dis}">Confirm dismiss</button></div>`;
    $("#r" + b.dataset.dis).focus();
    $("#ok" + b.dataset.dis).onclick = async () => { if (await act(() => api(`/findings/${b.dataset.dis}/dismiss`, { method: "POST", json: { reason: $("#r" + b.dataset.dis).value } }))) reload("Dismissed and logged."); };
  });
  const sub = $("#submit"); if (sub) sub.onclick = async () => { if (await act(() => api(`/content/${c.id}/submit`, { method: "POST" }))) reload("Submitted for approval."); };
  view.querySelectorAll("[data-d]").forEach(b => b.onclick = async () => { if (await act(() => api(`/content/${c.id}/decision`, { method: "POST", json: { decision: b.dataset.d, comment: $("#dcomment").value } }))) reload("Decision recorded."); });
  $("#cpost").onclick = async () => { const v = $("#cmt").value; if (v.trim() && await act(() => api(`/content/${c.id}/comments`, { method: "POST", json: { body: v } }))) reload(); };
}

/* ------------------------------------------------------- library view */
async function libraryView(tab = "rules") {
  const lib = await api("/library"); const mgr = me().role === "manager"; const rev = ["manager", "reviewer"].includes(me().role);
  view.innerHTML = `<div class="row sp"><div><h1>Brand library</h1><p class="sub">The approved sources every finding is checked against. Demo data for a fictional brand.</p></div>
  <button class="btn sec" id="exp">Export JSON</button></div>
  <div class="tabs"><button data-t="rules">Guidelines (${lib.rules.length})</button><button data-t="facts">Approved facts (${lib.facts.length})</button><button data-t="brand">Palette and assets</button></div><div id="tab"></div>`;
  view.querySelectorAll(".tabs button").forEach(b => { b.classList.toggle("on", b.dataset.t === tab); b.onclick = () => libraryView(b.dataset.t); });
  $("#exp").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(lib, null, 2)], { type: "application/json" })); a.download = "brand-library.json"; a.click(); };
  const t = $("#tab");
  if (tab === "rules") {
    t.innerHTML = `<div class="card" style="padding:0;overflow:auto"><table><thead><tr><th>ID</th><th>Category</th><th>Guideline</th><th>Severity</th><th>Active</th></tr></thead><tbody>
    ${lib.rules.map(r => `<tr><td>${esc(r.id)}</td><td>${esc(CAT[r.category] || r.category)}</td><td><b>${esc(r.title)}</b><br><span class="muted small">${esc(r.text)}</span></td><td><span class="sev ${r.severity}"></span>${r.severity}</td>
    <td>${mgr ? `<input type="checkbox" data-tg="${r.id}" ${r.active ? "checked" : ""} aria-label="Active"> ${r.id.startsWith("BG-9.") ? `<button class="btn sec sm" data-rm="${r.id}">Delete</button>` : ""}` : r.active ? "Yes" : "No"}</td></tr>`).join("")}</tbody></table></div>
    ${mgr ? ruleForm() : '<p class="muted small">Only a Brand Manager can add or switch off guidelines. Switch user to try.</p>'}`;
    t.querySelectorAll("[data-tg]").forEach(i => i.onchange = async () => { await act(() => api(`/library/rules/${i.dataset.tg}?active=${i.checked}`, { method: "PATCH" }), "Updated."); });
    t.querySelectorAll("[data-rm]").forEach(b => b.onclick = async () => { if (await act(() => api(`/library/rules/${b.dataset.rm}`, { method: "DELETE" }), "Deleted.")) libraryView("rules"); });
    const add = $("#addrule"); if (add) add.onclick = async () => {
      const kind = $("#rk").value, cfg = {}; const list = $("#rw").value.split(",").map(s => s.trim()).filter(Boolean);
      if (kind === "term") { cfg.banned = list; cfg.preferred = $("#rp").value; cfg.map = {}; list.forEach(w => cfg.map[w.toLowerCase()] = $("#rp").value); }
      else if (kind === "competitor") cfg.names = list;
      else if (kind === "pattern") { cfg.pattern = "\\b(" + list.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")\\b"; cfg.suggestion = $("#rp").value || "Reword this phrase."; }
      else { cfg.trigger = "\\b(" + list.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")\\b"; cfg.required = $("#rp").value; cfg.append = $("#rp").value + "."; }
      if (await act(() => api("/library/rules", { method: "POST", json: { category: $("#rc").value, title: $("#rt").value, text: $("#rx").value, severity: $("#rs").value, kind, config: cfg } }), "Guideline added.")) libraryView("rules");
    };
  } else if (tab === "facts") {
    t.innerHTML = `<div class="card" style="padding:0;overflow:auto"><table><thead><tr><th>ID</th><th>Approved statement</th><th>Matches sentences containing</th><th>Owner / source</th><th>Valid until</th>${rev ? "<th></th>" : ""}</tr></thead><tbody>
    ${lib.facts.map(f => `<tr><td>${esc(f.id)}</td><td>${esc(f.statement)}${f.supports.length ? `<br><span class="muted small">Supports claims: ${esc(f.supports.join(", "))}</span>` : ""}</td><td class="small">${esc(f.keywords.join(" + "))}</td><td class="small">${esc(f.owner)}<br>${esc(f.source)}</td><td class="small">${esc(f.valid_until || "no expiry")}</td>${rev ? `<td><button class="btn sec sm" data-fd="${f.id}">Delete</button></td>` : ""}</tr>`).join("")}</tbody></table></div>
    ${rev ? `<div class="card"><h2>Add an approved fact</h2><label class="f">Statement<input type="text" id="fs" placeholder="e.g. Lumora Smart Bulbs last up to 25,000 hours."></label>
    <div class="row"><label class="f" style="flex:1">Keywords (comma separated; all must appear in a sentence)<input type="text" id="fk" placeholder="bulb, hours"></label>
    <label class="f">Valid until (optional)<input type="date" id="fv"></label></div>
    <div class="row"><label class="f" style="flex:1">Owner<input type="text" id="fo"></label><label class="f" style="flex:1">Source<input type="text" id="fsrc"></label>
    <label class="f" style="flex:1">Supports claims (optional, comma separated)<input type="text" id="fsup" placeholder="highly rated"></label></div><button class="btn" id="addfact">Add fact</button></div>` : '<p class="muted small">Managers and Compliance Reviewers can add facts.</p>'}`;
    t.querySelectorAll("[data-fd]").forEach(b => b.onclick = async () => { if (await act(() => api(`/library/facts/${b.dataset.fd}`, { method: "DELETE" }), "Deleted.")) libraryView("facts"); });
    const af = $("#addfact"); if (af) af.onclick = async () => {
      const sp = s => $(s).value.split(",").map(x => x.trim()).filter(Boolean);
      if (await act(() => api("/library/facts", { method: "POST", json: { statement: $("#fs").value, keywords: sp("#fk"), valid_until: $("#fv").value || null, owner: $("#fo").value, source: $("#fsrc").value, supports: sp("#fsup") } }), "Fact added.")) libraryView("facts");
    };
  } else {
    const b = lib.settings;
    t.innerHTML = `<div class="card"><h2>Approved colour palette</h2><p>${b.palette.map(p => `<span style="margin-right:14px"><span class="swatch" style="background:${p.hex}"></span>${esc(p.name)} <code>${esc(p.hex)}</code></span>`).join("")}</p>
    <p class="small muted">Neutral black, white and greys are always allowed. Brand name: <b>${esc(b.name)}</b> · Tagline: “${esc(b.tagline)}”</p>
    ${mgr ? `<label class="f">Edit palette (one per line: Name, #hex)<textarea id="pal" rows="5">${b.palette.map(p => p.name + ", " + p.hex).join("\n")}</textarea></label>
    <label class="f">Allowed ALL-CAPS acronyms (comma separated)<input type="text" id="caps" value="${esc(b.allowed_caps.join(", "))}"></label><button class="btn" id="savebrand">Save</button>` : ""}</div>`;
    const sb = $("#savebrand"); if (sb) sb.onclick = async () => {
      const palette = $("#pal").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => { const [n, h] = l.split(","); return { name: (n || "").trim(), hex: (h || "").trim() }; });
      if (await act(() => api("/library/brand", { method: "PUT", json: { palette, allowed_caps: $("#caps").value.split(",").map(x => x.trim()).filter(Boolean) } }), "Saved.")) libraryView("brand");
    };
  }
}
function ruleForm() {
  return `<div class="card"><h2>Add a guideline</h2><div class="row">
  <label class="f">Type<select id="rk"><option value="term">Banned term → preferred term</option><option value="competitor">Competitor names</option><option value="pattern">Phrases to avoid</option><option value="require">Required wording when a phrase appears</option></select></label>
  <label class="f">Category<select id="rc">${Object.entries(CAT).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
  <label class="f">Severity<select id="rs"><option>medium</option><option>high</option><option>low</option></select></label></div>
  <label class="f">Title<input type="text" id="rt"></label><label class="f">Guideline text (shown as the source when it is breached)<input type="text" id="rx"></label>
  <label class="f">Words or phrases (comma separated: banned terms, competitor names, phrases to avoid, or trigger words)<input type="text" id="rw"></label>
  <label class="f">Preferred term / suggestion / required wording<input type="text" id="rp"></label><button class="btn" id="addrule">Add guideline</button></div>`;
}

/* ------------------------------------------------------ insights view */
async function insightsView() {
  const d = await api("/insights"); const max = Math.max(1, ...Object.values(d.by_category));
  const approved = d.by_status.approved || 0;
  view.innerHTML = `<h1>Governance insights</h1><p class="sub">Which mistakes keep coming back, and which guidelines may need clearer wording.</p>
  <div class="stats"><div class="stat"><b>${d.total_content}</b><span>pieces checked</span></div><div class="stat"><b>${d.avg_findings_first_pass}</b><span>avg findings on first check</span></div>
  <div class="stat"><b>${d.open_findings_now}</b><span>findings still open</span></div><div class="stat"><b>${approved}</b><span>approved by a person</span></div>
  <div class="stat"><b>${d.by_status.in_review || 0}</b><span>waiting for review</span></div></div>
  <div class="grid2"><div class="card"><h2>Issues by category (first check)</h2>${Object.entries(d.by_category).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div class="bar"><span class="lab">${esc(CAT[k] || k)}</span><span class="t"><i style="width:${v / max * 100}%"></i></span><b>${v}</b></div>`).join("") || '<p class="muted">No data yet.</p>'}</div>
  <div class="card"><h2>Recurring mistakes</h2><p class="small muted">The same rule broken by the same person in two or more pieces: a good topic for coaching.</p>
  ${d.recurring.map(r => `<div class="small" style="margin:6px 0"><b>${esc(r.author)}</b> · ${esc(r.rule_id)} ${esc(r.title)} <span class="badge">${r.pieces} pieces</span></div>`).join("") || '<p class="muted small">None yet.</p>'}</div></div>
  <div class="card"><h2>Guidelines that may be unclear</h2><p class="small muted">When people often dismiss a rule with a reason, the rule may be too strict, outdated or ambiguous. Review its wording.</p>
  ${d.unclear_rules.map(r => `<div class="note"><b>${esc(r.rule_id)} ${esc(r.title)}</b>: dismissed ${r.dismissed} of ${r.accepted + r.dismissed} times (${Math.round(r.dismissal_rate * 100)}%). Consider adding an exception or clearer examples.</div>`).join("") || '<p class="muted small">No rule is dismissed often enough yet (needs 3+ resolved findings and 40%+ dismissals).</p>'}</div>
  <div class="card" style="padding:0;overflow:auto"><table><thead><tr><th>Rule</th><th>Category</th><th>Flagged</th><th>Accepted</th><th>Dismissed</th><th>Dismissal rate</th></tr></thead><tbody>
  ${d.top_rules.map(r => `<tr><td>${esc(r.rule_id)} ${esc(r.title)}</td><td>${esc(CAT[r.category] || r.category)}</td><td>${r.count}</td><td>${r.accepted}</td><td>${r.dismissed}</td><td>${r.dismissal_rate == null ? "–" : Math.round(r.dismissal_rate * 100) + "%"} ${r.unclear ? '<span class="tag">possibly unclear</span>' : ""}</td></tr>`).join("")}</tbody></table></div>`;
}

/* --------------------------------------------------------- about view */
async function aboutView() {
  const d = await api("/ai-disclosure");
  view.innerHTML = `<h1>AI use, privacy and human control</h1><div class="card">
  <h2>What reviews your content</h2><p>${esc(d.review_engine)}</p>
  <h2>External services</h2><p>${d.external_services.length ? esc(d.external_services.join(", ")) : "None."} ${esc(d.data_sent_outside)}</p>
  <h2>Human control</h2><ul><li>Suggestions are never applied automatically. The creator accepts, edits or dismisses each one.</li>
  <li>Dismissing a high-severity finding needs a written reason, and the reason is logged.</li>
  <li>Claim and fact findings must be confirmed by a Compliance Reviewer.</li>
  <li>Nobody can approve their own content. Nothing is published by BrandLoom.</li></ul>
  <h2>Confidentiality</h2><p>This demo uses a fictional brand. Content, revisions and comments are stored on this server only. Roles limit who can change the library and who can approve.</p>
  <h2>Coming in a later round</h2><p>${esc(d.note)}</p>
  <h2>Demo limitations</h2><p class="small muted">Sign-in here is a role switcher for demonstration, not real authentication. The rule engine finds exact terms, patterns, numbers and formats; it does not understand meaning, so a human reviewer remains essential.</p></div>`;
}
init();
