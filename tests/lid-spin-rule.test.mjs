// Issue #191: the lid is closed before the spin coater spins above 120 RPM (owner rule, 2026-10-21).
//
// Homing and index searches may run with the lid open, so the operator can check the chuck
// alignment; a spin above SPIN_LID_RPM may not. The Spin Coater block and Start Spin close the lid
// (M400, then M280 P1 S<closed> T800) before such an M750. The block reopens the lid it closed only
// once the firmware has shown the chuck stopped: M750 prints OK: CYCLE_COMPLETE or
// ERR: CYCLE_COMPLETE_NO_HOME only after its ramp-down read |RPM| <= 6 (M750.cpp). Every other
// ending leaves the lid closed. Start Spin never reopens it. The Syringe block's paths that lower B
// refuse, with nothing sent, while the lid was last commanded closed, from any path (this page on
// Web Serial, the bridge's TX echo for every client and button); an unknown lid state does not block.
//
// These checks drive the real blocks through the real ok ledger. A fake Marlin answers every
// written command in order, printing the M750 lines taken verbatim from M750.cpp first.
//
//   node tests/lid-spin-rule.test.mjs RMR_Controller.html RMR_Touch.html
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
const waitFor = async (pred, ms = 3000) => { for (let i = 0; i < ms / 5 && !pred(); i++) await sleep(5); return pred(); };

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
ev('isConnected = true');
// The wire, and one log of both directions in order: 'TX <command>' and 'RX <line>'.
ev('globalThis.__wire = []; globalThis.__log = []');
ev(`writer = { write: async (b) => { const c = new TextDecoder().decode(b).trim(); globalThis.__wire.push(c); globalThis.__log.push('TX ' + c); } }`);
const wire = ev('__wire'), log = ev('__log');
const rx = line => { log.push('RX ' + line); ev('processLine')(line); };
// Console messages, so a lid left closed can be checked for saying why.
ev(`globalThis.__msgs = []; globalThis.__li = logInfo; globalThis.__le = logErr;
    logInfo = m => { globalThis.__msgs.push(String(m)); return globalThis.__li(m); };
    logErr  = m => { globalThis.__msgs.push(String(m)); return globalThis.__le(m); }`);
const msgs = ev('__msgs');
// A short ok timeout for the M750 step on request, so a timeout can be tested.
ev(`globalThis.__m750Timeout = 0; globalThis.__awaitOrig = seqAwaitOk;
    seqAwaitOk = (ms, label) => globalThis.__awaitOrig(globalThis.__m750Timeout && /^M750/.test(label) ? globalThis.__m750Timeout : ms, label)`);
const status = () => String(el('seqStatus').innerHTML);
const lidState = () => ev('lidState')();

const CLOSE = 'M280 P1 S115 T800', OPEN = 'M280 P1 S30 T800';
const isM750 = c => /^M750\b/.test(c);
const isLower = c => /^G1 B(?!0 )/.test(c);   // a B move to the dispense height, not the raise to B0

// M750 lines, verbatim from M750.cpp (and spincoater.cpp for the index search inside H1).
const HEAD = ['echo:SPIN OK: Cycle — RPM=5000 DUR=30s RISE=5.00s SINK=1.00s HOME=ON', 'echo:SPIN DATA: accel=16.67 decel=83.33 rev/s2',
              'echo:SPIN STATE:CONNECTING', 'echo:SPIN STATE:ODRIVE_FOUND', 'echo:SPIN DATA: Vbus=24.07V',
              'echo:SPIN STATE:CALIBRATING', 'echo:SPIN STATE:CLOSED_LOOP', 'echo:SPIN STATE:RAMP_UP',
              'echo:SPIN TELEM: RPM=4991.20 POS=210.10 DEG=36.00'];
