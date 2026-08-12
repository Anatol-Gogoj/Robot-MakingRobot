#!/usr/bin/env bash
# =============================================================================
#  RMR BENCH LAPTOP PROVISIONING  --  Ubuntu 24.04 and 26.04 LTS
# =============================================================================
#
#  WHAT THIS DOES
#    Turns a fresh Ubuntu laptop sitting next to the robot into a remote
#    firmware bench: SSH in, stable serial device names for the Mega and the
#    ODrive, a working PlatformIO toolchain, and a graphical session the owner
#    can drive for the Web Serial UIs.
#
#  WHO RUNS IT
#    The on-site colleague. One command, one sudo password. Everything else
#    is automatic.
#
#  DESIGN RULE
#    Only genuinely fatal problems stop this script. Everything else is
#    recorded and appears in the final report, so the colleague is never
#    left stranded half-provisioned.
#
#  BEFORE YOU PUT THIS ON THE SHAREDRIVE  --  edit the CONFIG block below.
#    OWNER_SSH_PUBKEY is mandatory. The script refuses to run without it.
#
# =============================================================================

# NOTE: deliberately NOT 'set -e'. This script must always reach its report
# phase so the colleague is never left half-provisioned with no idea why.
# Anything that genuinely matters is wrapped in soft() and recorded.
set -uo pipefail

# =============================================================================
#  CONFIG  --  EDIT THIS BLOCK BEFORE DISTRIBUTING
# =============================================================================

# --- MANDATORY -------------------------------------------------------------
# Your SSH public key. This is what lets you in. Get it on the RHEL9 box with:
#     cat ~/.ssh/id_ed25519.pub
OWNER_SSH_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICgvdDE8+XdMxxG6I5edNg82Edv71ZflN8r45KK6H4hW amg17031@hc18kx2.engr.uconn.edu"

# --- Identity --------------------------------------------------------------
BENCH_HOSTNAME="rmr-bench"          # laptop becomes rmr-bench.local via mDNS

# --- Reaching this laptop from outside the lab -----------------------------
# Handled by setup-wireguard.sh, not by this script. The laptop joins the
# existing WireGuard mesh as 10.20.30.4 and is then addressable directly:
#     ssh anatol@10.20.30.4        mstsc /v:10.20.30.4
#
# This replaced an autossh reverse tunnel to the RHEL9 box. WireGuard does
# the same job -- surviving DHCP changes and NAT -- and does it better, with
# one less bespoke moving part and one less machine in the critical path.
RHEL9_USER="amg17031"               # only used to address you in the report

# --- ShareDrive (SMB/Samba) ------------------------------------------------
# Used to write the handoff report back. If the mount fails the report is
# written to the Desktop instead and the colleague is told to copy it.
SHARE_UNC=""                        # e.g. "//10.0.4.5/ShareDrive"
SHARE_USER=""                       # empty => guest mount attempt
SHARE_PASS=""
SHARE_SUBDIR="RMR/bench-laptop"     # where reports land inside the share

# --- Repository source -----------------------------------------------------
# "share"  -> copy from the ShareDrive (a directory or a .bundle). No creds.
# "git"    -> git clone REPO_GIT_URL (needs the laptop to have credentials)
# "skip"   -> do not fetch; skip the test build
REPO_SOURCE="share"
REPO_SHARE_PATH="RMR/Robot-MakingRobot.bundle"   # relative to the share root
REPO_GIT_URL=""
REPO_BRANCH="fix/44-feedback-numeric-validation" # the stack tip
REPO_DEST="$HOME/Robot-MakingRobot"

# --- Graphical desktop -----------------------------------------------------
# The laptop is BOTH the local operator console (colleagues stand at it and
# drive the machine) AND the owner's remote desktop.
#
# IMPORTANT: both must attach to the SAME physical session (:0). A serial
# port has exactly one holder -- if the owner opens Chrome in a separate
# remote session while a colleague has the UI open on the console, one of
# them cannot open /dev/rmr-mega. Everything below shadows display :0 for
# that reason. Do not "improve" this into per-user sessions.
ENABLE_GUI_REMOTE=true

# PRIMARY PATH: gnome-remote-desktop (RDP, port 3389). Works on Wayland and
# on Xorg, has real TLS, and no 8-character password limit. This is the
# password for the RDP login -- set it, and tell the colleagues.
RDP_PASSWORD="changeme"

# FALLBACK: x11vnc. Only works on an Xorg session; on Wayland it fails with
# "-auth guess: failed for display ':0'". The VNC protocol truncates the
# password at 8 characters, which is a protocol limit, not a typo.
VNC_PASSWORD="changeme"

# false -> x11vnc listens on 127.0.0.1 only; reach it through the SSH
#          tunnel. Encrypted, and invisible to the rest of the LAN.
# true  -> x11vnc listens on the LAN. Convenient, but VNC's own transport
#          security is weak. Lab LAN only.
VNC_LAN_ACCESS=false

# NoMachine: much better interactivity than VNC over a WAN link, and it
# shadows the physical display by default. Check the current .deb link at
# https://downloads.nomachine.com  -- version numbers move.
# Leave empty to skip.
NOMACHINE_DEB_URL="https://download.nomachine.com/download/8.16/Linux/nomachine_8.16.1_1_amd64.deb"

# Google Chrome. MANDATORY for the HTML UIs: the Web Serial API does not
# exist in Firefox, and the Chromium *snap* is confined away from /dev/tty*.
# Only the Google Chrome .deb reliably reaches the serial ports.
INSTALL_CHROME=true

# =============================================================================
#  END OF CONFIG
# =============================================================================

