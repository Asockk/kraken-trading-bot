#!/usr/bin/env python3
"""
Interaktives Setup-Script für den Kraken Trading Bot
"""

import os
import sys
from pathlib import Path

def create_env_file():
    """Erstellt eine .env Datei mit Benutzerinput"""
    
    print("=== Kraken API-Konfiguration ===")
    print()
    print("Sie benötigen API-Keys von Kraken:")
    print("1. Gehen Sie zu https://www.kraken.com/u/security/api")
    print("2. Erstellen Sie einen neuen API-Key mit folgenden Berechtigungen:")
    print("   - Query Funds")
    print("   - Create & Modify Orders")
    print("   - Query Open/Closed Orders")
    print("3. Geben Sie die API-Credentials hier ein:")
    print()
    
    # API-Key eingeben
    api_key = input("Kraken API-Key: ").strip()
    if not api_key:
        print("❌ API-Key ist erforderlich!")
        return False
    
    # API-Secret eingeben
    api_secret = input("Kraken API-Secret: ").strip()
    if not api_secret:
        print("❌ API-Secret ist erforderlich!")
        return False
    
    # Sandbox-Modus
    sandbox_input = input("Sandbox-Modus verwenden? (y/n) [y]: ").strip().lower()
    sandbox = sandbox_input != 'n'
    
    # Validiere API-Secret (sollte base64 sein)
    try:
        import base64
        # Test decode
        missing_padding = len(api_secret) % 4
        if missing_padding:
            api_secret_padded = api_secret + '=' * (4 - missing_padding)
        else:
            api_secret_padded = api_secret
        
        base64.b64decode(api_secret_padded)
        print("✅ API-Secret Format validiert")
    except Exception as e:
        print(f"⚠️  API-Secret Format-Warnung: {e}")
        proceed = input("Trotzdem fortfahren? (y/n) [n]: ").strip().lower()
        if proceed != 'y':
            return False
    
    # Erstelle .env Datei
    env_content = f"""KRAKEN_API_KEY={api_key}
KRAKEN_API_SECRET={api_secret}
KRAKEN_SANDBOX={str(sandbox).lower()}
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("✅ .env Datei erfolgreich erstellt")
    return True

def setup_project():
    """Setup des gesamten Projekts"""
    
    print("=== Kraken Trading Bot Setup ===")
    print()
    
    # Erstelle notwendige Verzeichnisse
    os.makedirs("logs", exist_ok=True)
    print("✅ Logs-Verzeichnis erstellt")
    
    # Installiere Dependencies
    print("📦 Installiere Python Dependencies...")
    try:
        import subprocess
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Dependencies installiert")
        else:
            print(f"⚠️  Warnung bei Installation: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Fehler bei Installation: {e}")
    
    # Erstelle .env Datei
    if os.path.exists('.env'):
        overwrite = input(".env Datei existiert bereits. Überschreiben? (y/n) [n]: ").strip().lower()
        if overwrite != 'y':
            print("✅ Setup abgeschlossen (bestehende .env verwendet)")
            return True
    
    if not create_env_file():
        print("❌ Setup abgebrochen")
        return False
    
    print()
    print("🎉 Setup erfolgreich abgeschlossen!")
    print()
    print("Nächste Schritte:")
    print("1. Testen Sie die Verbindung: python test_kraken.py")
    print("2. Starten Sie den Bot: python run_bot.py")
    print()
    
    return True

def main():
    """Hauptfunktion"""
    
    # Prüfe ob wir im richtigen Verzeichnis sind
    if not os.path.exists("config.yaml"):
        print("❌ config.yaml nicht gefunden!")
        print("Stellen Sie sicher, dass Sie im Bot-Verzeichnis sind.")
        return
    
    # Führe Setup aus
    if setup_project():
        print("Setup abgeschlossen. Bereit zum Testen!")
    else:
        print("Setup fehlgeschlagen. Versuchen Sie es erneut.")

if __name__ == "__main__":
    main()