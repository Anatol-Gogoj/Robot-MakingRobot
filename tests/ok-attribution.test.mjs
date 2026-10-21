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

// == T9: Pi bridge: entries come from the echo stream ==
// rmr_bridge.py echoes every write it makes, for every client and physical button, and the echo
// is queued before the bytes leave, so the echo stream is the order the Mega receives commands in.
console.log('\nT9  bridge mode: attribution follows the echo stream, every source counted');
ev('globalThis.WebSocket = { OPEN: 1 }');
ev('useWS = true');
ev(`ws = { readyState: 1, send: c => { globalThis.__wire.push(String(c)); } }`);
const bridge = m => ev('handleWSMessage')(JSON.stringify(m));
ev('okLedgerReset')();
startProgram();
await flush();
ok('line 1 sent to the bridge', last() === 'G28');
ok('no entry before its echo', ev('okLedger').length === 0);
bridge({ _rmr: 'tx', cmd: 'M114', source: 'ws' });                     // another client's poll, written first
bridge({ _rmr: 'tx', cmd: 'G28', source: 'ws' });                      // this page's line 1
bridge({ _rmr: 'tx', cmd: 'G28\nM118 RMR:HOMED_ALL', source: 'button:home_all' });   // a two-line button
ok('four entries: the other poll, line 1, both button lines', ev('okLedger').length === 4);
rx('ok');                                                              // the other client's M114
await flush();
ok("another client's ok advanced nothing", last() === 'G28');
rx('ok');                                                              // line 1's own
await flush();
ok("line 1's own ok advanced to line 2", last() === PROG[1]);
rx('ok'); rx('ok');                                                    // the button's G28 and M118
await flush();
ok("the button's two oks advanced nothing", last() === PROG[1] && ev('progWaitingOk') === true);
bridge({ _rmr: 'tx', cmd: PROG[1], source: 'ws' });
bridge({ _rmr: 'error', msg: 'serial not open; dropped: ' + PROG[1] });
ok('a write the bridge dropped halts the run and clears the ledger', ev('progRunning') === false && ev('okLedger').length === 0);
ev('okLedgerReset')();
startProgram();
await flush();
bridge({ _rmr: 'tx', cmd: 'G28', source: 'ws' });
bridge({ _rmr: 'status', serial: 'closed', port: '/dev/rmr-mega' });
ok('the bridge losing the port halts the run', ev('progRunning') === false && ev('okLedger').length === 0);
ev('useWS = false');
ev('wsOwnPending = []');

// == T10: firmware lines after which nothing outstanding is answered ==
console.log('\nT10 a firmware restart, kill, motor-power loss or RX flush halts the run');
for (const [what, line] of [
  ["'start'", 'start'],
  ['kill()', 'Error:Printer halted. kill() called!'],
  ['MOTOR POWER LOST', 'echo:MOTOR POWER LOST \u2014 motion halted; re-home (G28) required'],
  ["M999's 'Resend:'", 'Resend: 1'],
]) {
  ev('okLedgerReset')();
  startProgram();
  await flush();
  rx(line);
  ok(what + ': run halted, ledger cleared', ev('progRunning') === false && ev('okLedger').length === 0);
}

// == T11: which lines earn an ok ==
console.log('\nT11 only lines Marlin answers get an entry');
ev('okLedgerReset')();
ev('sendCmd')('; a comment on its own');
ev('sendCmd')('M410');
ev('sendCmd')('M108');
ev('sendCmd')('G4 S1 ; with a comment');
await flush();
ok('a comment-only line gets none; M410, M108 and a commented G4 get one each', ev('okLedger').length === 3);
ev('sendCmd')('M112');
await flush();
ok('M112 gets none and clears the ledger', ev('okLedger').length === 0);

