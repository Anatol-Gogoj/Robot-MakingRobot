// Drives the Stamp block in either UI. The filter feeder (Marlin's I axis, letter A) homes to MAX, so
// an advance is a relative A- move (A+ is clamped at the max soft endstop and never moves); it happens
// once per pick in left-/right-only mode and once per L+R pair when alternating (one shared carriage
// lifts both stacks). The gripper opens only after an M400 with the arm over the pick, and the lift-Z
// guard refuses a post-press lift at or below the press / approach depth before anything is sent.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el, document } = loadUI(FILE);
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
ev('isConnected = true');
ev('globalThis.__sent = []');
ev('writer = { write: async (b) => { globalThis.__sent.push(new TextDecoder().decode(b).trim()); } }');
const sent = ev('__sent');

// drive an async block: feed one 'ok' per pending command until it settles (the dispose step has a fixed 500 ms browser-side sleep)
async function drive(fnName, ...args) {
  sent.length = 0;
  let done = false, err = null;
  ev(fnName)(...args).then(() => { done = true; }, e => { done = true; err = e; });
  for (let i = 0; i < 800 && !done; i++) { await sleep(5); ev('processLine')('ok'); }
  await sleep(5);
  return { done, err, cmds: [...sent] };
}
const setSide = v => { document.querySelector('input[name="stampSide"][value="' + v + '"]').checked = true; };
const feedLines = cmds => cmds.filter(c => /^G1 A/.test(c));

// no dwells, so a run settles inside the drive budget
el('stampGrabDelay').value = '0'; el('stampHold').value = '0';

// 1 -- defaults
ok('defaults: stack 4 mm, press Z155, approach Z150, lift Z75, alternating',
   el('stampStack').value == 4 && el('stampForce').value == 155 && el('stApproachZ').value == 150 && el('stampLiftZ').value == 75 && document.querySelector('input[name="stampSide"]:checked').value === 'alt',
   [el('stampStack').value, el('stampForce').value, el('stApproachZ').value, el('stampLiftZ').value]);

// 2 -- left only: exact order, and the feeder advances A- on every pick
setSide('left');
{
  const r = await drive('runStampBlock');
  ok('left-only run completed', r.done && !r.err, r.err && r.err.message);
  const head = ['G90', 'M400', 'G1 Z0 F3000', 'G1 X607 F24000', 'G1 Y143 F24000', 'M400', 'M280 P0 S170',
                'G91', 'G1 A-4.000 F2000', 'G90', 'M400', 'G1 Z41 F3000', 'M400', 'M280 P0 S90',
                'G1 Z0 F3000', 'G1 Y0 F24000', 'G1 X122.3 F24000', 'G1 Y27.3 F24000', 'G1 Z150 F3000', 'G1 Z155 F300', 'M400',
                'G90', 'G1 Z75.000 F3000', 'G1 Y0 F24000', 'G1 Z0 F3000'];
  ok('exact order through the retreat: travel · M400 · open · feed A- · descend · grab · transit · press · 3-step retreat',
     JSON.stringify(r.cmds.slice(0, head.length)) === JSON.stringify(head), r.cmds);
  const tail = r.cmds.slice(head.length).filter(c => c !== 'G1 Y0 F24000');   // the Controller repeats a Y0 the retreat already made true
  ok('dispose tail: X to the bin · down · M400 · open · up',
     JSON.stringify(tail) === JSON.stringify(['G1 X674 F24000', 'G1 Z15 F3000', 'M400', 'M280 P0 S170', 'G1 Z0 F3000']), tail);
  ok('the feeder advances toward MIN (A-), never A+', feedLines(r.cmds).length === 1 && feedLines(r.cmds)[0] === 'G1 A-4.000 F2000', feedLines(r.cmds));
  const iOpen = r.cmds.indexOf('M280 P0 S170');
  ok('the gripper opens only after the arm is over the pick, with an M400 first',
     iOpen === r.cmds.indexOf('G1 Y143 F24000') + 2 && r.cmds[iOpen - 1] === 'M400', r.cmds.slice(0, 8));
}
{
  const r = await drive('runStampBlock');
  ok('left-only: the next pick advances the feeder again', feedLines(r.cmds).length === 1 && feedLines(r.cmds)[0] === 'G1 A-4.000 F2000', feedLines(r.cmds));
}

// 3 -- right only: the right pick point, and the feeder advances every pick
setSide('right');
{
  const r = await drive('runStampBlock');
  ok('right-only picks at the right feeder and advances A-',
     r.done && !r.err && r.cmds.includes('G1 X747 F24000') && r.cmds.includes('G1 Z43 F3000') && JSON.stringify(feedLines(r.cmds)) === JSON.stringify(['G1 A-4.000 F2000']),
     r.err ? r.err.message : r.cmds.slice(0, 12));
}

