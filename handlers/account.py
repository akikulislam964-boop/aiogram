from telethon import events, Button
from datetime import datetime
import os
from bot_utils import check_force_subscribe
from localization import get_str

async def account_handler(event, db, bot):
    if not event.is_private:
        return
    
    # Check Force Subscribe
    if not await check_force_subscribe(event, bot, db):
        return

    sender_id = event.sender_id
    user = await db.get_user(sender_id)
    if not user:
        await event.respond("Please /start first.")
        return

    stats = await db.get_user_account_stats(sender_id)
    balance = user.get('balance', 0.0)
    lang = user.get('language', 'en')
    
    # Report Date Formatting
    report_date = datetime.now().strftime('%Y-%m-%d')
    
    info_text = get_str('user_info', lang, sender_id, stats['verified'], balance)
    caption = (
        f"{info_text}\n\n"
        f"Report taken on :\n"
        f"`{report_date}`"
        f"`-{datetime.now().strftime('%Y-%m-%d')}`"
    )
    
    buttons = [
        [Button.inline(get_str('withdrawal_btn', lang), "user_withdraw_start")],
        [Button.inline(get_str('withdraw_history_btn', lang), "user_wd_history")],
        [Button.inline(get_str('change_lang_btn', lang), "user_change_lang")]
    ]
    
    image_path = 'image_bf3d28.png' 
    
    # Send image if exists, else text
    if os.path.exists(image_path):
        await bot.send_file(
            event.chat_id, 
            image_path, 
            caption=caption, 
            buttons=buttons
        )
    else:
        await event.respond(caption, buttons=buttons)