SCRIPT_VERSION="1.2"
RDP_READY=0
RDP_FINGERPRINT=""
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="/tmp/rmr-provision-${STAMP}.log"
REPORT="/tmp/rmr-bench-report-${STAMP}.txt"
MOUNTPOINT="/mnt/sharedrive"
FAILURES=()
NOTES=()

# ---------------------------------------------------------------- output ----
c_reset=$'\033[0m'; c_bold=$'\033[1m'; c_dim=$'\033[2m'
c_red=$'\033[31m'; c_grn=$'\033[32m'; c_yel=$'\033[33m'; c_blu=$'\033[34m'

log()  { printf '%s\n' "$*" >>"$LOG"; }
say()  { printf '%s\n' "$*"; log "$*"; }
step() { printf '\n%s==>%s %s%s%s\n' "$c_blu" "$c_reset" "$c_bold" "$*" "$c_reset"; log "== $*"; }
ok()   { printf '  %s[ ok ]%s %s\n' "$c_grn" "$c_reset" "$*"; log "[ok] $*"; }
warn() { printf '  %s[warn]%s %s\n' "$c_yel" "$c_reset" "$*"; log "[warn] $*"; NOTES+=("$*"); }
bad()  { printf '  %s[FAIL]%s %s\n' "$c_red" "$c_reset" "$*"; log "[FAIL] $*"; FAILURES+=("$*"); }
die()  { printf '\n%s FATAL:%s %s\n\n' "$c_red" "$c_reset" "$*"; log "FATAL $*"; exit 1; }

# Run a phase; never abort the script if it fails.
soft() {
  local label="$1"; shift
  if "$@" >>"$LOG" 2>&1; then ok "$label"; else bad "$label (see $LOG)"; fi
}

# ============================================================== preflight ====
banner() {
cat <<'EOF'

  ####################################################################
  #                                                                  #
  #     R M R   B E N C H   L A P T O P   P R O V I S I O N I N G     #
  #                                                                  #
  #   This takes 10 to 25 minutes. Keep the laptop plugged in to      #
  #   mains power and connected to the network the whole time.        #
  #   You can leave it running and come back.                        #
  #                                                                  #
  ####################################################################

EOF
}

preflight() {
  step "Preflight checks"

  [[ -n "$OWNER_SSH_PUBKEY" ]] || die \
"OWNER_SSH_PUBKEY is empty.
   The owner must paste their SSH public key into the CONFIG block at the
   top of this script before it is put on the ShareDrive.
   Nothing has been changed on this laptop."

  [[ $EUID -ne 0 ]] || die \
"Do not run this with sudo.
   Run it as your normal user:   bash $0
   The script asks for your password when it needs it."

  if ! sudo -v; then die "This account cannot use sudo. Ask the owner."; fi
  # keep the sudo timestamp warm for the whole run
  ( while true; do sudo -n true 2>/dev/null; sleep 50; done ) &
  SUDO_KEEPALIVE=$!
  trap 'kill "$SUDO_KEEPALIVE" 2>/dev/null || true' EXIT

  local ver; ver="$(. /etc/os-release && echo "${VERSION_ID:-unknown}")"
  if [[ "$ver" == "24.04" ]]; then ok "Ubuntu 24.04 detected"
  else warn "Expected Ubuntu 24.04, found ${ver}. Continuing anyway."; fi

  if ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 || ping -c1 -W3 8.8.8.8 >/dev/null 2>&1; then
    ok "Internet reachable"
  else
    warn "No internet. Package installs and the PlatformIO toolchain will fail."
    warn "Fix the network, then run this script again."
  fi

  ok "Logging to $LOG"
}

# ========================================================= power settings ====
# Do this FIRST. A laptop that suspends mid-install, or when the lid closes,
# is the single most common way this whole exercise fails.
phase_power() {
  step "Stop the laptop from sleeping"

  sudo mkdir -p /etc/systemd/logind.conf.d
  sudo tee /etc/systemd/logind.conf.d/99-rmr-bench.conf >/dev/null <<'EOF'
# RMR bench laptop: never suspend. The machine must stay reachable.
[Login]
HandleLidSwitch=ignore
HandleLidSwitchDocked=ignore
HandleLidSwitchExternalPower=ignore
HandleSuspendKey=ignore
IdleAction=ignore
EOF
  ok "Lid close and idle no longer suspend the laptop"

  soft "Masked suspend/hibernate targets" \
    sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

  # GNOME session-level settings (best effort; only meaningful for the desktop user)
  if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing' 2>/dev/null || true
    gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
    gsettings set org.gnome.desktop.screensaver lock-enabled false 2>/dev/null || true
    ok "Screen blanking and idle lock disabled"
  fi

  # Do not let unattended-upgrades reboot the bench out from under us.
  sudo tee /etc/apt/apt.conf.d/99-rmr-no-reboot >/dev/null <<'EOF'
Unattended-Upgrade::Automatic-Reboot "false";
EOF
  ok "Automatic reboots disabled"
}

# ============================================================== packages ====
phase_packages() {
  step "Install packages"

  export DEBIAN_FRONTEND=noninteractive
  soft "apt update" sudo apt-get update -y

  local pkgs=(
    openssh-server avahi-daemon
    git curl wget ca-certificates
    build-essential python3 python3-venv python3-pip pipx
    cifs-utils
    usbutils picocom minicom
    htop tree jq
  )
  [[ "$ENABLE_GUI_REMOTE" == true ]] && pkgs+=(x11vnc xdotool)


  soft "Installed base packages" sudo apt-get install -y "${pkgs[@]}"

  # brltty claims CH340-based USB serial adapters and breaks Arduino serial.
  # This is a well-known Ubuntu gotcha and there is no braille display here.
  if dpkg -l brltty 2>/dev/null | grep -q '^ii'; then
    soft "Removed brltty (it hijacks USB serial adapters)" \
      sudo apt-get remove -y brltty
  else
    ok "brltty not installed"
  fi
}

