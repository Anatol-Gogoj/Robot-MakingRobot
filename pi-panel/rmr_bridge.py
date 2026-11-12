#!/usr/bin/env python3
"""
RMR serial <-> WebSocket bridge  (Pi touch-panel, "Path B").

The Raspberry Pi owns the USB serial link to the Arduino Mega (Marlin). The
browser UI (RMR_Controller.html / RMR_Touch.html) is just a display: it talks
to this bridge over a WebSocket instead of using the browser's Web Serial API.

Because the browser no longer needs Web Serial, ANY browser works (Firefox,
a WebKit kiosk such as cog/wpe, etc.) — no Chromium requirement.

Data plane (kept intentionally line-oriented, 1:1 with the serial protocol):
    browser -> bridge : a raw G-code command string  (bridge appends '\n')
    bridge  -> browser: one raw serial line per message (Marlin's replies)

Meta plane (JSON, always begins with '{' and carries an "_rmr" key):
    {"_rmr":"status","serial":"open"|"closed","port":...}
    {"_rmr":"tx","cmd":...,"source":"ws"|"button:NAME"}   # every write, echoed to ALL clients
    {"_rmr":"button","name":...,"cmd":...}                # a physical button fired
    {"_rmr":"button","name":...,"cmd":...,"action":...}   # ... and asks this page to act on it
    {"_rmr":"estop","pressed":true|false}                # E-stop sense input changed
    {"_rmr":"error","msg":...}
    browser -> bridge: {"_rmr":"state","busy":true|false}  # never written to serial

Operator panel buttons (issue #218) carry an "action" instead of, or as well as, a
"cmd": "stop" goes to every client (each stops its own sequencer run and Program
Runner); "start" goes to exactly one client, the page the Pi's own browser opened
over loopback. It is refused when there is no such page or more than one, and while
any other page reports a run, a program or a Run Log hold open ("state", which the
greeting's "caps" invites), so a phone, a laptop or a second tab never gets a second
run started on top of its own.

Multiple clients may connect at once (the panel + a phone/laptop on the LAN);
serial RX is broadcast to all of them and every TX is echoed to all of them, so
the console stays in sync no matter who (or which button) issued a command.

Optional GPIO I/O (all off unless configured in rmr_io.json — see the example):
  • Physical buttons (gloved/dirty-hand operation) mapped to G-code; they call
    the exact same write path as the UI.
  • A status tower (red / amber / green) + buzzer, driven from machine state the
    bridge infers off the serial stream + connection: green = ready/idle,
    amber = active, red(+buzzer) = error / E-stop, red = serial down.
  • An E-stop SENSE input that annunciates on the tower and to the UI, and can
    optionally also send M112.

SAFETY: the GPIO "E-STOP" button/sense here works in software (it sends/echoes
M112) and depends on the Pi, USB link, and firmware all being alive. It is NOT a
safety-rated interlock. For real safety, ALSO wire a hardware E-stop that
physically cuts stepper-driver / ODrive motor power, independent of the Pi.

Deps:  pip install pyserial websockets     (gpiozero is preinstalled on Pi OS)
"""

import argparse
import asyncio
import functools
import ipaddress
import json
import os
import signal
import threading
import time

import serial  # pyserial
import websockets

# gpiozero is only needed for GPIO (buttons / tower / e-stop) and only exists on a Pi.
try:
    from gpiozero import Button, LED, Buzzer
    HAVE_GPIO = True
except Exception:
    HAVE_GPIO = False


# ─── Shared state ───────────────────────────────────────────────────────────
clients = set()                 # connected WebSocket client protocols
client_busy = {}                # client -> True while its page reports a run, program or hold open (#218)
serial_lock = threading.Lock()  # guards writes (WS thread + button threads)
stop_event = threading.Event()
loop = None                     # asyncio loop, set in main()
ser = None                      # the pyserial Serial instance (or None)
_buttons = []                   # keep gpiozero Button refs alive
estop_btn = None                # gpiozero Button for the E-stop sense input (or None)
tower = None                    # StatusTower instance (or None)

# Machine-state flags for the status tower, guarded by io_lock.
io_lock = threading.Lock()
_last_tx_ts = 0.0               # time.monotonic() of the last serial write (activity)
_error_until = 0.0             # tower alarm latched (red+buzzer) until this monotonic time
_serial_open = False            # is the serial port currently open?
_estop = False                  # E-stop sense input asserted?
_motor_lost = False             # Mega reported motor power removed (latched red until restored)
_tower_last = None              # last (color, alarm) applied, to avoid redundant GPIO writes

