param(
    [ValidateRange(1, 65535)][int]$Port = 8189,
    [string]$DataDir = ""
)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$selectedDataDir = $DataDir
if (-not $selectedDataDir) { $selectedDataDir = $env:PICTIDE_DATA_DIR }
if (-not $selectedDataDir) { $selectedDataDir = $env:PICTIDE_WEB_DATA_DIR }
if (-not $selectedDataDir) { $selectedDataDir = Join-Path $projectPath 'data' }
$dataRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($selectedDataDir)
$runtimePath = Join-Path $dataRoot 'runtime'
$venvPath = Join-Path $runtimePath 'venv'
$cachePath = Join-Path $dataRoot 'cache'
$tempPath = Join-Path $dataRoot 'tmp'
foreach ($directory in @($dataRoot, $runtimePath, $cachePath, $tempPath)) {
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
}
$env:PICTIDE_DATA_DIR = $dataRoot
$env:PICTIDE_WEB_DATA_DIR = $dataRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $cachePath 'python'
$env:PIP_CACHE_DIR = Join-Path $cachePath 'pip'
$env:TEMP = $tempPath
$env:TMP = $tempPath
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCandidates = @(
        $env:PICTIDE_PYTHON,
        $env:PICTIDE_WEB_PYTHON,
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    )
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) { $pythonCandidates += $pythonCommand.Source }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $locatedPython = & $launcher.Source -3 -c 'import sys; print(sys.executable)'
        if ($LASTEXITCODE -eq 0) { $pythonCandidates += $locatedPython }
    }
    $pythonPath = $pythonCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $pythonPath) { throw 'Python 3.10+ is required. Set PICTIDE_PYTHON to python.exe.' }
    & $pythonPath -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }
    & $pythonPath -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the virtual environment.' }
}
& $venvPython -c "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(name) for name in ('aiohttp', 'fastembed', 'numpy')) and __import__('importlib.metadata', fromlist=['version']).version('fastembed') == '0.9.0' and __import__('importlib.metadata', fromlist=['version']).version('numpy') == ('2.5.4' if sys.version_info >= (3,12) else '2.2.6') else 1)"
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r (Join-Path $projectPath 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$appArguments = @('-m', 'backend.host', '--port', "$Port", '--data-dir', $dataRoot)
Write-Host "Pictide: http://127.0.0.1:$Port"
Write-Host "Data directory: $dataRoot"
Write-Host 'Close this terminal or press Ctrl+C to stop the Web application.'
Push-Location -LiteralPath $projectPath
try { & $venvPython @appArguments }
finally { Pop-Location }
