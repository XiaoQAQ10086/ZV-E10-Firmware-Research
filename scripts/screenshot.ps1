$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
}
"@

$process = Get-Process ZV-E10-Installer -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if (-not $process) { throw "GUI window not found" }

$rect = New-Object Win32+RECT
[Win32]::GetWindowRect($process.MainWindowHandle, [ref]$rect) | Out-Null
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$hdc = $graphics.GetHdc()
$ok = [Win32]::PrintWindow($process.MainWindowHandle, $hdc, 2)
$graphics.ReleaseHdc($hdc)
$graphics.Dispose()

$target = Join-Path (Split-Path -Parent $PSScriptRoot) "gui-window.png"
$bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Host "Saved $target ($width x $height), PrintWindow=$ok"
