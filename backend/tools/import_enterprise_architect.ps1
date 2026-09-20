param(
    [Parameter(Mandatory = $true)][string]$JsonPath,
    [Parameter(Mandatory = $true)][string]$ProjectPath
)

$ErrorActionPreference = "Stop"
$json = (Resolve-Path -LiteralPath $JsonPath).Path
$extension = [IO.Path]::GetExtension($ProjectPath).ToLowerInvariant()
if ($extension -notin @(".qea", ".qeax", ".eap", ".eapx")) {
    throw "El destino debe ser un proyecto de Enterprise Architect (.qea, .qeax, .eap o .eapx)."
}
$destination = [IO.Path]::GetFullPath($ProjectPath)
$script = Join-Path $PSScriptRoot "import_enterprise_architect.py"

try {
    py $script $json $destination
} catch {
    throw "No se pudo ejecutar Python. Instala Python y pywin32 con: py -m pip install --user pywin32"
}
if ($LASTEXITCODE -ne 0) {
    throw "Enterprise Architect no pudo completar la importación (código $LASTEXITCODE). Verifica que EA y Python usen la misma arquitectura de 64 bits."
}
