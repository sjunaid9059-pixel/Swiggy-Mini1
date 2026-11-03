#!/usr/bin/env python3
"""SJ Cash Telegram bot — Menu Open App + inline Mini App button."""
from __future__ import annotations

import logging
import os

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
    MenuButtonWebApp,
)
from telegram.ext import Application, CommandHandler, ContextTypes

import config

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("sj.bot")

OWNER_HANDLE = "@sjnd88"


def webapp_url() -> str:
    url = (config.WEBAPP_URL or os.getenv("WEBAPP_URL") or "").rstrip("/")
    if not url:
        url = "https://example.com"
    return url


def open_app_inline() -> InlineKeyboardMarkup:
    url = webapp_url()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▣ Open App", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton("✦ Open Mini App", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(f"Owner {OWNER_HANDLE}", url=f"https://t.me/{OWNER_HANDLE.lstrip('@')}")],
    ])


def reply_kb() -> ReplyKeyboardMarkup:
    url = webapp_url()
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="▣ Open App", web_app=WebAppInfo(url=url))],
            [KeyboardButton(text="✦ Open Mini App", web_app=WebAppInfo(url=url))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


WELCOME = (
    "✦ *SJ CASH* — premium mini app\n\n"
    "Multi-account cash engine\n"
    "• Up to *15 accounts* (admin unlimited)\n"
    "• Late Night · Breakfast · 50 FC · Diya\n"
    "• Claim on all saved sessions in one tap\n"
    "• Delete → recreate → full session JSON\n\n"
    f"Owner: *{OWNER_HANDLE}*\n\n"
    "Tap *Open App* / *Open Mini App* below."
)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME,
        parse_mode="Markdown",
        reply_markup=open_app_inline(),
    )
    await update.message.reply_text(
        "Quick access 👇",
        reply_markup=reply_kb(),
    )


async def app_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"✦ *SJ CASH*\nOwner: {OWNER_HANDLE}\n\nOpen the mini app:",
        parse_mode="Markdown",
        reply_markup=open_app_inline(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*SJ Cash*\n"
        "/start — welcome + Open App\n"
        "/app — mini app buttons\n"
        "/id — your telegram id\n\n"
        f"Owner: {OWNER_HANDLE}\n"
        "All login / claim / delete flows are inside the Mini App.",
        parse_mode="Markdown",
        reply_markup=open_app_inline(),
    )


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    await update.message.reply_text(f"Your Telegram ID: `{uid}`", parse_mode="Markdown")


async def post_init(app: Application):
    """Chat menu button = Open App (blue bar style)."""
    url = webapp_url()
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=url))
        )
        log.info("Menu button set → Open App → %s", url)
    except Exception as e:
        log.warning("set_chat_menu_button failed: %s", e)
    try:
        await app.bot.set_my_commands([
            BotCommand("start", "Open SJ Cash"),
            BotCommand("app", "Open Mini App"),
            BotCommand("help", "Help"),
            BotCommand("id", "My Telegram ID"),
        ])
    except Exception as e:
        log.warning("set_my_commands: %s", e)


def main():
    if not config.BOT_TOKEN or ":" not in config.BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN")
    if not (config.WEBAPP_URL or os.getenv("WEBAPP_URL")):
        log.warning("WEBAPP_URL not set — set it on Render for Open App to work")

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("app", app_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("myid", id_cmd))
    log.info("SJ Cash bot starting… token=%s…", config.BOT_TOKEN[:12])
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
