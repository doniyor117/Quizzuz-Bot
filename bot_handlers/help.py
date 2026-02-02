from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import get_user
from bot_services.translator import tr

router = Router()

@router.message(Command("help", "info"))
async def cmd_help(message: types.Message):
    user = await get_user(message.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    
    await show_help_menu(message, lang)

async def show_help_menu(message, lang, is_edit=False):
    text = tr.get_text('help_title', lang)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr.get_text('help_btn_practice', lang), callback_data="help_practice"),
         InlineKeyboardButton(text=tr.get_text('help_btn_ai', lang), callback_data="help_ai")],
        [InlineKeyboardButton(text=tr.get_text('help_btn_game', lang), callback_data="help_game"),
         InlineKeyboardButton(text=tr.get_text('help_btn_progress', lang), callback_data="help_progress")],
        [InlineKeyboardButton(text=tr.get_text('help_btn_library', lang), callback_data="help_library"),
         InlineKeyboardButton(text=tr.get_text('help_btn_faq', lang), callback_data="help_faq")],
        [InlineKeyboardButton(text=tr.get_text('help_btn_close', lang), callback_data="cancel")]
    ])
    
    if is_edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "help_menu")
async def back_to_help_menu(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    await show_help_menu(call.message, lang, is_edit=True)

@router.callback_query(F.data == "help_practice")
async def help_practice(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    
    text = tr.get_text('help_practice_text', lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr.get_text('help_btn_back', lang), callback_data="help_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "help_ai")
async def help_ai(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    
    text = tr.get_text('help_ai_text', lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr.get_text('help_btn_back', lang), callback_data="help_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "help_game")
async def help_game(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    
    text = tr.get_text('help_game_text', lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr.get_text('help_btn_back', lang), callback_data="help_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "help_progress")
async def help_progress(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    
    text = tr.get_text('help_progress_text', lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr.get_text('help_btn_back', lang), callback_data="help_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "help_library")
async def help_library(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    
    text = tr.get_text('help_library_text', lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr.get_text('help_btn_back', lang), callback_data="help_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "help_faq")
async def help_faq(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.get('lang_code', 'en') if user else 'en'
    
    text = tr.get_text('help_faq_text', lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr.get_text('help_btn_back', lang), callback_data="help_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
