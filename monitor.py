import os
import logging
import asyncio
import json
import shutil
import random
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, functions, errors
from telethon.tl.functions.account import GetAuthorizationsRequest
from telethon.errors import SessionPasswordNeededError

try:
    from telethon.errors.rpcerrorlist import FreshResetAuthorizationsForbiddenError
except ImportError:
    class FreshResetAuthorizationsForbiddenError(Exception):
        pass

import config
from client import get_proxy_for_phone, TelegramBot
from web_server import ACTIVE_LOGIN_PHONES

logger = logging.getLogger('Monitor')
PROXY_FAILURE_COUNTS = {}
PROCESSED_FILES_CACHE = set()
MULTI_SESSION_DIR = os.path.join(config.SESSIONS_DIR, 'Multi_Session')

def parse_proxy_string(proxy_str):
    if not proxy_str or proxy_str == 'None':
        return None
    if isinstance(proxy_str, dict):
        return proxy_str
    
    match = re.match(r'(.*)://(.*):(.*)@(.*):(.*)', proxy_str)
    if match:
        return {
            'protocol': match.group(1), 
            'user': match.group(2), 
            'pass': match.group(3), 
            'host': match.group(4), 
            'port': int(match.group(5))
        }
    return {}

async def _approve_account(bot, db_acc, db_user, account, owner_id, price, is_prem, phone, chat_id, bypass):
    balance_field = 'premium_balance' if is_prem else 'balance'
    await db_user.update_one({'user_id': owner_id}, {'$inc': {balance_field: price}})
    await db_acc.update_one({'_id': account['_id']}, {'$set': {'acceptance_status': 'accepted', 'status': 'active'}})
    logger.info(f'Verified {phone} for {owner_id}')
    
    try:
        db_instance = db_user.database
        settings = await db_instance.settings.find_one({'_id': 'global_settings'})
        number_channel = settings.get('number_channel_id') if settings else None
        
        if number_channel and str(number_channel).lower() != 'not set':
            updated_user = await db_user.find_one({'user_id': owner_id})
            current_bal = updated_user.get(balance_field, 0.0) if updated_user else 0.0
            admin_msg = f'<b>🔖 New Account Accepted:</b>\n\n📍 User ID: <code>{owner_id}</code>\n📍 Number: {phone}\n📍 Price: ${price:.2f}\n📍 Balance: ${current_bal:.2f}\n\n⏰ Time: {datetime.now().strftime("%Y/%m/%d - %H:%M:%S")}'
            try:
                target_peer = int(number_channel)
            except ValueError:
                target_peer = number_channel
            await bot.send_message(target_peer, admin_msg, parse_mode='html')
    except Exception as e:
        logger.error(f'Error in channel notification: {e}')

async def get_connected_client(session_name: str, db=None):
    clean_phone = session_name.replace('+', '').strip()
    phone_with_plus = f'+{clean_phone}' if not session_name.startswith('+') else session_name
    
    # সব সম্ভাব্য পাথে ফাইল খোঁজার অল-রাউন্ডার লজিক
    possible_paths = [
        os.path.join(config.SESSIONS_DIR, f'{phone_with_plus}.session'),
        os.path.join(config.SESSIONS_DIR, f'{clean_phone}.session'),
        os.path.join(config.VALID_SESSIONS_DIR, f'{phone_with_plus}.session'),
        os.path.join(config.VALID_SESSIONS_DIR, f'{clean_phone}.session'),
    ]
    
    final_path = None
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            final_path = path
            break
            
    if not final_path:
        for root, dirs, files in os.walk(config.VALID_SESSIONS_DIR):
            for file in files:
                if file in [f'{phone_with_plus}.session', f'{clean_phone}.session']:
                    final_path = os.path.join(root, file)
                    break
            if final_path:
                break
                
    if not final_path:
        return (None, 'file_not_found', None)
        
    if PROXY_FAILURE_COUNTS.get(phone_with_plus, 0) >= 3:
        logger.warning(f'🚫 Skipping {session_name}: Too many proxy failures.')
        return (None, 'proxy_failed_state', None)
        
    proxy_config = None
    if db:
        acc = await db.accounts.find_one({'phone_number': phone_with_plus})
        if not acc:
            acc = await db.accounts.find_one({'phone_number': clean_phone})
        if acc and 'proxy' in acc:
            p_data = acc['proxy']
            if isinstance(p_data, str) and '://' in p_data:
                proxy_config = parse_proxy_string(p_data)
            elif isinstance(p_data, dict):
                proxy_config = p_data
                
    if not proxy_config:
        proxy_config = get_proxy_for_phone(phone_with_plus)
        
    max_retries = 5
    base_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            bot_instance = TelegramBot(phone_with_plus, proxy_data=proxy_config)
            lang_code = bot_instance.language_code[0] if isinstance(bot_instance.language_code, list) else bot_instance.language_code
            
            bot_instance.client = TelegramClient(
                session=final_path, 
                api_id=bot_instance.api_id, 
                api_hash=bot_instance.api_hash, 
                device_model=bot_instance.device_model, 
                system_version=bot_instance.system_version, 
                app_version=bot_instance.app_version, 
                lang_code=lang_code, 
                system_lang_code=bot_instance.system_lang_pack, 
                proxy=bot_instance.proxy, 
                receive_updates=False
            )
            
            if hasattr(bot_instance, '_patch_client'):
                await bot_instance._patch_client()
                
            await bot_instance.client.connect()
            
            if bot_instance.client and bot_instance.client.is_connected():
                if phone_with_plus in PROXY_FAILURE_COUNTS:
                    del PROXY_FAILURE_COUNTS[phone_with_plus]
                return (bot_instance.client, 'connected', bot_instance)
            
            if bot_instance.client:
                await bot_instance.client.disconnect()
                
            if attempt == max_retries - 1:
                return (None, 'connection_failed', None)
        
        except Exception as e:
            err_msg = str(e).lower()
            logger.error(f'Error connecting {phone_with_plus}: {e}')
            if 'bot_instance' in locals() and bot_instance.client:
                await bot_instance.client.disconnect()
            
            if 'database is locked' in err_msg or 'ioerror' in err_msg:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(delay)
            else:
                PROXY_FAILURE_COUNTS[phone_with_plus] = PROXY_FAILURE_COUNTS.get(phone_with_plus, 0) + 1
                await asyncio.sleep(2)
                
    return (None, 'error', None)

