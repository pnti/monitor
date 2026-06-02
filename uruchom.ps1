# Ustawienie katalogu roboczego na miejsce, w którym znajduje się skrypt
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Nazwa folderu środowiska wirtualnego
$VenvDir = "env"

# Jeśli folder środowiska nie istnieje, stwórz go i zainstaluj Flask
if (-not (Test-Path -Path $VenvDir)) {
    Write-Host "Inicjalizacja środowiska wirtualnego..." -ForegroundColor Cyan
    python -m venv $VenvDir
    
    # Aktywacja i instalacja pakietów
    & "$VenvDir\Scripts\Activate.ps1"
    pip install flask
} else {
    # Jeśli istnieje, po prostu aktywuj
    & "$VenvDir\Scripts\Activate.ps1"
}

Write-Host "Uruchamianie aplikacji monitorującej..." -ForegroundColor Green
python app.py

# Zatrzymanie okna w przypadku błędu lub wyłączenia aplikacji
Read-Host -Prompt "Naciśnij Enter, aby zamknąć..."
