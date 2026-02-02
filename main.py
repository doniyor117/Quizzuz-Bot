import asyncio
import logging
import os
import aiohttp 
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiohttp import web 
from datetime import datetime, timezone

# Load handlers
from bot_handlers import start, add_cards, manage, practice, explore, stats, settings, admin, vocabulary, help
from bot_services.firebase_service import get_all_users
from bot_services.notifications import check_and_send_due_card_notifications
from bot_services.middleware import BanCheckMiddleware

# Load Env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8080)) 
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    exit("Error: BOT_TOKEN not found in env")

# Logging
logging.basicConfig(level=logging.INFO)

# --- Notification Logic ---
async def send_smart_notifications(bot: Bot):
    """Checks all users and sends personalized nudges (once per day)."""
    logging.info("🔔 Starting Smart Notification Run...")
    users = await get_all_users()
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    count = 0
    for u in users:
        try:
            uid = u['user_id']
            name = u.get('first_name', 'Friend')
            lang = u.get('lang_code', 'en')
            
            # 1. ALREADY NOTIFIED TODAY? Skip to avoid spam
            last_notif = u.get('last_notif_date', '')
            if last_notif == today_str:
                continue  # Already sent a notification today
            
            # 2. SUPER USER CHECK: If they hit daily goal, DO NOT DISTURB
            if u.get('daily_goal_hit'):
                continue
            
            # 3. ACTIVE TODAY: Already practiced, don't bother them
            last_active = u.get('last_active_date_str', '')
            if last_active == today_str:
                continue  # They're active, don't nag
            
            # 4. STREAK AT RISK: Has streak but hasn't practiced today
            streak = u.get('streak', 0)
            if streak > 0:
                msg = f"🔥 {name}, your {streak}-day streak is at risk! Practice now to save it!"
                if lang == 'uz': 
                    msg = f"🔥 {name}, {streak} kunlik streekingiz yonib ketishi mumkin! Saqlab qoling!"
            else:
                # 5. DEAD STREAK / INACTIVE: Only send if not notified today
                msg = f"📚 {name}, ready to learn something new today?"
                if lang == 'uz': 
                    msg = f"📚 {name}, bugun yangi narsa o'rganishga tayyormisiz?"

            # Send the nudge
            await bot.send_message(uid, msg)
            
            # Mark as notified today to prevent spam
            from bot_services.firebase_service import db
            db.collection('users').document(str(uid)).update({
                'last_notif_date': today_str
            })
            
            count += 1
            await asyncio.sleep(0.05)  # Anti-spam safety
            
        except Exception as e:
            # User might have blocked the bot, ignore
            continue
            
    logging.info(f"🔔 Sent {count} notifications.")

async def notification_scheduler(bot: Bot):
    """Runs the notification logic once per day (every 24 hours)."""
    while True:
        # Wait 24 hours between notification runs
        await asyncio.sleep(86400)  # 24 hours = 86400 seconds
        await send_smart_notifications(bot)

async def health_check(request):
    return web.Response(text="Bot is running!")

# ===== GAME API ROUTES =====
import json
from datetime import datetime, timedelta
from bot_services.firebase_service import add_tx_coins, add_total_xp, db, get_user

GAME_DIR = os.path.join(os.path.dirname(__file__), 'game', 'hexagame')

async def serve_game(request):
    """Serve the main game HTML."""
    return web.FileResponse(os.path.join(GAME_DIR, 'index.html'))

async def serve_game_static(request):
    """Serve static game files."""
    path = request.match_info.get('path', '')
    
    # Allow serving from both root and hexagame subfolder
    if path.startswith('hexagame/'):
        path = path.replace('hexagame/', '', 1)
        
    file_path = os.path.join(GAME_DIR, path)
    if os.path.isfile(file_path):
        return web.FileResponse(file_path)
    
    # Fallback to index if path is 'hexagame' or 'hexagame/'
    if path == '' or path == 'index.html':
        return web.FileResponse(os.path.join(GAME_DIR, 'index.html'))
        
    return web.Response(status=404, text=f"Not found: {path}")

