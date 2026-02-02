# Firestore Vocabulary Cache Schema

## Collection: `vocabulary_cache`

This collection stores vocabulary lookups to reduce API calls and improve response times.

### Document Structure

**Document ID:** `{word_lowercase}` (e.g., "apple", "serendipity")

**Fields:**

```javascript
{
  // Original word (preserves case)
  "word": string,
  
  // Definition in English
  "definition": string,
  
  // Uzbek translation
  "translation_uz": string,
  
  // English translation (if input was Uzbek)
  "translation_en": string,
  
  // Example sentences
  "examples": array<string>,
  
  // Phonetic pronunciation (optional)
  "phonetic": string,
  
  // Source type: "ai" or "dict"
  "source_type": string,
  
  // When this entry was cached
  "cached_at": timestamp,
  
  // Number of times upgraded from dict to AI
  "upgrade_count": number
}
```

### Example Documents

**AI-sourced entry:**
```json
{
  "word": "Ephemeral",
  "definition": "Lasting for a very short time; transient.",
  "translation_uz": "Vaqtinchalik, o'tkinchi",
  "translation_en": "",
  "examples": [
    "The beauty of the sunset was ephemeral.",
    "Fashion trends are often ephemeral."
  ],
  "phonetic": "/ɪˈfɛm(ə)r(ə)l/",
  "source_type": "ai",
  "cached_at": "2025-11-27T10:30:00Z",
  "upgrade_count": 0
}
```

**Dictionary-sourced entry (before upgrade):**
```json
{
  "word": "apple",
  "definition": "(noun) A round fruit with red, green, or yellow skin",
  "translation_uz": "olma",
  "translation_en": "",
  "examples": [
    "She ate an apple for breakfast."
  ],
  "phonetic": "/ˈapəl/",
  "source_type": "dict",
  "cached_at": "2025-11-27T09:15:00Z",
  "upgrade_count": 0
}
```

**Upgraded entry:**
```json
{
  "word": "apple",
  "definition": "A round fruit with firm white flesh and red, green, or yellow skin, commonly eaten raw or used in cooking.",
  "translation_uz": "olma (daraxt mevasi)",
  "translation_en": "",
  "examples": [
    "An apple a day keeps the doctor away.",
    "The apple tree in our garden produces delicious fruit."
  ],
  "phonetic": "/ˈæpl/",
  "source_type": "ai",
  "cached_at": "2025-11-27T11:00:00Z",
  "upgrade_count": 1
}
```

### Indexes Required

1. **Single Field Index: `source_type`**
   - Collection: `vocabulary_cache`
   - Field: `source_type`
   - Order: Ascending
   - Purpose: Analytics, finding upgradeable entries

2. **Single Field Index: `cached_at`**
   - Collection: `vocabulary_cache`
   - Field: `cached_at`
   - Order: Descending
   - Purpose: Cleanup old entries, analytics

### Cache Behavior

**Lookup Priority:**
1. Check cache by `word.lower()`
2. If `source_type == "ai"`, return immediately
3. If `source_type == "dict"` and user has AI quota, upgrade to AI

**Upgrade Logic:**
- Triggered when user with AI quota searches a dict-cached word
- Original entry is completely replaced with AI version
- `upgrade_count` incremented
- `cached_at` updated to current time
- `source_type` changed to "ai"

### Maintenance

**Cleanup Policy (Future):**
- Keep entries accessed in last 90 days
- Archive rarely-accessed entries
- Monitor storage costs

**Pre-caching (Future):**
- Top 10,000 common English words
- Academic vocabulary lists (IELTS, TOEFL, SAT)
- All cached with AI source for quality
