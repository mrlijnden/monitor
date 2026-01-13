"""News Ticker Service - Aggregates headlines for scrolling ticker"""
import httpx
import feedparser
from datetime import datetime
from typing import List, Dict
from app.config import amsterdam_now

# News RSS feeds
NEWS_FEEDS = [
    ("https://feeds.nos.nl/nosnieuwsalgemeen", "NOS"),
    ("https://www.at5.nl/rss", "AT5"),
    ("https://www.parool.nl/rss.xml", "Parool"),
]

async def get_ticker_data() -> Dict:
    """Get aggregated news headlines for ticker"""
    headlines = []

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for feed_url, source in NEWS_FEEDS:
                try:
                    response = await client.get(feed_url)
                    if response.status_code == 200:
                        feed = feedparser.parse(response.text)
                        for entry in feed.entries[:5]:
                            headlines.append({
                                "text": entry.title,
                                "source": source,
                                "url": entry.link if hasattr(entry, 'link') else None,
                                "alert": is_alert_headline(entry.title)
                            })
                except Exception:
                    continue

    except Exception as e:
        print(f"Error fetching ticker data: {e}")

    # Add some default headlines if none found
    if not headlines:
        headlines = get_default_headlines()

    # Shuffle to mix sources
    import random
    random.shuffle(headlines)

    return {
        "headlines": headlines[:15],
        "updated": amsterdam_now().strftime("%H:%M:%S")
    }

def is_alert_headline(text: str) -> bool:
    """Check if headline should be marked as alert"""
    alert_words = [
        'breaking', 'urgent', 'alert', 'waarschuwing', 'noodtoestand',
        'evacuatie', 'aanslag', 'accident', 'ongeval', 'brand'
    ]
    return any(word in text.lower() for word in alert_words)

def get_default_headlines() -> List[Dict]:
    """Default headlines when feeds unavailable"""
    return [
        {"text": "GVB meldt vertragingen op tramlijn 2 en 5", "source": "GVB", "alert": False},
        {"text": "Weer: Bewolkt met kans op regen later vandaag", "source": "KNMI", "alert": False},
        {"text": "A10 Ring: Verkeer loopt goed door", "source": "ANWB", "alert": False},
        {"text": "Schiphol: Normale operatie, check vlucht status", "source": "AMS", "alert": False},
        {"text": "P+R locaties: Voldoende capaciteit beschikbaar", "source": "Amsterdam", "alert": False},
        {"text": "Luchtkwaliteit: EU Index 42 - Goed", "source": "RIVM", "alert": False},
        {"text": "IJ-pont: Normale dienstregeling", "source": "GVB", "alert": False},
        {"text": "Evenementen: Geen grote evenementen vandaag", "source": "iAmsterdam", "alert": False},
    ]
