// Runs every UI check against the HTML files in the repo root.
//
//   node tests/run.mjs
//
// A check whose target file is not on this branch is skipped, not failed.
//
// Running this on `main` is EXPECTED to report failures. The checks assert the
// fixed behaviour, so on an unfixed branch they are the reproductions. See
// tests/README.md.
import { existsSync } from 'fs';
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join, basename } from 'path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const f = name => join(root, name);

const CONTROLLER = f('RMR_Controller.html');
const TOUCH = f('RMR_Touch.html');

const checks = [
  { issue: '—',   name: 'syntax: RMR_Controller.html',  script: 'syntax-check.mjs',                 args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '—',   name: 'syntax: RMR_Touch.html',       script: 'syntax-check.mjs',                 args: [TOUCH],      needs: [TOUCH] },
  { issue: '#48', name: 'ok attribution: Controller',   script: 'ok-attribution.test.mjs',          args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '#48', name: 'ok attribution: Touch',        script: 'ok-attribution.test.mjs',          args: [TOUCH],      needs: [TOUCH] },
  { issue: '#48', name: 'homing indicator: Touch',      script: 'homing-indicator.test.mjs',        args: [TOUCH],      needs: [TOUCH] },
  { issue: '#47', name: 'spin markers: Controller',     script: 'spin-markers.test.mjs',            args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '#47', name: 'spin markers: Touch',          script: 'spin-markers.test.mjs',            args: [TOUCH],      needs: [TOUCH] },
  { issue: '—',   name: 'run log: Controller',          script: 'runlog.test.mjs',                  args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '—',   name: 'run log: Touch',               script: 'runlog.test.mjs',                  args: [TOUCH],      needs: [TOUCH] },
  { issue: '—',   name: 'run log: shared block in sync', script: 'runlog-sync.test.mjs',             args: [CONTROLLER, TOUCH], needs: [CONTROLLER, TOUCH] },
  { issue: '—',   name: 'syringe dose: Controller',      script: 'syringe-dose.test.mjs',            args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '—',   name: 'syringe dose: Touch',           script: 'syringe-dose.test.mjs',            args: [TOUCH],      needs: [TOUCH] },
  { issue: '—',   name: 'stamp block: Controller',       script: 'stamp-block.test.mjs',             args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '—',   name: 'stamp block: Touch',            script: 'stamp-block.test.mjs',             args: [TOUCH],      needs: [TOUCH] },
  { issue: '—',   name: 'lid angle: Controller',         script: 'lid-angle.test.mjs',               args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '—',   name: 'lid angle: Touch',              script: 'lid-angle.test.mjs',               args: [TOUCH],      needs: [TOUCH] },
  { issue: '—',   name: 'UV refusal feedback: Controller', script: 'uv-refusal-feedback.test.mjs',   args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '—',   name: 'UV refusal feedback: Touch',    script: 'uv-refusal-feedback.test.mjs',     args: [TOUCH],      needs: [TOUCH] },
  { issue: '#141', name: 'relays off by firmware: Controller', script: 'relay-off-by-firmware.test.mjs', args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '#141', name: 'relays off by firmware: Touch', script: 'relay-off-by-firmware.test.mjs',  args: [TOUCH],      needs: [TOUCH] },
  { issue: '#182', name: 'seq fault on reset: both pages', script: 'seq-fault-on-reset.test.mjs',    args: [CONTROLLER, TOUCH], needs: [CONTROLLER, TOUCH] },
  { issue: '#183', name: 'UV index after the cure: both pages', script: 'uv-index-order.test.mjs',   args: [CONTROLLER, TOUCH], needs: [CONTROLLER, TOUCH] },
  { issue: '#186', name: 'UV relay off after a sent ON: both pages', script: 'uv-relay-flags.test.mjs', args: [CONTROLLER, TOUCH], needs: [CONTROLLER, TOUCH] },
  { issue: '#188', name: 'seq end poll guard: both pages', script: 'seq-end-poll.test.mjs',         args: [CONTROLLER, TOUCH], needs: [CONTROLLER, TOUCH] },
  { issue: '#187', name: 'homing index search: Controller', script: 'homing-index.test.mjs',         args: [CONTROLLER], needs: [CONTROLLER] },
];

const verbose = process.argv.includes('-v');
let pass = 0, fail = 0, skip = 0;

for (const c of checks) {
  const missing = c.needs.filter(p => !existsSync(p));
  if (missing.length) {
    skip++;
    console.log(`  SKIP  ${c.issue.padEnd(4)} ${c.name}  (no ${missing.map(m => basename(m)).join(', ')} on this branch)`);
    continue;
  }
  const r = spawnSync(process.execPath, [join(here, c.script), ...c.args], { encoding: 'utf8' });
  if (r.status === 0) {
    pass++;
    console.log(`  PASS  ${c.issue.padEnd(4)} ${c.name}`);
  } else {
    fail++;
    console.log(`  FAIL  ${c.issue.padEnd(4)} ${c.name}`);
  }
  if (verbose || r.status !== 0) {
    const out = (r.stdout || '') + (r.stderr || '');
    console.log(out.split('\n').map(l => '          ' + l).join('\n'));
  }
}

console.log(`\n${pass} passed, ${fail} failed, ${skip} skipped`);
process.exit(fail ? 1 : 0);
