"use strict";
(function () {
  const BAR = location.hash === "#bar";      // this window is the bar (window.py BarMode)
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  let api = null;
  const st = {
    call: "", calls: [], prefix: "home", country: "", countries: [], ex: {}, spots: new Map(), qsos: new Map(), lastAt: 0, lastQ: 0,
    start: null, timer: null, poll: null, source: "app", adif: "", out: "", outDir: "",
    acts: [], selected: new Set(), listeners: [], receiver: {}, editing: null, bar: false, cheered: null,
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
        const locs = el.parentElement.querySelector(".pv-locs");          // the start screen: the park's prefectures / states
        if (locs) { locs.innerHTML = (i.locations || []).map((l) => `<span class="loc-tag" data-code="${esc(l.code)}" title="${esc(l.name || "")}">${esc(l.code)}</span>`).join(""); markShared(); }
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
  // 設定 → 表示: the text size (the web view's own zoom, set by Python: window.py set_zoom) and light / dark
  // (data-theme; "" = follow the OS). Both windows: the bar picks a change up in poll_live and grows with the text.
  const LOOK = { font_scale: 1, theme: "" };
  function applyLook(s) {
    const z = [1, 1.15, 1.3].includes(+s.font_scale) ? +s.font_scale : 1, th = ["light", "dark"].includes(s.theme) ? s.theme : "";
    if (z === LOOK.font_scale && th === LOOK.theme) return false;
    Object.assign(LOOK, { font_scale: z, theme: th });
    if (th) document.documentElement.dataset.theme = th; else delete document.documentElement.dataset.theme;
    segSet("#fontScale", "scale", String(z)); segSet("#themeSel", "theme", th);
    return true;
  }
  // distances: always "about" (a park is one point for the whole park); km or miles (設定 → 表示); one
  // decimal under 10, whole numbers with the language's thousands separator above
  const MILE_COUNTRIES = ["US", "GB", "LR", "MM"];
  const distUnit = () => st.distUnit || (MILE_COUNTRIES.includes(st.country) ? "mi" : "km");
  function fmtDist(km) {
    if (km == null) return "";
    const unit = distUnit(), v = unit === "mi" ? km / 1.609344 : km;
    const d = v < 10 ? v.toLocaleString(st.lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : Math.round(v).toLocaleString(st.lang);
    return t("dist.about", { d, u: unit === "mi" ? "mi" : "km" });
  }
  const distTag = (km) => (km == null ? "" : `<span class="dist">${esc(fmtDist(km))}</span>`);
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
    // one line per park: plate, name, which activation it would be (and a retired / unknown note)
    $("#parksPreview").innerHTML = parks.map((p) => `<div class="pv">${plate(p)}<span class="park-name" data-ref="${esc(p)}"></span><span class="pv-locs"></span><span class="park-act" data-act="${esc(p)}"></span></div>`).join("");
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
  // a 2fer / 3fer: the prefectures / states every park has, marked on each park's line
  function markShared() { $$("#parksPreview .loc-tag").forEach((e) => e.classList.toggle("is-shared", (st.sharedLocs || []).includes(e.dataset.code))); }
  function renderLoc(r) {
    const box = $("#parkLoc"); st.locOptions = r ? r.options : [];
    const warn = $("#parkApart");
    warn.hidden = !(r && r.apart && r.apart.length);
    if (!warn.hidden) warn.textContent = r.apart.map(([a, b]) => t("live.warn.apart", { a, b })).join(" ");
    // a note, not a warning: a park is one point here, so how far apart they are can't say whether they overlap
    const spread = $("#parkSpread");
    spread.hidden = !(r && r.spread_km != null) || !!r.none || !!(r.apart && r.apart.length);   // already known they can't
    if (!spread.hidden) spread.textContent = t("live.note.spread", { d: fmtDist(r.spread_km) });
    const linear = (r && r.linear) || [];
    $("#parkLinear").hidden = !linear.length;
    $("#parkLinear").textContent = t("live.note.linear", { park: linear.join(", ") });
    // they can't be one activation: no prefecture/state in common, or pota.app says they don't overlap
    st.noOverlap = !!(r && (r.none || (r.apart && r.apart.length)));
    $("#startLive").disabled = st.noOverlap; $("#startLive").classList.toggle("is-blocked", st.noOverlap);
    st.sharedLocs = r && splitParks(parkValue()).length > 1 ? r.options.map((o) => o.code) : [];
    markShared();
    if (!r || (!r.options.length && !r.multi.length && !r.none)) { box.hidden = true; st.loc = ""; return; }
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
    if (parks.length > 1 && st.noOverlap) { ($("#parkApart").hidden ? $("#parkLoc") : $("#parkApart")).scrollIntoView({ block: "nearest" }); return; }   // that row says why
    if ((st.locOptions || []).length > 1 && !st.loc) return showError(err, t("live.err.loc"));
    showError(err, ""); $("#doneCard").hidden = true;
    const r = await api.start_live(parks.join(","), st.call, st.loc || "", $("#liveOp").value);
    if (!r.ok) return showError(err, r.error);
    st.operators = { ...(st.operators || {}), [st.call]: r.operator };
    enterRunning(r);
  }
  $("#startLive").addEventListener("click", startLive);
  // a club station hands over without stopping: QSOs from now on carry the new OPERATOR
  $("#dashOp").addEventListener("change", async (e) => {
    const r = await api.set_operator(e.target.value);
    if (!r.ok) { toast(r.error); e.target.innerHTML = opOptions(st.operator); return; }
    st.operator = r.operator; e.target.value = r.operator; st.operators = { ...(st.operators || {}), [st.call]: r.operator }; showOperator(); e.target.innerHTML = opOptions(r.operator);
    if (r.operator) toast(t("live.operator.now", { op: r.operator }));
    else $("#dashOpBox").hidden = true;
  });

  const refHtml = (p) => `<span class="ref">${refInner(p)}</span>`;
  // live: {parks, start, locs, operator, shifts} from start_live, or get_state's running session
  async function enterRunning(live) {
    const { parks, start } = live;
    st.spots.clear(); st.qsos.clear(); st.lastAt = 0; st.start = utcMs(start); st.cheered = null; st.parks = parks; st.seq = 0;
    st.locs = live.locs || {}; st.day = utcDay(); st.shifts = live.shifts || {};
    // a new session (another park): the last place's notices and weather go; a reopened window takes what there is now
    notice.queue = []; $("#storm").hidden = true; document.body.classList.remove("has-storm");
    st.wxSeq = live.weather ? live.weather.seq : 0; renderWeather(live.weather || null, false);   // no notice for a reopened window
  // the bar opens with the session: a fresh start inside a shift plays its rise; a reopened bar does not
    st.shiftOn = BAR && Date.now() - utcMs(start) < 60e3 ? [] : activeShifts();
    st.operator = live.operator || ""; $("#dashOpBox").hidden = !st.operator; $("#dashOp").innerHTML = opOptions(st.operator);   // club station only
    $("#liveIdle").hidden = true; $("#liveRun").hidden = false; $("#liveDot").hidden = false;
    $("#signParks").innerHTML = parks.map((p) =>
      `<div class="sign-park">${plate(p)}<span class="name" data-ref="${esc(p)}"></span></div>`).join("");
    $("#barParks").innerHTML = parks.map(refHtml).join(JOIN);
    $("#liveStatus").textContent = t("live.status.first");
    for (const q of await api.session_qsos(start, parks.join(","))) { q.seq = ++st.seq; st.qsos.set(q.uid, q); huntedNow(q).forEach((p) => st.huntedShown.add(p)); }
    st.lastQ = Date.now() / 1000 - 1;
    renderSpots(); renderQsos(); if (!BAR) renderEvent();
    clearTimeout(st.timer); tick();
    st.pollOn = true; schedulePoll();
    if (!BAR) setBar(true);
    fillParkNames("#signParks", parks);
  }
  // the strip under the dashboard: QSOs in the last hour and the newest QSO (ts = UTC YYYYMMDDhhmmss)
  const tsMs = (ts) => Date.UTC(+ts.slice(0, 4), +ts.slice(4, 6) - 1, +ts.slice(6, 8), +ts.slice(8, 10), +ts.slice(10, 12), +ts.slice(12, 14) || 0);
  function renderStats() {
    const times = [...st.qsos.values()].filter((q) => q.ts && q.ts.length >= 12).map((q) => tsMs(q.ts));
    const now = Date.now(), last = times.length ? Math.max(...times) : 0;
    $("#statRate").textContent = times.filter((x) => now - x < 3600e3).length;
    $("#statLast").textContent = last ? new Date(last).toISOString().slice(11, 16) + "Z" : "–";
    const ago = last ? Math.floor((now - last) / 60000) : -1;
    $("#statAgo").textContent = ago < 0 ? "" : ago < 1 ? t("live.stat.now") : t("live.stat.ago", { n: ago });
  }
  function tick() {
    const ms = Date.now() - st.start, s = Math.max(0, Math.floor(ms / 1000));
    clearTimeout(st.timer); st.timer = setTimeout(tick, 1000 - (((ms % 1000) + 1000) % 1000) + 20);   // the next whole second
    const p = (n) => String(n).padStart(2, "0");
    const tm = `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
    $("#elapsed").textContent = tm; $("#barElapsed").textContent = tm;
    if (!BAR && s % 15 === 0) renderStats();      // "N 分前" and the last hour move on with the clock
    if (utcDay() !== st.day) newDay();            // 0000Z: a new activation starts, the session goes on
    else if (s % 15 === 0) renderCount();         // the minutes left before 0000Z
    if (!BAR && s % 15 === 0) renderEvent();
    if (BAR) skyTick();
  }
  // Poll every second on the second, in both windows: a QSO (and its celebration) shows in the main window
  // and the bar at the same moment (separate 2.5 s timers put the bar up to 2.5 s behind)
  function schedulePoll() {
    clearTimeout(st.poll);
    st.poll = setTimeout(async () => { try { await poll(); } finally { if (st.pollOn) schedulePoll(); } }, 1000 - (Date.now() % 1000) + 30);
  }
  async function poll() {
    const r = await api.poll_live(st.lastAt, st.lastQ);
    if (BAR && !r.running) { api.set_bar(false); return; }             // finished in the main window
    if (BAR && r.look && applyLook(r.look)) { st.barW = 0; fitBar(); }  // 設定 → 表示 changed in the main window
    if (r.status) $("#liveStatus").textContent = r.status;
    if (r.weather && r.weather.seq !== st.wxSeq) { st.wxSeq = r.weather.seq; renderWeather(r.weather, true); }
    else if (!r.weather && st.weather) renderWeather(null, false);   // a new place: nothing of the last one until its own look
    if (!BAR) {
      $("#clockWarn").hidden = r.clock == null;
      if (r.clock != null) $("#clockWarn").textContent = t(r.clock > 0 ? "live.warn.clockAhead" : "live.warn.clockBehind", { m: Math.max(1, Math.round(Math.abs(r.clock) / 60)) });
    }
    if (!BAR && "bar" in r && Date.now() - (st.barSetAt || 0) > 3000) showBarOn(r.bar);   // not an answer older than our own switch
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
      if (q.action === "update") {                 // a P2P answer given in the other window (main / bar)
        const old = st.qsos.get(q.uid);
        if (old) { st.qsos.set(q.uid, { ...old, ...q, at: old.at, seq: old.seq }); removed = true; }
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
      if (BAR) { if (!$("#ask").hidden) blinkAsk(); if (!q.decision && q.candidate.length) ask.q.push(q.uid); }
    }
    if (freshS.size || freshQ.size || removed) { renderSpots(freshS); renderQsos(freshQ); }
    if (BAR) { askNext(); fitBar(); }
  }
  function workedCalls() { return new Set([...st.qsos.values()].map((q) => baseCall(q.call))); }
  // An activation is one park at one location on one UTC day: the 10-QSO count is today's distinct count keys
  // (Python's count_key: date|location|CALL|band|mode) at the session's location, the smallest over its parks.
  const utcDay = (ms = Date.now()) => new Date(ms).toISOString().slice(0, 10).replace(/-/g, "");
  function dayCount(day) {
    const list = [...st.qsos.values()], parks = st.parks || [];
    const per = parks.map((p) => {
      const head = `${day}|${st.locs[p] || ""}|`;
      return [p, new Set(list.map((q) => (q.ck || {})[p] || (q.ck || {})["*"]).filter((k) => k && k.startsWith(head))).size];
    });
    return { per, n: per.length ? Math.min(...per.map((x) => x[1])) : 0 };
  }
  function newDay() {
    const prev = st.day; st.day = utcDay();
    const { n } = dayCount(prev);
    st.cheered = 0;                               // the next 10 is a new activation: celebrate it
    if (!BAR) toast(t("live.newDay", { n, state: t(n >= 10 ? "live.newDay.ok" : "live.newDay.short") }));
    renderQsos();
  }
  // POTA event periods (Python sends their UTC dates) and the Early / Late Shift hours of these parks, beside 運用中
  const SHIFT_NAMES = { early: "Early Shift", late: "Late Shift" }, SHIFT_LOCAL = { early: 2, late: 18 };   // local start hour
  // the shifts on now: st.shifts = {early: [UTC hour it starts, hours long], late: [...]} from Python
  const activeShifts = () => {
    const h = new Date(Date.now()).getUTCHours();
    return Object.keys(SHIFT_NAMES).filter((k) => { const w = (st.shifts || {})[k]; return w && (h - w[0] + 24) % 24 < w[1]; });
  };
  function renderEvent() {
    const now = Date.now();
    const names = (st.events || []).filter((e) => Date.parse(e.start) <= now && now < Date.parse(e.end)).map((e) => e.name);
    $("#dashEvent").textContent = names.concat(activeShifts().map((k) => SHIFT_NAMES[k])).join(" · ");
    $("#dashEvent").hidden = !$("#dashEvent").textContent;
  }
  // The weather at the parks (Python asks Open-Meteo at the start and every 15 min: weather.py). One line on the
  // 運用中 page; an alert (thunderstorm, rain, strong gusts within 3 h) turns it amber, shows a short word in the bar
  // and, when it is new, a toast. Open-Meteo's data is CC BY 4.0: its credit links to it wherever it shows.
  const WX_ICON = { clear: "☀️", cloudy: "⛅", overcast: "☁️", fog: "🌫️", drizzle: "🌦️", rain: "🌧️", snow: "❄️", showers: "🌦️", thunder: "⛈️" };
  const fmtTemp = (c) => (distUnit() === "mi" ? Math.round(c * 9 / 5 + 32) + "°F" : Math.round(c) + "°C");
  const fmtWind = (ms) => (distUnit() === "mi" ? Math.round(ms * 2.237) + " mph" : Math.round(ms) + " m/s");
  function renderWeather(w, notify) {
    const line = $("#wxLine"), alerts = Object.keys((w && w.alerts) || {});
    // Japan: the JMA's warnings (Python: jma.py) are alerts "jma:<code>"; the rest are the forecast's (Open-Meteo)
    const om = alerts.filter((k) => !k.startsWith("jma:")), official = (w && w.jma) || [];
    const jmaName = (x) => t("jma." + x.code);
    // the bar's weather: one short line - the gravest of the JMA's (how many more, where), else the forecast's words
    const barLine = official.length ? jmaName(official[0]) + (official.length > 1 ? " " + t("wx.more", { n: official.length - 1 }) : "") +
      (w && w.jma_place ? t("jma.at", { place: w.jma_place }) : "") : om.map((k) => t("wx.short." + k)).join(" · ");
    const alertText = (k) => { const a = w.alerts[k] || {};
      return t("wx.alert." + k, { when: whenText(a.in), p: a.p, g: fmtWind(a.g || 0) }); };
    line.hidden = !w;
    st.weather = w;
    if (!w) {                                    // no look yet (a new place): nothing of the last one stays up
      notice.queue = []; $("#storm").hidden = true; document.body.classList.remove("has-storm");
      if (lmap.tab === "weather") renderWxTab();
      return;
    }
    // one line, never wrapped: what it is like now, the gravest warning (and how many more), and the 天気 tab for the rest
    const parts = [`${WX_ICON[w.group] || ""} ${t("wx.k." + w.kind)}`];
    if (w.temp != null) parts.push(fmtTemp(w.temp));
    if (w.wind != null) parts.push(t("wx.windShort", { v: fmtWind(w.wind) }));
    const top = official[0];
    line.innerHTML = `<span class="wx-now">${esc(parts.join(" · "))}</span>` +
      (top ? `<span class="jma jma-l${top.level}" title="${esc(w.jma_place || "")}">${esc(jmaName(top))}</span>` + (official.length > 1 ? `<span class="wx-more">${esc(t("wx.more", { n: official.length - 1 }))}</span>` : "") : "") +
      om.map((k) => `<span class="wx-alert">${esc(t("wx.short." + k))}</span>`).join("") +
      `<button class="link wx-open">${esc(t("wx.details"))}</button><button class="link wx-src wx-src-line" data-url="https://open-meteo.com/">Open-Meteo</button>`;
    line.classList.toggle("is-alert", alerts.length > 0);
    if (lmap.tab === "weather") renderWxTab();
    const fresh = w.new || [], notices = fresh.filter((k) => noticeOf(k, w));
    if (notify && !BAR) {                  // the rest: one toast (the notices below have their own screen)
      const words = fresh.filter((k) => !k.startsWith("jma:") && !noticeOf(k, w)).map(alertText);
      const named = official.filter((x) => fresh.includes("jma:" + x.code) && !noticeOf("jma:" + x.code, w)).map(jmaName);
      if (named.length) words.unshift(t("jma.new", { names: named.join("・") }) + (w.jma_place ? t("jma.at", { place: w.jma_place }) : ""));
      if (words.length) toast(words.join(" "));
    }
    if (notify && notices.length) showNotices(notices, w);   // thunder and wind: their own notice, apart from the weather
    // the bar: the first look of a recording, and a new alert, play the weather over the bar
    if (notify && BAR && (w.first || fresh.length)) playWx(w, barLine ? [barLine] : []);
  }
  // A thunderstorm on the way is dangerous at a park with an antenna up: both windows put a yellow screen over
  // everything with what to do, flashing for a few seconds, and it stays until the operator closes it.
  // What matters to a station in the field - lightning and wind - has its own notice in both windows: the JMA's for a
  // park in Japan (its name, in its colour: advisory yellow, warning red, emergency purple), the forecast's elsewhere.
  // {alert key: [icon, level, title (null = the JMA's own name), body key, the bar's short body key]}
  const NOTICES = {
    "jma:14": ["bolt", 2, null, "wx.storm.jma", "wx.storm.jmaShort"],
    "jma:15": ["wind", 2, null, "wx.notice.windJma", "wx.notice.windJmaShort"],
    "jma:13": ["wind", 2, null, "wx.notice.windJma", "wx.notice.windJmaShort"],
    "jma:05": ["wind", 3, null, "wx.notice.stormJma", "wx.notice.stormJmaShort"],
    "jma:02": ["wind", 3, null, "wx.notice.stormJma", "wx.notice.stormJmaShort"],
    "jma:35": ["wind", 5, null, "wx.notice.emergency", "wx.notice.emergencyShort"],
    "jma:32": ["wind", 5, null, "wx.notice.emergency", "wx.notice.emergencyShort"],
    thunder: ["bolt", 2, "wx.storm.title", "wx.storm.body", "wx.alert.thunder"],
    wind: ["wind", 2, "wx.notice.windTitle", "wx.notice.wind", "wx.notice.windShort"],
  };
  // the JMA's colours by 警戒レベル相当: 2 yellow, 3 red, 4 purple, 5 black (pulsing toward a deeper shade)
  // every other JMA warning of 警報 or graver (大雨警報, 土砂災害危険警報 ...) has a notice too, in its level's colour;
  // 注意報 other than thunder and wind stay plates and a toast
  function noticeOf(key, w) {
    if (NOTICES[key]) return NOTICES[key];
    const a = (w.alerts || {})[key];
    if (!key.startsWith("jma:") || !a || a.level < 3) return null;
    return a.level >= 4 ? ["warn", a.level, null, "wx.notice.jmaDanger", "wx.notice.jmaDangerShort"]
      : ["warn", 3, null, "wx.notice.jmaWarn", "wx.notice.jmaWarnShort"];
  }
  const PULSE = { 2: ["#F2E700", "#FFB300"], 3: ["#FF2800", "#B81D00"], 4: ["#AA00AA", "#6E006E"], 5: ["#0C000C", "#3A2A3A"] };
  const notice = { queue: [] };
  // the new ones, gravest first, one at a time: closing one shows the next
  function showNotices(keys, w) {
    notice.queue = keys.map((k) => [k, w]).concat(notice.queue.filter(([k]) => !keys.includes(k)))
      .sort((a, b) => noticeOf(b[0], b[1])[1] - noticeOf(a[0], a[1])[1]);
    nextNotice();
  }
  function nextNotice() {
    const box = $("#storm"), item = notice.queue.shift();
    if (!item) { box.hidden = true; document.body.classList.remove("has-storm"); return; }
    const [key, w] = item, [icon, level, title, body, short] = noticeOf(key, w), a = w.alerts[key] || {};
    const words = { when: whenText(a.in), g: fmtWind(a.g || 0), name: key.startsWith("jma:") ? t("jma." + key.slice(4)) : "" };
    box.dataset.icon = icon; box.className = "storm lv" + level;
    // what a click does: the next notice (how many are left) or close - in the bar a click anywhere, in the main window the button
    const left = notice.queue.length;
    $("#stormHint").textContent = left ? t("wx.storm.hintNext", { n: left }) : t("wx.storm.hintClose");
    $("#stormOk").textContent = left ? t("wx.storm.next", { n: left }) : t("wx.storm.ok");
    // the JMA's: where it is in force too, so the operator knows the warning is for this place
    $("#stormName").textContent = title ? t(title) : t("jma." + key.slice(4)) + (w.jma_place ? t("jma.at", { place: w.jma_place }) : "");
    $("#stormBody").textContent = BAR ? t(short, words).replace(/^[^\p{L}\p{N}]+/u, "") : t(body, words);   // the bar: the short line, its mark is on the plate
    if (BAR) {                                     // the warning comes first: the sky stops and plays again after it
      if (!$("#sky").hidden && playSky.last) { const again = playSky.last; setTimeout(() => playSky(...again), 700); }
      playSky.id = (playSky.id || 0) + 1; playWx.id = (playWx.id || 0) + 1;
      $("#sky").hidden = true; $("#wxa").hidden = true; $("#wxaFx").innerHTML = "";
    }
    box.hidden = false; document.body.classList.add("has-storm");
    box.getAnimations().forEach((x) => x.cancel());
    const [c1, c2] = PULSE[level];
    box.animate([{ background: c1 }, { background: c2 }, { background: c1 }], { duration: 700, iterations: 5 });
  }
  const closeStorm = () => nextNotice();
  // when an alert comes: hours from now from Python (0 = this hour)
  const whenText = (n) => (!n ? t("wx.when.soon") : n === 1 ? t("wx.when.1") : t("wx.when.n", { n }));
  $("#stormOk").addEventListener("click", closeStorm);
  $("#storm").addEventListener("click", () => { if (BAR) closeStorm(); });
  // The weather over the bar for about 6 s (a click closes it), like a phone's weather app: the sky of its kind
  // (night when the next sun event is the sunrise), the sun or moon glowing through, clouds drifting, rain, snow, mist,
  // lightning or gusts (Web Animations API), and the temperature large. It waits for the sky (Early / Late Shift).
  function playWx(w, alertLines) {
    // one at a time in the bar: a warning notice, then the shift's sky, then the weather
    if (!$("#sky").hidden || !$("#storm").hidden) { setTimeout(() => playWx(w, alertLines), 700); return; }
    const box = $("#wxa"), fx = $("#wxaFx"), W = innerWidth, H = innerHeight, D = 5200, g = w.group;
    const rnd = (a, b) => a + Math.random() * (b - a);
    const id = (playWx.id = (playWx.id || 0) + 1);
    box.getAnimations({ subtree: true }).forEach((x) => x.cancel());
    fx.innerHTML = ""; box.dataset.g = g; box.hidden = false;
    if (w.sun && w.sun.kind === "sunrise") box.dataset.night = ""; else delete box.dataset.night;
    $("#wxaTemp").textContent = w.temp != null ? fmtTemp(w.temp).replace(/[CF]$/, "") : "";   // "18°" as a phone shows it
    $("#wxaMain").textContent = t("wx.k." + w.kind);
    $("#wxaSub").textContent = [w.wind != null ? t("wx.windShort", { v: fmtWind(w.wind) }) : "", w.rain != null ? t("wx.popShort", { p: w.rain }) : ""]
      .filter(Boolean).join(" · ");
    $("#wxaAlert").textContent = alertLines.join(" "); $("#wxaAlert").hidden = !alertLines.length;
    const add = (cls, css) => { const el = document.createElement("i"); el.className = cls; Object.assign(el.style, css); fx.appendChild(el); return el; };
    const wet = ["drizzle", "rain", "showers", "thunder"].includes(g);
    // the sun / moon glow: bright when it is clear, faint through thin cloud, none under rain
    const glow = { clear: 1, cloudy: .7 }[g] ?? 0, lv = w.level || 2;   // lv: 1 light, 2 moderate, 3 heavy
    if (glow) box.querySelector(".wxa-glow").animate([{ opacity: 0, transform: "scale(.85)" }, { opacity: glow, transform: "scale(1)" }],
                                                    { duration: 1400, easing: "ease-out", fill: "forwards" });
    // clouds drifting right, slowly, at a few heights; more and lower in bad weather
    const clouds = { clear: 0, cloudy: 3, overcast: 6, fog: 4, drizzle: 6, rain: 7, showers: 6, snow: 6, thunder: 7 }[g] ?? 3;
    for (let i = 0; i < clouds; i++) {
      const y = rnd(-.12, wet || g === "overcast" ? .25 : .45) * H, sc = rnd(.8, 1.5), x0 = rnd(-.3, .95) * W;
      add("wxa-cloud", { left: x0 + "px", top: y + 26 + "px", transform: `scale(${sc})` }).animate(
        [{ transform: `translateX(0) scale(${sc})` }, { transform: `translateX(${rnd(30, 70)}px) scale(${sc})` }], { duration: D + 800, easing: "linear", fill: "forwards" });
    }
    // rain and snow are already falling when the weather shows: each piece starts part-way through its fall (negative delay)
    if (wet) for (let i = 0; i < [0, 20, 34, 60][lv]; i++) {                         // rain: streaks falling, more and faster when heavy
      const dur = rnd(450, 700) * [0, 1.3, 1, .75][lv];
      add("wxa-drop", { left: rnd(-.05, 1.1) * W + "px", height: [0, 10, 14, 18][lv] + "px" }).animate(
        [{ transform: "translate(0, -20px) rotate(12deg)" }, { transform: `translate(-${H * .2}px, ${H + 20}px) rotate(12deg)` }],
        { duration: dur, delay: -rnd(0, dur), iterations: Math.ceil(D / 300), easing: "linear" });
    }
    if (g === "snow") for (let i = 0; i < [0, 12, 26, 50][lv]; i++) {                                 // snow: flakes drifting down, swaying
      const sway = rnd(10, 26);
      add("wxa-flake", { left: rnd(0, 1) * W + "px", opacity: rnd(.5, 1) }).animate([{ transform: "translate(0, -10px)" }, { transform: `translate(${sway}px, ${H * .5}px)` },
        { transform: `translate(${-sway}px, ${H + 10}px)` }], { duration: rnd(2200, 3400), delay: -rnd(0, 3400), iterations: 4, easing: "linear" });
    }
    if (g === "fog") for (let i = 0; i < 3; i++)                                     // mist: soft bands passing low
      add("wxa-band", { top: (40 + i * 20) + "%" }).animate([{ transform: "translateX(0)" }, { transform: `translateX(${W * 1.1}px)` }],
        { duration: rnd(5000, 7000), delay: -rnd(0, 4000), easing: "linear" });
    if (w.alerts && w.alerts.wind) for (let i = 0; i < 7; i++)                        // strong gusts: streaks blowing across
      add("wxa-gust", { top: rnd(.1, .9) * H + "px" }).animate([{ transform: "translateX(-80px)", opacity: 0 }, { opacity: 1, offset: .3 }, { transform: `translateX(${W + 80}px)`, opacity: 0 }],
        { duration: rnd(700, 1000), delay: -rnd(0, 1000), iterations: 6, easing: "ease-in" });
    if (g === "thunder")                                                             // lightning: two flashes
      box.querySelector(".wxa-flash").animate([{ opacity: 0 }, { opacity: 0, offset: .2 }, { opacity: .75, offset: .22 }, { opacity: 0, offset: .26 },
        { opacity: .5, offset: .29 }, { opacity: 0, offset: .34 }, { opacity: 0, offset: .62 }, { opacity: .7, offset: .64 }, { opacity: 0, offset: .7 }], { duration: D });
    $("#wxa .wxa-text").animate([{ opacity: 0, transform: "translateY(-50%) translateY(8px)" }, { opacity: 1, transform: "translateY(-50%)" }],
                                { duration: 800, delay: 250, fill: "backwards", easing: "ease-out" });
    setTimeout(() => {                              // then fade out (unless a newer weather took over)
      if (playWx.id !== id) return;
      // hidden by the clock, not the animation's end: a hidden or covered window may not run animations at all
      box.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 700, fill: "forwards" });
      setTimeout(() => { if (playWx.id === id) { box.hidden = true; fx.innerHTML = ""; } }, 720);
    }, D);
  }
  document.addEventListener("click", (e) => { const b = e.target.closest(".wx-src[data-url]"); if (b) api.open_url(b.dataset.url); });
  document.addEventListener("click", (e) => { if (e.target.closest(".wx-open")) liveTab("weather"); });
  // small drawn weather marks for the table (no emoji): sun / moon, cloud, rain, snow, lightning, mist
  function wxIcon(group, day) {
    const sun = day ? `<circle cx="12" cy="12" r="4.5" fill="#F5A623"/><g stroke="#F5A623" stroke-width="1.8" stroke-linecap="round">${
      [0, 45, 90, 135, 180, 225, 270, 315].map((a) => `<line x1="12" y1="3" x2="12" y2="5" transform="rotate(${a} 12 12)"/>`).join("")}</g>`
      : `<path d="M15.5 4.5a7.5 7.5 0 1 0 4 12.5 6 6 0 0 1-4-12.5z" fill="#C9B458"/>`;
    const cloud = (c, dy = 0) => `<path transform="translate(0 ${dy})" d="M7 18h10.5a3.5 3.5 0 0 0 .4-7A5 5 0 0 0 8.3 10.6 3.8 3.8 0 0 0 7 18z" fill="${c}"/>`;
    const drops = (c) => `<g stroke="${c}" stroke-width="1.6" stroke-linecap="round"><line x1="9" y1="19" x2="8" y2="22"/><line x1="13" y1="19" x2="12" y2="22"/><line x1="17" y1="19" x2="16" y2="22"/></g>`;
    const body = { clear: sun, cloudy: `<g transform="translate(-3 -3) scale(.8)">${sun}</g>${cloud("#AEB7C2", 2)}`, overcast: cloud("#8E99A6"),
      fog: `<g stroke="#9AA4AF" stroke-width="2" stroke-linecap="round"><line x1="4" y1="9" x2="20" y2="9"/><line x1="6" y1="13" x2="18" y2="13"/><line x1="4" y1="17" x2="20" y2="17"/></g>`,
      drizzle: cloud("#8E99A6", -3) + drops("#5B9BD5"), rain: cloud("#7D8996", -3) + drops("#2F7BD0"), showers: cloud("#7D8996", -3) + drops("#2F7BD0"),
      snow: cloud("#9AA5B1", -3) + `<g fill="#7FB3E6"><circle cx="9" cy="20" r="1.3"/><circle cx="13" cy="21.5" r="1.3"/><circle cx="17" cy="20" r="1.3"/></g>`,
      thunder: cloud("#5E6875", -3) + `<path d="M12.5 15 9.5 20h2.5l-1 3.5 4-5.5h-2.5l1-3z" fill="#F2C500"/>` }[group] || cloud("#AEB7C2");
    return `<svg class="wx-ic" viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  }
  // 天気 tab: the JMA's warnings and forecast for a park in Japan (its words, its credit), and Open-Meteo's hours
  // (park time) for any park; both looked at by Python every 15 minutes while recording
  function renderWxTab() {
    const w = st.weather, box = $("#liveWx");
    if (!w) { box.innerHTML = `<p class="muted wx-wait">${esc(t("wx.tab.wait"))}</p>`; return; }
    const jmaSrc = `<button class="link wx-src" data-url="https://www.jma.go.jp/bosai/forecast/">${esc(t("jma.src"))}</button>`;
    const hm = (iso) => (iso || "").slice(11, 16);
    // the park's point is one pin: a big park, or one near a border, may have other weather where the operator is
    let html = `<p class="wx-note">${esc(t("wx.tab.note"))}</p>`;
    // Japan, with a 警報 or graver in force: evacuation orders (避難指示 ...) come from the municipality, not the JMA,
    // and are not here - said where it matters, in amber
    if ((w.jma || []).some((x) => x.level >= 3)) html += `<p class="wx-note wx-note-evac">${esc(t("wx.tab.evac"))}</p>`;
    // say where: the JMA issues them for each municipality (not the prefecture or the region)
    if (w.jma) html += `<section class="wx-sec"><h3>${esc(w.jma_place ? t("wx.tab.jmaWarnAt", { place: w.jma_place }) : t("wx.tab.jmaWarn"))}<small>${esc(t("wx.tab.jmaBy"))}</small></h3>${w.jma.length
      // one row per class, gravest first: 特別警報 / 危険警報 / 警報 / 注意報 (警戒レベル相当 5-2), only the classes in force
      ? [5, 4, 3, 2].filter((lv) => w.jma.some((x) => x.level === lv)).map((lv) => `<div class="wx-class"><span class="wx-class-name">${esc(t("wx.lv." + lv))} / ${esc(t("wx.lv.eq", { n: lv }))}</span>
          <span class="wx-chips">${w.jma.filter((x) => x.level === lv).map((x) => `<span class="jma jma-l${x.level}" title="${esc(t("jma." + x.code))}">${esc(t("jma.p." + x.code))}</span>`).join("")}</span></div>`).join("")
      : `<span class="muted">${esc(t("wx.tab.none"))}</span>`}</section>`;
    const fc = w.jma_forecast;
    if (fc && fc.area) {
      const temps = fc.temps && fc.temps.list.length === 2 ? t("wx.fc.temps", { place: fc.temps.place, lo: fc.temps.list[0].t, hi: fc.temps.list[1].t }) : "";
      html += `<section class="wx-sec"><h3>${esc(t("wx.tab.jmaFc"))}<small>${esc(fc.area)} · ${esc(t("wx.fc.at", { at: hm(fc.at) }))}</small></h3>
        <div class="wx-days">${fc.days.map((d, i) => `<div class="wx-day"><b>${esc(t("wx.day." + i))}</b><span class="wx-day-w">${esc(d.weather)}</span>
          <small>${esc(t("wx.fc.wind"))} ${esc(d.wind)}${d.wave ? ` · ${esc(t("wx.fc.wave"))} ${esc(d.wave)}` : ""}</small></div>`).join("")}</div>
        ${fc.pops.length ? `<div class="wx-pops"><span>${esc(t("wx.fc.pop"))}</span>${fc.pops.map((p) => `<span class="wx-pop"><small>${esc(hm(p.at))}</small>${esc(p.p)}%</span>`).join("")}</div>` : ""}
        ${temps ? `<div class="wx-temps">${esc(temps)}</div>` : ""}<div class="wx-foot">${jmaSrc}</div></section>`;
    }
    const hours = w.hours || [];
    if (hours.length) {
      const row = (label, f) => `<tr><th>${esc(label)}</th>${hours.map((h) => `<td>${f(h)}</td>`).join("")}</tr>`;
      html += `<section class="wx-sec"><h3>${esc(t("wx.tab.om"))}<small>${esc(t("wx.tab.local"))}</small></h3><div class="wx-table-wrap"><table class="wx-table">
        ${row(t("wx.row.time"), (h) => `<b>${esc(h.t.slice(0, 2))}</b>`)}
        ${row(t("wx.row.weather"), (h) => `<span title="${esc(t("wx.k." + h.kind))}">${wxIcon(h.group, h.day)}</span>`)}
        ${row(t("wx.row.mm"), (h) => (h.mm != null ? `${esc(h.mm)}<small>mm</small>` : "–"))}
        ${row(t("wx.row.pop"), (h) => (h.pop != null ? `${esc(h.pop)}<small>%</small>` : "–"))}
        ${row(t("wx.row.temp"), (h) => (h.temp != null ? esc(fmtTemp(h.temp)) : "–"))}
        ${row(t("wx.row.wind"), (h) => (h.wind != null ? `<span class="wx-arrow" style="transform: rotate(${Number(h.dir) || 0}deg)">↓</span><br>${esc(fmtWind(h.wind))}` : "–"))}
      </table></div><div class="wx-foot"><button class="link wx-src" data-url="https://open-meteo.com/">Weather data by Open-Meteo.com</button></div></section>`;
    }
    box.innerHTML = html;
  }
  $("#wxa").addEventListener("click", () => { playWx.id = (playWx.id || 0) + 1; $("#wxa").hidden = true; $("#wxaFx").innerHTML = ""; });
  // The bar's sky, by the local hour of the shift (POTA's shifts are 15° bands: Late 18-02, Early 02-08 local):
  // Late starts at dusk (the moon rises), its second half and Early's first are the middle of the night (stars, the
  // moon high), Early's second half is the dawn (the sun rises) and it ends in the morning (the sun climbs into the
  // day). Late's end is Early's start (same band, same hour): that moment plays Early's night.
  // Layers' opacity at the start, middle, end; path = the orb's way.
  const SKY = {
    dusk: { orb: "moon", path: "rise", dusk: [1, .5, 0], night: [0, .7, 1], stars: [0, .6, 1], meteors: 1 },
    night: { orb: "moon", path: "drift", night: [1, 1, 1], stars: [.2, .8, 1], meteors: 2 },
    dawn: { orb: "sun", path: "rise", night: [1, .6, 0], dawn: [0, 1, 0], day: [0, 0, 1], stars: [1, .3, 0] },
    morning: { orb: "sun", path: "climb", dawn: [1, .3, 0], day: [0, .8, 1], stars: [0, 0, 0] },
  };
  function skyScene(shift, rise) {
    if (!rise) return shift === "early" ? "morning" : "night";
    const w = st.shifts[shift], half = (new Date(Date.now()).getUTCHours() - w[0] + 24) % 24 >= w[1] / 2;
    return shift === "early" ? (half ? "dawn" : "night") : (half ? "night" : "dusk");
  }
  function playSky(shift, rise) {
    if (!$("#storm").hidden) { setTimeout(() => playSky(shift, rise), 700); return; }   // a warning first: the sky after it
    playSky.last = [shift, rise];
    const sc = SKY[skyScene(shift, rise)], box = $("#sky"), orb = $("#skyOrb"), D = 4200;
    const w = st.shifts[shift];
    $("#skyName").textContent = SHIFT_NAMES[shift];
    const hh = (h) => String(h % 24).padStart(2, "0") + ":00", local = SHIFT_LOCAL[shift];
    // two lines: the park's local time by its 15° band (what a shift is: 02-08 / 18-02, whatever the computer's clock
    // is set to; real time zones and summer time may differ, as the docs say) and UTC
    $("#skyLine").textContent = rise ? t("sky.start", { from: hh(local), to: hh(local + w[1]) }) : t("sky.end");
    $("#skyLine").hidden = rise && w[0] === local;          // the band is UTC itself (around 0°): the UTC line only
    $("#skyUtc").textContent = rise ? t("sky.utc", { from: hh(w[0]), to: hh(w[0] + w[1]) }) : "";
    $("#skyUtc").hidden = !rise;
    orb.className = "sky-orb is-" + sc.orb;
    const id = (playSky.id = (playSky.id || 0) + 1);
    box.getAnimations({ subtree: true }).forEach((a) => a.cancel());   // the last fade-out keeps opacity 0 (fill)
    box.hidden = false;
    const opt = { duration: D, easing: "ease-in-out", fill: "forwards" };
    $$("#sky .sky-l").forEach((el) => { const o = sc[el.dataset.sky] || [0, 0, 0]; el.animate(o.map((x) => ({ opacity: x })), opt); });
    $("#sky .sky-stars").animate(sc.stars.map((x) => ({ opacity: x })), opt);
    const low = "translate(-22px, 74px)", high = "translate(0, -18px)", past = "translate(22px, 74px)", top = "translate(26px, -84px)";   // behind the hills / over them / above the bar
    const PATHS = { rise: [[low, high], "cubic-bezier(.2, .6, .3, 1)"], set: [[high, past], "cubic-bezier(.6, 0, .8, .4)"],
                    climb: [[high, top], "cubic-bezier(.5, 0, .7, .6)"], drift: [["translate(-36px, -4px)", "translate(8px, -20px)"], "ease-out"] };
    const [path, easing] = PATHS[sc.path];
    orb.animate(path.map((tr) => ({ transform: tr })), { ...opt, easing });
    // shooting stars in the night scenes: a streak across the upper sky at a random moment, behind the hills
    $$("#sky .sky-meteor").forEach((m) => m.remove());
    const rnd = (a, b) => a + Math.random() * (b - a);
    for (let i = 0; i < (sc.meteors || 0); i++) {
      const m = document.createElement("i"), x = rnd(.3, .8) * innerWidth, y = rnd(.04, .3) * innerHeight, len = rnd(90, 150);
      m.className = "sky-meteor"; $("#sky").insertBefore(m, $("#sky .sky-hills"));
      m.animate([{ transform: `translate(${x}px, ${y}px) rotate(20deg)`, opacity: 0 },
                 { opacity: 1, offset: .25 },
                 { transform: `translate(${x + len}px, ${y + len * .364}px) rotate(20deg)`, opacity: 0 }],   // tan 20°
                { duration: rnd(650, 900), delay: rnd(D * .3, D * .9) + i * 600, easing: "ease-in", fill: "both" })
        .finished.then(() => m.remove(), () => m.remove());
    }
    $("#sky .sky-text").animate([{ opacity: 0, transform: "translateY(-50%) translateX(8px)" }, { opacity: 1, transform: "translateY(-50%)" }],
                                { duration: 700, delay: 500, fill: "backwards", easing: "ease-out" });
    setTimeout(() => {                              // hold a moment, then fade out (unless a newer sky took over)
      if (playSky.id !== id) return;
      box.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 700, fill: "forwards" });   // hidden by the clock (as playWx)
      setTimeout(() => { if (playSky.id === id) box.hidden = true; }, 720);
    }, D + 1600);
  }
  $("#sky").addEventListener("click", () => { playSky.id = (playSky.id || 0) + 1; $("#sky").hidden = true; });
  // the bar only: a shift that begins or ends while recording (checked with the clock, every second)
  function skyTick() {
    const now = activeShifts(), was = st.shiftOn || [];
    st.shiftOn = now;
    const gone = was.find((k) => !now.includes(k)), came = now.find((k) => !was.includes(k));
    if (came) playSky(came, true); else if (gone) playSky(gone, false);   // 02 local: Late ends as Early starts
  }
  // the count, the ring and the note under it; from 30 minutes before 0000Z the note says how long is left
  function renderCount() {
    const { per, n } = dayCount(st.day);
    const differ = per.length > 1 && new Set(per.map((x) => x[1])).size > 1;
    const breakdown = differ ? per.map(([p, c]) => `${p.split("-")[1]}: ${c}`).join(" · ") : "";
    const now = Date.now(), d = new Date(now), left = Math.ceil((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1) - now) / 60000);
    const soon = left <= 30;
    $("#qsoCount").textContent = n; $("#barCount").textContent = n;
    $("#barPer").textContent = soon ? t("live.dayEnd.bar", { m: left }) : breakdown;
    $("#barPer").classList.toggle("is-alert", soon && n < 10);
    // the goal grows by 10 once reached: /10, then /20, /30 ...; the ring shows the current ten
    const goal = Math.max(10, Math.ceil(n / 10) * 10), pct = ((n - (goal - 10)) / 10) * 100;
    $("#qsoGoal").textContent = "/" + goal + " QSO"; $("#barGoal").textContent = "/" + goal;
    for (const id of ["#dashRing", "#barRing"]) { $(id).style.setProperty("--p", pct); $(id).classList.toggle("is-done", n >= 10); }
    const note = soon ? t(n >= 10 ? "live.dayEnd.done" : "live.dayEnd.left", { m: left, n: 10 - n })
      : n >= 10 ? t("live.qsoNote.done", { n }) : t("live.qsoNote.left", { n: 10 - n });
    $("#qsoNote").textContent = (breakdown && !soon ? breakdown + " — " : "") + note;
    $("#qsoNote").classList.toggle("is-alert", soon && n < 10);
    return n;
  }
  function spotRow(e, worked, fresh, page) {
    return `
      <li class="spot${e.twofer ? " is-twofer" : ""}${worked ? " is-worked" : ""}${fresh ? " is-new" : ""}${page && e.ago >= 30 ? " is-stale" : ""}">
        <span class="spot-time">${esc(e.time)}Z</span>
        <span class="spot-call">${esc(e.call)}${worked ? `<span class="worked-tag">${t("spots.worked")}</span>` : ""}</span>
        <span class="plates">${e.country ? `<span class="flag" title="${esc(countryName(e.country))}">${flagOf(e.country)}</span>` : ""}${plates(e.parks, e.new)}${e.twofer ? `<span class="twofer-tag">${e.parks.length}fer</span>` : ""}${newTag(e.new)}${e.qrt ? `<span class="qrt-tag">QRT</span>` : ""}${distTag(e.km)}</span>
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
    else if (p2p) ctl = `<span class="p2p-tag">P2P</span><span class="plates">${plates(q.parks, q.new)}</span>${newTag(q.new.filter((p) => q.parks.includes(p)))}${distTag(q.km)}<button class="link" data-act="edit" data-uid="${esc(q.uid)}">${t("row.change")}</button>`;
    else if (q.decision === "no") ctl = `<span class="qso-none">${t("row.none")}</span><button class="link" data-act="edit" data-uid="${esc(q.uid)}">${t("row.change")}</button>`;
    else if (q.candidate.length) ctl = `<span class="ask-text">${t("row.ask")}</span><span class="plates">${plates(q.candidate, q.new)}</span>${newTag(q.new)}${distTag(q.km)}${q.note ? `<span class="ask-note">${esc(t("row.note." + q.note))}</span>` : ""}
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
  // 運用中 → 一覧 / 地図. The map centres on my parks and joins each P2P's parks to them, with the call and
  // the distance; the points come from Python (Api.map_points: the same middles as the distances).
  const lmap = { tab: "list", map: null, layer: null, framed: "" };
  function liveTab(tab) {
    lmap.tab = tab; segSet("#liveTabs", "tab", tab);
    $(".live-grid").hidden = tab !== "list"; $("#liveMap").hidden = tab !== "map"; $("#liveWx").hidden = tab !== "weather";
    if (tab === "map") drawLiveMap();
    if (tab === "weather") renderWxTab();
  }
  async function drawLiveMap() {
    const Lf = window.L;                      // Leaflet (L in this file is the dictionary)
    if (!Lf || BAR || lmap.tab !== "map") return;
    const p2p = [...st.qsos.values()].filter((q) => q.decision && q.decision !== "no" && q.parks.length);
    const r = await api.map_points(st.parks || [], p2p.map((q) => q.parks));
    if (!lmap.map) {
      lmap.map = Lf.map("liveMap", { worldCopyJump: true, zoomSnap: 0.25 }).setView([20, 0], 2);
      Lf.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(lmap.map);
      lmap.layer = Lf.layerGroup().addTo(lmap.map);
    }
    lmap.map.invalidateSize(); lmap.layer.clearLayers();
    if (!r.me) return;
    const pts = [r.me], side = { left: 0, right: 0 };            // the widest label on each side
    p2p.forEach((q, i) => {
      const g = r.groups[i];
      if (!g) return;
      const at = [g[0], g[1] + Math.round((r.me[1] - g[1]) / 360) * 360];    // the short way, not across the whole map
      pts.push(at);
      Lf.polyline([r.me, at], { color: "#E9B457", weight: 2, opacity: .9 }).addTo(lmap.layer);
      const dir = at[1] < r.me[1] ? "left" : "right";
      const dot = Lf.circleMarker(at, { radius: 6, weight: 1.5, color: "#fff", fillColor: "#C98A1E", fillOpacity: 1 })
        .bindTooltip(`${esc(q.call)} · ${esc(q.parks.join(" + "))}${q.km != null ? " · " + esc(fmtDist(q.km)) : ""}`,
                     // beside the dot, away from me: labels of stations east and west don't pile up on the line
                     { permanent: true, direction: dir, offset: [dir === "left" ? -6 : 6, 0], className: "map-tag" }).addTo(lmap.layer);
      const el = dot.getTooltip() && dot.getTooltip().getElement();
      if (el) side[dir] = Math.max(side[dir], el.offsetWidth + 16);
    });
    const me = Lf.circleMarker(r.me, { radius: 8, weight: 2, color: "#fff", fillColor: "#2A6A50", fillOpacity: 1 })
      .bindTooltip(esc((st.parks || []).join(" + ")), { permanent: true, direction: "bottom", offset: [0, 8], className: "map-tag" }).addTo(lmap.layer);
    const meEl = me.getTooltip() && me.getTooltip().getElement();       // centred under my dot: half of it on each side
    if (meEl) { side.left = Math.max(side.left, meEl.offsetWidth / 2 + 16); side.right = Math.max(side.right, meEl.offsetWidth / 2 + 16); }
    // frame when a P2P is added or the parks change, not on every redraw
    const key = (st.parks || []).join() + "|" + pts.length;
    if (key !== lmap.framed) { lmap.framed = key; pts.length > 1   // room at each side for the widest label there
      ? lmap.map.fitBounds(pts, { paddingTopLeft: [side.left + 12, 40], paddingBottomRight: [side.right + 12, 40], maxZoom: 9 })
      : lmap.map.setView(r.me, 9); }
  }
  $$("#liveTabs button").forEach((b) => b.addEventListener("click", () => liveTab(b.dataset.tab)));
  function renderQsos(fresh) {
    const key = (q) => q.ts || q.date + q.time;           // to the second when the logger sent seconds
    const list = [...st.qsos.values()].sort((a, b) => key(b).localeCompare(key(a)) || (b.seq || 0) - (a.seq || 0));   // newest first
    // a line between UTC days (a session across 0000Z keeps yesterday's QSOs below it)
    const day = (q) => (q.date || "").replace(/^(\d{4})(\d\d)(\d\d)$/, "$1-$2-$3");
    $("#qsos").innerHTML = list.map((q, i) => (i && day(q) !== day(list[i - 1]) ? `<li class="qso-day">${esc(day(q))} UTC</li>` : "")
      + qsoRow(q, fresh)).join("");
    $("#barQsos").innerHTML = list.slice(0, 1).map((q) => qsoRow(q, fresh)).join("");   // the bar: the latest QSO
    $("#qsosEmpty").hidden = list.length > 0; $("#qsos").hidden = list.length === 0;
    $("#barEmpty").hidden = list.length > 0; $("#barQsos").hidden = list.length === 0;
    // Count per park for the day: a 2fer whose parks differ (one shared with an earlier session)
    // shows the smaller count as the number and the breakdown beside it.
    const n = renderCount();
    const p2p = list.filter((q) => q.decision && q.decision !== "no" && q.parks.length).length;
    const pending = list.filter((q) => !q.decision && q.candidate.length).length;
    $("#statP2p").textContent = p2p; $("#statPending").textContent = pending;
    $("#statPendingBox").classList.toggle("is-alert", pending > 0);
    renderStats();
    if (st.editing) { const el = $(`[data-in="${CSS.escape(st.editing)}"]`); if (el) el.focus(); }
    // a celebration at every 10 QSOs; the ones already passed when the list (re)opens are not repeated
    const tens = Math.floor(n / 10);
    if (lmap.tab === "map") drawLiveMap();
    if (st.cheered === null) st.cheered = tens;
    else if (tens > st.cheered) { st.cheered = tens; cheer(tens * 10); }
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
  function cheer(n) {
    $("#cheerN").textContent = n + " QSO";
    $("#cheerSub").textContent = n === 10 ? t("cheer.sub") : t("cheer.next", { n: n + 10 });
    celebrate("#cheer", burst(48));
  }
  $("#cheer").addEventListener("click", () => ($("#cheer").hidden = true));

  // ---- the bar asks about a P2P candidate over the whole bar: はい / いいえ / スキップ; a skipped one stays
  // unanswered in the main window's list to decide there. Only QSOs that arrive while the bar is open ask.
  const ask = { q: [], skipped: new Set() };
  const asking = (u) => { const q = st.qsos.get(u); return q && !q.decision && q.candidate.length && !ask.skipped.has(u); };
  function askNext() {
    ask.q = ask.q.filter(asking);
    const box = $("#ask"), q = st.qsos.get(ask.q[0]);
    if (!q) { box.hidden = true; fitBar(); return; }
    if (!box.hidden && box.dataset.uid === q.uid) return;
    box.dataset.uid = q.uid; box.hidden = false;
    $("#askCall").textContent = q.call; $("#askParks").innerHTML = plates(q.candidate, q.new);
    fitBar();                                      // a 3fer question is wider than the row under it
  }
  // the bar window is as wide as its content needs: no wraps, nothing to spare (window.py BarMode.fit)
  function fitBar() {
    const bar = $("#bar"); bar.classList.add("is-measure");
    let w = Math.ceil(bar.getBoundingClientRect().width);
    bar.classList.remove("is-measure");
    if (!$("#ask").hidden) w = Math.max(w, Math.ceil($(".ask-q").getBoundingClientRect().width) + 32);   // its 16 px sides
    w = Math.max(360, Math.round(w * LOOK.font_scale));   // window px (CSS px x zoom); 360: the P2P question's buttons
    const h = Math.round(100 * LOOK.font_scale);
    const z = LOOK.font_scale;                     // innerWidth / innerHeight are CSS px: compare in window px
    if ((Math.abs(w - innerWidth * z) > 2 || Math.abs(h - innerHeight * z) > 2) && w + "x" + h !== st.barW) { st.barW = w + "x" + h; api.fit_bar(w, h); }
  }
  function blinkAsk() { const b = $("#ask"); b.classList.remove("is-blink"); void b.offsetWidth; b.classList.add("is-blink"); }
  $$("#ask [data-ask]").forEach((b) => b.addEventListener("click", async () => {
    const uid = $("#ask").dataset.uid, q = st.qsos.get(uid), act = b.dataset.ask;
    if (act === "skip") ask.skipped.add(uid);
    else if (q) await decide(uid, act, act === "yes" ? q.candidate.join(",") : "");
    $("#ask").hidden = true; askNext();
  }));

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

  // ---- the bar: a second small window (this page with #bar) kept above the logger; the main window stays
  async function setBar(on) {
    st.barSetAt = Date.now();
    try { showBarOn(await api.set_bar(on)); } catch (e) { /* window control is best effort */ }
  }
  // バー表示 ON / OFF: also follows the bar's own × (poll_live "bar")
  function showBarOn(on) { st.bar = !!on; $("#toBar").setAttribute("aria-checked", String(st.bar)); }
  $("#toBar").addEventListener("click", () => setBar(!st.bar));
  $("#barClose").addEventListener("click", () => setBar(false));
  // the main window may have been in the background (timers slowed down): catch up when it comes back
  document.addEventListener("visibilitychange", () => { if (!document.hidden && st.start && !BAR) poll(); });

  $$("#liveRun .live-grid .seg button").forEach((b) => b.addEventListener("click", () => {   // the home / world switch, not the tabs
    st.prefix = b.dataset.prefix; segSet("#liveRun .live-grid .seg", "prefix", st.prefix); api.save({ prefix: st.prefix }); renderSpots();
  }));

  // ---- finish: stop, write this park's upload file(s), back to the start
  const finishLabels = () => ($("#finishLive").textContent = t("live.finish"));
  async function finishLive(e) {
    const pending = [...st.qsos.values()].filter((q) => !q.decision && q.candidate.length).length;
    const btns = [$("#finishLive")];
    if (pending && !secondPress(e.currentTarget, t("live.finishArmed", { n: pending }), finishLabels, 6000)) {
      toast(t("live.finishPending", { n: pending }));
      return;
    }
    btns.forEach((b) => { b.disabled = true; b.textContent = t("live.working"); });
    const r = await api.finish_live(true);
    btns.forEach((b) => (b.disabled = false)); finishLabels();
    clearTimeout(st.timer); st.pollOn = false; clearTimeout(st.poll);
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
    $("#spotsPageEmpty").hidden = list.length > 0; $("#spotsPage").hidden = list.length === 0 || sp.tab === "map";
    drawSpotsMap(list);
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
  // 一覧 / 地図: the same filtered stations as dots at their parks (Python's "at"); 2fer amber, worked grey
  function spotsTab(tab) {
    sp.tab = tab; segSet("#spotsTabs", "tab", tab); $("#spotsMap").hidden = tab !== "map";
    renderSpotsPage();
  }
  $$("#spotsTabs button").forEach((b) => b.addEventListener("click", () => spotsTab(b.dataset.tab)));
  function drawSpotsMap(list) {
    const Lf = window.L;                      // Leaflet (L in this file is the dictionary)
    if (!Lf || sp.tab !== "map") return;
    if (!sp.map) {
      sp.map = Lf.map("spotsMap", { preferCanvas: true, worldCopyJump: true, zoomSnap: 0.25 }).setView([20, 0], 2);
      Lf.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(sp.map);
      sp.dots = Lf.layerGroup().addTo(sp.map);
    }
    sp.map.invalidateSize(); sp.dots.clearLayers();
    let wide = 0;
    const pts = [], named = list.length <= 25;      // a few stations: their calls on the map; many: on hover
    for (const e of list) {
      if (!e.at) continue;
      pts.push(e.at);
      const worked = sp.worked.has(e.base);
      const dot = Lf.circleMarker(e.at, { radius: 6, weight: 1.5, color: "#fff", fillOpacity: e.qrt ? .35 : 1,
                                          fillColor: worked ? "#7D8A83" : e.twofer ? "#C98A1E" : "#2A6A50" }).addTo(sp.dots);
      const info = `<b>${esc(e.call)}</b> · ${esc(e.parks.join(" + "))}<br>${esc(e.freq || "")} ${esc(e.mode)} · ${esc(e.time)}Z${e.qrt ? " · QRT" : ""}`;
      if (named) {
        dot.bindTooltip(esc(e.call), { permanent: true, direction: "right", offset: [6, 0], className: "map-tag" }).bindPopup(info);   // details on a click
        const el = dot.getTooltip().getElement();
        if (el) wide = Math.max(wide, el.offsetWidth + 16);
      }
      else dot.bindTooltip(info, { className: "map-tag" });
    }
    // frame when the filter changes, not on the minutely refresh of the same list
    const key = [sp.region, sp.country, sp.group, sp.band, sp.q, sp.twofer, sp.newOnly, sp.hideQrt].join("|");
    if (pts.length && key !== sp.framed) { sp.framed = key; sp.map.fitBounds(pts, { paddingTopLeft: [24, 24], paddingBottomRight: [wide + 24, 24], maxZoom: 9 }); }   // room for the labels
  }

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
        <span class="act-n${Math.min(...Object.values(a.per || {}), a.qsos) < 10 ? " is-short" : ""}">${a.qsos} QSO</span>
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
    $("#editor").hidden = false; api.set_busy("edit", true);
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
  $("#editorClose").addEventListener("click", () => { $("#editor").hidden = true; api.set_busy("edit", false); loadActs(ed.path || undefined); });
  // closing the window while recording or editing: app.py's closing handler asks here first
  window.potarooAskClose = (reasons) => {
    $("#closeText").innerHTML = reasons.map((r) => `<p>${esc(t("close." + r))}</p>`).join("");
    $("#closeModal").hidden = false; $("#closeCancel").focus();
  };
  $("#closeCancel").addEventListener("click", () => ($("#closeModal").hidden = true));
  $("#closeGo").addEventListener("click", () => api.quit_app());
  $("#pickAdif").addEventListener("click", async () => { const r = await api.pick_adif(); if (r) renderActs(r); });
  $("#pickOut").addEventListener("click", async () => { const p = await api.pick_out(); if (p) { st.out = p; $("#outPath").textContent = p; } });

  const SRC_CLASS = { hunter: "src-ok", confirmed: "src-ok", manual: "src-ok", spot: "src-spot", log: "src-log", logspot: "src-log" };
  // POTA asks that logs are not uploaded 03-11 UTC: uploads then often end in "Unknown Failure" (database
  // maintenance, log rotation, autoscaling). Not on docs.pota.app or the upload page; POTA sent it by mail / SNS,
  // e.g. POTA JAPAN EVENT INFORMATION (@PotaEvent) on X, 2025-07-05, relaying POTA. Shown in the user's local time.
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
    // Rover: parks activated in one UTC day; the award names are POTA's own
    const rover = (r.rover || []).map((x) => `<p class="res-rover">${esc(t(x.award ? "res.rover.award" : "res.rover", { date: fmtDate(x.date), n: x.parks, award: x.award }))}</p>`).join("");
    // a wrong line is not replaced by uploading again: delete the upload (My Log Uploads, 24 h) or ask POTA
    const fix = files.length ? `<p class="res-fix">${esc(t("res.fix"))} <button class="link" data-url="https://pota.app/#/user/logs">${esc(t("res.fix.open"))}</button></p>` : "";
    return (files.length ? uploadHoursHtml() : "") + rover + (files.length ? `<div class="res-tools"><label class="switch switch-sm"><input type="checkbox" class="res-p2p-only"><span class="switch-ui"></span><span>${esc(t("res.p2pOnly"))}</span></label></div>` : "") +
      files.map((f) => `
      <article class="file">
        <div class="file-head">
          ${plate(f.park)}
          <div><div class="file-date">${fmtDate(f.date)}</div><div class="file-name">${esc(f.file)}</div></div>
          <div class="file-q${(f.counted ?? f.qsos) < 10 ? " is-short" : ""}"><strong>${f.qsos}</strong><span>${esc(t((f.counted ?? f.qsos) < 10 ? "res.qsoShort" : "res.qso"))}</span>
            ${f.unique && f.unique < f.qsos ? `<small>${esc(t("res.unique", { n: f.unique }))}</small>` : ""}
            ${f.records && f.records !== f.qsos ? `<small>${esc(t("res.lines", { n: f.records }))}</small>` : ""}</div>
        </div>
        ${(f.rows || []).length ? `<div class="p2p">${f.rows.map(row).join("")}</div>`
          : f.p2p.length ? `<div class="p2p">${f.p2p.map((p) => row({ ...p, band: "", mode: "" })).join("")}</div>` : `<div class="p2p-none">${esc(t("res.noP2P"))}</div>`}
      </article>`).join("") +
      (files.length && r.notes && r.notes.length ? `<div class="notes"><h3>${esc(t("res.notes"))}</h3><ul>${r.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>` : "") +
      (!files.length && r.notes && r.notes.length ? `<p class="muted">${esc(r.notes[0])}</p>` : "") + fix;
  }
  document.addEventListener("click", (e) => { const b = e.target.closest(".res-fix [data-url]"); if (b) api.open_url(b.dataset.url); });
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
    st.calls = calls; st.call = call; showOperator();
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
  // the operator is remembered per call: a club call's operator must not follow into a personal call's session
  // a select (a datalist's native popup can't be styled): なし + 設定 → オペレーター, plus the one in use if removed since
  const opOptions = (sel) => `<option value="">${esc(t("live.operator.ph"))}</option>` +
    [...new Set([...(st.opList || []), sel].filter(Boolean))].map((c) => `<option value="${esc(c)}"${c === sel ? " selected" : ""}>${esc(c)}</option>`).join("");
  function showOperator() {
    const sel = (st.operators || {})[st.call] || "";
    $("#liveOp").innerHTML = opOptions(sel); $("#liveOpField").hidden = !sel && !(st.opList || []).length;
  }
  $("#liveCall").addEventListener("change", (e) => saveCalls(st.calls, e.target.value));
  // 設定 → クラブ局のオペレーター: offered in the operator boxes (still free to type)
  function renderOps() {
    $("#ops").innerHTML = (st.opList || []).map((c) => `
      <li class="call-row"><span class="call-name">${esc(c)}</span>
        <button class="link" data-del="${esc(c)}">${esc(t("cfg.calls.remove"))}</button></li>`).join("");
    showOperator(); if (st.operator) $("#dashOp").innerHTML = opOptions(st.operator);
  }
  async function saveOps(list) { st.opList = list; renderOps(); await api.save({ op_list: list }); }
  $("#opsAdd").addEventListener("submit", (e) => {
    e.preventDefault();
    const err = $("#opsError"), c = $("#opNew").value.trim().toUpperCase();
    if (!/^[A-Z0-9/]{3,}$/.test(c)) return showError(err, t("cfg.calls.err"));       // = potacommon.CALL_RE
    showError(err, ""); $("#opNew").value = "";
    if (!st.opList.includes(c)) saveOps([...st.opList, c]);
  });
  $("#ops").addEventListener("click", (e) => {
    const b = e.target.closest("[data-del]"); if (b) saveOps(st.opList.filter((c) => c !== b.dataset.del));
  });
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
    const g = r.goals || {};          // Kilo / Repeat Offender reached, and the next one from halfway
    const goals = (g.has || []).map((n) => `<span class="rec-goal">${esc(n)}</span>`).join("") +
      (g.next ? `<span>${esc(t("rec.goalLeft", { left: g.left, name: g.next }))}</span>` : "");
    return `<li class="rec">
      <span class="rec-date">${esc((rec.kind === "hunted" ? r.first : r.last) || "")}</span>
      <span class="rec-park"><span class="flag">${flagOf(r.ref.split("-")[0])}</span>${plate(r.ref)}<span class="rec-name" title="${esc(r.name || "")}">${esc(r.name || "")}</span>${statusTag(r.listed)}</span>
      <span class="rec-meta">${goals}${meta}</span></li>`;
  }
  function renderRecord() {
    const d = rec.data;
    if (!d) return;
    const empty = !d.hunted.length && !d.activated.length;
    $("#recEmpty").hidden = !empty; $("#recBody").hidden = empty;
    if (empty) return;
    const sum = (k, rows) => esc(t(k, { n: rows.length, added: rows.filter((r) => r.added).length }));
    const u = (d.unique || {})[rec.kind];      // the next Unique Reference level for the list shown
    $("#recSum").innerHTML = `<span>${sum("rec.sum.hunted", d.hunted)}</span><span>${sum("rec.sum.activated", d.activated)}</span>` +
      (u && u.next ? `<span class="rec-next">${esc(t("rec.next", { n: u.next, left: u.next - u.n }))}</span>` : "");
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
  $("#barOnTop").addEventListener("change", (e) => api.set_bar_on_top(e.target.checked));
  $$("#fontScale button").forEach((b) => b.addEventListener("click", () => { applyLook({ ...LOOK, font_scale: +b.dataset.scale }); api.save({ font_scale: LOOK.font_scale }); }));
  $$("#distUnit button").forEach((b) => b.addEventListener("click", () => {
    st.distUnit = b.dataset.unit; segSet("#distUnit", "unit", distUnit()); api.save({ dist_unit: st.distUnit }); renderQsos(); renderSpots();
  }));
  $$("#themeSel button").forEach((b) => b.addEventListener("click", () => { applyLook({ ...LOOK, theme: b.dataset.theme }); api.save({ theme: LOOK.theme }); }));

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
  $("#openLog").addEventListener("click", () => api.open_log());
  // 不具合を報告 (half automatic): the operator reads and edits the report, then copies it or opens a
  // prefilled GitHub issue. Nothing is sent by the app itself.
  $("#report").addEventListener("click", async () => {
    const r = await api.report_info();
    $("#reportText").value = `## ${t("report.h.what")}\n\n\n## ${t("report.h.env")}\nPotaroo ${r.version} / ${t("ver.data", { v: r.data_version || "-" })} / ${r.os}\n\n` +
      `## ${t("report.h.log", { n: r.lines })}\n\`\`\`\n${r.log}\n\`\`\`\n`;
    $("#reportModal").hidden = false; $("#reportText").focus(); $("#reportText").setSelectionRange(0, 0);
  });
  $("#reportClose").addEventListener("click", () => ($("#reportModal").hidden = true));
  $("#reportCopy").addEventListener("click", () => copyText($("#reportText").value));
  $("#reportGithub").addEventListener("click", () => {
    // a URL of about 6000 characters still opens: drop the log's oldest lines, never what the operator wrote
    const text = $("#reportText").value, cut = text.indexOf("```\n") + 4;
    const body = text.length <= 6000 || cut < 4 ? text.slice(0, 6000) : text.slice(0, cut) + text.slice(cut).slice(-(6000 - cut));
    api.open_url("https://github.com/PudiPara/potaroo/issues/new?title=" + encodeURIComponent(t("report.issue")) + "&body=" + encodeURIComponent(body));
  });
  // the page's own errors go to potaroo.log too (Api.log_js): there is no console in the installed app
  const logJs = (what) => { try { if (api) api.log_js(what); } catch (e) { /* nothing else to tell */ } };
  window.addEventListener("error", (e) => logJs(`${e.message} @ ${e.filename}:${e.lineno}:${e.colno}${e.error && e.error.stack ? "\n" + e.error.stack : ""}`));
  window.addEventListener("unhandledrejection", (e) => logJs("unhandled rejection: " + (e.reason && (e.reason.stack || e.reason.message) || e.reason)));
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
    applyLook(s); segSet("#fontScale", "scale", String(LOOK.font_scale)); segSet("#themeSel", "theme", LOOK.theme);
    st.distUnit = s.dist_unit || "";
    Object.assign(st, { call: s.call || "", calls: s.calls || [], prefix: s.prefix, out: s.out, adif: s.adif, source: s.source || "app", listeners: s.listeners,
                        langs: s.langs || [["ja", "日本語"]], events: s.events || [], termsAccepted: s.terms_accepted || "", countries: s.countries || [] });
    $("#lang").innerHTML = st.langs.map(([c, name]) => `<option value="${esc(c)}">${esc(name)}</option>`).join("");
    const lang = s.lang || pickLang(navigator.language);
    if (!s.lang) api.save({ lang });
    const country = s.country || guessCountry(navigator.language, lang);
    if (!s.country && country) api.save({ country });
    await setCountry(country);
    segSet("#distUnit", "unit", distUnit());       // not saved: follows 所在国 until the operator picks one
    await loadLang(lang);
    $("#version").textContent = `v${s.version}`;
    st.dataVersion = s.data_version || "";
    $("#dataVersion").textContent = st.dataVersion ? t("ver.data", { v: st.dataVersion }) : "";
    st.operators = s.operators || {}; st.opList = s.op_list || []; renderOps(); renderCalls(); showOperator(); $("#p2pAuto").checked = !!s.p2p_auto; $("#onTop").checked = !!s.on_top; $("#barOnTop").checked = s.bar_on_top !== false;
    st.lookup = s.lookup || ["qrz"]; renderLookup();
    st.mypota = s.mypota || {}; renderMypota();
    setParks(s.parks);
    $("#outPath").textContent = s.out;
    setLogCount(s.log_count);
    segSet("#liveRun .live-grid .seg", "prefix", st.prefix);
    renderListeners(); updateReceiver(s.receiver);
    setSource(st.source);
    if (BAR) {                                      // the bar window: the running activation only
      document.body.classList.add("is-bar"); $("#bar").hidden = false;
      if (s.live) { await enterRunning(s.live); await document.fonts.ready; fitBar(); } else api.set_bar(false);
      return;
    }
    if (s.live) enterRunning(s.live);
    if (st.termsAccepted !== TERMS_VERSION) showTerms(true);
    setTimeout(promptUpdate, 1500);                 // the first thing after the window is up
  }
  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener("pywebviewready", boot);
})();