# =============================================== serial device plumbing =====
# Both the Mega and the ODrive enumerate as USB CDC-ACM. Which one becomes
# /dev/ttyACM0 depends on plug order at boot. Give each a stable name.
phase_serial() {
  step "Serial devices: stable names and access rights"

  soft "Added $USER to the dialout group" sudo usermod -aG dialout "$USER"
  NOTES+=("The colleague's account was added to 'dialout'. It takes effect after logout or reboot.")

  local rules=/etc/udev/rules.d/99-rmr-bench.rules
  sudo tee "$rules" >/dev/null <<'EOF'
# =====================================================================
#  RMR bench -- stable serial names + keep ModemManager's hands off
# =====================================================================
# ModemManager probes every new ttyACM for ~10 s. That probe corrupts the
# first seconds of a serial session and can make an avrdude upload fail.
# We do not mask ModemManager globally (the laptop may have a WWAN card);
# we tell it to ignore only our two devices.

# --- Arduino Mega 2560 (genuine ATmega16U2) --------------------------
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", SYMLINK+="rmr-mega", ENV{ID_MM_DEVICE_IGNORE}="1", MODE="0660", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2a03", SYMLINK+="rmr-mega", ENV{ID_MM_DEVICE_IGNORE}="1", MODE="0660", GROUP="dialout"
# --- Mega clones: CH340 / CH341 and FTDI ------------------------------
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", SYMLINK+="rmr-mega", ENV{ID_MM_DEVICE_IGNORE}="1", MODE="0660", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", SYMLINK+="rmr-mega", ENV{ID_MM_DEVICE_IGNORE}="1", MODE="0660", GROUP="dialout"

# --- ODrive (pid.codes vendor 0x1209) --------------------------------
SUBSYSTEM=="tty", ATTRS{idVendor}=="1209", SYMLINK+="rmr-odrive", ENV{ID_MM_DEVICE_IGNORE}="1", MODE="0660", GROUP="dialout"
# odrivetool talks raw USB, not tty -- it needs the usb node too.
SUBSYSTEM=="usb", ATTR{idVendor}=="1209", MODE="0666", GROUP="dialout"
EOF

  soft "Installed udev rules" sudo udevadm control --reload-rules
  soft "Triggered udev" sudo udevadm trigger --subsystem-match=tty --subsystem-match=usb
  ok "Rules written to $rules"

  # Report what is actually plugged in right now.
  say ""
  say "  Serial devices seen right now:"
  local found=0
  for dev in /dev/ttyACM* /dev/ttyUSB*; do
    [[ -e "$dev" ]] || continue
    found=1
    local vid pid ser mdl
    vid="$(udevadm info -q property -n "$dev" 2>/dev/null | sed -n 's/^ID_VENDOR_ID=//p')"
    pid="$(udevadm info -q property -n "$dev" 2>/dev/null | sed -n 's/^ID_MODEL_ID=//p')"
    ser="$(udevadm info -q property -n "$dev" 2>/dev/null | sed -n 's/^ID_SERIAL_SHORT=//p')"
    mdl="$(udevadm info -q property -n "$dev" 2>/dev/null | sed -n 's/^ID_MODEL=//p')"
    say "    $dev  vid:pid=${vid:-?}:${pid:-?}  ${mdl:-unknown}  serial=${ser:-none}"
    log "DEVICE $dev vid=$vid pid=$pid model=$mdl serial=$ser"
  done
  if [[ $found -eq 0 ]]; then
    warn "No USB serial devices found. Plug in the Mega and the ODrive, then re-run this script."
  fi
  for link in /dev/rmr-mega /dev/rmr-odrive; do
    if [[ -e "$link" ]]; then ok "$link -> $(readlink -f "$link")"
    else warn "$link not present yet (device unplugged, or an unexpected USB vendor ID)"; fi
  done
}

# =================================================================== ssh ====
phase_ssh() {
  step "SSH access for the owner"

  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  touch "$HOME/.ssh/authorized_keys" && chmod 600 "$HOME/.ssh/authorized_keys"
  if grep -qF "$OWNER_SSH_PUBKEY" "$HOME/.ssh/authorized_keys"; then
    ok "Owner key already authorized"
  else
    printf '%s\n' "$OWNER_SSH_PUBKEY" >>"$HOME/.ssh/authorized_keys"
    ok "Owner key authorized"
  fi

  soft "Enabled sshd at boot" sudo systemctl enable --now ssh

  # Keep long remote sessions alive across NAT/Wi-Fi idle timeouts.
  sudo tee /etc/ssh/sshd_config.d/99-rmr-bench.conf >/dev/null <<'EOF'
# RMR bench: keep long firmware sessions alive.
ClientAliveInterval 30
ClientAliveCountMax 20
TCPKeepAlive yes
EOF
  soft "Restarted sshd" sudo systemctl restart ssh

  if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q '^Status: active'; then
    soft "Opened port 22 in ufw" sudo ufw allow 22/tcp
  else
    ok "ufw inactive; no firewall change needed"
  fi
}

