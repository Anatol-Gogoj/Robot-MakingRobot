// Drives the shipped Run Log module (rmrLog) in either UI: the sequencer hooks,
// the spin capture window, hold / resume, edit precedence and the exports.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 0));
const sleep = ms => new Promise(r => setTimeout(r, ms));

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);

const log = ev('rmrLog');
ok('rmrLog module is loaded and attached', !!log && typeof log.event === 'function' && !!log.prefs, typeof log);

// quiet the toasts / console helpers but keep them callable
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');

// 1 -- a device log, armed
ok('createDevice', log.createDevice({ id: 'T-1', material: 'CN9018 7.5% HDDA', thicknessUm: 70, targetLayers: 3, rpm: 1000, holdS: 50, cureS: 5, dispenseMl: 0.05, firstElectrode: 'P', electrodeNote: 'hand press' }) === true);
log.setLogging(true);
ok('logging armed', log.device.state.logging === 'armed', log.device.state);
ok('prefill sets Run All cycles to the remaining layers', el('seqCycles').value == 3 && el('seqRepeat').checked === true, [el('seqCycles').value, el('seqRepeat').checked]);

// 2 -- the real Syringe block: dispense is recorded when the M400 after the push is acknowledged
ev('isConnected = true');
ev('writer = { write: async () => {} }');
el('syrVol').value = '0.05'; el('syrPull').value = '0.005'; el('calMm').value = '100'; el('calMl').value = '1';
el('syrDwell').value = '0.02';   // the post-dose dwell is a browser-side sleep; keep the test quick
{
  const sent = [];
  ev('globalThis.__sent = []');
  ev('writer = { write: async (b) => { globalThis.__sent.push(new TextDecoder().decode(b).trim()); } }');
  let done = false, err = null;
  ev('runSyringeBlock')().then(() => { done = true; }, e => { done = true; err = e; });
  for (let i = 0; i < 400 && !done; i++) { await sleep(5); ev('processLine')('ok'); }
  await flush();
  const cmds = ev('__sent');
  ok('syringe block ran to completion', done && !err, err && err.message);
  ok('syringe block sent the dispense push then M400', cmds.some(c => /^G1 C5\.0000 F/.test(c)) && cmds.includes('M400'), cmds);
  const rows = log.device.rows;
  ok('one layer row opened', rows.length === 1 && rows[0].kind === 'layer' && rows[0].layer === 1, rows.map(r => r.kind));
  ok('dispense time + volume recorded', !!rows[0].dispense.at && rows[0].dispense.mL === 0.05 && rows[0].dispense.mm === 5, rows[0].dispense);
}

// 3 -- spin capture window: MeanRPM comes only from lines between M750 and its ok
const feed = line => ev('processLine')(line);
log.event('spin.start', { rpm: 1000, dur: 10, rise: 3, sink: 3, home: 1 });
ok('spin.start opens a capture on the open layer', !!log.capture && log.capture.rowId === log.device.rows[0].id, log.capture);
feed('echo:SPIN STATE:MEASURING');
feed('echo:SPIN DATA: MeanRPM=1009.88');
feed('echo:SPIN DATA: StdDevRPM=4.47');
feed('echo:SPIN DATA: Samples=99');
feed('echo:SPIN DATA: HomeSettleErr=0.40 deg');
feed('echo:SPIN OK: CYCLE_COMPLETE');
log.event('spin.done', { aborted: false, fault: null });
{
  const s = log.device.rows[0].spin;
  ok('MeanRPM / σ / n / HomeSettleErr captured', s.meanRpm === 1009.88 && s.stdRpm === 4.47 && s.samples === 99 && s.homeSettleErr === 0.4, s);
  ok('spin result ok from OK: CYCLE_COMPLETE', s.result === 'ok' && s.rpmSet === 1000, s);
  ok('capture closed', !log.capture);
}

// 4 -- UV: on / off, then a cut-short cure
log.event('uv.on', { pin: 4, setS: 5, argon: false, lid: true });
await sleep(20);
log.event('uv.off', {});
{
  const c = log.device.rows[0].cure;
  ok('cure on/off/actual recorded', !!c.onAt && !!c.offAt && c.setS === 5 && typeof c.actualS === 'number' && !c.aborted, c);
}