cfg = None                      # argparse.Namespace, set in main()


# ─── Broadcast helpers (called from any thread) ──────────────────────────────
def schedule_broadcast(msg: str):
    """Thread-safe: hand a string to the event loop to fan out to all clients."""
    if loop is not None and not loop.is_closed():
        try:
            loop.call_soon_threadsafe(_broadcast_sync, msg)
        except RuntimeError:
            pass


def _broadcast_sync(msg: str):
    for ws in list(clients):
        asyncio.create_task(_safe_send(ws, msg))


async def _safe_send(ws, msg: str):
    try:
        await ws.send(msg)
    except Exception:
        clients.discard(ws)


# ─── Serial write (from WS clients and from GPIO buttons) ────────────────────
def write_serial(cmd: str, source: str = "ws", before_write=None):
    """before_write: called under the lock once the echo is queued, before the bytes leave (#218)."""
    global _last_tx_ts
    cmd = cmd.strip()
    if not cmd:
        if before_write:
            before_write()
        return
    data = (cmd + "\n").encode("utf-8", "replace")
    wrote = False
    with serial_lock:
        # Echo every write to ALL clients so each UI (and each button press) is visible everywhere.
        # Queued before the bytes leave, so every client sees the echo before any reply to it: the
        # UIs attribute each 'ok' to the oldest echoed command (issue #48). A failed write is
        # reported right after it, below.
        schedule_broadcast(json.dumps({"_rmr": "tx", "cmd": cmd, "source": source}))
        if before_write:
            before_write()
        try:
            if ser is not None and ser.is_open:
                ser.write(data)
                wrote = True
        except Exception as e:
            schedule_broadcast(json.dumps({"_rmr": "error", "msg": "serial write failed: %s" % e}))
    with io_lock:
        _last_tx_ts = time.monotonic()  # any command counts as activity (tower → amber)
    if not wrote:
        schedule_broadcast(json.dumps({"_rmr": "error", "msg": "serial not open; dropped: %s" % cmd}))


# ─── Serial reader thread ────────────────────────────────────────────────────
def serial_reader():
    """Own the port: (re)open with backoff, read lines, broadcast each line."""
    global ser, _serial_open
    buf = bytearray()
    backoff = 1.0
    while not stop_event.is_set():
        if ser is None or not ser.is_open:
            try:
                ser = serial.Serial(cfg.port, cfg.baud, timeout=0.1)
                backoff = 1.0
                buf.clear()
                with io_lock:
                    _serial_open = True
                print("[serial] opened %s @ %d" % (cfg.port, cfg.baud))
                schedule_broadcast(json.dumps({"_rmr": "status", "serial": "open", "port": cfg.port}))
            except Exception as e:
                with io_lock:
                    _serial_open = False
                schedule_broadcast(json.dumps({"_rmr": "status", "serial": "closed",
                                               "port": cfg.port, "error": str(e)}))
                time.sleep(min(backoff, 5.0))
                backoff *= 1.5
                continue
        try:
            data = ser.read(4096)  # returns whatever arrived within the 0.1 s timeout
        except Exception as e:
            print("[serial] read error: %s" % e)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            with io_lock:
                _serial_open = False
            schedule_broadcast(json.dumps({"_rmr": "status", "serial": "closed", "port": cfg.port}))
            continue
        if not data:
            continue
        buf.extend(data)
        while True:
            nl = buf.find(b"\n")
            if nl < 0:
                break
            line = bytes(buf[:nl])
            del buf[:nl + 1]
            text = line.decode("utf-8", "replace").rstrip("\r")
            note_serial_line(text)   # update tower alarm latch from Marlin errors/boot
            schedule_broadcast(text)


# ─── Physical buttons (optional) ─────────────────────────────────────────────
def setup_buttons(mapping):
    if not mapping:
        return
    if not HAVE_GPIO:
        print("[gpio] gpiozero unavailable; skipping %d button(s). "
              "(Buttons only work on a Raspberry Pi.)" % len(mapping))
        return
    for b in mapping:
        try:
            pin = b["pin"]
            name = b.get("name", "btn%s" % pin)
            cmd, action = button_spec(b)
            pull = b.get("pull", "up")            # "up" = wire button to GND, active-low (default)
            bounce = float(b.get("bounce", 0.05))  # debounce seconds
            btn = Button(pin, pull_up=(pull == "up"), bounce_time=bounce)
            btn.when_pressed = functools.partial(_on_button, name, cmd, action)
            _buttons.append(btn)
            print("[gpio] %-10s GPIO%-2s -> %s%s" % (name, pin, cmd or "",
                                                     (" [action %s]" % action) if action else ""))
        except Exception as e:
            print("[gpio] failed to set up button %r: %s" % (b, e))


