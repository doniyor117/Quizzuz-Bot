import json
import os

class Translator:
    def __init__(self):
        self.languages = {}
        self.load_languages()

    def load_languages(self):
        for lang in ['en', 'uz']:
            try:
                with open(f'{lang}.json', 'r', encoding='utf-8') as f:
                    self.languages[lang] = json.load(f)
            except FileNotFoundError:
                print(f"Warning: {lang}.json not found.")
                self.languages[lang] = {}

    def get_text(self, key, lang_code='en', **kwargs):
        # Fallback to EN if key missing in target lang
        lang_data = self.languages.get(lang_code, self.languages['en'])
        text = lang_data.get(key, self.languages['en'].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except:
                return text
        return text

tr = Translator()