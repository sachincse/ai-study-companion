# Start backend + frontend dev servers on Windows.
#   powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -SetupOnly   (setup only, no servers; used for testing)
# The flag lets PowerShell run this one script without changing any system setting,
# and nothing below needs an activation script, so the default execution policy is fine.
# Every run repairs the setup: .env (with a random SECRET_KEY), backend\.venv (Python 3.11+) and the
# pip / npm installs, which run again after a failure or when requirements*.txt / package-lock.json change.
param([switch]$SetupOnly)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venv = Join-Path $backend ".venv"
$py = Join-Path $venv "Scripts\python.exe"
$minPython = [version]"3.11"
$versionCode = "import sys; print('%d.%d.%d' % sys.version_info[:3])"
# A SECRET_KEY line in .env; group 1 is everything before the value.
$keyLine = '(?m)^([ \t]*(?:export[ \t]+)?SECRET_KEY[ \t]*=)([^\r\n]*)'

function Stop-Setup([string]$Message) {
  Write-Host $Message -ForegroundColor Red
  exit 1
}

# Runs a program with its output going to the console; callers check $LASTEXITCODE. "Continue" keeps
# Windows PowerShell 5.1 from turning stderr output (pip and npm warnings) into terminating errors.
function Invoke-Native([string]$FilePath, [string[]]$Arguments) {
  $ErrorActionPreference = "Continue"
  & $FilePath @Arguments
}

# Runs a program and returns its trimmed stdout, or $null when it does not start or exits non-zero.
function Get-NativeOutput([string]$FilePath, [string[]]$Arguments) {
  $ErrorActionPreference = "Continue"
  try { $out = & $FilePath @Arguments 2>$null } catch { return $null }
  if ($LASTEXITCODE -ne 0) { return $null }
  ($out | Out-String).Trim()
}

# The Python that creates backend\.venv: "python" from PATH, else the py launcher ("py -3", then the newest
# 3.x it has; an older launcher's -3 is not always the newest installed version).
function Find-Python {
  $found = @()
  $candidates = @(@{ Exe = "python"; Pre = @() }, @{ Exe = "py"; Pre = @("-3") }) + @(foreach ($v in "3.15", "3.14", "3.13", "3.12", "3.11") { @{ Exe = "py"; Pre = @("-$v") } })
  foreach ($candidate in $candidates) {
    $out = Get-NativeOutput $candidate.Exe ($candidate.Pre + @("-c", "$versionCode; print(sys.executable)"))
    if (-not $out) { continue }
    $version, $path = $out -split "\r?\n"
    $parsed = $version -as [version]
    if ($parsed -and $parsed -ge $minPython) { return $candidate + @{ Version = $version; Path = $path } }
    $found += "$($candidate.Exe) is Python $version ($path)"
  }
  $what = if ($found) { $found -join ", " } else { "no working Python was found (tried python, py -3 and py -3.11 to -3.15)" }
  Stop-Setup "Python 3.11 or newer is required to create backend\.venv, but $what. Install it from https://www.python.org/downloads/ (tick ""Add python.exe to PATH""), open a new terminal and run this script again."
}

# Value of the last SECRET_KEY line (python-dotenv lets the last one win), unquoted, inline comment dropped.
function Get-SecretKey([string]$Text) {
  $lines = [regex]::Matches($Text, $keyLine)
  if ($lines.Count -eq 0) { return "" }
  $value = $lines[$lines.Count - 1].Groups[2].Value.Trim()
  if ($value -match '^"([^"]*)"' -or $value -match "^'([^']*)'") { return $Matches[1].Trim() }
  ($value -replace '\s+#.*$', '').Trim()
}

# Same rule as backend/app/core/config.py: missing, empty, the "change-me" placeholder or under 32 bytes.
function Test-WeakSecret([string]$Key) {
  -not $Key -or $Key.StartsWith("change-me", [StringComparison]::Ordinal) -or [Text.Encoding]::UTF8.GetByteCount($Key) -lt 32
}

