import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone
import os
import asyncio
import threading
from functools import partial
from dotenv import load_dotenv

# Tashkent timezone (GMT+5)
TASHKENT_TZ = timezone(timedelta(hours=5))

load_dotenv()
raw_admin_ids = os.getenv("ADMIN_ID", "")
ADMIN_IDS = [x.strip() for x in raw_admin_ids.split(",") if x.strip()]

# --- NATURAL SORTING HELPER ---
import re
def natural_sort_key(text):
    """Sort strings with numbers naturally (1, 2, 11 instead of 1, 11, 2)"""
    def atoi(text):
        return int(text) if text.isdigit() else text.lower()
    return [atoi(c) for c in re.split(r'(\d+)', text)]

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- ASYNC HELPER ---
async def run_sync(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))

# --- ADMIN HELPERS ---
def _get_admins_sync():
    # Get admins from DB
    docs = db.collection('admins').stream()
    db_admins = [doc.id for doc in docs]
    # Combine with Env Admins
    return list(set(ADMIN_IDS + db_admins))

async def get_admins():
    return await run_sync(_get_admins_sync)

def _is_admin_sync(user_id):
    uid = str(user_id)
    if uid in ADMIN_IDS: return True
    doc = db.collection('admins').document(uid).get()
    return doc.exists

async def is_admin_check(user_id):
    return await run_sync(_is_admin_sync, user_id)

def _add_admin_sync(user_id, added_by):
    db.collection('admins').document(str(user_id)).set({
        "added_by": str(added_by),
        "added_at": firestore.SERVER_TIMESTAMP
    })

async def add_admin_db(user_id, added_by):
    await run_sync(_add_admin_sync, user_id, added_by)

def _remove_admin_sync(user_id):
    db.collection('admins').document(str(user_id)).delete()

async def remove_admin_db(user_id):
    await run_sync(_remove_admin_sync, user_id)

# --- USER & DAILY GOALS (OPTIMIZED) ---
def _get_user_sync(user_id):
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        now_str = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
        last_reset = data.get('last_daily_reset', '')
        
        if last_reset != now_str:
            updates = {
                'last_daily_reset': now_str,
                'daily_cards': 0,
                'daily_goal_hit': False
            }
            doc_ref.update(updates)
            data.update(updates)
        
        # Initialize new fields for dual currency system
        if 'xp' not in data: 
            data['xp'] = 0.0  # TX Coins (spendable)
        if 'total_xp' not in data:
            data['total_xp'] = 0.0  # XP for leveling
        if 'level' not in data:
            data['level'] = 1
        if 'daily_cards' not in data: 
            data['daily_cards'] = 0
            
        return data
    return None

async def get_user(user_id):
    return await run_sync(_get_user_sync, user_id)

def _get_users_details_sync(user_ids):
    results = []
    for uid in user_ids:
        u = _get_user_sync(uid)
        if u:
            results.append({'user_id': uid, 'first_name': u.get('first_name', 'Unknown')})
        else:
            results.append({'user_id': uid, 'first_name': 'Unknown'})
    return sorted(results, key=lambda x: natural_sort_key(x.get('first_name', '')))

async def get_users_details(user_ids):
    return await run_sync(_get_users_details_sync, user_ids)

def _get_all_users_sync():
    docs = db.collection('users').stream()
    return [doc.to_dict() for doc in docs]

async def get_all_users():
    return await run_sync(_get_all_users_sync)

def _create_user_sync(user_id, first_name, lang_code='en', referrer_id=None, username=None):
    doc_ref = db.collection('users').document(str(user_id))
    if doc_ref.get().exists:
        data = doc_ref.get().to_dict()
        return data, False
    else:
        data = {
            "user_id": str(user_id),
            "first_name": first_name,
            "username": username if username else "",  # Store Telegram username
            "lang_code": lang_code,
            "xp": 0.0,  # TX Coins (spendable currency)
            "total_xp": 0.0,  # XP for leveling
            "level": 1,  # Starting level
            "daily_cards": 0,
            "last_daily_reset": datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d'),
            "created_at": firestore.SERVER_TIMESTAMP,
            "referrer_id": str(referrer_id) if referrer_id else None,
            # Vocabulary AI rate limiting
            "vocab_requests_today": 0,
            "vocab_last_reset_date": datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d'),
            "vocab_requests_this_minute": 0,
            "vocab_minute_window_start": firestore.SERVER_TIMESTAMP
        }
        doc_ref.set(data)
        
        # Award referrer if exists
        if referrer_id:
            try:
                _add_tx_coins_sync(referrer_id, 5.0)  # Bonus TX coins for referral
            except:
                pass
            
            return data, True
            
    return data, False

async def create_user(user_id, first_name, lang_code='en', referrer_id=None, username=None):
    return await run_sync(_create_user_sync, user_id, first_name, lang_code, referrer_id, username)

# --- LEVEL SYSTEM ---
LEVEL_RANKS = {
    (1, 5): {"name": "Bronze Learner", "emoji": "🥉"},
    (6, 10): {"name": "Silver Scholar", "emoji": "🥈"},
    (11, 15): {"name": "Gold Master", "emoji": "🥇"},
    (16, 20): {"name": "Platinum Sage", "emoji": "💎"},
    (21, 30): {"name": "Diamond Legend", "emoji": "💠"},
    (31, 40): {"name": "Sapphire Wizard", "emoji": "🔮"},
    (41, 50): {"name": "Quantum Genius", "emoji": "⚡"},
    (51, 999): {"name": "Cosmic Teacher", "emoji": "🌟"}
}

def get_xp_for_level(level):
    """Calculate total XP required to reach a specific level."""
    total = 0
    for lvl in range(1, level):
        if lvl <= 10:
            total += 100
        elif lvl <= 20:
            total += 200
        elif lvl <= 30:
            total += 300
        else:
            total += 500
    return total

def get_level_from_xp(total_xp):
    """Calculate level from total XP."""
    level = 1
    while get_xp_for_level(level + 1) <= total_xp:
        level += 1
    return level

def get_level_info(level):
    """Get rank name, emoji, and XP to next level."""
    # Find rank
    rank_name = "Cosmic Teacher"
    rank_emoji = "🌟"
    for (min_lvl, max_lvl), rank_data in LEVEL_RANKS.items():
        if min_lvl <= level <= max_lvl:
            rank_name = rank_data["name"]
            rank_emoji = rank_data["emoji"]
            break
    
    # Calculate XP needed for next level
    current_xp_threshold = get_xp_for_level(level)
    next_xp_threshold = get_xp_for_level(level + 1)
    xp_for_next = next_xp_threshold - current_xp_threshold
    
    return {
        "rank_name": rank_name,
        "rank_emoji": rank_emoji,
        "xp_for_next_level": xp_for_next
    }

# --- DUAL CURRENCY SYSTEM ---
def _add_total_xp_sync(user_id, amount):
    """Add XP for leveling (never decreases)."""
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    
    if user_doc.exists:
        data = user_doc.to_dict()
        new_total_xp = data.get('total_xp', 0) + float(amount)
        new_level = get_level_from_xp(new_total_xp)
        
        updates = {
            "total_xp": new_total_xp,
            "level": new_level
        }
        
        # Also update streak since they gained XP (activity)
        streak_updates = _update_streak_logic_internal(data, data.get('streak', 0))
        updates.update(streak_updates)
        
        user_ref.update(updates)

