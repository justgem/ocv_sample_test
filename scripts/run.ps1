$EnvFile = ".env"
if (Test-Path $EnvFile) {
  Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) {
      return
    }
    $pair = $line -split "=", 2
    if ($pair.Length -eq 2) {
      $key = $pair[0].Trim()
      $value = $pair[1].Trim()
      [System.Environment]::SetEnvironmentVariable($key, $value)
    }
  }
}

Write-Host "Starting server on http://localhost:8000"

$PythonExe = "python"
if (Test-Path ".\\.venv\\Scripts\\python.exe") {
  $PythonExe = ".\\.venv\\Scripts\\python.exe"
} else {
  if (Test-Path ".\\.venv\\Scripts\\Activate.ps1") {
    . .\\.venv\\Scripts\\Activate.ps1
  }
}

$UvicornInstalled = & $PythonExe -m pip show uvicorn 2>$null
if (-not $UvicornInstalled) {
  Write-Host "uvicorn not found. Installing dependencies from requirements.txt"
  & $PythonExe -m pip install -r requirements.txt
}

& $PythonExe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
