import json
import asyncio
import time
import os
import sys
import shutil
import re
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
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

# ANWB Traffic URL for Amsterdam region
ANWB_TRAFFIC_URL = "https://www.anwb.nl/verkeer/nederland/amsterdam"

# Road coordinates for major Amsterdam area highways (approximate center points)
# Used when ANWB doesn't provide exact coordinates
ROAD_COORDINATES = {
    "A1": {"lat": 52.3150, "lng": 5.0500},
    "A2": {"lat": 52.2800, "lng": 4.9600},
    "A4": {"lat": 52.2900, "lng": 4.7200},
    "A5": {"lat": 52.4000, "lng": 4.8000},
    "A6": {"lat": 52.4500, "lng": 5.2000},
    "A7": {"lat": 52.4700, "lng": 4.8200},
    "A8": {"lat": 52.4300, "lng": 4.8800},
    "A9": {"lat": 52.3800, "lng": 4.8400},
    "A10": {"lat": 52.3676, "lng": 4.9041},  # Ring Amsterdam
    "A27": {"lat": 52.2500, "lng": 5.1500},
    "A28": {"lat": 52.2000, "lng": 5.2500},
    "N201": {"lat": 52.2700, "lng": 4.8200},
    "N205": {"lat": 52.3900, "lng": 4.6500},
    "N232": {"lat": 52.3200, "lng": 4.7600},
    "N247": {"lat": 52.4500, "lng": 4.9500},
}


def get_chromedriver_path():
    """Get chromedriver path - prefer system install on Linux"""
    system_paths = [
        shutil.which("chromedriver"),
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
    ]
    for path in system_paths:
        if path and os.path.exists(path):
            return path

    if HAS_WEBDRIVER_MANAGER:
        try:
            return ChromeDriverManager().install()
        except Exception:
            pass

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


def extract_road_number(text: str) -> Optional[str]:
    """Extract road number (A10, N201, etc.) from text"""
    match = re.search(r'\b([AN]\d+)\b', text.upper())
    return match.group(1) if match else None


def get_coordinates_for_road(road: str, location_hint: str = "") -> Dict:
    """Get approximate coordinates for a road"""
    road_upper = road.upper() if road else ""

    # Try to find in our coordinate database
    if road_upper in ROAD_COORDINATES:
        coords = ROAD_COORDINATES[road_upper]
        return {"lat": coords["lat"], "lng": coords["lng"]}

    # Extract road number from location hint
    if location_hint:
        road_match = extract_road_number(location_hint)
        if road_match and road_match in ROAD_COORDINATES:
            coords = ROAD_COORDINATES[road_match]
            return {"lat": coords["lat"], "lng": coords["lng"]}

    # Default to Amsterdam center area
    return {"lat": 52.3676, "lng": 4.9041}


def parse_traffic_item(item_data: dict) -> Optional[Dict]:
    """Parse a traffic item from ANWB data"""
    try:
        road = item_data.get("road", "") or item_data.get("roadNumber", "") or ""
        location = item_data.get("location", "") or item_data.get("from", "") or ""
        to_location = item_data.get("to", "") or item_data.get("toLocation", "") or ""

        # Get delay/distance
        delay = item_data.get("delay", 0) or item_data.get("delayMinutes", 0) or 0
        distance = item_data.get("distance", 0) or item_data.get("length", 0) or 0

        # Convert distance to km if in meters
        if distance > 1000:
            distance = distance / 1000

        # Get type (file = jam, werk = roadwork, etc.)
        jam_type = item_data.get("type", "jam") or item_data.get("category", "jam") or "jam"

        # Get reason/description
        reason = item_data.get("reason", "") or item_data.get("description", "") or item_data.get("cause", "") or ""

        # Get coordinates if available
        lat = item_data.get("lat") or item_data.get("latitude")
        lng = item_data.get("lng") or item_data.get("lon") or item_data.get("longitude")

        # If no coordinates, estimate from road
        if not lat or not lng:
            coords = get_coordinates_for_road(road, location)
            lat = coords["lat"]
            lng = coords["lng"]

        # Build location string
        location_str = road
        if location:
            location_str += f" - {location}"
        if to_location:
            location_str += f" → {to_location}"

        # Determine severity based on delay
        if delay >= 30:
            severity = "severe"
        elif delay >= 15:
            severity = "moderate"
        elif delay >= 5:
            severity = "minor"
        else:
            severity = "info"

        return {
            "road": road,
            "location": location_str,
            "from_location": location,
            "to_location": to_location,
            "delay": int(delay),
            "distance": round(float(distance), 1),
            "type": jam_type,
            "reason": reason,
            "severity": severity,
            "lat": float(lat) if lat else None,
            "lng": float(lng) if lng else None,
        }
    except Exception as e:
        print(f"Error parsing traffic item: {e}")
        return None


