// Drive the running dev app's web view without taking over the mouse (Windows, WebView2):
// start the app with WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333, then
//   node scripts/cdp.mjs eval "document.title"
//   node scripts/cdp.mjs click "#startLive"          (a CSS selector)
//   node scripts/cdp.mjs shot out.png
// Needs Node 22+ (built-in WebSocket). Window-level things (bar mode, on-top, file dialogs) still need
// a real desktop check.
import { writeFileSync } from "node:fs";

const [cmd, arg] = process.argv.slice(2);
const port = process.env.CDP_PORT || 9333;
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0;
const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expr) => {
  const d = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (d.result.exceptionDetails) throw new Error(d.result.exceptionDetails.exception?.description || "error");
  return d.result.result.value;
};

if (cmd === "eval") console.log(JSON.stringify(await evaluate(arg), null, 1));
else if (cmd === "click") console.log(await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(arg)});
  if (!el) return "not found"; el.click(); return "clicked"; })()`));
else if (cmd === "shot") {
  const d = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(arg || "shot.png", Buffer.from(d.result.data, "base64")); console.log(arg || "shot.png");
} else console.log("usage: cdp.mjs eval <js> | click <selector> | shot <file.png>");
ws.close();