async def add_total_xp(user_id, amount):
    """Add to total XP (for leveling)."""
    await run_sync(_add_total_xp_sync, user_id, amount)

def _add_tx_coins_sync(user_id, amount):
    """Add TX Coins (spendable currency)."""
    db.collection('users').document(str(user_id)).update({
        "xp": firestore.Increment(float(amount))  # Keep 'xp' field name for backward compatibility
    })

async def add_tx_coins(user_id, amount):
    """Add TX Coins (spendable currency)."""
    await run_sync(_add_tx_coins_sync, user_id, amount)

# Legacy function for backward compatibility
def _add_xp_sync(user_id, amount):
    """Legacy: adds to TX coins only."""
    _add_tx_coins_sync(user_id, amount)

async def add_xp(user_id, amount):
    """Legacy: adds to TX coins only. Use add_total_xp or add_tx_coins explicitly."""
    await run_sync(_add_xp_sync, user_id, amount)

# ==========================================
# BOT CONFIGURATION & AI MANAGEMENT
# ==========================================
def _get_bot_config_sync():
    """Get bot configuration including AI settings."""
    doc = db.collection('bot_config').document('main').get()
    if doc.exists:
        return doc.to_dict()
    # Default config
    return {
        'ai_enabled': True,
        'api_keys': [],
        'blocked_users': []
    }

async def get_bot_config():
    return await run_sync(_get_bot_config_sync)

def _toggle_ai_feature_sync(enabled: bool):
    """Enable or disable AI features globally."""
    db.collection('bot_config').document('main').set(
        {'ai_enabled': enabled}, merge=True
    )

async def toggle_ai_feature(enabled: bool):
    await run_sync(_toggle_ai_feature_sync, enabled)

def _add_api_key_sync(key: str):
    """Add a new Groq API key."""
    db.collection('bot_config').document('main').update({
        'api_keys': firestore.ArrayUnion([key])
    })

async def add_api_key(key: str):
    await run_sync(_add_api_key_sync, key)

def _remove_api_key_sync(key: str):
    """Remove a Groq API key."""
    db.collection('bot_config').document('main').update({
        'api_keys': firestore.ArrayRemove([key])
    })

async def remove_api_key(key: str):
    await run_sync(_remove_api_key_sync, key)

def _block_user_ai_sync(user_id: int):
    """Block a user from using AI features."""
    db.collection('bot_config').document('main').update({
        'blocked_users': firestore.ArrayUnion([user_id])
    })

async def block_user_ai(user_id: int):
    await run_sync(_block_user_ai_sync, user_id)

def _unblock_user_ai_sync(user_id: int):
    """Unblock a user from using AI features."""
    db.collection('bot_config').document('main').update({
        'blocked_users': firestore.ArrayRemove([user_id])
    })

async def unblock_user_ai(user_id: int):
    await run_sync(_unblock_user_ai_sync, user_id)

def _check_ai_limit_sync(user_id):
    """
    Check if user has reached daily AI limit (15 requests).
    Resets counter if it's a new day (UTC).
    Returns: True if allowed, False if limit reached.
    """
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if not doc.exists: return True # Should exist, but fail safe
    
    data = doc.to_dict()
    today_str = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
    
    last_date = data.get('ai_requests_date', '')
    current_count = data.get('ai_requests_today', 0)
    
    # Reset if new day
    if last_date != today_str:
        current_count = 0
        doc_ref.update({
            'ai_requests_date': today_str,
            'ai_requests_today': 0
        })
        
    # Check limit (40/day - Option A increase from 15)
    if current_count >= 40:
        return False
        
    # Increment
    doc_ref.update({
        'ai_requests_today': firestore.Increment(1),
        'ai_requests_date': today_str
    })
    return True

async def check_ai_limit(user_id):
    return await run_sync(_check_ai_limit_sync, user_id)

# --- GLOBAL AI USAGE TRACKING ---
def _track_ai_usage_sync(feature: str, tokens_used: int = 0):
    """Track global AI usage for analytics dashboard."""
    today_str = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
    doc_ref = db.collection('ai_stats').document(today_str)
    
    doc = doc_ref.get()
    if doc.exists:
        doc_ref.update({
            'total_requests': firestore.Increment(1),
            'total_tokens': firestore.Increment(tokens_used),
            f'features.{feature}': firestore.Increment(1)
        })
    else:
        doc_ref.set({
            'date': today_str,
            'total_requests': 1,
            'total_tokens': tokens_used,
            'features': {feature: 1}
        })

async def track_ai_usage(feature: str, tokens_used: int = 0):
    """Track global AI usage (async wrapper)."""
    await run_sync(_track_ai_usage_sync, feature, tokens_used)

def _get_ai_stats_sync(date_str: str = None):
    """Get AI usage stats for a specific day."""
    if date_str is None:
        date_str = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
    
    doc = db.collection('ai_stats').document(date_str).get()
    if doc.exists:
        return doc.to_dict()
    return {
        'date': date_str,
        'total_requests': 0,
        'total_tokens': 0,
        'features': {}
    }

async def get_ai_stats(date_str: str = None):
    """Get AI usage stats for a specific day (async)."""
    return await run_sync(_get_ai_stats_sync, date_str)

async def get_ai_stats_range(days: int = 7):
    """Get AI usage stats for past N days."""
    stats = []
    today = datetime.now(TASHKENT_TZ)
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        day_stats = await get_ai_stats(date_str)
        stats.append(day_stats)
    return stats

# --- THE SUPER FUNCTION (SPEED FIX) ---
def _process_card_action_sync(user_id, is_correct, xp_reward):
    """Handles Streak, Daily Count, and XP in ONE database call."""
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if not doc.exists: return False
    user = doc.to_dict()
    
    updates = {}
    today_str = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
    
    # 1. Update Active Date (Always)
    if user.get('last_active_date_str') != today_str:
        updates['last_active_date_str'] = today_str
        
    # 2. Daily Reset Logic (If needed)
    last_reset = user.get('last_daily_reset', '')
    current_daily_cards = user.get('daily_cards', 0)
    daily_goal_hit = user.get('daily_goal_hit', False)
    
    if last_reset != today_str:
        updates['last_daily_reset'] = today_str
        updates['daily_cards'] = 0
        updates['daily_goal_hit'] = False
        current_daily_cards = 0
        daily_goal_hit = False
    
    goal_just_hit = False
    
    # 3. Handle Success Logic (Only if correct/knew)
    if is_correct:
        # Increment Count
        new_total = current_daily_cards + 1
        updates['daily_cards'] = new_total
        
        # Add XP
        current_xp = user.get('xp', 0.0)
        current_total_xp = user.get('total_xp', 0.0)
        updates['xp'] = round(current_xp + float(xp_reward), 1)
        updates['total_xp'] = round(current_total_xp + float(xp_reward), 1)
        
        # Level Up Check
        new_total_xp = updates['total_xp']
        current_level = user.get('level', 1)
        level_up_threshold = get_xp_for_level(current_level + 1)
        
        if new_total_xp >= level_up_threshold:
            updates['level'] = current_level + 1
        
        # Check Goal
        if new_total >= 20 and not daily_goal_hit:
            updates['daily_goal_hit'] = True
            updates['xp'] = updates['xp'] + 2.0  # Bonus (reduced from 5.0)
            goal_just_hit = True

    # 4. FIXED STREAK LOGIC
    # Extracted to reusable helper function
    streak_updates = _update_streak_logic_internal(user, user.get('streak', 0))
    updates.update(streak_updates)

    # Execute all updates in ONE write
    if updates:
        doc_ref.update(updates)
        
    return goal_just_hit

