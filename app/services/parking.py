import httpx
import re
import json
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
from app.config import CACHE_TTL, amsterdam_now
from app.core.cache import cache

# Amsterdam Maps parking garages URL
AMSTERDAM_PARKING_URL = "https://maps.amsterdam.nl/parkeergarages_bezetting/"

def parse_parking_html(html_content: str) -> List[Dict]:
    """Parse Amsterdam Maps parking page for garage availability"""
    garages = []
    
    if not html_content:
        return garages
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Amsterdam Maps loads data via JavaScript/JSON
        # Look for JSON data in script tags
        scripts = soup.find_all('script')
        
        for script in scripts:
            script_text = script.string or ""
            
            # Look for parking garage data in various JSON formats
            # Try to find arrays or objects with parking data
            json_patterns = [
                r'garages\s*[:=]\s*\[(.*?)\]',
                r'parking\s*[:=]\s*\[(.*?)\]',
                r'data\s*[:=]\s*\[(.*?)\]',
                r'features\s*[:=]\s*\[(.*?)\]',  # GeoJSON format
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, script_text, re.DOTALL | re.IGNORECASE)
                for match in matches[:50]:  # Limit matches
                    try:
                        # Try to parse as JSON array
                        json_str = '[' + match + ']'
                        data = json.loads(json_str)
                        
                        for item in data:
                            if isinstance(item, dict):
                                garage = parse_garage_data(item)
                                if garage:
                                    garages.append(garage)
                    except:
                        continue
            
            # Also try to find GeoJSON format
            if 'geojson' in script_text.lower() or 'features' in script_text.lower():
                try:
                    # Look for complete JSON objects
                    json_match = re.search(r'\{[^{}]*"type"[^{}]*"FeatureCollection"[^{}]*"features"[^{}]*\[(.*?)\][^{}]*\}', script_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        geojson_data = json.loads(json_str)
                        
                        if 'features' in geojson_data:
                            for feature in geojson_data['features']:
                                garage = parse_geojson_feature(feature)
                                if garage:
                                    garages.append(garage)
                except:
                    pass
        
        # Also try to find data in HTML attributes or data-* attributes
        # Look for elements with parking data
        parking_elements = soup.find_all(attrs={'data-garage': True}) or \
                          soup.find_all(attrs={'data-parking': True}) or \
                          soup.find_all(class_=re.compile(r'garage|parking', re.I))
        
        for elem in parking_elements[:30]:
            garage = parse_html_element(elem)
            if garage:
                garages.append(garage)
    
    except Exception as e:
        print(f"Error parsing parking HTML: {e}")
    
    return garages


def parse_garage_data(data: dict) -> Dict:
    """Parse garage data from JSON object"""
    try:
        name = data.get('name') or data.get('title') or data.get('garage') or 'Unknown'
        
        # Try different field names for capacity and free spaces
        capacity = None
        free_spaces = None
        
        if 'capacity' in data:
            capacity = int(data['capacity'])
        elif 'total' in data:
            capacity = int(data['total'])
        elif 'max' in data:
            capacity = int(data['max'])
        
        if 'free' in data:
            free_spaces = int(data['free'])
        elif 'available' in data:
            free_spaces = int(data['available'])
        elif 'free_spaces' in data:
            free_spaces = int(data['free_spaces'])
        elif 'vacant' in data:
            free_spaces = int(data['vacant'])
        
        # Calculate occupancy if we have both
        if capacity and free_spaces is not None:
            occupied = capacity - free_spaces
            occupancy = int((occupied / capacity) * 100) if capacity > 0 else 0
            
            return {
                "name": name,
                "capacity": capacity,
                "free_spaces": free_spaces,
                "occupied": occupied,
                "occupancy": occupancy
            }
    except:
        pass
    
    return None


def parse_geojson_feature(feature: dict) -> Dict:
    """Parse GeoJSON feature for parking garage"""
    try:
        properties = feature.get('properties', {})
        return parse_garage_data(properties)
    except:
        return None


def parse_html_element(elem) -> Dict:
    """Parse parking data from HTML element"""
    try:
        name = elem.get('data-garage') or elem.get('data-parking') or elem.get_text(strip=True)
        if not name or len(name) < 3:
            return None
        
        # Try to extract numbers from text
        text = elem.get_text()
        numbers = re.findall(r'\d+', text)
        
        if len(numbers) >= 2:
            free_spaces = int(numbers[0])
            capacity = int(numbers[1])
            occupied = capacity - free_spaces
            occupancy = int((occupied / capacity) * 100) if capacity > 0 else 0
            
            return {
                "name": name[:30],
                "capacity": capacity,
                "free_spaces": free_spaces,
                "occupied": occupied,
                "occupancy": occupancy
            }
    except:
        pass
    
    return None


async def fetch_parking() -> dict:
    """Fetch Amsterdam parking garage availability from Maps Amsterdam."""
    garages = []
    
    try:
        import asyncio
        
        def scrape_parking_sync(url: str) -> str:
            """Synchronous scraping with cloudscraper"""
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                },
                delay=10
            )
            try:
                response = scraper.get(url, timeout=20, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                })
                return response.text if response.status_code == 200 else ""
            except Exception as e:
                print(f"Cloudscraper error for parking: {e}")
                return ""
        
        loop = asyncio.get_event_loop()
        html_content = await loop.run_in_executor(None, scrape_parking_sync, AMSTERDAM_PARKING_URL)
        
        if html_content:
            garages = parse_parking_html(html_content)
            print(f"Scraped {len(garages)} parking garages from Amsterdam Maps")
    
    except Exception as e:
        print(f"Error fetching parking data: {e}")
    
    result = {
        "garages": garages[:20],  # Limit to top 20
        "source": "amsterdam_maps" if garages else None,
        "updated_at": amsterdam_now().isoformat(),
        "updated": amsterdam_now().strftime("%H:%M:%S"),
    }

    cache.set("parking", result, CACHE_TTL.get("parking", 300))
    return result


async def get_parking() -> dict:
    """Get parking data from cache or fetch if needed."""
    cached = cache.get("parking")
    if cached:
        return cached
    return await fetch_parking()
