# Remote Bench Laptop — Setup Plan

**Goal:** the Ubuntu laptop becomes the machine's permanent operator console. Colleagues stand at it and
drive the robot through the HTML UIs. The owner shadows the same desktop remotely and does firmware work.

**Date:** 2026-08-12 · **Script:** `provision-bench-laptop.sh` v1.1 · **Target:** Ubuntu 24.04 LTS

---

## 1. The constraint that decides the architecture

**A serial port has exactly one holder.**

If the owner opens Chrome in a private remote session while a colleague has the UI open on the console,
one of them gets `/dev/rmr-mega` and the other gets an error. Two desktops means two browsers means a
fight over the port.

So the remote desktop must **shadow the physical display `:0`** — one desktop, one Chrome, one serial
connection, both people looking at it. This is not a convenience choice, and it should not be "improved"
into per-user sessions later.

It also happens to be what you want operationally: when the owner is driving and something goes wrong,
the colleague standing at the machine sees exactly what the owner sees.

```
   owner  ──(existing remote access)──▶  RHEL9 benchtop
                                              │
                                              │  LAN
                                              ▼
                                    Ubuntu 24.04 laptop  ──USB──▶  Mega 2560
                                     (rmr-bench.local)   ──USB──▶  ODrive S1
                                              │
                                     ┌────────┴────────┐
                                colleague          owner
                              (at the keyboard)  (shadowing :0)
```

### Access paths

| Path | What it is | When it is used |
|---|---|---|
| **NoMachine** | Shadows `:0`. TCP 4000. Logs in with a normal system account. | The daily driver. Much better interactivity than VNC over a WAN link. |
| **x11vnc** | Shadows `:0`. TCP 5900, localhost-bound by default. | The baseline that always works. Reach it through the SSH tunnel. |
| **Direct SSH** | RHEL9 → laptop by IP | Builds, flashing, logs, anything without a GUI. |
| **Reverse tunnel** | Laptop dials **out** to RHEL9; connect to `localhost:2222` there | Resilience. Survives DHCP changes, Wi-Fi reconnects and NAT. |

Two remote desktop paths on purpose: NoMachine is better but is a third-party `.deb` whose download URL
moves between versions. x11vnc comes from the Ubuntu archive and will still be there in five years. If
NoMachine fails to install, nothing is lost.

### Autologin is now load-bearing

`x11vnc` and NoMachine both attach to a desktop that must already exist. After an unattended reboot with
nobody in the room, there is no desktop unless the laptop logs itself in. So autologin is not an optional
convenience any more — without it, a power blip makes the console unreachable until someone walks over.

The trade is real and worth stating: **anyone with physical access to the laptop gets a logged-in desktop.**
On a lab bench next to the machine they are already able to drive, that is an acceptable trade. Say no by
setting `ENABLE_GUI_REMOTE=false`, and accept that the HTML UIs then cannot be used.

---

## 2. The browser

The HTML UIs need the **Web Serial API**. This is not negotiable and it narrows the field to one option.

| Browser | Web Serial | Verdict |
|---|---|---|
| **Google Chrome (`.deb`)** | Native | **Use this.** What the UIs were written and tested against. |
| Chromium (snap) | Native, but | Snap confinement blocks `/dev/tty*`, so the port list comes back empty. |
| Firefox (stock) | None | Mozilla has declined to implement it. |
| Firefox + `WebSerial for Firefox` polyfill | Shimmed | Fallback only — see below. |

### On the Firefox polyfill

`WebSerial for Firefox` (kuba2k2) exists and does work. WebExtensions has no serial API, so by
architectural necessity the extension hands off to a **native helper** on the host that opens the port on
its behalf — it is "Firefox + extension + a native binary", not "Firefox gained Web Serial".

**Do not put it in the critical path here**, for a reason specific to this machine: connecting the browser
pulses DTR, the ATmega16U2 resets the Mega, and the spincoater datum in RAM is destroyed. That is issue
**#54**, and gotcha **#6** is built on the same behaviour. Both UIs and the documented M112 recovery
procedure assume it. A polyfill routing `setSignals()` through a native helper is exactly where DTR timing
quietly diverges from Chrome's native implementation, and the failure would not be an error message — it
would be "the datum sometimes survives a reconnect", which costs a day to chase. Same class of risk at
250000 baud.

It buys nothing: the Chrome install is two lines in the script.

Keep it as the fallback for the case where Chrome is blocked by lab policy or the Google repo is
unreachable. If anyone does use it, the acceptance test is specifically:

1. Does the Mega reset on connect, as it does under Chrome?
2. Does 250000 baud stream a full `DemoProgram.gcode` with no lost lines?

Not merely "does it connect".

---

## 3. Owner: prepare the ShareDrive (about 10 minutes)

**Step 1 — get your public key.** On the RHEL9 box:

```bash
cat ~/.ssh/id_ed25519.pub
```

If there is no key, make one: `ssh-keygen -t ed25519`.

**Step 2 — edit the CONFIG block** at the top of `provision-bench-laptop.sh`:

