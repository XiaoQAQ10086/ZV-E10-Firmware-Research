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

# Portable distribution: extract, run, and keep backups beside the executable.
$portable = Join-Path $dist "ZV-E10-Portable"
New-Item -ItemType Directory -Force $portable | Out-Null
Copy-Item (Join-Path $dist "ZV-E10-Installer.exe") $portable
Copy-Item (Join-Path $dist "zve10-installer.exe") $portable
Copy-Item (Join-Path $repo "README.md") $portable
Copy-Item (Join-Path $repo "LICENSE") $portable
Copy-Item (Join-Path $repo "NOTICE.md") $portable
Copy-Item (Join-Path $repo "docs") $portable -Recurse
$licenses = Join-Path $portable "licenses"
New-Item -ItemType Directory -Force $licenses | Out-Null
Copy-Item (Join-Path $repo "vendor\zadig\COPYING.txt") $licenses
Copy-Item (Join-Path $repo "vendor\zadig\SOURCE.txt") $licenses
$backup = Join-Path $portable "backup"
New-Item -ItemType Directory -Force $backup | Out-Null
@"
Backups and run evidence are written here by ZV-E10-Installer.
Do not delete this folder while a check or write is running.
"@ | Set-Content -Path (Join-Path $backup "README.txt") -Encoding ASCII

$zip = Join-Path $dist "ZV-E10-Portable.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $portable -DestinationPath $zip -CompressionLevel Optimal
Write-Host "  $zip  (portable folder)"
