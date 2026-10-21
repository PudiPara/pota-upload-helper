"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  let api = null;
  const st = {
    call: "", calls: [], prefix: "home", country: "", countries: [], ex: {}, spots: new Map(), qsos: new Map(), lastAt: 0, lastQ: 0,
    start: null, timer: null, poll: null, source: "app", adif: "", out: "", outDir: "",
    acts: [], selected: new Set(), listeners: [], receiver: {}, editing: null, bar: false, cheered: false,
    lang: "ja", langs: [], termsAccepted: "", mypota: {}, huntedShown: new Set(),
  };
  const TERMS_VERSION = "2026-10-20";

  // ---------- i18n ----------
  let L = {};
  // {park}, {park2}, {cc} without a value = the example parks of the operator's country (Api.examples)
  const t = (k, p) => String(L[k] != null ? L[k] : k).replace(/\{(\w+)\}/g, (_, n) => (p && p[n] != null ? p[n] : st.ex[n] ?? ""));
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
    $("#country").innerHTML = st.countries.map((c) => [c, countryName(c)]).sort((a, b) => a[1].localeCompare(b[1], lang))
      .map(([c, name]) => `<option value="${esc(c)}">${esc(name)}</option>`).join("");   // name first: type to find it
    $("#country").value = st.country;
  }
  function rerender() {           // dynamic parts that hold translated text
    $("#dataVersion").textContent = st.dataVersion ? t("ver.data", { v: st.dataVersion }) : "";
    renderListeners(); updateReceiver(st.receiver); renderCalls(); renderMypota();
    if (!$("#liveRun").hidden) { renderQsos(); renderSpots(); }
    if (!$("#view-spots").hidden) { spotsOptions(); renderSpotsPage(); }
    if (!$("#view-record").hidden) renderRecord();
    if (!$("#view-history").hidden) renderHistory();
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
  const refInner = (ref) => { const i = ref.indexOf("-"); return `<b>${esc(ref.slice(0, i + 1))}</b>${esc(ref.slice(i + 1))}`; };
  // isNew: parks the operator has not hunted yet (Python's mypota) get an amber rule
  const plate = (ref, isNew) => `<span class="plate${isNew ? " is-new" : ""}" data-ref="${esc(ref)}">${refInner(ref)}</span>`;
  const JOIN = '<span class="plate-join" aria-hidden="true">+</span>';
  const plates = (refs, fresh) => (refs || []).map((r) => plate(r, fresh && fresh.includes(r))).join(JOIN);
  // a park that is not active in pota.app's list: "POTA で終了" or "リストにない" (record and history pages)
  const statusTag = (s) => s === "retired" ? `<span class="rec-tag" title="${esc(t("rec.retiredTip"))}">${esc(t("rec.retired"))}</span>`
    : s === "no" ? `<span class="rec-tag" title="${esc(t("rec.unlistedTip"))}">${esc(t("rec.unlisted"))}</span>` : "";
  const newTag = (fresh) => (fresh && fresh.length ? `<span class="new-tag">${esc(t("tag.new"))}</span>` : "");
  // Country = the park prefix (ISO 3166 alpha-2, sent by Python): flag from regional indicators, name in the UI language.
  const flagOf = (cc) => /^[A-Z]{2}$/.test(cc) ? String.fromCodePoint(...[...cc].map((c) => 0x1F1E6 + c.charCodeAt(0) - 65)) : "";
  const countryName = (cc) => { try { return new Intl.DisplayNames([st.lang], { type: "region" }).of(cc) || cc; } catch (e) { return cc; } };
  // the operator's country = the country of the (first) park being activated; "" before any park
  const homeOf = (parks) => (splitParks(parks)[0] || "").split("-")[0];
  const fmtDate = (d) => {
    try {
      return new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8)))
        .toLocaleDateString(st.lang, { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
    } catch (e) { return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`; }
  };
  const hhmm = (tm) => `${esc(String(tm).slice(0, 2))}:${esc(String(tm).slice(2, 4))}`;
  function fmtFreq(khz) {
    const k = parseFloat(khz);
    return k ? `${(k / 1000).toFixed(3)}<small>MHz</small>` : esc(khz || "");
  }
  function toast(msg) {
    const el = $("#toast"); el.textContent = msg; el.hidden = false;
    clearTimeout(toast.h); toast.h = setTimeout(() => (el.hidden = true), 2800);
  }
  const utcMs = (iso) => Date.parse(iso.length === 16 ? iso + ":00Z" : iso + "Z");
  function showError(el, msg) { el.textContent = msg || ""; el.hidden = !msg; }
  function setLogCount(n) { $("#logCount").textContent = n ? " " + t("build.count", { n }) : ""; }
  // Park names from pota.app into the [data-ref] slots of a container (optional: a failure leaves them empty)
  async function fillParkNames(sel, parks) {
    try {
      const info = await api.park_info(parks.join(","));
      $$(sel + " [data-ref].park-name, " + sel + " .name[data-ref]").forEach((el) => {
        const ref = el.dataset.ref, i = info[ref] || {};
        el.textContent = i.name || "";
        el.parentElement.querySelectorAll(`.park-retired[data-for="${CSS.escape(ref)}"]`).forEach((x) => x.remove());
        const after = el.nextElementSibling && el.nextElementSibling.classList.contains("park-act") ? el.nextElementSibling : el;
        if (i.active === false || i.listed === false)   // retired, or a number nobody knows: details on pota.app
          after.insertAdjacentHTML("afterend", `<span class="park-retired" data-for="${esc(ref)}">${esc(t(i.active === false ? "park.retired" : "park.unknown"))}
            <button type="button" class="link" data-url="https://pota.app/#/park/${esc(ref)}">${esc(t("park.retiredLink"))}</button></span>`);
      });
    } catch (e) { /* optional */ }
  }
  // A destructive button needs a second press (window.confirm is unavailable in the web view): the first
  // press arms it for `ms` with `armedText`; then `label` (text, or a function that resets it) comes back.
  // -> true on the second press.
  function secondPress(btn, armedText, label, ms = 4000) {
    if (btn.classList.contains("is-armed")) { btn.classList.remove("is-armed"); clearTimeout(btn._arm); return true; }
    btn.classList.add("is-armed"); btn.textContent = armedText;
    btn._arm = setTimeout(() => { btn.classList.remove("is-armed"); if (typeof label === "function") label(); else btn.textContent = label; }, ms);
    return false;
  }
  function segSet(group, attr, val) {
    $$(group + " button").forEach((x) => { const on = x.dataset[attr] === val; x.classList.toggle("is-on", on); x.setAttribute("aria-checked", on); });
  }

  // ---------- navigation ----------
  function show(view) {
    $$(".nav-item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === view));
    ["live", "spots", "build", "history", "record", "config"].forEach((v) => ($("#view-" + v).hidden = v !== view));
    $(".main").scrollTo(0, 0);
    if (view === "build" && st.source === "app") loadActs();
    if (view === "config") api.poll_live(1e12, 1e12).then((r) => updateReceiver(r.receiver));
    if (view === "spots") loadSpotsPage();
    if (view === "record") loadRecord();
    if (view === "history") loadHistory();
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
    $("#parksPreview").innerHTML = parks.map((p) => `${plate(p)}<span class="park-name" data-ref="${esc(p)}"></span><span class="park-act" data-act="${esc(p)}"></span>`).join("");
    clearTimeout(renderPreview.h);
    if (parks.length) renderPreview.h = setTimeout(async () => {
      fillParkNames("#parksPreview", parks);
      try { renderLoc(await api.park_locations(parks.join(","))); } catch (e) { /* optional */ }
      try {                                   // 設定 → POTA の実績: which activation of this park this would be
        const mine = await api.my_parks(parks.join(","));
        $$("#parksPreview .park-act").forEach((el) => {
          const a = mine[el.dataset.act];
          el.textContent = !a ? "" : a.next === 1 ? t("park.first") : t("park.nth", { n: a.next, done: a.done, qsos: a.qsos });
        });
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
      st.loc = r.options[0].code; st.locPicked = false;      // fixed, not the operator's choice
      box.innerHTML = `<span class="loc-label">${esc(t("live.loc"))}</span><span class="loc-fixed">${label(r.options[0])}</span>`;
      return;
    }
    // keep a location only if the operator picked it in this select: one that came fixed with the
    // previous park (JP-1266 -> Tokyo) must not pre-fill a park that spans several (JP-0016)
    if (!st.locPicked || !r.options.some((o) => o.code === st.loc)) { st.loc = ""; st.locPicked = false; }
    box.innerHTML = `<span class="loc-label">${esc(t("live.loc"))}</span><select id="locSel"><option value="">${esc(t("live.loc.pick"))}</option>` +
      r.options.map((o) => `<option value="${esc(o.code)}"${o.code === st.loc ? " selected" : ""}>${label(o)}</option>`).join("") + `</select>`;
    $("#locSel").addEventListener("change", (e) => { st.loc = e.target.value; st.locPicked = !!st.loc; });
  }
  $("#parks").addEventListener("input", onParkInput);
  $("#parks").addEventListener("keydown", (e) => { if (e.key === "Enter") startLive(); });

  async function startLive() {
    const parks = splitParks(parkValue());
    const err = $("#liveError");
    if (!parks.length) return showError(err, t("live.err.park"));
    if ((st.locOptions || []).length > 1 && !st.loc) return showError(err, t("live.err.loc"));
    showError(err, ""); $("#doneCard").hidden = true;
    const r = await api.start_live(parks.join(","), st.call, st.loc || "");
    if (!r.ok) return showError(err, r.error);
    enterRunning(r.parks, r.start);
  }
  $("#startLive").addEventListener("click", startLive);

  const refHtml = (p) => `<span class="ref">${refInner(p)}</span>`;
  async function enterRunning(parks, start) {
    st.spots.clear(); st.qsos.clear(); st.lastAt = 0; st.start = utcMs(start); st.cheered = false; st.parks = parks; st.seq = 0;
    $("#liveIdle").hidden = true; $("#liveRun").hidden = false; $("#liveDot").hidden = false;
    $("#signParks").innerHTML = parks.map((p) =>
      `<div class="sign-park">${refHtml(p)}<span class="name" data-ref="${esc(p)}"></span></div>`).join("");
    $("#barParks").innerHTML = parks.map(refHtml).join(JOIN);
    $("#liveStatus").textContent = t("live.status.first");
    for (const q of await api.session_qsos(start, parks.join(","))) { q.seq = ++st.seq; st.qsos.set(q.uid, q); huntedNow(q).forEach((p) => st.huntedShown.add(p)); }
    st.lastQ = Date.now() / 1000 - 1;
    st.cheered = st.qsos.size >= 10;            // re-opened mid-activation: don't celebrate twice
    renderSpots(); renderQsos();
    tick(); clearInterval(st.timer); st.timer = setInterval(tick, 1000);
    poll(); clearInterval(st.poll); st.poll = setInterval(poll, 2500);
    setBar(true);
    fillParkNames("#signParks", parks);
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
    let removed = false;
    for (const e of r.events) { st.lastAt = Math.max(st.lastAt, e.at); st.spots.set(e.call, e); freshS.add(e.call); }
    // the next QSO closes a celebration still up (FT4 or a CW 599 BK one leaves several seconds)
    if (r.qsos.some((q) => q.action !== "delete" && q.live)) hideCelebrations();
    for (const q of r.qsos) {
      st.lastQ = Math.max(st.lastQ, q.at);
      if (q.action === "delete") {                 // Python sends every copy it deleted
        (q.uids || []).forEach((u) => { removed = st.qsos.delete(u) || removed; });
        toast(t("live.deleted", { call: q.call }));
        continue;
      }
      if (!q.live) continue;                       // Python: not this session's (another park, before the start)
      for (const k of q.twins || []) {             // the same contact already shown (WSJT-X start time vs logger end time)
        const v = st.qsos.get(k); if (!v) continue;
        if (!q.decision && v.decision) Object.assign(q, { decision: v.decision, parks: v.parks });
        st.qsos.delete(k);
      }
      q.seq = (st.qsos.get(q.uid) || {}).seq || ++st.seq;   // arrival order breaks ties in the sort
      st.qsos.set(q.uid, q); freshQ.add(q.uid);
      hunted(q);                                   // decided as it arrived (設定 → P2P, or typed in the logger)
    }
    if (freshS.size || freshQ.size || removed) { renderSpots(freshS); renderQsos(freshQ); }
  }
  function workedCalls() { return new Set([...st.qsos.values()].map((q) => baseCall(q.call))); }
  function spotRow(e, worked, fresh, page) {
    return `
      <li class="spot${e.twofer ? " is-twofer" : ""}${worked ? " is-worked" : ""}${fresh ? " is-new" : ""}${page && e.ago >= 30 ? " is-stale" : ""}">
        <span class="spot-time">${esc(e.time)}Z</span>
        <span class="spot-call">${esc(e.call)}${worked ? `<span class="worked-tag">${t("spots.worked")}</span>` : ""}</span>
        <span class="plates">${e.country ? `<span class="flag" title="${esc(countryName(e.country))}">${flagOf(e.country)}</span>` : ""}${plates(e.parks, e.new)}${e.twofer ? `<span class="twofer-tag">${e.parks.length}fer</span>` : ""}${newTag(e.new)}${e.qrt ? `<span class="qrt-tag">QRT</span>` : ""}</span>
        <span class="spot-meta"><span class="spot-freq">${fmtFreq(e.freq)}</span>${e.mode ? `<span class="spot-mode">${esc(e.mode)}</span>` : ""}</span>
        ${page ? `<span class="spot-ago">${e.ago ? t("spots.ago", { n: e.ago }) : t("spots.now")}</span>
        <span class="spot-note" title="${esc(e.comments)}">${esc(e.comments)}</span>` : ""}
      </li>`;
  }
  function renderSpots(fresh) {
    const worked = workedCalls(), home = st.country || homeOf(st.parks);
    $("#segHome").innerHTML = `<span class="flag">${flagOf(home)}</span> ${esc(countryName(home))}`;
    const list = [...st.spots.values()].filter((e) => !st.prefix || e.parks.some((p) => p.startsWith(home + "-")))
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
    else if (p2p) ctl = `<span class="p2p-tag">P2P</span><span class="plates">${plates(q.parks, q.new)}</span>${newTag(q.new.filter((p) => q.parks.includes(p)))}<button class="link" data-act="edit" data-uid="${esc(q.uid)}">${t("row.change")}</button>`;
    else if (q.decision === "no") ctl = `<span class="qso-none">${t("row.none")}</span><button class="link" data-act="edit" data-uid="${esc(q.uid)}">${t("row.change")}</button>`;
    else if (q.candidate.length) ctl = `<span class="ask-text">${t("row.ask")}</span><span class="plates">${plates(q.candidate, q.new)}</span>${newTag(q.new)}${q.note ? `<span class="ask-note">${esc(t("row.note." + q.note))}</span>` : ""}
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
  // Party poppers over a celebration: two, at the bottom corners, each firing a cloud of paper confetti up
  // toward the middle; the pieces flip and flutter side to side down to the bottom of the window. It plays
  // whatever the OS motion setting says: it is a few seconds and the operator asked for it (Windows had
  // "Animation effects" off on the owner's PC, and the still version looked like nothing happened).
  const CONFETTI = ["#F2C46B", "#F4F1E4", "#7FC79F", "#E9A9A0", "#8EC5FF", "#C9A0F0"];
  // -> a promise that settles when the last piece is gone
  function burst(perPopper = 36) {
    const done = [], W = innerWidth, H = innerHeight;
    [[W * .05, H * .98, 1], [W * .95, H * .98, -1]].forEach(([x0, y0, dir]) => {
      for (let i = 0; i < perPopper; i++) {
        const el = document.createElement("i");
        el.className = "confetti"; el.style.background = CONFETTI[(i + (dir > 0 ? 0 : 3)) % CONFETTI.length];
        if (i % 3 === 0) el.classList.add("is-long");                       // some strips among the squares
        el.style.left = x0 + "px"; el.style.top = y0 + "px";
        document.body.appendChild(el);
        const tx = dir * W * (.12 + Math.random() * .48), ty = -H * (.5 + Math.random() * .4);   // the arc's top
        const rnd = (a, b) => a + Math.random() * (b - a);
        const r = rnd(0, 360), spin = (Math.random() < .5 ? -1 : 1) * rnd(200, 900);
        const fall = -ty + H * .03, drift = rnd(-.12, .12) * W, apex = rnd(.12, .26);
        // flip: scaleY swings through 0 so a piece seems to turn over as it falls
        const at = (x, y, rot, sy, o, offset, easing) => ({ transform: `translate(${x}px, ${y}px) rotate(${rot}deg) scaleY(${sy})`,
                                                            opacity: o, ...(offset != null && { offset }), ...(easing && { easing }) });
        const frames = [at(0, 0, r, 1, 1, 0, `cubic-bezier(.1, ${rnd(.7, .9)}, .3, 1)`),        // shot out of the popper
                        at(tx, ty, r + spin * .3, 1, 1, apex, "ease-in-out")];                  // top of the arc
        // then flutter down: each piece its own number of swings, widths, timing and flips
        const n = 3 + Math.floor(Math.random() * 5);
        let side = Math.random() < .5 ? -1 : 1, f = 0;
        for (let k = 1; k <= n; k++) {
          f = Math.min(.97, f + (1 / (n + 1)) * rnd(.6, 1.4));
          side = Math.random() < .8 ? -side : side;
          frames.push(at(tx + drift * f + side * rnd(8, 50) * (1 - f * .5), ty + fall * f * rnd(.9, 1), r + spin * (.3 + f * .7) + rnd(-40, 40),
                         rnd(-1, 1), 1, apex + f * (.95 - apex), "ease-in-out"));
        }
        frames.push(at(tx + drift, ty + fall, r + spin, rnd(-1, 1), 0));                      // gone at the bottom
        const anim = el.animate(frames, { duration: rnd(2700, 4800), delay: rnd(0, 260), fill: "forwards" });
        done.push(anim.finished.then(() => el.remove(), () => el.remove()));
      }
    });
    return Promise.all(done);
  }
  // A celebration closes when its poppers are done (at least 3 s), on a click or
  // Esc, or when the next QSO arrives; a newer celebration is not closed by an older one's end.
  function celebrate(sel, poppers) {
    const id = (celebrate.id = (celebrate.id || 0) + 1);
    $(sel).hidden = false;
    Promise.all([poppers, new Promise((r) => setTimeout(r, 3000))]).then(() => { if (celebrate.id === id) $(sel).hidden = true; });
  }

  // Hunted!: a P2P that hunts a park the operator had never hunted (Python's mypota marks it "new"),
  // once per park per session; rows loaded when the session (re)opens don't celebrate
  const huntedNow = (q) => (q.decision && q.decision !== "no" ? (q.new || []).filter((p) => (q.parks || []).includes(p)) : []);
  function hunted(q) {
    const parks = huntedNow(q).filter((p) => !st.huntedShown.has(p));
    if (!parks.length) return;
    parks.forEach((p) => st.huntedShown.add(p));
    $("#huntedParks").innerHTML = plates(parks);
    $("#cheer").hidden = true; celebrate("#hunted", burst());
  }
  function hideCelebrations() { $("#hunted").hidden = true; $("#cheer").hidden = true; }
  $("#hunted").addEventListener("click", hideCelebrations);
  function cheer() {
    celebrate("#cheer", burst(48));
  }
  $("#cheer").addEventListener("click", () => ($("#cheer").hidden = true));

  async function decide(uid, decision, parks) {
    const r = await api.set_p2p(uid, decision, parks || "");
    if (!r.ok) { toast(r.error); return; }
    st.editing = null;
    for (const ev of r.events) { const old = st.qsos.get(ev.uid); if (old) st.qsos.set(ev.uid, { ...old, ...ev }); }
    renderQsos();
    if (st.qsos.get(uid)) hunted(st.qsos.get(uid));
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
  async function finishLive(e) {
    const pending = [...st.qsos.values()].filter((q) => !q.decision && q.candidate.length).length;
    const btns = [$("#finishLive"), $("#barFinish")];
    if (pending && !secondPress(e.currentTarget, t("live.finishArmed", { n: pending }), finishLabels, 6000)) {
      toast(t("live.finishPending", { n: pending }));
      return;
    }
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
  const sp = { items: [], worked: new Set(), region: "", country: "", group: "", band: "", q: "", twofer: false, newOnly: false, hideQrt: false, timer: null };
  const REGIONS = ["as", "eu", "na", "sa", "af", "oc"];      // continent codes from spots.continent_of
  async function loadSpotsPage() {
    const r = await api.spots_now();
    showError($("#spotsError"), r.ok ? "" : r.error);
    if (!r.ok) return;
    sp.items = r.items; sp.worked = new Set(r.worked || []);
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
      (!sp.newOnly || (e.new || []).length) && (!sp.hideQrt || !e.qrt) &&
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
  $("#spotsNew").addEventListener("change", (e) => { sp.newOnly = e.target.checked; renderSpotsPage(); });
  $("#spotsHideQrt").addEventListener("change", (e) => { sp.hideQrt = e.target.checked; renderSpotsPage(); });
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
      if (!secondPress(b, t("build.deleteArmed"), t("build.delete"))) return;
      const r = await api.delete_activation(b.dataset.date);
      if (!r.ok) { toast(r.error); return; }
      toast(t("build.deleted", { n: r.n }));
      setLogCount(r.log_count);
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
      if (!secondPress(b, t("build.deleteArmed"), t("ed.delete"))) return;
      const res = await api.delete_qso(b.closest("tr").dataset.uid);
      if (!res.ok) { toast(res.error); return; }
      toast(t("ed.deleted"));
      setLogCount(res.log_count);
      loadEditor();
    }));
  }
  $("#editorClose").addEventListener("click", () => { $("#editor").hidden = true; loadActs(ed.path || undefined); });
  $("#pickAdif").addEventListener("click", async () => { const r = await api.pick_adif(); if (r) renderActs(r); });
  $("#pickOut").addEventListener("click", async () => { const p = await api.pick_out(); if (p) { st.out = p; $("#outPath").textContent = p; } });

  const SRC_CLASS = { hunter: "src-ok", confirmed: "src-ok", manual: "src-ok", spot: "src-spot", log: "src-log", logspot: "src-log" };
  // POTA asks that logs are not uploaded 03-11 UTC (log processing); shown in the user's local time
  function uploadHoursHtml() {
    const now = new Date(), at = (h) => new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), h));
    const hm = (d) => d.toLocaleTimeString(st.lang, { hour: "2-digit", minute: "2-digit" });
    const busy = now.getUTCHours() >= 3 && now.getUTCHours() < 11;
    return `<p class="upload-hours${busy ? " is-now" : ""}">${esc(t(busy ? "res.hours.now" : "res.hours", { from: hm(at(3)), to: hm(at(11)) }))}</p>`;
  }
  function resultsHtml(r) {
    const files = r.summary || [];
    // every QSO of each file; P2P rows carry the other park(s) and how they were known; a switch hides the rest
    const row = (q) => `
          <div class="qrow${q.parks.length ? " is-p2p" : ""}"><span class="muted">${hhmm(q.time)}</span>
          <span class="qrow-call">${esc(q.call)}</span><span class="qrow-bm">${esc(q.band)} ${esc(q.mode)}</span>
          ${q.parks.length ? `<span class="plates">${plates(q.parks)}</span><span class="src ${SRC_CLASS[q.source] || "src-log"}">${esc(t("src." + q.source))}</span>` : ""}</div>`;
    return (files.length ? uploadHoursHtml() : "") + (files.length ? `<div class="res-tools"><label class="switch switch-sm"><input type="checkbox" class="res-p2p-only"><span class="switch-ui"></span><span>${esc(t("res.p2pOnly"))}</span></label></div>` : "") +
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
  const KINDS = [["n1mm", "N1MM"], ["wsjtx", "WSJT-X"], ["adif", "ADIF"], ["hamlog", "Turbo HAMLOG"]];
  const recvState = (l) => { const s = st.receiver[l.name]; return s && typeof s === "object" ? s : { code: l.enabled ? "" : "off", text: l.enabled ? "" : t("set.off") }; };
  const recvClass = (s) => (s.code === "error" || s.code === "badforward") ? "is-bad" : (s.code === "listening" || s.code === "receiving") ? "is-ok" : "";
  function renderListeners() {
    $("#listeners").innerHTML = st.listeners.map((l, i) => {
      const s = recvState(l);
      const hl = l.kind === "hamlog";          // no port: the app asks HAMLOG itself
      return `<div class="lis${hl ? " is-hamlog" : ""}" data-i="${i}">
        <label class="switch" title="${esc(t("set.toggle"))}"><input type="checkbox" data-k="enabled" ${l.enabled ? "checked" : ""}><span class="switch-ui"></span></label>
        <label>${esc(t("set.name"))}<input type="text" data-k="name" value="${esc(l.name)}"></label>
        <label>${esc(t("set.kind"))}<select data-k="kind">${KINDS.map(([v, k]) => `<option value="${v}"${l.kind === v ? " selected" : ""}>${k}</option>`).join("")}</select></label>
        ${hl ? `<p class="lis-note">${esc(t("set.hamlog.note"))}</p>` : `
        <label>${esc(t("set.port"))}<input type="text" inputmode="numeric" data-k="port" value="${esc(l.port)}"></label>
        <label>${esc(t("set.mc"))}<input type="text" data-k="multicast" placeholder="${esc(t("set.mc.ph"))}" value="${esc(l.multicast)}"></label>
        <label>${esc(t("set.fwd"))}<input type="text" data-k="forward" placeholder="${esc(t("set.fwd.ph"))}" value="${esc(l.forward)}"></label>`}
        <button class="link lis-del" data-del="${i}">${esc(t("set.del"))}</button>
        <div class="lis-state ${recvClass(s)}">${esc(s.text)}</div>
      </div>`;
    }).join("") || `<p class="muted">${esc(t("set.none"))}</p>`;
    $$("#listeners [data-k]").forEach((el) => el.addEventListener("change", () => {
      const l = st.listeners[+el.closest(".lis").dataset.i];
      l[el.dataset.k] = el.type === "checkbox" ? el.checked : el.value;
      if (el.dataset.k === "kind") renderListeners();          // HAMLOG hides the port fields
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
    showError($("#listenError"), r.ok ? "" : r.error);
    if (!r.ok) return;
    st.listeners = r.listeners; st.receiver = r.receiver || {}; renderListeners(); updateReceiver(st.receiver);
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
    box.hidden = false;
    showUpdate(txt, go);
  }
  // "v2.0.4 is out (you have v2.0.3)" + how it installs, or a link to the release page when it can't
  function showUpdate(txt, go) {
    txt.innerHTML = (upd.data_only ? t("upd.dataAvailable", { latest: esc(upd.data_latest), current: esc(upd.data_current || "-") })
                                   : t("upd.available", { latest: esc(upd.latest), current: esc(upd.current) })) + " " +
      (upd.can_install ? esc(t(upd.translocated ? "upd.install.dl" : "upd.install.swap"))
        : `<button class="link upd-page">${esc(t("upd.page"))}</button>`);
    const pg = txt.querySelector(".upd-page"); if (pg) pg.addEventListener("click", () => api.open_url(upd.page));
    go.hidden = !upd.can_install; go.disabled = false; go.textContent = t("upd.go");
  }
  $("#checkUpdate").addEventListener("click", () => checkUpdate(false));
  async function installUpdate(go, txt) {           // from the settings box or the startup modal
    if (!upd || !upd.asset) return;
    go.disabled = true; go.textContent = t("upd.downloading");
    const r = await api.install_update(upd.asset);
    if (!r.ok) { go.disabled = false; go.textContent = t("upd.go"); txt.textContent = r.error; return; }
    go.hidden = true;
    if (r.manual) { txt.innerHTML = t("upd.manual", { path: esc(r.manual) }); api.open_out(r.manual_dir); }
    else txt.textContent = t("upd.done", { v: upd.data_only ? t("ver.data", { v: upd.data_latest }) : upd.latest });
  }
  $("#updateGo").addEventListener("click", () => installUpdate($("#updateGo"), $("#updateText")));
  // At startup: check first and, when a newer release exists, ask in a modal (after the terms, if those are up).
  // A data-only release (the monthly pota.app park list) is quiet: a small link under the version, which
  // opens the settings box - no modal every month.
  async function promptUpdate() {
    await checkUpdate(true);
    if (!upd || !upd.newer) return;
    if (upd.data_only) { $("#dataUpd").hidden = false; return; }
    const show = () => { showUpdate($("#updModalText"), $("#updModalGo")); $("#updModal").hidden = false; };
    if ($("#terms").hidden) show(); else st.afterTerms = show;
  }
  $("#updModalLater").addEventListener("click", () => ($("#updModal").hidden = true));
  document.addEventListener("click", (e) => { const b = e.target.closest(".park-retired [data-url]"); if (b) api.open_url(b.dataset.url); });
  $("#dataUpd").addEventListener("click", () => { show("config"); cfgTab("app"); $("#update").hidden = false; showUpdate($("#updateText"), $("#updateGo")); });
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
    if (!/^[A-Z0-9/]{3,}$/.test(c)) return showError(err, t("cfg.calls.err"));       // = potacommon.CALL_RE
    showError(err, ""); $("#callNew").value = "";
    saveCalls(st.calls.includes(c) ? st.calls : [...st.calls, c], st.calls.length ? st.call : c);
  });
  $("#calls").addEventListener("click", (e) => {
    const b = e.target.closest("[data-del]"); if (!b) return;
    const err = $("#callsError");
    if (st.calls.length <= 1) return showError(err, t("cfg.calls.last"));
    showError(err, "");
    const calls = st.calls.filter((c) => c !== b.dataset.del);
    saveCalls(calls, calls.includes(st.call) ? st.call : calls[0]);
  });
  $("#liveCall").addEventListener("change", (e) => saveCalls(st.calls, e.target.value));
  $("#p2pAuto").addEventListener("change", (e) => api.save({ p2p_auto: e.target.checked }));
  function renderMypota() {
    const m = st.mypota || {}, day = (iso) => fmtDate(iso.slice(0, 10).replace(/-/g, ""));
    // one line per CSV: which file, and what was read from it (or that it is still missing)
    $("#mypotaStatus").innerHTML = [["hunter", "hunter_parks.csv"], ["activator", "activator_parks.csv"]].map(([k, file]) =>
      `<li class="${m[k] ? "" : "is-missing"}"><b>${esc(t("cfg.mypota.kind." + k))}</b><code>${file}</code>
        <span>${esc(m[k] ? t("cfg.mypota.count", { n: m[k].n, at: day(m[k].at) }) : t("cfg.mypota.missing"))}</span></li>`).join("");
    $("#spotsNewBox").hidden = !m.hunter;                 // "New" needs the hunter list
  }
  async function importMypota() {
    const r = await api.import_mypota();
    if (!r) return;
    if (!r.ok) { toast(r.error); return; }
    st.mypota = r.mypota; renderMypota(); toast(t("cfg.mypota.done"));
    if (!$("#view-record").hidden) loadRecord();
  }
  $("#mypotaPick").addEventListener("click", importMypota);

  // ---------- 実績: the imported CSVs plus the parks this app found since (mypota.record) ----------
  const rec = { data: null, kind: "hunted", q: "", added: false };
  async function loadRecord() { rec.data = await api.mypota_record(); renderRecord(); }
  function recRow(r) {
    // grey = from the imported CSV, green = found by this app since the import (a re-import turns it grey)
    const src = (key, mine, p) => `<span class="rec-src${mine ? " is-app" : ""}">${esc(t(key, p))}</span>`;
    const meta = rec.kind === "hunted"
      ? src("rec.src." + r.source, r.added) + (r.qsos ? `<span>${esc(t("rec.qsos", { n: r.qsos }))}</span>` : "")
      : (r.added ? "" : src("rec.src.csv", false)) + (r.app ? src("rec.appDays", true, { n: r.app }) : "") +
        `<span>${esc(t("rec.acts", { done: r.activations, n: r.attempts }))}</span><span>${esc(t("rec.qsos", { n: r.qsos }))}</span>`;
    return `<li class="rec">
      <span class="rec-date">${esc((rec.kind === "hunted" ? r.first : r.last) || "")}</span>
      <span class="rec-park"><span class="flag">${flagOf(r.ref.split("-")[0])}</span>${plate(r.ref)}<span class="rec-name" title="${esc(r.name || "")}">${esc(r.name || "")}</span>${statusTag(r.listed)}</span>
      <span class="rec-meta">${meta}</span></li>`;
  }
  function renderRecord() {
    const d = rec.data;
    if (!d) return;
    const empty = !d.hunted.length && !d.activated.length;
    $("#recEmpty").hidden = !empty; $("#recBody").hidden = empty;
    if (empty) return;
    const sum = (k, rows) => esc(t(k, { n: rows.length, added: rows.filter((r) => r.added).length }));
    $("#recSum").innerHTML = `<span>${sum("rec.sum.hunted", d.hunted)}</span><span>${sum("rec.sum.activated", d.activated)}</span>`;
    const q = rec.q.trim().toUpperCase();
    const rows = d[rec.kind].filter((r) => (!rec.added || r.added) && (!q || r.ref.includes(q) || (r.name || "").toUpperCase().includes(q)));
    $("#recList").innerHTML = rows.map(recRow).join("");
    $("#recList").hidden = !rows.length; $("#recNone").hidden = rows.length > 0;
    drawRecordMap(rows);
  }
  // The same rows on an OpenStreetMap map (Leaflet, ui/vendor): grey = from the CSV, green = this app.
  // Park positions come from the shipped park list (grid); only the map tiles are fetched.
  function drawRecordMap(rows) {
    const Lf = window.L;                      // Leaflet (L in this file is the dictionary)
    if (!Lf) return;
    if (!rec.map) {
      rec.map = Lf.map("recMap", { preferCanvas: true, worldCopyJump: true, zoomControl: true }).setView([20, 0], 2);
      Lf.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(rec.map);
      rec.dots = Lf.layerGroup().addTo(rec.map);
    }
    rec.map.invalidateSize();
    rec.dots.clearLayers();
    const pts = [];
    for (const r of [...rows].sort((a, b) => a.added - b.added)) {     // green on top of grey
      if (!r.at) continue;
      pts.push(r.at);
      const c = r.added ? "#2F9E6B" : "#7D8A83";     // a park pota.app retired: a hollow ring
      Lf.circleMarker(r.at, r.listed === "retired" ? { radius: 5, weight: 2, color: c, fillOpacity: 0 }
                                                   : { radius: 5, weight: 1, color: "#fff", fillOpacity: .9, fillColor: c })
        .bindTooltip(`${esc(r.ref)} ${esc(r.name || "")}`).addTo(rec.dots);
    }
    // frame the dots when the list changes kind or filter, not on every redraw of the same list
    const key = rec.kind + "|" + rec.q + "|" + rec.added + "|" + pts.length;
    if (pts.length && key !== rec.framed) { rec.map.fitBounds(pts, { padding: [24, 24], maxZoom: 9 }); rec.framed = key; }
  }
  $$(".rec-kind button").forEach((b) => b.addEventListener("click", () => { rec.kind = b.dataset.kind; segSet(".rec-kind", "kind", rec.kind); renderRecord(); }));
  $("#recSearch").addEventListener("input", (e) => { rec.q = e.target.value; renderRecord(); });
  $("#recAdded").addEventListener("change", (e) => { rec.added = e.target.checked; renderRecord(); });
  $("#recPick").addEventListener("click", importMypota);
  $("#recReimport").addEventListener("click", importMypota);

  // ---------- 履歴: what the app received (qsolog.history), read-only; grouped by UTC day ----------
  const hist = { rows: [], parks: {}, q: "" };
  async function loadHistory() { const r = await api.qso_history(); hist.rows = r.rows; hist.parks = r.parks; renderHistory(); }
  const histPlates = (refs) => refs.map((p) => plate(p) + statusTag(hist.parks[p])).join(JOIN);
  function renderHistory() {
    const q = hist.q.trim().toUpperCase();
    const rows = hist.rows.filter((r) => !q || r.call.toUpperCase().includes(q) || r.my.concat(r.their).some((p) => p.includes(q)));
    const per = {};
    rows.forEach((r) => (per[r.date] = (per[r.date] || 0) + 1));
    let day = "", html = "";
    for (const r of rows) {
      if (r.date !== day) {
        day = r.date;
        html += `<li class="hist-day"><b>${esc(`${day.slice(0, 4)}-${day.slice(4, 6)}-${day.slice(6, 8)}`)}</b><span>${esc(t("rec.qsos", { n: per[day] }))}</span></li>`;
      }
      const p2p = r.their.length ? `<span class="hist-p2p">P2P</span>${histPlates(r.their)}`
        : r.p2p === "no" ? `<span class="muted">${esc(t("hist.noP2p"))}</span>` : "";
      html += `<li class="hist-row"><span class="rec-date">${hhmm(r.time)}Z</span><span class="hist-call">${esc(r.call)}</span>
        <span class="hist-bm">${esc(r.band)} ${esc(r.mode)}</span><span class="hist-parks">${histPlates(r.my)}</span>
        <span class="hist-their">${p2p}</span><span class="hist-src">${esc(r.source)}</span>
        <button type="button" class="link hist-del" data-uid="${esc(r.uid)}">${esc(t("ed.delete"))}</button></li>`;
    }
    $("#histList").innerHTML = html;
    $("#histList").hidden = !rows.length; $("#histNone").hidden = rows.length > 0;
    $("#histCount").textContent = t("hist.count", { n: rows.length });
  }
  $("#histSearch").addEventListener("input", (e) => { hist.q = e.target.value; renderHistory(); });
  $("#histList").addEventListener("click", async (e) => {         // one contact, with its copies (two presses)
    const b = e.target.closest(".hist-del");
    if (!b || !secondPress(b, t("build.deleteArmed"), t("ed.delete"))) return;
    const r = await api.delete_qso(b.dataset.uid);
    if (!r.ok) { toast(r.error); return; }
    hist.rows = hist.rows.filter((x) => x.uid !== b.dataset.uid); renderHistory();
    setLogCount(r.log_count); toast(t("ed.deleted"));
  });

  // 設定 → アプリ → 内部データ: the app's QSO log, decisions, sessions and spot recordings (two presses)
  $("#clearData").addEventListener("click", async (e) => {
    if (!secondPress(e.currentTarget, t("cfg.data.armed"), t("cfg.data.clear"), 6000)) return;
    const r = await api.clear_app_data();
    if (!r.ok) { toast(r.error); return; }
    setLogCount(r.log_count); toast(t("cfg.data.done", { n: r.n }));
  });
  $("#onTop").addEventListener("change", (e) => api.set_on_top(e.target.checked));

  // ---------- click a park plate or a callsign: copy, or open it on the web ----------
  const LOOKUP = {         // where 設定 → コールサインの検索先 sends a callsign
    qrz: ["QRZ.com", (c) => `https://www.qrz.com/db/${encodeURIComponent(c)}`],
    hamqth: ["HamQTH", (c) => `https://www.hamqth.com/${encodeURIComponent(c)}`],
    qrzcq: ["QRZCQ", (c) => `https://www.qrzcq.com/call/${encodeURIComponent(c)}`],
    hamcall: ["HamCall.net", (c) => `https://hamcall.net/call?callsign=${encodeURIComponent(c)}`],
    soumu: ["総務省 無線局等情報検索", (c) => `https://www.tele.soumu.go.jp/musen/SearchServlet?SK=2&DC=100&SC=1&pageID=3&CONFIRM=0&SelectID=1&CONTENTS=&SelectOW=01&IT=A&HC=&HV=&FF=&TF=&HZ=3&NA=&MA=${encodeURIComponent(c)}&DFY=&DFM=&DFD=&DTY=&DTM=&DTD=&SN=1`],
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
                                     // the sites know the licensed call: JF1AWC/1, JA1XXX/P -> JF1AWC, JA1XXX
                                     ...sites.map((site) => [t("pop.call", { site: site[0] }), () => api.open_url(site[1](baseCall(call)))]),
                                     [t("pop.profile"), () => api.open_url(`https://pota.app/#/profile/${encodeURIComponent(baseCall(call))}`)]]);
    }
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("#pop").hidden = true; hideCelebrations(); } });
  $("#openData").addEventListener("click", () => api.open_data());
  // 設定 tabs: one group of blocks at a time
  function cfgTab(tab) {
    segSet(".cfg-tabs", "tab", tab);
    $$(".cfg-block").forEach((el) => (el.hidden = el.dataset.tab !== tab));
  }
  $$(".cfg-tabs button").forEach((b) => b.addEventListener("click", () => cfgTab(b.dataset.tab)));
  cfgTab("general");
  $("#lang").addEventListener("change", async (e) => {
    await api.save({ lang: e.target.value }); await loadLang(e.target.value); rerender();
  });
  // 所在国: "my country" on the live spots switch, the アクティベート中 page's first country, the example parks
  async function setCountry(cc) {
    st.country = cc; st.ex = await api.examples(cc); sp.country = cc;
  }
  $("#country").addEventListener("change", async (e) => {
    await api.save({ country: e.target.value }); await setCountry(e.target.value); await loadLang(st.lang); rerender();
  });
  // first run: the region of the system language ("en-GB" -> GB), else the language's main country
  const LANG_COUNTRY = { ja: "JP", en: "US", "zh-CN": "CN", "zh-TW": "TW", fr: "FR", de: "DE", es: "ES", it: "IT", "pt-BR": "BR", ko: "KR", pl: "PL" };
  const guessCountry = (tag, lang) => { const m = /-([a-z]{2})(?:-|$)/i.exec(String(tag || "").replace("_", "-"));
    const cc = m ? m[1].toUpperCase() : LANG_COUNTRY[lang] || ""; return st.countries.includes(cc) ? cc : ""; };

  // ---------- boot ----------
  async function boot() {
    api = window.pywebview.api;
    const s = await api.get_state();
    Object.assign(st, { call: s.call || "", calls: s.calls || [], prefix: s.prefix, out: s.out, adif: s.adif, source: s.source || "app", listeners: s.listeners,
                        langs: s.langs || [["ja", "日本語"]], termsAccepted: s.terms_accepted || "", countries: s.countries || [] });
    $("#lang").innerHTML = st.langs.map(([c, name]) => `<option value="${esc(c)}">${esc(name)}</option>`).join("");
    const lang = s.lang || pickLang(navigator.language);
    if (!s.lang) api.save({ lang });
    const country = s.country || guessCountry(navigator.language, lang);
    if (!s.country && country) api.save({ country });
    await setCountry(country);
    await loadLang(lang);
    $("#version").textContent = `v${s.version}`;
    st.dataVersion = s.data_version || "";
    $("#dataVersion").textContent = st.dataVersion ? t("ver.data", { v: st.dataVersion }) : "";
    renderCalls(); $("#p2pAuto").checked = !!s.p2p_auto; $("#onTop").checked = !!s.on_top;
    st.lookup = s.lookup || ["qrz"]; renderLookup();
    st.mypota = s.mypota || {}; renderMypota();
    setParks(s.parks);
    $("#outPath").textContent = s.out;
    setLogCount(s.log_count);
    segSet("#liveRun .seg", "prefix", st.prefix);
    renderListeners(); updateReceiver(s.receiver);
    setSource(st.source);
    if (s.live) enterRunning(s.live.parks, s.live.start);
    if (st.termsAccepted !== TERMS_VERSION) showTerms(true);
    setTimeout(promptUpdate, 1500);                 // the first thing after the window is up
  }
  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener("pywebviewready", boot);
})();
