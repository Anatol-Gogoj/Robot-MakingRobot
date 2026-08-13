# Remote Bench Laptop — Setup and Access

**Status: built and working**, on `gogoj-laptop` (Ubuntu 26.04, GNOME 50, Wayland).

The laptop is the robot's permanent operator console. Colleagues stand at it and drive the machine
through the HTML UIs. The owner shares that same desktop remotely and does firmware work.

Everything here was run on the real hardware. Where the first design was wrong, the correction is
recorded rather than quietly edited out — §7 is the useful part of this document.

---

## 1. The constraint that decides the architecture

**A serial port has exactly one holder.**

If the owner opens Chrome in a private remote session while a colleague has the UI open at the bench,
one of them gets `/dev/rmr-mega` and the other gets an error.

So the remote desktop **shares the session that is already running** rather than creating a second
one. One desktop, one Chrome, one serial connection, both people looking at it. This is not a
convenience choice and must not be "improved" into per-user sessions later.

It is also better operationally: when the owner is driving and something goes wrong, the person
standing at the machine sees exactly what the owner sees, and can reach the power switch.

```
   owner's desktop ──┐
                     │  WireGuard mesh (hub-and-spoke via Node0)
   RHEL9 lab      ───┤
                     │
   gogoj-laptop     ─┘   10.20.30.4  ──USB──▶ Mega 2560   (/dev/rmr-mega)
                                     ──USB──▶ ODrive S1   (/dev/rmr-odrive)
```

### Access paths

| Path | What it is | When |
|---|---|---|
| **WireGuard mesh** | The laptop is peer `10.20.30.4` | Everything. `ssh anatol@10.20.30.4`, `mstsc /v:10.20.30.4`. No jump host. |
| **gnome-remote-desktop** | RDP on 3389, shares the running session | The operator console. Wayland-native. |
| **RHEL9 forward** | `ssh -L 13389:<lan-ip>:3389` via `10.20.30.2` | Fallback only, before the laptop joins the mesh. |

`ConnectBench.ps1` chooses between them automatically.

### Autologin is load-bearing

The remote desktop attaches to a session that must already exist. After an unattended reboot with
nobody in the room, there is no desktop unless the laptop logs itself in.

The trade is real: **anyone with physical access to the laptop gets a logged-in desktop.** On a bench
next to a machine those people can already drive, that is acceptable. It also has a consequence that
cost real time — see §7.3.

---

## 2. The browser

The HTML UIs need the **Web Serial API**, which narrows the field to one option.

| Browser | Web Serial | Verdict |
|---|---|---|
| **Google Chrome (`.deb`)** | Native | **Use this.** What the UIs were written against. |
| Chromium (snap) | Native, but | Snap confinement blocks `/dev/tty*`; the port list comes back empty. |
| Firefox (stock) | None | Mozilla declined to implement it. |
| Firefox + `WebSerial for Firefox` | Shimmed | Fallback only. |

