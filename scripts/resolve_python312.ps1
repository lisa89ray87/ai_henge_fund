$ErrorActionPreference = 'Stop'

$candidates = New-Object System.Collections.Generic.List[string]

if (-not [string]::IsNullOrWhiteSpace($env:PYTHON_312_PATH)) {
  $candidates.Add($env:PYTHON_312_PATH)
}

$knownCandidates = @(
  'C:\Users\limli\AppData\Local\Programs\Python\Python312\python.exe',
  'C:\Program Files\Python312\python.exe',
  'C:\Python312\python.exe'
)
foreach ($candidate in $knownCandidates) {
  $candidates.Add($candidate)
}

if (Test-Path 'C:\Users') {
  Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $candidates.Add((Join-Path $_.FullName 'AppData\Local\Programs\Python\Python312\python.exe'))
  }
}

foreach ($root in @('C:\Program Files', 'C:\Program Files (x86)', 'C:\Python312')) {
  if (Test-Path $root) {
    Get-ChildItem $root -Directory -Filter 'Python312*' -ErrorAction SilentlyContinue | ForEach-Object {
      $candidates.Add((Join-Path $_.FullName 'python.exe'))
    }
  }
}

$python = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    continue
  }

  try {
    $version = (& $candidate --version 2>&1 | Out-String).Trim()
    $versionExitCode = $LASTEXITCODE
    $versionInfo = (& $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>&1 | Out-String).Trim()
    $pipVersion = (& $candidate -c "import pip; print(pip.__version__)" 2>&1 | Out-String).Trim()
    $candidateExitCode = $LASTEXITCODE
    Write-Host "Checking ${candidate} -> $version | version=$versionInfo | pip=$pipVersion"

    if ($versionExitCode -eq 0 -and $candidateExitCode -eq 0 -and $versionInfo -match '^3\.12\.' -and $pipVersion -notmatch 'No module named pip') {
      $python = (Resolve-Path -LiteralPath $candidate).Path
      break
    }
  }
  catch {
    Write-Host "Unable to validate ${candidate}: $($_.Exception.Message)"
  }
}

if (-not $python) {
  throw 'No valid Python 3.12.x installation with pip was found. Python from PATH, the py launcher, and the GitHub Actions toolcache are not used as fallbacks.'
}

Write-Host "Using Python 3.12 with pip: $python"
& $python --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pip --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$pythonDir = Split-Path -Parent $python
$pythonScriptsDir = Join-Path $pythonDir 'Scripts'
$pythonDir | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
if (Test-Path $pythonScriptsDir) {
  $pythonScriptsDir | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
}
"PYTHON_312_PATH=$python" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
