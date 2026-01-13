import httpx
import yfinance as yf
from datetime import datetime
from app.config import COINGECKO_URL, CACHE_TTL
from app.core.cache import cache


async def fetch_crypto() -> dict:
    """Fetch crypto prices from CoinGecko."""
    try:
        params = {
            "ids": "bitcoin,ethereum,solana",
            "vs_currencies": "eur,usd",
            "include_24hr_change": "true",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(COINGECKO_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            crypto = {}
            for coin_id, values in data.items():
                crypto[coin_id.upper()] = {
                    "eur": values.get("eur"),
                    "usd": values.get("usd"),
                    "change_24h": values.get("eur_24h_change"),
                }

            return crypto

    except Exception:
        return {}


def fetch_stocks() -> dict:
    """Fetch stock data using yfinance."""
    try:
        # AEX Index (Amsterdam)
        aex = yf.Ticker("^AEX")
        aex_info = aex.fast_info

        return {
            "AEX": {
                "price": aex_info.last_price if hasattr(aex_info, 'last_price') else None,
                "change": aex_info.last_price - aex_info.previous_close if hasattr(aex_info, 'previous_close') else None,
                "change_pct": ((aex_info.last_price - aex_info.previous_close) / aex_info.previous_close * 100)
                             if hasattr(aex_info, 'previous_close') and aex_info.previous_close else None,
            }
        }
    except Exception:
        return {}


async def fetch_markets() -> dict:
    """Fetch all market data."""
    crypto = await fetch_crypto()
    stocks = fetch_stocks()

    result = {
        "crypto": crypto,
        "stocks": stocks,
        "updated_at": datetime.now().isoformat(),
    }

    cache.set("markets", result, CACHE_TTL["markets"])
    return result


async def get_markets() -> dict:
    """Get markets from cache or fetch if needed."""
    cached = cache.get("markets")
    if cached:
        return cached
    return await fetch_markets()
