import asyncio
import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
import signal
import sys
from datetime import datetime
import json
from pathlib import Path

from config import ConfigManager
from exchange_api import create_exchange, Position
from strategy import BTCCharlieStrategy, Signal, StrategySignal
from health_check import HealthCheckServer
from database import TradeDatabase

@dataclass
class BotStats:
    trades_executed: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    daily_pnl: float = 0.0
    last_reset: datetime = None

class TradingBot:
    """
    Main trading bot implementing btc_charlie Trader XO Macro Trend Scanner strategy
    """
    
    def __init__(self, config_file: str = "config.yaml"):
        # Load configuration
        self.config_manager = ConfigManager(config_file)
        self.config = self.config_manager.trading_config
        
        # Initialize logging
        self.setup_logging()
        
        # Initialize exchange
        exchange_name = self.config_manager.get_active_exchange()
        exchange_config = self.config_manager.exchange_configs[exchange_name]
        self.exchange = create_exchange(exchange_config)
        
        # Initialize strategy
        self.strategy = BTCCharlieStrategy(self.config)
        
        # Initialize bot state
        self.active_positions = {}  # symbol -> Position
        self.position_lock = asyncio.Lock()
        self.is_running = False
        self.emergency_stop = False
        
        # Initialize statistics
        self.stats = BotStats(last_reset=datetime.now())
        
        # Risk management
        self.account_balance = 0.0
        self.initial_balance = 0.0
        
        # Stats persistence
        self.stats_file = Path("data/stats.json")
        self.stats_file.parent.mkdir(exist_ok=True)
        self.load_stats()
        
        # Save stats periodically
        self.last_stats_save = time.time()
        self.stats_save_interval = getattr(self.config, 'save_stats_interval', 3600)
        
        # Dead Man's Switch
        self.last_heartbeat = time.time()
        self.dead_mans_switch_enabled = getattr(
            self.config, 'enable_dead_mans_switch', False
        )
        self.dead_mans_switch_timeout = getattr(
            self.config, 'dead_mans_switch_timeout', 3600
        )
        
        # Health Check Server
        self.health_server = None
        if getattr(self.config, 'enable_health_check', False):
            self.health_server = HealthCheckServer(
                self, 
                getattr(self.config, 'health_check_port', 8080)
            )
        
        # Database (optional)
        self.database = None
        if getattr(self.config, 'enable_database', False):
            db_path = getattr(self.config, 'database_path', 'data/trades.db')
            self.database = TradeDatabase(db_path)
            self.logger.info(f"Database initialized at {db_path}")
        
        self.logger.info(f"Trading bot initialized with {exchange_name} exchange")
        self.logger.info(f"Trading pairs: {self.config.trading_pairs}")
        self.logger.info(f"Dead Man's Switch: {'ENABLED' if self.dead_mans_switch_enabled else 'DISABLED'}")
        self.logger.info(f"Health Check: {'ENABLED' if self.health_server else 'DISABLED'}")
        self.logger.info(f"Database: {'ENABLED' if self.database else 'DISABLED'}")
    
    def setup_logging(self):
        """Setup comprehensive logging"""
        self.logger = logging.getLogger("trading_bot")
        self.logger.setLevel(getattr(logging, self.config.log_level))
        
        # File handler
        file_handler = logging.FileHandler('logs/trading_bot.log')
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    async def start(self):
        """Start the trading bot"""
        self.logger.info("Starting trading bot...")
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Start health check server if enabled
        if self.health_server:
            await self.health_server.start()
        
        # Initialize account balance
        await self._update_account_balance()
        self.initial_balance = self.account_balance
        
        # Start main trading loop
        self.is_running = True
        await self._main_loop()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.is_running = False
    
    async def _check_dead_mans_switch(self):
        """Check if bot is still responsive"""
        if not self.dead_mans_switch_enabled:
            return
            
        time_since_heartbeat = time.time() - self.last_heartbeat
        
        if time_since_heartbeat > self.dead_mans_switch_timeout:
            self.logger.critical(
                f"Dead man's switch triggered! No activity for {time_since_heartbeat:.0f}s"
            )
            self.emergency_stop = True
            await self._emergency_close_all_positions()
    
    def update_heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = time.time()
    
    async def _main_loop(self):
        """Main trading loop"""
        while self.is_running and not self.emergency_stop:
            try:
                # Update heartbeat at start of each loop
                self.update_heartbeat()
                
                # Check dead man's switch
                await self._check_dead_mans_switch()
                
                # Update market data for all trading pairs
                await self._update_market_data()
                
                # Generate and process signals
                await self._process_signals()
                
                # Update account balance and check risk limits
                await self._update_account_balance()
                await self._check_risk_limits()
                
                # Monitor existing positions
                await self._monitor_positions()
                
                # Log statistics
                self._log_statistics()
                
                # Update daily performance in database
                if self.database:
                    await self._update_database_performance()
                
                # Wait before next iteration
                await asyncio.sleep(self.config.data_update_interval)
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying
        
        # Shutdown cleanup
        await self._shutdown()
    
    async def _update_market_data(self):
        """Update market data for all trading pairs"""
        for symbol in self.config.trading_pairs:
            try:
                # Get historical data
                historical_data = await self.exchange.get_historical_data(
                    symbol, self.config.timeframe, limit=200
                )
                
                # Update strategy with new data
                self.strategy.update_market_data(symbol, historical_data)
                
            except Exception as e:
                self.logger.error(f"Error updating market data for {symbol}: {e}")
    
    async def _process_signals(self):
        """Process trading signals for all pairs"""
        for symbol in self.config.trading_pairs:
            try:
                # Generate main trading signal (Bull/Bear based on EMA counter logic)
                signal = self.strategy.generate_signal(symbol)
                
                if signal and signal.signal != Signal.HOLD:
                    await self._execute_signal(signal)
                
                # Check for Stochastic RSI alerts (informational only)
                stoch_alert = self.strategy.check_stoch_rsi_alerts(symbol)
                if stoch_alert:
                    self.logger.info(f"Stochastic RSI Alert for {symbol}: {stoch_alert.alert_type} "
                                   f"at price {stoch_alert.price:.2f}, "
                                   f"K={stoch_alert.stoch_k:.2f}, D={stoch_alert.stoch_d:.2f}")
                    
            except Exception as e:
                self.logger.error(f"Error processing signal for {symbol}: {e}")
    
    async def _execute_signal(self, signal: StrategySignal):
        """Execute a trading signal"""
        async with self.position_lock:
            # Check if we already have a position for this symbol
            if (self.config.one_position_per_pair and 
                signal.symbol in self.active_positions):
                self.logger.info(f"Skipping signal for {signal.symbol} - position already exists")
                return
            
            # Calculate position size with min/max limits
            position_size = self._calculate_position_size(signal.price)
            
            # Check minimum order size
            min_order_usd = getattr(self.config, 'min_order_size_usd', 10.0)
            if position_size * signal.price < min_order_usd:
                self.logger.warning(f"Position size too small for {signal.symbol}: ${position_size * signal.price:.2f}")
                return
            
            # Execute order
            self.logger.info(f"Executing {signal.signal.value} signal for {signal.symbol}")
            self.logger.info(f"Price: {signal.price}, Size: {position_size}, Confidence: {signal.confidence}")
            
            order_result = await self.exchange.place_order(
                symbol=signal.symbol,
                side=signal.signal.value,
                amount=position_size,
                order_type=self.config.order_type,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit
            )
            
            if order_result.success:
                self.logger.info(f"Order executed successfully: {order_result.order_id}")
                
                # Track position
                self.active_positions[signal.symbol] = {
                    'order_id': order_result.order_id,
                    'signal': signal,
                    'entry_time': datetime.now(),
                    'size': position_size
                }
                
                self.stats.trades_executed += 1
                
                # Log to database
                if self.database:
                    await self.database.log_trade(
                        order_id=order_result.order_id,
                        symbol=signal.symbol,
                        side=signal.signal.value,
                        amount=position_size,
                        price=signal.price,
                        fee=self._calculate_fee(position_size * signal.price),
                        strategy_signal={
                            'type': signal.signal_type,
                            'confidence': signal.confidence,
                            'stop_loss': signal.stop_loss,
                            'take_profit': signal.take_profit
                        }
                    )
                
            else:
                self.logger.error(f"Order execution failed: {order_result.error_message}")
    
    def _calculate_position_size(self, price: float) -> float:
        """Calculate position size based on risk management rules"""
        if self.account_balance <= 0:
            return 0.0
        
        # Calculate maximum position value
        max_position_value = self.account_balance * self.config.max_position_size
        
        # Apply max order size limit
        max_order_usd = getattr(self.config, 'max_order_size_usd', 10000.0)
        max_position_value = min(max_position_value, max_order_usd)
        
        # Calculate position size
        position_size = max_position_value / price
        
        # Apply symbol-specific minimums (hardcoded for now, should be from config)
        if 'BTC' in price:
            position_size = max(position_size, 0.0001)  # Min BTC
        elif 'ETH' in price:
            position_size = max(position_size, 0.005)   # Min ETH
        
        return position_size
    
    def _calculate_fee(self, order_value: float) -> float:
        """Calculate trading fee"""
        if self.config.order_type == "market":
            fee_rate = getattr(self.config, 'taker_fee', 0.0026)
        else:
            fee_rate = getattr(self.config, 'maker_fee', 0.0016)
        
        return order_value * fee_rate
    
    async def _update_account_balance(self):
        """Update account balance - nur USD verwenden"""
        try:
            balances = await self.exchange.get_balance()
            
            # NUR USD Balance verwenden (Kraken nutzt USD, nicht USDT)
            self.account_balance = balances.get('USD', 0.0)
            
            # Optional: Zeige auch andere Balances zur Info
            if self.logger.level == logging.DEBUG:
                for currency, balance in balances.items():
                    if balance > 0:
                        self.logger.debug(f"Balance {currency}: {balance}")
            
            self.logger.info(f"USD Balance: ${self.account_balance:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error updating account balance: {e}")
    
    async def _check_risk_limits(self):
        """Check risk limits and implement emergency stop if needed"""
        if self.initial_balance <= 0:
            return
        
        # Calculate current drawdown
        current_drawdown = (self.initial_balance - self.account_balance) / self.initial_balance
        self.stats.current_drawdown = current_drawdown
        
        if current_drawdown > self.stats.max_drawdown:
            self.stats.max_drawdown = current_drawdown
        
        # Check maximum drawdown limit
        if current_drawdown > self.config.max_drawdown:
            self.logger.critical(f"Maximum drawdown exceeded: {current_drawdown:.2%}")
            self.emergency_stop = True
            await self._emergency_close_all_positions()
        
        # Check daily loss limit
        daily_loss = (self.account_balance - self.initial_balance) / self.initial_balance
        if daily_loss < -self.config.max_daily_loss:
            self.logger.critical(f"Daily loss limit exceeded: {daily_loss:.2%}")
            self.emergency_stop = True
            await self._emergency_close_all_positions()
    
    async def _monitor_positions(self):
        """Monitor existing positions"""
        try:
            positions = await self.exchange.get_positions()
            
            for position in positions:
                if position.symbol in self.active_positions:
                    # Update position tracking
                    self.active_positions[position.symbol]['unrealized_pnl'] = position.unrealized_pnl
                    
                    # Log position status
                    self.logger.debug(f"Position {position.symbol}: "
                                    f"Size: {position.size}, "
                                    f"Entry: {position.entry_price}, "
                                    f"PnL: {position.unrealized_pnl}")
        
        except Exception as e:
            self.logger.error(f"Error monitoring positions: {e}")
    
    async def _emergency_close_all_positions(self):
        """Emergency close all positions"""
        self.logger.warning("Emergency closing all positions")
        
        try:
            positions = await self.exchange.get_positions()
            
            for position in positions:
                # Close position with market order
                side = "sell" if position.side == "long" else "buy"
                
                order_result = await self.exchange.place_order(
                    symbol=position.symbol,
                    side=side,
                    amount=position.size,
                    order_type="market"
                )
                
                if order_result.success:
                    self.logger.info(f"Emergency closed position {position.symbol}")
                else:
                    self.logger.error(f"Failed to close position {position.symbol}: {order_result.error_message}")
        
        except Exception as e:
            self.logger.error(f"Error during emergency close: {e}")
    
    async def _update_database_performance(self):
        """Update daily performance in database"""
        if not self.database:
            return
            
        try:
            metrics = await self.database.calculate_performance_metrics()
            # Log daily performance
            # This would be expanded with actual daily tracking
            self.logger.debug(f"Performance metrics: {metrics}")
        except Exception as e:
            self.logger.error(f"Error updating database performance: {e}")
    
    def _log_statistics(self):
        """Log current statistics"""
        win_rate = (self.stats.winning_trades / max(self.stats.trades_executed, 1)) * 100
        
        self.logger.info(f"Statistics - Balance: ${self.account_balance:.2f}, "
                        f"Trades: {self.stats.trades_executed}, "
                        f"Win Rate: {win_rate:.1f}%, "
                        f"Drawdown: {self.stats.current_drawdown:.2%}, "
                        f"Active Positions: {len(self.active_positions)}")
        
        # Save stats periodically
        if time.time() - self.last_stats_save > self.stats_save_interval:
            self.save_stats()
            self.last_stats_save = time.time()
    
    async def _shutdown(self):
        """Shutdown cleanup"""
        self.logger.info("Shutting down trading bot...")
        
        # Close all positions if emergency stop
        if self.emergency_stop:
            await self._emergency_close_all_positions()
        
        # Final statistics
        self._log_final_statistics()
        
        # Save final stats
        self.save_stats()
        
        self.logger.info("Trading bot shutdown complete")
    
    def _log_final_statistics(self):
        """Log final statistics"""
        runtime = datetime.now() - self.stats.last_reset
        total_return = ((self.account_balance - self.initial_balance) / self.initial_balance) * 100
        
        self.logger.info("=== FINAL STATISTICS ===")
        self.logger.info(f"Runtime: {runtime}")
        self.logger.info(f"Initial Balance: ${self.initial_balance:.2f}")
        self.logger.info(f"Final Balance: ${self.account_balance:.2f}")
        self.logger.info(f"Total Return: {total_return:.2f}%")
        self.logger.info(f"Total Trades: {self.stats.trades_executed}")
        self.logger.info(f"Winning Trades: {self.stats.winning_trades}")
        self.logger.info(f"Losing Trades: {self.stats.losing_trades}")
        self.logger.info(f"Maximum Drawdown: {self.stats.max_drawdown:.2%}")
        
    def load_stats(self):
        """Load statistics from file"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    # Restore stats (except last_reset)
                    self.stats.trades_executed = data.get('trades_executed', 0)
                    self.stats.winning_trades = data.get('winning_trades', 0)
                    self.stats.losing_trades = data.get('losing_trades', 0)
                    self.stats.total_pnl = data.get('total_pnl', 0.0)
                    self.logger.info(f"Loaded stats: {self.stats.trades_executed} trades")
            except Exception as e:
                self.logger.error(f"Error loading stats: {e}")
                
    def save_stats(self):
        """Save statistics to file"""
        try:
            stats_data = {
                'trades_executed': self.stats.trades_executed,
                'winning_trades': self.stats.winning_trades,
                'losing_trades': self.stats.losing_trades,
                'total_pnl': self.stats.total_pnl,
                'max_drawdown': self.stats.max_drawdown,
                'last_update': datetime.now().isoformat(),
                'current_balance': self.account_balance
            }
            
            with open(self.stats_file, 'w') as f:
                json.dump(stats_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving stats: {e}")

async def main():
    """Main entry point"""
    bot = TradingBot("config.yaml")
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())