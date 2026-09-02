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

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