def _update_streak_logic_internal(user_data, current_streak):
    """Helper to calculate streak updates based on last activity."""
    updates = {}
    today = datetime.now(TASHKENT_TZ).date()
    today_str = today.strftime('%Y-%m-%d')
    
    last_active_str = user_data.get('last_active_date_str', '')
    freeze_count = user_data.get('streak_freeze_count', 0)
    
    if last_active_str == today_str:
        return {} # Already active today
        
    if not last_active_str:
         updates['streak'] = 1
    else:
        try:
            last_date = datetime.strptime(last_active_str, '%Y-%m-%d').date()
            days_diff = (today - last_date).days
            
            if days_diff == 1:
                updates['streak'] = current_streak + 1
            elif days_diff > 1:
                if freeze_count > 0:
                    updates['streak_freeze_count'] = freeze_count - 1
                else:
                    updates['streak'] = 1
        except:
            updates['streak'] = 1
    
    updates['last_active_date_str'] = today_str
    updates['dates_practiced'] = firestore.ArrayUnion([today_str])
    return updates

async def process_card_action(user_id, is_correct, xp_reward):
    return await run_sync(_process_card_action_sync, user_id, is_correct, xp_reward)

# Keep this for manual streak updates if needed, but process_card_action handles it now
def _update_streak_sync(user_id):
    today_str = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
    db.collection('users').document(str(user_id)).update({"last_active_date_str": today_str})

async def update_streak(user_id):
    await run_sync(_update_streak_sync, user_id)

def _get_leaderboard_sync():
    # Get top users by total_xp (not TX coins)
    docs = db.collection('users').order_by('total_xp', direction=firestore.Query.DESCENDING).limit(50).stream()
    # Filter out admins from leaderboard
    results = []
    for doc in docs:
        user_data = doc.to_dict()
        user_id = user_data.get('user_id', '')
        # Skip admins
        if str(user_id) not in ADMIN_IDS:
            results.append(user_data)
        # Stop once we have 10 non-admin users
        if len(results) >= 10:
            break
    return results  # Already sorted by total_xp from query

async def get_leaderboard():
    return await run_sync(_get_leaderboard_sync)

# --- FOLDERS ---
def _create_book_sync(user_id, folder_name, parent_id):
    ref = db.collection('folders').document()
    
    # Determine if this is an official library folder or user's personal folder
    # Only set is_official=True if admin creates under official library (parent is official)
    # For now, all user-created folders via this function are personal (folder_type='user')
    is_admin = str(user_id) in ADMIN_IDS
    
    data = {
        "folder_id": ref.id,
        "owner_id": str(user_id),
        "parent_id": parent_id, 
        "folder_name": folder_name,
        "set_count": 0,
        "is_official": False,  # User-created folders are never official
        "folder_type": "user",  # Explicit type prevents showing in admin queries
        "created_at": firestore.SERVER_TIMESTAMP
    }
    ref.set(data)
    return ref.id

async def create_book(user_id, folder_name, parent_id=None):
    return await run_sync(_create_book_sync, user_id, folder_name, parent_id)

def _create_official_folder_sync(admin_id, folder_name, parent_id):
    """Create an official library folder (admin-only)."""
    if str(admin_id) not in ADMIN_IDS:
        return None  # Safety check
    
    ref = db.collection('folders').document()
    data = {
        "folder_id": ref.id,
        "owner_id": str(admin_id),
        "parent_id": parent_id, 
        "folder_name": folder_name,
        "set_count": 0,
        "is_official": True,
        "folder_type": "official",
        "created_at": firestore.SERVER_TIMESTAMP
    }
    ref.set(data)
    return ref.id

async def create_official_folder(admin_id, folder_name, parent_id=None):
    """Create an official library folder (admin-only)."""
    return await run_sync(_create_official_folder_sync, admin_id, folder_name, parent_id)

def _update_folder_description_sync(folder_id, description):
    """Update a folder's description."""
    doc_ref = db.collection('folders').document(folder_id)
    doc_ref.update({'description': description})
    return True

async def update_folder_description(folder_id, description):
    """Update a folder's description (async)."""
    return await run_sync(_update_folder_description_sync, folder_id, description)

def _get_user_folders_sync(user_id, parent_id):
    query = db.collection('folders').where('owner_id', '==', str(user_id))
    if parent_id:
        query = query.where('parent_id', '==', parent_id)
    else:
        query = query.where('parent_id', '==', None)
    
    docs = query.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['folder_id'] = doc.id
        results.append(d)
    return sorted(results, key=lambda x: natural_sort_key(x.get('folder_name', '')))

async def get_user_folders(user_id, parent_id=None):
    return await run_sync(_get_user_folders_sync, user_id, parent_id)

def _get_admin_folders_sync(parent_id=None, folder_type=None):
    """Get admin folders, optionally filtered by folder_type."""
    query = db.collection('folders').where('is_official', '==', True)
    if parent_id:
        query = query.where('parent_id', '==', parent_id)
    else:
        query = query.where('parent_id', '==', None)
    
    docs = query.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['folder_id'] = doc.id
        
        # Filter by folder_type if specified
        if folder_type:
            if folder_type == 'official':
                # Include folders with folder_type='official' OR no folder_type (legacy)
                current_type = d.get('folder_type')
                if current_type == 'official' or current_type is None:
                    results.append(d)
            else:
                # For other types (e.g., 'community'), exact match required
                if d.get('folder_type') == folder_type:
                    results.append(d)
        else:
            # No filter - include all admin folders
            results.append(d)
    
    return sorted(results, key=lambda x: natural_sort_key(x.get('folder_name', '')))

async def get_admin_folders(parent_id=None, folder_type=None):
    return await run_sync(_get_admin_folders_sync, parent_id, folder_type)

def _get_folder_sync(folder_id):
    doc = db.collection('folders').document(folder_id).get()
    if doc.exists:
        d = doc.to_dict()
        d['folder_id'] = doc.id
        return d
    return None

async def get_folder(folder_id):
    return await run_sync(_get_folder_sync, folder_id)

