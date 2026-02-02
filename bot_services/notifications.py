import asyncio
from datetime import datetime, timezone
from bot_services.firebase_service import get_all_users, get_due_cards, update_notification_state
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def check_and_send_due_card_notifications(bot):
    """
    Background task that checks for users with due cards and sends them practice reminders.
    Uses exponential backoff: 1h → 2h → 4h → 8h → 24h (max)
    Resets when user practices.
    """
    while True:
        try:
            print(f"[{datetime.now(timezone.utc)}] Checking for due cards...")
            
            users = await get_all_users()
            notifications_sent = 0
            
            for user in users:
                try:
                    user_id = user.get('user_id')
                    if not user_id or user.get('is_banned'):
                        continue
                    
                    # Get user's backoff state
                    last_sent = user.get('last_notification_sent')
                    backoff_level = user.get('notification_backoff_level', 0)
                    
                    # Calculate required wait time based on backoff level
                    wait_times_hours = [1, 2, 4, 8, 24]  # hours for each level
                    current_wait_hours = wait_times_hours[min(backoff_level, 4)]
                    required_wait_seconds = current_wait_hours * 3600  # convert to seconds
                    
                    # Check if enough time has passed since last notification
                    now = datetime.now(timezone.utc)
                    if last_sent:
                        # Convert Firestore timestamp to datetime if needed
                        if hasattr(last_sent, 'seconds'):
                            last_sent_dt = datetime.fromtimestamp(last_sent.seconds, tz=timezone.utc)
                        else:
                            last_sent_dt = last_sent
                        
                        time_since_last = (now - last_sent_dt).total_seconds()
                        if time_since_last < required_wait_seconds:
                            continue  # Skip this user, not enough time passed
                    
                    # Check for due cards
                    due_cards = await get_due_cards(user_id)
                    
                    if due_cards and len(due_cards) > 0:
                        card_count = len(due_cards)
                        
                        # Send notification
                        msg = (
                            f"🧠 **Smart Practice Reminder**\n\n"
                            f"You have **{card_count} card{'s' if card_count != 1 else ''}** "
                            f"ready for review!\n\n"
                            f"Practice now to strengthen your memory 💪"
                        )
                        
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🚀 Practice Now", callback_data="start_sm2")]
                        ])
                        
                        try:
                            await bot.send_message(user_id, msg, reply_markup=kb, parse_mode="Markdown")
                            
                            # Update user's notification state - INCREASE backoff level
                            await update_notification_state(user_id, backoff_level + 1)
                            notifications_sent += 1
                        except Exception as e:
                            print(f"Failed to send notification to {user_id}: {e}")
                except Exception as e:
                    print(f"Error processing user: {e}")
                    continue
            
            print(f"[{datetime.now(timezone.utc)}] Sent {notifications_sent} notifications")
            
        except Exception as e:
            print(f"Error in notification checker: {e}")
        
        # Check every hour
        await asyncio.sleep(3600)  # 3600 seconds = 1 hour