const MEASURED = ['echo:SPIN STATE:MEASURING', 'echo:SPIN DATA: Samples=300', 'echo:SPIN DATA: MeanRPM=5009.88', 'echo:SPIN DATA: StdDevRPM=1.20',
                  'echo:SPIN DATA: MinRPM=5006.00', 'echo:SPIN DATA: MaxRPM=5013.00', 'echo:SPIN DATA: Range=7.00'];
const STOPPED = ['echo:SPIN STATE:RAMP_DOWN', 'echo:SPIN TELEM: RPM=3.10 POS=830.20 DEG=72.00', 'echo:SPIN STATE:SETTLING', 'echo:SPIN STATE:STOPPED'];
const INDEX_OK = ['echo:SPIN STATE:HOMING', 'echo:SPIN STATE:INDEX_SEARCH_ACTIVE', 'echo:SPIN STATE:HOME_SETTLE',
                  'echo:SPIN DATA: HomeSettleErr=0.22 deg', 'echo:SPIN OK: INDEX_COMPLETE'];
const M750_OK = [...HEAD, ...MEASURED, ...STOPPED, ...INDEX_OK, 'echo:SPIN OK: CYCLE_COMPLETE'];
const M750_NO_HOME = [...HEAD, ...MEASURED, ...STOPPED, 'echo:SPIN STATE:HOMING', 'echo:SPIN STATE:INDEX_SEARCH_ACTIVE',
  'echo:SPIN ERR: Index search failed, procedure_result=1',
  'echo:SPIN WARN: Index homing failed — datum PRESERVED at 830.38 turns (not re-datuming)',
  'echo:SPIN ERR: CYCLE_COMPLETE_NO_HOME — rotor parked off datum, angular registration unverified'];
// Every other way an M750 ends.
const ABNORMAL = [
  ['the M410 abort (OK: ABORTED, STATE:STOPPED before the rotor stops)', [...HEAD, 'echo:SPIN STATE:MEASURING', 'echo:SPIN STATE:STOPPED', 'echo:SPIN OK: ABORTED']],
  ['RAMP_TIMEOUT', [...HEAD, 'echo:SPIN ERR: Ramp-up timeout — reached 3000.00 of 4900.00 RPM', 'echo:SPIN STATE:RAMP_TIMEOUT']],
  ['RAMP_STALL', [...HEAD, 'echo:SPIN ERR: RPM stalled at 3000.00 — target 4900.00 unreachable', 'echo:SPIN STATE:RAMP_STALL']],
  ['MEASURE_LINK_LOST', [...HEAD, 'echo:SPIN STATE:MEASURING', 'echo:SPIN ERR: No ODrive telemetry for 3s during measure -- link lost',
                         'echo:SPIN STATE:MEASURE_LINK_LOST', 'echo:SPIN ERR: Measure phase aborted -- stopping spin']],
  ['Samples=0', [...HEAD, 'echo:SPIN STATE:MEASURING', 'echo:SPIN ERR: No telemetry samples during measure -- statistics unavailable',
                 'echo:SPIN DATA: Samples=0', 'echo:SPIN ERR: Measure phase aborted -- stopping spin']],
  ['DECEL_LINK_LOST', [...HEAD, ...MEASURED, 'echo:SPIN STATE:RAMP_DOWN',
                       'echo:SPIN ERR: Ramp-down aborted, no ODrive telemetry for 3s -- last seen 2500.00 RPM; rotor may still be spinning', 'echo:SPIN STATE:DECEL_LINK_LOST']],
  ['DECEL_STALL (the drive is disarmed and the chuck freewheels)', [...HEAD, ...MEASURED, 'echo:SPIN STATE:RAMP_DOWN',
                       'echo:SPIN ERR: Ramp-down stalled at 2500.00 RPM -- not decelerating', 'echo:SPIN STATE:DECEL_STALL']],
  ['ODrive boot failed', ['echo:SPIN STATE:BOOTING', 'echo:SPIN STATE:WAITING_ODRIVE', 'echo:SPIN ERR: ODrive not detected (15s timeout)',
                          'echo:SPIN ERR: ODrive boot failed — check wiring and power']],
  ['ODrive not responding', [HEAD[0], HEAD[1], 'echo:SPIN STATE:CONNECTING', 'echo:SPIN ERR: ODrive not responding (5s)']],
  ['closed loop refused', [...HEAD.slice(0, 6), 'echo:SPIN ERR: Failed to enter closed-loop']],
  ['bad parameters', ['echo:SPIN ERR: All values must be > 0']],
  ['no marker at all (a bare ok)', []],
  ["only an earlier command's OK: CYCLE_COMPLETE, then this M750's RAMP_TIMEOUT",
   ['echo:SPIN OK: CYCLE_COMPLETE', ...HEAD, 'echo:SPIN ERR: Ramp-up timeout — reached 3000.00 of 4900.00 RPM', 'echo:SPIN STATE:RAMP_TIMEOUT']],
];

