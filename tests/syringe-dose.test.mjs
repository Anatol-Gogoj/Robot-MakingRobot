// Drives the retuned Syringe block in either UI: the post-dose dwell, the separate retract feed, the
// snap lift, the dose / retract / stroke guards, the purge and prime routines, the barrel calibration, and
// the preset → Process Sequencer apply path used by the Run Log. The stroke guard is checked against the
// position the fake firmware reports to M114 (not the readout), and a Stop / fault inside the relative-mode
// section must still put the firmware back into G90.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
ev('isConnected = true');
ev('globalThis.__sent = []');
// The fake firmware answers M114 with a position line whose C field is __posC (NaN = no C in the reply).
// The line is fed before the 'ok' that drive() supplies, as on the wire.
ev('globalThis.__posC = 0');
ev(`writer = { write: async (b) => {
  const c = new TextDecoder().decode(b).trim(); globalThis.__sent.push(c);
  if (c === 'M114') { const p = globalThis.__posC, hasC = !isNaN(p);
    processLine('X:0.00 Y:0.00 Z:0.00 A:0.00 B:0.00' + (hasC ? ' C:' + p.toFixed(2) : '') + ' Count X:0 Y:0 Z:0 A:0 B:0' + (hasC ? ' C:0' : '')); }
} }`);
const sent = ev('__sent');

// drive an async block: feed one 'ok' per pending command until it settles (a dwell is a browser-side sleep)
async function drive(fnName, ...args) {
  sent.length = 0;
  let done = false, err = null;
  ev(fnName)(...args).then(() => { done = true; }, e => { done = true; err = e; });
  for (let i = 0; i < 400 && !done; i++) { await sleep(5); ev('processLine')('ok'); }
  await sleep(5);
  return { done, err, cmds: [...sent] };
}
// drive until `untilCmd` has been sent (its 'ok' still pending), end the run the given way, let it unwind
async function driveThenAbort(fnName, untilCmd, abort) {
  sent.length = 0;
  let done = false, err = null;
  ev(fnName)().then(() => { done = true; }, e => { done = true; err = e; });
  for (let i = 0; i < 400 && !sent.includes(untilCmd); i++) { await sleep(5); ev('processLine')('ok'); }
  ev('seqRunning = true'); abort();            // seqStop() / seqFault() act only on a running sequence
  for (let i = 0; i < 100 && !done; i++) await sleep(5);
  ev('seqRunning = false; seqAbort = false; seqFaultReason = null');
  return { done, err, cmds: [...sent] };
}
const after = (cmds, c) => cmds.slice(cmds.indexOf(c) + 1);

// 1 -- defaults
ok('dwell defaults to 2 s', el('syrDwell').value == 2, el('syrDwell').value);
ok('max-retract guard defaults to 0.05 mm', el('syrMaxRetract').value == 0.05, el('syrMaxRetract').value);
ok('purge defaults: 2 mL at 60 mm/min, idle limit 300 s', el('syrPurgeVol').value == 2 && el('syrPurgeFeed').value == 60 && el('syrIdleLimit').value == 300);
ok('the 150 mL syringe is the default: 0.7958 mm/mL, 5 mL at 15.9 mm/min, 0.0227 mL retract at 1 mm/min, 4 mm snap, 120 mm stroke, 4.18 mm max dose, 0.5 mL prime',
   el('calMm').value == 0.7958 && el('syrVol').value == 5 && el('syrFeed').value == 15.9 && el('syrPull').value == 0.0227 && el('syrRetractFeed').value == 1 && el('syrSnapMm').value == 4 && el('syrStroke').value == 120 && el('syrMaxDose').value == 4.18 && el('syrPrimeVol').value == 0.5,
   [el('calMm').value, el('syrVol').value, el('syrFeed').value, el('syrStroke').value, el('syrPrimeVol').value]);

// 2 -- barrel calibration: 40 mm ID → 0.7958 mm of plunger per mL
el('syrBarrelId').value = '40';
ev('syrCalFromBarrel')();
ok('calibration from the barrel ID', Math.abs(parseFloat(el('calMm').value) - 0.7958) < 0.0005 && el('calMl').value == 1, [el('calMm').value, el('calMl').value]);

