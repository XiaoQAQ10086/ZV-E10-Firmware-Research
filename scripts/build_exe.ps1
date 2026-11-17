param(
    [Parameter(Mandatory = $true)][string]$Upstream
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $repo "build\upstream"
$dist = Join-Path $repo "dist"
$work = Join-Path $repo "build\pyinstaller"

if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Force $stage | Out-Null

robocopy $Upstream $stage /E /XD private .git __pycache__ /XF *.bin *.elf /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

$main = (git -C $Upstream rev-parse HEAD).Trim()
$toolkit = (git -C (Join-Path $Upstream "vendor\zv-e10-toolkit") rev-parse HEAD).Trim()
$pmca = (git -C (Join-Path $Upstream "vendor\zv-e10-toolkit\linux\vendor\Sony-PMCA-RE") rev-parse HEAD).Trim()

$json = @"
{
  "main": "$main",
  "toolkit": "$toolkit",
  "pmca": "$pmca"
}
"@
[System.IO.File]::WriteAllText((Join-Path $stage "PIN.json"), $json, [System.Text.UTF8Encoding]::new($false))

$env:ZVE10_UPSTREAM_BUILD = $stage
$pyinstaller = if ($env:ZVE10_PYINSTALLER) {
    $env:ZVE10_PYINSTALLER
} else {
    Join-Path $repo ".venv\Scripts\pyinstaller.exe"
}
& $pyinstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $repo "packaging\zve10_installer.spec")
& $pyinstaller --noconfirm --clean --distpath $dist --workpath (Join-Path $repo "build\pyinstaller-gui") (Join-Path $repo "packaging\zve10_installer_gui.spec")

Write-Host ""
Write-Host "Built:"
Write-Host "  $dist\zve10-installer.exe   (console CLI)"
Write-Host "  $dist\ZV-E10-Installer.exe  (GUI)"
