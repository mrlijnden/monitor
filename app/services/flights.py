"""Schiphol Flights Service - Scrapes flight data"""
import httpx
import re
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.config import amsterdam_now, CACHE_TTL
from app.core.cache import cache

# Schiphol URLs
SCHIPHOL_DEPARTURES_URL = "https://www.schiphol.nl/en/departures/"
SCHIPHOL_ARRIVALS_URL = "https://www.schiphol.nl/en/arrivals/"

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
    
    return flights[:15]  # Limit to 15 flights
    
    # Look for JSON data embedded in script tags
    # Schiphol often loads flight data via JavaScript/JSON
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
    
    # Also try to find flight data in HTML tables/divs
    # Look for common patterns: flight numbers, times, destinations
    flight_number_pattern = r'\b([A-Z]{2,3}\s*\d{2,4})\b'
    flight_numbers = re.findall(flight_number_pattern, html_content)
    
    # Look for time patterns near flight numbers
    time_pattern = r'(\d{1,2}):(\d{2})'
    times = re.findall(time_pattern, html_content)
    
    # Try to match flight numbers with times and destinations
    # This is a fallback if JSON parsing doesn't work
    if not flights and flight_numbers:
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


async def get_flights_data() -> Dict:
    """Get Schiphol flight data - tries API first, then HTML scraping"""
    departures = []
    arrivals = []
    
    # First try official Schiphol API (if credentials available)
    api_data = await fetch_schiphol_api()
    if api_data:
        return {
            "departures": api_data.get("departures", []),
            "arrivals": api_data.get("arrivals", []),
            "updated": amsterdam_now().strftime("%H:%M:%S"),
            "runway": None,
            "source": "api"
        }
    
    # Try HTML scraping with cloudscraper to bypass Cloudflare
    try:
        # Use cloudscraper (synchronous) - wrap in thread if needed for async
        import asyncio
        
        def scrape_schiphol_sync(url: str) -> str:
            """Synchronous scraping with cloudscraper"""
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            try:
                response = scraper.get(url, timeout=15)
                return response.text if response.status_code == 200 else ""
            except Exception as e:
                print(f"Cloudscraper error for {url}: {e}")
                return ""
        
        # Run scraping in executor to avoid blocking
        loop = asyncio.get_event_loop()
        
        # Try departures
        try:
            dep_html = await loop.run_in_executor(None, scrape_schiphol_sync, SCHIPHOL_DEPARTURES_URL)
            if dep_html:
                departures = parse_schiphol_html(dep_html, "departure")
                print(f"Scraped {len(departures)} departures from Schiphol")
        except Exception as e:
            print(f"Error scraping departures: {e}")
        
        # Try arrivals
        try:
            arr_html = await loop.run_in_executor(None, scrape_schiphol_sync, SCHIPHOL_ARRIVALS_URL)
            if arr_html:
                arrivals = parse_schiphol_html(arr_html, "arrival")
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
