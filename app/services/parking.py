import httpx
import re
import json
import asyncio
import time
import os
import sys
import shutil
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.config import CACHE_TTL, amsterdam_now
from app.core.cache import cache

# Only import webdriver_manager on non-Linux (local dev)
if sys.platform != "linux":
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        HAS_WEBDRIVER_MANAGER = True
    except ImportError:
        HAS_WEBDRIVER_MANAGER = False
else:
    HAS_WEBDRIVER_MANAGER = False

# Amsterdam parking data sources
AMSTERDAM_MAPS_URL = "https://maps.amsterdam.nl/parkeergarages_bezetting/"

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


def get_chromedriver_path():
    """Get chromedriver path - prefer system install on Linux"""
    # Check for system chromedriver first (nixpacks/linux)
    system_paths = [
        shutil.which("chromedriver"),
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
    ]
    for path in system_paths:
        if path and os.path.exists(path):
            print(f"Using system chromedriver: {path}")
            return path

    # Fallback to webdriver_manager (local dev only, not on Linux)
    if HAS_WEBDRIVER_MANAGER:
        try:
            path = ChromeDriverManager().install()
            print(f"Using webdriver_manager chromedriver: {path}")
            return path
        except Exception as e:
            print(f"webdriver_manager failed: {e}")

    print("No chromedriver found!")
    return None


def get_chromium_path():
    """Get chromium binary path for Linux/nixpacks"""
    paths = [
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for path in paths:
        if path and os.path.exists(path):
            return path
    return None


async def scrape_with_selenium(url: str) -> List[Dict]:
    """Scrape parking data using Selenium with network interception"""
    def run_selenium():
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

        # Set chromium binary path for nixpacks/linux
        chromium_path = get_chromium_path()
        if chromium_path:
            print(f"Using chromium binary: {chromium_path}")
            options.binary_location = chromium_path

        # Enable performance logging to capture network requests
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        garages = []
        driver = None

        try:
            driver_path = get_chromedriver_path()
            if driver_path:
                service = Service(driver_path)
            else:
                service = Service()
            driver = webdriver.Chrome(service=service, options=options)

            print("Opening Amsterdam parking page...")
            driver.get(url)

            # Wait for page to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Wait for network activity to settle (instead of fixed sleep)
            last_log_count = 0
            stable_count = 0
            for _ in range(10):  # Max 5 seconds (10 * 0.5)
                logs = driver.get_log('performance')
                if len(logs) == last_log_count and last_log_count > 20:
                    stable_count += 1
                    if stable_count >= 2:  # Stable for 1 second
                        break
                else:
                    stable_count = 0
                last_log_count = len(logs)
                time.sleep(0.5)

            # Get performance logs to find network responses
            logs = driver.get_log('performance')

            # Look for parking data in ALL network responses (multiple layers)
            seen_names = set()
            for log in logs:
                try:
                    message = json.loads(log['message'])['message']
                    method = message.get('method', '')

                    if method == 'Network.responseReceived':
                        params = message.get('params', {})
                        request_id = params.get('requestId')
                        response_url = params.get('response', {}).get('url', '')

                        # Check if this is the WFS endpoint with parking data
                        if 'haal.objecten.wfs.php' in response_url or 'haal.objecten.php' in response_url:
                            try:
                                body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                body_text = body.get('body', '')

                                if body_text and 'FreeSpaceShort' in body_text:
                                    data = json.loads(body_text)
                                    if isinstance(data, list):
                                        for item in data:
                                            if isinstance(item, dict) and 'FreeSpaceShort' in item:
                                                garage = parse_maps_garage(item)
                                                if garage and garage['name'] not in seen_names:
                                                    garages.append(garage)
                                                    seen_names.add(garage['name'])
                            except Exception:
                                continue
                except Exception:
                    continue

            if garages:
                print(f"Found {len(garages)} parking garages from network")

            return garages

        except Exception as e:
            print(f"Selenium error: {e}")
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_selenium)


def parse_maps_garage(item: dict) -> Dict:
    """Parse garage data from Amsterdam Maps API response"""
    try:
        name = item.get('V') or item.get('L') or 'Unknown'
        free_spaces = item.get('FreeSpaceShort')
        capacity = item.get('ShortCapacity')

        if capacity and capacity > 0 and free_spaces is not None:
            occupied = capacity - free_spaces
            occupancy = int((occupied / capacity) * 100) if capacity > 0 else 0

            return {
                "name": name,
                "capacity": capacity,
                "free_spaces": free_spaces,
                "occupied": occupied,
                "occupancy": occupancy,
                "lat": item.get('T'),
                "lng": item.get('G')
            }
    except Exception as e:
        print(f"Error parsing garage: {e}")

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


