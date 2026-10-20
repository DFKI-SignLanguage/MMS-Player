/* MMS-Player web editor client. */
"use strict";

(() => {

const BOOT = window.MMSWEB_BOOT;
const SCHEMA = BOOT.schema;
const HOLD = SCHEMA.hold;
const MMS_SUFFIX = ".mms.csv";

const $ = (sel) => document.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k === "dataset") Object.assign(e.dataset, v);
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children) if (c !== null && c !== undefined) e.append(c);
  return e;
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

//
// ---------------------------------------------------------------- Server API
//
async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const isJson = (res.headers.get("content-type") || "").includes("json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    const err = new Error((isJson && data && data.error) || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

async function pollJob(jobId, onUpdate, withLog = () => false) {
  for (;;) {
    const job = await api("GET", `/api/jobs/${jobId}${withLog() ? "?log=1" : ""}`);
    onUpdate(job);
    if (["done", "error", "cancelled"].includes(job.status)) return job;
    await sleep(job.status === "queued" ? 1200 : 600);
  }
}

let statusTimer = null;
function setStatus(msg, isError = false) {
  const s = $("#status");
  s.textContent = msg;
  s.classList.toggle("error", isError);
  clearTimeout(statusTimer);
  if (msg) statusTimer = setTimeout(() => { s.textContent = ""; }, isError ? 12000 : 5000);
}

//
// ---------------------------------------------------------------- Schema
//
const GROUPS = [];        // {section, sub, group}
const FILL_OF = {};       // column -> the fill group it belongs to
const GROUP_OF_COL = {};  // column -> group entry
for (const section of SCHEMA.sections) {
  for (const sub of section.subsections) {
    for (const group of sub.groups) {
      const entry = { section, sub, group };
      GROUPS.push(entry);
      for (const c of group.columns) GROUP_OF_COL[c] = entry;
    }
  }
}
for (const fg of SCHEMA.fill_groups) for (const c of fg) FILL_OF[c] = fg;
const KNOWN_COLS = GROUPS.flatMap((g) => g.group.columns);
const GLOSS_COLS = new Set(SCHEMA.gloss_columns);
const TIMING_ABS = new Set(["framestart", "frameend"]);
const TIMING_REL = new Set(["duration", "transition"]);
const isInflection = (c) => c in SCHEMA.identity;
const INFLECTION_SUBS = SCHEMA.sections.find((s) => s.id === "inflections").subsections;
// Rotations are stored in radians in the MMS, but edited in degrees.
// Locations and rotations are shown with one decimal.
const INFLECTION_GROUPS = INFLECTION_SUBS.flatMap((s) => s.groups);
const ROT_COLS = new Set(INFLECTION_GROUPS.filter((g) => g.unit === "°").flatMap((g) => g.columns));
const ROUND1_COLS = INFLECTION_GROUPS.filter((g) => g.unit === "°" || g.unit === "cm").flatMap((g) => g.columns);
const TRIPLET_IDS = GROUPS.filter((g) => g.group.columns.length > 1).map((g) => g.group.id);
const OTHER_SECTION = { id: "other", label: "Other" };
const OTHER_SUB = { id: "other", label: "Unknown columns" };

//
// ---------------------------------------------------------------- State
//
const state = {
  name: "untitled" + MMS_SUFFIX,
  loadedFrom: null,   // name of the project file this document is bound to (for overwrite checks)
  rows: [],
  extraColumns: [],
  relative: true,
  selected: 0,
  dirty: false,
};

const PREFS_KEY = "mmsweb.prefs";
const DRAFT_KEY = "mmsweb.draft";
const prefs = Object.assign({
  expanded: [], hiddenSubs: [], size: String(BOOT.defaults.render_size_pct), panel: false, rightW: 540, zoom: 120,
  view: "3d", leftW: 250, signsHidden: false,
}, readStorage(PREFS_KEY));

function readStorage(key) {
  try { return JSON.parse(localStorage.getItem(key)) || {}; } catch (e) { return {}; }
}
function writeStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* storage unavailable */ }
}
const savePrefs = () => writeStorage(PREFS_KEY, prefs);
const saveDraft = debounce(() => writeStorage(DRAFT_KEY, {
  name: state.name, loadedFrom: state.loadedFrom, rows: state.rows, extraColumns: state.extraColumns,
  relative: state.relative, dirty: state.dirty, units: "deg",
}), 400);

const glossState = {
  list: [], ids: new Set(), loaded: false,
  durations: {},        // gloss id -> original duration in seconds
  filtered: [],         // ids shown in the list
  active: -1,           // keyboard-highlighted index in filtered
  chosen: null,         // id selected for preview
  target: null,         // {row, col} gloss cell receiving the inserted signs
  typing: false,        // the user typed in the target cell since focusing it
};

function emptyRow() {
  const r = {};
  for (const c of KNOWN_COLS) r[c] = "";
  for (const c of state.extraColumns) r[c] = "";
  return r;
}

function newRow(prev) {
  const r = emptyRow();
  const prevEnd = prev ? parseNum(prev.frameend) : NaN;
  const start = isFinite(prevEnd) ? prevEnd : 0;
  r.framestart = state.relative ? "0" : String(start);
  r.frameend = state.relative ? "0" : String(round3(start + 1));
  r.duration = "100%";
  r.transition = prev ? "0.5" : "0.2";
  return r;
}

const round3 = (x) => Math.round(x * 1000) / 1000;

function parseNum(s) {
  s = (s ?? "").toString().trim();
  if (s === "") return NaN;
  return Number(s);
}

/** Converts an inflection value from the MMS file units to the editor units (degrees, one decimal). */
function toDisplay(col, s) {
  const x = parseNum(s);
  if (!isFinite(x)) return s;
  const v = ROT_COLS.has(col) ? x * 180 / Math.PI : x;
  return String(Math.round(v * 10) / 10);
}

/** Converts a value from the editor units back to the MMS file units (radians for rotations). */
function toFile(col, s) {
  const x = parseNum(s);
  if (!ROT_COLS.has(col) || !isFinite(x)) return s;
  return String(Math.round(x * Math.PI / 180 * 1e6) / 1e6);
}

function parseDuration(s) {
  s = (s ?? "").toString().trim();
  if (s === "") return null;
  const m = s.match(/^([0-9]*\.?[0-9]+)\s*%$/);
  if (m) return { value: Number(m[1]) / 100, pct: true };
  const n = Number(s);
  return isFinite(n) ? { value: n, pct: false } : null;
}

function markChanged({ timeline = true, structure = false } = {}) {
  if (!state.dirty) {
    state.dirty = true;
    updateDirtyFlag();
  }
  if (structure) renderTable();
  scheduleValidate();
  if (timeline) scheduleTimeline();
  saveDraft();
}

function updateDirtyFlag() {
  $("#dirty-flag").textContent = state.dirty ? "● unsaved" : "";
  document.title = (state.dirty ? "● " : "") + state.name + " — MMS-Player Editor";
  // Only files of the project folder can be deleted (not examples, imports, or never saved MMS)
  $("#btn-delete").disabled = !state.loadedFrom;
}

//
// ---------------------------------------------------------------- Table rendering
//
function visibleGroups() {
  const out = GROUPS.filter((g) => !prefs.hiddenSubs.includes(g.sub.id));
  for (const c of state.extraColumns) {
    out.push({ section: OTHER_SECTION, sub: OTHER_SUB, group: { id: "x:" + c, label: c, columns: [c], unit: "" } });
  }
  return out;
}

function isExpanded(g) {
  return g.group.columns.length > 1 && prefs.expanded.includes(g.group.id);
}

function leavesOf(g) {
  if (g.group.columns.length === 1 || isExpanded(g)) {
    return g.group.columns.map((c) => ({ kind: "col", col: c, g }));
  }
  return [{ kind: "triplet", g }];
}

function tripletText(row, group) {
  const vals = group.columns.map((c) => (row[c] ?? "").trim());
  return vals.every((v) => v === "") ? "" : vals.join(", ");
}

function setTriplet(row, group, text) {
  const t = text.trim();
  const parts = t === "" ? [] : t.split(/\s*[,;]\s*|\s+/);
  group.columns.forEach((c, k) => { row[c] = (parts[k] ?? "").trim(); });
}

