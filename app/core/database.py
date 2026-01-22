"""Database module for PostgreSQL connection and detection storage"""
import os
import asyncpg
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.config import amsterdam_now

# Database connection pool
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> Optional[asyncpg.Pool]:
    """Get or create database connection pool"""
    global _pool

    if _pool is not None:
        return _pool

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[DB] DATABASE_URL not set, detection history disabled")
        return None

    try:
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=5,
            command_timeout=10
        )
        print(f"[DB] Connected to PostgreSQL")
        return _pool
    except Exception as e:
        print(f"[DB] Failed to connect: {e}")
        return None


async def init_db():
    """Initialize database tables"""
    pool = await get_pool()
    if not pool:
        return

    async with pool.acquire() as conn:
        # Create detections table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id SERIAL PRIMARY KEY,
                camera_id VARCHAR(50) NOT NULL,
                detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                object_count INTEGER NOT NULL DEFAULT 0,
                objects JSONB NOT NULL DEFAULT '[]',
                summary JSONB NOT NULL DEFAULT '{}',
                source VARCHAR(50),
                frame_size INTEGER
            )
        """)

        # Create index on camera_id and timestamp for fast queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_camera_time
            ON detections (camera_id, detected_at DESC)
        """)

        # Create panel_cache table for all dashboard data
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS panel_cache (
                id SERIAL PRIMARY KEY,
                panel_name VARCHAR(50) NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                data JSONB NOT NULL DEFAULT '{}'
            )
        """)

        # Create index for fast lookups by panel and time
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_panel_cache_name_time
            ON panel_cache (panel_name, fetched_at DESC)
        """)

        print("[DB] Tables initialized")


async def save_detection(
    camera_id: str,
    objects: List[Dict],
    summary: Dict[str, int],
    source: Optional[str] = None,
    frame_size: Optional[int] = None
) -> Optional[int]:
    """Save a detection result to database"""
    pool = await get_pool()
    if not pool:
        return None

    try:
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO detections (camera_id, detected_at, object_count, objects, summary, source, frame_size)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """,
                camera_id,
                amsterdam_now(),
                len(objects),
                json.dumps(objects),
                json.dumps(summary),
                source,
                frame_size
            )
            return result['id'] if result else None
    except Exception as e:
        print(f"[DB] Error saving detection: {e}")
        return None


async def get_recent_detections(
    camera_id: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get recent detections, optionally filtered by camera"""
    pool = await get_pool()
    if not pool:
        return []

    try:
        async with pool.acquire() as conn:
            if camera_id:
                rows = await conn.fetch("""
                    SELECT id, camera_id, detected_at, object_count, summary, source
                    FROM detections
                    WHERE camera_id = $1
                    ORDER BY detected_at DESC
                    LIMIT $2
                """, camera_id, limit)
            else:
                rows = await conn.fetch("""
                    SELECT id, camera_id, detected_at, object_count, summary, source
                    FROM detections
                    ORDER BY detected_at DESC
                    LIMIT $1
                """, limit)

            return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] Error fetching detections: {e}")
        return []


async def get_detection_stats(camera_id: Optional[str] = None) -> Dict[str, Any]:
    """Get detection statistics"""
    pool = await get_pool()
    if not pool:
        return {}

    try:
        async with pool.acquire() as conn:
            if camera_id:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_detections,
                        AVG(object_count) as avg_objects,
                        MAX(object_count) as max_objects,
                        MIN(detected_at) as first_detection,
                        MAX(detected_at) as last_detection
                    FROM detections
                    WHERE camera_id = $1
                """, camera_id)
            else:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_detections,
                        AVG(object_count) as avg_objects,
                        MAX(object_count) as max_objects,
                        MIN(detected_at) as first_detection,
                        MAX(detected_at) as last_detection
                    FROM detections
                """)

            return dict(row) if row else {}
    except Exception as e:
        print(f"[DB] Error fetching stats: {e}")
        return {}


