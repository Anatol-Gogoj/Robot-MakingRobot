// Issue #183: the UV block's spincoater index search (M752) runs after the cure, never during it.
//
// M752 blocks Marlin's serial input until it returns (idle() reads none), so an M752 sent
// during the cure held back everything sent after it: the lamp-off at the end of a short cure,
// the argon-close, and the lamp-off of a Stop (M410 does not interrupt M752). The lamp could
// stay on for most of a minute past the cure or the Stop. The fix runs the M752 once the lamp
// is off and the argon is closed, with the lid still closed, as a step that waits for its own
// 'ok', and judges it by the firmware's terminal marker, not by the 'ok'.
//
// These checks drive the real runUvBlock() through the real ok ledger. A fake Marlin answers
// every written command in order, and can hold an answer back the way a blocking M752 does.
//
// RMR_Touch.html has no uvSpinHome checkbox today (the stub DOM creates the element on first
// lookup), so a preset cannot turn the option on there; its engine is kept identical anyway.
//
//   node tests/uv-index-order.test.mjs RMR_Controller.html RMR_Touch.html
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

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
ev('isConnected = true');
// The wire, plus what the ok ledger owed at the moment each command was written (the
// commands ahead of it, itself included): a lamp-off queued behind an M752 shows up here.
ev('globalThis.__wire = []; globalThis.__owed = []');
ev(`writer = { write: async (b) => {
  globalThis.__wire.push(new TextDecoder().decode(b).trim());
  globalThis.__owed.push(okLedger.map(e => e.cmd));
} }`);
const wire = ev('__wire'), owed = ev('__owed');
const owedAt = cmd => owed[wire.indexOf(cmd)] || null;
// Run Log events, with how many commands had been written when each fired.
ev(`globalThis.__rl = []; globalThis.__rlOrig = rlEvent;
    rlEvent = (k, d) => { globalThis.__rl.push({ k, at: globalThis.__wire.length, d }); return globalThis.__rlOrig(k, d); }`);
const rl = ev('__rl');
// The ok timeout each sequencer step was given.
ev(`globalThis.__waits = []; globalThis.__awaitOrig = seqAwaitOk;
    seqAwaitOk = (ms, label) => { globalThis.__waits.push({ label, ms }); return globalThis.__awaitOrig(ms, label); }`);
const waits = ev('__waits');
const rx = line => ev('processLine')(line);
const status = () => String(el('seqStatus').innerHTML);
// The UV block's M752 verdict watch: null when idle (undefined on a page without one).
const watch = () => ev("typeof uvIndexVerdict === 'undefined' ? undefined : uvIndexVerdict");

const LAMP_ON = 'M42 P4 S1', LAMP_OFF = 'M42 P4 S0', AR_OPEN = 'M42 P42 S1', AR_CLOSE = 'M42 P42 S0';
const LID_CLOSE = 'M280 P1 S115 T800', LID_OPEN = 'M280 P1 S30 T800';
const INDEX_OK = ['echo:SPIN STATE:HOMING', 'echo:SPIN STATE:INDEX_SEARCH_ACTIVE', 'echo:SPIN STATE:HOME_SETTLE',
                  'echo:SPIN DATA: HomeSettleErr=0.22 deg', 'echo:SPIN OK: INDEX_COMPLETE'];

// Fake Marlin: answers each written command in order with 'ok'. An M752 first prints `m752`;
// `hold[cmd]` ms delays that command's answer, and everything behind it, as Marlin would.
function marlin({ m752 = INDEX_OK, hold = {} } = {}) {
  let answered = 0, stop = false;
  (async () => {
    while (!stop) {
      if (answered < wire.length) {
        const cmd = wire[answered];
        if (hold[cmd]) await sleep(hold[cmd]);
        if (stop) break;
        if (cmd === 'M752') m752.forEach(rx);
        rx('ok');
        answered++;
      } else await sleep(2);
    }
  })();
  return () => { stop = true; };
}

function setUp({ index, argon, lid = true, cure = 0.1 }) {
  el('uvTime').value = String(cure);
  el('uvSeqPin').value = '4';
  el('uvLid').checked = lid; el('uvLidClose').value = '115'; el('uvLidOpen').value = '30';
  el('uvSpinHome').checked = index;
  el('uvArgon').checked = argon; el('uvArgonPin').value = '42';
  el('uvArgonLead').value = '0.05'; el('uvArgonLag').value = '0.05';
}