// == T12: a stopped run's late ok ==
console.log("\nT12 a stopped run's late ok does not advance the next run");
ev('okLedgerReset')();
startProgram();
await flush();
ev('progStop')();                                    // line 1 still running on the machine
startProgram();
await flush();
const before12 = wire.length;
rx('ok');                                            // <- the stopped run's G28
await flush();
ok("the old line's ok sent nothing", wire.length === before12);
rx('ok');                                            // <- the new run's own
await flush();
ok("the new line's own ok advanced it", last() === PROG[1]);
ev('progStop')();

// == T13: Resume on the Pause button ==
console.log('\nT13 the Pause button resumes, sending the next line if its ok came during the pause');
ev('okLedgerReset')();
startProgram();
await flush();
ev('progPause')();
rx('ok');                                            // line 1 finishes while paused
await flush();
ok('nothing sent while paused', last() === 'G28');
ev('progPause')();                                   // the same button, now reading Resume
await flush();
ok('Resume sent line 2', last() === PROG[1]);
ev('progStop')();

// == T14: the poll waits for an empty ledger ==
console.log('\nT14 the auto-report poll sends only while nothing is unanswered');
ev('okLedgerReset')();
ev('sendCmd')('G28 X');
await flush();
const before14 = wire.length;
ev('autoReportTick')();
await flush();
ok('no M114 behind an unanswered command', wire.length === before14);
rx('ok');
ev('autoReportTick')();
await flush();
ok('M114 once nothing is unanswered', last() === 'M114');
ev('okLedgerReset')();

// == Process Sequencer (issue #180) ==
// seqCmd() waits for its own step's 'ok' through the ledger, as the Program Runner does. The
// checks drive the real Homing block (G28, then the M118 marker) and the real UV block.
if (ev('typeof showToast') === 'function') ev('showToast = () => {}');
el('homeAll').checked = true;
el('homeSpin').checked = false;   // Controller only: no M752 after the home
const seqStatus = () => String(el('seqStatus').innerHTML);
const seqHome = () => { ev('seqRunBlock')('homing'); return flush(); };
const MARK = 'M118 RMR:HOMED_ALL';
// Each case starts idle with nothing owed, so a failure on an unfixed page stays in its own case.
const seqFresh = async () => { if (ev('seqRunning')) { ev('seqStop')(); await flush(); } ev('okLedgerReset')(); };

// == T15: Web Serial: an earlier command's ok does not advance a step ==
console.log('\nT15 sequencer, Web Serial: only a step\'s own ok advances it');
await seqFresh();
ev('sendCmd')('G4 S2');                              // a console command, still unanswered
await flush();
await seqHome();
ok('the Homing block sent G28', last() === 'G28' && ev('seqRunning') === true);
rx('ok');                                            // <- the G4's
await flush();
ok("the console G4's ok did not advance the sequence", last() === 'G28' && ev('seqRunning') === true);
rx('ok');                                            // <- G28's own
await flush();
ok("G28's own ok advanced it to the marker", last() === MARK);
ev('sendCmd')('M114');                               // console traffic sent while the marker is in flight
await flush();
rx('ok');                                            // <- the marker's own (it was sent first)
await flush();
ok("the marker's own ok completed the block", ev('seqRunning') === false && /complete/.test(seqStatus()));
rx('ok');                                            // <- the M114's, after the run
await flush();
ok('nothing left owed', ev('okLedger').length === 0);

// == T16: Pi bridge: another client's and a button's oks do not advance a step ==
console.log("\nT16 sequencer, bridge: other clients' and buttons' oks do not advance it");
ev('useWS = true');
ev(`ws = { readyState: 1, send: c => { globalThis.__wire.push(String(c)); } }`);
await seqFresh();
ev('wsOwnPending = []');
await seqHome();
ok('G28 sent to the bridge', last() === 'G28');
bridge({ _rmr: 'tx', cmd: 'M114', source: 'ws' });                     // another client's poll, written first
bridge({ _rmr: 'tx', cmd: 'G28', source: 'ws' });                      // this page's step
bridge({ _rmr: 'tx', cmd: 'G28\nM118 RMR:HOMED_ALL', source: 'button:home_all' });   // a button after it
rx('ok');                                                              // <- the other client's M114
await flush();
ok("another client's ok did not advance the sequence", last() === 'G28' && ev('seqRunning') === true);
rx('ok');                                                              // <- this page's G28
await flush();
ok("the step's own ok advanced it", last() === MARK);
bridge({ _rmr: 'tx', cmd: MARK, source: 'ws' });                       // the marker's echo, behind the button's two lines
rx('ok'); rx('ok');                                                    // <- the button's G28 and M118
await flush();
ok("the button's two oks did not complete the block", ev('seqRunning') === true);
rx('ok');                                                              // <- the marker's own
await flush();
ok("the marker's own ok completed the block", ev('seqRunning') === false && /complete/.test(seqStatus()));
ev('useWS = false');
ev('wsOwnPending = []');