# Actions a button may ask the browser pages to take (issue #218).
BUTTON_ACTIONS = ("start", "stop")


def button_spec(b):
    """(cmd, action) of one button entry. A button needs a 'cmd', an 'action', or both."""
    cmd = b.get("cmd") or None
    action = b.get("action") or None
    if action is not None and action not in BUTTON_ACTIONS:
        raise ValueError("unknown action %r (expected one of %s)" % (action, ", ".join(BUTTON_ACTIONS)))
    if cmd is None and action is None:
        raise ValueError("a button needs a 'cmd', an 'action', or both")
    return cmd, action


def _on_button(name, cmd, action=None):
    """GPIO thread. The button message is queued after the command's TX echo and before its
    bytes are written, so a page stops its run before any reply to that command can reach it
    (Stop: abort the run, then M410 at the board, as the page's own Stop does)."""
    def dispatch():
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(_dispatch_button, name, cmd, action)
            except RuntimeError:
                pass
    if cmd:
        write_serial(cmd, source="button:%s" % name, before_write=dispatch)
    else:
        dispatch()


def is_loopback(ws):
    """True when the client connected from the Pi itself (the panel's kiosk browser)."""
    try:
        addr = ipaddress.ip_address(str(getattr(ws, "remote_address", ("",))[0]).split("%")[0])
    except (ValueError, IndexError, TypeError):
        return False
    if getattr(addr, "ipv4_mapped", None) is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback


def button_targets(action, conns, busy=None):
    """(clients asked to act, error message or None) for one press, given the connected clients.
    'stop' asks every client; 'start' asks the single loopback client, and nobody when there is
    none or more than one, since two pages each running Run All would drive one machine twice,
    or while busy(ws) is true for another client: its run, program or Run Log hold is open."""
    conns = list(conns)
    busy = busy or (lambda ws: False)
    if action == "stop":
        return conns, None
    if action == "start":
        local = [ws for ws in conns if is_loopback(ws)]
        if len(local) == 1:
            others = [ws for ws in conns if ws is not local[0] and busy(ws)]
            if others:
                return [], ("start button ignored: a run, program or hold is open on another screen "
                            "(%s); resume or stop it there" % ", ".join(_peer(ws) for ws in others))
            return local, None
        if not local:
            return [], "start button ignored: no panel page is open on the Pi (http://localhost)"
        return [], ("start button ignored: %d pages are open on the Pi; close all but one so "
                    "only one of them can start a run" % len(local))
    return [], None


def _peer(ws):
    try:
        return str(ws.remote_address[0])
    except Exception:
        return "?"


def _dispatch_button(name, cmd, action):
    """Event loop thread: tell every client about the press, and the chosen ones what to do."""
    base = {"_rmr": "button", "name": name, "cmd": cmd}
    actors, err = button_targets(action, clients, lambda ws: client_busy.get(ws, False))
    for ws in list(clients):
        msg = dict(base, action=action) if ws in actors else base
        asyncio.create_task(_safe_send(ws, json.dumps(msg)))
    if err:
        print("[gpio] %s" % err)
        _broadcast_sync(json.dumps({"_rmr": "error", "msg": err}))


def load_io_config(path):
    """Load the GPIO config file: {buttons:[...], tower:{...}, estop:{...}}.
    A bare list is accepted as buttons-only (legacy)."""
    if not path:
        return {}
    if not os.path.exists(path):
        print("[gpio] IO config %s not found; no GPIO buttons / tower / e-stop" % path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"buttons": data} if isinstance(data, list) else data


