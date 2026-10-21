// Drives the shipped spincoater marker handling (issue #47) in either UI.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };

// capture phase + toast instead of touching the DOM
ev('globalThis.__phase = []; globalThis.__toast = []');
ev('spinSetPhase = (s, t) => { globalThis.__phase.push([s, t]); }');
if (ev('typeof showToast') === 'function') ev('showToast = (t, k) => { globalThis.__toast.push([k, t]); }');
const phase = ev('__phase'), toast = ev('__toast');

const feed = line => { phase.length = 0; toast.length = 0; ev('processLine')(line); return { p: [...phase], t: [...toast] }; };
const lastPhase = r => r.p.at(-1) || [null, null];

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);

// 1 -- the substring false-trigger
let r = feed('echo:SPIN STATE:HOME_SETTLE');
ok('STATE:HOME_SETTLE does not claim "Home datum set"',
   !r.p.some(([s, t]) => t === 'Home datum set'), r.p);
ok('STATE:HOME_SETTLE shows a settling phase',
   lastPhase(r)[0] === 'warn', r.p);

// 2 -- the real success marker still works
r = feed('echo:SPIN OK: HOME_SET');
ok('OK: HOME_SET sets the datum phase', lastPhase(r)[1] === 'Home datum set', r.p);

// 3 -- a cycle that finished without homing must not read green
r = feed('echo:SPIN ERR: CYCLE_COMPLETE_NO_HOME — rotor parked off datum, angular registration unverified');
ok('CYCLE_COMPLETE_NO_HOME is an error phase', lastPhase(r)[0] === 'error', r.p);
ok('CYCLE_COMPLETE_NO_HOME never reads "Cycle complete"',
   !r.p.some(([s, t]) => t === 'Cycle complete'), r.p);
ok('CYCLE_COMPLETE_NO_HOME raises no success toast',
   !r.t.some(([k]) => k === 'success'), r.t);

// 4 -- the failure markers the #41/#43 branch adds
for (const [msg, name] of [
  ['ERR: INDEX_INCOMPLETE -- datum not reached', 'INDEX_INCOMPLETE'],
  ['ERR: INDEX_HOME_FAILED',                     'INDEX_HOME_FAILED'],
  ['ERR: HOME_SET_FAILED',                       'HOME_SET_FAILED'],
]) {
  r = feed('echo:SPIN ' + msg);
  ok(`${name} is an error phase`, lastPhase(r)[0] === 'error', r.p);
}
// INDEX_INCOMPLETE must not be mistaken for INDEX_COMPLETE either way round
r = feed('echo:SPIN ERR: INDEX_INCOMPLETE -- datum not reached');
ok('INDEX_INCOMPLETE never reads "Index search done"',
   !r.p.some(([s, t]) => t === 'Index search done'), r.p);

// 5 -- the catch-all: a prose ERR: with no token at all
r = feed('echo:SPIN ERR: ODrive not responding (5s)');
ok('an unmapped ERR: still shows as an error', lastPhase(r)[0] === 'error', r.p);

// 6 -- states added by the #42/#57 branch
for (const [st, name] of [
  ['MEASURE_LINK_LOST', 'MEASURE_LINK_LOST'],
  ['DECEL_LINK_LOST',   'DECEL_LINK_LOST'],
  ['DECEL_STALL',       'DECEL_STALL'],
]) {
  r = feed('echo:SPIN STATE:' + st);
  ok(`STATE:${name} is an error phase`, lastPhase(r)[0] === 'error', r.p);
}

// 7 -- the ordering hazard the old loop had to be hand-sorted around
r = feed('echo:SPIN STATE:INDEX_SETTLE_BOOT');
ok('INDEX_SETTLE_BOOT still maps correctly', lastPhase(r)[1] === 'Settling to index...', r.p);

// 8 -- an unknown state must not leave the old phase on screen
r = feed('echo:SPIN STATE:SOMETHING_NEW');
ok('an unmapped STATE says so', lastPhase(r)[1] === 'State: SOMETHING_NEW', r.p);

// 9 -- the stale Home card after a boot re-datum
el('spinValHome').textContent = '—';
feed('echo:SPIN DATA: InitialPos=3433.00');
ok('DATA: InitialPos updates the Home card',
   el('spinValHome').textContent !== '—', el('spinValHome').textContent);

