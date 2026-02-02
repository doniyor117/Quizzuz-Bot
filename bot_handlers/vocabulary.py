from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.translator import tr
from bot_services.firebase_service import get_user, create_set, add_xp
from bot_services.utils import VocabularyStates, get_cancel_kb, get_home_kb
from bot_services.dictionary_service import lookup_vocabulary

router = Router()

# ===== VOCABULARY MENU =====
@router.callback_query(F.data == "menu_vocabulary")
async def vocabulary_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    msg = tr.get_text('vocab_menu_title', lang) + "\n\n" + tr.get_text('vocab_menu_desc', lang)
    
    await state.set_state(VocabularyStates.waiting_word)
    await call.message.edit_text(msg, reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")

# ===== WORD LOOKUP =====
@router.message(VocabularyStates.waiting_word)
async def lookup_word(message: types.Message, state: FSMContext):
    word = message.text.strip()
    user_id = message.from_user.id
    
    # WORD LIMIT VALIDATION
    words = word.split()
    if len(words) > 5:
        await message.answer(
            "⚠️ **Too Many Words**\n\n"
            "Maximum: 5 words\n"
           f"You entered: {len(words)} words\n\n"
            "Please search one term at a time.",
            parse_mode="Markdown"
        )
        return
    
    # Character limit
    if len(word) > 100:
        await message.answer(
            "⚠️ **Input Too Long**\n\n"
            "Maximum: 100 characters\n"
            f"You entered: {len(word)} characters\n\n"
            "Please shorten your search.",
            parse_mode="Markdown"
        )
        return
    
    user = await get_user(user_id)
    lang = user['lang_code']
    
    # Show processing message
    processing_msg = await message.answer("🔍 Looking up...")
    
    # Use new smart lookup system
    from bot_services.vocabulary_lookup import lookup_word_smart
    from bot_services.vocab_rate_limiter import get_vocab_quota_status
    vocab_result = await lookup_word_smart(word, user_id)
    
    if not vocab_result:
        # Nothing found
        result_text = (
            f"❌ Sorry, couldn't find information for **{word}**.\n\n"
            "Try:\n"
            "• Checking spelling\n"
            "• Using base form of the word\n"
            "• Trying a different word"
        )
        
        await processing_msg.edit_text(result_text, parse_mode="Markdown")
        await state.set_state(VocabularyStates.waiting_word)
        return
    
    # Build response message with source indicator
    result_text = f"📖 **{vocab_result['word'].title()}**\n\n"
    
    # Add source badge
    source = vocab_result.get('source', '')
    if source == 'ai' or source == 'cache_ai':
        if vocab_result.get('upgraded'):
            result_text += "🔄 **Upgraded to AI Quality!**\n\n"
        else:
            result_text += "✨ **AI-Powered Result**\n\n"
    elif source == 'dict' or source == 'cache_dict':
        result_text += "📚 **Dictionary Result**\n\n"
    
    # Add phonetic if available
    if vocab_result.get('phonetic'):
        result_text += f"🔊 *{vocab_result['phonetic']}*\n\n"
    
    # Add definition
    if vocab_result.get('definition'):
        result_text += f"**Definition:**\n{vocab_result['definition']}\n\n"
    
    # Add translations with INTELLIGENT FLAGS
    # Auto-detect which language is input vs output
    translation = vocab_result.get('translation_uz') or vocab_result.get('translation_en')
    
    if translation:
        # Simple heuristic: If input word has Cyrillic, it's Uzbek → English
        # Otherwise it's English → Uzbek
        has_cyrillic = any('а' <= c <= 'я' or 'А' <= c <= 'Я' for c in word)
        
        if has_cyrillic:
            # Uzbek input → English output
            result_text += f"🇬🇧 **English Translation:** {translation}\n"
        else:
            # English input → Uzbek output
            result_text += f"🇺🇿 **O'zbek Tarjimasi:** {translation}\n"
    
    # Add examples
    examples = vocab_result.get('examples', [])
    if examples:
        result_text += "\n**Examples:**\n"
        for example in examples[:2]:  # Max 2
            result_text += f"• _{example}_\n"
    
    # Show quota status if limit reached
    if not vocab_result.get('quota_used') and source in ['dict', 'cache_dict']:
        quota = await get_vocab_quota_status(user_id)
        
        if quota['day_remaining'] == 0:
            result_text += f"\n⚠️ **AI Daily Limit Reached** ({quota['requests_today']}/{quota['day_limit']})\n"
            result_text += f"Resets in {quota['next_reset_hours']:.1f} hours\n"
    
    # Store data for potential save
    await state.update_data(
        lookup_word=vocab_result['word'],
        lookup_definition=vocab_result.get('translation_uz') or vocab_result.get('definition', '')
    )
    
    # Show result with action buttons
    kb = [
        [InlineKeyboardButton(text="💾 Save as Flashcard", callback_data="vocab_save")],
        [InlineKeyboardButton(text="🔍 Lookup Another Word", callback_data="vocab_another")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ]
    
    await processing_msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await state.set_state(VocabularyStates.viewing_result)

# ===== SAVE TO SET =====
@router.callback_query(F.data == "vocab_save", VocabularyStates.viewing_result)
async def save_vocabulary_start(call: types.CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    msg = tr.get_text('vocab_save_title', lang) + "\n\n" + tr.get_text('vocab_choose_option', lang)
    
    kb = [
        [InlineKeyboardButton(text=tr.get_text('btn_add_existing', lang), callback_data="vocab_add_existing")],
        [InlineKeyboardButton(text=tr.get_text('btn_create_new', lang), callback_data="vocab_create_new")],
        [InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")]
    ]
    
    await call.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "vocab_add_existing")
async def vocab_add_to_existing(call: types.CallbackQuery, state: FSMContext):
    """Show list of user's sets to add the card to."""
    user_id = call.from_user.id
    user = await get_user(user_id)
    lang = user['lang_code']
    
    from bot_services.firebase_service import get_user_sets
    sets = await get_user_sets(user_id)
    
    if not sets:
        await call.answer(tr.get_text('vocab_no_sets', lang), show_alert=True)
        return
    
    kb = []
    for s in sets[:15]:  # Max 15 sets in list
        kb.append([InlineKeyboardButton(text=f"📝 {s['set_name']}", callback_data=f"vocab_to_set_{s['set_id']}")])
    
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="vocab_save")])
    
    await call.message.edit_text(
        "📁 **Select a set to add the card to:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("vocab_to_set_"))
async def vocab_add_to_selected_set(call: types.CallbackQuery, state: FSMContext):
    """Add the vocabulary card to the selected set."""
    set_id = call.data.replace("vocab_to_set_", "")
    user_id = call.from_user.id
    user = await get_user(user_id)
    lang = user['lang_code']
    
    data = await state.get_data()
    term = data.get('lookup_word', 'Unknown')
    definition = data.get('lookup_definition', 'No definition')
    
    # Add card to existing set
    from bot_services.firebase_service import add_card_to_set, get_set
    await add_card_to_set(set_id, term, definition)
    
    # Get set name for confirmation
    target_set = await get_set(set_id)
    set_name = target_set.get('set_name', 'your set') if target_set else 'your set'
    
    # Award XP
    await add_xp(user_id, 1.0)
    
    success_msg = (
        f"✅ **Added!**\n\n"
        f"📝 **{term}** → {set_name}\n"
        f"+1 XP earned!"
    )
    
    await call.message.edit_text(success_msg, reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")
    await state.clear()

@router.callback_query(F.data == "vocab_create_new")
async def vocab_create_new_set(call: types.CallbackQuery, state: FSMContext):
    """Prompt user to enter a name for a new set."""
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    msg = (
        "➕ **Create New Set**\n\n"
        "Enter a name for this vocabulary set:"
    )
    
    await state.set_state(VocabularyStates.waiting_set_name)
    await call.message.edit_text(msg, reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(VocabularyStates.waiting_set_name)
async def save_vocabulary_final(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user['lang_code']
    
    set_name = message.text.strip()
    if len(set_name) > 100:
        set_name = set_name[:100]
    
    # Get stored vocabulary data
    data = await state.get_data()
    term = data.get('lookup_word', 'Unknown')
    definition = data.get('lookup_definition', 'No definition')
    
    # Create flashcard set
    cards = [{'term': term, 'def': definition}]
    await create_set(user_id, None, set_name, False, cards)
    
    # Award XP
    await add_xp(user_id, 1.0)
    
    success_msg = (
        f"✅ **Set Created!**\n\n"
        f"📝 **{term}** saved to '{set_name}'\n"
        f"+1 XP earned!\n\n"
        f"Practice it anytime in your library."
    )
    
    await message.answer(success_msg, reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")
    await state.clear()

# ===== LOOKUP ANOTHER =====
@router.callback_query(F.data == "vocab_another")
async def lookup_another(call: types.CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    await state.set_state(VocabularyStates.waiting_word)
    await call.message.edit_text("📖 Send me another word to look up:", reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")
