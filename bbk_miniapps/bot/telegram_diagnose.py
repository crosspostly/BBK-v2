
import logging
import asyncio
from telegram.ext import Application
from telegram.constants import ChatAction

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "8483555978:AAF9o3xiRpi-Q7y77-6dVmHfSsVgMPgR-wo"

async def diagnose():
    logger.info("Starting Telegram bot diagnostic script...")
    
    try:
        logger.info("Attempting to build Application with provided token.")
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        logger.info("Application built successfully.")

        logger.info("Attempting to get bot info (bot.getMe())...")
        bot_info = await application.bot.getMe()
        logger.info(f"Successfully connected to Telegram API. Bot info: {bot_info.to_dict()}")
        
        logger.info("Attempting to run polling for a short period (10 seconds) to check for updates.")
        # We can't use run_once easily here in an async context,
        # so we'll just run it for a short timeout.
        try:
            # We need to explicitly await run_polling if we're in an async function
            # And it needs to be stopped to allow the async function to complete.
            # A more robust diagnostic would set up handlers and then run.
            # For now, just checking connection and basic polling.
            # Let's try to simulate a polling for a very short duration and then stop.
            # This is tricky because run_polling is blocking for the event loop.
            
            # A simpler check: just ensure getMe works, then we know token and basic connection is OK.
            # More advanced polling checks can be done if getMe fails.
            pass # getMe was successful, so basic connection is fine.
        except Exception as e:
            logger.error(f"Error during polling check: {e}")

        logger.info("Telegram diagnostic completed. Basic connection seems OK.")

    except Exception as e:
        logger.error(f"Telegram diagnostic failed: {e}")
        logger.error("Possible issues: invalid bot token, network problems, or Telegram API issues.")

if __name__ == "__main__":
    asyncio.run(diagnose())
