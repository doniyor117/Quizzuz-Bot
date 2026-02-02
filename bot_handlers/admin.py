from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot_services.firebase_service import get_global_stats, ban_user, unban_user, delete_user_data, get_all_users, ADMIN_IDS, get_bot_config, toggle_ai_feature, add_api_key, remove_api_key, block_user_ai, unblock_user_ai, get_public_requests, approve_public_request, reject_public_request, get_users_details, get_banned_users, search_users, get_all_sets_admin, get_set, toggle_set_privacy, delete_set
from bot_services.utils import AdminStates, get_cancel_kb, get_home_kb
from bot_services.translator import tr
from bot_services import analytics_service
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio

router = Router()

# Helper to check admin from ID
def is_admin(uid):
    return str(uid) in ADMIN_IDS

def _get_admin_panel_kb():
    """Get admin panel keyboard (shared to avoid duplication)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_broadcast"),
         InlineKeyboardButton(text="🔎 Find User", callback_data="adm_search_user")],
        [InlineKeyboardButton(text="📊 Analytics", callback_data="adm_analytics")],
        [InlineKeyboardButton(text="🔔 Public Requests", callback_data="adm_public_requests")],
        [InlineKeyboardButton(text="🚫 Ban User", callback_data="adm_ban_menu")],
        [InlineKeyboardButton(text="📚 Manage Official Content", callback_data="adm_brow_None_0")],
        [InlineKeyboardButton(text="🗂 Manage All Sets", callback_data="adm_all_sets")],
        [InlineKeyboardButton(text="🌍 Review Public Content", callback_data="adm_mod_public")],
        [InlineKeyboardButton(text="🤖 AI Settings", callback_data="adm_ai_settings")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
    ])

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id): return
    stats = await get_global_stats()
    text = f"ADMIN PANEL\nUsers: {stats['users']}\nSets: {stats['sets']}"
    await message.answer(text, reply_markup=_get_admin_panel_kb())

@router.message(AdminStates.waiting_user_search)
async def execute_user_search(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    query = message.text.strip()
    results = await search_users(query)
    
    if not results:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Search Again", callback_data="adm_search_user")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]
        ])
        await message.answer(f"❌ No users found matching '{query}'.", reply_markup=kb)
        await state.clear()
        return
    
    # Show first result
    u = results[0]
    user_id = u.get('user_id')
    
    # Get AI limits
    from bot_services.vocab_rate_limiter import get_vocab_quota_status
    from datetime import datetime
    from bot_services.firebase_service import TASHKENT_TZ
    
    # Vocabulary AI limits
    vocab_today = u.get('vocab_requests_today', 0)
    vocab_minute = u.get('vocab_requests_this_minute', 0)
    vocab_limit_day = 100    # Option A increase
    vocab_limit_minute = 12  # Option A increase
    
    # Card generation AI limits (40/day - Option A)
    card_ai_today = u.get('ai_requests_today', 0)
    card_ai_limit = 40
    
    # Practice AI Review limits (daily cards limit)
    daily_cards = u.get('daily_cards', 0)
    daily_cards_limit = 30
    
    # Check if limits reset (use current date)
    today = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
    last_reset = u.get('vocab_last_reset_date', '')
    if last_reset != today:
        vocab_today = 0  # Would be reset
    
    card_last_reset = u.get('last_daily_reset', '')
    if card_last_reset != today:
        card_ai_today = 0
        daily_cards = 0
    
    text = (
        f"👤 **User Found**\n\n"
        f"ID: `{user_id}`\n"
        f"Name: {u.get('first_name', 'N/A')}\n"
        f"Username: @{u.get('username', 'N/A')}\n"
        f"Level: {u.get('level', 1)} | XP: {u.get('total_xp', 0)}\n"
        f"TX Coins: {u.get('xp', 0)}\n\n"
        f"**📊 AI Usage Limits:**\n"
        f"🔍 Vocab Search: {vocab_today}/{vocab_limit_day} today | {vocab_minute}/{vocab_limit_minute} /min\n"
        f"🤖 Card Gen: {card_ai_today}/{card_ai_limit} today\n"
        f"📝 AI Review: {daily_cards}/{daily_cards_limit} today\n"
    )
    
    kb = []
    if len(results) > 1:
        kb.append([InlineKeyboardButton(text=f"Next ({len(results)-1} more)", callback_data=f"adm_user_next_1")])
    
    kb.append([InlineKeyboardButton(text="⚙️ Actions", callback_data=f"adm_user_actions_{user_id}")])
    kb.append([InlineKeyboardButton(text="🔄 New Search", callback_data="adm_search_user")])
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")])
    
    # Store results in state for navigation
    await state.update_data(search_results=results, current_index=0)
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    stats = await get_global_stats()
    text = f"ADMIN PANEL\nUsers: {stats['users']}\nSets: {stats['sets']}"
    await call.message.edit_text(text, reply_markup=_get_admin_panel_kb())

# --- AI SETTINGS ---
@router.callback_query(F.data == "adm_ai_settings")
async def ai_settings_menu(call: types.CallbackQuery):
    config = await get_bot_config()
    is_enabled = config.get('ai_enabled', True)
    status_icon = "✅ ON" if is_enabled else "🔴 OFF"
    
    keys_count = len(config.get('api_keys', []))
    blocked_count = len(config.get('blocked_users', []))
    
    text = (
        f"🤖 **AI Management**\n\n"
        f"Status: {status_icon}\n"
        f"API Keys: {keys_count}\n"
        f"Restricted Users: {blocked_count}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Turn {'OFF' if is_enabled else 'ON'}", callback_data=f"adm_ai_toggle_{str(not is_enabled).lower()}")],
        [InlineKeyboardButton(text="🔑 Manage Keys", callback_data="adm_ai_keys")],
        [InlineKeyboardButton(text="🚫 Restricted Users", callback_data="adm_ai_users")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

# --- PUBLIC REQUESTS ---
@router.callback_query(F.data == "adm_public_requests")
async def list_public_requests_root(call: types.CallbackQuery):
    """Handle root requests list (page 0)."""
    await list_public_requests(call, 0)

@router.callback_query(F.data.startswith("adm_req_page_"))
async def list_public_requests_paginated(call: types.CallbackQuery):
    """Handle paginated requests list."""
    page = int(call.data.replace("adm_req_page_", ""))
    await list_public_requests(call, page)

async def list_public_requests(call: types.CallbackQuery, page: int = 0):
    """List public requests with pagination."""
    if not is_admin(call.from_user.id): return
    
    # Clean up requests for deleted folders first
    from bot_services.firebase_service import clean_invalid_requests
    cleaned_count = await clean_invalid_requests()
    
    reqs = await get_public_requests()
    
    if not reqs:
        # No requests - show alert and stay on current screen
        msg = "📭 No pending requests."
        if cleaned_count > 0:
            msg += f"\n\n🧹 Removed {cleaned_count} requests for deleted folders."
        await call.answer(msg, show_alert=True)
        return

    # Pagination: 5 requests per page
    REQUESTS_PER_PAGE = 5
    total_pages = (len(reqs) - 1) // REQUESTS_PER_PAGE + 1
    page = max(0, min(page, total_pages - 1))  # Clamp page number
    
    start_idx = page * REQUESTS_PER_PAGE
    end_idx = start_idx + REQUESTS_PER_PAGE
    page_reqs = reqs[start_idx:end_idx]
    
    text = f"🌟 **Community Requests** (Page {page + 1}/{total_pages})\n\n"
    if cleaned_count > 0:
        text += f"🧹 *Removed {cleaned_count} requests for deleted folders.*\n\n"
    
    kb = []
    
    # Number requests globally (not just per page)
    for idx, r in enumerate(page_reqs, start_idx + 1):
        rid = r['request_id']
        uname = r.get('user_name', 'Unknown')
        fname = r.get('folder_name', 'Untitled')
        
        # Compact numbered display
        text += f"**{idx}.** 📂 {fname}\n   👤 {uname}\n\n"
        
        # Action buttons: Preview | Accept #{idx} | Reject
        kb.append([
            InlineKeyboardButton(text=f"👁 #{idx}", callback_data=f"adm_prev_{rid}"),
            InlineKeyboardButton(text=f"✅ #{idx}", callback_data=f"adm_app_req_{rid}"),
            InlineKeyboardButton(text=f"❌ #{idx}", callback_data=f"adm_rej_req_{rid}")
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"adm_req_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"adm_req_page_{page + 1}"))
    
    if nav_buttons:
        kb.append(nav_buttons)
    
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("adm_prev_"))
async def preview_request(call: types.CallbackQuery):
    """Preview a request's folder contents before approving/rejecting."""
    if not is_admin(call.from_user.id): return
    
    rid = call.data.replace("adm_prev_", "")
    
    # Get request details
    reqs = await get_public_requests()
    req = next((r for r in reqs if r['request_id'] == rid), None)
    
    if not req:
        await call.answer("❌ Request not found.", show_alert=True)
        return
    
    folder_id = req.get('folder_id')
    folder_name = req.get('folder_name', 'Untitled')
    user_name = req.get('user_name', 'Unknown')
    
    # Get folder contents
    from bot_services.firebase_service import get_sets_in_folder
    sets = await get_sets_in_folder(folder_id)
    
    # Build preview text - use HTML to avoid markdown escaping issues
    import html
    text = f"👁 <b>Preview Request</b>\n\n"
    text += f"📂 <b>Folder:</b> {html.escape(folder_name)}\n"
    text += f"👤 <b>Creator:</b> {html.escape(user_name)}\n"
    text += f"🎯 <b>Sets:</b> {len(sets)}\n\n"
    
    if sets:
        text += "<b>Contents:</b>\n"
        for idx, s in enumerate(sets[:10], 1):  # Show first 10 sets
            set_name = html.escape(s.get('set_name', 'Untitled'))
            card_count = s.get('card_count', 0)
            text += f"{idx}. {set_name} ({card_count} cards)\n"
        
        if len(sets) > 10:
            text += f"\n<i>...and {len(sets) - 10} more sets</i>"
    else:
        text += "<i>⚠️ Empty folder</i>"
    
    # Determine back button destination
    # Check if there are other requests besides this one
    other_requests = [r for r in reqs if r['request_id'] != rid]
    back_callback = "adm_public_requests" if other_requests else "admin_panel"
    back_text = "🔙 Back to Requests" if other_requests else "🔙 Back to Admin"
    
    # Action buttons
    kb = [
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_app_req_{rid}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_rej_req_{rid}")
        ],
        [InlineKeyboardButton(text=back_text, callback_data=back_callback)]
    ]
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_app_req_"))
async def approve_req_handler(call: types.CallbackQuery, state: FSMContext):
    rid = call.data.replace("adm_app_req_", "")
    
    # Get request details before approving
    reqs = await get_public_requests()
    req = next((r for r in reqs if r['request_id'] == rid), None)
    
    if not req:
        await call.answer("❌ Request not found.", show_alert=True)
        return
    
    success = await approve_public_request(rid)
    if success:
        await call.answer("✅ Approved! Folder is now in Community Sets.")
        
        # Store context in state BEFORE showing buttons
        user_id = req.get('user_id')
        folder_name = req.get('folder_name', 'Untitled')
        
        await state.update_data(
            pending_comment_user=user_id,
            pending_comment_folder=folder_name,
            pending_comment_action="approved"
        )
        
        # Check if more requests exist
        reqs_after = await get_public_requests()
        skip_callback = "adm_public_requests" if reqs_after else "admin_panel"
        
        kb = [
            [InlineKeyboardButton(text="💬 Send Comment to User", callback_data="adm_send_comment")],
            [InlineKeyboardButton(text="Skip", callback_data=skip_callback)]
        ]
        
        await call.message.edit_text(
            f"✅ **Approved**\n\n"
            f"📂 {folder_name} is now in Community Sets!\n\n"
            f"Send optional comment to user?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="Markdown"
        )
    else:
        await call.answer("❌ Request not found.")
        await list_public_requests(call)