**On the Firefox polyfill.** It works, but WebExtensions has no serial API, so the extension hands off
to a native helper on the host — it is "Firefox + extension + a native binary", not "Firefox gained
Web Serial". Do not put it in the critical path here: connecting the browser pulses DTR, the
ATmega16U2 resets the Mega, and the spincoater datum in RAM is destroyed (issue **#54**, gotcha
**#6**). Both UIs and the M112 recovery procedure depend on that behaviour. A polyfill routing
`setSignals()` through a native helper is exactly where DTR timing diverges quietly. If anyone must
use it, the acceptance test is "does the Mega reset on connect" and "does 250000 baud stream
`DemoProgram.gcode` with no lost lines" — not "does it connect".

---

## 3. The scripts

| Script | Where it runs | What it does |
|---|---|---|
| `setup-ssh.sh` | Laptop, at the keyboard | Installs `openssh-server` (absent on Ubuntu Desktop), authorizes the owner's key, stops suspend on lid close, disables the GNOME screen lock, makes network connections system-wide, adds the user to `dialout`. |
| `provision-bench-laptop.sh` | Laptop, over SSH | Everything else. Idempotent. |
| `setup-wireguard.sh` | Laptop, over SSH | Joins the mesh as `10.20.30.4`. Prints the public key and the `[Peer]` stanza for the hub. |
| `check-sharedrive.sh` | Laptop, any time | Finds and mounts the SMB share, write-tests it, persists with `nofail`. |
| `ConnectBench.ps1` | Owner's Windows desktop | Connects. Sibling of `ConnectLab.ps1`. |

Two design rules in the provisioner worth keeping:

- **No `set -e`.** It always reaches its report phase. A script that dies silently at step 9 of 15
  leaves a non-expert colleague with a half-built machine and no information.
- **It never uploads firmware.** It builds — that build is the acceptance test — but nothing on the
  robot changes.

---

## 4. Connecting

```bash
powershell -ExecutionPolicy Bypass -File ConnectBench.ps1
```

It prompts for the WireGuard tunnel, checks the hub, then picks DIRECT (mesh) or FORWARD (via RHEL9).
It writes an `.rdp` file with the username pinned and launches `mstsc`.

Manually, over the mesh:

```bash
ssh anatol@10.20.30.4
mstsc /v:10.20.30.4
```

**The RDP password is its own credential.** Not the Linux account password, not any AD/SSSD password.
It is what was passed to `grdctl rdp set-credentials`.

---

## 5. Verifying the bench

```bash
ssh anatol@10.20.30.4 'ls -l /dev/rmr-mega /dev/rmr-odrive'
ssh anatol@10.20.30.4 'google-chrome --version'
ssh anatol@10.20.30.4 'cd ~/Robot-MakingRobot/Marlin-2.1.2.7 && pio run -e mega2560'
```

Then the one that matters: on the remote desktop, open **RMR Controller (full)**, connect at 250000
baud, send `M119`, and confirm the endstop states come back.

---

## 6. Safety

The machine has a 5000 RPM chuck, a UV lamp and a solenoid valve, and the mechanical E-stop is
**issue #20 and does not exist yet**. The owner can now flash firmware and drive the full operator UI
from another building.

> **WARNING — INJURY TO PERSONS**
> Do not command motion when no person is in the room with the machine.
> Motion commands are `G28`, `G1`, `M280`, `M750`, `M752` and any G-code program.

Safe alone and remotely: `pio run`, `M114`, `M119`, `M503`, `M753`, reading logs, and all of run sheet
Task 2 — that is ODrive configuration over USB with the motor idle.

The shared desktop helps rather than hurts: the colleague at the keyboard sees every command the owner
sends. Say what you are about to do before you do it.

Two cheap additions still worth making: a **USB webcam** pointed at the gantry and chuck, and a
**switched mains socket** within reach of whoever is in the room.

---

## 7. What went wrong, and what it cost

This section exists because every one of these looked like a working design until it met the hardware.

### 7.1 x11vnc cannot work here — the laptop is Wayland

The first design forced `WaylandEnable=false` to get an Xorg session for x11vnc. The laptop turned out
to be Ubuntu **26.04 / GNOME 50**, not 24.04. x11vnc failed with `-auth guess: failed for display
':0'` and `/home/anatol/.Xauthority does not exist`, then restart-looped 27 times.

`gnome-remote-desktop` shares the existing session on **both** Wayland and Xorg, so it is now primary
and the Xorg forcing is gone. x11vnc remains only as a fallback, and is skipped outright on a Wayland
session rather than enabled to fail.

### 7.2 GNOME 50 does not generate the RDP TLS certificate

Without one, the server answers every connection with `RDP server certificate is invalid`. The script
generates a self-signed cert, and sets the **key before the cert** — validating a cert with no
matching key prints an alarming error that means nothing.

`grdctl` also needs `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` exported; an SSH shell does not
inherit the user D-Bus session.

### 7.3 Autologin means the login keyring is never unlocked

`grdctl rdp set-credentials` writes through libsecret. Under autologin, PAM never unlocks the login
keyring, so the call **blocks forever** waiting for an unlock prompt that cannot appear over SSH — it
does not fail, it hangs. Bound it with `timeout`.

The fix needs one action at the physical keyboard: Passwords and Keys (`seahorse`) → right-click
**Login** → Change Password → leave the new password **blank**. An empty-password keyring auto-unlocks
under autologin.

### 7.4 The daemon reads credentials only at startup

Setting credentials without `systemctl --user restart gnome-remote-desktop` leaves the running daemon
holding the old ones. The symptom is an authentication failure that looks like a wrong password.

### 7.5 Windows sends the wrong username

Left to itself the Windows credential picker offers `MicrosoftAccount\<your-email>`. The server log
says `Could not find user in SAM database` and the client says only "Your credentials did not work".
`ConnectBench.ps1` writes an `.rdp` with `username:s:anatol` pinned so the picker never gets the
chance.

### 7.6 WireGuard: `AllowedIPs` means opposite things at each end

On a **spoke**, the hub peer takes `10.20.30.0/24` — "send all mesh traffic to the hub".
On the **hub**, each peer takes **its own /32**.

Getting it backwards on the hub routes the entire mesh at one peer. A related failure cost an hour: an
extra `[Peer]` on the Windows side with `AllowedIPs = 10.20.30.4/32` beat the hub's `/24` on
longest-prefix match, so every packet for the laptop was encrypted for a peer that could not deliver
it. Route present, traffic sent, nothing back.

Also: **do not assume the hub interface is `wg0`.** Node0 carries more than one tunnel; the mesh is
`wg1` on port 51847. Identify it by listen port and public key.

Apply hub changes with `wg syncconf`, never `wg-quick down/up` — the owner may be connected through
the tunnel being torn down, and `wg1` carries `PostUp`/`PostDown` iptables rules.

### 7.7 Smaller ones

- **`brltty`** claims CH340 USB serial adapters on Ubuntu and silently breaks Arduino serial. Removed.
- **ModemManager** probes every new `ttyACM` for ~10 s, corrupting the start of a session and failing
  uploads. Suppressed per-device with `ID_MM_DEVICE_IGNORE` rather than masking it globally.
- Both devices are CDC-ACM, so `ttyACM0` is a coin flip at boot — hence `/dev/rmr-mega` and
  `/dev/rmr-odrive`.
- **PEP 668** means a system-wide `pip install platformio` is refused. The official installer builds
  its own venv.
- **A user-owned Wi-Fi profile only connects after login**, so on a headless bench it is unreachable
  after a reboot. All connections are made system-wide.
- The VNC protocol truncates passwords at **8 characters**. A protocol limit, not a typo.
- `wg show <iface> dump` prints the **private key** as its first field. Use plain `wg show`.
- **The ODrive must be powered**, not merely USB-connected, before it enumerates.
- Clicking **Edit** in the WireGuard GUI for Windows can leave the tunnel service registration stale;
  activation then fails with "The system cannot find the file specified". Restarting the GUI does not
  fix it — delete and re-add the tunnel, and save the private key first.

### 7.8 The pattern

Every one of these was a design that was correct in the abstract and wrong against this specific
hardware, and in most cases the failure mode was **silence or a misleading message** rather than a
clear error. When something does not work here, find the log before changing anything: the
`journalctl` line, the WireGuard GUI Log tab, the `wg show` counters. Each of the above was settled by
one line of log after an hour of guessing.