def _delete_folder_sync(folder_id):
    # 1. Get folder details to find parent
    folder_ref = db.collection('folders').document(folder_id)
    folder_doc = folder_ref.get()
    if not folder_doc.exists: return
    
    folder_data = folder_doc.to_dict()
    parent_id = folder_data.get('parent_id')
    owner_id = folder_data.get('owner_id')
    
    # 2. Find or create "Untitled" folder in the same location
    untitled_ref = None
    
    # Search for existing "Untitled" folder in same parent
    query = db.collection('folders').where('owner_id', '==', owner_id).where('folder_name', '==', 'Untitled')
    if parent_id:
        query = query.where('parent_id', '==', parent_id)
    else:
        query = query.where('parent_id', '==', None)
        
    results = list(query.stream())
    
    if results:
        untitled_ref = results[0].reference
    else:
        # Create new Untitled folder
        new_folder_ref = db.collection('folders').document()
        new_folder_ref.set({
            "owner_id": owner_id,
            "folder_name": "Untitled",
            "parent_id": parent_id,
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_public": folder_data.get('is_public', False),
            "folder_type": folder_data.get('folder_type', None),
            "set_count": 0
        })
        untitled_ref = new_folder_ref

    # 3. Move all sets to Untitled folder
    sets = db.collection('sets').where('folder_id', '==', folder_id).stream()
    batch = db.batch()
    count = 0
    
    for s in sets:
        batch.update(s.reference, {"folder_id": untitled_ref.id})
        count += 1
        
    # Update set count for Untitled folder
    batch.update(untitled_ref, {"set_count": firestore.Increment(count)})
    
    # 4. Delete the original folder
    batch.delete(folder_ref)
    batch.commit()

async def delete_folder(folder_id):
    await run_sync(_delete_folder_sync, folder_id)

def _move_folder_sync(folder_id, new_parent_id):
    """Move a folder to a new parent location."""
    db.collection('folders').document(folder_id).update({
        "parent_id": new_parent_id
    })

async def move_folder(folder_id, new_parent_id):
    await run_sync(_move_folder_sync, folder_id, new_parent_id)

# --- PUBLIC REQUESTS ---
def _create_public_request_sync(user_id, folder_id):
    # Check if request already exists (FIXED: convert stream to list)
    existing = list(db.collection('public_requests').where('folder_id', '==', folder_id).limit(1).stream())
    if existing:
        print(f"Public request already exists for folder {folder_id}")
        return False
    
    user = _get_user_sync(user_id)
    folder = _get_folder_sync(folder_id)
    
    if not folder:
        print(f"Folder {folder_id} not found")
        return False
    
    data = {
        "user_id": str(user_id),
        "user_name": user.get('first_name', 'Unknown'),
        "folder_id": folder_id,
        "folder_name": folder.get('folder_name', 'Untitled'),
        "created_at": firestore.SERVER_TIMESTAMP
    }
    db.collection('public_requests').add(data)
    print(f"✅ Public request created for folder {folder_id} by user {user_id}")
    return True

async def create_public_request(user_id, folder_id):
    return await run_sync(_create_public_request_sync, user_id, folder_id)

def _get_public_requests_sync():
    docs = db.collection('public_requests').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['request_id'] = doc.id
        results.append(d)
    return sorted(results, key=lambda x: natural_sort_key(x.get('set_name', '')))

async def get_public_requests():
    return await run_sync(_get_public_requests_sync)

def _approve_public_request_sync(request_id):
    req_ref = db.collection('public_requests').document(request_id)
    req_doc = req_ref.get()
    if not req_doc.exists:
        return False
    data = req_doc.to_dict()
    folder_id = data['folder_id']
    
    # Check if folder still exists
    folder_ref = db.collection('folders').document(folder_id)
    folder_doc = folder_ref.get()
    
    if not folder_doc.exists:
        # Folder was deleted, clean up request
        db.collection('public_requests').document(request_id).delete()
        return False

    # Make folder official (for admin visibility) and set as COMMUNITY (not fully official yet)
    folder_ref.update({
        "is_official": True,         # Required for get_admin_folders query
        "folder_type": "community",  # Distinguishes from official books
        "is_public": True            # Make visible to all users
    })
    
    # Mark all sets in folder as public
    sets_in_folder = db.collection('sets').where('folder_id', '==', folder_id).stream()
    batch = db.batch()
    for s in sets_in_folder:
        batch.update(s.reference, {"is_public": True})
    batch.commit()
    
    db.collection('public_requests').document(request_id).delete()
    return True

async def approve_public_request(request_id):
    return await run_sync(_approve_public_request_sync, request_id)

def _reject_public_request_sync(request_id):
    try:
        db.collection('public_requests').document(request_id).delete()
        return True
    except Exception:
        return False

async def reject_public_request(request_id):
    return await run_sync(_reject_public_request_sync, request_id)

def _check_request_exists_sync(folder_id):
    """Check if a pending request exists for this folder."""
    docs = db.collection('public_requests').where('folder_id', '==', folder_id).limit(1).stream()
    for doc in docs:
        return doc.id
    return None

async def check_request_exists(folder_id):
    return await run_sync(_check_request_exists_sync, folder_id)

def _clean_invalid_requests_sync():
    """Remove requests for deleted folders."""
    docs = db.collection('public_requests').stream()
    deleted_count = 0
    batch = db.batch()
    
    for doc in docs:
        data = doc.to_dict()
        folder_id = data.get('folder_id')
        if not folder_id:
            batch.delete(doc.reference)
            deleted_count += 1
            continue
            
        folder_ref = db.collection('folders').document(folder_id)
        if not folder_ref.get().exists:
            batch.delete(doc.reference)
            deleted_count += 1
            
    if deleted_count > 0:
        batch.commit()
    return deleted_count

async def clean_invalid_requests():
    return await run_sync(_clean_invalid_requests_sync)

def _move_to_official_sync(folder_id):
    """Move a community folder to official library."""
    db.collection('folders').document(folder_id).update({
        "folder_type": "official"
    })

async def move_to_official(folder_id):
    await run_sync(_move_to_official_sync, folder_id)

def _revert_to_community_sync(folder_id):
    """Move an official folder back to community for review/editing."""
    db.collection('folders').document(folder_id).update({
        "folder_type": "community"
    })

async def revert_to_community(folder_id):
    """Move an official folder back to community for review/editing."""
    await run_sync(_revert_to_community_sync, folder_id)

# --- MOVE SET ---
def _move_set_sync(set_id, new_folder_id):
    """Move a set to a different folder, updating folder set_counts."""
    set_ref = db.collection('sets').document(set_id)
    set_doc = set_ref.get()
    
    if not set_doc.exists:
        return False
    
    old_folder_id = set_doc.to_dict().get('folder_id')
    
    # Update the set's folder_id
    set_ref.update({'folder_id': new_folder_id})
    
    # Decrement old folder's set_count (if it exists)
    if old_folder_id:
        try:
            db.collection('folders').document(old_folder_id).update({
                'set_count': firestore.Increment(-1)
            })
        except Exception:
            pass  # Old folder might not exist
    
    # Increment new folder's set_count (if it exists)
    if new_folder_id:
        try:
            db.collection('folders').document(new_folder_id).update({
                'set_count': firestore.Increment(1)
            })
        except Exception:
            pass  # New folder might not exist
    
    return True

async def move_set(set_id, new_folder_id):
    """Move a set to a different folder."""
    return await run_sync(_move_set_sync, set_id, new_folder_id)

