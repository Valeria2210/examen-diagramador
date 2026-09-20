$ErrorActionPreference = 'Stop'
$backendDirectory = $PSScriptRoot
$projectDirectory = Split-Path -Parent $backendDirectory
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Falta el entorno .venv. Ejecuta py -3.13 -m venv .venv desde la raíz del proyecto.'
}
# This machine has a global DEBUG=release, which is not a Django boolean.
$env:DEBUG = 'True'
$env:DB_ENGINE = 'postgres'
& $pythonExecutable (Join-Path $backendDirectory 'manage.py') runserver 127.0.0.1:8000 --noreload
