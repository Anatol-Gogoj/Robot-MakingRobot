// Issue #187: the Homing block's optional spincoater index search (M752).
//
// Only RMR_Controller.html's Homing block has the "Spincoater index" option (homeSpin);
// RMR_Touch.html's has none, so this check runs on the Controller alone.
//
// Until #187 the block sent M752 with a 40 s ok-timeout and accepted any 'ok'. M752's worst case
// is about 130 s (a first-use boot() after a reset, then doIndexHome(); the sum is in the comment
// above SPIN_INDEX_TIMEOUT_MS), so the first M752 after a reset, which includes every Web Serial
// connect, could time out on a healthy machine and fail the run. And M752 answers 'ok' on
// failure too (gotcha 25). The block now runs the M752 through the same step as the UV block
// (#183): the 150 s bound, and a pass only on OK: INDEX_COMPLETE.
//
// These checks drive the real runHomingBlock() through the real ok ledger and the real
// seqAwaitOk() timer. A fake Marlin answers every written command in order. Time is compressed
// by SCALE: each step's ok-timeout is armed SCALE times shorter than the page asks for, and the
// fake Marlin's holds are given in machine seconds and shortened the same way, so a 90 s M752
// takes 0.9 s here and still overruns the old 40 s bound (0.4 s).
//
//   node tests/homing-index.test.mjs RMR_Controller.html
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SCALE = 100;                              // machine ms per real ms
const machineS = s => s * 1000 / SCALE;         // real ms for s machine seconds

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
ev('isConnected = true');
ev('globalThis.__wire = []');
ev(`writer = { write: async (b) => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); } }`);
const wire = ev('__wire');
// Console lines, with how many commands had been written when each was logged.
ev(`globalThis.__log = [];
    globalThis.__logInfoOrig = logInfo; logInfo = (m) => { globalThis.__log.push({ m, at: globalThis.__wire.length }); return globalThis.__logInfoOrig(m); };
    globalThis.__logErrOrig = logErr;   logErr  = (m) => { globalThis.__log.push({ m, at: globalThis.__wire.length, err: true }); return globalThis.__logErrOrig(m); }`);
const log = ev('__log');
// The ok-timeout each sequencer step asked for (machine ms), armed SCALE times shorter.
ev(`globalThis.__waits = []; globalThis.__awaitOrig = seqAwaitOk;
    seqAwaitOk = (ms, label) => { globalThis.__waits.push({ label, ms }); return globalThis.__awaitOrig(ms / ${SCALE}, label); }`);
const waits = ev('__waits');
const rx = line => ev('processLine')(line);
const status = () => String(el('seqStatus').innerHTML);
// The M752 verdict watch: null when idle.
const watch = () => ev("typeof uvIndexVerdict === 'undefined' ? undefined : uvIndexVerdict");
const bound = () => ev("typeof SPIN_INDEX_TIMEOUT_MS === 'undefined' ? undefined : SPIN_INDEX_TIMEOUT_MS");

const HOME = ['G28', 'M118 RMR:HOMED_ALL'];
// The first M752 after a reset: boot() (M751_M752.cpp prints BOOTING), then doIndexHome().
const INDEX_FIRST = ['echo:SPIN STATE:BOOTING', 'echo:SPIN STATE:WAITING_ODRIVE', 'echo:SPIN DATA: Vbus=24.07V',
  'echo:SPIN STATE:INDEX_SEARCH_BOOT', 'echo:SPIN STATE:INDEX_SEARCH_ACTIVE', 'echo:SPIN STATE:INDEX_SETTLE_BOOT',
  'echo:SPIN DATA: BootSettleErr=0.30 deg', 'echo:SPIN DATA: InitialPos=0.38',
  'echo:SPIN WARN: datum established at the index mark on boot -- re-run M751 if layer registration matters',
  'echo:SPIN OK: READY', 'echo:SPIN STATE:HOMING', 'echo:SPIN STATE:INDEX_SEARCH_ACTIVE', 'echo:SPIN STATE:HOME_SETTLE',
  'echo:SPIN DATA: HomeSettleErr=0.22 deg', 'echo:SPIN OK: INDEX_COMPLETE'];
const INDEX_FAILED = ['echo:SPIN STATE:HOMING', 'echo:SPIN STATE:INDEX_SEARCH_ACTIVE', 'echo:SPIN DATA: HomeSettle timeout (8s)',
  'echo:SPIN ERR: INDEX_INCOMPLETE -- datum not reached', 'echo:SPIN ERR: INDEX_HOME_FAILED'];
const BOOT_FAILED = ['echo:SPIN STATE:BOOTING', 'echo:SPIN STATE:WAITING_ODRIVE',
  'echo:SPIN ERR: ODrive not detected (15s timeout)', 'echo:SPIN ERR: ODrive boot failed'];

