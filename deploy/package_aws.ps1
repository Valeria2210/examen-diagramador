param(
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $sourceRoot) 'examen-aws.zip'
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)

if ($OutputPath.StartsWith($sourceRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'El ZIP debe crearse fuera de la carpeta que se empaqueta.'
}

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('examen-aws-' + [guid]::NewGuid().ToString('N'))
$excludedDirectoryPattern = '(^|[\\/])(\.git|\.venv|\.test-tmp|node_modules|dist|__pycache__|generados|artifacts|audit_output|staticfiles)([\\/]|$)'
$excludedExtensions = @('.pyc', '.pyo', '.log', '.sqlite3')

try {
    New-Item -ItemType Directory -Path $temporaryRoot | Out-Null

    $files = Get-ChildItem -LiteralPath $sourceRoot -Recurse -Force -File | Where-Object {
        $relativePath = $_.FullName.Substring($sourceRoot.Length).TrimStart('\')
        $relativePath -notmatch $excludedDirectoryPattern -and
        $_.Name -ne '.env' -and
        $excludedExtensions -notcontains $_.Extension.ToLowerInvariant()
    }

    foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
        $destination = Join-Path $temporaryRoot $relativePath
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination
    }

    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }
    Compress-Archive -Path (Join-Path $temporaryRoot '*') -DestinationPath $OutputPath -CompressionLevel Optimal

    $archive = Get-Item -LiteralPath $OutputPath
    $hash = Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256
    [pscustomobject]@{
        Archive = $archive.FullName
        Files = $files.Count
        SizeMB = [math]::Round($archive.Length / 1MB, 2)
        SHA256 = $hash.Hash
    } | Format-List
}
finally {
    $resolvedTemporaryRoot = [IO.Path]::GetFullPath($temporaryRoot)
    $systemTemporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTemporaryRoot.StartsWith($systemTemporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTemporaryRoot) -like 'examen-aws-*' -and
        (Test-Path -LiteralPath $resolvedTemporaryRoot)) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
    }
}
