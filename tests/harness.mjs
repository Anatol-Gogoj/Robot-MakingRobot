// Loads the real <script> blocks out of an RMR HTML UI under a stub DOM, so the
// shipped code can be driven directly instead of re-implemented in a test.
//
// Every inline (non-src) <script> is run, in page order, in ONE vm scope: the
// pre-paint theme applier, the main UI script, and the shared Run Log module at
// the end of the page. That mirrors the browser, where top-level let/const of
// classic scripts share the global lexical scope.
//
// let/const bindings live in that scope, not on the sandbox global, so a direct
// eval is appended to the same scope to reach them.
import { readFileSync } from 'fs';
import vm from 'vm';

export function loadUI(file) {
  const html = readFileSync(file, 'utf8');
  const scripts = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
  if (!scripts.length) throw new Error('no inline <script> in ' + file);
  const els = new Map();

  function mkEl(id) {
    const o = {
      value: '', checked: false, textContent: '', innerHTML: '', disabled: false, hidden: false, open: false,
      readOnly: false, scrollTop: 0, clientHeight: 200, scrollHeight: 200, childElementCount: 0,
      style: { cssText: '' }, dataset: {}, files: [], children: [], firstChild: null,
      htmlFor: '', type: '', min: '', max: '', step: '', placeholder: '', title: '',
      href: '', download: '', onclick: null, tag: '',
      classList: {
        _s: new Set(),
        add(...c) { c.forEach(x => this._s.add(x)); },
        remove(...c) { c.forEach(x => this._s.delete(x)); },
        toggle(c, f) { if (f === undefined) f = !this._s.has(c); if (f) this._s.add(c); else this._s.delete(c); },
        contains(c) { return this._s.has(c); },
      },
      addEventListener() {}, removeEventListener() {},
      appendChild(c) { this.children.push(c); this.childElementCount = this.children.length; return c; },
      append(...c) { c.forEach(x => this.appendChild(x)); },
      removeChild(c) {
        const i = this.children.indexOf(c);
        if (i >= 0) this.children.splice(i, 1);
        this.childElementCount = this.children.length;
      },
      replaceWith() {}, closest() { return null; },
      focus() {}, click() {}, remove() {}, scrollIntoView() {}, insertAdjacentHTML() {},
      querySelectorAll() { return []; }, querySelector() { return null; },
      getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 100 }; },
      setAttribute() {}, getAttribute() { return null; },
    };
    // Registering on id assignment is what lets a test reach an element the page
    // created at runtime -- renderParams() builds its inputs with createElement.
    Object.defineProperty(o, 'id', {
      get() { return o._id || ''; },
      set(v) { o._id = v; if (v) els.set(v, o); },
      enumerable: true, configurable: true,
    });
    o.id = id;
    return o;
  }

  const document = {
    getElementById(id) { if (!els.has(id)) mkEl(id); return els.get(id); },
    // Only the one selector shape the UIs actually use: [id^="prefix"]. The
    // layer table is built with innerHTML, so this is the only way its cells are
    // reachable, and both renderLayerTable() and clearLayerCells() depend on it.
    querySelectorAll(sel) {
      const m = /^\[id\^=["']?([^"'\]]+)["']?\]$/.exec(String(sel || '').trim());
      if (!m) return [];
      return [...els.entries()].filter(([id]) => id.startsWith(m[1])).map(([, el]) => el);
    },
    querySelector() { return null; },
    createElement(t) { const e = mkEl(''); e.tag = t; return e; },
    createElementNS(ns, t) { const e = mkEl(''); e.tag = t; return e; },
    addEventListener() {}, body: mkEl('body'), documentElement: mkEl('html'),
  };

  // Seed elements from the markup, so defaults declared as HTML attributes
  // (checked, value, type) are visible to the script -- which reads them at load.
  const TAG_WITH_ID = /<([A-Za-z]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g;
  for (const t of html.matchAll(TAG_WITH_ID)) {
    const el = document.getElementById(t[3]);
    el.tag = t[1];
    if (/\bchecked\b/.test(t[2])) el.checked = true;
    const v = t[2].match(/\bvalue="([^"]*)"/);
    if (v) el.value = v[1];
    const ty = t[2].match(/\btype="([^"]*)"/);
    if (ty) el.type = ty[1];
  }

  const sandbox = {
    document, console,
    navigator: { serial: { addEventListener() {}, getPorts: async () => [] } },
    localStorage: {
      _m: new Map(),
      getItem(k) { return this._m.has(k) ? this._m.get(k) : null; },
      setItem(k, v) { this._m.set(k, String(v)); },
      removeItem(k) { this._m.delete(k); },
    },
    TextEncoder, TextDecoder, TextDecoderStream,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Date, Math, JSON, Promise, Set, Map,
    alert() {}, confirm: () => true, prompt: () => null,
    requestAnimationFrame: cb => setTimeout(cb, 0),
    // Delivers the text a test attached to the fake file, so an import path can
    // be driven end to end. Synchronous on purpose: no timing to wait on.
    FileReader: class {
      readAsText(file) {
        const result = file && file.__text !== undefined ? file.__text : '';
        if (this.onload) this.onload({ target: { result } });
      }
    },
    performance,
    getComputedStyle: () => ({ lineHeight: '16px' }),
    Event: class {}, CustomEvent: class {},
    Blob: class { constructor(p) { this.parts = p; } },
    URL: { createObjectURL: () => 'blob:stub', revokeObjectURL() {} },
    addEventListener() {}, removeEventListener() {},
    location: { search: '', protocol: 'file:', href: 'file:///stub.html' },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(scripts.join('\n;\n') + '\n;globalThis.__ev = (s) => eval(s);', ctx, { filename: file });
  return { ctx, els, document, ev: ctx.__ev, el: id => document.getElementById(id) };
}
