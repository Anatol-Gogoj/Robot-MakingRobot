import { loadUI } from './harness.mjs';
const FILE = process.argv[2];
const { ev } = loadUI(FILE);
ev('globalThis.__cleared = 0');
ev('isConnected = true');
ev('writer = { write: async () => {} }');
ev('clearHomingState = () => { globalThis.__cleared++; }');
const flush = () => new Promise(r => setTimeout(r, 0));
ev('sendCmd')('M114');            // an ordinary command, still unanswered
ev('sendCmd')('G28');             // then a home
await flush();
ev('processLine')('ok');          // <- the M114's ok, NOT G28's
await flush();
console.log(`${FILE.split(/[\/]/).pop().padEnd(22)} homing cleared by the M114's ok: ${ev('__cleared') ? 'YES (wrong)' : 'no'}`);
