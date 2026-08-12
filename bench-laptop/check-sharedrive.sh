#!/usr/bin/env bash
# =============================================================================
#  SHAREDRIVE CHECK AND MOUNT  --  Ubuntu 24.04
# =============================================================================
#
#  Checks whether the SMB/Samba ShareDrive is mounted. If it is not, it finds
#  the server, lists the shares, mounts one, and makes the mount survive a
#  reboot. Then it proves it can actually WRITE there, which is the whole
#  point -- the provisioning report has to get back to the owner.
#
#  RUN IT AS:   bash check-sharedrive.sh
#  (not with sudo -- it asks for your password when it needs it)
#
#  The owner should fill in whatever they already know below. Anything left
#  empty is either discovered automatically or asked for.
#
#  The share PASSWORD is never stored in this file. It is prompted for, and
#  written to a root-only credentials file on the laptop.
#
# =============================================================================

set -uo pipefail

# ----------------------------------------------------------------- CONFIG ---
SHARE_SERVER=""                 # e.g. "10.0.4.5" or "fileserver.local". Empty = search the LAN.
SHARE_NAME=""                   # e.g. "ShareDrive". Empty = list what the server offers.
SHARE_USER=""                   # Empty = try a guest mount first.
MOUNTPOINT="/mnt/sharedrive"
PERSIST=true                    # add it to /etc/fstab so it survives a reboot
# -----------------------------------------------------------------------------

c_reset=$'\033[0m'; c_bold=$'\033[1m'
c_red=$'\033[31m'; c_grn=$'\033[32m'; c_yel=$'\033[33m'; c_blu=$'\033[34m'
step(){ printf '\n%s==>%s %s%s%s\n' "$c_blu" "$c_reset" "$c_bold" "$*" "$c_reset"; }
ok(){   printf '  %s[ ok ]%s %s\n' "$c_grn" "$c_reset" "$*"; }
warn(){ printf '  %s[warn]%s %s\n' "$c_yel" "$c_reset" "$*"; }
bad(){  printf '  %s[FAIL]%s %s\n' "$c_red" "$c_reset" "$*"; }

[[ $EUID -ne 0 ]] || { echo "Run this WITHOUT sudo: bash $0"; exit 1; }

# ======================================================= 1. already there? ===
step "Is anything mounted already?"

if findmnt -t cifs -n >/dev/null 2>&1; then
  ok "CIFS mounts found:"
  findmnt -t cifs -o TARGET,SOURCE,OPTIONS | sed 's/^/     /'
else
  warn "No CIFS mount on this laptop yet"
fi

if mountpoint -q "$MOUNTPOINT" 2>/dev/null; then
  ok "$MOUNTPOINT is already mounted"
  if touch "$MOUNTPOINT/.rmr-write-test" 2>/dev/null; then
    rm -f "$MOUNTPOINT/.rmr-write-test"
    ok "And it is WRITABLE. Nothing to do."
    echo
    echo "  Share source: $(findmnt -n -o SOURCE --target "$MOUNTPOINT")"
    exit 0
  else
    bad "Mounted but NOT writable. Re-mounting with credentials below."
    sudo umount "$MOUNTPOINT" 2>/dev/null || true
  fi
fi

# =========================================================== 2. packages =====
step "Making sure the SMB tools are installed"
if ! command -v mount.cifs >/dev/null 2>&1 || ! command -v smbclient >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y cifs-utils smbclient >/dev/null 2>&1 \
    && ok "Installed cifs-utils and smbclient" \
    || { bad "Could not install the SMB tools. Is there internet?"; exit 1; }
else
  ok "cifs-utils and smbclient present"
fi

# =========================================================== 3. find server ==
step "Finding the file server"

