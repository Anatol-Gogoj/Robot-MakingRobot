// Proves LayerCycle.segments.gcode is LayerCycle.gcode with markers added:
// at default parameter values and one layer, the executable lines the runner
// would send must be identical, in order, to the plain file's.
import { readFileSync } from 'fs';
import { loadUI } from './harness.mjs';

const [runnerHtml, plainFile, annotatedFile] = process.argv.slice(2);

const plain = readFileSync(plainFile, 'utf8')
  .split(/\r?\n/)
  .map(l => l.replace(/;.*$/, '').trim())
  .filter(Boolean);

const u = loadUI(runnerHtml);
u.el('src').value = readFileSync(annotatedFile, 'utf8');
u.ev('parseProgram')();

const errors = u.ev('program.errors');
if (errors.length) {
  console.log('PARSE ERRORS in ' + annotatedFile + ':');
  errors.forEach(e => console.log('  ' + e));
  process.exit(1);
}
const warnings = u.ev('program.warnings');
warnings.forEach(w => console.log('warn: ' + w));

u.el('layerCount').value = '1';
u.ev('onLayerCountChange')();

const sent = [];
for (const st of u.ev('plan')) {
  for (const l of st.seg.lines) sent.push(u.ev('substitute')(l.code, st.layer));
}

console.log('\nplain file executable lines : ' + plain.length);
console.log('runner would send           : ' + sent.length);
console.log('segments                    : ' + u.ev('program.segments').length);
console.log('parameters                  : ' + u.ev('program.params').size);

let bad = 0;
const n = Math.max(plain.length, sent.length);
for (let i = 0; i < n; i++) {
  if (plain[i] !== sent[i]) {
    bad++;
    console.log('\nDIFFERS at line ' + (i + 1));
    console.log('  plain : ' + (plain[i] === undefined ? '(none)' : plain[i]));
    console.log('  runner: ' + (sent[i] === undefined ? '(none)' : sent[i]));
  }
}
console.log(bad ? '\n' + bad + ' DIFFERENCE(S)' : '\nIDENTICAL — the annotation changed no executable line.');
process.exit(bad ? 1 : 0);
