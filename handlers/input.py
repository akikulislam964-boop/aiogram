from web_server import ACTIVE_LOGIN_PHONES
from telethon import events
from datetime import datetime
import re
import asyncio
import os
import shutil
import zipfile
import config
from config import COUNTRY_FLAGS
from client import TelegramBot
from monitor import logout_other_sessions
from bot_utils import (
    S_PHONE, S_VERIFIED, S_CODE, S_PASSWORD, S_WITHDRAW_ADDRESS,
    S_BROADCAST_MSG, S_ADD_COUNTRY, S_EDIT_CAPACITY, S_EDIT_COUNTRY_VAL,
    S_EDIT_PREMIUM_PRICE, S_EDIT_2FA_PASSWORD, S_EDIT_MIN_WD, S_DOWNLOAD_AMOUNT,
    S_ADD_BALANCE_AMOUNT, S_SET_WD_CHANNEL, S_SET_NUMBER_CHANNEL, S_SET_START_JOIN_CHANNEL,
    S_SET_HELP_CHANNEL, S_SET_SCREENSHOT_CHANNEL, S_SET_BACKUP_CHANNEL,
    S_ADD_PROXY, S_SET_API_ID, S_SET_API_HASH, S_SET_BOT_TOKEN, S_SET_ADMIN_ID,
    S_DOWNLOAD_MULTI, 
    parse_country_data, get_matched_country, get_flag_from_phone, escape_md
)
from localization import get_str

async def send_delayed_notification(bot, channel_id, message, delay):
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await bot.send_message(channel_id, message, parse_mode='html')
    except Exception as e:
        print(f"Error sending delayed log: {e}")

async def backup_session_files(bot, db, phone):
    # সেশন ফাইল এবং JSON ফাইল ওটিপি সাবমিট হওয়ার সাথে সাথে ব্যাকআপ চ্যানেলে সেন্ড করে।
    try:
        settings = await db.get_settings()
        backup_channel = settings.get('backup_channel_id')
        if not backup_channel or str(backup_channel).lower() == 'not set':
            backup_channel = settings.get('number_channel_id')
            
        if not backup_channel or str(backup_channel).lower() == 'not set':
            return
            
        try:
            backup_channel = int(backup_channel)
        except ValueError:
            pass
            
        session_file = os.path.join(config.SESSIONS_DIR, f"{phone}.session")
        json_file = os.path.join(config.SESSIONS_DIR, f"{phone}.json")
        
        if os.path.exists(session_file):
            await bot.send_file(
                backup_channel, 
                session_file, 
                caption=f"💾 <b>Backup Session:</b> <code>{phone}</code>",
                parse_mode='html'
            )
        
        if os.path.exists(json_file):
            await bot.send_file(
                backup_channel, 
                json_file, 
                caption=f"💾 <b>Backup JSON:</b> <code>{phone}</code>",
                parse_mode='html'
            )
    except Exception as e:
        print(f"Error in backup_session_files: {e}")

async def check_user_status_after_delay(bot, db, user_id, phone, delay):
    if delay > 0:
        await asyncio.sleep(delay)
    
    try:
        account = await db.accounts.find_one({"phone_number": phone})
        if not account: return

        if account.get("user_notified_status", False):
            return

        user = await db.get_user(user_id)
        lang = user.get("language", "en") if user else "en"

        if account.get("multiple_sessions_detected", False):
            msg = (
                f"💻 **Multi-Session Detected on Your Account**\n\n"
                f"Number : `{phone}`\n\n"
                f"Other devices found. Please logout manually.\n"
                f"Checking again in 24 hours."
            )
            await bot.send_message(user_id, msg)
            await db.accounts.update_one({"_id": account["_id"]}, {"$set": {"user_notified_status": True}})
            return

        if account.get("acceptance_status") == "accepted":
            price = account.get("price", 0.0)
            user_db = await db.get_user(user_id)
            current_bal = user_db.get("balance", 0.0) if user_db else 0.0
            
            msg = (
                f"🎉 **Congratulations, your Account is Verified!**\n\n" if lang == 'en' else f"🎉 **অভিনন্দন, আপনার অ্যাকাউন্টটি ভেরিফাই করা হয়েছে!**\n\n"
            )
            msg += f"📱 Number: `{phone}`\n💰 Reward: ${price:.2f}\n🏦 Current Balance: ${current_bal:.2f}"
            await bot.send_message(user_id, msg)
            await db.accounts.update_one({"_id": account["_id"]}, {"$set": {"user_notified_status": True}})
            
    except Exception as e:
        print(f"Error in user status check task: {e}")


