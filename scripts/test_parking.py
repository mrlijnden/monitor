#!/usr/bin/env python3
"""Test script for Amsterdam parking data - using Selenium to capture network requests"""
import asyncio
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def get_parking_with_selenium():
    """Use Selenium with network logging to find the parking API"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

    # Enable performance logging to capture network requests
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        print("Opening Amsterdam parking page...")
        driver.get("https://maps.amsterdam.nl/parkeergarages_bezetting/")

        # Wait for page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Wait for JavaScript to load data
        print("Waiting for data to load...")
        time.sleep(5)

        # Get performance logs
        logs = driver.get_log('performance')

        print(f"\nFound {len(logs)} network events")
        print("\n" + "="*60)
        print("Looking for parking data requests...")
        print("="*60)

        parking_data = None
        api_url = None

        for log in logs:
            try:
                message = json.loads(log['message'])['message']
                method = message.get('method', '')

                # Look for network responses
                if method == 'Network.responseReceived':
                    url = message.get('params', {}).get('response', {}).get('url', '')
                    mime = message.get('params', {}).get('response', {}).get('mimeType', '')

                    if 'haal' in url or 'parking' in url.lower() or 'wfs' in url:
                        print(f"\nFound: {url}")
                        print(f"  MIME: {mime}")
                        api_url = url

                # Look for received data
                if method == 'Network.responseReceivedExtraInfo':
                    pass

            except Exception as e:
                continue

        # Try to get the page's JavaScript variables
        print("\n" + "="*60)
        print("Checking JavaScript variables...")
        print("="*60)

        try:
            # Try to execute JS to get data
            result = driver.execute_script("""
                // Look for parking data in various global variables
                var data = null;

                // Try common patterns
                if (typeof deObjecten !== 'undefined') {
                    return JSON.stringify({source: 'deObjecten', data: deObjecten});
                }
                if (typeof parkingData !== 'undefined') {
                    return JSON.stringify({source: 'parkingData', data: parkingData});
                }

                // Try to find Leaflet layers with parking data
                if (typeof deKaart !== 'undefined' && deKaart._layers) {
                    var layers = [];
                    for (var key in deKaart._layers) {
                        var layer = deKaart._layers[key];
                        if (layer.feature || layer._popup) {
                            layers.push({
                                id: key,
                                hasFeature: !!layer.feature,
                                hasPopup: !!layer._popup
                            });
                        }
                    }
                    if (layers.length > 0) {
                        return JSON.stringify({source: 'leaflet_layers', count: layers.length});
                    }
                }

                return null;
            """)

            if result:
                print(f"Found JS data: {result[:500]}")
        except Exception as e:
            print(f"JS execution error: {e}")

        # Try to intercept XHR requests by checking for responses in the page
        print("\n" + "="*60)
        print("Looking for parking data in network responses...")
        print("="*60)

        # Use Chrome DevTools Protocol to get response bodies
        for log in logs:
            try:
                message = json.loads(log['message'])['message']
                method = message.get('method', '')

                if method == 'Network.responseReceived':
                    params = message.get('params', {})
                    request_id = params.get('requestId')
                    url = params.get('response', {}).get('url', '')

                    # Check if this might be parking data
                    if 'wfs' in url or 'objecten' in url or 'parking' in url.lower():
                        try:
                            body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                            body_text = body.get('body', '')

                            if body_text and ('FreeSpaceShort' in body_text or 'ShortCapacity' in body_text):
                                print(f"\n*** FOUND PARKING DATA ***")
                                print(f"URL: {url}")
                                print(f"Data preview: {body_text[:1000]}")
                                parking_data = json.loads(body_text)
                                api_url = url
                                break
                        except:
                            pass
            except:
                continue

        if parking_data:
            print("\n" + "="*60)
            print("SUCCESS! Found parking data")
            print("="*60)
            print(f"API URL: {api_url}")
            print(f"Number of garages: {len(parking_data) if isinstance(parking_data, list) else 'unknown'}")

            # Show sample data
            if isinstance(parking_data, list) and len(parking_data) > 1:
                print("\nSample garage:")
                print(json.dumps(parking_data[1], indent=2))
        else:
            print("\nCould not capture parking data from network requests")
            print("The data might be loaded differently or blocked")

        return parking_data, api_url

    finally:
        driver.quit()


def main():
    print("Amsterdam Parking API Discovery")
    print("="*60)

    data, url = get_parking_with_selenium()

    if url:
        print(f"\n\nWorking API URL: {url}")

    return data


if __name__ == "__main__":
    main()
