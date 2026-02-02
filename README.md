# 🎓 QuizzuzBot - AI-Powered Vocabulary & Quiz Learning Platform


<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Aiogram](https://img.shields.io/badge/Aiogram-3.22.0-green.svg)
![Firebase](https://img.shields.io/badge/Firebase-Admin-orange.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Your intelligent companion for mastering vocabularies and any subject through AI-enhanced flashcards and spaced repetition!**

[Features](#-features) • [Quick Start](#-quick-start) • [Documentation](#-documentation) • [Contributing](#-contributing)

</div>

---
> **LIVE ON** [@Quizzuz_Bot](https://t.me/Quizzuz_Bot)

> **Bot updates on** [telegram channel](https://t.me/Quizzuz)


## 📖 Overview

**QuizzuzBot** is a sophisticated Telegram bot designed to revolutionize the way you learn vocabulary and prepare for exams. Leveraging cutting-edge AI technology, spaced repetition algorithms (SM-2), and gamification elements, QuizzuzBot transforms studying into an engaging and highly effective experience.

Whether you're preparing for IELTS, SAT, or simply expanding your vocabulary, QuizzuzBot provides personalized learning paths, instant AI-powered word lookups, and multiple practice modes to suit your learning style.

### 🎯 Why QuizzuzBot?

- **🤖 AI-Powered**: Groq AI integration for instant vocabulary definitions, translations, and flashcard generation
- **🧠 Smart Learning**: SM-2 spaced repetition algorithm ensures optimal retention
- **🎮 Gamified Experience**: Earn TX coins, build streaks, level up, and compete on leaderboards
- **🌍 Bilingual Support**: Full English and Uzbek language support
- **📊 Progress Tracking**: Comprehensive analytics, daily goals, and performance insights
- **🎯 Multiple Modes**: Flashcards, quizzes, written tests, mix mode, and AI review
- **📱 Accessible**: Learn anytime, anywhere via Telegram

---

## ✨ Features

### 🎓 Core Learning Features

#### **AI Vocabulary Helper** 📖
- Instant word lookups in English ↔ Uzbek
- Comprehensive definitions with pronunciations
- Real-world example sentences
- Direct save to flashcard sets
- Daily limit: 100 lookups, 12/minute

#### **Smart Practice Modes** 🧠
1. **Flashcards** 🃏 - Classic flip-card mode for active recall
2. **Quiz Mode** 🎯 - Native Telegram polls with instant feedback
3. **Mix Mode** 🔀 - MCQ and True/False questions for variety
4. **AI Review** ✨ - AI-generated definition variations to test deep understanding
5. **Written Test** ✏️ - Type answers for better retention
6. **SM-2 Smart Practice** 🧠 - Spaced repetition algorithm shows cards right before you forget them

#### **AI Card Generation** ✨
- Input a list of words → AI creates complete flashcards
- Auto-generates definitions, translations, and examples
- Supports bulk creation (40 cards/day limit)
- Intelligent parsing of various input formats

### 🎮 Gamification & Engagement

#### **Progression System** 📈
- **TX Coins** 💰 - Earn by practicing, creating sets, and playing games
- **XP & Levels** 🌟 - Progress through ranks: Bronze → Silver → Gold → Platinum → Diamond → Master → Grand Master → Legend → Ultimate → Cosmic Teacher
- **Streaks** 🔥 - Build daily practice streaks with freeze protection
- **Daily Goals** 🎯 - Complete 20 cards/day for bonus rewards
- **Leaderboards** 🏆 - Compete with friends and see top performers

#### **Word Scramble Game** 🎮
- Fun word puzzle mini-game
- Multiple difficulty levels
- Earn TX coins and XP
- Daily challenges with bonus rewards
- Real-time leaderboard

### 📚 Content Management

#### **Library System**
- **My Library** 📝 - Personal flashcard sets
  - Create manually, via CSV, or with AI
  - Organize into books with descriptions
  - Public/Private visibility options
  - Submit to community library
  
- **Official Library** 📚 - Curated content
  - IELTS, SAT, and exam prep sets
  - Community-contributed quality sets
  - Organized by topics and difficulty

#### **Flexible Input Methods**
1. **Manual Entry** - One-by-one card creation
2. **Bulk Import** - Paste term-definition pairs
3. **CSV Upload** - Import spreadsheets
4. **AI Generation** - Automated flashcard creation
5. **Quiz Builder** - Custom quiz creation from topics or files

#### **Export Options** 📄
- Export any set as **PDF** or **DOCX**
- Perfect for printing or offline study
- Formatted and ready to share

### 🔔 Smart Notifications

#### **Intelligent Nudges**
- Daily practice reminders
- Streak protection alerts
- Due card notifications (SM-2 based)
- Daily goal progress updates
- New feature announcements

#### **Personalized Messages**
- Respects user activity patterns
- Won't spam active users
- Tailored to user progress and goals
- Bilingual support

### 👥 Social & Collaboration

- **Group Play** 🎲 - Take quizzes in group chats
- **Referral System** 🤝 - Invite friends and earn 20 TX per referral
- **Content Sharing** - Submit sets to public library
- **Favorites** ⭐ - Bookmark and quickly access favorite sets

### 🛠️ Admin Features

- **Broadcast System** 📢 - Send announcements with variable personalization
- **Content Moderation** - Review and approve public submissions
- **User Management** - Ban/unban users, view analytics
- **Book Management** - Create and organize official content
- **Analytics Dashboard** - Monitor bot usage and engagement

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Firebase Project with Firestore enabled
- Groq API Key (for AI features)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/Quizzuz-Bot.git
   cd Quizzuz-Bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   BOT_TOKEN=your_telegram_bot_token_here
   GROQ_API_KEY=your_groq_api_key_here
   ADMIN_ID=your_telegram_user_id,another_admin_id
   GAME_URL=https://your-deployment-url.com/game/hexagame/index.html
   PORT=8080
   RENDER_EXTERNAL_URL=https://your-deployment-url.com
   ```

4. **Setup Firebase**
   
   - Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
   - Enable Firestore Database
   - Download the service account key JSON file
   - Save it as `serviceAccountKey.json` in the root directory

5. **Run the bot**
   ```bash
   python main.py
   ```

   You should see:
   ```
   🚀 QuizTeebBot V3.0 Started...
   🌐 Server started on port 8080
   🎮 QuizzWords Game available at http://localhost:8080/game/
   ```

### First Steps

1. Start a chat with your bot on Telegram
2. Send `/start` to initialize your account
3. Explore the main menu:
   - 📖 Try AI Vocabulary to look up words
   - ➕ Create your first flashcard set
   - 🧠 Start practicing
   - 🎮 Play Word Scramble for fun

---

## 📚 Documentation

### Project Structure

```
Quizzuz-Bot/
├── main.py                    # Bot initialization, game API, notifications
├── broadcast.py               # Standalone broadcast script
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (create this)
├── serviceAccountKey.json     # Firebase credentials (create this)
│
├── bot_handlers/              # Command and callback handlers
│   ├── start.py              # /start command, dashboard
│   ├── add_cards.py          # Flashcard creation (manual, bulk, AI, CSV)
│   ├── vocabulary.py         # AI vocabulary lookup
│   ├── practice.py           # All practice modes (flashcards, quiz, SM-2)
│   ├── manage.py             # Set/book management, export
│   ├── explore.py            # Browse public library
│   ├── stats.py              # User statistics
│   ├── profile.py            # User profile display
│   ├── favorites.py          # Favorite sets management
│   ├── leaderboard.py        # Top users leaderboard
│   ├── quiz_builder.py       # Custom quiz creation
│   ├── quiz_studio.py        # Quiz from topic/file
│   ├── group_play.py         # Group quiz functionality
│   ├── settings.py           # Language settings
│   ├── admin.py              # Admin panel, moderation
│   ├── help.py               # Help system
│   └── states.py             # FSM state definitions
│
├── bot_services/              # Core business logic
│   ├── firebase_service.py   # Firestore database operations
│   ├── ai_service.py         # Groq AI integration
│   ├── vocabulary_lookup.py  # Dictionary API wrapper
│   ├── dictionary_service.py # Fallback dictionary service
│   ├── vocabulary_cache.py   # Cache for vocabulary lookups
│   ├── vocab_rate_limiter.py # Rate limiting for AI requests
│   ├── translator.py         # Multi-language support
│   ├── analytics_service.py  # User analytics tracking
│   ├── notifications.py      # Smart notification system
│   ├── export_service.py     # PDF/DOCX export
│   ├── utils.py              # Helper utilities, FSM states
│   └── middleware.py         # Ban check middleware
│
├── game/                      # Word Scramble game
│   ├── game_api.py           # Game backend API
│   └── hexagame/             # Game frontend
│       ├── index.html
│       ├── style.css
│       └── script.js
│
├── assets/                    # Media assets
│   └── fonts/                # Custom fonts for PDF export
│
├── docs/                      # Documentation
│   └── firestore_vocab_cache_schema.md
│
├── en.json                    # English translations
└── uz.json                    # Uzbek translations
```

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize bot, show dashboard |
| `/help` | Show comprehensive help guide |
| `/admin` | Admin panel (admins only) |

### Database Schema (Firestore)

**Collections:**
- `users` - User profiles, XP, streaks, settings
- `sets` - Flashcard sets (user and official)
- `books` - Book collections for organizing sets
- `cards` - Individual flashcards
- `game_scores` - Word Scramble scores
- `daily_challenges` - Daily challenge completions
- `quiz_explanations` - Cached AI-generated explanations
- `vocab_cache` - Cached vocabulary lookups
- `config` - Bot configuration (AI limits, announcements)

### AI Integration

QuizzuzBot uses **Groq AI** with automatic model fallback:

**Priority Models:**
1. `llama-3.3-70b-versatile` (Primary)
2. `llama-3.1-70b-versatile` (Secondary)
3. `gemma2-9b-it` (Tertiary)
4. `mixtral-8x7b-32768` (Quaternary)
5. `llama3-8b-8192` (Final fallback)

**Features:**
- Automatic fallback on rate limits or errors
- Daily usage tracking per user
- Admin notifications on limit reached
- Separate limits for card generation and vocabulary

### Broadcasting

Two methods available:

1. **Terminal Script** (Recommended)
   ```bash
   python broadcast.py
   ```
   - Dynamic personalization with variables
   - Preview before sending
   - Real-time progress tracking
   
2. **In-Bot Admin Panel**
   - `/admin` → Broadcast
   - Supports media attachments
   - Same variable support

**Available Variables:**
- `{user_first_name}` - User's name
- `{level}` - Current level
- `{streak}` - Streak days
- `{xp}` - TX coins balance
- `{user_id}` - Telegram user ID

See [README_BROADCAST.md](README_BROADCAST.md) for detailed guide.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot API token | ✅ Yes |
| `GROQ_API_KEY` | Groq AI API key | ✅ Yes |
| `ADMIN_ID` | Comma-separated admin user IDs | ✅ Yes |
| `GAME_URL` | Full URL to word game | ⚠️ For game feature |
| `PORT` | Server port (default 8080) | ❌ No |
| `RENDER_EXTERNAL_URL` | External URL for keep-alive | ❌ No |

---

## 🎨 Features in Detail

### Spaced Repetition (SM-2 Algorithm)

QuizzuzBot implements the **SuperMemo SM-2 algorithm** for optimal learning:

**How it works:**
1. Cards are scheduled based on your performance
2. Rate each card: Again, Hard, Good, Easy, Mastered
3. Better ratings = longer intervals before next review
4. Cards appear right before you're likely to forget them

**Benefits:**
- Scientifically proven to improve long-term retention
- Focuses your time on difficult material
- Reduces unnecessary reviews of well-known content

### Gamification Details

**TX Coins** 💰
- Earn from: Correct answers (+0.5 TX), daily goals (+5 TX), referrals (+20 TX), word game
- Spend on: Streak freezes (150 TX), future shop items

**XP & Levels** 🌟
```
Level  1: Bronze I         (0 XP)
Level  5: Silver III       (500 XP)
Level 10: Gold V           (2,000 XP)
Level 15: Platinum II      (6,000 XP)
Level 20: Diamond I        (15,000 XP)
Level 25: Master III       (35,000 XP)
Level 30: Grand Master     (70,000 XP)
Level 35: Legend           (150,000 XP)
Level 40: Ultimate         (300,000 XP)
Level 45: Cosmic Teacher   (500,000+ XP)
```

**Streaks** 🔥
- Practice daily to maintain your streak
- Miss a day? Streak resets to 1
- Use Streak Freezes to protect your progress
- Smart notifications remind you when at risk

---

## 🔧 Deployment

### Render (Recommended)

1. Fork this repository
2. Create a new Web Service on [Render](https://render.com)
3. Connect your GitHub repository
4. Set environment variables in Render dashboard
5. Upload `serviceAccountKey.json` as a secret file
6. Deploy!

**Start Command:**
```bash
python main.py
```

### Heroku

1. Install Heroku CLI
2. Create a new Heroku app
3. Set config vars (environment variables)
4. Add Firebase credentials
5. Deploy:
   ```bash
   git push heroku main
   ```

### VPS (Ubuntu/Debian)

1. Install Python 3.8+
2. Clone repository
3. Install dependencies
4. Setup systemd service for auto-restart
5. Configure nginx reverse proxy (optional)

**Systemd Service Example:**
```ini
[Unit]
Description=QuizzuzBot Telegram Bot
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/Quizzuz-Bot
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 🤝 Contributing

We welcome contributions! Here's how you can help:

### Ways to Contribute

1. **🐛 Report Bugs** - Found an issue? [Open an issue](https://github.com/doniyor117/Quizzuz-Bot/issues)
2. **💡 Suggest Features** - Have ideas? We'd love to hear them!
3. **📝 Improve Documentation** - Help make our docs better
4. **🔧 Submit Pull Requests** - Fix bugs or add features

### Development Setup

1. Fork the repository
2. Create a feature branch
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. Make your changes
4. Test thoroughly
5. Commit with clear messages
   ```bash
   git commit -m "Add amazing feature"
   ```
6. Push to your fork
   ```bash
   git push origin feature/amazing-feature
   ```
7. Open a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable names
- Comment complex logic
- Keep functions focused and modular
- Update documentation for new features

---

## 📊 Bot Statistics

*Current stats (as of Feb 2026):*
- **Active Users:** Growing daily
- **Flashcard Sets:** 1000+ public sets
- **Cards Studied:** Millions
- **Languages Supported:** 2 (English, Uzbek)
- **AI Requests Daily:** Thousands
- **Average User Streak:** 7 days

---

## 🆘 Troubleshooting

### Common Issues

**Bot doesn't respond:**
- Check `BOT_TOKEN` is correct
- Verify bot is running (`python main.py`)
- Check server/hosting logs

**AI features not working:**
- Verify `GROQ_API_KEY` is valid
- Check if daily limit reached (resets at 00:00 UTC)
- Ensure API key has credits

**Firebase errors:**
- Verify `serviceAccountKey.json` is correct
- Check Firestore is enabled in Firebase Console
- Ensure billing is set up (Firebase free tier is usually sufficient)

**Game not loading:**
- Verify `GAME_URL` points to correct deployment
- Check server is accessible
- Ensure static files are served correctly

### Getting Help

- 📧 Email: doniyor@lucentra.uz
- 💬 Telegram: [@QuizzuzSupport](https://t.me/QuizzuzSupport)
- 🐛 Issues: [GitHub Issues](https://github.com/doniyor117/Quizzuz-Bot/issues)

---

## 📜 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.


## 🙏 Acknowledgments

- **Groq AI** - For lightning-fast AI inference
- **Google Firebase** - For robust backend infrastructure
- **Aiogram** - For excellent Telegram Bot API framework
- **SuperMemo** - For the SM-2 spaced repetition algorithm
- **Contributors** - [To'rabek](http://github.com/t6rabek/) and everyone who has helped improve Quizzuz_Bot

---

## 🗺️ Roadmap

### Upcoming Features

- [ ] **Multi-language Support** - Add more languages (Russian, Spanish, etc.)
- [ ] **Image Cards** - Support images in flashcards
- [ ] **Voice Practice** - Pronunciation practice mode
- [ ] **Study Groups** - Collaborative learning features
- [ ] **Mobile App** - Native iOS/Android apps
- [ ] **Advanced Analytics** - Detailed learning insights
- [ ] **Custom Themes** - Personalize bot appearance
- [ ] **Marketplace** - Buy/sell premium flashcard sets
- [ ] **Integration** - Connect with Anki, Quizlet, etc.
- [ ] **Offline Mode** - Download sets for offline study

---

## 📞 Contact

**QuizzuzBot Team**
- 📧 Email: doniyor@lucentra.uz
- 💬 Telegram: [@Quizzuz_Bot](https://t.me/Quizzuz_Bot)
---

<div align="center">

**Made with ❤️ by the QuizzuzBot Team**

⭐ **Star this repo if you find it helpful!** ⭐

[Report Bug](https://github.com/doniyor117/Quizzuz-Bot/issues) · [Request Feature](https://github.com/doniyor117/Quizzuz-Bot/issues) · [Documentation](https://github.com/doniyor117/Quizzuz-Bot/wiki)

</div>




