"""
Analytics Service for QuizTeeb Bot

Tracks user behavior, feature usage, and bot performance metrics.
Provides insights into DAU, MAU, retention, feature adoption, etc.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from collections import defaultdict
import logging

from firebase_admin import firestore

logger = logging.getLogger(__name__)

# Firestore client
db = firestore.client()


# ============================================
# EVENT TRACKING
# ============================================

async def track_event(user_id: int, event_name: str, properties: Optional[Dict[str, Any]] = None):
    """
    Track a generic analytics event.
    
    Args:
        user_id: Telegram user ID
        event_name: Name of the event (e.g., 'command_start', 'card_added')
        properties: Additional event properties
    """
    if properties is None:
        properties = {}
    
    try:
        now = datetime.now(timezone.utc)
        date_str = now.strftime('%Y-%m-%d')
        
        event_data = {
            'user_id': user_id,
            'event_name': event_name,
            'properties': properties,
            'timestamp': now,
            'date_str': date_str
        }
        
        # Store event (async to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: db.collection('analytics_events').add(event_data)
        )
        
        # Update user analytics profile
        await _update_user_analytics(user_id, event_name)
        
        # Update daily aggregation (fire and forget)
        asyncio.create_task(_update_daily_stats(date_str, event_name, properties))
        
    except Exception as e:
        logger.error(f"Error tracking event {event_name}: {e}")


async def track_command(user_id: int, command_name: str):
    """Track command usage."""
    await track_event(user_id, 'command_used', {'command': command_name})


async def track_feature(user_id: int, feature_name: str, action: str):
    """Track feature usage."""
    await track_event(user_id, 'feature_used', {'feature': feature_name, 'action': action})


async def track_error(user_id: Optional[int], error_type: str, details: str):
    """Track errors and exceptions."""
    await track_event(user_id or 0, 'error_occurred', {'error_type': error_type, 'details': details})


# ============================================
# USER ANALYTICS PROFILE
# ============================================

async def _update_user_analytics(user_id: int, event_name: str):
    """Update user's analytics profile."""
    try:
        loop = asyncio.get_event_loop()
        user_ref = db.collection('analytics_users').document(str(user_id))
        
        def update_profile():
            doc = user_ref.get()
            now = datetime.now(timezone.utc)
            
            if doc.exists:
                user_ref.update({
                    'last_active': now,
                    'total_events': firestore.Increment(1),
                    f'events.{event_name}': firestore.Increment(1)
                })
            else:
                user_ref.set({
                    'user_id': user_id,
                    'first_seen': now,
                    'last_active': now,
                    'total_events': 1,
                    'events': {event_name: 1}
                })
        
        await loop.run_in_executor(None, update_profile)
        
    except Exception as e:
        logger.error(f"Error updating user analytics: {e}")


# ============================================
# DAILY STATS AGGREGATION
# ============================================

async def _update_daily_stats(date_str: str, event_name: str, properties: Dict):
    """Update daily aggregated statistics."""
    try:
        loop = asyncio.get_event_loop()
        daily_ref = db.collection('analytics_daily').document(date_str)
        
        def update_stats():
            # Increment counters based on event type
            updates = {
                f'events.{event_name}': firestore.Increment(1)
            }
            
            # Track specific metrics
            if event_name == 'command_used':
                command = properties.get('command', 'unknown')
                updates[f'commands.{command}'] = firestore.Increment(1)
            
            elif event_name == 'feature_used':
                feature = properties.get('feature', 'unknown')
                updates[f'features.{feature}'] = firestore.Increment(1)
            
            elif event_name == 'card_added':
                updates['total_cards_added'] = firestore.Increment(1)
            
            elif event_name == 'card_practiced':
                updates['total_cards_practiced'] = firestore.Increment(1)
            
            elif event_name == 'vocab_lookup':
                updates['total_vocab_lookups'] = firestore.Increment(1)
            
            doc = daily_ref.get()
            if doc.exists:
                daily_ref.update(updates)
            else:
                initial_data = {
                    'date': date_str,
                    'total_cards_added': 0,
                    'total_cards_practiced': 0,
                    'total_vocab_lookups': 0,
                    'events': {},
                    'commands': {},
                    'features': {}
                }
                initial_data.update(updates)
                daily_ref.set(initial_data)
        
        await loop.run_in_executor(None, update_stats)
        
    except Exception as e:
        logger.error(f"Error updating daily stats: {e}")


# ============================================
# METRICS RETRIEVAL
# ============================================

async def get_daily_stats(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Get statistics for a specific day.
    
    Args:
        date_str: Date in format 'YYYY-MM-DD', defaults to today
        
    Returns:
        Dictionary with daily metrics
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    try:
        loop = asyncio.get_event_loop()
        
        def fetch_stats():
            # Get aggregated daily stats
            daily_doc = db.collection('analytics_daily').document(date_str).get()
            
            if not daily_doc.exists:
                return {
                    'date': date_str,
                    'dau': 0,
                    'new_users': 0,
                    'total_cards_added': 0,
                    'total_cards_practiced': 0,
                    'total_vocab_lookups': 0,
                    'commands': {},
                    'features': {}
                }
            
            stats = daily_doc.to_dict()
            
            # Calculate DAU (unique users active today)
            dau_count = db.collection('analytics_events')\
                .where('date_str', '==', date_str)\
                .select(['user_id'])\
                .stream()
            
            unique_users = set()
            for doc in dau_count:
                unique_users.add(doc.to_dict().get('user_id'))
            
            stats['dau'] = len(unique_users)
            
            # Calculate new users
            new_users = db.collection('analytics_users')\
                .where('first_seen', '>=', datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc))\
                .where('first_seen', '<', (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).replace(tzinfo=timezone.utc))\
                .stream()
            
            stats['new_users'] = len(list(new_users))
            
            return stats
        
        return await loop.run_in_executor(None, fetch_stats)
        
    except Exception as e:
        logger.error(f"Error fetching daily stats: {e}")
        return {}