// Run the UV block from its Run button and wait for the sequencer to finish.
async function runUv(opts, during) {
  wire.length = 0; owed.length = 0; rl.length = 0; waits.length = 0;
  ev('okLedgerReset')();
  ev('seqSetHomed')(true, 'test');
  const stopMarlin = marlin(opts);
  ev('seqRunBlock')('uv');
  if (during) await during();
  for (let i = 0; i < 1500 && ev('seqRunning'); i++) await sleep(5);
  stopMarlin();
  await sleep(10);
  return [...wire];
}
const waitFor = async (pred, ms = 3000) => { for (let i = 0; i < ms / 5 && !pred(); i++) await sleep(5); return pred(); };

// == 1: option on: lamp on, lamp off, argon closed, THEN the M752, then the lid ==
console.log('\n1  option on: the M752 runs after the lamp-off and the argon-close, before the lid reopens');
setUp({ index: true, argon: true });
{
  let heldQuiet = null;
  const cmds = await runUv({ hold: { M752: 300 } }, async () => {
    await waitFor(() => wire.at(-1) === 'M752');
    await sleep(150);                                  // the M752 is still running on the machine
    heldQuiet = wire.at(-1) === 'M752';
  });
  ok('order: M400, lid close, argon open, lamp on, lamp off, argon close, M752, lid reopen',
     JSON.stringify(cmds) === JSON.stringify(['M400', LID_CLOSE, AR_OPEN, LAMP_ON, LAMP_OFF, AR_CLOSE, 'M752', LID_OPEN]), cmds);
  ok('lamp-off and argon-close went out with nothing ahead of them',
     JSON.stringify(owedAt(LAMP_OFF)) === JSON.stringify([LAMP_OFF]) && JSON.stringify(owedAt(AR_CLOSE)) === JSON.stringify([AR_CLOSE]),
     [owedAt(LAMP_OFF), owedAt(AR_CLOSE)]);
  ok('the M752 went out alone, after both relays were answered', JSON.stringify(owedAt('M752')) === JSON.stringify(['M752']), owedAt('M752'));
  ok('nothing was sent while the M752 ran (the lid waits for its ok)', heldQuiet === true, wire);
  const on = rl.find(e => e.k === 'uv.on'), off = rl.find(e => e.k === 'uv.off');
  ok("Run Log: uv.on after the lamp-on's ok, uv.off after the lamp-off's ok and before the M752 went out",
     on && off && on.at === cmds.indexOf(LAMP_ON) + 1 && off.at === cmds.indexOf(LAMP_OFF) + 1 && off.at <= cmds.indexOf('M752') && !off.d.aborted,
     rl.filter(e => /^uv\./.test(e.k)));
  const w = waits.find(x => x.label === 'M752');
  ok('the M752 step allows at least the ~130 s worst case (first-use boot + index search)', w && w.ms >= 130000, w);
  ok('the block completed', ev('seqRunning') === false && /UV<\/b> complete/.test(status()), status());
  ok('no verdict watch left armed', watch() === null, watch());
}

// == 2: Stop mid-cure: lamp-off at once, no M752 ==
// The M752 is held for 2 s: on the old code it was sent at lamp-on and would sit ahead of the
// Stop's lamp-off in the ledger, which is the overrun this issue is about.
console.log('\n2  a Stop mid-cure sends the lamp-off and argon-close at once, and no M752');
setUp({ index: true, argon: true, cure: 5 });
{
  const cmds = await runUv({ hold: { M752: 2000 } }, async () => {
    await waitFor(() => rl.some(e => e.k === 'uv.on'));   // the lamp-on's own ok has come
    await sleep(120);
    ev('seqStop')();
  });
  ok('no M752 was sent', !cmds.includes('M752'), cmds);
  ok('Stop sent M410, then the lamp-off, then the argon-close',
     JSON.stringify(cmds.slice(cmds.indexOf('M410'))) === JSON.stringify(['M410', LAMP_OFF, AR_CLOSE]), cmds);
  ok('nothing blocking was ahead of the lamp-off', owedAt(LAMP_OFF) && !owedAt(LAMP_OFF).includes('M752')
     && owedAt(LAMP_OFF).every(c => c === 'M410' || c === LAMP_OFF), owedAt(LAMP_OFF));
  ok('the lid was not reopened', !cmds.includes(LID_OPEN), cmds);
  ok('Run Log: the aborted lamp-off is recorded', rl.some(e => e.k === 'uv.off' && e.d && e.d.aborted), rl.filter(e => /^uv\./.test(e.k)));
  ok('the run reads Stopped', ev('seqRunning') === false && /Stopped/.test(status()), status());
}