@router.callback_query(F.data.startswith("adm_rej_req_"))
async def reject_req_handler(call: types.CallbackQuery, state: FSMContext):
    rid = call.data.replace("adm_rej_req_", "")
    
    # Get request details before rejecting
    reqs = await get_public_requests()
    req = next((r for r in reqs if r['request_id'] == rid), None)
    
    if not req:
        await call.answer("❌ Request not found.", show_alert=True)
        return
    
    # Reject the request (request already validated above, so just proceed)
    await reject_public_request(rid)
    await call.answer("❌ Request rejected.")
    
    # Store context in state BEFORE showing buttons
    user_id = req.get('user_id')
    folder_name = req.get('folder_name', 'Untitled')
    
    await state.update_data(
        pending_comment_user=user_id,
        pending_comment_folder=folder_name,
        pending_comment_action="rejected"
    )
    
    # Check if more requests exist
    reqs_after = await get_public_requests()
    skip_callback = "adm_public_requests" if reqs_after else "admin_panel"
    
    kb = [
        [InlineKeyboardButton(text="💬 Send Comment to User", callback_data="adm_send_comment")],
        [InlineKeyboardButton(text="Skip", callback_data=skip_callback)]
    ]
    
    await call.message.edit_text(
        f"❌ **Rejected**\n\n"
        f"📂 {folder_name} request was rejected.\n\n"
        f"Send optional comment to user?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "adm_send_comment")
async def prepare_admin_comment(call: types.CallbackQuery, state: FSMContext):
    # Get data from state (stored when approve/reject happened)
    data = await state.get_data()
    user_id = data.get('pending_comment_user')
    folder_name = data.get('pending_comment_folder', 'Unknown')
    action = data.get('pending_comment_action', 'reviewed')
    
    if not user_id:
        await call.answer("❌ Error: No pending comment", show_alert=True)
        return
    
    # Store in state for later use
    await state.update_data(
        comment_target_user=user_id,
        comment_folder_name=folder_name,
        comment_action=action
    )
    
    await state.set_state(AdminStates.waiting_admin_comment)
    await call.message.edit_text(
        f"💬 **Send Comment to User**\n\n"
        f"Re: **{folder_name}**\n\n"
        f"Type your message:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="adm_public_requests")]
        ]),
        parse_mode="Markdown"
    )

