# RMR Integrated Touch Panel (Raspberry Pi)

Turns a Raspberry Pi + a generic 10″ touchscreen into a built-in operator panel
for the machine. The Pi owns the USB link to the Arduino Mega (Marlin); the
existing web UI (`RMR_Controller.html`) runs in a browser on the Pi and talks to
the Pi over a **WebSocket** instead of the browser's Web Serial API.

Because the browser no longer needs Web Serial, **any browser works** — Firefox
or a lightweight WebKit kiosk (`cog`) — no Chromium requirement.

## Architecture

```
   10" touch  (HDMI video  +  USB touch-HID)
        │
   ┌────┴─────┐   browser (Firefox / cog kiosk) → RMR_Controller.html?transport=ws
   │  Pi 4/5  │        │  WebSocket ws://localhost:8765   (+ static HTTP :8000)
   │          │   ┌────┴─────────────┐
   │          │   │ rmr_bridge.py    │  owns the serial port, fans out to all clients
   │          │   └────┬─────────────┘
   └────┬─────┘        │
        │ USB  /dev/rmr-mega @ 250000     ← the only control link
   ┌────┴─────┐
   │ Mega 2560│   Marlin  (M750 drives the spincoater)
   └────┬─────┘
        │ Serial2 UART (pins 16/17, 115200)
   ┌────┴─────┐
   │ ODrive S1│──▶ motor
   └────┬─────┘
        ╎ USB → Pi  (OPTIONAL: /dev/rmr-odrive, for odrivetool / debugging only)
```

The ODrive is driven **by the Mega** over Serial2 (`M750/M751/M752`), so run-time
control is one USB link (Pi → Mega). Wiring the ODrive's USB to the Pi is only a
convenience for `odrivetool` during calibration/tuning — it is not used at run time.

## Hardware

- **Raspberry Pi 4 (2–4 GB) or Pi 5** — a Pi 3 struggles with a browser UI.
- **10″ touchscreen:** HDMI video + **USB-HID capacitive touch** is the most
  universal (plug-and-play on Linux, no driver). Avoid panels that need a vendor
  touch driver.
