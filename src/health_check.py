from aiohttp import web
import json
from datetime import datetime
import asyncio

class HealthCheckServer:
    """Simple HTTP server for health monitoring"""
    
    def __init__(self, bot, port=8080):
        self.bot = bot
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/stats', self.get_stats)
        self.app.router.add_get('/positions', self.get_positions)
        
    async def health_check(self, request):
        """Basic health check endpoint"""
        health_data = {
            'status': 'healthy' if self.bot.is_running and not self.bot.emergency_stop else 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'uptime': str(datetime.now() - self.bot.stats.last_reset),
            'emergency_stop': self.bot.emergency_stop,
            'last_heartbeat': datetime.fromtimestamp(self.bot.last_heartbeat).isoformat()
        }
        
        return web.json_response(health_data)
    
    async def get_stats(self, request):
        """Get bot statistics"""
        stats_data = {
            'trades_executed': self.bot.stats.trades_executed,
            'winning_trades': self.bot.stats.winning_trades,
            'losing_trades': self.bot.stats.losing_trades,
            'win_rate': (self.bot.stats.winning_trades / max(self.bot.stats.trades_executed, 1)) * 100,
            'current_balance': self.bot.account_balance,
            'initial_balance': self.bot.initial_balance,
            'pnl': self.bot.account_balance - self.bot.initial_balance,
            'pnl_percentage': ((self.bot.account_balance - self.bot.initial_balance) / self.bot.initial_balance * 100) if self.bot.initial_balance > 0 else 0,
            'max_drawdown': self.bot.stats.max_drawdown * 100,
            'active_positions': len(self.bot.active_positions)
        }
        
        return web.json_response(stats_data)
    
    async def get_positions(self, request):
        """Get current positions"""
        positions_data = {
            'positions': [
                {
                    'symbol': symbol,
                    'order_id': pos['order_id'],
                    'entry_time': pos['entry_time'].isoformat(),
                    'size': pos['size'],
                    'unrealized_pnl': pos.get('unrealized_pnl', 0)
                }
                for symbol, pos in self.bot.active_positions.items()
            ]
        }
        
        return web.json_response(positions_data)
    
    async def start(self):
        """Start health check server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        self.bot.logger.info(f"Health check server started on port {self.port}")