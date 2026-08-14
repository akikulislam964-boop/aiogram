from telethon import events, Button
import config

async def finance_handler(event):
    if event.sender_id != config.OWNER_ID:
        return

    buttons = [
        [Button.inline("⚙️ Add Balance to User", "admin_add_balance")],
        [Button.inline("⚙️ Reset All Balances", "admin_reset_all")],
        [Button.inline("⚙️ User Stats", "admin_user_stats")],
        [Button.inline("📜 Transaction History", "admin_tx_history")],
        [Button.inline("🔙 Back", "adm_home")]
    ]
    await event.respond("<b>🔐 Finance Panel</b>", buttons=buttons, parse_mode='html')