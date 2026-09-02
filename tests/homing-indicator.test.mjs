// RMR_Touch's homing indicator must clear on G28's own `ok`, not on whichever
// `ok` happens to arrive first (issue #48).
//
// The failure it guards against: send any command, then G28 while the first is
// still unanswered. The first command's `ok` comes back and the old code, which
// only knew "a G28 is pending", cleared the indicator and toasted "Homing
// complete" before homing had begun.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev } = loadUI(FILE);
const flush = () => new Promise(r => setTimeout(r, 0));
let fails = 0;
const ok = (n, c, got) => {
  console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '   [got ' + JSON.stringify(got) + ']'));
  if (!c) fails++;
};

if (ev('typeof clearHomingState') !== 'function') {
  console.log('  SKIP  no homing indicator in ' + FILE.split(/[\\/]/).pop());
  process.exit(0);
}

ev('globalThis.__cleared = 0');
ev('isConnected = true');
ev('writer = { write: async () => {} }');
ev('clearHomingState = () => { globalThis.__cleared++; }');

ev('sendCmd')('M114');       // an ordinary command, still unanswered
ev('sendCmd')('G28');        // then a home, queued behind it
await flush();

ev('processLine')('ok');     // <- the M114's ok, NOT G28's
await flush();
ok('a foreign ok does not clear the homing indicator', ev('__cleared') === 0, ev('__cleared'));

ev('processLine')('ok');     // <- now G28's own
await flush();
ok('G28 own ok clears it', ev('__cleared') === 1, ev('__cleared'));

console.log(fails ? '\n' + fails + ' FAILED' : '\nall passed');
process.exit(fails ? 1 : 0);
