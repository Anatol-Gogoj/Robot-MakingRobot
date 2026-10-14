# RMR Integrated Touch Panel (Raspberry Pi)

Turns a Raspberry Pi and a generic 10″ touchscreen into a built-in operator panel for the
machine. The Pi owns the USB link to the Arduino Mega (Marlin). The web UI runs in a browser on
the Pi and talks to the Pi over a **WebSocket** instead of the browser's Web Serial API.
`RMR_Touch.html` is the operator page; `RMR_Controller.html` works the same way and is the one to
open for debugging and tuning.

Because the browser no longer needs Web Serial, **any browser works**, such as Firefox or a
lightweight WebKit kiosk (`cog`). Chromium is not required.

The Pi panel is not in service on the machine yet; the instructions below have not been run end
to end on the final hardware.

## Architecture

```
   10" touch  (HDMI video  +  USB touch-HID)
        │
   ┌────┴─────┐   browser (Firefox / cog kiosk) → RMR_Touch.html  (bridge mode auto-selected)
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

The Mega drives the ODrive over Serial2 (`M750` to `M754`), so run-time control is one USB link
(Pi to Mega). Wiring the ODrive's USB to the Pi is only a convenience for `odrivetool` during
calibration and tuning; it is not used at run time.

## Hardware

- **Raspberry Pi 4 (2 to 4 GB) or Pi 5.** A Pi 3 struggles with a browser UI.
- **10″ touchscreen:** HDMI video with **USB-HID capacitive touch** is the most universal
  (plug-and-play on Linux, no driver). Avoid panels that need a vendor touch driver.
- A separate **5 V / 3 A** supply for the Pi (do not power it from the Mega).
- Active cooling if it lives in an enclosure.

## One-time setup

### 1. OS and repo
Install Raspberry Pi OS (64-bit, Bookworm). Clone this repo, for example to
`/home/pi/Robot-MakingRobot`.

### 2. Python bridge dependencies (isolated venv)
```bash
cd /home/pi/Robot-MakingRobot/pi-panel
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
`requirements.txt` installs `pyserial` and `websockets`. `gpiozero` (for physical buttons, the
status tower and the E-stop sense) is already present in Raspberry Pi OS; without it the bridge
runs with GPIO disabled.

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
The shipped rules cover a genuine Mega (2341:0042) and CH340 clones (1a86:7523); other IDs are
listed as comments. Confirm that `ls -l /dev/rmr-mega` now points at the Mega.

### 4. Test the bridge manually
```bash
cd /home/pi/Robot-MakingRobot
pi-panel/.venv/bin/python pi-panel/rmr_bridge.py \
    --port /dev/rmr-mega --baud 250000 \
    --serve-dir "$PWD" --http-port 8000 --ws-port 8765
```
You should see `[serial] opened /dev/rmr-mega @ 250000` and `[ws] listening on ws://0.0.0.0:8765`.
Open a browser on the Pi at **`http://localhost:8000/RMR_Touch.html`**. The page detects HTTP and
connects to the bridge, and its console shows `Bridge connected`.

Flags: `--port` (default `/dev/rmr-mega`), `--baud` (250000), `--ws-host` (`0.0.0.0`),
`--ws-port` (8765), `--serve-dir` (off unless given), `--http-port` (8000), and `--io` (path to
the GPIO config, off unless given).

### 5. Run on boot (systemd)
```bash
# edit paths/User in rmr-bridge.service if needed, then:
sudo cp pi-panel/rmr-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rmr-bridge.service
journalctl -u rmr-bridge -f      # watch it
```
The unit passes `--io pi-panel/rmr_io.json`. If that file does not exist, the bridge says so and
runs without GPIO.

### 6. Kiosk browser autostart (no Chromium needed)
Point a full-screen browser at the UI. Two options:

- **Firefox kiosk:** `firefox --kiosk "http://localhost:8000/RMR_Touch.html"`
- **cog** (lean WPE WebKit): `sudo apt install cog && cog "http://localhost:8000/RMR_Touch.html"`

Autostart on Bookworm (labwc/wayfire desktop): add to `~/.config/wayfire.ini`:
```ini
[autostart]
panel = firefox --kiosk http://localhost:8000/RMR_Touch.html
blank = swayidle timeout 0 'true'    # or disable screen blanking via raspi-config
```
On the older X11 desktop, put a `.desktop` launcher in `~/.config/autostart/`. Disable screen
blanking with `raspi-config` → Display, or `xset s off -dpms` (X11).

### 7. On-screen keyboard (touch input for text fields)
The panel has text and number fields (raw G-code, preset names, tunables), so add a virtual
keyboard:
- Wayland (Bookworm): `sudo apt install wvkbd` (or `squeekboard`)
- X11: `sudo apt install onboard` (or `matchbox-keyboard`)

## Using it

- **On the Pi:** `http://localhost:8000/RMR_Touch.html` (bridge mode is selected automatically).
  The Process Sequencer is its **Recipe** tab and the Run Log its **Log** tab.
- **Debugging and tuning:** swap the URL to `RMR_Controller.html` (same bridge).
- **From a phone or laptop on the LAN:** `http://<pi-hostname>.local:8000/RMR_Touch.html`.
  Several clients can be connected at once; every serial line and every command (including
  physical-button presses) is mirrored to all of them.

### Transport selection (URL)
The page picks its transport automatically; query parameters override it:

| Situation | Transport | How |
|---|---|---|
| Served over `http(s)://` (the Pi) | WebSocket bridge | automatic |
| Opened as a local `file://` (dev laptop) | Web Serial | automatic |
| Force bridge | WebSocket | `?transport=ws` |
| Force Web Serial | Web Serial | `?transport=serial` |
| Bridge on another host/port | WebSocket | `?ws=ws://host:8765` |

