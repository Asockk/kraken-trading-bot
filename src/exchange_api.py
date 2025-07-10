import time
import hmac
import hashlib
import base64
import json
import requests
import asyncio
import urllib.parse
import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    error_message: Optional[str] = None
    filled_quantity: float = 0.0
    average_price: float = 0.0

@dataclass
class Position:
    symbol: str
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class BaseExchange(ABC):
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(f"exchange.{config.name}")
        
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Dict[str, float]:
        pass

    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        pass

    @abstractmethod
    async def place_order(self, symbol: str, side: str, amount: float,
                          price: float = None, order_type: str = "market",
                          stop_loss: float = None, take_profit: float = None) -> OrderResult:
        pass

class KrakenNonceManager:
    """Thread-safe nonce manager to prevent nonce conflicts"""
    def __init__(self):
        self.last_nonce = 0
        self.lock = threading.Lock()
    
    def get_nonce(self):
        with self.lock:
            nonce = int(time.time() * 1000)
            if nonce <= self.last_nonce:
                nonce = self.last_nonce + 1
            self.last_nonce = nonce
            return str(nonce)

class KrakenExchange(BaseExchange):
    def __init__(self, config):
        super().__init__(config)
        
        self.base_url = "https://api.kraken.com"
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Kraken Trading Bot/1.0'})
        
        # Dekodiere API-Secret
        self.api_secret_decoded = self._decode_api_secret(config.api_secret)
        
        # Nonce manager
        self.nonce_manager = KrakenNonceManager()
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.5
        self.lockout_until = 0
        
        self.logger.info(f"Kraken Exchange initialized")

    def _decode_api_secret(self, api_secret: str) -> bytes:
        """Decode API-Secret from Base64 to bytes"""
        try:
            # Remove whitespace
            api_secret = api_secret.strip()
            
            # Add missing padding if needed
            missing_padding = len(api_secret) % 4
            if missing_padding:
                api_secret += '=' * (4 - missing_padding)
            
            # Decode Base64
            decoded = base64.b64decode(api_secret)
            self.logger.debug(f"API-Secret successfully decoded: {len(decoded)} bytes")
            return decoded
            
        except Exception as e:
            self.logger.error(f"Error decoding API-Secret: {e}")
            raise ValueError(f"Invalid API-Secret: {e}")

    def _convert_symbol_to_kraken(self, symbol: str) -> str:
        """Convert symbol to Kraken format"""
        base, quote = symbol.split("/")
        
        # Kraken-specific conversions
        kraken_map = {
            "BTC": "XBT",
            "USDT": "USD", 
            "USDC": "USD"
        }
        
        base = kraken_map.get(base, base)
        quote = kraken_map.get(quote, quote)
        
        return f"{base}{quote}"

    def _get_kraken_signature(self, urlpath: str, data: Dict[str, str], secret: bytes) -> str:
        """
        Create Kraken API signature based on official documentation
        CRITICAL: URL-encode POST data properly!
        """
        # URL-encode the POST data (CRITICAL FIX!)
        postdata = urllib.parse.urlencode(data)
        
        # Create encoded string for SHA256
        encoded = (str(data['nonce']) + postdata).encode()
        
        # Calculate SHA256 of nonce + POST data
        sha256_hash = hashlib.sha256(encoded).digest()
        
        # Create message: URI path + SHA256 hash
        message = urlpath.encode() + sha256_hash
        
        # Create HMAC-SHA512 with decoded API-Secret
        mac = hmac.new(secret, message, hashlib.sha512)
        
        # Encode to Base64 for API-Sign header
        signature = base64.b64encode(mac.digest()).decode()
        
        return signature

    async def _check_lockout(self):
        """Check if we're in a lockout period"""
        if self.lockout_until > time.time():
            wait_time = self.lockout_until - time.time()
            self.logger.warning(f"API lockout active. Waiting {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)

    async def _make_request(self, method: str, endpoint: str, data: Dict = None, retry_count: int = 0) -> Dict:
        """
        Make API request with correct Kraken authentication
        CRITICAL FIXES: Correct header names and URL encoding
        """
        
        # Check lockout
        await self._check_lockout()
        
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
        
        url = f"{self.base_url}{endpoint}"

        if method == "GET":
            # Public API - no authentication needed
            self.logger.debug(f"GET {url} params={data}")
            response = self.session.get(url, params=data)
            
        else:
            # Private API - authentication required
            if data is None:
                data = {}
            
            # CRITICAL: Use thread-safe nonce manager
            data["nonce"] = self.nonce_manager.get_nonce()
            
            # Create signature
            signature = self._get_kraken_signature(endpoint, data, self.api_secret_decoded)
            
            # CRITICAL: Correct header names!
            headers = {
                "API-Key": self.config.api_key,        # NOT "Kraken_API_key"!
                "API-Sign": signature,                  # NOT "Kraken_API_Signature"!
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            self.logger.debug(f"POST {url}")
            self.logger.debug(f"Nonce: {data['nonce']}")
            self.logger.debug(f"API-Key: {self.config.api_key[:10]}...")
            self.logger.debug(f"API-Sign: {signature[:20]}...")
            
            # POST request with URL-encoded data
            response = self.session.post(url, data=data, headers=headers)

        # Response processing
        self.logger.debug(f"Response Status: {response.status_code}")
        
        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

        try:
            result = response.json()
        except Exception as e:
            error_msg = f"JSON Parse Error: {e}, Response: {response.text}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

        self.logger.debug(f"Response: {result}")

        # Kraken error handling
        if result.get("error") and result["error"]:
            error_msg = result["error"]
            self.logger.error(f"Kraken API Error: {error_msg}")
            
            # Specific error handling
            if "EAPI:Invalid key" in str(error_msg):
                self.logger.error("❌ EAPI:Invalid key - Possible causes:")
                self.logger.error("1. API-Key missing Query Funds permission")
                self.logger.error("2. API-Secret is incomplete or corrupted")
                self.logger.error("3. API-Key has expired")
                self.logger.error("4. Signature algorithm is incorrect")
                
                # Set lockout for 15 minutes
                self.lockout_until = time.time() + 900
                self.logger.warning("Setting 15-minute lockout due to authentication failure")
                
            elif "EAPI:Invalid nonce" in str(error_msg):
                self.logger.error("❌ EAPI:Invalid nonce - Nonce problem")
                if retry_count < 3:
                    await asyncio.sleep(0.1)
                    return await self._make_request(method, endpoint, data, retry_count + 1)
                
            elif "EAPI:Rate limit exceeded" in str(error_msg):
                self.logger.error("❌ Rate limit exceeded - Too many requests")
                self.lockout_until = time.time() + 300  # 5 minute lockout
                self.logger.warning("Setting 5-minute lockout due to rate limit")
            
            raise Exception(f"Kraken API error: {error_msg}")
            
        return result.get("result", {})

    async def get_ticker(self, symbol: str) -> Dict[str, float]:
        """Get ticker data (public API)"""
        try:
            kraken_pair = self._convert_symbol_to_kraken(symbol)
            data = await self._make_request("GET", "/0/public/Ticker", {"pair": kraken_pair})
            
            if not data:
                raise Exception(f"No ticker data for {symbol}")
            
            ticker_data = list(data.values())[0]
            return {
                "bid": float(ticker_data["b"][0]),
                "ask": float(ticker_data["a"][0]),
                "last": float(ticker_data["c"][0]),
                "volume": float(ticker_data["v"][0])
            }
            
        except Exception as e:
            self.logger.error(f"Ticker error for {symbol}: {e}")
            raise

    async def get_balance(self) -> Dict[str, float]:
        """Get account balance - vereinfacht"""
        try:
            data = await self._make_request("POST", "/0/private/Balance")
            
            # Konvertiere Kraken-Währungen zurück
            result = {}
            for currency, balance in data.items():
                # Z = USD prefix bei Kraken
                if currency.startswith('Z'):
                    currency = currency[1:]  # Entferne 'Z' prefix
                elif currency == 'XXBT':
                    currency = 'BTC'
                    
                result[currency] = float(balance)
                
            return result
        except Exception as e:
            self.logger.error(f"Balance error: {e}")
            raise

    async def place_order(self, symbol: str, side: str, amount: float,
                          price: float = None, order_type: str = "market",
                          stop_loss: float = None, take_profit: float = None) -> OrderResult:
        """Place an order"""
        try:
            kraken_pair = self._convert_symbol_to_kraken(symbol)
            
            order_data = {
                "pair": kraken_pair,
                "type": side.lower(),
                "ordertype": order_type,
                "volume": str(amount)
            }
            
            if order_type == "limit" and price:
                order_data["price"] = str(price)
            
            result = await self._make_request("POST", "/0/private/AddOrder", order_data)
            return OrderResult(
                success=True, 
                order_id=result.get("txid", [None])[0] if result.get("txid") else None
            )
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order"""
        try:
            await self._make_request("POST", "/0/private/CancelOrder", {"txid": order_id})
            return True
        except:
            return False

    async def get_positions(self) -> List[Position]:
        """Get open positions"""
        try:
            data = await self._make_request("POST", "/0/private/OpenPositions")
            positions = []
            for pos_id, pos_data in data.items():
                positions.append(Position(
                    symbol=pos_data["pair"],
                    side="long" if pos_data["type"] == "buy" else "short",
                    size=float(pos_data["vol"]),
                    entry_price=float(pos_data["cost"]) / float(pos_data["vol"]),
                    unrealized_pnl=float(pos_data["net"])
                ))
            return positions
        except Exception as e:
            # Normal spot accounts have no positions
            if "EGeneral:Internal error" in str(e) or "EAPI:Feature disabled" in str(e):
                return []
            raise

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 500) -> List[Dict]:
        """Get historical data"""
        try:
            interval_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
            kraken_pair = self._convert_symbol_to_kraken(symbol)
            
            data = await self._make_request("GET", "/0/public/OHLC", {
                "pair": kraken_pair,
                "interval": interval_map.get(timeframe, 60)
            })
            
            if not data:
                return []
            
            candles = list(data.values())[0]
            
            result = []
            for candle in candles[-limit:]:
                result.append({
                    "timestamp": int(candle[0]) * 1000,
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[6])
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Historical data error for {symbol}: {e}")
            return []

def create_exchange(config) -> BaseExchange:
    """Factory function for exchange creation"""
    if config.name.lower() == "kraken":
        return KrakenExchange(config)
    else:
        raise ValueError(f"Unsupported exchange: {config.name}")