@router.message(AdminStates.waiting_admin_comment)
async def send_admin_comment(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_user_id = data.get('comment_target_user')
    folder_name = data.get('comment_folder_name', 'Your Request')
    action = data.get('comment_action', 'reviewed')
    
    if not target_user_id:
        await message.answer("❌ Error: Target user not found.")
        await state.clear()
        return
    
    # Format comment with reference header
    status_emoji = "✅" if action == "approved" else "❌" if action == "rejected" else "💬"
    header = f"{status_emoji} **Folder Submission to Official Books\nFolder name: {folder_name} **\n\n"
    full_message = header + message.text
    
    try:
        await bot.send_message(
            chat_id=int(target_user_id),
            text=full_message,
            parse_mode="Markdown"
        )
        await message.answer(
            "✅ Comment sent to user!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Requests", callback_data="adm_public_requests")]
            ])
        )
    except Exception as e:
        await message.answer(f"❌ Failed to send: {e}")
    
    await state.clear()

@router.callback_query(F.data.startswith("adm_ai_toggle_"))
async def toggle_ai(call: types.CallbackQuery):
    state_str = call.data.replace("adm_ai_toggle_", "")
    is_enabled = state_str == "true"
    await toggle_ai_feature(is_enabled)
    await ai_settings_menu(call)

# --- API KEYS ---
@router.callback_query(F.data == "adm_ai_keys")
async def manage_keys(call: types.CallbackQuery):
    config = await get_bot_config()
    keys = config.get('api_keys', [])
    
    text = "🔑 **API Keys**\n\n"
    for i, key in enumerate(keys):
        masked = key[:4] + "..." + key[-4:]
        text += f"{i+1}. `{masked}`\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Key", callback_data="adm_add_key")],
        [InlineKeyboardButton(text="➖ Remove Key", callback_data="adm_rem_key")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="adm_ai_settings")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "adm_add_key")
async def start_add_key(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_api_key)
    await call.message.edit_text("Enter new Groq API Key:", reply_markup=get_cancel_kb())

@router.message(AdminStates.waiting_api_key)
async def process_add_key(message: types.Message, state: FSMContext):
    key = message.text.strip()
    if key.startswith("gsk_"):
        await add_api_key(key)
        await message.answer("✅ Key added!")
    else:
        await message.answer("❌ Invalid key format. Must start with 'gsk_'")
    await state.clear()

@router.callback_query(F.data == "adm_rem_key")
async def start_rem_key(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_rem_key)
    await call.message.edit_text("Enter FULL API Key to remove:", reply_markup=get_cancel_kb())

@router.message(AdminStates.waiting_rem_key)
async def process_rem_key(message: types.Message, state: FSMContext):
    key = message.text.strip()
    await remove_api_key(key)
    await message.answer("✅ Key removed (if existed).")
    await state.clear()

# --- RESTRICTED USERS ---
@router.callback_query(F.data == "adm_ai_users")
async def manage_users(call: types.CallbackQuery):
    config = await get_bot_config()
    users = config.get('blocked_users', [])
    
    text = f"🚫 **Restricted Users** ({len(users)})\n\n" + ", ".join(map(str, users))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 List Restricted", callback_data="adm_list_restricted")],
        [InlineKeyboardButton(text="➕ Block User", callback_data="adm_block_user")],
        [InlineKeyboardButton(text="➖ Unblock User", callback_data="adm_unblock_user")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="adm_ai_settings")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "adm_block_user")
async def start_block_user(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_block_id)
    await call.message.edit_text("Enter User ID to block from AI:", reply_markup=get_cancel_kb())

@router.message(AdminStates.waiting_block_id)
async def process_block_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await block_user_ai(uid)
        await message.answer(f"✅ User {uid} blocked from AI.")
    except ValueError:
        await message.answer("❌ Invalid ID.")
    await state.clear()