# --- SETS ---
def _create_set_sync(user_id, folder_id, set_name, is_public, cards_list):
    set_ref = db.collection('sets').document()
    set_id = set_ref.id
    set_data = {
        "set_id": set_id,
        "owner_id": str(user_id),
        "folder_id": folder_id,
        "set_name": set_name,
        "is_public": is_public,
        "card_count": len(cards_list),
        "created_at": firestore.SERVER_TIMESTAMP
    }
    set_ref.set(set_data)
    batch = db.batch()
    for card in cards_list:
        card_ref = db.collection('sets').document(set_id).collection('cards').document()
        card_data = {
            "card_id": card_ref.id,
            "term": card['term'],
            "definition": card['def'],
            "created_at": firestore.SERVER_TIMESTAMP,
            # SM-2 Default Fields
            "sm2_n": 0,
            "sm2_ef": 2.5,
            "sm2_interval": 0,
            "next_review": None
        }
        batch.set(card_ref, card_data)
    batch.commit()
    if folder_id:
        db.collection('folders').document(folder_id).update({"set_count": firestore.Increment(1)})
    return set_id

async def create_set(user_id, folder_id, set_name, is_public, cards_list):
    return await run_sync(_create_set_sync, user_id, folder_id, set_name, is_public, cards_list)

def _rename_set_sync(set_id, new_name):
    """Rename a set."""
    db.collection('sets').document(set_id).update({'set_name': new_name})
    return True

async def rename_set(set_id, new_name):
    """Rename a set (async)."""
    return await run_sync(_rename_set_sync, set_id, new_name)

def _add_card_to_set_sync(set_id, term, definition):
    """Add a single card to an existing set."""
    set_ref = db.collection('sets').document(set_id)
    set_doc = set_ref.get()
    
    if not set_doc.exists:
        return False
    
    # Add the card
    card_ref = set_ref.collection('cards').document()
    card_data = {
        "card_id": card_ref.id,
        "term": term,
        "definition": definition,
        "created_at": firestore.SERVER_TIMESTAMP,
        "sm2_n": 0,
        "sm2_ef": 2.5,
        "sm2_interval": 0,
        "next_review": None
    }
    card_ref.set(card_data)
    
    # Update card count
    set_ref.update({"card_count": firestore.Increment(1)})
    return True

async def add_card_to_set(set_id, term, definition):
    """Add a single card to an existing set (async)."""
    return await run_sync(_add_card_to_set_sync, set_id, term, definition)

def _get_set_sync(set_id):
    """Get a single set's details."""
    doc = db.collection('sets').document(set_id).get()
    if doc.exists:
        data = doc.to_dict()
        data['set_id'] = doc.id
        return data
    return None

async def get_set(set_id):
    """Async wrapper for getting a set."""
    return await run_sync(_get_set_sync, set_id)

def _get_set_cards_sync(set_id):
    """Get all cards for a specific set."""
    docs = db.collection('sets').document(set_id).collection('cards').stream()
    cards = []
    for doc in docs:
        d = doc.to_dict()
        d['card_id'] = doc.id
        cards.append(d)
    return cards

async def get_set_cards(set_id):
    return await run_sync(_get_set_cards_sync, set_id)

def _add_cards_to_set_sync(set_id, cards_list):
    """Add new cards to an existing set"""
    batch = db.batch()
    for card in cards_list:
        card_ref = db.collection('sets').document(set_id).collection('cards').document()
        card_data = {
            "card_id": card_ref.id,
            "term": card['term'],
            "definition": card['def'],
            "created_at": firestore.SERVER_TIMESTAMP,
            # SM-2 Default Fields
            "sm2_n": 0,
            "sm2_ef": 2.5,
            "sm2_interval": 0,
            "next_review": None
        }
        batch.set(card_ref, card_data)
    batch.commit()
    
    # Update card count
    db.collection('sets').document(set_id).update({
        "card_count": firestore.Increment(len(cards_list))
    })

async def add_cards_to_set(set_id, cards_list):
    return await run_sync(_add_cards_to_set_sync, set_id, cards_list)

def _get_user_sets_sync(user_id, folder_id=None, recursive=False):
    query = db.collection('sets').where('owner_id', '==', str(user_id))
    
    if not recursive:
        if folder_id:
            query = query.where('folder_id', '==', folder_id)
        else:
            query = query.where('folder_id', '==', None)
        
    docs = query.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['set_id'] = doc.id
        if 'set_name' not in d: d['set_name'] = "Untitled"
        results.append(d)
    return sorted(results, key=lambda x: natural_sort_key(x.get('set_name', '')))

async def get_user_sets(user_id, folder_id=None, recursive=False):
    return await run_sync(_get_user_sets_sync, user_id, folder_id, recursive)

def _get_public_user_sets_sync():
    docs = db.collection('sets').where('is_public', '==', True).stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        if d['owner_id'] not in ADMIN_IDS:
            d['set_id'] = doc.id
            if 'set_name' not in d: d['set_name'] = "Untitled"
            results.append(d)
    return sorted(results, key=lambda x: natural_sort_key(x.get('set_name', '')))

async def get_public_user_sets():
    return await run_sync(_get_public_user_sets_sync)

def _get_all_sets_admin_sync(limit=10, offset=0):
    """Get all sets (private & public) for admin management."""
    docs = db.collection('sets').order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).offset(offset).stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['set_id'] = doc.id
        if 'set_name' not in d: d['set_name'] = "Untitled"
        results.append(d)
    return sorted(results, key=lambda x: natural_sort_key(x.get('set_name', '')))

async def get_all_sets_admin(limit=10, offset=0):
    return await run_sync(_get_all_sets_admin_sync, limit, offset)

def _get_sets_in_folder_sync(folder_id):
    docs = db.collection('sets').where('folder_id', '==', folder_id).stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['set_id'] = doc.id
        results.append(d)
    return sorted(results, key=lambda x: natural_sort_key(x.get('set_name', '')))

async def get_sets_in_folder(folder_id):
    return await run_sync(_get_sets_in_folder_sync, folder_id)

def _delete_set_sync(set_id):
    # 1. Update parent folder count if exists
    set_ref = db.collection('sets').document(set_id)
    set_doc = set_ref.get()
    
    if set_doc.exists:
        fid = set_doc.to_dict().get('folder_id')
        if fid:
            # Check if folder still exists before updating
            if db.collection('folders').document(fid).get().exists:
                 db.collection('folders').document(fid).update({"set_count": firestore.Increment(-1)})

    # 2. Delete all cards in subcollection
    cards = set_ref.collection('cards').stream()
    batch = db.batch()
    for c in cards:
        batch.delete(c.reference)
    batch.commit()
    
    # 3. Delete the set document itself
    set_ref.delete()

async def delete_set(set_id):
    return await run_sync(_delete_set_sync, set_id)

def _toggle_set_privacy_sync(set_id):
    """Toggle the is_public status of a set."""
    set_ref = db.collection('sets').document(set_id)
    doc = set_ref.get()
    if doc.exists:
        is_public = doc.to_dict().get('is_public', False)
        set_ref.update({'is_public': not is_public})
        return not is_public
    return False

