from telethon import events, Button
from datetime import datetime
import os
import shutil
import zipfile
from telethon.errors import MessageNotModifiedError
import config
from config import COUNTRY_FLAGS
from bot_utils import (
    S_CAPCHA, S_VERIFIED, S_WITHDRAW_ADDRESS, 
    S_DOWNLOAD_AMOUNT, S_ADD_BALANCE_AMOUNT,
    S_ADD_COUNTRY, S_EDIT_CAPACITY, S_EDIT_COUNTRY_VAL, S_EDIT_PREMIUM_PRICE,
    S_EDIT_MIN_WD, S_EDIT_2FA_PASSWORD,
    S_SET_WD_CHANNEL, S_SET_NUMBER_CHANNEL, S_SET_START_JOIN_CHANNEL, 
    S_SET_HELP_CHANNEL, S_SET_SCREENSHOT_CHANNEL, S_BROADCAST_MSG,
    S_ADD_PROXY, 
    S_SET_API_ID, S_SET_API_HASH, S_SET_BOT_TOKEN, S_SET_ADMIN_ID,
    S_DOWNLOAD_MULTI, S_SET_BACKUP_CHANNEL,
    admin_menu, escape_md
)
from handlers.start import start_handler
from localization import LANGUAGES, get_str

async def callback_handler(event, db, bot, user_states, user_data, data_override=None):
    sender_id = event.sender_id
    data = data_override if data_override else event.data.decode('utf-8')

    # --- User Callbacks ---
    user_db = await db.get_user(sender_id)
    lang = user_db.get('language', 'en') if user_db else 'en'

    if data.startswith("set_lang_"):
        new_lang = data.replace("set_lang_", "")
        await db.update_user_language(sender_id, new_lang)
        await event.answer(f"Success! Language updated to: {LANGUAGES[new_lang]}", alert=True)
        try:
            await event.delete()
        except:
            pass
        await start_handler(event, db, bot, user_states, user_data)
        return

    if data == "user_change_lang":
        buttons = []
        lang_keys = list(LANGUAGES.keys())
        for i in range(0, len(lang_keys), 2):
            row = []
            row.append(Button.inline(LANGUAGES[lang_keys[i]], f"set_lang_{lang_keys[i]}"))
            if i + 1 < len(lang_keys):
                row.append(Button.inline(LANGUAGES[lang_keys[i+1]], f"set_lang_{lang_keys[i+1]}"))
            buttons.append(row)
        buttons.append([Button.inline("« Back", "back_to_account")])
        await event.edit(get_str('welcome_unverified', lang), buttons=buttons)
        return

    if data.startswith("cap_"):
        if user_states.get(sender_id) == S_CAPCHA:
            if data == "cap_fish":
                user_states[sender_id] = S_VERIFIED
                await db.update_user_config(sender_id, "is_verified", True)
                await start_handler(event, db, bot, user_states, user_data)
                try:
                    await event.delete()
                except:
                    pass
            else:
                await event.answer("❌ Wrong selection, try again!" if lang == 'en' else "❌ ভুল সিলেকশন, আবার চেষ্টা করুন!", alert=True)
                from handlers.start import send_captcha
                await send_captcha(event, user_states, user_data, edit=True, lang_code=lang)
        else:
            await event.answer("Operation expired or invalid state.", alert=True)
        return
    
    if data == "user_cancel":
        # টাইমার সচল থাকলে তা ক্যানসেল করার লজিক
        if sender_id in user_data and 'timer_task' in user_data[sender_id]:
            try: user_data[sender_id]['timer_task'].cancel()
            except: pass
        if sender_id in S_VERIFIED:
             user_states[sender_id] = S_VERIFIED
        if sender_id in user_states:
            del user_states[sender_id]
        if sender_id in user_data:
            del user_data[sender_id]
        text = get_str('cancel_text', lang)
        try:
            await event.edit(text, buttons=None)
        except Exception:
            await event.respond(text)
        return
        
    if data == "user_withdraw_start":
        settings = await db.get_settings()
        wd_mode = settings.get('wd_mode', False)
        min_wd = settings.get('wd_min', 0.0)
        
        user = await db.get_user(sender_id)
        balance = user.get('balance', 0.0)

        if not wd_mode:
            await event.answer(get_str('wd_closed_admin', lang), alert=True)
            return

        if balance < min_wd:
            await event.answer(get_str('min_wd_err', lang, min_wd), alert=True)
            return

        user_data[sender_id] = {
            'card_name': "Leader Card",
            'wd_amount': balance
        }
        user_states[sender_id] = S_WITHDRAW_ADDRESS
        
        text = get_str('wd_prompt', lang, balance)
        await event.edit(text, buttons=[[Button.inline("Cancel", "user_cancel")]])
        return

    if data == "user_wd_history":
        orders = await db.get_user_orders(sender_id)
        if not orders:
            await event.edit(
                get_str('no_wd_history', lang),
                buttons=[[Button.inline("« Back", "back_to_account")]]
            )
            return

        text = get_str('wd_history_title', lang)
        for i, order in enumerate(orders[:10], 1):
            status_raw = order.get('status', 'pending')
            status_emoji = "⏳"
            if status_raw in ["completed", "withdrawn", "approved"]:
                status_emoji = "✅"
            elif status_raw in ["rejected", "cancelled"]:
                status_emoji = "❌"

            text += (
                f"**Request #{i}**\n"
                f"💰 **Amount:** `${order.get('amount', 0.0):.2f}`\n"
                f"💳 **Address:** `{order.get('address', 'N/A')}`\n"
                f"⚙️ **Status:** {status_emoji} {status_raw.upper()}\n"
                f"📅 **Date:** `{order.get('created_at', 'N/A')}`\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
        
        buttons = [[Button.inline("« Back", "back_to_account")]]
        await event.edit(text, buttons=buttons, parse_mode='md')
        return

    if data == "back_to_account":
        try:
            await event.delete()
        except Exception:
            pass
        from handlers.account import account_handler
        await account_handler(event, db, bot)
        return

    # --- Admin Checks ---
    settings = await db.get_settings()
    custom_admin_id = settings.get('custom_admin_id')
    
    is_admin = (sender_id == config.OWNER_ID)
    if custom_admin_id:
        try:
            if sender_id == int(custom_admin_id):
                is_admin = True
        except: pass

    if not is_admin:
        await event.answer("Not authorized!", alert=True)
        return
    
    # --- Admin Menus ---
    if data == "adm_home":
        await admin_menu(event, edit=True)

    elif data == "adm_wd":
        pending_orders = await db.get_pending_withdrawal_orders()
        
        text = "🏦 **Withdrawal Panel**\n\n"
        buttons = []
        
        if not pending_orders:
            text += "No pending withdrawal requests found."
        else:
            text += f"There are **{len(pending_orders)}** pending withdrawals.\n\n"
            for order in pending_orders[:5]:
                order_id = order.get('order_id')
                text += (
                    f"👤 **User:** `{order.get('user_id')}`\n"
                    f"💰 **Amount:** `${order.get('amount', 0.0):.2f}`\n"
                    f"💳 **Wallet:** `{order.get('address')}`\n"
                    f"📅 **Date:** `{order.get('created_at')}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                )
                buttons.append([
                    Button.inline(f"✅ Pay ${order.get('amount'):.1f}", f"wd_pay_{order_id}"),
                    Button.inline("❌ Reject", f"wd_rej_{order_id}")
                ])
                
            if len(pending_orders) > 5:
                text += f"_Showing first 5 of {len(pending_orders)} requests. Please use the TXT download for full list._\n"
        
        buttons.append([Button.inline("📥 Get Pending List (TXT)", "dl_wd_txt")])
        buttons.append([Button.inline("« Back", "adm_home")])
        await event.edit(text, buttons=buttons, parse_mode='md')
        return

    elif data == "dl_wd_txt":
        await event.answer("Generating withdrawal file, please wait...")
        pending_orders = await db.get_pending_withdrawal_orders()
        
        if not pending_orders:
            await event.answer("No pending withdrawals!", alert=True)
            return

        file_content = f"--- Pending Withdrawal Requests ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---\n\n"
        for i, order in enumerate(pending_orders, 1):
            file_content += f"----------------- Request {i} -----------------\n"
            file_content += f"Request ID: {order.get('order_id', 'N/A')}\n"
            file_content += f"User ID: {order.get('user_id', 'N/A')}\n"
            file_content += f"Amount: ${order.get('amount', 0.0):.2f}\n"
            file_content += f"Method/Card Name: {order.get('card_name', 'N/A')}\n"
            file_content += f"Address/Wallet: {order.get('address', 'N/A')}\n"
            file_content += f"Date: {order.get('created_at', 'N/A')}\n"
            file_content += "----------------------------------------------\n\n"

        file_name = f"pending_withdrawals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        temp_path = os.path.join('.', file_name)
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        try:
            await bot.send_file(event.chat_id, temp_path, caption=f"Total Pending Withdrawals: {len(pending_orders)}")
        except Exception as e:
            await event.answer(f"❌ Failed to send file: {e}", alert=True)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return

    elif data.startswith("wd_pay_"):
        order_id = data.replace("wd_pay_", "")
        order = await db.get_order(order_id)
        if not order:
            await event.answer("❌ Order not found!", alert=True)
            return
            
        if order.get('status') != 'pending':
            await event.answer("⚠️ Order already processed!", alert=True)
            return
            
        await db.update_order_status(order_id, "completed")
        await event.answer("✅ Marked as Paid / Completed!", alert=True)
        
        user_id = order.get('user_id')
        amount = order.get('amount', 0.0)
        address = order.get('address')
        try:
            notification_text = (
                "🎉 **Withdrawal Paid Successfully!**\n\n"
                f"💰 **Amount:** `${amount:.2f}`\n"
                f"💳 **To Address:** `{address}`\n"
                f"⚙️ **Status:** Completed (Paid)\n\n"
                "Thank you for using our bot!"
            )
            await bot.send_message(user_id, notification_text, parse_mode='md')
        except Exception:
            pass
            
        await callback_handler(event, db, bot, user_states, user_data, data_override="adm_wd")
        return

    elif data.startswith("wd_rej_"):
        order_id = data.replace("wd_rej_", "")
        order = await db.get_order(order_id)
        if not order:
            await event.answer("❌ Order not found!", alert=True)
            return
            
        if order.get('status') != 'pending':
            await event.answer("⚠️ Order already processed!", alert=True)
            return
            
        await db.update_order_status(order_id, "rejected")
        user_id = order.get('user_id')
        amount = order.get('amount', 0.0)
        await db.update_balance(user_id, amount)
        await db.log_balance_transaction(user_id, amount, "Withdrawal Rejected (Refunded)", by_admin=True)
        await event.answer("❌ Rejected and refunded!", alert=True)
        
        try:
            notification_text = (
                "❌ **Withdrawal Rejected!**\n\n"
                f"💰 **Amount:** `${amount:.2f}`\n"
                "⚠️ Your withdrawal request was rejected and the amount has been successfully refunded to your balance."
            )
            await bot.send_message(user_id, notification_text, parse_mode='md')
        except Exception:
            pass
            
        await callback_handler(event, db, bot, user_states, user_data, data_override="adm_wd")
        return
        
    elif data == "adm_country":
        countries = await db.get_countries()
        buttons = []
        for c in countries:
            flag = c.get('flag', COUNTRY_FLAGS.get(c['code'], "🌐"))
            buttons.append([Button.inline(f"{flag} {c['name']} ({c['code']})", f"country_detail_{c['code']}")])
        buttons.append([Button.inline("➕ Add Country", "add_country_start")])
        buttons.append([Button.inline("🗑️ Delete Country", "delete_country_menu")])
        buttons.append([Button.inline("🛡️ Add Country Proxy", "add_proxy_start")])
        buttons.append([Button.inline("« Back", "adm_country")])
        await event.edit("**🌍 Country Settings**\nSelect a country:", buttons=buttons)

    elif data.startswith("country_detail_"):
        code = data.replace("country_detail_", "")
        c = await db.countries.find_one({"code": code})
        if c:
            flag = c.get('flag', COUNTRY_FLAGS.get(code, "🌐"))
            usage = await db.get_current_capacity_usage(code)
            proxy_info = "None"
            if c.get('proxy'):
                p = c['proxy']
                proxy_info = f"{p.get('host')}:{p.get('port')}"

            text = (
                f"⚙️ **Configuration {c['name']}** {flag}\n\n"
                f"🌎 **Country:** `{c['code']}`\n"
                f"📊 **Usage:** `{usage}` / `{c.get('capacity', 0)}`\n"
                f"💵 **Base Price:** {c.get('base_price', 0):.2f}$\n"
                f"💎 **Premium Price:** {c.get('premium_price', 0):.2f}$\n"
                f"📦 **Capacity:** {c.get('capacity', 0)}\n"
                f"🟢 **Free:** {c.get('free_price', 0):.2f}$\n"
                f"🔵 **Register:** {c.get('register_price', 0):.2f}$\n"
                f"🔴 **Limit:** {c.get('limit_price', 0):.2f}$\n"
                f"🛡️ **Proxy:** `{proxy_info}`\n"
                f"🔍 **CSpam:** {c.get('cspam', 'V2')}\n"
                f"⏱ **Confirm Time:** {c.get('confirm_time', 400)}s"
            )
            buttons = [
                [Button.inline("💵 Edit Price", f"edit_price_{code}"), Button.inline("💎 Edit Premium", f"edit_prem_{code}")],
                [Button.inline("/ new cap ✅", f"edit_capacity_{code}"), Button.inline("🔍 Toggle CSpam", f"toggle_cspam_{code}")],
                [Button.inline("« Back to List", "adm_country")]
            ]
            await event.edit(text, buttons=buttons)

    elif data.startswith("toggle_cspam_"):
        code = data.replace("toggle_cspam_", "")
        c = await db.countries.find_one({"code": code})
        if c:
            current = c.get('cspam', 'V2')
            new_val = "OFF" if current == "V2" else "V2"
            await db.update_country_config(code, "cspam", new_val)
            await callback_handler(event, db, bot, user_states, user_data, data_override=f"country_detail_{code}")

    elif data == "add_country_start":
        user_states[event.sender_id] = S_ADD_COUNTRY
        await event.edit("➕ Enter country data:\n+CODE FreePrice RegisterPrice LimitedPrice Capacity UnlockTime\nExample: +91 0.30 0.29 0.28 1000 120", buttons=[[Button.inline("Cancel", "adm_country")]])

    elif data == "delete_country_menu":
        countries = await db.get_countries()
        buttons = []
        for c in countries:
            flag = c.get('flag', COUNTRY_FLAGS.get(c['code'], "🌐"))
            buttons.append([Button.inline(f"{flag} {c['name']} ({c['code']})", f"del_country_{c['code']}")])
        buttons.append([Button.inline("« Back", "adm_country")])
        try:
            await event.edit("🗑️ Select country to delete:", buttons=buttons)
        except MessageNotModifiedError:
            pass

    elif data.startswith("del_country_"):
        code = data.replace("del_country_", "")
        await db.delete_country(code)
        await event.answer(f"Deleted {code}", alert=True)
        await callback_handler(event, db, bot, user_states, user_data, data_override="delete_country_menu")

    elif data == "add_proxy_start":
        user_states[event.sender_id] = S_ADD_PROXY
        await event.edit(
            "🛡️ **Add Country Proxy**\n\n"
            "Format: `+CountryCode protocol:host:port:user:pass`\n"
            "Example: `+880 http:123.45.67.89:8000:admin:pass123`\n"
            "To remove proxy, type: `+CountryCode DELETE`\n\n"
            "Send proxy details now:",
            buttons=[[Button.inline("Cancel", "adm_country")]]
        )

    elif data.startswith("edit_price_"):
        code = data.replace("edit_price_", "")
        user_states[event.sender_id] = S_EDIT_COUNTRY_VAL
        user_data[event.sender_id] = {'target': 'base_price', 'code': code}
        await event.edit(f"Enter new base price for {code}:", buttons=[[Button.inline("Cancel", "adm_country")]])

    elif data.startswith("edit_prem_"):
        code = data.replace("edit_prem_", "")
        user_states[event.sender_id] = S_EDIT_PREMIUM_PRICE
        user_data[event.sender_id] = {'code': code}
        await event.edit(f"Enter new PREMIUM price for {code}:", buttons=[[Button.inline("Cancel", "adm_country")]])

    elif data.startswith("edit_capacity_"):
        code = data.replace("edit_capacity_", "")
        user_states[event.sender_id] = S_EDIT_CAPACITY
        user_data[event.sender_id] = {'code': code}
        usage = await db.get_current_capacity_usage(code)
        await event.edit(
            f"✍️ **Edit Capacity for {code}**\n\n"
            f"📊 Current Active/Pending: `{usage}`\n"
            f"⚠️ **Tip:** Set capacity > `{usage}` to allow new logins.\n\n"
            f"Enter new capacity (0 to close):", 
            buttons=[[Button.inline("Cancel", "adm_country")]]
        )
    
    elif data == "adm_broadcast":
        user_states[event.sender_id] = S_BROADCAST_MSG
        await event.edit("📢 Send the message for broadcast:", buttons=[[Button.inline("Cancel", "adm_home")]])

    elif data == "adm_confirm":
        active_count = await db.get_active_accounts_count()
        text = f"⏰ **Confirmation Menu**\nTotal Active Accounts: `{active_count}`"
        buttons = [[Button.inline("« Back", "adm_home")]]
        await event.edit(text, buttons=buttons)

    elif data == "adm_files":
        buttons = [
            [Button.inline("📥 Download Sessions", "adm_download")], 
            [Button.inline("💻 Multiple Session Download", "adm_download_multi")], 
            [Button.inline("📊 Statistics", "adm_stats")],
            [Button.inline("« Back", "adm_home")]
        ]
        await event.edit("📂 **File Manager & Sessions Menegment **\n", buttons=buttons)

    elif data == "adm_download_multi":
        countries = await db.get_countries()
        if not countries:
            await event.answer("No countries added yet!", alert=True)
            return
        
        buttons = []
        has_multi = False
        for c in countries:
            code = c['code']
            count = await db.get_session_counts_by_folder(code, 'multi_session')
            if count > 0:
                has_multi = True
                flag = c.get('flag', COUNTRY_FLAGS.get(code, "🌐"))
                buttons.append([Button.inline(f"{flag} {c['name']} ({count})", f"dl_multi_{code}")])
        
        if not has_multi:
             await event.answer("⚠️ No Multi-Session accounts found!", alert=True)
             return

        buttons.append([Button.inline("« Back", "adm_files")])
        await event.edit("💻 **Select Country (Multi-Session):**\nClick to download:", buttons=buttons)

    elif data == "adm_download":
        stats = await db.get_country_stats()
        countries = await db.get_countries()
        buttons = []
        for c in countries:
            flag = c.get('flag', COUNTRY_FLAGS.get(c['code'], "🌐"))
            buttons.append([Button.inline(f"{flag} {c['name']} ({c['code']})", f"fm_view_{c['code']}")])
            
        buttons.append([Button.inline("« Back", "adm_files")])
        try:
            await event.edit("📂 **Select Country to Download:**", buttons=buttons)
        except MessageNotModifiedError:
            pass

    elif data == "adm_stats":
        stats = await db.get_country_stats()
        countries = await db.get_countries()
        total_valid = sum(stats.values())
        total_multi = 0
        multi_stats = {}
        for c in countries:
            code = c['code']
            count = await db.get_session_counts_by_folder(code, 'multi_session')
            if count > 0:
                multi_stats[code] = count
                total_multi += count

        text = (
            f"📊 **Bot Statistics**\n\n"
            f"✅ Total Valid Sessions: `{total_valid}`\n\n"
            f"⚠️ Total Multi-Sessions: `{total_multi}`\n\n"
            f"<b>Breakdown:</b>\n"
        )
        
        all_codes = set(stats.keys()) | set(multi_stats.keys())
        for code in all_codes:
            v = stats.get(code, 0)
            m = multi_stats.get(code, 0)
            if v > 0 or m > 0:
                text += f"• {code}: ✅{v} | ⚠️{m}\n"
        
        await event.edit(text, buttons=[[Button.inline("« Back", "adm_files")]])

    elif data.startswith("fm_view_"):
        code = data.replace("fm_view_", "")
        free = await db.get_session_counts_by_folder(code, 'free')
        register = await db.get_session_counts_by_folder(code, 'register')
        limit = await db.get_session_counts_by_folder(code, 'limit')
        all_valid = await db.get_session_counts_by_folder(code, 'all_valid')
        premium = await db.get_session_counts_by_folder(code, 'premium') 
        
        buttons = [
            [Button.inline(f"💎 Premium - {premium}", f"dl_ask_{code}_premium")],
            [Button.inline(f"🟢 Free - {free}", f"dl_ask_{code}_free")],
            [Button.inline(f"🔵 Register - {register}", f"dl_ask_{code}_register")],
            [Button.inline(f"🔴 Limit - {limit}", f"dl_ask_{code}_limit")],
            [Button.inline(f"📂 All Valid Session - {all_valid}", f"dl_ask_{code}_all_valid")],
            [Button.inline("« Back", "adm_download")]
        ]
        await event.edit(f"📂 **{code} Folders**\nSelect a folder to download:", buttons=buttons)

    elif data.startswith("dl_ask_"):
        parts = data.split("_")
        code = parts[2]
        cat = parts[3]
        user_states[event.sender_id] = S_DOWNLOAD_AMOUNT
        user_data[event.sender_id] = {'dl_code': code, 'dl_cat': cat}
        await event.edit(f"How many {cat.replace('_', ' ').title()} accounts to download?\nEnter number:", buttons=[[Button.inline("Cancel", "adm_files")]])
    
    elif data.startswith("dl_multi_"):
        code = data.replace("dl_multi_", "")
        user_states[event.sender_id] = S_DOWNLOAD_MULTI
        user_data[event.sender_id] = {'dl_code': code}
        await event.edit(f"⚠️ **Multi-Session Download ({code})**\n\nEnter number to download:", buttons=[[Button.inline("Cancel", "adm_files")]])

    elif data == "adm_finance":
        buttons = [
            [Button.inline("⚙️ Add Balance to User", "admin_add_balance")],
            [Button.inline("⚙️ Reset All Balances", "admin_reset_all")],
            [Button.inline("⚙️ User Stats", "admin_user_stats")],
            [Button.inline("📜 Transaction History", "admin_tx_history")],
            [Button.inline("🔙 Back", "adm_home")]
        ]
        await event.edit("<b>🔐 Finance Panel</b>", buttons=buttons, parse_mode='html')

    elif data == "admin_add_balance":
        users = await db.get_users_with_stats()
        buttons = []
        for user in users[:45]:
            name = escape_md(user.get('first_name', 'Unknown')[:15])
            username = f"@{user.get('username')}" if user.get('username') else ""
            bal = user.get('balance', 0.0)
            text = f"{name} {username} - ${bal:.2f}"
            buttons.append([Button.inline(text, f"addbal_{user['user_id']}")])
        buttons.append([Button.inline("Back", "adm_finance")])
        await event.edit("Select user to add balance:", buttons=buttons)

    elif data.startswith("addbal_"):
        user_id = int(data.split("_")[1])
        user_states[event.sender_id] = S_ADD_BALANCE_AMOUNT
        user_data[event.sender_id] = {"target_user": user_id}
        user = await db.get_user(user_id)
        if not user:
            await event.answer("❌ User not found in database.", alert=True)
            return
        name = escape_md(user.get('first_name', 'User'))
        current_bal = user.get('balance', 0.0)
        await event.edit(f"Add balance to {name}\nCurrent: ${current_bal:.2f}\nSend amount:", parse_mode='html')

    elif data == "admin_reset_all":
        users = await db.get_users_with_stats()
        total_bal = sum(u.get('balance', 0.0) for u in users)
        text = f"Reset All Balances\nTotal: ${total_bal:.2f}\nConfirm?"
        buttons = [
            [Button.inline("Confirm Reset", "confirm_reset")],
            [Button.inline("Cancel", "adm_finance")]
        ]
        await event.edit(text, buttons=buttons)

    elif data == "confirm_reset":
        await event.edit("🔄 Resetting balances and generating report... please wait.")
        users = await db.get_users()
        total_wiped = 0.0
        file_content = f"--- User Balance Reset Log ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---\n\n"
        users_reset_count = 0
        for u in users:
            bal = u.get('balance', 0.0)
            if bal > 0: 
                user_id = u.get('user_id', 'Unknown')
                username = u.get('username', 'N/A')
                first_name = u.get('first_name', 'N/A')
                file_content += f"User ID: {user_id} | Name: {first_name} (@{username}) | Balance: ${bal:.2f}\n"
                total_wiped += bal
                users_reset_count += 1
                await db.update_balance(u['user_id'], -bal)
                await db.log_balance_transaction(u['user_id'], -bal, "All Balances Reset by Admin", by_admin=True)
        file_content += f"\n----------------------------------------------\n"
        file_content += f"Total Users Reset: {users_reset_count}\n"
        file_content += f"Total Amount Wiped: ${total_wiped:.2f}\n"
        file_name = f"balance_reset_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        temp_path = os.path.join('.', file_name)
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            await bot.send_file(
                event.chat_id, 
                temp_path, 
                caption=f"✅ All balances reset!\nTotal Wiped: ${total_wiped:.2f}\nUsers Affected: {users_reset_count}"
            )
            await event.delete() 
        except Exception as e:
            await event.edit(f"⚠️ Reset complete but failed to send log file: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    elif data == "admin_user_stats":
        users = await db.get_users_with_stats()
        text = "<b>User Stats</b>\n\n"
        for u in users[:25]:
            name = escape_md(u.get('first_name', 'Unknown'))
            username = f"@{u.get('username')}" if u.get('username') else ""
            bal = u.get('balance', 0.0)
            total = u.get('total_accounts', 0)
            acc = u.get('accepted_accounts', 0)
            pend = u.get('pending_accounts', 0)
            rej = u.get('rejected_accounts', 0)
            text += f"<b>{name}</b> {username}\nBalance: ${bal:.2f}\nAccounts: {total} (✅{acc} ⏳{pend} ❌{rej})\n\n"
        buttons = [[Button.inline("Back", "adm_finance")]]
        await event.edit(text, buttons=buttons, parse_mode='html')

    elif data == "admin_tx_history":
        txs = await db.get_recent_transactions(50)
        text = "<b>Transaction History</b>\n\n"
        for tx in txs:
            sign = "+" if tx['amount'] > 0 else "-"
            admin_tag = " (Admin)" if tx['by_admin'] else ""
            text += f"<code>{tx['timestamp']}</code>\n"
            text += f"<b>{tx['display_name']}</b>{admin_tag}\n"
            text += f"{sign}${abs(tx['amount']):.2f} — {tx['reason']}\n\n"
        buttons = [[Button.inline("Back", "adm_finance")]]
        await event.edit(text, buttons=buttons, parse_mode='html')

    elif data == "adm_config":
        s = await db.get_settings()
        twofa = s.get('twofa_password', 'Not Set')
        wd_mode = "ON" if s.get('wd_mode', True) else "OFF"
        min_wd = s.get('wd_min', 3.0)
        wd_channel_id = s.get('wd_channel_id', 'Not Set')
        number_channel_id = s.get('number_channel_id', 'Not Set')
        start_join_channel_id = s.get('start_join_channel_id', 'Not Set')
        help_channel_id = s.get('help_channel_id', 'Not Set')
        backup_channel_id = s.get('backup_channel_id', 'Not Set')

        text = (
            "**⚙️ Configuration**\n\n"
            f"🔐 2FA Password: `{twofa}`\n"
            f"🏦 Withdrawal Mode: {wd_mode}\n"
            f"💵 Minimum Withdrawal: ${min_wd:.2f}\n"
            f"💰 WD Channel ID: `{wd_channel_id}`\n"
            f"🔢 Number ID Channel: `{number_channel_id}`\n"
            f"➕ Start Join Channel ID: `{start_join_channel_id}`\n"
            f"❓ Help Channel ID: `{help_channel_id}`\n"
            f"💾 Backup Channel ID: `{backup_channel_id}`"
        )
        buttons = [
            [Button.inline("🔐 Set 2FA Password", "set_2fa")],
            [Button.inline("🏦 Toggle Withdrawal", "tog_wd")],
            [Button.inline("💵 Set Min Withdrawal", "set_min_wd")],
            [Button.inline("⚙️ Set WD Channel ID", "set_wd_channel")],
            [Button.inline("⚙️ Set Number ID", "set_number_channel")],
            [Button.inline("⚙️ Set Start Join Channel ID", "set_start_join_channel")],
            [Button.inline("⚙️ Set Help Channel ID", "set_help_channel")],
            [Button.inline("💾 Set Backup Channel", "set_backup_chan")],
            [Button.inline("« Back", "adm_home")]
        ]
        await event.edit(text, buttons=buttons)

    elif data == "adm_screenshot":
        s = await db.get_settings()
        screenshot_channel_id = s.get('screenshot_channel_id', 'Not Set')
        text = (
            "**📸 Screenshot Settings**\n\n"
            f"Current Channel: `{screenshot_channel_id}`\n\n"
            "This channel is used to display screenshots or payment proofs."
        )
        buttons = [
            [Button.inline("⚙️ Set Channel", "set_screenshot_channel")],
            [Button.inline("« Back", "adm_home")]
        ]
        await event.edit(text, buttons=buttons)

    elif data == "set_screenshot_channel":
        user_states[sender_id] = S_SET_SCREENSHOT_CHANNEL
        user_data[sender_id] = {'target_key': 'screenshot_channel_id'}
        await event.edit("📸 Send the new Screenshot Channel ID/Username (e.g., @proofs_channel):", buttons=[[Button.inline("Cancel", "adm_screenshot")]])

    elif data == "set_2fa":
        user_states[event.sender_id] = S_EDIT_2FA_PASSWORD
        await event.edit("🔐 Enter new 2FA password for new accounts:", buttons=[[Button.inline("Cancel", "adm_config")]])

    elif data == "tog_wd":
        s = await db.get_settings()
        new_mode = not s.get('wd_mode', True)
        await db.update_settings("wd_mode", new_mode)
        await event.answer(f"Withdrawal mode {'ON' if new_mode else 'OFF'}!", alert=True)
        await callback_handler(event, db, bot, user_states, user_data, data_override="adm_config")

    elif data == "set_min_wd":
        user_states[event.sender_id] = S_EDIT_MIN_WD
        await event.edit("💵 Enter new minimum withdrawal amount (e.g., 5.00):", buttons=[[Button.inline("Cancel", "adm_config")]])

    elif data == "set_wd_channel":
        user_states[sender_id] = S_SET_WD_CHANNEL
        user_data[sender_id] = {'target_key': 'wd_channel_id'}
        await event.edit("⚙️ Send the new Withdrawal Channel ID/Username:", buttons=[[Button.inline("Cancel", "adm_config")]])

    elif data == "set_number_channel":
        user_states[sender_id] = S_SET_NUMBER_CHANNEL
        user_data[sender_id] = {'target_key': 'number_channel_id'}
        await event.edit("⚙️ Send the new Number ID Channel ID/Username:", buttons=[[Button.inline("Cancel", "adm_config")]])
    
    elif data == "set_start_join_channel":
        user_states[sender_id] = S_SET_START_JOIN_CHANNEL
        user_data[sender_id] = {'target_key': 'start_join_channel_id'}
        await event.edit("⚙️ Send the new Start Join Channel ID/Username (e.g., @your_channel):", buttons=[[Button.inline("Cancel", "adm_config")]])

    elif data == "set_help_channel":
        user_states[sender_id] = S_SET_HELP_CHANNEL
        user_data[sender_id] = {'target_key': 'help_channel_id'}
        await event.edit("⚙️ Send the new Help Channel ID/Username (e.g., @support_channel):", buttons=[[Button.inline("Cancel", "adm_config")]])

    elif data == "set_backup_chan":
        user_states[sender_id] = S_SET_BACKUP_CHANNEL
        user_data[sender_id] = {'target_key': 'backup_channel_id'}
        await event.edit("💾 Send the **Backup Channel ID** (e.g. -100123456):", buttons=[[Button.inline("Cancel", "adm_config")]])
        return

    elif data == "adm_danger":
        settings = await db.get_settings()
        curr_admin = settings.get('custom_admin_id') or 'Not Set'
        buttons = [
            [Button.inline("💻 Api id", "set_api_id")],
            [Button.inline("🖥️ Api Hash", "set_api_hash")],
            [Button.inline("🤖 Bot Token", "set_bot_token")],
            [Button.inline("👤 Set New Admin", "set_admin_id")],
            [Button.inline("🗑️ Remove Custom Admin", "remove_admin")],
            [Button.inline("« Back", "adm_home")]
        ]
        try:
            await event.edit(f"⚠️ **Dangerous Settings**\n\nCurrent Custom Admin: `{curr_admin}`\nHandle with care!", buttons=buttons)
        except MessageNotModifiedError:
            pass

    elif data == "remove_admin":
        await db.update_settings("custom_admin_id", None)
        await event.answer("✅ Custom Admin access removed!", alert=True)
        await callback_handler(event, db, bot, user_states, user_data, data_override="adm_danger")

    elif data == "set_api_id":
        user_states[sender_id] = S_SET_API_ID
        await event.edit("💻 Send the new API ID (Integer):", buttons=[[Button.inline("Cancel", "adm_danger")]])

    elif data == "set_api_hash":
        user_states[sender_id] = S_SET_API_HASH
        await event.edit("🖥️ Send the new API HASH:", buttons=[[Button.inline("Cancel", "adm_danger")]])

    elif data == "set_bot_token":
        user_states[sender_id] = S_SET_BOT_TOKEN
        await event.edit("🤖 Send the new BOT TOKEN:", buttons=[[Button.inline("Cancel", "adm_danger")]])

    elif data == "set_admin_id":
        user_states[sender_id] = S_SET_ADMIN_ID
        await event.edit("👤 Send the new **Admin Username** (e.g., @user) or **ID**:", buttons=[[Button.inline("Cancel", "adm_danger")]])