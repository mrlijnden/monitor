"""Vision Detection Service - Object detection on camera feeds"""
import httpx
import base64
import asyncio
import subprocess
import tempfile
import os
import io
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from app.config import amsterdam_now, CACHE_TTL
from app.core.cache import cache

# Colors for bounding boxes (RGB)
BBOX_COLORS = [
    (255, 107, 107),  # Red
    (78, 205, 196),   # Cyan
    (255, 230, 109),  # Yellow
    (170, 166, 255),  # Purple
    (255, 154, 162),  # Pink
    (144, 238, 144),  # Light green
    (255, 179, 71),   # Orange
    (135, 206, 235),  # Sky blue
]

# Google Cloud Vision API (optional - requires API key)
GOOGLE_VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"
GOOGLE_VISION_API_KEY = None  # Set via GOOGLE_VISION_API_KEY env var

# Hugging Face Inference API (requires free API key from huggingface.co/settings/tokens)
HUGGINGFACE_API_URL = "https://router.huggingface.co/hf-inference/models/facebook/detr-resnet-50"
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
    """Detect objects using Hugging Face Inference API (requires free API key)"""
    import os
    api_key = os.getenv("HUGGINGFACE_API_KEY")

    if not api_key:
        # API key required - get one free at huggingface.co/settings/tokens
        return []

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "image/jpeg"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                HUGGINGFACE_API_URL,
                headers=headers,
                content=image_bytes
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
                # Model is loading, wait and retry once
                print("Hugging Face model loading, waiting...")
                await asyncio.sleep(5)
                response = await client.post(
                    HUGGINGFACE_API_URL,
                    headers=headers,
                    content=image_bytes
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return [{"label": item.get('label', 'Unknown'), "score": item.get('score', 0), "box": item.get('box', {})} for item in data]
            elif response.status_code == 401:
                print("Hugging Face API: Invalid or missing API key")
            else:
                print(f"Hugging Face API error: {response.status_code}")
    except Exception as e:
        print(f"Hugging Face API error: {e}")

    return []


async def extract_youtube_frame(video_id: str, timestamp: int = 5) -> Optional[bytes]:
    """Extract a frame from YouTube video using yt-dlp and ffmpeg"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"

        # Use explicit /tmp for Docker/nixpacks compatibility
        tmpdir = f"/tmp/vision_{video_id}_{os.getpid()}"
        os.makedirs(tmpdir, exist_ok=True)

        try:
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
        finally:
            # Clean up temp directory
            import shutil
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except:
                pass

    except FileNotFoundError as e:
        print(f"yt-dlp or ffmpeg not found: {e}")
        # Fallback to thumbnail if yt-dlp/ffmpeg not available
        return await extract_youtube_thumbnail(video_id)
    except subprocess.TimeoutExpired:
        print(f"Timeout extracting frame from {video_id}")
        return await extract_youtube_thumbnail(video_id)
    except Exception as e:
        print(f"Error extracting YouTube frame from {video_id}: {e}")
        # Fallback to thumbnail
        return await extract_youtube_thumbnail(video_id)

    # Final fallback to thumbnail
    print(f"Frame extraction failed for {video_id}, using thumbnail")
    return await extract_youtube_thumbnail(video_id)


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


async def fetch_vision() -> Dict:
    """Fetch vision detections for all cameras and cache results"""
    from app.services import cameras

    camera_list = cameras.get_camera_list()
    all_detections = []

    for cam in camera_list:
        try:
            detection = await detect_camera_objects(cam["id"])
            all_detections.append(detection)
            # Cache individual detection
            cache.set(f"vision_{cam['id']}", detection, CACHE_TTL.get("vision", 300))
        except Exception as e:
            print(f"Error detecting objects for camera {cam['id']}: {e}")

    result = {
        "detections": all_detections,
        "updated": amsterdam_now().strftime("%H:%M:%S"),
        "camera_count": len(all_detections)
    }

    cache.set("vision", result, CACHE_TTL.get("vision", 300))
    return result


def draw_bounding_boxes(image_bytes: bytes, objects: List[Dict], image_size: Tuple[int, int] = None) -> bytes:
    """Draw bounding boxes on an image and return the annotated image as bytes"""
    try:
        # Open image
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')

        draw = ImageDraw.Draw(image)
        width, height = image.size

        # Try to load a font, fall back to default
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
            small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
        except:
            font = ImageFont.load_default()
            small_font = font

        # Track labels for color assignment and counting
        label_colors = {}
        label_counts = {}
        color_index = 0
        drawn_count = 0

        for obj in objects:
            label = obj.get('label') or obj.get('name', 'Unknown')
            score = obj.get('score', 0)
            box = obj.get('box', {})

            # Skip low confidence detections
            if score < 0.4:
                continue

            # Count labels
            label_counts[label] = label_counts.get(label, 0) + 1
            drawn_count += 1

            # Get bounding box coordinates
            if isinstance(box, dict) and 'xmin' in box:
                xmin = box.get('xmin', 0)
                ymin = box.get('ymin', 0)
                xmax = box.get('xmax', 0)
                ymax = box.get('ymax', 0)
            else:
                continue

            # Assign color to label
            if label not in label_colors:
                label_colors[label] = BBOX_COLORS[color_index % len(BBOX_COLORS)]
                color_index += 1

            color = label_colors[label]

            # Draw bounding box
            draw.rectangle([xmin, ymin, xmax, ymax], outline=color, width=2)

            # Draw label background
            label_text = f"{label} {score:.0%}"
            bbox = draw.textbbox((xmin, ymin - 20), label_text, font=small_font)
            draw.rectangle([bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2], fill=color)

            # Draw label text
            draw.text((xmin, ymin - 20), label_text, fill=(0, 0, 0), font=small_font)

        # Draw summary overlay in top-right corner
        summary_lines = [f"DETECTED: {drawn_count}"]
        for label, count in sorted(label_counts.items(), key=lambda x: -x[1])[:5]:
            summary_lines.append(f"{label}: {count}")

        # Calculate box size
        padding = 8
        line_height = 14
        max_width = 0
        for line in summary_lines:
            bbox = draw.textbbox((0, 0), line, font=small_font)
            max_width = max(max_width, bbox[2] - bbox[0])

        box_width = max_width + padding * 2
        box_height = len(summary_lines) * line_height + padding * 2

        # Draw summary box
        box_x = width - box_width - 10
        box_y = 10
        draw.rectangle([box_x, box_y, box_x + box_width, box_y + box_height],
                      fill=(0, 0, 0, 200), outline=(0, 204, 204))

        # Draw summary text
        y = box_y + padding
        for i, line in enumerate(summary_lines):
            color = (0, 204, 204) if i == 0 else (200, 200, 200)
            draw.text((box_x + padding, y), line, fill=color, font=small_font)
            y += line_height

        # Convert back to bytes
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=85)
        output.seek(0)
        return output.getvalue()

    except Exception as e:
        print(f"Error drawing bounding boxes: {e}")
        return image_bytes


def generate_placeholder_image(camera_id: str) -> Optional[bytes]:
    """Generate a placeholder image when frame extraction fails"""
    try:
        # Create a dark placeholder image
        img = Image.new('RGB', (640, 360), color=(10, 10, 10))
        draw = ImageDraw.Draw(img)

        # Try to load font
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
            small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
        except:
            font = ImageFont.load_default()
            small_font = font

        # Draw text
        text = "NO SIGNAL"
        draw.text((280, 160), text, fill=(0, 204, 204), font=font)
        draw.text((250, 200), f"Camera: {camera_id}", fill=(100, 100, 100), font=small_font)
        draw.text((220, 220), "Waiting for frame extraction...", fill=(60, 60, 60), font=small_font)

        # Draw border
        draw.rectangle([0, 0, 639, 359], outline=(0, 204, 204), width=2)

        # Convert to bytes
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
        output.seek(0)
        return output.getvalue()
    except Exception as e:
        print(f"Error generating placeholder: {e}")
        return None


async def get_annotated_frame(camera_id: str) -> Optional[bytes]:
    """Get cached annotated frame or return None if not available"""
    cache_key = f"vision_image_{camera_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    # If not cached, generate one (first request)
    return await refresh_annotated_frame(camera_id)


async def refresh_annotated_frame(camera_id: str) -> Optional[bytes]:
    """Generate and cache a new annotated frame for a camera"""
    from app.services import cameras

    # Get camera info
    camera_list = cameras.get_camera_list()
    camera_info = next((cam for cam in camera_list if cam["id"] == camera_id), None)

    if not camera_info:
        return None

    video_id = camera_info.get("video_id")
    image_url = camera_info.get("url")

    # Get image from source
    image_bytes = None
    if video_id:
        import random
        timestamp = random.randint(3, 10)
        image_bytes = await extract_youtube_frame(video_id, timestamp=timestamp)
    elif image_url:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(image_url)
            if response.status_code == 200:
                image_bytes = response.content

    if not image_bytes:
        # Generate placeholder image
        image_bytes = generate_placeholder_image(camera_id)
        if not image_bytes:
            return None

    # Detect objects
    objects = await detect_objects_huggingface(image_bytes)
    if not objects:
        objects = await detect_objects_google_vision(image_bytes)

    if not objects:
        # Cache original image if no detections
        cache.set(f"vision_image_{camera_id}", image_bytes, 60)
        return image_bytes

    # Draw bounding boxes
    annotated_image = draw_bounding_boxes(image_bytes, objects)

    # Cache for 60 seconds (will be refreshed by scheduler every 30s)
    cache.set(f"vision_image_{camera_id}", annotated_image, 60)
    print(f"Refreshed AI detection for camera {camera_id}: {len(objects)} objects")

    return annotated_image


async def refresh_all_annotated_frames():
    """Refresh annotated frames for all cameras - called by scheduler"""
    from app.services import cameras

    camera_list = cameras.get_camera_list()
    for cam in camera_list:
        try:
            await refresh_annotated_frame(cam["id"])
        except Exception as e:
            print(f"Error refreshing AI frame for {cam['id']}: {e}")
