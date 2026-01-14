"""Schiphol Flights Service - Scrapes flight data"""
import httpx
import re
import asyncio
import os
import sys
import shutil
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.config import amsterdam_now, CACHE_TTL
from app.core.cache import cache

# Try to import curl transport for better scraping
try:
    from httpx_curl_cffi import AsyncCurlTransport
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

# Only import webdriver_manager on non-Linux (local dev)
if sys.platform != "linux":
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        HAS_WEBDRIVER_MANAGER = True
    except ImportError:
        HAS_WEBDRIVER_MANAGER = False
else:
    HAS_WEBDRIVER_MANAGER = False

# Schiphol URLs
SCHIPHOL_DEPARTURES_URL = "https://www.schiphol.nl/en/departures/"
SCHIPHOL_ARRIVALS_URL = "https://www.schiphol.nl/en/arrivals/"

# Flightradar24 URLs
FLIGHTRADAR24_AMS_URL = "https://www.flightradar24.com/data/airports/ams"

# Schiphol Flight API (requires API keys - set in environment)
SCHIPHOL_API_URL = "https://api.schiphol.nl/public-flights/flights"
SCHIPHOL_APP_ID = None  # Set via SCHIPHOL_APP_ID env var
SCHIPHOL_APP_KEY = None  # Set via SCHIPHOL_APP_KEY env var

# Common airlines and airport codes
AIRLINES = ["KLM", "Transavia", "EasyJet", "Vueling", "British Airways", "Air France", "Lufthansa"]

