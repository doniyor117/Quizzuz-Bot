"""
Vocabulary Cache Service

Handles all Firestore operations for vocabulary caching:
- Getting cached words
- Saving new entries
- Upgrading dict entries to AI quality
"""

from typing import Optional, Dict
from bot_services.firebase_service import db, run_sync, TASHKENT_TZ
from datetime import datetime

def _get_from_cache_sync(word: str) -> Optional[Dict]:
    """
    Get vocabulary from cache by word (case-insensitive).
    
    Args:
        word: The word to look up
        
    Returns:
        Cached vocabulary data or None if not found
    """
    word_key = word.lower().strip()
    doc_ref = db.collection('vocabulary_cache').document(word_key)
    doc = doc_ref.get()
    
    if not doc.exists:
        return None
    
    data = doc.to_dict()
    return data

async def get_from_cache(word: str) -> Optional[Dict]:
    """Get vocabulary from cache (async)."""
    return await run_sync(_get_from_cache_sync, word)

def _save_to_cache_sync(word: str, vocab_data: Dict, source_type: str) -> None:
    """
    Save vocabulary data to cache.
    
    Args:
        word: The word being cached
        vocab_data: Vocabulary data (definition, translation, examples, etc.)
        source_type: "ai" or "dict"
    """
    word_key = word.lower().strip()
    
    cache_entry = {
        'word': word,  # Preserve original case
        'definition': vocab_data.get('definition', ''),
        'translation_uz': vocab_data.get('translation', ''),
        'translation_en': vocab_data.get('translation_en', ''),
        'examples': vocab_data.get('examples', []),
        'phonetic': vocab_data.get('phonetic', ''),
        'source_type': source_type,
        'cached_at': datetime.now(TASHKENT_TZ),
        'upgrade_count': 0
    }
    
    doc_ref = db.collection('vocabulary_cache').document(word_key)
    doc_ref.set(cache_entry)
    print(f"✅ Cached '{word}' as {source_type}")

async def save_to_cache(word: str, vocab_data: Dict, source_type: str) -> None:
    """Save vocabulary to cache (async)."""
    await run_sync(_save_to_cache_sync, word, vocab_data, source_type)

def _should_upgrade_cache_sync(word: str, user_has_quota: bool) -> bool:
    """
    Check if a cached word should be upgraded from dict to AI.
    
    Args:
        word: The word to check
        user_has_quota: Whether the requesting user has AI quota
        
    Returns:
        True if should upgrade, False otherwise
    """
    if not user_has_quota:
        return False
    
    word_key = word.lower().strip()
    doc_ref = db.collection('vocabulary_cache').document(word_key)
    doc = doc_ref.get()
    
    if not doc.exists:
        return False
    
    data = doc.to_dict()
    source_type = data.get('source_type', '')
    
    # Only upgrade if source is 'dict'
    return source_type == 'dict'

async def should_upgrade_cache(word: str, user_has_quota: bool) -> bool:
    """Check if cache should be upgraded (async)."""
    return await run_sync(_should_upgrade_cache_sync, word, user_has_quota)

def _upgrade_cache_entry_sync(word: str, ai_data: Dict) -> None:
    """
    Upgrade a dictionary-sourced cache entry with AI data.
    
    Args:
        word: The word to upgrade
        ai_data: New AI-generated vocabulary data
    """
    word_key = word.lower().strip()
    doc_ref = db.collection('vocabulary_cache').document(word_key)
    doc = doc_ref.get()
    
    if not doc.exists:
        # Entry doesn't exist, just save as AI
        _save_to_cache_sync(word, ai_data, 'ai')
        return
    
    # Get current upgrade count
    current_data = doc.to_dict()
    upgrade_count = current_data.get('upgrade_count', 0)
    
    # Prepare upgraded entry
    upgraded_entry = {
        'word': word,
        'definition': ai_data.get('definition', ''),
        'translation_uz': ai_data.get('translation', ''),
        'translation_en': ai_data.get('translation_en', ''),
        'examples': ai_data.get('examples', []),
        'phonetic': ai_data.get('phonetic', ''),
        'source_type': 'ai',  # Changed from 'dict' to 'ai'
        'cached_at': datetime.now(TASHKENT_TZ),
        'upgrade_count': upgrade_count + 1
    }
    
    doc_ref.set(upgraded_entry)
    print(f"🔄 Upgraded '{word}' from dict to AI (count: {upgrade_count + 1})")

async def upgrade_cache_entry(word: str, ai_data: Dict) -> None:
    """Upgrade cache entry with AI data (async)."""
    await run_sync(_upgrade_cache_entry_sync, word, ai_data)

# ===== CACHE ANALYTICS (Optional, for admin dashboard) =====

def _get_cache_stats_sync() -> Dict:
    """Get cache statistics for monitoring."""
    total_docs = db.collection('vocabulary_cache').stream()
    total_count = 0
    ai_count = 0
    dict_count = 0
    upgrade_count_total = 0
    
    for doc in total_docs:
        total_count += 1
        data = doc.to_dict()
        source = data.get('source_type', '')
        
        if source == 'ai':
            ai_count += 1
        elif source == 'dict':
            dict_count += 1
        
        upgrade_count_total += data.get('upgrade_count', 0)
    
    return {
        'total_cached': total_count,
        'ai_source': ai_count,
        'dict_source': dict_count,
        'total_upgrades': upgrade_count_total,
        'ai_percentage': round((ai_count / total_count * 100) if total_count > 0 else 0, 1)
    }

async def get_cache_stats() -> Dict:
    """Get cache statistics (async)."""
    return await run_sync(_get_cache_stats_sync)