async def fetch_parking_from_api() -> List[Dict]:
    """Try to fetch parking data from Amsterdam Open Data API"""
    garages = []
    
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Try the locations JSON endpoint first
            try:
                print(f"Trying: {AMSTERDAM_PARKING_LOCATIONS_URL}")
                response = await client.get(AMSTERDAM_PARKING_LOCATIONS_URL)
                print(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"JSON parsed successfully, type: {type(data)}")
                        
                        # Handle different JSON structures
                        if isinstance(data, list):
                            items = data
                            print(f"Found list with {len(items)} items")
                        elif isinstance(data, dict):
                            items = data.get('features', []) or data.get('results', []) or data.get('data', []) or data.get('parkeerlocaties', [])
                            print(f"Found dict with keys: {list(data.keys())[:10]}")
                        else:
                            items = []
                        
                        for item in items[:50]:  # Limit to first 50
                            garage = parse_api_garage(item)
                            if garage:
                                garages.append(garage)
                        
                        if garages:
                            print(f"Fetched {len(garages)} garages from Amsterdam Open Data API")
                            return garages
                        else:
                            print("No garages parsed from API data")
                            # Debug: show first item structure
                            if items:
                                print(f"First item structure: {items[0]}")
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                        print(f"Response preview: {response.text[:500]}")
            except Exception as e:
                print(f"Error fetching from locations API: {e}")
                import traceback
                traceback.print_exc()
            
            # Try the official API endpoint
            try:
                print(f"Trying: {AMSTERDAM_PARKING_API_URL}")
                response = await client.get(AMSTERDAM_PARKING_API_URL, headers={
                    'Accept': 'application/json'
                })
                print(f"API Response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if isinstance(data, dict):
                        items = data.get('results', []) or data.get('features', []) or data.get('data', [])
                    elif isinstance(data, list):
                        items = data
                    else:
                        items = []
                    
                    for item in items[:50]:
                        garage = parse_api_garage(item)
                        if garage:
                            garages.append(garage)
                    
                    if garages:
                        print(f"Fetched {len(garages)} garages from Amsterdam API")
                        return garages
            except Exception as e:
                print(f"Error fetching from API endpoint: {e}")
    
    except Exception as e:
        print(f"Error fetching parking from API: {e}")
        import traceback
        traceback.print_exc()
    
    return garages


def parse_api_garage(item: dict) -> Dict:
    """Parse garage data from API response"""
    try:
        # Handle GeoJSON format
        if 'properties' in item:
            props = item['properties']
            name = props.get('name') or props.get('title') or props.get('garage') or props.get('locatie') or 'Unknown'
            capacity = props.get('capacity') or props.get('total') or props.get('max_capacity') or props.get('aantal_plaatsen')
            free = props.get('free') or props.get('available') or props.get('free_spaces') or props.get('vacant') or props.get('vrij')
            # Also check for bezetting (occupancy) and calculate free spaces
            if not free and capacity:
                bezetting = props.get('bezetting') or props.get('occupied') or props.get('bezet')
                if bezetting is not None and capacity:
                    free = int(capacity) - int(bezetting)
        else:
            name = item.get('name') or item.get('title') or item.get('garage') or item.get('locatie') or 'Unknown'
            capacity = item.get('capacity') or item.get('total') or item.get('max_capacity') or item.get('aantal_plaatsen')
            free = item.get('free') or item.get('available') or item.get('free_spaces') or item.get('vacant') or item.get('vrij')
            # Also check for bezetting (occupancy) and calculate free spaces
            if not free and capacity:
                bezetting = item.get('bezetting') or item.get('occupied') or item.get('bezet')
                if bezetting is not None and capacity:
                    free = int(capacity) - int(bezetting)
        
        # Try to extract from description or other fields
        if not capacity or free is None:
            desc = item.get('description', '') or item.get('info', '') or item.get('omschrijving', '') or ''
            # Look for numbers in description
            numbers = re.findall(r'\d+', desc)
            if len(numbers) >= 2:
                if free is None:
                    free = int(numbers[0])
                if not capacity:
                    capacity = int(numbers[1])
        
        if capacity and free is not None:
            capacity = int(capacity)
            free = int(free)
            occupied = capacity - free
            occupancy = int((occupied / capacity) * 100) if capacity > 0 else 0
            
            return {
                "name": name[:50],
                "capacity": capacity,
                "free_spaces": free,
                "occupied": occupied,
                "occupancy": occupancy
            }
    except Exception as e:
        print(f"Error parsing garage: {e}")
        # Debug: print item structure
        if isinstance(item, dict):
            print(f"  Item keys: {list(item.keys())[:10]}")
    
    return None


async def fetch_parking() -> dict:
    """Fetch Amsterdam parking garage availability."""
    garages = []
    source = None

    # Use Selenium to scrape from Maps Amsterdam with network interception
    try:
        garages = await scrape_with_selenium(AMSTERDAM_MAPS_URL)
        if garages:
            print(f"Fetched {len(garages)} parking garages from Amsterdam Maps")
            source = "amsterdam_maps"
    except Exception as e:
        print(f"Error fetching parking data: {e}")

    result = {
        "garages": garages[:30],  # Limit to top 30
        "source": source,
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
