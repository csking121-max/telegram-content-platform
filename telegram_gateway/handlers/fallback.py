"""
Fallback handler — catches all unhandled messages.
"""

from aiogram import Router
from aiogram.types import Message

fallback_router = Router(name="fallback")


@fallback_router.message(lambda m: m.chat.type == "private")
async def handle_fallback(message: Message) -> None:
    """Only respond to unhandled messages in private chats, not groups."""
    await message.answer(
        "I didn't understand that.\n\n"
        "Available commands:\n"
        "/start - Main menu\n"
        "/plans - Browse membership plans\n"
        "/buy - Purchase a membership\n"
        "/pay <UTR> - Submit payment reference\n"
        "/mystatus - Check payment status\n"
        "/profile - View your profile\n"
        "/menu - Show main menu"
    )