// Loads the real <script> out of an RMR HTML UI under a stub DOM, so the
// shipped code can be driven directly instead of re-implemented in a test.
//
// let/const bindings live in the script's own lexical scope, not on the sandbox
// global, so a direct eval is appended to that same scope to reach them.
import { readFileSync } from 'fs';
import vm from 'vm';

export function loadUI(file) {
  const html = readFileSync(file, 'utf8');
  const m = html.match(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/i);
  const els = new Map();

  function mkEl(id) {
    const o = {
      value: '', checked: false, textContent: '', innerHTML: '', disabled: false,
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
    querySelectorAll() { return []; },
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
    FileReader: class { readAsText() {} },
    performance,
    getComputedStyle: () => ({ lineHeight: '16px' }),
    Event: class {}, CustomEvent: class {},
    Blob: class { constructor(p) { this.parts = p; } },
    URL: { createObjectURL: () => 'blob:stub', revokeObjectURL() {} },
    addEventListener() {}, removeEventListener() {},
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(m[1] + '\n;globalThis.__ev = (s) => eval(s);', ctx, { filename: file });
  return { ctx, els, document, ev: ctx.__ev, el: id => document.getElementById(id) };
}
