from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import get_top_users
from bot_services.utils import get_rank_title

router = Router()

@router.callback_query(F.data == "menu_leaderboard")
async def show_leaderboard(call: types.CallbackQuery, state: FSMContext):
    """Display global leaderboard of top users by XP."""
    top_users = await get_top_users(10)
    
    if not top_users:
        await call.message.edit_text(
            "🏆 **Leaderboard**\n\n"
            "No users yet! Be the first to study!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 **Global Leaderboard**\n\n"
    
    for idx, user in enumerate(top_users):
        medal = medals[idx] if idx < 3 else f"{idx+1}."
        level_info = get_rank_title(user['level'])
        rank_emoji = level_info['rank_emoji']
        text += f"{medal} **{user['username'][:15]}** {rank_emoji}\n"
        text += f"    └ {int(user['total_xp'])} XP (Lv.{user['level']})\n"
    
    kb = [[InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]]
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
