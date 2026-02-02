from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot_services.translator import tr
from bot_services.firebase_service import get_user, create_set, add_total_xp, add_tx_coins, get_user_folders, get_bot_config
from bot_services.utils import AddCardStates, get_cancel_kb, get_home_kb
from bot_services.ai_service import generate_card_content
import io
import csv
from docx import Document

router = Router()

async def ask_visibility(message, state, user_id):
    """Ask user if set should be public or private, then create the set."""
    data = await state.get_data()
    cards = data.get('cards', [])
    set_name = data.get('set_name', 'Untitled')
    user = await get_user(user_id)
    lang = user['lang_code']
    
    if not cards:
        await message.answer("❌ No cards found to create.")
        return
    
    # For now, just create as private set directly (simpler flow)
    new_set_id = await create_set(
        user_id=user_id, 
        folder_id=None, 
        set_name=set_name, 
        is_public=False,
        cards_list=cards
    )
    
    # Dual currency rewards
    from bot_services.firebase_service import add_total_xp, add_tx_coins
    xp_earned = len(cards) * 0.5  # 0.5 XP per card
    tx_earned = len(cards) * 0.2  # 0.2 TX per card
    
    await add_total_xp(user_id, xp_earned)
    await add_tx_coins(user_id, tx_earned)
    
    success_text = (
        f"✅ Created {len(cards)} flashcard(s)!\n"
        f"🎯 +{xp_earned:.0f} XP  |  💰 +{tx_earned:.1f} TX\n"
    )
    
    # Post-Creation Options
    kb = [
        [InlineKeyboardButton(text="📂 Add to Folder", callback_data=f"post_add_folder_{new_set_id}")],
        [InlineKeyboardButton(text="➕ New Folder & Add", callback_data=f"post_new_folder_{new_set_id}")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ]
    
    await message.answer(success_text + "\n\nWhat's next?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

# ... (Keep start, name, method, input steps as is) ...
# --- Step 1: Start with Set Name ---
@router.callback_query(F.data == "menu_add")
async def start_add_flow(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = await get_user(user_id)
    if not user:
        await call.answer("Please /start first.")
        return
    lang = user['lang_code']
    
    await state.set_state(AddCardStates.waiting_set_name)
    await call.message.edit_text(tr.get_text('enter_set_name', lang), reply_markup=get_home_kb(tr.languages[lang]))

@router.message(AddCardStates.waiting_set_name)
async def set_name_entered(message: types.Message, state: FSMContext):
    await state.update_data(set_name=message.text)
    user = await get_user(message.from_user.id)
    lang = user['lang_code']
    
    # Check AI Config
    config = await get_bot_config()
    ai_enabled = config.get('ai_enabled', True)
    is_blocked = message.from_user.id in config.get('blocked_users', [])
    
    kb = [
        [InlineKeyboardButton(text=tr.get_text('btn_one_by_one', lang), callback_data="mode_one")],
        [InlineKeyboardButton(text=tr.get_text('btn_bulk', lang), callback_data="mode_bulk")],
    ]
    
    if ai_enabled and not is_blocked:
        kb.append([InlineKeyboardButton(text="🤖 AI Generate", callback_data="mode_ai")])
        
    kb.append([InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")])
    
    await state.set_state(AddCardStates.waiting_add_method)
    await message.answer(tr.get_text('choose_add_mode', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(AddCardStates.waiting_add_method)
async def add_mode_selected(call: types.CallbackQuery, state: FSMContext):
    mode = call.data
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    if mode == "mode_one":
        await state.set_state(AddCardStates.adding_one_term)
        await state.update_data(cards=[])
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Back", callback_data="back_to_mode")],
            [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
        ])
        await call.message.edit_text(tr.get_text('enter_term', lang), reply_markup=kb)
    elif mode == "mode_bulk":
        await state.set_state(AddCardStates.adding_bulk)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Back", callback_data="back_to_mode")],
            [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
        ])
        await call.message.edit_text(
            "📤 Upload a file with your flashcards or paste them here.\n\n"
            "**Supported files**: .csv, .txt, .docx\n"
            "**Format**: term,definition OR term/definition\n"
            "One card per line.",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    
    elif mode == "mode_ai":
        # Double check permission
        config = await get_bot_config()
        if not config.get('ai_enabled', True) or call.from_user.id in config.get('blocked_users', []):
            await call.answer("❌ AI features are currently disabled or restricted.", show_alert=True)
            return

        await state.set_state(AddCardStates.waiting_ai_words)
        await state.update_data(ai_cards=[])
        
        msg = (
            "🤖 **AI Card Generator**\n\n"
            "Enter words or phrases (one per line) that you want to learn.\n\n"
            "AI will automatically generate:\n"
            "• Definitions\n"
            "• Uzbek translations\n"
            "• Example sentences\n\n"
            "Example:\n"
            "serendipity\n"
            "ephemeral\n"
            "catalyst"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Back", callback_data="back_to_mode")],
            [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
        ])
        await call.message.edit_text(msg, reply_markup=kb, parse_mode="Markdown")

@router.message(AddCardStates.adding_bulk, F.document)
async def handle_file_upload(message: types.Message, state: FSMContext, bot: Bot):
    doc = message.document
    file_name = doc.file_name.lower()
    
    # Support CSV, TXT, and DOCX
    if not file_name.endswith(('.csv', '.txt', '.docx')):
        await message.answer("❌ Please upload a .csv, .txt, or .docx file.")
        return

    file_info = await bot.get_file(doc.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    
    # Extract content based on file type
    if file_name.endswith('.docx'):
        # Extract text from DOCX
        docx_file = Document(io.BytesIO(downloaded_file.read()))
        lines = [p.text for p in docx_file.paragraphs if p.text.strip()]
        content = '\n'.join(lines)
    else:
        # CSV or TXT - both are plain text
        content = downloaded_file.read().decode('utf-8')
    csv_reader = csv.reader(io.StringIO(content))
    
    cards = []
    for row in csv_reader:
        if len(row) >= 2:
            # If more than 2 columns, join the rest as definition? 
            # User asked: "if the file is comma separated and also definitions contain commas, separate the term and definition from the first comma"
            # csv.reader handles quoted fields with commas correctly. 
            # But if it's a raw text file without quotes, we might need manual split.
            # Let's trust csv.reader for standard CSVs.
            # But wait, user said "accept '/' separated files".
            # If it's not a standard CSV, we should parse manually line by line?
            # Let's try to detect.
            pass

    # Re-implementing manual parsing for flexibility as requested
    content_lines = content.splitlines()
    cards = []
    for line in content_lines:
        line = line.strip()
        if not line:
            continue
        
        # Find whichever separator comes first
        comma_pos = line.find(',')
        slash_pos = line.find('/')
        
        if comma_pos == -1 and slash_pos == -1:
            continue
        elif comma_pos == -1:
            sep_pos = slash_pos
        elif slash_pos == -1:
            sep_pos = comma_pos
        else:
            sep_pos = min(comma_pos, slash_pos)
        
        term = line[:sep_pos].strip()
        definition = line[sep_pos + 1:].strip()
        
        if term and definition:
            cards.append({'term': term, 'def': definition})
            
    if not cards:
        await message.answer("❌ No valid cards found in file.")
        return
        
    await state.update_data(cards=cards)
    await ask_visibility(message, state, message.from_user.id)

@router.message(AddCardStates.adding_one_term)
async def one_term_input(message: types.Message, state: FSMContext):
    await state.update_data(temp_term=message.text)
    user = await get_user(message.from_user.id)
    lang = user['lang_code']
    await state.set_state(AddCardStates.adding_one_def)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back", callback_data="back_to_mode")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ])
    await message.answer(tr.get_text('enter_def', lang), reply_markup=kb)

@router.message(AddCardStates.adding_one_def)
async def one_def_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cards = data.get('cards', [])
    cards.append({'term': data['temp_term'], 'def': message.text})
    await state.update_data(cards=cards)
    
    user = await get_user(message.from_user.id)
    lang = user['lang_code']
    
    # Show card count on buttons
    card_count = len(cards)
    kb = [
        [InlineKeyboardButton(text="➕ Add More", callback_data="add_more")],
        [InlineKeyboardButton(text=f"✅ Finish ({card_count} card{'s' if card_count != 1 else ''})", callback_data="finish_add")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")] 
    ]
    
    success_msg = f"✅ Card added! Total: {card_count}\n\n**{data['temp_term']}** → {message.text}"
    await message.answer(success_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "back_to_mode")
async def back_to_mode_selection(call: types.CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    kb = [
        [InlineKeyboardButton(text=tr.get_text('btn_one_by_one', lang), callback_data="mode_one")],
        [InlineKeyboardButton(text=tr.get_text('btn_bulk', lang), callback_data="mode_bulk")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")] 
    ]
    await state.set_state(AddCardStates.waiting_add_method)
    await call.message.edit_text(tr.get_text('choose_add_mode', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "add_more")
async def add_more_cards(call: types.CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    await state.set_state(AddCardStates.adding_one_term)
    await call.message.answer(tr.get_text('enter_term', lang), reply_markup=get_home_kb(tr.languages[lang]))

@router.message(AddCardStates.adding_bulk)
async def bulk_input(message: types.Message, state: FSMContext):
    text = message.text
    lines = text.split('\n')
    cards = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Find positions of both separators
        comma_pos = line.find(',')
        slash_pos = line.find('/')
        
        # Determine which separator comes first
        if comma_pos == -1 and slash_pos == -1:
            # No separator found, skip this line
            continue
        elif comma_pos == -1:
            # Only slash found
            sep_pos = slash_pos
        elif slash_pos == -1:
            # Only comma found
            sep_pos = comma_pos
        else:
            # Both found - use whichever comes first
            sep_pos = min(comma_pos, slash_pos)
        
        term = line[:sep_pos].strip()
        definition = line[sep_pos + 1:].strip()
        
        if term and definition:
            cards.append({'term': term, 'def': definition})
    
    if not cards:
        await message.answer(
            "❌ No valid cards found.\n\n"
            "Please use format:\n"
            "• term, definition\n"
            "• term/definition\n\n"
            "One card per line."
        )
        return
    
    await state.update_data(cards=cards)
    await ask_visibility(message, state, message.from_user.id)

@router.callback_query(F.data == "finish_add")
async def confirm_before_create(call: types.CallbackQuery, state: FSMContext):
    """Show confirmation with all cards before creating set"""
    data = await state.get_data()
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    cards = data.get('cards', [])
    set_name = data.get('set_name', 'Untitled')
    
    if not cards:
        await call.answer("❌ No cards added yet!", show_alert=True)
        return
    
    # Build card list preview
    preview = f"📊 **Ready to create set?**\n\n**{set_name}** ({len(cards)} cards)\n\n"
    for i, card in enumerate(cards[:10], 1):  # Show first 10
        preview += f"{i}. {card['term']} → {card['def']}\n"
    
    if len(cards) > 10:
        preview += f"\n... and {len(cards) - 10} more cards"
    
    kb = [
        [InlineKeyboardButton(text="✅ Create Set", callback_data="confirm_create")],
        [InlineKeyboardButton(text="➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
    ]
    
    await call.message.edit_text(preview, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "confirm_create")
async def finalize_one_by_one(call: types.CallbackQuery, state: FSMContext):
    """Create set after confirmation"""
    data = await state.get_data()
    user_id = call.from_user.id
    user = await get_user(user_id)
    cards = data.get('cards', [])
    set_name = data.get('set_name', 'Untitled')
    
    # CREATE NEW SET
    new_set_id = await create_set(
        user_id=user_id, 
        folder_id=None, 
        set_name=set_name, 
        is_public=False,
        cards_list=cards
    )
    
    # Dual currency rewards
    xp_earned = len(cards) * 0.5  # 0.5 XP per card (for leveling)
    tx_earned = len(cards) * 0.2  # 0.2 TX per card (spendable)
    
    await add_total_xp(user_id, xp_earned)
    await add_tx_coins(user_id, tx_earned)
    
    success_text = (
        f"✅ Created {len(cards)} flashcard(s)!\n"
        f"🎯 +{xp_earned:.0f} XP  |  💰 +{tx_earned:.1f} TX\n"
    )
    
    # Post-Creation Options
    kb = [
        [InlineKeyboardButton(text="📂 Add to Folder", callback_data=f"post_add_folder_{new_set_id}")],
        [InlineKeyboardButton(text="➕ New Folder & Add", callback_data=f"post_new_folder_{new_set_id}")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', user['lang_code']), callback_data="cancel")]
    ]
    
    await call.message.edit_text(success_text + "\n\nWhat's next?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

# --- Post-Creation Handlers ---
@router.callback_query(F.data.startswith("post_add_folder_"))
async def post_add_to_folder(call: types.CallbackQuery, state: FSMContext):
    set_id = call.data.replace("post_add_folder_", "")
    # Reuse the user move browser!
    # We need to import it or re-implement. 
    # It's in manage.py. We can't easily cross-import handlers without circular deps.
    # Let's redirect user to the move flow in manage.py? 
    # Or just implement a simple folder picker here.
    
    user_id = call.from_user.id
    folders = await get_user_folders(user_id, None) # Root folders
    
    kb = []
    for f in folders:
        kb.append([InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"do_post_move_{set_id}_{f['folder_id']}")])
    
    kb.append([InlineKeyboardButton(text="Cancel", callback_data="cancel")])
    await call.message.edit_text("Select a Folder:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("do_post_move_"))
async def execute_post_move(call: types.CallbackQuery):
    parts = call.data.replace("do_post_move_", "").split("_")
    set_id = parts[0]
    folder_id = parts[1]
    
    from bot_services.firebase_service import move_set # Safe import
    await move_set(set_id, folder_id)
    await call.message.edit_text("✅ Set moved to folder!", reply_markup=get_home_kb({'btn_home': '🏠 Home'}))

@router.callback_query(F.data.startswith("post_new_folder_"))
async def post_create_folder(call: types.CallbackQuery, state: FSMContext):
    set_id = call.data.replace("post_new_folder_", "")
    await state.set_state(AddCardStates.waiting_post_folder_name)
    await state.update_data(post_set_id=set_id)  # FIX: Use post_set_id instead of temp_set_id
    
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    await call.message.edit_text(tr.get_text('enter_folder_name', lang), reply_markup=get_cancel_kb())

# ===== AI GENERATE - WORD PROCESSING =====
@router.message(AddCardStates.waiting_ai_words)
async def process_ai_words(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user['lang_code']
    
    words = [w.strip() for w in message.text.split('\n') if w.strip()]
    
    # WORD LIMIT VALIDATION
    if len(words) > 10:  # Maximum 10 words
        await message.answer(
            "⚠️ **Word Limit Exceeded**\n\n"
            "Maximum: 10 words\n"
            f"You entered: {len(words)} words\n\n"
            "Please reduce and try again.",
            parse_mode="Markdown"
        )
        return
    
    # Character limit (500 chars total)
    total_chars = sum(len(w) for w in words)
    if total_chars > 500:
        await message.answer(
            "⚠️ **Input Too Long**\n\n"
            "Maximum: 500 characters total\n"
            f"You entered: {total_chars} characters\n\n"
            "Please shorten your input.",
            parse_mode="Markdown"
        )
        return
    
    if not words:
        await message.answer("❌ Please enter at least one word.")
        return
    
    # Show processing message
    processing_msg = await message.answer(f"🤖 Generating flashcards for {len(words)} word(s)...\nThis may take a moment.")
    
    # CHECK IF WE'RE ADDING MORE (accumulate cards)
    data = await state.get_data()
    accumulated_cards = data.get('accumulated_ai_cards', [])
    
    # Generate cards for each word
    generated_cards = []
    failures = []
    
    for word in words:
        # Generate Content
        content = await generate_card_content(word, user_id=message.from_user.id)
        
        if content and 'error' in content:
            if content['error'] == 'limit_reached':
                await message.answer(
                    "⚠️ **Daily AI Limit Reached**\n\n"
                    "You have hit the limit of 40 AI requests/day.\n"
                    "Please try again tomorrow or add cards manually."
                )
                break # Stop processing loop
            else:
                # Other errors, treat as a failure for this word
                failures.append(word)
                continue # Skip to next word
        
        if content:
            #  Create card with AI-generated content
            definition = content.get('definition', '')
            translation = content.get('translation', '')
            examples = content.get('examples', [])
            
            # Combine definition and examples
            full_definition = definition
            if translation:
                full_definition += f"\n\n🇺🇿 {translation}"
            if examples:
                full_definition += "\n\n📝 Examples:\n" + "\n".join(f"• {ex}" for ex in examples)
            
            generated_cards.append({'term': word, 'def': full_definition})
        else:
            failures.append(word)
    
    # Show results
    if not generated_cards:
        await processing_msg.edit_text(
            "❌ Failed to generate cards.\n\n"
            "This might be due to:\n"
            "• Missing GROQ_API_KEY in environment\n"
            "• API rate limits\n"
            "• Network issues\n\n"
            "Try again later or use manual mode."
        )
        await state.clear()
        return
    
    # ACCUMULATE with previous cards
    accumulated_cards.extend(generated_cards)
    total_cards = len(accumulated_cards)
    
    # Show confirmation before creating
    data = await state.get_data()
    set_name = data.get('set_name', 'AI Generated Set')
    
    # Store ALL accumulated cards in state
    await state.update_data(
        accumulated_ai_cards=accumulated_cards,
        ai_generated_cards=accumulated_cards,  # For finalization
        ai_failures=failures
    )
    
    # Build preview showing ALL cards
    preview = f"🤖 **AI Generated Cards**\n\n**{set_name}** ({total_cards} cards total)\n\n"
    
    # Show last 5 cards (most recent)
    cards_to_show = accumulated_cards[-5:]
    start_index = total_cards - len(cards_to_show) + 1
    
    for i, card in enumerate(cards_to_show, start_index):
        term = card['term']
        # Truncate long definitions for preview
        definition = card['def'][:80] + "..." if len(card['def']) > 80 else card['def']
        preview += f"{i}. **{term}**\n   {definition}\n\n"
    
    if total_cards > 5:
        preview += f"(Showing last 5 of {total_cards} cards)\n\n"
    
    if failures:
        preview += f"⚠️ Failed to generate: {', '.join(failures)}\n\n"
    
    preview += f"✅ Just added: {len(generated_cards)} card(s)"
    
    kb = [
        [InlineKeyboardButton(text="✅ Finish", callback_data="confirm_ai_create")],
        [InlineKeyboardButton(text="➕ Add More Words", callback_data="ai_add_more")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
    ]
    
    await processing_msg.edit_text(preview, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "confirm_ai_create")
async def finalize_ai_cards(call: types.CallbackQuery, state: FSMContext):
    """Create set after AI generation confirmation"""
    data = await state.get_data()
    generated_cards = data.get('ai_generated_cards', [])
    failures = data.get('ai_failures', [])
    set_name = data.get('set_name', 'AI Generated Set')
    user_id = call.from_user.id
    
    if not generated_cards:
        await call.answer("❌ No cards to create!", show_alert=True)
        return
    
    # CREATE NEW SET
    await create_set(user_id, None, set_name, False, generated_cards)
    
    # Award XP and TX
    xp_earned = len(generated_cards) * 2.0  # 2 XP per AI-generated card
    tx_earned = len(generated_cards) * 1.0  # 1 TX per AI-generated card
    
    await add_total_xp(user_id, xp_earned)
    await add_tx_coins(user_id, tx_earned)
    
    # Show success message
    success_text = (
        f"✅ Created {len(generated_cards)} flashcard(s)!\n"
        f"🎯 +{xp_earned:.0f} XP  |  💰 +{tx_earned:.1f} TX\n\n"
        f"Set: '{set_name}'\n"
    )
    
    if failures:
        success_text += f"\n\n⚠️ Failed to generate: {', '.join(failures)}"
    
    success_text += "\n\n📚 Practice your new cards anytime!"
    
    # Ask if user wants to add more
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add More Words", callback_data="ai_add_more")],
        [InlineKeyboardButton(text="✅ Finish", callback_data="ai_finish")]
    ])
    
    await call.message.edit_text(success_text, reply_markup=kb)

@router.callback_query(F.data == "ai_add_more")
async def ai_add_more(call: types.CallbackQuery, state: FSMContext):
    """Add more words to current AI generation session (accumulative)"""
    await state.set_state(AddCardStates.waiting_ai_words)
    
    # Get current count
    data = await state.get_data()
    current_count = len(data.get('accumulated_ai_cards', []))
    
    await call.message.edit_text(
        f"🤖 **Add More Words**\n\n"
        f"Current cards: {current_count}\n\n"
        f"Enter more words or phrases (one per line):\n"
        f"Max: 10 words",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "ai_finish")
async def ai_finish(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    set_name = data.get('set_name', 'Set')
    await call.message.edit_text(
        f"✅ **Done!**\n\nSet '{set_name}' is ready.",
        reply_markup=get_home_kb({'btn_home': '🏠 Home'}),
        parse_mode="Markdown"
    )
    await state.clear()


@router.message(AddCardStates.waiting_post_folder_name)
async def process_post_folder_name(message: types.Message, state: FSMContext):
    folder_name = message.text
    data = await state.get_data()
    user_id = message.from_user.id
    
    # Fix: Check if post_set_id exists in state
    set_id = data.get('post_set_id')
    if not set_id:
        # Fallback: try to get from target_id (alternate key)
        set_id = data.get('target_id')
    
    if not set_id:
        await message.answer("❌ Error: Set ID not found. Please try again.")
        await state.clear()
        return
    
    from bot_services.firebase_service import create_book, move_set
    
    # Create the folder
    folder_id = await create_book(user_id, folder_name, parent_id=None)
    
    # Move the set to the new folder
    await move_set(set_id, folder_id)
    
    user = await get_user(user_id)
    await message.answer(
        f"✅ Set moved to new folder '{folder_name}'!",
        reply_markup=get_home_kb(tr.languages[user['lang_code']])
    )
    await state.clear()