| Field | Value |
|---|---|
| `OWNER_SSH_PUBKEY` | The key from Step 1. **Mandatory** — the script refuses to run without it. |
| `VNC_PASSWORD` | Set it. Both you and the colleagues need to know it. |
| `VNC_LAN_ACCESS` | `false` (localhost + SSH tunnel) or `true` (open on the LAN, weak transport security). |
| `NOMACHINE_DEB_URL` | Check the current link at <https://downloads.nomachine.com> — version numbers move. Empty to skip. |
| `RHEL9_HOST`, `RHEL9_USER` | The benchtop machine, for the reverse tunnel. Empty to skip. |
| `SHARE_UNC` | `//<ip>/ShareDrive` — where the report gets written back. |

**Step 3 — put a copy of the repo on the ShareDrive.** The laptop has no GitHub credentials, so ship
history instead of asking it to authenticate:

```bash
git bundle create Robot-MakingRobot.bundle --all
```

Drop that at `RMR/Robot-MakingRobot.bundle` on the share. One file, full history, all branches, no secrets.
The desktop launchers are built from the checkout, so this also decides where the UIs live.

**Step 4 — drop the script on the ShareDrive** next to the bundle, and tell the colleague where it is.

---

## 4. Colleague: run it (about 25 minutes, mostly waiting)

Written in ASD-STE100, to match the run sheet.

> **CAUTION — DAMAGE TO EQUIPMENT**
> Do not send commands to the robot during this task. This task only prepares the laptop.
> The script does not change the firmware on the machine.

**Step 1** — Put the laptop near the machine. Connect it to mains power. Connect it to the network.
A network cable is better than Wi-Fi.

**Step 2** — Connect the USB cable from the laptop to the Mega 2560.

**Step 3** — Connect the USB cable from the laptop to the native USB port of the ODrive.

**Step 4** — Copy the file `provision-bench-laptop.sh` from the ShareDrive to the Desktop.

**Step 5** — Open a terminal. Push `Ctrl` + `Alt` + `T`.

**Step 6** — Type this command and push Enter:

```bash
bash ~/Desktop/provision-bench-laptop.sh
```

**Step 7** — Type your password when the laptop asks for it. Then wait. The script writes `[ ok ]` for
each part that it completes.

**Step 8** — Read the last lines. The script tells you where it put the report.

**Step 9** — Type `sudo reboot` and push Enter. The laptop must restart before the desktop access works.

**Step 10** — After the restart, make sure that the laptop shows the desktop without a password.

**Step 11** — Find the two icons on the Desktop: **RMR Touch Controller** and **RMR Controller (full)**.
Push one of them two times. Chrome must open the interface.

**Step 12** — Tell the owner that the report is ready.

**Step 13** — Leave the laptop switched on. Leave it connected to mains power and to the network.
You can close the lid. The laptop does not go to sleep.

---

## 5. Owner: take over (about 5 minutes)

**Step 1 — read the report** on the ShareDrive at `RMR/bench-laptop/`. It carries the laptop IP, the SSH
host key fingerprints, the serial devices found, the toolchain versions, the Chrome version, and the test
build result.

**Step 2 — connect over SSH** from the RHEL9 box, checking the fingerprint against the report:

```bash
ssh <user>@<laptop-ip>
```

**Step 3 — authorize the tunnel key.** The report contains the line ready to paste, with the real key in
it. `autossh` retries every 15 s, so the tunnel comes up by itself:

```bash
echo 'ssh-ed25519 AAAA...  rmr-bench-tunnel' >> ~/.ssh/authorized_keys
```

**Step 4 — get the desktop.**

NoMachine, if it installed — point the client at `<laptop-ip>:4000` and log in as the colleague's system
account. It attaches to the physical desktop automatically.

x11vnc, always available:

```bash
ssh -L 5900:localhost:5900 <user>@<laptop-ip>
```

Then point a VNC client at `localhost:5900` with the password from `VNC_PASSWORD`.

**Step 5 — confirm the console works end to end:**

```bash
ls -l /dev/rmr-mega /dev/rmr-odrive
google-chrome --version
pio device list
```

Then, in the remote desktop, open **RMR Controller (full)**, connect at 250000 baud, and send `M119`.

---

## 6. What the script does

