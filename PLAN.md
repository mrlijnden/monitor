# Amsterdam Monitor Dashboard - Implementation Plan

## Overview
A Bloomberg-style terminal dashboard for Amsterdam with 6 panels in a 3x2 grid, built with Python (FastAPI) and a web frontend.

## Tech Stack
- **Backend:** FastAPI (async support, SSE capability)
- **Frontend:** HTML/CSS + htmx (lightweight, no build step)
- **Real-time:** Server-Sent Events (simpler than WebSocket for one-way updates)
- **Styling:** Custom CSS with Bloomberg terminal aesthetic (dark theme, monospace, green text)

## 6-Panel Layout
```
┌─────────────┬─────────────┬─────────────┐
│   WEATHER   │    NEWS     │   TRANSIT   │
│  (30 min)   │  (10 min)   │   (1 min)   │
├─────────────┼─────────────┼─────────────┤
│   EVENTS    │ AIR QUALITY │   MARKETS   │
│   (1 hr)    │  (15 min)   │   (2 min)   │
└─────────────┴─────────────┴─────────────┘
```

## Data Sources (All Free)
| Panel | API | Notes |
|-------|-----|-------|
| Weather | Open-Meteo | No API key needed, KNMI data |
| News | RSS feeds (NOS, AT5, DutchNews) | No API key needed |
| Transit | OVapi | Free, GVB real-time departures |
| Events | Ticketmaster Discovery | Free tier: 5000 calls/day |
| Air Quality | WAQI (aqicn.org) | Free token required |
| Markets | CoinGecko + yfinance | No API key for basic use |

## Project Structure
```
amsterdam-monitor/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # API keys, settings
│   ├── api/
│   │   ├── routes.py        # HTTP endpoints
│   │   └── sse.py           # Real-time updates
│   ├── services/            # One file per data source
│   │   ├── weather.py
│   │   ├── news.py
│   │   ├── transit.py
│   │   ├── events.py
│   │   ├── air_quality.py
│   │   └── markets.py
│   ├── core/
│   │   ├── scheduler.py     # Background refresh jobs
│   │   └── cache.py         # In-memory TTL cache
│   └── templates/
│       └── index.html       # Dashboard template
├── static/
│   └── css/
│       └── bloomberg.css    # Terminal styling
├── requirements.txt
├── .env                     # API keys
└── Dockerfile
```

## Implementation Steps

### Phase 1: Foundation
1. Create project structure and `requirements.txt`
2. Build FastAPI app skeleton with static files and templates
3. Create config module for API endpoints and keys

### Phase 2: Data Services
4. Implement weather service (Open-Meteo API)
5. Implement news service (RSS feed parser)
6. Implement transit service (OVapi for GVB)
7. Implement events service (Ticketmaster API)
8. Implement air quality service (WAQI API)
9. Implement markets service (CoinGecko + yfinance)

### Phase 3: Backend Infrastructure
10. Build in-memory cache with TTL
11. Configure APScheduler for background data refresh
12. Create SSE endpoint for real-time browser updates

### Phase 4: Frontend
13. Create Bloomberg-style CSS (dark theme, monospace, data-dense)
14. Build main dashboard template with 3x2 grid
15. Add htmx for SSE integration and partial updates
16. Add client-side clock widget

### Phase 5: Polish
17. Error handling and fallbacks
18. Create Dockerfile for deployment
19. Write .env.example with required API keys

## Key Dependencies
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
httpx>=0.26.0
feedparser>=6.0.10
apscheduler>=3.10.4
jinja2>=3.1.2
sse-starlette>=1.8.2
python-dotenv>=1.0.0
yfinance>=0.2.0
```

## Verification
1. Run `uvicorn app.main:app --reload`
2. Open `http://localhost:8000` in browser
3. Verify all 6 panels load with data
4. Confirm real-time updates work (watch transit panel update every minute)
5. Test error handling by disconnecting network temporarily
