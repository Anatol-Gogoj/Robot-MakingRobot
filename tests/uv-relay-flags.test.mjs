// Issue #186: a lamp or valve the UV block sent ON always gets its OFF.
//
// runUvBlock() used to set uvIsOn / arIsOpen only on the lamp-on / argon-open M42's own 'ok',
// and its finally sent the OFF only when the flag was set. A Stop, a fault or the step timeout
// landing between the write and that 'ok' left the lamp, or the valve, on: a few ms on Web
// Serial, a network round trip on the Pi bridge, and the whole 90 s step timeout when the 'ok'
// never came. The fix records "an ON was sent" before the send and keys the OFF on that; the
// Run Log still takes the cure from the lamp-on's own 'ok', and gets a uv.off only for a uv.on
// it has (its uv.off handler would otherwise rewrite the open layer's last finished cure).
//
// These checks drive the real runUvBlock() through the real ok ledger, on Web Serial and on the
// bridge-echo path, answering each command by hand so a Stop, a fault or a timeout can land
// inside the window. On the bridge the window has two parts: before the bridge's TX echo (the
// network round trip) and after it, before Marlin's 'ok'.
//
//   node tests/uv-relay-flags.test.mjs RMR_Controller.html RMR_Touch.html
//
// Given several pages, it runs itself once per page, each in its own process (its own vm and
// timers), so one row in tests/run.mjs covers both.
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'url';
import { loadUI } from './harness.mjs';