async def get_detections_timeline(hours: int = 24) -> Dict[str, Any]:
    """Get hourly aggregated detection counts by category"""
    pool = await get_pool()
    if not pool:
        return {"labels": [], "categories": {}}

    try:
        async with pool.acquire() as conn:
            # Query to extract and aggregate categories from summary JSONB
            rows = await conn.fetch("""
                SELECT
                    date_trunc('hour', detected_at) as hour,
                    key as category,
                    SUM(value::int) as total_count
                FROM detections,
                     jsonb_each_text(summary::jsonb)
                WHERE detected_at > NOW() - INTERVAL '1 hour' * $1
                GROUP BY hour, key
                ORDER BY hour, key
            """, hours)

            # Build timeline data structure
            hours_set: set = set()
            categories_data: Dict[str, Dict[str, int]] = {}

            for row in rows:
                hour_str = row['hour'].strftime('%H:%M')
                category = row['category']
                hours_set.add(hour_str)

                if category not in categories_data:
                    categories_data[category] = {}
                categories_data[category][hour_str] = row['total_count']

            # Sort hours and build response
            sorted_hours = sorted(hours_set)

            # Build category arrays, fill missing hours with 0
            categories = {}
            for cat, hour_data in categories_data.items():
                categories[cat] = [hour_data.get(h, 0) for h in sorted_hours]

            return {
                "labels": sorted_hours,
                "categories": categories
            }
    except Exception as e:
        print(f"[DB] Error fetching timeline: {e}")
        return {"labels": [], "categories": {}}


async def save_panel_data(panel_name: str, data: Dict[str, Any]) -> Optional[int]:
    """Save panel data to database for historical tracking"""
    pool = await get_pool()
    if not pool:
        return None

    try:
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO panel_cache (panel_name, fetched_at, data)
                VALUES ($1, $2, $3)
                RETURNING id
            """, panel_name, amsterdam_now(), json.dumps(data))
            return result['id'] if result else None
    except Exception as e:
        print(f"[DB] Error saving panel data: {e}")
        return None


async def get_latest_panel_data(panel_name: str) -> Optional[Dict[str, Any]]:
    """Get the most recent data for a panel"""
    pool = await get_pool()
    if not pool:
        return None

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT data, fetched_at
                FROM panel_cache
                WHERE panel_name = $1
                ORDER BY fetched_at DESC
                LIMIT 1
            """, panel_name)
            if row:
                data = json.loads(row['data']) if isinstance(row['data'], str) else row['data']
                data['_fetched_at'] = row['fetched_at'].isoformat()
                return data
            return None
    except Exception as e:
        print(f"[DB] Error fetching panel data: {e}")
        return None


async def get_panel_history(
    panel_name: str,
    hours: int = 24,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get historical data for a panel"""
    pool = await get_pool()
    if not pool:
        return []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, fetched_at, data
                FROM panel_cache
                WHERE panel_name = $1
                  AND fetched_at > NOW() - INTERVAL '1 hour' * $2
                ORDER BY fetched_at DESC
                LIMIT $3
            """, panel_name, hours, limit)

            result = []
            for row in rows:
                data = json.loads(row['data']) if isinstance(row['data'], str) else row['data']
                result.append({
                    'id': row['id'],
                    'fetched_at': row['fetched_at'].isoformat(),
                    'data': data
                })
            return result
    except Exception as e:
        print(f"[DB] Error fetching panel history: {e}")
        return []


async def cleanup_old_panel_data(days: int = 7):
    """Remove panel data older than specified days"""
    pool = await get_pool()
    if not pool:
        return

    try:
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM panel_cache
                WHERE fetched_at < NOW() - INTERVAL '1 day' * $1
            """, days)
            print(f"[DB] Cleaned up old panel data: {result}")
    except Exception as e:
        print(f"[DB] Error cleaning up panel data: {e}")


async def close_pool():
    """Close database connection pool"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[DB] Connection pool closed")
