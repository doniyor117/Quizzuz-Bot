"""
Vocabulary AI Rate Limiting Service

Tracks and enforces rate limits for vocabulary AI lookups:
- 12 requests per minute (rolling window)
- 100 requests per day (resets at midnight GMT+5)
"""

from datetime import datetime, timedelta, timezone
from bot_services.firebase_service import db, TASHKENT_TZ, run_sync

# Rate limits (Option A increase)
VOCAB_MINUTE_LIMIT = 12  # Increased from 7
VOCAB_DAY_LIMIT = 100    # Increased from 50

def _check_vocab_rate_limit_sync(user_id: int) -> tuple[bool, int, int]:
    """
    Check if user can make a vocabulary AI request.
    
    Returns:
        (allowed, remaining_minute, remaining_day)
    """
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if not doc.exists:
        return False, 0, 0
    
    user_data = doc.to_dict()
    now = datetime.now(TASHKENT_TZ)
    today_str = now.strftime('%Y-%m-%d')
    
    # Get current counts
    requests_today = user_data.get('vocab_requests_today', 0)
    last_reset_date = user_data.get('vocab_last_reset_date', '')
    requests_this_minute = user_data.get('vocab_requests_this_minute', 0)
    minute_window_start = user_data.get('vocab_minute_window_start')
    
    # Daily reset check
    if last_reset_date != today_str:
        requests_today = 0
        # Reset will happen on next increment
    
    # Minute window reset check
    if minute_window_start:
        # Convert Firestore timestamp to datetime
        if hasattr(minute_window_start, 'timestamp'):
            window_start_dt = datetime.fromtimestamp(minute_window_start.timestamp(), tz=TASHKENT_TZ)
        else:
            # Fallback if it's already a datetime
            window_start_dt = minute_window_start
        
        # Check if 60 seconds have passed
        seconds_elapsed = (now - window_start_dt).total_seconds()
        if seconds_elapsed >= 60:
            requests_this_minute = 0
            # Reset will happen on next increment
    else:
        # No window set, first request
        requests_this_minute = 0
    
    # Calculate remaining
    remaining_day = max(0, VOCAB_DAY_LIMIT - requests_today)
    remaining_minute = max(0, VOCAB_MINUTE_LIMIT - requests_this_minute)
    
    # Check if allowed
    allowed = (requests_today < VOCAB_DAY_LIMIT and 
               requests_this_minute < VOCAB_MINUTE_LIMIT)
    
    return allowed, remaining_minute, remaining_day

async def check_vocab_rate_limit(user_id: int) -> tuple[bool, int, int]:
    """
    Check if user can make a vocabulary AI request (async).
    
    Returns:
        (allowed: bool, remaining_minute: int, remaining_day: int)
    """
    return await run_sync(_check_vocab_rate_limit_sync, user_id)

def _increment_vocab_usage_sync(user_id: int) -> None:
    """
    Increment vocabulary usage counters after successful AI request.
    Handles automatic resets for both minute and day windows.
    """
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if not doc.exists:
        return
    
    user_data = doc.to_dict()
    now = datetime.now(TASHKENT_TZ)
    today_str = now.strftime('%Y-%m-%d')
    
    # Prepare updates
    updates = {}
    
    # Get current values
    requests_today = user_data.get('vocab_requests_today', 0)
    last_reset_date = user_data.get('vocab_last_reset_date', '')
    requests_this_minute = user_data.get('vocab_requests_this_minute', 0)
    minute_window_start = user_data.get('vocab_minute_window_start')
    
    # Handle daily reset
    if last_reset_date != today_str:
        updates['vocab_requests_today'] = 1
        updates['vocab_last_reset_date'] = today_str
    else:
        updates['vocab_requests_today'] = requests_today + 1
    
    # Handle minute window reset
    should_reset_minute = False
    if minute_window_start:
        if hasattr(minute_window_start, 'timestamp'):
            window_start_dt = datetime.fromtimestamp(minute_window_start.timestamp(), tz=TASHKENT_TZ)
        else:
            window_start_dt = minute_window_start
        
        seconds_elapsed = (now - window_start_dt).total_seconds()
        if seconds_elapsed >= 60:
            should_reset_minute = True
    else:
        should_reset_minute = True
    
    if should_reset_minute:
        updates['vocab_requests_this_minute'] = 1
        updates['vocab_minute_window_start'] = now
    else:
        updates['vocab_requests_this_minute'] = requests_this_minute + 1
    
    # Apply updates
    doc_ref.update(updates)

async def increment_vocab_usage(user_id: int) -> None:
    """
    Increment vocabulary usage counters (async).
    Call this after a successful AI vocabulary request.
    """
    await run_sync(_increment_vocab_usage_sync, user_id)

def _get_vocab_quota_status_sync(user_id: int) -> dict:
    """
    Get detailed quota status for display.
    
    Returns:
        {
            'requests_today': int,
            'requests_this_minute': int,
            'day_limit': int,
            'minute_limit': int,
            'day_remaining': int,
            'minute_remaining': int,
            'day_used_percent': float,
            'next_reset_hours': float
        }
    """
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if not doc.exists:
        return {
            'requests_today': 0,
            'requests_this_minute': 0,
            'day_limit': VOCAB_DAY_LIMIT,
            'minute_limit': VOCAB_MINUTE_LIMIT,
            'day_remaining': VOCAB_DAY_LIMIT,
            'minute_remaining': VOCAB_MINUTE_LIMIT,
            'day_used_percent': 0.0,
            'next_reset_hours': 0.0
        }
    
    user_data = doc.to_dict()
    now = datetime.now(TASHKENT_TZ)
    today_str = now.strftime('%Y-%m-%d')
    
    requests_today = user_data.get('vocab_requests_today', 0)
    requests_this_minute = user_data.get('vocab_requests_this_minute', 0)
    last_reset_date = user_data.get('vocab_last_reset_date', '')
    
    # Reset if new day
    if last_reset_date != today_str:
        requests_today = 0
    
    day_remaining = max(0, VOCAB_DAY_LIMIT - requests_today)
    minute_remaining = max(0, VOCAB_MINUTE_LIMIT - requests_this_minute)
    day_used_percent = (requests_today / VOCAB_DAY_LIMIT) * 100 if VOCAB_DAY_LIMIT > 0 else 0
    
    # Calculate next reset (midnight GMT+5)
    tomorrow = now + timedelta(days=1)
    midnight_tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    hours_until_reset = (midnight_tomorrow - now).total_seconds() / 3600
    
    return {
        'requests_today': requests_today,
        'requests_this_minute': requests_this_minute,
        'day_limit': VOCAB_DAY_LIMIT,
        'minute_limit': VOCAB_MINUTE_LIMIT,
        'day_remaining': day_remaining,
        'minute_remaining': minute_remaining,
        'day_used_percent': round(day_used_percent, 1),
        'next_reset_hours': round(hours_until_reset, 1)
    }

async def get_vocab_quota_status(user_id: int) -> dict:
    """Get detailed quota status for display (async)."""
    return await run_sync(_get_vocab_quota_status_sync, user_id)
