from aiogram import BaseMiddleware
from aiogram.types import Update
from bot_services.firebase_service import get_user

class BanCheckMiddleware(BaseMiddleware):
    """Middleware to check if user is banned before processing any update."""
    
    async def __call__(self, handler, event: Update, data):
        # Extract user_id from the update
        user_id = None
        
        if event.message:
            user_id = event.message.from_user.id
        elif event.callback_query:
            user_id = event.callback_query.from_user.id
        elif event.inline_query:
            user_id = event.inline_query.from_user.id
        
        # Check if user is banned
        if user_id:
            user = await get_user(user_id)
            if user and user.get('is_banned'):
                # Silently ignore updates from banned users
                # They won't get any response
                return
        
        # User is not banned, continue processing
        return await handler(event, data)
