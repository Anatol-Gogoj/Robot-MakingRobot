// Drives the shipped RMR_SegmentRunner.html (issue #62) under a stub DOM.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
let fails = 0, total = 0;
const ok = (n, c, got) => {
  total++;
  console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '   [got ' + JSON.stringify(got) + ']'));
  if (!c) fails++;
};
const head = t => console.log('\n' + t);
const flush = () => new Promise(r => setTimeout(r, 0));

function boot(src, opts) {
  const connected = !opts || opts.connected !== false;
  const u = loadUI(FILE);
  u.wire = u.ev('globalThis.__wire = []');
  u.ev('writer = { write: async b => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); } }');
  if (connected) { u.ev('isConnected = true'); u.ev('identityOk = true'); }
  u.el('src').value = src;
  u.ev('parseProgram')();
  u.rx = l => u.ev('processLine')(l);
  u.last = () => u.wire.at(-1);
  // Only lines the runner itself sent: M115 is the identity probe, M114 is
  // foreign traffic a test injects on purpose.
  u.progWire = () => [...u.wire].filter(c => c !== 'M115' && c !== 'M114');
  return u;
}
const errs = u => u.ev('program.errors');
const warns = u => u.ev('program.warnings');

// ════════════════════════════════════════════════════════════════════════
head('A  Load-time validation - an undeclared placeholder must not be a run-time surprise');

let u = boot([';SEGMENT: a', 'M750 S{nope} D10'].join('\n'));
ok('undeclared placeholder is an error', errs(u).some(e => /\{nope\} is not declared/.test(e)), errs(u));
ok('nothing is runnable after a parse error', u.ev('plan').length === 0, u.ev('plan').length);

u = boot([';PARAM: x label="X" default=5 min=1', ';SEGMENT: a', 'G4 S{x}'].join('\n'));
ok('a parameter without max is an error', errs(u).some(e => /missing max/.test(e)), errs(u));

u = boot([';PARAM: x default=5 min=1 max=3', ';SEGMENT: a', 'G4 S{x}'].join('\n'));
ok('default outside min..max is an error', errs(u).some(e => /outside 1\.\.3/.test(e)), errs(u));

u = boot([';PARAM: x default=1 min=1 max=3', ';PARAM: x default=2 min=1 max=3', ';SEGMENT: a', 'G4 S{x}'].join('\n'));
ok('a duplicate parameter is an error', errs(u).some(e => /declared twice/.test(e)), errs(u));

u = boot([';LAYER-SEGMENT: a', 'G4 S1', ';SEGMENT: mid', 'G4 S1', ';LAYER-SEGMENT: b', 'G4 S1'].join('\n'));
ok('non-contiguous layer segments are an error', errs(u).some(e => /not contiguous/.test(e)), errs(u));

u = boot([';SEGMENT: a', 'G1 X{ Y10'].join('\n'));
ok('a stray brace is an error', errs(u).some(e => /stray/.test(e)), errs(u));

u = boot([';PARAM: unused default=1 min=0 max=2', ';SEGMENT: a', 'G4 S1'].join('\n'));
ok('a declared-but-unused parameter warns', warns(u).some(w => /never used/.test(w)), warns(u));
ok('...but still runs', u.ev('plan').length === 1, u.ev('plan').length);

// ════════════════════════════════════════════════════════════════════════
head('B  Substitution - global, per-layer, and the bounds that make it worth having');

const PROG = [
  ';PARAM: rpm  label="RPM"  default=1000 min=100 max=5000 unit=RPM scope=layer',
  ';PARAM: push label="Push" default=6    min=0.5 max=20   unit=mm',
  ';SEGMENT: Home',
  ';PROVIDES: homed',
  'G28',
  ';LAYER-SEGMENT: Spin',
  ';REQUIRES: homed',
  'G1 E-{push} F300',
  'M750 S{rpm} D10 A3 C3 H1',
  ';SEGMENT: Park',
  ';REQUIRES: homed',
  'G1 Z0 F3000',
].join('\n');

