import os
from functools import wraps
from typing import Awaitable, Callable, Set

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


def _vip_ids() -> Set[int]:
    return {
        int(x.strip())
        for x in os.getenv("VIP_USER_IDS", "").split(",")
        if x.strip().isdigit()
    }


CONTACT_USERNAME = "mehmetecetr"
PAYWALL_MESSAGE = (
    "💎 <b>PUMP•GPT VIP PANEL</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "Bu premium sinyal paneline erişiminiz bulunmuyor.\n\n"
    "🔐 <b>Özel erişim için:</b>\n"
    "Telegram: @mehmetecetr\n\n"
    "Lütfen erişim talebi ve ödeme detayları için @mehmetecetr ile iletişime geçin."
)


def is_vip(user_id: int) -> bool:
    return user_id in _vip_ids()


def contact_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="💬 @mehmetecetr ile iletişime geç",
                    url=f"https://t.me/{CONTACT_USERNAME}",
                )
            ]
        ]
    )


def vip_required(func: Callable[..., Awaitable]) -> Callable[..., Awaitable]:
    """
    Decorator to guard command handlers with VIP access.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        chat = update.effective_chat

        if not user:
            logger.warning("VIP check skipped: update has no user information.")
            return

        if not is_vip(user.id):
            if chat:
                try:
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=PAYWALL_MESSAGE,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as exc:
                    logger.error(f"Paywall message failed for chat {chat.id}: {exc}")
            else:
                logger.warning("VIP check failed but chat is missing; cannot send paywall message.")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
