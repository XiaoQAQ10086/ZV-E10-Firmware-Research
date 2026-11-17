param(
    [Parameter(Mandatory = $true)][string]$Upstream
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Upstream)) {
    throw "upstream checkout not found: $Upstream"
}

if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}

$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -e .

Write-Host ""
Write-Host "Installed. Next:"
Write-Host "  .\.venv\Scripts\zve10-installer.exe doctor --upstream `"$Upstream`""
Write-Host "  .\.venv\Scripts\zve10-installer.exe inspect --upstream `"$Upstream`""
Write-Host ""
Write-Host "Remember: install the upstream toolkit dependencies in this venv too."
