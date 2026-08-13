#!/usr/bin/env bash
# =============================================================================
#  STEP 1 -- REMOTE ACCESS  --  Ubuntu 24.04
# =============================================================================
#
#  Gets the owner onto this laptop over SSH, and makes sure the laptop stays
#  reachable after everyone leaves the room. That is all it does. It installs
#  no toolchain, touches no firmware, and sends nothing to the robot.
#
#  ORDER OF THE THREE SCRIPTS:
#     1. setup-ssh.sh            <-- you are here. Run at the keyboard.
#     2. check-sharedrive.sh     mount the ShareDrive (optional, any time)
#     3. provision-bench-laptop.sh   everything else -- the owner runs this
#                                    remotely over SSH once step 1 works.
#
#  RUN IT AS:   bash setup-ssh.sh
#  (not with sudo -- it asks for your password when it needs it)
#
#  OWNER: paste your public key into OWNER_SSH_PUBKEY below before you send
#  this file. Then the colleague types one command and nothing else.
#
# =============================================================================

set -uo pipefail

# ----------------------------------------------------------------- CONFIG ---
# Get this on the RHEL9 box with:   cat ~/.ssh/id_ed25519.pub
# Leave it empty and the script will ask for it, or read owner_key.pub
# from the same folder as this script.
OWNER_SSH_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICgvdDE8+XdMxxG6I5edNg82Edv71ZflN8r45KK6H4hW amg17031@hc18kx2.engr.uconn.edu"
# -----------------------------------------------------------------------------

c_reset=$'\033[0m'; c_bold=$'\033[1m'
c_red=$'\033[31m'; c_grn=$'\033[32m'; c_yel=$'\033[33m'; c_blu=$'\033[34m'
step(){ printf '\n%s==>%s %s%s%s\n' "$c_blu" "$c_reset" "$c_bold" "$*" "$c_reset"; }
ok(){   printf '  %s[ ok ]%s %s\n' "$c_grn" "$c_reset" "$*"; }
warn(){ printf '  %s[warn]%s %s\n' "$c_yel" "$c_reset" "$*"; }
bad(){  printf '  %s[FAIL]%s %s\n' "$c_red" "$c_reset" "$*"; }

PROBLEMS=()
note_bad(){ bad "$*"; PROBLEMS+=("$*"); }

cat <<'EOF'

  ##################################################################
  #                                                                #
  #   S T E P  1   --   R E M O T E   A C C E S S                  #
  #                                                                #
  #   Takes about 2 minutes. It does not touch the robot.          #
  #                                                                #
  ##################################################################

EOF

# ============================================================== preflight ====
step "Checks before starting"

[[ $EUID -ne 0 ]] || { echo "  Run this WITHOUT sudo:   bash $0"; exit 1; }
sudo -v || { bad "This account cannot use sudo. Ask the owner."; exit 1; }
ok "sudo works"

ver="$(. /etc/os-release && echo "${VERSION_ID:-unknown}")"
[[ "$ver" == "24.04" ]] && ok "Ubuntu 24.04" || warn "Expected Ubuntu 24.04, found $ver. Continuing."

# ---- find the owner's key ---------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$OWNER_SSH_PUBKEY" && -f "$SCRIPT_DIR/owner_key.pub" ]]; then
  OWNER_SSH_PUBKEY="$(cat "$SCRIPT_DIR/owner_key.pub")"
  ok "Read the owner's key from owner_key.pub"
fi
if [[ -z "$OWNER_SSH_PUBKEY" ]]; then
  echo
  echo "  The owner's public key is not in this script."
  echo "  Paste it now (one long line starting with 'ssh-'), then push Enter:"
  read -r OWNER_SSH_PUBKEY