# ─── Status tower + buzzer (optional GPIO outputs) ───────────────────────────
class StatusTower:
    """Red/amber/green tower light + buzzer. Any channel may be omitted."""
    def __init__(self, tcfg):
        ah = bool(tcfg.get("active_high", True))  # False for active-low relay boards
        self.red = LED(tcfg["red"], active_high=ah) if tcfg.get("red") is not None else None
        self.amber = LED(tcfg["amber"], active_high=ah) if tcfg.get("amber") is not None else None
        self.green = LED(tcfg["green"], active_high=ah) if tcfg.get("green") is not None else None
        self.buzzer = Buzzer(tcfg["buzzer"], active_high=ah) if tcfg.get("buzzer") is not None else None

    def apply(self, color, alarm):
        for led, on in ((self.red, color == "red"),
                        (self.amber, color == "amber"),
                        (self.green, color == "green")):
            if led is not None:
                (led.on if on else led.off)()
        if self.buzzer is not None:
            if alarm:
                self.buzzer.beep(on_time=0.25, off_time=0.25)  # pulse while alarming
            else:
                self.buzzer.off()


def setup_tower(tcfg):
    global tower
    if not tcfg:
        return
    if not HAVE_GPIO:
        print("[gpio] gpiozero unavailable; status tower disabled.")
        return
    try:
        tower = StatusTower(tcfg)
        pins = {k: tcfg.get(k) for k in ("red", "amber", "green", "buzzer") if tcfg.get(k) is not None}
        print("[gpio] status tower %s (active_high=%s)" % (pins, tcfg.get("active_high", True)))
    except Exception as e:
        print("[gpio] status tower setup failed: %s" % e)
        tower = None


def note_serial_line(text):
    """Latch a tower alarm on Marlin errors / motor-power loss; clear it on a reset/boot line."""
    global _error_until, _motor_lost
    low = text.lower()
    if "motor power lost" in low:                     # Mega motor_power sense: E-stop cut the motors
        with io_lock:
            _motor_lost = True                         # latched red until Marlin reports restore
        schedule_broadcast(json.dumps({"_rmr": "motorpower", "ok": False}))
    elif "motor power restored" in low:
        with io_lock:
            _motor_lost = False
        schedule_broadcast(json.dumps({"_rmr": "motorpower", "ok": True}))
    elif text.startswith("Error:") or text.startswith("!!") or "kill()" in low or "emergency" in low:
        with io_lock:
            _error_until = time.monotonic() + 5.0   # refreshed while errors keep coming
    elif text == "start" or text.startswith("echo:Marlin") or "marlin ready" in low:
        with io_lock:
            _error_until = 0.0                        # M999 / boot clears the alarm
            _motor_lost = False                        # boot clears the motor-power latch too


def _tower_state():
    """Priority: E-stop / error (red+buzz) > serial down (red) > active (amber) > idle (green)."""
    now = time.monotonic()
    with io_lock:
        estop, err, mlost = _estop, now < _error_until, _motor_lost
        opened, active = _serial_open, (now - _last_tx_ts) < 1.5
    if estop or err or mlost:
        return ("red", True)
    if not opened:
        return ("red", False)
    if active:
        return ("amber", False)
    return ("green", False)


def tower_ticker():
    """Re-evaluate + apply tower state ~3 Hz; only touch GPIO when it changes."""
    global _tower_last
    while not stop_event.is_set():
        if tower is not None:
            state = _tower_state()
            if state != _tower_last:
                try:
                    tower.apply(*state)
                except Exception as e:
                    print("[tower] apply error: %s" % e)
                _tower_last = state
        time.sleep(0.3)


# ─── E-stop sense input (optional) ───────────────────────────────────────────
def setup_estop(ecfg):
    global estop_btn
    if not ecfg:
        return
    if not HAVE_GPIO:
        print("[gpio] gpiozero unavailable; E-stop sense disabled.")
        return
    try:
        pin = ecfg["pin"]
        pull = ecfg.get("pull", "up")
        bounce = float(ecfg.get("bounce", 0.02))
        cmd = ecfg.get("cmd")  # optional G-code to also send on press (e.g. "M112")
        nc = bool(ecfg.get("nc", False))  # True = normally-closed contact (opens when pressed)
        estop_btn = Button(pin, pull_up=(pull == "up"), bounce_time=bounce)
        if nc:
            # NC safety contact: closed (gpiozero "active") at rest, opens when the mushroom is hit.
            estop_btn.when_released = functools.partial(_on_estop, True, cmd)
            estop_btn.when_pressed  = functools.partial(_on_estop, False, None)
            _on_estop(not estop_btn.is_active, None)   # seed current state (contact open == pressed)
        else:
            estop_btn.when_pressed  = functools.partial(_on_estop, True, cmd)
            estop_btn.when_released = functools.partial(_on_estop, False, None)
        print("[gpio] E-stop sense GPIO%s (pull=%s, nc=%s, cmd=%s)" % (pin, pull, nc, cmd))
    except Exception as e:
        print("[gpio] E-stop sense setup failed: %s" % e)


