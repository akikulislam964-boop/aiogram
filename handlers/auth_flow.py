import asyncio
import os
import json
import time 
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError, PhoneNumberBannedError
from telethon.sessions import StringSession

# Assume these are imported from the surrounding project structure
from config import API_ID, API_HASH, SESSIONS_DIR, get_setting 
from database import get_country_config 
from utils.logger import logger

# --- Country Code to Flag Mapping ---
COUNTRY_FLAGS = {
    "+93": "🇦🇫", # Afghanistan
    "+1": "🇺🇸",  # United States/Canada
    "+44": "🇬🇧", # United Kingdom
    "+91": "🇮🇳", # India
    "+880": "🇧🇩", # Bangladesh
    "+49": "🇩🇪", # Germany
    "+33": "🇫🇷", # France
    "+7": "🇷🇺",  # Russia
}

def _find_country_code(phone_number: str) -> str or None:
    """
    Attempts to find the longest matching country code prefix 
    (up to 4 digits) based on the configured prefixes in the database.
    """
    # Ensure the number starts with '+' for consistent checking
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number

    # Check for prefixes from longest (e.g., +880) to shortest (e.g., +1)
    for length in range(4, 0, -1):
        # Prefix includes '+' and up to 'length' digits
        prefix = phone_number[:length + 1] 
        if get_country_config(prefix):
            return prefix
    return None