# ============================================================== hostname ====
phase_hostname() {
  step "Hostname and network"

  soft "Hostname set to $BENCH_HOSTNAME" sudo hostnamectl set-hostname "$BENCH_HOSTNAME"
  soft "Enabled avahi (mDNS: ${BENCH_HOSTNAME}.local)" sudo systemctl enable --now avahi-daemon

  # A Wi-Fi profile owned by a single user only comes up AFTER that user logs
  # in. On a headless bench that means the laptop is unreachable after a
  # reboot. Make every saved connection system-wide and autoconnecting.
  if command -v nmcli >/dev/null 2>&1; then
    while IFS= read -r con; do
      [[ -n "$con" ]] || continue
      sudo nmcli connection modify "$con" connection.permissions "" \
                                          connection.autoconnect yes 2>/dev/null || true
    done < <(nmcli -g NAME connection show 2>/dev/null)
    ok "All saved network connections are system-wide and autoconnect"
  fi

  NOTES+=("Ask the network admin for a DHCP reservation so the laptop keeps this IP.")
}

# ========================================================== platformio ======
phase_platformio() {
  step "PlatformIO toolchain"

  # Ubuntu 24.04 ships Python 3.12 with PEP 668, so 'pip install platformio'
  # is refused system-wide. The official installer builds its own venv under
  # ~/.platformio/penv, which sidesteps that cleanly.
  if [[ -x "$HOME/.platformio/penv/bin/pio" ]]; then
    ok "PlatformIO already installed"
  else
    if curl -fsSL -o /tmp/get-platformio.py \
         https://raw.githubusercontent.com/platformio/platformio-core-installer/master/get-platformio.py >>"$LOG" 2>&1
    then
      soft "Installed PlatformIO core" python3 /tmp/get-platformio.py
    else
      bad "Could not download the PlatformIO installer (no internet?)"
    fi
  fi

  mkdir -p "$HOME/.local/bin"
  ln -sf "$HOME/.platformio/penv/bin/pio"       "$HOME/.local/bin/pio"       2>/dev/null || true
  ln -sf "$HOME/.platformio/penv/bin/platformio" "$HOME/.local/bin/platformio" 2>/dev/null || true

  # ~/.local/bin is on PATH for login shells on 24.04, but make it explicit
  # for the non-interactive SSH sessions the owner will use.
  if ! grep -q 'RMR bench PATH' "$HOME/.bashrc" 2>/dev/null; then
    cat >>"$HOME/.bashrc" <<'EOF'

# RMR bench PATH
export PATH="$HOME/.local/bin:$HOME/.platformio/penv/bin:$PATH"
EOF
  fi
  export PATH="$HOME/.local/bin:$HOME/.platformio/penv/bin:$PATH"

  if command -v pio >/dev/null 2>&1; then ok "pio $(pio --version 2>/dev/null || echo '?')"
  else bad "pio not on PATH"; fi
}

# ============================================================ odrivetool ====
phase_odrivetool() {
  step "odrivetool (needed for run sheet Task 2)"

  # This is the most fragile install here. The odrive package has historically
  # lagged new Python releases, and 24.04 ships 3.12. Failure is NOT fatal:
  # Task 2 can also be done from the ODrive web GUI or over raw serial.
  if command -v odrivetool >/dev/null 2>&1; then
    ok "odrivetool already installed"
    return
  fi
  pipx ensurepath >>"$LOG" 2>&1 || true
  if pipx install odrive >>"$LOG" 2>&1; then
    ok "odrivetool installed via pipx"
  else
    bad "odrivetool install failed on Python 3.12 -- see $LOG"
    NOTES+=("odrivetool did not install. Owner: try a Python 3.11 venv remotely, or use the ODrive web GUI for Task 2.")
  fi
}

# ================================================================ share =====
phase_share() {
  step "ShareDrive"

  if [[ -z "$SHARE_UNC" ]]; then
    warn "No ShareDrive configured; the report will be left on the Desktop"
    return
  fi

  sudo mkdir -p "$MOUNTPOINT"
  local cred=/etc/rmr-share.cred
  if [[ -n "$SHARE_USER" ]]; then
    sudo tee "$cred" >/dev/null <<EOF
username=$SHARE_USER
password=$SHARE_PASS
EOF
    sudo chmod 600 "$cred"
    local opts="credentials=$cred,uid=$(id -u),gid=$(id -g),iocharset=utf8,vers=3.0,nofail,x-systemd.automount"
  else
    local opts="guest,uid=$(id -u),gid=$(id -g),iocharset=utf8,vers=3.0,nofail,x-systemd.automount"
  fi

  if ! grep -q "$MOUNTPOINT" /etc/fstab; then
    echo "$SHARE_UNC  $MOUNTPOINT  cifs  $opts  0  0" | sudo tee -a /etc/fstab >/dev/null
  fi
  soft "Reloaded systemd mount units" sudo systemctl daemon-reload
  if sudo mount "$MOUNTPOINT" >>"$LOG" 2>&1 || mountpoint -q "$MOUNTPOINT"; then
    ok "ShareDrive mounted at $MOUNTPOINT"
  else
    bad "Could not mount $SHARE_UNC -- the report will be left on the Desktop"
  fi
}

