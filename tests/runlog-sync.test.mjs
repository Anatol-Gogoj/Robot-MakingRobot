// The Run Log module is one block of code carried by both UIs. This check fails
// when the two copies drift (run `python tools/sync_runlog.py` to fix) and when a
// page lost its glue: the tab, the containers, or the Touch tab-order coupling.
import { readFileSync } from 'fs';

const [CONTROLLER, TOUCH] = process.argv.slice(2);
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };
const BLOCK = /<!-- RMR-RUNLOG:BEGIN -->[\s\S]*?<!-- RMR-RUNLOG:END -->/g;

const c = readFileSync(CONTROLLER, 'utf8'), t = readFileSync(TOUCH, 'utf8');
const cb = c.match(BLOCK) || [], tb = t.match(BLOCK) || [];
ok('Controller carries exactly one RMR-RUNLOG block', cb.length === 1, cb.length);
ok('Touch carries exactly one RMR-RUNLOG block', tb.length === 1, tb.length);
ok('the two blocks are byte-identical', cb[0] === tb[0]);
ok('the block defines rmrLog once', (cb[0] || '').split('const rmrLog = ').length === 2);

for (const [name, html] of [['Controller', c], ['Touch', t]]) {
  const count = (re) => (html.match(re) || []).length;
  ok(`${name}: one #rlRoot and one #rlStrip`, count(/id="rlRoot"/g) === 1 && count(/id="rlStrip"/g) === 1);
  ok(`${name}: rmrLogHost declared once`, count(/window\.rmrLogHost = \{/g) === 1);
  ok(`${name}: every sequencer hook present`, ['dispense', 'spin.start', 'spin.done', 'uv.on', 'uv.off', 'stamp.press', 'cycle.begin', 'run.begin', 'seq.fault', 'seq.stop', 'estop'].every(k => html.includes(`rlEvent('${k}'`)),
     ['dispense', 'spin.start', 'spin.done', 'uv.on', 'uv.off', 'stamp.press', 'cycle.begin', 'run.begin', 'seq.fault', 'seq.stop', 'estop'].filter(k => !html.includes(`rlEvent('${k}'`)));
  ok(`${name}: processLine observes lines (rlRx)`, /homedTrackRx\(line\);\s*\n\s*rlRx\(line\);/.test(html));
  ok(`${name}: the block sits after the main script`, html.indexOf('window.rmrLogHost = {') < html.indexOf('<!-- RMR-RUNLOG:BEGIN -->'));
}

// Touch: switchTab matches buttons by index, so tabNames must list the buttons in DOM order.
{
  const btns = [...t.matchAll(/<button class="tab-btn[^"]*" onclick="switchTab\('([a-z]+)'\)"/g)].map(m => m[1]);
  const names = (t.match(/const tabNames = \[([^\]]*)\]/) || ['', ''])[1].split(',').map(s => s.trim().replace(/['"]/g, '')).filter(Boolean);
  ok('Touch: tabNames matches the tab buttons in order (log included)', JSON.stringify(btns) === JSON.stringify(names) && names.includes('log'), { btns, names });
  ok('Touch: a #tab-log page exists', /id="tab-log"/.test(t));
}
ok('Controller: Run Log tab button + page exist', /id="tabbtn-runlog"/.test(c) && /id="tab-runlog"/.test(c));
for (const [name, html] of [['Controller', c], ['Touch', t]]) {
  const open = ['homing', 'syringe', 'spin', 'uv', 'stamp'].filter(b => new RegExp('<details class="seq-block" id="seqBlock-' + b + '" open>').test(html));
  ok(`${name}: all five sequencer cards open by default`, open.length === 5, open);
}

console.log(fails ? `\n${fails} check(s) failed` : '\nall checks passed');
process.exit(fails ? 1 : 0);
