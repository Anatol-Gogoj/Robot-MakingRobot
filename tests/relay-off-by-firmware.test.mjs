// The #131 firmware drives the UV lamp relay (pin 4) and the argon valve relay (pin 42) to OFF
// by itself at boot, in kill() (M112) and on a motor-power loss, and prints no line of its own
// for it. Both UIs highlight the last relay button pressed, so after those events they kept
// showing UV ON / valve OPEN while both relays were off (#141). Each page now drops both pairs
// to OFF on a sent M112 (its own E-STOP, the console, or the bridge's echo of another client's)
// and on the 'start', 'MOTOR POWER LOST' and 'kill() called' lines, and on nothing else.
// The change is display-only: none of these events may send anything.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
const IS_TOUCH = /RMR_Touch\.html$/.test(FILE);
const UV_ON = IS_TOUCH ? 'fabUvOn' : 'uvOnBtn', UV_OFF = IS_TOUCH ? 'fabUvOff' : 'uvOffBtn';
const SOL_ON = IS_TOUCH ? 'fabSolOn' : 'solOnBtn', SOL_OFF = IS_TOUCH ? 'fabSolOff' : 'solOffBtn';
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
ev('globalThis.__toasts = []');
ev('showToast = (m, t) => { globalThis.__toasts.push([String(m), t]); }');
ev('isConnected = true');
ev('globalThis.__sent = []');
ev('writer = { write: async (b) => { globalThis.__sent.push(new TextDecoder().decode(b).trim()); } }');
const sent = ev('__sent');
const lit = id => el(id).classList.contains('on');
const rx = line => ev('processLine')(line);
const tick = () => new Promise(r => setTimeout(r, 0));   // sendCmd runs homedTrackTx after its await
const state = () => ({ uvOn: lit(UV_ON), uvOff: lit(UV_OFF), solOn: lit(SOL_ON), solOff: lit(SOL_OFF) });
const isBothOn = s => s.uvOn && !s.uvOff && s.solOn && !s.solOff;
const isBothOff = s => !s.uvOn && s.uvOff && !s.solOn && s.solOff;
const bothOn = async () => { ev('relayCmd')('uv', 1); ev('relayCmd')('sol', 1); await tick(); };

// Firmware lines, verbatim: MarlinCore.cpp setup() prints "start"; motor_power.cpp prints the
// loss through SERIAL_ECHO_MSG; kill() prints STR_ERR_KILLED through SERIAL_ERROR_MSG.
const START = 'start';
const MOTOR_LOST = 'echo:MOTOR POWER LOST \u2014 motion halted; re-home (G28) required';
const KILLED = 'Error:Printer halted. kill() called!';

// 1 -- a manual press still highlights ON, as before
await bothOn();
ok('UV ON and valve OPEN send M42 P4 S1 / M42 P42 S1 and highlight ON',
   sent[0] === 'M42 P4 S1' && sent[1] === 'M42 P42 S1' && isBothOn(state()), [sent, state()]);

// 2 -- a board reset: the firmware drives both relays off in setup() and prints 'start'
let n = sent.length;
rx(START);
ok("'start' (any reset, including the DTR reset on connect) shows both pairs OFF", isBothOff(state()), state());
ok("'start' sends nothing", sent.length === n, sent.slice(n));

// 3 -- a motor-power loss (the K2 contactor drops, pin 43 sees it)
await bothOn(); n = sent.length;
rx(MOTOR_LOST);
ok('MOTOR POWER LOST shows both pairs OFF', isBothOff(state()), state());
ok('MOTOR POWER LOST sends nothing', sent.length === n, sent.slice(n));

// 4 -- this page's E-STOP button: M112 reaches kill(), which drops both relays first
await bothOn(); n = sent.length;
ev('emergencyStop')(); await tick();
ok('E-STOP sends M112 and shows both pairs OFF', sent.slice(n).join('|') === 'M112' && isBothOff(state()), [sent.slice(n), state()]);

// 5 -- an M112 typed in the console takes the same path
await bothOn(); n = sent.length;
ev('sendCmd')('m112'); await tick();
ok('a console M112 shows both pairs OFF', sent.slice(n).join('|') === 'm112' && isBothOff(state()), [sent.slice(n), state()]);

// 6 -- on the Pi bridge, another client's M112 (or the physical E-stop's optional one) is echoed
await bothOn(); n = sent.length;
ev('handleWSMessage')(JSON.stringify({ _rmr: 'tx', cmd: 'M112', source: 'estop' }));
ok("the bridge's echo of an M112 from elsewhere shows both pairs OFF", isBothOff(state()), state());
ok('the echo sends nothing', sent.length === n, sent.slice(n));

// 7 -- kill() announces itself; that line also drops the pairs, and still fails a sequence
await bothOn(); n = sent.length;
ev('seqRunning = true'); ev('seqFaultReason = null');
rx(KILLED);
ok("'kill() called' shows both pairs OFF", isBothOff(state()), state());
ok("'kill() called' still fails a running sequence through the Error: check", ev('seqFaultReason') === KILLED, ev('seqFaultReason'));
ev('seqRunning = false'); ev('seqFaultReason = null');
ok("'kill() called' sends nothing", sent.length === n, sent.slice(n));

// 8 -- events on which the firmware does NOT touch the relays leave the highlight alone
await bothOn(); n = sent.length;
rx('ok'); rx('echo:busy: processing'); rx('X:0.00 Y:0.00 Z:0.00 A:0.00 B:0.00 C:0.00 Count X:0 Y:0 Z:0');
rx('echo:SPIN STATE:RAMP_UP'); rx('echo:Motor power restored \u2014 re-home (G28) before moving');
rx('echo:Move refused: re-home (G28) after motor power loss');
rx('Error:Unknown command: "M9999"');
ok('ordinary traffic, motor power restored, a refused move and other Error: lines leave both ON', isBothOn(state()), state());
ev('sendCmd')('M999'); ev('sendCmd')('M18'); ev('sendCmd')('M84'); await tick();
ok('M999 / M18 / M84 leave both ON', isBothOn(state()), state());
ev('handleWSMessage')(JSON.stringify({ _rmr: 'estop', pressed: true }));
// The bridge's E-stop sense alone is not one of the firmware's relay-off events. K2 cuts the lamp
// supply, but the relay stays commanded ON until MOTOR POWER LOST (pin 43) or an M112 arrives,
// and ON is then the honest warning that the lamp relights when K2 is reset.
ok('a physical E-stop event with no M112 and no MOTOR POWER LOST leaves both ON', isBothOn(state()), state());

// 9 -- after a reset to OFF, the buttons work as before
rx(START);
ev('relayCmd')('uv', 1);
const s = state();
ok('a fresh UV ON after a reset highlights UV ON and leaves the valve OFF', s.uvOn && !s.uvOff && !s.solOn && s.solOff, s);

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