def parse_schiphol_html(html_content: str, flight_type: str = "departure") -> List[Dict]:
    """Parse Schiphol HTML page for flight data using BeautifulSoup"""
    flights = []
    
    if not html_content:
        return flights
    
    # Check for Cloudflare challenge
    if "Just a moment" in html_content or "challenge-platform" in html_content or "cf-browser-verification" in html_content:
        print("Schiphol: Cloudflare protection detected")
        return flights
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for flight data in various possible structures
        # Schiphol might use data attributes, classes, or IDs
        
        # Try to find flight rows/items
        flight_elements = soup.find_all(['tr', 'div', 'li'], class_=re.compile(r'flight|departure|arrival', re.I))
        
        if not flight_elements:
            # Try data attributes
            flight_elements = soup.find_all(attrs={'data-flight': True})
        
        if not flight_elements:
            # Try finding tables with flight data
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                flight_elements.extend(rows)
        
        for element in flight_elements[:30]:  # Limit to 30
            try:
                text = element.get_text()
                
                # Extract flight number (e.g., KL1234, EZY1234)
                flight_match = re.search(r'\b([A-Z]{2,3})\s*(\d{2,4})\b', text)
                if not flight_match:
                    continue
                
                airline_code = flight_match.group(1)
                flight_num = flight_match.group(2)
                flight_code = f"{airline_code}{flight_num}"
                
                # Extract time (HH:MM format)
                time_match = re.search(r'(\d{1,2}):(\d{2})', text)
                if not time_match:
                    continue
                time_str = time_match.group(0)
                
                # Extract destination (look for city names or airport codes)
                destination = "Unknown"
                
                # Look for destination in various ways
                dest_elem = element.find(class_=re.compile(r'destination|city|airport', re.I))
                if dest_elem:
                    destination = dest_elem.get_text().strip()
                else:
                    # Try to find airport codes (3 letters)
                    airport_match = re.search(r'\b([A-Z]{3})\b', text)
                    if airport_match and airport_match.group(1) not in ['NOW', 'GATE', 'TER']:
                        destination = airport_match.group(1)
                    else:
                        # Look for common destination patterns
                        dest_patterns = [
                            r'to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                            r'→\s*([A-Z][a-z]+)',
                            r'([A-Z][a-z]+\s+(?:Airport|International))',
                        ]
                        for pattern in dest_patterns:
                            dest_match = re.search(pattern, text)
                            if dest_match:
                                destination = dest_match.group(1).strip()
                                break
                
                # Extract status
                status = "on-time"
                text_lower = text.lower()
                if "delayed" in text_lower or "delay" in text_lower:
                    status = "delayed"
                    # Try to extract delay minutes
                    delay_match = re.search(r'(\d+)\s*(?:min|minutes?)\s*(?:delay|late)', text_lower)
                    if delay_match:
                        delay = int(delay_match.group(1))
                    else:
                        delay = None
                elif "boarding" in text_lower:
                    status = "boarding"
                    delay = None
                elif "departed" in text_lower or "left" in text_lower:
                    status = "departed"
                    delay = None
                elif "cancelled" in text_lower or "canceled" in text_lower:
                    status = "cancelled"
                    delay = None
                else:
                    delay = None
                
                # Extract gate
                gate = None
                gate_elem = element.find(class_=re.compile(r'gate', re.I))
                if gate_elem:
                    gate_text = gate_elem.get_text()
                    gate_match = re.search(r'([A-Z]\d+)', gate_text)
                    if gate_match:
                        gate = gate_match.group(1)
                else:
                    gate_match = re.search(r'gate\s*:?\s*([A-Z]\d+)', text_lower)
                    if gate_match:
                        gate = gate_match.group(1).upper()
                
                # Extract terminal
                terminal = None
                term_elem = element.find(class_=re.compile(r'terminal', re.I))
                if term_elem:
                    term_text = term_elem.get_text()
                    term_match = re.search(r'(\d+)', term_text)
                    if term_match:
                        terminal = int(term_match.group(1))
                
                flights.append({
                    "code": flight_code,
                    "airline": airline_code,
                    "destination": destination,
                    "time": time_str,
                    "status": status,
                    "delay": delay,
                    "gate": gate,
                    "terminal": terminal
                })
            except Exception as e:
                continue
    
    except Exception as e:
        print(f"Error parsing Schiphol HTML: {e}")
    
    # If we already found flights, return early
    if flights:
        return flights[:15]
    
    # Look for JSON data embedded in script tags
    # Schiphol often loads flight data via JavaScript/JSON
    try:
        script_pattern = r'<script[^>]*>(.*?)</script>'
        scripts = re.findall(script_pattern, html_content, re.DOTALL | re.IGNORECASE)
        
        for script in scripts:
            # Look for flight data in JSON format
            if "flight" in script.lower() or "departure" in script.lower() or "arrival" in script.lower():
                # Try to extract JSON objects
                json_patterns = [
                    r'\{[^{}]*"flightNumber"[^{}]*\}',
                    r'\{[^{}]*"destination"[^{}]*\}',
                    r'flights\s*[:=]\s*\[(.*?)\]',
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, script, re.DOTALL | re.IGNORECASE)
                    for match in matches[:20]:
                        try:
                            import json
                            # Try to parse as JSON
                            if match.strip().startswith('{'):
                                data = json.loads(match)
                                # Extract flight info
                                flight_code = data.get("flightNumber") or data.get("flight")
                                if flight_code:
                                    flights.append({
                                        "code": str(flight_code),
                                        "airline": str(flight_code)[:2] if len(str(flight_code)) >= 2 else "Unknown",
                                        "destination": data.get("destination", {}).get("city", "") if isinstance(data.get("destination"), dict) else data.get("destination", "Unknown"),
                                        "time": data.get("time", ""),
                                        "status": data.get("status", "on-time"),
                                        "delay": data.get("delay"),
                                        "gate": data.get("gate"),
                                        "terminal": data.get("terminal")
                                    })
                        except:
                            continue
    except Exception as e:
        print(f"Error parsing JSON from scripts: {e}")
    
    # Also try to find flight data in HTML tables/divs
    # Look for common patterns: flight numbers, times, destinations
    if not flights:
        try:
            flight_number_pattern = r'\b([A-Z]{2,3}\s*\d{2,4})\b'
            flight_numbers = re.findall(flight_number_pattern, html_content)
            
            # Look for time patterns near flight numbers
            time_pattern = r'(\d{1,2}):(\d{2})'
            
            # Extract structured data from HTML
            # Look for flight rows/items
            flight_item_patterns = [
                r'<div[^>]*class="[^"]*flight[^"]*"[^>]*>(.*?)</div>',
                r'<tr[^>]*>(.*?)</tr>',
                r'<li[^>]*data-flight[^>]*>(.*?)</li>',
            ]
            
            for pattern in flight_item_patterns:
                items = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
                for item in items[:20]:
                    # Extract flight number
                    fn_match = re.search(flight_number_pattern, item)
                    if not fn_match:
                        continue
                    
                    flight_code = fn_match.group(1).strip()
                    
                    # Extract time
                    time_match = re.search(time_pattern, item)
                    time_str = time_match.group(0) if time_match else None
                    
                    # Extract destination (look for city names or airport codes)
                    dest_patterns = [
                        r'<span[^>]*class="[^"]*destination[^"]*"[^>]*>(.*?)</span>',
                        r'<td[^>]*class="[^"]*destination[^"]*"[^>]*>(.*?)</td>',
                        r'\b([A-Z]{3})\b',  # Airport code
                    ]
                    
                    destination = "Unknown"
                    for dp in dest_patterns:
                        dest_match = re.search(dp, item, re.IGNORECASE)
                        if dest_match:
                            destination = re.sub(r'<[^>]+>', '', dest_match.group(1)).strip()
                            if len(destination) > 2:
                                break
                    
                    # Extract status
                    status = "on-time"
                    item_lower = item.lower()
                    if "delayed" in item_lower or "delay" in item_lower:
                        status = "delayed"
                    elif "boarding" in item_lower:
                        status = "boarding"
                    elif "departed" in item_lower or "left" in item_lower:
                        status = "departed"
                    elif "cancelled" in item_lower or "canceled" in item_lower:
                        status = "cancelled"
                    
                    if flight_code and time_str:
                        flights.append({
                            "code": flight_code.replace(" ", ""),
                            "airline": flight_code[:2] if len(flight_code) >= 2 else "Unknown",
                            "destination": destination,
                            "time": time_str,
                            "status": status,
                            "delay": None,
                            "gate": None,
                            "terminal": None
                        })
                
                if flights:
                    break
        except Exception as e:
            print(f"Error parsing HTML fallback: {e}")
    
    return flights[:15]  # Limit to 15 flights


