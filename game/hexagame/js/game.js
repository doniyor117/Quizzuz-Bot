/* Word Scramble - Game Logic */

(function () {
    'use strict';

    // ===== WORD LISTS BY DIFFICULTY =====
    const WORDS = {
        easy: [
            // 3-4 letter simple words (100+ words)
            'cat', 'dog', 'sun', 'hat', 'cup', 'bed', 'box', 'map', 'pen', 'red',
            'run', 'sit', 'top', 'wet', 'win', 'yes', 'zip', 'ace', 'age', 'air',
            'ant', 'arm', 'art', 'bag', 'bat', 'bee', 'big', 'bit', 'bow', 'boy',
            'bus', 'buy', 'cab', 'can', 'car', 'cow', 'cry', 'cut', 'dad', 'day',
            'dig', 'dot', 'dry', 'ear', 'eat', 'egg', 'end', 'eye', 'fan', 'far',
            'fat', 'fig', 'fit', 'fix', 'fog', 'fox', 'fun', 'gap', 'gas', 'get',
            'god', 'got', 'gum', 'gun', 'gut', 'gym', 'ham', 'hen', 'hid', 'hit',
            'hop', 'hot', 'hug', 'ice', 'ill', 'ink', 'inn', 'ion', 'jam', 'jar',
            'jaw', 'jet', 'job', 'jog', 'joy', 'jug', 'key', 'kid', 'kit', 'lab',
            'lap', 'law', 'lay', 'led', 'leg', 'let', 'lid', 'lip', 'log', 'lot',
            'low', 'mad', 'man', 'mat', 'max', 'men', 'met', 'mix', 'mob', 'mom',
            'mop', 'mud', 'mug', 'nap', 'net', 'new', 'nod', 'nor', 'not', 'now',
            'nut', 'oak', 'odd', 'off', 'oil', 'old', 'one', 'orb', 'ore', 'our',
            'out', 'owe', 'owl', 'own', 'pad', 'pan', 'pat', 'paw', 'pay', 'pea',
            'pet', 'pie', 'pig', 'pin', 'pit', 'pod', 'pop', 'pot', 'pub', 'pun'
        ],
        moderate: [
            // 5-6 letter common words (100+ words)
            'apple', 'beach', 'brain', 'bread', 'chair', 'chest', 'clock', 'cloud',
            'dance', 'drink', 'earth', 'fight', 'flame', 'flash', 'floor', 'fruit',
            'ghost', 'glass', 'grape', 'grass', 'green', 'happy', 'heart', 'house',
            'juice', 'knife', 'lemon', 'light', 'money', 'month', 'mouse', 'music',
            'night', 'ocean', 'paint', 'party', 'peace', 'phone', 'piano', 'pizza',
            'plant', 'queen', 'quick', 'river', 'robot', 'salad', 'sheep', 'shine',
            'shirt', 'shoes', 'sleep', 'smile', 'smoke', 'snake', 'space', 'speed',
            'spoon', 'sport', 'stamp', 'stand', 'steam', 'steel', 'stone', 'store',
            'storm', 'story', 'sugar', 'sweet', 'table', 'teeth', 'tiger', 'toast',
            'train', 'truck', 'truth', 'video', 'watch', 'water', 'wheel', 'world',
            'album', 'alert', 'angle', 'ankle', 'arrow', 'badge', 'basic', 'beard',
            'beast', 'bench', 'birth', 'blade', 'blame', 'blank', 'blast', 'blaze',
            'bleed', 'blend', 'blind', 'block', 'blood', 'bloom', 'board', 'boast',
            'bonus', 'boost', 'bound', 'bowel', 'brain', 'brake', 'brand', 'brave',
            'bride', 'brief', 'bring', 'broad', 'broke', 'brook', 'brown', 'brush',
            'build', 'bunch', 'burst', 'cabin', 'cable', 'candy', 'cargo', 'carry',
            'carve', 'catch', 'cause', 'chain', 'chalk', 'charm', 'chart', 'chase',
            'cheap', 'check', 'cheek', 'cheer', 'chess', 'child', 'chill', 'china',
            'chunk', 'civic', 'claim', 'class', 'clean', 'clear', 'clerk', 'click',
            'cliff', 'climb', 'close', 'cloth', 'coach', 'coast', 'coral', 'couch'
        ],
        hard: [
            // 7+ letter challenging words (100+ words)
            'absolute', 'abstract', 'academic', 'accident', 'accurate', 'achieve',
            'acquired', 'activate', 'addition', 'adequate', 'adjacent', 'advanced',
            'adventure', 'advocate', 'affected', 'aircraft', 'alliance', 'allocate',
            'although', 'aluminum', 'american', 'analysis', 'announce', 'anything',
            'anywhere', 'apparent', 'appetite', 'approach', 'approval', 'argument',
            'artistic', 'assembly', 'assuming', 'athletic', 'attached', 'attorney',
            'audience', 'bachelor', 'backward', 'bacteria', 'balanced', 'baseball',
            'bathroom', 'becoming', 'behavior', 'bellying', 'benefits', 'birthday',
            'boarding', 'boundary', 'breaking', 'breeding', 'briefing', 'brilliant',
            'bringing', 'brochure', 'brothers', 'browsers', 'brunette', 'building',
            'bulletin', 'business', 'calendar', 'campaign', 'capacity', 'category',
            'centered', 'ceremony', 'chairman', 'champion', 'changing', 'chapters',
            'charging', 'charming', 'checking', 'chemical', 'children', 'choosing',
            'circular', 'cipline', 'citizens', 'claiming', 'cleaning', 'climbing',
            'clothing', 'coaching', 'collapse', 'colonial', 'colorful', 'combined',
            'comeback', 'commerce', 'commonly', 'compared', 'compiler', 'complete',
            'composed', 'compound', 'computer', 'conclude', 'concrete', 'conflict',
            'confused', 'congress', 'consider', 'constant', 'consumer', 'contains',
            'continue', 'contract', 'contrast', 'controls', 'convince', 'corridor',
            'counting', 'covering', 'creative', 'creature', 'criminal', 'critical'
        ]
    };

    // ===== GAME STATE =====
    let state = {
        currentWord: '',
        scrambledWord: '',
        difficulty: 'moderate',
        score: 0,
        streak: 0,
        lives: 3,
        wordsSolved: 0,
        timeLeft: 60,
        timerInterval: null,
        isPlaying: false,
        usedWords: []
    };

    // ===== DOM ELEMENTS =====
    const elements = {
        // Screens
        menuScreen: document.getElementById('menuScreen'),
        gameScreen: document.getElementById('gameScreen'),
        leaderboardScreen: document.getElementById('leaderboardScreen'),
        gameOverOverlay: document.getElementById('gameOverOverlay'),

        // Menu buttons - Difficulty
        btnEasy: document.getElementById('btnEasy'),
        btnModerate: document.getElementById('btnModerate'),
        btnHard: document.getElementById('btnHard'),
        btnLeaderboard: document.getElementById('btnLeaderboard'),
        btnQuit: document.getElementById('btnQuit'),

        // Game elements
        scrambledWord: document.getElementById('scrambledWord'),
        answerInput: document.getElementById('answerInput'),
        btnSubmit: document.getElementById('btnSubmit'),
        btnSkip: document.getElementById('btnSkip'),
        btnQuitGame: document.getElementById('btnQuitGame'),
        gameScore: document.getElementById('gameScore'),
        gameTimer: document.getElementById('gameTimer'),
        gameStreak: document.getElementById('gameStreak'),
        gameLives: document.getElementById('gameLives'),
        feedback: document.getElementById('feedback'),

        // Game over
        finalScore: document.getElementById('finalScore'),
        wordsSolved: document.getElementById('wordsSolved'),
        txEarned: document.getElementById('txEarned'),
        btnPlayAgain: document.getElementById('btnPlayAgain'),
        btnBackToMenu: document.getElementById('btnBackToMenu'),

        // Leaderboard
        leaderboardContent: document.getElementById('leaderboardContent'),
        btnBackFromLeaderboard: document.getElementById('btnBackFromLeaderboard'),

        // TX Display
        txAmount: document.getElementById('txAmount')
    };

    // ===== TELEGRAM INTEGRATION =====
    const telegram = {
        app: window.Telegram?.WebApp,
        userId: null,
        userName: 'Player',
        isInTelegram: false,
        sessionScore: 0,
        scoreSubmitted: false,

        init() {
            if (this.app) {
                this.isInTelegram = true;
                this.app.ready();
                this.app.expand();

                if (this.app.initDataUnsafe?.user) {
                    this.userId = this.app.initDataUnsafe.user.id;
                    this.userName = this.app.initDataUnsafe.user.first_name || 'Player';
                }

                // Handle back button
                this.app.BackButton.show();
                this.app.BackButton.onClick(() => {
                    this.submitScoreAndClose();
                });

                // Handle closing
                this.app.onEvent('viewportChanged', () => {
                    if (!this.app.isExpanded && this.sessionScore > 0 && !this.scoreSubmitted) {
                        this.submitScore();
                    }
                });

                // Fetch user stats
                this.fetchUserStats();
            }

            console.log('🎮 Word Scramble initialized', this.isInTelegram ? 'in Telegram' : 'in browser');
        },

        async fetchUserStats() {
            try {
                const response = await fetch(`/api/game/user-stats?user_id=${this.userId}`, {
                    headers: { 'X-User-Id': String(this.userId || '') }
                });
                const data = await response.json();
                elements.txAmount.textContent = data.tx || 0;
            } catch (e) {
                console.error('Failed to fetch user stats:', e);
            }
        },

        async submitScore(callback) {
            if (this.scoreSubmitted || this.sessionScore <= 0) {
                if (callback) callback();
                return;
            }

            this.scoreSubmitted = true;
            const txEarned = Math.floor(this.sessionScore / 20);  // Reduced rewards

            try {
                await fetch('/api/game/submit-score', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-User-Id': String(this.userId || '')
                    },
                    body: JSON.stringify({
                        user_id: this.userId || 'debug_user',
                        user_name: this.userName,
                        score: this.sessionScore,
                        words: state.wordsSolved,
                        tx_earned: txEarned
                    })
                });
                console.log('✅ Score submitted:', this.sessionScore);
            } catch (e) {
                console.error('Failed to submit score:', e);
            }

            if (callback) callback();
        },

        submitScoreAndClose() {
            this.submitScore(() => {
                if (this.isInTelegram) {
                    this.app.close();
                }
            });
        },

        addScore(points) {
            this.sessionScore += points;
        }
    };

    // ===== UTILITY FUNCTIONS =====
    function scrambleWord(word) {
        let arr = word.split('');
        let scrambled = word;

        // Keep scrambling until it's different from original
        let attempts = 0;
        while (scrambled === word && attempts < 20) {
            for (let i = arr.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [arr[i], arr[j]] = [arr[j], arr[i]];
            }
            scrambled = arr.join('');
            attempts++;
        }

        return scrambled.toUpperCase();
    }

    function getRandomWord() {
        // Get word list for current difficulty
        const wordList = WORDS[state.difficulty];

        // Get words not yet used
        const available = wordList.filter(w => !state.usedWords.includes(w));

        // Reset if we've used all words
        if (available.length === 0) {
            state.usedWords = [];
            return wordList[Math.floor(Math.random() * wordList.length)];
        }

        return available[Math.floor(Math.random() * available.length)];
    }

    function showScreen(screenElement) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        screenElement.classList.add('active');
    }

    function updateDisplay() {
        elements.gameScore.textContent = state.score;
        elements.gameTimer.textContent = state.timeLeft;
        elements.gameStreak.textContent = state.streak;

        // Update lives display (Hearts)
        let hearts = '';
        for (let i = 0; i < 3; i++) {
            hearts += i < state.lives ? '❤️' : '🖤';
        }
        elements.gameLives.textContent = hearts;
    }

    function showFeedback(message, isCorrect) {
        elements.feedback.textContent = message;
        elements.feedback.className = 'feedback ' + (isCorrect ? 'correct' : 'wrong');

        setTimeout(() => {
            elements.feedback.textContent = '';
            elements.feedback.className = 'feedback';
        }, 1000);
    }

    // ===== GAME FUNCTIONS =====
    function startGame(difficulty = 'moderate') {
        state = {
            currentWord: '',
            scrambledWord: '',
            difficulty: difficulty,
            score: 0,
            streak: 0,
            lives: 3,
            wordsSolved: 0,
            timeLeft: 60,
            timerInterval: null,
            isPlaying: true,
            usedWords: []
        };

        telegram.sessionScore = 0;
        telegram.scoreSubmitted = false;

        showScreen(elements.gameScreen);
        updateDisplay();
        nextWord();
        startTimer();

        elements.answerInput.focus();
    }

    function nextWord() {
        state.currentWord = getRandomWord();
        state.scrambledWord = scrambleWord(state.currentWord);
        state.usedWords.push(state.currentWord);

        elements.scrambledWord.textContent = state.scrambledWord;
        elements.answerInput.value = '';
        elements.answerInput.focus();

        // Add pop animation
        elements.scrambledWord.classList.add('pop');
        setTimeout(() => elements.scrambledWord.classList.remove('pop'), 300);
    }

    function checkAnswer() {
        const answer = elements.answerInput.value.toLowerCase().trim();

        if (answer === state.currentWord) {
            // Correct!
            state.streak++;
            const points = 1 + Math.floor(state.streak * 0.5); // Reduced scoring (was 10 + streak*2)
            state.score += points;
            state.wordsSolved++;

            telegram.addScore(points);

            showFeedback(`+${points} points!`, true);
            updateDisplay();
            nextWord();
        } else if (answer.length >= state.currentWord.length) {
            // Wrong answer
            state.streak = 0;
            state.lives--;

            showFeedback('Wrong!', false);
            elements.answerInput.classList.add('shake');
            setTimeout(() => elements.answerInput.classList.remove('shake'), 300);

            updateDisplay();

            if (state.lives <= 0) {
                setTimeout(endGame, 500);
            }
        }
    }

    function skipWord() {
        // Skip penalty: lose a life and streak
        state.streak = 0;
        state.lives--;

        showFeedback(`It was: ${state.currentWord}`, false);
        updateDisplay();

        if (state.lives <= 0) {
            setTimeout(endGame, 1000);
        } else {
            setTimeout(() => {
                nextWord();
            }, 1000);
        }
    }

    function startTimer() {
        state.timerInterval = setInterval(() => {
            state.timeLeft--;
            elements.gameTimer.textContent = state.timeLeft;

            if (state.timeLeft <= 10) {
                elements.gameTimer.style.color = '#e94560';
            }

            if (state.timeLeft <= 0) {
                endGame();
            }
        }, 1000);
    }

    function endGame() {
        state.isPlaying = false;
        clearInterval(state.timerInterval);

        elements.gameTimer.style.color = '';

        const txEarned = Math.floor(state.score / 10);

        // Update final stats
        elements.finalScore.textContent = state.score;
        elements.wordsSolved.textContent = state.wordsSolved;
        elements.txEarned.textContent = `+${txEarned}`;

        // Submit score
        telegram.submitScore();

        // Show game over
        elements.gameOverOverlay.classList.add('active');
    }

    function quitGame() {
        if (state.isPlaying) {
            clearInterval(state.timerInterval);
            state.isPlaying = false;

            // Submit whatever score they have
            if (state.score > 0) {
                telegram.submitScore();
            }
        }

        elements.gameOverOverlay.classList.remove('active');
        showScreen(elements.menuScreen);
    }

    // ===== LEADERBOARD =====
    async function loadLeaderboard() {
        showScreen(elements.leaderboardScreen);
        elements.leaderboardContent.innerHTML = '<div class="leaderboard-loading">Loading...</div>';

        try {
            const response = await fetch('/api/game/leaderboard?period=daily&limit=10');
            const data = await response.json();

            if (!data.leaderboard || data.leaderboard.length === 0) {
                elements.leaderboardContent.innerHTML = '<div class="leaderboard-loading">No scores yet. Be the first!</div>';
                return;
            }

            let html = '';
            data.leaderboard.forEach((entry, index) => {
                const isCurrentUser = entry.user_id === telegram.userId;
                const rankClass = index === 0 ? 'gold' : index === 1 ? 'silver' : index === 2 ? 'bronze' : '';

                html += `
                    <div class="leaderboard-entry ${isCurrentUser ? 'current-user' : ''}">
                        <div class="leaderboard-rank ${rankClass}">${entry.rank || index + 1}</div>
                        <div class="leaderboard-name">${escapeHtml(entry.name || 'Player')}</div>
                        <div class="leaderboard-score">${entry.score}</div>
                    </div>
                `;
            });

            elements.leaderboardContent.innerHTML = html;
        } catch (e) {
            console.error('Failed to load leaderboard:', e);
            elements.leaderboardContent.innerHTML = '<div class="leaderboard-loading">Failed to load leaderboard</div>';
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ===== EVENT LISTENERS =====
    function setupEventListeners() {
        // Difficulty buttons
        elements.btnEasy.addEventListener('click', () => startGame('easy'));
        elements.btnModerate.addEventListener('click', () => startGame('moderate'));
        elements.btnHard.addEventListener('click', () => startGame('hard'));
        elements.btnLeaderboard.addEventListener('click', loadLeaderboard);
        elements.btnQuit.addEventListener('click', () => telegram.submitScoreAndClose());

        // Game buttons
        elements.btnSubmit.addEventListener('click', checkAnswer);
        elements.btnSkip.addEventListener('click', skipWord);
        elements.btnQuitGame.addEventListener('click', quitGame);

        // Answer input
        elements.answerInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                checkAnswer();
            }
        });

        // Auto-check on input
        elements.answerInput.addEventListener('input', () => {
            const answer = elements.answerInput.value.toLowerCase().trim();
            if (answer === state.currentWord) {
                checkAnswer();
            }
        });

        // Game over buttons
        elements.btnPlayAgain.addEventListener('click', () => {
            elements.gameOverOverlay.classList.remove('active');
            startGame();
        });
        elements.btnBackToMenu.addEventListener('click', () => {
            elements.gameOverOverlay.classList.remove('active');
            showScreen(elements.menuScreen);
        });

        // Leaderboard back button
        elements.btnBackFromLeaderboard.addEventListener('click', () => {
            showScreen(elements.menuScreen);
        });

        // Handle page visibility for score submission
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden' && telegram.sessionScore > 0 && !telegram.scoreSubmitted) {
                telegram.submitScore();
            }
        });

        // Handle page unload
        window.addEventListener('beforeunload', () => {
            if (telegram.sessionScore > 0 && !telegram.scoreSubmitted) {
                telegram.submitScore();
            }
        });
    }

    // ===== INITIALIZE =====
    function init() {
        telegram.init();
        setupEventListeners();
        console.log('🎮 Word Scramble ready!');
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
