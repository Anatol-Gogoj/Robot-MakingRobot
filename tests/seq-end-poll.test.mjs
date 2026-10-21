// Drives the shipped Process Sequencer in both UIs (issue #188). A run pauses the auto-report
// poll and seqEnd() brings it back, but only while the page is connected and nothing else owns a
// poll: after a disconnect fails a run, a restarted poll would log "Not connected" once a second
// until a reconnect. A connect brings the poll back while the Auto box is still ticked, so the
// guard on seqEnd() does not leave the box ticked with no poll behind it.
//
//   node tests/seq-end-poll.test.mjs RMR_Controller.html RMR_Touch.html
import { loadUI } from './harness.mjs';

let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 0));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (cond, limitMs = 1500) => { const t0 = Date.now(); while (!cond() && Date.now() - t0 < limitMs) await sleep(10); return Date.now() - t0; };

for (const FILE of process.argv.slice(2)) {
  const { ev, el } = loadUI(FILE);
  console.log(`\n=== ${FILE.split(/[\\/]/).pop()} ===`);

  // Fake link: a Web Serial writer that appends to the wire.
  const wire = ev('globalThis.__wire = []');   // must live in the sandbox realm
  const rx = line => ev('processLine')(line);
  const webOk = () => rx('ok');
  const last = () => wire.at(-1);
  const writerSrc = 'writer = { write: async b => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); }, releaseLock() {} }';
  if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
  const seqStatus = () => String(el('seqStatus').innerHTML);

  // The poll's timer is replaced by a registry, so a test counts the live polls and fires one
  // second of them by hand. Every other timer the page sets stays real.
  ev(`{ const realSet = setInterval, realClear = clearInterval; let n = 0; globalThis.__polls = new Map();
    globalThis.setInterval = (fn, ms, ...a) => { if (fn !== autoReportTick) return realSet(fn, ms, ...a); const id = 'poll' + (++n); globalThis.__polls.set(id, fn); return id; };
    globalThis.clearInterval = id => { if (!globalThis.__polls.delete(id)) realClear(id); }; }`);
  const polls = ev('globalThis.__polls');
  const tick = () => { for (const f of [...polls.values()]) f(); };

  // Every console error line.
  const errs = ev('globalThis.__errs = []');
  ev('{ const orig = logErr; logErr = m => { globalThis.__errs.push(String(m)); return orig(m); }; }');
  const notConnected = () => errs.filter(e => e === 'Not connected').length;

  // As the operator does it with the Auto box.
  const pollOn  = () => { el('autoReport').checked = true;  ev('toggleAutoReport')(); };
  const pollOff = () => { el('autoReport').checked = false; ev('toggleAutoReport')(); };
  const linkUp = () => { ev(writerSrc); ev('isConnected = true'); };
  const reconnect = () => { ev(writerSrc); ev('setConnected')(true); };   // what both transports call on a connect
  // Each case starts connected, idle, the Auto box ticked and its poll running.
  async function fresh() {
    if (ev('seqRunning')) { ev('seqStop')(); await until(() => !ev('seqRunning')); }
    linkUp(); pollOff();
    polls.clear();   // a poll an unfixed page leaked stays in its own case
    ev('okLedgerReset')(); wire.length = 0; errs.length = 0;
    pollOn();
  }
  // The Homing block parks the run on its G28's own 'ok'.
  async function startHoming() {
    el('homeAll').checked = true; el('homeSpin').checked = false;   // homeSpin: Controller only, no M752 after the home
    ev('seqRunBlock')('homing');
    await flush();
  }
  async function finishHoming() {
    webOk(); await flush();   // <- G28's
    webOk(); await flush();   // <- the M118 marker's
  }
  // A disconnect two ways: the page's own button (it clears the poll itself), and a drop under
  // the page (a lost device, a closed bridge socket), which clears nothing.
  const drops = [
    ['Disconnect button', () => ev('disconnect')()],
    ['link dropped',      () => ev('setConnected')(false)],
  ];

  // == A: a run that ends after a disconnect starts no poll ==
  console.log('\nA  a run that ends after a disconnect starts no poll and logs no "Not connected"');
  for (const [tag, drop] of drops) {
    await fresh();
    ok(tag + ': the poll runs before the run', polls.size === 1, polls.size);
    await startHoming();
    ok(tag + ': G28 in flight, and the run paused the poll', last() === 'G28' && ev('seqRunning') === true && polls.size === 0, [last(), polls.size]);
    await drop();
    await until(() => !ev('seqRunning'));
    await flush();
    ok(tag + ': the disconnect failed the run', ev('seqRunning') === false && /disconnected during the run/.test(seqStatus()), seqStatus());
    ok(tag + ': seqEnd started no poll', polls.size === 0, polls.size);
    const n = wire.length; errs.length = 0;
    tick(); tick(); tick(); await flush();
    ok(tag + ': three seconds later nothing is logged and nothing is sent', notConnected() === 0 && wire.length === n, [notConnected(), wire.slice(n)]);
  }

  // == B: the poll comes back on a reconnect while the box is ticked ==
  console.log('\nB  after the run failed on a disconnect, a reconnect brings the poll back once');
  for (const [tag, drop] of drops) {
    await fresh();
    await startHoming();
    await drop();
    await until(() => !ev('seqRunning'));
    await flush();
    ok(tag + ': no poll while disconnected', polls.size === 0, polls.size);
    reconnect(); await flush();
    ok(tag + ': the poll is back after the reconnect', polls.size === 1, polls.size);
    const n = wire.length;
    tick(); await flush();
    ok(tag + ': and it polls the position', wire.slice(n).join(' | ') === 'M114', wire.slice(n));
    webOk(); await flush();
    reconnect(); reconnect(); await flush();
    ok(tag + ': a further connect stacks no second poll', polls.size === 1, polls.size);
  }
  {
    await fresh();
    await startHoming();
    await ev('disconnect')();
    await until(() => !ev('seqRunning'));
    await flush();
    pollOff();   // the operator unticks the box while disconnected
    reconnect(); await flush();
    ok('box unticked while disconnected: a reconnect starts no poll', polls.size === 0, polls.size);
    pollOn();
    ok('...and ticking it again starts one', polls.size === 1, polls.size);
  }
  {
    // No run at all: a link that drops under an idle page leaves its poll running (nothing clears
    // it), and the reconnect must not stack a second one on it.
    await fresh();
    ev('setConnected')(false);
    ok('idle drop: the poll the page already had is untouched', polls.size === 1, polls.size);
    reconnect(); await flush();
    ok('idle drop: the reconnect stacks no second poll', polls.size === 1, polls.size);
  }

  // == C: a run that ends normally restores the poll ==
  console.log('\nC  a run that ends while connected restores the poll');
  {
    await fresh();
    await startHoming();
    ok('the run paused the poll', polls.size === 0, polls.size);
    await finishHoming();
    ok('the run completed', ev('seqRunning') === false && /complete/.test(seqStatus()), seqStatus());
    ok('the poll is back', polls.size === 1, polls.size);
    const n = wire.length;
    tick(); await flush();
    ok('and it polls the position', wire.slice(n).join(' | ') === 'M114', wire.slice(n));
    webOk(); await flush();
  }
  {
    await fresh();
    await startHoming();
    ev('seqStop')();
    await until(() => !ev('seqRunning'));
    await flush();
    ok('a Stop while connected restores it too', ev('seqRunning') === false && polls.size === 1, [ev('seqRunning'), polls.size]);
  }
  {
    await fresh();
    pollOff();   // the box is unticked before the run: nothing to restore
    await startHoming();
    await finishHoming();
    ok('a run that began with the poll off ends with it off', ev('seqRunning') === false && polls.size === 0, polls.size);
  }

  // == D: no second interval is ever stacked ==
  console.log('\nD  no second interval is stacked');
  {
    await fresh();
    await startHoming();
    pollOff(); pollOn();   // the operator unticks and reticks the box in the middle of the run
    ok('mid-run: the re-tick started the one poll', polls.size === 1, polls.size);
    await finishHoming();
    ok('seqEnd did not stack a second on it', ev('seqRunning') === false && polls.size === 1, polls.size);
  }
  {
    // A connect while a run holds the poll paused (a UV cure waits on the browser, not on an ok)
    // starts none: the run's own end restores it, once.
    await fresh();
    el('uvTime').value = '30'; el('uvSeqPin').value = '4';
    el('uvLid').checked = false; el('uvSpinHome').checked = false; el('uvArgon').checked = false;
    ev('seqSetHomed')(true, 'test');
    ev('seqRunBlock')('uv');
    await flush();
    ok('the UV block lit the lamp', last() === 'M42 P4 S1', last());
    webOk(); await flush();
    ok('the run sits in its cure with the poll paused', ev('seqRunning') === true && ev('seqWaiter') === null && polls.size === 0, [ev('seqRunning'), polls.size]);
    reconnect(); await flush();
    ok('a connect mid-run starts no poll', polls.size === 0, polls.size);
    ev('seqStop')();
    await until(() => !ev('seqRunning'));
    await flush();
    ok('the run ended and restored the one poll', ev('seqRunning') === false && polls.size === 1, [ev('seqRunning'), polls.size]);
  }

  for (const id of [...polls.keys()]) polls.delete(id);
}

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