async def toggle_set_privacy(set_id):
    return await run_sync(_toggle_set_privacy_sync, set_id)

def _update_card_sync(card_id, term=None, definition=None):
    """Update card term and/or definition."""
    update_data = {}
    if term is not None:
        update_data['term'] = term
    if definition is not None:
        update_data['definition'] = definition
    
    if update_data:
        db.collection('cards').document(card_id).update(update_data)

async def update_card(card_id, term=None, definition=None):
    await run_sync(_update_card_sync, card_id, term, definition)

def _delete_card_sync(card_id):
    """Delete a card from a set."""
    # Note: This attempts to delete from a root 'cards' collection which might not exist
    # if cards are only in subcollections.
    # To delete properly, you usually need the set_id, or do a collection group query.
    # For now, assuming direct ID access works or this is legacy.
    try:
        db.collection('cards').document(card_id).delete()
    except:
        pass

async def delete_card(card_id):
    await run_sync(_delete_card_sync, card_id)

# --- EXPLORE ---
def _search_public_sets_sync(query_text):
    """
    Search for public sets by name.
    Also includes folder names in search for better discoverability.
    """
    # Get all public sets ordered by newest first
    docs = db.collection('sets')\
        .where('is_public', '==', True)\
        .order_by('created_at', direction=firestore.Query.DESCENDING)\
        .limit(100)\
        .stream()
    
    results = []
    q = query_text.lower()
    
    for doc in docs:
        d = doc.to_dict()
        set_name = d.get('set_name', '').lower()
        
        # Get folder name for better search
        folder_id = d.get('folder_id')
        folder_name = ''
        if folder_id:
            try:
                folder_doc = db.collection('folders').document(folder_id).get()
                if folder_doc.exists:
                    folder_name = folder_doc.to_dict().get('folder_name', '').lower()
            except:
                pass
        
        # Match query against BOTH set name AND folder name
        if q in set_name or q in folder_name:
            d['set_id'] = doc.id
            if 'set_name' not in d: d['set_name'] = "Untitled"
            if 'card_count' not in d: d['card_count'] = 0
            
            # Add folder name for display
            if folder_name:
                d['folder_name'] = folder_doc.to_dict().get('folder_name', '')
            
            results.append(d)
            
            # Log for debugging
            print(f"🔍 Search match: {d['set_name']} (folder: {folder_name or 'none'})")
    
    print(f"📊 Total public sets found: {len(results)} out of query")
    return results[:20]  # Return top 20 matches

async def search_public_sets(query_text):
    return await run_sync(_search_public_sets_sync, query_text)

def _search_users_sync(query):
    """Search users by first_name, user_id, or username (admin only)."""
    query = query.strip()
    results = []
    
    # Try exact ID match first (fastest)
    if query.isdigit():
        doc = db.collection('users').document(query).get()
        if doc.exists:
            user_data = doc.to_dict()
            user_data['user_id'] = doc.id
            results.append(user_data)
            return results  # Return immediately if ID match
    
    # Search by first_name (case-insensitive, partial match)
    all_users = db.collection('users').limit(200).stream()  # Limit for performance
    query_lower = query.lower()
    
    for doc in all_users:
        user_data = doc.to_dict()
        first_name = user_data.get('first_name', '').lower()
        username = user_data.get('username', '').lower()
        
        # Match by first_name or username
        if query_lower in first_name or query_lower in username:
            user_data['user_id'] = doc.id
            results.append(user_data)
            
            # Limit results to 10
            if len(results) >= 10:
                break
    
    return sorted(results, key=lambda x: natural_sort_key(x.get('set_name', '')))

async def search_users(query):
    """Search users by name, ID, or username."""
    return await run_sync(_search_users_sync, query)

# --- ADMIN ---
def _get_global_stats_sync():
    users = len(list(db.collection('users').stream()))
    sets = len(list(db.collection('sets').stream()))
    return {"users": users, "sets": sets}

async def get_global_stats():
    return await run_sync(_get_global_stats_sync)

# --- NOTIFICATION BACKOFF MANAGEMENT ---
async def update_notification_state(user_id, new_backoff_level):
    """Update user's notification backoff state after sending notification."""
    def _update_sync(user_id, level):
        db.collection('users').document(str(user_id)).update({
            "last_notification_sent": firestore.SERVER_TIMESTAMP,
            "notification_backoff_level": min(level, 4)  # Cap at level 4 (24h max)
        })
    await run_sync(_update_sync, user_id, new_backoff_level)

def _reset_notification_backoff_sync(user_id):
    db.collection('users').document(str(user_id)).update({
        "notification_backoff_level": 0
    })

async def reset_notification_backoff(user_id):
    """Reset notification_backoff_level to 0 when user practices."""
    await run_sync(_reset_notification_backoff_sync, user_id)

# === STREAK FREEZE PURCHASE ===
def _purchase_streak_freeze_sync(user_id):
    """Purchase a streak freeze for 350 TX."""
    user_ref = db.collection('users').document(str(user_id))
    user = user_ref.get().to_dict()
    
    if not user:
        return False
    
    current_tx = user.get('xp', 0)
    if current_tx < 350:
        return False  # Not enough TX
    
    # Deduct TX and add freeze
    user_ref.update({
        'xp': round(current_tx - 350, 1),
        'streak_freeze_count': user.get('streak_freeze_count', 0) + 1
    })
    return True

async def purchase_streak_freeze(user_id):
    """Purchase a streak freeze for 350 TX."""
    return await run_sync(_purchase_streak_freeze_sync, user_id)

def _ban_user_sync(user_id):
    db.collection('users').document(str(user_id)).update({"is_banned": True})

async def ban_user(user_id):
    await run_sync(_ban_user_sync, user_id)

def _unban_user_sync(user_id):
    db.collection('users').document(str(user_id)).update({"is_banned": False})

async def unban_user(user_id):
    await run_sync(_unban_user_sync, user_id)

def _get_banned_users_sync():
    docs = db.collection('users').where('is_banned', '==', True).stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        results.append({'user_id': doc.id, 'first_name': d.get('first_name', 'Unknown')})
    return sorted(results, key=lambda x: natural_sort_key(x.get('set_name', '')))

async def get_banned_users():
    return await run_sync(_get_banned_users_sync)

def _delete_user_data_sync(user_id):
    sets = _get_user_sets_sync(user_id, recursive=True)
    for s in sets:
        _delete_set_sync(s['set_id'])
    db.collection('users').document(str(user_id)).delete()

async def delete_user_data(user_id):
    await run_sync(_delete_user_data_sync, user_id)