// 5 -- electrode: hand press closes the layer; polarity follows the sheet rule
log.mark('press');
{
  const rows = log.device.rows;
  const e = rows.find(r => r.kind === 'electrode');
  ok('electrode row created after layer 1 with polarity P', !!e && e.layer === 1 && e.polarity === 'P' && !!e.stamp.at && e.stamp.manual === true, e);
  ok('hand-press note applied', e && e.notes === 'hand press', e && e.notes);
  ok('layer closed (no open layer)', log.device.state.openLayer === null, log.device.state.openLayer);
}

// 6 -- next dispense opens layer 2; a failed measure leaves RPM blank (never the previous value)
log.event('cycle.begin', { cycle: 2, cycles: 3, blocks: ['syringe', 'spin', 'uv'] });
log.event('dispense', { mL: 0.05, mm: 5, pullMl: 0.005, pullMm: 0.5, heightB: 304 });
{
  const L = log.device.rows.filter(r => r.kind === 'layer');
  ok('layer 2 opened by the next dispense', L.length === 2 && L[1].layer === 2 && !!L[1].dispense.at, L.map(r => r.layer));
}
log.event('spin.start', { rpm: 1000, dur: 10, rise: 3, sink: 3, home: 1 });
feed('echo:SPIN DATA: Samples=0');
feed('echo:SPIN ERR: Measure phase aborted -- stopping spin');
log.event('spin.done', { aborted: false, fault: null });
{
  const s = log.device.rows.filter(r => r.kind === 'layer')[1].spin;
  ok('no MeanRPM in the window → blank cell, "no samples" result', s.meanRpm === undefined && s.result === 'no samples', s);
}
log.event('uv.on', { pin: 4, setS: 5, argon: false, lid: true });
log.event('uv.off', { aborted: true });
{
  const c = log.device.rows.filter(r => r.kind === 'layer')[1].cure;
  ok('aborted cure is flagged with an actual duration', c.aborted === true && typeof c.actualS === 'number', c);
}
log.event('stamp.press', { side: 'R', holdS: 2, pressZ: 180 });
{
  const e = log.device.rows.filter(r => r.kind === 'electrode')[1];
  ok('electrode after layer 2 is N (even layer) with side R', !!e && e.polarity === 'N' && e.stamp.side === 'R' && e.stamp.holdS === 2, e);
}

// 7 -- an operator edit is never overwritten by a later automatic value
{
  const row = log.device.rows.filter(r => r.kind === 'layer')[1];
  row.edits['dispense.mL'] = { auto: 0.05, at: log.isoLocal() };
  row.dispense.mL = 0.12;
  log.event('dispense', { mL: 0.05, mm: 5 });   // a re-dispense of the same (uncured? no: cured) layer → opens layer 3, so edit layer 3 instead
  const L = log.device.rows.filter(r => r.kind === 'layer');
  const r3 = L[L.length - 1];
  r3.edits['dispense.mL'] = { auto: r3.dispense.mL, at: log.isoLocal() };
  r3.dispense.mL = 0.12;
  log.event('dispense', { mL: 0.07, mm: 7 });   // same open, uncured layer → re-dispense, must not touch the edited cell
  ok('edited cell survives an automatic re-dispense', r3.dispense.mL === 0.12 && r3.edits['dispense.mL'].auto === 0.07 && r3.flags.includes('re-dispensed'), [r3.dispense, r3.flags]);
}

