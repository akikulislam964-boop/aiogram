import random
from telethon import events, Button
from telethon.tl.types import ChannelParticipant, ChannelParticipantCreator, ChannelParticipantAdmin, ChannelParticipantLeft
import telethon.errors.rpcerrorlist
from datetime import datetime
from typing import Optional, Dict, Any
import config
from config import COUNTRY_FLAGS 

# --- User States ---
S_CAPCHA = 0
S_VERIFIED = 1
S_PHONE = 2
S_CODE = 3
S_PASSWORD = 4
S_WITHDRAW_ADDRESS = 5
S_WITHDRAW_CARD_NAME = 7 

# --- Admin States ---
S_BROADCAST_MSG = 10
S_EDIT_COUNTRY_VAL = 12
S_EDIT_CAPACITY = 14
S_ADD_COUNTRY = 15
S_EDIT_MIN_WD = 17
S_EDIT_2FA_PASSWORD = 18
S_DOWNLOAD_AMOUNT = 19
S_ADD_BALANCE_AMOUNT = 20
S_SET_WD_CHANNEL = 21
S_SET_NUMBER_CHANNEL = 22
S_SET_START_JOIN_CHANNEL = 23
S_SET_HELP_CHANNEL = 24
S_SET_SCREENSHOT_CHANNEL = 25
S_EDIT_PREMIUM_PRICE = 26
S_ADD_PROXY = 27
S_DOWNLOAD_MULTI = 28 
S_SET_BACKUP_CHANNEL = 29

# --- Dangerous States ---
S_SET_API_ID = 30
S_SET_API_HASH = 31
S_SET_BOT_TOKEN = 32
S_SET_ADMIN_ID = 33

def escape_md(text: str) -> str:
    if not text:
        return ""
    return str(text)

def format_price(p: float) -> str:
    return f"{p:.2f}$"

def get_country_row(c):
    flag = c.get('flag')
    if not flag or flag == "🌐":
        flag = COUNTRY_FLAGS.get(c.get('code'), "🌐")
        
    code = c.get('code', 'N/A')
    price_val = c.get('base_price', 0.0)
    price = format_price(price_val)
    time_val = c.get('confirm_time', 0)
    cap = c.get('capacity', 0)
    return f"▎ {flag} `{code:<5} | 💰 {price:<6} | 📦 Cap: {cap}`"

def get_flag_from_phone(phone):
    for code in sorted(COUNTRY_FLAGS.keys(), key=len, reverse=True):
        if phone.startswith(code):
            return COUNTRY_FLAGS[code]
    return "🌐"

def parse_country_data(text: str) -> Optional[Dict[str, Any]]:
    parts = text.strip().split()
    if len(parts) < 6:
        return None
    try:
        code = parts[0].strip()
        if not code.startswith('+'):
            return None
        free_price = float(parts[1])
        register_price = float(parts[2])
        limit_price = float(parts[3])
        capacity = int(parts[4])
        confirm_time = int(parts[5])
    except ValueError:
        return None
        
    flag = COUNTRY_FLAGS.get(code, "🌐")

    data = {
        'code': code,
        'free_price': free_price,
        'register_price': register_price,
        'limit_price': limit_price,
        'premium_price': free_price * 2,
        'capacity': capacity,
        'confirm_time': confirm_time,
        'base_price': free_price,
        'price': free_price,
        'status': True,
        'cspam': "V2",
        'api_type': "Desktop",
        'name': "Unknown",
        'flag': flag,
        'proxy': None
    }
    return data

async def get_matched_country(phone_number, db):
    countries = await db.get_countries()
    countries.sort(key=lambda x: len(x.get('code', '')), reverse=True)
    
    for c in countries:
        if phone_number.startswith(c['code']):
            return c
    return None

async def check_force_subscribe(event, bot, db):
    settings = await db.get_settings()
    channel_id = settings.get('start_join_channel_id')

    if not channel_id or channel_id.lower() == 'not set':
        return True 
        
    clean_id = channel_id.replace('https://t.me/', '').lstrip('@')
    channel_link = f"https://t.me/{clean_id}"

    try:
        chat = await bot.get_entity(channel_id)
        participant = await bot.get_permissions(chat, event.sender_id)
        
        is_member = False
        if participant:
            if isinstance(participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                is_member = True
            elif hasattr(participant, 'read_messages') and participant.read_messages:
                 is_member = True
            elif not isinstance(participant, ChannelParticipantLeft):
                 is_member = True
        
        if is_member:
            return True 
        
    except telethon.errors.rpcerrorlist.UserNotParticipantError:
        pass 
    except Exception as e:
        print(f"Force Subscribe Error: {e}")
        return True 

    text = (
        f"🚫 **Access Denied**\n\n"
        f"You must join our channel to use this bot.\n"
    )
    buttons = [
        [Button.url("➕ Join Channel", channel_link)]
    ]
    await event.respond(text, buttons=buttons, parse_mode='md')
    return False

async def admin_menu(event, edit=False):
    text = (
        "**Welcome, to control panel Admin!**\n"
        "Please choose an option below.\n"
        "🟢 **Bot Status:** Running\n"
        f"📅 **Date:** {datetime.now().strftime('%Y-%m-%d')}"
    )
    buttons = [
        [Button.inline("🌍 Country Settings", "adm_country")],
        [Button.inline("💰 Finance", "adm_finance"), Button.inline("🏦 Withdrawal", "adm_wd")],
        [Button.inline("📢 Broadcast", "adm_broadcast"), Button.inline("⏰ Confirmation", "adm_confirm")],
        [Button.inline("📂 File Manager", "adm_files"), Button.inline("⚙️ Configuration", "adm_config")],
        [Button.inline("📸 Screenshot", "adm_screenshot")],
        [Button.inline("⚠️ Dangerous ⚠️", "adm_danger")]
    ]
    if edit:
        try:
            await event.edit(text, buttons=buttons, parse_mode='md')
        except Exception:
            pass
    else:
        await event.respond(text, buttons=buttons, parse_mode='md')