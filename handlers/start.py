from telethon import events, Button
import config
from bot_utils import check_force_subscribe, admin_menu, S_VERIFIED, S_PHONE, S_CAPCHA
from localization import LANGUAGES, get_str

# [MANUAL CONFIG] অতিরিক্ত এডমিন ম্যানুয়ালি যুক্ত করতে চাইলে এখানে ID দিন
EXTRA_ADMINS = []

async def start_handler(event, db, bot, user_states, user_data):
    if not event.is_private:
        return

    # ব্যান চেক
    if await db.is_user_banned(event.sender_id):
        await event.respond("❌ <b>You are banned from using this bot!</b>" if user_db.get('language') == 'bn' else "❌ <b>আপনাকে এই বট থেকে ব্যান করা হয়েছে!</b>", parse_mode='html')
        return

    sender = await event.get_sender()
    sender_id = sender.id

    is_admin = False
    if sender_id == config.OWNER_ID:
        is_admin = True
    elif sender_id in EXTRA_ADMINS:
        is_admin = True
    else:
        settings = await db.get_settings()
        custom_admin_id = settings.get('custom_admin_id')
        if custom_admin_id:
            try:
                if sender_id == int(custom_admin_id):
                    is_admin = True
            except:
                pass

    if is_admin:
        await admin_menu(event)
        return

    if not await check_force_subscribe(event, bot, db):
        return
    
    await db.add_user(sender_id, sender.first_name, sender.username)
    user_db = await db.get_user(event.sender_id)
    
    if not user_db.get('language') or (hasattr(event, 'text') and event.text.strip().startswith('/lang')):
        buttons = []
        lang_keys = list(LANGUAGES.keys())
        for i in range(0, len(lang_keys), 2):
            row = []
            row.append(Button.inline(LANGUAGES[lang_keys[i]], f"set_lang_{lang_keys[i]}"))
            if i + 1 < len(lang_keys):
                row.append(Button.inline(LANGUAGES[lang_keys[i+1]], f"set_lang_{lang_keys[i+1]}"))
            buttons.append(row)
        
        lang_code = user_db.get('language', 'en')
        text = get_str('welcome_unverified', lang_code)
        await event.respond(text, buttons=buttons)
        return

    lang = user_db.get('language', 'en')
    is_verified_persistent = user_db.get('is_verified', False)

    if user_states.get(sender_id, 0) >= S_VERIFIED or is_verified_persistent:
        if user_states.get(sender_id, 0) < S_PHONE:
             user_states[sender_id] = S_PHONE

        text = get_str('welcome_verified', lang)
        await event.respond(text)
        return

    await send_captcha(event, user_states, user_data, lang_code=lang)


async def send_captcha(event, user_states, user_data, edit=False, lang_code='en'):
    import random
    emojis = ["🐟", "✈️", "🛞", "🏸", "🎮"]
    correct_emoji = random.choice(emojis)
    random.shuffle(emojis)

    buttons = []
    for emoji in emojis:
        callback_data = f"cap_{'fish' if emoji == correct_emoji else 'wrong'}"
        buttons.append(Button.inline(emoji, callback_data))
    
    final_buttons = [buttons, [Button.inline("Cancel" if lang_code == 'en' else "Cancel", "user_cancel")]]

    text = get_str('captcha_verify', lang_code, correct_emoji)
    
    user_data[event.sender_id] = {'correct_cap': correct_emoji}
    user_states[event.sender_id] = S_CAPCHA

    if edit:
        await event.edit(text, buttons=final_buttons)
    else:
        await event.respond(text, buttons=final_buttons)