async def game_start(request):
    """Initialize a new game session."""
    user_id = request.headers.get('X-User-Id', '')
    if not user_id:
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        user = await get_user(int(user_id))
        return web.json_response({
            'success': True,
            'user': {
                'id': user_id,
                'name': user.get('first_name', 'Player') if user else 'Player',
                'tx_coins': user.get('xp', 0) if user else 0,  # xp field = TX coins
                'xp': user.get('total_xp', 0) if user else 0
            }
        })
    except Exception as e:
        logging.error(f"Game start error: {e}")
        return web.json_response({'success': True, 'user': {'id': user_id}})

async def game_submit_score(request):
    """Submit game score and award TX/XP."""
    user_id = request.headers.get('X-User-Id', '')
    if not user_id:
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.json()
        score = data.get('score', 0)
        words_found = data.get('words', 0)
        level = data.get('level', 1)
        
        # Calculate rewards (balanced)
        tx_earned = (words_found * 0.5) + (level * 10)
        xp_earned = (words_found * 2) + (level * 20)  # Lowered from 5/50
        
        # Award TX and XP
        await add_tx_coins(int(user_id), tx_earned)
        await add_total_xp(int(user_id), xp_earned)
        
        # Save game score to Firestore
        game_data = {
            'user_id': str(user_id),
            'score': score,
            'words': words_found,
            'level': level,
            'tx_earned': tx_earned,
            'xp_earned': xp_earned,
            'timestamp': datetime.now(timezone.utc)
        }
        db.collection('game_scores').add(game_data)
        
        logging.info(f"🎮 Game score: user={user_id}, score={score}, +{tx_earned}TX, +{xp_earned}XP")
        
        return web.json_response({
            'success': True,
            'tx_earned': tx_earned,
            'xp_earned': xp_earned
        })
    except Exception as e:
        logging.error(f"Game submit error: {e}")
        return web.json_response({'success': False, 'error': str(e)}, status=500)

async def game_user_stats(request):
    """Get current user's game stats."""
    user_id = request.headers.get('X-User-Id', '')
    if not user_id:
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        user = await get_user(int(user_id))
        return web.json_response({
            'success': True,
            'user': {
                'id': user_id,
                'name': user.get('first_name', 'Player') if user else 'Player',
                'tx_coins': user.get('xp', 0) if user else 0,
                'xp': user.get('total_xp', 0) if user else 0
            }
        })
    except Exception as e:
        logging.error(f"Game stats error: {e}")
        return web.json_response({'success': False, 'error': str(e)}, status=500)

async def game_leaderboard(request):
    """Get game leaderboard."""
    period = request.query.get('period', 'daily')  # daily, weekly, all
    limit = min(int(request.query.get('limit', 10)), 50)
    
    try:
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
            .limit(limit * 5)
        
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
        
        # Add rank and names
        for i, entry in enumerate(leaderboard):
            entry['rank'] = i + 1
            # Get user name from Firestore
            try:
                user = await get_user(int(entry['user_id']))
                entry['name'] = user.get('first_name', 'Player') if user else 'Player'
            except:
                entry['name'] = 'Player'
        
        return web.json_response({
            'success': True,
            'period': period,
            'leaderboard': leaderboard
        })
    except Exception as e:
        logging.error(f"Leaderboard error: {e}")
        return web.json_response({'success': True, 'leaderboard': []})

async def game_daily_challenge(request):
    """Get today's daily challenge info."""
    user_id = request.headers.get('X-User-Id', '')
    
    try:
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # Check if user already completed today's challenge
        completed = False
        bonus_earned = 0
        
        if user_id:
            # Check for existing daily completion
            query = db.collection('daily_challenges')\
                .where('user_id', '==', str(user_id))\
                .where('date', '==', today)\
                .limit(1)
            docs = list(query.stream())
            if docs:
                completed = True
                bonus_earned = docs[0].to_dict().get('bonus_earned', 0)
        
        # Daily challenge config (could be from DB in future)
        challenge = {
            'date': today,
            'target_score': 500,  # Target score for bonus
            'target_words': 10,   # Target words for bonus
            'bonus_tx': 25,       # Bonus TX for completing
            'bonus_xp': 75,       # Bonus XP for completing (lowered)
            'completed': completed,
            'bonus_earned': bonus_earned
        }
        
        return web.json_response({'success': True, 'challenge': challenge})
    except Exception as e:
        logging.error(f"Daily challenge error: {e}")
        return web.json_response({'success': False, 'error': str(e)}, status=500)