u = boot(PROG);
ok('parses cleanly', errs(u).length === 0, errs(u));
u.el('layerCount').value = '2';
u.ev('onLayerCountChange')();
ok('two layers expand to 4 steps', u.ev('plan').length === 4, u.ev('plan').map(s => s.seg.name));

ok('global default substitutes', u.ev('substitute')('G1 E-{push} F300', null) === 'G1 E-6 F300',
   u.ev('substitute')('G1 E-{push} F300', null));
ok('a layer param falls back to global when its cell is blank',
   u.ev('substitute')('M750 S{rpm}', 2) === 'M750 S1000', u.ev('substitute')('M750 S{rpm}', 2));
u.el('lp_rpm_2').value = '3000';
ok('a filled layer cell overrides the global', u.ev('substitute')('M750 S{rpm}', 2) === 'M750 S3000',
   u.ev('substitute')('M750 S{rpm}', 2));
ok('layer 1 is unaffected by layer 2 cell', u.ev('substitute')('M750 S{rpm}', 1) === 'M750 S1000',
   u.ev('substitute')('M750 S{rpm}', 1));

u.el('gp_push').value = '99';                       // above max=20
let threw = false;
try { u.ev('substitute')('G1 E-{push}', null); } catch (e) { threw = /outside its declared range/.test(e.message); }
ok('an out-of-bounds value is refused at send time', threw, threw);
u.el('gp_push').value = 'abc';
threw = false;
try { u.ev('substitute')('G1 E-{push}', null); } catch (e) { threw = /is not a number/.test(e.message); }
ok('a non-numeric value is refused at send time', threw, threw);

// ════════════════════════════════════════════════════════════════════════
head('C  Execution - one line per attributed ok');

u = boot(PROG);
u.ev('runAll')();
await flush();
ok('run started, first line sent', u.last() === 'G28', u.progWire());
ok('exactly one line in flight', u.progWire().length === 1, u.progWire());

for (let i = 0; i < 4; i++) u.ev('sendCmd')('M114');   // foreign traffic
await flush();
u.rx('ok');                                            // G28's own ok is first in line
await flush();
ok('the segment closed on its own ok', u.ev('runState') === 'segPause', u.ev('runState'));
for (let i = 0; i < 4; i++) u.rx('ok');                // the four foreign oks
await flush();
ok('foreign oks did not advance anything', u.ev('runState') === 'segPause' && u.progWire().length === 1,
   { state: u.ev('runState'), wire: u.progWire() });

// ════════════════════════════════════════════════════════════════════════
head('D  Pause after each segment - the default, and Continue');

u = boot(PROG);
ok('pause-after-segment defaults to on', u.el('pauseEachSeg').checked === true);
u.ev('runAll')();
await flush();
u.rx('ok');
await flush();
ok('halted between segments', u.ev('runState') === 'segPause', u.ev('runState'));
ok('no further line was sent', u.progWire().length === 1, u.progWire());
ok('segment 1 marked done', u.ev('plan')[0].status === 'done', u.ev('plan')[0].status);
u.ev('continueRun')();
await flush();
ok('Continue sends the next segment first line', u.last() === 'G1 E-6 F300', u.progWire());

// ════════════════════════════════════════════════════════════════════════
head('E  An ERR: from the spincoater must fail the segment, not be walked past');

u = boot(PROG);
u.el('pauseEachSeg').checked = false;
u.ev('runAll')();
await flush();
u.rx('ok'); await flush();                    // G28
u.rx('ok'); await flush();                    // G1 E-6
ok('reached the M750 line', String(u.last()).startsWith('M750'), u.progWire());
u.rx('echo:SPIN ERR: CYCLE_COMPLETE_NO_HOME - rotor parked off datum');
u.rx('ok');                                   // Marlin still answers ok for the parsed line
await flush();
ok('the run halted', u.ev('runState') === 'failed', u.ev('runState'));
ok('the segment is marked failed', u.ev('plan').some(s => s.status === 'failed'), u.ev('plan').map(s => s.status));
const wireAtFail = u.progWire().length;
u.rx('ok'); await flush();
ok('no line is sent after a failure', u.progWire().length === wireAtFail, u.progWire());

