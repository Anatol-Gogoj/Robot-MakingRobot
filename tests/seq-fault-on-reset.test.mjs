// Drives the shipped Process Sequencer in both UIs (issue #182). A board reset or a lost link
// while the run sits in a browser-timed wait (a UV cure, a Run Log hold), with no step waiting
// for its 'ok', must fail the run at once: the UV block's finally sends the lamp-off and the
// argon-close where it still can, and the Run Log records the cure as cut short. With no run
// going, the same lines change nothing.
//
//   node tests/seq-fault-on-reset.test.mjs RMR_Controller.html RMR_Touch.html
import { loadUI } from './harness.mjs';

let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 0));
const sleep = ms => new Promise(r => setTimeout(r, ms));
// Wait for cond, polling every 10 ms; returns the time it took (or the limit).
const until = async (cond, limitMs = 1500) => { const t0 = Date.now(); while (!cond() && Date.now() - t0 < limitMs) await sleep(10); return Date.now() - t0; };

const CURE_S = 30;      // the UV block's browser-timed cure; every fault below must end the run long before it
const FAST_MS = 1000;   // "at once": seqSleep polls every 100 ms, a Run Log hold every 500 ms

for (const FILE of process.argv.slice(2)) {
  const { ev, el } = loadUI(FILE);
  console.log(`\n=== ${FILE.split(/[\\/]/).pop()} ===`);

  // Fake link: a Web Serial writer, and a bridge socket for the WS cases.
  const wire = ev('globalThis.__wire = []');   // must live in the sandbox realm
  ev('isConnected = true');
  ev(`writer = { write: async b => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); } }`);
  const rx = line => ev('processLine')(line);
  const bridge = m => ev('handleWSMessage')(JSON.stringify(m));
  const last = () => wire.at(-1);
  const webOk = () => rx('ok');
  const bridgeOk = cmd => { bridge({ _rmr: 'tx', cmd, source: 'ws' }); rx('ok'); };   // the echo, then its 'ok'
  ev('globalThis.WebSocket = { OPEN: 1 }');   // sendCmd checks ws.readyState against it
  const useBridge = on => {
    ev('useWS = ' + !!on);
    ev(on ? `ws = { readyState: 1, send: c => { globalThis.__wire.push(String(c)); } }` : 'ws = null');
    ev('wsOwnPending = []'); ev('okLedgerReset')();
  };
  if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
  const seqStatus = () => String(el('seqStatus').innerHTML);

  // Run Log: an armed device, and every event the page hands the module.
  const log = ev('rmrLog');
  log.createDevice({ id: 'F-182', material: 'test', thicknessUm: 70, targetLayers: 3, rpm: 1000, holdS: 50, cureS: CURE_S, dispenseMl: 0.05, firstElectrode: 'P' });
  log.setLogging(true);
  const events = ev('globalThis.__rl = []');
  ev('{ const orig = rmrLog.event; rmrLog.event = (k, d) => { globalThis.__rl.push({ k, d: d || {} }); return orig(k, d); }; }');
  const uvOffs = () => events.filter(e => e.k === 'uv.off');
  const faults = () => events.filter(e => e.k === 'seq.fault');
  const layerRow = () => log.device.rows.filter(r => r.kind === 'layer').at(-1);
  // Each case starts idle with nothing owed, so a failure on an unfixed page (a run that never
  // ended) stays in its own case.
  async function fresh() {
    if (ev('seqRunning')) { ev('seqStop')(); await until(() => !ev('seqRunning')); }
    ev('wsOwnPending = []'); ev('okLedgerReset')();
    events.length = 0;
  }

  // The UV block: argon opens with the lamp, then a 30 s cure with nothing in flight.
  el('uvTime').value = String(CURE_S); el('uvSeqPin').value = '4';
  el('uvLid').checked = false; el('uvSpinHome').checked = false;
  el('uvArgon').checked = true; el('uvArgonLead').value = '0'; el('uvArgonLag').value = '1'; el('uvArgonPin').value = '42';
  async function startCure(answer, tag) {
    await fresh();
    ev('seqSetHomed')(true, 'test');
    ev('seqRunBlock')('uv');
    await flush();
    ok(tag + ': argon open sent first', last() === 'M42 P42 S1', last());
    answer('M42 P42 S1'); await flush();
    ok(tag + ': lamp on sent', last() === 'M42 P4 S1', last());
    answer('M42 P4 S1'); await flush();
    ok(tag + ': the run sits in its cure with no step waiting for an ok',
      ev('seqRunning') === true && ev('seqWaiter') === null && events.some(e => e.k === 'uv.on'), [ev('seqRunning'), ev('seqWaiter')]);
    return wire.length;
  }
  // The run failed fast, named the cause, and the Run Log holds the cure as cut short.
  async function expectCutCure(tag, statusRe) {
    const took = await until(() => !ev('seqRunning'));
    ok(tag + ': the run failed at once, not at the end of the ' + CURE_S + ' s cure', !ev('seqRunning') && took < FAST_MS, took);
    ok(tag + ': the status names the cause', statusRe.test(seqStatus()), seqStatus());
    ok(tag + ': the fault reached the Run Log', faults().length === 1 && statusRe.test('Error: ' + faults()[0].d.reason), faults());
    ok(tag + ": the Run Log's uv.off carries aborted", uvOffs().length === 1 && uvOffs()[0].d.aborted === true, uvOffs());
    const r = layerRow();
    ok(tag + ': the layer row records the cure as cut short', !!r && r.cure.aborted === true && !!r.cure.offAt, r && r.cure);
  }

  // == A: with no run going, the same lines fault nothing ==
  // First, while the page has never faulted, so seqFaultReason is still null.
  console.log("\nA  no run going: a 'start', a closed port, a dropped write and a connect fault nothing");
  {
    const n = wire.length;
    rx('start');
    bridge({ _rmr: 'status', serial: 'closed', port: '/dev/rmr-mega' });
    bridge({ _rmr: 'error', msg: 'serial not open; dropped: M114' });
    rx('Resend: 1');
    ev('setConnected')(true);
    await flush();
    ok('no fault is set or recorded', ev('seqFaultReason') === null && faults().length === 0, [ev('seqFaultReason'), faults()]);
    ok('nothing was sent', wire.length === n, wire.slice(n));
    // ...and the next run is not poisoned by them: the Homing block runs to completion.
    el('homeAll').checked = true; el('homeSpin').checked = false;   // homeSpin: Controller only, no M752 after the home
    ev('seqRunBlock')('homing');
    await flush();
    ok('a run started afterwards sends its G28', last() === 'G28' && ev('seqRunning') === true, last());
    webOk(); await flush();
    webOk(); await flush();   // <- the M118 marker's
    ok('...and completes', ev('seqRunning') === false && /complete/.test(seqStatus()), seqStatus());
  }

  // == B: a firmware restart during the cure (Web Serial) ==
  console.log("\nB  a firmware 'start' during a UV cure fails the run at once");
  {
    const n = await startCure(webOk, 'start');
    rx('start');
    await expectCutCure('start', /Error: firmware restarted during the run/);
    ok('start: lamp off, then argon closed, sent to the rebooted board', wire.slice(n).join(' | ') === 'M42 P4 S0 | M42 P42 S0', wire.slice(n));
    ok('start: the message claims no lamp state of its own', /#131 firmware turns the UV lamp and valve relays off at boot/.test(seqStatus()), seqStatus());
    ev('okLedgerReset')();
  }

  // == C: the bridge loses the port, or drops a write, during the cure ==
  console.log('\nC  the bridge losing the serial port, or failing a write, during a UV cure fails the run at once');
  useBridge(true);
  for (const [tag, act, re] of [
    ['port closed', () => bridge({ _rmr: 'status', serial: 'closed', port: '/dev/rmr-mega' }), /Error: the bridge lost the serial port during the run: .*may still be on/],
    ['write failed', () => bridge({ _rmr: 'error', msg: 'serial write failed: [Errno 5] Input/output error' }), /Error: the bridge could not write to the board during the run \(serial write failed: .*\): .*may still be on/],
  ]) {
    const n = await startCure(bridgeOk, tag);
    act();
    await expectCutCure(tag, re);
    ok(tag + ': lamp off, then argon closed, handed to the bridge', wire.slice(n).join(' | ') === 'M42 P4 S0 | M42 P42 S0', wire.slice(n));
    ev('wsOwnPending = []'); ev('okLedgerReset')();
  }
  useBridge(false);

  // == D: a disconnect during the cure ==
  // Nothing can reach the board now, so the lamp-off cannot go out. The fault says the lamp may
  // still be on instead of claiming either state.
  console.log('\nD  a disconnect during a UV cure fails the run at once');
  {
    const n = await startCure(webOk, 'disconnect');
    ev('setConnected')(false);
    await expectCutCure('disconnect', /Error: disconnected during the run: a UV lamp or valve the run switched on may still be on/);
    ok('disconnect: nothing could be sent', wire.length === n, wire.slice(n));
    ev('isConnected = true');   // "reconnect" for the next cases
    ev('okLedgerReset')();
  }

  // == E: the firmware flushing its RX ring, or the ledger overflowing, during the cure ==
  console.log("\nE  a 'Resend:' or a ledger overflow during a UV cure fails the run at once");
  for (const [tag, act, re] of [
    ['Resend', () => rx('Resend: 1'), /Error: the firmware flushed its receive buffer during the run/],
    ['overflow', () => { for (let i = 0; i < ev('OK_LEDGER_MAX') + 2; i++) ev('sendCmd')('M114'); }, /Error: ok ledger overflow during the run/],
  ]) {
    const n = await startCure(webOk, tag);
    act();
    await expectCutCure(tag, re);
    ok(tag + ': the lamp-off and the argon-close were sent', wire.slice(n).includes('M42 P4 S0') && wire.slice(n).includes('M42 P42 S0'), wire.slice(n));
    ev('okLedgerReset')();
  }

  // == F: a Run Log hold ends with RunLogAbort ==
  // The hold is a browser-side wait between commands, like the cure. Armed, the seq.fault event
  // closes it at once; unarmed, the hold's own 500 ms poll of the abort reason does.
  console.log('\nF  a reset or a lost port during a Run Log hold ends the hold and fails the run');
  for (const [tag, armed, act, re] of [
    ["'start', logging on", true, () => rx('start'), /firmware restarted during the run/],
    ['port closed, logging off', false, () => bridge({ _rmr: 'status', serial: 'closed', port: '/dev/rmr-mega' }), /the bridge lost the serial port during the run/],
  ]) {
    await fresh();
    log.setLogging(armed);
    ev('seqRunBlock')('homing');
    await flush();
    log.requestHold('hold', 'test');   // queued while running; applies after the block ('single')
    webOk(); await flush();             // <- G28's own
    webOk(); await flush();             // <- the marker's own; the hold begins
    await flush();
    const hold = log.device.state.hold;
    ok(tag + ': the run sits in the hold with no step waiting for an ok', ev('seqRunning') === true && !!hold && ev('seqWaiter') === null, [ev('seqRunning'), hold, ev('seqWaiter')]);
    act();
    const took = await until(() => !ev('seqRunning'));
    ok(tag + ': the hold ended and the run failed at once', !ev('seqRunning') && log.device.state.hold === null && took < FAST_MS, took);
    const hr = log.device.rows.filter(r => r.kind === 'hold').at(-1);
    ok(tag + ': the hold row was closed by the fault', !!hr && !!hr.to && re.test(hr.endedBy || ''), hr && hr.endedBy);
    ok(tag + ': the status names the cause', re.test(seqStatus()) && /^Error: /.test(seqStatus()), seqStatus());
    ev('okLedgerReset')();
  }
  log.setLogging(true);

  // == G: a step in flight keeps the "ok lost" wording, with the cause first ==
  console.log("\nG  a 'start' with a step in flight names the restart and the lost ok");
  {
    await fresh();
    ev('seqRunBlock')('homing');
    await flush();
    ok('G28 in flight', last() === 'G28' && ev('seqWaiter') !== null, last());
    rx('start');
    await flush();
    ok('the run failed at once with both causes',
      ev('seqRunning') === false && /^Error: firmware restarted during the run: .*; the "ok" of the step in flight is lost$/.test(seqStatus()), seqStatus());
    ev('okLedgerReset')();
  }

  if (ev('autoReportInterval')) clearInterval(ev('autoReportInterval'));
}

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
