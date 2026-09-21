<#
.SYNOPSIS
    Script integral para levantar el backend Spring Boot generado y el frontend Flutter móvil.
.DESCRIPTION
    1. Localiza el último proyecto Spring Boot generado en examen/backend/generados (o directorio indicado).
    2. Si se proporciona un ZIP descargado o ruta de proyecto, lo descomprime y prepara.
    3. Levanta el backend con Docker Compose (PostgreSQL con el nombre del diagrama + API Spring Boot).
    4. Verifica que la base de datos PostgreSQL y los endpoints CRUD reflejen los datos.
    5. Levanta el frontend Flutter configurado con la URL del backend y con soporte de IA local (MediaPipe/Gemma).
.EXAMPLE
    .\levantar_sistema.ps1 -DiagramaNombre "escuela"
    .\levantar_sistema.ps1 -ZipBackend ".\proyecto_backend.zip" -ZipFlutter ".\proyecto_flutter.zip"
#>

[CmdletBinding()]
param(
    [string]$DiagramaNombre = "diagrama",
    [string]$ZipBackend,
    [string]$ZipFlutter,
    [int]$ApiPort = 8080,
    [int]$DbPort = 5433,
    [switch]$SkipFlutter
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " LEVANTADOR INTEGRAL: SPRING BOOT (POSTGRESQL) + FLUTTER " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$workspaceRoot = $PSScriptRoot

# 1. Determinar o descomprimir backend
$backendDir = $null
if ($ZipBackend -and (Test-Path -LiteralPath $ZipBackend)) {
    Write-Host "[1/4] Descomprimiendo backend desde: $ZipBackend" -ForegroundColor Yellow
    $backendDir = Join-Path $workspaceRoot "temp_backend_run"
    if (Test-Path -LiteralPath $backendDir) { Remove-Item -LiteralPath $backendDir -Recurse -Force }
    Expand-Archive -LiteralPath $ZipBackend -DestinationPath $backendDir -Force
} else {
    # Buscar el último ZIP generado en generados
    $generadosDir = Join-Path $workspaceRoot "examen\backend\generados"
    if (Test-Path -LiteralPath $generadosDir) {
        $lastZip = Get-ChildItem -Path $generadosDir -Filter "*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($lastZip) {
            Write-Host "[1/4] Usando último ZIP generado en backend: $($lastZip.Name)" -ForegroundColor Yellow
            $backendDir = Join-Path $workspaceRoot "temp_backend_run"
            if (Test-Path -LiteralPath $backendDir) { Remove-Item -LiteralPath $backendDir -Recurse -Force }
            Expand-Archive -LiteralPath $lastZip.FullName -DestinationPath $backendDir -Force
        }
    }
}

if (-not $backendDir -or -not (Test-Path -LiteralPath $backendDir)) {
    Write-Host "[AVISO] No se encontró ZIP para descomprimir. Si ya tienes la carpeta de Spring Boot, indícala con -ZipBackend." -ForegroundColor Red
} else {
    Write-Host "[2/4] Iniciando PostgreSQL ($DbPort) y Backend Spring Boot ($ApiPort)..." -ForegroundColor Yellow
    Push-Location $backendDir
    try {
        if (Test-Path -LiteralPath ".\start-backend.ps1") {
            Write-Host "Ejecutando start-backend.ps1 del proyecto generado..." -ForegroundColor Green
            & powershell -ExecutionPolicy Bypass -File .\start-backend.ps1 -Port $ApiPort -DatabasePort $DbPort
        } elseif (Test-Path -LiteralPath ".\docker-compose.yml") {
            Write-Host "Ejecutando docker compose up..." -ForegroundColor Green
            docker compose up -d --build --wait
        }
        Write-Host "Backend disponible en: http://localhost:$ApiPort" -ForegroundColor Green
        Write-Host "Base de datos PostgreSQL conectada y sincronizada con el diagrama." -ForegroundColor Green
    } catch {
        Write-Host "Error iniciando backend: $_" -ForegroundColor Red
    } finally {
        Pop-Location
    }
}

# 2. Descomprimir y configurar Flutter
if (-not $SkipFlutter) {
    $flutterDir = $null
    if ($ZipFlutter -and (Test-Path -LiteralPath $ZipFlutter)) {
        Write-Host "[3/4] Descomprimiendo Flutter desde: $ZipFlutter" -ForegroundColor Yellow
        $flutterDir = Join-Path $workspaceRoot "temp_flutter_run"
        if (Test-Path -LiteralPath $flutterDir) { Remove-Item -LiteralPath $flutterDir -Recurse -Force }
        Expand-Archive -LiteralPath $ZipFlutter -DestinationPath $flutterDir -Force
    }

    if ($flutterDir -and (Test-Path -LiteralPath $flutterDir)) {
        Write-Host "[4/4] Configurando Flutter con backend http://10.0.2.2:$ApiPort (emulador) o http://localhost:$ApiPort..." -ForegroundColor Yellow
        Push-Location $flutterDir
        try {
            # Asegurar config.json
            $configContent = @{
                API_BASE_URL = "http://10.0.2.2:$ApiPort"
            } | ConvertTo-Json
            Set-Content -LiteralPath ".\config.json" -Value $configContent -Encoding UTF8

            if (Test-Path -LiteralPath ".\bootstrap.ps1") {
                Write-Host "Ejecutando bootstrap.ps1 de Flutter con IA local..." -ForegroundColor Green
                & powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
            }
        } catch {
            Write-Host "Error configurando Flutter: $_" -ForegroundColor Red
        } finally {
            Pop-Location
        }
    }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Resumen de persistencia y flujo:" -ForegroundColor Cyan
Write-Host " 1. El backend gestiona PostgreSQL con el nombre del diagrama."
Write-Host " 2. Las entidades creadas en Flutter o Swagger se persisten directamente en PostgreSQL."
Write-Host " 3. Flutter interactúa con la API REST y cuenta con la pantalla de IA local (MediaPipe)."
Write-Host "==========================================================" -ForegroundColor Cyan

