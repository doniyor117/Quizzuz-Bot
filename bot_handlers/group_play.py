from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.firebase_service import get_custom_quiz
from bot_services.utils import get_home_kb
import asyncio

router = Router()

# Group play sessions stored in memory
GROUP_SESSIONS = {}  # {chat_id: session_data}

LOBBY_DURATION = 20  # seconds to join
MAX_EMPTY_ROUNDS = 2  # Stop quiz after this many unanswered questions

@router.callback_query(F.data.startswith("host_group_"))
async def start_group_host(call: types.CallbackQuery, state: FSMContext):
    """Generate instructions for hosting quiz in a group."""
    quiz_id = call.data.replace("host_group_", "")
    quiz = await get_custom_quiz(quiz_id)
    
    if not quiz:
        await call.answer("Quiz not found", show_alert=True)
        return
    
    bot_info = await call.bot.get_me()
    bot_username = bot_info.username
    
    group_link = f"https://t.me/{bot_username}?startgroup=quiz_{quiz_id}"
    
    text = (
        f"👥 **Host Quiz in Group**\n\n"
        f"📝 **Quiz:** {quiz['title']}\n"
        f"❓ **Questions:** {len(quiz.get('questions', []))}\n\n"
        f"**Features:**\n"
        f"✋ Lobby phase - players join first\n"
        f"⚡ Turbo mode - skips to next when all answer\n"
        f"🛑 Auto-stop if no one answers\n\n"
        f"Click below to start!"
    )
    
    kb = [
        [InlineKeyboardButton(text="🚀 Start in Group", url=group_link)],
        [InlineKeyboardButton(text="Back", callback_data=f"act_cust_quiz_{quiz_id}")]
    ]
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# --- GROUP QUIZ START ---
@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.regexp(r"^/start(@\w+)?\s+quiz_"))
async def handle_group_quiz_start(message: types.Message):
    """Handle quiz start command in group chat via deep link."""
    text = message.text
    if "quiz_" in text:
        quiz_id = text.split("quiz_")[1].split()[0].strip()
    else:
        return
    
    quiz = await get_custom_quiz(quiz_id)
    if not quiz:
        await message.answer("❌ Quiz not found.")
        return
    
    chat_id = message.chat.id
    
    if chat_id in GROUP_SESSIONS:
        await message.answer("⚠️ A quiz is already running! Use /stop to end it first.")
        return
    
    timer = quiz.get('timer', 30)
    questions = quiz.get('questions', [])
    
    # Initialize session
    GROUP_SESSIONS[chat_id] = {
        'quiz_id': quiz_id,
        'quiz': quiz,
        'current_q': 0,
        'scores': {},
        'participants': set(),
        'answered': set(),
        'timer': timer,
        'empty_rounds': 0,
        'stopped': False,
        'host_id': message.from_user.id
    }
    
    # Send lobby message
    lobby_msg = await message.answer(
        f"🎮 **{quiz['title']}**\n\n"
        f"❓ {len(questions)} questions | ⏱️ {timer}s per question\n\n"
        f"✋ **Click JOIN to participate!**\n"
        f"_Lobby closes in {LOBBY_DURATION} seconds..._\n\n"
        f"👥 Participants: 0",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✋ JOIN", callback_data=f"grp_join_{chat_id}")]
        ]),
        parse_mode="Markdown"
    )
    
    GROUP_SESSIONS[chat_id]['lobby_msg_id'] = lobby_msg.message_id
    
    # Start lobby countdown
    await lobby_countdown(chat_id, message.bot, LOBBY_DURATION)

async def lobby_countdown(chat_id: int, bot, duration: int):
    """Countdown for lobby phase, then start quiz."""
    await asyncio.sleep(duration)
    
    session = GROUP_SESSIONS.get(chat_id)
    if not session or session.get('stopped'):
        return
    
    participants = session['participants']
    
    if not participants:
        await bot.send_message(chat_id, "❌ No one joined! Quiz cancelled.")
        del GROUP_SESSIONS[chat_id]
        return
    
    await bot.send_message(
        chat_id,
        f"🚀 **Starting Quiz!**\n\n"
        f"👥 {len(participants)} participant(s)\n"
        f"_First question in 3 seconds..._",
        parse_mode="Markdown"
    )
    
    await asyncio.sleep(3)
    await send_group_question(chat_id, bot)