# ================================================================= repo =====
phase_repo() {
  step "Repository and test build"

  if [[ "$REPO_SOURCE" == "skip" ]]; then
    warn "Repository fetch skipped by config; no test build"
    return
  fi

  if [[ -d "$REPO_DEST/.git" ]]; then
    ok "Repository already present at $REPO_DEST"
  else
    case "$REPO_SOURCE" in
      share)
        local src="$MOUNTPOINT/$REPO_SHARE_PATH"
        if [[ -f "$src" ]]; then
          soft "Cloned from bundle on the ShareDrive" git clone "$src" "$REPO_DEST"
        elif [[ -d "$src" ]]; then
          soft "Copied repository from the ShareDrive" cp -a "$src" "$REPO_DEST"
        else
          bad "Not found on the ShareDrive: $src"
          NOTES+=("Owner: place a 'git bundle create <name>.bundle --all' at $REPO_SHARE_PATH on the share.")
          return
        fi ;;
      git)
        [[ -n "$REPO_GIT_URL" ]] || { bad "REPO_SOURCE=git but REPO_GIT_URL is empty"; return; }
        soft "Cloned $REPO_GIT_URL" git clone "$REPO_GIT_URL" "$REPO_DEST" ;;
    esac
  fi

  [[ -d "$REPO_DEST" ]] || return
  git -C "$REPO_DEST" checkout "$REPO_BRANCH" >>"$LOG" 2>&1 \
    && ok "Checked out $REPO_BRANCH" \
    || warn "Could not check out $REPO_BRANCH (staying on the default branch)"

  # THE ACCEPTANCE TEST. This downloads the AVR toolchain and compiles the
  # real firmware. If this passes, the owner can build and flash remotely.
  say ""
  say "  Building the firmware. This downloads the AVR toolchain on first run"
  say "  and can take several minutes. Please wait."
  if ( cd "$REPO_DEST/Marlin-2.1.2.7" && pio run -e mega2560 ) >>"$LOG" 2>&1; then
    ok "TEST BUILD PASSED -- the toolchain works end to end"
    BUILD_RESULT="PASS"
    BUILD_SIZES="$(grep -E 'Flash:|RAM:' "$LOG" | tail -2 | sed 's/^/      /')"
  else
    bad "TEST BUILD FAILED -- see $LOG"
    BUILD_RESULT="FAIL"
    BUILD_SIZES=""
  fi
}

# ============================================================== browser =====
# The HTML UIs ARE the machine's interface. Without a browser that can reach
# the serial ports, the laptop cannot be an operator console at all.
phase_browser() {
  step "Browser and operator shortcuts"

  if [[ "$INSTALL_CHROME" != true ]]; then
    warn "Chrome install disabled by config -- the HTML UIs will not work"
    return
  fi

  if command -v google-chrome >/dev/null 2>&1; then
    ok "Google Chrome already installed"
  else
    # Deliberately the .deb and NOT the Chromium snap: snap confinement
    # blocks /dev/tty* access, so Web Serial sees no ports. Firefox has no
    # Web Serial API at all (a third-party polyfill exists -- see the setup
    # doc -- but it routes DTR through a native helper, and this machine's
    # reset-on-connect behaviour depends on DTR).
    if wget -qO /tmp/chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb >>"$LOG" 2>&1
    then
      soft "Installed Google Chrome" sudo apt-get install -y /tmp/chrome.deb
    else
      bad "Could not download Google Chrome (no internet?) -- the HTML UIs will not work"
    fi
  fi

  # Desktop launchers so a colleague double-clicks instead of navigating to
  # a file path. --app= opens without browser chrome, which suits the touch UI.
  mkdir -p "$HOME/Desktop"
  make_launcher() {
    local name="$1" file="$2" out="$HOME/Desktop/$3"
    [[ -f "$file" ]] || { warn "UI file not found, no launcher made: $file"; return; }
    cat >"$out" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$name
Comment=Web Serial controller for the RMR machine
Exec=/usr/bin/google-chrome --app=file://$file
Icon=google-chrome
Terminal=false
Categories=Utility;
EOF
    chmod +x "$out"
    # Without this GNOME shows the launcher as untrusted and refuses to run it.
    gio set "$out" metadata::trusted true 2>/dev/null || true
    ok "Desktop launcher: $name"
  }
  make_launcher "RMR Touch Controller" "$REPO_DEST/RMR_Touch.html"      "RMR-Touch.desktop"
  make_launcher "RMR Controller (full)" "$REPO_DEST/RMR_Controller.html" "RMR-Controller.desktop"
}

# ========================================================== gui remote ======
# The laptop is both the local operator console and the owner's remote
# desktop. Both must attach to the SAME session -- a serial port has exactly
# one holder, so per-user sessions would fight over /dev/rmr-mega.
#
# gnome-remote-desktop shares the EXISTING session on both Wayland and Xorg,
# so it is the primary path. x11vnc only works on Xorg and is the fallback.
# Verified against Ubuntu 26.04 / GNOME 50 on the real bench laptop.
phase_gui() {
  [[ "$ENABLE_GUI_REMOTE" == true ]] || { step "Graphical remote access"; warn "Disabled by config (SSH only)"; return; }
  step "Graphical remote access (for the Web Serial UIs)"

  # Autologin: the remote desktop attaches to a session that must ALREADY
  # exist. Without it, an unattended reboot leaves no desktop at all and the
  # console is unreachable until somebody walks over to the machine.
  if [[ -f /etc/gdm3/custom.conf ]]; then
    sudo sed -i "s/^#\?  *AutomaticLoginEnable *=.*/AutomaticLoginEnable=true/" /etc/gdm3/custom.conf
    sudo sed -i "s/^#\?  *AutomaticLogin *=.*/AutomaticLogin=$USER/"           /etc/gdm3/custom.conf
    ok "Autologin configured (takes effect after reboot)"
    NOTES+=("Autologin is ON. Anyone with physical access to the laptop gets a logged-in desktop.")
  else
    warn "/etc/gdm3/custom.conf not found; set autologin by hand in Settings > System > Users"
  fi

  local sid stype
  sid="$(loginctl list-sessions --no-legend 2>/dev/null | awk -v u="$USER" '$3==u && $4=="seat0" {print $1; exit}')"
  stype="$(loginctl show-session "${sid:-1}" -p Type --value 2>/dev/null)"
  ok "Graphical session type: ${stype:-unknown}"

  if setup_gnome_rdp; then return; fi
  if [[ "$stype" == "x11" ]]; then
    warn "Falling back to x11vnc"
    setup_x11vnc
  else
    warn "Session is '${stype:-unknown}', so x11vnc cannot attach to a display. No fallback."
  fi
}