// Fake Marlin: answers each written command in order with 'ok', after the lines it prints for it.
// `hold[prefix]` ms delays the answer of a command starting with prefix, and everything behind it.
function marlin({ m750 = M750_OK, hold = {}, posC = 10 } = {}) {
  let answered = 0, stop = false;
  (async () => {
    while (!stop) {
      if (answered < wire.length) {
        const cmd = wire[answered];
        const h = Object.keys(hold).find(k => cmd.startsWith(k));
        if (h) await sleep(hold[h]);
        if (stop) break;
        if (isM750(cmd)) m750.forEach(rx);
        if (cmd === 'M752') INDEX_OK.forEach(rx);
        if (cmd === 'M114') rx('X:385.00 Y:0.00 Z:0.00 A:0.00 B:0.00 C:' + posC.toFixed(2) + ' Count X:0 Y:0 Z:0 A:0 B:0 C:0');
        rx('ok');
        answered++;
      } else await sleep(2);
    }
  })();
  return () => { stop = true; };
}

function reset() {
  wire.length = 0; log.length = 0; msgs.length = 0;
  ev('okLedgerReset')(); ev('wsOwnPending = []');
  ev('seqSetHomed')(true, 'test');
}
// Run one sequencer block from its Run button and wait for the sequencer to finish, then `after`
// ms more, so a held answer that comes after a Stop or a timeout is delivered before the checks.
async function runBlock(id, opts, during, after = 20) {
  reset();
  const stopMarlin = marlin(opts);
  ev('seqRunBlock')(id);
  if (during) await during();
  await waitFor(() => !ev('seqRunning'), 10000);
  await sleep(after);                    // let the fake answer what is still owed
  stopMarlin();
  return [...wire];
}
// Run a manual function (Start Spin) against the fake Marlin until the wire is quiet.
async function runManual(fn, opts) {
  reset();
  const stopMarlin = marlin(opts);
  ev(fn)();
  let n = -1;
  for (let i = 0; i < 200 && n !== wire.length; i++) { n = wire.length; await sleep(30); }
  stopMarlin();
  return [...wire];
}
// Put the lid in a known commanded state the way the operator would: a manual lid command.
async function commandLid(cmd) { await ev('sendCmd')(cmd); ev('okLedgerReset')(); }

// Short browser-side waits, so the Run All checks run in seconds; every other field keeps its default.
el('syrDwell').value = '0.02'; el('uvTime').value = '0.1';
el('stampGrabDelay').value = '0'; el('stampHold').value = '0';
el('uvLidClose').value = '115'; el('uvLidOpen').value = '30';

