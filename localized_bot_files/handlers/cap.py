from telethon import events
from bot_utils import check_force_subscribe, COUNTRY_FLAGS

async def cap_handler(event, db, bot):
    # 📦 Shows capacity info with blockquote formatting matching JIA system.
    
    if not event.is_private:
        return
    
    if not await check_force_subscribe(event, bot, db):
        return

    settings = await db.get_settings()
    if settings.get("capacity_status", "ON") == "OFF":
        await event.respond("❌ Service is currently turned off by the admin.")
        return

    all_countries_config = await db.get_countries()
    active_countries = [c for c in all_countries_config if c.get('status', True)]

    if not active_countries:
        await event.respond("❌ **No capacity available right now**\n\nNo active countries found.")
        return

    try:
        active_countries.sort(key=lambda x: int(str(x.get("code", "0")).replace('+', '') or 0))
    except (ValueError, TypeError):
        pass

    message_lines = ["<b>🌍 Available Countries & Capacity Info:</b>\n"]

    for config in active_countries:
        code_str = str(config.get("code", "N/A")).strip()
        code_pure = code_str.replace('+', '')
        c_name = config.get("name", "Unknown")
        
        flag = config.get('flag')
        if not flag or flag == "🌐":
             flag = COUNTRY_FLAGS.get(code_pure, COUNTRY_FLAGS.get(code_str, "🏳️"))
        
        try:
            free_price = float(config.get("free_price", config.get("base_price", 0.0)))
        except (ValueError, TypeError):
            free_price = 0.0
            
        try:
            register_price = float(config.get("register_price", 0.0))
        except (ValueError, TypeError):
            register_price = 0.0
            
        try:
            limit_price = float(config.get("limit_price", 0.0))
        except (ValueError, TypeError):
            limit_price = 0.0

        try:
            confirm_time = int(config.get("confirm_time", 120))
        except (ValueError, TypeError):
            confirm_time = 120

        header = f"{flag} {code_str} {c_name}"
        blockquote_str = f"<blockquote>Free:${free_price:.2f}|New:${register_price:.2f}|Spam:${limit_price:.2f}|{confirm_time}s</blockquote>"
        
        message_lines.append(f"{header}\n{blockquote_str}")

    message_text = "\n".join(message_lines)

    await event.respond(message_text, parse_mode="HTML")