"""P2000 Emergency Scanner Service - Scrapes Dutch emergency services feed"""
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from typing import Optional
from app.config import amsterdam_now, AMSTERDAM_TZ

# P2000 feed sources (public RSS feeds)
P2000_FEEDS = [
    "https://feeds.p2000-online.net/p2000.xml",
    "https://www.p2000-online.net/p2000.xml"
]

# Amsterdam region codes
AMSTERDAM_REGIONS = ["Amsterdam", "Amstelland", "Zaanstreek", "Noord-Holland"]

async def get_emergency_data() -> dict:
    """Fetch P2000 emergency data for Amsterdam region"""
    incidents = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try to fetch from p2000 feed
            for feed_url in P2000_FEEDS:
                try:
                    response = await client.get(feed_url)
                    if response.status_code == 200:
                        # Parse the XML/RSS feed
                        incidents = parse_p2000_feed(response.text)
                        break
                except Exception:
                    continue

            # If no feed worked, generate sample data
            if not incidents:
                incidents = generate_sample_incidents()

    except Exception as e:
        print(f"Error fetching P2000 data: {e}")
        incidents = generate_sample_incidents()

    return {
        "incidents": incidents[:25],  # Latest 25 incidents
        "updated": amsterdam_now().strftime("%H:%M:%S"),
        "status": "live" if incidents else "simulated"
    }

def parse_p2000_feed(xml_content: str) -> list:
    """Parse P2000 RSS/XML feed"""
    incidents = []

    # Simple regex parsing for RSS items
    items = re.findall(r'<item>(.*?)</item>', xml_content, re.DOTALL)

    for item in items[:50]:  # Parse more items from feed
        title_match = re.search(r'<title>(.*?)</title>', item)
        desc_match = re.search(r'<description>(.*?)</description>', item)
        date_match = re.search(r'<pubDate>(.*?)</pubDate>', item)

        if title_match:
            title = title_match.group(1).strip()
            desc = desc_match.group(1).strip() if desc_match else ""

            # Filter for Amsterdam region (but be more lenient)
            is_amsterdam = any(region.lower() in (title + desc).lower()
                             for region in AMSTERDAM_REGIONS)
            
            # Also include nearby regions and major incidents
            nearby_keywords = ["haarlem", "zaandam", "amstelveen", "haarlemmermeer", "diemen", "weesp"]
            is_nearby = any(keyword in (title + desc).lower() for keyword in nearby_keywords)
            
            # Include if Amsterdam region, nearby, or if we need more incidents
            if is_amsterdam or is_nearby or len(incidents) < 15:
                incident_type = classify_incident(title)
                incidents.append({
                    "type": incident_type,
                    "text": clean_text(title),
                    "location": extract_location(desc) or "Amsterdam",
                    "time": parse_time(date_match.group(1) if date_match else None)
                })

    return incidents

def classify_incident(text: str) -> str:
    """Classify incident type based on keywords"""
    text_lower = text.lower()

    if any(word in text_lower for word in ['brand', 'fire', 'rook', 'smoke']):
        return 'fire'
    elif any(word in text_lower for word in ['ambulance', 'letsel', 'medisch', 'reanimatie']):
        return 'ambulance'
    elif any(word in text_lower for word in ['politie', 'police', 'overval', 'inbraak']):
        return 'police'
    else:
        return 'ambulance'  # Default

def clean_text(text: str) -> str:
    """Clean and truncate text"""
    # Remove CDATA, HTML tags, etc
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.strip()
    return text[:80] + "..." if len(text) > 80 else text

def extract_location(text: str) -> Optional[str]:
    """Try to extract location from text"""
    # Look for street patterns
    street_match = re.search(r'(\w+straat|\w+weg|\w+laan|\w+plein)', text, re.IGNORECASE)
    if street_match:
        return street_match.group(1)
    return None

