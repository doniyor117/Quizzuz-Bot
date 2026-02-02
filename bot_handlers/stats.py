from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import get_user, get_user_sets, get_leaderboard, get_level_info, get_xp_for_level
from bot_services.translator import tr
from bot_services.utils import get_home_kb

router = Router()

@router.callback_query(F.data == "menu_stats")
async def show_stats(call: types.CallbackQuery):
    user_id = call.from_user.id
    user = await get_user(user_id)
    sets = await get_user_sets(user_id)
    lang = user['lang_code']
    
    # Get level and rank info
    level = user.get('level', 1)
    total_xp = user.get('total_xp', 0.0)
    tx_coins = round(user.get('xp', 0), 1)  # 'xp' field = TX coins
    
    level_info = get_level_info(level)
    rank_name = level_info['rank_name']
    rank_emoji = level_info['rank_emoji']
    xp_for_next = level_info['xp_for_next_level']
    
    # Calculate progress to next level
    current_level_xp = get_xp_for_level(level)
    xp_in_current_level = max(0, total_xp - current_level_xp)
    progress_percent = min(100, int((xp_in_current_level / max(1, xp_for_next)) * 100)) if xp_for_next > 0 else 0
    
    # Progress bar
    filled = int(progress_percent / 10)
    empty = 10 - filled
    progress_bar = "▰" * filled + "▱" * empty
    
    streak = user.get('streak', 0)
    first_name = user.get('first_name', 'User')
    freeze_count = user.get('streak_freeze_count', 0)
    
    text = (
        f"👤 **{first_name}'s Profile**\n\n"
        f"{rank_emoji} **{rank_name}** - Level {level}\n"
        f"{progress_bar} {progress_percent}%\n"
        f"📊 {int(xp_in_current_level)}/{xp_for_next} XP to Level {level + 1}\n\n"
        f"💰 TX Coins: **{tx_coins}**\n"
        f"🔥 Streak: **{streak} days**\n"
        f"🛡️ Streak Freezes: **{freeze_count}**\n"
        f"📚 Sets: **{len(sets)}**\n"
        f"🎴 Cards: **{sum([s['card_count'] for s in sets])}**"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡️ Buy Streak Freeze (350 TX)", callback_data="buy_freeze")],
        [InlineKeyboardButton(text=tr.get_text('btn_invite', lang), callback_data="invite_friend")],
        [InlineKeyboardButton(text=tr.get_text('btn_leaderboard', lang), callback_data="menu_leaderboard")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "invite_friend")
async def generate_invite_link(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    bot_info = await call.bot.get_me()
    bot_username = bot_info.username
    link = f"https://t.me/{bot_username}?start={call.from_user.id}"
    
    msg = tr.get_text('invite_msg', lang, link=link)
    await call.message.edit_text(msg, reply_markup=get_home_kb(tr.languages[lang]), disable_web_page_preview=True)

@router.callback_query(F.data == "leaderboard")
async def show_leaderboard(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    leaders = await get_leaderboard()
    
    list_text = ""
    for idx, leader in enumerate(leaders):
        name = leader.get('first_name', 'User')
        total_xp = int(leader.get('total_xp', 0))
        level = leader.get('level', 1)
        medal = "🥇" if idx==0 else ("🥈" if idx==1 else ("🥉" if idx==2 else f"{idx+1}."))
        list_text += f"{medal} {name} - Lvl {level} ({total_xp} XP)\n"
    
    final_text = tr.get_text('leaderboard_title', lang, list=list_text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back", callback_data="menu_stats"),
         InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ])
    
    await call.message.edit_text(final_text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "buy_freeze")
async def buy_streak_freeze(call: types.CallbackQuery):
    from bot_services.firebase_service import purchase_streak_freeze
    
    user = await get_user(call.from_user.id)
    current_tx = user.get('xp', 0)
    
    if current_tx < 350:
        await call.answer("❌ Not enough TX! You need 350 TX to buy a Streak Freeze.", show_alert=True)
        return
    
    success = await purchase_streak_freeze(call.from_user.id)
    
    if success:
        await call.answer("✅ Streak Freeze purchased! It will auto-save your streak if you miss a day.", show_alert=True)
        # Refresh stats to show updated counts
        await show_stats(call)
    else:
        await call.answer("❌ Purchase failed. Please try again.", show_alert=True)