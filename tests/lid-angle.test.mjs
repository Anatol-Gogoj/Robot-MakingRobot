// The spincoater moved, and its swing-out lid now has to travel to 115 deg to close over it
// (commit 76239bd set the sequencer default). Every lid-close path a UI offers has to agree,
// or a manual Close button parks the lid short of the spincoater while the UV block closes it
// properly: the Manual-tab slider + Close preset (Controller), the Lid CLOSE FAB and the
// long-press servo sheet (Touch), the UV block's default, and the built-in presets that
// rewrite the sequencer fields. The raw override stays 0-180 in both.
//
// The last check documents today's failure mode: the firmware's lid interlock refuses
// M42 P4 S1 with the lid open, and the UV block must surface that instead of counting a cure.
import { readFileSync } from 'fs';
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
const html = readFileSync(FILE, 'utf8');
const IS_TOUCH = /RMR_Touch\.html$/.test(FILE);
const LID_CLOSED = 115, LID_OPEN = 30, LID_MS = 800;
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
ev('isConnected = true');
ev('globalThis.__sent = []');
ev('writer = { write: async (b) => { globalThis.__sent.push(new TextDecoder().decode(b).trim()); } }');
const sent = ev('__sent');

// drive an async block: feed one 'ok' per pending command until it settles.
// `inject(cmd)` may return a firmware line to deliver BEFORE that command's ok (once per command).
async function drive(fnName, inject) {
  sent.length = 0;
  const injected = new Set();
  let done = false, err = null;
  ev(fnName)().then(() => { done = true; }, e => { done = true; err = e; });
  for (let i = 0; i < 800 && !done; i++) {
    await sleep(5);
    const last = sent[sent.length - 1];
    if (inject && last && !injected.has(last)) { const line = inject(last); if (line) { injected.add(last); ev('processLine')(line); } }
    ev('processLine')('ok');
  }
  await sleep(5);
  return { done, err, cmds: [...sent] };
}

// 1 -- the UV block's defaults
ok(`UV block defaults: lid closed ${LID_CLOSED}, open ${LID_OPEN}, lid managed`,
   +el('uvLidClose').value === LID_CLOSED && +el('uvLidOpen').value === LID_OPEN && el('uvLid').checked === true,
   [el('uvLidClose').value, el('uvLidOpen').value, el('uvLid').checked]);
ok('built-in presets rewrite the field with the same closed angle (a stale preset would silently reset it)',
   (html.match(/uvLidClose: 115\b/g) || []).length >= 1 && !/uvLidClose: 11[0-4]\b/.test(html),
   html.match(/uvLidClose: \d+/g));

// 2 -- the UV block closes to 115, cures, and reopens to 30
el('uvTime').value = '0.02';                       // browser-timed cure, keep the run short
el('uvSpinHome').checked = false; el('uvArgon').checked = false;
{
  const r = await drive('runUvBlock');
  ok('UV block completed', r.done && !r.err, r.err && r.err.message);
  ok(`UV block: M400 · close to ${LID_CLOSED} (T ramp) · UV on · UV off · reopen to ${LID_OPEN}`,
     JSON.stringify(r.cmds) === JSON.stringify(['M400', `M280 P1 S${LID_CLOSED} T${LID_MS}`, 'M42 P4 S1', 'M42 P4 S0', `M280 P1 S${LID_OPEN} T${LID_MS}`]),
     r.cmds);
}

// 3 -- the manual lid controls reach the same angle
if (IS_TOUCH) {
  const cfg = ev('servoConfig')[1];
  ok(`Touch servoConfig lid: range ${LID_OPEN}-${LID_CLOSED}, open ${LID_OPEN}, close ${LID_CLOSED}`,
     cfg.min === LID_OPEN && cfg.max === LID_CLOSED && cfg.openVal === LID_OPEN && cfg.closeVal === LID_CLOSED, cfg);
  sent.length = 0; ev('lidClose')();
  ok(`Lid CLOSE FAB sends M280 P1 S${LID_CLOSED} with the T ramp`, sent[0] === `M280 P1 S${LID_CLOSED} T${LID_MS}`, sent);
  sent.length = 0; ev('lidOpen')();
  ok(`Lid OPEN FAB sends M280 P1 S${LID_OPEN}`, sent[0] === `M280 P1 S${LID_OPEN} T${LID_MS}`, sent);
  ev('openServoSheet')(1);
  ok(`long-press servo sheet: slider spans ${LID_OPEN}-${LID_CLOSED} for the lid`,
     +el('servoSheetSlider').min === LID_OPEN && +el('servoSheetSlider').max === LID_CLOSED, [el('servoSheetSlider').min, el('servoSheetSlider').max]);
  sent.length = 0; ev('servoSheetPreset')('close');
  ok(`servo sheet Close preset sends S${LID_CLOSED}`, sent[0] === `M280 P1 S${LID_CLOSED} T${LID_MS}` && +el('servoSheetSlider').value === LID_CLOSED, sent);
  ok('default lid position matches the closed angle', ev('servoPositions')[1] === LID_CLOSED, ev('servoPositions'));
} else {
  ok(`Manual-tab lid slider spans ${LID_OPEN}-${LID_CLOSED} and starts closed`,
     +el('servo1').min === LID_OPEN && +el('servo1').max === LID_CLOSED && +el('servo1').value === LID_CLOSED, [el('servo1').min, el('servo1').max, el('servo1').value]);
  const closeBtn = new RegExp(`getElementById\\('servo1'\\)\\.value=${LID_CLOSED};[^"]*setServo\\(1\\)">Close<`);
  const openBtn = new RegExp(`getElementById\\('servo1'\\)\\.value=${LID_OPEN};[^"]*setServo\\(1\\)">Open<`);
  ok(`Close / Open quick buttons set ${LID_CLOSED} / ${LID_OPEN} before sending`, closeBtn.test(html) && openBtn.test(html));
  el('servo1').value = el('servo1').max; sent.length = 0; ev('setServo')(1);
  ok(`slider at its max sends M280 P1 S${LID_CLOSED} with the T ramp`, sent[0] === `M280 P1 S${LID_CLOSED} T${LID_MS}`, sent);
}
ok('raw override textbox still allows the full 0-180 servo range',
   +el('servo1Override').min === 0 && +el('servo1Override').max === 180, [el('servo1Override').min, el('servo1Override').max]);

// 4 -- the firmware lid interlock: a refused M42 P4 S1 fails the block, no cure is counted, the lamp is never "on"
{
  const r = await drive('runUvBlock', cmd => (cmd === 'M42 P4 S1' ? 'echo:UV inhibited: lid open (interlock)' : null));
  ok('UV block fails with the interlock message when the firmware refuses UV-on',
     r.done && r.err && /lid interlock refused UV/.test(r.err.message), r.err && r.err.message);
  ok('after the refusal: nothing else is sent (no UV-off, no reopen) and the lid stays closed',
     JSON.stringify(r.cmds) === JSON.stringify(['M400', `M280 P1 S${LID_CLOSED} T${LID_MS}`, 'M42 P4 S1']), r.cmds);
}

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
