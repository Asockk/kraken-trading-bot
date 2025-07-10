# Kraken Trading Bot - BTC Charlie Strategy

A cryptocurrency trading bot implementing the btc_charlie Trader XO Macro Trend Scanner strategy on Kraken exchange.

## ⚠️ Disclaimer

**USE AT YOUR OWN RISK!** This bot trades with real money. The developers are not responsible for any financial losses. Always test thoroughly with small amounts first.

## Features

- **BTC Charlie Strategy**: EMA crossover with counter logic
- **Stochastic RSI Alerts**: Additional momentum indicators
- **Risk Management**: Configurable stop-loss, take-profit, and position sizing
- **Multi-pair Trading**: Trade multiple cryptocurrency pairs simultaneously
- **Comprehensive Logging**: Detailed logs for debugging and analysis

## Requirements

- Python 3.8+
- Kraken API account with trading permissions
- USD balance on Kraken

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/kraken-trading-bot.git
cd kraken-trading-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the example environment file:
```bash
cp .env.example .env
```

4. Edit `.env` with your Kraken API credentials:
```bash
KRAKEN_API_KEY=your_api_key_here
KRAKEN_API_SECRET=your_api_secret_here
KRAKEN_SANDBOX=false
```

## Configuration

Edit `config.yaml` to customize:
- Trading pairs
- Risk management parameters
- Strategy parameters
- Update intervals

## Usage

1. Test your connection first:
```bash
python tools/test_kraken.py
```

2. Run the bot:
```bash
python run_bot.py
```

## Project Structure

```
├── src/                  # Core bot modules
│   ├── bot.py           # Main trading bot
│   ├── strategy.py      # BTC Charlie strategy
│   ├── exchange_api.py  # Kraken API wrapper
│   └── config.py        # Configuration manager
├── tools/               # Utility scripts
├── logs/                # Trading logs
├── data/                # Persistent data
├── config.yaml          # Bot configuration
├── requirements.txt     # Python dependencies
└── run_bot.py          # Entry point
```

## Strategy Overview

The BTC Charlie strategy uses:
- Fast EMA (12) and Slow EMA (25) crossovers
- Counter logic to filter signals
- Stochastic RSI for additional confirmation
- 4-hour timeframe by default

## Security Notes

- Never commit your `.env` file
- Keep your API keys secret
- Use read-only API keys for testing
- Enable 2FA on your Kraken account

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues first

## Acknowledgments

- Based on the btc_charlie Trader XO Macro Trend Scanner strategy
- Built with ccxt alternative for Kraken