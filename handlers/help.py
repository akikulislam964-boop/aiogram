from telethon import events, Button
from localization import get_str

async def help_handler(event, db):
    if not event.is_private:
        return
    
    sender_id = event.sender_id
    user = await db.get_user(sender_id)
    lang = user.get('language', 'en') if user else 'en'
    
    settings = await db.get_settings()
    help_channel_id = settings.get('help_channel_id', 'Not Set')

    text = "💥 Bot Help Channel:\n\n" if lang == 'en' else "💥 সাহায্যকারী চ্যানেলের লিংক নিচে দেওয়া হলো:\n\n"
    
    buttons = []
    if help_channel_id and help_channel_id.lower() != 'not set':
        clean_id = help_channel_id.replace('https://t.me/', '').lstrip('@')
        channel_link = f"https://t.me/{clean_id}"
        text += f"🔗 {channel_link}\n\n"
        buttons.append([Button.url("📖 Open Help Channel", channel_link)])
    else:
        text += get_str('help_channel_not_set', lang) + "\n\n"
        
    text += "/cancel"
    buttons.append([Button.inline("Cancel", "user_cancel")]) 
    await event.respond(text, buttons=buttons, parse_mode='md')