| Phase | Why it is there |
|---|---|
| **Power** | Stops suspend on lid close and on idle. A laptop that sleeps is a laptop you cannot reach. Done *first*, so a long install cannot be interrupted by a suspend. |
| **Packages** | SSH, git, PlatformIO prerequisites, CIFS, `picocom`, `x11vnc`, `autossh`. Also removes **brltty**, which claims CH340 USB serial adapters on Ubuntu and silently breaks Arduino serial. |
| **Hostname / network** | Sets `rmr-bench`, enables mDNS, and makes every saved network connection **system-wide**. A user-owned Wi-Fi profile only connects after someone logs in — on a headless bench that means unreachable after a reboot. |
| **Serial** | `udev` rules give stable `/dev/rmr-mega` and `/dev/rmr-odrive` names, and set `ID_MM_DEVICE_IGNORE` so **ModemManager** stops probing them. That probe corrupts the first seconds of a session and can fail an upload. Adds the user to `dialout`. |
| **SSH** | Installs the owner key, enables sshd at boot, sets keepalives so long sessions survive idle NAT timeouts. |
| **PlatformIO** | Official installer into its own venv. Ubuntu 24.04 enforces PEP 668, so a system-wide `pip install platformio` is refused. |
| **odrivetool** | Via `pipx`. **Non-fatal** — see the risks below. |
| **ShareDrive** | CIFS mount, so the report is delivered without the colleague touching anything. |
| **Repo + test build** | Clones from the bundle, checks out the stack tip, runs `pio run -e mega2560`. **This is the acceptance test** — it proves the toolchain works while the colleague is still standing there. |
| **Browser** | Google Chrome from the `.deb`, plus two Desktop launchers that open the UIs in app mode. Without this the laptop cannot be an operator console at all. |
| **Desktop** | Forces Xorg, enables autologin, runs `x11vnc` shadowing `:0`. |
| **NoMachine** | Optional high-performance desktop, also shadowing `:0`. |
| **Tunnel** | Generates a dedicated keypair, installs an `autossh` service, prints the public key into the report. |
| **Report** | Everything above, written to the ShareDrive. |

Two design choices worth stating plainly:

- **The script does not use `set -e`.** It always reaches its report phase. A provisioning script that dies
  silently at step 9 of 15 leaves a non-expert colleague with a half-built machine and no information.
  Anything that matters is wrapped and recorded instead.
- **The script never uploads firmware.** It builds, but does not flash. Nothing on the robot changes.

---

## 7. Risks, and what happens if they land

| Risk | Odds | What you get | Fallback |
|---|---|---|---|
| **No internet on the laptop** | Medium | apt, Chrome, PlatformIO and NoMachine all fail | The script says so clearly. Fix the network and re-run — it is idempotent. |
| **`odrivetool` will not install on Python 3.12** | **High** | Run sheet Task 2 has no CLI tool | Non-fatal by design. Remotely: build a Python 3.11 venv, or do Task 2 through the ODrive web GUI. Task 2 is the highest-value bench task, so fix this first. |
| **NoMachine URL has moved** | **High** | No NoMachine | x11vnc still works. Get the current link and install it remotely later. |
| **Chrome fails to install** | Low | No operator console at all | This one is worth stopping for. Re-run once the network is fixed. Firefox + polyfill only as a last resort, with the DTR test in §2. |
| **Laptop IP changes** | Medium | Direct SSH breaks | The reverse tunnel. Also ask for a DHCP reservation. |
| **`/dev/rmr-*` symlinks absent** | Low | Unknown USB vendor ID | The report lists every device with its real vid:pid. Send one `udevadm` line and fix the rule remotely. |
| **Reboot with nobody there** | Medium | — | Autologin restores the desktop; sshd, tunnel, VNC and NoMachine are all `systemctl enable`d. |
| **VNC does not start after reboot** | Low | No desktop, SSH still fine | `journalctl -u rmr-x11vnc -b`. Usually the X authority path — fixable remotely. |

---

## 8. Safety — remote work on a live machine

This is a real machine with a 5000 RPM chuck, a UV lamp, and a solenoid valve. The mechanical E-stop is
**issue #20 and does not exist yet**. Once this is provisioned, the owner can flash firmware and command
motion from another building — and now also drive the full operator UI.

> **WARNING — INJURY TO PERSONS**
> Do not command motion when no person is in the room with the machine.
> Motion commands are `G28`, `G1`, `M280`, `M750`, `M752` and any G-code program.
> Agree a time with a colleague before you send them.

The shared desktop helps here rather than hurting: the colleague at the keyboard sees every command the
owner sends, and can hit the physical power switch. Take advantage of that — say what you are about to do
before you do it.

Safe to do alone, remotely: `pio run` (build), `M114`, `M119`, `M503`, `M753`, and reading logs. Everything
in run sheet Task 2 is also safe — it is ODrive configuration over USB with the motor idle.

Two cheap additions worth making before the first remote motion test:

1. **A USB webcam** pointed at the gantry and the chuck. Being able to see the machine changes what is
   reasonable to attempt.
2. **A switched mains socket** for the machine, within reach of whoever is in the room, so there is a
   physical way to cut power that does not depend on firmware.

---

## 9. Verifying it worked

```bash
ssh <user>@<laptop-ip> 'ls -l /dev/rmr-mega /dev/rmr-odrive'
ssh <user>@<laptop-ip> 'google-chrome --version'
ssh <user>@<laptop-ip> 'cd ~/Robot-MakingRobot/Marlin-2.1.2.7 && pio run -e mega2560'
ssh -p 2222 <user>@localhost 'hostname'        # reverse tunnel is up
```

Then the one that actually matters, in the remote desktop: open **RMR Controller (full)**, connect at
250000 baud, send `M119`, and confirm the endstop states come back. If that works, the bench is yours and
run sheet Lane A can start.