// == 1: the threshold ==
console.log('\n1  the threshold: above 120 RPM the lid closes first, at or below it nothing changes');
ok('the threshold is a named 120 RPM, and a missing S means the firmware default, 5000 RPM',
   ev('SPIN_LID_RPM') === 120 && ev('SPIN_DEFAULT_RPM') === 5000, [ev('SPIN_LID_RPM'), ev('SPIN_DEFAULT_RPM')]);
{
  const r = ev('spinCmdRpm');
  const cases = [['M750', 5000], ['M750 D30 A5 C1 H1', 5000], ['M750 S D30', 5000], ['M750 S121 D30', 121], ['M750 S120', 120], ['M750 S1000.7', 1000]];
  ok('spinCmdRpm reads S as Marlin does (intval), and S missing or empty as 5000', cases.every(([c, w]) => r(c) === w), cases.map(([c]) => r(c)));
}
await commandLid(OPEN);
el('seqSpinRPM').value = '5000';
{
  const cmds = await runBlock('spin');
  ok('Spin Coater block at 5000 RPM: M400, close the lid (T ramp), M750, then reopen',
     cmds.length === 4 && cmds[0] === 'M400' && cmds[1] === CLOSE && /^M750 S5000\b/.test(cmds[2]) && cmds[3] === OPEN, cmds);
  ok('the block completed', /complete/.test(status()), status());
}
for (const [rpm, closes] of [[121, true], [120, false], [100, false]]) {
  el('seqSpinRPM').value = String(rpm);
  const cmds = await runBlock('spin');
  ok(`Spin Coater block at ${rpm} RPM ${closes ? 'closes and reopens the lid' : 'sends the M750 alone, as before'}`,
     closes ? (cmds[1] === CLOSE && isM750(cmds[2]) && cmds[3] === OPEN) : (cmds.length === 1 && cmds[0].startsWith('M750 S' + rpm + ' ')), cmds);
}
el('seqSpinRPM').value = '5000';

// == 2: Start Spin ==
console.log('\n2  Start Spin closes the lid above 120 RPM, sends the M750 only on the lid move\'s own ok, and never reopens');
{
  el('spinRPM').value = '5000';
  reset();
  ev('spinStart')();
  await waitFor(() => wire.length >= 2);
  await sleep(30);
  ok('Start Spin: M400 and the lid close go out, and no M750 before the close is answered',
     wire.length === 2 && wire[0] === 'M400' && wire[1] === CLOSE, [...wire]);
  rx('ok');                              // M400's
  await sleep(10);
  ok('still no M750 on the M400\'s ok', wire.length === 2, [...wire]);
  rx('ok');                              // the lid close's
  await waitFor(() => wire.length >= 3);
  ok('the M750 follows the lid close\'s own ok', wire.length === 3 && /^M750 S5000\b/.test(wire[2]), [...wire]);
  M750_OK.forEach(rx); rx('ok');
  await sleep(30);
  ok('no reopen after OK: CYCLE_COMPLETE: Start Spin leaves the lid to the operator', wire.length === 3 && lidState() === 'closed', [[...wire], lidState()]);
}
{
  el('spinRPM').value = '120';
  const cmds = await runManual('spinStart');
  ok('Start Spin at 120 RPM sends the M750 alone', cmds.length === 1 && cmds[0].startsWith('M750 S120 '), cmds);
  el('spinRPM').value = '';
  const cmds2 = await runManual('spinStart');
  ok('Start Spin with an empty RPM field (M750 S with no number: the 5000 RPM default) closes the lid first',
     cmds2.length === 3 && cmds2[0] === 'M400' && cmds2[1] === CLOSE && /^M750 S D/.test(cmds2[2]), cmds2);
  el('spinRPM').value = '5000';
}

// == 3: the reopen ==
console.log('\n3  the block reopens the lid only after OK: CYCLE_COMPLETE or ERR: CYCLE_COMPLETE_NO_HOME');
await commandLid(OPEN);
{
  await runBlock('spin');
  const mark = log.indexOf('RX echo:SPIN OK: CYCLE_COMPLETE'), reopen = log.indexOf('TX ' + OPEN);
  ok('the reopen goes out after the M750 printed OK: CYCLE_COMPLETE', mark > 0 && reopen > mark, [mark, reopen]);
  ok('the lid ends commanded open', lidState() === 'open', lidState());
}
{
  const cmds = await runBlock('spin', { m750: M750_NO_HOME });
  ok('ERR: CYCLE_COMPLETE_NO_HOME (the ramp-down stopped the chuck, the index home failed after it) also reopens',
     cmds.at(-1) === OPEN && lidState() === 'open', cmds);
  ok('and says the chuck is not at its datum', msgs.some(m => /CYCLE_COMPLETE_NO_HOME/.test(m) && /not at its datum/.test(m)), msgs);
}