function colClass(col) {
  if (GLOSS_COLS.has(col)) return "col-gloss";
  if (TIMING_ABS.has(col) || TIMING_REL.has(col)) return "col-timing";
  if (isInflection(col)) return "col-num";
  return "col-other";
}

function timingDisabled(col) {
  return (state.relative && TIMING_ABS.has(col)) || (!state.relative && TIMING_REL.has(col));
}

function renderTable() {
  const groups = visibleGroups();
  const thead = $("#mms-table thead");
  const tbody = $("#mms-table tbody");
  thead.textContent = "";
  tbody.textContent = "";

  // Leaves, with flags for the first leaf of each subsection
  const leaves = [];
  let lastSub = null;
  for (const g of groups) {
    leavesOf(g).forEach((leaf, k) => {
      leaf.subStart = k === 0 && g.sub !== lastSub && lastSub !== null;
      leaves.push(leaf);
    });
    lastSub = g.sub;
  }

  // Header rows: sections, subsections, groups, components
  const tr1 = el("tr"), tr2 = el("tr"), tr3 = el("tr"), tr4 = el("tr");
  tr1.append(el("th", { class: "rowhead", rowspan: 4, text: "#" }));

  const spans = (keyFn) => {
    const out = [];
    for (const leaf of leaves) {
      const key = keyFn(leaf);
      if (out.length && out[out.length - 1].key === key) out[out.length - 1].n++;
      else out.push({ key, leaf, n: 1 });
    }
    return out;
  };
  for (const s of spans((l) => l.g.section)) {
    tr1.append(el("th", { class: `sec-${s.key.id}` + (s.leaf.subStart ? " sub-start" : ""), colspan: s.n, text: s.key.label }));
  }
  for (const s of spans((l) => l.g.sub)) {
    tr2.append(el("th", { class: `sec-${s.leaf.g.section.id}` + (s.leaf.subStart ? " sub-start" : ""), colspan: s.n, text: s.key.label }));
  }
  for (const s of spans((l) => l.g.group)) {
    const g = s.leaf.g;
    const th = el("th", { class: (s.leaf.subStart ? "sub-start " : "") + timingHeaderClass(g), colspan: s.n, title: g.group.hint || "" });
    if (g.group.columns.length > 1) {
      th.append(el("button", {
        class: "toggle", title: isExpanded(g) ? "Collapse x/y/z" : "Expand x/y/z",
        text: isExpanded(g) ? "▾" : "▸", onclick: () => toggleExpanded(g.group.id),
      }));
    }
    th.append(g.group.label);
    if (g.group.unit) th.append(el("span", { class: "unit", text: `(${g.group.unit})` }));
    tr3.append(th);
  }
  for (const leaf of leaves) {
    const g = leaf.g;
    let text;
    if (leaf.kind === "triplet") text = g.group.columns.map((c) => c.slice(g.group.id.length)).join(", ");
    else if (g.group.columns.length > 1) text = leaf.col.slice(g.group.id.length);
    else text = leaf.col;
    tr4.append(el("th", { class: (leaf.subStart ? "sub-start " : "") + timingHeaderClass(g), text, title: leaf.col || g.group.columns.join(", ") }));
  }
  thead.append(tr1, tr2, tr3, tr4);

  // Body
  state.rows.forEach((row, i) => {
    const tr = el("tr", { dataset: { row: i }, class: i === state.selected ? "selected" : "" });
    tr.append(el("td", { class: "rowhead", draggable: "true", title: "Drag to reorder. Right click for more actions." },
      el("span", { class: "grip", text: "⋮⋮" }), String(i + 1)));
    for (const leaf of leaves) {
      const sub = leaf.subStart ? " sub-start" : "";
      if (leaf.kind === "triplet") {
        const g = leaf.g.group;
        tr.append(el("td", { class: "col-triplet" + sub, dataset: { group: g.id } },
          el("input", { type: "text", spellcheck: "false", autocomplete: "off", value: tripletText(row, g),
            dataset: { group: g.id }, title: g.columns.join(", ") })));
      } else {
        const c = leaf.col;
        tr.append(el("td", { class: colClass(c) + sub + (timingDisabled(c) ? " disabled-timing" : ""), dataset: { col: c } },
          el("input", { type: "text", spellcheck: "false", autocomplete: "off", value: row[c] ?? "", dataset: { col: c } })));
      }
    }
    tbody.append(tr);
  });

  validate();
  applyValidationMarks();
}

function timingHeaderClass(g) {
  const c = g.group.columns[0];
  return (TIMING_ABS.has(c) || TIMING_REL.has(c)) && timingDisabled(c) ? "disabled-timing" : "";
}

function refreshRowInputs(i) {
  const tr = rowElement(i);
  if (!tr) return;
  const row = state.rows[i];
  for (const input of tr.querySelectorAll("input")) {
    if (input === document.activeElement) continue;
    if (input.dataset.col) input.value = row[input.dataset.col] ?? "";
    else if (input.dataset.group) input.value = tripletText(row, groupById(input.dataset.group));
  }
}

const groupById = (id) => GROUPS.find((g) => g.group.id === id).group;
const rowElement = (i) => $(`#mms-table tbody tr[data-row="${i}"]`);

function toggleExpanded(groupId) {
  const k = prefs.expanded.indexOf(groupId);
  if (k >= 0) prefs.expanded.splice(k, 1); else prefs.expanded.push(groupId);
  savePrefs();
  renderTable();
}

function selectRow(i, { scroll = false, focus = false } = {}) {
  if (i < 0 || i >= state.rows.length) return;
  if (state.selected !== i) {
    rowElement(state.selected)?.classList.remove("selected");
    state.selected = i;
    rowElement(i)?.classList.add("selected");
    updateTimelineSelection();
  }
  const tr = rowElement(i);
  if (scroll && tr) tr.scrollIntoView({ block: "nearest" });
  if (focus && tr) tr.querySelector("input")?.focus();
}

function focusCell(i, col) {
  const tr = rowElement(i);
  if (!tr) return;
  let input = tr.querySelector(`input[data-col="${col}"]`);
  if (!input && GROUP_OF_COL[col]) input = tr.querySelector(`input[data-group="${GROUP_OF_COL[col].group.id}"]`);
  if (input) { input.focus(); input.select(); }
}

//
// ---------------------------------------------------------------- Row operations
//
function insertRow(at, row) {
  state.rows.splice(at, 0, row);
  state.selected = at;
  markChanged({ structure: true });
  focusCell(at, "maingloss");
}

function addRow() {
  const i = Math.min(state.selected, state.rows.length - 1);
  insertRow(i + 1, newRow(state.rows[i]));
}

function duplicateRow(i = state.selected) {
  insertRow(i + 1, { ...state.rows[i] });
}

function removeRow(i = state.selected) {
  if (state.rows.length <= 1) {
    state.rows = [newRow(null)];
  } else {
    state.rows.splice(i, 1);
  }
  state.selected = Math.min(i, state.rows.length - 1);
  markChanged({ structure: true });
}

function moveRowTo(from, to) {
  if (to < 0 || to >= state.rows.length || from === to) return;
  const [r] = state.rows.splice(from, 1);
  state.rows.splice(to, 0, r);
  state.selected = to;
  markChanged({ structure: true });
}

function fillIdentity(i, cols, force = false) {
  const row = state.rows[i];
  for (const c of cols) if (force || (row[c] ?? "").trim() === "") row[c] = SCHEMA.identity[c];
}

function clearCols(i, cols) {
  for (const c of cols) state.rows[i][c] = "";
}

/** When a value is entered in an x/y/z triple whose other cells are empty, fill them with identity values. */
function autofillGroups(i, cols) {
  const row = state.rows[i];
  const triples = new Set(cols.filter((c) => FILL_OF[c]).map((c) => GROUP_OF_COL[c].group.columns));
  for (const triple of triples) {
    const typed = cols.some((c) => triple.includes(c) && (row[c] ?? "").trim() !== "");
    if (typed) fillIdentity(i, triple);
  }
}