// 4 -- alternating: one shared carriage lifts both stacks, so advance once per L+R pair
setSide('alt');
ev('stampAltNext = "left"; stampAltPick = 0');
{
  const r1 = await drive('runStampBlock');
  ok('alternating pick 1 (L): no feeder advance yet', r1.done && !r1.err && r1.cmds.includes('G1 X607 F24000') && feedLines(r1.cmds).length === 0, r1.err ? r1.err.message : feedLines(r1.cmds));
  const r2 = await drive('runStampBlock');
  ok('alternating pick 2 (R): the pair is complete, advance once', r2.cmds.includes('G1 X747 F24000') && JSON.stringify(feedLines(r2.cmds)) === JSON.stringify(['G1 A-4.000 F2000']), feedLines(r2.cmds));
  const r3 = await drive('runStampBlock');
  const r4 = await drive('runStampBlock');
  ok('alternating picks 3 + 4: again one advance per pair', feedLines(r3.cmds).length === 0 && feedLines(r4.cmds).length === 1, [feedLines(r3.cmds), feedLines(r4.cmds)]);
  ok('next-pick indicator is back to Left', el('stampNext').textContent === 'Left', el('stampNext').textContent);
}

// 5 -- stack 0: no relative block at all
setSide('left'); el('stampStack').value = '0';
{
  const r = await drive('runStampBlock');
  ok('stack 0 sends no G91 / A / G90', r.done && !r.err && !r.cmds.includes('G91') && feedLines(r.cmds).length === 0, r.err ? r.err.message : r.cmds);
}
el('stampStack').value = '4';

// 6 -- the lift-Z guard refuses before anything is sent (numv ignores the input's max)
setSide('alt');
const altBefore = ev('stampAltNext');
el('stampLiftZ').value = '175';   // a typo for 75: at or below the press it would drive Z deeper at the fast feed
{
  const r = await drive('runStampBlock');
  ok('lift Z below the press is refused with nothing sent', r.err && /lift Z/.test(r.err.message) && r.cmds.length === 0, [r.err && r.err.message, r.cmds]);
  ok('a refused run does not consume the alternating side', ev('stampAltNext') === altBefore && ev('stampAltPick') === 0, [ev('stampAltNext'), ev('stampAltPick')]);
}
el('stampLiftZ').value = '155';   // equal to the press depth
{ const r = await drive('runStampBlock'); ok('lift Z equal to the press is refused', r.err && /press Z/.test(r.err.message) && r.cmds.length === 0, r.err && r.err.message); }
el('stampLiftZ').value = '150';   // equal to the approach
{ const r = await drive('runStampBlock'); ok('lift Z equal to the approach is refused', r.err && /approach Z/.test(r.err.message) && r.cmds.length === 0, r.err && r.err.message); }
el('stampLiftZ').value = '149';
setSide('left');
{ const r = await drive('runStampBlock'); ok('lift Z just above the approach runs and lifts to it', r.done && !r.err && r.cmds.includes('G1 Z149.000 F3000'), r.err ? r.err.message : r.cmds); }
el('stampLiftZ').value = '75';

// 7 -- filter feeder jog: Advance is A- (toward MIN, the stack rises), Retract is A+; locked until homed, refused while running
const hasJog = ev('typeof feederJog') === 'function';
ok('feeder jog helper and its inputs are on the page', hasJog && el('feedJogMm').value == 4 && el('feedJogFeed').value == 2000, [hasJog, el('feedJogMm').value, el('feedJogFeed').value]);
if (hasJog) {
  const jog = async dir => { sent.length = 0; ev('feederJog')(dir); await sleep(10); return [...sent]; };
  ev('seqHomed = false');
  ok('feeder jog is locked until all axes are homed', (await jog(1)).length === 0, sent);
  ev('seqHomed = true');
  ok('Advance jogs A- by the jog amount at the jog feed', JSON.stringify(await jog(1)) === JSON.stringify(['G91', 'G1 A-4.000 F2000', 'G90']), sent);
  el('feedJogMm').value = '2.5'; el('feedJogFeed').value = '1000';
  ok('Retract jogs A+ (toward the MAX home)', JSON.stringify(await jog(-1)) === JSON.stringify(['G91', 'G1 A2.500 F1000', 'G90']), sent);
  ev('seqRunning = true');
  ok('feeder jog is refused while a sequence runs', (await jog(1)).length === 0, sent);
  ev('seqRunning = false');
  el('feedJogMm').value = '4'; el('feedJogFeed').value = '2000';
}

console.log(fails ? `\n${fails} check(s) failed` : '\nall checks passed');
process.exit(fails ? 1 : 0);