// The rest of #47: WARN lines, OK: ABORTED, stale stat cards, the Home card,
// dead stateMap keys, ERR console styling. Lines are taken from the firmware
// (spincoater.cpp, M750.cpp) as emitted.
const IS_TOUCH = /Touch/.test(FILE);
const DASH = '—';
const warnRow = () => ({ text: el('spinWarn').textContent, hidden: el('spinWarn').hidden });
const feedAll = lines => lines.map(feed).at(-1);
ev('spinWarnLines = []; spinWarnClosed = false');   // earlier sections left a terminal marker behind

// 10. WARN: shown in the panel, never as the verdict
const BOOT_WARN = 'echo:SPIN WARN: datum established at the index mark on boot -- re-run M751 if layer registration matters';
r = feed(BOOT_WARN);
ok('a WARN: never calls spinSetPhase', r.p.length === 0, r.p);
ok('a WARN: shows in the warning row',
   warnRow().text.includes('datum established at the index mark on boot') && !warnRow().hidden, warnRow());
if (IS_TOUCH) ok('a WARN: raises a warn toast on the Touch page',
   r.t.some(([k, t]) => k === 'warn' && t.includes('datum established')), r.t);
// Boot WARNs arrive before OK: READY and the cycle; they stay with that M750.
r = feedAll(['echo:SPIN OK: READY', 'echo:SPIN OK: Cycle — RPM=1000 DUR=50s RISE=3.00s SINK=3.00s HOME=ON',
             'echo:SPIN STATE:CONNECTING', 'echo:SPIN STATE:RAMP_UP', 'echo:SPIN OK: CYCLE_COMPLETE']);
ok('a WARN leaves the success verdict alone', lastPhase(r)[1] === 'Cycle complete', r.p);
ok('the boot WARN is still shown with that cycle\'s verdict',
   warnRow().text.includes('datum established') && !warnRow().hidden, warnRow());
feed('echo:SPIN TELEM: RPM=0.00 POS=12.38 DEG=0.00');
ok('a TELEM after the verdict does not clear the row', warnRow().text.includes('datum established'), warnRow());
feed('echo:SPIN STATE:HOMING');   // the next command (M752) starts
ok('the next command clears the warning row', warnRow().text === '' && warnRow().hidden, warnRow());
// M750 H1 fallback: OK: HOME_SET and a WARN come before the terminal ERR.
r = feedAll(['echo:SPIN STATE:STOPPED',
             'echo:SPIN WARN: Index homing failed and no datum set — attempting fallback set-home',
             'echo:SPIN DATA: HomePos=12.38', 'echo:SPIN OK: HOME_SET', 'echo:SPIN WARN: Fallback home set OK',
             'echo:SPIN ERR: CYCLE_COMPLETE_NO_HOME — rotor parked off datum, angular registration unverified']);
ok('a WARN leaves the error verdict alone', lastPhase(r)[0] === 'error', r.p);
ok('every WARN of the command is in the row',
   warnRow().text.includes('attempting fallback set-home') && warnRow().text.includes('Fallback home set OK'), warnRow());

// 11. OK: ABORTED (M410) wins over the STATE:STOPPED before it
r = feed('echo:SPIN STATE:STOPPED');
ok('STATE:STOPPED alone reads "Motor stopped"', lastPhase(r)[1] === 'Motor stopped', r.p);
r = feed('echo:SPIN OK: ABORTED');
ok('OK: ABORTED reads "Aborted by operator"', lastPhase(r)[1] === 'Aborted by operator', r.p);
ok('OK: ABORTED is a warn phase, not idle or error', lastPhase(r)[0] === 'warn', r.p);
ok('OK: ABORTED raises no success toast', !r.t.some(([k]) => k === 'success'), r.t);

// 12. stale stat cards: a new cycle (STATE:CONNECTING) blanks the six RPM cards
const STAT_IDS = ['spinValMean', 'spinValStd', 'spinValMin', 'spinValMax', 'spinValRange', 'spinValSamples'];
STAT_IDS.forEach(id => { el(id).textContent = '1009.9'; });
el('spinValVbus').textContent = '24.1';
el('spinValHome').textContent = '136.8';
feed('echo:SPIN STATE:CONNECTING');
ok('STATE:CONNECTING blanks the six RPM stat cards',
   STAT_IDS.every(id => el(id).textContent === DASH), STAT_IDS.map(id => el(id).textContent));