const FILES = process.argv.slice(2);
if (FILES.length > 1) {
  let bad = 0;
  for (const f of FILES) {
    const r = spawnSync(process.execPath, [fileURLToPath(import.meta.url), f], { encoding: 'utf8' });
    process.stdout.write((r.stdout || '') + (r.stderr || ''));
    if (r.status !== 0) bad++;
  }
  process.exit(bad ? 1 : 0);
}
const FILE = FILES[0];
const { ev, el } = loadUI(FILE);
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (cond, limitMs = 2000) => { const t0 = Date.now(); while (!cond() && Date.now() - t0 < limitMs) await sleep(5); return cond(); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log(`\n=== ${FILE.split(/[\\/]/).pop()} ===`);
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
ev('isConnected = true');

// The link: a Web Serial writer, and a bridge socket. Both append to one wire.
const wire = ev('globalThis.__wire = []');   // must live in the sandbox realm
ev(`writer = { write: async b => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); } }`);
ev('globalThis.WebSocket = { OPEN: 1 }');    // sendCmd checks ws.readyState against it
const rx = line => ev('processLine')(line);
const bridge = m => ev('handleWSMessage')(JSON.stringify(m));
let BRIDGE = false;
function useBridge(on) {
  BRIDGE = !!on;
  ev('useWS = ' + BRIDGE);
  ev(BRIDGE ? `ws = { readyState: 1, send: c => { globalThis.__wire.push(String(c)); } }` : 'ws = null');
}

// The fake board answers the written commands in order. On the bridge an answer is the
// bridge's TX echo (the write reached the port), then Marlin's 'ok'.
let answered = 0;            // wire index of the next command to answer
const echoed = new Set();    // bridge: wire indexes whose echo has been delivered
function echo(i) { if (BRIDGE && !echoed.has(i)) { bridge({ _rmr: 'tx', cmd: wire[i], source: 'ws' }); echoed.add(i); } }
function answer(i, before) { echo(i); if (before) rx(before); rx('ok'); }
// Answer everything written ahead of `target`; return the index of `target`, written and unanswered.
async function pumpTo(target) {
  const t0 = Date.now();
  while (Date.now() - t0 < 2000) {
    if (answered < wire.length) {
      if (wire[answered] === target) return answered;
      answer(answered++);
    } else await sleep(2);
  }
  return -1;
}
// Answer everything until the run ends.
async function pumpAll() {
  const t0 = Date.now();
  while (ev('seqRunning') && Date.now() - t0 < 3000) {
    if (answered < wire.length) answer(answered++); else await sleep(2);
  }
}
// The late answers: the held command's 'ok' (and echo) and everything written after it.
async function drainLate() { while (answered < wire.length) answer(answered++); await sleep(20); }

// The step timeout, shortened for the relay M42s while __shortM42 is set, so the case of an
// 'ok' that never comes runs in milliseconds instead of 90 s.
ev(`globalThis.__shortM42 = false; globalThis.__awaitOrig = seqAwaitOk;
    seqAwaitOk = (ms, label) => globalThis.__awaitOrig(globalThis.__shortM42 && /^M42 /.test(label) ? 150 : ms, label)`);

// Run Log: an armed device, and every event the page hands the module.
const log = ev('rmrLog');
log.createDevice({ id: 'F-186', material: 'test', thicknessUm: 70, targetLayers: 3, rpm: 1000, holdS: 50, cureS: 30, dispenseMl: 0.05, firstElectrode: 'P' });
log.setLogging(true);
const events = ev('globalThis.__rl = []');
ev('{ const orig = rmrLog.event; rmrLog.event = (k, d) => { globalThis.__rl.push({ k, d: d || {} }); return orig(k, d); }; }');
const uvEvents = () => events.filter(e => /^uv\./.test(e.k));
const layers = () => log.device.rows.filter(r => r.kind === 'layer');
const status = () => String(el('seqStatus').innerHTML);

const LAMP_ON = 'M42 P4 S1', LAMP_OFF = 'M42 P4 S0', AR_OPEN = 'M42 P42 S1', AR_CLOSE = 'M42 P42 S0';

// Each case starts idle with nothing owed and nothing on the wire.
async function fresh({ argon, cure = 30, shortM42 = false }) {
  if (ev('seqRunning')) { ev('seqStop')(); await until(() => !ev('seqRunning')); }
  wire.length = 0; answered = 0; echoed.clear(); events.length = 0;
  ev('wsOwnPending = []'); ev('okLedgerReset')();
  ev('globalThis.__shortM42 = ' + shortM42);   // before the run starts: the block reaches its first seqCmd at once
  el('uvTime').value = String(cure); el('uvSeqPin').value = '4';
  el('uvLid').checked = false; el('uvSpinHome').checked = false;
  el('uvArgon').checked = argon; el('uvArgonPin').value = '42';
  el('uvArgonLead').value = '0'; el('uvArgonLag').value = '0.05';
  ev('seqSetHomed')(true, 'test');
  ev('seqRunBlock')('uv');
}

// Web Serial; the bridge before its echo; the bridge after its echo, before the 'ok'.
const PATHS = [['Web Serial', false, false], ['bridge, before the echo', true, false], ['bridge, after the echo', true, true]];

// == 1: a Stop between the lamp-on write and its 'ok' ==
console.log("\n1  a Stop between the lamp-on write and its 'ok' sends the lamp-off; the Run Log records no cure");
for (const [tag, bridgeOn, echoFirst] of PATHS) {
  useBridge(bridgeOn);
  await fresh({ argon: false });
  const i = await pumpTo(LAMP_ON);
  ok(tag + ': the lamp-on was written', i === 0, wire);
  if (echoFirst) echo(i);
  ev('seqStop')();
  await until(() => !ev('seqRunning'));
  ok(tag + ': Stop sent M410, then the lamp-off', same(wire.slice(i + 1), ['M410', LAMP_OFF]), wire.slice(i + 1));
  ok(tag + ': the run reads Stopped', ev('seqRunning') === false && /Stopped/.test(status()), status());
  await drainLate();   // the lamp-on's 'ok' comes after all, then the others'
  ok(tag + ": the Run Log has no uv.on or uv.off, even once the lamp-on's late 'ok' came", uvEvents().length === 0, uvEvents());
  ok(tag + ': no layer row holds a cure', layers().every(r => !r.cure.onAt), layers().map(r => r.cure));
  ok(tag + ': nothing more was sent after the late answers', same(wire.slice(i + 1), ['M410', LAMP_OFF]), wire.slice(i + 1));
}

// == 2: a Stop between the argon-open write and its 'ok' ==
console.log("\n2  a Stop between the argon-open write and its 'ok' sends the argon-close, and no lamp command");
for (const [tag, bridgeOn, echoFirst] of PATHS) {
  useBridge(bridgeOn);
  await fresh({ argon: true });
  const i = await pumpTo(AR_OPEN);
  ok(tag + ': the argon-open was written first', i === 0, wire);
  if (echoFirst) echo(i);
  ev('seqStop')();
  await until(() => !ev('seqRunning'));
  ok(tag + ': Stop sent M410, then the argon-close', same(wire.slice(i + 1), ['M410', AR_CLOSE]), wire.slice(i + 1));
  ok(tag + ': no lamp command went out', !wire.includes(LAMP_ON) && !wire.includes(LAMP_OFF), wire);
  await drainLate();
  ok(tag + ': the Run Log has no uv.on or uv.off', uvEvents().length === 0, uvEvents());
}

// == 3: a normal cure ==
console.log('\n3  a normal cure sends exactly one lamp-off and one argon-close, and the Run Log records it');
for (const [tag, bridgeOn] of PATHS.slice(0, 2)) {
  const path = bridgeOn ? 'bridge' : tag;
  useBridge(bridgeOn);
  await fresh({ argon: true, cure: 0.1 });
  await pumpAll();
  ok(path + ': order: argon open, lamp on, lamp off, argon close; nothing after',
     same([...wire], [AR_OPEN, LAMP_ON, LAMP_OFF, AR_CLOSE]), wire);
  ok(path + ': exactly one lamp-off and one argon-close',
     wire.filter(c => c === LAMP_OFF).length === 1 && wire.filter(c => c === AR_CLOSE).length === 1, wire);
  ok(path + ': the block completed', ev('seqRunning') === false && /UV<\/b> complete/.test(status()), status());
  ok(path + ': the Run Log has one uv.on and one uv.off, not aborted',
     same(uvEvents().map(e => e.k), ['uv.on', 'uv.off']) && !uvEvents()[1].d.aborted, uvEvents());
  const r = layers().at(-1);
  ok(path + ': the layer row holds the finished cure', !!r && !!r.cure.onAt && !!r.cure.offAt && r.cure.aborted === false, r && r.cure);
}

// == 4: after a finished cure, a Stop in the lamp-on window leaves that cure's record alone ==
// A uv.off with no uv.on would land on the open layer, whose cure is the finished one above:
// the Run Log's uv.off handler would move its off time and mark it cut short.
console.log("\n4  after a finished cure, a Stop before the next lamp-on's 'ok' leaves the recorded cure alone");
for (const [tag, bridgeOn, echoFirst] of PATHS) {
  useBridge(bridgeOn);
  const before = JSON.stringify(layers().at(-1).cure);
  await fresh({ argon: false });
  const i = await pumpTo(LAMP_ON);
  if (echoFirst) echo(i);
  ev('seqStop')();
  await until(() => !ev('seqRunning'));
  ok(tag + ': the lamp-off was sent', wire.slice(i + 1).includes(LAMP_OFF), wire.slice(i + 1));
  await drainLate();
  ok(tag + ': no uv.on or uv.off reached the Run Log', uvEvents().length === 0, uvEvents());
  ok(tag + ': the finished cure is unchanged (on, off, actual time, not cut short)', JSON.stringify(layers().at(-1).cure) === before,
     [JSON.parse(before), layers().at(-1).cure]);
}

// == 5: the lamp-on's 'ok' never comes ==
console.log("\n5  the lamp-on's 'ok' never comes: the step times out and the lamp-off goes out");
for (const [tag, bridgeOn] of PATHS.slice(0, 2)) {
  const path = bridgeOn ? 'bridge' : tag;
  useBridge(bridgeOn);
  await fresh({ argon: false, shortM42: true });
  const i = await pumpTo(LAMP_ON);
  echo(i);   // the write reached the board; its 'ok' is lost
  await until(() => !ev('seqRunning'));
  ok(path + ': the run failed on the timeout', ev('seqRunning') === false && /no "ok" for "M42 P4 S1"/.test(status()), status());
  ok(path + ': the lamp-off went out after the timeout', same(wire.slice(i + 1), [LAMP_OFF]), wire.slice(i + 1));
  ok(path + ': the Run Log records no cure', uvEvents().length === 0, uvEvents());
}

// == 6: a fault in the lamp-on window, and the lid interlock refusing the lamp-on ==
console.log("\n6  a fault before the lamp-on's 'ok', or the interlock refusing it, sends the lamp-off");
for (const [tag, bridgeOn] of PATHS.slice(0, 2)) {
  const path = bridgeOn ? 'bridge' : tag;
  useBridge(bridgeOn);
  await fresh({ argon: false });
  const i = await pumpTo(LAMP_ON);
  echo(i);
  rx('echo:MOTOR POWER LOST');   // the firmware cleared its queue: the lamp-on's 'ok' will not come
  await until(() => !ev('seqRunning'));
  ok(path + ': MOTOR POWER LOST: the run failed', ev('seqRunning') === false && /MOTOR POWER LOST/.test(status()), status());
  ok(path + ': MOTOR POWER LOST: the lamp-off went out', same(wire.slice(i + 1), [LAMP_OFF]), wire.slice(i + 1));
  ok(path + ': MOTOR POWER LOST: the Run Log records no cure', uvEvents().length === 0, uvEvents());

  await fresh({ argon: false });
  const j = await pumpTo(LAMP_ON);
  answer(answered++, 'echo:UV inhibited: lid open (interlock)');   // refused, then its 'ok'
  await until(() => !ev('seqRunning'));
  ok(path + ': interlock refusal: the run failed with the refusal', ev('seqRunning') === false && /lid interlock refused UV/.test(status()), status());
  ok(path + ': interlock refusal: a lamp-off still went out', same(wire.slice(j + 1), [LAMP_OFF]), wire.slice(j + 1));
  ok(path + ': interlock refusal: the Run Log records no cure', uvEvents().length === 0, uvEvents());
}

// == 7: a Stop between the lamp-off write and its 'ok' ==
// The OFF is keyed on its own 'ok' too, so the finally sends it again (harmless), and the
// argon, still open, is closed. The cure was recorded, so its uv.off carries aborted.
console.log("\n7  a Stop between the lamp-off write and its 'ok' sends the lamp-off again and closes the argon");
for (const [tag, bridgeOn, echoFirst] of PATHS) {
  useBridge(bridgeOn);
  await fresh({ argon: true, cure: 0.1 });
  const i = await pumpTo(LAMP_OFF);
  ok(tag + ': argon open, lamp on, lamp off written', same(wire.slice(0, i + 1), [AR_OPEN, LAMP_ON, LAMP_OFF]), wire);
  if (echoFirst) echo(i);
  ev('seqStop')();
  await until(() => !ev('seqRunning'));
  ok(tag + ': Stop sent M410, the lamp-off again, then the argon-close', same(wire.slice(i + 1), ['M410', LAMP_OFF, AR_CLOSE]), wire.slice(i + 1));
  await drainLate();
  ok(tag + ': the Run Log has the uv.on and one uv.off, aborted',
     same(uvEvents().map(e => e.k), ['uv.on', 'uv.off']) && uvEvents()[1].d.aborted === true, uvEvents());
}

useBridge(false);
console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