def _get_extended_session_data(phone, user_id):
    """
    Placeholder to generate/fetch the extended data fields requested by the user.
    Includes register_time and last_check_time.
    """
    current_time = int(time.time())
    
    # User-requested JSON data structure with dynamic values
    return {
        "session_file": phone.lstrip('+'),
        "phone": phone,
        "user_id": user_id,
        "app_id": 2040, # Placeholder value
        "app_hash": "b18441a1ff607e10a989891a5462e627", # Placeholder value
        "sdk": "Windows 11",
        "app_version": "10.0.0 x64",
        "device": "FX516PR-HN109TS",
        "device_token": "dOTnyAr7Sf2R8vWuTrgWDV:APA91bGlN47KY6nQMoV0WqjXacgRmjL6Ps6OX_H3ZIt08cI5-qbLwlFIScGBo0EhgtajB2F3x8poIqjzmRJDef_XoyqJV_p9cjouQEmYtWDdtLRhXv65N80ZVsHwm5ICnN3KC_KCAek5",
        "device_token_secret": "+4Js4DcgGd9vBdmHv32SRIISMbwR+nx+Te4Eigd0fssQHZ/EA99uueB4aas0O2iuojTeoG1KHU4vP2m+6wi7Rg==",
        "device_secret": "zLC41s7WaD7XAEaYE8ZFxyUVEWIwS6yF9eFyAPiSegiWWWPXRt7J2vMdEZQRiY+8CATgHvARoTsgeyUIUxY9ZyNjcAtvCvdoc6EE/PMl72S2BMCePUQY/LBxP7WW4URpNyr8GSSlTLklEfWQFL9mjoAM1n9D9icHJtIWlX+vQXxgz8HzIpw9rQqXpMBF/0HP5gOKz3k9J0DwAFA8XMznILZpCuaIaA3bbiAqhaycCZYryIXceQDWjpkBWFHK/5HHvDZPTjy+RXEuUkqzJxIBkCs15my+04Q2yewTymxAheMQHZh9u2SmWRMkuDRUUOrYQ/Ob6xgJ0cBNX5Kc0HNMMw==",
        "signature": "8M06lqi/7zkCcJKB677uLVpWEpv/zZ4tv6dHG7s0n0i80pHUb3fEiVBeH/63Ly1utANA4rq9lRdH0l1IS5HBqgaG-oF4ZRCOc/2WIHUM3q2GFdg1fNT07DrcAPMCKU538WW9Q0YSwR-CuYEVpKamISWDEIZjLDfhOatLG-SckSinl6pqhc8Dw/u4xFdFRPp9DajL0wLKqiVRnl8bwW31sp3/UtI43XD//sf9XTY5ob7ExnvmswwrKEJxFXj/mGlwaYoiAWkw5I85fD-8uJw7gPIGNG-x0qSDSEs7Qil4xPHOK65porVSgfAPejjgDblqfHL1cTcAhp2o1Eg5DPZg==",
        "certificate": "NoGJ7inureqDe7H5wkwH3ZBux3fkmV7TGBA4l0+815QE9Ud9F/UZkH/PT2kI8tGBxWryk8ecy/sjNpk9lJFQ0ALgF5IAnJ+02Z/wxSrudpJEoX35HVbAd7b8caUsxa061XuYaMdhvUduU04HYnIZan1Ir0g14ZLRQmhVedb57Oq8HwTbIMNxyD2bmtkisn8e0H6XMgj03jHjBNdjnVr4STNQ3SSV7DGIB4h2DGYwqG3BhkVWanryaU65N9iZitatFAfjMcirRQ384UTx+Z1d1c3qubKcF2TzUhO1z4PfeNhh2UWjIP/wrZIM2v9HcaVgGEgwmBQdzjywU2Bj1Bib4w==",
        "safetynet": "4sXvcM49mfh3eDn0pSIvikbq7dY/+ooZi0GM8vfbfcn/8s6uU9HAKn4b2EmsBNTT4UNJ8D3YjOjXfp2HuT08c6xRaTudVcAE11apKGGV3ZYtY0N1yk6bwkTCDOula1bDm2gI3O6SSLK9xZTnDWZMKOPa1L24RvNieTTvXzuKKfSADfNBg6D3+S9ZonOnUhTYu7qB9B2b0utg3Hef3tGi15NUMBTAKeDv3mt4gk2YCEZVz8Eu3oQd1p6xj7l62tzoCi4ThfODbS/5A6JlgJLDrfcC2/N6sMd+3L41OKshC3bMYCi7YH2mwXGZPMu4RadACayx08mDF0u1OL3c5IQm02uc5lOBpzhUtmMpQgCTp9QLMWwa5D+vBha94Uy3qwebaB8uD2KPQuEeOurw403kdwyMhSwcBc0sqD4FXASWPUJlV4zg21AdCgPZ3AivNtRGFUP9OGyqIq7dOHITYfOFH8GzazyAJ39krJA/18JjE5ugxwA4zicZPx36umulVIO7PyeZuOibNfXoiPhQ6IMyG5F24dz6HiH+/fMF99xnjCy3vGc4wsGe+rkbneki5zipNdkHFmBNKwEcL3W3EZrxfR4knBh6O8a28LXV4Ln0HuurOh1HuPqg+avI+XlJrE5mjNOPosH7LmxGl7RIFSVt2t/kqbHXSYGoHCjPelw2p2o=",
        "perf_cat": 2,
        "tz_offset": 8280,
        "register_time": current_time,
        "last_check_time": current_time,
        "avatar": "img/default.png",
        "sex": 0,
        "lang_code": "en",
        "system_lang_code": "en-US",
        "lang_pack": "tdesktop",
        "twoFA": "22322",
        "proxy": None,
        "ipv6": False,
        "module": "AddAccount",
        "program": "https://telegram.org/"
    }


def get_current_capacity(country_code: str, category: str) -> int:
    """
    Counts the number of session files for the given country code and category.
    """
    try:
        # Construct the directory path: SESSIONS_DIR / country_code_without_plus / category
        target_dir = os.path.join(SESSIONS_DIR, country_code.lstrip("+"), category)
        
        if not os.path.isdir(target_dir):
            return 0
            
        # Count only .session files
        session_files = [f for f in os.listdir(target_dir) if f.endswith('.session')]
        return len(session_files)
    except Exception as e:
        logger.error(f"Error checking capacity for {country_code}/{category}: {e}")
        return 0

