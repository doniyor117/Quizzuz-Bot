from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.translator import tr
from bot_services.firebase_service import *
from bot_services.firebase_service import *
from bot_services.firebase_service import create_public_request, get_user_custom_quizzes, delete_custom_quiz
from bot_services.utils import ManageStates, QuizEditStates, get_cancel_kb, get_home_kb, build_vkm_pagination_kb
import os

router = Router()

async def is_admin(uid):
    return await is_admin_check(uid)

@router.callback_query(F.data == "menu_manage")
async def manage_menu(call: types.CallbackQuery, state: FSMContext):
    # REMOVED: My Sets intermediate layer - go directly to library
    await browse_user_library(call, state, None, 0)


# ... (Keep User Manage Sets, Set Actions, Rename, Toggle, Delete logic EXACTLY same as before) ...
@router.callback_query(F.data.startswith("adm_comm_folder_"))
async def show_community_folder_actions(call: types.CallbackQuery, state: FSMContext):
    """Show actions for a community folder: browse or move to official."""
    if not await is_admin(call.from_user.id): return
    
    folder_id = call.data.replace("adm_comm_folder_", "")
    folder = await get_folder(folder_id)
    
    if not folder:
        await call.answer("❌ Folder not found.", show_alert=True)
        return
    
    folder_name = folder.get('folder_name', 'Untitled')
    set_count = folder.get('set_count', 0)
    folder_desc = folder.get('description', '')
    
    kb = [
        [InlineKeyboardButton(text="📂 Browse Folder", callback_data=f"adm_brow_{folder_id}_0")],
        [InlineKeyboardButton(text="📝 Edit Description", callback_data=f"adm_edit_desc_{folder_id}")],
        [InlineKeyboardButton(text="⭐ Move to Official", callback_data=f"adm_make_official_{folder_id}")],
        [InlineKeyboardButton(text="🗑 Delete", callback_data=f"del_fold_{folder_id}")],
        [InlineKeyboardButton(text="Back", callback_data="adm_mod_public")]
    ]
    
    text = (
        f"🌍 **Community Folder**\n\n"
        f"📂 {folder_name}\n"
        f"🃏 Sets: {set_count}\n"
    )
    if folder_desc:
        text += f"\n_{folder_desc}_\n"
    text += "\nChoose an action:"
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("adm_make_official_"))
async def move_folder_to_official(call: types.CallbackQuery, state: FSMContext):
    """Move a community folder to official library."""
    if not await is_admin(call.from_user.id): return
    
    folder_id = call.data.replace("adm_make_official_", "")
    
    from bot_services.firebase_service import move_to_official
    await move_to_official(folder_id)
    
    await call.answer("✅ Moved to Official Content!", show_alert=True)
    
    # Go back to admin panel to avoid confusion
    from bot_handlers.admin import admin_panel_cb
    await admin_panel_cb(call)

@router.callback_query(F.data.startswith("move_to_community_"))
async def move_folder_back_to_community(call: types.CallbackQuery, state: FSMContext):
    """Move an official folder back to community for review."""
    if not await is_admin(call.from_user.id): return
    
    folder_id = call.data.replace("move_to_community_", "")
    
    # Update folder_type back to 'community' using proper async pattern
    from bot_services.firebase_service import revert_to_community
    await revert_to_community(folder_id)
    
    await call.answer("✅ Moved back to Review Public Content!", show_alert=True)
    
    # Go back to community review section
    await browse_community_folders(call, state, None, 0)

# ==========================================
# FOLDER MOVING
# ==========================================

# ==========================================
# USER: MANAGE SETS
# ==========================================

@router.callback_query(F.data == "mng_sets")
async def browse_user_library_root(call: types.CallbackQuery, state: FSMContext):
    await browse_user_library(call, state, None)