# --- primary: gnome-remote-desktop (RDP), works on Wayland and Xorg ---------
setup_gnome_rdp() {
  command -v grdctl >/dev/null 2>&1 || \
    sudo apt-get install -y gnome-remote-desktop >>"$LOG" 2>&1 || \
    { warn "gnome-remote-desktop is not available"; return 1; }

  # grdctl talks to the user D-Bus session, which an SSH shell does not
  # inherit. Without these two the calls fail with no useful message.
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

  local dir="$HOME/.local/share/gnome-remote-desktop"
  mkdir -p "$dir"
  if [[ -f "$dir/rdp-tls.crt" && -f "$dir/rdp-tls.key" ]]; then
    ok "RDP certificate already present"
  else
    # GNOME 50 does NOT generate this by itself. Without a cert the server
    # answers every connection with "RDP server certificate is invalid".
    if openssl req -new -newkey rsa:4096 -days 3650 -nodes -x509 \
         -subj "/CN=$BENCH_HOSTNAME" \
         -keyout "$dir/rdp-tls.key" -out "$dir/rdp-tls.crt" >>"$LOG" 2>&1; then
      chmod 600 "$dir/rdp-tls.key"
      ok "Generated a self-signed RDP certificate"
    else
      bad "Could not generate the RDP certificate"; return 1
    fi
  fi

  # Set the key BEFORE the cert: validating a cert with no matching key
  # prints a harmless but alarming "certificate is invalid" error.
  grdctl rdp set-tls-key  "$dir/rdp-tls.key" >>"$LOG" 2>&1
  grdctl rdp set-tls-cert "$dir/rdp-tls.crt" >>"$LOG" 2>&1

  # set-credentials writes through libsecret. Under autologin, PAM never
  # unlocks the login keyring, so this call BLOCKS FOREVER waiting for an
  # unlock prompt that cannot appear over SSH. Bound it and say what to do.
  if timeout 15 grdctl rdp set-credentials "$USER" "$RDP_PASSWORD" >>"$LOG" 2>&1; then
    ok "RDP credentials stored"
  else
    bad "RDP credentials rejected or timed out -- the GNOME login keyring is locked"
    NOTES+=("KEYRING FIX (needs one action at the physical keyboard): open 'Passwords and Keys' (sudo apt install seahorse), right-click the 'Login' keyring, Change Password, leave the new password BLANK. An empty-password keyring auto-unlocks under autologin. Then run this script again.")
    return 1
  fi

  grdctl rdp disable-view-only >>"$LOG" 2>&1
  grdctl rdp enable            >>"$LOG" 2>&1
  systemctl --user enable --now gnome-remote-desktop >>"$LOG" 2>&1
  systemctl --user restart     gnome-remote-desktop  >>"$LOG" 2>&1

  sleep 2
  if ss -tln 2>/dev/null | grep -q ':3389'; then
    RDP_READY=1
    RDP_FINGERPRINT="$(grdctl status 2>/dev/null | sed -n 's/.*TLS fingerprint: *//p')"
    ok "RDP is listening on 3389 and shares the current session"
    NOTES+=("gnome-remote-desktop listens on ALL interfaces. Reach it over an SSH tunnel, or restrict it if the LAN is not trusted.")
    return 0
  fi
  bad "gnome-remote-desktop is not listening on 3389"
  return 1
}

