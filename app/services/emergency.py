"""P2000 Emergency Scanner Service - Scrapes Dutch emergency services feed"""
import httpx
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from typing import Optional, Tuple
from app.config import amsterdam_now, AMSTERDAM_TZ

# P2000 data sources
# Use the Python script endpoint that returns HTML table
P2000_URL = "https://www.p2000-online.net/p2000.py?adamal=1&aantal=50"  # Amsterdam-Amstelland, 50 items
P2000_RSS_FEEDS = [
    "https://feeds.p2000-online.net/p2000.xml",  # RSS feed (if available)
    # Alternative RSS feeds:
    # "https://112-nu.nl/rss.php?regio=noord-holland",
    # "https://alarmeringen.nl/webfeeds/rss.php?regio=noord-holland",
]

# Amsterdam region codes
AMSTERDAM_REGIONS = ["Amsterdam", "Amstelland", "Zaanstreek", "Noord-Holland"]

# Geocoding cache to avoid repeated API calls
_geocoding_cache = {}

async def get_emergency_data() -> dict:
    """Fetch P2000 emergency data for Amsterdam region"""
    incidents = []
    is_live_data = False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # First try HTML scraping (main source)
            try:
                response = await client.get(P2000_URL, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if response.status_code == 200:
                    parsed_incidents = parse_p2000_html(response.text)
                    if parsed_incidents:
                        incidents = parsed_incidents
                        is_live_data = True
            except Exception as e:
                print(f"Error fetching P2000 HTML {P2000_URL}: {e}")
            
            # If HTML didn't work, try RSS feeds as fallback
            if not incidents:
                for feed_url in P2000_RSS_FEEDS:
                    try:
                        response = await client.get(feed_url)
                        if response.status_code == 200:
                            # Check if response is actually RSS/XML (not HTML error page)
                            content_type = response.headers.get('content-type', '').lower()
                            if 'xml' in content_type or response.text.strip().startswith('<?xml') or '<rss' in response.text.lower() or '<feed' in response.text.lower():
                                # Parse the XML/RSS feed
                                parsed_incidents = parse_p2000_feed(response.text)
                                if parsed_incidents:
                                    incidents = parsed_incidents
                                    is_live_data = True
                                    break
                    except Exception as e:
                        print(f"Error fetching RSS feed {feed_url}: {e}")
                        continue

    except Exception as e:
        print(f"Error fetching P2000 data: {e}")

    # Geocode only top incidents for faster loading
    # Limit to first 10 incidents to avoid slow API calls
    # Use parallel geocoding for better performance
    geocoding_tasks = []
    incidents_to_geocode = incidents[:10]  # Only geocode top 10
    
    for incident in incidents_to_geocode:
        location = incident.get("location", "")
        # Only geocode if it's a specific street/address, not generic locations
        if location and location != "Amsterdam" and any(word in location.lower() for word in ["straat", "weg", "laan", "plein", "kade", "gracht"]):
            geocoding_tasks.append((incident, geocode_address(location)))
    
    # Run geocoding in parallel (but limit concurrent requests)
    if geocoding_tasks:
        # Process in batches of 3 to respect rate limits
        for i in range(0, len(geocoding_tasks), 3):
            batch = geocoding_tasks[i:i+3]
            results = await asyncio.gather(*[task[1] for task in batch], return_exceptions=True)
            for (incident, _), coords in zip(batch, results):
                if coords and not isinstance(coords, Exception):
                    incident["lat"] = coords[0]
                    incident["lng"] = coords[1]
    
    return {
        "incidents": incidents[:25],  # Return all incidents, but only top 10 have coords
        "updated": amsterdam_now().strftime("%H:%M:%S"),
        "status": "live" if is_live_data else "simulated"
    }

def parse_p2000_html(html_content: str) -> list:
    """Parse P2000 HTML page with table structure"""
    incidents = []
    
    if not html_content or '<table' not in html_content.lower():
        return incidents
    
    # Find all table rows with incident data
    # Pattern: <tr><td class="DT">date time</td><td class="Po|Am|Br">type</td><td class="Regio">region</td><td class="Md">message</td></tr>
    row_pattern = r'<tr><td class="DT">([^<]+)</td><td class="(Po|Am|Br)">([^<]+)</td><td class="Regio">([^<]+)</td><td class="Md">([^<]+)</td></tr>'
    matches = re.findall(row_pattern, html_content, re.IGNORECASE)
    
    for match in matches[:50]:  # Limit to 50 incidents
        date_time_str, type_class, type_name, region, message = match
        
        # Parse date/time
        # Format: "13-01-2026 17:19:17"
        time_str = amsterdam_now().strftime("%H:%M")
        try:
            dt_match = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', date_time_str)
            if dt_match:
                time_str = f"{dt_match.group(1)}:{dt_match.group(2)}"
        except:
            pass
        
        # Determine incident type from class
        if type_class.lower() == 'br':
            incident_type = 'fire'
        elif type_class.lower() == 'am':
            incident_type = 'ambulance'
        elif type_class.lower() == 'po':
            incident_type = 'police'
        else:
            incident_type = classify_incident(message)
        
        # Extract location and postcode from message
        location = extract_location(message) or region or "Amsterdam"
        postcode = extract_postcode(message)
        
        incident = {
            "type": incident_type,
            "text": clean_text(message),
            "location": location,
            "postcode": postcode,
            "time": time_str
        }
        
        incidents.append(incident)
    
    return incidents

def parse_p2000_feed(xml_content: str) -> list:
    """Parse P2000 RSS/XML feed"""
    incidents = []
    
    # Check if content is actually XML/RSS (not HTML error page)
    if not xml_content or '<html' in xml_content.lower() or '404' in xml_content or 'not found' in xml_content.lower():
        return incidents

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
                location = extract_location(title + " " + desc) or "Amsterdam"
                postcode = extract_postcode(title + " " + desc)
                incident = {
                    "type": incident_type,
                    "text": clean_text(title),
                    "location": location,
                    "postcode": postcode,
                    "time": parse_time(date_match.group(1) if date_match else None)
                }
                incidents.append(incident)

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

def extract_postcode(text: str) -> Optional[str]:
    """Extract Dutch postcode from text (format: 1234AB or 1234 AB)"""
    # Dutch postcode pattern: 4 digits + 2 letters (optional space)
    postcode_pattern = r'\b(\d{4}\s?[A-Z]{2})\b'
    match = re.search(postcode_pattern, text, re.IGNORECASE)
    if match:
        # Normalize: remove space, uppercase letters
        postcode = match.group(1).replace(' ', '').upper()
        return postcode
    return None

def extract_location(text: str) -> Optional[str]:
    """Try to extract location from text"""
    # Look for street patterns (more comprehensive)
    patterns = [
        r'([A-Z][a-z]+(?:straat|weg|laan|plein|kade|gracht|dijk|singel|park|hof|plantsoen|brug))',
        r'([A-Z][a-z]+(?:straat|weg|laan|plein|kade|gracht|dijk|singel|park|hof|plantsoen|brug)\s+\d+)',
        r'(\d+\s+[A-Z][a-z]+(?:straat|weg|laan|plein|kade|gracht|dijk|singel|park|hof|plantsoen|brug))',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    # Also check for known Amsterdam areas/districts
    amsterdam_areas = [
        "Centrum", "Jordaan", "De Pijp", "Oud-West", "Oud-Zuid", "Nieuw-West",
        "Noord", "Oost", "Zuidoost", "West", "Zuid", "Amstelveen", "Diemen"
    ]
    for area in amsterdam_areas:
        if area.lower() in text.lower():
            return area
    
    return None

async def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """Geocode an address to lat/lng using OpenStreetMap Nominatim"""
    if not address or address == "Amsterdam":
        return None
    
    # Check cache first
    if address in _geocoding_cache:
        return _geocoding_cache[address]
    
    try:
        # Add Amsterdam context for better results
        query = f"{address}, Amsterdam, Netherlands"
        
        # Use shorter timeout for faster failure
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "nl"
                },
                headers={
                    "User-Agent": "AmsterdamMonitor/1.0"  # Required by Nominatim
                },
                follow_redirects=True
            )
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    lat = float(data[0]["lat"])
                    lng = float(data[0]["lon"])
                    # Cache the result
                    _geocoding_cache[address] = (lat, lng)
                    return (lat, lng)
    except (httpx.TimeoutException, httpx.RequestError) as e:
        # Don't log timeout errors, just return None
        pass
    except Exception as e:
        print(f"Geocoding error for {address}: {e}")
    
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
