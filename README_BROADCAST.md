# 📢 Broadcast System Guide

The QuizTeeb Bot has two ways to send broadcast messages to all users:

## Method 1: Terminal Script (Recommended for Dynamic Messages)

### Features

- ✨ Dynamic personalization with user variables
- 📋 Preview before sending
- 📊 Real-time progress tracking
- 🔄 Multi-line message support

### Usage

1. Run the broadcast script:

```bash
python broadcast.py
```

2. Enter your message with variables:

```
Assalomu alaykum {user_first_name}! 👋

We are happy that you are using our bot. You are currently level {level} with a {streak}-day streak!

Keep learning! 🎉
```

3. Review the preview and confirm

### Available Variables

| Variable            | Description       | Example     |
| ------------------- | ----------------- | ----------- |
| `{user_first_name}` | User's first name | "Ali"       |
| `{user_id}`         | Telegram user ID  | "123456789" |
| `{level}`           | Current level     | "5"         |
| `{streak}`          | Current streak    | "7"         |
| `{xp}`              | TX coins balance  | "150.5"     |

### Examples

**Simple Welcome:**

```
Assalomu alaykum {user_first_name}! 👋
We are happy that you are using our bot.
```

**Motivational Message:**

```
Hey {user_first_name}! 🌟

You're doing amazing at level {level}!
Your {streak}-day streak shows real dedication.

Keep it up! 💪
```

**Update Announcement:**

```
Hi {user_first_name}!

🎉 New features are here!

Check them out and earn more TX coins.
Current balance: {xp} TX

Happy learning! 📚
```

---

## Method 2: In-Bot Admin Panel

### Features

- 🤖 Accessible via Telegram bot
- 📱 Easy to use
- 🎨 Supports media (photos, videos)

### Usage

1. Send `/admin` command to the bot
2. Click **📢 Broadcast** button
3. Type your message
4. Message will be sent to all users

### Personalization in Admin Panel

The admin panel now supports the same variables as the terminal script:

```
Assalomu alaykum {user_first_name}!

You are level {level} with {xp} TX coins.
Keep up your {streak}-day streak! 🔥
```

When you use variables, you'll see:

- ✅ A preview of how the message will look
- 📊 Confirmation button before sending
- 📈 Detailed delivery report

---

## Tips

### ✅ Best Practices

1. **Personalize**: Use `{user_first_name}` to make messages feel personal
2. **Keep it short**: Users prefer concise messages
3. **Add value**: Share updates, tips, or motivation
4. **Use emojis**: Make messages more engaging 🎉
5. **Test first**: Send to yourself first to check formatting

### ⚠️ Important Notes

- Messages support Markdown formatting (`**bold**`, `*italic*`)
- Broadcasts have anti-flood protection (50ms delay between messages)
- Blocked users are counted separately in the report
- Terminal script shows progress every 10 users

### 📊 Understanding Reports

After broadcast, you'll see:

- **✅ Sent**: Successfully delivered messages
- **❌ Failed**: Temporary errors (network, etc.)
- **🚫 Blocked**: Users who blocked the bot
- **📊 Total**: All users in database

---

## Troubleshooting

**"Failed to send" errors:**

- Check your BOT_TOKEN in `.env`
- Verify Firebase connection
- Check internet connection

**Users not receiving:**

- They may have blocked the bot
- Check if they started the bot at least once

**Variables not replacing:**

- Use exact variable names: `{user_first_name}` not `{firstname}`
- Check for typos in variable names
- Variables are case-sensitive

---

## Examples from Usage

### Daily Motivation (Uzbek)

```
Assalomu alaykum {user_first_name}! 🌅

Bugun ham yangi so'zlar o'rganing!
Sizning {streak} kunlik izchil ishingiz ajoyib! 🔥

Darajangiz: {level} | TX: {xp}
```

### Feature Announcement (English)

```
Hi {user_first_name}! 🎉

We've just added new features to help you learn faster!

Your stats:
• Level: {level}
• Streak: {streak} days
• TX Coins: {xp}

Try them now! 🚀
```

### Weekly Challenge

```
Hey {user_first_name}! 💪

Weekly Challenge: Review 50 cards!

Current Progress:
📊 Level {level}
🔥 {streak}-day streak
💰 {xp} TX coins

You got this! 🎯
```

---

Need help? Contact the development team or check the main documentation.