//
// ---------------------------------------------------------------- Table events
//
function setupTableEvents() {
  const tbody = $("#mms-table tbody");

  tbody.addEventListener("focusin", (e) => {
    const input = e.target.closest("input");
    if (!input) return;
    const i = Number(input.closest("tr").dataset.row);
    selectRow(i);
    const col = input.dataset.col;
    glossState.typing = false;
    if (col && GLOSS_COLS.has(col)) {
      setGlossTarget(i, col);
      filterSigns(input.value);
    }
  });

  tbody.addEventListener("input", (e) => {
    const input = e.target;
    const i = Number(input.closest("tr").dataset.row);
    const row = state.rows[i];
    if (input.dataset.col) {
      const col = input.dataset.col;
      row[col] = input.value;
      if (GLOSS_COLS.has(col)) {
        glossState.typing = true;
        setGlossTarget(i, col);
        filterSigns(input.value, true);
        scheduleDurations();
      }
    } else if (input.dataset.group) {
      setTriplet(row, groupById(input.dataset.group), input.value);
    }
    markChanged();
  });

  tbody.addEventListener("change", (e) => {
    const input = e.target;
    const i = Number(input.closest("tr").dataset.row);
    const row = state.rows[i];
    const cols = input.dataset.col ? [input.dataset.col] : groupById(input.dataset.group).columns;
    for (const c of cols) row[c] = (row[c] ?? "").trim();
    autofillGroups(i, cols);
    refreshRowInputs(i);
    if (input.dataset.group) input.value = tripletText(row, groupById(input.dataset.group));
    markChanged();
  });

  tbody.addEventListener("keydown", (e) => {
    const input = e.target.closest("input");
    if (!input) return;
    const i = Number(input.closest("tr").dataset.row);
    const key = input.dataset.col ? `[data-col="${input.dataset.col}"]` : `[data-group="${input.dataset.group}"]`;
    const isGloss = input.dataset.col && GLOSS_COLS.has(input.dataset.col);
    const listNav = isGloss && glossState.typing && glossState.filtered.length > 0;

    if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      const to = i + (e.key === "ArrowUp" ? -1 : 1);
      moveRowTo(i, to);
      rowElement(state.selected)?.querySelector(`input${key}`)?.focus();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      addRow();
    } else if (listNav && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      moveSignActive(e.key === "ArrowDown" ? 1 : -1);
    } else if (listNav && e.key === "Enter" && glossState.active >= 0) {
      e.preventDefault();
      insertSign(glossState.filtered[glossState.active]);
    } else if (e.key === "Escape" && isGloss) {
      glossState.typing = false;
      setSignActive(-1);
    } else if (e.key === "Enter" || e.key === "ArrowDown" || e.key === "ArrowUp") {
      const to = i + (e.key === "ArrowUp" ? -1 : 1);
      const next = rowElement(to)?.querySelector(`input${key}`);
      if (next) { e.preventDefault(); input.dispatchEvent(new Event("change", { bubbles: true })); next.focus(); next.select(); }
    }
  });

  // Row selection via the row header
  tbody.addEventListener("mousedown", (e) => {
    const head = e.target.closest("td.rowhead");
    if (head) selectRow(Number(head.parentElement.dataset.row));
  });

  // Drag and drop reordering
  let dragFrom = null;
  const clearDropMarks = () => tbody.querySelectorAll(".drop-before, .drop-after").forEach((t) => t.classList.remove("drop-before", "drop-after"));
  tbody.addEventListener("dragstart", (e) => {
    const head = e.target.closest("td.rowhead");
    if (!head) { e.preventDefault(); return; }
    dragFrom = Number(head.parentElement.dataset.row);
    head.parentElement.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(dragFrom));
  });
  tbody.addEventListener("dragover", (e) => {
    if (dragFrom === null) return;
    const tr = e.target.closest("tr");
    if (!tr) return;
    e.preventDefault();
    clearDropMarks();
    const r = tr.getBoundingClientRect();
    tr.classList.add(e.clientY < r.top + r.height / 2 ? "drop-before" : "drop-after");
  });
  tbody.addEventListener("drop", (e) => {
    if (dragFrom === null) return;
    const tr = e.target.closest("tr");
    if (!tr) return;
    e.preventDefault();
    let to = Number(tr.dataset.row) + (tr.classList.contains("drop-after") ? 1 : 0);
    if (to > dragFrom) to--;
    clearDropMarks();
    const from = dragFrom;
    dragFrom = null;
    moveRowTo(from, to);
  });
  tbody.addEventListener("dragend", () => {
    dragFrom = null;
    clearDropMarks();
    tbody.querySelectorAll(".dragging").forEach((t) => t.classList.remove("dragging"));
  });

  // Context menu
  tbody.addEventListener("contextmenu", (e) => {
    const td = e.target.closest("td");
    if (!td) return;
    const i = Number(td.parentElement.dataset.row);
    selectRow(i);
    const items = [];
    const cols = td.dataset.col ? [td.dataset.col] : td.dataset.group ? groupById(td.dataset.group).columns : [];
    const fg = cols.length && FILL_OF[cols[0]];
    if (fg) {
      const { sub: s, group: g } = GROUP_OF_COL[cols[0]];
      const sub = s.fill_groups.length > 1 ? `${s.label} – ${g.label}` : s.label;
      items.push([`Fill "${sub}" group with identity values`, () => { fillIdentity(i, fg, true); refreshRowInputs(i); markChanged(); }]);
      items.push([`Clear "${sub}" group in this row`, () => { clearCols(i, fg); refreshRowInputs(i); markChanged(); }]);
      items.push([`Copy "${sub}" group to all rows`, () => {
        state.rows.forEach((r, k) => { if (k !== i) for (const c of fg) r[c] = state.rows[i][c]; });
        markChanged({ structure: true });
      }]);
      items.push(null);
    }
    items.push(["Insert row above", () => insertRow(i, newRow(state.rows[i - 1]))]);
    items.push(["Insert row below", () => insertRow(i + 1, newRow(state.rows[i]))]);
    items.push(["Duplicate row", () => duplicateRow(i)]);
    items.push(["Remove row", () => removeRow(i)]);
    showContextMenu(e, items);
  });
}

function showContextMenu(e, items) {
  e.preventDefault();
  const menu = $("#context-menu");
  menu.textContent = "";
  for (const it of items) {
    if (it === null) { menu.append(el("hr")); continue; }
    if (it[2]?.disabled) { menu.append(el("div", { text: it[0], class: "disabled" })); continue; }
    menu.append(el("div", { text: it[0], onclick: () => { menu.hidden = true; it[1](); } }));
  }
  menu.hidden = false;
  const w = menu.offsetWidth, h = menu.offsetHeight;
  menu.style.left = Math.min(e.clientX, window.innerWidth - w - 4) + "px";
  menu.style.top = Math.min(e.clientY, window.innerHeight - h - 4) + "px";
}
document.addEventListener("mousedown", (e) => {
  const menu = $("#context-menu");
  if (!menu.hidden && !menu.contains(e.target)) menu.hidden = true;
});

//
// ---------------------------------------------------------------- Validation
//
let issues = [];
const scheduleValidate = debounce(() => { validate(); applyValidationMarks(); }, 250);