# --- SM-2 & PROGRESS ---
def _update_card_progress_sync(user_id, set_id, card_id, quality):
    # We store progress in a subcollection of the USER, not the card
    # users/{uid}/progress/{card_id}
    # This allows multiple users to study the same public set
    
    ref = db.collection('users').document(str(user_id)).collection('progress').document(card_id)
    doc = ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        n = data.get('n', 0)
        ef = data.get('ef', 2.5)
        interval = data.get('interval', 0)
    else:
        n = 0
        ef = 2.5
        interval = 0
        
    # Enhanced SM-2 Algorithm with 4 difficulty levels
    # Quality: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    
    if quality == 1:  # Again - Forgot completely
        n = 0
        interval = 0.001  # ~1 minute
        ef = max(1.3, ef - 0.2)  # Decrease ease factor
    elif quality == 2:  # Hard - Difficult
        if n == 0:
            interval = 0.007  # ~10 minutes
        else:
            interval = max(0.007, interval * 1.2)
        n += 1
        ef = max(1.3, ef - 0.15)
    elif quality == 3:  # Good - OK
        if n == 0:
            interval = 1  # 1 day
        elif n == 1:
            interval = 2  # 2 days
        else:
            interval = int(interval * ef)
        n += 1
        ef = ef + 0.1
        if ef > 2.5: ef = 2.5
    elif quality == 4:  # Easy - Perfect
        if n == 0:
            interval = 3  # 3 days
        elif n == 1:
            interval = 5  # 5 days
        else:
            interval = int(interval * ef * 1.3)  # Boost for easy cards
        n += 1
        ef = ef + 0.15
        if ef > 2.5: ef = 2.5
    elif quality == 5: # Mastered - Effectively retired
        # Set a very long interval, effectively retiring the card from frequent review
        interval = 365 # 365 days
        n += 1 # Increment n, but it won't affect interval much due to fixed value
        ef = 2.5 # Max out ease factor
    else:
        # Fallback for invalid quality
        n = 0
        interval = 1
        
    next_review = datetime.now(TASHKENT_TZ) + timedelta(days=interval)
    
    update_data = {
        "set_id": set_id, # Link back to set
        "n": n,
        "ef": ef,
        "interval": interval,
        "next_review": next_review,
        "last_reviewed": firestore.SERVER_TIMESTAMP
    }
    ref.set(update_data)

async def update_card_progress(user_id, set_id, card_id, quality):
    await run_sync(_update_card_progress_sync, user_id, set_id, card_id, quality)

def _get_due_cards_sync(user_id):
    now = datetime.now(TASHKENT_TZ)
    # Get all progress items where next_review <= now (using filter to avoid deprecation warning)
    # Note: Firestore queries can't compare None, so cards with next_review=None won't match
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
        docs = db.collection('users').document(str(user_id)).collection('progress')\
                 .where(filter=FieldFilter('next_review', '<=', now)).limit(50).stream()
    except ImportError:
        # Fallback for older Firestore versions
        docs = db.collection('users').document(str(user_id)).collection('progress')\
                 .where('next_review', '<=', now).limit(50).stream()
    
    # OPTIMIZATION: Group by set_id to batch queries
    # Instead of 1 query per card (N+1 problem), do 1 query per set
    cards_by_set = {}  # {set_id: [card_ids]}
    
    for d in docs:
        data = d.to_dict()
        set_id = data.get('set_id')
        card_id = d.id
        
        if set_id:
            if set_id not in cards_by_set:
                cards_by_set[set_id] = []
            cards_by_set[set_id].append(card_id)
    
    # Fetch all cards for each set (1 query per set instead of 1 per card!)
    due_cards = []
    for set_id, card_ids in cards_by_set.items():
        # Fetch all cards from this set at once
        cards_docs = db.collection('sets').document(set_id).collection('cards').stream()
        for c_doc in cards_docs:
            if c_doc.id in card_ids:
                c_data = c_doc.to_dict()
                c_data['card_id'] = c_doc.id
                c_data['set_id'] = set_id
                due_cards.append(c_data)
    
    return due_cards

async def get_due_cards(user_id):
    return await run_sync(_get_due_cards_sync, user_id)

# --- COPY SET ---
def _copy_set_to_user_sync(user_id, source_set_id):
    source = _get_set_sync(source_set_id)
    if not source: return None
    
    cards = _get_set_cards_sync(source_set_id)
    
    # Create new set for user
    # Format cards list for create_set
    formatted_cards = [{'term': c['term'], 'def': c['definition']} for c in cards]
    
    new_id = _create_set_sync(user_id, None, f"Copy of {source['set_name']}", False, formatted_cards)
    return new_id

async def copy_set_to_user(user_id, source_set_id):
    return await run_sync(_copy_set_to_user_sync, user_id, source_set_id)

# --- CUSTOM QUIZ BUILDER DB ---
def _add_custom_quiz_sync(user_id, title, questions, timer=30):
    """
    questions: list of dicts:
    [
      {
        'text': '...',
        'options': ['Correct', 'Wrong1', ...], 
        'correct_index': 0  (Enforced by builder logic)
      }
    ]
    """
    doc_ref = db.collection('custom_quizzes').document()
    quiz_data = {
        'id': doc_ref.id,
        'creator_id': str(user_id),
        'title': title,
        'questions': questions,
        'timer': timer,  # Quiz timer in seconds
        'created_at': firestore.SERVER_TIMESTAMP,
        'plays': 0
    }
    doc_ref.set(quiz_data)
    return doc_ref.id

async def add_custom_quiz(user_id, title, questions, timer=30):
    return await run_sync(_add_custom_quiz_sync, user_id, title, questions, timer)

def _get_custom_quiz_sync(quiz_id):
    doc = db.collection('custom_quizzes').document(quiz_id).get()
    if doc.exists:
        return doc.to_dict()
    return None

async def get_custom_quiz(quiz_id):
    return await run_sync(_get_custom_quiz_sync, quiz_id)

def _get_user_custom_quizzes_sync(user_id):
    # Retrieve quizzes created by this user
    # Remove order_by to avoid index requirement
    docs = db.collection('custom_quizzes').where('creator_id', '==', str(user_id)).stream()
    quizzes = [doc.to_dict() for doc in docs]
    # Client-side sorting (newest first)
    quizzes.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    return quizzes

async def get_user_custom_quizzes(user_id):
    return await run_sync(_get_user_custom_quizzes_sync, user_id)

def _delete_custom_quiz_sync(quiz_id):
    db.collection('custom_quizzes').document(quiz_id).delete()

async def delete_custom_quiz(quiz_id):
    return await run_sync(_delete_custom_quiz_sync, quiz_id)

def _increment_quiz_plays_sync(quiz_id):
    ref = db.collection('custom_quizzes').document(quiz_id)
    ref.update({'plays': firestore.Increment(1)})

async def increment_quiz_plays(quiz_id):
    await run_sync(_increment_quiz_plays_sync, quiz_id)

def _update_custom_quiz_title_sync(quiz_id, new_title):
    db.collection('custom_quizzes').document(quiz_id).update({'title': new_title})

async def update_custom_quiz_title(quiz_id, new_title):
    await run_sync(_update_custom_quiz_title_sync, quiz_id, new_title)

def _add_question_to_quiz_sync(quiz_id, new_question):
    # new_question is dict: {text, options, correct_index}
    ref = db.collection('custom_quizzes').document(quiz_id)
    ref.update({'questions': firestore.ArrayUnion([new_question])})

async def add_question_to_quiz(quiz_id, new_question):
    await run_sync(_add_question_to_quiz_sync, quiz_id, new_question)

