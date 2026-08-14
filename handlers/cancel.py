from telethon import events

async def cancel_handler(event, user_states, user_data):
    if not event.is_private:
        return
    
    sender_id = event.sender_id
    if sender_id in user_states:
        del user_states[sender_id]
    if sender_id in user_data:
        del user_data[sender_id]
        
    text = "❎ The operation was canceled!\n\nTo continue, send the desired virtual account number or send /help to get help."
    await event.respond(text)