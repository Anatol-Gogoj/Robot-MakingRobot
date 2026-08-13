# ConnectLab.ps1
# Connect to the RHEL9 lab desktop (hc18kx2.engr.uconn.edu) via the WireGuard mesh.
# Activates verification flow: prompts for tunnel activation, pings hub and lab,
# clears any stale console session, then launches mstsc at a proper resolution.
#
# Place this script anywhere convenient (Desktop, ~\Scripts\) and run with:
#   powershell -ExecutionPolicy Bypass -File ConnectLab.ps1
# Or pin a shortcut with that command line.
#
#   -Windowed    open in a window instead of fullscreen
#   -MultiMon    span all monitors
#   -SkipCheck   do not look for a stale console session

param(
    [switch]$Windowed,
    [switch]$MultiMon,
    [switch]$SkipCheck
)

# ---------------------------------------------------------------------------
# Network parameters - mirror the mesh configuration documented in
# WireGuardRemoteDesktopSetup.md. Update both files together if these change.
# ---------------------------------------------------------------------------
$HubIp        = "10.20.30.1"
$LabIp        = "10.20.30.2"
$HubLabel     = "Node0 hub"
$LabLabel     = "RHEL9 lab (hc18kx2)"
$TunnelName   = "gogoj-mesh"
$LabUser      = "amg17031"
$WgGuiPath    = "C:\Program Files\WireGuard\wireguard.exe"
$PingCount    = 3

# ---------------------------------------------------------------------------
# Display parameters
#
# xrdp creates a NEW session, so its display is virtual and can be whatever we
# ask for - unlike a shared-session remote desktop, which is capped at the
# physical panel of the machine it mirrors. Ask for the full 1920x1080.
#
# desktopscalefactor 100 matters as much as the resolution: with Windows at
# 150% DPI, a session gets scaled up and everything looks blown up regardless
# of how many pixels it actually has.
# ---------------------------------------------------------------------------
$RdpWidth     = 1920
$RdpHeight    = 1080
$RdpScale     = 100      # percent; 100 = no DPI inflation

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host " $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Test-PeerReachable {
    param(
        [string]$Target,
        [string]$Label
    )

    Write-Host -NoNewline ("  Pinging {0,-25} ({1})... " -f $Label, $Target)

    $Reachable = Test-Connection -ComputerName $Target -Count $PingCount `
                                  -Quiet -ErrorAction SilentlyContinue

    if ($Reachable) {
        Write-Host "OK" -ForegroundColor Green
        return $true
    }
    else {
        Write-Host "FAILED" -ForegroundColor Red
        return $false
    }
}

function Show-HubFailureDiagnostic {
    Write-Host ""
    Write-Host "Cannot reach $HubLabel. Most likely causes, in order:" -ForegroundColor Yellow
    Write-Host "  1. WireGuard tunnel '$TunnelName' is not actually active."
    Write-Host "     Check the WireGuard GUI - the tunnel should show 'Active'."
    Write-Host "  2. Home internet at the Node0 site is down."
    Write-Host "  3. wg.gogoj.cloud resolution is stale (very rare; Node0 runs a DDNS updater)."
    Write-Host ""
    Write-Host "Try: deactivate and reactivate the tunnel in the WireGuard GUI, then rerun." `
        -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If the tunnel refuses to activate with 'The system cannot find the file" -ForegroundColor DarkGray
    Write-Host "specified', the tunnel SERVICE registration is stale, not the config." -ForegroundColor DarkGray
    Write-Host "Restarting the GUI does not fix it - delete the tunnel and re-add it." -ForegroundColor DarkGray
    Write-Host "SAVE THE PRIVATE KEY FIRST. Clicking Edit is what triggers this." -ForegroundColor DarkGray
}