async def get_weekly_stats() -> Dict[str, Any]:
    """Get statistics for the past 7 days."""
    try:
        today = datetime.now(timezone.utc)
        stats = {
            'period': 'last_7_days',
            'daily_breakdown': [],
            'total_dau': 0,
            'total_new_users': 0,
            'avg_dau': 0
        }
        
        for i in range(7):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            daily = await get_daily_stats(date_str)
            stats['daily_breakdown'].append(daily)
            stats['total_dau'] += daily.get('dau', 0)
            stats['total_new_users'] += daily.get('new_users', 0)
        
        stats['avg_dau'] = stats['total_dau'] / 7
        
        return stats
        
    except Exception as e:
        logger.error(f"Error fetching weekly stats: {e}")
        return {}


async def get_monthly_stats() -> Dict[str, Any]:
    """Get statistics for the past 30 days."""
    try:
        today = datetime.now(timezone.utc)
        stats = {
            'period': 'last_30_days',
            'total_dau': 0,
            'total_new_users': 0,
            'avg_dau': 0
        }
        
        dau_sum = 0
        new_users_sum = 0
        
        for i in range(30):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            daily = await get_daily_stats(date_str)
            dau_sum += daily.get('dau', 0)
            new_users_sum += daily.get('new_users', 0)
        
        stats['total_new_users'] = new_users_sum
        stats['avg_dau'] = dau_sum / 30
        
        return stats
        
    except Exception as e:
        logger.error(f"Error fetching monthly stats: {e}")
        return {}


async def get_feature_usage(days: int = 7) -> Dict[str, int]:
    """
    Get feature usage statistics.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Dictionary with feature names and usage counts
    """
    try:
        loop = asyncio.get_event_loop()
        
        def fetch_usage():
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            start_date_str = start_date.strftime('%Y-%m-%d')
            
            features = defaultdict(int)
            
            # Query feature usage events
            events = db.collection('analytics_events')\
                .where('event_name', '==', 'feature_used')\
                .where('date_str', '>=', start_date_str)\
                .stream()
            
            for event in events:
                data = event.to_dict()
                feature_name = data.get('properties', {}).get('feature', 'unknown')
                features[feature_name] += 1
            
            return dict(features)
        
        return await loop.run_in_executor(None, fetch_usage)
        
    except Exception as e:
        logger.error(f"Error fetching feature usage: {e}")
        return {}


async def get_command_usage(days: int = 7) -> Dict[str, int]:
    """
    Get command usage statistics.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Dictionary with command names and usage counts
    """
    try:
        loop = asyncio.get_event_loop()
        
        def fetch_usage():
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            start_date_str = start_date.strftime('%Y-%m-%d')
            
            commands = defaultdict(int)
            
            # Query command usage events
            events = db.collection('analytics_events')\
                .where('event_name', '==', 'command_used')\
                .where('date_str', '>=', start_date_str)\
                .stream()
            
            for event in events:
                data = event.to_dict()
                command_name = data.get('properties', {}).get('command', 'unknown')
                commands[command_name] += 1
            
            return dict(commands)
        
        return await loop.run_in_executor(None, fetch_usage)
        
    except Exception as e:
        logger.error(f"Error fetching command usage: {e}")
        return {}


async def get_user_retention(days: int = 7) -> float:
    """
    Calculate user retention rate.
    
    Args:
        days: Period for retention calculation
        
    Returns:
        Retention percentage (0-100)
    """
    try:
        loop = asyncio.get_event_loop()
        
        def calculate_retention():
            today = datetime.now(timezone.utc)
            start_date = today - timedelta(days=days)
            
            # Users who joined during the period
            new_users = db.collection('analytics_users')\
                .where('first_seen', '>=', start_date)\
                .where('first_seen', '<', today)\
                .stream()
            
            new_user_ids = set()
            for user in new_users:
                new_user_ids.add(user.to_dict()['user_id'])
            
            if not new_user_ids:
                return 0.0
            
            # How many are still active
            active_count = 0
            yesterday = today - timedelta(days=1)
            
            for uid in new_user_ids:
                user_doc = db.collection('analytics_users').document(str(uid)).get()
                if user_doc.exists:
                    last_active = user_doc.to_dict().get('last_active')
                    if last_active and last_active >= yesterday:
                        active_count += 1
            
            retention = (active_count / len(new_user_ids)) * 100
            return round(retention, 1)
        
        return await loop.run_in_executor(None, calculate_retention)
        
    except Exception as e:
        logger.error(f"Error calculating retention: {e}")
        return 0.0
