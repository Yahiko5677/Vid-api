import asyncio
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aiohttp import web
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="VideoSequenceBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="handlers"),
            sleep_threshold=10,
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        logger.info(f"✅ Bot started as @{me.username}")

        # Reload pending files from DB into memory (restart recovery)
        from memory_store import reload_from_db
        await reload_from_db()

        # Log startup event to log channel
        from config import ADMINS, LOG_CHANNEL
        from memory_store import count_pending
        from services.log import log_bot_started
        if LOG_CHANNEL:
            for admin_id in ADMINS:
                recovered = count_pending(admin_id)
                await log_bot_started(self, admin_id, recovered, LOG_CHANNEL)

    async def stop(self):
        await super().stop()
        logger.info("⛔ Bot stopped")


# ── Dummy web server to satisfy Render port requirement ───────────────────
async def health(request):
    return web.Response(text="✅ VideoSequenceBot is alive!", status=200)

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Web server on port {PORT}")
    return runner


async def main():
    bot = Bot()
    runner = await run_web_server()
    await bot.start()
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await bot.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
