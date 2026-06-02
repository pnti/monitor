#!/bin/bash
# Przejdź do katalogu, w którym znajduje się skrypt
cd "$(dirname "$0")"

# Jeśli folder 'env' nie istnieje, stwórz go i zainstaluj Flask
if [ ! -d "env" ]; then
    echo "Inicjalizacja środowiska wirtualnego..."
    python3 -m venv env
    source env/bin/activate
    pip install flask
else
    source env/bin/activate
fi

# Uruchomienie aplikacji
echo "Uruchamianie aplikacji..."
python3 app.py
