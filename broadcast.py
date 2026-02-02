"""
Terminal-based Broadcast Script for QuizTeeb Bot
Allows admins to send personalized broadcasts to all users.

Usage:
    python broadcast.py

Features:
    - Dynamic variable replacement: {user_first_name}, {user_id}, {level}, {streak}
    - Preview before sending
    - Progress tracking
    - Error handling
"""

import asyncio
import os
from dotenv import load_dotenv
from bot_services.firebase_service import get_all_users, ADMIN_IDS
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def broadcast_message():
    """Main broadcast function."""
    print("\n" + "="*60)
    print("📢 QUIZTEEB BOT BROADCAST SYSTEM")
    print("="*60)
    print("\nAvailable Variables:")
    print("  {user_first_name} - User's first name")
    print("  {user_id} - User's Telegram ID")
    print("  {level} - User's current level")
    print("  {streak} - User's current streak")
    print("  {xp} - User's TX coins")
    print("\nExample:")
    print("  Assalomu alaykum {user_first_name}! 👋")
    print("  You are currently level {level} with a {streak}-day streak!")
    print("  Keep up the great work! 🎉")
    print("\n" + "-"*60)
    
    # Get message from admin
    print("\n📝 Enter your broadcast message (use variables as shown above):")
    print("(Press Enter twice when done, or type 'cancel' to exit)\n")
    
    lines = []
    while True:
        line = input()
        if line.lower() == 'cancel':
            print("\n❌ Broadcast cancelled.")
            return
        if line == "" and lines and lines[-1] == "":
            lines.pop()  # Remove the last empty line
            break
        lines.append(line)
    
    message_template = "\n".join(lines).strip()
    
    if not message_template:
        print("\n❌ Empty message. Broadcast cancelled.")
        return
    
    # Get all users
    print("\n🔄 Fetching users from database...")
    users = await get_all_users()
    total_users = len(users)
    
    print(f"\n✅ Found {total_users} users")
    
    # Show preview with first user
    if users:
        first_user = users[0]
        preview_message = message_template.format(
            user_first_name=first_user.get('first_name', 'User'),
            user_id=first_user.get('user_id', 'N/A'),
            level=first_user.get('level', 1),
            streak=first_user.get('streak', 0),
            xp=round(first_user.get('xp', 0), 1)
        )
        
        print("\n" + "="*60)
        print("📋 PREVIEW (for first user):")
        print("-"*60)
        print(preview_message)
        print("="*60)
    
    # Confirm
    confirm = input(f"\n⚠️ Send this message to {total_users} users? (yes/no): ").lower()
    
    if confirm not in ['yes', 'y']:
        print("\n❌ Broadcast cancelled.")
        return
    
    # Initialize bot
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    
    print("\n🚀 Starting broadcast...")
    print("-"*60)
    
    success = 0
    failed = 0
    blocked = 0
    
    # Send to each user
    for idx, user in enumerate(users, 1):
        try:
            user_id = user.get('user_id')
            
            # Format message for this user
            personalized_message = message_template.format(
                user_first_name=user.get('first_name', 'User'),
                user_id=user_id,
                level=user.get('level', 1),
                streak=user.get('streak', 0),
                xp=round(user.get('xp', 0), 1)
            )
            
            # Send message
            await bot.send_message(
                chat_id=int(user_id),
                text=personalized_message,
                parse_mode=ParseMode.MARKDOWN
            )
            
            success += 1
            
            # Progress indicator
            if idx % 10 == 0 or idx == total_users:
                print(f"Progress: {idx}/{total_users} | ✅ {success} | ❌ {failed} | 🚫 {blocked}")
            
            # Anti-flood delay
            await asyncio.sleep(0.05)
            
        except Exception as e:
            if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                blocked += 1
            else:
                failed += 1
            
            # Show error for first few failures
            if failed + blocked <= 3:
                print(f"  ⚠️ Failed to send to {user_id}: {str(e)[:50]}")
    
    # Final report
    print("\n" + "="*60)
    print("📊 BROADCAST COMPLETE")
    print("="*60)
    print(f"✅ Successfully sent: {success}")
    print(f"❌ Failed: {failed}")
    print(f"🚫 Blocked bot: {blocked}")
    print(f"📈 Total: {total_users}")
    print(f"📊 Success rate: {(success/total_users*100):.1f}%")
    print("="*60 + "\n")
    
    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(broadcast_message())
    except KeyboardInterrupt:
        print("\n\n❌ Broadcast interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