async def game_complete_daily(request):
    """Complete daily challenge and earn bonus."""
    user_id = request.headers.get('X-User-Id', '')
    if not user_id:
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.json()
        score = data.get('score', 0)
        words = data.get('words', 0)
        
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # Check if already completed today
        query = db.collection('daily_challenges')\
            .where('user_id', '==', str(user_id))\
            .where('date', '==', today)\
            .limit(1)
        docs = list(query.stream())
        
        if docs:
            return web.json_response({'success': False, 'error': 'already_completed'})
        
        # Check if targets met
        target_score = 500
        target_words = 10
        
        if score >= target_score or words >= target_words:
            bonus_tx = 25
            bonus_xp = 75  # Lowered from 150
            
            # Award bonus
            await add_tx_coins(int(user_id), bonus_tx)
            await add_total_xp(int(user_id), bonus_xp)
            
            # Record completion
            db.collection('daily_challenges').add({
                'user_id': str(user_id),
                'date': today,
                'score': score,
                'words': words,
                'bonus_earned': bonus_tx,
                'completed_at': datetime.now(timezone.utc)
            })
            
            logging.info(f"🏆 Daily challenge completed: user={user_id}, +{bonus_tx}TX, +{bonus_xp}XP")
            
            return web.json_response({
                'success': True,
                'completed': True,
                'bonus_tx': bonus_tx,
                'bonus_xp': bonus_xp
            })
        
        return web.json_response({'success': True, 'completed': False, 'message': 'Target not met'})
    except Exception as e:
        logging.error(f"Complete daily error: {e}")
        return web.json_response({'success': False, 'error': str(e)}, status=500)

async def start_dummy_server():
    app = web.Application()
    
    # Health check
    app.router.add_get('/', health_check)
    
    # Game routes
    app.router.add_get('/game/', serve_game)
    app.router.add_get('/game/{path:.*}', serve_game_static)
    
    # Game API (with underscores - original)
    app.router.add_post('/api/game/start', game_start)
    app.router.add_post('/api/game/submit_score', game_submit_score)
    app.router.add_get('/api/game/user_stats', game_user_stats)
    app.router.add_get('/api/game/leaderboard', game_leaderboard)
    app.router.add_get('/api/game/daily_challenge', game_daily_challenge)
    app.router.add_post('/api/game/complete_daily', game_complete_daily)
    
    # Game API (with hyphens - for frontend compatibility)
    app.router.add_post('/api/game/submit-score', game_submit_score)
    app.router.add_get('/api/game/user-stats', game_user_stats)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🌐 Server started on port {PORT}")
    print(f"🎮 QuizzWords Game available at http://localhost:{PORT}/game/")

async def keep_alive():
    while True:
        await asyncio.sleep(200) 
        if RENDER_EXTERNAL_URL:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(RENDER_EXTERNAL_URL) as response:
                        pass
            except: pass

async def main():
    await start_dummy_server()
    asyncio.create_task(keep_alive())

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Start the Notification Scheduler
    asyncio.create_task(notification_scheduler(bot))
    asyncio.create_task(check_and_send_due_card_notifications(bot))  # SM-2 Due Card Notifications

    # Register middleware (must be before routers)
    dp.update.middleware(BanCheckMiddleware())
    
    # Group Play (MUST be before start.router to handle group quiz starts)
    from bot_handlers import group_play
    dp.include_router(group_play.router)

    dp.include_router(start.router)
    dp.include_router(add_cards.router)
    dp.include_router(vocabulary.router)  # AI Vocabulary Helper
    dp.include_router(practice.router)
    dp.include_router(manage.router)
    dp.include_router(explore.router)
    dp.include_router(stats.router)
    dp.include_router(settings.router)
    dp.include_router(admin.router)
    
    # Custom Quiz Builder
    from bot_handlers import quiz_builder
    dp.include_router(quiz_builder.router)
    
    # New Phase 1 Handlers
    from bot_handlers import favorites, profile, quiz_studio
    dp.include_router(favorites.router)
    dp.include_router(profile.router)
    dp.include_router(quiz_studio.router)
    
    # Leaderboard
    from bot_handlers import leaderboard
    dp.include_router(leaderboard.router)
    
    dp.include_router(help.router)

    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 QuizTeebBot V3.0 Started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")