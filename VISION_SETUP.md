# Vision Detection Setup Guide

## Lokale Setup

### 1. Installeer yt-dlp en ffmpeg

**macOS:**
```bash
brew install yt-dlp ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y yt-dlp ffmpeg
```

**Windows:**
```bash
# Via chocolatey
choco install yt-dlp ffmpeg

# Of download van:
# - yt-dlp: https://github.com/yt-dlp/yt-dlp/releases
# - ffmpeg: https://ffmpeg.org/download.html
```

### 2. Installeer Python dependencies

```bash
cd /Users/acio/experiments/monitor
pip install -r requirements.txt
# Of met uv:
uv pip install -r requirements.txt
```

### 3. (Optioneel) Hugging Face API Key

Voor betere rate limits en snellere responses:

1. Ga naar https://huggingface.co/settings/tokens
2. Maak een nieuwe token
3. Voeg toe aan `.env`:
```bash
HUGGINGFACE_API_KEY=your_token_here
```

**Zonder API key werkt het ook**, maar met beperkte rate limits.

### 4. Test lokaal

```bash
# Start de server
uvicorn app.main:app --reload

# Open browser
open http://localhost:8000
```

De vision detection overlay verschijnt automatisch op de camera panels (linksonder).

## Deployment (Dokploy/Nixpacks)

### Automatisch via Nixpacks

De `nixpacks.toml` configureert automatisch:
- `ffmpeg` en `yt-dlp` worden geïnstalleerd tijdens build
- Python dependencies worden geïnstalleerd via `requirements.txt`

**Geen extra stappen nodig!** Push naar repo en deploy.

### Environment Variables (optioneel)

Voeg toe in Dokploy environment settings:
```
HUGGINGFACE_API_KEY=your_token_here
```

## Troubleshooting

### "yt-dlp not found" of "ffmpeg not found"

**Lokaal:**
- Installeer de tools (zie stap 1 hierboven)
- Check met: `which yt-dlp ffmpeg`

**Deployment:**
- Check of `nixpacks.toml` correct is gepusht
- Check build logs in Dokploy

### "No detections" in overlay

- Check browser console voor errors
- Check server logs voor API errors
- Hugging Face model kan "loading" zijn (wacht 10-30 seconden)
- Probeer met `HUGGINGFACE_API_KEY` voor betere performance

### Frames worden niet geëxtraheerd

- Check of YouTube video ID correct is in `cameras.py`
- Check server logs voor yt-dlp/ffmpeg errors
- Fallback naar thumbnail werkt altijd als backup

## Hoe het werkt

1. **Frame Extractie**: `yt-dlp` haalt stream URL op, `ffmpeg` extraheert frame op random timestamp (3-10s)
2. **Object Detection**: Frame wordt naar Hugging Face API gestuurd (DETR-resnet-50 model)
3. **Display**: Resultaten worden getoond in overlay op camera panel
4. **Refresh**: Elke 60 seconden automatisch

## API Endpoints

- `GET /api/vision/{camera_id}` - JSON met detection results
- `GET /partial/vision/{camera_id}` - HTML partial voor overlay

## Performance

- Frame extractie: ~5-15 seconden per camera
- Object detection: ~2-5 seconden (Hugging Face API)
- Cache: 60 seconden per camera
- Scheduler refresh: Elke 5 minuten