`RMR_Controller.html` also has a **Web Serial / Pi Bridge** selector in its header that overrides
the automatic choice without a URL change. The choice is remembered (`localStorage`), so a dev
laptop served over `http://localhost` can switch to Web Serial once and stay there. The selector
is disabled while connected, and "Web Serial" shows as `(n/a)` in insecure contexts (plain
`http://` to a LAN IP), where the browser does not expose the API; use `localhost`, `https://` or
a local `file://` instead. `RMR_Touch.html` has no selector; use the URL parameters.

## GPIO I/O: buttons, status tower, E-stop sense

All of it is optional and off unless configured. Copy `rmr_io.example.json` to `rmr_io.json`,
edit it, and pass it with `--io …/rmr_io.json` (the systemd unit already does). Pins are BCM GPIO
numbers.

**Physical buttons (gloves or dirty hands):** momentary buttons mapped to G-code. The default
wiring is button between the GPIO pin and GND (internal pull-up, active-low); `bounce` sets the
debounce time in seconds. Each press goes through the same write path as the UI and is echoed to
every connected screen. A `cmd` may hold several lines (`\n` inside the JSON string). The example
`home_all` button sends `G28` and then `M118 RMR:HOMED_ALL`. Marlin prints that marker back only
after the homing has finished, and every browser UI uses it to unlock the Process Sequencer's
homing gate (Syringe, UV and Stamp stay locked until a full home).

**Status tower and buzzer:** a red/amber/green tower light and buzzer, driven from machine state
the bridge infers from the serial stream and the connection:

| State | Tower | Meaning |
|---|---|---|
| `green` | steady | connected and idle |
| `amber` | steady | active: a command was sent in the last 1.5 s |
| `red` + buzzer | red steady, buzzer beeping | E-stop sense asserted; a Marlin error (an `Error:` or `!!` line, `kill()`, "emergency"), held 5 s after the last one; or `MOTOR POWER LOST`, latched until `Motor power restored` or a firmware restart |
| `red` | steady | serial link down (Mega unplugged or not responding) |

Omit any channel you don't have, and use `"active_high": false` for active-LOW relay or driver
boards. Tower lights are usually 12 or 24 V: switch them from the Pi's 3.3 V GPIO through a
transistor, MOSFET or relay, and do not drive them directly.

**E-stop sense:** wire the auxiliary contact of the hardware E-stop to a GPIO input so the
software knows it was hit. The tower goes red with the buzzer, the UI is told
(`{"_rmr":"estop"}`), it re-locks the homing gate and fails any running sequence, and if `"cmd"`
is set the bridge also sends it (for example `M112`). Match `"pull"` to the contact wiring. Set
`"nc": true` for a normally-closed contact, which is the safer choice: an open contact reads as
pressed, so a cut wire also raises the alarm. The Mega also prints `MOTOR POWER LOST` when the
motor contactor drops, which latches the tower red even without this input wired.

A trimmed `rmr_io.json` (see `rmr_io.example.json` for all four example buttons):

```json
{
  "buttons": [
    { "pin": 17, "name": "estop",    "cmd": "M112", "pull": "up", "bounce": 0.03 },
    { "pin": 22, "name": "home_all", "cmd": "G28\nM118 RMR:HOMED_ALL", "pull": "up", "bounce": 0.05 }
  ],
  "tower":   { "red": 5, "amber": 6, "green": 13, "buzzer": 26, "active_high": true },
  "estop":   { "pin": 20, "pull": "up", "nc": true, "cmd": "M112" }
}
```

> **SAFETY: the GPIO E-stop (button or sense) is a software convenience, not a safety
> interlock.** It sends or echoes `M112`, and it only works if the Pi, the USB link and the
> firmware are all alive. Also fit a hardware E-stop that physically cuts stepper-driver and
> ODrive motor power, independent of the Pi, and wire its aux contact to the `estop` sense input
> so the panel reports it.

## How it works (protocol)

- **Data plane** (line-oriented, 1:1 with serial): the browser sends the bridge a raw command
  string (the bridge appends `\n`); the bridge sends the browser one raw serial line per message,
  which the UI feeds to its `processLine()`.
- **Meta plane** (JSON, starts with `{` and carries `_rmr`):
  - `status`: serial port open or closed
  - `tx`: every write, echoed to all clients with its source (`ws`, `button:NAME` or `estop`)
  - `button`: a physical button fired
  - `estop`: the sense input changed
  - `motorpower`: `MOTOR POWER LOST` or `Motor power restored` was seen (the UIs act on the serial line itself)
  - `error`: a bridge error
- The bridge holds the port open, so the Mega resets (DTR) **once** at bridge start rather than
  on every UI connect. It reopens the serial port with backoff (1 s, growing to at most 5 s
  between tries) if the USB drops, and the UI retries the WebSocket every 2 s.

## Troubleshooting

- **UI says "serial closed":** check that `/dev/rmr-mega` exists (udev), that the Mega is
  powered, and that no other program holds the port. Watch `journalctl -u rmr-bridge -f`.
- **Can't reach the panel from another device:** the bridge binds `0.0.0.0`. Check the Pi's
  firewall and that you used the Pi's hostname or IP and ports 8000 and 8765.
- **Buttons, tower or E-stop do nothing:** is `gpiozero` present, and does `--io` point at your
  `rmr_io.json`? Are the BCM pin numbers and `active_high` polarity right? At startup the bridge
  log shows `[gpio] status tower …`, `[gpio] E-stop sense …` and a `[gpio] … -> …` line per button.
- **Spincoater tuning:** connect `odrivetool` to `/dev/rmr-odrive` (USB). The Mega's Serial2 link
  is separate and can stay connected.