// 8 -- hold / resume between commands, and a hold that aborts with the run
ev('seqRunning = true');
log.requestHold('hold', 'refill');
ok('hold requested while running is queued, not applied', !!log.device.state.holdReq && !log.device.state.hold, log.device.state);
ok('holdApplies: layer point only at cycle end', log.holdApplies('layer', 'uv', { blocks: ['syringe', 'uv'] }) === false && log.holdApplies('layer', 'cycle', {}) === true);
ok('holdApplies: cured point after uv/stamp/homing or cycle', log.holdApplies('cured', 'syringe', { blocks: ['syringe', 'spin', 'uv'] }) === false && log.holdApplies('cured', 'uv', { blocks: ['syringe', 'spin', 'uv'] }) === true);
ok('holdApplies: cured point with no UV block = any boundary', log.holdApplies('cured', 'syringe', { blocks: ['syringe', 'spin'] }) === true);
{
  let resolved = false, rejected = null;
  const p = log.seqHoldPoint('syringe', { blocks: ['syringe', 'spin', 'uv'] });
  await flush();
  ok('no hold at a non-matching point', log.device.state.hold === null && !!log.device.state.holdReq);
  await p;
  const p2 = log.seqHoldPoint('cycle', { blocks: ['syringe', 'spin', 'uv'] });
  p2.then(() => { resolved = true; }, e => { rejected = e; });
  await flush();
  ok('hold applied at the cycle boundary (hold row open, request cleared)', !!log.device.state.hold && !log.device.state.holdReq && log.device.rows.at(-1).kind === 'hold' && !log.device.rows.at(-1).to, log.device.state);
  await sleep(30);
  ok('sequencer is still waiting', !resolved && !rejected);
  log.resume();
  await flush();
  ok('resume releases the sequencer and closes the hold row', resolved && !!log.device.rows.at(-1).to && log.device.state.hold === null, [resolved, log.device.rows.at(-1)]);
}
{
  let rejected = null;
  log.requestHold('break', 'lunch');
  const p = log.seqHoldPoint('single', { blocks: ['uv'] });
  p.then(() => {}, e => { rejected = e; });
  await flush();
  ok('break applied after a single block run', !!log.device.state.hold && log.device.state.hold.kind === 'break');
  ev('seqAbort = true');
  await sleep(700);   // the hold polls the abort reason every 500 ms
  ok('a Stop during a hold rejects with RunLogAbort and closes the hold row', rejected && rejected.name === 'RunLogAbort' && log.device.state.hold === null && log.device.rows.at(-1).endedBy === 'aborted', rejected && rejected.name);
  ev('seqAbort = false'); ev('seqRunning = false');
}

// 9 -- logging off: events are ignored, the gap is noted on re-arm
log.setLogging(false);
const before = log.device.rows.length;
log.event('dispense', { mL: 0.05, mm: 5 });
ok('events ignored while logging is off', log.device.rows.length === before);
log.setLogging(true);
ok('re-arming adds a note about the gap with the missed dispense count', log.device.rows.at(-1).kind === 'note' && /1 dispense/.test(log.device.rows.at(-1).text), log.device.rows.at(-1));

// 10 -- exports
{
  const csv = log.buildCsv();
  const lines = csv.trim().split(/\r?\n/);
  ok('CSV has the header and one line per row', lines[0].startsWith('device,kind,layer,polarity,dispensed_at') && lines.length === log.device.rows.length + 1, [lines[0].slice(0, 60), lines.length]);
  ok('CSV carries the settled RPM', /1009\.88/.test(csv));
  const x = log.buildXlsx();
  ok('XLSX is a ZIP (PK signature) of a plausible size', x instanceof Uint8Array && x[0] === 0x50 && x[1] === 0x4B && x.length > 3000, x && x.length);
}

// 11 -- the shims are inert without the module and the hooks exist in the page
ok('page has the shims', ev('typeof rlEvent') === 'function' && ev('typeof rlRx') === 'function' && ev('typeof rlHoldPoint') === 'function');
ok('page declares rmrLogHost', ev('typeof window.rmrLogHost') === 'object' && typeof ev('window.rmrLogHost').isRunning === 'function');

// 12 -- persistence: a reload sees the same device
{
  const idx = JSON.parse(ev('localStorage').getItem('rmr.runlog.index'));
  const saved = JSON.parse(ev('localStorage').getItem('rmr.runlog.dev.T-1'));
  ok('device persisted in localStorage with its rows', idx.active === 'T-1' && saved && saved.rows.length === log.device.rows.length, idx);
}

console.log(fails ? `\n${fails} check(s) failed` : '\nall checks passed');
process.exit(fails ? 1 : 0);
