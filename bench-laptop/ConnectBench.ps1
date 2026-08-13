# ConnectBench.ps1
# Connect to the bench laptop (gogoj-laptop, Ubuntu) via the WireGuard mesh.
# Companion to ConnectLab.ps1, which connects to the RHEL9 lab desktop.
#
# Two routes, chosen automatically:
#   DIRECT  - the laptop is on the mesh at 10.20.30.4. Nothing in between.
#   FORWARD - the laptop is not on the mesh yet, so RHEL9 (10.20.30.2)
#             forwards onward to it on the lab LAN.
#
# Run setup-wireguard.sh on the laptop and this script upgrades itself to
# DIRECT with no edits.
#
# Place next to ConnectLab.ps1 and run with:
#   powershell -ExecutionPolicy Bypass -File ConnectBench.ps1
# Or pin a shortcut with that command line.
#
#   -ShellOnly   open an SSH session instead of the desktop
#   -NoNla       disable CredSSP if the RDP login is refused (see notes)

param(
    [switch]$ShellOnly,
    [switch]$NoNla
)

# ---------------------------------------------------------------------------
# Network parameters - mirror the mesh configuration documented in
# WireGuardRemoteDesktopSetup.md and bench-laptop/BENCH_LAPTOP_SETUP.md.
# Update those files together with this one if these change.
# ---------------------------------------------------------------------------
$HubIp        = "10.20.30.1"
$JumpIp       = "10.20.30.2"        # RHEL9 lab desktop, used only as a relay
$BenchMeshIp  = "10.20.30.4"        # bench laptop, once it joins the mesh
$BenchLanIp   = "192.168.68.59"     # bench laptop on the lab LAN
$HubLabel     = "Node0 hub"
$BenchLabel   = "gogoj-laptop"
$TunnelName   = "gogoj-mesh"
$JumpUser     = "amg17031"
$BenchUser    = "anatol"            # the LAPTOP account, not your UConn login
$LocalPort    = 13389               # 3389 is taken by RHEL9's own xrdp
$WgGuiPath    = "C:\Program Files\WireGuard\wireguard.exe"
$PingCount    = 3

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
        [string]$Label,
        [switch]$Quiet
    )

    if (-not $Quiet) {
        Write-Host -NoNewline ("  Pinging {0,-25} ({1})... " -f $Label, $Target)
    }

    $Reachable = Test-Connection -ComputerName $Target -Count $PingCount `
                                  -Quiet -ErrorAction SilentlyContinue

    if (-not $Quiet) {
        if ($Reachable) { Write-Host "OK" -ForegroundColor Green }
        else            { Write-Host "FAILED" -ForegroundColor Red }
    }
    return $Reachable
}

function Test-LocalPortFree {
    param([int]$Port)
    $InUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -eq $InUse)
}

function Show-HubFailureDiagnostic {
    Write-Host ""
    Write-Host "Cannot reach $HubLabel. Most likely causes, in order:" -ForegroundColor Yellow
    Write-Host "  1. WireGuard tunnel '$TunnelName' is not actually active."
    Write-Host "     Check the WireGuard GUI - the tunnel should show 'Active'."
    Write-Host "  2. Home internet at the Node0 site is down."
    Write-Host ""
    Write-Host "If the tunnel refuses to activate with 'The system cannot find the" -ForegroundColor Yellow
    Write-Host "file specified', the tunnel SERVICE registration is stale - not the" -ForegroundColor Yellow
    Write-Host "config. Restarting the GUI does not fix it. Delete the tunnel and" -ForegroundColor Yellow
    Write-Host "re-add it. SAVE THE PRIVATE KEY FIRST." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Clicking Edit is what triggers this. Keep a copy of the config text" -ForegroundColor DarkGray
    Write-Host "next to these scripts so you never need to open Edit to read it." -ForegroundColor DarkGray
}

function Show-BenchFailureDiagnostic {
    Write-Host ""
    Write-Host "Tunnel to $HubLabel is up but the bench laptop is unreachable" -ForegroundColor Yellow
    Write-Host "by BOTH routes (mesh and via RHEL9)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Most likely causes:"
    Write-Host "  1. The laptop is powered off, or somebody closed the lid AND"
    Write-Host "     the no-suspend settings were lost."
    Write-Host "  2. The laptop took a new DHCP lease and is no longer at"
    Write-Host "     $BenchLanIp. This is exactly what putting it on the mesh"
    Write-Host "     is meant to solve - run setup-wireguard.sh on it."
    Write-Host "  3. RHEL9 is down, which only matters on the FORWARD route."
    Write-Host ""
    Write-Host "Recovery may require someone with physical access to the lab." -ForegroundColor Yellow
}

function Show-LoginGuidance {
    Write-Section "If the RDP login is REFUSED"

    Write-Host ""
    Write-Host "This script writes an .rdp file that pins the username, so the" -ForegroundColor DarkGray
    Write-Host "Windows credential picker cannot substitute your Microsoft account." -ForegroundColor DarkGray
    Write-Host "If you are still refused, it is one of these two." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "1. The daemon is holding stale credentials." -ForegroundColor Cyan
    Write-Host "   grdctl writes to the keyring, but gnome-remote-desktop only"
    Write-Host "   reads them at startup. SSH in and restart it:"
    Write-Host ""
    Write-Host "     ssh $BenchUser@<bench-ip>" -ForegroundColor White
    Write-Host "     export XDG_RUNTIME_DIR=/run/user/`$(id -u)" -ForegroundColor White
    Write-Host "     export DBUS_SESSION_BUS_ADDRESS=unix:path=`$XDG_RUNTIME_DIR/bus" -ForegroundColor White
    Write-Host "     systemctl --user restart gnome-remote-desktop" -ForegroundColor White
    Write-Host "     grdctl status | grep -E 'Username|Password'" -ForegroundColor White
    Write-Host ""
    Write-Host "2. The login keyring is locked." -ForegroundColor Cyan
    Write-Host "   Autologin means PAM never unlocks it, so 'grdctl rdp"
    Write-Host "   set-credentials' HANGS instead of failing. Test with:"
    Write-Host ""
    Write-Host "     timeout 15 grdctl rdp set-credentials $BenchUser 'pw'; echo `$?" -ForegroundColor White
    Write-Host ""
    Write-Host "   A timeout means the keyring is locked. Fixing it needs one"
    Write-Host "   action at the PHYSICAL keyboard: Passwords and Keys (seahorse),"
    Write-Host "   right-click 'Login', Change Password, leave the new one BLANK."
    Write-Host ""
    Write-Host "The RDP password is NOT your UConn password and NOT the laptop's" -ForegroundColor Yellow
    Write-Host "Linux account password. grdctl stores a credential of its own." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Last resort: rerun this script with -NoNla, which disables CredSSP" -ForegroundColor DarkGray
    Write-Host "and moves authentication into the session instead." -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