fi
if [[ ! "$OWNER_SSH_PUBKEY" =~ ^(ssh-(rsa|ed25519|dss)|ecdsa-sha2-) ]]; then
  bad "That does not look like an SSH public key."
  echo "     It must start with 'ssh-ed25519' or 'ssh-rsa'."
  echo "     Nothing has been changed. Ask the owner to re-send the file."
  exit 1
fi
ok "Owner key looks valid"

# ============================================================ ssh server =====
step "Installing and starting the SSH server"

# Ubuntu Desktop does NOT ship an SSH server. This is the whole point.
if dpkg -l openssh-server 2>/dev/null | grep -q '^ii'; then
  ok "openssh-server already installed"
else
  sudo apt-get update -qq
  sudo apt-get install -y openssh-server >/dev/null 2>&1 \
    && ok "Installed openssh-server" \
    || note_bad "Could not install openssh-server. Is there internet?"
fi

sudo systemctl enable --now ssh >/dev/null 2>&1 || sudo systemctl enable --now sshd >/dev/null 2>&1
sudo systemctl enable --now ssh.socket >/dev/null 2>&1 || true

# Keep long remote sessions alive across idle NAT and Wi-Fi timeouts.
sudo mkdir -p /etc/ssh/sshd_config.d
sudo rm -f /etc/ssh/sshd_config.d/99-rmr-bench.conf   # pre-rename name
sudo tee /etc/ssh/sshd_config.d/99-rmr.conf >/dev/null <<'EOF'
# RMR bench: keep long firmware sessions alive.
ClientAliveInterval 30
ClientAliveCountMax 20
TCPKeepAlive yes
EOF
sudo systemctl restart ssh >/dev/null 2>&1 || sudo systemctl restart sshd >/dev/null 2>&1

# The real test is not "is the unit enabled" but "is anything listening on 22".
sleep 1
if ss -tln 2>/dev/null | grep -qE ':22\s'; then
  ok "Port 22 is listening"
else
  note_bad "Nothing is listening on port 22 -- the owner will not be able to connect"
fi

# ============================================================== the key ======
step "Authorizing the owner's key"

mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys" && chmod 600 "$HOME/.ssh/authorized_keys"
if grep -qF "$OWNER_SSH_PUBKEY" "$HOME/.ssh/authorized_keys"; then
  ok "Key was already authorized"
else
  printf '%s\n' "$OWNER_SSH_PUBKEY" >> "$HOME/.ssh/authorized_keys"
  ok "Key authorized"
fi

# ================================================================ sleep ======
step "Stopping the laptop from going to sleep"

# If the laptop suspends when the lid closes, the owner loses the machine and
# somebody has to walk back over. This is the most important part after SSH.
sudo mkdir -p /etc/systemd/logind.conf.d
sudo rm -f /etc/systemd/logind.conf.d/99-rmr-bench.conf   # pre-rename name
sudo tee /etc/systemd/logind.conf.d/99-rmr.conf >/dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchDocked=ignore
HandleLidSwitchExternalPower=ignore
HandleSuspendKey=ignore
IdleAction=ignore
EOF
ok "Closing the lid no longer suspends the laptop"

sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target >/dev/null 2>&1 \
  && ok "Suspend and hibernate disabled" \
  || warn "Could not mask the sleep targets"

# ========================================================== screen lock ======
step "Turning off the screen lock"

# A locked GNOME session shows the owner a lock screen they cannot get past
# without this colleague's password. It would make the remote desktop useless.
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.desktop.screensaver lock-enabled false 2>/dev/null || true
  gsettings set org.gnome.desktop.screensaver idle-activation-enabled false 2>/dev/null || true
  gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
  gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
  gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing' 2>/dev/null || true
  ok "Screen lock and screen blanking disabled"
else
  warn "gsettings not available -- check the screen lock by hand in Settings > Privacy"
fi

# =============================================================== network =====
step "Making the network come up without anybody logged in"