// == 4: every abnormal ending leaves the lid closed ==
console.log('\n4  every other ending leaves the lid closed and says why');
for (const [name, lines] of ABNORMAL) {
  await commandLid(OPEN);
  const cmds = await runBlock('spin', { m750: lines });
  ok(`${name}: the block fails, the lid stays closed, no reopen`,
     /Error:/.test(status()) && /lid stays closed/.test(status()) && cmds.at(-1).startsWith('M750') && !cmds.includes(OPEN) && lidState() === 'closed',
     [status(), cmds, lidState()]);
}
{
  await commandLid(OPEN);
  const cmds = await runBlock('spin', { m750: ABNORMAL[0][1], hold: { M750: 200 } }, async () => {
    await waitFor(() => wire.some(isM750)); await sleep(50);
    ev('seqStop')();
  }, 300);
  ok('Stop during the M750: M410 goes out, the run stops, no reopen (also after STATE:STOPPED and OK: ABORTED came), the lid stays closed',
     cmds.includes('M410') && log.includes('RX echo:SPIN OK: ABORTED') && !cmds.includes(OPEN) && lidState() === 'closed' && /Stopped/.test(status()), [cmds, status()]);
  ok('Stop: the console says the lid stays closed and why', msgs.some(m => /lid stays closed/.test(m) && /Stop/.test(m)), msgs);
}
{
  await commandLid(OPEN);
  const cmds = await runBlock('spin', { hold: { M750: 200 } }, async () => {
    await waitFor(() => wire.some(isM750)); await sleep(50);
    rx('echo:MOTOR POWER LOST');
  }, 300);
  ok('a fault during the M750 (MOTOR POWER LOST): the run fails, no reopen, the lid stays closed',
     /Error:/.test(status()) && !cmds.includes(OPEN) && lidState() === 'closed', [status(), cmds]);
  ok('fault: the console says the lid stays closed', msgs.some(m => /lid stays closed/.test(m)), msgs);
}
{
  await commandLid(OPEN);
  ev('__m750Timeout = 100');
  const cmds = await runBlock('spin', { hold: { M750: 400 } }, null, 500);
  ev('__m750Timeout = 0');
  ok('the M750 step times out: the run fails, no reopen even when the late OK: CYCLE_COMPLETE and ok come, the lid stays closed',
     /Error:.*no "ok"/.test(status()) && log.includes('RX echo:SPIN OK: CYCLE_COMPLETE') && !cmds.includes(OPEN) && lidState() === 'closed', [status(), cmds]);
}
{
  await commandLid(OPEN);
  el('seqSpinRPM').value = '100';
  const cmds = await runBlock('spin', { m750: ABNORMAL[1][1] });
  ok('at or below 120 RPM an abnormal ending is unchanged: no lid move, the block passes on the ok (gotcha 25)',
     cmds.length === 1 && /complete/.test(status()) && lidState() === 'open', [cmds, status()]);
  el('seqSpinRPM').value = '5000';
}

