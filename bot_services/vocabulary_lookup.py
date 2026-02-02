"""
Vocabulary Lookup Orchestrator

Master function that coordinates all vocabulary lookup logic:
1. Cache check
2. AI upgrade if applicable
3. Rate-limited AI lookup (3-model fallback)
4. Dictionary API fallback
5. Cache result
"""

from typing import Optional, Dict
from bot_services.vocabulary_cache import (
    get_from_cache,
    save_to_cache,
    upgrade_cache_entry
)
from bot_services.vocab_rate_limiter import (
    check_vocab_rate_limit,
    increment_vocab_usage
)
from bot_services.ai_service import generate_vocabulary_ai
from bot_services.dictionary_service import lookup_vocabulary

async def lookup_word_smart(word: str, user_id: int) -> Optional[Dict]:
    """
    Intelligent vocabulary lookup with caching and multi-tier fallbacks.
    
    Flow:
    1. Check cache
       - If AI-sourced → return immediately
       - If dict-sourced + user has quota → upgrade to AI
    2. If not cached, check rate limits
    3. Try AI models (3-tier fallback)
    4. Fallback to dictionary API
    5. Cache result
    
    Args:
        word: The word to look up
        user_id: User ID for rate limiting
        
    Returns:
        {
            'word': str,
            'definition': str,
            'translation_uz': str,
            'translation_en': str,
            'examples': list,
            'phonetic': str,
            'source': 'cache_ai' | 'cache_dict' | 'ai' | 'dict',
            'from_cache': bool,
            'upgraded': bool,
            'quota_used': bool
        }
    """
    
    # STEP 1: Check cache
    cached = await get_from_cache(word)
    
    if cached:
        # Found in cache
        source_type = cached.get('source_type', '')
        
        if source_type == 'ai':
            # AI cache hit - best case, return immediately
            return {
                **cached,
                'source': 'cache_ai',
                'from_cache': True,
                'upgraded': False,
                'quota_used': False
            }
        
        elif source_type == 'dict':
            # Dictionary cache - try to upgrade if user has quota
            allowed, remaining_min, remaining_day = await check_vocab_rate_limit(user_id)
            
            if allowed:
                # User has quota, try AI upgrade
                ai_result = await generate_vocabulary_ai(word)
                
                if ai_result:
                    # Upgrade successful!
                    await upgrade_cache_entry(word, ai_result)
                    await increment_vocab_usage(user_id)
                    
                    return {
                        'word': word,
                        'definition': ai_result.get('definition', ''),
                        'translation_uz': ai_result.get('translation', ''),
                        'translation_en': ai_result.get('translation_en', ''),
                        'examples': ai_result.get('examples', []),
                        'phonetic': ai_result.get('phonetic', ''),
                        'source': 'ai',
                        'from_cache': False,
                        'upgraded': True,  # Special flag!
                        'quota_used': True
                    }
            
            # No quota or AI failed, return dict cache
            return {
                **cached,
                'source': 'cache_dict',
                'from_cache': True,
                'upgraded': False,
                'quota_used': False
            }
    
    # STEP 2: Not in cache, check rate limits
    allowed, remaining_min, remaining_day = await check_vocab_rate_limit(user_id)
    
    # STEP 3: Try AI if quota available
    if allowed:
        ai_result = await generate_vocabulary_ai(word)
        
        if ai_result:
            # AI success! Cache and return
            await save_to_cache(word, ai_result, 'ai')
            await increment_vocab_usage(user_id)
            
            return {
                'word': word,
                'definition': ai_result.get('definition', ''),
                'translation_uz': ai_result.get('translation', ''),
                'translation_en': ai_result.get('translation_en', ''),
                'examples': ai_result.get('examples', []),
                'phonetic': ai_result.get('phonetic', ''),
                'source': 'ai',
                'from_cache': False,
                'upgraded': False,
                'quota_used': True
            }
    
    # STEP 4: Fallback to dictionary API
    dict_result = await lookup_vocabulary(word)
    
    if dict_result and dict_result.get('has_definition'):
        # Dictionary found something
        standardized = _standardize_dict_format(dict_result)
        await save_to_cache(word, standardized, 'dict')
        
        return {
            **standardized,
            'source': 'dict',
            'from_cache': False,
            'upgraded': False,
            'quota_used': False
        }
    
    # STEP 5: Nothing found
    return None

def _standardize_dict_format(dict_result: Dict) -> Dict:
    """Convert dictionary API result to standard format."""
    definition_data = dict_result.get('definition_data', {})
    
    # Extract definition
    definitions = definition_data.get('definitions', []) if definition_data else []
    definition_text = definitions[0] if definitions else ''
    
    # Extract examples
    examples = definition_data.get('examples', []) if definition_data else []
    
    return {
        'word': dict_result.get('word', ''),
        'definition': definition_text,
        'translation': dict_result.get('en_to_uz', ''),
        'translation_en': dict_result.get('uz_to_en', ''),
        'examples': examples[:2],  # Max 2 examples
        'phonetic': definition_data.get('phonetic', '') if definition_data else ''
    }