function validate() {
  const out = [];
  const add = (row, col, msg, level = "err") => out.push({ row, col, msg, level });
  let prevEnd = 0;
  const triples = GROUPS.filter((g) => g.group.columns.length === 3 && g.group.columns.every(isInflection));

  state.rows.forEach((r, i) => {
    const v = (c) => (r[c] ?? "").trim();

    // Glosses
    if (v("maingloss") === "") add(i, "maingloss", "The main gloss is missing.");
    for (const c of GLOSS_COLS) {
      const g = v(c);
      if (g === "") continue;
      if (g === HOLD) {
        if (i === 0) add(i, c, `${HOLD} can not be used in the first row.`);
      } else if (g.split(":").length > 2) {
        add(i, c, `Invalid gloss '${g}'. Use NAME or class:NAME.`);
      } else if (glossState.loaded && !glossState.ids.has(g)) {
        add(i, c, `Sign '${g}' is not in the dictionary.`);
      }
    }

    // Timing
    if (state.relative) {
      const d = parseDuration(v("duration"));
      if (v("duration") === "") add(i, "duration", "The duration is missing.");
      else if (!d) add(i, "duration", "Duration must be seconds (e.g. 0.5) or a percentage (e.g. 100%).");
      else if (d.value <= 0) add(i, "duration", "Duration must be greater than zero.");
      else if (d.pct && v("maingloss") === HOLD) add(i, "duration", `A percentage duration can not be used with ${HOLD}. Use seconds.`);
      const t = parseNum(v("transition"));
      if (v("transition") === "") add(i, "transition", "The transition is missing.");
      else if (!isFinite(t)) add(i, "transition", "Transition must be a number of seconds.");
      else if (t < 0) add(i, "transition", "Transition can not be negative.");
    } else {
      const s = parseNum(v("framestart")), e = parseNum(v("frameend"));
      if (!isFinite(s)) add(i, "framestart", "Start must be a number of seconds.");
      if (!isFinite(e)) add(i, "frameend", "End must be a number of seconds.");
      if (isFinite(s) && isFinite(e)) {
        if (e <= s) add(i, "frameend", "End must be after the start.");
        if (s < prevEnd) add(i, "framestart", "The sign starts before the end of the previous one.", "warn");
        prevEnd = e;
      }
    }

    // Inflections: empty triples default to identity (or skip the inflection),
    // but the x/y/z of a triple must be all filled or all empty.
    for (const { sub, group } of triples) {
      const filled = group.columns.filter((c) => v(c) !== "");
      if (filled.length > 0 && filled.length < group.columns.length) {
        for (const c of group.columns) if (v(c) === "") add(i, c, `${sub.label} ${group.label}: x, y and z must be all filled (or all left empty).`);
      }
      for (const c of filled) if (!isFinite(parseNum(v(c)))) add(i, c, `'${v(c)}' is not a number.`);
    }
  });
  issues = out;
  return out;
}

function applyValidationMarks() {
  const tbody = $("#mms-table tbody");
  tbody.querySelectorAll("td.invalid, td.warning").forEach((td) => { td.classList.remove("invalid", "warning"); td.removeAttribute("title"); });
  for (const it of issues) {
    const tr = rowElement(it.row);
    if (!tr) continue;
    let td = tr.querySelector(`td[data-col="${it.col}"]`);
    if (!td && GROUP_OF_COL[it.col]) td = tr.querySelector(`td[data-group="${GROUP_OF_COL[it.col].group.id}"]`);
    if (!td) continue;
    td.classList.add(it.level === "err" ? "invalid" : "warning");
    td.title = td.title ? td.title + "\n" + it.msg : it.msg;
  }

  const box = $("#validation");
  box.textContent = "";
  // One message per row/message pair (groups produce one issue per column)
  const seen = new Set();
  for (const it of issues) {
    const k = it.row + "|" + it.msg;
    if (seen.has(k)) continue;
    seen.add(k);
    box.append(el("div", {
      class: "item " + it.level, text: `Row ${it.row + 1}, ${it.col}: ${it.msg}`,
      onclick: () => revealCell(it.row, it.col),
    }));
  }
  box.hidden = issues.length === 0;
}

function revealCell(i, col) {
  const g = GROUP_OF_COL[col];
  if (g && prefs.hiddenSubs.includes(g.sub.id)) {
    prefs.hiddenSubs = prefs.hiddenSubs.filter((s) => s !== g.sub.id);
    savePrefs();
    renderInflectionToggles();
    renderTable();
  }
  selectRow(i, { scroll: true });
  focusCell(i, col);
}

//
// ---------------------------------------------------------------- Sign browser
//
async function loadGlosses() {
  try {
    const data = await api("GET", "/api/glosses");
    glossState.list = data.glosses.map((g) => ({ ...g, idL: g.id.toLowerCase(), nameL: g.name.toLowerCase() }));
    glossState.ids = new Set(data.glosses.map((g) => g.id));
    glossState.loaded = true;
    renderCategoryOptions();
    filterSigns($("#sb-filter").value);
    validate();
    applyValidationMarks();
  } catch (e) {
    setStatus("Can not load the dictionary: " + e.message, true);
  }
}

function setGlossTarget(row, col) {
  glossState.target = { row, col };
  const t = $("#sb-target");
  t.textContent = "";
  t.append("Double click inserts into ", el("b", { text: `row ${row + 1}, ${col}` }));
}

function renderCategoryOptions() {
  const sel = $("#sb-category");
  const current = sel.value;
  const counts = {};
  for (const g of glossState.list) counts[g.cls] = (counts[g.cls] || 0) + 1;
  sel.textContent = "";
  sel.append(el("option", { value: "", text: `All categories (${glossState.list.length})` }));
  for (const cls of Object.keys(counts).sort()) sel.append(el("option", { value: cls, text: `${cls} (${counts[cls]})` }));
  sel.value = current in counts ? current : "";
}

function filterSigns(query, fromCell = false) {
  if (fromCell || document.activeElement !== $("#sb-filter")) $("#sb-filter").value = query;
  const q = query.trim().toLowerCase();
  const cat = $("#sb-category").value;
  const pool = cat ? glossState.list.filter((g) => g.cls === cat) : glossState.list;
  let res;
  if (q === "") {
    res = pool.map((g) => g.id);
  } else {
    const scored = [];
    for (const g of pool) {
      let s;
      if (g.idL === q || g.nameL === q) s = 0;
      else if (g.idL.startsWith(q) || g.nameL.startsWith(q)) s = 1;
      else if (g.idL.includes(q)) s = 2;
      else continue;
      scored.push([s, g.id]);
    }
    scored.sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]));
    res = scored.map((x) => x[1]);
  }
  if (!cat && (q === "" || HOLD.toLowerCase().includes(q))) res.unshift(HOLD);
  glossState.filtered = res;
  glossState.active = q !== "" && res.length > 0 ? 0 : -1;
  renderSignList();
}

const MAX_LIST = 400;

function renderSignList() {
  const ul = $("#sb-list");
  ul.textContent = "";
  const shown = glossState.filtered.slice(0, MAX_LIST);
  shown.forEach((id, k) => {
    const g = glossState.list.find((x) => x.id === id);
    const li = el("li", {
      dataset: { idx: k, id },
      class: [k === glossState.active ? "active" : "", id === glossState.chosen ? "chosen" : ""].join(" ").trim(),
      title: id === HOLD ? "Freeze the body in the last pose of the previous sign." : id,
    });
    li.append(el("span", { text: g ? g.name : id }));
    const meta = [];
    if (g && g.cls !== "signs") meta.push(g.cls);
    if (glossState.durations[id] !== undefined) meta.push(glossState.durations[id].toFixed(2) + "s");
    if (meta.length) li.append(el("span", { class: "cls", text: meta.join(" · ") }));
    ul.append(li);
  });
  if (glossState.filtered.length > MAX_LIST) {
    ul.append(el("li", { class: "more", text: `… ${glossState.filtered.length - MAX_LIST} more, keep typing to filter` }));
  }
  const n = glossState.list.length;
  $("#sb-count").textContent = glossState.filtered.length === n + 1 ? `(${n})` : `(${glossState.filtered.length} of ${n})`;
}

function setSignActive(k) {
  glossState.active = k;
  const ul = $("#sb-list");
  ul.querySelectorAll("li.active").forEach((li) => li.classList.remove("active"));
  const li = ul.querySelector(`li[data-idx="${k}"]`);
  if (li) { li.classList.add("active"); li.scrollIntoView({ block: "nearest" }); }
}

function moveSignActive(delta) {
  const n = Math.min(glossState.filtered.length, MAX_LIST);
  if (n === 0) return;
  setSignActive(Math.max(0, Math.min(n - 1, glossState.active + delta)));
  chooseSign(glossState.filtered[glossState.active]);
}

function chooseSign(id) {
  glossState.chosen = id;
  $("#sb-list").querySelectorAll("li.chosen").forEach((li) => li.classList.remove("chosen"));
  $("#sb-list").querySelector(`li[data-id="${CSS.escape(id)}"]`)?.classList.add("chosen");
  previewSign(id);
}