ok('STATE:CONNECTING leaves Vbus and the Home card alone',
   el('spinValVbus').textContent === '24.1' && el('spinValHome').textContent === '136.8',
   [el('spinValVbus').textContent, el('spinValHome').textContent]);
feedAll(['echo:SPIN STATE:MEASURING', 'echo:SPIN ERR: No telemetry samples during measure -- statistics unavailable',
         'echo:SPIN DATA: Samples=0']);
ok('a Samples=0 measure shows 0 samples and no mean',
   String(el('spinValSamples').textContent) === '0' && el('spinValMean').textContent === DASH,   // a real DOM stringifies; the stub keeps the number
   [el('spinValSamples').textContent, el('spinValMean').textContent]);
STAT_IDS.forEach(id => { el(id).textContent = '1009.9'; });
feedAll(['echo:SPIN STATE:CONNECTING', 'echo:SPIN STATE:MEASURING',
         'echo:SPIN ERR: No ODrive telemetry for 3s during measure -- link lost', 'echo:SPIN STATE:MEASURE_LINK_LOST']);
ok('a MEASURE_LINK_LOST abort leaves every stat card blank',
   STAT_IDS.every(id => el(id).textContent === DASH), STAT_IDS.map(id => el(id).textContent));

// 13. the Home card: HomePos turns -> angle within one turn; DegFromHome is gone
for (const [v, want] of [['1281.38', '136.8'], ['-0.25', '270.0'], ['3433.00', '0.0'], ['12.9999', '0.0']]) {
  feed('echo:SPIN DATA: HomePos=' + v);
  ok(`DATA: HomePos=${v} shows ${want} deg`, el('spinValHome').textContent === want, el('spinValHome').textContent);
}
feed('echo:SPIN DATA: InitialPos=10.3757');
ok('DATA: InitialPos uses the same transform', el('spinValHome').textContent === '135.3', el('spinValHome').textContent);
// A boot after a reset: the old datum is gone; with no stable read, boot()
// emits no InitialPos, so the card must stay blank (spincoater.cpp:337-341).
el('spinValHome').textContent = '136.8';
feedAll(['echo:SPIN STATE:BOOTING',
         'echo:SPIN WARN: could not read a consistent initial position -- no datum, run M751 before relying on angles',
         'echo:SPIN OK: READY']);
ok('STATE:BOOTING blanks the Home card until boot() reports a datum',
   el('spinValHome').textContent === DASH, el('spinValHome').textContent);
el('spinValHome').textContent = 'untouched';
feed('echo:SPIN DATA: DegFromHome=12.5');
ok('DegFromHome (never emitted) no longer drives the card', el('spinValHome').textContent === 'untouched',
   el('spinValHome').textContent);

// 14. dead stateMap keys are gone; INDEX_SETTLE_BOOT still maps by longest key
for (const st of ['INDEX_SETTLE', 'INDEX_FOUND_INSTANT']) {
  r = feed('echo:SPIN STATE:' + st);
  ok(`STATE:${st} is no longer a mapped key`, lastPhase(r)[1] === 'State: ' + st, r.p);
}
r = feed('echo:SPIN STATE:INDEX_SETTLE_BOOT');
ok('INDEX_SETTLE_BOOT maps after the dead keys went', lastPhase(r)[1] === 'Settling to index...', r.p);

// 15. ERR: lines get error styling in the console
ev('globalThis.__log = []; logErr = m => __log.push(["err", m]); logRx = m => __log.push(["rx", m])');
const log = ev('__log');
feed('echo:SPIN ERR: Ramp-up timeout — reached 412.00 of 980.00 RPM');
ok('a spincoater ERR: goes to logErr', log.length === 1 && log[0][0] === 'err', log);
log.length = 0;
feed('echo:SPIN STATE:RAMP_UP');
ok('a spincoater STATE: still goes to logRx', log.length === 1 && log[0][0] === 'rx', log);
log.length = 0;
feed(BOOT_WARN);
ok('a spincoater WARN: still goes to logRx', log.length === 1 && log[0][0] === 'rx', log);

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