# SHA-256 of the files' bytes back to back (what `cat ... | sha256sum` gives in dev.sh); a missing file counts as empty.
function Get-FilesHash([string[]]$Paths) {
  $data = [IO.MemoryStream]::new()
  foreach ($path in $Paths) {
    if (Test-Path -LiteralPath $path -PathType Leaf) { $bytes = [IO.File]::ReadAllBytes($path); $data.Write($bytes, 0, $bytes.Length) }
  }
  $sha = [Security.Cryptography.SHA256]::Create()
  try { -join ($sha.ComputeHash($data.ToArray()) | ForEach-Object { $_.ToString("x2") }) } finally { $sha.Dispose() }
}

# An install is current when its stamp file holds the hash of the files it was installed from.
function Test-Stamp([string]$Stamp, [string]$Hash) {
  (Test-Path -LiteralPath $Stamp -PathType Leaf) -and ([string](Get-Content -LiteralPath $Stamp -Raw)).Trim() -eq $Hash
}

# A -EncodedCommand payload for a server window. Every value becomes an escaped single-quoted literal and the
# command travels Base64-encoded, so spaces, apostrophes or brackets in the folder path cannot break it.
function ConvertTo-Literal([string]$Text) {
  "'" + [Management.Automation.Language.CodeGeneration]::EscapeSingleQuotedStringContent($Text) + "'"
}
function New-ServerCommand([string]$Title, [string]$Directory, [string]$FilePath, [string[]]$Arguments) {
  $call = (@($FilePath) + $Arguments | ForEach-Object { ConvertTo-Literal $_ }) -join " "
  $command = "`$Host.UI.RawUI.WindowTitle = $(ConvertTo-Literal $Title); " +
    "Set-Location -LiteralPath $(ConvertTo-Literal $Directory) -ErrorAction Stop; & $call"
  [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}

# .env: copied from .env.example on the first run.
if (-not (Test-Path -LiteralPath $envFile)) {
  if (-not (Test-Path -LiteralPath $envExample)) { Stop-Setup ".env.example is missing; restore it with: git checkout -- .env.example" }
  Copy-Item -LiteralPath $envExample -Destination $envFile
  Write-Host "Created .env from .env.example - add an API key (or use Ollama) before chatting." -ForegroundColor Yellow
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  Stop-Setup "npm.cmd was not found. Install Node.js 22.12 or newer from https://nodejs.org/, open a new terminal and run this script again."
}

# backend\.venv: created with Python 3.11+; an existing venv is checked as well.
if (-not (Test-Path -LiteralPath $py -PathType Leaf)) {
  $base = Find-Python
  Write-Host "Creating backend\.venv with Python $($base.Version) ($($base.Path))..."
  $hadVenv = Test-Path -LiteralPath $venv
  Invoke-Native $base.Exe ($base.Pre + @("-m", "venv", $venv))
  $code = $LASTEXITCODE
  if ($code -ne 0 -or -not (Test-Path -LiteralPath $py -PathType Leaf)) {
    if (-not $hadVenv) { Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction SilentlyContinue }
    Stop-Setup "Creating backend\.venv failed (exit code $code, see above). Fix the cause and run this script again."
  }
}
$venvVersion = (Get-NativeOutput $py @("-c", $versionCode)) -as [version]
if (-not $venvVersion) {
  Stop-Setup "backend\.venv is broken: its python.exe does not run (often the Python it was created from was removed or upgraded). Delete the backend\.venv folder and run this script again."
}
if ($venvVersion -lt $minPython) {
  Stop-Setup "backend\.venv uses Python $venvVersion, but 3.11 or newer is required. Delete the backend\.venv folder, install Python 3.11+ from https://www.python.org/downloads/ and run this script again."
}

# SECRET_KEY: replaced whenever it is weak, so a .env copied by hand gets one too. It is generated with the
# venv's python, and .env is written as UTF-8 without a BOM (Set-Content in PowerShell 5.1 writes ANSI or a BOM).
$envText = [string](Get-Content -LiteralPath $envFile -Raw -Encoding UTF8)
if (Test-WeakSecret (Get-SecretKey $envText)) {
  $secret = Get-NativeOutput $py @("-c", "import secrets; print(secrets.token_urlsafe(48))")
  if ($secret -cnotmatch '^[A-Za-z0-9_-]{32,}$') {
    Stop-Setup "Could not generate a SECRET_KEY with backend\.venv\Scripts\python.exe; .env was not changed. Run this script again."
  }
  if ([regex]::IsMatch($envText, $keyLine)) {
    $envText = [regex]::Replace($envText, $keyLine, '${1}' + $secret)
  } else {
    $newline = if ($envText.Contains("`r`n")) { "`r`n" } else { "`n" }
    if ($envText -and -not $envText.EndsWith("`n")) { $envText += $newline }
    $envText += "SECRET_KEY=$secret$newline"
  }
  try {
    [IO.File]::WriteAllText($envFile, $envText, [Text.UTF8Encoding]::new($false))
  } catch {
    Stop-Setup "Could not write SECRET_KEY to .env ($($_.Exception.Message)). Make sure the file is writable and not open in another program, then run this script again."
  }
  if ((Get-SecretKey ([string](Get-Content -LiteralPath $envFile -Raw -Encoding UTF8))) -cne $secret) {
    Stop-Setup "Could not write SECRET_KEY to .env; check that the file is writable and run this script again."
  }
  Write-Host "Generated a random SECRET_KEY in .env" -ForegroundColor Yellow
}

# Backend packages: installed again when the stamp is missing or requirements*.txt changed.
$requirements = Join-Path $backend "requirements-dev.txt"
$backendStamp = Join-Path $venv ".deps-installed"
$backendHash = Get-FilesHash @((Join-Path $backend "requirements.txt"), $requirements)
if (Test-Stamp $backendStamp $backendHash) {
  Write-Host "Backend dependencies are up to date."
} else {
  Write-Host "Installing backend dependencies (pip install -r backend\requirements-dev.txt)..."
  Remove-Item -LiteralPath $backendStamp -Force -ErrorAction SilentlyContinue
  Invoke-Native $py @("-m", "pip", "install", "--disable-pip-version-check", "-r", $requirements)
  if ($LASTEXITCODE -ne 0) {
    Stop-Setup "pip install failed (exit code $LASTEXITCODE, see above). Fix the cause (network, proxy, disk space) and run this script again; it retries the install."
  }
  Set-Content -LiteralPath $backendStamp -Value $backendHash -Encoding Ascii
}

# Frontend packages: installed again when the stamp is missing or package-lock.json changed.
$lockFile = Join-Path $frontend "package-lock.json"
$frontendStamp = Join-Path $frontend "node_modules\.deps-installed"
if (Test-Stamp $frontendStamp (Get-FilesHash @($lockFile))) {
  Write-Host "Frontend dependencies are up to date."
} else {
  Write-Host "Installing frontend dependencies (npm install)..."
  Remove-Item -LiteralPath $frontendStamp -Force -ErrorAction SilentlyContinue
  Push-Location -LiteralPath $frontend
  try { Invoke-Native "npm.cmd" @("install"); $code = $LASTEXITCODE } finally { Pop-Location }
  if ($code -ne 0) {
    Stop-Setup "npm install failed (exit code $code, see above). Fix the cause (network, proxy, Node.js older than 22.12) and run this script again; it retries the install."
  }
  # Hashed after the install because npm may rewrite package-lock.json; an empty project gets no node_modules.
  [void][IO.Directory]::CreateDirectory((Split-Path -Parent $frontendStamp))
  Set-Content -LiteralPath $frontendStamp -Value (Get-FilesHash @($lockFile)) -Encoding Ascii
}

if ($SetupOnly) {
  Write-Host "Setup complete; servers not started (-SetupOnly)." -ForegroundColor Green
  exit 0
}

# One window per server. The venv's python.exe and npm.cmd are called directly (no Activate.ps1 / npm.ps1).
$backendCommand = New-ServerCommand "AI Study Companion - backend" $backend $py @("-m", "uvicorn", "app.main:app", "--reload", "--port", "8000")
$frontendCommand = New-ServerCommand "AI Study Companion - frontend" $frontend "npm.cmd" @("run", "dev")
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $backendCommand
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $frontendCommand
Write-Host "Backend: http://localhost:8000/api/docs   Frontend: http://localhost:5173" -ForegroundColor Green