@router.callback_query(F.data.startswith("grp_join_"))
async def handle_join(call: types.CallbackQuery):
    """Handle player joining the quiz lobby."""
    chat_id = int(call.data.replace("grp_join_", ""))
    session = GROUP_SESSIONS.get(chat_id)
    
    if not session:
        await call.answer("This quiz has ended.", show_alert=True)
        return
    
    user_id = call.from_user.id
    user_name = call.from_user.first_name or call.from_user.username or f"User_{user_id}"
    
    if user_id in session['participants']:
        await call.answer("You've already joined!", show_alert=False)
        return
    
    session['participants'].add(user_id)
    session['scores'][user_id] = {'score': 0, 'name': user_name}
    
    await call.answer(f"✅ You joined! ({len(session['participants'])} players)", show_alert=False)
    
    # Update lobby message
    try:
        quiz = session['quiz']
        await call.message.edit_text(
            f"🎮 **{quiz['title']}**\n\n"
            f"❓ {len(quiz.get('questions', []))} questions | ⏱️ {session['timer']}s per question\n\n"
            f"✋ **Click JOIN to participate!**\n"
            f"_Lobby closes soon..._\n\n"
            f"👥 Participants: **{len(session['participants'])}**",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✋ JOIN", callback_data=f"grp_join_{chat_id}")]
            ]),
            parse_mode="Markdown"
        )
    except:
        pass  # Message already updated or lobby ended

# --- QUESTIONS ---
async def send_group_question(chat_id: int, bot):
    """Send next question to the group as a poll."""
    import random
    
    session = GROUP_SESSIONS.get(chat_id)
    if not session or session.get('stopped'):
        return
    
    quiz = session['quiz']
    q_idx = session['current_q']
    questions = quiz.get('questions', [])
    timer = session['timer']
    
    if q_idx >= len(questions):
        await show_group_leaderboard(chat_id, bot)
        return
    
    # Check AFK
    if session['empty_rounds'] >= MAX_EMPTY_ROUNDS:
        await bot.send_message(
            chat_id,
            "🛑 **Quiz Stopped**\n\n_No one answered for multiple questions._",
            parse_mode="Markdown"
        )
        await show_group_leaderboard(chat_id, bot)
        return
    
    q = questions[q_idx]
    options = q['options'][:10]
    correct_answer = options[0]
    
    shuffled = options.copy()
    random.shuffle(shuffled)
    correct_index = shuffled.index(correct_answer)
    
    session['current_correct'] = correct_index
    session['answered'] = set()
    session['current_poll_id'] = None
    
    try:
        poll = await bot.send_poll(
            chat_id=chat_id,
            question=f"❓ Q{q_idx + 1}/{len(questions)}: {q['text'][:200]}",
            options=shuffled,
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=False,
            open_period=timer
        )
        session['current_poll_id'] = poll.poll.id
        
        # Schedule timeout
        asyncio.create_task(question_timeout(chat_id, bot, timer + 2, q_idx))
        
    except Exception as e:
        print(f"Group poll error: {e}")
        await bot.send_message(chat_id, f"❌ Error: {str(e)[:100]}")

async def question_timeout(chat_id: int, bot, delay: int, expected_q_idx: int):
    """Wait for poll to end, check if we need to advance."""
    await asyncio.sleep(delay)
    
    session = GROUP_SESSIONS.get(chat_id)
    if not session or session.get('stopped'):
        return
    
    # Only advance if we're still on the same question
    if session['current_q'] != expected_q_idx:
        return
    
    # Track empty rounds
    if not session['answered']:
        session['empty_rounds'] += 1
    else:
        session['empty_rounds'] = 0
    
    session['current_q'] += 1
    await send_group_question(chat_id, bot)

def is_group_poll(poll_answer: types.PollAnswer) -> bool:
    """Filter to check if this poll answer belongs to a group session."""
    pid = poll_answer.poll_id
    # Check if this poll ID exists in any active session
    return any(s.get('current_poll_id') == pid for s in GROUP_SESSIONS.values())

