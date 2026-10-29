param([switch]$Stop, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'mineru-env.ps1')
    $pythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
    $launcher = Join-Path $PSScriptRoot 'mineru_web_launcher.py'
    $launcherArgs = @('-B', ('"' + $launcher + '"'))
    if ($Stop) { $launcherArgs += '--stop' }
    if ($NoBrowser) { $launcherArgs += '--no-browser' }
    Start-Process -FilePath $pythonw -ArgumentList $launcherArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'MinerU startup error') | Out-Null
}
