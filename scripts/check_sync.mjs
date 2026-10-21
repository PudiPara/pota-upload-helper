// How long after a QSO arrives does its row show in the main window and in the bar? (They should agree:
// both poll on the same second.) Sends test QSOs: use the copy instance (scripts/copy_instance.py).
//   CDP_PORT=9334 node scripts/check_sync.mjs [udp port, default 22299]
import { execFileSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const port = process.env.CDP_PORT || 9334, udp = process.argv[2] || "22299";
const send = join(dirname(fileURLToPath(import.meta.url)), "send_test_qso.py");
const python = process.platform === "win32" ? ["py", "-3"] : ["python3"];
async function conn(bar) {
  const t = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page" && t.url.endsWith("#bar") === bar);
  if (!t) throw new Error(bar ? "no bar window: start an activation first" : "no main window");
  const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
  let id = 0; const pend = new Map(); ws.onmessage = (m) => { const d = JSON.parse(m.data); pend.get(d.id)?.(d); };
  const ev = async (e) => (await new Promise((r) => { pend.set(++id, r); ws.send(JSON.stringify({ id, method: "Runtime.evaluate", params: { expression: e, returnByValue: true } })); })).result.result?.value;
  return { ev, close: () => ws.close() };
}
const main = await conn(false), bar = await conn(true);
const watch = (sel, call) => `window.__seen = 0; new MutationObserver(() => { if (!window.__seen && document.querySelector('${sel}').textContent.includes('${call}')) window.__seen = Date.now(); })
  .observe(document.querySelector('${sel}'), { childList: true, subtree: true, characterData: true }); 1`;
for (const call of ["K2SYNA", "K2SYNB", "K2SYNC"]) {
  await main.ev(watch("#qsos", call)); await bar.ev(watch("#barQsos", call));
  const sent = Date.now();
  execFileSync(python[0], [...python.slice(1), send, udp, call]);
  await new Promise((r) => setTimeout(r, 3500));
  const a = await main.ev("window.__seen"), b = await bar.ev("window.__seen");
  console.log(`${call}: main +${a - sent} ms, bar +${b - sent} ms, apart ${Math.abs(a - b)} ms`);
}
main.close(); bar.close();
