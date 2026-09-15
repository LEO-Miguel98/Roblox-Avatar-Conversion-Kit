param(
  [Parameter(Mandatory=$true)][int]$ProcessId,
  [Parameter(Mandatory=$true)][string]$OutputPath
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class RackWin32 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@

$p = Get-Process -Id $ProcessId -ErrorAction Stop
for ($i = 0; $i -lt 40 -and $p.MainWindowHandle -eq 0; $i++) {
    Start-Sleep -Milliseconds 250
    $p.Refresh()
}
if ($p.MainWindowHandle -eq 0) { throw "PMXEditor has no visible main window." }
[void][RackWin32]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Milliseconds 300
$rect = New-Object RackWin32+RECT
if (-not [RackWin32]::GetWindowRect($p.MainWindowHandle, [ref]$rect)) { throw "GetWindowRect failed." }
$width = [Math]::Max(1, $rect.Right - $rect.Left)
$height = [Math]::Max(1, $rect.Bottom - $rect.Top)
$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
    $dir = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($OutputPath))
    if ($dir) { [System.IO.Directory]::CreateDirectory($dir) | Out-Null }
    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}