// == 5: the syringe guard ==
console.log('\n5  the Syringe block refuses to lower B into a lid last commanded closed');
await commandLid(CLOSE);
{
  const cmds = await runBlock('syringe');
  ok('dispense refused with nothing sent (not even the stroke guard\'s M114)', cmds.length === 0 && /Error:/.test(status()), [cmds, status()]);
  ok('the refusal says the lid is closed and to open it with the Lid button once the chuck has stopped',
     /lid was last commanded closed \(115 deg; open is 30 deg or less\)/.test(status()) && /Open it with the Lid button once the chuck has stopped/.test(status()), status());
}
{
  el('syrPurgeVol').value = '2';
  reset(); let err = null;
  await ev('runSyringePurge')(false).catch(e => { err = e; });
  ok('purge refused with nothing sent', err && /Purge refused/.test(err.message) && wire.length === 0, [err && err.message, [...wire]]);
  reset(); ev('syrPurgeNow')();
  await sleep(20);
  ok('the Purge button refuses before its confirm, nothing sent', wire.length === 0 && !ev('seqRunning') && msgs.some(m => /Purge refused/.test(m)), [[...wire], msgs]);
  reset(); ev('syrLower')();
  await sleep(20);
  ok('the Lower helper refuses, nothing sent', wire.length === 0 && msgs.some(m => /Lower refused/.test(m)), [[...wire], msgs]);
}
{
  el('syrPrimeVol').value = '0.5';
  reset(); const stopMarlin = marlin(); let err = null;
  await ev('runSyringePrime')().catch(e => { err = e; });
  stopMarlin();
  ok('prime is not refused: it pushes the plunger with the tip where it is and never moves B',
     !err && wire.includes('M114') && !wire.some(c => /^G1 B/.test(c)), [err && err.message, [...wire]]);
}
await commandLid('M280 P1 S80 T800');
ok('a lid parked part-way (80 deg) counts as closed', lidState() === 'closed', lidState());
await commandLid('M280 P0 S170');
ok('a gripper command (P0) leaves the lid state alone', lidState() === 'closed' && ev('lidLastDeg') === 80, ev('lidLastDeg'));
await commandLid('M280 P1');
await commandLid('M280 P1 S-1');
ok('M280 P1 with no S (a report) or a negative S (detach) moves nothing and changes nothing', ev('lidLastDeg') === 80, ev('lidLastDeg'));
await commandLid('G28 O');
ok('G28 O (homes only if needed, so it may not touch the lid) changes nothing', lidState() === 'closed', lidState());
await commandLid('G28 X Y');
ok('a partial G28 opens the lid to 30 deg first (G28.cpp), so the lid counts as open', ev('lidLastDeg') === 30 && lidState() === 'open', ev('lidLastDeg'));
await commandLid('M280P1S115');
ok('a close written without spaces still counts', lidState() === 'closed', lidState());
el('uvLidOpen').value = '45';
await commandLid('M280 P1 S45 T800');
ok('the sequencer\'s own open angle (uvLidOpen 45) counts as open', lidState() === 'open', lidState());
el('uvLidOpen').value = '120';
await commandLid(CLOSE);
ok('the closed angle counts as closed even with the open field mistyped past it (uvLidOpen 120)', lidState() === 'closed', lidState());
el('uvLidOpen').value = '30';
await commandLid('G28');
ok('a bare G28 opens the lid', lidState() === 'open', lidState());

// == 6: the bridge echo ==
console.log('\n6  on the Pi bridge the lid is tracked from the TX echo, whoever sent the command');
{
  ev('globalThis.WebSocket = { OPEN: 1 }');
  ev('useWS = true');
  ev('globalThis.__ws = []');
  ev(`ws = { readyState: 1, send: c => { globalThis.__ws.push(String(c)); } }`);
  const bridge = m => ev('handleWSMessage')(JSON.stringify(m));
  bridge({ _rmr: 'tx', cmd: 'G28\nM118 RMR:HOMED_ALL', source: 'button:home_all' });
  ok('a two-line button echo with a G28 opens the lid', lidState() === 'open', lidState());
  await ev('sendCmd')(CLOSE);
  ok('this page\'s own close sent to the bridge does not count before its echo', lidState() === 'open' && ev('__ws').at(-1) === CLOSE, lidState());
  bridge({ _rmr: 'tx', cmd: CLOSE, source: 'ws' });
  ok('its echo does', lidState() === 'closed', lidState());
  bridge({ _rmr: 'tx', cmd: OPEN, source: 'ws' });
  ok('another client\'s open, echoed', lidState() === 'open', lidState());
  bridge({ _rmr: 'tx', cmd: CLOSE, source: 'button:lid' });
  ok('a physical button\'s close, echoed', lidState() === 'closed', lidState());
  ev('useWS = false');
  const cmds = await runBlock('syringe');
  ok('a dispense is refused after a close that came through the bridge echo', cmds.length === 0 && /lid was last commanded closed/.test(status()), [cmds, status()]);
}