function Show-LabFailureDiagnostic {
    Write-Host ""
    Write-Host "Tunnel to $HubLabel is up but $LabLabel is unreachable." -ForegroundColor Yellow
    Write-Host "Most likely causes:"
    Write-Host "  1. Lab desktop is powered off or lost network."
    Write-Host "  2. wg-quick@wg0.service on the lab did not come up after a reboot."
    Write-Host "  3. UConn outbound firewall dropped the keepalive (unusual but possible)."
    Write-Host ""
    Write-Host "If 2 or 3, recovery requires someone with physical access to the lab." `
        -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Stale console session check
#
# The black screen happens because there are TWO sessions for one user: a local
# GNOME session on seat0 and the new one xrdp spawns. Both want
# /run/user/<uid>, they collide, and MATE cannot resolve monitor info.
#
# This finds the local one BEFORE connecting, so the collision never happens.
# It replaces the after-the-fact recovery in Show-BlackScreenGuidance.
# ---------------------------------------------------------------------------
function Get-StaleConsoleSession {
    # Version-independent: list session ids, then ask about each one by
    # property rather than parsing loginctl's columns, which move between
    # systemd releases.
    $probe = @'
for s in $(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}'); do
  seat=$(loginctl show-session $s -p Seat --value 2>/dev/null)
  tty=$(loginctl show-session $s -p TTY --value 2>/dev/null)
  cls=$(loginctl show-session $s -p Class --value 2>/dev/null)
  rem=$(loginctl show-session $s -p Remote --value 2>/dev/null)
  if [ "$seat" = "seat0" ] && [ "$cls" = "user" ] && [ "$rem" = "no" ]; then
    echo "$s|$tty"
  fi
done
'@ -replace "`r`n", "`n"

    # BatchMode so a password prompt fails fast instead of hanging invisibly.
    $out = & ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new `
                 "$LabUser@$LabIp" $probe 2>&1

    if ($LASTEXITCODE -ne 0) { return $null }   # no key auth, or ssh unavailable
    return @($out | Where-Object { $_ -match '^\d+\|' })
}

function Invoke-ConsoleSessionCleanup {
    Write-Section "Checking for a stale console session"
    Write-Host ""

    $sessions = Get-StaleConsoleSession

    if ($null -eq $sessions) {
        Write-Host "  Could not check - SSH needs a password from this machine." -ForegroundColor DarkGray
        Write-Host "  Set up key auth and this check runs automatically next time:" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "     ssh-keygen -t ed25519" -ForegroundColor White
        Write-Host "     type `$env:USERPROFILE\.ssh\id_ed25519.pub | ssh $LabUser@$LabIp `"cat >> ~/.ssh/authorized_keys`"" -ForegroundColor White
        Write-Host ""
        Write-Host "  Continuing. If you land on a black screen, see the guidance below." -ForegroundColor DarkGray
        return
    }

    if ($sessions.Count -eq 0) {
        Write-Host "  No local console session. A black screen is unlikely." -ForegroundColor Green
        return
    }

    Write-Host "  Found a local GNOME session on seat0:" -ForegroundColor Yellow
    foreach ($s in $sessions) {
        $parts = $s -split '\|'
        Write-Host ("    session {0}  on {1}" -f $parts[0], $parts[1])
    }
    Write-Host ""
    Write-Host "  This is what causes the black screen. Terminating it now avoids" -ForegroundColor Yellow
    Write-Host "  the collision entirely." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  It will close anything left open on the lab's PHYSICAL screen." -ForegroundColor Red
    Write-Host "  Do not do this if somebody is sitting at the machine." -ForegroundColor Red
    Write-Host ""

    $answer = Read-Host "  Terminate it? (y/N)"
    if ($answer -notmatch "^[Yy]") {
        Write-Host "  Left alone. Expect a black screen; see the guidance below." -ForegroundColor DarkGray
        return
    }

    foreach ($s in $sessions) {
        $id = ($s -split '\|')[0]
        # Terminating your own session normally needs no escalation. If polkit
        # refuses, say so rather than hanging on a sudo password prompt.
        & ssh -o BatchMode=yes -o ConnectTimeout=8 "$LabUser@$LabIp" `
              "loginctl terminate-session $id" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Terminated session $id." -ForegroundColor Green
        }
        else {
            Write-Host "  Could not terminate session $id without escalation." -ForegroundColor Yellow
            Write-Host "  Run this by hand:" -ForegroundColor Yellow
            Write-Host "     ssh $LabUser@$LabIp 'sudo loginctl terminate-session $id'" -ForegroundColor White
        }
    }
    Start-Sleep -Seconds 2
}

function Show-BlackScreenGuidance {
    Write-Section "If you land on a BLACK SCREEN after login"

    Write-Host ""
    Write-Host "Cause: a stale local GNOME-Wayland session for $LabUser exists on the"
    Write-Host "lab's physical console (seat0). Both that session and your RDP session"
    Write-Host "share /run/user/159550375, and MATE cannot resolve monitor info."
    Write-Host ""
    Write-Host "The pre-flight check above normally prevents this. It only reaches" -ForegroundColor DarkGray
    Write-Host "here if the check could not run, or you declined it." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Fix:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1. Open a second PowerShell window."
    Write-Host "  2. SSH in via the same tunnel:"
    Write-Host ""
    Write-Host "       ssh $LabUser@$LabIp" -ForegroundColor White
    Write-Host ""
    Write-Host "  3. List active sessions:"
    Write-Host ""
    Write-Host "       loginctl list-sessions" -ForegroundColor White
    Write-Host ""
    Write-Host "  4. Find the session on seat0 with a TTY entry (the local GUI session)."
    Write-Host "     IGNORE pts/X entries - those are SSH sessions including this one."
    Write-Host ""
    Write-Host "  5. Terminate ONLY that session (NEVER terminate-user, that kills SSH):"
    Write-Host ""
    Write-Host "       sudo loginctl terminate-session <seat0-session-id>" -ForegroundColor White
    Write-Host ""
    Write-Host "  6. Close the RDP window, run this script again to reconnect."
    Write-Host ""
    Write-Host "Long-term: log out of the local GNOME session before leaving the lab." `
        -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

Clear-Host
Write-Section "Lab Remote Desktop Connection"

# Step 1 - prompt for WG activation
Write-Host ""
Write-Host "STEP 1: Activate the WireGuard tunnel '$TunnelName'." -ForegroundColor Yellow
Write-Host "         The tunnel must be ACTIVE in the WireGuard GUI before continuing."
Write-Host ""

if (Test-Path $WgGuiPath) {
    $LaunchWg = Read-Host "Open the WireGuard GUI now? (y/N)"
    if ($LaunchWg -match "^[Yy]") {
        Start-Process $WgGuiPath
        Write-Host "  WireGuard GUI opened." -ForegroundColor Green
    }
}
else {
    Write-Host "  (WireGuard GUI not found at default install path; activate manually.)" `
        -ForegroundColor DarkGray
}

Write-Host ""
Read-Host "Press Enter once the '$TunnelName' tunnel is active"

# Step 2 - reachability checks
Write-Section "Verifying mesh reachability"
Write-Host ""

$HubOk = Test-PeerReachable -Target $HubIp -Label $HubLabel

if (-not $HubOk) {
    Show-HubFailureDiagnostic
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

$LabOk = Test-PeerReachable -Target $LabIp -Label $LabLabel

if (-not $LabOk) {
    Show-LabFailureDiagnostic
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 2
}

# Step 3 - clear the stale console session before it can collide
if (-not $SkipCheck) {
    Invoke-ConsoleSessionCleanup
}

# Step 4 - build an .rdp and launch
Write-Section "Launching RDP session"
Write-Host ""

$RdpPath = Join-Path $env:TEMP "lab-rhel9.rdp"

$ScreenMode = 2                      # 2 = fullscreen, 1 = windowed
if ($Windowed) { $ScreenMode = 1 }

$RdpLines = @(
    "full address:s:$LabIp",
    "username:s:$LabUser",
    "screen mode id:i:$ScreenMode",
    "desktopwidth:i:$RdpWidth",
    "desktopheight:i:$RdpHeight",
    "desktopscalefactor:i:$RdpScale",
    "smart sizing:i:0",              # 0 = show true pixels, do not rescale
    "dynamic resolution:i:1",        # resize the session with the window
    "redirectclipboard:i:1",
    "authentication level:i:0",      # xrdp's cert is self-signed
    "prompt for credentials:i:0"     # the xrdp greeter asks, not Windows
)

if ($MultiMon) { $RdpLines += "use multimon:i:1" }

$RdpLines | Out-File -FilePath $RdpPath -Encoding ascii -Force

Write-Host "Connecting to $LabIp at ${RdpWidth}x${RdpHeight}..."
if ($MultiMon) { Write-Host "  Spanning all monitors." -ForegroundColor DarkGray }
Write-Host ""
Write-Host "At the xrdp login dialog:" -ForegroundColor Cyan
Write-Host "  Session:  Xorg" -ForegroundColor White
Write-Host "  Username: $LabUser" -ForegroundColor White
Write-Host "  Password: your AD/SSSD password"
Write-Host ""

Start-Process "mstsc.exe" -ArgumentList "`"$RdpPath`""

# Step 5 - print black-screen debug reference
Show-BlackScreenGuidance

Write-Host ""
Write-Host "Connection script complete. Window can be closed." -ForegroundColor Green
Write-Host ""
