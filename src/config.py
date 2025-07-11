import os
from dataclasses import dataclass
from typing import List, Dict, Any
import yaml

@dataclass
class ExchangeConfig:
    name: str
    api_key: str
    api_secret: str
    sandbox: bool = False
    rate_limit: int = 100  # requests per minute

@dataclass
class TradingConfig:
    # Strategy Parameters
    fast_ema_period: int = 12
    slow_ema_period: int = 25
    stoch_rsi_length: int = 14
    stoch_length: int = 14
    stoch_k_smooth: int = 3
    stoch_d_smooth: int = 3
    
    # Risk Management
    max_position_size: float = 0.02  # 2% of account balance
    stop_loss_percentage: float = 0.02  # 2% stop loss
    take_profit_percentage: float = 0.04  # 4% take profit
    max_daily_loss: float = 0.03  # 3% maximum daily loss
    max_drawdown: float = 0.10  # 10% maximum drawdown
    
    # Timeframe
    timeframe: str = "1h"
    
    # Trading Parameters
    trading_pairs: List[str] = None
    order_type: str = "market"  # market or limit
    one_position_per_pair: bool = True
    
    # System Configuration
    log_level: str = "INFO"
    data_update_interval: int = 1  # seconds
    
    def __post_init__(self):
        if self.trading_pairs is None:
            self.trading_pairs = ["BTC/USDT", "ETH/USDT"]

class ConfigManager:
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.trading_config = TradingConfig()
        self.exchange_configs = {}
        self.load_config()
        self.validate_config()
    
    def load_config(self):
        """Load configuration from file and environment variables"""
        # Load from YAML file if exists
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config_data = yaml.safe_load(f)
                self._update_trading_config(config_data.get('trading', {}))
        
        # Load exchange configurations from environment
        self._load_exchange_configs()
    
    def _load_exchange_configs(self):
        """Load exchange configurations from environment variables - NUR KRAKEN"""
        # Kraken configuration
        kraken_key = os.getenv('KRAKEN_API_KEY')
        kraken_secret = os.getenv('KRAKEN_API_SECRET')
        
        if not kraken_key or not kraken_secret:
            raise ValueError(
                "Kraken API credentials not found! "
                "Please set KRAKEN_API_KEY and KRAKEN_API_SECRET in .env file"
            )
        
        self.exchange_configs['kraken'] = ExchangeConfig(
            name='kraken',
            api_key=kraken_key,
            api_secret=kraken_secret,
            sandbox=os.getenv('KRAKEN_SANDBOX', 'false').lower() == 'true'
        )
    
    def _update_trading_config(self, config_data: Dict[str, Any]):
        """Update trading configuration with data from file"""
        for key, value in config_data.items():
            if hasattr(self.trading_config, key):
                setattr(self.trading_config, key, value)
    
    def validate_config(self):
        """Validate configuration parameters"""
        if not self.exchange_configs:
            raise ValueError("No exchange configurations found. Please set API keys in environment variables.")
        
        if self.trading_config.max_position_size <= 0 or self.trading_config.max_position_size > 1:
            raise ValueError("max_position_size must be between 0 and 1")
        
        if not self.trading_config.trading_pairs:
            raise ValueError("No trading pairs configured")
          
        allowed_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        if self.trading_config.timeframe not in allowed_timeframes:
            raise ValueError(
                f"Invalid timeframe: {self.trading_config.timeframe}. Allowed values: {allowed_timeframes}"
            )
    
    def get_active_exchange(self) -> str:
        """Get the active exchange name (first available)"""
        return list(self.exchange_configs.keys())[0]