// == 7: an unknown lid state does not block ==
console.log('\n7  an unknown lid state (after a connect or a firmware restart) does not block');
{
  await commandLid(CLOSE);
  ev('setConnected')(true);
  ok('a new connection makes the lid state unknown', lidState() === 'unknown' && ev('lidLastDeg') === null, ev('lidLastDeg'));
  const cmds = await runBlock('syringe');
  ok('unknown: the dispense runs (M114, lower, dose, raise)', cmds[0] === 'M114' && cmds.some(isLower) && /complete/.test(status()), [cmds, status()]);
  await commandLid(CLOSE);
  rx('start');
  ok('a firmware restart (start) makes it unknown too', lidState() === 'unknown', lidState());
  const cmds2 = await runBlock('syringe');
  ok('and the dispense runs', cmds2.some(isLower) && /complete/.test(status()), [cmds2, status()]);
}

// == 8: Run All on a healthy machine ==
console.log('\n8  Run All (Syringe, Spin, UV, Stamp) still completes on a healthy machine, two cycles');
ev('globalThis.__enabled = []');
ev('seqIsEnabled = id => globalThis.__enabled.includes(id)');
el('seqRepeat').checked = true; el('seqCycles').value = '2';
el('uvLid').checked = true; el('uvSpinHome').checked = false; el('uvArgon').checked = false;
async function runAll(blocks, opts, lidBefore) {
  ev('globalThis.__enabled = ' + JSON.stringify(blocks));
  reset();
  if (lidBefore) { await commandLid(lidBefore); wire.length = 0; log.length = 0; }
  const stopMarlin = marlin(opts);
  ev('seqRunAll')();
  await waitFor(() => !ev('seqRunning'), 20000);
  await sleep(20);
  stopMarlin();
  return [...wire];
}
for (const [blocks, lidBefore] of [[['syringe', 'spin', 'uv', 'stamp'], OPEN], [['syringe', 'spin', 'uv', 'stamp'], null],
                                   [['homing', 'syringe', 'spin', 'uv', 'stamp'], CLOSE], [['syringe', 'spin', 'stamp'], OPEN]]) {
  if (!lidBefore) { ev('lidLastDeg = null'); }
  const cmds = await runAll(blocks, {}, lidBefore);
  const lowers = cmds.map((c, i) => (isLower(c) ? i : -1)).filter(i => i >= 0);
  const spins = cmds.map((c, i) => (isM750(c) ? i : -1)).filter(i => i >= 0);
  const label = blocks.join(' > ') + (lidBefore ? ' (lid last ' + (lidBefore === OPEN ? 'open' : 'closed') + ')' : ' (lid unknown)');
  ok(label + ': Run All complete, two dispenses and two spins', /Run All complete/.test(status()) && lowers.length === 2 && spins.length === 2, [status(), lowers, spins]);
  ok(label + ': each spin follows a lid close, and the second dispense follows a reopen',
     spins.every(i => cmds[i - 1] === CLOSE) && cmds.slice(spins[0], lowers[1]).includes(OPEN), cmds);
}
{
  const cmds = await runAll(['syringe', 'spin', 'uv', 'stamp'], { m750: ABNORMAL[1][1] }, OPEN);
  ok('a RAMP_TIMEOUT in cycle 1 fails the Run All at the Spin Coater block: no UV, no Stamp, no reopen',
     /Error:.*lid stays closed/.test(status()) && !cmds.includes('M42 P4 S1') && !cmds.includes(OPEN) && cmds.filter(isM750).length === 1 && lidState() === 'closed',
     [status(), cmds]);
}

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