function insertSign(id) {
  const t = glossState.target;
  if (!t || t.row >= state.rows.length) {
    setStatus("Select a gloss cell (main gloss, dom. arm, non-dom. arm) first.", true);
    return;
  }
  state.rows[t.row][t.col] = id;
  const input = rowElement(t.row)?.querySelector(`input[data-col="${t.col}"]`);
  if (input) {
    input.value = id;
    input.focus();
  }
  glossState.typing = false;
  setSignActive(-1);
  selectRow(t.row);
  markChanged();
  scheduleDurations();
}

function setupSignBrowser() {
  const ul = $("#sb-list");
  ul.addEventListener("click", (e) => {
    const li = e.target.closest("li[data-id]");
    if (!li) return;
    setSignActive(Number(li.dataset.idx));
    chooseSign(li.dataset.id);
  });
  ul.addEventListener("dblclick", (e) => {
    const li = e.target.closest("li[data-id]");
    if (li) insertSign(li.dataset.id);
  });
  // Keep the focus in the edited cell when clicking the list
  ul.addEventListener("mousedown", (e) => { if (glossState.target) e.preventDefault(); });

  const filter = $("#sb-filter");
  filter.addEventListener("input", () => filterSigns(filter.value));
  $("#sb-category").addEventListener("change", () => filterSigns(filter.value));
  filter.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); moveSignActive(e.key === "ArrowDown" ? 1 : -1); }
    else if (e.key === "Enter" && glossState.active >= 0) { e.preventDefault(); insertSign(glossState.filtered[glossState.active]); }
  });
}

// ---- Previews (real-time 3D)
let previewToken = 0;
let previewJobId = null;