async def logout_other_sessions(session_name: str, country_code: str=None):
    logger.info(f'ℹ️ [Safe Mode] Skipping immediate logout for {session_name}.')
    return 'bypassed'

async def move_session_to_folder(phone_number, target_folder):
    await asyncio.sleep(1.0)
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
        
    clean_phone = phone_number.replace('+', '').strip()
    src_session = os.path.join(config.SESSIONS_DIR, f'{phone_number}.session')
    dst_session = os.path.join(target_folder, f'{phone_number}.session')
    
    if not os.path.exists(src_session):
        logger.warning(f'⚠️ Source session not found: {phone_number}')
        return False
        
    src_json = None
    json_plus = os.path.join(config.SESSIONS_DIR, f'{phone_number}.json')
    json_clean = os.path.join(config.SESSIONS_DIR, f'{clean_phone}.json')
    
    if os.path.exists(json_plus):
        src_json = json_plus
    elif os.path.exists(json_clean):
        src_json = json_clean
        
    dst_json = os.path.join(target_folder, os.path.basename(src_json)) if src_json else None
    
    copy_success = False
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            shutil.copy2(src_session, dst_session)
            copy_success = True
            break
        except OSError:
            await asyncio.sleep(1.0)
            
    if copy_success and src_json:
        for attempt in range(max_retries):
            try:
                shutil.copy2(src_json, dst_json)
                break
            except OSError:
                await asyncio.sleep(0.5)
                
    if copy_success:
        try:
            os.remove(src_session)
            if src_json:
                os.remove(src_json)
            return True
        except OSError as e:
            logger.error(f'❌ Failed to remove original session: {e}')
            return False
            
    return False

async def ensure_json_data(client, bot_inst, phone_number):
    clean_ph = phone_number.replace('+', '')
    json_path = os.path.join(config.SESSIONS_DIR, f'{phone_number}.json')
    if not os.path.exists(json_path):
        try:
            if not client.is_connected():
                await client.connect()
            me = await client.get_me()
            json_data = {
                'session_file': f'{phone_number}.session',
                'phone': clean_ph,
                'app_id': bot_inst.api_id,
                'app_hash': bot_inst.api_hash,
                'sdk': getattr(bot_inst, 'system_version', 'Unknown'),
                'device': getattr(bot_inst, 'device_model', 'Unknown'),
                'device_model': getattr(bot_inst, 'device_model', 'Unknown'),
                'lang_pack': getattr(bot_inst, 'lang_pack', 'tdesktop'),
                'system_lang_pack': getattr(bot_inst, 'system_lang_pack', 'en-US'),
                'last_name': me.last_name or '',
                'register_time': int(datetime.now().timestamp()),
                'proxy': None,
                'twoFA': '',
                'ipv6': False
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4)
            logger.info(f'✅ Regenerated JSON for {phone_number}')
            return True
        except Exception as ex:
            logger.error(f'❌ Failed to regenerate JSON: {ex}')
            return False
    return True

