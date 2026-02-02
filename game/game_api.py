"""
QuizzWords Game API - Backend for Hexagame Integration
Handles: user sessions, scores, TX/XP rewards, leaderboards
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from functools import wraps

# Add parent directory to path for firebase_service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__, static_folder='hexagame')
CORS(app)

# TX Coin rewards configuration
TX_REWARDS = {
    'word_found': 0.25,       # Per word found (reduced from 0.5)
    'level_complete': 5,      # Per level completed (reduced from 10)
    'perfect_level': 10,      # All words found in level (reduced from 25)
    'daily_bonus': 10,        # First game of the day (reduced from 20)
    'streak_bonus': 2,        # Per day streak (reduced from 5)
}

# XP rewards configuration
XP_REWARDS = {
    'word_found': 2,          # Per word × word_length (reduced from 5)
    'level_complete': 25,     # Per level (reduced from 50)
    'game_complete': 50,      # Finish a game (reduced from 100)
}

def get_telegram_user_id():
    """Extract user ID from Telegram init data."""
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    user_id = request.headers.get('X-User-Id', '')
    
    if user_id:
        return int(user_id)
    
    # Parse init data if present (simplified - in production use proper validation)
    if init_data:
        try:
            import urllib.parse
            data = dict(urllib.parse.parse_qsl(init_data))
            if 'user' in data:
                user_data = json.loads(data['user'])
                return user_data.get('id')
        except:
            pass
    
    return None

def require_auth(f):
    """Decorator to require Telegram authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = get_telegram_user_id()
        if not user_id:
            return jsonify({'error': 'unauthorized'}), 401
        request.user_id = user_id
        return f(*args, **kwargs)
    return decorated

# ============================================
# STATIC FILES - Serve the game
# ============================================

@app.route('/')
def serve_game():
    """Serve the main game HTML."""
    return send_from_directory('hexagame', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files from hexagame folder."""
    return send_from_directory('hexagame', path)

# ============================================
# GAME API ENDPOINTS
# ============================================

@app.route('/api/game/start', methods=['POST'])
@require_auth
def start_game():
    """Initialize a new game session."""
    user_id = request.user_id
    
    try:
        from bot_services.firebase_service import get_user
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        user = loop.run_until_complete(get_user(user_id))
        loop.close()
        
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        return jsonify({
            'success': True,
            'user': {
                'id': user_id,
                'name': user.get('first_name', 'Player'),
                'tx_coins': user.get('tx_coins', 0),
                'xp': user.get('xp', 0)
            }
        })
    except Exception as e:
        print(f"Error starting game: {e}")
        return jsonify({'success': True, 'user': {'id': user_id}})

@app.route('/api/game/submit_score', methods=['POST'])
@require_auth
def submit_score():
    """Submit game score and award TX/XP."""
    user_id = request.user_id
    data = request.get_json()
    
    score = data.get('score', 0)
    words_found = data.get('words', 0)
    level = data.get('level', 1)
    letters = data.get('letters', 0)
    
    # Calculate rewards
    tx_earned = (words_found * TX_REWARDS['word_found']) + (level * TX_REWARDS['level_complete'])
    xp_earned = (words_found * XP_REWARDS['word_found']) + (level * XP_REWARDS['level_complete'])
    
    try:
        from bot_services.firebase_service import add_tx_coins, add_total_xp, db
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Award TX and XP
        loop.run_until_complete(add_tx_coins(user_id, tx_earned))
        loop.run_until_complete(add_total_xp(user_id, xp_earned))
        
        # Save game score to Firestore
        game_data = {
            'user_id': str(user_id),
            'score': score,
            'words': words_found,
            'level': level,
            'letters': letters,
            'tx_earned': tx_earned,
            'xp_earned': xp_earned,
            'timestamp': datetime.now(timezone.utc)
        }
        db.collection('game_scores').add(game_data)
        
        loop.close()
        
        return jsonify({
            'success': True,
            'tx_earned': tx_earned,
            'xp_earned': xp_earned
        })
    except Exception as e:
        print(f"Error submitting score: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/game/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get game leaderboard."""
    period = request.args.get('period', 'daily')  # daily, weekly, all
    limit = min(int(request.args.get('limit', 10)), 50)
    
    try:
        from bot_services.firebase_service import db
        from google.cloud.firestore_v1 import Query
        
        # Calculate time filter
        now = datetime.now(timezone.utc)
        if period == 'daily':
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'weekly':
            start_time = now - timedelta(days=7)
        else:
            start_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        
        # Query top scores
        query = db.collection('game_scores')\
            .where('timestamp', '>=', start_time)\
            .order_by('timestamp', direction=Query.DESCENDING)\
            .limit(limit * 5)  # Get more to aggregate by user
        
        docs = query.stream()
        
        # Aggregate best scores per user
        user_scores = {}
        for doc in docs:
            data = doc.to_dict()
            uid = data.get('user_id')
            score = data.get('score', 0)
            
            if uid not in user_scores or score > user_scores[uid]['score']:
                user_scores[uid] = {
                    'user_id': uid,
                    'score': score,
                    'words': data.get('words', 0),
                    'level': data.get('level', 1)
                }
        
        # Sort by score and limit
        leaderboard = sorted(user_scores.values(), key=lambda x: x['score'], reverse=True)[:limit]
        
        # Add rank
        for i, entry in enumerate(leaderboard):
            entry['rank'] = i + 1
        
        return jsonify({
            'success': True,
            'period': period,
            'leaderboard': leaderboard
        })
    except Exception as e:
        print(f"Error getting leaderboard: {e}")
        return jsonify({'success': True, 'leaderboard': []})

@app.route('/api/game/user_stats', methods=['GET'])
@require_auth
def get_user_stats():
    """Get current user's game stats."""
    user_id = request.user_id
    
    try:
        from bot_services.firebase_service import db, get_user
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        user = loop.run_until_complete(get_user(user_id))
        loop.close()
        
        # Get user's best score
        query = db.collection('game_scores')\
            .where('user_id', '==', str(user_id))\
            .order_by('score', direction='DESCENDING')\
            .limit(1)
        
        docs = list(query.stream())
        best_score = docs[0].to_dict() if docs else None
        
        return jsonify({
            'success': True,
            'user': {
                'id': user_id,
                'name': user.get('first_name', 'Player') if user else 'Player',
                'tx_coins': user.get('tx_coins', 0) if user else 0,
                'xp': user.get('xp', 0) if user else 0
            },
            'best_score': best_score
        })
    except Exception as e:
        print(f"Error getting user stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# HEALTH CHECK
# ============================================

@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'game': 'quizzwords'})

if __name__ == '__main__':
    port = int(os.environ.get('GAME_PORT', 8081))
    print(f"🎮 QuizzWords Game Server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