@router.poll_answer(is_group_poll)
async def handle_group_poll_answer(poll_answer: types.PollAnswer):
    """Handle answers in group quiz."""
    user_id = poll_answer.user.id
    user_name = poll_answer.user.first_name or poll_answer.user.username or f"User_{user_id}"
    poll_id = poll_answer.poll_id
    selected = poll_answer.option_ids[0] if poll_answer.option_ids else -1
    
    for chat_id, session in list(GROUP_SESSIONS.items()):
        if session.get('current_poll_id') == poll_id:
            # Only count participants
            if user_id not in session['participants']:
                session['participants'].add(user_id)
                session['scores'][user_id] = {'score': 0, 'name': user_name}
            
            if user_id in session['answered']:
                return
            
            session['answered'].add(user_id)
            correct_idx = session.get('current_correct', -1)
            
            if selected == correct_idx:
                session['scores'][user_id]['score'] += 1
            
            # TURBO MODE: Check if all participants answered
            if session['answered'] >= session['participants']:
                # Everyone answered - advance immediately!
                session['empty_rounds'] = 0
                session['current_q'] += 1
                
                # Small delay before next question
                asyncio.create_task(turbo_advance(chat_id, poll_answer.bot))
            
            break

async def turbo_advance(chat_id: int, bot):
    """Advance to next question immediately (turbo mode)."""
    await asyncio.sleep(1)  # Brief pause
    session = GROUP_SESSIONS.get(chat_id)
    if session and not session.get('stopped'):
        await send_group_question(chat_id, bot)

# --- STOP COMMAND ---
@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.regexp(r"^/stop(@\w+)?$"))
async def handle_stop_command(message: types.Message):
    """Stop the current quiz in the group."""
    chat_id = message.chat.id
    session = GROUP_SESSIONS.get(chat_id)
    
    if not session:
        await message.reply("❌ No quiz is running in this group.")
        return
    
    # Check if user is host or admin
    user_id = message.from_user.id
    is_host = session.get('host_id') == user_id
    
    try:
        member = await message.bot.get_chat_member(chat_id, user_id)
        is_admin = member.status in ['administrator', 'creator']
    except:
        is_admin = False
    
    if not is_host and not is_admin:
        await message.reply("⚠️ Only the quiz host or group admins can stop the quiz.")
        return
    
    session['stopped'] = True
    
    await message.reply("🛑 **Quiz stopped!**\n\n_Showing final results..._", parse_mode="Markdown")
    await show_group_leaderboard(chat_id, message.bot)

# --- LEADERBOARD ---
async def show_group_leaderboard(chat_id: int, bot):
    """Show final leaderboard for group quiz."""
    session = GROUP_SESSIONS.get(chat_id)
    if not session:
        return
    
    scores = session['scores']
    quiz = session['quiz']
    total_q = len(quiz.get('questions', []))
    current_q = session.get('current_q', total_q)
    
    if not scores:
        await bot.send_message(
            chat_id, 
            "📊 **Quiz Ended!**\n\nNo participants.",
            parse_mode="Markdown"
        )
        del GROUP_SESSIONS[chat_id]
        return
    
    sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
    
    text = f"🏆 **{quiz['title']}** - Final Results\n"
    text += f"_Completed {current_q}/{total_q} questions_\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for idx, (user_id, data) in enumerate(sorted_scores[:10]):
        medal = medals[idx] if idx < 3 else f"{idx+1}."
        name = data['name'][:15]
        score = data['score']
        pct = int(score / current_q * 100) if current_q else 0
        text += f"{medal} **{name}**: {score}/{current_q} ({pct}%)\n"
    
    if len(sorted_scores) > 0:
        winner = sorted_scores[0][1]['name']
        text += f"\n🎉 **Winner: {winner}!**"
    
    text += "\n\n_Thanks for playing! 🎮_"
    
    await bot.send_message(chat_id, text, parse_mode="Markdown")
    
    del GROUP_SESSIONS[chat_id]