@router.callback_query(F.data.startswith("mng_brow_"))
async def browse_user_library_handler(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.replace("mng_brow_", "").split("_")
    raw_pid = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    parent_id = None if raw_pid == "None" else raw_pid
    await browse_user_library(call, state, parent_id, page)

async def browse_user_library(call: types.CallbackQuery, state: FSMContext, parent_id=None, page=0):
    # Determine mode based on callback data
    is_admin_mode = call.data and call.data.startswith("adm_brow_")
    
    user_id = call.from_user.id
    user = await get_user(user_id)
    lang = user['lang_code']
    
    # Fetch Folders and Sets
    folders = await get_user_folders(user_id, parent_id)
    sets = await get_user_sets(user_id, parent_id)
    
    if not folders and not sets and parent_id:
        await call.answer(tr.get_text('empty_book', lang), show_alert=True)
        # Don't return, let them see empty folder with controls
    
    current_name = "My Library"
    current_description = ""
    back_cb = "cancel"  # At root, go back to main menu
    raw_pid = parent_id if parent_id else "None"

    
    if parent_id:
        curr = await get_folder(parent_id)
        if curr:
            current_name = curr['folder_name']
            current_description = curr.get('description', '')
            gp = curr.get('parent_id')
            gp_raw = gp if gp else "None"
            back_cb = f"mng_brow_{gp_raw}_0"
        else:
            parent_id = None
    
    # Combine folders and sets for pagination
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
    
    # 2. Build Buttons Items
    kb_items = []
    for item in current_items:
        if item['type'] == 'folder':
            f = item['data']
            kb_items.append({'callback_data': f"mng_brow_{f['folder_id']}_0"})
        else:
            s = item['data']
            kb_items.append({'callback_data': f"act_set_{s['set_id']}"})
            
    # 3. Generate Keyboard
    nav_pid = raw_pid
    # Use helper but we want to customize the "back" behavior logic which is complex here
    # Helper puts "back_callback" in middle of nav row
    # In manage.py, back_cb is dynamic. Let's use it.
    
    kb_markup = build_vkm_pagination_kb(
        items=kb_items,
        page=page,
        total_items=len(all_items),
        limit=limit,
        back_callback=back_cb,
        nav_prefix=f"mng_brow_{nav_pid}_"
    )
    
    # Convert markup to list to append controls
    kb = kb_markup.inline_keyboard
    
    # Separator for visual clarity
    kb.append([])
    
    # 3. Controls (GRID LAYOUT - Option B)
    if parent_id:
        # Check for pending request
        from bot_services.firebase_service import check_request_exists
        req_id = await check_request_exists(parent_id)
        
        # 2-column grid for actions
        kb.append([InlineKeyboardButton(text="➕ New Folder", callback_data=f"usr_mk_fold_{parent_id}"),
                   InlineKeyboardButton(text="📁 Add Folder", callback_data=f"add_fold_{parent_id}")])
        kb.append([InlineKeyboardButton(text="➕ Add Set", callback_data=f"usr_add_set_{parent_id}")])
        kb.append([InlineKeyboardButton(text="📂 Move Folder", callback_data=f"move_fold_{parent_id}"),
                   InlineKeyboardButton(text="✏️ Rename", callback_data=f"ren_fold_{parent_id}")])
        kb.append([InlineKeyboardButton(text="📝 Edit Description", callback_data=f"edit_desc_{parent_id}")])
        
        if req_id:
            kb.append([InlineKeyboardButton(text="🔄 Withdraw Request", callback_data=f"withd_req_{req_id}_{parent_id}")])
        else:
            kb.append([InlineKeyboardButton(text="📢 Submit to Community", callback_data=f"req_public_{parent_id}")])
            
        kb.append([InlineKeyboardButton(text="🗑 Delete Folder", callback_data=f"del_fold_{parent_id}")])
    else:
        # Root level - create options
        kb.append([InlineKeyboardButton(text="➕ Create Set", callback_data="menu_add")])
        kb.append([InlineKeyboardButton(text="📁 New Book", callback_data="usr_mk_fold_None"),
                   InlineKeyboardButton(text="📥 Import", callback_data="add_fold_None")])
        kb.append([InlineKeyboardButton(text="🛠 My Custom Quizzes", callback_data="mng_cust_quizzes")])

    # Back button logic already handled by VKM helper in nav row (X button)
    # BUT existing code had explicit Back buttons at bottom.
    # VKM helper Back is "X" (Close/Cancel). 
    # User might want explicit "Back" if deep in hierarchy?
    # Helper's 'back_callback' acts as the "Home/Cancel" button in recent modification.
    # Let's check helper again. It uses `back_callback` for the middle button.
    # If we want explicit Home at bottom we can add it.
    
    kb.append([InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")])
    
    # Save current location for "Back" from set actions
    await state.update_data(back_to=f"mng_brow_{raw_pid}_{page}")
    

    
    try:
        await call.message.edit_text(display_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except TelegramBadRequest:
        pass # Message content is the same, ignore

@router.callback_query(F.data.startswith("req_public_"))
async def request_public_folder(call: types.CallbackQuery, state: FSMContext):
    folder_id = call.data.replace("req_public_", "")
    success = await create_public_request(call.from_user.id, folder_id)
    if success:
        await call.answer("✅ Request sent to admins!", show_alert=True)
        # Refresh to show Withdraw button
        await browse_user_library(call, state, folder_id, 0)
    else:
        await call.answer("❌ Request already sent or invalid.", show_alert=True)

@router.callback_query(F.data.startswith("withd_req_"))
async def withdraw_request_handler(call: types.CallbackQuery, state: FSMContext):
    # Format: withd_req_{req_id}_{folder_id}
    parts = call.data.replace("withd_req_", "").split("_", 1)  # Split only on first underscore
    req_id = parts[0]
    folder_id = parts[1] if len(parts) > 1 else None
    
    from bot_services.firebase_service import reject_public_request
    await reject_public_request(req_id)
    
    await call.answer("✅ Community request withdrawn.", show_alert=True)
    
    # Refresh the folder view to update button state
    if folder_id:
        await browse_user_library(call, state, folder_id, 0)

@router.callback_query(F.data.startswith("act_set_"))
async def set_actions(call: types.CallbackQuery, state: FSMContext):
    set_id = call.data.replace("act_set_", "")
    s = await get_set(set_id)
    if not s: return
    
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    
    await state.update_data(target_id=set_id)
    
    kb = [
        [InlineKeyboardButton(text="✏️ Rename", callback_data="set_rename")],
    ]
    
    # Add card editor for admins
    if await is_admin(call.from_user.id):
        kb.append([InlineKeyboardButton(text="✏️ Edit Cards", callback_data=f"adm_edit_cards_{set_id}")])
    
    kb.append([InlineKeyboardButton(text="🗑 Delete", callback_data="set_delete")])
    kb.append([InlineKeyboardButton(text="📄 Export", callback_data=f"export_set_{set_id}")])  # NEW: Export button
    kb.append([InlineKeyboardButton(text="👀 Preview", callback_data=f"prev_mng_{set_id}_0")])
    kb.append([InlineKeyboardButton(text="📂 Move", callback_data=f"usr_move_start_None")])
    
    # Admin Tool: Move this set into the Official Books
    if await is_admin(call.from_user.id):
        kb.insert(0, [InlineKeyboardButton(text=tr.get_text('btn_move_to_book', lang), callback_data="adm_move_start_None")])

    data = await state.get_data()
    back_cb = data.get('back_to', 'mng_sets')
    
    kb.append([InlineKeyboardButton(text="Back", callback_data=back_cb),
               InlineKeyboardButton(text=tr.get_text('btn_home', lang), callback_data="cancel")])
    
    await call.message.edit_text(f"Set: {s['set_name']}\nActions:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "set_rename")
async def ask_set_rename(call: types.CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = user['lang_code']
    await state.set_state(ManageStates.waiting_set_rename)
    await call.message.edit_text(tr.get_text('enter_new_set_name', lang), reply_markup=get_home_kb(tr.languages[lang]))

@router.message(ManageStates.waiting_set_rename)
async def process_rename_set(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = await get_user(message.from_user.id)
    await rename_set(data['target_id'], message.text)
    
    await message.answer(tr.get_text('set_renamed', user['lang_code'], name=message.text), 
                         reply_markup=get_home_kb(tr.languages[user['lang_code']]))
    await state.clear()

@router.callback_query(F.data == "set_toggle_priv")
async def toggle_privacy(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    set_id = data['target_id']
    s = await get_set(set_id)
    user_id = call.from_user.id
    
    # Get the set's parent folder
    folder_id = s.get('folder_id')
    
    if s['is_public']:
        # Currently public (approved by admin) - cannot change back
        await call.answer("⚠️ This set is already public and approved by admin. Cannot make private.", show_alert=True)
        return
    else:
        # Currently private - check if there's a pending request
        if folder_id:
            # Check for existing request
            from bot_services.firebase_service import get_public_requests
            reqs = await get_public_requests()
            pending = next((r for r in reqs if r.get('folder_id') == folder_id), None)
            
            if pending:
                # Check status - only allow withdrawal if still pending
                status = pending.get('status', 'pending')
                if status == 'pending':
                    # Request is pending - withdraw it
                    from bot_services.firebase_service import reject_public_request
                    await reject_public_request(pending['request_id'])
                    await call.answer("✅ Community request withdrawn.", show_alert=True)
                else:
                    # Request already processed
                    await call.answer("⚠️ Request already processed by admin. Cannot withdraw.", show_alert=True)
            else:
                # No request - create one
                from bot_services.firebase_service import create_public_request
                success = await create_public_request(user_id, folder_id)
                if success:
                    await call.answer("✅ Public request sent to admins!", show_alert=True)
                else:
                    await call.answer("❌ Failed to send request. Try again.", show_alert=True)
        else:
            # Set has no folder - toggle directly (legacy behavior)
            await toggle_set_privacy(set_id, True)
            await call.answer("🌍 Set is now public.")
    
    # Refresh the actions menu to update button text
    await set_actions(call, state)

@router.callback_query(F.data == "set_delete")
async def process_delete_set(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await delete_set(data['target_id'])
    await call.answer(tr.get_text('set_deleted', 'en'))
    # Return to where we came from
    data = await state.get_data()
    back_cb = data.get('back_to', 'mng_sets')
    if "mng_brow_" in back_cb:
        pid = back_cb.replace("mng_brow_", "")
        pid = None if pid == "None" else pid
        await browse_user_library(call, state, pid)
    else:
        await browse_user_library(call, state, None)

@router.callback_query(F.data.startswith("export_set_"))
async def export_set_handler(call: types.CallbackQuery, state: FSMContext):
    """Show export format selection."""
    set_id = call.data.replace("export_set_", "")
    
    # Get set details for display
    set_data = await get_set(set_id)
    if not set_data:
        await call.answer("❌ Set not found!", show_alert=True)
        return
    
    # Show format selection
    kb = [
        [InlineKeyboardButton(text="📝 DOCX (Word)", callback_data=f"export_docx_{set_id}")],
        [InlineKeyboardButton(text="📕 PDF", callback_data=f"export_pdf_{set_id}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"act_set_{set_id}")]
    ]
    
    await call.message.edit_text(
        f"📄 **Export Set**\n\n"
        f"Set: {set_data.get('set_name')}\n"
        f"Cards: {set_data.get('card_count', 0)}\n\n"
        f"Choose format:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("export_docx_"))
async def export_docx_handler(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Export set as DOCX file."""
    set_id = call.data.replace("export_docx_", "")
    await _perform_export(call, state, bot, set_id, format='docx')

@router.callback_query(F.data.startswith("export_pdf_"))
async def export_pdf_handler(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Export set as PDF file."""
    set_id = call.data.replace("export_pdf_", "")
    await _perform_export(call, state, bot, set_id, format='pdf')

async def _perform_export(call: types.CallbackQuery, state: FSMContext, bot: Bot, set_id: str, format: str):
    """Common export logic for both DOCX and PDF."""
    # Show processing message
    format_name = "DOCX" if format == 'docx' else "PDF"
    await call.answer(f"📄 Generating {format_name} file...", show_alert=False)
    
    # Get set details
    set_data = await get_set(set_id)
    if not set_data:
        await call.answer("❌ Set not found!", show_alert=True)
        return
    
    # Get all cards
    cards = await get_set_cards(set_id)
    if not cards:
        await call.answer("❌ No cards in this set!", show_alert=True)
        return
    
    try:
        # Generate file
        from bot_services.export_service import generate_set_docx, generate_set_pdf, cleanup_export_file
        from datetime import datetime
        
        # Prepare data for export
        export_data = {
            'set_name': set_data.get('set_name', 'Untitled'),
            'created_at': set_data.get('created_at', datetime.now().strftime('%Y-%m-%d'))
        }
        
        # Convert cards to simple format
        cards_list = [{'term': card.get('term', ''), 'definition': card.get('definition', '')} for card in cards]
        
        # Generate based on format
        if format == 'docx':
            filepath = await generate_set_docx(export_data, cards_list)
            file_ext = 'docx'
            icon = '📝'
        else:  # pdf
            filepath = await generate_set_pdf(export_data, cards_list)
            file_ext = 'pdf'
            icon = '📕'
        
        # Send document to user
        with open(filepath, 'rb') as doc_file:
            await bot.send_document(
                chat_id=call.message.chat.id,
                document=types.BufferedInputFile(
                    file=doc_file.read(),
                    filename=f"{set_data.get('set_name', 'flashcards')}.{file_ext}"
                ),
                caption=f"{icon} **{set_data.get('set_name')}**\n{len(cards_list)} cards exported as {format_name}",
                parse_mode="Markdown"
            )
        
        # Cleanup temp file
        cleanup_export_file(filepath)
        
        # Show success
        await call.answer(f"✅ {format_name} file sent!", show_alert=False)
        
        # Return to set actions
        await set_actions(call, state)
        
    except Exception as e:
        print(f"Export error: {e}")
        await call.answer(f"❌ Export failed: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("prev_mng_"))
async def preview_set_manage(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.replace("prev_mng_", "").split("_")
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
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"prev_mng_{set_id}_{page-1}"))
    if end_idx < len(cards):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"prev_mng_{set_id}_{page+1}"))
    
    if nav_row:
            kb.append(nav_row)
        
    kb.append([InlineKeyboardButton(text="Back", callback_data=f"act_set_{set_id}")])
    await call.message.edit_text(preview_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("adm_edit_cards_"))
async def admin_edit_cards_handler(call: types.CallbackQuery, state: FSMContext):
    """Admin card editor - paginated view with edit buttons."""
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.replace("adm_edit_cards_", "").split("_")
    set_id = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    
    s = await get_set(set_id)
    if not s:
        await call.answer("❌ Set not found.", show_alert=True)
        return
    
    cards = await get_set_cards(set_id)
    
    if not cards:
        await call.answer("This set has no cards yet.", show_alert=True)
        text = f"✏️ **Edit Cards: {s['set_name']}**\n\nNo cards in this set yet."
        kb = [[InlineKeyboardButton(text="Back", callback_data=f"act_set_{set_id}")]]
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
        return
    
    # Pagination - show 5 cards per page
    limit = 5
    start_idx = page * limit
    end_idx = min(start_idx + limit, len(cards))
    current_cards = cards[start_idx:end_idx]
    
    # Build message text
    text = f"✏️ **Edit Cards: {s['set_name']}**\n\n"
    text += f"Total cards: {len(cards)} | Page {page+1}/{(len(cards)-1)//limit + 1}\n\n"
    
    for i, c in enumerate(current_cards, start=start_idx+1):
        term = c.get('term', '???')
        definition = c.get('definition', '???')
        text += f"{i}. **{term}** → {definition}\n\n"
    
    # Build keyboard with numbered buttons for each card
    kb = []
    row = []
    for i in range(start_idx, end_idx):
        card_num = i + 1
        row.append(InlineKeyboardButton(text=str(card_num), callback_data=f"edit_card_{set_id}_{i}"))
        if len(row) == 5:  # 5 buttons per row
            kb.append(row)
            row = []
    if row:  # Add remaining buttons
        kb.append(row)
    
    # Navigation arrows
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_edit_cards_{set_id}_{page-1}"))
    if end_idx < len(cards):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_edit_cards_{set_id}_{page+1}"))
    if nav_row:
        kb.append(nav_row)
    
    kb.append([InlineKeyboardButton(text="Back", callback_data=f"act_set_{set_id}")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("edit_card_"))
async def start_edit_card(call: types.CallbackQuery, state: FSMContext):
    """Start editing a specific card."""
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.replace("edit_card_", "").split("_")
    set_id = parts[0]
    card_index = int(parts[1])
    
    cards = await get_set_cards(set_id)
    if card_index >= len(cards):
        await call.answer("❌ Card not found.", show_alert=True)
        return
    
    card = cards[card_index]
    
    # Store card info in state
    await state.update_data(
        edit_set_id=set_id,
        edit_card_index=card_index,
        edit_card_id=card.get('card_id'),
        old_term=card.get('term'),
        old_definition=card.get('definition')
    )
    
    text = (
        f"**Edit Card #{card_index+1}**\n\n"
        f"Current:\n"
        f"**Term**: {card.get('term', '???')}\n"
        f"**Definition**: {card.get('definition', '???')}\n\n"
        f"Enter new term:"
    )
    
    await state.set_state(ManageStates.waiting_card_edit_term)
    await call.message.edit_text(text, reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(ManageStates.waiting_card_edit_term)
async def process_card_term(message: types.Message, state: FSMContext):
    """Process the new term."""
    new_term = message.text
    await state.update_data(new_term=new_term)
    
    data = await state.get_data()
    old_def = data.get('old_definition', '???')
    
    text = (
        f"**New Term**: {new_term}\n\n"
        f"Current Definition: {old_def}\n\n"
        f"Enter new definition:"
    )
    
    await state.set_state(ManageStates.waiting_card_edit_def)
    await message.answer(text, reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(ManageStates.waiting_card_edit_def)
async def process_card_definition(message: types.Message, state: FSMContext):
    """Process the new definition and update the card."""
    new_definition = message.text
    
    data = await state.get_data()
    set_id = data.get('edit_set_id')
    new_term = data.get('new_term')
    
    # Update card in Firebase
    # Cards are stored in subcollection: sets/{set_id}/cards/{card_id}
    from bot_services.firebase_service import db
    cards = await get_set_cards(set_id)
    card_index = data.get('edit_card_index')
    
    if card_index < len(cards):
        card = cards[card_index]
        card_id = card.get('card_id')
        
        # Update the card
        db.collection('sets').document(set_id).collection('cards').document(card_id).update({
            "term": new_term,
            "definition": new_definition
        })
        
        await message.answer(
            f"✅ Card #{card_index+1} updated!\n\n**{new_term}** → {new_definition}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Back to Edit Cards", callback_data=f"adm_edit_cards_{set_id}_0")
            ]])
        )
    else:
        await message.answer("❌ Error updating card.")
    
    await state.clear()


# ==========================================
# ADMIN: MODERATE PUBLIC SETS (NEW)
# ==========================================
@router.callback_query(F.data.startswith("adm_mod_public"))
async def list_community_folders(call: types.CallbackQuery, state: FSMContext):
    """Show community folders (approved but not yet official)."""
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.split("_")
    page = int(parts[3]) if len(parts) > 3 else 0
    
    # Get folders with folder_type='community'
    from bot_services.firebase_service import get_admin_folders
    folders = await get_admin_folders(parent_id=None, folder_type='community')
    
    if not folders:
        await call.answer("No community folders pending review.", show_alert=True)
        # Still show the view with back button
        kb = [[InlineKeyboardButton(text="Back", callback_data="admin_panel")]]
        await call.message.edit_text(
            "🌍 **Review Public Content**\n\nNo community folders pending review.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="Markdown"
        )
        return

    limit = 10
    start_idx = page * limit
    end_idx = start_idx + limit
    current_folders = folders[start_idx:end_idx]

    kb = []
    for f in current_folders:
        folder_name = f.get('folder_name', 'Untitled')
        folder_id = f['folder_id']
        owner_name = f.get('owner_id', 'Unknown')  # Could fetch user name if needed
        kb.append([InlineKeyboardButton(
            text=f"� {folder_name}",
            callback_data=f"adm_comm_folder_{folder_id}"
        )])
        
    # Navigation
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_mod_public_{page-1}"))
    if end_idx < len(folders):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_mod_public_{page+1}"))
    if nav_row: kb.append(nav_row)

    kb.append([InlineKeyboardButton(text="Back", callback_data="admin_panel")])
    await state.update_data(back_to=f"adm_mod_public_{page}")
    
    text = f"🌍 **Review Public Content**\n\nCommunity folders pending review: {len(folders)}"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "adm_community_sets")
async def browse_community_root(call: types.CallbackQuery, state: FSMContext):
    """Browse community folders (approved but not official yet)."""
    if not await is_admin(call.from_user.id): return
    await browse_community_folders(call, state, None, 0)

@router.callback_query(F.data.startswith("adm_comm_"))
async def browse_community_handler(call: types.CallbackQuery, state: FSMContext):
    """Handle community folder navigation."""
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.replace("adm_comm_", "").split("_")
    raw_pid = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    parent_id = None if raw_pid == "None" else raw_pid
    
    await browse_community_folders(call, state, parent_id, page)

async def browse_community_folders(call, state, parent_id, page=0):
    """Browse community folders with pagination."""
    current_name = "Community Library"
    raw_pid = parent_id if parent_id else "None"
    
    # Determine correct "Back" callback
    if parent_id:
        # In a subfolder - back to parent
        curr_folder = await get_folder(parent_id)
        if curr_folder:
            current_name = curr_folder['folder_name']
            grandparent = curr_folder.get('parent_id')
            back_id = f"adm_comm_{grandparent if grandparent else 'None'}_0"
        else:
            # Folder not found, default to admin panel
            parent_id = None
            back_id = "admin_panel"
    else:
        # At root - go back to admin panel
        back_id = "admin_panel"

    # Get community folders (folder_type='community')
    subfolders = await get_admin_folders(parent_id, folder_type='community')
    sets = []
    if parent_id:
        sets = await get_sets_in_folder(parent_id)

    # Combine for Pagination
    all_items = []
    for f in subfolders: all_items.append({'type': 'folder', 'data': f})
    for s in sets: all_items.append({'type': 'set', 'data': s})
    
    limit = 10
    start_idx = page * limit
    end_idx = start_idx + limit
    current_items = all_items[start_idx:end_idx]

    kb = []
    for item in current_items:
        if item['type'] == 'folder':
            f = item['data']
            kb.append([InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"adm_comm_{f['folder_id']}_0")]) 
        else:
            s = item['data']
            kb.append([InlineKeyboardButton(text=f"📄 {s['set_name']}", callback_data=f"act_set_{s['set_id']}")])

    # Navigation
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_comm_{raw_pid}_{page-1}"))
    if end_idx < len(all_items):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_comm_{raw_pid}_{page+1}"))
    if nav_row: kb.append(nav_row)

    # Admin action: Move to Official
    if parent_id:
        kb.append([InlineKeyboardButton(text="⭐ Move to Official Library", callback_data=f"move_official_{parent_id}")])
    
    kb.append([InlineKeyboardButton(text="Back", callback_data=back_id),
               InlineKeyboardButton(text="🏠 Home", callback_data="cancel")])
    
    await call.message.edit_text(f"🌍 **{current_name}** (Page {page+1})\n\nCommunity Sets:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# Note: move_folder_to_official for "move_official_" callback is handled by the earlier
# definition at line 54-68 which uses "adm_make_official_" callback pattern

@router.callback_query(F.data.startswith("adm_pub_sets_"))
async def list_public_user_sets(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.split("_")
    page = int(parts[3]) if len(parts) > 3 else 0
    
    sets = await get_public_user_sets()
    
    if not sets:
        await call.answer("No public user sets found.", show_alert=True)
        return

    limit = 10
    start_idx = page * limit
    end_idx = start_idx + limit
    current_sets = sets[start_idx:end_idx]

    kb = []
    for s in current_sets:
        kb.append([InlineKeyboardButton(text=f"👤 {s['set_name']}", callback_data=f"act_set_{s['set_id']}")])
        
    # Navigation
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_mod_public_{page-1}"))
    if end_idx < len(sets):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_mod_public_{page+1}"))
    if nav_row: kb.append(nav_row)

    kb.append([InlineKeyboardButton(text="Back", callback_data="admin_panel")])
    await state.update_data(back_to=f"adm_mod_public_{page}")
    await call.message.edit_text(f"🌐 **Public User Sets (Page {page+1}):**\nClick to Moderate/Steal", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# ... (Keep Admin Browser, Create/Rename/Delete Folder, Move Set Logic EXACTLY same as before) ...
# ==========================================
# ADMIN: INFINITE FOLDER BROWSER
# ==========================================

# Handles browsing folders: adm_brow_{folder_id} (or None for root)
@router.callback_query(F.data.startswith("adm_brow_"))
async def admin_browse_folder(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.replace("adm_brow_", "").split("_")
    raw_pid = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    parent_id = None if raw_pid == "None" else raw_pid
    
    current_name = "Root Library"
    back_id = "admin_panel"
    
    if parent_id:
        curr_folder = await get_folder(parent_id)
        if curr_folder:
            current_name = curr_folder['folder_name']
            grandparent = curr_folder.get('parent_id')
            back_id = f"adm_brow_{grandparent}_0"
        else:
            parent_id = None 

    subfolders = await get_admin_folders(parent_id, folder_type='official')
    sets = []
    if parent_id:
        sets = await get_sets_in_folder(parent_id)

    # Combine for Pagination
    all_items = []
    for f in subfolders: all_items.append({'type': 'folder', 'data': f})
    for s in sets: all_items.append({'type': 'set', 'data': s})
    
    limit = 10
    start_idx = page * limit
    end_idx = start_idx + limit
    current_items = all_items[start_idx:end_idx]

    kb = []
    for item in current_items:
        if item['type'] == 'folder':
            f = item['data']
            kb.append([InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"adm_brow_{f['folder_id']}_0")]) 
        else:
            s = item['data']
            kb.append([InlineKeyboardButton(text=f"📄 {s['set_name']}", callback_data=f"act_set_{s['set_id']}")])

    # Navigation
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_brow_{raw_pid}_{page-1}"))
    if end_idx < len(all_items):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_brow_{raw_pid}_{page+1}"))
    if nav_row: kb.append(nav_row)

    # Admin Controls
    kb.append([InlineKeyboardButton(text="➕ New Folder Here", callback_data=f"mk_fold_{raw_pid}"),
               InlineKeyboardButton(text="📁 Add Folder", callback_data=f"adm_add_fold_{raw_pid}")])

    
    
    if parent_id:
        kb.append([InlineKeyboardButton(text="✏️ Rename This Folder", callback_data=f"ren_fold_{parent_id}"),
                   InlineKeyboardButton(text="📝 Edit Description", callback_data=f"adm_edit_desc_{parent_id}")])
        
        # Move folder within official hierarchy
        kb.append([InlineKeyboardButton(text="📂 Move Folder", callback_data=f"adm_move_fold_{parent_id}")])
        
        # Check if this is an official folder - offer to move back to review
        curr_folder = await get_folder(parent_id)
        if curr_folder and curr_folder.get('folder_type') == 'official':
            kb.append([InlineKeyboardButton(text="⬅️ Move Back to Review", callback_data=f"move_to_community_{parent_id}")])
        
        kb.append([InlineKeyboardButton(text="🗑 Delete This Folder", callback_data=f"del_fold_{parent_id}")])

    kb.append([InlineKeyboardButton(text="Back", callback_data=back_id),
               InlineKeyboardButton(text="🏠 Home", callback_data="cancel")])
    
    # Get description if viewing a folder
    folder_desc = ""
    if parent_id:
        curr_folder = await get_folder(parent_id) if not curr_folder else curr_folder
        if curr_folder:
            folder_desc = curr_folder.get('description', '')
    
    display_text = f"📂 **{current_name}** (Page {page+1})\n\nContents:"
    if folder_desc:
        display_text = f"📂 **{current_name}** (Page {page+1})\n\n_{folder_desc}_\n\nContents:"
    
    await call.message.edit_text(display_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# --- Create Folder Logic ---
@router.callback_query(F.data.startswith("mk_fold_"))
async def ask_new_folder_name_admin(call: types.CallbackQuery, state: FSMContext):
    await ask_new_folder_name(call, state, is_admin_mode=True)

@router.callback_query(F.data.startswith("usr_mk_fold_"))
async def ask_new_folder_name_user(call: types.CallbackQuery, state: FSMContext):
    await ask_new_folder_name(call, state, is_admin_mode=False)

async def ask_new_folder_name(call: types.CallbackQuery, state: FSMContext, is_admin_mode=True):
    prefix = "mk_fold_" if is_admin_mode else "usr_mk_fold_"
    raw_pid = call.data.replace(prefix, "")
    # Save where we are creating it
    await state.update_data(parent_id=None if raw_pid == "None" else raw_pid)
    await state.update_data(is_renaming=False)
    await state.update_data(is_admin_mode=is_admin_mode) # Track who is creating
    await state.set_state(ManageStates.waiting_new_book_name)
    await call.message.edit_text("Enter Name for New Folder:", reply_markup=get_home_kb({'btn_home': '🏠 Home'}))

# --- Rename Folder Logic ---
@router.callback_query(F.data.startswith("ren_fold_"))
async def ask_rename_folder(call: types.CallbackQuery, state: FSMContext):
    fid = call.data.replace("ren_fold_", "")
    await state.update_data(target_id=fid)
    await state.set_state(ManageStates.waiting_new_book_name) 
    await state.update_data(is_renaming=True)
    await call.message.edit_text("Enter new name:", reply_markup=get_home_kb({'btn_home': '🏠 Home'}))

# --- Handle Folder Name Input (Create or Rename) ---
@router.message(ManageStates.waiting_new_book_name)
async def process_book_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = await get_user(message.from_user.id)
    
    if data.get('is_renaming'):
        from bot_services.firebase_service import db # Safe local import
        db.collection('folders').document(data['target_id']).update({"folder_name": message.text})
        msg_text = f"✅ Folder renamed to '{message.text}'."
    else:
        is_admin_mode = data.get('is_admin_mode', False)
        if is_admin_mode:
            # Admin creating official library folder
            from bot_services.firebase_service import create_official_folder
            await create_official_folder(message.from_user.id, message.text, parent_id=data.get('parent_id'))
        else:
            # User creating personal folder
            await create_book(message.from_user.id, message.text, parent_id=data.get('parent_id'))
        msg_text = tr.get_text('book_created', user['lang_code'], name=message.text)
    
    # Determine where to go back
    pid = data.get('parent_id')
    is_admin_mode = data.get('is_admin_mode', False)  # FIXED: Default to False for user mode
    
    if is_admin_mode:
        back_key = f"adm_brow_{pid}_0" if not data.get('is_renaming') else "menu_manage"
    else:
        back_key = f"mng_brow_{pid}" if not data.get('is_renaming') else "menu_manage"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Folder", callback_data=back_key)],
        [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
    ])
    
    await message.answer(msg_text, reply_markup=kb)
    await state.clear()

# --- Edit Folder Description ---
@router.callback_query(F.data.startswith("edit_desc_"))
async def ask_folder_description(call: types.CallbackQuery, state: FSMContext):
    """Ask user to enter folder description."""
    folder_id = call.data.replace("edit_desc_", "")
    folder = await get_folder(folder_id)
    
    if not folder:
        await call.answer("❌ Folder not found.", show_alert=True)
        return
    
    current_desc = folder.get('description', '')
    
    await state.update_data(folder_id=folder_id)
    await state.set_state(ManageStates.waiting_folder_description)
    
    text = (
        f"📝 **Edit Description**\n\n"
        f"**Folder:** {folder.get('folder_name', 'Untitled')}\n\n"
    )
    if current_desc:
        text += f"**Current Description:**\n_{current_desc}_\n\n"
    text += "Enter a new description (or send `/clear` to remove it):"
    
    await call.message.edit_text(text, reply_markup=get_home_kb({'btn_home': '🏠 Cancel'}), parse_mode="Markdown")

@router.message(ManageStates.waiting_folder_description)
async def process_folder_description(message: types.Message, state: FSMContext):
    """Process folder description input."""
    data = await state.get_data()
    folder_id = data.get('folder_id')
    
    if not folder_id:
        await message.answer("❌ Error: Folder not found.")
        await state.clear()
        return
    
    # Handle /clear command to remove description
    if message.text.strip().lower() == '/clear':
        description = ""
        msg_text = "✅ Description removed!"
    else:
        description = message.text.strip()
        msg_text = f"✅ Description updated!"
    
    # Update in Firebase
    from bot_services.firebase_service import update_folder_description
    await update_folder_description(folder_id, description)
    
    # Build back keyboard - different for admin vs user mode
    is_admin_mode = data.get('is_admin_mode', False)
    if is_admin_mode:
        back_cb = f"adm_brow_{folder_id}_0"
    else:
        back_cb = f"mng_brow_{folder_id}_0"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Folder", callback_data=back_cb)],
        [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
    ])
    
    await message.answer(msg_text, reply_markup=kb)
    await state.clear()

# --- Admin Edit Description ---
@router.callback_query(F.data.startswith("adm_edit_desc_"))
async def admin_ask_folder_description(call: types.CallbackQuery, state: FSMContext):
    """Ask admin to enter folder description (for official/community folders)."""
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Admin only.", show_alert=True)
        return
        
    folder_id = call.data.replace("adm_edit_desc_", "")
    folder = await get_folder(folder_id)
    
    if not folder:
        await call.answer("❌ Folder not found.", show_alert=True)
        return
    
    current_desc = folder.get('description', '')
    
    await state.update_data(folder_id=folder_id, is_admin_mode=True)
    await state.set_state(ManageStates.waiting_folder_description)
    
    text = (
        f"📝 **Edit Description** (Admin)\n\n"
        f"**Folder:** {folder.get('folder_name', 'Untitled')}\n\n"
    )
    if current_desc:
        text += f"**Current Description:**\n_{current_desc}_\n\n"
    text += "Enter a new description (or send `/clear` to remove it):"
    
    await call.message.edit_text(text, reply_markup=get_home_kb({'btn_home': '🏠 Cancel'}), parse_mode="Markdown")

# --- Delete Folder Logic ---
@router.callback_query(F.data.startswith("del_fold_"))
async def ask_delete_confirmation(call: types.CallbackQuery, state: FSMContext):
    """Ask for confirmation before deleting folder."""
    fid = call.data.replace("del_fold_", "")
    folder = await get_folder(fid)
    
    if not folder:
        await call.answer("❌ Folder not found.", show_alert=True)
        return
    
    folder_name = folder.get('folder_name', 'Untitled')
    parent_id = folder.get('parent_id')  # Get parent for navigation after delete
    
    # Detect if we're in admin mode by checking current state
    data = await state.get_data()
    current_back = data.get('back_to', '')
    is_admin = current_back.startswith('adm_brow_')
    
    # Store folder ID, parent, and mode in state
    await state.update_data(
        delete_folder_id=fid,
        delete_parent_id=parent_id,
        delete_is_admin=is_admin
    )
    await state.set_state(ManageStates.waiting_delete_folder)
    
    # Show confirmation dialog
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"confirm_del_{fid}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_delete")]
    ])
    
    warning_text = (
        f"⚠️ **Delete Folder?**\n\n"
        f"📂 Folder: **{folder_name}**\n\n"
        f"This will:\n"
        f"• Move all sets to 'Untitled' folder\n"
        f"• Remove all subfolders\n\n"
        f"**This action cannot be undone!**"
    )
    
    await call.message.edit_text(warning_text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("confirm_del_"), ManageStates.waiting_delete_folder)
async def delete_folder_handler(call: types.CallbackQuery, state: FSMContext):
    fid = call.data.replace("confirm_del_", "")
    
    # Get stored context
    data = await state.get_data()
    parent_id = data.get('delete_parent_id')
    is_admin = data.get('delete_is_admin', False)
    
    await delete_folder(fid)
    await call.answer("✅ Folder deleted successfully!", show_alert=True)
    await state.clear()
    
    # Navigate based on context
    if is_admin:
        # Admin mode - go back to admin panel to avoid confusion
        from bot_handlers.admin import admin_panel_cb
        await admin_panel_cb(call)
    else:
        # User mode - navigate to parent or root
        await browse_user_library(call, state, parent_id, 0)


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete_folder(call: types.CallbackQuery, state: FSMContext):
    """Cancel folder deletion."""
    await call.answer("Deletion cancelled.")
    await state.clear()
    
    # Return to manage menu
    await manage_menu(call, state) 

# --- Move Folder Logic ---
@router.callback_query(F.data.startswith("move_fold_"))
async def start_folder_move(call: types.CallbackQuery, state: FSMContext):
    """Start folder move process."""
    folder_id = call.data.replace("move_fold_", "")
    await state.update_data(moving_folder_id=folder_id)
    await show_folder_move_browser(call, state, None)

async def show_folder_move_browser(call: types.CallbackQuery, state: FSMContext, current_location):
    """Show folder browser for selecting destination."""
    user_id = call.from_user.id
    data = await state.get_data()
    folder_id_being_moved = data.get('moving_folder_id')
    
    # Get folder being moved
    folder_being_moved = await get_folder(folder_id_being_moved)
    if not folder_being_moved:
        await call.answer("❌ Folder not found.", show_alert=True)
        return
    
    folder_name = folder_being_moved.get('folder_name', 'Unknown')
    
    # Get folders at current location
    folders = await get_user_folders(user_id, current_location)
    
    # Filter out the folder being moved
    valid_folders = [f for f in folders if f['folder_id'] != folder_id_being_moved]
    
    current_name = "Root Library" if not current_location else "..."
    if current_location:
        curr = await get_folder(current_location)
        if curr:
            current_name = curr.get('folder_name', 'Folder')
    
    kb = []
    
    # "Move Here" button
    kb.append([InlineKeyboardButton(text="📥 MOVE HERE", callback_data=f"exec_fold_move_{current_location if current_location else 'None'}")])
    kb.append([])  # Separator
    
    # Show subfolders
    for f in valid_folders:
        kb.append([InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"browse_fold_move_{f['folder_id']}")])
    
    # Navigation
    if current_location:
        curr = await get_folder(current_location)
        if curr:
            parent = curr.get('parent_id')
            parent_raw = parent if parent else "None"
            kb.append([InlineKeyboardButton(text="⬆️ Parent Folder", callback_data=f"browse_fold_move_{parent_raw}")])
    
    kb.append([InlineKeyboardButton(text="❌ Cancel", callback_data=f"mng_brow_{folder_id_being_moved}_0")])
    
    await call.message.edit_text(
        f"📂 **Move Folder: {folder_name}**\n\n"
        f"Current location: **{current_name}**\n\n"
        f"Select destination folder or click 'MOVE HERE':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("browse_fold_move_"))
async def navigate_folder_move(call: types.CallbackQuery, state: FSMContext):
    """Navigate through folders during move."""
    raw_pid = call.data.replace("browse_fold_move_", "")
    parent_id = None if raw_pid == "None" else raw_pid
    await show_folder_move_browser(call, state, parent_id)

@router.callback_query(F.data.startswith("exec_fold_move_"))
async def execute_folder_move(call: types.CallbackQuery, state: FSMContext):
    """Execute the folder move."""
    raw_dest = call.data.replace("exec_fold_move_", "")
    dest_folder_id = None if raw_dest == "None" else raw_dest
    
    data = await state.get_data()
    folder_id = data.get('moving_folder_id')
    # Move the folder
    await move_folder(folder_id, dest_folder_id)
    
    await call.answer("✅ Folder moved successfully!", show_alert=True)
    await state.update_data(moving_folder_id=None)
    
    # Return to the destination folder
    await browse_user_library(call, state, dest_folder_id, 0) 

# --- Admin Move Folder Logic (for Official Content) ---
@router.callback_query(F.data.startswith("adm_move_fold_"))
async def start_admin_folder_move(call: types.CallbackQuery, state: FSMContext):
    """Start admin folder move process for official content."""
    if not await is_admin(call.from_user.id): return
    
    folder_id = call.data.replace("adm_move_fold_", "")
    await state.update_data(adm_moving_folder_id=folder_id)
    await show_admin_folder_move_browser(call, state, None)

async def show_admin_folder_move_browser(call: types.CallbackQuery, state: FSMContext, current_location):
    """Show admin folder browser for selecting destination in official content."""
    data = await state.get_data()
    folder_id_being_moved = data.get('adm_moving_folder_id')
    
    # Get folder being moved
    folder_being_moved = await get_folder(folder_id_being_moved)
    if not folder_being_moved:
        await call.answer("❌ Folder not found.", show_alert=True)
        return
    
    folder_name = folder_being_moved.get('folder_name', 'Unknown')
    
    # Get official folders at current location
    folders = await get_admin_folders(current_location, folder_type='official')
    
    # Filter out the folder being moved and its children
    valid_folders = [f for f in folders if f['folder_id'] != folder_id_being_moved]
    
    current_name = "Root Library" if not current_location else "..."
    if current_location:
        curr = await get_folder(current_location)
        if curr:
            current_name = curr.get('folder_name', 'Folder')
    
    kb = []
    
    # "Move Here" button
    kb.append([InlineKeyboardButton(text="📥 MOVE HERE", callback_data=f"adm_exec_fold_move_{current_location if current_location else 'None'}")])
    kb.append([])  # Separator
    
    # Show subfolders
    for f in valid_folders:
        kb.append([InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"adm_browse_fold_move_{f['folder_id']}")])
    
    # Navigation
    if current_location:
        curr = await get_folder(current_location)
        if curr:
            parent = curr.get('parent_id')
            parent_raw = parent if parent else "None"
            kb.append([InlineKeyboardButton(text="⬆️ Parent Folder", callback_data=f"adm_browse_fold_move_{parent_raw}")])
    
    kb.append([InlineKeyboardButton(text="❌ Cancel", callback_data=f"adm_brow_{folder_id_being_moved}_0")])
    
    await call.message.edit_text(
        f"📂 **Move Folder: {folder_name}**\n\n"
        f"Current location: **{current_name}**\n\n"
        f"Select destination folder or click 'MOVE HERE':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("adm_browse_fold_move_"))
async def navigate_admin_folder_move(call: types.CallbackQuery, state: FSMContext):
    """Navigate through admin folders during move."""
    if not await is_admin(call.from_user.id): return
    
    raw_pid = call.data.replace("adm_browse_fold_move_", "")
    parent_id = None if raw_pid == "None" else raw_pid
    await show_admin_folder_move_browser(call, state, parent_id)

@router.callback_query(F.data.startswith("adm_exec_fold_move_"))
async def execute_admin_folder_move(call: types.CallbackQuery, state: FSMContext):
    """Execute the admin folder move."""
    if not await is_admin(call.from_user.id): return
    
    raw_dest = call.data.replace("adm_exec_fold_move_", "")
    dest_folder_id = None if raw_dest == "None" else raw_dest
    
    data = await state.get_data()
    folder_id = data.get('adm_moving_folder_id')
    
    # Move the folder
    await move_folder(folder_id, dest_folder_id)
    
    await call.answer("✅ Folder moved successfully!", show_alert=True)
    await state.update_data(adm_moving_folder_id=None)
    
    # Return to the destination folder in admin browser
    if dest_folder_id:
        # Simulate callback to admin browser
        call.data = f"adm_brow_{dest_folder_id}_0"
        await admin_browse_folder(call, state)
    else:
        call.data = "adm_brow_None_0"
        await admin_browse_folder(call, state)

# --- Add Folder Logic (move existing folder INTO current folder) ---
@router.callback_query(F.data.startswith("add_fold_"))
async def start_add_folder_to_current(call: types.CallbackQuery, state: FSMContext):
    """Start process of adding existing folder into current folder."""
    destination_id = call.data.replace("add_fold_", "")
    if destination_id == "None":
        destination_id = None
    
    await state.update_data(add_folder_destination=destination_id)
    
    # Show folder picker starting at root
    await show_add_folder_picker(call, state, None)

async def show_add_folder_picker(call, state, browse_location):
    """Show folders to select which one to add to destination."""
    user_id = call.from_user.id
    data = await state.get_data()
    destination_id = data.get('add_folder_destination')
    
    # Get destination folder info
    dest_name = "Root Library"
    if destination_id:
        dest_folder = await get_folder(destination_id)
        dest_name = dest_folder.get('folder_name', 'Folder') if dest_folder else "Folder"
    
    # Get folders at browse location
    folders = await get_user_folders(user_id, browse_location)
    
    # Exclude destination folder
    valid_folders = [f for f in folders if f['folder_id'] != destination_id]
    
    current_name = "Root Library" if not browse_location else "..."
    if browse_location:
        curr = await get_folder(browse_location)
        if curr:
            current_name = curr.get('folder_name', 'Folder')
    
    kb = []
    
    # Show folders with browse and select buttons
    for f in valid_folders:
        kb.append([
            InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"browse_add_fold_{f['folder_id']}"),
            InlineKeyboardButton(text="✅ Select", callback_data=f"select_add_fold_{f['folder_id']}")
        ])
    
    # Navigation
    if browse_location:
        curr = await get_folder(browse_location)
        if curr:
            parent = curr.get('parent_id')
            parent_raw = parent if parent else "None"
            kb.append([InlineKeyboardButton(text="⬆️ Parent Folder", callback_data=f"browse_add_fold_{parent_raw}")])
    
    kb.append([InlineKeyboardButton(text="❌ Cancel", callback_data=f"mng_brow_{destination_id if destination_id else 'None'}_0")])
    
    text = (
        f"**Add Folder to: {dest_name}**\n\n"
        f"Browsing: {current_name}\n\n"
        f"Click folder name to browse inside,\n"
        f"or click ✅ to select it:"
    )
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("browse_add_fold_"))
async def navigate_add_folder_picker(call, state):
    """Navigate through folders in picker."""
    raw_id = call.data.replace("browse_add_fold_", "")
    location = None if raw_id == "None" else raw_id
    await show_add_folder_picker(call, state, location)

@router.callback_query(F.data.startswith("select_add_fold_"))
async def execute_add_folder(call, state):
    """Execute adding the selected folder to destination."""
    folder_to_add = call.data.replace("select_add_fold_", "")
    
    data = await state.get_data()
    destination_id = data.get('add_folder_destination')
    
    # Move folder
    await move_folder(folder_to_add, destination_id)
    
    await call.answer("✅ Folder added successfully!", show_alert=True)
    await state.clear()
    
    # Return to destination folder
    await browse_user_library(call, state, destination_id, 0)

# --- Admin Add Folder Logic (for Official/Review sections) ---
@router.callback_query(F.data.startswith("adm_add_fold_"))
async def start_admin_add_folder(call: types.CallbackQuery, state: FSMContext):
    """Start process of adding existing folder into current admin folder."""
    if not await is_admin(call.from_user.id): return
    
    destination_id = call.data.replace("adm_add_fold_", "")
    if destination_id == "None":
        destination_id = None
    
    await state.update_data(adm_add_folder_destination=destination_id)
    
    # Show admin folder picker starting at root
    await show_admin_add_folder_picker(call, state, None)

async def show_admin_add_folder_picker(call, state, browse_location):
    """Show admin folders to select which one to add to destination."""
    data = await state.get_data()
    destination_id = data.get('adm_add_folder_destination')
    
    # Get destination folder info
    dest_name = "Root Official Library"
    if destination_id:
        dest_folder = await get_folder(destination_id)
        dest_name = dest_folder.get('folder_name', 'Folder') if dest_folder else "Folder"
    
    # Get admin folders at browse location (official folders)
    folders = await get_admin_folders(browse_location, folder_type='official')
    
    # Exclude destination folder
    valid_folders = [f for f in folders if f['folder_id'] != destination_id]
    
    current_name = "Root Official Library" if not browse_location else "..."
    if browse_location:
        curr = await get_folder(browse_location)
        if curr:
            current_name = curr.get('folder_name', 'Folder')
    
    kb = []
    
    # Show folders with browse and select buttons
    for f in valid_folders:
        kb.append([
            InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"browse_adm_add_fold_{f['folder_id']}"),
            InlineKeyboardButton(text="✅ Select", callback_data=f"select_adm_add_fold_{f['folder_id']}")
        ])
    
    # Navigation
    if browse_location:
        curr = await get_folder(browse_location)
        if curr:
            parent = curr.get('parent_id')
            parent_raw = parent if parent else "None"
            kb.append([InlineKeyboardButton(text="⬆️ Parent Folder", callback_data=f"browse_adm_add_fold_{parent_raw}")])
    
    kb.append([InlineKeyboardButton(text="❌ Cancel", callback_data=f"adm_brow_{destination_id if destination_id else 'None'}_0")])
    
    text = (
        f"**Add Folder to: {dest_name}**\n\n"
        f"Browsing: {current_name}\n\n"
        f"Click folder name to browse inside,\n"
        f"or click ✅ to select it:"
    )
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("browse_adm_add_fold_"))
async def navigate_admin_add_folder_picker(call, state):
    """Navigate through admin folders in picker."""
    if not await is_admin(call.from_user.id): return
    
    raw_id = call.data.replace("browse_adm_add_fold_", "")
    location = None if raw_id == "None" else raw_id
    await show_admin_add_folder_picker(call, state, location)

@router.callback_query(F.data.startswith("select_adm_add_fold_"))
async def execute_admin_add_folder(call, state):
    """Execute adding the selected folder to admin destination."""
    if not await is_admin(call.from_user.id): return
    
    folder_to_add = call.data.replace("select_adm_add_fold_", "")
    
    data = await state.get_data()
    destination_id = data.get('adm_add_folder_destination')
    
    # Move folder
    await move_folder(folder_to_add, destination_id)
    
    await call.answer("✅ Folder added successfully!", show_alert=True)
    await state.clear()
    
    # Return to destination folder in admin view
    await admin_browse_folder(call, state)
 

# ==========================================
# ADMIN: MOVE SET LOGIC
# ==========================================

@router.callback_query(F.data.startswith("adm_move_start_"))
async def move_browser_start(call: types.CallbackQuery, state: FSMContext):
    # The argument is the current folder ID we are browsing to DROP the set
    raw_pid = call.data.replace("adm_move_start_", "")
    await show_move_browser(call, raw_pid, state)

async def show_move_browser(call, raw_pid, state):
    parent_id = None if raw_pid == "None" else raw_pid
    subfolders = await get_admin_folders(parent_id, folder_type='official')
    
    kb = []
    # Option 1: DROP HERE
    kb.append([InlineKeyboardButton(text="⬇️ PASTE HERE", callback_data=f"do_move_{raw_pid}")])
    
    # Option 2: Go Deeper
    for f in subfolders:
        kb.append([InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"adm_move_start_{f['folder_id']}")])
    
    # Option 3: Back
    back_id = "mng_sets" 
    if parent_id:
        curr = await get_folder(parent_id)
        gp = curr.get('parent_id')
        back_id = f"adm_move_start_{gp}"
        
    kb.append([InlineKeyboardButton(text="Back", callback_data=back_id)])
    
    target_name = "Root"
    if parent_id:
        f = await get_folder(parent_id)
        target_name = f['folder_name']
        
    await call.message.edit_text(f"Select Destination Folder:\nCurrent: **{target_name}**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("do_move_"))
async def execute_move(call: types.CallbackQuery, state: FSMContext):
    target_pid = call.data.replace("do_move_", "")
    final_folder_id = None if target_pid == "None" else target_pid
    
    data = await state.get_data()
    set_id = data['target_id']
    
    await move_set(set_id, final_folder_id)
    
    user = await get_user(call.from_user.id)
    await call.answer(tr.get_text('set_moved', user['lang_code']))
    
    # Return to library
    if "usr_move_" in call.data: # If we add user move logic later
         await browse_user_library(call, state, None)
    else:
         await list_sets(call, state) # Fallback

# ==========================================
# USER: MOVE SET LOGIC (NEW)
# ==========================================
@router.callback_query(F.data.startswith("usr_move_start_"))
async def user_move_browser_start(call: types.CallbackQuery, state: FSMContext):
    raw_pid = call.data.replace("usr_move_start_", "")
    await show_user_move_browser(call, raw_pid, state)

async def show_user_move_browser(call, raw_pid, state):
    parent_id = None if raw_pid == "None" else raw_pid
    user_id = call.from_user.id
    subfolders = await get_user_folders(user_id, parent_id)
    
    kb = []
    # Option 1: DROP HERE
    kb.append([InlineKeyboardButton(text="⬇️ PASTE HERE", callback_data=f"do_usr_move_{raw_pid}")])
    
    # Option 2: Go Deeper
    for f in subfolders:
        kb.append([InlineKeyboardButton(text=f"📁 {f['folder_name']}", callback_data=f"usr_move_start_{f['folder_id']}")])
    
    # Option 3: Back
    back_id = "mng_sets" # Default fallback
    # Ideally we want to go back to set actions, but we lost that context?
    # Actually, we are BROWSING TO MOVE. Back should go up folder tree.
    
    if parent_id:
        curr = await get_folder(parent_id)
        gp = curr.get('parent_id')
        back_id = f"usr_move_start_{gp}"
    else:
        # If at root of move browser, back goes to set actions?
        # We need set_id to go back to actions.
        data = await state.get_data()
        set_id = data.get('target_id')
        back_id = f"act_set_{set_id}"

    kb.append([InlineKeyboardButton(text="Back", callback_data=back_id)])
    
    target_name = "My Library Root"
    if parent_id:
        f = await get_folder(parent_id)
        target_name = f['folder_name']
        
    await call.message.edit_text(f"Select Destination Folder:\nCurrent: **{target_name}**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("do_usr_move_"))
async def execute_user_move(call: types.CallbackQuery, state: FSMContext):
    target_pid = call.data.replace("do_usr_move_", "")
    final_folder_id = None if target_pid == "None" else target_pid
    
    data = await state.get_data()
    set_id = data['target_id']
    
    await move_set(set_id, final_folder_id)
    
    user = await get_user(call.from_user.id)
    await call.answer(tr.get_text('set_moved', user['lang_code']))
    
    # Return to set actions
    await set_actions(call, state)

# ==========================================
# USER: ADD SET TO FOLDER (NEW)
# ==========================================
@router.callback_query(F.data.startswith("usr_add_set_"))
async def select_set_to_add(call: types.CallbackQuery, state: FSMContext):
    target_folder_id = call.data.replace("usr_add_set_", "")
    user_id = call.from_user.id
    
    # Get sets that are in ROOT (folder_id=None)
    root_sets = await get_user_sets(user_id, folder_id=None)
    
    if not root_sets:
        await call.answer("No sets in Root Library to add!", show_alert=True)
        return

    kb = []
    for s in root_sets:
        kb.append([InlineKeyboardButton(text=f"📄 {s['set_name']}", callback_data=f"do_add_set_{s['set_id']}_{target_folder_id}")])
        
    kb.append([InlineKeyboardButton(text="Back", callback_data=f"mng_brow_{target_folder_id}")])
    
    await call.message.edit_text("Select a Set to Move Here:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("do_add_set_"))
async def execute_add_set(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.replace("do_add_set_", "").split("_")
    set_id = parts[0]
    target_folder_id = parts[1]
    
    await move_set(set_id, target_folder_id)
    
    user = await get_user(call.from_user.id)
    await call.answer(tr.get_text('set_moved', user['lang_code']))
    
    # Return to folder
    await browse_user_library(call, state, target_folder_id)

# ==========================================
# ADMIN: MANAGE ADMINS (NEW)
# ==========================================
@router.callback_query(F.data == "adm_manage_admins")
async def admin_management_flow(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    
    admins = await get_admins()
    
    msg = "👥 **Admin List:**\n"
    for a_id in admins:
        u = await get_user(a_id)
        name = u['first_name'] if u else "Unknown"
        msg += f"- {name} (`{a_id}`)\n"
        
    kb = [
        [InlineKeyboardButton(text="➕ Add Admin", callback_data="adm_add_start")],
        [InlineKeyboardButton(text="➖ Remove Admin", callback_data="adm_rem_start")],
        [InlineKeyboardButton(text="Back", callback_data="admin_panel")]
    ]
    await call.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "adm_add_start")
async def add_admin_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ManageStates.waiting_admin_id)
    await call.message.edit_text("Enter the Telegram User ID of the new admin:", reply_markup=get_cancel_kb())

@router.message(ManageStates.waiting_admin_id)
async def add_admin_input(message: types.Message, state: FSMContext):
    new_admin_id = message.text.strip()
    if not new_admin_id.isdigit():
        await message.answer("❌ Invalid ID. Must be numbers only.")
        return
        
    await add_admin_db(new_admin_id, message.from_user.id)
    await message.answer(f"✅ User `{new_admin_id}` added as Admin.", parse_mode="Markdown")
    await state.clear()
    
    # Notify other admins? (Optional, maybe later)

@router.callback_query(F.data == "adm_rem_start")
async def remove_admin_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ManageStates.waiting_rm_admin_id)
    await call.message.edit_text("Enter the Telegram User ID to REMOVE:", reply_markup=get_cancel_kb())

@router.message(ManageStates.waiting_rm_admin_id)
async def remove_admin_input(message: types.Message, state: FSMContext):
    target_id = message.text.strip()
    
    # Safety check: Don't remove yourself? Or allow it?
    # Allow it, but warn.
    
    await message.answer(f"✅ User `{target_id}` removed from Admins.", parse_mode="Markdown")
    await state.clear()

# --- CUSTOM QUIZ MANAGEMENT ---
@router.callback_query(F.data == "mng_cust_quizzes")
async def browse_custom_quizzes(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    quizzes = await get_user_custom_quizzes(user_id)
    
    text = "🛠 **My Custom Quizzes**\n\n"
    if not quizzes:
        text += "You haven't created any quizzes yet."
    else:
        for idx, q in enumerate(quizzes, 1):
             text += f"**{idx}. {q['title']}**\n   Plays: {q.get('plays', 0)}\n"
             
    kb_items = []
    for q in quizzes:
        kb_items.append({'callback_data': f"act_cust_quiz_{q['id']}"})
        
    kb = build_vkm_pagination_kb(
        items=kb_items,
        page=0, 
        total_items=len(quizzes),
        limit=10,
        back_callback="menu_manage",
        nav_prefix="mng_cust_quiz_page_"
    )
    
    # Add Create New button
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Create New Quiz", callback_data="build_quiz_start")])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("act_cust_quiz_"))
async def custom_quiz_actions(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("act_cust_quiz_", "")
    from bot_services.firebase_service import get_custom_quiz, get_quiz_rating, is_favorite
    quiz = await get_custom_quiz(quiz_id)
    
    if not quiz:
        await call.answer("Quiz not found", show_alert=True)
        await browse_custom_quizzes(call, state)
        return
        
    bot_username = (await call.bot.get_me()).username
    share_link = f"https://t.me/{bot_username}?start=quiz_{quiz_id}"
    
    # Get rating
    rating_info = await get_quiz_rating(quiz_id)
    avg_rating = rating_info.get('avg', 0)
    rating_count = rating_info.get('count', 0)
    if rating_count > 0:
        stars = "⭐" * round(avg_rating) + "☆" * (5 - round(avg_rating))
        rating_text = f"{stars} {avg_rating:.1f} ({rating_count} votes)"
    else:
        rating_text = "☆☆☆☆☆ No ratings yet"
    
    # Get timer info
    timer = quiz.get('timer', 30)
    timer_text = {10: "⚡ 10s", 30: "⏱️ 30s", 60: "🐢 60s"}.get(timer, f"{timer}s")
    
    # Check favorite status
    is_fav = await is_favorite(call.from_user.id, 'quiz', quiz_id)
    fav_text = "💔 Remove Favorite" if is_fav else "❤️ Add to Favorites"
    
    text = (
        f"🛠 **{quiz['title']}**\n"
        f"❓ Questions: {len(quiz.get('questions', []))}\n"
        f"▶️ Plays: {quiz.get('plays', 0)}\n"
        f"⏱️ Timer: {timer_text}\n"
        f"⭐ Rating: {rating_text}\n\n"
        f"🔗 Share Link:\n`{share_link}`"
    )
    
    kb = [
        [InlineKeyboardButton(text="📥 Share / Play", url=f"https://t.me/share/url?url={share_link}&text=Play my quiz!")],
        [InlineKeyboardButton(text="👥 Host in Group", callback_data=f"host_group_{quiz_id}")],
        [InlineKeyboardButton(text=fav_text, callback_data=f"tog_fav_quiz_{quiz_id}")],
        [InlineKeyboardButton(text="👁 View Questions", callback_data=f"view_cust_quiz_{quiz_id}")],
        [InlineKeyboardButton(text="✏️ Edit Quiz", callback_data=f"edit_cust_menu_{quiz_id}")],
        [InlineKeyboardButton(text="🗑 Delete", callback_data=f"del_cust_quiz_{quiz_id}")],
        [InlineKeyboardButton(text="Back", callback_data="mng_cust_quizzes")]
    ]
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("tog_fav_quiz_"))
async def toggle_quiz_favorite(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("tog_fav_quiz_", "")
    from bot_services.firebase_service import toggle_favorite
    is_now_fav = await toggle_favorite(call.from_user.id, 'quiz', quiz_id)
    
    if is_now_fav:
        await call.answer("❤️ Added to Favorites!", show_alert=False)
    else:
        await call.answer("💔 Removed from Favorites", show_alert=False)
    
    # Refresh quiz actions
    await custom_quiz_actions(call, state)

@router.callback_query(F.data.startswith("edit_cust_menu_"))
async def edit_quiz_menu(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("edit_cust_menu_", "")
    # Simple menu for Edit actions
    kb = [
        [InlineKeyboardButton(text="📝 Rename Title", callback_data=f"ren_cust_{quiz_id}")],
        [InlineKeyboardButton(text="➕ Add Question", callback_data=f"add_q_cust_{quiz_id}")],
        [InlineKeyboardButton(text="Back", callback_data=f"act_cust_quiz_{quiz_id}")]
    ]
    await call.message.edit_text("✏️ **Edit Quiz**\nChoose an action:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("ren_cust_"))
async def start_rename_quiz(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("ren_cust_", "")
    from bot_services.utils import QuizEditStates
    await state.set_state(QuizEditStates.waiting_new_title)
    await state.update_data(target_quiz_id=quiz_id)
    await call.message.edit_text("Send me the **New Title** for this quiz:", reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(QuizEditStates.waiting_new_title)
async def handle_rename_quiz(message: types.Message, state: FSMContext):
    new_title = message.text.strip()
    if len(new_title) > 50:
        await message.reply("⚠️ Title too long (max 50 chars).")
        return
    data = await state.get_data()
    quiz_id = data['target_quiz_id']
    from bot_services.firebase_service import update_custom_quiz_title
    await update_custom_quiz_title(quiz_id, new_title)
    await message.answer(f"✅ Renamed to **{new_title}**!", reply_markup=get_home_kb()) # Or back to menu?
    # Better to go back to menu? Hard to reconstruct message without call.
    # Just show dashboard or simple text.
    await state.clear()

@router.callback_query(F.data.startswith("add_q_cust_"))
async def start_add_question(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("add_q_cust_", "")
    from bot_services.utils import QuizEditStates
    # Check limit first? 
    from bot_services.firebase_service import get_custom_quiz
    quiz = await get_custom_quiz(quiz_id)
    if not quiz or len(quiz.get('questions', [])) >= 50:
        await call.answer("⚠️ Limit reached (50 questions).", show_alert=True)
        return

    await state.set_state(QuizEditStates.waiting_new_q_text)
    await state.update_data(target_quiz_id=quiz_id)
    await call.message.edit_text("Send me the **New Question Text**:", reply_markup=get_cancel_kb(), parse_mode="Markdown")

@router.message(QuizEditStates.waiting_new_q_text)
async def handle_add_question_text(message: types.Message, state: FSMContext):
    await state.update_data(new_q_text=message.text.strip())
    from bot_services.utils import QuizEditStates
    await state.set_state(QuizEditStates.waiting_new_q_options)
    await message.answer(
        "Send **Options** (Answers) on new lines.\n"
        "1st line = Correct Answer.\n"
        "Min 2 lines, Max 10 lines.",
        reply_markup=get_cancel_kb()
    )

@router.message(QuizEditStates.waiting_new_q_options)
async def handle_add_question_options(message: types.Message, state: FSMContext):
    lines = [l.strip() for l in message.text.split('\n') if l.strip()]
    if len(lines) < 2:
        await message.reply("⚠️ Need at least 2 options.")
        return
    if len(lines) > 10:
        await message.reply("⚠️ Max 10 options.")
        return
        
    data = await state.get_data()
    quiz_id = data['target_quiz_id']
    q_text = data['new_q_text']
    
    new_q = {
        'text': q_text,
        'options': lines,
        'correct_index': 0 
    }
    
    from bot_services.firebase_service import add_question_to_quiz
    await add_question_to_quiz(quiz_id, new_q)
    
    await message.answer("✅ Question Added!", reply_markup=get_home_kb())
    await state.clear()


@router.callback_query(F.data.startswith("view_cust_quiz_"))
async def view_quiz_questions(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("view_cust_quiz_", "")
    from bot_services.firebase_service import get_custom_quiz
    quiz = await get_custom_quiz(quiz_id)
    
    if not quiz:
        await call.answer("Quiz not found", show_alert=True)
        return
        
    text = f"👁 **Questions for: {quiz['title']}**\n\n"
    
    def escape_md(t):
        if not t: return ""
        # Escape characters that break Markdown
        for char in ['*', '_', '`', '[']:
            t = t.replace(char, f"\\{char}")
        return t

    for idx, q in enumerate(quiz.get('questions', []), 1):
        q_text = escape_md(q['text'])
        text += f"**Q{idx}: {q_text}**\n"
        
        # Show options, bold the correct one (first one)
        opts = q['options']
        # Escape options too
        safe_opts = [escape_md(o) for o in opts]
        
        text += f"   ✅ {safe_opts[0]}\n"
        for o in safe_opts[1:]:
            text += f"   ▫️ {o}\n"
        text += "\n"
        
    kb = [
        [InlineKeyboardButton(text="🗑 Delete Question", callback_data=f"del_quiz_q_start_{quiz_id}")],
        [InlineKeyboardButton(text="Back", callback_data=f"act_cust_quiz_{quiz_id}")]
    ]
    
    # Split text if too long
    if len(text) > 4000:
        text = text[:4000] + "\n...(truncated)"
        
    # Send as new message if edit fails (sometimes safer for large content changes)
    try:
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except Exception:
        # Fallback if edit fails (e.g. message too old or content identical)
        await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# --- DELETE SPECIFIC QUESTION ---
@router.callback_query(F.data.startswith("del_quiz_q_start_"))
async def start_delete_question(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("del_quiz_q_start_", "")
    from bot_services.firebase_service import get_custom_quiz
    quiz = await get_custom_quiz(quiz_id)
    
    if not quiz:
        await call.answer("Quiz not found", show_alert=True)
        return
        
    questions = quiz.get('questions', [])
    if not questions:
        await call.answer("No questions to delete.", show_alert=True)
        return
        
    # Build keyboard with question numbers
    kb = []
    row = []
    for i in range(len(questions)):
        row.append(InlineKeyboardButton(text=f"Q{i+1}", callback_data=f"del_quiz_q_do_{quiz_id}_{i}"))
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
        
    kb.append([InlineKeyboardButton(text="🔙 Cancel", callback_data=f"view_cust_quiz_{quiz_id}")])
    
    await call.message.edit_text(
        f"🗑 **Delete Question**\n\n"
        f"Select the question number you want to remove from **{quiz['title']}**:\n"
        f"_(This action cannot be undone)_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("del_quiz_q_do_"))
async def perform_delete_question(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.replace("del_quiz_q_do_", "").split("_")
    # Format: quiz_id_index. But quiz_id might contain underscores? 
    # Actually quiz_ids are document IDs (usually alphanumeric), but let's be safe.
    # The last part is index, rest is quiz_id
    index = int(parts[-1])
    quiz_id = "_".join(parts[:-1])
    
    from bot_services.firebase_service import delete_question_from_quiz
    success = await delete_question_from_quiz(quiz_id, index)
    
    if success:
        await call.answer("✅ Question deleted!", show_alert=True)
        # Return to view questions (which will refresh lists)
        call.data = f"view_cust_quiz_{quiz_id}"
        await view_quiz_questions(call, state)
    else:
        await call.answer("❌ Failed to delete question.", show_alert=True)

@router.callback_query(F.data.startswith("del_cust_quiz_"))
async def delete_custom_quiz_handler(call: types.CallbackQuery, state: FSMContext):
    quiz_id = call.data.replace("del_cust_quiz_", "")
    await delete_custom_quiz(quiz_id)
    await call.answer("Quiz deleted.", show_alert=True)
    await browse_custom_quizzes(call, state)