# A Wi-Fi profile owned by one user only connects AFTER that user logs in.
# On a laptop nobody is sitting at, that means unreachable after a reboot.
if command -v nmcli >/dev/null 2>&1; then
  while IFS= read -r con; do
    [[ -n "$con" ]] || continue
    sudo nmcli connection modify "$con" connection.permissions "" \
                                        connection.autoconnect yes 2>/dev/null || true
  done < <(nmcli -g NAME connection show 2>/dev/null)
  ok "All saved connections are system-wide and reconnect by themselves"
fi

if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q '^Status: active'; then
  sudo ufw allow 22/tcp >/dev/null 2>&1 && ok "Opened port 22 in the firewall"
else
  ok "Firewall inactive -- nothing to open"
fi

# ============================================================== serial =======
step "Serial port access"

sudo usermod -aG dialout "$USER" >/dev/null 2>&1 \
  && ok "Added $USER to the 'dialout' group (takes effect after a restart)" \
  || warn "Could not add $USER to 'dialout'"

found=0
for dev in /dev/ttyACM* /dev/ttyUSB*; do
  [[ -e "$dev" ]] || continue
  found=$((found+1))
  mdl="$(udevadm info -q property -n "$dev" 2>/dev/null | sed -n 's/^ID_MODEL=//p')"
  ok "Found $dev  ${mdl:-}"
done
[[ $found -gt 0 ]] || warn "No USB serial devices seen. Plug in the Mega and the ODrive."

# =============================================================== report ======
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
REPORT="$HOME/Desktop/rmr-ssh-details.txt"
[[ -d "$HOME/Desktop" ]] || REPORT="$HOME/rmr-ssh-details.txt"

{
  echo "RMR BENCH LAPTOP -- SSH DETAILS"
  echo "Generated $(date -Is)"
  echo
  echo "  username : $(whoami)"
  echo "  hostname : $(hostname)"
  echo "  IP       : $(hostname -I)"
  echo
  echo "  The owner connects with:"
  echo "      ssh $(whoami)@${IP}"
  echo
  echo "  SSH host key fingerprints (the owner checks these on first connect):"
  for f in /etc/ssh/ssh_host_*_key.pub; do
    ssh-keygen -lf "$f" 2>/dev/null | sed 's/^/      /'
  done
  echo
  echo "  USB serial devices present:"
  for dev in /dev/ttyACM* /dev/ttyUSB*; do
    [[ -e "$dev" ]] && echo "      $dev"
  done
} > "$REPORT" 2>/dev/null

# Drop a copy on the ShareDrive too, if it happens to be mounted.
for m in /mnt/sharedrive /media/*/ShareDrive; do
  [[ -d "$m" ]] && cp "$REPORT" "$m/" 2>/dev/null && ok "Copy left on the ShareDrive at $m" && break
done

echo
echo "======================================================================"
if [[ ${#PROBLEMS[@]} -eq 0 ]]; then
  printf '%s  SSH IS READY%s\n' "$c_grn$c_bold" "$c_reset"
else
  printf '%s  FINISHED WITH %d PROBLEM(S)%s\n' "$c_yel$c_bold" "${#PROBLEMS[@]}" "$c_reset"
  printf '    - %s\n' "${PROBLEMS[@]}"
fi
echo "======================================================================"
cat "$REPORT"
echo "======================================================================"
echo
echo "  A copy of this is on your Desktop: $(basename "$REPORT")"
echo
echo "  WHAT TO DO NOW"
echo
echo "    1. Send those details to the owner."
echo "    2. Wait. The owner logs in and tells you it works."
echo "    3. Only then, restart the laptop:   sudo reboot"
echo "    4. Log back in after the restart."
echo "    5. Wait again. The owner checks a second time."
echo "    6. When the owner says so, you are finished."
echo
echo "  WHEN YOU LEAVE"
echo
echo "    Leave the laptop switched on."
echo "    Leave it connected to mains power and to the network."
echo "    Do NOT log out. Do NOT shut down."
echo "    You can close the lid."
echo