// == T17: a stopped run's late ok does not advance the next run ==
console.log("\nT17 sequencer: a stopped run's late ok does not advance the next run");
await seqFresh();
await seqHome();
ev('seqStop')();                                     // G28 still running on the machine
await flush();
ok('Stop ended the run and sent M410', ev('seqRunning') === false && last() === 'M410');
await seqHome();
ok('the next run sent its G28', last() === 'G28' && ev('seqRunning') === true);
rx('ok'); rx('ok');                                  // <- the stopped G28's and the M410's
await flush();
ok("the old run's oks did not advance the new one", last() === 'G28' && ev('seqRunning') === true);
rx('ok');                                            // <- the new G28's own
await flush();
ok("the new step's own ok advanced it", last() === MARK);
rx('ok');
await flush();
ok('the new run completed', ev('seqRunning') === false);

// == T18: a cleared ledger fails the step in flight at once ==
console.log('\nT18 sequencer: a cleared ledger fails the step in flight, not at its timeout');
for (const [what, act] of [
  ["a firmware 'start'", () => rx('start')],
  ['the bridge losing the port', () => bridge({ _rmr: 'status', serial: 'closed', port: '/dev/rmr-mega' })],
  ['a disconnect', () => { ev('setConnected')(false); ev('isConnected = true'); }],
  ['a ledger overflow', () => { for (let i = 0; i < ev('OK_LEDGER_MAX') + 2; i++) ev('sendCmd')('M114'); }],
]) {
  await seqFresh();
  await seqHome();
  act();
  await flush();
  ok(what + ': the run failed at once, naming the lost ok', ev('seqRunning') === false && /Error: .*ok.*lost/.test(seqStatus()));
  ok(what + ': nothing more was sent', last() !== MARK);
}

// == T19: the UV block's parallel M752 ==
// The M752 sent during the cure is fire-and-forget. If the cure ends first, the lamp-off M42
// queues behind it and must wait for its own ok, not take the M752's.
console.log("\nT19 sequencer: the UV block's lamp-off step does not take the parallel M752's ok");
await seqFresh();
ev('seqSetHomed')(true, 'test');
el('uvTime').value = '0.05'; el('uvLid').checked = false; el('uvArgon').checked = false; el('uvSpinHome').checked = true;
ev('seqRunBlock')('uv');
await flush();
ok('lamp on sent', last() === 'M42 P4 S1');
rx('ok');                                            // <- the lamp-on's own
for (let i = 0; i < 100 && last() !== 'M42 P4 S0'; i++) await new Promise(r => setTimeout(r, 10));
ok('M752 sent in parallel, then lamp off after the cure', wire.slice(-2).join(' | ') === 'M752 | M42 P4 S0');
rx('ok');                                            // <- the M752's
await flush();
ok("the M752's ok did not complete the lamp-off step", last() === 'M42 P4 S0' && ev('seqRunning') === true);
rx('ok');                                            // <- the lamp-off's own
await flush();
ok("the lamp-off's own ok advanced to the M400 check", last() === 'M400');
rx('ok');
await flush();
ok('the UV block completed', ev('seqRunning') === false && /complete/.test(seqStatus()));
ok('nothing left owed', ev('okLedger').length === 0);

if (ev('autoReportInterval')) clearInterval(ev('autoReportInterval'));
console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