Clear-Host
Write-Section "RMR Bench Laptop Connection"

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

# Step 2 - hub reachability
Write-Section "Verifying mesh reachability"
Write-Host ""

$HubOk = Test-PeerReachable -Target $HubIp -Label $HubLabel

if (-not $HubOk) {
    Show-HubFailureDiagnostic
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Step 3 - choose the route
Write-Host ""
Write-Host "  Looking for the bench laptop..." -ForegroundColor DarkGray

$Route     = $null
$TargetIp  = $null
$SshHost   = $null

if (Test-PeerReachable -Target $BenchMeshIp -Label "$BenchLabel (mesh)") {
    $Route    = "DIRECT"
    $TargetIp = $BenchMeshIp
    $SshHost  = "$BenchUser@$BenchMeshIp"
}
else {
    Write-Host "  Not on the mesh. Trying the RHEL9 relay instead." -ForegroundColor DarkGray
    if (Test-PeerReachable -Target $JumpIp -Label "RHEL9 relay") {
        $Route    = "FORWARD"
        $TargetIp = "localhost:$LocalPort"
        $SshHost  = "-J $JumpUser@$JumpIp $BenchUser@$BenchLanIp"
    }
}

if ($null -eq $Route) {
    Show-BenchFailureDiagnostic
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 2
}

Write-Host ""
if ($Route -eq "DIRECT") {
    Write-Host "  Route: DIRECT - the laptop is on the mesh." -ForegroundColor Green
}
else {
    Write-Host "  Route: FORWARD - via RHEL9, because the laptop is not on the mesh." -ForegroundColor Yellow
    Write-Host "         Run setup-wireguard.sh on the laptop to remove this hop." -ForegroundColor DarkGray
}

# Step 4 - SSH-only mode exits here
if ($ShellOnly) {
    Write-Section "Opening an SSH session"
    Write-Host ""
    Write-Host "  ssh $SshHost" -ForegroundColor White
    Write-Host ""
    $SshArgs = $SshHost -split ' '
    & ssh @SshArgs
    exit 0
}

# Step 5 - stand up the forward if needed
$SshProc = $null

if ($Route -eq "FORWARD") {
    Write-Section "Opening the SSH port forward"
    Write-Host ""

    if (-not (Test-LocalPortFree -Port $LocalPort)) {
        Write-Host "  Port $LocalPort is already listening - reusing the existing tunnel." `
            -ForegroundColor Yellow
    }
    else {
        Write-Host "  localhost:$LocalPort  ->  $JumpIp  ->  ${BenchLanIp}:3389"
        Write-Host ""
        Write-Host "  A second window is opening for the SSH forward." -ForegroundColor Yellow
        Write-Host "  WATCH IT - if it asks for your password or to accept a host" -ForegroundColor Yellow
        Write-Host "  key, answer it there. This window waits up to 90 seconds." -ForegroundColor Yellow
        Write-Host ""

        # Deliberately NOT minimized. ssh may prompt for a password or a
        # host key, and a hidden prompt looks identical to a hang.
        $SshProc = Start-Process ssh `
            -ArgumentList "-N", "-L", "${LocalPort}:${BenchLanIp}:3389", "$JumpUser@$JumpIp" `
            -PassThru

        Write-Host -NoNewline "  Waiting for the forward to come up... "
        $Ready = $false
        for ($i = 0; $i -lt 180; $i++) {
            Start-Sleep -Milliseconds 500
            if (-not (Test-LocalPortFree -Port $LocalPort)) { $Ready = $true; break }
            if ($SshProc.HasExited) { break }
        }

        if ($Ready) {
            Write-Host "OK" -ForegroundColor Green
        }
        else {
            Write-Host "FAILED" -ForegroundColor Red
            Write-Host ""
            if ($SshProc.HasExited) {
                Write-Host "  The SSH process exited. Read the error in its window." -ForegroundColor Yellow
            }
            else {
                Write-Host "  SSH is still running but no forward opened - it is probably" -ForegroundColor Yellow
                Write-Host "  still waiting for input in its own window." -ForegroundColor Yellow
            }
            Write-Host ""
            Write-Host "  Run this once by hand to clear any host-key prompt and to" -ForegroundColor Yellow
            Write-Host "  confirm whether it wants a password:" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "     ssh $JumpUser@$JumpIp" -ForegroundColor White
            Write-Host ""
            Write-Host "  If it asks for a password every time, set up key auth so this" -ForegroundColor DarkGray
            Write-Host "  script can run unattended:" -ForegroundColor DarkGray
            Write-Host ""
            Write-Host "     ssh-keygen -t ed25519" -ForegroundColor White
            Write-Host "     type `$env:USERPROFILE\.ssh\id_ed25519.pub | ssh $JumpUser@$JumpIp `"cat >> ~/.ssh/authorized_keys`"" -ForegroundColor White
            Write-Host ""
            if ($null -ne $SshProc -and -not $SshProc.HasExited) {
                Stop-Process -Id $SshProc.Id -ErrorAction SilentlyContinue
            }
            Read-Host "Press Enter to exit"
            exit 3
        }
    }
}

