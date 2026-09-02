// Drives the shipped ok-attribution code (issue #48) in both UIs.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
let fails = 0;
const ok = (n, c) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 0));

// ── fake serial link ───────────────────────────────────────────────────────
const wire = ev("globalThis.__wire = []");   // must live in the sandbox realm
ev('isConnected = true');
ev(`writer = { write: async b => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); } }`);
const rx = line => ev('processLine')(line);
const last = () => wire.at(-1);

const PROG = ['G28', 'M750 S1000 D10 A3 C3 H1', 'M42 P4 S1', 'G4 S5', 'M42 P4 S0'];
function startProgram() {
  el('progTextarea').value = PROG.join('\n');
  el('progWaitOk').checked = true;
  ev('progRun')();
}

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);

// ── T1: the burst ──────────────────────────────────────────────────────────
console.log('\nT1  auto-report ok burst must not advance the program');
el('autoReport').checked = true;
ev('toggleAutoReport')();
ok('poll runs when idle', ev('autoReportInterval') !== null);
startProgram();
await flush();
ok('poll suspended for the run', ev('autoReportInterval') === null);
ok('line 1 sent', last() === 'G28');

for (let i = 0; i < 5; i++) ev('sendCmd')('M114');   // five foreign commands
await flush();
rx('ok');                                            // <- G28's own
await flush();
ok('advanced exactly one line on G28 ok', last() === PROG[1]);
for (let i = 0; i < 5; i++) rx('ok');                // <- the five M114s
await flush();
ok('five foreign oks advanced nothing', last() === PROG[1]);
ok('exactly one program line in flight', ev('progWaitingOk') === true);

// ── T2: interleaving ───────────────────────────────────────────────────────
console.log('\nT2  a command sent after a program line consumes its own ok');
ev('sendCmd')('M114');
await flush();
rx('ok');                                            // M750's
await flush();
ok('advanced to line 3', last() === PROG[2]);
rx('ok');                                            // the trailing M114's
await flush();
ok('trailing M114 ok did not advance', last() === PROG[2]);

// ── T3: pause / resume ─────────────────────────────────────────────────────
console.log('\nT3  pause with a line outstanding, then resume');
ev('progPause')();
ok('paused', ev('progPaused') === true);
const atPause = wire.length;
ev('progRun')();                                     // resume, ok still outstanding
await flush();
ok('resume sent nothing while an ok was outstanding', wire.length === atPause);
rx('ok');
await flush();
ok('the outstanding ok advanced it', last() === PROG[3]);

ev('progPause')();
rx('ok');                                            // finishes while paused
await flush();
ok('paused: ok recorded, nothing sent', ev('progWaitingOk') === false && last() === PROG[3]);
ev('progRun')();
await flush();
ok('resume sent the next line', last() === PROG[4]);

// ── T4: completion restores the poll ───────────────────────────────────────
console.log('\nT4  the poll comes back when the program ends');
rx('ok');
await flush();
ok('program complete', ev('progRunning') === false);
ok('poll restored', ev('autoReportInterval') !== null);
ev('toggleAutoReport');
clearInterval(ev('autoReportInterval'));
ev('autoReportInterval = null');

// ── T5: unaccounted ok ─────────────────────────────────────────────────────
console.log('\nT5  an ok arriving with an empty ledger');
ev('okLedgerReset')();
const before5 = wire.length;
rx('ok');
ok('ignored', wire.length === before5 && ev('okLedger').length === 0);

// ── T6: failed write ───────────────────────────────────────────────────────
console.log('\nT6  a write that throws leaves no ledger entry');
ev('okLedgerReset')();
ev(`writer = { write: async () => { throw new Error('device lost'); } }`);
await ev('sendCmd')('M114');
ok('ledger empty after a failed write', ev('okLedger').length === 0);
ev(`writer = { write: async b => { globalThis.__wire.push(new TextDecoder().decode(b).trim()); } }`);

// ── T7: overflow halts the run ─────────────────────────────────────────────
console.log('\nT7  ledger overflow halts the run rather than guessing');
ev('okLedgerReset')();
startProgram();
await flush();
for (let i = 0; i < ev('OK_LEDGER_MAX') + 2; i++) ev('sendCmd')('M114');
await flush();
ok('program halted', ev('progRunning') === false);
ok('ledger cleared', ev('okLedger').length <= 2);

// ── T8: E-stop clears the ledger and stops the run ─────────────────────────
console.log('\nT8  E-stop stops the program and clears the ledger');
ev('okLedgerReset')();
startProgram();
await flush();
ev('emergencyStop')();
await flush();
ok('program stopped', ev('progRunning') === false);
ok('ledger cleared', ev('okLedger').length === 0);
ok('poll not left running at a halted board', ev('autoReportInterval') === null);

if (ev('autoReportInterval')) clearInterval(ev('autoReportInterval'));
console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
