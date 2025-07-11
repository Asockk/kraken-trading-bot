# src/database.py
import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

class TradeDatabase:
    """Async SQLite database for trade history and analytics"""
    
    def __init__(self, db_path: str = "data/trades.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.db_initialized = False
    
    async def initialize(self):
        """Initialize database tables - must be called before use"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    amount REAL NOT NULL,
                    price REAL NOT NULL,
                    fee REAL DEFAULT 0,
                    timestamp DATETIME NOT NULL,
                    status TEXT NOT NULL,
                    pnl REAL,
                    strategy_signal TEXT,
                    notes TEXT
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL,
                    size REAL NOT NULL,
                    unrealized_pnl REAL DEFAULT 0,
                    opened_at DATETIME NOT NULL,
                    closed_at DATETIME,
                    status TEXT NOT NULL
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    balance REAL NOT NULL,
                    trades_count INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    max_drawdown REAL DEFAULT 0,
                    sharpe_ratio REAL,
                    UNIQUE(date)
                )
            ''')
            
            await db.commit()
            self.db_initialized = True
    
    async def log_trade(self, order_id: str, symbol: str, side: str, 
                       amount: float, price: float, fee: float = 0,
                       strategy_signal: dict = None):
        """Log a trade to database"""
        if not self.db_initialized:
            await self.initialize()
            
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO trades 
                (order_id, symbol, side, amount, price, fee, timestamp, status, strategy_signal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_id, symbol, side, amount, price, fee,
                datetime.now().isoformat(), 'executed',
                json.dumps(strategy_signal) if strategy_signal else None
            ))
            await db.commit()
    
    async def update_trade_pnl(self, order_id: str, pnl: float):
        """Update trade PnL"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE trades SET pnl = ? WHERE order_id = ?',
                (pnl, order_id)
            )
            await db.commit()
    
    async def get_trade_history(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """Get trade history"""
        if not self.db_initialized:
            await self.initialize()
            
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if symbol:
                cursor = await db.execute(
                    'SELECT * FROM trades WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?',
                    (symbol, limit)
                )
            else:
                cursor = await db.execute(
                    'SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?',
                    (limit,)
                )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def log_position_open(self, symbol: str, side: str, entry_price: float, size: float):
        """Log opening of a position"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO positions 
                (symbol, side, entry_price, size, opened_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                symbol, side, entry_price, size,
                datetime.now().isoformat(), 'open'
            ))
            await db.commit()
    
    async def log_position_close(self, symbol: str, close_price: float, pnl: float):
        """Log closing of a position"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE positions 
                SET current_price = ?, 
                    unrealized_pnl = ?, 
                    closed_at = ?,
                    status = ?
                WHERE symbol = ? AND status = 'open'
                ORDER BY opened_at DESC
                LIMIT 1
            ''', (
                close_price, pnl, datetime.now().isoformat(), 
                'closed', symbol
            ))
            await db.commit()
    
    async def calculate_performance_metrics(self) -> Dict:
        """Calculate performance metrics"""
        if not self.db_initialized:
            await self.initialize()
            
        async with aiosqlite.connect(self.db_path) as db:
            # Get all executed trades
            cursor = await db.execute(
                "SELECT pnl FROM trades WHERE status = 'executed' AND pnl IS NOT NULL"
            )
            trades = await cursor.fetchall()
            
            if not trades:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'avg_win': 0,
                    'avg_loss': 0,
                    'profit_factor': 0
                }
            
            pnls = [trade[0] for trade in trades]
            winning_trades = [pnl for pnl in pnls if pnl > 0]
            losing_trades = [pnl for pnl in pnls if pnl < 0]
            
            total_trades = len(pnls)
            num_winning = len(winning_trades)
            num_losing = len(losing_trades)
            
            total_pnl = sum(pnls)
            avg_win = sum(winning_trades) / num_winning if num_winning > 0 else 0
            avg_loss = sum(losing_trades) / num_losing if num_losing > 0 else 0
            
            # Profit factor = total wins / total losses
            total_wins = sum(winning_trades) if winning_trades else 0
            total_losses = abs(sum(losing_trades)) if losing_trades else 1
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
            
            return {
                'total_trades': total_trades,
                'winning_trades': num_winning,
                'losing_trades': num_losing,
                'win_rate': (num_winning / total_trades * 100) if total_trades > 0 else 0,
                'total_pnl': total_pnl,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor
            }
    
    async def save_daily_performance(self, balance: float, trades_today: int, 
                                   wins_today: int, losses_today: int, 
                                   pnl_today: float, max_drawdown: float):
        """Save daily performance metrics"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO performance 
                (date, balance, trades_count, winning_trades, losing_trades, 
                 total_pnl, max_drawdown)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().date().isoformat(),
                balance, trades_today, wins_today, losses_today,
                pnl_today, max_drawdown
            ))
            await db.commit()