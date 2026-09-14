// Drives the retuned Syringe block in either UI: the post-dose dwell, the separate retract feed, the
// snap lift, the dose / retract / stroke guards, the purge routine, the barrel calibration, and the
// preset → Process Sequencer apply path used by the Run Log.
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
ev('writer = { write: async (b) => { globalThis.__sent.push(new TextDecoder().decode(b).trim()); } }');
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

// 1 -- defaults
ok('dwell defaults to 2 s', el('syrDwell').value == 2, el('syrDwell').value);
ok('max-retract guard defaults to 0.05 mm', el('syrMaxRetract').value == 0.05, el('syrMaxRetract').value);
ok('purge defaults: 2 mL at 60 mm/min, idle limit 300 s', el('syrPurgeVol').value == 2 && el('syrPurgeFeed').value == 60 && el('syrIdleLimit').value == 300);

// 2 -- barrel calibration: 40 mm ID → 0.7958 mm of plunger per mL
el('syrBarrelId').value = '40';
ev('syrCalFromBarrel')();
ok('calibration from the barrel ID', Math.abs(parseFloat(el('calMm').value) - 0.7958) < 0.0005 && el('calMl').value == 1, [el('calMm').value, el('calMl').value]);

// 3 -- the 150 mL dose: 5 mL in 15 s, 0.02 s dwell (kept short for the test), 0.018 mm retract at 1 mm/min, 4 mm snap
Object.entries({ syrVol: '5', syrPull: '0.0227', syrFeed: '15.9', syrRetractFeed: '1', syrDwell: '0.02', syrSnapMm: '4', syrSnapFeed: '3000',
                 syrPos: '304', syrPosFeed: '1500', syrMaxDose: '4.18', syrMaxRetract: '0.05', syrStroke: '119.4' }).forEach(([k, v]) => { el(k).value = v; });
el('posE').textContent = '---';
{
  const r = await drive('runSyringeBlock');
  ok('dose block completed', r.done && !r.err, r.err && r.err.message);
  const want = ['G90', 'G1 B304.000 F1500', 'M400', 'G91', 'G1 C3.9790 F15.9', 'M400', 'G1 C-0.0181 F1', 'M400', 'G1 B-4.000 F3000', 'M400', 'G90', 'G1 B0 F1500', 'M400'];
  ok('exact command order: lower · dose · M400 · (dwell) · retract at its own feed · snap lift · raise', JSON.stringify(r.cmds) === JSON.stringify(want), r.cmds);
}

// 4 -- guards refuse before anything is sent
el('syrPull').value = '0.1';   // 0.0796 mm of plunger > 0.05 mm
{
  const r = await drive('runSyringeBlock');
  ok('retract above the guard is refused with nothing sent', r.err && /max-retract/.test(r.err.message) && r.cmds.length === 0, [r.err && r.err.message, r.cmds]);
}
el('syrPull').value = '0.0227'; el('syrVol').value = '6';   // 4.775 mm > 4.18 mm
{
  const r = await drive('runSyringeBlock');
  ok('dose above the guard is refused', r.err && /max-dose/.test(r.err.message) && r.cmds.length === 0, r.err && r.err.message);
}
el('syrVol').value = '5'; el('posE').textContent = '118.0';   // 118 + 3.979 > 119.4
{
  const r = await drive('runSyringeBlock');
  ok('a dose past the barrel stroke is refused using the last C position', r.err && /stroke/.test(r.err.message) && r.cmds.length === 0, r.err && r.err.message);
}
el('posE').textContent = '---';

// 5 -- purge: 2 mL at 60 mm/min with the same dwell / retract / snap
{
  const r = await drive('runSyringePurge', false);
  ok('purge completed', r.done && !r.err, r.err && r.err.message);
  ok('purge pushes 2 mL = 1.5916 mm at 60 mm/min then retracts and snaps', r.cmds.includes('G1 C1.5916 F60') && r.cmds.includes('G1 C-0.0181 F1') && r.cmds.includes('G1 B-4.000 F3000'), r.cmds);
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