async def fetch_schiphol_api() -> Optional[Dict]:
    """Fetch flights from Schiphol Flight API (requires API keys)"""
    import os
    
    app_id = os.getenv("SCHIPHOL_APP_ID")
    app_key = os.getenv("SCHIPHOL_APP_KEY")
    
    if not app_id or not app_key:
        return None
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Fetch departures
            dep_response = await client.get(
                SCHIPHOL_API_URL,
                headers={
                    "app_id": app_id,
                    "app_key": app_key,
                    "ResourceVersion": "v4",
                    "Accept": "application/json"
                },
                params={
                    "flightDirection": "D",
                    "includedelays": "true",
                    "page": 0,
                    "sort": "+scheduleTime"
                }
            )
            
            arr_response = await client.get(
                SCHIPHOL_API_URL,
                headers={
                    "app_id": app_id,
                    "app_key": app_key,
                    "ResourceVersion": "v4",
                    "Accept": "application/json"
                },
                params={
                    "flightDirection": "A",
                    "includedelays": "true",
                    "page": 0,
                    "sort": "+scheduleTime"
                }
            )
            
            departures = []
            arrivals = []
            
            if dep_response.status_code == 200:
                dep_data = dep_response.json()
                for flight in dep_data.get("flights", [])[:15]:
                    schedule_time = flight.get("scheduleTime", "")
                    now = amsterdam_now()
                    # Parse time and calculate minutes until departure
                    try:
                        flight_time = datetime.fromisoformat(schedule_time.replace("Z", "+00:00"))
                        ams_time = flight_time.astimezone(now.tzinfo)
                        minutes = int((ams_time - now).total_seconds() / 60)
                        
                        if 0 <= minutes <= 180:  # Next 3 hours
                            departures.append({
                                "code": flight.get("flightNumber", {}).get("publicFlightNumber", ""),
                                "airline": flight.get("flightNumber", {}).get("airline", {}).get("code", ""),
                                "destination": flight.get("route", {}).get("destinations", [""])[0] if flight.get("route", {}).get("destinations") else "Unknown",
                                "time": ams_time.strftime("%H:%M"),
                                "status": flight.get("flightStatus", "on-time"),
                                "delay": flight.get("scheduleTime", {}).get("delay", 0),
                                "gate": flight.get("gate", ""),
                                "terminal": flight.get("terminal", "")
                            })
                    except:
                        continue
            
            if arr_response.status_code == 200:
                arr_data = arr_response.json()
                for flight in arr_data.get("flights", [])[:15]:
                    schedule_time = flight.get("scheduleTime", "")
                    now = amsterdam_now()
                    try:
                        flight_time = datetime.fromisoformat(schedule_time.replace("Z", "+00:00"))
                        ams_time = flight_time.astimezone(now.tzinfo)
                        minutes = int((ams_time - now).total_seconds() / 60)
                        
                        if -30 <= minutes <= 180:  # Past 30 min to next 3 hours
                            arrivals.append({
                                "code": flight.get("flightNumber", {}).get("publicFlightNumber", ""),
                                "airline": flight.get("flightNumber", {}).get("airline", {}).get("code", ""),
                                "origin": flight.get("route", {}).get("destinations", [""])[0] if flight.get("route", {}).get("destinations") else "Unknown",
                                "time": ams_time.strftime("%H:%M"),
                                "status": flight.get("flightStatus", "on-time"),
                                "delay": flight.get("scheduleTime", {}).get("delay", 0),
                                "gate": flight.get("gate", ""),
                                "terminal": flight.get("terminal", "")
                            })
                    except:
                        continue
            
            if departures or arrivals:
                return {
                    "departures": departures,
                    "arrivals": arrivals
                }
    except Exception as e:
        print(f"Schiphol API error: {e}")
    
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


