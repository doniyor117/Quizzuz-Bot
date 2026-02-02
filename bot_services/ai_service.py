import os
import aiohttp
from typing import Optional, Dict, List

from bot_services.firebase_service import get_bot_config, get_all_users, check_ai_limit
from aiogram import Bot

# Get Groq API key from environment (Fallback)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# AI Model Fallback List (for card generation and AI review in practice)
# Expanded for high load scenarios with 6 production models
AI_MODELS = [
    "llama-3.3-70b-versatile",     # Primary: Best quality, newest
    "llama-3.1-8b-instant",        # Secondary: Fast, highly available
    "llama3-70b-8192",             # Tertiary: Reliable, large context
    "gemma2-9b-it",                # Quaternary: Google's Gemma (different provider)
    "mixtral-8x7b-32768",          # Quinary: Mistral's efficient model
    "llama3-8b-8192",              # Final: Fastest, smallest
]

# Vocabulary-specific AI Models (for vocabulary lookup service)
# Expanded for high load - same models as AI_MODELS for consistency
VOCAB_AI_MODELS = [
    "llama-3.3-70b-versatile",     # Primary: Best quality, newest
    "llama-3.1-8b-instant",        # Secondary: Fast, highly available
    "llama3-70b-8192",             # Tertiary: Reliable, large context
    "gemma2-9b-it",                # Quaternary: Google's Gemma
    "mixtral-8x7b-32768",          # Quinary: Mistral MoE
    "llama3-8b-8192",              # Final: Fastest fallback
]

# ===== GROQ API INTEGRATION =====
async def generate_card_content(word: str, reverse_mode: bool = False, user_id: int = None) -> Optional[Dict]:
    """
    Generate flashcard content using Groq AI with automatic model fallback.
    Tries models in priority order until one succeeds.
    Returns: dict with 'definition', 'translation', 'examples'
    """
    # 1. Get Config
    config = await get_bot_config()
    
    # 2. Check Global Toggle
    if not config.get('ai_enabled', True):
        return None
        
    # 3. Check Blacklist
    if user_id and user_id in config.get('blocked_users', []):
        return None

    # 4. Check Daily Limit (40/day - Option A)
    if user_id:
        allowed = await check_ai_limit(user_id)
        if not allowed:
            return {'error': 'limit_reached'}

    # 5. Get API Key (DB first, then Env)
    api_keys = config.get('api_keys', [])
    api_key = api_keys[0] if api_keys else GROQ_API_KEY
    
    if not api_key:
        print("Warning: No Groq API key available")
        return None
    
    # 6. Build prompt (same as before)
    if reverse_mode:
        # Input is Uzbek (Definition side), output should be English explanation
        prompt = f"""The user is learning English. The input word is in UZBEK: "{word}"
        
Provide:
1. The English translation (Term)
2. A clear English definition
3. 2 example sentences in English

Format your response EXACTLY like this:
DEFINITION: [English definition]
TRANSLATION: [English translation of the word]
EXAMPLE1: [English example 1]
EXAMPLE2: [English example 2]"""
    else:
        # Input is English (Term side), output should be Uzbek translation
        prompt = f"""Create a vocabulary flashcard for the word: "{word}"

Provide:
1. A clear, concise definition (1-2 sentences)
2. Uzbek translation
3. 2 example sentences using the word in context

Format your response EXACTLY like this:
DEFINITION: [definition here]
TRANSLATION: [Uzbek translation]
EXAMPLE1: [first example sentence]
EXAMPLE2: [second example sentence]"""

    # 7. CHECK VOCABULARY CACHE FIRST (reuse existing cache)
    try:
        from bot_services.vocabulary_cache import get_from_cache
        cached = await get_from_cache(word)
        
        if cached and cached.get('source_type') == 'ai':
            # AI cache hit! Return immediately
            print(f"✅ Card cache hit for: {word}")
            return {
                'definition': cached.get('definition', ''),
                'translation': cached.get('translation_uz', ''),
                'examples': cached.get('examples', []),
                'phonetic': cached.get('phonetic', '')
            }
    except Exception as e:
        print(f"Cache check failed (non-fatal): {e}")
        # Continue to AI generation
    
    # 8. Try models in order until one works
    for model in AI_MODELS:
        result = await _try_model(model, prompt, api_key)
        if result:
            print(f"✅ AI Success with model: {model}")
            
            # Track global AI usage for analytics
            try:
                from bot_services.firebase_service import track_ai_usage
                asyncio.create_task(track_ai_usage('card_generation', 500))  # Estimate tokens
            except Exception as e:
                print(f"AI tracking failed (non-fatal): {e}")
            
            # SAVE TO VOCABULARY CACHE for future use
            try:
                from bot_services.vocabulary_cache import save_to_cache
                await save_to_cache(word, result, 'ai')
                print(f"💾 Cached AI card: {word}")
            except Exception as e:
                print(f"Cache save failed (non-fatal): {e}")
            
            return result
        # If failed (rate limit or error), try next model
    
    # All models failed
    print("❌ All AI models failed!")
    return None