# --- fallback: x11vnc, Xorg sessions only ----------------------------------
setup_x11vnc() {
  command -v x11vnc >/dev/null 2>&1 || sudo apt-get install -y x11vnc >>"$LOG" 2>&1

  local vncpass="$HOME/.vnc/passwd"
  mkdir -p "$HOME/.vnc"
  if [[ "$VNC_PASSWORD" == "changeme" || -z "$VNC_PASSWORD" ]]; then
    warn "VNC_PASSWORD is still the default. Change it in the CONFIG block."
  fi
  # The VNC protocol truncates passwords at 8 characters. Not a typo.
  x11vnc -storepasswd "${VNC_PASSWORD:0:8}" "$vncpass" >>"$LOG" 2>&1 \
    && ok "VNC password stored (8 characters max -- protocol limit)" \
    || bad "Could not store the VNC password"
  chmod 600 "$vncpass" 2>/dev/null || true

  local bindopt="-localhost" bindtxt="127.0.0.1:5900 (reach it through the SSH tunnel)"
  if [[ "$VNC_LAN_ACCESS" == true ]]; then
    bindopt=""; bindtxt="0.0.0.0:5900 (open on the LAN -- VNC transport security is weak)"
    NOTES+=("x11vnc is listening on the LAN. Anyone on the LAN who knows the password can drive the machine.")
  fi

  sudo tee /etc/systemd/system/rmr-x11vnc.service >/dev/null <<EOF
[Unit]
Description=RMR bench x11vnc -- shadows the physical display :0
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=$USER
Environment=DISPLAY=:0
ExecStart=/usr/bin/x11vnc -display :0 -auth guess $bindopt \
  -forever -shared -threads -noxdamage \
  -rfbport 5900 -rfbauth $vncpass
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF
  soft "Enabled x11vnc service" sudo systemctl enable rmr-x11vnc.service
  ok "After the reboot x11vnc listens on $bindtxt"
  NOTES+=("If VNC does not come up after the reboot, check: journalctl -u rmr-x11vnc -b")
}
# =========================================================== nomachine ======
# VNC is the baseline that always works. NoMachine is markedly better over a
# WAN link, and it shadows the physical desktop by default -- same session,
# same Chrome, same serial port.
phase_nomachine() {
  [[ "$ENABLE_GUI_REMOTE" == true ]] || return
  step "NoMachine (high-performance remote desktop)"

  if [[ -z "$NOMACHINE_DEB_URL" ]]; then
    warn "No NoMachine URL configured; skipping (x11vnc still available)"
    return
  fi
  if command -v /usr/NX/bin/nxplayer >/dev/null 2>&1 || [[ -d /usr/NX ]]; then
    ok "NoMachine already installed"
    return
  fi

  # wget returns 0 even when the server hands back an HTML error page, so the
  # download must be validated as a real .deb before apt is asked to install
  # it. Without this check a moved URL produces "Invalid archive signature".
  if ! wget -qO /tmp/nomachine.deb "$NOMACHINE_DEB_URL" >>"$LOG" 2>&1; then
    bad "NoMachine download failed -- no network, or the URL is dead"
    NOTES+=("Get the current .deb link from https://downloads.nomachine.com and install it later. x11vnc still works.")
  elif ! dpkg-deb --info /tmp/nomachine.deb >>"$LOG" 2>&1; then
    bad "NoMachine download is not a valid .deb -- the version in the URL has moved"
    NOTES+=("Get the current .deb link from https://downloads.nomachine.com and install it later. x11vnc still works.")
  elif sudo apt-get install -y /tmp/nomachine.deb >>"$LOG" 2>&1; then
    ok "Installed NoMachine -- listens on TCP 4000, attaches to the physical display"
    NOTES+=("NoMachine login uses a normal system account: $USER plus that account's password.")
    if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q '^Status: active'; then
      sudo ufw allow 4000/tcp >>"$LOG" 2>&1 || true
    fi
  else
    bad "NoMachine package downloaded but failed to install"
    NOTES+=("See the log for the apt error. x11vnc still works.")
  fi
}