# --- FAVORITES SYSTEM ---
def _toggle_favorite_sync(user_id, item_type, item_id):
    """Toggle favorite status. item_type: 'set' or 'folder'"""
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    if not user_doc.exists:
        return False
    
    favorites = user_doc.to_dict().get('favorites', [])
    fav_key = f"{item_type}_{item_id}"
    
    if fav_key in favorites:
        favorites.remove(fav_key)
        is_now_fav = False
    else:
        favorites.append(fav_key)
        is_now_fav = True
    
    user_ref.update({'favorites': favorites})
    return is_now_fav

async def toggle_favorite(user_id, item_type, item_id):
    return await run_sync(_toggle_favorite_sync, user_id, item_type, item_id)

def _get_favorites_sync(user_id):
    """Get list of favorite item keys"""
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    if not user_doc.exists:
        return []
    return user_doc.to_dict().get('favorites', [])

async def get_favorites(user_id):
    return await run_sync(_get_favorites_sync, user_id)

def _is_favorite_sync(user_id, item_type, item_id):
    fav_key = f"{item_type}_{item_id}"
    favorites = _get_favorites_sync(user_id)
    return fav_key in favorites

async def is_favorite(user_id, item_type, item_id):
    return await run_sync(_is_favorite_sync, user_id, item_type, item_id)

# --- QUIZ RATINGS ---
def _rate_quiz_sync(user_id, quiz_id, stars):
    """Rate a quiz (1-5 stars). Updates average rating."""
    quiz_ref = db.collection('custom_quizzes').document(quiz_id)
    quiz_doc = quiz_ref.get()
    
    if not quiz_doc.exists:
        return
    
    quiz_data = quiz_doc.to_dict()
    ratings = quiz_data.get('ratings', {})
    
    # Store individual rating
    ratings[str(user_id)] = stars
    
    # Calculate average
    all_ratings = list(ratings.values())
    avg = sum(all_ratings) / len(all_ratings) if all_ratings else 0
    
    quiz_ref.update({
        'ratings': ratings,
        'avg_rating': round(avg, 1),
        'rating_count': len(all_ratings)
    })

async def rate_quiz(user_id, quiz_id, stars):
    await run_sync(_rate_quiz_sync, user_id, quiz_id, stars)

def _get_quiz_rating_sync(quiz_id):
    """Get quiz rating info."""
    doc = db.collection('custom_quizzes').document(quiz_id).get()
    if doc.exists:
        data = doc.to_dict()
        return {
            'avg': data.get('avg_rating', 0),
            'count': data.get('rating_count', 0)
        }
    return {'avg': 0, 'count': 0}

async def get_quiz_rating(quiz_id):
    return await run_sync(_get_quiz_rating_sync, quiz_id)

# --- BADGE SYSTEM ---
BADGE_DEFINITIONS = {
    'creator': {'emoji': '🎨', 'name': 'Creator', 'desc': 'Created 5+ quizzes'},
    'player': {'emoji': '🎮', 'name': 'Player', 'desc': 'Played 20+ quizzes'},
    'perfect': {'emoji': '💯', 'name': 'Perfect', 'desc': 'Got 100% on a quiz'},
    'streak_7': {'emoji': '🔥', 'name': 'On Fire', 'desc': '7-day streak'},
    'streak_30': {'emoji': '⚡', 'name': 'Unstoppable', 'desc': '30-day streak'},
    'social': {'emoji': '👥', 'name': 'Social', 'desc': 'Shared 10+ quizzes'},
    'master': {'emoji': '🏆', 'name': 'Quiz Master', 'desc': 'Reached Level 10'},
}

def _award_badge_sync(user_id, badge_id):
    """Award a badge to user if not already earned."""
    if badge_id not in BADGE_DEFINITIONS:
        return False
    
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    if not user_doc.exists:
        return False
    
    badges = user_doc.to_dict().get('badges', [])
    if badge_id in badges:
        return False  # Already has badge
    
    badges.append(badge_id)
    user_ref.update({'badges': badges})
    return True

async def award_badge(user_id, badge_id):
    return await run_sync(_award_badge_sync, user_id, badge_id)

def _get_user_badges_sync(user_id):
    """Get user's badges with full info."""
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    if not user_doc.exists:
        return []
    
    badge_ids = user_doc.to_dict().get('badges', [])
    return [
        {**BADGE_DEFINITIONS.get(b, {}), 'id': b}
        for b in badge_ids if b in BADGE_DEFINITIONS
    ]

async def get_user_badges(user_id):
    return await run_sync(_get_user_badges_sync, user_id)

# --- LEADERBOARD ---
def _get_top_users_sync(limit=10):
    """Get top users by total XP, excluding admins."""
    # Get admin IDs to exclude
    admin_docs = db.collection('admins').stream()
    admin_ids = set(doc.id for doc in admin_docs)
    
    # Get more users than needed (to account for admins)
    docs = db.collection('users').order_by('total_xp', direction=firestore.Query.DESCENDING).limit(limit + 20).stream()
    users = []
    for doc in docs:
        if doc.id in admin_ids:
            continue  # Skip admins
        if len(users) >= limit:
            break
        data = doc.to_dict()
        # Use first_name, fallback to username, then User
        display_name = data.get('first_name') or data.get('username') or 'User'
        # Clean display name of special characters
        display_name = ''.join(c for c in display_name if c.isprintable() and ord(c) < 10000)
        if not display_name:
            display_name = 'User'
        users.append({
            'user_id': doc.id,
            'username': display_name,
            'total_xp': data.get('total_xp', 0),
            'level': data.get('level', 1)
        })
    return users

async def get_top_users(limit=10):
    return await run_sync(_get_top_users_sync, limit)


# --- AI USAGE (DAILY LIMITS) ---
def _get_user_ai_usage_sync(user_id):
    """Get number of AI generations used today."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    doc = db.collection('daily_stats').document(f"ai_usage_{today}_{user_id}").get()
    if doc.exists:
        return doc.to_dict().get('count', 0)
    return 0

def _increment_ai_usage_sync(user_id):
    """Increment AI generation count for user today."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    ref = db.collection('daily_stats').document(f"ai_usage_{today}_{user_id}")
    
    if ref.get().exists:
        ref.update({'count': firestore.Increment(1)})
    else:
        ref.set({
            'user_id': user_id,
            'date': today,
            'count': 1,
            'created_at': firestore.SERVER_TIMESTAMP
        })

async def get_user_ai_usage(user_id):
    return await run_sync(_get_user_ai_usage_sync, user_id)

async def increment_ai_usage(user_id):
    return await run_sync(_increment_ai_usage_sync, user_id)

# --- QUESTION MANAGEMENT ---
def _delete_question_from_quiz_sync(quiz_id: str, index: int):
    """Delete a specific question from a quiz by index."""
    ref = db.collection('custom_quizzes').document(quiz_id)
    doc = ref.get()
    
    if not doc.exists:
        return False
        
    data = doc.to_dict()
    questions = data.get('questions', [])
    
    if 0 <= index < len(questions):
        # Remove question
        questions.pop(index)
        # Update DB
        ref.update({'questions': questions})
        return True
    return False

async def delete_question_from_quiz(quiz_id: str, index: int):
    return await run_sync(_delete_question_from_quiz_sync, quiz_id, index)