if [[ -z "$SHARE_SERVER" ]]; then
  myip="$(hostname -I | awk '{print $1}')"
  subnet="${myip%.*}"
  echo "  Scanning ${subnet}.0/24 for SMB (port 445). About 10 seconds."

  found=()
  for i in $(seq 1 254); do
    ( timeout 1 bash -c "echo > /dev/tcp/${subnet}.${i}/445" 2>/dev/null \
      && echo "${subnet}.${i}" ) &
  done > /tmp/rmr-smb-hosts 2>/dev/null
  wait
  mapfile -t found < <(sort -u /tmp/rmr-smb-hosts 2>/dev/null | grep -v '^$')

  if [[ ${#found[@]} -eq 0 ]]; then
    bad "No SMB servers found on this subnet."
    read -rp "  Type the server IP or name: " SHARE_SERVER
  elif [[ ${#found[@]} -eq 1 ]]; then
    SHARE_SERVER="${found[0]}"
    ok "Found one SMB server: $SHARE_SERVER"
  else
    echo "  Found ${#found[@]} SMB servers:"
    for i in "${!found[@]}"; do
      name="$(nmblookup -A "${found[$i]}" 2>/dev/null | awk '/<00>/ && !/GROUP/ {print $1; exit}')"
      printf '     [%d] %s %s\n' "$((i+1))" "${found[$i]}" "${name:+($name)}"
    done
    read -rp "  Which number? " pick
    SHARE_SERVER="${found[$((pick-1))]}"
  fi
fi
[[ -n "$SHARE_SERVER" ]] || { bad "No server. Stopping."; exit 1; }
ok "Server: $SHARE_SERVER"

# ============================================================ 4. credentials =
step "Credentials"

if [[ -z "$SHARE_USER" ]]; then
  echo "  Leave the username empty to try a guest (no password) mount."
  read -rp "  Share username [guest]: " SHARE_USER
fi
SHARE_PASS=""
if [[ -n "$SHARE_USER" ]]; then
  read -rsp "  Share password for '$SHARE_USER': " SHARE_PASS; echo
fi

# ============================================================== 5. shares ====
step "Listing the shares on $SHARE_SERVER"

if [[ -n "$SHARE_USER" ]]; then
  listing="$(smbclient -L "//$SHARE_SERVER" -U "$SHARE_USER%$SHARE_PASS" 2>/dev/null)"
else
  listing="$(smbclient -L "//$SHARE_SERVER" -N 2>/dev/null)"
fi

if [[ -n "$listing" ]]; then
  echo "$listing" | awk '/Disk/ && $1 !~ /\$$/ {print "     " $1}' | sort -u
else
  warn "Could not list the shares (this is common; the mount may still work)"
fi

if [[ -z "$SHARE_NAME" ]]; then
  read -rp "  Which share do you want to mount? " SHARE_NAME
fi
[[ -n "$SHARE_NAME" ]] || { bad "No share name. Stopping."; exit 1; }

UNC="//$SHARE_SERVER/$SHARE_NAME"

# =============================================================== 6. mount ====
step "Mounting $UNC at $MOUNTPOINT"

sudo mkdir -p "$MOUNTPOINT"
CRED=/etc/rmr-share.cred

if [[ -n "$SHARE_USER" ]]; then
  # Credentials live in a root-only file, NOT in /etc/fstab, so the password
  # is not readable by every account on the laptop.
  printf 'username=%s\npassword=%s\n' "$SHARE_USER" "$SHARE_PASS" | sudo tee "$CRED" >/dev/null
  sudo chmod 600 "$CRED"
  OPTS="credentials=$CRED,uid=$(id -u),gid=$(id -g),file_mode=0664,dir_mode=0775,iocharset=utf8,nofail,x-systemd.automount"
else
  OPTS="guest,uid=$(id -u),gid=$(id -g),file_mode=0664,dir_mode=0775,iocharset=utf8,nofail,x-systemd.automount"
fi

if sudo mount -t cifs "$UNC" "$MOUNTPOINT" -o "$OPTS" 2>/tmp/rmr-mount-err; then
  ok "Mounted"
else
  bad "Mount failed:"
  sed 's/^/     /' /tmp/rmr-mount-err
  echo
  echo "  Common causes:"
  echo "    - wrong password"
  echo "    - the share needs an older protocol: add  ,vers=2.0  or  ,vers=1.0"
  echo "    - the share name is wrong (check the list above)"
  exit 1
fi

# ========================================================== 7. write test ====
step "Can we actually write to it?"

if touch "$MOUNTPOINT/.rmr-write-test" 2>/dev/null; then
  rm -f "$MOUNTPOINT/.rmr-write-test"
  ok "WRITABLE -- the provisioning report will reach the owner"
else
  bad "Mounted READ-ONLY. The owner will not get the report here."
  warn "Ask for write permission, or the report gets left on the Desktop instead."
fi

# ============================================================= 8. persist ====
if [[ "$PERSIST" == true ]]; then
  step "Making it survive a reboot"
  if grep -qF "$MOUNTPOINT" /etc/fstab; then
    ok "Already in /etc/fstab"
  else
    # 'nofail' matters: without it, a file server that is down at boot time
    # stops the laptop from booting at all.
    echo "$UNC  $MOUNTPOINT  cifs  $OPTS  0  0" | sudo tee -a /etc/fstab >/dev/null
    sudo systemctl daemon-reload
    ok "Added to /etc/fstab with 'nofail' (a missing server can never block boot)"
  fi
fi

# ============================================================== 9. report ====
echo
echo "======================================================================"
echo "  SHAREDRIVE READY"
echo "======================================================================"
echo "  UNC path    : $UNC"
echo "  Mounted at  : $MOUNTPOINT"
echo "  Login       : ${SHARE_USER:-guest}"
echo "  Survives reboot: $PERSIST"
echo
echo "  Tell the owner this line:"
echo "      SHARE_UNC=\"$UNC\""
echo "======================================================================"
echo
echo "  Top level of the share:"
ls -la "$MOUNTPOINT" 2>/dev/null | head -20 | sed 's/^/     /'
echo
