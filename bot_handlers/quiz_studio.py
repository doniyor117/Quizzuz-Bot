from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_services.utils import get_cancel_kb, get_home_kb

router = Router()

class AIQuizStates(StatesGroup):
    waiting_topic = State()

@router.callback_query(F.data == "menu_quiz_studio")
async def show_quiz_studio(call: types.CallbackQuery, state: FSMContext):
    """Display the Quiz Studio submenu with creation options."""
    text = (
        "🛠 **Quiz Studio**\n\n"
        "What would you like to create today?"
    )
    
    kb = [
        [InlineKeyboardButton(text="🧙‍♂️ Manual Wizard", callback_data="build_quiz_start")],
        [InlineKeyboardButton(text="🤖 AI Generator", callback_data="ai_quiz_gen_start")],
        [InlineKeyboardButton(text="📥 Import File", callback_data="import_file_start")],
        [InlineKeyboardButton(text="📋 My Quizzes", callback_data="mng_cust_quizzes")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
    ]
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# --- AI QUIZ GENERATOR ---
AI_DAILY_LIMIT = 10

@router.callback_query(F.data == "ai_quiz_gen_start")
async def start_ai_gen(call: types.CallbackQuery, state: FSMContext):
    # Check daily limit
    from bot_services.firebase_service import get_user_ai_usage, increment_ai_usage
    user_id = call.from_user.id
    usage = await get_user_ai_usage(user_id)
    
    if usage >= AI_DAILY_LIMIT:
        await call.message.edit_text(
            f"⚠️ **Daily Limit Reached**\n\n"
            f"You've used all {AI_DAILY_LIMIT} AI quiz generations for today.\n"
            f"_Limit resets at midnight UTC._",
            reply_markup=get_home_kb(),
            parse_mode="Markdown"
        )
        return
    
    remaining = AI_DAILY_LIMIT - usage
    await state.set_state(AIQuizStates.waiting_topic)
    await call.message.edit_text(
        f"🤖 **AI Quiz Generator**\n\n"
        f"Send me a **topic** and I'll generate 10 quiz questions!\n\n"
        f"_Example: \"Python Basics\", \"World War II\", \"Solar System\"_\n\n"
        f"📊 Daily uses remaining: **{remaining}/{AI_DAILY_LIMIT}**",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.message(AIQuizStates.waiting_topic)
async def handle_ai_topic(message: types.Message, state: FSMContext):
    topic = message.text.strip()
    if len(topic) < 3:
        await message.reply("⚠️ Topic too short. Please be more specific.")
        return
    
    # Check daily limit again
    from bot_services.firebase_service import get_user_ai_usage, increment_ai_usage
    user_id = message.from_user.id
    usage = await get_user_ai_usage(user_id)
    
    if usage >= AI_DAILY_LIMIT:
        await message.reply(f"⚠️ Daily limit reached ({AI_DAILY_LIMIT}/day). Try again tomorrow!")
        await state.clear()
        return
    
    # Show generating message
    status_msg = await message.answer("🤖 Generating quiz... This may take a few seconds.")
    
    # Generate quiz
    from bot_services.ai_service import generate_quiz_from_topic
    questions = await generate_quiz_from_topic(topic, num_questions=10, user_id=message.from_user.id)
    
    if not questions:
        await status_msg.edit_text(
            "❌ Failed to generate quiz. Please try again with a different topic.",
            reply_markup=get_home_kb()
        )
        await state.clear()
        return
    
    # Increment usage counter
    await increment_ai_usage(user_id)
    
    # Track analytics
    from bot_services import analytics_service
    await analytics_service.track_feature(user_id, 'ai_quiz', 'generated')
    
    # Save to DB
    from bot_services.firebase_service import add_custom_quiz
    quiz_id = await add_custom_quiz(message.from_user.id, f"AI: {topic[:40]}", questions)
    
    # Get share link
    bot = message.bot
    bot_info = await bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=quiz_{quiz_id}"
    
    remaining = AI_DAILY_LIMIT - usage - 1
    await status_msg.edit_text(
        f"🎉 **Quiz Generated!**\n\n"
        f"📝 **Topic:** {topic}\n"
        f"❓ **Questions:** {len(questions)}\n"
        f"📊 Remaining today: {remaining}/{AI_DAILY_LIMIT}\n\n"
        f"🔗 **Share Link:**\n`{share_link}`",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share", url=f"https://t.me/share/url?url={share_link}&text=AI-generated quiz!")],
            [InlineKeyboardButton(text="🛠 Quiz Studio", callback_data="menu_quiz_studio")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
        ]),
        parse_mode="Markdown"
    )
    await state.clear()

# --- FILE IMPORT ---
class ImportStates(StatesGroup):
    waiting_file = State()

@router.callback_query(F.data == "import_file_start")
async def start_import(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ImportStates.waiting_file)
    await call.message.edit_text(
        "📥 **Import Quiz from File**\n\n"
        "Send me a **PDF** or **DOCX** file containing your quiz.\n\n"
        "_Format: Each question on a new line, followed by options (A, B, C, D)._\n"
        "_First option should be the correct answer._",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.message(ImportStates.waiting_file, F.document)
async def handle_file_import(message: types.Message, state: FSMContext):
    doc = message.document
    file_name = doc.file_name.lower()
    
    if not (file_name.endswith('.pdf') or file_name.endswith('.docx')):
        await message.reply("⚠️ Please send a PDF or DOCX file.")
        return
    
    status_msg = await message.answer("📄 Processing file... Please wait.")
    
    try:
        # Download file
        import tempfile
        import os
        
        file = await message.bot.get_file(doc.file_id)
        file_path = file.file_path
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
            await message.bot.download_file(file_path, tmp)
            tmp_path = tmp.name
        
        # Parse based on file type
        text_content = ""
        if file_name.endswith('.pdf'):
            text_content = await _parse_pdf(tmp_path)
        elif file_name.endswith('.docx'):
            text_content = await _parse_docx(tmp_path)
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        if not text_content:
            await status_msg.edit_text("❌ Could not extract text from the file.", reply_markup=get_home_kb())
            await state.clear()
            return

        # AI Parsing (Robus & Smart)
        await status_msg.edit_text("🤖 Analyzing file with AI... finding questions...")
        
        from bot_services.ai_service import generate_quiz_from_file_text
        questions = await generate_quiz_from_file_text(text_content, user_id=message.from_user.id)
        
        if not questions:
            await status_msg.edit_text(
                "❌ Could not find quiz questions in the file.\n\n"
                "Make sure your file follows this format:\n"
                "Q1: Question text\n"
                "A) Correct answer\n"
                "B) Wrong answer\n...",
                reply_markup=get_home_kb()
            )
            await state.clear()
            return
        
        # Save quiz
        from bot_services.firebase_service import add_custom_quiz
        title = f"Import: {doc.file_name[:30]}"
        quiz_id = await add_custom_quiz(message.from_user.id, title, questions)
        
        bot_info = await message.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start=quiz_{quiz_id}"
        
        await status_msg.edit_text(
            f"🎉 **Quiz Imported!**\n\n"
            f"📝 **Title:** {title}\n"
            f"❓ **Questions:** {len(questions)}\n\n"
            f"🔗 **Share Link:**\n`{share_link}`",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Share", url=f"https://t.me/share/url?url={share_link}")],
                [InlineKeyboardButton(text="🏠 Home", callback_data="cancel")]
            ]),
            parse_mode="Markdown"
        )
        await state.clear()
        
    except Exception as e:
        print(f"Import error: {e}")
        await status_msg.edit_text(f"❌ Error processing file: {str(e)[:100]}", reply_markup=get_home_kb())
        await state.clear()

