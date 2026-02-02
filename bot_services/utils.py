from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- States ---
class MainStates(StatesGroup):
    menu = State()
    waiting_language = State() # NEW: For onboarding

class AddCardStates(StatesGroup):
    waiting_set_name = State()
    waiting_add_method = State()
    adding_one_term = State()
    adding_one_def = State()
    adding_bulk = State()
    waiting_visibility = State()
    waiting_post_folder_name = State()
    waiting_ai_words = State()  # AI Generate mode

class VocabularyStates(StatesGroup):
    waiting_word = State()
    viewing_result = State()
    waiting_set_name = State()

class PracticeStates(StatesGroup):
    selecting_source = State()
    selecting_book = State()
    selecting_set = State()
    configuring = State()
    active_session = State()

class ManageStates(StatesGroup):
    main = State()
    waiting_new_book_name = State() 
    waiting_set_rename = State()
    selecting_move_target = State() 
    waiting_admin_id = State()
    waiting_rm_admin_id = State()
    waiting_delete_folder = State()  # For delete confirmation
    waiting_card_edit_term =State()  # For editing card term
    waiting_card_edit_def = State()  # For editing card definition
    waiting_folder_description = State()  # For editing folder description


class ExploreStates(StatesGroup):
    searching = State()

class QuizBuilderStates(StatesGroup):
    waiting_title = State()
    waiting_question = State()
    waiting_options = State()


class QuizEditStates(StatesGroup):
    waiting_new_title = State()
    waiting_new_q_text = State()
    waiting_new_q_options = State()
class AdminStates(StatesGroup):
    menu = State()
    searching_user = State()
    waiting_broadcast_msg = State()
    waiting_admin_comment = State()  # For sending comments to users after approve/reject
    waiting_api_key = State()
    waiting_rem_key = State()
    waiting_block_id = State()
    waiting_unblock_id = State()
    waiting_ban_id = State()
    waiting_unban_id = State()
    waiting_user_search = State()  # For searching users

# --- Rank Logic (Gamification) ---
def get_rank_title(level):
    """Returns rank info based on level."""
    if level < 3:
        return {"rank_emoji": "🐣", "rank_name": "Beginner"}
    elif level < 5:
        return {"rank_emoji": "📚", "rank_name": "Student"}
    elif level < 10:
        return {"rank_emoji": "🎓", "rank_name": "Scholar"}
    elif level < 20:
        return {"rank_emoji": "🧠", "rank_name": "Master"}
    elif level < 50:
        return {"rank_emoji": "🔮", "rank_name": "Grandmaster"}
    else:
        return {"rank_emoji": "🦁", "rank_name": "Legend"}

# --- Keyboard Helpers ---
def get_main_menu_kb(texts, is_admin=False, is_group=False):
    import os
    # Use RENDER_EXTERNAL_URL if available, otherwise fallback to default
    render_url = os.getenv('RENDER_EXTERNAL_URL', '')
    if render_url:
        game_url = f"{render_url}/game/"
    else:
        game_url = os.getenv('GAME_URL', 'https://quizzuz-bot.onrender.com/game/hexagame/index.html')
    
    kb = [
        # Row 1: Core Study (Unchanged)
        [InlineKeyboardButton(text=texts.get('btn_my_sets', '📚 My Library'), callback_data="src_my_sets"),
         InlineKeyboardButton(text=texts.get('btn_official_books', '🏛 Official Books'), callback_data="src_main_books")],
        
        # Row 2: Study Tools (Favorites + AI Vocab)
        [InlineKeyboardButton(text="❤️ Favorites", callback_data="menu_favorites"),
         InlineKeyboardButton(text="🔍 AI Vocabulary", callback_data="menu_vocabulary")],
    ]
    
    # Row 3: Creation & Fun (WebApp only in private chats)
    row3 = [InlineKeyboardButton(text="🛠 Quiz Studio", callback_data="menu_quiz_studio")]
    if not is_group:  # WebApp buttons not allowed in groups
        row3.append(InlineKeyboardButton(text="🎮 Word Scramble", web_app=WebAppInfo(url=game_url)))
    kb.append(row3)
    
    # Row 4: System
    kb.append([
        InlineKeyboardButton(text=texts.get('btn_manage', '⚙️ Manage'), callback_data="menu_manage"),
        InlineKeyboardButton(text="👤 Profile", callback_data="menu_profile")
    ])
    
    if is_admin:
        kb.append([InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_cancel_kb(texts=None):
    t = texts['btn_cancel'] if texts else "Cancel"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data="cancel")]])

def get_home_kb(texts=None):
    t = texts['btn_home'] if texts else "🏠 Home"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data="cancel")]])

# --- Text Similarity for MCQ ---
def text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts (0.0 to 1.0).
    Uses Jaccard similarity based on word overlap.
    
    Args:
        text1: First text to compare
        text2: Second text to compare
        
    Returns:
        Float between 0.0 (completely different) and 1.0 (identical)
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalize and tokenize
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    # Jaccard similarity: intersection / union
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0

def are_too_similar(text1: str, text2: str, threshold: float = 0.6) -> bool:
    """
    Check if two texts are too similar to be used as distinct MCQ options.
    
    Args:
        text1: First text to compare
        text2: Second text to compare
        threshold: Similarity threshold (default 0.6 = 60% word overlap)
        
    Returns:
        True if texts are too similar, False otherwise
        
    Examples:
        >>> are_too_similar("happy person", "joyful person")
        True  # 50% overlap ("person") might trigger depending on threshold
        >>> are_too_similar("cat", "dog")
        False  # No overlap
    """
    return text_similarity(text1, text2) > threshold

# --- VKM Style Pagination Helper ---
def build_vkm_pagination_kb(
    items: list[dict],      # [{'text': 'unused', 'callback_data': '...'}] text is technically unused for grid logic except labeling
    page: int,
    total_items: int,
    limit: int,
    back_callback: str,
    nav_prefix: str,        # Prefix for prev/next buttons e.g. "brow_my_sets_None_"
    home_callback: str = "cancel"
):
    """
    Creates a VKM-style numbered grid pagination.
    Buttons: [1] [2] [3] [4] [5]
             [6] [7] [8] [9] [10]
             [⬅️] [❌] [➡️]
    """
    kb = []
    
    # 1. Numbered Grid (5 items per row)
    current_row = []
    for idx, item in enumerate(items, 1):
        # Button text is just the number index (1-10)
        btn_text = str(idx) # Or maybe emojis? 1️⃣. User said 1, 2, 3. Let's stick to numbers.
        current_row.append(InlineKeyboardButton(text=btn_text, callback_data=item['callback_data']))
        
        if len(current_row) == 5:
            kb.append(current_row)
            current_row = []
            
    if current_row:
        kb.append(current_row)
        
    # 2. Navigation Row
    nav_row = []
    
    # Prev
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{nav_prefix}{page-1}"))

    # Cancel/Home (Always in middle)
    # User said: "Prev.., X, Next" or "cancel"
    nav_row.append(InlineKeyboardButton(text="❌", callback_data=back_callback)) 
    
    # Next
    if (page + 1) * limit < total_items:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{nav_prefix}{page+1}"))
        
    kb.append(nav_row)
    
    return InlineKeyboardMarkup(inline_keyboard=kb)