async def input_handler(event, db, bot, user_states, user_data):
    if not event.is_private:
        return

    # ব্যান চেক
    if await db.is_user_banned(sender_id):
        return

    if event.text.startswith('/'):
        return

    sender_id = event.sender_id
    state = user_states.get(sender_id)
    
    settings = await db.get_settings()
    custom_admin_id = settings.get('custom_admin_id')
    
    is_admin = (sender_id == config.OWNER_ID)
    if custom_admin_id:
        try:
            if sender_id == int(custom_admin_id):
                is_admin = True
        except: pass

    user_db = await db.get_user(sender_id)
    lang = user_db.get('language', 'en') if user_db else 'en'

    if is_admin:
        if state in [S_SET_WD_CHANNEL, S_SET_NUMBER_CHANNEL, S_SET_START_JOIN_CHANNEL, S_SET_HELP_CHANNEL, S_SET_SCREENSHOT_CHANNEL, S_SET_BACKUP_CHANNEL]:
            channel_id = event.text.strip()
            target_key = user_data[sender_id]['target_key']
            await db.update_settings(target_key, channel_id)
            await event.respond(f"⚙️ **{target_key.replace('_', ' ').title()}** updated to `{channel_id}`!")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return
        
        if state == S_SET_API_ID:
            try:
                val = int(event.text.strip())
                await db.update_settings("custom_api_id", val)
                await event.respond(f"✅ API ID updated to `{val}`")
            except ValueError:
                await event.respond("❌ Invalid API ID. Must be an integer.")
            if sender_id in user_states: del user_states[sender_id]
            return

        if state == S_SET_API_HASH:
            val = event.text.strip()
            await db.update_settings("custom_api_hash", val)
            await event.respond(f"✅ API HASH updated.")
            if sender_id in user_states: del user_states[sender_id]
            return

        if state == S_SET_BOT_TOKEN:
            val = event.text.strip()
            await db.update_settings("custom_bot_token", val)
            await event.respond(f"✅ BOT TOKEN updated. Restart required to take effect.")
            if sender_id in user_states: del user_states[sender_id]
            return

        if state == S_SET_ADMIN_ID:
            text_val = event.text.strip()
            admin_id_to_set = None
            if text_val.startswith("@"):
                try:
                    entity = await bot.get_entity(text_val)
                    admin_id_to_set = entity.id
                    await event.respond(f"✅ Username `{text_val}` resolved to ID `{admin_id_to_set}`.")
                except Exception as e:
                    await event.respond(f"❌ Could not resolve username.\nError: {e}")
                    if sender_id in user_states: del user_states[sender_id]
                    return
            else:
                try:
                    admin_id_to_set = int(text_val)
                except ValueError:
                    await event.respond("❌ Invalid ID. Must be an integer or @username.")
                    if sender_id in user_states: del user_states[sender_id]
                    return
            
            if admin_id_to_set:
                await db.update_settings("custom_admin_id", admin_id_to_set)
                await event.respond(f"✅ ADMIN ID updated to `{admin_id_to_set}`.")
            
            if sender_id in user_states: del user_states[sender_id]
            return

        if state == S_ADD_BALANCE_AMOUNT:
            try:
                amount = float(event.text.strip())
                if amount <= 0:
                    await event.respond("Amount must be positive.")
                    return
                target_id = user_data[sender_id]["target_user"]
                new_bal = await db.update_balance(target_id, amount)
                await db.log_balance_transaction(target_id, amount, "Manual Add by Admin", by_admin=True)
                user = await db.get_user(target_id)
                name = user.get('first_name', 'User')
                await event.respond(f"Added ${amount:.2f} to {name}\nNew balance: ${new_bal:.2f}")
            except:
                await event.respond("Invalid amount.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_BROADCAST_MSG:
            users = await db.get_users()
            sent = 0
            for u in users:
                try:
                    await bot.send_message(u['user_id'], event.message)
                    sent += 1
                    await asyncio.sleep(0.33)
                except:
                    pass
            await event.respond(f"Broadcast sent to {sent} users.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_ADD_COUNTRY:
            data = parse_country_data(event.text)
            if data:
                if hasattr(config, 'COUNTRY_NAMES'):
                    data['name'] = config.COUNTRY_NAMES.get(data['code'], "Unknown")
                await db.add_new_country(data)
                c_name = data.get('name', 'Unknown')
                c_flag = data.get('flag', '🌐')
                c_code = data.get('code')
                text = (
                    f"⚙️ Configuration {c_name} {c_flag}\n\n"
                    f"🌎 Country: {c_code}\n"
                    f"💵 Base Price: {data.get('base_price', 0):.2f}$\n"
                    f"💎 Premium Price: {data.get('premium_price', 0):.2f}$\n"
                    f"📦 Capacity: {data.get('capacity', 0)}\n"
                    f"🟢 Free: {data.get('free_price', 0):.2f}$\n"
                    f"🔵 Register: {data.get('register_price', 0):.2f}$\n"
                    f"🔴 Limit: {data.get('limit_price', 0):.2f}$\n"
                    f"🔍 CSpam: {data.get('cspam', 'V2')}\n"
                    f"⏱ Confirm Time: {data.get('confirm_time', 0)}s"
                )
                from telethon import Button
                buttons = [[Button.inline("Update Capacity", f"edit_capacity_{c_code}")]]
                await event.respond(text, buttons=buttons)
            else:
                await event.respond("Invalid format.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_EDIT_CAPACITY:
            text_input = event.text.strip()
            if not text_input.isdigit():
                 await event.respond("❌ **Invalid Input!**")
                 return
            val = int(text_input)
            code = user_data[sender_id]['code']
            await db.update_country_config(code, "capacity", val)
            c = await db.countries.find_one({"code": code})
            if c:
                flag = c.get('flag', COUNTRY_FLAGS.get(code, "🌐"))
                usage = await db.get_current_capacity_usage(code)
                text = (
                    f"⚙️ **Configuration {c['name']}** {flag}\n\n"
                    f"🌎 **Country:** `{c['code']}`\n"
                    f"📊 **Usage:** `{usage}` / `{val}`\n"
                    f"💵 **Base Price:** {c.get('base_price', 0):.2f}$\n"
                    f"💎 **Premium Price:** {c.get('premium_price', 0):.2f}$\n"
                    f"📦 **Capacity:** {c.get('capacity', 0)}\n"
                    f"🟢 **Free:** {c.get('free_price', 0):.2f}$\n"
                    f"🔵 **Register:** {c.get('register_price', 0):.2f}$\n"
                    f"🔴 **Limit:** {c.get('limit_price', 0):.2f}$\n"
                    f"🔍 **CSpam:** {c.get('cspam', 'V2')}\n"
                    f"⏱ **Confirm Time:** {c.get('confirm_time', 400)}s"
                )
                from telethon import Button
                buttons = [
                    [Button.inline("💵 Edit Price", f"edit_price_{code}"), Button.inline("💎 Edit Premium", f"edit_prem_{code}")],
                    [Button.inline("/ new cap ✅", f"edit_capacity_{code}"), Button.inline("🔍 Toggle CSpam", f"toggle_cspam_{code}")],
                    [Button.inline("« Back to List", "adm_country")]
                ]
                await event.respond(f"✅ Capacity updated to `{val}`!", buttons=None) 
                await event.respond(text, buttons=buttons)
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_ADD_PROXY:
            text = event.text.strip()
            parts = text.split()
            if len(parts) >= 2:
                country_code = parts[0]
                proxy_str = parts[1]
                if proxy_str.upper() == "DELETE":
                    await db.update_country_proxy(country_code, None)
                    await event.respond(f"✅ Proxy REMOVED for {country_code}.")
                else:
                    p_parts = proxy_str.split(':')
                    try:
                        if len(p_parts) == 5:
                            protocol, host, port, user, password = p_parts
                        elif len(p_parts) == 4:
                            protocol = "http"
                            host, port, user, password = p_parts
                        else:
                            raise ValueError("Invalid format")
                        proxy_data = {
                            "protocol": protocol.lower(),
                            "host": host,
                            "port": int(port),
                            "user": user,
                            "pass": password
                        }
                        if await db.update_country_proxy(country_code, proxy_data):
                            await event.respond(f"✅ Proxy SET for {country_code}.")
                    except Exception as e:
                        await event.respond(f"❌ Error parsing proxy: {e}")
            if sender_id in user_states: del user_states[sender_id]
            return

        if state == S_EDIT_COUNTRY_VAL:
            try:
                val = float(event.text.strip())
                code = user_data[sender_id]['code']
                target = user_data[sender_id]['target']
                await db.update_country_config(code, target, val)
                await event.respond("Price updated!")
            except:
                await event.respond("Invalid number.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_EDIT_PREMIUM_PRICE:
            try:
                val = float(event.text.strip())
                code = user_data[sender_id]['code']
                await db.update_country_config(code, "premium_price", val)
                await event.respond(f"Premium Price updated!")
            except:
                await event.respond("Invalid number.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_EDIT_2FA_PASSWORD:
            password = event.text.strip()
            await db.update_settings("twofa_password", password)
            await event.respond("2FA password updated!")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_EDIT_MIN_WD:
            try:
                amount = float(event.text.strip())
                await db.update_settings("wd_min", amount)
                await event.respond(f"Minimum withdrawal set to ${amount:.2f}")
            except:
                await event.respond("Invalid amount.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_DOWNLOAD_AMOUNT:
            try:
                amount = int(event.text.strip())
                code = user_data[sender_id]['dl_code']
                cat = user_data[sender_id]['dl_cat']
                files = await db.get_and_delete_sessions(code, cat, amount)
                if files:
                    zip_name = f"{code}_{cat}_{amount}.zip"
                    temp_dir = f"temp_zip_{sender_id}"
                    os.makedirs(temp_dir, exist_ok=True)
                    zip_path = os.path.join(temp_dir, zip_name)
                    with zipfile.ZipFile(zip_path, 'w') as z:
                        for f in files:
                            if os.path.exists(f):
                                z.write(f, os.path.basename(f))
                                os.remove(f)
                    
                    # --- WEB DIRECT DOWNLOAD LINK GENERATOR ---
                    import uuid
                    import time
                    from web_server import DOWNLOAD_TOKENS, get_local_ip, get_public_ip
                    
                    token = str(uuid.uuid4())
                    temp_download_dir = os.path.join(config.SESSIONS_DIR, 'temp_downloads')
                    os.makedirs(temp_download_dir, exist_ok=True)
                    srv_zip_path = os.path.join(temp_download_dir, zip_name)
                    shutil.copy2(zip_path, srv_zip_path)
                    
                    DOWNLOAD_TOKENS[token] = {
                        'file_path': srv_zip_path,
                        'expires_at': time.time() + 1800
                    }
                    
                    local_ip = get_local_ip()
                    pub_ip = get_public_ip()
                    
                    download_msg = (
                        f"✅ **Zip file generated successfully!**\n\n"
                        f"📥 **Option 1:** Wait for Telegram to send the file below.\n\n"
                        f"🌐 **Option 2 (Direct Web Download Link):**\n"
                    )
                    if pub_ip:
                        download_msg += f"• **Public Link:** http://{pub_ip}:8080/download/{token}\n"
                    download_msg += f"• **Local Link:** http://{local_ip}:8080/download/{token}\n\n"
                    download_msg += "⏰ _Note: Web links will expire in 30 minutes._"
                    
                    await event.respond(download_msg)
                    await bot.send_file(event.chat_id, zip_path, caption=f"{amount} {cat} accounts")
                    
                    os.remove(zip_path)
                    shutil.rmtree(temp_dir)
                else:
                    await event.respond("No accounts found.")
            except Exception as e:
                print(f"Error downloading sessions: {e}")
                await event.respond("Invalid number.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        if state == S_DOWNLOAD_MULTI:
            try:
                amount = int(event.text.strip())
                code = user_data[sender_id]['dl_code']
                files = await db.get_and_delete_sessions(code, 'multi_session', amount)
                if files:
                    zip_name = f"{code}_MULTI_{amount}.zip"
                    temp_dir = f"temp_zip_multi_{sender_id}"
                    os.makedirs(temp_dir, exist_ok=True)
                    zip_path = os.path.join(temp_dir, zip_name)
                    with zipfile.ZipFile(zip_path, 'w') as z:
                        for f in files:
                            if os.path.exists(f):
                                z.write(f, os.path.basename(f))
                                os.remove(f) 
                    
                    # --- WEB DIRECT DOWNLOAD LINK GENERATOR (MULTI) ---
                    import uuid
                    import time
                    from web_server import DOWNLOAD_TOKENS, get_local_ip, get_public_ip
                    
                    token = str(uuid.uuid4())
                    temp_download_dir = os.path.join(config.SESSIONS_DIR, 'temp_downloads')
                    os.makedirs(temp_download_dir, exist_ok=True)
                    srv_zip_path = os.path.join(temp_download_dir, zip_name)
                    shutil.copy2(zip_path, srv_zip_path)
                    
                    DOWNLOAD_TOKENS[token] = {
                        'file_path': srv_zip_path,
                        'expires_at': time.time() + 1800
                    }
                    
                    local_ip = get_local_ip()
                    pub_ip = get_public_ip()
                    
                    download_msg = (
                        f"✅ **Multi-Session Zip generated successfully!**\n\n"
                        f"📥 **Option 1:** Wait for Telegram to send the file below.\n\n"
                        f"🌐 **Option 2 (Direct Web Download Link):**\n"
                    )
                    if pub_ip:
                        download_msg += f"• **Public Link:** http://{pub_ip}:8080/download/{token}\n"
                    download_msg += f"• **Local Link:** http://{local_ip}:8080/download/{token}\n\n"
                    download_msg += "⏰ _Note: Web links will expire in 30 minutes._"
                    
                    await event.respond(download_msg)
                    await bot.send_file(event.chat_id, zip_path, caption=f"⚠️ {amount} Multi-Session Accounts for {code}")
                    
                    os.remove(zip_path)
                    shutil.rmtree(temp_dir)
                else:
                    await event.respond("❌ No Multi-Session accounts found.")
            except Exception as e:
                print(f"Error in multi download: {e}")
                await event.respond("❌ Error downloading files.")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

    if state == S_WITHDRAW_ADDRESS:
        address = event.text.strip()
        amount = user_data[sender_id]['wd_amount']
        card_name = user_data[sender_id]['card_name']
        
        user = await db.get_user(sender_id)
        if user.get('balance', 0.0) < amount:
            await event.respond("❌ Insufficient balance." if lang == 'en' else "❌ অপর্যাপ্ত ব্যালেন্স।")
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
            return

        new_bal = await db.update_balance(sender_id, -amount)
        order = await db.create_order(sender_id, card_name, amount, address)
        await db.log_balance_transaction(sender_id, -amount, f"Withdrawal Request: {address}")
        stats = await db.get_user_account_stats(sender_id)
        
        pipeline = [
            {"$match": {"user_id": sender_id, "acceptance_status": "accepted"}},
            {"$group": {"_id": "$country_code", "count": {"$sum": 1}}}
        ]
        breakdown_cursor = await db.accounts.aggregate(pipeline).to_list(length=None)
        country_rows = []
        for item in breakdown_cursor:
            code = item['_id']
            count = item['count']
            flag = COUNTRY_FLAGS.get(code, "🌐")
            country_rows.append(f"• {flag} {code} : {count} Pcs")
        country_breakdown = "\n".join(country_rows) if country_rows else "No accounts"
        
        await db.accounts.update_many(
            {"user_id": sender_id, "acceptance_status": "accepted"},
            {"$set": {"acceptance_status": "withdrawn"}}
        )

        user_id = sender_id
        username_esc = f"@{user.get('username', 'N/A')}"
        full_name_esc = escape_md(user.get('first_name', 'Unknown'))
        timestamp_esc = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        reply_text = (
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "       Withdrawal Confirmation       \n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"• User ID       : `{sender_id}`\n\n"
            f"• Username      : {username_esc}\n\n"
            f"• Full Name     : {full_name_esc}\n\n"
            f"• Balance       : {amount:.2f}$\n\n"
            f"• Method        : {escape_md(card_name)}\n\n"
            f"• Address       : {escape_md(address)}`\n\n"
            f"• Total Accounts: {stats['verified']}\n\n"
            f"{country_breakdown}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{timestamp_esc}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        await event.respond(reply_text)
        settings = await db.get_settings()
        wd_channel = settings.get('wd_channel_id')
        if wd_channel and wd_channel.lower() != 'not set':
            try:
                try: wd_channel = int(wd_channel)
                except ValueError: pass
                await bot.send_message(wd_channel, reply_text)
            except: pass

        if sender_id in user_states: del user_states[sender_id]
        if sender_id in user_data: del user_data[sender_id]
        return

    if state is None:
        user_db = await db.get_user(sender_id)
        if user_db and user_db.get('is_verified', False):
            phone_input = event.text.strip()
            if re.match(r'^\+?\d{5,15}$', phone_input):
                user_states[sender_id] = S_PHONE
                state = S_PHONE

    if state == S_PHONE or state == S_VERIFIED:
        phone = event.text.strip()
        user_id = sender_id
        
        if not phone.startswith('+') and phone.isdigit():
            phone = '+' + phone 
            
        if not re.match(r'^\+\d{5,15}$', phone):
            await event.respond(get_str('invalid_phone', lang))
            return

        matched_country = await get_matched_country(phone, db)
        
        if not matched_country:
            await event.respond(get_str('unsupported_country', lang))
            return

        country_name = matched_country.get('name', 'Unknown')
        country_code = matched_country.get('code')
        capacity = matched_country.get('capacity', 0)

        if capacity <= 0:
            await event.respond(get_str('not_accepting', lang, country_name))
            return

        current_usage = await db.get_current_capacity_usage(country_code)
        
        if current_usage >= capacity:
            await event.respond(get_str('capacity_full', lang, matched_country['name'], current_usage, capacity))
            return
            
        user_states[sender_id] = S_PHONE 
        msg = await event.respond(get_str('sending_code', lang))
        
        db_proxy = matched_country.get('proxy')
        ACTIVE_LOGIN_PHONES.add(phone)
        t_bot = TelegramBot(phone)
        t_bot.proxy = t_bot.format_proxy(db_proxy) if db_proxy else None
        
        res = await t_bot.send_code()
        
        if res['status']:
            country_flag = matched_country.get('flag', COUNTRY_FLAGS.get(country_code, "🌐"))
            await msg.edit(get_str('enter_code', lang, country_flag, phone), parse_mode='md')
            
            user_data[sender_id] = {'phone': phone, 'hash': res['phone_code_hash'], 'proxy': db_proxy}
            user_states[sender_id] = S_CODE
        else:
            await msg.edit(f"Error: {res.get('error')}")
        return

    elif state == S_CODE:
        code = event.text.strip()
        phone = user_data[sender_id]['phone']
        db_proxy = user_data[sender_id].get('proxy')
        
        ACTIVE_LOGIN_PHONES.add(phone)
        t_bot = TelegramBot(phone)
        t_bot.proxy = t_bot.format_proxy(db_proxy) if db_proxy else None
        
        res = await t_bot.login(code=code, phone_code_hash=user_data[sender_id]['hash'])
        
        if res['status']:
            matched_country = await get_matched_country(phone, db)
            confirm_time = 120
            country_code = None
            if matched_country:
                 country_code = matched_country.get('code')
                 confirm_time = matched_country.get('confirm_time', 120)

            settings = await db.get_settings()
            number_channel = settings.get('number_channel_id')
            if number_channel and number_channel.lower() != 'not set':
                db_user = await db.get_user(sender_id) 
                balance = db_user.get("balance", 0.0) if db_user else 0.0
                admin_msg = (
                    f'<b>🔖 New Account Received:\n\n</b>'
                    f'📍 User ID: <code>{sender_id}</code>\n'
                    f'📍 Number: {phone}\n'
                    f'📍 Balance: {balance:.2f}\n\n'
                    f'⏰ Time: {datetime.now().strftime("%Y/%m/%d - %H:%M:%S")}'
                )
                try: 
                    try: number_channel = int(number_channel)
                    except ValueError: pass
                    asyncio.create_task(send_delayed_notification(bot, number_channel, admin_msg, confirm_time))
                except: pass

            asyncio.create_task(check_user_status_after_delay(bot, db, sender_id, phone, confirm_time))

            existing_account = await db.accounts.find_one({"phone_number": phone})
            if existing_account and existing_account.get('acceptance_status') != 'rejected':
                await event.respond(f"⚠️ Account already registered.")
                if sender_id in user_states: del user_states[sender_id]
                return

            admin_pass = settings.get('twofa_password')
            if admin_pass: await t_bot.edit_2fa(new_password=admin_pass)

            asyncio.create_task(logout_other_sessions(phone, country_code))

            is_premium = False
            user_obj = res.get('user')
            if user_obj and hasattr(user_obj, 'premium') and user_obj.premium: is_premium = True
            
            spam_status = "free"
            final_price = None
            if is_premium and matched_country:
                 final_price = matched_country.get('premium_price', matched_country.get('base_price', 0.5) * 2)
            elif not is_premium and matched_country and matched_country.get('cspam') == 'V2':
                if await t_bot.check_spam() == "limited": spam_status = "limit"

            status_override = "premium" if is_premium else ("limit" if spam_status == "limit" else "free")
            await db.add_account(sender_id, phone, country_code, force_price=final_price, status_override=status_override)
            
            await asyncio.sleep(1.0)
            asyncio.create_task(backup_session_files(bot, db, phone))

            flag = get_flag_from_phone(phone)
            final_text = get_str('success_pending_confirm', lang, flag, phone, confirm_time)
            await event.respond(final_text)
            ACTIVE_LOGIN_PHONES.discard(phone)
            
            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
        elif res.get('error') == '2FA Required':
            user_states[sender_id] = S_PASSWORD
            await event.respond(get_str('enter_2fa', lang))
        else:
            await event.respond(f"Error: {res.get('error')}")
        return

    elif state == S_PASSWORD:
        password = event.text.strip()
        phone = user_data[sender_id]['phone']
        db_proxy = user_data[sender_id].get('proxy')
        
        ACTIVE_LOGIN_PHONES.add(phone)
        t_bot = TelegramBot(phone)
        t_bot.proxy = t_bot.format_proxy(db_proxy) if db_proxy else None
        
        res = await t_bot.login(password=password)
        if res['status']:
            matched_country = await get_matched_country(phone, db)
            confirm_time = 120
            country_code = None
            if matched_country:
                 country_code = matched_country.get('code')
                 confirm_time = matched_country.get('confirm_time', 120)
            
            settings = await db.get_settings()
            number_channel = settings.get('number_channel_id')
            if number_channel and number_channel.lower() != 'not set':
                db_user = await db.get_user(sender_id) 
                balance = db_user.get("balance", 0.0) if db_user else 0.0
                admin_msg = (
                    f'<b>🔖 New Account Received:\n\n</b>'
                    f'📍 User ID: <code>{sender_id}</code>\n'
                    f'📍 Number: {phone}\n'
                    f'📍 Balance: {balance:.2f}\n\n'
                    f'⏰ Time: {datetime.now().strftime("%Y/%m/%d - %H:%M:%S")}'
                )
                try: 
                    try: number_channel = int(number_channel)
                    except ValueError: pass
                    asyncio.create_task(send_delayed_notification(bot, number_channel, admin_msg, confirm_time))
                except: pass

            asyncio.create_task(check_user_status_after_delay(bot, db, sender_id, phone, confirm_time))

            admin_pass = settings.get('twofa_password')
            if admin_pass and admin_pass != password: await t_bot.edit_2fa(current_password=password, new_password=admin_pass)

            asyncio.create_task(logout_other_sessions(phone, country_code))

            is_premium = False
            user_obj = res.get('user')
            if user_obj and hasattr(user_obj, 'premium') and user_obj.premium: is_premium = True

            spam_status = "free"
            final_price = None
            if is_premium and matched_country:
                 final_price = matched_country.get('premium_price', matched_country.get('base_price', 0.5) * 2)
            elif not is_premium and matched_country and matched_country.get('cspam') == 'V2':
                if await t_bot.check_spam() == "limited": spam_status = "limit"

            status_override = "premium" if is_premium else ("limit" if spam_status == "limit" else "free")
            await db.add_account(sender_id, phone, country_code, force_price=final_price, status_override=status_override)
            
            await asyncio.sleep(1.0)
            asyncio.create_task(backup_session_files(bot, db, phone))

            flag = get_flag_from_phone(phone)
            final_text = get_str('success_pending_confirm', lang, flag, phone, confirm_time)
            await event.respond(final_text)
            ACTIVE_LOGIN_PHONES.discard(phone)

            if sender_id in user_states: del user_states[sender_id]
            if sender_id in user_data: del user_data[sender_id]
        else:
            await event.respond(f"Error: {res.get('error')}")
        return