async def process_single_account(bot, account, db):
    accounts_collection = db.accounts
    users_collection = db.users
    chat_id = account.get('user_id')
    owner_id = account.get('user_id')
    phone_number = account.get('phone_number') or account.get('phone')
    
    if phone_number in PROCESSED_FILES_CACHE:
        return
        
    if not phone_number:
        await accounts_collection.update_one({'_id': account['_id']}, {'$set': {'acceptance_status': 'rejected', 'reject_reason': 'Missing Phone Number'}})
        return
        
    price = account.get('price', 0.0)
    is_premium = account.get('premium', False)
    
    client, status, bot_inst = await get_connected_client(phone_number, db=db)
    if not client:
        if status in ['file_not_found', 'empty_file']:
            await accounts_collection.update_one({'_id': account['_id']}, {'$set': {'acceptance_status': 'rejected', 'reject_reason': 'Session File Missing'}})
        return None
        
    should_approve = False
    is_multi_session = False
    move_folder = None
    
    try:
        if not await client.is_user_authorized():
            await accounts_collection.update_one({'_id': account['_id']}, {'$set': {'acceptance_status': 'expired', 'status': 'expired'}})
            try:
                await bot.send_message(entity=chat_id, message=f'⚠️ Session expired for `{phone_number}`.')
            except:
                pass
            await ensure_json_data(client, bot_inst, phone_number)
            await client.disconnect()
            return
            
        logger.info(f'🔍 Checking SPAM status for {phone_number}...')
        spam_status_result = await bot_inst.check_spam()
        
        if spam_status_result == 'limited':
            logger.info(f'⚠️ Account {phone_number} is LIMITED.')
            await accounts_collection.update_one({'_id': account['_id']}, {'$set': {'limit_status': 'limit'}})
            
        if spam_status_result == 'spam':
            logger.warning(f'🚫 Account {phone_number} is SPAM/BANNED. Rejecting...')
            await accounts_collection.update_one({'_id': account['_id']}, {'$set': {'acceptance_status': 'rejected', 'reject_reason': 'Spam/Banned'}})
            try:
                await bot.send_message(entity=chat_id, message=f'❌ **Account Rejected:** `{phone_number}` is banned/spam.')
            except:
                pass
            await ensure_json_data(client, bot_inst, phone_number)
            await client.disconnect()
            return
            
        try:
            authorizations = await client(GetAuthorizationsRequest())
            active_sessions_count = len(authorizations.authorizations)
            logger.info(f'🔍 Checked {phone_number}: {active_sessions_count} active sessions.')
            
            if active_sessions_count > 1:
                logger.info(f'⚠️ {active_sessions_count} sessions found. Attempting terminate...')
                try:
                    await client(functions.auth.ResetAuthorizationsRequest())
                    should_approve = True
                    move_folder = config.VALID_SESSIONS_DIR
                    is_multi_session = False
                except Exception as e:
                    logger.warning('⚠️ Cannot terminate. Approving immediately as MULTI-SESSION.')
                    is_multi_session = True
                    should_approve = True
                    move_folder = MULTI_SESSION_DIR
                    await accounts_collection.update_one({'_id': account['_id']}, {'$set': {'multiple_sessions_detected': True, 'has_other_sessions': True}})
            elif active_sessions_count == 1:
                should_approve = True
                move_folder = config.VALID_SESSIONS_DIR
                
        except Exception as e:
            logger.error(f'Error processing authorizations for {phone_number}: {e}')
            
        await ensure_json_data(client, bot_inst, phone_number)
        await client.disconnect()
        
        if move_folder:
            await move_session_to_folder(phone_number, move_folder)
            
        if should_approve:
            await _approve_account(bot, accounts_collection, users_collection, account, owner_id, price, is_premium, phone_number, chat_id, False)
            
    except Exception as e:
        logger.error(f'Error in process_single_account for {phone_number}: {e}')
        if client:
            await client.disconnect()

async def monitor_pending_verifications(bot, db):
    logger.info('🚀 Monitoring service started...')
    while True:
        try:
            if os.path.exists(config.SESSIONS_DIR):
                temp_files = [f for f in os.listdir(config.SESSIONS_DIR) if f.endswith('.session')]
                for file_name in temp_files:
                    phone_val = file_name.replace('.session', '')
                    phone_plus = f'+{phone_val}' if not phone_val.startswith('+') else phone_val
                    
                    if phone_plus in ACTIVE_LOGIN_PHONES or phone_val in ACTIVE_LOGIN_PHONES:
                        continue
                        
                    acc = await db.accounts.find_one({'phone_number': phone_plus, 'acceptance_status': 'pending'})
                    if not acc:
                        acc = await db.accounts.find_one({'phone_number': phone_val, 'acceptance_status': 'pending'})
                    
                    if acc:
                        logger.info(f'📂 Processing: {phone_plus}')
                        await asyncio.sleep(2)
                        await process_single_account(bot, acc, db)
                        await asyncio.sleep(0.5)
                        
            now_millis = int(datetime.now().timestamp() * 1000)
            overdue_accounts = await db.accounts.find({'acceptance_status': 'pending', 'unlock_time': {'$lte': now_millis}}).to_list(length=None)
            
            if overdue_accounts:
                logger.info(f'Processing {len(overdue_accounts)} overdue accounts...')
                for account in overdue_accounts:
                    await process_single_account(bot, account, db)
                    await asyncio.sleep(1)
                    
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f'Monitor loop error: {e}')
            await asyncio.sleep(30)