- Its own solid **5 V / 3 A** supply for the Pi (don't power it from the Mega).
- Active cooling if it lives in an enclosure.

## One-time setup

### 1. OS + repo
Install Raspberry Pi OS (64-bit, Bookworm). Clone this repo, e.g. to
`/home/pi/Robot-MakingRobot`.

### 2. Python bridge dependencies (isolated venv)
```bash
cd /home/pi/Robot-MakingRobot/pi-panel
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
`gpiozero` (for physical buttons) is already present in Raspberry Pi OS.

### 3. Stable serial device names (udev)
So the Mega is always `/dev/rmr-mega` regardless of USB enumeration order:
```bash
# find your board's USB IDs first:
lsusb
udevadm info -a -n /dev/ttyACM0 | grep -E 'idVendor|idProduct'
# edit 99-rmr-serial.rules to match, then:
sudo cp 99-rmr-serial.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```
Confirm `ls -l /dev/rmr-mega` now points at the Mega.

### 4. Test the bridge manually
```bash
cd /home/pi/Robot-MakingRobot
pi-panel/.venv/bin/python pi-panel/rmr_bridge.py \
    --port /dev/rmr-mega --baud 250000 \
    --serve-dir "$PWD" --http-port 8000 --ws-port 8765
```
You should see `[serial] opened /dev/rmr-mega` and `[ws] listening …`. Open a
browser on the Pi to **`http://localhost:8000/RMR_Controller.html`** — it
auto-detects HTTP and connects to the bridge; the console shows
`Bridge connected`.

### 5. Run on boot (systemd)
```bash
# edit paths/User in rmr-bridge.service if needed, then:
sudo cp pi-panel/rmr-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rmr-bridge.service
journalctl -u rmr-bridge -f      # watch it
```

### 6. Kiosk browser autostart (no Chromium needed)
Point a full-screen browser at the UI. Two good options:

- **Firefox kiosk:** `firefox --kiosk "http://localhost:8000/RMR_Controller.html"`
- **cog** (lean WPE WebKit): `sudo apt install cog && cog "http://localhost:8000/RMR_Controller.html"`

Autostart on Bookworm (labwc/wayfire desktop) — add to `~/.config/wayfire.ini`:
```ini
[autostart]
panel = firefox --kiosk http://localhost:8000/RMR_Controller.html
blank = swayidle timeout 0 'true'    # or disable screen blanking via raspi-config
```
On the older X11 desktop, put a `.desktop` launcher in `~/.config/autostart/`.
Disable screen blanking with `raspi-config` → Display, or `xset s off -dpms` (X11).

### 7. On-screen keyboard (touch input for text fields)
The panel has text/number fields (raw G-code, preset names, tunables), so add a
virtual keyboard:
- Wayland (Bookworm): `sudo apt install wvkbd` (or `squeekboard`)
- X11: `sudo apt install onboard` (or `matchbox-keyboard`)

## Using it

- **On the Pi:** `http://localhost:8000/RMR_Controller.html` (bridge mode auto-selected).
- **Touch layout:** swap the URL to `RMR_Touch.html` for the big-target UI (same
  bridge; it has the Process Sequencer as its **Recipe** tab).
- **From a phone/laptop on the LAN:** `http://<pi-hostname>.local:8000/RMR_Controller.html`
  — multiple clients can be connected at once; every serial line and every command
  (including physical-button presses) is mirrored to all of them.

### Transport selection (URL)
The page auto-picks its transport, override with query params:
| Situation | Transport | How |
|---|---|---|
| Served over `http(s)://` (the Pi) | WebSocket bridge | automatic |
| Opened as a local `file://` (dev laptop) | Web Serial | automatic |
| Force bridge | WebSocket | `?transport=ws` |
| Force Web Serial | Web Serial | `?transport=serial` |
| Bridge on another host/port | WebSocket | `?ws=ws://host:8765` |

## GPIO I/O: buttons, status tower, E-stop sense

All optional and off unless configured. Copy `rmr_io.example.json` to `rmr_io.json`,
edit, and it's passed with `--io …/rmr_io.json` (the systemd unit already does).
Pins are BCM GPIO numbers.

**Physical buttons (gloves / dirty hands)** — momentary buttons mapped to G-code.
Default wiring is button → GPIO pin and GND (internal pull-up, active-low). Each
press calls the same path as the UI and is echoed to every connected screen.

**Status tower + buzzer** — a red/amber/green tower light and buzzer driven from
machine state the bridge infers off the serial stream + connection:

| State | Tower | Meaning |
|---|---|---|
| `green` | steady | connected and idle/ready |
| `amber` | steady | active — a command was sent in the last ~1.5 s |
| `red` + buzzer | pulsing | Marlin error/kill, or E-stop asserted |
| `red` | steady | serial link down (Mega unplugged / not responding) |

Omit any channel you don't have; use `"active_high": false` for active-LOW relay
or driver boards. Tower lights are usually 12/24 V — switch them from the Pi's
3.3 V GPIO through a transistor/MOSFET or relay, don't drive them directly.

**E-stop sense** — wire the auxiliary contact of your hardware E-stop to a GPIO
input so software knows it was hit: the tower goes red + buzzer, the UI is told
(`{"_rmr":"estop"}`), and if `"cmd"` is set it also sends it (e.g. `M112`). Match
`"pull"` to your contact wiring.

```json
{
  "buttons": [ { "pin": 17, "name": "estop", "cmd": "M112", "pull": "up" } ],
  "tower":   { "red": 5, "amber": 6, "green": 13, "buzzer": 26, "active_high": true },
  "estop":   { "pin": 20, "pull": "up", "cmd": "M112" }
}
```

> ⚠️ **SAFETY — the GPIO E-stop (button *or* sense) is a software convenience,
> not a safety interlock.** It sends/echoes `M112` and only works if the Pi, USB
> link, and firmware are all alive. For real safety, ALSO fit a hardware E-stop
> that physically cuts stepper-driver / ODrive motor power, independent of the Pi.
> Wire that hardware E-stop's aux contact to the `estop` sense input so the panel
> annunciates it.

## How it works (protocol)

- **Data plane** (line-oriented, 1:1 with serial): browser → bridge sends a raw
  command string (bridge appends `\n`); bridge → browser sends one raw serial
  line per message, which the UI feeds to its existing `processLine()`.
- **Meta plane** (JSON, begins with `{` and carries `_rmr`): `status` (serial
  open/closed), `tx` (every write, echoed to all clients with its source), `button`
  (a physical button fired), `estop` (sense input changed), `error`.
- The bridge holds the port open persistently, so the Mega DTR-resets **once** at
  bridge start rather than on every UI connect. It auto-reconnects the serial port
  (with backoff) if the USB drops, and the UI auto-reconnects the WebSocket.

## Troubleshooting

- **UI says "serial closed":** check `/dev/rmr-mega` exists (udev), the Mega is
  powered, and no other program holds the port. `journalctl -u rmr-bridge -f`.
- **Can't reach from another device:** the bridge binds `0.0.0.0`; check the Pi's
  firewall and that you used the Pi's hostname/IP, ports 8000 + 8765.
- **Buttons / tower / E-stop do nothing:** `gpiozero` present and `--io` pointing
  at your `rmr_io.json`? Correct BCM pin numbers and `active_high` polarity? Watch
  the bridge log at startup for `[gpio] status tower …`, `[gpio] E-stop sense …`,
  and per-button `[gpio] … -> …` lines.
- **Spincoater tuning:** connect `odrivetool` to `/dev/rmr-odrive` (USB) — the
  Mega's Serial2 link is separate and can stay connected.
