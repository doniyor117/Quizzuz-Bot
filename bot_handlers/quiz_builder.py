from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.utils import QuizBuilderStates, get_cancel_kb
from bot_services.firebase_service import add_custom_quiz, get_user
from bot_services.translator import tr

router = Router()

# Wizard Data Structure for FSM:
# {
#   'title': 'My Quiz',
#   'questions': [
#       {'text': 'Q1', 'options': ['A','B'], 'correct_index': 0}
#   ]
# }

@router.callback_query(F.data == "build_quiz_start")
async def start_quiz_creation(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await state.set_state(QuizBuilderStates.waiting_title)
    
    await call.message.edit_text(
        "🛠 **Quiz Builder Wizard**\n\n"
        "Let's create a custom quiz!\n"
        "First, **send me a name** for your quiz.",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.message(QuizBuilderStates.waiting_title)
async def handle_quiz_title(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if len(title) > 50:
        await message.reply("⚠️ Title is too long. Keep it under 50 chars.")
        return
        
    await state.update_data(title=title, questions=[])
    
    await state.set_state(QuizBuilderStates.waiting_question)
    await message.answer(
        f"✅ Quiz Name: **{title}**\n\n"
        "Now, send me **Question #1**.\n"
        "_(e.g. 'What is the capital of Uzbekistan?')_",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.message(QuizBuilderStates.waiting_question)
async def handle_question_text(message: types.Message, state: FSMContext):
    q_text = message.text.strip()
    await state.update_data(current_question=q_text)
    
    await state.set_state(QuizBuilderStates.waiting_options)
    await message.answer(
        f"❓ **Question:** {q_text}\n\n"
        "Now, send me the **Options** (Answers).\n"
        "⚠️ **Rules:**\n"
        "1. Send each option on a **new line**.\n"
        "2. The **FIRST** line must be the **CORRECT** answer.\n"
        "3. Provide at least 2 options.\n\n"
        "Example:\n"
        "Tashkent\n"
        "Samarkand\n"
        "Bukhara",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.message(QuizBuilderStates.waiting_options)
async def handle_options(message: types.Message, state: FSMContext):
    lines = [l.strip() for l in message.text.split('\n') if l.strip()]
    
    if len(lines) < 2:
        await message.reply("⚠️ Please provide at least 2 options (lines).")
        return
        
    if len(lines) > 10:
        await message.reply("⚠️ Maximum 10 options allowed per question.")
        return
        
    data = await state.get_data()
    questions = data.get('questions', [])
    current_q_text = data.get('current_question')
    
    # Logic: First option is correct (index 0)
    # We will shuffle them during Play Mode, but store them as is here?
    # Actually, storing them as is (0=correct) is standard.
    # We will trust the user followed the "First is correct" rule.
    
    new_q = {
        'text': current_q_text,
        'options': lines,
        'correct_index': 0 
    }
    
    questions.append(new_q)
    await state.update_data(questions=questions)
    
    # Ask: Add another or Finish (with timer selection)?
    kb = [
        [InlineKeyboardButton(text="➕ Add Another Question", callback_data="add_another_q")],
        [InlineKeyboardButton(text="🔚 Finish & Set Timer", callback_data="select_timer")],
        [InlineKeyboardButton(text="❌ Cancel Quiz", callback_data="cancel")]
    ]
    
    await message.answer(
        f"✅ Question #{len(questions)} saved!\n\n"
        "What's next?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@router.callback_query(F.data == "select_timer")
async def select_timer(call: types.CallbackQuery, state: FSMContext):
    """Let user choose quiz timer duration."""
    kb = [
        [InlineKeyboardButton(text="⚡ 10 sec (Blitz)", callback_data="timer_10")],
        [InlineKeyboardButton(text="⏱️ 30 sec (Standard)", callback_data="timer_30")],
        [InlineKeyboardButton(text="🐢 60 sec (Relaxed)", callback_data="timer_60")],
    ]
    await call.message.edit_text(
        "⏱️ **Select Quiz Timer**\n\n"
        "How long should players have per question?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("timer_"))
async def handle_timer_selection(call: types.CallbackQuery, state: FSMContext):
    timer = int(call.data.replace("timer_", ""))
    
    # Get quiz data and save
    data = await state.get_data()
    user_id = call.from_user.id
    title = data['title']
    questions = data['questions']
    
    if not questions:
        await call.answer("Empty quiz!", show_alert=True)
        return

    # Save to DB with timer
    quiz_id = await add_custom_quiz(user_id, title, questions, timer)
    bot = call.bot
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    share_link = f"https://t.me/{bot_username}?start=quiz_{quiz_id}"
    timer_text = {10: "⚡ 10s", 30: "⏱️ 30s", 60: "🐢 60s"}.get(timer, "30s")
    
    await call.message.edit_text(
        f"🎉 **Quiz Created Successfully!**\n\n"
        f"📝 **Title:** {title}\n"
        f"❓ **Questions:** {len(questions)}\n"
        f"⏱️ **Timer:** {timer_text}\n\n"
        f"🔗 **Share Link:**\n`{share_link}`",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share", url=f"https://t.me/share/url?url={share_link}&text=Challenge me in this quiz!")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
        ]),
        parse_mode="Markdown"
    )
    await state.clear()

@router.callback_query(F.data == "add_another_q")
async def add_next_question(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data.get('questions', [])
    if len(questions) >= 50:
        await call.answer("⚠️ Maximum 50 questions allowed per quiz!", show_alert=True)
        return

    count = len(questions) + 1
    
    await state.set_state(QuizBuilderStates.waiting_question)
    await call.message.edit_text(
        f"Send me **Question #{count}**",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "finish_quiz_creation")
async def finish_quiz(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = call.from_user.id
    title = data['title']
    questions = data['questions']
    
    if not questions:
        await call.answer("Empty quiz!", show_alert=True)
        return

    # Save to DB
    quiz_id = await add_custom_quiz(user_id, title, questions)
    bot = call.bot
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    share_link = f"https://t.me/{bot_username}?start=quiz_{quiz_id}"
    
    # Success Message
    await call.message.edit_text(
        f"🎉 **Quiz Created Successfully!**\n\n"
        f"📝 **Title:** {title}\n"
        f"❓ **Questions:** {len(questions)}\n\n"
        f"🔗 **Share Link:**\n"
        f"`{share_link}`\n\n"
        f"You can find this quiz in **Manage UI**.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share", url=f"https://t.me/share/url?url={share_link}&text=Challenge me in this quiz!")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
        ]),
        parse_mode="Markdown"
    )
    await state.clear()