async def _parse_pdf(file_path: str) -> str:
    """Extract text from PDF (max 10 pages)."""
    text = ""
    # Try PyMuPDF first
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        for i, page in enumerate(doc):
            if i >= 10:
                break  # Max 10 pages
            text += page.get_text()
        doc.close()
        return text
    except ImportError:
        pass  # fitz not installed, try fallback
    except Exception as e:
        print(f"PyMuPDF error: {e}")
    
    # Fallback to pypdf (more commonly available)
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        for i, page in enumerate(reader.pages[:10]):  # Max 10 pages
            text += page.extract_text() or ""
        return text
    except ImportError:
        pass
    except Exception as e:
        print(f"pypdf error: {e}")
    
    # Last fallback: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages[:10]):  # Max 10 pages
                text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"pdfplumber error: {e}")
    
    return ""

async def _parse_docx(file_path: str) -> str:
    """Extract text from DOCX (max 10 pages worth)."""
    try:
        from docx import Document
        doc = Document(file_path)
        # Estimate 500 words per page, limit to ~5000 words
        paragraphs = doc.paragraphs[:100]  # Roughly 10 pages worth
        text = "\n".join([para.text for para in paragraphs])
        return text
    except Exception as e:
        print(f"DOCX parse error: {e}")
        return ""

def _extract_questions_from_text(text: str) -> list:
    """Extract quiz questions from plain text."""
    questions = []
    lines = text.strip().split('\n')
    
    current_q = None
    current_options = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Detect question patterns: Q1:, 1., 1), Question 1:
        if any(line.startswith(p) for p in ['Q', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.']):
            if ':' in line or ')' in line:
                if current_q and len(current_options) >= 2:
                    questions.append({
                        'text': current_q,
                        'options': current_options[:10],
                        'correct_index': 0
                    })
                # Extract question text
                if ':' in line:
                    current_q = line.split(':', 1)[1].strip()
                elif ')' in line:
                    current_q = line.split(')', 1)[1].strip()
                else:
                    current_q = line
                current_options = []
        # Detect options: A), B), a., b.
        elif line[0:2] in ['A)', 'B)', 'C)', 'D)', 'E)', 'A.', 'B.', 'C.', 'D.', 'E.', 'a)', 'b)', 'c)', 'd)']:
            current_options.append(line[2:].strip())
    
    # Add last question
    if current_q and len(current_options) >= 2:
        questions.append({
            'text': current_q,
            'options': current_options[:10],
            'correct_index': 0
        })
    
    return questions[:50]


