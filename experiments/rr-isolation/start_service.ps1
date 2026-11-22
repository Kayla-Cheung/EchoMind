param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [ValidateRange(1024,65535)][int]$Port = 8782,
    [Parameter(Mandatory = $true)][string]$ReceiptPath
)
$ErrorActionPreference = 'Stop'
$serverPath = Join-Path $PSScriptRoot 'workbench.py'
$logDirectory = Join-Path $PSScriptRoot 'private_exports'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$stdoutPath = Join-Path $logDirectory "service-$stamp.stdout.log"
$stderrPath = Join-Path $logDirectory "service-$stamp.stderr.log"
$serverArguments = @('-B', '-u', ('"' + $serverPath + '"'), '--port', [string]$Port)
$serviceProcess = Start-Process -FilePath $PythonPath -ArgumentList $serverArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
[pscustomobject]@{pid=$serviceProcess.Id; stdout=$stdoutPath; stderr=$stderrPath} | ConvertTo-Json -Compress | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
