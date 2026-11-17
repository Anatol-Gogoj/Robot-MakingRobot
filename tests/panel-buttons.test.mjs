// Operator panel Start / Stop buttons (issue #218), in both UIs. The Pi bridge forwards a press as
// {_rmr:'button', name, cmd, action}. Stop: the bridge has written M410 itself, so the page stops
// its sequencer run (the UV block's finally still turns the lamp off) and its Program Runner
// without sending a second M410. Start: resumes an open Run Log hold or break, else starts Run All
// when nothing runs, else does nothing. The bridge decides which page gets which action
// (pi-panel/test_rmr_bridge.py); this test covers what a page does with it.
//
//   node tests/panel-buttons.test.mjs RMR_Controller.html RMR_Touch.html
import { loadUI } from './harness.mjs';

let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 0));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (cond, limitMs = 1500) => { const t0 = Date.now(); while (!cond() && Date.now() - t0 < limitMs) await sleep(10); return Date.now() - t0; };

for (const FILE of process.argv.slice(2)) {
  const { ev, el } = loadUI(FILE);
  console.log(`\n=== ${FILE.split(/[\\/]/).pop()} ===`);

  // Web Serial link: every write lands on the wire, and rx('ok') answers the oldest command.
  const wire = ev('globalThis.__wire = []');
  ev('isConnected = true');
  ev(`writer = { write: async b => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); } }`);
  const rx = line => ev('processLine')(line);
  const bridge = m => ev('handleWSMessage')(JSON.stringify(m));
  // keepGap: leave the page's one-press-one-action guard armed (only the guard's own case does)
  const press = (name, action, cmd, keepGap) => {
    if (action === 'start' && !keepGap) ev('panelLastStartAt = 0');
    bridge(cmd ? { _rmr: 'button', name, cmd, action } : { _rmr: 'button', name, cmd: null, action });
  };
  const toasts = ev('globalThis.__toasts = []');
  ev('showToast = (m, t) => { globalThis.__toasts.push(String(m)); }');
  const sentSince = n => wire.slice(n);

  // Run Log with an open device, and every event the page hands it.
  const log = ev('rmrLog');
  log.createDevice({ id: 'P-218', material: 'test', thicknessUm: 70, targetLayers: 3, rpm: 1000, holdS: 50, cureS: 30, dispenseMl: 0.05, firstElectrode: 'P' });
  log.setLogging(true);
  const events = ev('globalThis.__rl = []');
  ev('{ const orig = rmrLog.event; rmrLog.event = (k, d) => { globalThis.__rl.push({ k, d: d || {} }); return orig(k, d); }; }');

  // Run All is counted, not run: what it does is covered elsewhere; here only whether Start calls it.
  ev('globalThis.__runAll = 0');
  ev('seqRunAll = () => { globalThis.__runAll++; }');
  const runAlls = () => ev('globalThis.__runAll');

  async function fresh() {
    if (ev('seqRunning')) { ev('seqStop')(); await until(() => !ev('seqRunning')); }
    if (ev('progRunning')) ev('progStop')();
    if (log.device.state.hold || log.device.state.holdReq) log.resume();
    ev('okLedgerReset')();
    events.length = 0;
  }

  // The UV block alone: lamp on, a browser-timed cure, lamp off. No lid, argon or index.
  el('uvSeqPin').value = '4';
  el('uvLid').checked = false; el('uvArgon').checked = false;
  if (ev("!!document.getElementById('uvSpinHome')")) el('uvSpinHome').checked = false;   // the Controller only
  async function startCure(cureS) {
    await fresh();
    el('uvTime').value = String(cureS);
    ev('seqSetHomed')(true, 'test');
    ev('seqRunBlock')('uv');
    await flush();
    const n = wire.length;
    ok('setup: lamp on sent', wire.at(-1) === 'M42 P4 S1', wire.at(-1));
    rx('ok'); await flush();
    return n;
  }

  // --- Stop during a cure: the run ends, the lamp goes off, the page sends no M410 of its own.
  {
    const n = await startCure(30);
    ok('stop: the run is in its cure', ev('seqRunning') === true, ev('seqRunning'));
    bridge({ _rmr: 'tx', cmd: 'M410', source: 'button:stop' });   // the bridge's write, echoed
    press('stop', 'stop', 'M410');
    const took = await until(() => !ev('seqRunning'));
    ok('stop: the run ended at once', !ev('seqRunning') && took < 1000, took);
    ok('stop: the lamp-off went out', sentSince(n).includes('M42 P4 S0'), sentSince(n));
    ok('stop: the page sent no second M410', !sentSince(n).includes('M410'), sentSince(n));
    ok('stop: the Run Log has the stop and the cut cure',
      events.some(e => e.k === 'seq.stop') && events.some(e => e.k === 'uv.off' && e.d.aborted), events.map(e => e.k));
  }

  // --- Stop from a button with no M410 of its own: the page sends it.
  {
    const n = await startCure(30);
    press('stop', 'stop', null);
    await until(() => !ev('seqRunning'));
    ok('stop without cmd: the page sent M410', sentSince(n).includes('M410'), sentSince(n));
  }

  // --- Stop with nothing running sends nothing.
  {
    await fresh();
    const n = wire.length;
    press('stop', 'stop', 'M410');
    await flush();
    ok('stop idle: nothing sent', sentSince(n).length === 0, sentSince(n));
  }

  // --- Stop ends a running program.
  {
    await fresh();
    el('progTextarea').value = 'G4 S1\nG4 S1';
    ev('progRun')();
    await flush();
    ok('stop program: the program runs', ev('progRunning') === true, ev('progRunning'));
    press('stop', 'stop', 'M410');
    ok('stop program: the program stopped', ev('progRunning') === false, ev('progRunning'));
  }

  // --- Start, idle with no hold: Run All.
  {
    await fresh();
    const before = runAlls();
    press('start', 'start');
    ok('start idle: Run All called once', runAlls() === before + 1, runAlls() - before);
  }

  // --- Start while the sequencer runs: nothing.
  {
    await startCure(30);
    const before = runAlls(), n = wire.length;
    press('start', 'start');
    await flush();
    ok('start running: no Run All', runAlls() === before, runAlls() - before);
    ok('start running: nothing sent', sentSince(n).length === 0, sentSince(n));
    ok('start running: the run carries on', ev('seqRunning') === true, ev('seqRunning'));
  }

  // --- Start while a hold is only requested: the request stands.
  {
    await startCure(30);
    log.requestHold('hold', '');
    press('start', 'start');
    ok('start with a hold requested: the request stands', !!log.device.state.holdReq, log.device.state.holdReq);
  }

  // --- Start while a program runs: no Run All.
  {
    await fresh();
    el('progTextarea').value = 'G4 S1';
    ev('progRun')();
    const before = runAlls();
    press('start', 'start');
    ok('start with a program: no Run All', runAlls() === before, runAlls() - before);
  }

  // --- Start during an idle break: the break ends, nothing starts.
  {
    await fresh();
    log.requestHold('break', 'lunch');
    ok('break: open', !!log.device.state.hold, log.device.state.hold);
    const before = runAlls();
    press('start', 'start');
    ok('break: Start ended it', !log.device.state.hold, log.device.state.hold);
    ok('break: no Run All', runAlls() === before, runAlls() - before);
  }

  // --- Start during a hold the run is paused at: the run continues and finishes.
  {
    await startCure(0.2);
    log.requestHold('hold', '');
    await until(() => wire.at(-1) === 'M42 P4 S0', 2000);
    ok('hold: lamp off sent after the short cure', wire.at(-1) === 'M42 P4 S0', wire.at(-1));
    rx('ok');
    await until(() => !!log.device.state.hold);
    ok('hold: the run is paused at its hold point', ev('seqRunning') === true && !!log.device.state.hold, [ev('seqRunning'), log.device.state.hold]);
    const before = runAlls();
    press('start', 'start');
    await until(() => !ev('seqRunning'));
    ok('hold: Start resumed and the run finished', !ev('seqRunning') && !log.device.state.hold, [ev('seqRunning'), log.device.state.hold]);
    ok('hold: no Run All', runAlls() === before, runAlls() - before);
  }

  // --- One press, one action: a second Start within the guard does nothing.
  {
    await fresh();
    log.requestHold('break', 'lunch');
    const before = runAlls();
    press('start', 'start');
    press('start', 'start', null, true);   // a double tap or a long bounce
    ok('guard: the first press ended the break', !log.device.state.hold, log.device.state.hold);
    ok('guard: the second press started nothing', runAlls() === before, runAlls() - before);
  }

  // --- A refused Start is visible on the screen: Run All's own refusal, and the bridge's.
  {
    await fresh();
    toasts.length = 0;
    press('start', 'start');   // the counting stub never begins a run, as a refusing seqRunAll would not
    ok('refused: a toast says so', toasts.some(t => /Start refused/.test(t)), toasts);
    toasts.length = 0;
    bridge({ _rmr: 'error', msg: 'start button ignored: no panel page is open on the Pi (http://localhost)' });
    ok('bridge refusal: a toast says so', toasts.some(t => /^Start refused: no panel page/.test(t)), toasts);
    toasts.length = 0;
    bridge({ _rmr: 'error', msg: 'some other bridge error' });
    ok('other bridge errors: no Start toast', !toasts.some(t => /Start refused/.test(t)), toasts);
  }

  // --- The page tells a bridge that reads it whether a run, program or hold is open.
  {
    await fresh();
    const sent = ev('globalThis.__ws = []');
    ev('globalThis.WebSocket = { OPEN: 1 }');
    ev('useWS = true');
    ev(`ws = { readyState: 1, send: c => { globalThis.__ws.push(String(c)); } }`);
    ev('wsOwnPending = []'); ev('okLedgerReset')();
    const states = () => sent.filter(c => c.startsWith('{')).map(c => JSON.parse(c));
    bridge({ _rmr: 'status', serial: 'open', port: '/dev/rmr-mega' });   // an older bridge: no caps
    ev('progRunning = true'); ev('panelStateSync')(false);
    ok('state: nothing sent to a bridge without the capability', states().length === 0, sent);
    ev('progRunning = false');
    bridge({ _rmr: 'status', serial: 'open', port: '/dev/rmr-mega', caps: ['state'] });
    ok('state: the greeting gets the current state', JSON.stringify(states().at(-1)) === '{"_rmr":"state","busy":false}', states());
    ev('progRunning = true'); ev('panelStateSync')(false);
    ok('state: busy once a program runs', states().at(-1).busy === true, states());
    const n = states().length;
    ev('panelStateSync')(false);
    ok('state: no repeat while nothing changes', states().length === n, states().length - n);
    ev('progRunning = false');
    log.requestHold('break', 'lunch'); ev('panelStateSync')(false);
    ok('state: busy while a Run Log hold is open', states().at(-1).busy === true, states());
    log.resume(); ev('panelStateSync')(false);
    ok('state: idle again', states().at(-1).busy === false, states());
    ok('state: never sent as G-code', !wire.some(c => c.startsWith('{')), wire.filter(c => c.startsWith('{')));
    ev('useWS = false'); ev('ws = null'); ev('wsOwnPending = []'); ev('okLedgerReset')();
  }

  // --- A plain button, and a page that is not asked to act, change nothing.
  {
    await startCure(30);
    const n = wire.length, before = runAlls();
    bridge({ _rmr: 'button', name: 'home_all', cmd: 'G28' });
    bridge({ _rmr: 'button', name: 'stop', cmd: 'M410' });   // another page's Stop info, no action
    bridge({ _rmr: 'button', name: 'start', cmd: null });     // another page's Start info, no action
    await flush();
    ok('no action: the run carries on', ev('seqRunning') === true, ev('seqRunning'));
    ok('no action: nothing sent, no Run All', sentSince(n).length === 0 && runAlls() === before, [sentSince(n), runAlls() - before]);
    await fresh();
  }

}

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
