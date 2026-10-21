// Alignment check by ink (the owner looks at this closely): in every view of the main window and in the bar,
// for each flex/grid row, compare where the items actually draw - a framed item (plate, chip, tag) by its
// box, text by the rows of inked pixels - and list items on one line whose middles differ by > 1.5 px.
//   node scripts/check_align.mjs [views] [bar overlays]     e.g.  node scripts/check_align.mjs live,history ask,cheer
// Needs the dev app with CDP (see CLAUDE.md) and Python with Pillow (check_align.py). Look at a close-up before
// calling a number real: descenders and items spanning two lines fool it.
import { writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url)), port = process.env.CDP_PORT || 9333, S = 2;
const png = join(tmpdir(), "potaroo-align.png"), json = join(tmpdir(), "potaroo-align.json");
const python = process.platform === "win32" ? ["py", "-3"] : ["python3"];

// rows: every visible flex/grid row container, its children that share a line, framed or not (CSS px)
const ROWS = `(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && r.bottom > 0 && r.top < innerHeight; };
  const name = (e) => e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (typeof e.className === "string" && e.className.trim() ? "." + e.className.trim().split(/\\s+/).join(".") : "");
  const framed = (e) => { const cs = getComputedStyle(e);
    return !/rgba\\(0, 0, 0, 0\\)|transparent/.test(cs.backgroundColor) || parseFloat(cs.borderTopWidth) > 0 || cs.backgroundImage !== "none" || /^(INPUT|BUTTON|SELECT|IMG|SVG)$/i.test(e.tagName); };
  const rows = [];
  for (const p of document.querySelectorAll("body *")) {
    if (!vis(p)) continue;
    const cs = getComputedStyle(p);
    if (!/flex|grid/.test(cs.display) || cs.flexDirection === "column") continue;
    const kids = [...p.children].filter(vis).map((k) => { const r = k.getBoundingClientRect(); return { name: name(k), framed: framed(k), x: r.x, y: r.y, w: r.width, h: r.height }; }).filter((k) => k.h <= 70);
    const line = kids.filter((a) => kids.some((b) => a !== b && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > Math.min(a.h, b.h) * 0.6));
    if (line.length >= 2) rows.push({ row: name(p), kids: line });
  }
  return rows;
})()`;

async function conn(bar) {
  const t = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page" && t.url.endsWith("#bar") === bar);
  if (!t) return null;
  const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
  let id = 0; const pend = new Map(); ws.onmessage = (m) => { const d = JSON.parse(m.data);   // only answers to our own numbered requests
    const f = Number.isInteger(d.id) && pend.has(d.id) ? pend.get(d.id) : null; if (typeof f === "function") { pend.delete(d.id); f(d); } };
  const send = (method, params = {}) => new Promise((r) => { pend.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
  const ev = async (e) => (await send("Runtime.evaluate", { expression: e, awaitPromise: true, returnByValue: true })).result.result?.value;
  // a fixed function run in the page with values passed as arguments: nothing from the command line becomes code
  const win = (await send("Runtime.evaluate", { expression: "globalThis" })).result.result.objectId;
  const call = async (fn, ...args) => (await send("Runtime.callFunctionOn", { objectId: win, functionDeclaration: fn.toString(),
    arguments: args.map((value) => ({ value })), awaitPromise: true, returnByValue: true })).result.result?.value;
  return { send, ev, call, close: () => ws.close() };
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function check(c, label) {
  const [w, h] = await c.ev("[innerWidth, innerHeight]");
  writeFileSync(json, JSON.stringify(await c.ev(ROWS)));
  const d = await c.send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: w, height: h, scale: S } });
  writeFileSync(png, Buffer.from(d.result.data, "base64"));
  console.log("=== " + label + "\n" + execFileSync(python[0], [...python.slice(1), join(here, "check_align.py"), png, json, String(S)], { encoding: "utf8" }).trim());
}

const main = await conn(false);
// only the app's own view and overlay names
const VIEWS = ["live", "spots", "build", "history", "record", "config"], OVERLAYS = ["ask", "cheer", "hunted"];
const pick = (arg, known, all) => (arg ? arg.split(",") : all).filter((x) => known.includes(x));
for (const v of pick(process.argv[2], VIEWS, VIEWS)) {
  await main.call((view) => { [...document.querySelectorAll(".rail [data-view]")].find((b) => b.dataset.view === view)?.click();
    return new Promise((r) => setTimeout(r, 1500)); }, v);
  const more = await main.ev(`(() => { const m = document.querySelector('.main'); m.scrollTop = 0; return m.scrollHeight - m.clientHeight; })()`);
  for (let y = 0; y <= more && y < 3000; y += 600) {
    await main.ev(`document.querySelector('.main').scrollTop = ${y}; new Promise(r => setTimeout(r, 200))`);
    await check(main, v + (y ? " @" + y : ""));
  }
}
await main.ev(`document.querySelector('.main').scrollTop = 0; document.querySelector('.rail [data-view=live]').click()`);
main.close();

const bar = await conn(true);
if (bar) {
  await check(bar, "bar");
  // overlays, display only, on a copy (the page's own poll would hide the real P2P question)
  for (const o of pick(process.argv[3], OVERLAYS, [])) {
    await bar.call((id) => {                     // a 3fer in the plates, a call in the question
      const c = document.getElementById(id).cloneNode(true); c.id = "alignTest"; c.hidden = false;
      const plates = (box) => { box.textContent = ""; ["US-11782", "US-12320", "US-2153"].forEach((ref, i) => {
        if (i) { const j = document.createElement("span"); j.className = "plate-join"; j.textContent = "+"; box.append(j); }
        const p = document.createElement("span"), b = document.createElement("b"); p.className = "plate";
        b.textContent = ref.split("-")[0] + "-"; p.append(b, ref.split("-")[1]); box.append(p); }); };
      c.querySelectorAll("[id]").forEach((e) => { if (/Parks$/.test(e.id)) plates(e); if (e.id === "askCall") e.textContent = "KC4JAB"; e.id += "T"; });
      document.body.appendChild(c);
    }, o);
    await wait(300);
    await check(bar, "bar #" + o);
    await bar.ev(`document.querySelector('#alignTest').remove()`);
  }
  bar.close();
}