u = boot(PROG);
u.el('pauseEachSeg').checked = false;
u.ev('runAll')(); await flush();
u.rx('Error:Printer halted. kill() called!');
u.rx('ok'); await flush();
ok('a Marlin Error: also halts the run', u.ev('runState') === 'failed', u.ev('runState'));

// ════════════════════════════════════════════════════════════════════════
head('F  Run This Segment Only / Re-run Last / Pause mid-segment');

u = boot(PROG);
u.el('pauseEachSeg').checked = false;
u.ev('selectedStep = 1');                     // the layer Spin segment
u.ev('confirm = () => true');                 // its ;REQUIRES: homed is unmet
u.ev('runSelectedOnly')();
await flush();
u.rx('ok'); await flush();                    // G1 E-6
u.rx('ok'); await flush();                    // M750
ok('a single-segment run stops at its own end', u.ev('runState') === 'done', u.ev('runState'));
ok('it sent exactly that segment two lines', u.progWire().length === 2, u.progWire());

u.ev('rerunLast')();
await flush();
ok('Re-run Last restarts the same segment', u.last() === 'G1 E-6 F300', u.progWire());
u.ev('togglePause')();
ok('pause is requested', u.ev('runState') === 'paused', u.ev('runState'));
const atPause = u.progWire().length;
u.ev('togglePause')();                        // resume while the ok is still outstanding
await flush();
ok('resume sends nothing while an ok is outstanding', u.progWire().length === atPause, u.progWire());
u.rx('ok'); await flush();
ok('the outstanding ok then advances', u.progWire().length === atPause + 1, u.progWire());

// ════════════════════════════════════════════════════════════════════════
head('G  Guards');

u = boot(PROG);
u.rx('echo:SPIN DATA: HomePos=20000.00');
ok('the accumulator readout tracks HomePos', u.ev('accumTurns') === 20000, u.ev('accumTurns'));
u.ev('runAll')();
await flush();
ok('a run is refused above the block threshold', u.ev('runState') === 'idle' && u.progWire().length === 0,
   { state: u.ev('runState'), wire: u.progWire() });

u = boot(PROG);
u.rx('echo:SPIN DATA: HomePos=9000.00');
u.ev('confirm = () => false');
u.ev('runAll')();
await flush();
ok('above the warn threshold it asks, and a refusal stops the run', u.progWire().length === 0, u.progWire());

u = boot(PROG);
u.ev('selectedStep = 1');                     // needs `homed`, never provided
u.ev('confirm = () => false');
u.ev('runFromSelected')();
await flush();
ok('an unmet ;REQUIRES: is refused when the operator declines', u.progWire().length === 0, u.progWire());
u.ev('confirm = () => true');
u.ev('runFromSelected')();
await flush();
ok('...and proceeds when they accept', u.progWire().length === 1, u.progWire());

u = boot([';SEGMENT: a', 'G28', ';SEGMENT: b', 'M751', 'G4 S1'].join('\n'));
u.ev('selectedStep = 1');
u.ev('confirm = (m) => { globalThis.__asked = /M751/.test(m); return false; }');
u.ev('runFromSelected')();
await flush();
ok('a partial run containing M751 warns before redefining the datum', u.ev('__asked') === true, u.ev('__asked'));

u.ev('confirm = () => { globalThis.__asked2 = true; return true; }');
u.ev('runAll')();
await flush();
ok('a run from the top does not warn about M751', u.ev('typeof __asked2') === 'undefined', u.ev('typeof __asked2'));

// ════════════════════════════════════════════════════════════════════════
head('H  Preview and E-stop');

