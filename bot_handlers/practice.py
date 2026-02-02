import random
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.translator import tr
from bot_services.firebase_service import *
from bot_services.firebase_service import get_custom_quiz, increment_quiz_plays
from bot_services.ai_service import generate_card_content
from bot_services.utils import PracticeStates, get_cancel_kb, get_home_kb, get_rank_title, are_too_similar, build_vkm_pagination_kb

router = Router()

# --- BACKGROUND SPEED WORKER 🚀 ---
async def background_db_task(user_id, is_correct, xp_reward, bot):
    """Updates DB in the background so the user doesn't have to wait."""
    try:
        # This runs while the user is already looking at the next card
        hit_goal = await process_card_action(user_id, is_correct, xp_reward)
        if hit_goal:
            # If they hit the goal, send the notification asynchronously
            await bot.send_message(user_id, "🎯 Daily Goal Reached! (+2 TX)")
    except Exception as e:
        print(f"Background DB Error: {e}")

# Timer removed - users have full control over when to flip cards
@router.message(F.text.startswith("/play_"))
async def instant_play_command(message: types.Message, state: FSMContext):
    set_id = message.text.replace("/play_", "").strip()
    s = await get_set(set_id)
    if not s:
        await message.answer("❌ Set not found.")
        return
    await state.set_state(PracticeStates.configuring)
    await state.update_data(target_id=set_id)
    try: await message.delete()
    except: pass
    user = await get_user(message.from_user.id)
    lang = user['lang_code']
    kb = [
        [InlineKeyboardButton(text=tr.get_text('mode_flashcard', lang), callback_data="mode_flash")],
        [InlineKeyboardButton(text=tr.get_text('mode_mix', lang), callback_data="mode_mix")],
        [InlineKeyboardButton(text=tr.get_text('toggle_reverse', lang), callback_data="tog_rev")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ]
    await state.update_data(reverse=False)
    await message.answer(f"📚 **{s['set_name']}**\n" + tr.get_text('practice_config', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "menu_practice")
async def practice_start(call: types.CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    kb = [
        [InlineKeyboardButton(text="📝 My Sets", callback_data="src_my_sets"),
         InlineKeyboardButton(text="📚 Official Library", callback_data="src_main_books")],
        [InlineKeyboardButton(text="🧠 Smart Practice (SM-2)", callback_data="start_sm2")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ]
    
    help_text = "\n\n💡 **Smart Practice**: Reviews cards based on how well you know them. Study any set first in regular practice to unlock smart reviews!"
    try:
        await call.message.edit_text(tr.get_text('select_practice_source', lang) + help_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "src_my_sets")
async def browse_my_sets_root(call: types.CallbackQuery, state: FSMContext):
    await browse_my_sets(call, state, None)

@router.callback_query(F.data.startswith("prac_brow_"))
async def browse_my_sets_handler(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.replace("prac_brow_", "").split("_")
    raw_pid = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    parent_id = None if raw_pid == "None" else raw_pid
    await browse_my_sets(call, state, parent_id, page)

async def browse_my_sets(call: types.CallbackQuery, state: FSMContext, parent_id, page=0):
    user_id = call.from_user.id
    user = await get_user(user_id)
    lang = user['lang_code']
    
    # Fetch Folders and Sets
    folders = await get_user_folders(user_id, parent_id)
    sets = await get_user_sets(user_id, parent_id)
    
    if not folders and not sets and parent_id:
        await call.answer(tr.get_text('empty_book', lang), show_alert=True)
        # Don't return, let them see empty folder
    
    current_name = "My Library"
    current_description = ""
    back_cb = "cancel"
    raw_pid = parent_id if parent_id else "None"
    
    if parent_id:
        curr = await get_folder(parent_id)
        if curr:
            current_name = curr['folder_name']
            current_description = curr.get('description', '')
            gp = curr.get('parent_id')
            gp_raw = gp if gp else "None"
            back_cb = f"prac_brow_{gp_raw}_0"
        else:
            parent_id = None
    
    # Combine for pagination
    all_items = []
    for f in folders:
        all_items.append({'type': 'folder', 'data': f})
    for s in sets:
        all_items.append({'type': 'set', 'data': s})
    
    # Paginate
    # VKM Style Pagination Logic
    limit = 10
    start_idx = page * limit
    end_idx = start_idx + limit
    current_items = all_items[start_idx:end_idx]
    
    # 1. Build Text List
    page_text = f" (Page {page+1})" if len(all_items) > limit else ""
    display_text = f"📂 **{current_name}**{page_text}"
    if current_description:
        display_text += f"\n_{current_description}_"
    display_text += "\n\n"
    
    if not current_items:
        display_text += "_(Empty)_"
    else:
        for idx, item in enumerate(current_items, 1):
            if item['type'] == 'folder':
                display_text += f"**{idx}.** 📁 {item['data']['folder_name']}\n"
            else:
                s = item['data']
                icon = "🌍" if s['is_public'] else "🔒"
                display_text += f"**{idx}.** {icon} {s['set_name']} ({s.get('card_count', 0)})\n"
    
    # 2. Build Buttons Items for Helper
    kb_items = []
    for item in current_items:
        if item['type'] == 'folder':
            f = item['data']
            kb_items.append({'callback_data': f"prac_brow_{f['folder_id']}_0"})
        else:
            s = item['data']
            kb_items.append({'callback_data': f"p_set_{s['set_id']}"})
            
    # 3. Generate Keyboard
    # nav_prefix should be like "prac_brow_{parent_id}_"
    nav_pid = raw_pid
    kb = build_vkm_pagination_kb(
        items=kb_items,
        page=page,
        total_items=len(all_items),
        limit=limit,
        back_callback=back_cb,
        nav_prefix=f"prac_brow_{nav_pid}_"
    )
    
    await state.set_state(PracticeStates.selecting_set)
    await call.message.edit_text(display_text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "src_main_books")
async def start_book_browse(call: types.CallbackQuery, state: FSMContext):
    await browse_official_folder(call, None)

@router.callback_query(F.data.startswith("brow_book_"))
async def continue_book_browse(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.replace("brow_book_", "").split("_")
    raw_pid = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    parent_id = None if raw_pid == "None" else raw_pid
    await browse_official_folder(call, parent_id, page)

async def browse_official_folder(call, parent_id, page=0):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    subfolders = await get_admin_folders(parent_id, folder_type='official')
    sets = []
    if parent_id: 
        sets = await get_sets_in_folder(parent_id)
    
    if not subfolders and not sets and parent_id:
        await call.answer(tr.get_text('empty_book', lang), show_alert=True)
        return
        
    # Combine and Paginate
    # We treat folders and sets as one list for pagination
    # Items: [{'type': 'folder', 'data': f}, {'type': 'set', 'data': s}]
    all_items = []
    for f in subfolders: all_items.append({'type': 'folder', 'data': f})
    for s in sets: all_items.append({'type': 'set', 'data': s})
    
    # VKM Style Pagination Logic
    limit = 10
    start_idx = page * limit
    end_idx = start_idx + limit
    current_items = all_items[start_idx:end_idx]
    
    # 1. Build Text List
    folder_description = ""
    title = "Official Library"
    back_cb = "cancel"
    
    if parent_id:
        curr = await get_folder(parent_id)
        if curr:
            title = curr['folder_name']
            folder_description = curr.get('description', '')
            gp = curr.get('parent_id')
            gp_raw = gp if gp else "None"
            back_cb = f"brow_book_{gp_raw}_0"
        else:
            parent_id = None

    page_text = f" (Page {page+1})" if len(all_items) > limit else ""
    display_text = f"📚 **{title}**{page_text}"
    if folder_description:
        display_text += f"\n_{folder_description}_"
    display_text += "\n\n"
    
    if not current_items:
        display_text += "_(Empty)_"
    else:
        for idx, item in enumerate(current_items, 1):
            if item['type'] == 'folder':
                display_text += f"**{idx}.** 📁 {item['data']['folder_name']}\n"
            else:
                s = item['data']
                display_text += f"**{idx}.** 📄 {s['set_name']}\n"
    
    # 2. Build Buttons Items
    kb_items = []
    for item in current_items:
        if item['type'] == 'folder':
            f = item['data']
            kb_items.append({'callback_data': f"brow_book_{f['folder_id']}_0"})
        else:
            s = item['data']
            kb_items.append({'callback_data': f"p_set_{s['set_id']}"})
            
    # 3. Generate Keyboard
    raw_pid = parent_id if parent_id else "None"
    kb = build_vkm_pagination_kb(
        items=kb_items,
        page=page,
        total_items=len(all_items),
        limit=limit,
        back_callback=back_cb,
        nav_prefix=f"brow_book_{raw_pid}_"
    )
    
    # 4. Add favorites button if we're inside a folder (not root)
    if parent_id:
        from bot_services.firebase_service import is_favorite
        is_fav = await is_favorite(call.from_user.id, 'folder', parent_id)
        fav_text = "💔 Remove Favorite" if is_fav else "❤️ Add to Favorites"
        kb.inline_keyboard.insert(-1, [InlineKeyboardButton(text=fav_text, callback_data=f"tog_fav_folder_{parent_id}")])
    
    await call.message.edit_text(display_text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("p_set_"))
async def config_practice_set(call: types.CallbackQuery, state: FSMContext):
    set_id = call.data.replace("p_set_", "")
    await state.update_data(target_id=set_id)
    await show_config_ui(call, state)

async def show_config_ui(call: types.CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    data = await state.get_data()
    target_id = data.get('target_id')
    
    # Initialize reverse if not set
    if 'reverse' not in data:
        await state.update_data(reverse=False)
        data = await state.get_data()
    
    reverse_mode = data.get('reverse', False)
    reverse_text = "Def ➡️ Term" if reverse_mode else "Term ➡️ Def"
    
    # Check AI Config
    config = await get_bot_config()
    ai_enabled = config.get('ai_enabled', True)
    
    # Check if favorited
    from bot_services.firebase_service import is_favorite
    is_fav = await is_favorite(call.from_user.id, 'set', target_id)
    fav_text = "💔 Remove Favorite" if is_fav else "❤️ Add to Favorites"

    kb = [
        [InlineKeyboardButton(text=tr.get_text('mode_flashcard', lang), callback_data="mode_flash"),
         InlineKeyboardButton(text="⚡ Quiz", callback_data="mode_quiz")],
    ]
    
    # Mix Test + AI Review (if enabled)
    row2 = [InlineKeyboardButton(text=tr.get_text('mode_mix', lang), callback_data="mode_mix")]
    if ai_enabled:
        row2.append(InlineKeyboardButton(text="🤖 AI Review", callback_data="mode_ai_review"))
    kb.append(row2)
        
    kb.extend([
        [InlineKeyboardButton(text=reverse_text, callback_data="tog_rev")],
        [InlineKeyboardButton(text=fav_text, callback_data=f"tog_fav_set_{target_id}")],
        [InlineKeyboardButton(text="👀 Preview", callback_data=f"prev_prac_{target_id}_0")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ])
    await state.set_state(PracticeStates.configuring)
    await call.message.edit_text(tr.get_text('practice_config', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("prev_prac_"))
async def preview_set_practice(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.replace("prev_prac_", "").split("_")
    set_id = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    
    cards = await get_set_cards(set_id)
    
    if not cards:
        await call.answer("Set is empty.", show_alert=True)
        return

    limit = 15
    start_idx = page * limit
    end_idx = start_idx + limit
    current_cards = cards[start_idx:end_idx]
    
    preview_text = f"👀 **Preview: {len(cards)} cards (Page {page+1})**\n\n"
    for i, c in enumerate(current_cards):
        term = c['term']
        defi = c.get('definition', '???')
        preview_text += f"{start_idx + i + 1}. {term} - {defi}\n"
    
    kb = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"prev_prac_{set_id}_{page-1}"))
    if end_idx < len(cards):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"prev_prac_{set_id}_{page+1}"))
    
    if nav_row:
        kb.append(nav_row)
    
    kb.append([InlineKeyboardButton(text="Back", callback_data=f"p_set_{set_id}")])
    await call.message.edit_text(preview_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "tog_rev")
async def toggle_reverse(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    rev = not data.get('reverse', False)
    await state.update_data(reverse=rev)
    await show_config_ui(call, state)

@router.callback_query(F.data.startswith("mode_") & ~F.data.endswith("quiz"))
async def start_session(call: types.CallbackQuery, state: FSMContext):
    """Start a practice session. Excludes mode_quiz which has its own handler."""
    mode = call.data.replace("mode_", "")
    data = await state.get_data()
    
    # Safety check: ensure target_id exists
    if 'target_id' not in data:
        await call.answer("❌ Please select a set first!", show_alert=True)
        return
    
    if data.get('is_retry'):
        cards = data.get('cards', [])
    else:
        cards = await get_set_cards(data['target_id'])
    
    if not cards:
        await call.answer("No cards found!", show_alert=True)
        return
    
    if not data.get('is_retry'): 
        random.shuffle(cards)
    
    session_data = {
        "cards": cards,
        "index": 0,
        "score": 0,
        "xp_earned": 0.0, 
        "mistakes": [],
        "mode": mode,
        "reverse": data.get('reverse', False),
        "is_retry": False
    }
    await state.update_data(**session_data)
    await state.set_state(PracticeStates.active_session)
    await next_card(call.message, state, first=True)

async def next_card(message: types.Message, state: FSMContext, first=False):
    data = await state.get_data()
    idx = data['index']
    cards = data['cards']
    mode = data['mode']
    user_id = message.chat.id
    
    # In high-speed mode, fetching user on every card is slow.
    # We fetch only at end. For language, we assume 'en' or check if we can pass it.
    # Optimization: Fetch user ONLY at finish or start.
    # For now, we fetch to be safe, but 'process_card_action' handles the heavy lifting in BG.
    # If ultra-speed needed, store lang in state.
    lang = 'en' # Default fallback for speed during loop if not critical
    # To be correct, let's fetch user only if we are finishing.
    
    if idx >= len(cards):
        # FINISH STATE - Must fetch user to show stats
        user = await get_user(user_id)
        lang = user['lang_code']
        
        deck_size = len(cards)
        score = data['score']
        
        # XP is already awarded per-card via background_db_task (0.25 XP per card)
        # Only award bonus TX coins based on performance
        tx_gained = 0
        if score >= 80:
            tx_gained = deck_size * 0.1  # Bonus TX coins for good performance (>=80% correct)
        
        if tx_gained > 0:
            await add_tx_coins(user_id, tx_gained)
        
        mistakes = data.get('mistakes', [])
        mistake_text_lines = []
        for m in mistakes:
            definition_text = m.get('definition', '???')
            mistake_text_lines.append(f"❌ {m['term']} - {definition_text}")
        
        msg = ""
        if mode == 'flash':
            known_count = len(cards) - len(mistakes)
            msg = tr.get_text('flash_summary', lang, known=known_count, unknown=len(mistakes))
            msg += f"\n💎 TX: +{tx_gained}"
        else:
            msg = tr.get_text('session_done', lang, score=data['score'], total=len(cards), xp=tx_gained)

        if mistakes:
            msg += "\n\n" + "\n".join(mistake_text_lines[:10]) 
            if len(mistakes) > 10:
                msg += f"\n...and {len(mistakes)-10} more."

        old_xp = user.get('xp', 0)
        new_xp = old_xp + tx_gained
        if get_rank_title(old_xp) != get_rank_title(new_xp):
            msg += f"\n\n🎉 **LEVEL UP!**\n**{get_rank_title(new_xp)}** 🦁"

        kb_rows = []
        if mistakes:
            btn_text = tr.get_text('btn_retry_unknown', lang, count=len(mistakes))
            kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data="retry_mistakes")])
        
        kb_rows.append([InlineKeyboardButton(text=tr.get_text('btn_restart_full', lang), callback_data="restart_full")])
        kb_rows.append([InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")])
        
        try:
            if first:
                await message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="Markdown")
            else:
                await message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="Markdown")
        except:
            await message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="Markdown")
        return

    # CARD DISPLAY (Speed Optimized - No User Fetch)
    # We guess Lang or use state. ideally store lang in state at start_session.
    # For buttons, we need lang. 
    # Let's assume 'en' or fetch quickly? 
    # Actually, `tr.get_text` defaults to 'en'. 
    # To keep it FAST, we skip user fetch here. The buttons might be in English for a split second if we don't pass lang.
    # FIX: Let's try to get lang from state if available, else default.
    # Or just accept one fetch per card (since DB write is now backgrounded, read is fast).
    # Let's do the fetch to ensure correct language, as read is usually <100ms and acceptable.
    # If user complains about 100ms, we can cache lang in state.
    user = await get_user(user_id) # Keeping this for correct UI language
    lang = user['lang_code']

    card = cards[idx]
    definition_text = card.get('definition', '???')
    q = definition_text if data['reverse'] else card['term']
    a = card['term'] if data['reverse'] else definition_text

    if mode == "flash":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr.get_text('btn_flip', lang), callback_data="flash_flip")],
            [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
        ])
        text = f"{tr.get_text('flashcard_front', lang)}\n\n**{q}**"
        
        if first: 
            await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        else:
            try: await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            except: await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        # Timer removed - user controls when to flip
    
    elif mode == "ai_review":
        # AI Review mode - similar to flashcard but with AI-generated comprehensive answer
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Show AI Review", callback_data="ai_review_flip")],
            [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
        ])
        text = f"🤖 AI Review\n\n**{q}**"
        
        if first: 
            await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        else:
            try: await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            except: await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        # No auto-reveal for AI mode (takes longer)
    
    elif mode == "mix":
        is_mcq = random.choice([True, False])
        if is_mcq and len(cards) >= 4:
            # MCQ MODE with similarity filtering
            options = [a]  # Start with correct answer
            used_card_ids = [card.get('card_id') or f"current_card"]  # Track used cards to avoid duplicates
            attempts = 0
            max_attempts = 50  # Safety limit
            
            while len(options) < 4 and attempts < max_attempts:
                attempts += 1
                wrong = random.choice(cards)
                
                # Skip if we already used this card
                if wrong.get('card_id') in used_card_ids:
                    continue
                
                wrong_def = wrong.get('definition', '???')
                wa = wrong['term'] if data['reverse'] else wrong_def
                
                # Check exact duplicate
                if wa in options:
                    continue
                
                # Check similarity with ALL existing options
                too_similar = False
                for existing_opt in options:
                    if are_too_similar(wa, existing_opt):
                        too_similar = True
                        break
                
                # Only add if not too similar
                if not too_similar:
                    options.append(wa)
                    used_card_ids.append(wrong.get('card_id'))
            
            # If we couldn't get 4 unique options, fall back to True/False
            if len(options) < 4:
                show_true = random.choice([True, False])
                fake_def = cards[(idx+1)%len(cards)]['term'] if data['reverse'] else cards[(idx+1)%len(cards)].get('definition', '???')
                disp_def = a if show_true else fake_def
                correct_choice = "True" if show_true else "False"
                await state.update_data(expected_tf=correct_choice)
                kb = [
                    [InlineKeyboardButton(text=tr.get_text('btn_true', lang), callback_data="tf_res_True")],
                    [InlineKeyboardButton(text=tr.get_text('btn_false', lang), callback_data="tf_res_False")],
                    [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
                ]
                try:
                    await message.edit_text(tr.get_text('mix_tf_prompt', lang, term=q, definition=disp_def), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                except TelegramBadRequest:
                    await message.answer(tr.get_text('mix_tf_prompt', lang, term=q, definition=disp_def), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            else:
                # We have 4 unique options - shuffle and track correct index
                random.shuffle(options)
                correct_index = options.index(a)
                
                # Store in state for validation
                await state.update_data(
                    mcq_correct_index=correct_index,
                    mcq_options=options,
                    mcq_correct_answer=a
                )
                
                # Build keyboard with index-based callbacks
                kb_list = []
                for i, opt in enumerate(options):
                    kb_list.append([
                        InlineKeyboardButton(text=opt, callback_data=f"mcq_ans_{i}")
                    ])
                
                # Add Show Answer button
                kb_list.append([
                    InlineKeyboardButton(text="💡 Show Answer", callback_data="mcq_show")
                ])
                kb_list.append([
                    InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")
                ])
                
                try:
                    await message.edit_text(tr.get_text('mix_mcq_prompt', lang, question=q), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
                except TelegramBadRequest:
                    await message.answer(tr.get_text('mix_mcq_prompt', lang, question=q), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
        else:
            # True/False mode (when MCQ not selected or not enough cards)
            show_true = random.choice([True, False])
            fake_def = cards[(idx+1)%len(cards)]['term'] if data['reverse'] else cards[(idx+1)%len(cards)].get('definition', '???')
            disp_def = a if show_true else fake_def
            correct_choice = "True" if show_true else "False"
            await state.update_data(expected_tf=correct_choice)
            kb = [
                [InlineKeyboardButton(text=tr.get_text('btn_true', lang), callback_data="tf_res_True")],
                [InlineKeyboardButton(text=tr.get_text('btn_false', lang), callback_data="tf_res_False")],
                [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
            ]
            try:
                await message.edit_text(tr.get_text('mix_tf_prompt', lang, term=q, definition=disp_def), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            except TelegramBadRequest:
                await message.answer(tr.get_text('mix_tf_prompt', lang, term=q, definition=disp_def), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "retry_mistakes")
async def retry_mistakes_handler(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mistakes = data.get('mistakes', [])
    if not mistakes:
        await call.answer("No mistakes!", show_alert=True)
        return
    await state.update_data(cards=mistakes, is_retry=True)
    mode = data.get('mode', 'flash')
    session_data = {
        "cards": mistakes,
        "index": 0,
        "score": 0,
        "xp_earned": 0.0, 
        "mistakes": [],
        "mode": mode,
        "reverse": data.get('reverse', False),
        "is_retry": True
    }
    await state.update_data(**session_data)
    await next_card(call.message, state, first=False)

@router.callback_query(F.data == "restart_full")
async def restart_full_handler(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cards = await get_set_cards(data['target_id'])
    random.shuffle(cards)
    
    session_data = {
        "cards": cards,
        "index": 0,
        "score": 0,
        "xp_earned": 0.0, 
        "mistakes": [],
        "mode": data.get('mode', 'flash'),
        "reverse": data.get('reverse', False),
        "is_retry": False 
    }
    await state.update_data(**session_data)
    await next_card(call.message, state, first=False)

@router.callback_query(F.data == "flash_flip", PracticeStates.active_session)
async def flash_flip(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data or not data.get('cards') or data['index'] >= len(data['cards']):
        await call.answer("Session expired.", show_alert=True)
        await state.clear()
        return
    card = data['cards'][data['index']]
    definition_text = card.get('definition', '???')
    
    # Get term and answer based on mode
    if data['reverse']:
        question = definition_text  # User saw definition
        answer = card['term']       # Answer is the term
    else:
        question = card['term']      # User saw term
        answer = definition_text     # Answer is definition
    
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    kb = [
        [
            InlineKeyboardButton(text="❌ Again", callback_data="flash_rate_1"),
            InlineKeyboardButton(text="⚠️ Hard", callback_data="flash_rate_2")
        ],
        [
            InlineKeyboardButton(text="✅ Good", callback_data="flash_rate_3"),
            InlineKeyboardButton(text="⭐ Easy", callback_data="flash_rate_4")
        ],
        [InlineKeyboardButton(text="⚡ Mastered", callback_data="flash_rate_5")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ]
    
    # Show both term and answer for better memorization
    display_text = f"📝 **{question}**\n\n➡️ {answer}\n\n_How well did you know this?_"
    await call.message.edit_text(display_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "ai_review_flip", PracticeStates.active_session)
async def ai_review_flip(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    if not data or not data.get('cards') or data['index'] >= len(data['cards']):
        await call.answer("Session expired.", show_alert=True)
        await state.clear()
        return
    
    card = data['cards'][data['index']]
    term = card['term'] if not data['reverse'] else card.get('definition', '???')
    
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    # Show loading message
    await call.message.edit_text("🤖 Generating AI review...\nThis may take a moment.")
    
    # Generate AI content
    ai_content = await generate_card_content(term, reverse_mode=data.get('reverse', False), user_id=call.from_user.id)
    
    if ai_content and 'error' in ai_content:
        if ai_content['error'] == 'limit_reached':
            await call.message.edit_text(
                f"⚠️ **Daily AI Limit Reached**\n\n"
                f"You have used your 40 free AI requests for today.\n"
                f"Limit resets at midnight (Tashkent time).\n\n"
                f"Answer:\n**{term if data.get('reverse', False) else card.get('definition', '???')}**",
                parse_mode="Markdown"
            )
            return

    if ai_content:
        # Build comprehensive review
        review_text = f"🤖 **AI Review: {term}**\n\n"
        
        if ai_content.get('definition'):
            review_text += f"📝 **Definition:**\n{ai_content['definition']}\n\n"
        
        if ai_content.get('translation'):
            lang_label = "English" if data.get('reverse', False) else "Uzbek"
            flag = "🇬🇧" if data.get('reverse', False) else "🇺🇿"
            review_text += f"{flag} **{lang_label}:**\n{ai_content['translation']}\n\n"
        
        if ai_content.get('examples'):
            review_text += "📝 **Examples:**\n"
            for ex in ai_content['examples'][:2]:  # Limit to 2 examples
                review_text += f"- _{ex}_\n"
    else:
        # Fallback if AI fails
        answer = card.get('definition', '???') if not data['reverse'] else card['term']
        review_text = f"❌ AI unavailable\n\nAnswer:\n**{answer}**"
    
    # Show rating buttons
    kb = [
        [
            InlineKeyboardButton(text="❌ Again", callback_data="flash_rate_1"),
            InlineKeyboardButton(text="⚠️ Hard", callback_data="flash_rate_2")
        ],
        [
            InlineKeyboardButton(text="✅ Good", callback_data="flash_rate_3"),
            InlineKeyboardButton(text="⭐ Easy", callback_data="flash_rate_4")
        ],
        [InlineKeyboardButton(text="⚡ Mastered", callback_data="flash_rate_5")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ]
    
    await call.message.edit_text(review_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("flash_rate_"), PracticeStates.active_session)
async def flash_rate(call: types.CallbackQuery, state: FSMContext):
    await call.answer() # Immediate UI response
    quality = int(call.data.replace("flash_rate_", ""))
    data = await state.get_data()
    user_id = call.from_user.id
    
    if not data or not data.get('cards') or data['index'] >= len(data['cards']):
        return 
    
    card = data['cards'][data['index']]
    is_correct = quality >= 3  # Good or Easy = correct
    
    if is_correct:
        await state.update_data(score=data['score'] + 1, xp_earned=data['xp_earned'] + 0.25)
    else:
        mistakes = data['mistakes']
        mistakes.append(card)
        await state.update_data(mistakes=mistakes)
    
    # CRITICAL FIX: Update card progress for Smart Practice integration
    set_id = data.get('target_id')
    if set_id and 'card_id' in card:
        asyncio.create_task(update_card_progress(user_id, set_id, card['card_id'], quality))
    
    # SPEED FIX: Run database update in background task
    asyncio.create_task(background_db_task(user_id, is_correct, 0.25, call.bot))
    
    # Reset notification backoff - user is actively practicing!
    from bot_services.firebase_service import reset_notification_backoff
    asyncio.create_task(reset_notification_backoff(user_id))
    
    await state.update_data(index=data['index'] + 1)
    await next_card(call.message, state, first=False)


@router.callback_query(F.data.startswith("mcq_ans_"), PracticeStates.active_session)
async def handle_mcq_answer(call: types.CallbackQuery, state: FSMContext):
    """Handle MCQ answer selection with index-based validation."""
    await call.answer()
    
    # Extract selected index
    selected_index = int(call.data.replace("mcq_ans_", ""))
    
    data = await state.get_data()
    user_id = call.from_user.id
    
    if not data or not data.get('cards') or data['index'] >= len(data['cards']):
        return
    
    # Validate answer by index (not text!)
    correct_index = data.get('mcq_correct_index', 0)
    options = data.get('mcq_options', [])
    is_correct = selected_index == correct_index
    
    # Get user language
    user = await get_user(user_id)
    lang = user['lang_code']
    
    # Get the original question (term)
    card = data['cards'][data['index']]
    question_term = card.get('definition', '???') if data.get('reverse') else card.get('term', '???')
    
    # Build result message with feedback
    if is_correct:
        correct_answer = options[correct_index] if correct_index < len(options) else "???"
        result_text = f"📝 **{question_term}**\n\n"
        result_text += f"✅ **Correct!** → {correct_answer}\n\n"
    else:
        correct_answer = options[correct_index] if correct_index < len(options) else "???"
        selected_answer = options[selected_index] if selected_index < len(options) else "???"
        result_text = f"📝 **{question_term}**\n\n"
        result_text += f"❌ **Incorrect!**\n"
        result_text += f"You selected: {selected_answer}\n"
        result_text += f"➡️ Correct: **{correct_answer}**\n\n"
    
    # Show difficulty rating
    kb = [
        [
            InlineKeyboardButton(text="❌ Again", callback_data="mix_rate_1"),
            InlineKeyboardButton(text="⚠️ Hard", callback_data="mix_rate_2")
        ],
        [
            InlineKeyboardButton(text="✅ Good", callback_data="mix_rate_3"),
            InlineKeyboardButton(text="⭐ Easy", callback_data="mix_rate_4")
        ],
        [InlineKeyboardButton(text="⚡ Mastered", callback_data="mix_rate_5")]
    ]
    
    await state.update_data(mix_is_correct=is_correct)
    await call.message.edit_text(
        f"{result_text}_How well did you know this?_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "mcq_show", PracticeStates.active_session)
async def show_mcq_answer(call: types.CallbackQuery, state: FSMContext):
    """Show the correct answer without selecting (counts as incorrect)."""
    await call.answer()
    
    data = await state.get_data()
    user_id = call.from_user.id
    
    if not data or not data.get('cards'):
        return
    
    correct_index = data.get('mcq_correct_index', 0)
    options = data.get('mcq_options', [])
    correct_answer = options[correct_index] if correct_index < len(options) else "???"
    
    # Get the original question (term)
    card = data['cards'][data['index']]
    question_term = card.get('definition', '???') if data.get('reverse') else card.get('term', '???')
    
    user = await get_user(user_id)
    lang = user['lang_code']
    
    # Show answer with term for memorization
    result_text = f"📝 **{question_term}**\n\n"
    result_text += f"💡 **Answer Revealed**\n"
    result_text += f"➡️ {correct_answer}\n\n"
    
    kb = [
        [
            InlineKeyboardButton(text="❌ Again", callback_data="mix_rate_1"),
            InlineKeyboardButton(text="⚠️ Hard", callback_data="mix_rate_2")
        ],
        [
            InlineKeyboardButton(text="✅ Good", callback_data="mix_rate_3"),
            InlineKeyboardButton(text="⭐ Easy", callback_data="mix_rate_4")
        ],
        [InlineKeyboardButton(text="⚡ Mastered", callback_data="mix_rate_5")]
    ]
    
    # Treat as incorrect since they peeked
    await state.update_data(mix_is_correct=False)
    await call.message.edit_text(
        f"{result_text}_How well did you know this?_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("mix_rate_"), PracticeStates.active_session)
async def handle_mix_rating(call: types.CallbackQuery, state: FSMContext):
    """Handle difficulty rating after mix mode (MCQ/TF) question."""
    await call.answer()
    quality = int(call.data.replace("mix_rate_", ""))
    data = await state.get_data()
    user_id = call.from_user.id
    
    if not data or not data.get('cards') or data['index'] >= len(data['cards']):
        return
    
    card = data['cards'][data['index']]
    was_correct = data.get('mix_is_correct', False)
    
    # Update score based on user's original answer
    if was_correct:
        await state.update_data(score=data['score'] + 1, xp_earned=data['xp_earned'] + 0.25)
    else:
        mistakes = data['mistakes']
        mistakes.append(card)
        await state.update_data(mistakes=mistakes)
    
    # Update card progress for Smart Practice
    set_id = data.get('target_id')
    if set_id and 'card_id' in card:
        asyncio.create_task(update_card_progress(user_id, set_id, card['card_id'], quality))
    
    # Background DB task for user stats
    asyncio.create_task(background_db_task(user_id, was_correct, 0.25, call.bot))
    
    # Reset notification backoff - user is actively practicing!
    from bot_services.firebase_service import reset_notification_backoff
    asyncio.create_task(reset_notification_backoff(user_id))
    
    await state.update_data(index=data['index'] + 1)
    await next_card(call.message, state, first=False)

@router.callback_query(F.data.startswith("tf_res_"), PracticeStates.active_session)
async def handle_tf(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    user_choice = call.data.replace("tf_res_", "")
    data = await state.get_data()
    user_id = call.from_user.id
    expected = data.get('expected_tf')
    
    if not data or not data.get('cards') or data['index'] >= len(data['cards']):
        return 

    is_correct = user_choice == expected
    
    # Show difficulty rating prompt
    user = await get_user(user_id)
    lang = user['lang_code']
    
    result_text = "✅ Correct!" if is_correct else "❌ Incorrect!"
    
    kb = [
        [
            InlineKeyboardButton(text="❌ Again", callback_data="mix_rate_1"),
            InlineKeyboardButton(text="⚠️ Hard", callback_data="mix_rate_2")
        ],
        [
            InlineKeyboardButton(text="✅ Good", callback_data="mix_rate_3"),
            InlineKeyboardButton(text="⭐ Easy", callback_data="mix_rate_4")
        ],
        [InlineKeyboardButton(text="⚡ Mastered", callback_data="mix_rate_5")]
    ]
    
    await state.update_data(mix_is_correct=is_correct)
    await call.message.edit_text(f"{result_text}\n\nHow well did you know this?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# ==========================================
# SM-2 SMART PRACTICE LOGIC
# ==========================================
@router.callback_query(F.data == "start_sm2")
async def start_sm2_practice(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = await get_user(user_id)
    lang = user['lang_code']
    
    # Fetch due cards
    cards = await get_due_cards(user_id)
    
    if not cards:
        msg = (
            "🎉 **All caught up!**\n\n"
            "No cards are due for review right now.\n\n"
            "💡 **How Smart Practice works:**\n"
            "1. Practice any set in Flashcard or Mix mode\n"
            "2. Rate each card: Again (1min), Hard (10min), Good (1day), or Easy (3days)\n"
            "3. Cards return based on your rating - harder cards come back sooner!\n\n"
            "Start practicing now to build your review queue!"
        )
        await call.message.edit_text(msg, reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")
        return
        
    random.shuffle(cards)
    
    session_data = {
        "cards": cards,
        "index": 0,
        "mode": "sm2",
        "reverse": False # SM-2 usually standard direction
    }
    await state.update_data(**session_data)
    await state.set_state(PracticeStates.active_session)
    await next_sm2_card(call.message, state, first=True)

async def next_sm2_card(message: types.Message, state: FSMContext, first=False):
    data = await state.get_data()
    idx = data['index']
    cards = data['cards']
    
    if idx >= len(cards):
        # FIXED: Edit message instead of sending new one
        try:
            await message.edit_text(
                "✅ **Smart Session Complete!**\nCome back later for more.",
                reply_markup=get_home_kb({'btn_home': '🏠 Home'}),
                parse_mode="Markdown"
            )
        except:
            await message.answer(
                "✅ **Smart Session Complete!**\nCome back later for more.",
                reply_markup=get_home_kb({'btn_home': '🏠 Home'}),
                parse_mode="Markdown"
            )
        await state.clear()
        return

    card = cards[idx]
    term = card['term']
    
    # Show Question
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Show Answer", callback_data="sm2_show")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="cancel")]
    ])
    
    text = f"🧠 **Smart Review**\n\n**{term}**"
    
    if first:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "sm2_show", PracticeStates.active_session)
async def sm2_show_answer(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    card = data['cards'][data['index']]
    definition = card.get('definition', '???')
    term = card['term']
    
    kb = [
        [
            InlineKeyboardButton(text="❌ Again (1min)", callback_data="sm2_rate_1"),
            InlineKeyboardButton(text="⚠️ Hard (10min)", callback_data="sm2_rate_2")
        ],
        [
            InlineKeyboardButton(text="✅ Good (1d)", callback_data="sm2_rate_3"),
            InlineKeyboardButton(text="⭐ Easy (3d)", callback_data="sm2_rate_4")
        ],
        [
            InlineKeyboardButton(text="⚡ Mastered (1yr)", callback_data="sm2_rate_5")
        ]
    ]
    
    await call.message.edit_text(f"**{term}**\n\n{definition}\n\nRate difficulty:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("sm2_rate_"), PracticeStates.active_session)
async def handle_sm2_rating(call: types.CallbackQuery, state: FSMContext):
    quality = int(call.data.replace("sm2_rate_", ""))
    data = await state.get_data()
    card = data['cards'][data['index']]
    user_id = call.from_user.id
    
    # Update Progress
    await update_card_progress(user_id, card['set_id'], card['card_id'], quality)
    
    # Award XP for practice
    # Award small XP for using AI
    await add_total_xp(user_id, 0.25)
    
    # Next Card
    await state.update_data(index=data['index'] + 1)
    await next_sm2_card(call.message, state, first=False)


# ==========================================
# QUIZ MODE (TELEGRAM NATIVE POLLS)
# ==========================================

@router.callback_query(F.data == "mode_quiz")
async def start_quiz_mode(call: types.CallbackQuery, state: FSMContext):
    """Start a Quiz Mode session using Telegram native polls."""
    print(f"DEBUG: Quiz Mode triggered for user {call.from_user.id}")
    try:
        await call.answer("⚡ Starting Quiz...")
        
        data = await state.get_data()
        set_id = data.get('target_id')
        reverse = data.get('reverse', False)
        print(f"DEBUG: Set ID: {set_id}, Reverse: {reverse}")
        
        if not set_id:
            await call.message.edit_text("❌ No set selected. Please select a set first.")
            return
        
        # DEBUG: Check cards fetch
        print("DEBUG: Fetching cards...")
        cards = await get_set_cards(set_id)
        print(f"DEBUG: Cards fetched: {len(cards) if cards else 'None'}")
        
        if not cards or len(cards) < 4:
            await call.message.edit_text("⚠️ Need at least 4 cards for Quiz Mode. Add more cards to this set.")
            return
        
        # Shuffle and limit to 10 questions
        random.shuffle(cards)
        quiz_cards = cards[:min(10, len(cards))]
        
        # Store quiz state
        await state.update_data(
            quiz_cards=quiz_cards,
            quiz_index=0,
            quiz_correct=0,
            quiz_total=len(quiz_cards),
            quiz_all_cards=cards,  # For generating distractors
            quiz_reverse=reverse
        )
        print(f"DEBUG: State updated. Starting quiz with {len(quiz_cards)} questions.")
        
        # Get bot from callback
        bot = call.bot
        if not bot:
            print("CRITICAL: call.bot is None!")
            # Fallback (shouldn't happen in normal context)
            from main import bot as fallback_bot
            bot = fallback_bot
            
        chat_id = call.message.chat.id
        
        try:
            await call.message.delete()
        except Exception as e:
            print(f"DEBUG: Delete message failed: {e}")
        
        print(f"DEBUG: Calling send_quiz_question for chat {chat_id}")
        await send_quiz_question(chat_id, state, bot)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"CRITICAL ERROR in start_quiz_mode: {e}")
        try:
            await call.message.answer(f"❌ Error starting quiz: {str(e)}")
        except:
            pass

async def send_quiz_question(chat_id: int, state: FSMContext, bot: Bot):
    """Send a single quiz question as a Telegram poll."""
    data = await state.get_data()
    quiz_cards = data.get('quiz_cards', [])
    quiz_index = data.get('quiz_index', 0)
    quiz_all_cards = data.get('quiz_all_cards', [])
    reverse = data.get('quiz_reverse', False)
    
    if quiz_index >= len(quiz_cards):
        # Quiz complete
        correct = data.get('quiz_correct', 0)
        total = data.get('quiz_total', 0)
        pct = int((correct / total) * 100) if total > 0 else 0
        
        result_emoji = "🏆" if pct >= 80 else "👍" if pct >= 50 else "📚"
        
        # Check if this is a custom quiz (has quiz_id in state)
        custom_quiz_id = data.get('custom_quiz_id')
        
        if custom_quiz_id:
            # Show rating options for custom quizzes
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐", callback_data=f"rate_quiz_{custom_quiz_id}_1"),
                 InlineKeyboardButton(text="⭐⭐", callback_data=f"rate_quiz_{custom_quiz_id}_2"),
                 InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"rate_quiz_{custom_quiz_id}_3"),
                 InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"rate_quiz_{custom_quiz_id}_4"),
                 InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"rate_quiz_{custom_quiz_id}_5")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="cancel")]
            ])
            msg_text = (
                f"{result_emoji} **Quiz Complete!**\n\n"
                f"✅ Score: {correct}/{total} ({pct}%)\n\n"
                f"⭐ **Rate this quiz:**"
            )
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="cancel")]
            ])
            msg_text = (
                f"{result_emoji} **Quiz Complete!**\n\n"
                f"✅ Score: {correct}/{total} ({pct}%)\n\n"
                f"Keep practicing to improve!"
            )
        
        await bot.send_message(
            chat_id,
            msg_text,
            parse_mode="Markdown",
            reply_markup=kb
        )
        await state.clear()
        return
    
    current_card = quiz_cards[quiz_index]
    
    if current_card.get('is_custom', False):
        # Custom Quiz: Options are pre-defined
        question_text = current_card['term']
        correct_answer = current_card['options'][0] # We enforce 0 as correct in data
        
        # Options are already there
        # Truncate to 10 to satisfy Telegram Limit (just in case DB has more)
        options = current_card['options'][:10]
        
        # Validating options count
        while len(options) < 2:
            options.append("Option")
            
        random.shuffle(options)
        correct_index = options.index(correct_answer)
        
        explanation = f"✅ {correct_answer[:150]}"

    elif reverse:
        question_text = current_card.get('definition', current_card.get('back', ''))
        correct_answer = current_card.get('term', current_card.get('front', ''))
    else:
        question_text = current_card.get('term', current_card.get('front', ''))
        correct_answer = current_card.get('definition', current_card.get('back', ''))
    
    if not current_card.get('is_custom', False):
        # Generate 3 wrong answers (distractors) ONLY for NON-custom cards
        distractors = []
        for card in quiz_all_cards:
            if card.get('card_id') != current_card.get('card_id'):
                if reverse:
                    distractor = card.get('term', card.get('front', ''))
                else:
                    distractor = card.get('definition', card.get('back', ''))
                if distractor and distractor != correct_answer and len(distractor) < 100:
                    distractors.append(distractor[:100])  # Telegram limit
                    if len(distractors) >= 3:
                        break
        
        # Fallback if not enough distractors
        while len(distractors) < 3:
            distractors.append(f"Option {len(distractors) + 1}")
        
        # Validate correct answer is not empty
        if not correct_answer or not correct_answer.strip():
            correct_answer = "[Answer not set]"
        
        # Create options and randomize position
        correct_truncated = correct_answer[:100]
        options = [correct_truncated] + distractors[:3]
        random.shuffle(options)
        correct_index = options.index(correct_truncated)
        
        # Generate explanation (bilingual if possible) - skip if too slow
        explanation = f"✅ {correct_answer[:150]}"  # Simple fallback
    
    
    # Store poll ID for tracking
    # Get quiz timer (default 30s)
    quiz_timer = data.get('quiz_timer', 30)
    
    try:
        print(f"DEBUG: sending poll to {chat_id}, Q: {question_text[:20]}")
        poll_message = await bot.send_poll(
            chat_id=chat_id,
            question=f"❓ {question_text[:255]}",  # Telegram limit is 300
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            explanation=explanation[:200] if explanation else None,  # Telegram limit
            is_anonymous=False,
            open_period=quiz_timer  # Use custom timer
        )
        print(f"DEBUG: Poll sent successfully. ID: {poll_message.poll.id}")
        # Store poll ID and correct answer index for score tracking
        await state.update_data(
            current_poll_id=poll_message.poll.id,
            current_correct_index=correct_index
        )
        
    except Exception as e:
        print(f"CRITICAL: Quiz poll error: {e}")
        import traceback
        traceback.print_exc()
        await bot.send_message(chat_id, f"❌ Error sending quiz question: {e}")

async def generate_quiz_explanation(term: str, definition: str) -> str:
    """Generate a bilingual explanation for quiz feedback."""
    # Try to get from cache first
    try:
        from bot_services.vocabulary_cache import get_from_cache
        cached = await get_from_cache(term)
        if cached:
            eng_def = cached.get('definition', definition)
            uzb_def = cached.get('translation_uz', '')
            if eng_def and uzb_def:
                return f"🇬🇧 {eng_def[:80]}\n🇺🇿 {uzb_def[:80]}"
    except:
        pass
    
    # Try AI generation (async, non-blocking if fails)
    try:
        from bot_services.ai_service import generate_quiz_explanation_ai
        ai_result = await generate_quiz_explanation_ai(term, definition)
        if ai_result:
            eng = ai_result.get('eng', '')
            uzb = ai_result.get('uzb', '')
            if eng and uzb:
                return f"🇬🇧 {eng}\n🇺🇿 {uzb}"
    except:
        pass
    
    # Fallback to simple format
    return f"✅ {definition[:180]}"

@router.poll_answer()
async def handle_quiz_poll_answer(poll_answer: types.PollAnswer, state: FSMContext, bot: Bot):
    """Handle user's answer to a quiz poll and send next question."""
    user_id = poll_answer.user.id
    
    try:
        # Get user's state
        data = await state.get_data()
        current_poll_id = data.get('current_poll_id')
        
        if not current_poll_id or poll_answer.poll_id != current_poll_id:
            return  # Not our poll
        
        quiz_index = data.get('quiz_index', 0)
        quiz_correct = data.get('quiz_correct', 0)
        correct_index = data.get('current_correct_index')
        
        # Check if user's answer is correct
        if poll_answer.option_ids and len(poll_answer.option_ids) > 0:
            user_selected = poll_answer.option_ids[0]
            if user_selected == correct_index:
                quiz_correct += 1
                print(f"DEBUG: Correct! Score now: {quiz_correct}")
            else:
                print(f"DEBUG: Wrong. Selected {user_selected}, correct was {correct_index}")
        
        # Move to next question and update correct count
        await state.update_data(
            quiz_index=quiz_index + 1,
            quiz_correct=quiz_correct
        )
        
        # Small delay for user to see the result
        await asyncio.sleep(1.5)
        
        # Send next question
        await send_quiz_question(user_id, state, bot)
    except Exception as e:
        print(f"Poll answer handler error: {e}")
        import traceback
        traceback.print_exc()

# --- CUSTOM QUIZ PLAYER ADAPTER ---
async def start_custom_quiz_play(message: types.Message, state: FSMContext, quiz_id: str):
    """
    Handles deep link /start quiz_{id}.
    Loads the custom quiz and starts standard quiz mode with it.
    """
    # 1. Fetch Quiz Data
    quiz = await get_custom_quiz(quiz_id)
    if not quiz:
        await message.answer("❌ Quiz not found or deleted.", reply_markup=get_home_kb())
        return
        
    # 2. Increment plays
    await increment_quiz_plays(quiz_id)
    
    # 3. Convert to Standard Card Format
    cards = []
    for q in quiz.get('questions', []):
        cards.append({
            'term': q['text'],
            'definition': q['options'][0], # Convention: first option is correct answer definition
            'options': q['options'],
            'correct_index': 0, # Standardize to 0, shuffle logic handles position
            'is_custom': True
        })
        
    if not cards:
        await message.answer("❌ This quiz has no questions.", reply_markup=get_home_kb())
        return

    # 4. Start Quiz Session
    await state.clear()
    await state.set_state(PracticeStates.active_session)
    
    # Init Quiz State
    await state.update_data(
        mode="quiz",
        cards=cards,
        quiz_cards=cards, # VITAL for send_quiz_question
        total_cards=len(cards),
        quiz_total=len(cards), # VITAL for score screen
        quiz_index=0,
        quiz_correct=0,
        custom_quiz_id=quiz_id, # For rating at end
        quiz_timer=quiz.get('timer', 30), # Custom timer
        custom_quiz_title=quiz['title']
    )
    
    await message.answer(
        f"🎮 **Starting User Quiz: {quiz['title']}**\n"
        f"❓ {len(cards)} Questions\n",
        parse_mode="Markdown"
    )
    
    # Start first question
    user_id = message.from_user.id
    await send_quiz_question(user_id, state, message.bot)

# --- QUIZ RATING HANDLER ---
@router.callback_query(F.data.startswith("rate_quiz_"))
async def handle_quiz_rating(call: types.CallbackQuery, state: FSMContext):
    """Handle quiz rating from completion screen."""
    parts = call.data.replace("rate_quiz_", "").rsplit("_", 1)
    if len(parts) != 2:
        await call.answer("Invalid rating", show_alert=True)
        return
    
    quiz_id, stars_str = parts
    try:
        stars = int(stars_str)
    except ValueError:
        await call.answer("Invalid rating", show_alert=True)
        return
    
    if not 1 <= stars <= 5:
        await call.answer("Invalid rating", show_alert=True)
        return
    
    from bot_services.firebase_service import rate_quiz
    await rate_quiz(call.from_user.id, quiz_id, stars)
    
    await call.message.edit_text(
        f"⭐ Thanks for rating! ({stars} star{'s' if stars > 1 else ''})\n\n"
        f"🏠 Returning to main menu...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="cancel")]
        ])
    )
    await call.answer("Rating saved!")

# --- FAVORITES TOGGLE HANDLER ---
@router.callback_query(F.data.startswith("tog_fav_set_"))
async def toggle_favorite_set(call: types.CallbackQuery, state: FSMContext):
    """Toggle favorite status for a set."""
    set_id = call.data.replace("tog_fav_set_", "")
    from bot_services.firebase_service import toggle_favorite
    is_now_fav = await toggle_favorite(call.from_user.id, 'set', set_id)
    
    if is_now_fav:
        await call.answer("❤️ Added to Favorites!", show_alert=False)
    else:
        await call.answer("💔 Removed from Favorites", show_alert=False)
    
    # Refresh UI
    await show_config_ui(call, state)

# --- FOLDER FAVORITES TOGGLE HANDLER ---
@router.callback_query(F.data.startswith("tog_fav_folder_"))
async def toggle_folder_favorite(call: types.CallbackQuery, state: FSMContext):
    """Toggle favorite status for a folder."""
    folder_id = call.data.replace("tog_fav_folder_", "")
    from bot_services.firebase_service import toggle_favorite
    is_now_fav = await toggle_favorite(call.from_user.id, 'folder', folder_id)
    
    if is_now_fav:
        await call.answer("❤️ Added to Favorites!", show_alert=False)
    else:
        await call.answer("💔 Removed from Favorites", show_alert=False)
    
    # Refresh folder view
    await browse_official_folder(call, folder_id, page=0)