// Fake Marlin: answers each written command in order with 'ok'. An M752 first prints `m752`;
// `holdS[cmd]` machine seconds delays that command's answer, and everything behind it.
function marlin({ m752 = INDEX_FIRST, holdS = {} } = {}) {
  let answered = 0, stop = false;
  (async () => {
    while (!stop) {
      if (answered < wire.length) {
        const cmd = wire[answered];
        if (holdS[cmd]) await sleep(machineS(holdS[cmd]));
        if (stop) break;
        if (cmd === 'M752') m752.forEach(rx);
        if (cmd.startsWith('M118 ')) rx(cmd.slice(5));
        rx('ok');
        answered++;
      } else await sleep(2);
    }
  })();
  return () => { stop = true; };
}

// Run the Homing block from its Run button (or Run All) and wait for the sequencer to finish.
async function runHoming(opts, start = () => ev('seqRunBlock')('homing')) {
  wire.length = 0; log.length = 0; waits.length = 0;
  ev('okLedgerReset')();
  const stopMarlin = marlin(opts);
  start();
  for (let i = 0; i < 3000 && ev('seqRunning'); i++) await sleep(5);
  stopMarlin();
  await sleep(10);
  return [...wire];
}
el('homeAll').checked = true;

// == 1: option on, a slow but healthy M752 ==
console.log('\n1  option on: a first M752 after a reset that takes 90 s (over the old 40 s) passes');
el('homeSpin').checked = true;
{
  const cmds = await runHoming({ holdS: { M752: 90 } });
  ok('order: G28, M118 RMR:HOMED_ALL, M752', JSON.stringify(cmds) === JSON.stringify([...HOME, 'M752']), cmds);
  const w = waits.find(x => x.label === 'M752');
  ok('the M752 step allows at least the ~130 s worst case', w && w.ms >= 130000, w);
  ok('it is the shared bound, SPIN_INDEX_TIMEOUT_MS', w && bound() !== undefined && w.ms === bound(), [w, bound()]);
  ok('the block completed', ev('seqRunning') === false && /Homing<\/b> complete/.test(status()), status());
  const lid = log.find(l => /M752/.test(l.m) && /lid open/.test(l.m));
  ok('a console line before the M752 says it runs with the lid open', lid && lid.at === cmds.indexOf('M752'), log);
  ok('the pass is logged from the marker', log.some(l => /^Homing: spincoater at its datum \(OK: INDEX_COMPLETE\)/.test(l.m)), log);
  ok('no verdict watch left armed', watch() === null, watch());
}

// == 2: the M752 is judged by its terminal marker, not by its 'ok' ==
console.log("\n2  a failed index search fails the block, whatever the 'ok' says");
for (const [what, m752, re] of [
  ['ERR: INDEX_HOME_FAILED', INDEX_FAILED, /Error: .*INDEX_HOME_FAILED/],
  ["'ok' with no marker", [], /Error: M752 ended without OK: INDEX_COMPLETE/],
  ['a failed ODrive boot', BOOT_FAILED, /Error: .*ODrive boot failed/],
]) {
  const cmds = await runHoming({ m752 });
  ok(what + ': the M752 was sent and was the last command', cmds.at(-1) === 'M752', cmds);
  ok(what + ': the block failed, naming it', ev('seqRunning') === false && re.test(status()), status());
  ok(what + ': the failure is logged as an error', log.some(l => l.err && /Homing failed/.test(l.m)), log);
  ok(what + ': no verdict watch left armed', watch() === null, watch());
}

// == 3: Run All stops at a failed index search ==
console.log('\n3  Run All (Homing + Spin Coater): a failed index search fails the run before the spin');
ev("globalThis.__isEnabledOrig = seqIsEnabled; seqIsEnabled = (id) => id === 'homing' || id === 'spin'");
{
  const cmds = await runHoming({ m752: INDEX_FAILED }, () => ev('seqRunAll')());
  ok('G28, M118, M752 and nothing after it (no M750)', JSON.stringify(cmds) === JSON.stringify([...HOME, 'M752']), cmds);
  ok('the run failed, naming the marker', ev('seqRunning') === false && /Error: .*INDEX_HOME_FAILED/.test(status()), status());
}
ev('seqIsEnabled = globalThis.__isEnabledOrig');

// == 4: option off: no M752 ==
console.log('\n4  option off: no M752');
el('homeSpin').checked = false;
{
  const cmds = await runHoming({});
  ok('order: G28, M118 RMR:HOMED_ALL; no M752', JSON.stringify(cmds) === JSON.stringify(HOME), cmds);
  ok('the block completed', ev('seqRunning') === false && /Homing<\/b> complete/.test(status()), status());
  ok('no lid-open line', !log.some(l => /lid open/.test(l.m)), log);
}

// == 5: the step is still bounded ==
console.log('\n5  an M752 that has not answered after the bound fails the block at the bound');
el('homeSpin').checked = true;
{
  const cmds = await runHoming({ holdS: { M752: 200 } });
  ok('the M752 was the last command', cmds.at(-1) === 'M752', cmds);
  ok('the block failed on the M752 ok-timeout', ev('seqRunning') === false && /Error: no "ok" for "M752"/.test(status()), status());
  ok('no verdict watch left armed', watch() === null, watch());
}

if (ev('autoReportInterval')) clearInterval(ev('autoReportInterval'));
console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
