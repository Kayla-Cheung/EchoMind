[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$WorkspaceRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)
$ErrorActionPreference = 'Stop'
$cleanupRoot = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $WorkspaceRoot).Path).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $cleanupRoot 'repository\data_audit.py') -PathType Leaf)) {
    throw 'Expected the EchoMind workspace containing repository\data_audit.py.'
}
function Get-CheckedPath([string]$Relative) {
    $candidate = [IO.Path]::GetFullPath((Join-Path $cleanupRoot $Relative))
    if (-not $candidate.StartsWith($cleanupRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path leaves workspace.' }
    $cursor = $candidate
    while ($cursor.Length -ge $cleanupRoot.Length) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing a junction or symlink.' }
        }
        if ($cursor -eq $cleanupRoot) { break }
        $cursor = Split-Path -Parent $cursor
    }
    return $candidate
}
$cacheNames = @('__pycache__', 'tests\__pycache__', 'repository\__pycache__',
    'repository\tests\__pycache__', 'repository\scripts\__pycache__',
    'repository\human-analysis\__pycache__', '.pytest_cache', 'repository\.pytest_cache')
$summary = [ordered]@{ created_at = [DateTime]::UtcNow.ToString('o'); workspace = $cleanupRoot; caches = @(); staging = $null }
$reportName = 'cleanup-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$backupDir = Get-CheckedPath ('repository\data\local\backups\' + $reportName)
$staging = Get-CheckedPath 'sync-staging'

if ((Test-Path -LiteralPath $staging -PathType Container) -and $PSCmdlet.ShouldProcess($staging, 'Archive, verify every file, then remove temporary staging')) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $files = @(Get-ChildItem -LiteralPath $staging -Recurse -File -Force)
    $reparse = @(Get-ChildItem -LiteralPath $staging -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
    if ($reparse.Count) { throw 'Staging contains a junction or symlink.' }
    $manifest = @($files | ForEach-Object {
        [ordered]@{ path = $_.FullName.Substring($staging.Length + 1).Replace('\','/');
            bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    New-Item -ItemType Directory -Path $backupDir | Out-Null
    $archivePath = Join-Path $backupDir 'sync-staging.zip'
    [IO.Compression.ZipFile]::CreateFromDirectory($staging, $archivePath, [IO.Compression.CompressionLevel]::Optimal, $false)
    $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        if (@($archive.Entries | Where-Object { $_.Name }).Count -ne $manifest.Count) { throw 'Archive entry count mismatch.' }
        foreach ($entry in $manifest) {
            $zipped = $archive.GetEntry($entry.path)
            if (-not $zipped -or $zipped.Length -ne $entry.bytes) { throw 'Archive entry missing or wrong size.' }
            $stream = $zipped.Open(); $hasher = [Security.Cryptography.SHA256]::Create()
            try { $actualHash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','') }
            finally { $stream.Dispose(); $hasher.Dispose() }
            if ($actualHash -ne $entry.sha256) { throw 'Archive content verification failed.' }
            $original = Join-Path $staging $entry.path
            if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash -ne $entry.sha256) { throw 'Source changed during archival.' }
        }
    } finally { $archive.Dispose() }
    if (@(Get-ChildItem -LiteralPath $staging -Recurse -File -Force).Count -ne $manifest.Count) { throw 'Staging changed during archival.' }
    $summary.staging = [ordered]@{ archive = $archivePath; files = $manifest; archive_sha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $backupDir 'cleanup-manifest.json') -Encoding UTF8
    # The absolute directory was checked above; no source experiments or databases are targeted.
    Remove-Item -LiteralPath $staging -Recurse -Force
    Write-Output "Archived and removed staging: $($manifest.Count) files"
}
foreach ($name in $cacheNames) {
    $cache = Get-CheckedPath $name
    if (-not (Test-Path -LiteralPath $cache -PathType Container)) { continue }
    if (@(Get-ChildItem -LiteralPath $cache -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Cache contains a junction or symlink.' }
    $files = @(Get-ChildItem -LiteralPath $cache -Recurse -File -Force)
    if ($PSCmdlet.ShouldProcess($cache, 'Remove regenerable cache')) {
        $summary.caches += [ordered]@{ path = $cache; files = $files.Count; bytes = ($files | Measure-Object -Property Length -Sum).Sum }
        Remove-Item -LiteralPath $cache -Recurse -Force
    }
}
if (-not $WhatIfPreference) {
    if (-not (Test-Path -LiteralPath $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }
    $report = Join-Path $backupDir 'cleanup-manifest.json'
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $report -Encoding UTF8
    Write-Output "Cleanup record: $report"
    Write-Output "Cache directories removed: $($summary.caches.Count)"
}
