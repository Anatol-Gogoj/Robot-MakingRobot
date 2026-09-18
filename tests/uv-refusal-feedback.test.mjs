// When the firmware's UV lid interlock refuses a UV-on ("UV inhibited: lid open") or cuts the
// lamp mid-cure ("UV cut: lid opened"), the operator has to see it where they are looking.
// Before this check a manual UV ON that the firmware refused stayed highlighted as ON with
// nothing but a console "<< echo:" line, which is how a healthy relay got diagnosed with a
// multimeter (#123). Both UIs: error toast, console line, UV pair shown OFF, sequencer flag set.
import { loadUI } from './harness.mjs';

const FILE = process.argv[2];
const { ev, el } = loadUI(FILE);
const IS_TOUCH = /RMR_Touch\.html$/.test(FILE);
const ON = IS_TOUCH ? 'fabUvOn' : 'uvOnBtn', OFF = IS_TOUCH ? 'fabUvOff' : 'uvOffBtn';
const SOL_ON = IS_TOUCH ? 'fabSolOn' : 'solOnBtn';
let fails = 0;
const ok = (n, c, got) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : `   [got ${JSON.stringify(got)}]`)); if (!c) fails++; };

console.log(`\n=== ${FILE.split(/[\/]/).pop()} ===`);
ev('globalThis.__toasts = []');
ev('showToast = (m, t) => { globalThis.__toasts.push([String(m), t]); }');
ev('isConnected = true');
ev('globalThis.__sent = []');
ev('writer = { write: async (b) => { globalThis.__sent.push(new TextDecoder().decode(b).trim()); } }');
const toasts = ev('__toasts'), sent = ev('__sent');
const lit = id => el(id).classList.contains('on');
const rx = line => ev('processLine')(line);

// 1 -- a manual UV ON: command sent, ON highlighted (as before)
ev('relayCmd')('uv', 1);
ok('UV ON sends M42 P4 S1 and highlights ON', sent[0] === 'M42 P4 S1' && lit(ON) && !lit(OFF), [sent, lit(ON), lit(OFF)]);

// 2 -- the firmware refuses it
rx('echo:UV inhibited: lid open (interlock)');
ok('the refusal raises one error toast that names the lid interlock',
   toasts.length === 1 && toasts[0][1] === 'error' && /interlock/i.test(toasts[0][0]), toasts);
ok('the UV pair drops to OFF: the lamp is not lit', !lit(ON) && lit(OFF), [lit(ON), lit(OFF)]);
ok('the sequencer flag carries the refusal', /refused UV/.test(ev('uvInterlockMsg') || ''), ev('uvInterlockMsg'));

// 3 -- ordinary traffic raises nothing
rx('ok'); rx('echo:busy: processing'); rx('X:0.00 Y:0.00 Z:0.00 C:0.00');
ok('ok / busy / position lines raise no toast and leave the pair alone', toasts.length === 1 && !lit(ON) && lit(OFF), toasts);

// 4 -- lamp on, then the lid opens: the firmware cuts it
ev('relayCmd')('uv', 1); rx('ok');
ok('a fresh ON highlights ON again', lit(ON) && !lit(OFF));
rx('echo:UV cut: lid opened during cure (interlock)');
ok('a mid-cure cut raises an error toast and drops the pair to OFF',
   toasts.length === 2 && toasts[1][1] === 'error' && /cut/i.test(toasts[1][0]) && !lit(ON) && lit(OFF), [toasts, lit(ON), lit(OFF)]);

// 5 -- a UV refusal never touches the solenoid pair
ev('relayCmd')('sol', 1);
rx('echo:UV inhibited: lid open (interlock)');
ok('the solenoid pair keeps its own state through a UV refusal', lit(SOL_ON) && !lit(ON) && lit(OFF), [lit(SOL_ON), lit(ON), lit(OFF)]);

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