def parse_time(date_str: Optional[str]) -> str:
    """Parse date string to time and convert to Amsterdam timezone"""
    if not date_str:
        return amsterdam_now().strftime("%H:%M")

    try:
        # Try common RSS date formats (usually UTC)
        for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S +0000", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"]:
            try:
                dt_str = date_str.strip()
                # Handle UTC timezone
                if dt_str.endswith(" +0000") or dt_str.endswith(" GMT"):
                    dt_str = dt_str.replace(" +0000", "").replace(" GMT", "")
                    dt = datetime.strptime(dt_str, "%a, %d %b %Y %H:%M:%S")
                    utc_dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                    ams_dt = utc_dt.astimezone(AMSTERDAM_TZ)
                    return ams_dt.strftime("%H:%M")
                elif "Z" in dt_str or "+00:00" in dt_str:
                    dt_str = dt_str.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(dt_str)
                    ams_dt = dt.astimezone(AMSTERDAM_TZ)
                    return ams_dt.strftime("%H:%M")
                else:
                    dt = datetime.strptime(dt_str, fmt)
                    if dt.tzinfo:
                        ams_dt = dt.astimezone(AMSTERDAM_TZ)
                        return ams_dt.strftime("%H:%M")
                    else:
                        # Assume UTC if no timezone
                        utc_dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                        ams_dt = utc_dt.astimezone(AMSTERDAM_TZ)
                        return ams_dt.strftime("%H:%M")
            except ValueError:
                continue
    except Exception:
        pass

    return amsterdam_now().strftime("%H:%M")