async def scrape_flightradar24_with_selenium() -> str:
    """Scrape Flightradar24 page using Selenium for JavaScript rendering"""
    def run_selenium():
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # Set chromium binary path for nixpacks/linux
        chromium_path = get_chromium_path()
        if chromium_path:
            print(f"Using chromium binary: {chromium_path}")
            options.binary_location = chromium_path

        try:
            driver_path = get_chromedriver_path()
            if driver_path:
                service = Service(driver_path)
            else:
                service = Service()
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(FLIGHTRADAR24_AMS_URL)
            
            # Wait for page to load
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                # Wait for flight tables to load
                import time
                time.sleep(5)  # Give JavaScript time to load flight data
            except:
                pass
            
            html_content = driver.page_source
            driver.quit()
            return html_content
        except Exception as e:
            print(f"Selenium error for Flightradar24: {e}")
            try:
                driver.quit()
            except:
                pass
            return ""
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_selenium)


def parse_flightradar24_html(html_content: str) -> Dict:
    """Parse Flightradar24 airport page for arrivals and departures"""
    departures = []
    arrivals = []
    
    if not html_content:
        return {"departures": departures, "arrivals": arrivals}
    
    # Check for Cloudflare challenge
    if "Just a moment" in html_content or "challenge-platform" in html_content:
        print("Flightradar24: Cloudflare protection detected")
        return {"departures": departures, "arrivals": arrivals}
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Flightradar24 uses tables for flight data
        # Look for tables with flight information
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if not rows:
                continue
            
            # Check if this is arrivals or departures table
            # Look for headers or context
            table_text = table.get_text().lower()
            is_arrivals = 'arrival' in table_text or 'from' in table_text
            is_departures = 'departure' in table_text or 'to' in table_text
            
            for row in rows[1:]:  # Skip header row
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:
                    continue
                
                try:
                    # Extract flight data from cells
                    # Format: TIME | FLIGHT | FROM/TO | AIRLINE | AIRCRAFT | STATUS
                    flight_text = ' '.join([cell.get_text(strip=True) for cell in cells])
                    
                    # Extract flight number (e.g., KL1234, EZY567)
                    flight_match = re.search(r'\b([A-Z]{2,3}\s*\d{2,4})\b', flight_text)
                    if not flight_match:
                        continue
                    
                    flight_code = flight_match.group(1).replace(' ', '')
                    
                    # Extract time (HH:MM format)
                    time_match = re.search(r'(\d{1,2}):(\d{2})', flight_text)
                    time_str = time_match.group(0) if time_match else None
                    
                    # Extract destination/origin (airport code or city)
                    airport_match = re.search(r'\b([A-Z]{3})\b', flight_text)
                    destination = airport_match.group(1) if airport_match else "Unknown"
                    
                    # Extract status
                    status = "on-time"
                    if "delayed" in flight_text.lower() or "delay" in flight_text.lower():
                        status = "delayed"
                        delay_match = re.search(r'(\d+)\s*(?:min|minutes?)', flight_text.lower())
                        delay = int(delay_match.group(1)) if delay_match else None
                    elif "boarding" in flight_text.lower():
                        status = "boarding"
                        delay = None
                    elif "departed" in flight_text.lower() or "left" in flight_text.lower():
                        status = "departed"
                        delay = None
                    elif "landed" in flight_text.lower() or "arrived" in flight_text.lower():
                        status = "arrived"
                        delay = None
                    elif "cancelled" in flight_text.lower() or "canceled" in flight_text.lower():
                        status = "cancelled"
                        delay = None
                    else:
                        delay = None
                    
                    flight_data = {
                        "code": flight_code,
                        "airline": flight_code[:2] if len(flight_code) >= 2 else "Unknown",
                        "destination" if is_departures else "origin": destination,
                        "time": time_str or amsterdam_now().strftime("%H:%M"),
                        "status": status,
                        "delay": delay,
                        "gate": None,
                        "terminal": None
                    }
                    
                    if is_arrivals:
                        arrivals.append(flight_data)
                    elif is_departures:
                        departures.append(flight_data)
                        
                except Exception as e:
                    continue
        
        # Also try to find JSON data in script tags (Flightradar24 loads data via JS)
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.string or ""
            # Look for flight data in JSON format
            if 'flight' in script_text.lower() and ('arrival' in script_text.lower() or 'departure' in script_text.lower()):
                # Try to extract JSON arrays
                json_patterns = [
                    r'arrivals\s*[:=]\s*\[(.*?)\]',
                    r'departures\s*[:=]\s*\[(.*?)\]',
                    r'flights\s*[:=]\s*\[(.*?)\]',
                ]
                for pattern in json_patterns:
                    matches = re.findall(pattern, script_text, re.DOTALL | re.IGNORECASE)
                    # Could parse JSON here if found
                    break
    
    except Exception as e:
        print(f"Error parsing Flightradar24 HTML: {e}")
    
    return {"departures": departures[:15], "arrivals": arrivals[:15]}


