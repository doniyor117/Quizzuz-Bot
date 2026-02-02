from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import create_user, get_user, copy_set_to_user, is_admin_check
from bot_services.translator import tr
from bot_services.utils import get_main_menu_kb, get_rank_title, MainStates
from bot_services import analytics_service
import json

router = Router()

# ===== GAME WEB APP DATA HANDLER =====
@router.message(F.web_app_data)
async def handle_game_data(message: types.Message):
    """Handle data sent from QuizzWords game via Telegram sendData."""
    try:
        data = json.loads(message.web_app_data.data)
        
        if data.get('type') == 'game_complete':
            user = await get_user(message.from_user.id)
            lang = user.get('lang_code', 'en') if user else 'en'
            
            tx_earned = data.get('tx_earned', 0)
            xp_earned = data.get('xp_earned', 0)
            score = data.get('score', 0)
            words = data.get('words', 0)
            level = data.get('level', 1)
            
            # Send reward message
            if lang == 'uz':
                msg = (
                    f"🎮 **Word Scramble Tugadi!**\n\n"
                    f"🏆 Ball: **{score}**\n"
                    f"📝 So'zlar: **{words}**\n"
                    f"📊 Daraja: **{level}**\n\n"
                    f"💎 **+{tx_earned:.1f} TX** ishladingiz!\n"
                    f"⭐ **+{xp_earned:.0f} XP** oldingiz!"
                )
            else:
                msg = (
                    f"🎮 **Word Scramble Complete!**\n\n"
                    f"🏆 Score: **{score}**\n"
                    f"📝 Words Found: **{words}**\n"
                    f"📊 Level Reached: **{level}**\n\n"
                    f"💎 **+{tx_earned:.1f} TX Coins** earned!\n"
                    f"⭐ **+{xp_earned:.0f} XP** gained!"
                )
            
            await message.answer(msg, parse_mode="Markdown")
    except Exception as e:
        import logging
        logging.error(f"Error handling game data: {e}")

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    user_id = message.from_user.id
    
    # Check if this is a group chat
    is_group = message.chat.type in ['group', 'supergroup']
    
    # Save referrer info in state to use after language selection
    args = command.args
    referrer_id = None
    quiz_id_to_play = None
    
    if args:
        if args.startswith("quiz_"):
            quiz_id_to_play = args.replace("quiz_", "")
        else:
            referrer_id = args
    
    # In groups: only respond to quiz deep links, ignore plain /start
    if is_group:
        if quiz_id_to_play:
            # Let group_play.py handle this via its own handler
            # This handler won't process - group_play has higher priority filter
            pass
        # Don't send anything for plain /start in groups
        return
            
    await state.update_data(referrer_id=referrer_id, pending_quiz_id=quiz_id_to_play)
    
    user = await get_user(user_id)
    
    if quiz_id_to_play and user:
        from bot_handlers.practice import start_custom_quiz_play
        await start_custom_quiz_play(message, state, quiz_id_to_play)
        return
    
    if not user:
        # NEW USER: Force Language Selection
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="init_lang_en"),
             InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="init_lang_uz")]
        ])
        await message.answer("🇺🇿 Iltimos, tilni tanlang.\n🇬🇧 Please, choose a language.", reply_markup=kb)
        await state.set_state(MainStates.waiting_language)
        return
    
    # Track command usage
    await analytics_service.track_command(user_id, 'start')
    
    # Existing User Flow
    lang = user['lang_code']
    if user.get('is_banned'):
        await message.answer("🚫 Your access has been restricted. Contact support if you believe this is an error.")
        return

    # Check for Deep Links (e.g. Shared Set)
    if command.args and command.args.startswith("add_set_"):
        source_set_id = command.args.replace("add_set_", "")
        new_id = await copy_set_to_user(user_id, source_set_id)
        if new_id:
            await message.answer(tr.get_text('set_cloned', lang))
        else:
            await message.answer("❌ Set not found or error.")

    await state.clear()
    await show_dashboard(message, user, lang)

# --- Language Selection Callback ---
@router.callback_query(MainStates.waiting_language, F.data.startswith("init_lang_"))
async def initial_language_selected(call: types.CallbackQuery, state: FSMContext):
    lang = call.data.replace("init_lang_", "")
    data = await state.get_data()
    referrer_id = data.get('referrer_id')
    
    # Create User now
    user, is_referred = await create_user(
        call.from_user.id, 
        call.from_user.first_name, 
        lang, 
        referrer_id,
        username=call.from_user.username  # Pass Telegram username
    )
    
    # Track new user registration
    await analytics_service.track_event(call.from_user.id, 'user_registered', {'language': lang, 'is_referred': is_referred})
    
    if is_referred and referrer_id:
        try:
            await call.bot.send_message(
                chat_id=referrer_id,
                text=tr.get_text('referral_bonus', 'en') # Alert referrer
            )
        except: pass
    
    await state.clear()
    await show_dashboard(call.message, user, lang, is_edit=True)

async def show_dashboard(message, user, lang, is_edit=False):
    # Get level-based progress
    level = user.get('level', 1)
    total_xp = user.get('total_xp', 0.0)
    tx_coins = round(user.get('xp', 0), 1)  # 'xp' field = TX coins
    streak = user.get('streak', 0)
    
    from bot_services.firebase_service import get_level_info, get_xp_for_level
    level_info = get_level_info(level)
    rank_name = level_info['rank_name']
    rank_emoji = level_info['rank_emoji']
    xp_for_next = level_info['xp_for_next_level']
    
    # Calculate progress to next level
    current_level_xp = get_xp_for_level(level)
    xp_in_current_level = total_xp - current_level_xp
    progress_percent = min(100, int((xp_in_current_level / xp_for_next) * 100))
    
    # Progress bar
    filled = int(progress_percent / 10)
    empty = 10 - filled
    progress_bar = "▰" * filled + "▱" * empty
    
    name = user.get('first_name', 'User')
    
    # New dashboard message with level system
    msg_text = (
        f"👋 **Welcome back, {name}!**\n\n"
        f"{rank_emoji} **{rank_name}** - Level {level}\n"
        f"{progress_bar} {progress_percent}%\n"
        f"📊 {int(xp_in_current_level)}/{xp_for_next} XP to Level {level + 1}\n\n"
        f"💰 **TX Coins:** {tx_coins}\n"
        f"🔥 **Streak:** {streak} days\n\n"
        f"_Your learning journey continues!_"
    )
    
    is_admin = await is_admin_check(user['user_id'])
    is_group = message.chat.type in ['group', 'supergroup']
    
    if is_edit:
        try:
            await message.edit_text(msg_text, reply_markup=get_main_menu_kb(tr.languages[lang], is_admin, is_group), parse_mode="Markdown")
        except TelegramBadRequest:
            pass # Message is already up to date
    else:
        await message.answer(msg_text, reply_markup=get_main_menu_kb(tr.languages[lang], is_admin, is_group), parse_mode="Markdown")

@router.callback_query(F.data == "cancel")
async def cancel_action(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    await show_dashboard(call.message, user, lang, is_edit=True)