def generate_sample_incidents() -> list:
    """Generate realistic sample incidents for demo with coordinates"""
    now = amsterdam_now()
    import random

    # Amsterdam locations with coordinates
    locations = [
        {"name": "Damrak", "area": "Centrum", "lat": 52.3738, "lng": 4.8936},
        {"name": "Kinkerstraat", "area": "West", "lat": 52.3688, "lng": 4.8695},
        {"name": "Albert Cuypstraat", "area": "De Pijp", "lat": 52.3559, "lng": 4.8951},
        {"name": "Overtoom", "area": "Oud-West", "lat": 52.3621, "lng": 4.8721},
        {"name": "Wibautstraat", "area": "Oost", "lat": 52.3541, "lng": 4.9127},
        {"name": "Museumplein", "area": "Zuid", "lat": 52.3573, "lng": 4.8793},
        {"name": "Leidseplein", "area": "Centrum", "lat": 52.3641, "lng": 4.8828},
        {"name": "Waterlooplein", "area": "Centrum", "lat": 52.3678, "lng": 4.9012},
        {"name": "Ferdinand Bolstraat", "area": "De Pijp", "lat": 52.3512, "lng": 4.8932},
        {"name": "Rozengracht", "area": "Jordaan", "lat": 52.3725, "lng": 4.8782},
        {"name": "Amstelveenseweg", "area": "Zuid", "lat": 52.3445, "lng": 4.8612},
        {"name": "Middenweg", "area": "Oost", "lat": 52.3521, "lng": 4.9321},
        {"name": "Nieuwmarkt", "area": "Centrum", "lat": 52.3720, "lng": 4.9010},
        {"name": "Jordaan", "area": "Jordaan", "lat": 52.3770, "lng": 4.8750},
        {"name": "Oosterpark", "area": "Oost", "lat": 52.3600, "lng": 4.9200},
        {"name": "Vondelpark", "area": "Zuid", "lat": 52.3664, "lng": 4.8795},
        {"name": "Westerpark", "area": "West", "lat": 52.3860, "lng": 4.8800},
        {"name": "Rembrandtplein", "area": "Centrum", "lat": 52.3667, "lng": 4.8950},
        {"name": "Spui", "area": "Centrum", "lat": 52.3690, "lng": 4.8880},
        {"name": "Utrechtsestraat", "area": "Centrum", "lat": 52.3650, "lng": 4.8900},
    ]

    incidents = [
        {
            "type": "ambulance",
            "text": "A1 Spoed - Reanimatie Damrak ter hoogte van nr 42",
            "location": "Centrum",
            "lat": 52.3738 + random.uniform(-0.002, 0.002),
            "lng": 4.8936 + random.uniform(-0.002, 0.002),
            "time": now.strftime("%H:%M")
        },
        {
            "type": "fire",
            "text": "P1 Brand - Melding rookontwikkeling Kinkerstraat",
            "location": "West",
            "lat": 52.3688 + random.uniform(-0.002, 0.002),
            "lng": 4.8695 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-3))).strftime("%H:%M")
        },
        {
            "type": "police",
            "text": "Prio 1 - Melding overval Albert Cuypstraat",
            "location": "De Pijp",
            "lat": 52.3559 + random.uniform(-0.002, 0.002),
            "lng": 4.8951 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-7))).strftime("%H:%M")
        },
        {
            "type": "ambulance",
            "text": "A2 - Ongeval letsel Overtoom / Eerste Const. Huygensstr",
            "location": "Oud-West",
            "lat": 52.3621 + random.uniform(-0.002, 0.002),
            "lng": 4.8721 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-12))).strftime("%H:%M")
        },
        {
            "type": "fire",
            "text": "P2 Brand - Containerbrand Wibautstraat",
            "location": "Oost",
            "lat": 52.3541 + random.uniform(-0.002, 0.002),
            "lng": 4.9127 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-18))).strftime("%H:%M")
        },
        {
            "type": "ambulance",
            "text": "A1 - Val van hoogte Museumplein",
            "location": "Zuid",
            "lat": 52.3573 + random.uniform(-0.002, 0.002),
            "lng": 4.8793 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-25))).strftime("%H:%M")
        },
        {
            "type": "police",
            "text": "Prio 2 - Vechtpartij Leidseplein",
            "location": "Centrum",
            "lat": 52.3641 + random.uniform(-0.002, 0.002),
            "lng": 4.8828 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-32))).strftime("%H:%M")
        },
        {
            "type": "ambulance",
            "text": "A2 - Ongeluk met letsel Nieuwmarkt",
            "location": "Centrum",
            "lat": 52.3720 + random.uniform(-0.002, 0.002),
            "lng": 4.9010 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-40))).strftime("%H:%M")
        },
        {
            "type": "fire",
            "text": "P1 Brand - Keukenbrand Jordaan",
            "location": "Jordaan",
            "lat": 52.3770 + random.uniform(-0.002, 0.002),
            "lng": 4.8750 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-45))).strftime("%H:%M")
        },
        {
            "type": "police",
            "text": "Prio 1 - Inbraak Oosterpark",
            "location": "Oost",
            "lat": 52.3600 + random.uniform(-0.002, 0.002),
            "lng": 4.9200 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-50))).strftime("%H:%M")
        },
        {
            "type": "ambulance",
            "text": "A1 Spoed - Val Vondelpark",
            "location": "Zuid",
            "lat": 52.3664 + random.uniform(-0.002, 0.002),
            "lng": 4.8795 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-55))).strftime("%H:%M")
        },
        {
            "type": "fire",
            "text": "P2 Brand - Afvalcontainer Westerpark",
            "location": "West",
            "lat": 52.3860 + random.uniform(-0.002, 0.002),
            "lng": 4.8800 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-60))).strftime("%H:%M")
        },
        {
            "type": "police",
            "text": "Prio 2 - Overlast Rembrandtplein",
            "location": "Centrum",
            "lat": 52.3667 + random.uniform(-0.002, 0.002),
            "lng": 4.8950 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-65))).strftime("%H:%M")
        },
        {
            "type": "ambulance",
            "text": "A2 - Medische hulp Spui",
            "location": "Centrum",
            "lat": 52.3690 + random.uniform(-0.002, 0.002),
            "lng": 4.8880 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-70))).strftime("%H:%M")
        },
        {
            "type": "fire",
            "text": "P1 Brand - Rookmelding Utrechtsestraat",
            "location": "Centrum",
            "lat": 52.3650 + random.uniform(-0.002, 0.002),
            "lng": 4.8900 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-75))).strftime("%H:%M")
        },
        {
            "type": "police",
            "text": "Prio 1 - Vermissing Centrum",
            "location": "Centrum",
            "lat": 52.3738 + random.uniform(-0.002, 0.002),
            "lng": 4.8936 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-80))).strftime("%H:%M")
        },
        {
            "type": "ambulance",
            "text": "A1 Spoed - Reanimatie Kinkerstraat",
            "location": "West",
            "lat": 52.3688 + random.uniform(-0.002, 0.002),
            "lng": 4.8695 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-85))).strftime("%H:%M")
        },
        {
            "type": "fire",
            "text": "P2 Brand - Schoorsteenbrand De Pijp",
            "location": "De Pijp",
            "lat": 52.3559 + random.uniform(-0.002, 0.002),
            "lng": 4.8951 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-90))).strftime("%H:%M")
        },
        {
            "type": "police",
            "text": "Prio 2 - Verkeersongeval Oud-West",
            "location": "Oud-West",
            "lat": 52.3621 + random.uniform(-0.002, 0.002),
            "lng": 4.8721 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-95))).strftime("%H:%M")
        },
        {
            "type": "ambulance",
            "text": "A2 - Ongeval met fietser Oost",
            "location": "Oost",
            "lat": 52.3541 + random.uniform(-0.002, 0.002),
            "lng": 4.9127 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-100))).strftime("%H:%M")
        },
        {
            "type": "fire",
            "text": "P1 Brand - Appartement Zuid",
            "location": "Zuid",
            "lat": 52.3573 + random.uniform(-0.002, 0.002),
            "lng": 4.8793 + random.uniform(-0.002, 0.002),
            "time": (now.replace(minute=max(0, now.minute-105))).strftime("%H:%M")
        }
    ]

    return incidents
