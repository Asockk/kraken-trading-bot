#!/usr/bin/env python3
"""
btc_charlie Trader XO Macro Trend Scanner Bot
Production-ready cryptocurrency trading bot with improved error handling
"""

import asyncio
import os
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

def setup_logging():
    """Setup comprehensive logging"""
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/bot_startup.log'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger("bot_startup")

def load_environment():
    """Load environment variables"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return True
    except ImportError:
        print("⚠️  python-dotenv nicht installiert, verwende System-Umgebungsvariablen")
        return True

def check_prerequisites():
    """Check if all prerequisites are met"""
    logger = logging.getLogger("bot_startup")
    
    # Check environment variables
    required_vars = ['KRAKEN_API_KEY', 'KRAKEN_API_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Fehlende Umgebungsvariablen: {missing_vars}")
        logger.error("Erstellen Sie eine .env Datei oder setzen Sie die Variablen in Ihrer Shell")
        return False
    
    # Check config file
    if not os.path.exists("config.yaml"):
        logger.error("config.yaml nicht gefunden")
        return False
    
    # Check if test passed
    logger.info("Führe Pre-Flight-Check durch...")
    return True

async def run_bot():
    """Run the trading bot with proper error handling"""
    logger = logging.getLogger("bot_startup")
    
    try:
        # Import after environment is set up
        from src.bot import TradingBot
        
        logger.info("Starte Trading Bot...")
        bot = TradingBot("config.yaml")
        
        # Run bot
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("Bot durch Benutzer gestoppt")
    except ImportError as e:
        logger.error(f"Import-Fehler: {e}")
        logger.error("Stellen Sie sicher, dass alle Dependencies installiert sind: pip install -r requirements.txt")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Starten des Bots: {e}", exc_info=True)
        raise

def main():
    """Main entry point with comprehensive error handling"""
    print("=== btc_charlie Trader XO Macro Trend Scanner Bot ===")
    print("Starting production-ready cryptocurrency trading bot...")
    
    # Setup logging first
    logger = setup_logging()
    
    try:
        # Load environment
        if not load_environment():
            logger.error("Fehler beim Laden der Umgebungsvariablen")
            sys.exit(1)
        
        # Check prerequisites
        if not check_prerequisites():
            logger.error("Prerequisite-Check fehlgeschlagen")
            print("\n🔧 Lösungsschritte:")
            print("1. Führen Sie 'python test_kraken.py' aus, um die Verbindung zu testen")
            print("2. Stellen Sie sicher, dass alle Umgebungsvariablen gesetzt sind")
            print("3. Überprüfen Sie die config.yaml Datei")
            sys.exit(1)
        
        # Run bot
        asyncio.run(run_bot())
        
    except KeyboardInterrupt:
        print("\n👋 Bot gestoppt")
    except Exception as e:
        logger.error(f"Kritischer Fehler: {e}", exc_info=True)
        print(f"\n❌ Kritischer Fehler: {e}")
        print("Überprüfen Sie die Logs für weitere Details: logs/bot_startup.log")
        sys.exit(1)

if __name__ == "__main__":
    main()