async def scrape_anwb_traffic() -> List[Dict]:
    """Scrape traffic data from ANWB using Selenium"""
    def run_selenium():
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

        chromium_path = get_chromium_path()
        if chromium_path:
            options.binary_location = chromium_path

        # Enable performance logging to capture network requests
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        traffic_items = []
        driver = None

        try:
            driver_path = get_chromedriver_path()
            if driver_path:
                service = Service(driver_path)
            else:
                service = Service()
            driver = webdriver.Chrome(service=service, options=options)

            print("Opening ANWB traffic page...")
            driver.get(ANWB_TRAFFIC_URL)

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

            # Get performance logs to find network responses with traffic data
            logs = driver.get_log('performance')

            for log in logs:
                try:
                    message = json.loads(log['message'])['message']
                    method = message.get('method', '')

                    if method == 'Network.responseReceived':
                        params = message.get('params', {})
                        request_id = params.get('requestId')
                        response_url = params.get('response', {}).get('url', '')

                        # Look for traffic API endpoints
                        if any(x in response_url.lower() for x in ['traffic', 'verkeer', 'file', 'jam', 'hf']):
                            try:
                                body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                body_text = body.get('body', '')

                                if body_text:
                                    try:
                                        data = json.loads(body_text)

                                        # Handle different response structures
                                        items = []
                                        if isinstance(data, list):
                                            items = data
                                        elif isinstance(data, dict):
                                            # Try various keys
                                            items = (data.get('jams', []) or
                                                    data.get('files', []) or
                                                    data.get('traffic', []) or
                                                    data.get('items', []) or
                                                    data.get('roadEntries', []) or
                                                    data.get('incidents', []) or
                                                    [])

                                            # Also check for nested road entries
                                            if not items and 'roads' in data:
                                                for road in data['roads']:
                                                    if 'jams' in road:
                                                        items.extend(road['jams'])
                                                    if 'roadworks' in road:
                                                        items.extend(road['roadworks'])

                                        for item in items:
                                            if isinstance(item, dict):
                                                parsed = parse_traffic_item(item)
                                                if parsed:
                                                    traffic_items.append(parsed)
                                    except json.JSONDecodeError:
                                        pass
                            except Exception:
                                continue
                except Exception:
                    continue

            # If network interception didn't work, try parsing the page HTML
            if not traffic_items:
                print("Network interception found no data, trying HTML parsing...")
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')

                # Look for traffic jam elements
                jam_elements = soup.find_all(class_=re.compile(r'jam|file|traffic|incident', re.I))

                for elem in jam_elements[:50]:
                    text = elem.get_text(strip=True)

                    # Try to extract road number
                    road_match = extract_road_number(text)
                    if road_match:
                        # Try to extract delay
                        delay_match = re.search(r'(\d+)\s*(?:min|minuten)', text, re.I)
                        delay = int(delay_match.group(1)) if delay_match else 0

                        # Try to extract distance
                        dist_match = re.search(r'(\d+(?:[.,]\d+)?)\s*km', text, re.I)
                        distance = float(dist_match.group(1).replace(',', '.')) if dist_match else 0

                        coords = get_coordinates_for_road(road_match)

                        traffic_items.append({
                            "road": road_match,
                            "location": text[:100],
                            "from_location": "",
                            "to_location": "",
                            "delay": delay,
                            "distance": distance,
                            "type": "jam",
                            "reason": "",
                            "severity": "moderate" if delay >= 15 else "minor",
                            "lat": coords["lat"],
                            "lng": coords["lng"],
                        })

            # Deduplicate by road + location
            seen = set()
            unique_items = []
            for item in traffic_items:
                key = f"{item['road']}-{item.get('from_location', '')}"
                if key not in seen:
                    seen.add(key)
                    unique_items.append(item)

            print(f"Found {len(unique_items)} traffic items from ANWB")
            return unique_items

        except Exception as e:
            print(f"Selenium error scraping ANWB: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_selenium)


async def fetch_traffic() -> dict:
    """Fetch traffic data from ANWB."""
    traffic_items = []

    try:
        traffic_items = await scrape_anwb_traffic()
    except Exception as e:
        print(f"Error fetching traffic data: {e}")

    # Sort by severity (severe first) then by delay
    severity_order = {"severe": 0, "moderate": 1, "minor": 2, "info": 3}
    traffic_items.sort(key=lambda x: (severity_order.get(x.get("severity", "info"), 3), -x.get("delay", 0)))

    result = {
        "items": traffic_items[:30],  # Limit to top 30
        "total_jams": len(traffic_items),
        "total_delay": sum(item.get("delay", 0) for item in traffic_items),
        "updated_at": amsterdam_now().isoformat(),
        "updated": amsterdam_now().strftime("%H:%M:%S"),
    }

    cache.set("traffic", result, CACHE_TTL.get("traffic", 180))
    return result


async def get_traffic() -> dict:
    """Get traffic data from cache or fetch if needed."""
    cached = cache.get("traffic")
    if cached:
        return cached
    return await fetch_traffic()