@router.callback_query(F.data == "adm_unblock_user")
async def start_unblock_user(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_unblock_id)
    await call.message.edit_text("Enter User ID to unblock:", reply_markup=get_cancel_kb())

@router.message(AdminStates.waiting_unblock_id)
async def process_unblock_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await unblock_user_ai(uid)
        await message.answer(f"✅ User {uid} unblocked.")
    except:
        await message.answer("❌ Invalid ID.")
    await state.clear()

# --- BROADCAST HANDLERS ---
@router.callback_query(F.data == "adm_broadcast")
async def start_broadcast(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    
    # Force English for Admin Tools
    lang = 'en'
    
    instructions = (
        "📢 **Broadcast Message**\n\n"
        "Send a personalized message to all users.\n\n"
        "**Available Variables:**\n"
        "• `{user_first_name}` - User's first name\n"
        "• `{level}` - User's level\n"
        "• `{streak}` - User's streak\n"
        "• `{xp}` - User's TX coins\n\n"
        "**Example:**\n"
        "`Assalomu alaykum {user_first_name}! 👋`\n"
        "`You're level {level} with a {streak}-day streak!`\n\n"
        "Type your message below:"
    )
    
    await state.set_state(AdminStates.waiting_broadcast_msg)
    await call.message.edit_text(instructions, reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")

@router.message(AdminStates.waiting_broadcast_msg)
async def process_broadcast(message: types.Message, state: FSMContext, bot: Bot):
    # Force English for Admin Reports
    lang = 'en'
    
    # Store the message template
    message_template = message.text or message.caption or ""
    
    # 1. Get all users
    users = await get_all_users()
    total = len(users)
    
    # Check if template has variables
    has_variables = any(var in message_template for var in ['{user_first_name}', '{level}', '{streak}', '{xp}'])
    
    # Show preview if using variables
    if has_variables and users:
        preview_user = users[0]
        preview_msg = message_template.format(
            user_first_name=preview_user.get('first_name', 'User'),
            level=preview_user.get('level', 1),
            streak=preview_user.get('streak', 0),
            xp=round(preview_user.get('xp', 0), 1)
        )
        
        preview_text = (
            f"📋 **Preview** (for first user):\n\n"
            f"{preview_msg}\n\n"
            f"─────────────\n"
            f"📊 Will send to **{total} users**"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm Send", callback_data="adm_broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_panel")]
        ])
        
        # Store template in state
        await state.update_data(broadcast_template=message_template)
        await message.answer(preview_text, reply_markup=kb, parse_mode="Markdown")
        return
    
    # If no variables or legacy mode, send directly
    status_msg = await message.answer(f"📤 Sending to {total} users...")
    
    success = 0
    failed = 0
    blocked = 0
    
    # 2. Loop and Send
    for u in users:
        try:
            user_id = u['user_id']
            
            # Personalize message if it has variables
            if has_variables:
                personalized_text = message_template.format(
                    user_first_name=u.get('first_name', 'User'),
                    level=u.get('level', 1),
                    streak=u.get('streak', 0),
                    xp=round(u.get('xp', 0), 1)
                )
                await bot.send_message(chat_id=int(user_id), text=personalized_text, parse_mode="Markdown")
            else:
                # copy_to handles Text, Photo, Video, Voice, etc. automatically
                await message.copy_to(chat_id=user_id)
            
            success += 1
            await asyncio.sleep(0.05) # Anti-flood limit
        except Exception as e:
            if "blocked" in str(e).lower():
                blocked += 1
            else:
                failed += 1
            
    # 3. Report
    report = (
        f"✅ **Broadcast Complete**\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"🚫 Blocked: {blocked}\n"
        f"📊 Total: {total}"
    )
    await status_msg.edit_text(report, reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")
    await state.clear()

@router.callback_query(F.data == "adm_broadcast_confirm")
async def confirm_broadcast(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Execute the broadcast after confirmation."""
    data = await state.get_data()
    message_template = data.get('broadcast_template', '')
    
    if not message_template:
        await call.answer("❌ Message template not found", show_alert=True)
        return
    
    # Get all users
    users = await get_all_users()
    total = len(users)
    
    await call.message.edit_text(f"📤 Sending to {total} users...", parse_mode="Markdown")
    
    success = 0
    failed = 0
    blocked = 0
    
    # Send to all users
    for u in users:
        try:
            user_id = u['user_id']
            
            # Personalize message
            personalized_text = message_template.format(
                user_first_name=u.get('first_name', 'User'),
                level=u.get('level', 1),
                streak=u.get('streak', 0),
                xp=round(u.get('xp', 0), 1)
            )
            
            await bot.send_message(chat_id=int(user_id), text=personalized_text, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            if "blocked" in str(e).lower():
                blocked += 1
            else:
                failed += 1
    
    # Report
    lang = 'en'
    report = (
        f"✅ **Broadcast Complete**\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"🚫 Blocked: {blocked}\n"
        f"📊 Total: {total}"
    )
    await call.message.edit_text(report, reply_markup=get_home_kb(tr.languages[lang]), parse_mode="Markdown")
    await state.clear()

# --- OTHER ADMIN COMMANDS ---
@router.message(Command("ban"))
async def ban_cmd(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        target_id = int(message.text.split()[1])
        await ban_user(target_id)
        await message.answer(f"User {target_id} banned.")
    except:
        await message.answer("Usage: /ban user_id")

@router.message(Command("wipe"))
async def wipe_cmd(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        target_id = int(message.text.split()[1])
        await delete_user_data(target_id)
        await message.answer(f"User {target_id} WIPED.")
    except:
        await message.answer("Usage: /wipe user_id")

# --- BAN MANAGEMENT ---
@router.callback_query(F.data == "adm_ban_menu")
async def ban_menu(call: types.CallbackQuery):
    text = "🚫 **Ban Management**\n\nUse this to completely ban users from the bot."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 List Banned Users", callback_data="adm_list_banned")],
        [InlineKeyboardButton(text="➕ Ban User by ID", callback_data="adm_ban_user")],
        [InlineKeyboardButton(text="➖ Unban User by ID", callback_data="adm_unban_user")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "adm_ban_user")
async def start_ban_user(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_ban_id)
    await call.message.edit_text("Enter User ID to BAN:", reply_markup=get_cancel_kb())

@router.message(AdminStates.waiting_ban_id)
async def process_ban_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        if str(uid) in ADMIN_IDS:
            await message.answer("❌ Cannot ban an admin.")
        else:
            await ban_user(uid)
            await message.answer(f"✅ User {uid} has been BANNED.")
    except ValueError:
        await message.answer("❌ Invalid ID.")
    await state.clear()

@router.callback_query(F.data == "adm_unban_user")
async def start_unban_user(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_unban_id)
    await call.message.edit_text("Enter User ID to UNBAN:", reply_markup=get_cancel_kb())

@router.message(AdminStates.waiting_unban_id)
async def process_unban_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await unban_user(uid)
        await message.answer(f"✅ User {uid} has been UNBANNED.")
    except ValueError:
        await message.answer("❌ Invalid ID.")
    await state.clear()

# --- LIST HANDLERS ---
@router.callback_query(F.data == "adm_list_restricted")
async def list_restricted_handler(call: types.CallbackQuery):
    config = await get_bot_config()
    uids = config.get('blocked_users', [])
    if not uids:
        await call.answer("No restricted users.", show_alert=True)
        return
    
    details = await get_users_details(uids)
    text = f"🚫 **Restricted Users ({len(details)})**\n\n"
    for u in details:
        text += f"👤 {u['first_name']} (`{u['user_id']}`)\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="adm_ai_users")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "adm_list_banned")
async def list_banned_handler(call: types.CallbackQuery):
    users = await get_banned_users()
    if not users:
        await call.answer("No banned users.", show_alert=True)
        return
        
    text = f"🚫 **Banned Users ({len(users)})**\n\n"
    for u in users:
        text += f"👤 {u['first_name']} (`{u['user_id']}`)\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="adm_ban_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

# --- USER SEARCH ---
@router.callback_query(F.data == "adm_search_user")
async def start_user_search(call: types.CallbackQuery, state: FSMContext):
    """Start user search flow."""
    if not is_admin(call.from_user.id): return
    
    await state.set_state(AdminStates.waiting_user_search)
    await call.message.edit_text(
        "🔎 **Find User**\n\n"
        "Enter user's name, username, or ID:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]
        ]),
        parse_mode="Markdown"
    )

@router.message(AdminStates.waiting_user_search)
async def process_user_search(message: types.Message, state: FSMContext):
    """Process user search query and display results."""
    query = message.text.strip()
    
    if not query:
        await message.answer("❌ Please enter a search query.")
        return
    
    # Search users
    results = await search_users(query)
    
    if not results:
        await message.answer(
            f"🔍 No users found for '{query}'.\n\nTry searching by:"
            f"\n• First name\n• Username\n• User ID",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Search Again", callback_data="adm_search_user")],
                [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")]
            ])
        )
        await state.clear()
        return
    
    # Display results
    from bot_services.utils import get_rank_title
    text = f"🔍 **Found {len(results)} user(s)**\n\n"
    kb = []
    
    for user in results:
        user_id = user.get('user_id', 'Unknown')
        name = user.get('first_name', 'Unknown')
        username = user.get('username', '')
        level = user.get('level', 1)
        total_xp = user.get('total_xp', 0)
        streak = user.get('streak', 0)
        rank = get_rank_title(total_xp)
        
        # User info line
        username_str = f"@{username}" if username else "No username"
        text += f"👤 **{name}** ({username_str})\n"
        text += f"   ID: `{user_id}`\n"
        text += f"   Level {level} • {rank} • {total_xp:.0f} XP • 🔥 {streak}\n\n"
        
        # Action buttons for this user
        kb.append([
            InlineKeyboardButton(text=f"📊 Stats - {name[:10]}", callback_data=f"usr_stats_{user_id}"),
            InlineKeyboardButton(text=f"🚫 Ban - {name[:10]}", callback_data=f"usr_ban_{user_id}")
        ])
    
    # Navigation buttons
    kb.append([InlineKeyboardButton(text="🔄 New Search", callback_data="adm_search_user")])
    kb.append([InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await state.clear()

# --- ALL SETS MANAGEMENT ---
@router.callback_query(F.data == "adm_all_sets")
async def list_all_sets_root(call: types.CallbackQuery):
    """Handle root sets list (page 0)."""
    await list_all_sets(call, 0)

@router.callback_query(F.data.startswith("adm_sets_page_"))
async def list_all_sets_paginated(call: types.CallbackQuery):
    """Handle paginated sets list."""
    page = int(call.data.replace("adm_sets_page_", ""))
    await list_all_sets(call, page)

async def list_all_sets(call: types.CallbackQuery, page: int = 0):
    """List all sets with pagination."""
    if not is_admin(call.from_user.id): return
    
    SETS_PER_PAGE = 10
    offset = page * SETS_PER_PAGE
    
    # Fetch sets (limit + 1 to check if next page exists)
    sets = await get_all_sets_admin(limit=SETS_PER_PAGE + 1, offset=offset)
    
    has_next = len(sets) > SETS_PER_PAGE
    display_sets = sets[:SETS_PER_PAGE]
    
    if not display_sets and page == 0:
        await call.answer("📭 No sets found.", show_alert=True)
        return
    
    text = f"🗂 **All Sets Management** (Page {page + 1})\n\n"
    kb = []
    
    for s in display_sets:
        sid = s['set_id']
        name = s.get('set_name', 'Untitled')
        count = s.get('card_count', 0)
        is_public = s.get('is_public', False)
        status = "🌍" if is_public else "🔒"
        
        # Button: "🌍 Set Name (10)"
        kb.append([InlineKeyboardButton(text=f"{status} {name} ({count})", callback_data=f"adm_view_set_{sid}")])
    
    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"adm_sets_page_{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"adm_sets_page_{page + 1}"))
    
    if nav:
        kb.append(nav)
    
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("adm_view_set_"))
async def view_set_details(call: types.CallbackQuery):
    """View details of a specific set."""
    if not is_admin(call.from_user.id): return
    
    sid = call.data.replace("adm_view_set_", "")
    s = await get_set(sid)
    
    if not s:
        await call.answer("❌ Set not found.", show_alert=True)
        await list_all_sets(call, 0)
        return
    
    name = s.get('set_name', 'Untitled')
    count = s.get('card_count', 0)
    is_public = s.get('is_public', False)
    owner_id = s.get('owner_id', 'Unknown')
    created_at = s.get('created_at')
    
    # Get owner name
    from bot_services.firebase_service import get_user
    owner = await get_user(owner_id)
    owner_name = owner.get('first_name', 'Unknown') if owner else "Unknown"
    
    status_text = "🌍 Public" if is_public else "🔒 Private"
    
    text = (
        f"🗂 **Set Details**\n\n"
        f"📝 **Name:** {name}\n"
        f"🃏 **Cards:** {count}\n"
        f"👤 **Owner:** {owner_name} (`{owner_id}`)\n"
        f"👁 **Status:** {status_text}\n"
    )
    
    kb = []
    
    # Toggle Public/Private
    toggle_text = "🔒 Make Private" if is_public else "🌍 Make Public"
    kb.append([InlineKeyboardButton(text=toggle_text, callback_data=f"adm_pub_set_{sid}_{str(not is_public).lower()}")])
    
    # Delete
    kb.append([InlineKeyboardButton(text="🗑 Delete Set", callback_data=f"adm_del_set_{sid}")])
    
    # Back
    kb.append([InlineKeyboardButton(text="🔙 Back to List", callback_data="adm_all_sets")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data.startswith("adm_pub_set_"))
async def toggle_set_public(call: types.CallbackQuery):
    """Toggle set public/private status."""
    if not is_admin(call.from_user.id): return
    
    parts = call.data.split("_")
    # adm_pub_set_{sid}_{state}
    # parts: 0=adm, 1=pub, 2=set, 3=sid, 4=state
    
    # Handle potential underscores in ID? No, ID is usually safe.
    # But let's be careful. simpler to split by prefix.
    data = call.data.replace("adm_pub_set_", "")
    # data = "sid_true"
    sid, state_str = data.rsplit("_", 1)
    is_public = state_str == "true"
    
    await toggle_set_privacy(sid, is_public)
    
    status = "Public" if is_public else "Private"
    await call.answer(f"✅ Set is now {status}!")
    
    # Refresh view
    # We need to manually construct the callback data to call view_set_details
    # Or just call it directly if we mock the call object, but easier to just re-render
    # Let's just re-call view_set_details with the ID
    call.data = f"adm_view_set_{sid}"
    await view_set_details(call)

@router.callback_query(F.data.startswith("adm_del_set_"))
async def delete_set_confirm(call: types.CallbackQuery):
    """Ask for confirmation before deleting."""
    sid = call.data.replace("adm_del_set_", "")
    
    kb = [
        [InlineKeyboardButton(text="🗑 YES, DELETE", callback_data=f"adm_del_conf_{sid}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"adm_view_set_{sid}")]
    ]
    
    await call.message.edit_text(
        "⚠️ **Are you sure you want to delete this set?**\n\nThis action cannot be undone.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("adm_del_conf_"))
async def delete_set_execute(call: types.CallbackQuery):
    """Execute deletion."""
    sid = call.data.replace("adm_del_conf_", "")
    
    await delete_set(sid)
    await call.answer("✅ Set deleted.")
    await list_all_sets(call, 0)

@router.callback_query(F.data.startswith("usr_stats_"))
async def show_user_stats(call: types.CallbackQuery):
    """Show detailed user statistics."""
    if not is_admin(call.from_user.id): return
    
    user_id = call.data.replace("usr_stats_", "")
    
    from bot_services.firebase_service import get_user
    from bot_services.utils import get_rank_title
    
    user = await get_user(int(user_id))
    
    if not user:
        await call.answer("❌ User not found.", show_alert=True)
        return
    
    # Build detailed stats
    name = user.get('first_name', 'Unknown')
    username = user.get('username', 'N/A')
    level = user.get('level', 1)
    total_xp = user.get('total_xp', 0)
    tx_coins = user.get('xp', 0)
    streak = user.get('streak', 0)
    daily_cards = user.get('daily_cards', 0)
    rank = get_rank_title(total_xp)
    lang = user.get('lang_code', 'en')
    
    # AI Usage Limits
    from datetime import datetime
    from bot_services.firebase_service import TASHKENT_TZ
    
    vocab_today = user.get('vocab_requests_today', 0)
    vocab_minute = user.get('vocab_requests_this_minute', 0)
    card_ai_today = user.get('ai_requests_today', 0)
    
    # Check if limits reset today
    today = datetime.now(TASHKENT_TZ).strftime('%Y-%m-%d')
    last_reset = user.get('vocab_last_reset_date', '')
    if last_reset != today:
        vocab_today = 0
    
    card_last_reset = user.get('last_daily_reset', '')
    if card_last_reset != today:
        card_ai_today = 0
        daily_cards = 0
    
    text = (
        f"📊 **User Statistics**\n\n"
        f"👤 **Name:** {name}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"👤 **Username:** @{username}\n"
        f"🌍 **Language:** {lang.upper()}\n\n"
        f"📈 **Level:** {level}\n"
        f"🏆 **Rank:** {rank}\n"
        f"⭐ **Total XP:** {total_xp:.0f}\n"
        f"💰 **TX Coins:** {tx_coins:.1f}\n"
        f"🔥 **Streak:** {streak} days\n\n"
        f"**🤖 AI Usage Limits:**\n"
        f"🔍 Vocab Search: {vocab_today}/100 today | {vocab_minute}/12 per min\n"
        f"🃏 Card Generation: {card_ai_today}/40 today\n"
        f"📝 AI Review: {daily_cards}/30 today\n"
        f"📝 **Today's Cards:** {daily_cards}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="adm_search_user")],
        [InlineKeyboardButton(text="🏠 Admin Panel", callback_data="admin_panel")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("usr_ban_"))
async def quick_ban_user(call: types.CallbackQuery, state: FSMContext):
    """Quick ban user from search results."""
    if not is_admin(call.from_user.id): return
    
    user_id = call.data.replace("usr_ban_", "")
    
    # Check if trying to ban admin
    if str(user_id) in ADMIN_IDS:
        await call.answer("❌ Cannot ban an admin.", show_alert=True)
        return
    
    # Ban the user
    await ban_user(int(user_id))
    
    await call.answer(f"✅ User {user_id} has been banned.", show_alert=True)
    await call.message.edit_text(
        f"✅ **User Banned**\n\nUser ID `{user_id}` has been banned from the bot.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Search Again", callback_data="adm_search_user")],
            [InlineKeyboardButton(text="🏠 Admin Panel", callback_data="admin_panel")]
        ]),
        parse_mode="Markdown"
    )

# ============================================
# ANALYTICS DASHBOARD
# ============================================

@router.callback_query(F.data == "adm_analytics")
async def analytics_dashboard(call: types.CallbackQuery):
    """Main analytics dashboard with options."""
    if not is_admin(call.from_user.id):
        return
    
    text = (
        "📊 **Analytics Dashboard**\n\n"
        "View bot usage statistics, user engagement, and feature adoption metrics."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Today's Stats", callback_data="adm_analytics_today")],
        [InlineKeyboardButton(text="📅 7-Day Trends", callback_data="adm_analytics_week")],
        [InlineKeyboardButton(text="🏆 All-Time Stats", callback_data="adm_analytics_alltime")],
        [InlineKeyboardButton(text="🤖 AI Usage", callback_data="adm_analytics_ai")],
        [InlineKeyboardButton(text="🔥 Feature Usage", callback_data="adm_analytics_features")],
        [InlineKeyboardButton(text="⚡ Command Usage", callback_data="adm_analytics_commands")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "adm_analytics_today")
async def show_today_stats(call: types.CallbackQuery):
    """Show today's analytics."""
    if not is_admin(call.from_user.id):
        return
    
    await call.answer("📊 Loading today's stats...")
    
    from datetime import datetime, timezone
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Get daily stats
    stats = await analytics_service.get_daily_stats(today_str)
    
    dau = stats.get('dau', 0)
    new_users = stats.get('new_users', 0)
    cards_added = stats.get('total_cards_added', 0)
    cards_practiced = stats.get('total_cards_practiced', 0)
    vocab_lookups = stats.get('total_vocab_lookups', 0)
    
    # Top commands
    commands = stats.get('commands', {})
    top_commands = sorted(commands.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Top features
    features = stats.get('features', {})
    top_features = sorted(features.items(), key=lambda x: x[1], reverse=True)[:5]
    
    text = f"📊 **Today's Analytics** ({today_str})\n\n"
    text += f"👥 **Users**\n"
    text += f"• DAU: {dau}\n"
    text += f"• New Users: {new_users}\n\n"
    
    text += f"📚 **Activity**\n"
    text += f"• Cards Added: {cards_added}\n"
    text += f"• Cards Practiced: {cards_practiced}\n"
    text += f"• Vocab Lookups: {vocab_lookups}\n\n"
    
    if top_commands:
        text += f"🎯 **Top Commands**\n"
        for cmd, count in top_commands:
            text += f"• /{cmd}: {count}\n"
        text += "\n"
    
    if top_features:
        text += f"🔥 **Active Features**\n"
        for feat, count in top_features:
            text += f"• {feat}: {count}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="adm_analytics_today")],
        [InlineKeyboardButton(text="🔙 Back to Analytics", callback_data="adm_analytics")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "adm_analytics_ai")
async def show_ai_usage(call: types.CallbackQuery):
    """Show AI usage analytics."""
    if not is_admin(call.from_user.id):
        return
    
    await call.answer("🤖 Loading AI stats...")
    
    from datetime import datetime, timezone, timedelta
    from bot_services.firebase_service import get_ai_stats, get_ai_stats_range
    
    # Get today's stats
    today_stats = await get_ai_stats()
    today_requests = today_stats.get('total_requests', 0)
    today_tokens = today_stats.get('total_tokens', 0)
    features = today_stats.get('features', {})
    
    card_gen = features.get('card_generation', 0)
    vocab_lookup = features.get('vocab_lookup', 0)
    
    # Get 7-day stats
    weekly = await get_ai_stats_range(7)
    week_requests = sum(d.get('total_requests', 0) for d in weekly)
    week_tokens = sum(d.get('total_tokens', 0) for d in weekly)
    
    # Rate limits (from Groq Developer Plan)
    DAILY_LIMIT = 14400  # Groq API: 14,400 RPD (requests per day)
    
    text = "🤖 **AI Usage Analytics**\n\n"
    
    text += "📅 **Today**\n"
    text += f"• Total Requests: **{today_requests}** / {DAILY_LIMIT}\n"
    text += f"• Est. Tokens: ~{today_tokens:,}\n"
    text += f"• Card Generation: {card_gen}\n"
    text += f"• Vocab Lookups: {vocab_lookup}\n\n"
    
    # Usage bar
    pct = min((today_requests / DAILY_LIMIT) * 100, 100) if DAILY_LIMIT > 0 else 0
    bar_filled = int(pct / 10)
    bar = '█' * bar_filled + '░' * (10 - bar_filled)
    text += f"Usage: [{bar}] {pct:.1f}%\n\n"
    
    text += "📊 **Last 7 Days**\n"
    text += f"• Total Requests: {week_requests:,}\n"
    text += f"• Est. Tokens: ~{week_tokens:,}\n\n"
    
    # Daily breakdown
    text += "📈 **Daily Breakdown**\n"
    for day in weekly[:5]:  # Last 5 days
        date = day.get('date', '?')
        reqs = day.get('total_requests', 0)
        text += f"• {date}: {reqs} requests\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="adm_analytics_ai")],
        [InlineKeyboardButton(text="🔙 Back to Analytics", callback_data="adm_analytics")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "adm_analytics_week")
async def show_weekly_trends(call: types.CallbackQuery):
    """Show 7-day trends."""
    if not is_admin(call.from_user.id):
        return
    
    await call.answer("📈 Loading 7-day trends...")
    
    # Get weekly stats
    stats = await analytics_service.get_weekly_stats()
    
    daily = stats.get('daily_breakdown', [])
    avg_dau = stats.get('avg_dau', 0)
    total_new = stats.get('total_new_users', 0)
    
    # Calculate retention
    retention = await analytics_service.get_user_retention(7)
    
    text = f"📈 **7-Day Trends**\n\n"
    text += f"📊 **Overview**\n"
    text += f"• Avg DAU: {avg_dau:.1f}\n"
    text += f"• New Users: {total_new}\n"
    text += f"• D7 Retention: {retention}%\n\n"
    
    text += f"📅 **Daily Breakdown** (Last 7 days)\n"
    
    # Show daily stats (most recent first)
    for day_stats in daily[:7]:
        date = day_stats.get('date', 'N/A')
        dau = day_stats.get('dau', 0)
        new = day_stats.get('new_users', 0)
        cards = day_stats.get('total_cards_added', 0)
        
        # Create simple bar graph
        bar = "█" * min(int(dau / 10), 10)
        text += f"\n{date[-5:]}: {bar} {dau} users"
        if new > 0:
            text += f" (+{new} new)"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="adm_analytics_week")],
        [InlineKeyboardButton(text="🔙 Back to Analytics", callback_data="adm_analytics")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "adm_analytics_alltime")
async def show_alltime_stats(call: types.CallbackQuery):
    """Show all-time statistics."""
    if not is_admin(call.from_user.id):
        return
    
    await call.answer("🏆 Loading all-time stats...")
    
    try:
        from bot_services.firebase_service import db
        
        # Get total users
        users_ref = db.collection('users')
        total_users = len(list(users_ref.stream()))
        
        # Get total cards
        cards_ref = db.collection('cards')
        total_cards = len(list(cards_ref.stream()))
        
        # Get total sets
        sets_ref = db.collection('sets')
        total_sets = len(list(sets_ref.stream()))
        
        # Get total folders
        folders_ref = db.collection('folders')
        total_folders = len(list(folders_ref.stream()))
        
        # Get game stats
        game_scores_ref = db.collection('game_scores')
        game_scores = list(game_scores_ref.stream())
        total_games = len(game_scores)
        total_game_score = sum(doc.to_dict().get('score', 0) for doc in game_scores)
        
        # Get all-time feature usage
        all_time_features = await analytics_service.get_feature_usage(days=365)
        
        text = "🏆 **All-Time Statistics**\n\n"
        
        text += "👥 **Users**\n"
        text += f"• Total Registered: {total_users:,}\n\n"
        
        text += "📚 **Content**\n"
        text += f"• Total Cards: {total_cards:,}\n"
        text += f"• Total Sets: {total_sets:,}\n"
        text += f"• Total Folders: {total_folders:,}\n\n"
        
        text += "🎮 **Word Scramble**\n"
        text += f"• Games Played: {total_games:,}\n"
        text += f"• Total Score: {total_game_score:,}\n\n"
        
        text += "🔥 **Top Features (All-Time)**\n"
        for feature, count in list(all_time_features.items())[:5]:
            text += f"• {feature}: {count:,}\n"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="adm_analytics_alltime")],
            [InlineKeyboardButton(text="🔙 Back to Analytics", callback_data="adm_analytics")]
        ])
        
        await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        await call.message.edit_text(
            f"❌ Error loading stats: {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="adm_analytics")]
            ])
        )


