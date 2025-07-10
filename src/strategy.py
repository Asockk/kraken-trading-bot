import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

class Signal(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

@dataclass
class StrategySignal:
    symbol: str
    signal: Signal
    price: float
    timestamp: int
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.0
    signal_type: str = ""  # "bull" or "bear" for main signals

@dataclass
class StochRSIAlert:
    symbol: str
    alert_type: str  # "crossup_mid", "crossdown_mid", "crossup_os", "crossdown_ob"
    price: float
    timestamp: int
    stoch_k: float
    stoch_d: float

class BTCCharlieStrategy:
    """
    Implementation of btc_charlie Trader XO Macro Trend Scanner strategy
    
    Strategy logic:
    - Main signals (Bull/Bear) based on EMA crossover with counter logic
    - Stochastic RSI used for additional alerts and confirmation
    """
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("strategy.btc_charlie")
        
        # Strategy parameters from original
        self.fast_ema_period = 12  # Default from original
        self.slow_ema_period = 25  # Default from original
        self.consolidated_ema_period = 25  # Default EMA
        
        # Stochastic RSI parameters
        self.stoch_k_smooth = 3
        self.stoch_d_smooth = 3
        self.stoch_rsi_length = 14
        self.stoch_length = 14
        
        # Bands for Stochastic RSI
        self.upper_band = 80
        self.middle_band = 50
        self.lower_band = 20
        
        # Store historical data for each symbol
        self.market_data = {}
        
        # Counter tracking for each symbol (critical for strategy)
        self.counters = {}
    

    def update_market_data(self, symbol: str, ohlcv_data: List[Dict]):
        """Update market data for a symbol - mit Speicher-Limit"""
        df = pd.DataFrame(ohlcv_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Begrenze auf maximal die letzten 500 Datenpunkte
        max_points = getattr(self.config, 'max_data_points', 500)
        if len(df) > max_points:
            df = df.iloc[-max_points:]
        
        # Calculate indicators
        df = self._calculate_indicators(df)
        
        # Calculate counter logic
        df = self._calculate_counter_logic(df, symbol)
        
        # Speichere nur die letzten 200 Kerzen (ausreichend für Berechnungen)
        self.market_data[symbol] = df.iloc[-200:]
        
        self.logger.debug(f"Updated market data for {symbol}: {len(self.market_data[symbol])} candles")
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators"""
        # Calculate EMAs
        df['ema_fast'] = df['close'].ewm(span=self.fast_ema_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_ema_period, adjust=False).mean()
        df['ema_consolidated'] = df['close'].ewm(span=self.consolidated_ema_period, adjust=False).mean()
        
        # Buy/Sell conditions (from original: buy = v_fastEMA > v_slowEMA)
        df['buy'] = df['ema_fast'] > df['ema_slow']
        df['sell'] = df['ema_fast'] < df['ema_slow']
        
        # Calculate RSI
        df['rsi'] = self._calculate_rsi(df['close'], self.stoch_rsi_length)
        
        # Calculate Stochastic RSI
        df['stoch_rsi_k'], df['stoch_rsi_d'] = self._calculate_stochastic_rsi(
            df['rsi'], self.stoch_length, self.stoch_k_smooth, self.stoch_d_smooth
        )
        
        # Detect Stochastic RSI crossovers
        df['stoch_crossover_up'] = (df['stoch_rsi_k'] > df['stoch_rsi_d']) & (df['stoch_rsi_k'].shift(1) <= df['stoch_rsi_d'].shift(1))
        df['stoch_crossover_down'] = (df['stoch_rsi_k'] < df['stoch_rsi_d']) & (df['stoch_rsi_k'].shift(1) >= df['stoch_rsi_d'].shift(1))
        
        return df
    
    def _calculate_counter_logic(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Implement the counter logic from original strategy
        This is the core of the btc_charlie strategy
        """
        # Initialize counters for this symbol if not exists
        if symbol not in self.counters:
            self.counters[symbol] = {'countBuy': 0, 'countSell': 0}
        
        # Create counter columns
        df['countBuy'] = 0
        df['countSell'] = 0
        df['buysignal'] = False
        df['sellsignal'] = False
        df['bull'] = False
        df['bear'] = False
        
        countBuy = 0
        countSell = 0
        
        for i in range(len(df)):
            buy = df.iloc[i]['buy']
            sell = df.iloc[i]['sell']
            
            # Counter logic from original
            if buy:
                countBuy += 1
                countSell = 0
            
            if sell:
                countSell += 1
                countBuy = 0
            
            df.iloc[i, df.columns.get_loc('countBuy')] = countBuy
            df.iloc[i, df.columns.get_loc('countSell')] = countSell
            
            # Signal logic from original
            # buysignal = countBuy < 2 and countBuy > 0 and countSell < 1 and buy and not buy[1]
            if i > 0:
                prev_buy = df.iloc[i-1]['buy']
                prev_sell = df.iloc[i-1]['sell']
                
                buysignal = countBuy < 2 and countBuy > 0 and countSell < 1 and buy and not prev_buy
                sellsignal = countSell > 0 and countSell < 2 and countBuy < 1 and sell and not prev_sell
                
                df.iloc[i, df.columns.get_loc('buysignal')] = buysignal
                df.iloc[i, df.columns.get_loc('sellsignal')] = sellsignal
            
            # Bull/Bear status
            df.iloc[i, df.columns.get_loc('bull')] = countBuy > 1
            df.iloc[i, df.columns.get_loc('bear')] = countSell > 1
        
        # Update stored counters
        if len(df) > 0:
            self.counters[symbol]['countBuy'] = df.iloc[-1]['countBuy']
            self.counters[symbol]['countSell'] = df.iloc[-1]['countSell']
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_stochastic_rsi(self, rsi: pd.Series, stoch_length: int, 
                                 k_smooth: int, d_smooth: int) -> Tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI (following original implementation)"""
        # Calculate Stochastic of RSI
        rsi_min = rsi.rolling(window=stoch_length).min()
        rsi_max = rsi.rolling(window=stoch_length).max()
        
        # Avoid division by zero
        denominator = rsi_max - rsi_min
        denominator = denominator.replace(0, 1)
        
        stoch_rsi = 100 * (rsi - rsi_min) / denominator
        
        # Apply smoothing (SMA as in original)
        stoch_k = stoch_rsi.rolling(window=k_smooth).mean()
        stoch_d = stoch_k.rolling(window=d_smooth).mean()
        
        return stoch_k, stoch_d
    
    def generate_signal(self, symbol: str) -> Optional[StrategySignal]:
        """Generate trading signal for a symbol based on btc_charlie logic"""
        if symbol not in self.market_data:
            return None
        
        df = self.market_data[symbol]
        if len(df) < max(self.slow_ema_period, self.stoch_rsi_length + self.stoch_length):
            return None
        
        # Get latest data
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # Check for main signals (Bull/Bear from EMA crossover with counter)
        if latest['buysignal']:
            # Calculate stop loss and take profit
            stop_loss, take_profit = self._calculate_stop_loss_take_profit(
                current_price, Signal.BUY
            )
            
            return StrategySignal(
                symbol=symbol,
                signal=Signal.BUY,
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=0.9,  # High confidence for main signals
                signal_type="bull"
            )
        
        elif latest['sellsignal']:
            # Calculate stop loss and take profit
            stop_loss, take_profit = self._calculate_stop_loss_take_profit(
                current_price, Signal.SELL
            )
            
            return StrategySignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=0.9,  # High confidence for main signals
                signal_type="bear"
            )
        
        return None
    
    def check_stoch_rsi_alerts(self, symbol: str) -> Optional[StochRSIAlert]:
        """Check for Stochastic RSI alerts (additional alerts from original)"""
        if symbol not in self.market_data:
            return None
        
        df = self.market_data[symbol]
        if len(df) < 2:
            return None
        
        latest = df.iloc[-1]
        current_price = latest['close']
        stoch_k = latest['stoch_rsi_k']
        stoch_d = latest['stoch_rsi_d']
        
        # Check various Stochastic RSI alerts from original
        
        # Crossover alerts at middle level (50)
        if latest['stoch_crossover_up'] and (stoch_k < self.middle_band or stoch_d < self.middle_band):
            return StochRSIAlert(
                symbol=symbol,
                alert_type="crossup_mid",
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stoch_k=stoch_k,
                stoch_d=stoch_d
            )
        
        if latest['stoch_crossover_down'] and (stoch_k > self.middle_band or stoch_d > self.middle_band):
            return StochRSIAlert(
                symbol=symbol,
                alert_type="crossdown_mid",
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stoch_k=stoch_k,
                stoch_d=stoch_d
            )
        
        # Oversold/Overbought crossover alerts
        if latest['stoch_crossover_up'] and (stoch_k < self.lower_band or stoch_d < self.lower_band):
            return StochRSIAlert(
                symbol=symbol,
                alert_type="crossup_os",
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stoch_k=stoch_k,
                stoch_d=stoch_d
            )
        
        if latest['stoch_crossover_down'] and (stoch_k > self.upper_band or stoch_d > self.upper_band):
            return StochRSIAlert(
                symbol=symbol,
                alert_type="crossdown_ob",
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stoch_k=stoch_k,
                stoch_d=stoch_d
            )
        
        # Band crossing alerts
        prev_k = df.iloc[-2]['stoch_rsi_k']
        
        # K crosses under upper band (80)
        if prev_k >= self.upper_band and stoch_k < self.upper_band:
            return StochRSIAlert(
                symbol=symbol,
                alert_type="below_upper_band",
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stoch_k=stoch_k,
                stoch_d=stoch_d
            )
        
        # K crosses over lower band (20)
        if prev_k <= self.lower_band and stoch_k > self.lower_band:
            return StochRSIAlert(
                symbol=symbol,
                alert_type="above_lower_band",
                price=current_price,
                timestamp=int(latest.name.timestamp() * 1000),
                stoch_k=stoch_k,
                stoch_d=stoch_d
            )
        
        return None
    
    def _calculate_stop_loss_take_profit(self, price: float, signal: Signal) -> Tuple[float, float]:
        """Calculate stop loss and take profit levels"""
        if signal == Signal.BUY:
            stop_loss = price * (1 - self.config.stop_loss_percentage)
            take_profit = price * (1 + self.config.take_profit_percentage)
        else:  # SELL
            stop_loss = price * (1 + self.config.stop_loss_percentage)
            take_profit = price * (1 - self.config.take_profit_percentage)
        
        return stop_loss, take_profit
    
    def get_market_summary(self, symbol: str) -> Dict:
        """Get current market summary for a symbol"""
        if symbol not in self.market_data:
            return {}
        
        df = self.market_data[symbol]
        if len(df) == 0:
            return {}
        
        latest = df.iloc[-1]
        
        # Get current trend status
        trend_status = "neutral"
        if latest['bull']:
            trend_status = "strong_bullish"
        elif latest['bear']:
            trend_status = "strong_bearish"
        elif latest['buy']:
            trend_status = "bullish"
        elif latest['sell']:
            trend_status = "bearish"
        
        return {
            'symbol': symbol,
            'price': latest['close'],
            'ema_fast': latest['ema_fast'],
            'ema_slow': latest['ema_slow'],
            'ema_consolidated': latest['ema_consolidated'],
            'stoch_rsi_k': latest['stoch_rsi_k'],
            'stoch_rsi_d': latest['stoch_rsi_d'],
            'trend': trend_status,
            'momentum': 'overbought' if latest['stoch_rsi_k'] > self.upper_band else 'oversold' if latest['stoch_rsi_k'] < self.lower_band else 'neutral',
            'countBuy': int(latest['countBuy']),
            'countSell': int(latest['countSell']),
            'signal_ready': latest['buysignal'] or latest['sellsignal']
        }