# Step 6 - write an .rdp that pins the username, then launch
Write-Section "Launching RDP session"
Write-Host ""

# Pinning the username matters. Left to itself the Windows credential picker
# offers MicrosoftAccount\<your-email>, gnome-remote-desktop cannot find that
# in its SAM database, and the login fails with no useful message.
$RdpPath = Join-Path $env:TEMP "gogoj-laptop.rdp"

$RdpLines = @(
    "full address:s:$TargetIp",
    "username:s:$BenchUser",
    "prompt for credentials:i:0",
    "administrative session:i:0",
    "screen mode id:i:2",
    "smart sizing:i:1",
    "redirectclipboard:i:1"
)

if ($NoNla) {
    $RdpLines += "enablecredsspsupport:i:0"
    $RdpLines += "authentication level:i:0"
    Write-Host "  NLA disabled (-NoNla)." -ForegroundColor Yellow
}

$RdpLines | Out-File -FilePath $RdpPath -Encoding ascii -Force

Write-Host "  Target:   $TargetIp"
Write-Host "  Username: $BenchUser" -ForegroundColor White
Write-Host ""
Write-Host "  Password: the RDP credential set with 'grdctl rdp set-credentials'." -ForegroundColor Cyan
Write-Host "            NOT your UConn password. NOT the Linux account password." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Expect a certificate warning - it is the self-signed cert generated" -ForegroundColor DarkGray
Write-Host "  on the laptop. Accepting it is correct." -ForegroundColor DarkGray
Write-Host ""

Start-Process "mstsc.exe" -ArgumentList "`"$RdpPath`""

# Step 7 - guidance, then tear down
Show-LoginGuidance

Write-Section "Once you are on the desktop"
Write-Host ""
Write-Host "  Open 'RMR Controller (full)' or 'RMR Touch Controller' from the"
Write-Host "  Desktop. Connect at 250000 baud. Send M119 to confirm the link."
Write-Host ""
Write-Host "  Serial devices on the laptop:" -ForegroundColor DarkGray
Write-Host "    /dev/rmr-mega     the Arduino Mega 2560" -ForegroundColor DarkGray
Write-Host "    /dev/rmr-odrive   the ODrive S1" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  A serial port has ONE holder. If a colleague has the UI open at" -ForegroundColor Yellow
Write-Host "  the bench, you are sharing their session and their browser - do" -ForegroundColor Yellow
Write-Host "  not open a second copy expecting it to work." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Do not command motion (G28, G1, M280, M750, M752) unless somebody" -ForegroundColor Red
Write-Host "  is in the room with the machine." -ForegroundColor Red

if ($null -ne $SshProc) {
    Write-Host ""
    Read-Host "Press Enter to close the SSH forward when you are finished"
    Stop-Process -Id $SshProc.Id -ErrorAction SilentlyContinue
    Write-Host "  Forward closed." -ForegroundColor Green
}

Write-Host ""
Write-Host "Connection script complete. Window can be closed." -ForegroundColor Green
Write-Host ""
