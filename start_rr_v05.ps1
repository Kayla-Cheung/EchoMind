param([int]$Port = 8780, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction Stop).Source
$launchArguments = @((Join-Path $root 'launch_rr_v05.py'), '--port', "$Port")
if ($NoBrowser) { $launchArguments += '--no-browser' }
& $python @launchArguments
if ($LASTEXITCODE -ne 0) { throw 'EchoMind v0.5 did not start. Check the message above.' }