// 3 -- the 150 mL dose: 5 mL in 15 s, 0.02 s dwell (kept short for the test), 0.018 mm retract at 1 mm/min, 4 mm snap
Object.entries({ syrVol: '5', syrPull: '0.0227', syrFeed: '15.9', syrRetractFeed: '1', syrDwell: '0.02', syrSnapMm: '4', syrSnapFeed: '3000',
                 syrPos: '295', syrPosFeed: '1500', syrMaxDose: '4.18', syrMaxRetract: '0.05', syrStroke: '119.4' }).forEach(([k, v]) => { el(k).value = v; });
ev('__posC = 0'); el('posE').textContent = '118.0';   // the readout is stale (it would fail the guard); the firmware says C0
{
  const r = await drive('runSyringeBlock');
  ok('dose block completed', r.done && !r.err, r.err && r.err.message);
  const want = ['M114', 'G90', 'G1 X385 F24000', 'M400', 'G1 B295.000 F1500', 'M400', 'G91', 'G1 C3.9790 F15.9', 'M400', 'G1 C-0.0181 F1', 'M400', 'G1 B-4.000 F3000', 'M400', 'G90', 'G1 B0 F1500', 'M400'];
  ok('exact command order: position query · center X · lower · dose · M400 · (dwell) · retract at its own feed · snap lift · raise', JSON.stringify(r.cmds) === JSON.stringify(want), r.cmds);
  ok('the stroke guard used the M114 reply, not the stale readout, and the reply refreshed the readout', el('posE').textContent === '0.0', el('posE').textContent);
}

// 4 -- guards: the parameter caps refuse with nothing sent; the stroke check asks the firmware first
el('syrPull').value = '0.1';   // 0.0796 mm of plunger > 0.05 mm
{
  const r = await drive('runSyringeBlock');
  ok('retract above the guard is refused with nothing sent', r.err && /max-retract/.test(r.err.message) && r.cmds.length === 0, [r.err && r.err.message, r.cmds]);
}
el('syrPull').value = '0.0227'; el('syrVol').value = '6';   // 4.775 mm > 4.18 mm
{
  const r = await drive('runSyringeBlock');
  ok('dose above the guard is refused with nothing sent', r.err && /max-dose/.test(r.err.message) && r.cmds.length === 0, r.err && r.err.message);
}
el('syrVol').value = '5'; ev('__posC = 118'); el('posE').textContent = '0.0';   // 118 + 3.979 > 119.4, whatever the readout says
{
  const r = await drive('runSyringeBlock');
  ok('a dose past the barrel stroke is refused on the firmware position (M114 only, no move)', r.err && /stroke/.test(r.err.message) && JSON.stringify(r.cmds) === '["M114"]', [r.err && r.err.message, r.cmds]);
}
ev('__posC = NaN');
{
  const r = await drive('runSyringeBlock');
  ok('an M114 reply without a C position refuses the dose instead of guessing', r.err && /no C/.test(r.err.message) && JSON.stringify(r.cmds) === '["M114"]', [r.err && r.err.message, r.cmds]);
}
el('syrStroke').value = '0';
{
  const r = await drive('runSyringeBlock');
  ok('stroke guard off (0): no position query, the cycle starts with G90 as before', r.done && !r.err && r.cmds[0] === 'G90' && !r.cmds.includes('M114'), r.err ? r.err.message : r.cmds);
}
el('syrStroke').value = '119.4'; ev('__posC = 0'); el('posE').textContent = '---';

// 5 -- purge: 2 mL at 60 mm/min with the same dwell / retract / snap
{
  const r = await drive('runSyringePurge', false);
  ok('purge completed', r.done && !r.err, r.err && r.err.message);
  ok('purge queries the position, pushes 2 mL = 1.5916 mm at 60 mm/min then retracts and snaps', r.cmds[0] === 'M114' && r.cmds.includes('G1 C1.5916 F60') && r.cmds.includes('G1 C-0.0181 F1') && r.cmds.includes('G1 B-4.000 F3000'), r.cmds);
}

// 5b -- initial purge (prime): the increment only, tip stays put, no dwell / retract / lift
{
  el('syrPrimeVol').value = '0.5';
  const r = await drive('runSyringePrime');
  ok('initial purge queries the position, then pushes exactly the increment at the purge feed', r.done && !r.err && JSON.stringify(r.cmds) === JSON.stringify(['M114', 'G91', 'G1 C0.3979 F60', 'M400', 'G90']), r.err ? r.err.message : r.cmds);
  ev('__posC = 119.8');
  const r2 = await drive('runSyringePrime');
  ok('initial purge past the stroke is refused on the fresh position (repeated presses cannot walk past the barrel)', r2.err && /stroke/.test(r2.err.message) && JSON.stringify(r2.cmds) === '["M114"]', [r2.err && r2.err.message, r2.cmds]);
  ev('__posC = 0');
}