@router.callback_query(F.data == "adm_analytics_features")
async def show_feature_usage(call: types.CallbackQuery):
    """Show feature usage statistics."""
    if not is_admin(call.from_user.id):
        return
    
    await call.answer("🔥 Loading feature usage...")
    
    # Get feature usage for last 7 days
    features = await analytics_service.get_feature_usage(days=7)
    
    if not features:
        text = "📊 **Feature Usage (Last 7 days)**\n\n_No feature usage data yet._"
    else:
        sorted_features = sorted(features.items(), key=lambda x: x[1], reverse=True)
        total = sum(features.values())
        
        text = f"🔥 **Feature Usage** (Last 7 days)\n\n"
        text += f"Total Uses: {total}\n\n"
        
        for feat, count in sorted_features[:15]:
            percentage = (count / total * 100) if total > 0 else 0
            bar = "█" * min(int(percentage / 5), 10)
            text += f"{bar} **{feat}**: {count} ({percentage:.1f}%)\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="adm_analytics_features")],
        [InlineKeyboardButton(text="🔙 Back to Analytics", callback_data="adm_analytics")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "adm_analytics_commands")
async def show_command_usage(call: types.CallbackQuery):
    """Show command usage statistics."""
    if not is_admin(call.from_user.id):
        return
    
    await call.answer("⚡ Loading command usage...")
    
    # Get command usage for last 7 days
    commands = await analytics_service.get_command_usage(days=7)
    
    if not commands:
        text = "📊 **Command Usage (Last 7 days)**\n\n_No command usage data yet._"
    else:
        sorted_commands = sorted(commands.items(), key=lambda x: x[1], reverse=True)
        total = sum(commands.values())
        
        text = f"⚡ **Command Usage** (Last 7 days)\n\n"
        text += f"Total Commands: {total}\n\n"
        
        for cmd, count in sorted_commands[:15]:
            percentage = (count / total * 100) if total > 0 else 0
            bar = "█" * min(int(percentage / 5), 10)
            text += f"{bar} **/{cmd}**: {count} ({percentage:.1f}%)\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="adm_analytics_commands")],
        [InlineKeyboardButton(text="🔙 Back to Analytics", callback_data="adm_analytics")]
    ])
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except TelegramBadRequest:
        await call.answer("Data is already up to date", show_alert=False)