# --- Conversation Handler ---
@events.register(events.NewMessage(pattern=r'^\+?\d{10,}$', forwards=False))
async def auth_flow_handler(event):
    """
    Handles the user-provided phone number, initiates the Telegram login process,
    saves the session and metadata, enforces 2FA, and checks capacity limits.
    """
    user_id = event.sender_id
    phone_number = event.text.strip()
    bot = event.client

    # 1. Find Country Code
    country_code = _find_country_code(phone_number)
    
    if not country_code:
        # Use phone_number as it might be without '+' or invalid
        return await event.respond(f"❌ Configuration for the country of `{phone_number}` is not set in the admin panel or the format is invalid.")
    
    # Get flag emoji and category
    flag_emoji = COUNTRY_FLAGS.get(country_code, "🌍")
    category = "goods_and_brids" # Default category
    country_code_dir = country_code.lstrip("+")

    # Path to save the session files (e.g., sessions/880/goods_and_brids/88017xxxxxxx)
    session_path_prefix = os.path.join(SESSIONS_DIR, country_code_dir, category, phone_number.lstrip('+'))
    os.makedirs(os.path.dirname(session_path_prefix), exist_ok=True)
    
    # 2. Check for Duplicate Number
    if os.path.exists(f"{session_path_prefix}.session"):
        duplicate_message = "⚙️ This Number Already registered on Bot ✅"
        logger.info(f"User {user_id} tried to register duplicate number: {phone_number}")
        return await event.respond(duplicate_message, parse_mode='md')


    # 3. Load and Check Capacity Settings
    try:
        # MAX_CAPACITY: Maximum number of sessions. Default 100
        max_capacity = int(get_setting("MAX_CAPACITY", "100")) 
        # CONFIRMATION_TIME_SECONDS: Unlock/Confirmation time. Default 1000 seconds
        confirmation_time_sec = get_setting("CONFIRMATION_TIME_SECONDS", "1000") 
    except ValueError:
        max_capacity = 100
        confirmation_time_sec = "1000"
        logger.error("MAX_CAPACITY or CONFIRMATION_TIME_SECONDS setting is not a valid integer.")
        
    current_capacity = get_current_capacity(country_code, category)
    
    # Capacity Full Message
    if current_capacity >= max_capacity:
        capacity_full_message = (
            "📊 **Capacity Complite** ✅\n\n"
            f"এই মুহূর্তে `{country_code_dir}/{category}` ক্যাটাগরিতে অ্যাকাউন্টের ক্যাপাসিটি পূর্ণ।\n"
            f"⏳ **আনলক টাইম:** {confirmation_time_sec} সেকেন্ড। দয়া করে অপেক্ষা করুন।"
        )
        return await event.respond(capacity_full_message, parse_mode='md')
    
    
    # 4. Start Telethon Client and Conversation
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    await event.respond(f"Starting login process for `{phone_number}`...")

    try:
        async with bot.conversation(user_id, timeout=600) as conv:
            entered_password = None

            # --- Callback Functions ---
            async def code_callback():
                nonlocal conv
                # Prompt user for the code (using the flag)
                code_prompt = f"{flag_emoji} Enter the code sent to the number **{phone_number}**\n\n`/cancel`"
                m = await conv.send_message(code_prompt, parse_mode='md')
                
                code_msg = await conv.get_response()
                await m.delete()
                await code_msg.delete()
                
                # If user sends /cancel, raise ValueError to abort
                if code_msg.text.strip().lower() == '/cancel':
                    raise ValueError("Authentication cancelled by user.")
                    
                return code_msg.text.strip()

            async def password_callback(hint):
                nonlocal entered_password, conv
                m = await conv.send_message(f"🔒 2FA Password needed. Hint: `{hint}`\nPlease enter it:")
                password_msg = await conv.get_response()
                entered_password = password_msg.text.strip()
                await m.delete()
                await password_msg.delete()
                return entered_password

            # --- Login Process ---
            await client.connect()
            await client.start(
                phone=phone_number,
                password=password_callback,
                code_callback=code_callback
            )
            
            me = await client.get_me()
            
            # --- 5. Enforce New 2FA Password ---
            two_fa_password_to_set = get_setting("TWO_FA_ACCOUNT")
            if two_fa_password_to_set and (entered_password is None or str(two_fa_password_to_set) != entered_password):
                try:
                    # Note: We pass entered_password as current_password to change it
                    await client.edit_2fa(
                        current_password=entered_password, 
                        new_password=str(two_fa_password_to_set)
                    )
                    logger.info(f"Successfully set 2FA password for {phone_number} from admin settings.")
                except Exception as e:
                    logger.error(f"Failed to set 2FA for {phone_number}: {e}")
                    # Send a warning but allow registration to continue if session is active
                    await conv.send_message(f"⚠️ Could not set 2FA password automatically. Error: {e}")
            
            # --- 6. Spam Check Logic (Placeholder) ---
            spam_check_enabled = get_setting("SPAM_CHECK_ENABLED", "0") == "1"
            if spam_check_enabled:
                # Basic check: is there a name and is it long enough?
                if me.first_name is None or len(me.first_name.strip()) < 2: 
                    spam_message = "🚫 **Spam Check Failed!** Account appears generic (First name too short or missing)."
                    logger.warning(f"Spam check failed for {phone_number}: Generic name.")
                    await client.disconnect() 
                    await conv.send_message(spam_message, parse_mode='md')
                    return
                
            # --- 7. Save Session Files ---
            # Save .session file
            session_string = client.session.save()
            with open(f"{session_path_prefix}.session", "w") as f:
                f.write(session_string)
                
            # Create and save .json metadata file
            user_info = _get_extended_session_data(me.phone, me.id)
            
            # Override placeholders with actual Telethon data
            user_info["first_name"] = me.first_name
            user_info["last_name"] = me.last_name if me.last_name else ""
            user_info["username"] = me.username if me.username else ""
            user_info["user_id"] = me.id
            user_info["phone"] = me.phone
            
            with open(f"{session_path_prefix}.json", "w") as f:
                json.dump(user_info, f, indent=4)
                
            # Successful Login and Confirmation Message
            success_message = (
                f"{flag_emoji} The number **{me.phone}** has been successfully registered and is now waiting for confirmation.\n\n"
                f"⏳ **Confirmation Time:** {confirmation_time_sec} seconds\n\n"
                "⚠️ **Important:** Please log out of your account on all other devices to ensure a smooth confirmation process."
            )
            await conv.send_message(success_message, parse_mode='md')
            logger.info(f"Session created for {phone_number} by user {user_id}")

    except (PhoneCodeInvalidError, ValueError) as e:
        if "Authentication cancelled" in str(e):
            await bot.send_message(user_id, "🚫 Authentication process cancelled.")
        else:
            await bot.send_message(user_id, "❌ Invalid code. Please start over.")
    except SessionPasswordNeededError:
        # This handles cases where 2FA password was not provided by user 
        # or the bot couldn't change it, and the process aborted.
        await bot.send_message(user_id, "❌ 2FA Password required but not provided or invalid. Please start over.")
    except PhoneNumberBannedError:
        await bot.send_message(user_id, "❌ This phone number is banned.")
    except FloodWaitError as e:
        await bot.send_message(user_id, f"⏳ Too many attempts. Please wait for {e.seconds} seconds.")
    except asyncio.TimeoutError:
        await bot.send_message(user_id, "Operation timed out. Please try again.")
    except Exception as e:
        await bot.send_message(user_id, f"An unexpected error occurred: {e}")
        logger.error(f"Auth flow error for {phone_number}: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
