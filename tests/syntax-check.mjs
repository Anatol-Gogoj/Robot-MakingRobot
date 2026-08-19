// Extract every <script> block from an HTML file and syntax-check it.
// usage: node jscheck.mjs <file.html>
import { readFileSync, writeFileSync, mkdtempSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { execFileSync } from 'child_process';
const file = process.argv[2];
const html = readFileSync(file, 'utf8');
const re = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
let m, i = 0, bad = 0;
const dir = mkdtempSync(join(tmpdir(), 'jscheck-'));
while ((m = re.exec(html)) !== null) {
  const body = m[1];
  const line = html.slice(0, m.index).split('\n').length;
  const p = join(dir, `block${i}.js`);
  writeFileSync(p, body, 'utf8');
  try {
    execFileSync(process.execPath, ['--check', p], { stdio: 'pipe' });
    console.log(`  block ${i} (html line ${line}, ${body.split('\n').length} lines): OK`);
  } catch (e) {
    bad++;
    console.error(`  block ${i} (html line ${line}): SYNTAX ERROR`);
    console.error(String(e.stderr).split('\n').slice(0, 8).join('\n'));
  }
  i++;
}
console.log(bad ? `FAIL: ${bad} bad block(s)` : `PASS: ${i} script block(s) parse`);
process.exit(bad ? 1 : 0);