u = boot(PROG);
u.el('layerCount').value = '2';
u.ev('onLayerCountChange')();
u.el('lp_rpm_2').value = '2500';
u.ev('renderPreview')();
const pv = u.el('preview').textContent;
ok('preview substitutes per layer', /M750 S1000 D10/.test(pv) && /M750 S2500 D10/.test(pv), pv.slice(0, 400));
ok('preview shows the original alongside', /\(was: M750 S\{rpm\}/.test(pv), pv.slice(0, 400));
ok('preview sends nothing', u.progWire().length === 0, u.progWire());

u = boot(PROG);
u.ev('runAll')(); await flush();
u.ev('emergencyStop')();
await flush();
ok('E-stop sent M112', u.wire.includes('M112'), u.wire);
ok('E-stop halts the run', u.ev('runState') === 'failed', u.ev('runState'));
ok('E-stop clears the ledger', u.ev('okLedger').length === 0, u.ev('okLedger').length);
u.rx('ok'); await flush();
ok('no line is sent after an E-stop', u.wire.at(-1) === 'M112', u.wire);

// ════════════════════════════════════════════════════════════════════════
head('I  Session-only split and merge');

u = boot(PROG);
const before = u.ev('program.segments').length;
u.ev('splitSegment')(u.ev('program.segments')[1], 1);
ok('split adds a segment', u.ev('program.segments').length === before + 1, u.ev('program.segments').map(s => s.name));
ok('the split parts are marked session-only',
   u.ev('program.segments').filter(s => !s.fromFile).length === 2,
   u.ev('program.segments').map(s => s.name + ':' + s.fromFile));
u.ev('parseProgram')();
ok('re-parsing restores the file markers',
   u.ev('program.segments').length === before && u.ev('program.segments').every(s => s.fromFile),
   u.ev('program.segments').map(s => s.name));

// Merging a non-layer segment into the layer block would make the prelude repeat
// once per layer, so it must be refused.
u.ev('mergeSegment')(u.ev('program.segments')[0]);   // "Home" (plain) into "Spin" (layer)
ok('merging across the layer boundary is refused',
   u.ev('program.segments').length === before, u.ev('program.segments').map(s => s.name));

const u2 = boot([';SEGMENT: a', 'G28', ';SEGMENT: b', 'G4 S1', 'G4 S2'].join('\n'));
u2.ev('mergeSegment')(u2.ev('program.segments')[0]);
ok('two plain segments merge', u2.ev('program.segments').length === 1, u2.ev('program.segments').map(s => s.name));
ok('the merged segment holds both segments lines', u2.ev('program.segments')[0].lines.length === 3,
   u2.ev('program.segments')[0].lines.map(l => l.code));
ok('the merged segment is marked session-only', u2.ev('program.segments')[0].fromFile === false,
   u2.ev('program.segments')[0].fromFile);

// ════════════════════════════════════════════════════════════════════════
head('J  The plan cannot be rebuilt out from under a run');

u = boot(PROG);
u.el('layerCount').value = '2';
u.ev('onLayerCountChange')();
u.ev('runAll')();
await flush();
const planBefore = u.ev('plan').length;
u.el('layerCount').value = '5';
u.ev('onLayerCountChange')();
ok('layer count is refused mid-run', u.ev('plan').length === planBefore, u.ev('plan').length);
ok('...and the input is put back', u.el('layerCount').value === '2', u.el('layerCount').value);

u.el('src').value = [';SEGMENT: totally different', 'G4 S1'].join('\n');
u.ev('parseProgram')();
ok('re-parsing is refused mid-run', u.ev('plan').length === planBefore, u.ev('plan').length);
ok('the running segment still exists', u.ev('plan')[u.ev('planIdx')] !== undefined, u.ev('planIdx'));

// after a Stop, both are allowed again
u.ev('emergencyStop')();
u.el('layerCount').value = '3';
u.ev('onLayerCountChange')();
ok('layer count works again once the run has ended', u.ev('planLayerCount') === 3, u.ev('planLayerCount'));

console.log(fails ? '\n' + fails + '/' + total + ' FAILED' : '\nall ' + total + ' passed');
process.exit(fails ? 1 : 0);
