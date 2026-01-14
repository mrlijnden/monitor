#!/usr/bin/env python3
"""Quick script to check which services return real data"""
import asyncio
import httpx
import feedparser
from datetime import datetime

async def check_services():
    print("=== Checking Data Sources ===\n")
    
    # 1. Weather
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": 52.3676, "longitude": 4.9041,
                "current": "temperature_2m", "forecast_days": 1
            })
            if r.status_code == 200:
                data = r.json()
                temp = data.get("current", {}).get("temperature_2m")
                print(f"✅ Weather: REAL DATA - Temp: {temp}°C")
            else:
                print(f"❌ Weather: API error {r.status_code}")
    except Exception as e:
        print(f"❌ Weather: ERROR - {e}")
    
    # 2. News
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://feeds.nos.nl/nosnieuwsalgemeen", timeout=10)
            if r.status_code == 200:
                feed = feedparser.parse(r.text)
                articles = len(feed.entries)
                print(f"✅ News: REAL DATA - {articles} articles")
            else:
                print(f"❌ News: API error {r.status_code}")
    except Exception as e:
        print(f"❌ News: ERROR - {e}")
    
    # 3. Transit (OVapi)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("http://v0.ovapi.nl/stopareacode/AmsCS", timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Check if we have any departures
                has_data = False
                for stop_area in data.values():
                    if isinstance(stop_area, dict):
                        for tp in stop_area.values():
                            if isinstance(tp, dict) and tp.get("Passes"):
                                has_data = True
                                break
                if has_data:
                    print(f"✅ Transit: REAL DATA - Departures available")
                else:
                    print(f"⚠️  Transit: API works but no departures found")
            else:
                print(f"❌ Transit: API error {r.status_code}")
    except Exception as e:
        print(f"❌ Transit: ERROR - {e}")
    
    # 4. Air Quality
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
                "latitude": 52.3676, "longitude": 4.9041,
                "current": "european_aqi"
            })
            if r.status_code == 200:
                data = r.json()
                aqi = data.get("current", {}).get("european_aqi")
                print(f"✅ Air Quality: REAL DATA - AQI: {aqi}")
            else:
                print(f"❌ Air Quality: API error {r.status_code}")
    except Exception as e:
        print(f"❌ Air Quality: ERROR - {e}")
    
    # 5. Markets
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.coingecko.com/api/v3/simple/price", params={
                "ids": "bitcoin,ethereum", "vs_currencies": "eur"
            })
            if r.status_code == 200:
                data = r.json()
                btc = data.get("bitcoin", {}).get("eur")
                print(f"✅ Markets: REAL DATA - BTC: €{btc}")
            else:
                print(f"❌ Markets: API error {r.status_code}")
    except Exception as e:
        print(f"❌ Markets: ERROR - {e}")
    
    # 6. P2000 Feed
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://feeds.p2000-online.net/p2000.xml", timeout=10)
            if r.status_code == 200:
                content = r.text
                if "<rss" in content.lower() or "<feed" in content.lower() or "<item>" in content:
                    items = content.count("<item>")
                    print(f"✅ P2000: REAL DATA - {items} items in feed")
                else:
                    print(f"⚠️  P2000: Feed returns HTML (not XML)")
            else:
                print(f"❌ P2000: API error {r.status_code}")
    except Exception as e:
        print(f"❌ P2000: ERROR - {e}")
    
    # 7. OVapi Vehicle Positions
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://v0.ovapi.nl/vehicle", timeout=10)
            if r.status_code == 200:
                data = r.json()
                vehicle_count = len(data) if isinstance(data, dict) else 0
                if vehicle_count > 0:
                    print(f"✅ Map Vehicles: REAL DATA - {vehicle_count} vehicles")
                else:
                    print(f"⚠️  Map Vehicles: API works but no vehicles")
            else:
                print(f"❌ Map Vehicles: API error {r.status_code}")
    except Exception as e:
        print(f"❌ Map Vehicles: ERROR - {e}")
    
    # 8. Flights (Schiphol)
    print(f"⚠️  Flights: NO API - Would need scraping")
    
    # 9. Parking
    print(f"⚠️  Parking: NO API - Deprecated API")
    
    # 10. Events
    print(f"⚠️  Events: Requires TICKETMASTER_API_KEY")

if __name__ == "__main__":
    asyncio.run(check_services())
