// Runs every UI check against the HTML files in the repo root.
//
//   node tests/run.mjs
//
// A check whose target file is not on this branch is skipped, not failed:
// RMR_SegmentRunner.html only exists once #85 is merged.
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
const RUNNER = f('RMR_SegmentRunner.html');
const PLAIN = f('LayerCycle.gcode');
const ANNOTATED = f('LayerCycle.segments.gcode');

const checks = [
  { issue: '—',   name: 'syntax: RMR_Controller.html',  script: 'syntax-check.mjs',                 args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '—',   name: 'syntax: RMR_Touch.html',       script: 'syntax-check.mjs',                 args: [TOUCH],      needs: [TOUCH] },
  { issue: '—',   name: 'syntax: RMR_SegmentRunner',    script: 'syntax-check.mjs',                 args: [RUNNER],     needs: [RUNNER] },
  { issue: '#48', name: 'ok attribution: Controller',   script: 'ok-attribution.test.mjs',          args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '#48', name: 'ok attribution: Touch',        script: 'ok-attribution.test.mjs',          args: [TOUCH],      needs: [TOUCH] },
  { issue: '#48', name: 'homing indicator: Touch',      script: 'homing-indicator.test.mjs',        args: [TOUCH],      needs: [TOUCH] },
  { issue: '#47', name: 'spin markers: Controller',     script: 'spin-markers.test.mjs',            args: [CONTROLLER], needs: [CONTROLLER] },
  { issue: '#47', name: 'spin markers: Touch',          script: 'spin-markers.test.mjs',            args: [TOUCH],      needs: [TOUCH] },
  { issue: '#62', name: 'segment runner',               script: 'segment-runner.test.mjs',          args: [RUNNER],     needs: [RUNNER] },
  { issue: '#62', name: 'LayerCycle equivalence',       script: 'layercycle-equivalence.test.mjs',  args: [RUNNER, PLAIN, ANNOTATED], needs: [RUNNER, PLAIN, ANNOTATED] },
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
