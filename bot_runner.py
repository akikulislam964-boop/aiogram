import asyncio
import os
import sys
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.errors import MessageNotModifiedError
import config
from client import TelegramBot
from database import Database
from monitor import monitor_pending_verifications

# --- Import Handlers ---
from handlers.start import start_handler
from handlers.account import account_handler
from handlers.cap import cap_handler
from handlers.help import help_handler
from handlers.cancel import cancel_handler
from handlers.finance import finance_handler
from handlers.callback import callback_handler
from handlers.input import input_handler

# Web Server & Stats scheduler imports
from web_server import start_web_server
from config import COUNTRY_FLAGS

# Windows কনসোলে ইউনিকোড ক্যারেক্টার সাপোর্ট করার জন্য
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

OWNER_ID = config.OWNER_ID

db = Database()
user_states = {}
user_data = {}

bot = None

# --- Event Wrappers ---
async def start_wrapper(event):
    try:
        await start_handler(event, db, bot, user_states, user_data)
    except MessageNotModifiedError:
        pass

async def account_wrapper(event):
    await account_handler(event, db, bot)

async def cap_wrapper(event):
    await cap_handler(event, db, bot)

async def help_wrapper(event):
    await help_handler(event, db)

async def cancel_wrapper(event):
    await cancel_handler(event, user_states, user_data)

async def finance_wrapper(event):
    await finance_handler(event)

async def callback_wrapper(event):
    try:
        await callback_handler(event, db, bot, user_states, user_data)
    except MessageNotModifiedError:
        pass

async def input_wrapper(event):
    if event.text.startswith('/'):
        return
    await input_handler(event, db, bot, user_states, user_data)

async def daily_stats_scheduler_task(bot, db):
    # প্রতিদিন রাত ১২টায় অটোমেটিকালি ডেইলি স্ট্যাটাস রিপোর্ট ওনার এবং লগ চ্যানেলে সেন্ড করে।
    while True:
        now = datetime.now()
        tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
        seconds_until_midnight = (tomorrow - now).total_seconds()
        
        await asyncio.sleep(seconds_until_midnight)
        
        try:
            stats = await db.get_daily_stats()
            report_date = datetime.now().strftime('%Y-%m-%d')
            
            text = (
                f"📊 <b>Daily Activity Report ({report_date})</b>\n\n"
                f"📱 Total Accounts Received Today: <code>{stats['total_accounts']}</code>\n"
                f"💰 Total Withdrawals Completed Today: <code>${stats['total_withdrawn']:.2f}</code>\n\n"
                f"<b>🌍 Country Breakdown:</b>\n"
            )
            
            if not stats['country_breakdown']:
                text += "• No account activity today."
            else:
                for code, item in stats['country_breakdown'].items():
                    flag = COUNTRY_FLAGS.get(code, "🌐")
                    text += f"• {flag} {code}: {item['total']} Total (✅ {item['accepted']} | ❌ {item['rejected']})\n"
            
            await bot.send_message(config.OWNER_ID, text, parse_mode='html')
            
            settings = await db.get_settings()
            number_channel = settings.get('number_channel_id')
            if number_channel and str(number_channel).lower() != 'not set':
                try:
                    try: number_channel = int(number_channel)
                    except ValueError: pass
                    await bot.send_message(number_channel, text, parse_mode='html')
                except: pass
                
        except Exception as e:
            print(f"Error in daily stats report: {e}")
        
        await asyncio.sleep(10)

# --- Main Bot Startup ---
async def start_bot():
    global bot
    try:
        await db.connect()
        bot = TelegramClient('bot_session', config.API_ID, config.API_HASH)
        await bot.start(bot_token=config.BOT_TOKEN)
        
        bot.add_event_handler(start_wrapper, events.NewMessage(pattern=r'^/start$'))
        bot.add_event_handler(start_wrapper, events.NewMessage(pattern=r'^/lang$'))
        bot.add_event_handler(account_wrapper, events.NewMessage(pattern=r'^/account$'))
        bot.add_event_handler(cap_wrapper, events.NewMessage(pattern=r'^/(cap|capacity)$'))
        bot.add_event_handler(help_wrapper, events.NewMessage(pattern=r'^/help$'))
        bot.add_event_handler(cancel_wrapper, events.NewMessage(pattern=r'^/cancel$'))
        bot.add_event_handler(finance_wrapper, events.NewMessage(pattern=r'^/finance$'))
        
        bot.add_event_handler(callback_wrapper, events.CallbackQuery)
        bot.add_event_handler(input_wrapper, events.NewMessage)
        
        print("🤖 Bot Running with Localized Language Priority...")
        
        asyncio.create_task(start_web_server(bot, db))
        asyncio.create_task(daily_stats_scheduler_task(bot, db))
        asyncio.create_task(monitor_pending_verifications(bot, db))
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Error starting bot: {e}")

if __name__ == '__main__':
    asyncio.run(start_bot())