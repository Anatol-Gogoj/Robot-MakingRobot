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

// A no-op canvas 2D context. Both UIs draw the UV / argon progress bar to a
// <canvas> on load (uvProgressRender -> draw), and the stub DOM has no real
// canvas backing. The tests don't assert pixels, so every drawing call is a
// no-op and every property assignment (fillStyle, font, ...) is swallowed. A
// Proxy covers the whole 2D API without having to list each method by hand.
const CANVAS_CTX = new Proxy({}, { get: (t, k) => (k in t ? t[k] : () => {}), set: () => true });

export function loadUI(file) {
  const html = readFileSync(file, 'utf8');
  const scripts = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
  if (!scripts.length) throw new Error('no inline <script> in ' + file);
  const els = new Map();
  const byName = new Map();   // radio groups (name -> elements); they carry no id

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
      getContext() { return CANVAS_CTX; },
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
    // Only the selector shapes the UIs actually use. [id^="prefix"]: the layer
    // table is built with innerHTML, so this is the only way its cells are
    // reachable, and both renderLayerTable() and clearLayerCells() depend on it.
    // input[name="x"]: a radio group (the stamp feeder side).
    querySelectorAll(sel) {
      const s = String(sel || '').trim();
      const m = /^\[id\^=["']?([^"'\]]+)["']?\]$/.exec(s);
      if (m) return [...els.entries()].filter(([id]) => id.startsWith(m[1])).map(([, el]) => el);
      const n = /^input\[name=["']([^"'\]]+)["']\]$/.exec(s);
      if (n) return [...(byName.get(n[1]) || [])];
      return [];
    },
    // input[name="x"]:checked and input[name="x"][value="y"] -- how both UIs read
    // and set the stamp feeder side. Anything else is unresolved, as before.
    querySelector(sel) {
      const m = /^input\[name=["']([^"'\]]+)["']\](?::checked|\[value=["']([^"'\]]*)["']\])$/.exec(String(sel || '').trim());
      if (!m) return null;
      return (byName.get(m[1]) || []).find(e => (m[2] === undefined ? e.checked : e.value === m[2])) || null;
    },
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
    // min / max: the servo sliders' soft limits are declared in the markup only.
    const mn = t[2].match(/\bmin="([^"]*)"/);
    if (mn) el.min = mn[1];
    const mx = t[2].match(/\bmax="([^"]*)"/);
    if (mx) el.max = mx[1];
  }
  // Radio groups have a name but no id (the stamp feeder side). Seed them too, so
  // input[name="x"]:checked / [value="y"] resolve, and give each radio a checked
  // setter that unchecks the rest of its group, as a browser does.
  const INPUT_WITH_NAME = /<input\b([^>]*\bname="([^"]+)"[^>]*)>/g;
  for (const t of html.matchAll(INPUT_WITH_NAME)) {
    const attrs = t[1], name = t[2];
    const idm = attrs.match(/\bid="([^"]+)"/);
    const e = idm ? document.getElementById(idm[1]) : mkEl('');
    e.tag = 'input'; e.name = name;
    const ty = attrs.match(/\btype="([^"]*)"/); if (ty) e.type = ty[1];
    const v = attrs.match(/\bvalue="([^"]*)"/); if (v) e.value = v[1];
    if (!byName.has(name)) byName.set(name, []);
    const group = byName.get(name); group.push(e);
    let checked = /\bchecked\b/.test(attrs);
    if (e.type === 'radio') Object.defineProperty(e, 'checked', {
      get() { return checked; },
      set(x) { checked = !!x; if (checked) group.forEach(o => { if (o !== e) o.checked = false; }); },
      enumerable: true, configurable: true,
    });
    else e.checked = checked;
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
    TextEncoder, TextDecoder, TextDecoderStream, URLSearchParams,
    // Share the outer realm's typed-array + buffer intrinsics into the sandbox so
    // bytes the UI builds (e.g. the XLSX export) are `instanceof Uint8Array` when a
    // test in this realm checks them; a vm context otherwise has its own copies.
    ArrayBuffer, DataView, Uint8Array, Uint16Array, Uint32Array, Int8Array, Int16Array, Int32Array, Float32Array, Float64Array,
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
    // getPropertyValue backs the palette()/tok() reads of CSS custom properties;
    // returning '' makes the UIs fall through to their coded default colours.
    getComputedStyle: () => ({ lineHeight: '16px', getPropertyValue: () => '' }),
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