async def _try_model(model: str, prompt: str, api_key: str) -> Optional[Dict]:
    """Try a single AI model, return None if rate limited or failed."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful vocabulary tutor creating educational flashcards. Be concise and clear."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data['choices'][0]['message']['content']
                    
                    # Parse the response
                    parsed = parse_ai_response(content)
                    if parsed:
                        return parsed
                elif response.status == 429:  # Rate Limit
                    error_text = await response.text()
                    print(f"⚠️ Model {model} rate limited, trying next...")
                    # Don't notify admins on every rate limit, just try next model
                    return None  # Trigger fallback to next model
                else:
                    error_text = await response.text()
                    print(f"❌ Model {model} error {response.status}: {error_text}")
                    return None
    except Exception as e:
        print(f"❌ Model {model} exception: {e}")
        return None

async def notify_admins_limit_reached(error_text):
    """Notify all admins about API limit reached."""
    try:
        # We need a bot instance. This is tricky without passing it.
        # For now, we'll just print. In a real app, we'd pass bot or use a singleton.
        print(f"⚠️ ADMIN ALERT: AI Rate Limit Reached! {error_text}")
        # TODO: Implement actual telegram notification if bot instance available
    except Exception as e:
        print(f"Failed to notify admins: {e}")


def parse_ai_response(content: str) -> Optional[Dict]:
    """
    Parse AI response into structured data.
    """
    try:
        definition = ""
        translation = ""
        examples = []
        
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('DEFINITION:'):
                definition = line.replace('DEFINITION:', '').strip()
            elif line.startswith('TRANSLATION:'):
                translation = line.replace('TRANSLATION:', '').strip()
            elif line.startswith('EXAMPLE1:'):
                examples.append(line.replace('EXAMPLE1:', '').strip())
            elif line.startswith('EXAMPLE2:'):
                examples.append(line.replace('EXAMPLE2:', '').strip())
        
        if definition:
            return {
                'definition': definition,
                'translation': translation,
                'examples': examples
            }
        return None
    except Exception as e:
        print(f"Error parsing AI response: {e}")
        return None


# ===== ENHANCED DEFINITION WITH AI =====
async def enhance_definition(word: str, basic_definition: str) -> str:
    """
    Enhance a basic definition with AI to make it more educational.
    """
    if not GROQ_API_KEY:
        return basic_definition
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""Improve this vocabulary definition to be more educational and memorable:

Word: {word}
Current definition: {basic_definition}

Provide an enhanced definition that:
- Is clear and concise (2-3 sentences max)
- Includes context or usage hints
- Is easy to understand

Just provide the enhanced definition, nothing else."""

    payload = {
        "model": "llama-3.3-70b-versatile",  # Updated from deprecated llama-3.1-70b-versatile
        "messages": [
            {"role": "system", "content": "You are a vocabulary expert. Enhance definitions to be clear and educational."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": 200
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    enhanced = data['choices'][0]['message']['content'].strip()
                    return enhanced
                return basic_definition
    except Exception as e:
        print(f"AI enhancement error: {e}")
        return basic_definition
"""
AI Service Extension for Vocabulary Lookups

Adds vocabulary-specific AI function with dedicated models.
Append this to the end of bot_services/ai_service.py
"""

# ===== VOCABULARY AI (Separate from card generation) =====
async def generate_vocabulary_ai(word: str, reverse_mode: bool = False) -> Optional[Dict]:
    """
    Generate vocabulary definition using AI with 3-model fallback.
    Specifically for vocabulary lookup (not flashcard creation).
    
    Does NOT check AI card generation limits (uses vocab limits instead).
    
    Returns: {
        'definition': str,
        'translation': str,
        'examples': list,
        'phonetic': str,
        'source': 'ai'
    }
    """
    # 1. Get API Key
    config = await get_bot_config()
    api_keys = config.get('api_keys', [])
    api_key = api_keys[0] if api_keys else GROQ_API_KEY
    
    if not api_key:
        print("Warning: No Groq API key available for vocabulary")
        return None
    
    # 2. Build prompt with AUTO-LANGUAGE DETECTION
    # AI will detect if input is English or Uzbek and respond accordingly
    prompt = f"""Analyze the word "{word}" and provide a complete vocabulary explanation.

Steps:
1. Detect the language (English or Uzbek/Cyrillic)
2. If English: Provide definition + Uzbek translation
3. If Uzbek: Provide explanation + English translation

Provide:
- Clear definition/explanation
- Translation (to the opposite language)
- Phonetic pronunciation (IPA format, if applicable)
- 2 example sentences showing proper usage

Format EXACTLY like this:
DEFINITION: [Clear definition or explanation]
TRANSLATION: [Translation to opposite language]
PHONETIC: [IPA pronunciation or N/A]
EXAMPLE1: [First example sentence]
EXAMPLE2: [Second example sentence]

Note: Automatically adapt the language based on input. For Uzbek words, provide English translation. For English words, provide Uzbek translation."""
    
    # 3. Try vocabulary models in sequence
    for model in VOCAB_AI_MODELS:
        result = await _try_vocab_model(model, prompt, api_key)
        if result:
            print(f"✅ Vocab AI Success with model: {model}")
            # Add source indicator
            result['source'] = 'ai'
            
            # Track global AI usage for analytics
            try:
                from bot_services.firebase_service import track_ai_usage
                import asyncio
                asyncio.create_task(track_ai_usage('vocab_lookup', 500))  # Estimate tokens
            except Exception as e:
                print(f"AI tracking failed (non-fatal): {e}")
            
            return result
        print(f"⚠️ Vocab model {model} failed, trying next...")
    
    # All models failed
    print("❌ All vocabulary AI models failed!")
    return None

async def _try_vocab_model(model: str, prompt: str, api_key: str) -> Optional[Dict]:
    """Try a single vocabulary AI model, return parsed result or None."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data['choices'][0]['message']['content']
                    
                    # Parse the vocabulary response
                    parsed = _parse_vocab_response(content)
                    if parsed:
                        return parsed
                elif response.status == 429:  # Rate Limit
                    print(f"⚠️ Vocab model {model} rate limited")
                    return None
                else:
                    error_text = await response.text()
                    print(f"❌ Vocab model {model} error {response.status}: {error_text}")
                    return None
    except Exception as e:
        print(f"❌ Vocab model {model} exception: {e}")
        return None

def _parse_vocab_response(text: str) -> Optional[Dict]:
    """Parse AI vocabulary response into structured format."""
    try:
        lines = text.strip().split('\n')
        result = {
            'definition': '',
            'translation': '',
            'examples': [],
            'phonetic': ''
        }
        
        for line in lines:
            line = line.strip()
            if line.startswith('DEFINITION:'):
                result['definition'] = line.replace('DEFINITION:', '').strip()
            elif line.startswith('TRANSLATION:'):
                result['translation'] = line.replace('TRANSLATION:', '').strip()
            elif line.startswith('PHONETIC:'):
                phonetic = line.replace('PHONETIC:', '').strip()
                result['phonetic'] = phonetic if phonetic.upper() != 'N/A' else ''
            elif line.startswith('EXAMPLE1:'):
                result['examples'].append(line.replace('EXAMPLE1:', '').strip())
            elif line.startswith('EXAMPLE2:'):
                result['examples'].append(line.replace('EXAMPLE2:', '').strip())
        
        # Validate we got at least definition or translation
        if result['definition'] or result['translation']:
            return result
        
        return None
    except Exception as e:
        print(f"Error parsing vocab response: {e}")
        return None


# ===== QUIZ EXPLANATION AI =====
async def generate_quiz_explanation_ai(term: str, definition: str) -> Optional[Dict]:
    """
    Generate bilingual (English + Uzbek) explanation for quiz feedback.
    Returns: {'eng': '...', 'uzb': '...'} or None
    Caches result for future quiz usage.
    """
    # 1. Check cache first
    try:
        from bot_services.vocabulary_cache import get_from_cache, save_to_cache
        cached = await get_from_cache(term)
        if cached and cached.get('definition') and cached.get('translation_uz'):
            return {
                'eng': cached.get('definition', '')[:80],
                'uzb': cached.get('translation_uz', '')[:80]
            }
    except Exception as e:
        print(f"Quiz explanation cache check failed: {e}")
    
    # 2. Get API key
    config = await get_bot_config()
    api_keys = config.get('api_keys', [])
    api_key = api_keys[0] if api_keys else GROQ_API_KEY
    
    if not api_key:
        return None
    
    # 3. Generate with AI (fast model)
    prompt = f"""For the English word "{term}" with definition "{definition}":

Provide:
1. A brief English explanation (1 sentence, max 80 chars)
2. Uzbek translation (1-2 words)

Format EXACTLY:
ENG: [brief explanation]
UZB: [Uzbek translation]"""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",  # Fast model for quick explanations
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 100
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data['choices'][0]['message']['content']
                    
                    # Parse response
                    result = {'eng': '', 'uzb': ''}
                    for line in content.split('\n'):
                        line = line.strip()
                        if line.startswith('ENG:'):
                            result['eng'] = line.replace('ENG:', '').strip()[:80]
                        elif line.startswith('UZB:'):
                            result['uzb'] = line.replace('UZB:', '').strip()[:80]
                    
                    # Cache for future use
                    if result['eng'] or result['uzb']:
                        try:
                            await save_to_cache(term, {
                                'definition': result['eng'],
                                'translation_uz': result['uzb']
                            }, 'ai')
                        except:
                            pass
                        
                        # Track AI usage
                        try:
                            from bot_services.firebase_service import track_ai_usage
                            import asyncio
                            asyncio.create_task(track_ai_usage('quiz_explanation', 100))
                        except:
                            pass
                        
                        return result
                    
                return None
    except Exception as e:
        print(f"Quiz explanation AI error: {e}")
        return None

# ===== AI QUIZ GENERATOR =====
async def generate_quiz_from_topic(topic: str, num_questions: int = 10, user_id: int = None) -> Optional[List[Dict]]:
    """
    Generate quiz questions from a topic using AI.
    Returns list of questions: [{'text': '...', 'options': [...], 'correct_index': 0}, ...]
    """
    # 1. Get Config
    config = await get_bot_config()
    
    # 2. Check Global Toggle
    if not config.get('ai_enabled', True):
        return None
    
    # 3. Get API Key
    api_keys = config.get('api_keys', [])
    api_key = api_keys[0] if api_keys else GROQ_API_KEY
    
    if not api_key:
        return None
    
    # 4. Build Prompt
    prompt = f"""Generate {num_questions} multiple choice quiz questions about: "{topic}"

For each question:
- Create a clear question
- Provide 4 answer options (A, B, C, D)
- Mark the correct answer

Format EXACTLY like this for each question:
Q1: [Question text]
A) [Option 1 - CORRECT]
B) [Option 2]
C) [Option 3]
D) [Option 4]

