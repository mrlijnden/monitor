"""Vision Detection Service - Object detection on camera feeds"""
import httpx
import base64
import asyncio
import subprocess
import tempfile
import os
from typing import List, Dict, Optional
from datetime import datetime
from app.config import amsterdam_now, CACHE_TTL
from app.core.cache import cache

# Google Cloud Vision API (optional - requires API key)
GOOGLE_VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"
GOOGLE_VISION_API_KEY = None  # Set via GOOGLE_VISION_API_KEY env var

# Alternative: Use Hugging Face Inference API (free tier available)
HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/facebook/detr-resnet-50"
HUGGINGFACE_API_KEY = None  # Set via HUGGINGFACE_API_KEY env var

# Alternative: Use Roboflow API (free tier)
ROBOFLOW_API_URL = "https://detect.roboflow.com"
ROBOFLOW_API_KEY = None  # Set via ROBOFLOW_API_KEY env var


async def detect_objects_google_vision(image_bytes: bytes) -> List[Dict]:
    """Detect objects using Google Cloud Vision API"""
    import os
    api_key = os.getenv("GOOGLE_VISION_API_KEY")
    
    if not api_key:
        return []
    
    try:
        # Encode image to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{GOOGLE_VISION_API_URL}?key={api_key}",
                json={
                    "requests": [{
                        "image": {
                            "content": image_base64
                        },
                        "features": [{
                            "type": "OBJECT_LOCALIZATION",
                            "maxResults": 20
                        }]
                    }]
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                objects = []
                
                if 'responses' in data and len(data['responses']) > 0:
                    localized_objects = data['responses'][0].get('localizedObjectAnnotations', [])
                    
                    for obj in localized_objects:
                        objects.append({
                            "name": obj.get('name', 'Unknown'),
                            "score": obj.get('score', 0),
                            "bounding_box": obj.get('boundingPoly', {}).get('normalizedVertices', [])
                        })
                
                return objects
    except Exception as e:
        print(f"Google Vision API error: {e}")
    
    return []


async def detect_objects_huggingface(image_bytes: bytes) -> List[Dict]:
    """Detect objects using Hugging Face Inference API (free tier)"""
    import os
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                HUGGINGFACE_API_URL,
                headers=headers,
                data=image_bytes,
                content_type="image/jpeg"
            )
            
            if response.status_code == 200:
                data = response.json()
                objects = []
                
                if isinstance(data, list):
                    for item in data:
                        objects.append({
                            "label": item.get('label', 'Unknown'),
                            "score": item.get('score', 0),
                            "box": item.get('box', {})
                        })
                
                return objects
            elif response.status_code == 503:
                # Model is loading, wait and retry
                await asyncio.sleep(5)
                return await detect_objects_huggingface(image_bytes)
    except Exception as e:
        print(f"Hugging Face API error: {e}")
    
    return []