async def get_flights_data() -> Dict:
    """Get Schiphol flight data - tries Flightradar24 first, then Schiphol API/scraping"""
    departures = []
    arrivals = []
    
    # First try Flightradar24 scraping with Selenium (JavaScript-heavy page)
    try:
        fr24_html = await scrape_flightradar24_with_selenium()
        
        if fr24_html:
            fr24_data = parse_flightradar24_html(fr24_html)
            departures = fr24_data.get("departures", [])
            arrivals = fr24_data.get("arrivals", [])
            
            if departures or arrivals:
                print(f"Scraped {len(departures)} departures and {len(arrivals)} arrivals from Flightradar24")
                result = {
                    "departures": departures,
                    "arrivals": arrivals,
                    "updated": amsterdam_now().strftime("%H:%M:%S"),
                    "runway": None,
                    "source": "flightradar24"
                }
                cache.set("flights", result, CACHE_TTL.get("flights", 120))
                return result
    except Exception as e:
        print(f"Error scraping Flightradar24: {e}")
    
    # Fallback: Try official Schiphol API (if credentials available)
    api_data = await fetch_schiphol_api()
    if api_data:
        return {
            "departures": api_data.get("departures", []),
            "arrivals": api_data.get("arrivals", []),
            "updated": amsterdam_now().strftime("%H:%M:%S"),
            "runway": None,
            "source": "api"
        }
    
    # Last resort: Try Schiphol HTML scraping
    try:
        async with httpx.AsyncClient(
            transport=AsyncCurlTransport(impersonate="chrome110"),
            timeout=15.0
        ) as client:
            # Try departures
            try:
                dep_response = await client.get(
                    SCHIPHOL_DEPARTURES_URL,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                if dep_response.status_code == 200:
                    departures = parse_schiphol_html(dep_response.text, "departure")
                    print(f"Scraped {len(departures)} departures from Schiphol")
            except Exception as e:
                print(f"Error scraping departures: {e}")
            
            # Try arrivals
            try:
                arr_response = await client.get(
                    SCHIPHOL_ARRIVALS_URL,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                if arr_response.status_code == 200:
                    arrivals = parse_schiphol_html(arr_response.text, "arrival")
                    print(f"Scraped {len(arrivals)} arrivals from Schiphol")
            except Exception as e:
                print(f"Error scraping arrivals: {e}")
    
    except Exception as e:
        print(f"Error fetching flight data: {e}")
    
    result = {
        "departures": departures[:12],
        "arrivals": arrivals[:12],
        "updated": amsterdam_now().strftime("%H:%M:%S"),
        "runway": None,
        "source": "scraping" if departures or arrivals else "none"
    }
    
    # Cache the result
    cache.set("flights", result, CACHE_TTL.get("flights", 120))
    return result


async def fetch_flights() -> Dict:
    """Fetch flights data (for scheduler)"""
    return await get_flights_data()


async def get_flights() -> Dict:
    """Get flights from cache or fetch if needed."""
    cached = cache.get("flights")
    if cached:
        return cached
    return await get_flights_data()

async def get_flight_status(flight_code: str) -> Dict:
    """Get status for a specific flight"""
    # TODO: Implement real Schiphol API query
    return {
        "code": flight_code,
        "status": "unknown",
        "updated": amsterdam_now().strftime("%H:%M:%S")
    }
