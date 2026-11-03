#!/usr/bin/env python3
"""
Run both Mini App (FastAPI) + Telegram bot.

On Render:
  WEBAPP_URL=https://your-service.onrender.com
  BOT_TOKEN=...
  ADMIN_IDS=5427735251
  Start command: python main.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading

import uvicorn

import config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sj.main")


def run_api():
    port = int(os.getenv("PORT", str(config.PORT)))
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        factory=False,
    )


def run_bot():
    # import after env is ready
    from bot import main as bot_main
    bot_main()


def main():
    mode = os.getenv("RUN_MODE", "all").lower()  # all | api | bot
    if mode == "api":
        run_api()
        return
    if mode == "bot":
        run_bot()
        return

    # default: API in background thread, bot in main (polling blocks)
    t = threading.Thread(target=run_api, name="sj-api", daemon=True)
    t.start()
    log.info("API thread started on port %s", os.getenv("PORT", config.PORT))
    run_bot()


if __name__ == "__main__":
    main()