// == 3: a fault mid-cure (the lid interlock's cut) behaves the same ==
console.log('\n3  a fault mid-cure sends the lamp-off at once, and no M752');
setUp({ index: true, argon: false, cure: 5 });
{
  const cmds = await runUv({ hold: { M752: 2000 } }, async () => {
    await waitFor(() => rl.some(e => e.k === 'uv.on'));   // the lamp-on's own ok has come
    await sleep(120);
    rx('echo:UV cut: lid opened (interlock)');
  });
  ok('no M752 was sent', !cmds.includes('M752'), cmds);
  ok('the lamp-off went out with nothing ahead of it', cmds.at(-1) === LAMP_OFF && JSON.stringify(owedAt(LAMP_OFF)) === JSON.stringify([LAMP_OFF]), [cmds, owedAt(LAMP_OFF)]);
  ok('the lid was not reopened', !cmds.includes(LID_OPEN), cmds);
  ok('the run failed with the fault', ev('seqRunning') === false && /Error: .*lid/.test(status()), status());
}

// == 4: option off: no M752 at all ==
console.log('\n4  option off: no M752');
setUp({ index: false, argon: false });
{
  const cmds = await runUv({});
  ok('order: M400, lid close, lamp on, lamp off, lid reopen; no M752',
     JSON.stringify(cmds) === JSON.stringify(['M400', LID_CLOSE, LAMP_ON, LAMP_OFF, LID_OPEN]), cmds);
  ok('the block completed', ev('seqRunning') === false && /UV<\/b> complete/.test(status()), status());
}

// == 5: the M752 is judged by its terminal marker, not by its 'ok' ==
console.log("\n5  a failed index search fails the block, whatever the 'ok' says, and the lid stays closed");
for (const [what, m752, re] of [
  ['ERR: INDEX_HOME_FAILED', ['echo:SPIN STATE:HOMING', 'echo:SPIN STATE:INDEX_SEARCH_ACTIVE', 'echo:SPIN DATA: HomeSettle timeout (8s)',
    'echo:SPIN ERR: INDEX_INCOMPLETE -- datum not reached', 'echo:SPIN ERR: INDEX_HOME_FAILED'], /INDEX_HOME_FAILED/],
  ['a failed boot (no terminal marker)', ['echo:SPIN STATE:BOOTING', 'echo:SPIN STATE:WAITING_ODRIVE',
    'echo:SPIN ERR: ODrive not detected (15s timeout)', 'echo:SPIN ERR: ODrive boot failed'], /ODrive boot failed/],
  ['no marker at all', ['echo:Unknown command: "M752"'], /without OK: INDEX_COMPLETE/],
  ['an earlier M752\'s OK: INDEX_COMPLETE, then this one failing', ['echo:SPIN OK: INDEX_COMPLETE', 'echo:SPIN STATE:HOMING',
    'echo:SPIN ERR: ODrive not responding', 'echo:SPIN ERR: INDEX_HOME_FAILED'], /INDEX_HOME_FAILED/],
]) {
  setUp({ index: true, argon: false, cure: 0.05 });
  const cmds = await runUv({ m752 });
  ok(what + ': the block failed, naming it', ev('seqRunning') === false && re.test(status()), status());
  ok(what + ': the M752 was the last command; the lid stays closed', cmds.at(-1) === 'M752' && !cmds.includes(LID_OPEN), cmds);
  ok(what + ': no verdict watch left armed', watch() === null, watch());
}

// == 6: a Stop during the M752 leaves the lid closed ==
console.log('\n6  a Stop while the M752 runs ends the run and leaves the lid closed');
setUp({ index: true, argon: false, cure: 0.05 });
{
  const cmds = await runUv({ hold: { M752: 1000 } }, async () => {
    await waitFor(() => wire.at(-1) === 'M752');
    await sleep(50);
    ev('seqStop')();
  });
  ok('the lamp was off before the M752 went out', cmds.indexOf(LAMP_OFF) >= 0 && cmds.indexOf(LAMP_OFF) < cmds.indexOf('M752'), cmds);
  ok('Stop sent M410 and nothing else; no lid reopen', cmds.at(-1) === 'M410' && !cmds.includes(LID_OPEN), cmds);
  ok('the run reads Stopped', ev('seqRunning') === false && /Stopped/.test(status()), status());
  ok('no verdict watch left armed', watch() === null, watch());
}

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
