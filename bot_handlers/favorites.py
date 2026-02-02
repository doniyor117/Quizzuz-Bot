from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import get_favorites, get_set, get_folder, get_custom_quiz
from bot_services.utils import get_home_kb, build_vkm_pagination_kb

router = Router()

FAVORITES_PAGE_SIZE = 10

@router.callback_query(F.data == "menu_favorites")
async def show_favorites_root(call: types.CallbackQuery, state: FSMContext):
    await show_favorites_page(call, state, 0)

@router.callback_query(F.data.startswith("fav_page_"))
async def show_favorites_handler(call: types.CallbackQuery, state: FSMContext):
    page = int(call.data.replace("fav_page_", ""))
    await show_favorites_page(call, state, page)

async def show_favorites_page(call: types.CallbackQuery, state: FSMContext, page: int):
    user_id = call.from_user.id
    favorites = await get_favorites(user_id)
    
    if not favorites:
        await call.message.edit_text(
            "❤️ **Your Favorites**\n\n"
            "You haven't added any favorites yet.\n"
            "Browse your library and tap the ❤️ button to pin items here!",
            reply_markup=get_home_kb(),
            parse_mode="Markdown"
        )
        return
    
    # Build list of favorite items with their data
    items = []
    item_lines = []
    
    for fav_key in favorites:
        parts = fav_key.split('_', 1)
        if len(parts) != 2:
            continue
        item_type, item_id = parts
        
        if item_type == 'set':
            item = await get_set(item_id)
            if item:
                items.append({
                    'text': f"📄 {item.get('set_name', 'Set')[:25]}",
                    'callback_data': f"p_set_{item_id}"
                })
                item_lines.append(f"📄 {item.get('set_name', 'Set')}")
        elif item_type == 'folder':
            item = await get_folder(item_id)
            if item:
                items.append({
                    'text': f"📁 {item.get('folder_name', 'Folder')[:25]}",
                    'callback_data': f"prac_brow_{item_id}_0"
                })
                item_lines.append(f"📁 {item.get('folder_name', 'Folder')}")
        elif item_type == 'quiz':
            item = await get_custom_quiz(item_id)
            if item:
                items.append({
                    'text': f"🎮 {item.get('title', 'Quiz')[:25]}",
                    'callback_data': f"act_cust_quiz_{item_id}"
                })
                item_lines.append(f"🎮 {item.get('title', 'Quiz')}")
    
    if not items:
        await call.message.edit_text(
            "❤️ **Your Favorites**\n\nNo valid favorites found.",
            reply_markup=get_home_kb(),
            parse_mode="Markdown"
        )
        return
    
    total = len(items)
    start = page * FAVORITES_PAGE_SIZE
    end = start + FAVORITES_PAGE_SIZE
    page_items = items[start:end]
    page_lines = item_lines[start:end]
    
    # Build text (numbered list)
    text = "❤️ **Your Favorites**\n\n"
    for i, line in enumerate(page_lines, 1):
        text += f"{i}. {line}\n"
    text += f"\n📖 Page {page + 1}/{(total - 1) // FAVORITES_PAGE_SIZE + 1}"
    
    # Build VKM pagination keyboard
    kb = build_vkm_pagination_kb(
        items=page_items,
        page=page,
        total_items=total,
        limit=FAVORITES_PAGE_SIZE,
        back_callback="cancel",
        nav_prefix="fav_page_"
    )
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
