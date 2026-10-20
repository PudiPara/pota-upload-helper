"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  let api = null;
  const st = {
    call: "JL1FVA", prefix: "JP", spots: new Map(), qsos: new Map(), lastAt: 0, lastQ: 0,
    start: null, timer: null, poll: null, source: "app", adif: "", out: "", outDir: "",
    acts: [], selected: new Set(), listeners: [], receiver: {},
  };

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
    return `<span class="plate"><b>${esc(ref.slice(0, i + 1))}</b>${esc(ref.slice(i + 1))}</span>`;
  }
  const plates = (refs) => (refs || []).map(plate).join('<span class="plate-join" aria-hidden="true">+</span>');
  const fmtDate = (d) => `${d.slice(0, 4)}年${+d.slice(4, 6)}月${+d.slice(6, 8)}日`;
  const hhmm = (t) => `${esc(String(t).slice(0, 2))}:${esc(String(t).slice(2, 4))}`;
  function fmtFreq(khz) {
    const k = parseFloat(khz);
    return k ? `${(k / 1000).toFixed(3)}<small>MHz</small>` : esc(khz || "");
  }
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), 2800);
  }
  const utcMs = (iso) => Date.parse(iso.length === 16 ? iso + ":00Z" : iso + "Z");
  function segSet(group, attr, val) {
    $$(group + " button").forEach((x) => { const on = x.dataset[attr] === val; x.classList.toggle("is-on", on); x.setAttribute("aria-checked", on); });
  }

  // ---------- navigation ----------
  function show(view) {
    $$(".nav-item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === view));
    ["live", "build", "settings"].forEach((v) => ($("#view-" + v).hidden = v !== view));
    $(".main").scrollTo(0, 0);
    if (view === "build" && st.source === "app") loadActs();
    if (view === "settings") api.poll_live(1e12, 1e12).then((r) => updateReceiver(r.receiver));
  }
  $$(".nav-item").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

  // ================================================================ live
  function renderPreview() { $("#parksPreview").innerHTML = plates(splitParks($("#parks").value)); }
  $("#parks").addEventListener("input", renderPreview);
  $("#parks").addEventListener("keydown", (e) => { if (e.key === "Enter") startLive(); });

  async function startLive() {
    const parks = splitParks($("#parks").value);
    const err = $("#liveError");
    if (!parks.length) { err.textContent = "公園番号を JP-1281 の形で入力してください。"; err.hidden = false; return; }
    err.hidden = true;
    const r = await api.start_live(parks.join(","), st.call);
    if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
    enterRunning(r.parks, r.start);
  }
  $("#startLive").addEventListener("click", startLive);

  async function enterRunning(parks, start) {
    st.spots.clear(); st.qsos.clear(); st.lastAt = 0; st.start = utcMs(start);
    $("#liveIdle").hidden = true; $("#liveRun").hidden = false; $("#liveDot").hidden = false;
    $("#signParks").innerHTML = parks.map((p) => {
      const i = p.indexOf("-");
      return `<div class="sign-park"><span class="ref"><b>${esc(p.slice(0, i + 1))}</b>${esc(p.slice(i + 1))}</span><span class="name" data-ref="${esc(p)}"></span></div>`;
    }).join("");
    $("#liveStatus").textContent = "最初のスポットを取得しています";
    for (const q of await api.session_qsos(start)) st.qsos.set(`${baseCall(q.call)}|${q.date}${q.time}|${q.band}`, q);
    st.lastQ = Date.now() / 1000 - 1;
    renderSpots(); renderQsos();
    tick(); clearInterval(st.timer); st.timer = setInterval(tick, 1000);
    poll(); clearInterval(st.poll); st.poll = setInterval(poll, 2500);
    try {
      const info = await api.park_info(parks.join(","));
      $$("#signParks .name").forEach((el) => { const i = info[el.dataset.ref] || {}; el.textContent = i.local || i.name || ""; });
    } catch (e) { /* optional */ }
  }
  function tick() {
    const s = Math.max(0, Math.floor((Date.now() - st.start) / 1000));
    const p = (n) => String(n).padStart(2, "0");
    $("#elapsed").textContent = `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
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
        toast(`${q.call} の QSO がロガーで削除されました`);
        continue;
      }
      if (q.date && st.start && Date.parse(`${q.date.slice(0, 4)}-${q.date.slice(4, 6)}-${q.date.slice(6, 8)}T${q.time.slice(0, 2)}:${q.time.slice(2, 4)}:00Z`) < st.start - 300000) continue;
      const k = `${baseCall(q.call)}|${q.date}${q.time}|${q.band}`;
      st.qsos.set(k, q); freshQ.add(k);
      if (q.parks && q.parks.length) toast(`P2P: ${q.call}（${q.parks.join(" + ")}）`);
    }
    if (freshS.size || freshQ.size) { renderSpots(freshS); renderQsos(freshQ); }
  }
  function workedCalls() { return new Set([...st.qsos.values()].map((q) => baseCall(q.call))); }
  function renderSpots(fresh) {
    const worked = workedCalls();
    const list = [...st.spots.values()].filter((e) => !st.prefix || e.parks.some((p) => p.startsWith(st.prefix)))
      .sort((a, b) => b.at - a.at);
    $("#spots").innerHTML = list.map((e) => `
      <li class="spot${e.twofer ? " is-twofer" : ""}${worked.has(baseCall(e.call)) ? " is-worked" : ""}${fresh && fresh.has(e.call) ? " is-new" : ""}">
        <span class="spot-time">${esc(e.time)}Z</span>
        <span class="spot-call">${esc(e.call)}</span>
        <span class="spot-meta"><span class="spot-freq">${fmtFreq(e.freq)}</span>${e.mode ? `<span class="spot-mode">${esc(e.mode)}</span>` : ""}</span>
        <span class="plates">${plates(e.parks)}${e.twofer ? `<span class="twofer-tag">${e.parks.length}fer</span>` : ""}</span>
      </li>`).join("");
    $("#spotsEmpty").hidden = list.length > 0; $("#spots").hidden = list.length === 0;
    const tw = list.filter((e) => e.twofer).length;
    $("#liveCount").textContent = list.length ? `${list.length} 局${tw ? `・2fer 以上 ${tw} 局` : ""}` : "";
  }
  function renderQsos(fresh) {
    const list = [...st.qsos.entries()].sort((a, b) => (b[1].date + b[1].time).localeCompare(a[1].date + a[1].time));
    $("#qsos").innerHTML = list.map(([k, q]) => {
      const p2p = q.parks && q.parks.length;
      return `<li class="qso${p2p ? " is-p2p" : ""}${p2p > 1 ? " is-twofer" : ""}${fresh && fresh.has(k) ? " is-new" : ""}">
        <span class="qso-time">${hhmm(q.time)}</span>
        <span class="qso-call">${esc(q.call)}</span>
        <span class="qso-band">${esc(q.band)} ${esc(q.mode)}</span>
        ${p2p ? `<span class="plates"><span class="p2p-tag">P2P</span>${plates(q.parks)}</span>` : ""}
      </li>`;
    }).join("");
    $("#qsosEmpty").hidden = list.length > 0; $("#qsos").hidden = list.length === 0;
    const uniq = new Set(list.map(([, q]) => `${baseCall(q.call)}|${q.band}|${q.mode}`)).size;
    const n = list.length, p2p = list.filter(([, q]) => q.parks && q.parks.length).length;
    $("#qsoCount").textContent = n;
    $("#qsoBar").style.width = Math.min(100, (n / 10) * 100) + "%";
    $(".tally").classList.toggle("is-done", n >= 10);
    $("#qsoNote").textContent = n >= 10 ? `アクティベーション成立（${uniq} 局・バンド・モード）` : `あと ${10 - n} QSO でアクティベーション成立`;
    $("#p2pCount").textContent = p2p ? `P2P ${p2p} 件` : "";
  }
  $$("#liveRun .seg button").forEach((b) => b.addEventListener("click", () => {
    st.prefix = b.dataset.prefix; segSet("#liveRun .seg", "prefix", st.prefix); api.save({ prefix: st.prefix }); renderSpots();
  }));
  $("#stopLive").addEventListener("click", async () => {
    const r = await api.stop_live();
    clearInterval(st.timer); clearInterval(st.poll);
    $("#liveRun").hidden = true; $("#liveIdle").hidden = false; $("#liveDot").hidden = true;
    if (r.start) toast(`記録を止めました（${r.start.slice(11)}〜${r.end.slice(11)} UTC）`);
  });

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
      $("#adifName").textContent = st.adif ? st.adif.split(/[\\/]/).pop() : "まだ選ばれていません";
      $("#adifPath").textContent = st.adif || "RUMlogNG なら「Logbook → Export all QSOs as ADIF」";
    }
    st.acts = res.items || []; st.selected.clear(); $("#actHint").textContent = "選ばなければ全部作ります";
    if (res.error) { $("#acts").innerHTML = `<p class="pad error">${esc(res.error)}</p>`; return; }
    if (waitingFile) { $("#acts").innerHTML = '<p class="pad muted">ADIF を選ぶとここに一覧が出ます。</p>'; return; }
    if (!st.acts.length) {
      $("#acts").innerHTML = st.source === "app"
        ? '<p class="pad muted">まだアクティベーションの QSO を受け取っていません。運用中タブで記録を始め、ロガーから QSO が届くとここに並びます。</p>'
        : '<p class="pad muted">自分の公園（MY_SIG_INFO）が入った QSO が見つかりません。運用中タブで記録した時間帯の QSO は自動で拾います。</p>';
      return;
    }
    $("#acts").innerHTML = st.acts.map((a) => `
      <label class="act">
        <input type="checkbox" value="${esc(a.date)}">
        <span class="act-date">${fmtDate(a.date)}<small>UTC</small></span>
        <span class="plates">${plates(a.parks)}</span>
        <span class="act-n${a.qsos < 10 ? " is-short" : ""}">${a.qsos} QSO</span>
      </label>`).join("");
    $$("#acts input").forEach((i) => i.addEventListener("change", () => {
      i.checked ? st.selected.add(i.value) : st.selected.delete(i.value);
      i.closest(".act").classList.toggle("is-checked", i.checked);
      $("#actHint").textContent = st.selected.size ? `${st.selected.size} 件を選択中` : "選ばなければ全部作ります";
    }));
  }
  $("#pickAdif").addEventListener("click", async () => { const r = await api.pick_adif(); if (r) renderActs(r); });
  $("#pickOut").addEventListener("click", async () => { const p = await api.pick_out(); if (p) { st.out = p; $("#outPath").textContent = p; } });

  const SRC = (s) => s.includes("ハンター") ? ["src-ok", "確定"] : s.includes("スポット") ? ["src-spot", "スポット"] : ["src-log", "ログ"];
  $("#runBuild").addEventListener("click", async () => {
    if (st.source === "adif" && !st.adif) { toast("先に ADIF を選んでください"); return; }
    const btn = $("#runBuild"); btn.disabled = true; btn.textContent = "作成しています…";
    const r = await api.build({ source: st.source, adif: st.adif, dates: [...st.selected], override: $("#override").value,
                                call: st.call, out: st.out, online: $("#online").checked });
    btn.disabled = false; btn.textContent = "アップロード用ファイルを作成";
    const box = $("#results"); box.hidden = false;
    if (!r.ok) { $("#resultsTitle").textContent = "作成できませんでした"; $("#resultsBody").innerHTML = `<p class="error">${esc(r.error)}</p>`; return; }
    const files = r.summary || [];
    $("#resultsTitle").textContent = files.length ? `${files.length} 個のファイルを作成しました` : "作成するファイルがありません";
    $("#resultsBody").innerHTML = files.map((f) => `
      <article class="file">
        <div class="file-head">
          ${plate(f.park)}
          <div><div class="file-date">${fmtDate(f.date)}</div><div class="file-name">${esc(f.file)}</div></div>
          <div class="file-q${f.qsos < 10 ? " is-short" : ""}"><strong>${f.qsos}</strong><span>${f.qsos < 10 ? "QSO・10 未満" : "QSO"}</span></div>
        </div>
        ${f.p2p.length ? `<div class="p2p">${f.p2p.map((p) => { const [c, l] = SRC(p.source); return `
          <div class="p2p-row"><span class="muted">${hhmm(p.time)}</span>
          <span class="p2p-call">${esc(p.call)}</span><span class="plates">${plates(p.parks)}</span>
          <span class="src ${c}">${l}</span></div>`; }).join("")}</div>` : '<div class="p2p-none">P2P はありませんでした</div>'}
      </article>`).join("") +
      (r.p2p_fixes ? `<p class="fixnote">ロガーに入っていなかった相手の公園が ${r.p2p_fixes} 件ありました。logger_p2p_fix.adi に書き出しています。</p>` : "") +
      (files.length && r.notes && r.notes.length ? `<div class="notes"><h3>確認してください</h3><ul>${r.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>` : "") +
      (!files.length && r.notes && r.notes.length ? `<p class="muted">${esc(r.notes[0])}</p>` : "");
    st.outDir = r.out_dir;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("#openOut").addEventListener("click", () => api.open_out(st.outDir || st.out));
  $("#openPota").addEventListener("click", () => api.open_url("https://pota.app/"));

  // ================================================================ settings
  const KINDS = [["n1mm", "N1MM"], ["wsjtx", "WSJT-X"], ["adif", "ADIF"]];
  function renderListeners() {
    $("#listeners").innerHTML = st.listeners.map((l, i) => {
      const s = st.receiver[l.name] || (l.enabled ? "" : "オフ");
      const cls = /開けません|違います/.test(s) ? "is-bad" : /受信/.test(s) ? "is-ok" : "";
      return `<div class="lis" data-i="${i}">
        <label class="switch" title="オン / オフ"><input type="checkbox" data-k="enabled" ${l.enabled ? "checked" : ""}><span class="switch-ui"></span></label>
        <label>名前<input type="text" data-k="name" value="${esc(l.name)}"></label>
        <label>形式<select data-k="kind">${KINDS.map(([v, t]) => `<option value="${v}"${l.kind === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>
        <label>ポート<input type="text" inputmode="numeric" data-k="port" value="${esc(l.port)}"></label>
        <label>マルチキャスト<input type="text" data-k="multicast" placeholder="使わない" value="${esc(l.multicast)}"></label>
        <label>転送先<input type="text" data-k="forward" placeholder="例 127.0.0.1:2335" value="${esc(l.forward)}"></label>
        <button class="link lis-del" data-del="${i}">削除</button>
        <div class="lis-state ${cls}">${esc(s)}</div>
      </div>`;
    }).join("") || '<p class="muted">受信口がありません。「受信口を追加」から作ってください。</p>';
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
    const bad = on.some((l) => /開けません/.test(rs[l.name] || ""));
    $("#recvSummary").textContent = !on.length ? "受信していません" : bad ? "受信できない設定があります" : `${on.length} 個の受信口で待機中`;
    if (!$("#view-settings").hidden) $$("#listeners .lis").forEach((el) => {
      const l = st.listeners[+el.dataset.i]; const s = rs[l.name] || (l.enabled ? "" : "オフ");
      const box = el.querySelector(".lis-state"); box.textContent = s;
      box.className = "lis-state " + (/開けません|違います/.test(s) ? "is-bad" : /受信/.test(s) ? "is-ok" : "");
    });
  }
  $("#addListener").addEventListener("click", () => {
    st.listeners.push({ name: "受信口 " + (st.listeners.length + 1), kind: "n1mm", port: 2334, multicast: "", enabled: true, forward: "" });
    renderListeners();
  });
  $("#saveListeners").addEventListener("click", async () => {
    const r = await api.save_listeners(st.listeners);
    const err = $("#listenError");
    if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
    err.hidden = true; st.listeners = r.listeners; st.receiver = r.receiver || {}; renderListeners(); updateReceiver(st.receiver);
    toast("保存しました。受信し直しています");
  });
  setInterval(async () => { if (api) updateReceiver((await api.poll_live(1e12, 1e12)).receiver); }, 4000);

  // ---------- rail ----------
  $("#openData").addEventListener("click", () => api.open_data());
  $("#call").addEventListener("change", (e) => {
    st.call = e.target.value.trim().toUpperCase() || "JL1FVA"; e.target.value = st.call; api.save({ call: st.call });
  });

  // ---------- boot ----------
  async function boot() {
    api = window.pywebview.api;
    const s = await api.get_state();
    Object.assign(st, { call: s.call, prefix: s.prefix, out: s.out, adif: s.adif, source: s.source || "app", listeners: s.listeners });
    $("#version").textContent = `v${s.version}`;
    $("#call").value = s.call;
    $("#parks").value = s.parks; renderPreview();
    $("#outPath").textContent = s.out;
    $("#logCount").textContent = s.log_count ? `${s.log_count} 件` : "";
    segSet("#liveRun .seg", "prefix", st.prefix);
    renderListeners(); updateReceiver(s.receiver);
    setSource(st.source);
    if (s.live) enterRunning(s.live.parks, s.live.start);
  }
  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener("pywebviewready", boot);
})();
