"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  let api = null;
  const st = {
    call: "JL1FVA", prefix: "JP", spots: new Map(), qsos: new Map(), lastAt: 0, lastQ: 0,
    start: null, timer: null, poll: null, source: "app", adif: "", out: "", outDir: "",
    acts: [], selected: new Set(), listeners: [], receiver: {}, editing: null, bar: false, cheered: false,
    lang: "ja", langs: [], termsAccepted: "",
  };
  const TERMS_VERSION = "2026-10-20";

  // ---------- i18n ----------
  let L = {};
  const t = (k, p) => String(L[k] != null ? L[k] : k).replace(/\{(\w+)\}/g, (_, n) => (p && p[n] != null ? p[n] : ""));
  function pickLang(tag) {
    const codes = st.langs.map(([c]) => c);
    const low = String(tag || "").replace("_", "-").toLowerCase();
    const exact = codes.find((c) => c.toLowerCase() === low); if (exact) return exact;
    if (low.startsWith("zh")) return /hant|tw|hk|mo/.test(low) ? "zh-TW" : "zh-CN";
    if (low.startsWith("pt")) return "pt-BR";
    return codes.find((c) => c.split("-")[0] === low.split("-")[0]) || "en";
  }
  async function loadLang(lang) {
    try { L = await (await fetch(`i18n/${lang}.json`, { cache: "no-store" })).json(); } catch (e) { L = {}; }
    st.lang = lang; document.documentElement.lang = lang;
    $$("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
    $$("[data-i18n-ph]").forEach((el) => (el.placeholder = t(el.dataset.i18nPh)));
    $$("[data-i18n-html]").forEach((el) => (el.innerHTML = t(el.dataset.i18nHtml)));   // our own dictionaries only
    $$("[data-i18n-title]").forEach((el) => (el.title = t(el.dataset.i18nTitle)));
    $("#termsBody").innerHTML = t("terms.body");
    $("#lang").value = lang;
  }
  function rerender() {           // dynamic parts that hold translated text
    renderListeners(); updateReceiver(st.receiver); renderCalls();
    if (!$("#liveRun").hidden) { renderQsos(); renderSpots(); }
    if (!$("#view-spots").hidden) { spotsOptions(); renderSpotsPage(); }
    if (st.source) renderActs({ items: st.acts, path: st.adif }, st.source === "adif" && !st.adif);
  }

  // ---------- helpers ----------
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const PARK = /^[A-Z0-9]{1,4}-\d{4,5}$/;
  const splitParks = (v) => [...new Set(String(v || "").toUpperCase().split(/[,\s;]+/).filter((p) => PARK.test(p)))];
  const baseCall = (c) => {
    const parts = String(c || "").toUpperCase().split("/").filter((p) => /\d/.test(p) && /[A-Z]/.test(p) && p.length >= 3);
    return parts.length ? parts.sort((a, b) => b.length - a.length)[0] : String(c || "").toUpperCase();
  };
  function plate(ref) {
    const i = ref.indexOf("-");
    return `<span class="plate" data-ref="${esc(ref)}"><b>${esc(ref.slice(0, i + 1))}</b>${esc(ref.slice(i + 1))}</span>`;
  }
  const plates = (refs) => (refs || []).map(plate).join('<span class="plate-join" aria-hidden="true">+</span>');
  // Country = the park prefix (ISO 3166 alpha-2, sent by Python): flag from regional indicators, name in the UI language.
  const flagOf = (cc) => /^[A-Z]{2}$/.test(cc) ? String.fromCodePoint(...[...cc].map((c) => 0x1F1E6 + c.charCodeAt(0) - 65)) : "";
  const countryName = (cc) => { try { return new Intl.DisplayNames([st.lang], { type: "region" }).of(cc) || cc; } catch (e) { return cc; } };
  const fmtDate = (d) => {
    try {
      return new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8)))
        .toLocaleDateString(st.lang, { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
    } catch (e) { return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`; }
  };
  const hhmm = (tm) => `${esc(String(tm).slice(0, 2))}:${esc(String(tm).slice(2, 4))}`;
  const mins = (tm) => +String(tm).slice(0, 2) * 60 + +String(tm).slice(2, 4);
  function fmtFreq(khz) {
    const k = parseFloat(khz);
    return k ? `${(k / 1000).toFixed(3)}<small>MHz</small>` : esc(khz || "");
  }
  function toast(msg) {
    const el = $("#toast"); el.textContent = msg; el.hidden = false;
    clearTimeout(toast.h); toast.h = setTimeout(() => (el.hidden = true), 2800);
  }
  const utcMs = (iso) => Date.parse(iso.length === 16 ? iso + ":00Z" : iso + "Z");
  function segSet(group, attr, val) {
    $$(group + " button").forEach((x) => { const on = x.dataset[attr] === val; x.classList.toggle("is-on", on); x.setAttribute("aria-checked", on); });
  }

  // ---------- navigation ----------
  function show(view) {
    $$(".nav-item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === view));
    ["live", "spots", "build", "config"].forEach((v) => ($("#view-" + v).hidden = v !== view));
    $(".main").scrollTo(0, 0);
    if (view === "build" && st.source === "app") loadActs();
    if (view === "config") api.poll_live(1e12, 1e12).then((r) => updateReceiver(r.receiver));
    if (view === "spots") loadSpotsPage();
  }
  $$(".nav-item").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

  // ================================================================ live
  // Under the park input: the plate(s) plus the park name from pota.app (fetched after a pause in typing).
  // One input per park: the first next to the start button, more below with 「公園を追加」.
  // A pasted "JP-1266,JP-1206" is split into rows.
  const parkInputs = () => [$("#parks"), ...$$("#parkExtra input")];
  const parkValue = () => parkInputs().map((i) => i.value).join(",");
  function addParkRow(value) {
    const row = document.createElement("div"); row.className = "park-row";
    row.innerHTML = `<input placeholder="JP-1206" spellcheck="false" autocomplete="off"><button class="link" type="button">${esc(t("ed.delete"))}</button>`;
    const inp = row.querySelector("input"); inp.value = value || "";
    inp.addEventListener("input", onParkInput);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") startLive(); });
    row.querySelector("button").addEventListener("click", () => { row.remove(); renderPreview(); });
    $("#parkExtra").appendChild(row);
    return inp;
  }
  function setParks(value) {
    const parks = splitParks(value);
    $("#parkExtra").innerHTML = "";
    $("#parks").value = parks[0] || String(value || "").split(/[,\s;]+/)[0] || "";
    parks.slice(1).forEach((p) => addParkRow(p));
    renderPreview();
  }
  function onParkInput(e) {
    if (/[,;\s]/.test(e.target.value.trim())) { setParks(parkValue()); return; }   // pasted a list
    renderPreview();
  }
  $("#parkAdd").addEventListener("click", () => addParkRow("").focus());
  function renderPreview() {
    const parks = splitParks(parkValue());
    $("#parksPreview").innerHTML = parks.map((p) => `${plate(p)}<span class="park-name" data-ref="${esc(p)}"></span>`).join("");
    clearTimeout(renderPreview.h);
    if (parks.length) renderPreview.h = setTimeout(async () => {
      try {
        const info = await api.park_info(parks.join(","));
        $$("#parksPreview .park-name").forEach((el) => { const i = info[el.dataset.ref] || {}; el.textContent = i.local || i.name || ""; });
        renderLoc(await api.park_locations(parks.join(",")));
      } catch (e) { /* optional */ }
    }, 500);
    if (!parks.length) renderLoc(null);
  }
  // Where I stand: the prefecture/state the parks have in common - fixed when there is one, a choice
  // when a park spans several (JP-0016 = Kanagawa, Shizuoka, Tokyo, Yamanashi). Python computes it.
  function renderLoc(r) {
    const box = $("#parkLoc"); st.locOptions = r ? r.options : [];
    const warn = $("#parkApart");
    warn.hidden = !(r && r.apart && r.apart.length);
    if (!warn.hidden) warn.textContent = r.apart.map(([a, b]) => t("live.warn.apart", { a, b })).join(" ");
    if (!r || (!r.options.length && !r.multi.length)) { box.hidden = true; st.loc = ""; return; }
    box.hidden = false;
    const label = (o) => `${esc(o.code)}${o.name ? " " + esc(o.name) : ""}`;
    if (!r.options.length) { box.innerHTML = `<span class="loc-label">${esc(t("live.loc"))}</span><span class="error">${esc(t("live.err.noLoc"))}</span>`; st.loc = ""; return; }
    if (r.options.length === 1) {
      st.loc = r.options[0].code;
      box.innerHTML = `<span class="loc-label">${esc(t("live.loc"))}</span><span class="loc-fixed">${label(r.options[0])}</span>`;
      return;
    }
    if (!r.options.some((o) => o.code === st.loc)) st.loc = "";
    box.innerHTML = `<span class="loc-label">${esc(t("live.loc"))}</span><select id="locSel"><option value="">${esc(t("live.loc.pick"))}</option>` +
      r.options.map((o) => `<option value="${esc(o.code)}"${o.code === st.loc ? " selected" : ""}>${label(o)}</option>`).join("") + `</select>`;
    $("#locSel").addEventListener("change", (e) => (st.loc = e.target.value));
  }
  $("#parks").addEventListener("input", onParkInput);
  $("#parks").addEventListener("keydown", (e) => { if (e.key === "Enter") startLive(); });

  async function startLive() {
    const parks = splitParks(parkValue());
    const err = $("#liveError");
    if (!parks.length) { err.textContent = t("live.err.park"); err.hidden = false; return; }
    if ((st.locOptions || []).length > 1 && !st.loc) { err.textContent = t("live.err.loc"); err.hidden = false; return; }
    err.hidden = true; $("#doneCard").hidden = true;
    const r = await api.start_live(parks.join(","), st.call, st.loc || "");
    if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
    enterRunning(r.parks, r.start);
  }
  $("#startLive").addEventListener("click", startLive);

  const refHtml = (p) => { const i = p.indexOf("-"); return `<span class="ref"><b>${esc(p.slice(0, i + 1))}</b>${esc(p.slice(i + 1))}</span>`; };
  async function enterRunning(parks, start) {
    st.spots.clear(); st.qsos.clear(); st.lastAt = 0; st.start = utcMs(start); st.cheered = false; st.parks = parks; st.seq = 0;
    $("#liveIdle").hidden = true; $("#liveRun").hidden = false; $("#liveDot").hidden = false;
    $("#signParks").innerHTML = parks.map((p) =>
      `<div class="sign-park">${refHtml(p)}<span class="name" data-ref="${esc(p)}"></span></div>`).join("");
    $("#barParks").innerHTML = parks.map(refHtml).join('<span class="plate-join" aria-hidden="true">+</span>');
    $("#liveStatus").textContent = t("live.status.first");
    for (const q of await api.session_qsos(start, parks.join(","))) { q.seq = ++st.seq; st.qsos.set(q.uid, q); }
    st.lastQ = Date.now() / 1000 - 1;
    st.cheered = st.qsos.size >= 10;            // re-opened mid-activation: don't celebrate twice
    renderSpots(); renderQsos();
    tick(); clearInterval(st.timer); st.timer = setInterval(tick, 1000);
    poll(); clearInterval(st.poll); st.poll = setInterval(poll, 2500);
    setBar(true);
    try {
      const info = await api.park_info(parks.join(","));
      $$("#signParks .name").forEach((el) => { const i = info[el.dataset.ref] || {}; el.textContent = i.local || i.name || ""; });
    } catch (e) { /* optional */ }
  }
  function tick() {
    const s = Math.max(0, Math.floor((Date.now() - st.start) / 1000));
    const p = (n) => String(n).padStart(2, "0");
    const tm = `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
    $("#elapsed").textContent = tm; $("#barElapsed").textContent = tm;
  }
  async function poll() {
    const r = await api.poll_live(st.lastAt, st.lastQ);
    if (r.status) $("#liveStatus").textContent = r.status;
    updateReceiver(r.receiver);
    const freshS = new Set(), freshQ = new Set();
    for (const e of r.events) { st.lastAt = Math.max(st.lastAt, e.at); st.spots.set(e.call, e); freshS.add(e.call); }
    for (const q of r.qsos) {
      st.lastQ = Math.max(st.lastQ, q.at);
      if (q.action === "delete") {
        for (const [k, v] of st.qsos) if (baseCall(v.call) === baseCall(q.call) && v.date === q.date &&
          Math.abs(+v.time - +q.time) <= 3) st.qsos.delete(k);
        toast(t("live.deleted", { call: q.call }));
        continue;
      }
      // keep today's QSOs at these parks (a shared park counts for the whole day) and anything since the start
      const atMine = (q.my || []).some((p) => (st.parks || []).includes(p));
      if (!atMine && q.date && st.start && Date.parse(`${q.date.slice(0, 4)}-${q.date.slice(4, 6)}-${q.date.slice(6, 8)}T${q.time.slice(0, 2)}:${q.time.slice(2, 4)}:00Z`) < st.start - 300000) continue;
      // WSJT-X logs the start time, the logger the end time: show the same contact once
      for (const [k, v] of st.qsos) {
        if (k !== q.uid && v.date === q.date && v.band === q.band && baseCall(v.call) === baseCall(q.call) && Math.abs(mins(v.time) - mins(q.time)) <= 3) {
          if (!q.decision && v.decision) Object.assign(q, { decision: v.decision, parks: v.parks });
          st.qsos.delete(k);
        }
      }
      q.seq = (st.qsos.get(q.uid) || {}).seq || ++st.seq;   // arrival order breaks ties in the sort
      st.qsos.set(q.uid, q); freshQ.add(q.uid);
    }
    if (freshS.size || freshQ.size) { renderSpots(freshS); renderQsos(freshQ); }
  }
  function workedCalls() { return new Set([...st.qsos.values()].map((q) => baseCall(q.call))); }
  function spotRow(e, worked, fresh, page) {
    return `
      <li class="spot${e.twofer ? " is-twofer" : ""}${worked ? " is-worked" : ""}${fresh ? " is-new" : ""}${page && e.ago >= 30 ? " is-stale" : ""}">
        <span class="spot-time">${esc(e.time)}Z</span>
        <span class="spot-call">${esc(e.call)}${worked ? `<span class="worked-tag">${t("spots.worked")}</span>` : ""}</span>
        <span class="plates">${e.country ? `<span class="flag" title="${esc(countryName(e.country))}">${flagOf(e.country)}</span>` : ""}${plates(e.parks)}${e.twofer ? `<span class="twofer-tag">${e.parks.length}fer</span>` : ""}</span>
        <span class="spot-meta"><span class="spot-freq">${fmtFreq(e.freq)}</span>${e.mode ? `<span class="spot-mode">${esc(e.mode)}</span>` : ""}</span>
        ${page ? `<span class="spot-ago">${e.ago ? t("spots.ago", { n: e.ago }) : t("spots.now")}</span>
        <span class="spot-note" title="${esc(e.comments)}">${esc(e.comments)}</span>` : ""}
      </li>`;
  }
  function renderSpots(fresh) {
    const worked = workedCalls();
    const list = [...st.spots.values()].filter((e) => !st.prefix || e.parks.some((p) => p.startsWith(st.prefix)))
      .sort((a, b) => b.at - a.at);
    $("#spots").innerHTML = list.map((e) => spotRow(e, worked.has(baseCall(e.call)), fresh && fresh.has(e.call), false)).join("");
    $("#spotsEmpty").hidden = list.length > 0; $("#spots").hidden = list.length === 0;
    const tw = list.filter((e) => e.twofer).length;
    $("#liveCount").textContent = list.length ? t("live.count", { n: list.length }) + (tw ? t("live.count2fer", { n: tw }) : "") : "";
  }

  // One QSO row. The P2P part is a small state machine:
  //   candidate from spots, no answer yet  -> ask: yes / no / type it
  //   no candidate, no answer              -> an input for the park number (Phone/CW: the other side tells you)
  //   yes / manual / typed in the logger   -> P2P plates + change
  //   no                                   -> "not P2P" + change
  function qsoRow(q, fresh) {
    const decided = q.decision && q.decision !== "no";
    const p2p = decided && q.parks.length;
    const editing = st.editing === q.uid;
    const input = `<span class="p2p-in"><input data-in="${esc(q.uid)}" placeholder="${esc(t("row.ph"))}" spellcheck="false" autocomplete="off"
        value="${esc(editing ? (q.parks || []).join(",") : "")}"><button class="chip chip-yes" data-act="manual" data-uid="${esc(q.uid)}">${t("row.record")}</button>
        ${q.candidate.length || decided || q.decision === "no" ? `<button class="link" data-act="cancel" data-uid="${esc(q.uid)}">${t("row.cancel")}</button>` : ""}</span>`;
    let ctl;
    if (editing) ctl = input;
    else if (p2p) ctl = `<span class="p2p-tag">P2P</span><span class="plates">${plates(q.parks)}</span><button class="link" data-act="edit" data-uid="${esc(q.uid)}">${t("row.change")}</button>`;
    else if (q.decision === "no") ctl = `<span class="qso-none">${t("row.none")}</span><button class="link" data-act="edit" data-uid="${esc(q.uid)}">${t("row.change")}</button>`;
    else if (q.candidate.length) ctl = `<span class="ask-text">${t("row.ask")}</span><span class="plates">${plates(q.candidate)}</span>${q.note ? `<span class="ask-note">${esc(t("row.note." + q.note))}</span>` : ""}
        <button class="chip chip-yes" data-act="yes" data-uid="${esc(q.uid)}">${t("row.yes")}</button><button class="chip" data-act="no" data-uid="${esc(q.uid)}">${t("row.no")}</button>
        <button class="link" data-act="edit" data-uid="${esc(q.uid)}">${t("row.manual")}</button>`;
    else ctl = input;
    const ask = !decided && q.decision !== "no" && q.candidate.length && !editing;
    return `<li class="qso${p2p ? " is-p2p" : ""}${p2p > 1 ? " is-twofer" : ""}${ask ? " is-ask" : ""}${fresh && fresh.has(q.uid) ? " is-new" : ""}" data-uid="${esc(q.uid)}">
        <span class="qso-time">${hhmm(q.time)}</span>
        <span class="qso-call">${esc(q.call)}</span>
        <span class="qso-band">${esc(q.band)} ${esc(q.mode)}</span>
        <span class="qso-p2p">${ctl}</span>
      </li>`;
  }
  function renderQsos(fresh) {
    const key = (q) => q.ts || q.date + q.time;           // to the second when the logger sent seconds
    const list = [...st.qsos.values()].sort((a, b) => key(b).localeCompare(key(a)) || (b.seq || 0) - (a.seq || 0));   // newest first
    $("#qsos").innerHTML = list.map((q) => qsoRow(q, fresh)).join("");
    $("#barQsos").innerHTML = list.slice(0, 8).map((q) => qsoRow(q, fresh)).join("");
    $("#qsosEmpty").hidden = list.length > 0; $("#qsos").hidden = list.length === 0;
    $("#barEmpty").hidden = list.length > 0; $("#barQsos").hidden = list.length === 0;
    const uniq = new Set(list.map((q) => `${baseCall(q.call)}|${q.band}|${q.mode}`)).size;
    // Count per park for the day: a 2fer whose parks differ (one shared with an earlier session)
    // shows the smaller count as the number and the breakdown beside it.
    const parks = st.parks || [];
    const per = parks.map((p) => [p, list.filter((q) => !q.my || !q.my.length || q.my.includes(p)).length]);
    const n = per.length ? Math.min(...per.map((x) => x[1])) : list.length;
    const differ = per.length > 1 && new Set(per.map((x) => x[1])).size > 1;
    const breakdown = differ ? per.map(([p, c]) => `${p.split("-")[1]}: ${c}`).join(" · ") : "";
    const p2p = list.filter((q) => q.decision && q.decision !== "no" && q.parks.length).length;
    const pending = list.filter((q) => !q.decision && q.candidate.length).length;
    $("#qsoCount").textContent = n; $("#barCount").textContent = n; $("#barPer").textContent = breakdown;
    const w = Math.min(100, (n / 10) * 100) + "%";
    $("#qsoBar").style.width = w; $("#barMeter").style.width = w;
    $(".tally").classList.toggle("is-done", n >= 10); $(".bar-tally").classList.toggle("is-done", n >= 10);
    $("#qsoNote").textContent = (breakdown ? breakdown + " — " : "") + (n >= 10 ? t("live.qsoNote.done", { n: uniq }) : t("live.qsoNote.left", { n: 10 - n }));
    $("#p2pCount").textContent = [p2p ? t("live.p2pCount", { n: p2p }) : "", pending ? t("live.pendingCount", { n: pending }) : ""].filter(Boolean).join(" · ");
    if (st.editing) { const el = $(`[data-in="${CSS.escape(st.editing)}"]`); if (el) el.focus(); }
    if (n >= 10 && !st.cheered) { st.cheered = true; cheer(); }
  }
  function cheer() {
    const c = $("#cheer"); c.hidden = false;
    clearTimeout(cheer.h); cheer.h = setTimeout(() => (c.hidden = true), 7000);
  }
  $("#cheer").addEventListener("click", () => ($("#cheer").hidden = true));

  async function decide(uid, decision, parks) {
    const r = await api.set_p2p(uid, decision, parks || "");
    if (!r.ok) { toast(r.error); return; }
    st.editing = null;
    for (const ev of r.events) { const old = st.qsos.get(ev.uid); if (old) st.qsos.set(ev.uid, { ...old, ...ev }); }
    renderQsos();
    const q = st.qsos.get(uid);
    if (q && q.parks.length) toast(t("live.recorded", { call: q.call, parks: q.parks.join(" + ") }));
  }
  function onQsoClick(e) {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const uid = b.dataset.uid, act = b.dataset.act;
    if (act === "edit") { st.editing = uid; renderQsos(); }
    else if (act === "cancel") { st.editing = null; renderQsos(); }
    else if (act === "manual") decide(uid, "manual", b.closest(".p2p-in").querySelector("input").value);
    else decide(uid, act, act === "yes" ? (st.qsos.get(uid).candidate || []).join(",") : "");
  }
  function onQsoKey(e) {
    if (e.key === "Enter" && e.target.matches("[data-in]")) { e.preventDefault(); decide(e.target.dataset.in, "manual", e.target.value); }
    if (e.key === "Escape" && e.target.matches("[data-in]")) { st.editing = null; renderQsos(); }
  }
  for (const id of ["#qsos", "#barQsos"]) { $(id).addEventListener("click", onQsoClick); $(id).addEventListener("keydown", onQsoKey); }

  // ---- bar mode: the window shrinks to a strip kept above the logger
  async function setBar(on) {
    document.body.classList.toggle("is-bar", on); $("#bar").hidden = !on; st.bar = on;
    try { await api.set_bar(on); } catch (e) { /* window control is best effort */ }
  }
  $("#toBar").addEventListener("click", () => setBar(true));
  $("#barExpand").addEventListener("click", () => setBar(false));

  $$("#liveRun .seg button").forEach((b) => b.addEventListener("click", () => {
    st.prefix = b.dataset.prefix; segSet("#liveRun .seg", "prefix", st.prefix); api.save({ prefix: st.prefix }); renderSpots();
  }));

  // ---- finish: stop, write this park's upload file(s), back to the start
  const finishLabels = () => [$("#finishLive"), $("#barFinish")].forEach((b, i) => (b.textContent = i ? t("bar.finish") : t("live.finish")));
  async function finishLive() {
    const pending = [...st.qsos.values()].filter((q) => !q.decision && q.candidate.length).length;
    const btns = [$("#finishLive"), $("#barFinish")];
    if (pending && !st.finishArmed) {           // window.confirm is not available in the embedded view
      st.finishArmed = true;
      btns.forEach((b) => (b.textContent = t("live.finishArmed", { n: pending })));
      toast(t("live.finishPending", { n: pending }));
      clearTimeout(finishLive.h);
      finishLive.h = setTimeout(() => { st.finishArmed = false; finishLabels(); }, 6000);
      return;
    }
    st.finishArmed = false; clearTimeout(finishLive.h);
    btns.forEach((b) => { b.disabled = true; b.textContent = t("live.working"); });
    const r = await api.finish_live(true);
    btns.forEach((b) => (b.disabled = false)); finishLabels();
    clearInterval(st.timer); clearInterval(st.poll);
    await setBar(false);
    $("#liveRun").hidden = true; $("#liveIdle").hidden = false; $("#liveDot").hidden = true;
    const card = $("#doneCard"); card.hidden = false;
    if (!r.ok) {
      $("#doneTitle").textContent = t("done.fail.title");
      $("#doneBody").innerHTML = `<p class="error">${esc(r.error)}</p><p class="muted">${esc(t("done.fail.body"))}</p>`;
      return;
    }
    const files = r.summary || [];
    const s = r.session || {};
    const parks = (s.parks || []).join(" + ");
    $("#doneTitle").textContent = files.length ? t("done.title.files", { parks, n: files.length }) : t("done.title.nofiles", { parks });
    $("#doneBody").innerHTML = resultsHtml(r) + `<p class="muted">${esc(r.out_dir || "")}</p>`;
    st.outDir = r.out_dir;
    toast(t("live.stopped", { start: (s.start || "").slice(11, 16), end: (s.end || "").slice(11, 16) }));
    $("#parks").focus();
  }
  $("#finishLive").addEventListener("click", finishLive);
  $("#barFinish").addEventListener("click", finishLive);
  $("#doneClose").addEventListener("click", () => ($("#doneCard").hidden = true));
  $("#doneOpen").addEventListener("click", () => api.open_out(st.outDir || st.out));
  $("#donePota").addEventListener("click", () => api.open_url("https://pota.app/"));

  // ================================================================ spots page (like pota.app's list)
  // band and mode group come computed from Python (spots.summarize); the page only filters.
  const sp = { items: [], worked: new Set(), region: "", country: "JP", group: "", band: "", q: "", twofer: false, timer: null };
  const REGIONS = ["as", "eu", "na", "sa", "af", "oc"];      // continent codes from spots.continent_of
  async function loadSpotsPage() {
    const r = await api.spots_now();
    const err = $("#spotsError");
    if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
    err.hidden = true; sp.items = r.items; sp.worked = new Set(r.worked || []);
    $("#spotsAt").textContent = t("spots.at", { at: r.at, n: r.items.length });
    const bands = [...new Set(sp.items.map((e) => e.band).filter(Boolean))]
      .sort((a, b) => parseFloat(b) * (b.endsWith("cm") ? .01 : 1) - parseFloat(a) * (a.endsWith("cm") ? .01 : 1));
    const sel = $("#spotsBand"); const cur = sel.value;
    sel.innerHTML = `<option value="">${esc(t("spots.band.all"))}</option>` + bands.map((b) => `<option value="${b}">${b}</option>`).join("");
    sel.value = bands.includes(cur) ? cur : "";
    spotsOptions();
    renderSpotsPage();
    clearInterval(sp.timer); sp.timer = setInterval(() => { if (!$("#view-spots").hidden) loadSpotsPage(); else clearInterval(sp.timer); }, 60000);
    if (r.pending) setTimeout(() => { if (!$("#view-spots").hidden) loadSpotsPage(); }, 4000);   // spot histories still loading
  }
  // Region (continent) and country selects: only what is on the air now, with counts.
  function spotsOptions() {
    const nr = {}, n = {};
    sp.items.forEach((e) => { if (e.region) nr[e.region] = (nr[e.region] || 0) + 1; });
    if (sp.region && !nr[sp.region]) sp.region = "";
    $("#spotsRegion").innerHTML = `<option value="">${esc(t("spots.region.all"))}</option>` + REGIONS.filter((r) => nr[r]).map((r) =>
      `<option value="${r}"${r === sp.region ? " selected" : ""}>${esc(t("region." + r))} (${nr[r]})</option>`).join("");
    sp.items.forEach((e) => { if (e.country && (!sp.region || e.region === sp.region)) n[e.country] = (n[e.country] || 0) + 1; });
    const countries = Object.keys(n).sort((a, b) => n[b] - n[a] || countryName(a).localeCompare(countryName(b), st.lang));
    if (sp.country && !countries.includes(sp.country)) sp.country = "";
    $("#spotsCountry").innerHTML = `<option value="">${esc(t("spots.country.all"))}</option>` + countries.map((c) =>
      `<option value="${esc(c)}"${c === sp.country ? " selected" : ""}>${flagOf(c)} ${esc(countryName(c))} (${n[c]})</option>`).join("");
  }
  function renderSpotsPage() {
    const q = sp.q.toUpperCase();
    const list = sp.items.filter((e) =>
      (!sp.region || e.region === sp.region) &&
      (!sp.country || e.country === sp.country) &&
      (!sp.group || e.group === sp.group) &&
      (!sp.band || e.band === sp.band) &&
      (!sp.twofer || e.twofer) &&
      (!q || e.call.toUpperCase().includes(q) || e.parks.some((p) => p.includes(q))));
    $("#spotsPage").innerHTML = list.map((e) => spotRow(e, sp.worked.has(e.base), false, true)).join("");
    $("#spotsPageEmpty").hidden = list.length > 0; $("#spotsPage").hidden = list.length === 0;
    $("#spotsSummary").textContent = sp.items.length ? t("spots.summary", { shown: list.length, total: sp.items.length }) : t("nav.spots.sub");
  }
  $("#spotsRegion").addEventListener("change", (e) => { sp.region = e.target.value; spotsOptions(); renderSpotsPage(); });
  $("#spotsCountry").addEventListener("change", (e) => { sp.country = e.target.value; renderSpotsPage(); });
  $$(".seg-mode button").forEach((b) => b.addEventListener("click", () => { sp.group = b.dataset.modegroup; segSet(".seg-mode", "modegroup", sp.group); renderSpotsPage(); }));
  $("#spotsBand").addEventListener("change", (e) => { sp.band = e.target.value; renderSpotsPage(); });
  $("#spotsSearch").addEventListener("input", (e) => { sp.q = e.target.value.trim(); renderSpotsPage(); });
  $("#spotsTwofer").addEventListener("change", (e) => { sp.twofer = e.target.checked; renderSpotsPage(); });
  $("#spotsRefresh").addEventListener("click", loadSpotsPage);

  // ================================================================ build
  $$(".seg-src button").forEach((b) => b.addEventListener("click", () => setSource(b.dataset.src)));
  function setSource(src) {
    st.source = src; segSet(".seg-src", "src", src); api.save({ source: src });
    $("#filebox").hidden = src !== "adif";
    if (src === "app") loadActs(); else if (st.adif) loadActs(st.adif); else renderActs({ items: [] }, true);
  }
  async function loadActs(path) { renderActs(await api.activations(path || null)); }
  function renderActs(res, waitingFile) {
    if (st.source === "adif" && res.path !== undefined) {
      st.adif = res.path || st.adif;
      $("#adifName").textContent = st.adif ? st.adif.split(/[\\/]/).pop() : t("build.file.none");
      $("#adifPath").textContent = st.adif || t("build.file.hint");
    }
    st.acts = res.items || []; st.selected.clear(); $("#actHint").textContent = t("build.hint.all");
    if (res.error) { $("#acts").innerHTML = `<p class="pad error">${esc(res.error)}</p>`; return; }
    if (waitingFile) { $("#acts").innerHTML = `<p class="pad muted">${esc(t("build.acts.waiting"))}</p>`; return; }
    if (!st.acts.length) {
      $("#acts").innerHTML = `<p class="pad muted">${esc(t(st.source === "app" ? "build.acts.emptyApp" : "build.acts.emptyAdif"))}</p>`;
      return;
    }
    $("#acts").innerHTML = st.acts.map((a) => `
      <label class="act">
        <input type="checkbox" value="${esc(a.date)}">
        <span class="act-date">${fmtDate(a.date)}<small>UTC</small></span>
        <span class="act-parks">${a.parks.map((p) => `<span class="act-park">${plate(p)}<small>${a.per && a.per[p] != null ? a.per[p] : ""}</small><small class="act-pota">${a.pota && a.pota[p] != null && a.pota[p] !== a.per[p] ? esc(t("res.unique", { n: a.pota[p] })) : ""}</small></span>`).join("")}</span>
        <span class="act-n${a.qsos < 10 ? " is-short" : ""}">${a.qsos} QSO</span>
        <button type="button" class="link act-view" data-date="${esc(a.date)}">${esc(t("build.view"))}</button>
        ${st.source === "app" ? `<button type="button" class="link act-del" data-date="${esc(a.date)}">${esc(t("build.delete"))}</button>` : ""}
      </label>`).join("");
    $$("#acts .act-view").forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); openEditor(b.dataset.date); }));
    // Delete needs a second press (no window.confirm in the web view); the first press arms it for 4 s.
    $$("#acts .act-del").forEach((b) => b.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!b.classList.contains("is-armed")) {
        b.classList.add("is-armed"); b.textContent = t("build.deleteArmed");
        setTimeout(() => { b.classList.remove("is-armed"); b.textContent = t("build.delete"); }, 4000);
        return;
      }
      const r = await api.delete_activation(b.dataset.date);
      if (!r.ok) { toast(r.error); return; }
      toast(t("build.deleted", { n: r.n }));
      $("#logCount").textContent = r.log_count ? " " + t("build.count", { n: r.log_count }) : "";
      loadActs();
    }));
    $$("#acts input").forEach((i) => i.addEventListener("change", () => {
      i.checked ? st.selected.add(i.value) : st.selected.delete(i.value);
      i.closest(".act").classList.toggle("is-checked", i.checked);
      $("#actHint").textContent = st.selected.size ? t("build.hint.selected", { n: st.selected.size }) : t("build.hint.all");
    }));
  }
  // ---------- editor: the QSOs of one activation day; cells save on change (app log only) ----------
  const ed = { date: "", path: null };
  async function openEditor(date) {
    ed.date = date; ed.path = st.source === "adif" ? st.adif : null;
    $("#editorTitle").textContent = t("ed.title", { date: fmtDate(date) });
    $("#editor").hidden = false;
    await loadEditor();
  }
  async function loadEditor() {
    const r = await api.activation_qsos(ed.date, ed.path);
    const note = $("#editorNote");
    if (!r.ok) { $("#editorRows").innerHTML = ""; note.textContent = r.error; note.hidden = false; return; }
    note.textContent = r.editable ? "" : t("ed.readonly"); note.hidden = r.editable;
    const cell = (q, f, cls) => r.editable
      ? `<input class="${cls || ""}" data-f="${f}" value="${esc(q[f])}" spellcheck="false" autocomplete="off">`
      : `<span class="${cls || ""}">${esc(q[f])}</span>`;
    $("#editorRows").innerHTML = r.rows.length ? r.rows.map((q) => `
      <tr data-uid="${esc(q.uid || "")}">
        <td>${cell(q, "time")}</td><td>${cell(q, "call", "ed-call")}</td><td>${cell(q, "band")}</td><td>${cell(q, "mode")}</td>
        <td><span class="plates">${plates(q.my)}</span></td>
        <td>${r.editable ? `<input data-f="parks" value="${esc(q.parks.join(","))}" placeholder="JP-0000" spellcheck="false" autocomplete="off">`
                         : `<span class="plates">${plates(q.parks)}</span>`}</td>
        <td>${r.editable ? `<button type="button" class="link ed-del">${esc(t("ed.delete"))}</button>` : ""}</td>
      </tr>`).join("") : `<tr><td colspan="7" class="muted">${esc(t("ed.empty"))}</td></tr>`;
    const F = { time: "TIME_ON", call: "CALL", band: "BAND", mode: "MODE", parks: "parks" };
    $$("#editorRows input").forEach((i) => i.addEventListener("change", async () => {
      const res = await api.save_qso(i.closest("tr").dataset.uid, { [F[i.dataset.f]]: i.value.trim() });
      toast(res.ok ? t("ed.saved") : res.error);
      loadEditor();
    }));
    $$("#editorRows .ed-del").forEach((b) => b.addEventListener("click", async () => {
      if (!b.classList.contains("is-armed")) {
        b.classList.add("is-armed"); b.textContent = t("build.deleteArmed");
        setTimeout(() => { b.classList.remove("is-armed"); b.textContent = t("ed.delete"); }, 4000);
        return;
      }
      const res = await api.delete_qso(b.closest("tr").dataset.uid);
      if (!res.ok) { toast(res.error); return; }
      toast(t("ed.deleted"));
      $("#logCount").textContent = res.log_count ? " " + t("build.count", { n: res.log_count }) : "";
      loadEditor();
    }));
  }
  $("#editorClose").addEventListener("click", () => { $("#editor").hidden = true; loadActs(ed.path || undefined); });
  $("#pickAdif").addEventListener("click", async () => { const r = await api.pick_adif(); if (r) renderActs(r); });
  $("#pickOut").addEventListener("click", async () => { const p = await api.pick_out(); if (p) { st.out = p; $("#outPath").textContent = p; } });

  const SRC_CLASS = { hunter: "src-ok", confirmed: "src-ok", manual: "src-ok", spot: "src-spot", log: "src-log", logspot: "src-log" };
  function resultsHtml(r) {
    const files = r.summary || [];
    // every QSO of each file; P2P rows carry the other park(s) and how they were known; a switch hides the rest
    const row = (q) => `
          <div class="qrow${q.parks.length ? " is-p2p" : ""}"><span class="muted">${hhmm(q.time)}</span>
          <span class="qrow-call">${esc(q.call)}</span><span class="qrow-bm">${esc(q.band)} ${esc(q.mode)}</span>
          ${q.parks.length ? `<span class="plates">${plates(q.parks)}</span><span class="src ${SRC_CLASS[q.source] || "src-log"}">${esc(t("src." + q.source))}</span>` : ""}</div>`;
    return (files.length ? `<div class="res-tools"><label class="switch switch-sm"><input type="checkbox" class="res-p2p-only"><span class="switch-ui"></span><span>${esc(t("res.p2pOnly"))}</span></label></div>` : "") +
      files.map((f) => `
      <article class="file">
        <div class="file-head">
          ${plate(f.park)}
          <div><div class="file-date">${fmtDate(f.date)}</div><div class="file-name">${esc(f.file)}</div></div>
          <div class="file-q${f.qsos < 10 ? " is-short" : ""}"><strong>${f.qsos}</strong><span>${esc(t(f.qsos < 10 ? "res.qsoShort" : "res.qso"))}</span>
            ${f.unique && f.unique < f.qsos ? `<small>${esc(t("res.unique", { n: f.unique }))}</small>` : ""}
            ${f.records && f.records !== f.qsos ? `<small>${esc(t("res.lines", { n: f.records }))}</small>` : ""}</div>
        </div>
        ${(f.rows || []).length ? `<div class="p2p">${f.rows.map(row).join("")}</div>`
          : f.p2p.length ? `<div class="p2p">${f.p2p.map((p) => row({ ...p, band: "", mode: "" })).join("")}</div>` : `<div class="p2p-none">${esc(t("res.noP2P"))}</div>`}
      </article>`).join("") +
      (files.length && r.notes && r.notes.length ? `<div class="notes"><h3>${esc(t("res.notes"))}</h3><ul>${r.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>` : "") +
      (!files.length && r.notes && r.notes.length ? `<p class="muted">${esc(r.notes[0])}</p>` : "");
  }
  document.addEventListener("change", (e) => {           // the "P2P only" switch inside any results box
    if (e.target.classList && e.target.classList.contains("res-p2p-only")) e.target.closest(".res-tools").parentElement.classList.toggle("is-p2p-only", e.target.checked);
  });
  $("#runBuild").addEventListener("click", async () => {
    if (st.source === "adif" && !st.adif) { toast(t("build.pickFirst")); return; }
    const btn = $("#runBuild"); btn.disabled = true; btn.textContent = t("build.working");
    const r = await api.build({ source: st.source, adif: st.adif, dates: [...st.selected], override: $("#override").value,
                                call: st.call, out: st.out, online: $("#online").checked });
    btn.disabled = false; btn.textContent = t("build.run");
    const box = $("#results"); box.hidden = false;
    if (!r.ok) { $("#resultsTitle").textContent = t("build.res.fail"); $("#resultsBody").innerHTML = `<p class="error">${esc(r.error)}</p>`; return; }
    const files = r.summary || [];
    $("#resultsTitle").textContent = files.length ? t("build.res.files", { n: files.length }) : t("build.res.none");
    $("#resultsBody").innerHTML = resultsHtml(r);
    st.outDir = r.out_dir;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("#openOut").addEventListener("click", () => api.open_out(st.outDir || st.out));
  $("#openPota").addEventListener("click", () => api.open_url("https://pota.app/"));

  // ================================================================ settings
  const KINDS = [["n1mm", "N1MM"], ["wsjtx", "WSJT-X"], ["adif", "ADIF"]];
  const recvState = (l) => { const s = st.receiver[l.name]; return s && typeof s === "object" ? s : { code: l.enabled ? "" : "off", text: l.enabled ? "" : t("set.off") }; };
  const recvClass = (s) => (s.code === "error" || s.code === "badforward") ? "is-bad" : (s.code === "listening" || s.code === "receiving") ? "is-ok" : "";
  function renderListeners() {
    $("#listeners").innerHTML = st.listeners.map((l, i) => {
      const s = recvState(l);
      return `<div class="lis" data-i="${i}">
        <label class="switch" title="${esc(t("set.toggle"))}"><input type="checkbox" data-k="enabled" ${l.enabled ? "checked" : ""}><span class="switch-ui"></span></label>
        <label>${esc(t("set.name"))}<input type="text" data-k="name" value="${esc(l.name)}"></label>
        <label>${esc(t("set.kind"))}<select data-k="kind">${KINDS.map(([v, k]) => `<option value="${v}"${l.kind === v ? " selected" : ""}>${k}</option>`).join("")}</select></label>
        <label>${esc(t("set.port"))}<input type="text" inputmode="numeric" data-k="port" value="${esc(l.port)}"></label>
        <label>${esc(t("set.mc"))}<input type="text" data-k="multicast" placeholder="${esc(t("set.mc.ph"))}" value="${esc(l.multicast)}"></label>
        <label>${esc(t("set.fwd"))}<input type="text" data-k="forward" placeholder="${esc(t("set.fwd.ph"))}" value="${esc(l.forward)}"></label>
        <button class="link lis-del" data-del="${i}">${esc(t("set.del"))}</button>
        <div class="lis-state ${recvClass(s)}">${esc(s.text)}</div>
      </div>`;
    }).join("") || `<p class="muted">${esc(t("set.none"))}</p>`;
    $$("#listeners [data-k]").forEach((el) => el.addEventListener("change", () => {
      const l = st.listeners[+el.closest(".lis").dataset.i];
      l[el.dataset.k] = el.type === "checkbox" ? el.checked : el.value;
    }));
    $$("#listeners [data-del]").forEach((b) => b.addEventListener("click", () => { st.listeners.splice(+b.dataset.del, 1); renderListeners(); }));
  }
  function updateReceiver(rs) {
    if (!rs) return;
    st.receiver = rs;
    const on = st.listeners.filter((l) => l.enabled);
    const bad = on.some((l) => recvClass(recvState(l)) === "is-bad");
    $("#recvSummary").textContent = !on.length ? t("set.sum.none") : bad ? t("set.sum.bad") : t("set.sum.ok", { n: on.length });
    if (!$("#view-config").hidden) $$("#listeners .lis").forEach((el) => {
      const l = st.listeners[+el.dataset.i]; const s = recvState(l);
      const box = el.querySelector(".lis-state"); box.textContent = s.text; box.className = "lis-state " + recvClass(s);
    });
  }
  $("#addListener").addEventListener("click", () => {
    st.listeners.push({ name: t("set.newName", { n: st.listeners.length + 1 }), kind: "n1mm", port: 2334, multicast: "", enabled: true, forward: "" });
    renderListeners();
  });
  $("#saveListeners").addEventListener("click", async () => {
    const r = await api.save_listeners(st.listeners);
    const err = $("#listenError");
    if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
    err.hidden = true; st.listeners = r.listeners; st.receiver = r.receiver || {}; renderListeners(); updateReceiver(st.receiver);
    toast(t("set.saved"));
  });
  setInterval(async () => { if (api) updateReceiver((await api.poll_live(1e12, 1e12)).receiver); }, 4000);

  // ---------- updates ----------
  let upd = null;
  async function checkUpdate(quiet) {
    const box = $("#update"), txt = $("#updateText"), go = $("#updateGo");
    if (!quiet) { box.hidden = false; txt.textContent = t("upd.checking"); go.hidden = true; }
    const r = await api.check_update();
    if (!r.ok) { if (!quiet) txt.textContent = r.error; return; }
    upd = r;
    if (!r.newer) { if (!quiet) { txt.textContent = t("upd.latest", { v: r.current }); go.hidden = true; } return; }
    box.hidden = false; go.hidden = !r.can_install; go.disabled = false; go.textContent = t("upd.go");
    txt.innerHTML = t("upd.available", { latest: esc(r.latest), current: esc(r.current) }) +
      (r.can_install ? esc(t(r.translocated ? "upd.install.dl" : "upd.install.swap"))
        : `<button class="link" id="updatePage">${esc(t("upd.page"))}</button>`);
    const pg = $("#updatePage"); if (pg) pg.addEventListener("click", () => api.open_url(r.page));
  }
  $("#checkUpdate").addEventListener("click", () => checkUpdate(false));
  async function installUpdate(go, txt) {           // from the settings box or the startup modal
    if (!upd || !upd.asset) return;
    go.disabled = true; go.textContent = t("upd.downloading");
    const r = await api.install_update(upd.asset);
    if (!r.ok) { go.disabled = false; go.textContent = t("upd.go"); txt.textContent = r.error; return; }
    go.hidden = true;
    if (r.manual) { txt.innerHTML = t("upd.manual", { path: esc(r.manual) }); api.open_out(r.manual_dir); }
    else txt.textContent = t("upd.done", { v: upd.latest });
  }
  $("#updateGo").addEventListener("click", () => installUpdate($("#updateGo"), $("#updateText")));
  // At startup: check first and, when a newer release exists, ask in a modal (after the terms, if those are up).
  async function promptUpdate() {
    await checkUpdate(true);
    if (!upd || !upd.newer) return;
    const show = () => {
      $("#updModalText").innerHTML = t("upd.available", { latest: esc(upd.latest), current: esc(upd.current) }) + " " +
        (upd.can_install ? esc(t(upd.translocated ? "upd.install.dl" : "upd.install.swap"))
          : `<button class="link" id="updModalPage">${esc(t("upd.page"))}</button>`);
      const pg = $("#updModalPage"); if (pg) pg.addEventListener("click", () => api.open_url(upd.page));
      $("#updModalGo").hidden = !upd.can_install; $("#updModalGo").disabled = false; $("#updModalGo").textContent = t("upd.go");
      $("#updModal").hidden = false;
    };
    if ($("#terms").hidden) show(); else st.afterTerms = show;
  }
  $("#updModalLater").addEventListener("click", () => ($("#updModal").hidden = true));
  $("#updModalGo").addEventListener("click", () => installUpdate($("#updModalGo"), $("#updModalText")));

  // ---------- terms ----------
  function showTerms(mustAccept) {
    $("#termsBody").innerHTML = t("terms.body");
    $("#termsAccept").textContent = mustAccept ? t("terms.accept") : t("done.close");
    $("#terms").hidden = false;
  }
  $("#termsLink").addEventListener("click", () => showTerms(false));
  $("#termsAccept").addEventListener("click", () => {
    if (st.termsAccepted !== TERMS_VERSION) { st.termsAccepted = TERMS_VERSION; api.save({ terms_accepted: TERMS_VERSION }); }
    $("#terms").hidden = true;
    if (st.afterTerms) { st.afterTerms(); st.afterTerms = null; }
  });

  // ---------- settings (設定): callsigns, language, app ----------
  // The saved callsigns are a list; st.call is the one in use. Python keeps the list clean
  // (uppercase, valid, the chosen one first), the UI only shows it.
  function renderCalls() {
    $("#calls").innerHTML = st.calls.map((c) => `
      <li class="call-row"><span class="call-name">${esc(c)}</span>
        <button class="link" data-del="${esc(c)}">${esc(t("cfg.calls.remove"))}</button></li>`).join("");
    $("#liveCall").innerHTML = st.calls.map((c) => `<option value="${esc(c)}"${c === st.call ? " selected" : ""}>${esc(c)}</option>`).join("");
  }
  async function saveCalls(calls, call) {
    st.calls = calls; st.call = call;
    await api.save({ calls, call });
    renderCalls();
  }
  $("#callsAdd").addEventListener("submit", (e) => {
    e.preventDefault();
    const err = $("#callsError"), c = $("#callNew").value.trim().toUpperCase();
    if (!/^[A-Z0-9/]{3,}$/.test(c)) { err.textContent = t("cfg.calls.err"); err.hidden = false; return; }
    err.hidden = true; $("#callNew").value = "";
    saveCalls(st.calls.includes(c) ? st.calls : [...st.calls, c], st.calls.length ? st.call : c);
  });
  $("#calls").addEventListener("click", (e) => {
    const b = e.target.closest("[data-del]"); if (!b) return;
    const err = $("#callsError");
    if (st.calls.length <= 1) { err.textContent = t("cfg.calls.last"); err.hidden = false; return; }
    err.hidden = true;
    const calls = st.calls.filter((c) => c !== b.dataset.del);
    saveCalls(calls, calls.includes(st.call) ? st.call : calls[0]);
  });
  $("#liveCall").addEventListener("change", (e) => saveCalls(st.calls, e.target.value));
  $("#p2pAuto").addEventListener("change", (e) => api.save({ p2p_auto: e.target.checked }));

  // ---------- click a park plate or a callsign: copy, or open it on the web ----------
  const LOOKUP = {         // where 設定 → コールサインの検索先 sends a callsign
    qrz: ["QRZ.com", (c) => `https://www.qrz.com/db/${encodeURIComponent(c)}`],
    hamqth: ["HamQTH", (c) => `https://www.hamqth.com/${encodeURIComponent(c)}`],
    qrzcq: ["QRZCQ", (c) => `https://www.qrzcq.com/call/${encodeURIComponent(c)}`],
    hamcall: ["HamCall.net", (c) => `https://hamcall.net/call?callsign=${encodeURIComponent(c)}`],
    soumu: ["総務省 無線局等情報検索", (c) => `https://www.tele.soumu.go.jp/musen/list?ST=1&OF=2&DA=0&SC=0&DC=1&OW=AT&MA=${encodeURIComponent(baseCall(c))}`],
  };
  function renderLookup() {           // several sites can be on; the click menu lists each
    $("#lookupSel").innerHTML = Object.entries(LOOKUP).map(([k, v]) =>
      `<label class="switch switch-sm"><input type="checkbox" value="${k}"${(st.lookup || []).includes(k) ? " checked" : ""}><span class="switch-ui"></span><span>${esc(v[0])}</span></label>`).join("");
  }
  $("#lookupSel").addEventListener("change", () => {
    st.lookup = $$("#lookupSel input:checked").map((i) => i.value);
    api.save({ lookup: st.lookup });
  });
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); }
    catch (e) { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); }
    toast(t("pop.copied", { text }));
  }
  function showPop(x, y, items) {
    const pop = $("#pop");
    pop.innerHTML = items.map((it, i) => `<button type="button" data-i="${i}">${esc(it[0])}</button>`).join("");
    pop.hidden = false;
    const w = pop.offsetWidth, h = pop.offsetHeight;
    pop.style.left = Math.min(x, window.innerWidth - w - 8) + "px";
    pop.style.top = (y + h + 8 > window.innerHeight ? y - h - 4 : y + 4) + "px";
    $$("#pop button").forEach((b) => b.addEventListener("click", () => { pop.hidden = true; items[+b.dataset.i][1](); }));
  }
  const CALL_SEL = ".spot-call, .qso-call, .p2p-call, .qrow-call";
  document.addEventListener("click", (e) => {
    const pop = $("#pop");
    if (pop.contains(e.target)) return;
    const plateEl = e.target.closest(".plate[data-ref]");
    const callEl = !plateEl && e.target.closest(CALL_SEL);
    if (!plateEl && !callEl) { pop.hidden = true; return; }
    if (e.target.closest("label")) e.preventDefault();          // don't tick the row's checkbox
    e.stopPropagation();
    if (plateEl) {
      const ref = plateEl.dataset.ref;
      showPop(e.clientX, e.clientY, [[t("pop.copy", { text: ref }), () => copyText(ref)],
                                     [t("pop.park"), () => api.open_url(`https://pota.app/#/park/${encodeURIComponent(ref)}`)]]);
    } else {
      const call = (callEl.firstChild ? callEl.firstChild.textContent : callEl.textContent).trim();
      const sites = (st.lookup || []).filter((k) => LOOKUP[k]).map((k) => LOOKUP[k]);
      showPop(e.clientX, e.clientY, [[t("pop.copy", { text: call }), () => copyText(call)],
                                     ...sites.map((site) => [t("pop.call", { site: site[0] }), () => api.open_url(site[1](call))]),
                                     [t("pop.profile"), () => api.open_url(`https://pota.app/#/profile/${encodeURIComponent(baseCall(call))}`)]]);
    }
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#pop").hidden = true; });
  $("#openData").addEventListener("click", () => api.open_data());
  $("#lang").addEventListener("change", async (e) => {
    await api.save({ lang: e.target.value }); await loadLang(e.target.value); rerender();
  });

  // ---------- boot ----------
  async function boot() {
    api = window.pywebview.api;
    const s = await api.get_state();
    Object.assign(st, { call: s.call, calls: s.calls || [s.call], prefix: s.prefix, out: s.out, adif: s.adif, source: s.source || "app", listeners: s.listeners,
                        langs: s.langs || [["ja", "日本語"]], termsAccepted: s.terms_accepted || "" });
    $("#lang").innerHTML = st.langs.map(([c, name]) => `<option value="${esc(c)}">${esc(name)}</option>`).join("");
    const lang = s.lang || pickLang(navigator.language);
    if (!s.lang) api.save({ lang });
    await loadLang(lang);
    $("#version").textContent = `v${s.version}`;
    renderCalls(); $("#p2pAuto").checked = !!s.p2p_auto;
    st.lookup = s.lookup || ["qrz"]; renderLookup();
    setParks(s.parks);
    $("#outPath").textContent = s.out;
    $("#logCount").textContent = s.log_count ? " " + t("build.count", { n: s.log_count }) : "";
    segSet("#liveRun .seg", "prefix", st.prefix); sp.country = st.prefix || "";
    renderListeners(); updateReceiver(s.receiver);
    setSource(st.source);
    if (s.live) enterRunning(s.live.parks, s.live.start);
    if (st.termsAccepted !== TERMS_VERSION) showTerms(true);
    setTimeout(promptUpdate, 1500);                 // the first thing after the window is up
  }
  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener("pywebviewready", boot);
})();