// 5c -- a Stop or a fault inside the relative-mode section still leaves the firmware in absolute mode
{
  const r = await driveThenAbort('runSyringePrime', 'G1 C0.3979 F60', () => ev('seqStop')());
  ok('Stop during the prime push: the run aborts, M410 quickstops the machine and G90 puts the firmware back into absolute mode (both UIs)',
     r.done && r.err && /aborted/.test(r.err.message) && JSON.stringify(after(r.cmds, 'G1 C0.3979 F60')) === '["M410","G90"]', [r.err && r.err.message, r.cmds]);
}
{
  const r = await driveThenAbort('runSyringeBlock', 'G1 C3.9790 F15.9', () => ev('seqFault')('MOTOR POWER LOST — test'));
  ok('fault during the dose: G90 is the only command sent after the fault', r.done && r.err && /MOTOR POWER LOST/.test(r.err.message) && JSON.stringify(after(r.cmds, 'G1 C3.9790 F15.9')) === '["G90"]', [r.err && r.err.message, r.cmds]);
}
{
  const r = await driveThenAbort('runSyringePurge', 'G1 C1.5916 F60', () => ev('seqStop')());
  ok('Stop during the purge push: M410 then G90, nothing else', r.done && r.err && JSON.stringify(after(r.cmds, 'G1 C1.5916 F60')) === '["M410","G90"]', [r.err && r.err.message, r.cmds]);
}
{
  const r = await drive('runSyringePrime');
  ok('a normal prime after an aborted one still sends G90 exactly once', r.done && !r.err && r.cmds.filter(c => c === 'G90').length === 1, r.err ? r.err.message : r.cmds);
}

// 6 -- idle warning: never blocks
{
  ev('syrLastActivity = Date.now() - 400 * 1000');
  el('syrIdleLimit').value = '300';
  const r = await drive('runSyringeBlock');
  ok('a dose after the idle limit still runs', r.done && !r.err, r.err && r.err.message);
}

// 7 -- preset → sequencer (the Run Log's few-clicks path)
const log = ev('rmrLog');
ok('built-in 150 mL preset carries sequencer settings', !!log.presets['CN9018 7.5% HDDA · 150 mL syringe'] && Object.keys(log.presets['CN9018 7.5% HDDA · 150 mL syringe'].sequencer).length > 20);
{
  const n = log.seqApply({ seqSpinRPM: 1234, uvTime: 77, syrVol: 2.5, 'enable.stamp': false, stampSide: 'left', syrDwell: 3 });
  ok('seqApply writes the inputs', el('seqSpinRPM').value == 1234 && el('uvTime').value == 77 && el('syrVol').value == 2.5 && el('syrDwell').value == 3, [n, el('seqSpinRPM').value]);
  const snap = log.seqSnapshot();
  ok('seqSnapshot reads them back', snap.seqSpinRPM == 1234 && snap.uvTime == 77 && snap.syrDwell == 3, snap);
}
{
  const pre = log.presets['CN9018 7.5% HDDA · 150 mL syringe'];
  ok('createDevice stores the preset sequencer settings', log.createDevice({ id: 'T-150', material: pre.material, sequencer: pre.sequencer }) === true && log.device.sequencer && log.device.sequencer.syrFeed === 15.9);
  const n = log.applyToSequencer();
  ok('applyToSequencer sets up the Process Sequencer from the device', n > 20 && el('syrFeed').value == 15.9 && el('syrRetractFeed').value == 1 && el('syrPull').value == 0.0227 && el('seqSpinRPM').value == 1000 && el('uvTime').value == 480, [n, el('syrFeed').value, el('seqSpinRPM').value]);
  log.setLogging(true);
  const r = await drive('runSyringePurge', true);
  ok('purge is journaled', r.done && !r.err && log.device.journal.some(j => /purged 2\.00 mL/.test(j.text)), log.device.journal.slice(-2));
}

console.log(fails ? `\n${fails} check(s) failed` : '\nall checks passed');
process.exit(fails ? 1 : 0);