async def extract_youtube_frame(video_id: str, timestamp: int = 5) -> Optional[bytes]:
    """Extract a frame from YouTube video using yt-dlp and ffmpeg"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Method 1: Get stream URL with yt-dlp, then extract frame with ffmpeg
        # This is the most reliable method for live streams
        with tempfile.TemporaryDirectory() as tmpdir:
            # Get the stream URL
            stream_result = await asyncio.to_thread(
                subprocess.run,
                [
                    "yt-dlp",
                    "-g",
                    "-f", "best[height<=720]/best",  # Limit to 720p for faster processing
                    "--no-playlist",
                    url
                ],
                capture_output=True,
                timeout=20,
                text=True,
                check=False
            )
            
            if stream_result.returncode == 0 and stream_result.stdout.strip():
                stream_url = stream_result.stdout.strip().split('\n')[0]
                
                # Use ffmpeg to extract frame from stream at specific timestamp
                frame_path = os.path.join(tmpdir, "frame.jpg")
                ffmpeg_result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg",
                        "-ss", str(timestamp),
                        "-i", stream_url,
                        "-vframes", "1",
                        "-q:v", "2",  # High quality JPEG
                        "-y",  # Overwrite output file
                        frame_path
                    ],
                    capture_output=True,
                    timeout=25,
                    check=False
                )
                
                if os.path.exists(frame_path) and os.path.getsize(frame_path) > 1000:
                    with open(frame_path, 'rb') as f:
                        frame_data = f.read()
                        print(f"Extracted frame from {video_id} at {timestamp}s: {len(frame_data)} bytes")
                        return frame_data
            
            # Method 2: Fallback - use yt-dlp with postprocessor
            # This is slower but works if ffmpeg direct method fails
            output_path = os.path.join(tmpdir, "frame.jpg")
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "yt-dlp",
                    "--skip-download",
                    "--no-playlist",
                    "--format", "best[height<=720]/best",
                    "--postprocessor-args", f"ffmpeg:-ss {timestamp} -vframes 1 -q:v 2",
                    "-o", output_path,
                    url
                ],
                capture_output=True,
                timeout=45,
                check=False
            )
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                with open(output_path, 'rb') as f:
                    frame_data = f.read()
                    print(f"Extracted frame (method 2) from {video_id}: {len(frame_data)} bytes")
                    return frame_data
    
    except FileNotFoundError as e:
        print(f"yt-dlp or ffmpeg not found: {e}")
        # Fallback to thumbnail if yt-dlp/ffmpeg not available
        return await extract_youtube_thumbnail(video_id)
    except subprocess.TimeoutExpired:
        print(f"Timeout extracting frame from {video_id}")
    except Exception as e:
        print(f"Error extracting YouTube frame from {video_id}: {e}")
        # Fallback to thumbnail
        return await extract_youtube_thumbnail(video_id)
    
    return None


async def extract_youtube_thumbnail(video_id: str) -> Optional[bytes]:
    """Fallback: Extract thumbnail from YouTube"""
    try:
        # Try maxresdefault first (highest quality)
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(thumbnail_url)
            if response.status_code == 200 and len(response.content) > 1000:
                return response.content
        
        # Fallback to hqdefault
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(thumbnail_url)
            if response.status_code == 200:
                return response.content
    except Exception as e:
        print(f"Error extracting thumbnail: {e}")
    
    return None


async def detect_camera_objects(camera_id: str, video_id: Optional[str] = None, image_url: Optional[str] = None) -> Dict:
    """Detect objects in a camera feed"""
    from app.services import cameras
    
    image_bytes = None
    
    # Get camera info to find video_id or image_url
    camera_list = cameras.get_camera_list()
    camera_info = next((cam for cam in camera_list if cam["id"] == camera_id), None)
    
    if camera_info:
        video_id = video_id or camera_info.get("video_id")
        image_url = image_url or camera_info.get("url")
    
    # Get image from source
    if video_id:
        # Extract frame from live stream (use random timestamp to get different frames)
        import random
        timestamp = random.randint(3, 10)  # Random timestamp between 3-10 seconds
        image_bytes = await extract_youtube_frame(video_id, timestamp=timestamp)
    elif image_url:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(image_url)
            if response.status_code == 200:
                image_bytes = response.content
    
    if not image_bytes:
        return {
            "camera_id": camera_id,
            "objects": [],
            "detection_count": 0,
            "updated": amsterdam_now().strftime("%H:%M:%S"),
            "source": None
        }
    
    # Try detection APIs in order
    objects = []
    source = None
    
    # Try Hugging Face first (free tier)
    objects = await detect_objects_huggingface(image_bytes)
    if objects:
        source = "huggingface"
    else:
        # Fallback to Google Vision
        objects = await detect_objects_google_vision(image_bytes)
        if objects:
            source = "google_vision"
    
    # Count common objects
    detection_summary = {}
    for obj in objects:
        label = obj.get('label') or obj.get('name', 'Unknown')
        detection_summary[label] = detection_summary.get(label, 0) + 1
    
    return {
        "camera_id": camera_id,
        "objects": objects[:10],  # Limit to top 10
        "detection_count": len(objects),
        "summary": detection_summary,
        "updated": amsterdam_now().strftime("%H:%M:%S"),
        "source": source
    }


async def get_camera_detections(camera_id: str) -> Dict:
    """Get cached or fresh detections for a camera"""
    cache_key = f"vision_{camera_id}"
    cached = cache.get(cache_key)
    
    if cached:
        return cached
    
    # Fetch fresh detection
    detection = await detect_camera_objects(camera_id)
    
    # Cache for 60 seconds
    cache.set(cache_key, detection, 60)
    return detection