async function previewSign(id) {
  const token = ++previewToken;
  const v = await signViewer;
  $("#sb-preview-title").textContent = "Preview: " + id;
  if (previewJobId) {
    api("POST", `/api/jobs/${previewJobId}/cancel`).catch(() => {});
    previewJobId = null;
  }
  if (id === HOLD) {
    v.clear(`${escapeHtml(HOLD)} freezes the avatar in the last pose of the previous sign.`);
    return;
  }
  v.clear("Loading preview…");
  try {
    const r = await api("POST", "/api/glosses/preview", { id });
    let url = r.anim_url;
    if (r.status === "pending") {
      previewJobId = r.job.id;
      const job = await pollJob(r.job.id, (j) => {
        if (token !== previewToken) return;
        const pct = j.progress != null ? ` ${Math.round(j.progress * 100)}%` : "";
        v.setStatus(j.status === "queued" ? "Preview queued…" : `Computing preview…${pct}<br><small>${escapeHtml(j.phase)}</small>`);
      });
      if (previewJobId === r.job.id) previewJobId = null;
      if (token !== previewToken) return;
      if (job.status !== "done") throw new Error(job.error || job.status);
      url = job.result.anim_url;
    }
    const data = await api("GET", url);
    if (token !== previewToken) return;
    await v.load(data, id);
    if (token !== previewToken) return;
    v.play();
  } catch (e) {
    if (token === previewToken) v.clear("Preview failed:<br>" + escapeHtml(e.message));
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- Original durations of the signs (needed by the timeline for % durations)
const requestedDurations = new Set();
const scheduleDurations = debounce(fetchDurations, 700);

async function fetchDurations() {
  let ids = [...new Set(state.rows.map((r) => (r.maingloss ?? "").trim()))]
    .filter((id) => glossState.ids.has(id) && glossState.durations[id] === undefined && !requestedDurations.has(id));
  if (ids.length === 0) return;
  ids.forEach((id) => requestedDurations.add(id));
  try {
    for (let attempt = 0; attempt < 100 && ids.length; attempt++) {
      const r = await api("POST", "/api/glosses/durations", { ids });
      Object.assign(glossState.durations, r.durations);
      renderTimeline();
      if (!r.pending.length) break;
      if (r.job) await pollJob(r.job.id, () => {}); else await sleep(1500);
      ids = r.pending;
    }
    renderSignList();
  } catch (e) {
    ids.forEach((id) => requestedDurations.delete(id));
  }
}

//
// ---------------------------------------------------------------- Timeline
//
const TL_X0 = 74;
const TL_TRACKS = { main: 26, dom: 54, ndom: 74 };
let timelineItems = [];
const scheduleTimeline = debounce(renderTimeline, 150);

function computeTimeline() {
  const items = [];
  let t = 0;
  let estimated = false;
  state.rows.forEach((r, i) => {
    const gloss = (r.maingloss ?? "").trim();
    let tstart, start, end, est = false;
    if (state.relative) {
      const tr = parseNum(r.transition);
      tstart = t;
      start = t + (isFinite(tr) && tr > 0 ? tr : 0);
      const d = parseDuration(r.duration);
      let dur;
      if (!d || d.value <= 0) { dur = 0.5; est = true; }
      else if (d.pct) {
        const nominal = glossState.durations[gloss];
        if (nominal === undefined) { dur = d.value; est = true; } else dur = nominal * d.value;
      } else dur = d.value;
      end = start + Math.max(dur, 0.02);
    } else {
      const s = parseNum(r.framestart), e = parseNum(r.frameend);
      start = isFinite(s) ? s : t;
      end = isFinite(e) && e > start ? e : start + 0.02;
      tstart = Math.min(t, start);
    }
    t = end;
    estimated = estimated || est;
    items.push({ i, tstart, start, end, est, gloss, domarm: (r.domarm ?? "").trim(), ndomarm: (r.ndomarm ?? "").trim() });
  });
  return { items, total: t, estimated };
}

function renderTimeline() {
  const { items, total, estimated } = computeTimeline();
  timelineItems = items;
  const pps = Number(prefs.zoom);
  const tl = $("#timeline");
  tl.textContent = "";
  const width = TL_X0 + (Math.max(total, 1) + 1) * pps;
  tl.style.width = width + "px";
  const x = (s) => TL_X0 + s * pps;

  // Ruler
  const ruler = el("div", { class: "tl-ruler" });
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 30];
  const major = steps.find((s) => s * pps >= 60) || 30;
  const minor = major / 5;
  const end = Math.max(total, 1) + 1;
  for (let k = 0; k * minor <= end + 1e-9; k++) {
    const s = k * minor;
    const isMajor = k % 5 === 0;
    if (!isMajor && minor * pps < 8) continue;
    const tick = el("div", { class: "tl-tick" + (isMajor ? "" : " minor") });
    tick.style.left = x(s) + "px";
    if (isMajor) tick.textContent = (Math.round(s * 100) / 100) + "s";
    ruler.append(tick);
  }
  tl.append(ruler);

  for (const [name, label] of [["main", "Main"], ["dom", "Dom. arm"], ["ndom", "Non-dom."]]) {
    const lab = el("div", { class: "tl-track-label", text: label });
    lab.style.top = (TL_TRACKS[name] + 3) + "px";
    tl.append(lab);
  }

  tl.append(el("div", { class: "tl-band", id: "tl-band" }));

  for (const it of items) {
    const sel = it.i === state.selected ? " selected" : "";
    const title = `#${it.i + 1} ${it.gloss || "?"}\n${it.start.toFixed(2)} – ${it.end.toFixed(2)} s (${(it.end - it.start).toFixed(2)} s)` +
      (it.est ? "\nEstimated: the original duration of the sign is not known yet." : "");
    if (it.start > it.tstart) {
      const tr = el("div", { class: "tl-transition" + sel, dataset: { row: it.i } });
      Object.assign(tr.style, { left: x(it.tstart) + "px", width: (it.start - it.tstart) * pps + "px", top: (TL_TRACKS.main + 11) + "px" });
      tl.append(tr);
    }
    const block = (track, text, extra) => {
      const b = el("div", { class: `tl-block${extra}${sel}${it.est ? " estimated" : ""}${text === HOLD ? " hold" : ""}`, dataset: { row: it.i }, title, text });
      Object.assign(b.style, { left: x(it.start) + "px", width: Math.max(3, (it.end - it.start) * pps - 1) + "px", top: TL_TRACKS[track] + "px" });
      tl.append(b);
    };
    block("main", it.gloss || "?", "");
    if (it.domarm) block("dom", it.domarm, " arm");
    if (it.ndomarm) block("ndom", it.ndomarm, " arm");
  }

  tl.append(el("div", { class: "tl-playhead", id: "tl-playhead", hidden: true }));
  $("#tl-total").textContent = `Total ${estimated ? "≈ " : ""}${total.toFixed(2)} s`;
  $("#tl-note").textContent = estimated ? "Dashed: estimated duration (loading the original sign durations…)" : "";
  updateTimelineSelection(false);
}

function updateTimelineSelection(scroll = true) {
  const tl = $("#timeline");
  tl.querySelectorAll(".selected").forEach((b) => b.classList.remove("selected"));
  tl.querySelectorAll(`[data-row="${state.selected}"]`).forEach((b) => b.classList.add("selected"));
  const it = timelineItems[state.selected];
  const band = $("#tl-band");
  if (!it || !band) return;
  const pps = Number(prefs.zoom);
  band.style.left = (TL_X0 + it.start * pps) + "px";
  band.style.width = Math.max(2, (it.end - it.start) * pps) + "px";
  if (scroll) {
    const sc = $("#timeline-scroll");
    const left = TL_X0 + it.start * pps, right = TL_X0 + it.end * pps;
    if (left < sc.scrollLeft + TL_X0 || right > sc.scrollLeft + sc.clientWidth) sc.scrollLeft = Math.max(0, left - TL_X0 - 20);
  }
}

function setupTimeline() {
  $("#timeline").addEventListener("click", (e) => {
    const b = e.target.closest("[data-row]");
    if (!b) return;
    const row = Number(b.dataset.row);
    selectRow(row, { scroll: true, focus: true });
    seekToRow(row);
  });
  const zoom = $("#tl-zoom");
  zoom.value = prefs.zoom;
  zoom.addEventListener("input", () => { prefs.zoom = Number(zoom.value); savePrefs(); renderTimeline(); });

  // Playhead synchronized with the generated video, or with the 3D preview
  const video = $("#result-video");
  const tick = () => {
    if (prefs.view !== "video") return;
    showPlayhead(video.currentTime);
    if (!video.paused) requestAnimationFrame(tick);
  };
  video.addEventListener("play", () => requestAnimationFrame(tick));
  video.addEventListener("seeked", tick);
  viewer3d.then((v) => v.onTime((t) => { if (prefs.view === "3d") showPlayhead(t); }));
}

/** Move the 3D preview and the video to the start of the gloss of the given row (keeping their play/pause state). */
function seekToRow(row) {
  const it = timelineItems[row];
  if (!it) return;
  // The 3D animation knows the exact realized time of each row; the timeline time is an estimate.
  viewer3d.then((v) => {
    if (!v.hasAnimation) return;
    const t = v.glossStart(row);
    v.seek(t ?? it.start);
  });
  const video = $("#result-video");
  if (video.currentSrc) {
    const g = videoGlosses && videoGlosses.glosses.find((s) => s.index === row);
    const t = g ? (g.start - videoGlosses.frameStart) / videoGlosses.fps : it.start;
    video.currentTime = Math.min(t, video.duration || t);
    if (prefs.view === "video") showPlayhead(t);
  }
}

function showPlayhead(t) {
  const ph = $("#tl-playhead");
  if (!ph) return;
  ph.hidden = false;
  ph.style.left = (TL_X0 + t * Number(prefs.zoom)) + "px";
}

//
// ---------------------------------------------------------------- Documents
//
function setDocument(data, { name, loadedFrom, displayUnits = false }) {
  state.extraColumns = data.extra_columns || [];
  state.rows = (data.rows.length ? data.rows : [newRow(null)]).map((r) => Object.assign(emptyRow(), r));
  if (!displayUnits) {
    for (const r of state.rows) for (const c of ROUND1_COLS) r[c] = toDisplay(c, r[c]);
  }
  state.relative = data.relative !== undefined ? !!data.relative : true;
  state.name = name;
  state.loadedFrom = loadedFrom;
  state.selected = 0;
  state.dirty = false;

  // Show the inflection subsections that contain data
  for (const sub of INFLECTION_SUBS) {
    const cols = sub.groups.flatMap((g) => g.columns);
    if (state.rows.some((r) => cols.some((c) => (r[c] ?? "").trim() !== ""))) {
      prefs.hiddenSubs = prefs.hiddenSubs.filter((s) => s !== sub.id);
    }
  }
  savePrefs();
  renderAll();
  saveDraft();
  fetchDurations();
}

function renderAll() {
  $("#inp-name").value = state.name;
  $("#chk-relative").checked = state.relative;
  updateDirtyFlag();
  renderInflectionToggles();
  validate();
  renderTable();
  renderTimeline();
}

function showColumnsMenu() {
  const n = state.extraColumns.length;
  const r = $("#btn-columns-menu").getBoundingClientRect();
  showContextMenu({ preventDefault() {}, clientX: r.left, clientY: r.bottom + 2 }, [
    ["Expand x/y/z", () => { prefs.expanded = [...TRIPLET_IDS]; savePrefs(); renderTable(); }],
    ["Collapse x/y/z", () => { prefs.expanded = []; savePrefs(); renderTable(); }],
    null,
    n ? [`Remove unknown columns (${n})…`, dropUnknownColumns] : ["No unknown columns", null, { disabled: true }],
  ]);
}

// Old MMS files may contain columns that are no longer used, or that have been renamed.
function dropUnknownColumns() {
  const cols = state.extraColumns;
  if (!cols.length) return;
  const withData = cols.filter((c) => state.rows.some((r) => (r[c] ?? "").trim() !== ""));
  let msg = `Remove ${cols.length} column(s) not used by the MMS-Player?\n\n${cols.join(", ")}`;
  if (withData.length) msg += `\n\nThese contain values, which will be lost: ${withData.join(", ")}`;
  if (!confirm(msg)) return;
  for (const r of state.rows) for (const c of cols) delete r[c];
  state.extraColumns = [];
  markChanged({ structure: true });
  setStatus(`Removed ${cols.length} unknown column(s)`);
}

function confirmDiscard() {
  return !state.dirty || confirm("The current MMS has unsaved changes. Discard them?");
}

function newDocument() {
  if (!confirmDiscard()) return;
  state.extraColumns = [];
  setDocument({ rows: [newRow(null)], relative: true }, { name: "untitled" + MMS_SUFFIX, loadedFrom: null });
}

async function refreshProjects() {
  const sel = $("#sel-open");
  try {
    const data = await api("GET", "/api/projects");
    sel.textContent = "";
    sel.append(el("option", { value: "", text: "Open…" }));
    const og1 = el("optgroup", { label: `Project (${BOOT.project_dir})` });
    for (const p of data.projects) og1.append(el("option", { value: "p:" + p.name, text: p.name }));
    if (!data.projects.length) og1.append(el("option", { value: "", disabled: true, text: "(no MMS saved yet)" }));
    const og2 = el("optgroup", { label: "Examples (read-only)" });
    for (const p of data.examples) og2.append(el("option", { value: "e:" + p.name, text: p.name }));
    sel.append(og1, og2);
  } catch (e) {
    setStatus("Can not list the projects: " + e.message, true);
  }
}

async function openSelected() {
  const sel = $("#sel-open");
  const v = sel.value;
  sel.value = "";
  if (!v || !confirmDiscard()) return;
  const kind = v.slice(0, 2), name = v.slice(2);
  try {
    const url = kind === "p:" ? `/api/projects/${encodeURIComponent(name)}` : `/api/examples/${encodeURIComponent(name)}`;
    const data = await api("GET", url);
    setDocument(data, { name, loadedFrom: kind === "p:" ? name : null });
    setStatus(`Opened ${name}` + (kind === "e:" ? " (example: saving creates a copy in the project folder)" : ""));
  } catch (e) {
    setStatus(`Can not open ${name}: ${e.message}`, true);
  }
}

function normalizedName() {
  let n = $("#inp-name").value.trim() || "untitled";
  if (n.endsWith(".csv") && !n.endsWith(MMS_SUFFIX)) n = n.slice(0, -4);
  if (!n.endsWith(MMS_SUFFIX)) n += MMS_SUFFIX;
  return n;
}

function exportRows() {
  const cols = [...KNOWN_COLS, ...state.extraColumns];
  return state.rows.map((r) => Object.fromEntries(cols.map((c) => [c, toFile(c, (r[c] ?? "").trim())])));
}

async function saveDocument() {
  const name = normalizedName();
  const body = { rows: exportRows(), extra_columns: state.extraColumns, overwrite: state.loadedFrom === name };
  try {
    let r;
    try {
      r = await api("PUT", `/api/projects/${encodeURIComponent(name)}`, body);
    } catch (e) {
      if (e.status !== 409) throw e;
      if (!confirm(`'${name}' already exists in the project folder. Overwrite it?`)) return;
      r = await api("PUT", `/api/projects/${encodeURIComponent(name)}`, { ...body, overwrite: true });
    }
    state.name = r.name;
    state.loadedFrom = r.name;
    state.dirty = false;
    $("#inp-name").value = r.name;
    updateDirtyFlag();
    saveDraft();
    refreshProjects();
    const errs = validate().filter((x) => x.level === "err").length;
    setStatus(`Saved ${r.name}` + (errs ? ` (with ${errs} problem(s) to fix before generating)` : ""));
  } catch (e) {
    setStatus("Save failed: " + e.message, true);
  }
}

/** Deletes the file of the current MMS from the project folder. The content stays in the editor, as unsaved. */
async function deleteDocument() {
  const name = state.loadedFrom;
  if (!name) return;
  if (!confirm(`Delete '${name}' from the project folder?\n\nThis can not be undone. The content stays in the editor until you close or replace it.`)) return;
  try {
    await api("DELETE", `/api/projects/${encodeURIComponent(name)}`);
    state.loadedFrom = null;
    state.dirty = true;
    updateDirtyFlag();
    saveDraft();
    refreshProjects();
    setStatus(`Deleted ${name}`);
  } catch (e) {
    setStatus(`Can not delete ${name}: ${e.message}`, true);
  }
}

async function downloadDocument() {
  try {
    const res = await fetch("/api/mms/serialize", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: exportRows(), extra_columns: state.extraColumns }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const a = el("a", { href: URL.createObjectURL(blob), download: normalizedName() });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  } catch (e) {
    setStatus("Download failed: " + e.message, true);
  }
}

async function importDocument(file) {
  if (!file || !confirmDiscard()) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/mms/parse", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    let name = file.name.endsWith(MMS_SUFFIX) ? file.name : file.name.replace(/\.csv$/i, "") + MMS_SUFFIX;
    setDocument(data, { name, loadedFrom: null });
    state.dirty = true;
    updateDirtyFlag();
    setStatus(`Imported ${file.name}. Save it to store it in the project folder.`);
  } catch (e) {
    setStatus("Import failed: " + e.message, true);
  }
}

