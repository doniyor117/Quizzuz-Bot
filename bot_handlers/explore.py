import hashlib
import html
from aiogram import Router, types, F
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot_services.firebase_service import search_public_sets
from bot_services.translator import tr

router = Router()

@router.callback_query(F.data == "menu_explore")
async def explore_start(call: types.CallbackQuery, state: FSMContext):
    # Just show the search button
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Start Searching", switch_inline_query_current_chat="")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")] # Replaced Back with Home
    ])
    await call.message.edit_text("Tap below to search public tests:", reply_markup=kb)

@router.inline_query()
async def inline_search_handler(query: types.InlineQuery):
    text = query.query.strip()
    results = await search_public_sets(text)
    
    articles = []
    for r in results:
        set_id = r['set_id']
        raw_title = r.get('set_name', 'Untitled')
        folder_name = r.get('folder_name', '')
        count = r.get('card_count', 0)
        title = html.escape(raw_title)
        
        # Show folder name in description if available
        description = f"📁 {folder_name} | " if folder_name else ""
        description += f"{count} cards - Click to practice"
        
        message_content = InputTextMessageContent(
            message_text=f"/play_{set_id}", 
        )
        
        result_id = hashlib.md5(set_id.encode()).hexdigest()
        item = InlineQueryResultArticle(
            id=result_id,
            title=f"{raw_title} ({count} cards)",
            description=description,
            input_message_content=message_content,
            thumbnail_url="https://img.icons8.com/emoji/48/000000/play-button-emoji.png"
        )
        articles.append(item)

    await query.answer(articles, cache_time=1, is_personal=False)