// The README's pictures, one set per language: docs/<lang>/{live,map,bar,record,settings,build,start}.webp
// Run on the copy instance (python scripts/copy_instance.py) while it records an activation with a few QSOs:
//   CDP_PORT=9334 node scripts/readme_shots.mjs [lang ...]            live, map, bar, record, settings, build
// then with the copy not recording (settings.json "live": null, start it again):
//   CDP_PORT=9334 node scripts/readme_shots.mjs --start [lang ...]    start
// Dark colours, the main window at 1180 x 800 CSS px.
import { mkdirSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const port = process.env.CDP_PORT || 9334, SCALE = 1.25;
// made-up callsigns: the demo QSOs use OURS, anything else on screen is shown as one of FAKE
const OURS = ["JL1FVA", "JA1XYZ", "JH1ABC", "JR2DEF", "JE3GHI", "JA7QRZ", "K9ABC"];
const FAKE = ["W5XYZ", "K4QRZ", "N7ABC", "JR6XYZ", "DL1QRZ", "F4ABC", "VK2XYZ", "KD8QRZ", "W9ABC", "N2XYZ", "K6QRZ", "JA8ABC", "G4XYZ", "WB4QRZ", "KC7ABC", "N5XYZ", "AB1QRZ", "KE0ABC", "W3XYZ", "JH4QRZ"];
const LANGS = ["ja", "en", "zh-CN", "zh-TW", "fr", "de", "es", "it", "pt-BR", "ko", "pl"];
const langs = process.argv.slice(2).filter((l) => LANGS.includes(l));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function conn(bar) {
  const t = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page" && t.url.endsWith("#bar") === bar);
  if (!t) return null;
  const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
  let id = 0; const pend = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data);   // only answers to our own numbered requests
    const f = Number.isInteger(d.id) && pend.has(d.id) ? pend.get(d.id) : null; if (typeof f === "function") { pend.delete(d.id); f(d); } };
  const send = (method, params = {}) => new Promise((r) => { pend.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
  const win = (await send("Runtime.evaluate", { expression: "globalThis" })).result.result.objectId;
  const call = async (fn, ...args) => (await send("Runtime.callFunctionOn", { objectId: win, functionDeclaration: fn.toString(),
    arguments: args.map((value) => ({ value })), awaitPromise: true, returnByValue: true })).result.result?.value;
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "dark" }] });
  // every callsign on screen that is not one of ours becomes a made-up one (the README shows no real station)
  const anonymize = () => call((ours, fake) => {
    const seen = window.__fakeCalls || (window.__fakeCalls = {});
    const calls = [...document.querySelectorAll(".spot-call, .qso-call, #askCall")].map((e) => (e.firstChild ? e.firstChild.textContent : e.textContent).trim())
      .filter((c) => c && !ours.includes(c));
    for (const c of calls) if (!seen[c]) seen[c] = fake[Object.keys(seen).length % fake.length];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) for (const [real, f] of Object.entries(seen)) if (n.textContent.includes(real)) n.textContent = n.textContent.split(real).join(f);
  }, OURS, FAKE);
  const shot = async (file, clip) => {
    await anonymize();
    const [w, h] = await call(() => [innerWidth, innerHeight]);
    const d = await send("Page.captureScreenshot", { format: "webp", quality: 88, clip: { x: 0, y: 0, width: w, height: h, ...clip, scale: SCALE * (bar ? 1.6 : 1) } });
    writeFileSync(file, Buffer.from(d.result.data, "base64"));
  };
  return { send, call, shot, close: () => ws.close() };
}

if (!process.argv.includes("--start")) {
const main = await conn(false);
await main.send("Emulation.setDeviceMetricsOverride", { width: 1180, height: 800, deviceScaleFactor: 1, mobile: false });
const view = (v, tab) => main.call(async (v, tab) => {
  document.querySelector(`.rail [data-view="${v}"]`).click();
  if (tab) document.querySelector(`[data-tab="${tab}"]`)?.click();
  document.querySelector(".main").scrollTop = 0;
  await new Promise((r) => setTimeout(r, v === "record" || tab === "map" ? 3500 : 1200));
}, v, tab || "");

for (const lang of langs) {
  const dir = join(root, "docs", lang); mkdirSync(dir, { recursive: true });
  await main.call(async (l) => { const s = document.querySelector("#lang"); s.value = l; s.dispatchEvent(new Event("change")); await new Promise((r) => setTimeout(r, 1500)); }, lang);
  await view("live", "list"); await main.shot(join(dir, "live.webp"));
  await view("live", "map"); await main.shot(join(dir, "map.webp"));
  await view("live", "list");
  await main.call(async () => { await pywebview.api.set_bar(false); await new Promise((r) => setTimeout(r, 1500)); await pywebview.api.set_bar(true); await new Promise((r) => setTimeout(r, 5000)); });
  const bar = await conn(true);                    // reopened: it starts in the new language
  if (bar) { await bar.shot(join(dir, "bar.webp")); bar.close(); }
  await view("record"); await main.shot(join(dir, "record.webp"));
  await view("config", "loggers"); await main.shot(join(dir, "settings.webp"));
  await view("build"); await main.shot(join(dir, "build.webp"));
  console.log(lang, "done");
}
} else {
// the start screen: a 2fer that really overlaps (JP-0016 + JP-1445, both in Shizuoka)
const start = await conn(false);
await start.send("Emulation.setDeviceMetricsOverride", { width: 1180, height: 800, deviceScaleFactor: 1, mobile: false });
for (const lang of langs) {
  await start.call(async (l) => {
    const s = document.querySelector("#lang"); s.value = l; s.dispatchEvent(new Event("change")); await new Promise((r) => setTimeout(r, 1500));
    document.querySelector('.rail [data-view="live"]').click();
    document.querySelectorAll("#parkExtra .park-row button").forEach((b) => b.click());
    const i = document.querySelector("#parks"); i.value = "JP-0016,JP-1445"; i.dispatchEvent(new Event("input"));   // a real 2fer (the owner's)
    await new Promise((r) => setTimeout(r, 3500));
  }, lang);
  await start.shot(join(root, "docs", lang, "start.webp"));
}
await start.call(async () => { const s = document.querySelector("#lang"); s.value = "ja"; s.dispatchEvent(new Event("change")); });
start.close();
}
console.log("all done");