//
// ---------------------------------------------------------------- Generation
//
let currentJobId = null;

function showProgress(job) {
  const box = $("#progress");
  box.hidden = false;
  const bar = box.querySelector(".progress-bar");
  const fill = box.querySelector(".progress-fill");
  box.classList.toggle("error", job.status === "error");
  bar.classList.toggle("error", job.status === "error");
  bar.classList.toggle("indeterminate", job.progress == null && !["error", "cancelled", "done"].includes(job.status));
  fill.style.width = Math.round((job.progress || 0) * 100) + "%";
  let phase = job.phase;
  if (job.status === "queued") phase = "Waiting for other jobs to finish…";
  else if (job.status === "error") phase = "Failed: " + (job.error || "unknown error");
  else if (job.status === "running" && job.progress != null) phase = `${phase} — ${Math.round(job.progress * 100)}%`;
  $("#progress-phase").textContent = phase;
  $("#progress-time").textContent = job.elapsed ? `${Math.round(job.elapsed)} s` : "";
  if (job.log) {
    const pre = $("#job-log");
    const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20;
    pre.textContent = job.log.slice(-300).join("\n");
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  }
}

// The 3D viewers are created by an ES module (viewer3d.js), loaded after this script.
const viewers3d = new Promise((resolve) => {
  if (window.MMSViewers) resolve(window.MMSViewers);
  else window.addEventListener("mmsviewer3d-ready", () => resolve(window.MMSViewers), { once: true });
});
const viewer3d = viewers3d.then((v) => v.main);      // full sentences (right panel)
const signViewer = viewers3d.then((v) => v.sign);    // single signs (sign browser)

function generationBody() {
  return {
    name: normalizedName(), rows: exportRows(), extra_columns: state.extraColumns, relative: state.relative,
    options: { render_size_pct: Number($("#opt-size").value), gloss_panel: $("#opt-panel").checked },
  };
}

/** Submit a generation job (video or 3D preview) and follow its progress. Returns the finished job or null. */
async function runGenerationJob(url, what) {
  const problems = validate();
  applyValidationMarks();
  const errs = problems.filter((p) => p.level === "err");
  if (errs.length && !confirm(`The MMS has ${errs.length} problem(s) (see the list below the table). The ${what} will probably fail.\n\nContinue anyway?`)) return null;

  const buttons = [$("#btn-generate"), $("#btn-preview3d")];
  buttons.forEach((b) => { b.disabled = true; });
  $("#btn-cancel").hidden = false;
  $("#job-log").textContent = "";
  try {
    const r = await api("POST", url, generationBody());
    currentJobId = r.job.id;
    showProgress(r.job);
    const job = await pollJob(r.job.id, showProgress, () => $("#log-details").open);
    if (job.status === "done") return job;
    if (job.status === "error") {
      const full = await api("GET", `/api/jobs/${job.id}?log=1`);
      showProgress(full);
      $("#log-details").open = true;
      setStatus(`The ${what} failed: ` + (job.error || ""), true);
    } else {
      setStatus(`The ${what} was cancelled.`);
    }
  } catch (e) {
    setStatus(`The ${what} failed: ` + e.message, true);
  } finally {
    currentJobId = null;
    buttons.forEach((b) => { b.disabled = false; });
    $("#btn-cancel").hidden = true;
  }
  return null;
}

async function generate() {
  const job = await runGenerationJob("/api/generate", "video rendering");
  if (!job) return;
  showVideo(job.result.url, job.result.name, job.result.anim_url);
  setStatus(`Video generated in ${Math.round(job.elapsed)} s.`);
  refreshRenders();
}

async function preview3d() {
  const job = await runGenerationJob("/api/preview3d", "3D preview");
  if (!job) return;
  if (await show3D(job.result.anim_url, normalizedName() + " (preview)")) {
    setStatus(`3D preview computed in ${Math.round(job.elapsed)} s.`);
  }
}

/** Load the animation data into the 3D viewer, switch to its tab, and play it. */
async function show3D(animUrl, label) {
  try {
    const [v, data] = await Promise.all([viewer3d, api("GET", animUrl)]);
    setView("3d");
    await v.load(data, label);
    v.play();
    return true;
  } catch (e) {
    setStatus("Can not show the 3D animation: " + e.message, true);
    return false;
  }
}

function setView(name) {
  prefs.view = name === "video" ? "video" : "3d";
  savePrefs();
  document.querySelectorAll(".view-tab").forEach((b) => b.classList.toggle("active", b.dataset.view === prefs.view));
  document.querySelectorAll(".view-pane").forEach((p) => { p.hidden = p.dataset.view !== prefs.view; });
  if (prefs.view !== "video") $("#result-video").pause();
  viewer3d.then((v) => v.setActive(prefs.view === "3d"));
}

// Realized time ranges of the glosses of the shown video (from its animation data), for exact seeking.
let videoGlosses = null;

