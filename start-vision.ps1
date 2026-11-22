param(
    [string]$Ip,
    [int]$Port = 8443,
    [int]$SetupPort = 8000
)

$ErrorActionPreference = 'Stop'
$visionPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $visionPython)) {
    throw 'Create the project environment first: python -m venv .venv'
}
& $visionPython -c 'import cv2, numpy, aiohttp'
if ($LASTEXITCODE -ne 0) {
    throw 'Install vision packages first: .\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt'
}
$visionArguments = @((Join-Path $PSScriptRoot 'local_https.py'), '--vision', '--port', $Port, '--setup-port', $SetupPort)
if ($Ip) { $visionArguments += @('--ip', $Ip) }
& $visionPython @visionArguments
exit $LASTEXITCODE