# ============================================================== report ======
phase_report() {
  step "Handoff report"

  local ips; ips="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^$' | sed 's/^/    /')"
  local fps; fps="$(for f in /etc/ssh/ssh_host_*_key.pub; do ssh-keygen -lf "$f" 2>/dev/null | sed 's/^/    /'; done)"

  {
    echo "======================================================================"
    echo " RMR BENCH LAPTOP -- HANDOFF REPORT"
    echo " Generated $(date -Is)  by provisioning script v${SCRIPT_VERSION}"
    echo "======================================================================"
    echo
    echo "-- CONNECT TO IT ------------------------------------------------------"
    echo "  user           : $USER"
    echo "  hostname       : $(hostname)   (mDNS: $(hostname).local)"
    echo "  IP addresses   :"; echo "$ips"
    echo
    echo "  From the RHEL9 box:"
    echo "      ssh ${USER}@$(hostname -I | awk '{print $1}')"
    echo
    echo "-- SSH HOST KEY FINGERPRINTS (check these on first connect) -----------"
    echo "$fps"
    echo
    echo "-- SERIAL DEVICES -----------------------------------------------------"
    for link in /dev/rmr-mega /dev/rmr-odrive; do
      if [[ -e "$link" ]]; then echo "  $link -> $(readlink -f "$link")"
      else echo "  $link  ABSENT"; fi
    done
    echo
    for dev in /dev/ttyACM* /dev/ttyUSB*; do
      [[ -e "$dev" ]] || continue
      echo "  $dev"
      udevadm info -q property -n "$dev" 2>/dev/null \
        | grep -E '^(ID_VENDOR_ID|ID_MODEL_ID|ID_MODEL|ID_SERIAL_SHORT)=' | sed 's/^/      /'
    done
    echo
    echo "-- TOOLCHAIN ----------------------------------------------------------"
    echo "  python3     : $(python3 --version 2>&1)"
    echo "  pio         : $(pio --version 2>&1 || echo 'NOT INSTALLED')"
    echo "  odrivetool  : $(command -v odrivetool >/dev/null && odrivetool --version 2>&1 | head -1 || echo 'NOT INSTALLED')"
    echo "  git         : $(git --version 2>&1)"
    echo
    echo "-- TEST BUILD ---------------------------------------------------------"
    echo "  repository  : ${REPO_DEST}"
    echo "  branch      : $(git -C "$REPO_DEST" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'n/a')"
    echo "  commit      : $(git -C "$REPO_DEST" rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
    echo "  result      : ${BUILD_RESULT:-NOT RUN}"
    [[ -n "${BUILD_SIZES:-}" ]] && echo "$BUILD_SIZES"
    echo
    echo "-- GRAPHICAL DESKTOP --------------------------------------------------"
    if [[ "$ENABLE_GUI_REMOTE" == true ]]; then
      echo "  The remote desktop SHARES the session already running on the"
      echo "  laptop. One desktop, one Chrome, one holder of the serial port."
      echo "  That is deliberate -- do not switch to per-user sessions."
      echo
      if [[ "$RDP_READY" == "1" ]]; then
        echo "  gnome-remote-desktop (RDP, port 3389)"
        echo "      username: $USER"
        echo "      password: the RDP_PASSWORD from this script's config."
        echo "                NOT the Linux account password, and NOT any"
        echo "                AD/SSSD password -- grdctl stores its own."
        [[ -n "$RDP_FINGERPRINT" ]] && echo "      TLS fingerprint: $RDP_FINGERPRINT"
        echo
        if ip addr show wg0 >/dev/null 2>&1; then
          echo "      On the mesh:  mstsc /v:$(ip -4 -o addr show wg0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
        else
          echo "      Not on the mesh yet, so it needs a forward through the"
          echo "      jump host. From the owner's desktop:"
          echo "          ssh -L 13389:${IP}:3389 ${RHEL9_USER:-<you>}@<jump-host>"
          echo "          mstsc /v:localhost:13389"
          echo "      (local port 13389 because 3389 is usually already in use"
          echo "       by the jump host's own xrdp)"
        fi
      else
        echo "  RDP is NOT running. See the PROBLEMS and NOTES sections."
      fi
      echo
      echo "  x11vnc  (fallback, Xorg sessions only)"
      if [[ "$VNC_LAN_ACCESS" == true ]]; then
        echo "      VNC client -> $(hostname -I | awk '{print $1}'):5900"
      else
        echo "      ssh -L 5900:localhost:5900 ${USER}@$(hostname -I | awk '{print $1}')"
        echo "      then point a VNC client at localhost:5900"
      fi
      if [[ -d /usr/NX ]]; then
        echo
        echo "  NoMachine  (better over a WAN link)"
        echo "      NoMachine client -> $(hostname -I | awk '{print $1}'):4000"
        echo "      log in as '$USER' with that account's system password"
      fi
      echo
      echo "  Chrome    : $(google-chrome --version 2>/dev/null || echo 'NOT INSTALLED -- the HTML UIs will not work')"
      echo "  Launchers : $(ls "$HOME/Desktop"/RMR-*.desktop 2>/dev/null | tr '\n' ' ' || echo 'none')"
    else
      echo "  Disabled. SSH only. The HTML UIs cannot be used."
    fi
    echo
    echo "-- REACHING THIS LAPTOP FROM OUTSIDE THE LAB --------------------------"
    if ip addr show wg0 >/dev/null 2>&1; then
      echo "  On the WireGuard mesh: $(ip -4 -o addr show wg0 2>/dev/null | awk '{print $4}')"
      echo "      ssh ${USER}@$(ip -4 -o addr show wg0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
      echo "      mstsc /v:$(ip -4 -o addr show wg0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
      echo "  No jump host and no port forward needed."
    else
      echo "  NOT on the WireGuard mesh. Until it is, reaching this laptop means"
      echo "  going through the RHEL9 box, and it breaks whenever the DHCP"
      echo "  lease changes. Run:   bash bench-laptop/setup-wireguard.sh"
    fi
    echo
    echo "-- PROBLEMS -----------------------------------------------------------"
    if [[ ${#FAILURES[@]} -eq 0 ]]; then echo "  None."
    else printf '  FAILED: %s\n' "${FAILURES[@]}"; fi
    echo
    echo "-- NOTES --------------------------------------------------------------"
    if [[ ${#NOTES[@]} -eq 0 ]]; then echo "  None."
    else printf '  - %s\n' "${NOTES[@]}"; fi
    echo
    echo "-- FULL LOG -----------------------------------------------------------"
    echo "  $LOG   (also copied next to this report if the share mounted)"
    echo "======================================================================"
  } >"$REPORT"

  # Deliver it.
  local delivered=""
  if mountpoint -q "$MOUNTPOINT" 2>/dev/null; then
    local dest="$MOUNTPOINT/$SHARE_SUBDIR"
    if mkdir -p "$dest" 2>/dev/null && cp "$REPORT" "$dest/" 2>/dev/null; then
      cp "$LOG" "$dest/" 2>/dev/null || true
      delivered="$dest/$(basename "$REPORT")"
      ok "Report written to the ShareDrive"
    fi
  fi
  if [[ -z "$delivered" ]]; then
    cp "$REPORT" "$HOME/Desktop/" 2>/dev/null || cp "$REPORT" "$HOME/" 2>/dev/null || true
    delivered="$HOME/Desktop/$(basename "$REPORT")"
    warn "Could not write to the ShareDrive. Report left at $delivered"
  fi
  REPORT_LOCATION="$delivered"
}

# ================================================================= main =====
main() {
  banner
  preflight
  phase_power
  phase_packages
  phase_hostname
  phase_serial
  phase_ssh
  phase_platformio
  phase_odrivetool
  phase_share
  phase_repo
  phase_browser
  phase_gui
  phase_nomachine
  phase_report

  echo
  echo "======================================================================"
  if [[ ${#FAILURES[@]} -eq 0 ]]; then
    printf '%s  PROVISIONING COMPLETE%s\n' "$c_grn$c_bold" "$c_reset"
  else
    printf '%s  PROVISIONING FINISHED WITH %d PROBLEM(S)%s\n' "$c_yel$c_bold" "${#FAILURES[@]}" "$c_reset"
    printf '    - %s\n' "${FAILURES[@]}"
  fi
  echo "======================================================================"
  echo
  echo "  Report : ${REPORT_LOCATION:-$REPORT}"
  echo "  Log    : $LOG"
  echo
  echo "  TELL THE OWNER: the report is ready."
  echo
  if [[ "$ENABLE_GUI_REMOTE" == true ]]; then
    echo "  ONE LAST STEP: restart the laptop now, so the graphical remote"
    echo "  access and the group membership take effect."
    echo
    echo "      sudo reboot"
    echo
    echo "  After the restart, leave the laptop switched on, plugged in,"
    echo "  and connected to the network. You can close the lid."
  else
    echo "  ONE LAST STEP: log out and log in again (or restart) so that the"
    echo "  serial port permissions take effect."
  fi
  echo
}

main "$@"