function showVideo(url, name, animUrl) {
  setView("video");
  const v = $("#result-video");
  v.src = url;
  videoGlosses = null;
  if (animUrl) {
    api("GET", animUrl).then((d) => {
      if (v.src.endsWith(url)) videoGlosses = { fps: d.fps, frameStart: d.frame_start, glosses: d.glosses || [] };
    }).catch(() => {});
  }
  $("#video-placeholder").classList.add("hidden");
  v.play().catch(() => {});
  const cap = $("#video-caption");
  cap.textContent = "";
  if (name) cap.append(name + " — ", el("a", { href: url, download: name, text: "download" }));
  if (name && animUrl) {
    cap.append(" — ", el("a", {
      href: "#", text: "view in 3D", title: "Play the animation of this video on the 3D character",
      onclick: (e) => { e.preventDefault(); show3D(animUrl, name); },
    }));
  }
  document.querySelectorAll("#render-list li").forEach((li) => li.classList.toggle("current", li.dataset.name === name));
}

async function refreshRenders() {
  try {
    const data = await api("GET", "/api/renders");
    const ul = $("#render-list");
    ul.textContent = "";
    for (const r of data.renders) {
      const when = new Date(r.modified * 1000).toLocaleString();
      const li = el("li", { dataset: { name: r.name }, title: when, onclick: () => showVideo(r.url, r.name, r.anim_url) });
      li.append(el("span", { class: "name", text: r.name }));
      if (r.anim_url) {
        li.append(el("a", {
          href: "#", text: "3D", title: "Play the animation of this video on the 3D character",
          onclick: (e) => { e.preventDefault(); e.stopPropagation(); show3D(r.anim_url, r.name); },
        }));
      }
      if (r.mms) {
        li.append(el("a", {
          href: "#", text: "load MMS", title: "Load the MMS used for this video into the editor",
          onclick: async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!confirmDiscard()) return;
            try {
              const data = await api("GET", `/api/renders/${encodeURIComponent(r.mms)}/mms`);
              const name = r.mms.replace(/-\d{8}-\d{6}\.mms\.csv$/, MMS_SUFFIX);
              setDocument(data, { name, loadedFrom: null });
              showVideo(r.url, r.name, r.anim_url);
            } catch (err) {
              setStatus("Can not load the MMS: " + err.message, true);
            }
          },
        }));
      }
      ul.append(li);
    }
    if (!data.renders.length) ul.append(el("li", { class: "muted", text: "No renders yet." }));
  } catch (e) {
    setStatus("Can not list the renders: " + e.message, true);
  }
}

//
// ---------------------------------------------------------------- Toolbar & layout
//
function renderInflectionToggles() {
  const box = $("#inflection-toggles");
  box.querySelectorAll("label").forEach((l) => l.remove());
  for (const sub of INFLECTION_SUBS) {
    const cb = el("input", { type: "checkbox", checked: !prefs.hiddenSubs.includes(sub.id) });
    cb.addEventListener("change", () => {
      prefs.hiddenSubs = cb.checked ? prefs.hiddenSubs.filter((s) => s !== sub.id) : [...prefs.hiddenSubs, sub.id];
      savePrefs();
      renderTable();
    });
    box.append(el("label", { title: `Show/hide the ${sub.label} inflection columns` }, cb, sub.label));
  }
}

function setupToolbar() {
  $("#btn-new").addEventListener("click", newDocument);
  $("#sel-open").addEventListener("change", openSelected);
  $("#btn-save").addEventListener("click", saveDocument);
  $("#btn-download").addEventListener("click", downloadDocument);
  $("#btn-delete").addEventListener("click", deleteDocument);
  $("#inp-import").addEventListener("change", (e) => { importDocument(e.target.files[0]); e.target.value = ""; });
  $("#inp-name").addEventListener("change", () => {
    state.name = normalizedName();
    $("#inp-name").value = state.name;
    updateDirtyFlag();
    saveDraft();
  });

  $("#btn-add-row").addEventListener("click", addRow);
  $("#btn-dup-row").addEventListener("click", () => duplicateRow());
  $("#btn-del-row").addEventListener("click", () => removeRow());
  $("#btn-up-row").addEventListener("click", () => moveRowTo(state.selected, state.selected - 1));
  $("#btn-down-row").addEventListener("click", () => moveRowTo(state.selected, state.selected + 1));

  $("#chk-relative").addEventListener("change", (e) => {
    state.relative = e.target.checked;
    saveDraft();
    validate();
    renderTable();
    renderTimeline();
  });
  // Clicking the button while its menu is open closes the menu (the document mousedown handler hides it)
  let columnsMenuWasOpen = false;
  $("#btn-columns-menu").addEventListener("mousedown", () => { columnsMenuWasOpen = !$("#context-menu").hidden; });
  $("#btn-columns-menu").addEventListener("click", () => { if (!columnsMenuWasOpen) showColumnsMenu(); });

  $("#btn-generate").addEventListener("click", generate);
  $("#btn-preview3d").addEventListener("click", preview3d);
  document.querySelectorAll(".view-tab").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  $("#btn-cancel").addEventListener("click", () => {
    if (currentJobId) api("POST", `/api/jobs/${currentJobId}/cancel`).catch(() => {});
  });
  const size = $("#opt-size");
  size.value = prefs.size;
  if (size.selectedIndex < 0) size.value = "50";   // stored size no longer offered
  size.addEventListener("change", () => { prefs.size = size.value; savePrefs(); });
  const panel = $("#opt-panel");
  panel.checked = !!prefs.panel;
  panel.addEventListener("change", () => { prefs.panel = panel.checked; savePrefs(); });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveDocument(); }
  });
  window.addEventListener("beforeunload", (e) => { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });

  // Splitters around the editor: sign browser | editor | video. The editor keeps at least MIN_EDITOR_W.
  const root = document.documentElement;
  const MIN_EDITOR_W = 170;
  const leftSpace = () => (prefs.signsHidden ? 0 : prefs.leftW + 6);
  const applyWidths = () => {
    root.style.setProperty("--left-w", prefs.leftW + "px");
    root.style.setProperty("--right-w", prefs.rightW + "px");
  };
  const dragSplitter = (splitter, onMove) => splitter.addEventListener("mousedown", (e) => {
    e.preventDefault();
    splitter.classList.add("dragging");
    const move = (ev) => { onMove(ev.clientX); applyWidths(); };
    const up = () => {
      splitter.classList.remove("dragging");
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      savePrefs();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
  dragSplitter($("#splitter"), (x) => {
    prefs.rightW = Math.max(260, Math.min(window.innerWidth - leftSpace() - MIN_EDITOR_W, window.innerWidth - x - 3));
  });
  dragSplitter($("#splitter-left"), (x) => {
    prefs.leftW = Math.max(180, Math.min(window.innerWidth - prefs.rightW - 6 - MIN_EDITOR_W, x - 3));
  });
  applyWidths();

  // Show/hide the sign browser
  const toggleSigns = $("#btn-toggle-signs");
  const applySignsHidden = () => {
    const hidden = prefs.signsHidden;
    $("#layout").classList.toggle("signs-hidden", hidden);
    toggleSigns.setAttribute("aria-expanded", String(!hidden));
    toggleSigns.title = hidden ? "Show the sign browser" : "Hide the sign browser";
    toggleSigns.querySelector(".label").textContent = hidden ? "Signs ›" : "‹ Hide";
    signViewer.then((v) => v.setActive(!prefs.signsHidden));
  };
  toggleSigns.addEventListener("click", () => {
    prefs.signsHidden = !prefs.signsHidden;
    savePrefs();
    applySignsHidden();
  });
  applySignsHidden();
}

//
// ---------------------------------------------------------------- Boot
//
function boot() {
  setupToolbar();
  setupTableEvents();
  setupSignBrowser();
  setupTimeline();
  setView(prefs.view);

  const draft = readStorage(DRAFT_KEY);
  if (draft.rows && draft.rows.length) {
    setDocument({ rows: draft.rows, extra_columns: draft.extraColumns, relative: draft.relative },
      { name: draft.name || "untitled" + MMS_SUFFIX, loadedFrom: draft.loadedFrom || null, displayUnits: draft.units === "deg" });
    state.dirty = !!draft.dirty;
    updateDirtyFlag();
  } else {
    setDocument({ rows: [newRow(null)], relative: true }, { name: "untitled" + MMS_SUFFIX, loadedFrom: null });
  }

  loadGlosses().then(fetchDurations);
  refreshProjects();
  refreshRenders();
}

boot();

})();
