$EnvFile = ".env"
if (Test-Path $EnvFile) {
  Get-Content $EnvFile | ForEach-Object {
    if ($_ -match "^") {
      $pair = $_ -split "=", 2
      if ($pair.Length -eq 2) {
        [System.Environment]::SetEnvironmentVariable($pair[0], $pair[1])
      }
    }
  }
}

Write-Host "Starting server on http://localhost:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
