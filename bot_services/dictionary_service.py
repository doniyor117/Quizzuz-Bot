import aiohttp
from typing import Optional, Dict, List

# ===== FREE DICTIONARY API =====
async def get_word_definition(word: str) -> Optional[Dict]:
    """
    Fetch word definition from Free Dictionary API.
    Returns: dict with 'word', 'phonetic', 'meanings', 'examples'
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        entry = data[0]
                        
                        # Extract definitions
                        definitions = []
                        examples = []
                        
                        for meaning in entry.get('meanings', []):
                            part_of_speech = meaning.get('partOfSpeech', '')
                            for definition in meaning.get('definitions', [])[:2]:  # Max 2 definitions per part of speech
                                def_text = definition.get('definition', '')
                                if def_text:
                                    definitions.append(f"({part_of_speech}) {def_text}")
                                
                                example = definition.get('example')
                                if example and len(examples) < 2:  # Max 2 examples total
                                    examples.append(example)
                        
                        return {
                            'word': entry.get('word', word),
                            'phonetic': entry.get('phonetic', ''),
                            'definitions': definitions[:3],  # Max 3 definitions
                            'examples': examples
                        }
                return None
    except Exception as e:
        print(f"Dictionary API error: {e}")
        return None


# ===== MYMEMORY TRANSLATION API =====
async def translate_word(text: str, from_lang: str = "en", to_lang: str = "uz") -> Optional[str]:
    """
    Translate text using MyMemory Translation API.
    Supports: en <-> uz
    Returns: translated text or None
    """
    # MyMemory uses language codes: en-US, uz-UZ
    lang_pair = f"{from_lang}|{to_lang}"
    url = f"https://api.mymemory.translated.net/get?q={text}&langpair={lang_pair}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('responseStatus') == 200:
                        translated = data.get('responseData', {}).get('translatedText')
                        return translated
                return None
    except Exception as e:
        print(f"Translation API error: {e}")
        return None


# ===== BIDIRECTIONAL TRANSLATION =====
async def get_translation_both_ways(word: str) -> Dict[str, Optional[str]]:
    """
    Get translation in both directions (en->uz and uz->en).
    Returns: {'en_to_uz': str, 'uz_to_en': str}
    """
    en_to_uz = await translate_word(word, "en", "uz")
    uz_to_en = await translate_word(word, "uz", "en")
    
    return {
        'en_to_uz': en_to_uz,
        'uz_to_en': uz_to_en
    }


# ===== COMBINED LOOKUP =====
async def lookup_vocabulary(word: str) -> Dict:
    """
    Complete vocabulary lookup: definition + translation.
    Returns comprehensive vocabulary data.
    """
    # Try to get English definition
    definition_data = await get_word_definition(word)
    
    # Get translations
    translations = await get_translation_both_ways(word)
    
    return {
        'word': word,
        'definition_data': definition_data,
        'en_to_uz': translations.get('en_to_uz'),
        'uz_to_en': translations.get('uz_to_en'),
        'has_definition': definition_data is not None,
        'has_translation': any(translations.values())
    }
