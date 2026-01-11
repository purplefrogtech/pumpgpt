"""
Legacy command handlers kept for compatibility.
Prefer pumpbot.bot.handlers for active commands.
"""

from pumpbot.bot.handlers import cmd_help as help
from pumpbot.bot.handlers import cmd_start as start
from pumpbot.bot.handlers import cmd_status as status

__all__ = ["start", "help", "status"]
