#!/usr/bin/env node
// Uses an existing Steam debugging endpoint, optionally through an SSH tunnel.
// It does not enable debugging or open additional listening ports.
const action = process.argv[2] ?? 'status';
const base = process.argv[3] ?? 'http://127.0.0.1:8080';
if (!['status', 'reload'].includes(action)) throw new Error('Use status or reload');
const pages = await (await fetch(`${base}/json/list`, { signal: AbortSignal.timeout(5000) })).json();
const page = pages.find(p => p.title === 'SteamVR - Keyboard') ?? pages.find(p => p.title === 'SharedJSContext');
if (!page) throw new Error('Steam UI is unavailable. Wake the Frame and open its keyboard.');
const wsURL = new URL(page.webSocketDebuggerUrl);
wsURL.host = new URL(base).host;
const ws = new WebSocket(wsURL);
const timeout = setTimeout(() => { console.error('Steam did not respond.'); process.exit(1); }, 10000);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
async function evaluate(expression) {
  return new Promise((resolve, reject) => {
    ws.onmessage = event => {
      const data = JSON.parse(event.data);
      if (data.id !== 1) return;
      if (data.error || data.result?.exceptionDetails) reject(new Error(JSON.stringify(data.error ?? data.result.exceptionDetails)));
      else resolve(data.result.result.value);
    };
    ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
  });
}
try {
  const expression = `(async () => {
    const root = window.ControllerStore ? window : window.opener;
    const controller = root?.ControllerStore?.GetControllers().find(c => c.eControllerType === 21);
    if (!controller) return {ok:false, reason:'Steam Frame controllers are asleep or disconnected; wake both controllers.'};
    const index = controller.nControllerIndex, input = root.SteamClient.Input;
    const before = await input.GetConfigForAppAndController(769,index);
    if (${JSON.stringify(action)} === 'reload') {
      if (before.bSelected) return {ok:false, reason:'A custom profile is selected; refusing to clear it.'};
      input.ClearSelectedConfigForApp(769,index,0);
    }
    await new Promise(r=>setTimeout(r,500));
    const after = await input.GetConfigForAppAndController(769,index);
    return {ok:true, action:${JSON.stringify(action)}, controller:controller.strName,
      before:{url:before.URL,selected:before.bSelected}, after:{url:after.URL,selected:after.bSelected,type:after.nControllerType}};
  })()`;
  const result = await evaluate(expression);
  console.log(JSON.stringify(result, null, 2));
  if (!result.ok) process.exitCode = 2;

} finally { clearTimeout(timeout); ws.close(); }