Q2: [Question text]
...

IMPORTANT: Always put the CORRECT answer as option A."""

    # 5. Try AI Models
    for model in AI_MODELS[:3]:  # Use top 3 models
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data['choices'][0]['message']['content']
                        
                        # Parse the response
                        questions = _parse_quiz_response(content)
                        if questions:
                            return questions
        except Exception as e:
            print(f"AI Quiz Gen error with {model}: {e}")
            continue
    
    return None

def _parse_quiz_response(content: str) -> List[Dict]:
    """Parse AI response into structured questions."""
    questions = []
    lines = content.strip().split('\n')
    
    current_q = None
    current_options = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Detect question line
        if line.startswith('Q') and ':' in line:
            # Save previous question if exists
            if current_q and len(current_options) >= 2:
                questions.append({
                    'text': current_q,
                    'options': current_options,
                    'correct_index': 0  # A is always correct per prompt
                })
            # Start new question
            current_q = line.split(':', 1)[1].strip()
            current_options = []
        # Detect option lines
        elif line.startswith(('A)', 'B)', 'C)', 'D)', 'A.', 'B.', 'C.', 'D.')):
            option_text = line[2:].strip()
            # Remove "CORRECT" markers if present
            option_text = option_text.replace('- CORRECT', '').replace('[CORRECT]', '').strip()
            current_options.append(option_text)
    
    # Add last question
    if current_q and len(current_options) >= 2:
        questions.append({
            'text': current_q,
            'options': current_options[:10],  # Limit to 10 options
            'correct_index': 0
        })
    
    return questions[:50]  # Limit to 50 questions


async def generate_quiz_from_file_text(text: str, user_id: int = None) -> Optional[List[Dict]]:
    """
    Generate quiz questions from raw file text using AI.
    Handles messy formatting, extracting questions and options.
    """
    # 1. Get Config
    config = await get_bot_config()
    
    # 2. Check Global Toggle
    if not config.get('ai_enabled', True):
        return None
        
    # 3. Get API Key
    api_keys = config.get('api_keys', [])
    api_key = api_keys[0] if api_keys else GROQ_API_KEY
    
    if not api_key:
        return None
        
    # 4. Build Prompt
    # Truncate text if too long (approx 6000 chars to fit in context)
    safe_text = text[:6000]
    
    prompt = f"""Extract multiple choice quiz questions from the following text.
The text might be messy (from PDF/DOCX). Find all valid questions.

TEXT CONTENT:
\"\"\"
{safe_text}
\"\"\"

INSTRUCTIONS:
1. Find every question that has at least 2 options.
2. If correct answer is marked (e.g. bold, asterisk, key at end), ensure option A is the correct answer.
3. If no correct answer is indicated, use your knowledge to pick the correct answer and put it as option A.
4. Rewrite the question to be clear and concise.

FORMAT:
For each question found, output EXACTLY like this:
Q: [Question text]
A) [Correct Option]
B) [Distractor 1]
C) [Distractor 2]
D) [Distractor 3]

---
"""

    # 5. Try AI Models
    for model in AI_MODELS[:3]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3, # Lower temperature for extraction
                        "max_tokens": 2500
                    },
                    timeout=aiohttp.ClientTimeout(total=45)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data['choices'][0]['message']['content']
                        
                        # Parse the response using the existing parser
                        # The parser expects Q... lines so we reuse the format
                        questions = _parse_quiz_response(content)
                        if questions and len(questions) > 0:
                            return questions
        except Exception as e:
            print(f"AI File Import error {model}: {e}")
            continue
            
    return None
