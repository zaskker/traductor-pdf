$ErrorActionPreference = "Stop"

$Version = "1.0.0-rc1"
$ZipName = "TraductorPDF-v$Version-windows-x64.zip"

Write-Host "Limpiando directorios de build..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path $ZipName) { Remove-Item -Force $ZipName }
if (Test-Path "SHA256SUMS.txt") { Remove-Item -Force "SHA256SUMS.txt" }
Write-Host "Verificando entorno y corriendo tests source (baseline)..."
# Configuramos variables de entorno desde powershell para que pytest no toque el sistema real
$env:TMP = "$PWD\temp_run_5"
$env:TEMP = "$PWD\temp_run_5"
$env:LOCALAPPDATA = "$PWD\temp_run_5"
if (-Not (Test-Path $env:TMP)) { New-Item -ItemType Directory -Path $env:TMP | Out-Null }

# Ejecutamos con run_tests
.venv\Scripts\python run_tests.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Los tests fallaron. Abortando build RC1."
    exit $LASTEXITCODE
}

Write-Host "Construyendo ejecutable con PyInstaller (OneDir)..."
.venv\Scripts\pyinstaller --clean packaging/TraductorPDF.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "Fallo PyInstaller."
    exit $LASTEXITCODE
}

Write-Host "Verificando ejecutable..."
if (-Not (Test-Path "dist\TraductorPDF\TraductorPDF.exe")) {
    Write-Error "Ejecutable no encontrado en dist\TraductorPDF\"
    exit 1
}

Write-Host "Creando ZIP Release..."
Compress-Archive -Path "dist\TraductorPDF" -DestinationPath $ZipName -Force

Write-Host "Generando SHA-256..."
$Hash = Get-FileHash $ZipName -Algorithm SHA256
$HashLine = "$($Hash.Hash) *$ZipName"
$HashLine | Out-File -FilePath "SHA256SUMS.txt" -Encoding ascii

Write-Host "Generando MANIFEST.txt..."
$Date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$PythonVer = & .venv\Scripts\python --version
$PyInstallerVer = & .venv\Scripts\pyinstaller --version
$FileSize = (Get-Item $ZipName).Length / 1MB
$ManifestContent = @"
App Version: $Version
Build Date: $Date
Python: $PythonVer
PyInstaller: $PyInstallerVer
Artifact: $ZipName
SHA256: $($Hash.Hash)
Size (MB): $([math]::Round($FileSize, 2))
"@
$ManifestContent | Out-File -FilePath "MANIFEST.txt" -Encoding utf8

Write-Host "Build completado exitosamente: $ZipName"
