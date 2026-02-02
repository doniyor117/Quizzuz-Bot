from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import get_user, get_user_badges
from bot_services.utils import get_rank_title

router = Router()

@router.callback_query(F.data == "menu_profile")
async def show_profile(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = await get_user(user_id)
    if not user:
        user = {}  # Default to empty dict to prevent crash
    
    # Stats
    total_xp = user.get('total_xp', 0)
    tx_coins = user.get('xp', 0)
    streak = user.get('streak', 0)
    level = user.get('level', 1)
    level_info = get_rank_title(level)
    rank_emoji = level_info['rank_emoji']
    rank_name = level_info['rank_name']
    
    # Fetch real badges
    badges = await get_user_badges(user_id)
    if badges:
        badge_display = " ".join([f"{b['emoji']}" for b in badges[:8]])
        badge_names = ", ".join([b['name'] for b in badges[:5]])
        badge_text = f"{badge_display}\n_{badge_names}_"
    else:
        badge_text = "🔒 No badges yet\n_Keep playing to earn badges!_"
    
    text = (
        f"👤 **Your Profile**\n\n"
        f"{rank_emoji} **{rank_name}** (Level {level})\n"
        f"📊 Total XP: {int(total_xp)}\n"
        f"💰 TX Coins: {int(tx_coins)}\n"
        f"🔥 Streak: {streak} days\n\n"
        f"🏆 **Badges:**\n{badge_text}"
    )
    
    kb = [
        [InlineKeyboardButton(text="🏆 Leaderboard", callback_data="menu_leaderboard")],
        [InlineKeyboardButton(text="📊 My Stats", callback_data="menu_stats")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="menu_settings")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
    ]
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

