# Amsterdam Monitor - Services Status Overzicht

## ✅ Werkende Services

### 1. **Weather** (Weer)
- **Status**: ✅ Werkend
- **Bron**: Open-Meteo API (gratis, geen API key nodig)
- **Data**: Temperatuur, vochtigheid, neerslag, wind, weercodes
- **Refresh**: Elke 30 minuten
- **Panel**: Weather panel

### 2. **News** (Nieuws)
- **Status**: ✅ Werkend
- **Bron**: RSS feeds (NOS, Dutch News)
- **Data**: Laatste nieuwsartikelen met Amsterdam tijdzone
- **Refresh**: Elke 10 minuten
- **Panel**: NL News panel

### 3. **Transit** (OV - Trams/Metro/Bus)
- **Status**: ✅ Werkend
- **Bron**: OVapi (v0.ovapi.nl)
- **Data**: Real-time vertrektijden van 12 Amsterdam haltes
- **Refresh**: Elke 1 minuut
- **Panel**: Transit panel (niet zichtbaar in huidige layout, maar data beschikbaar)

### 4. **Trains** (Treinen)
- **Status**: ✅ Werkend
- **Bron**: OVapi (v0.ovapi.nl)
- **Data**: Treinvertrektijden van Amsterdam stations
- **Refresh**: Elke 2 minuten
- **Panel**: Trains panel (niet zichtbaar in huidige layout)

### 5. **Markets** (Markten)
- **Status**: ✅ Werkend
- **Bron**: CoinGecko API (crypto) + yfinance (AEX, stocks)
- **Data**: Crypto prijzen (BTC, ETH, SOL), AEX index, belangrijke stocks
- **Refresh**: Elke 2 minuten
- **Panel**: Markets panel

### 6. **Air Quality** (Luchtkwaliteit)
- **Status**: ✅ Werkend
- **Bron**: Open-Meteo Air Quality API (gratis)
- **Data**: European AQI, PM10, PM2.5, NO2, O3, etc.
- **Refresh**: Elke 15 minuten
- **Panel**: Air Quality panel

### 7. **Bikes** (Fietsen)
- **Status**: ✅ Werkend
- **Bron**: Open-Meteo (weerdata voor fietscondities)
- **Data**: Fiets-score gebaseerd op weer (temperatuur, wind, regen)
- **Refresh**: Elke 15 minuten
- **Panel**: Cycling panel

### 8. **Emergency** (P2000)
- **Status**: ✅ Werkend
- **Bron**: P2000-online.net HTML scraping
- **Data**: Live P2000 incidenten (brand, ambulance, politie) met postcode extractie
- **Features**: Geocoding voor kaart, postcode notificaties
- **Refresh**: Elke 30 seconden
- **Panel**: P2000 Scanner panel

### 9. **Cameras** (Live Camera's)
- **Status**: ✅ Werkend
- **Bron**: YouTube live streams
- **Data**: 3 live camera feeds (Dam Square, Centraal Station, Live Camera)
- **Panels**: 2 camera panels (CAM 1 en CAM 2)
- **Features**: Auto-rotate elke 30 seconden, handmatige navigatie

### 10. **Map Data** (Kaart Data)
- **Status**: ✅ Werkend
- **Bron**: OVapi voor voertuigposities
- **Data**: Real-time OV voertuigen op de kaart (trams, metro, bus, ferry)
- **Panel**: Live Map panel

### 11. **Ticker** (Nieuws Ticker)
- **Status**: ✅ Werkend
- **Bron**: RSS feeds (NOS, AT5, Parool)
- **Data**: Scrollende nieuws headlines bovenaan het scherm
- **Refresh**: Elke 60 seconden

## ⚠️ Gedeeltelijk Werkend / Problemen

### 12. **Flights** (Vluchten)
- **Status**: ⚠️ Gedeeltelijk werkend
- **Bron**: Flightradar24 scraping (probeert eerst), Schiphol API (fallback)
- **Probleem**: Flightradar24 HTML scraping werkt mogelijk niet goed (JavaScript-heavy pagina)
- **Refresh**: Elke 2 minuten
- **Panel**: Schiphol panel
- **Notitie**: Gebruikt httpx-curl-cffi voor Cloudflare bypass

### 13. **Parking** (Parkeren)
- **Status**: ⚠️ Niet werkend (geen data)
- **Bron**: Amsterdam Maps API (probeert eerst), HTML scraping (fallback)
- **Probleem**: Amsterdam Maps laadt data via JavaScript, scraping werkt niet
- **Refresh**: Elke 5 minuten
- **Panel**: Parking panel
- **Notitie**: Gebruikt httpx-curl-cffi, maar heeft mogelijk Selenium nodig voor JavaScript rendering

### 14. **Events** (Evenementen)
- **Status**: ⚠️ Alleen met API key
- **Bron**: Ticketmaster API
- **Data**: Evenementen in Amsterdam (volgende 14 dagen)
- **Probleem**: Vereist TICKETMASTER_API_KEY environment variable
- **Refresh**: Elke 1 uur
- **Panel**: Geen (niet zichtbaar in huidige layout)

## ❌ Verwijderd

### 15. **Hacker News**
- **Status**: ❌ Verwijderd
- **Reden**: Gebruiker heeft gevraagd om te verwijderen
- **Vervangen door**: Tweede camera panel

## 📊 Overzicht Dashboard Panels

**Row 1:**
- Live Map (2x2) - ✅ Werkend
- Weather - ✅ Werkend
- Markets - ✅ Werkend
- Schiphol Flights - ⚠️ Gedeeltelijk

**Row 2:**
- NL News - ✅ Werkend
- P2000 Scanner - ✅ Werkend
- Live Cameras 1 - ✅ Werkend
- Live Cameras 2 - ✅ Werkend
- System Status - Static

**Row 3:**
- Cycling - ✅ Werkend
- Air Quality - ✅ Werkend
- Parking - ⚠️ Geen data

## 🔧 Technische Details

### Dependencies:
- `httpx` - HTTP client
- `httpx-curl-cffi` - Cloudflare bypass (vervangen cloudscraper)
- `beautifulsoup4` - HTML parsing
- `feedparser` - RSS parsing
- `yfinance` - Stock data
- `apscheduler` - Background jobs
- `sse-starlette` - Server-Sent Events

### Data Sources:
- Open-Meteo (weer, luchtkwaliteit) - ✅ Gratis, geen key
- OVapi (OV data) - ✅ Gratis, geen key
- CoinGecko (crypto) - ✅ Gratis, geen key
- P2000-online.net (emergency) - ✅ Gratis scraping
- Flightradar24 (vluchten) - ⚠️ Scraping problemen
- Amsterdam Maps (parking) - ⚠️ Scraping problemen
- Ticketmaster (events) - ⚠️ Vereist API key
