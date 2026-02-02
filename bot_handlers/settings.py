from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import get_user, db
from bot_services.translator import tr

router = Router()

@router.callback_query(F.data == "menu_settings")
async def show_settings(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    # Use safe default if lang_code missing
    lang = user.get('lang_code', 'en')
    
    kb = [
        [InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="set_lang_uz"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")] # Replaced Back with Home
    ]
    await call.message.edit_text(tr.get_text('settings_lang', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("set_lang_"))
async def change_lang(call: types.CallbackQuery):
    lang = call.data.replace("set_lang_", "")
    db.collection('users').document(str(call.from_user.id)).update({"lang_code": lang})
    
    user = await get_user(call.from_user.id)
    is_admin = user.get('is_admin', False)
    
    await call.message.delete()
    from bot_services.utils import get_main_menu_kb
    # Send welcome in new lang with main menu
    await call.message.answer(tr.get_text('welcome', lang), reply_markup=get_main_menu_kb(tr.languages[lang], is_admin=is_admin))