def _on_estop(pressed, cmd):
    global _estop
    with io_lock:
        _estop = pressed
    schedule_broadcast(json.dumps({"_rmr": "estop", "pressed": pressed}))
    print("[gpio] E-STOP %s" % ("PRESSED" if pressed else "released"))
    if pressed and cmd:
        write_serial(cmd, source="estop")


# ─── Optional static file server (serve the HTML UI over http://) ────────────
def start_http(directory, port):
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print("[http] serving %s at http://0.0.0.0:%d/" % (directory, port))
    return httpd


def note_client_message(ws, text):
    """True when text is a page's meta message, which never goes to the serial port. G-code never
    starts with '{'; a '{' line that is not one of ours is dropped too, not sent to Marlin."""
    if not text.lstrip().startswith("{"):
        return False
    try:
        m = json.loads(text)
    except ValueError:
        return True
    if isinstance(m, dict) and m.get("_rmr") == "state":
        client_busy[ws] = bool(m.get("busy"))
    return True


# ─── WebSocket handler ───────────────────────────────────────────────────────
async def ws_handler(websocket, *args):  # *args: older websockets passes `path`
    clients.add(websocket)
    peer = getattr(websocket, "remote_address", ("?",))[0]
    print("[ws] client connected (%s); %d total" % (peer, len(clients)))
    # Greet with current serial status
    try:
        await websocket.send(json.dumps({
            "_rmr": "status",
            "serial": "open" if (ser is not None and ser.is_open) else "closed",
            "port": cfg.port,
            "caps": ["state"],   # this bridge reads {"_rmr":"state"} (issue #218)
        }))
        async for message in websocket:
            cmd = message if isinstance(message, str) else message.decode("utf-8", "replace")
            if note_client_message(websocket, cmd):
                continue
            write_serial(cmd, source="ws")
    except Exception:
        pass
    finally:
        clients.discard(websocket)
        client_busy.pop(websocket, None)
        print("[ws] client disconnected (%s); %d total" % (peer, len(clients)))


# ─── Main ────────────────────────────────────────────────────────────────────
async def main():
    global loop
    loop = asyncio.get_running_loop()

    # Clean shutdown on SIGINT/SIGTERM
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows dev machines

    io = load_io_config(cfg.io)
    threading.Thread(target=serial_reader, daemon=True).start()
    setup_buttons(io.get("buttons"))
    setup_tower(io.get("tower"))
    setup_estop(io.get("estop"))
    if tower is not None:
        threading.Thread(target=tower_ticker, daemon=True).start()

    if cfg.serve_dir:
        start_http(cfg.serve_dir, cfg.http_port)

    print("[ws] listening on ws://%s:%d" % (cfg.ws_host, cfg.ws_port))
    async with websockets.serve(ws_handler, cfg.ws_host, cfg.ws_port, ping_interval=20):
        # Run until stop_event is set (signal handler), polling cooperatively.
        while not stop_event.is_set():
            await asyncio.sleep(0.25)

    print("\n[bridge] shutting down")
    with serial_lock:
        try:
            if ser is not None and ser.is_open:
                ser.close()
        except Exception:
            pass


def parse_args():
    p = argparse.ArgumentParser(description="RMR serial <-> WebSocket bridge")
    p.add_argument("--port", default="/dev/rmr-mega",
                   help="serial device for the Mega (default: /dev/rmr-mega; see udev rule)")
    p.add_argument("--baud", type=int, default=250000, help="serial baud (Marlin default 250000)")
    p.add_argument("--ws-host", default="0.0.0.0", help="WebSocket bind host")
    p.add_argument("--ws-port", type=int, default=8765, help="WebSocket port")
    p.add_argument("--serve-dir", default=None,
                   help="if set, also serve this directory over HTTP (e.g. the repo root)")
    p.add_argument("--http-port", type=int, default=8000, help="static HTTP port (with --serve-dir)")
    p.add_argument("--io", default=None,
                   help="path to a GPIO config JSON (buttons + status tower + e-stop sense)")
    return p.parse_args()


if __name__ == "__main__":
    cfg = parse_args()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
