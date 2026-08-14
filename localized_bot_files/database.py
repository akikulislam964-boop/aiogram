import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient
import config
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('Database')

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.sessions_dir = getattr(config, 'SESSIONS_DIR', 'sessions')
        self.valid_sessions_dir = getattr(config, 'VALID_SESSIONS_DIR', 'sessions/valid')
        self.multi_session_dir = os.path.join(self.sessions_dir, 'Multi_Session')
        self.users = None
        self.accounts = None
        self.countries = None
        self.settings = None
        self.orders = None
        self.transactions = None

    async def connect(self):
        if self.client and self.db:
            return
        else:
            try:
                self.client = AsyncIOMotorClient(config.MONGO_URI)
                self.db = self.client[config.MONGO_DATABASE]
                self.users = self.db.users
                self.accounts = self.db.accounts
                self.countries = self.db.countries
                self.settings = self.db.settings
                self.orders = self.db.orders
                self.transactions = self.db.transactions
                await self._init_db()
                logger.info('MongoDB connected and initialized successfully.')
            except Exception as e:
                logger.error(f'Failed to connect to MongoDB: {e}')
                raise

    async def _init_db(self):
        default_settings = {
            '_id': 'global_settings',
            'bot_mode': True,
            'add_account_mode': True,
            'wd_mode': True,
            'wd_min': 3.0,
            'wd_max': 2000.0,
            'fees': {'trx': 1.0, 'usdt_trc20': 1.5, 'card': 2.0, 'leader': 0.5},
            'wd_modes': {'trx': True, 'usdt_trc20': False, 'card': True},
            'wd_channel_id': 'Not Set',
            'number_channel_id': 'Not Set',
            'start_join_channel_id': 'Not Set',
            'help_channel_id': 'Not Set',
            'screenshot_channel_id': 'Not Set',
            'backup_channel_id': 'Not Set',
            'custom_api_id': None,
            'custom_api_hash': None,
            'custom_bot_token': None,
            'custom_admin_id': None
        }
        await self.settings.update_one({'_id': 'global_settings'}, {'$setOnInsert': default_settings}, upsert=True)
        await self.users.create_index('user_id', unique=True)
        await self.accounts.create_index('phone_number', unique=True)
        await self.accounts.create_index('user_id')
        await self.accounts.create_index('acceptance_status')
        await self.countries.create_index('code', unique=True)

    async def add_user(self, user_id: int, first_name: str, username: Optional[str] = None) -> bool:
        user_doc = {
            'user_id': user_id,
            'first_name': first_name,
            'username': username,
            'balance': 0.0,
            'premium_balance': 0.0,
            'joined_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'accounts_added': 0,
            'is_verified': False,
            'language': 'en'
        }
        result = await self.users.update_one({'user_id': user_id}, {'$setOnInsert': user_doc}, upsert=True)
        return result.upserted_id is not None

    async def upsert_user(self, user_id, username, first_name):
        update_data = {'username': username, 'first_name': first_name}
        insert_defaults = {
            'user_id': user_id,
            'balance': 0.0,
            'premium_balance': 0.0,
            'is_verified': False,
            'accounts_added': 0,
            'joined_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'language': 'en'
        }
        await self.users.update_one({'user_id': user_id}, {'$set': update_data, '$setOnInsert': insert_defaults}, upsert=True)

    async def get_user(self, user_id: int) -> Optional[Dict]:
        return await self.users.find_one({'user_id': user_id})

    async def update_user_language(self, user_id: int, lang_code: str) -> bool:
        # ডাটাবেসে ইউজারের ল্যাঙ্গুয়েজ কোড আপডেট করে।
        result = await self.users.update_one({'user_id': user_id}, {'$set': {'language': lang_code}})
        return result.modified_count > 0

    async def update_user_config(self, user_id: int, key: str, value: Any) -> bool:
        result = await self.users.update_one({'user_id': user_id}, {'$set': {key: value}})
        return result.modified_count > 0

    async def get_users(self) -> List[Dict]:
        return await self.users.find({}).to_list(length=None)

    async def update_balance(self, user_id: int, amount: float) -> float:
        result = await self.users.find_one_and_update({'user_id': user_id}, {'$inc': {'balance': amount}}, return_document=True)
        return result.get('balance', 0.0) if result else 0.0

    async def get_user_account_stats(self, user_id: int) -> Dict[str, int]:
        total = await self.accounts.count_documents({'user_id': user_id})
        verified = await self.accounts.count_documents({'user_id': user_id, 'acceptance_status': 'accepted'})
        pending = await self.accounts.count_documents({'user_id': user_id, 'acceptance_status': 'pending'})
        rejected = await self.accounts.count_documents({'user_id': user_id, 'acceptance_status': {'$in': ['rejected', 'expired']}})
        return {'total': total, 'verified': verified, 'pending': pending, 'rejected': rejected}

    async def add_account(self, user_id: int, phone: str, country_code: str, force_price: float = None, status_override: str = None) -> float:
        country = await self.countries.find_one({'code': country_code})
        default_confirm_time = 400
        price = 0.0
        country_proxy = None
        if country:
            default_confirm_time = country.get('confirm_time', 400)
            price = force_price if force_price is not None else country.get('base_price', 0.0)
            if 'proxy' in country:
                country_proxy = country['proxy']
        limit_status = status_override if status_override else 'free'
        is_premium = limit_status == 'premium'
        new_acc = {
            'user_id': user_id,
            'phone_number': phone,
            'country_code': country_code,
            'price': price,
            'limit_status': limit_status,
            'premium': is_premium,
            'acceptance_status': 'pending',
            'unlock_time': int((datetime.now() + timedelta(seconds=default_confirm_time)).timestamp() * 1000),
            'multiple_sessions_detected': False,
            'created_at': datetime.now(),
            'twofa_rotated': False,
            'proxy': country_proxy,
            'admin_downloaded': False
        }
        try:
            await self.accounts.insert_one(new_acc)
            if country_proxy:
                logger.info(f'✅ Assigned proxy to new account {phone}')
        except Exception as e:
            logger.error(f'Error adding account {phone}: {e}')
        return price

    async def get_current_capacity_usage(self, country_code: str) -> int:
        return await self.accounts.count_documents({'country_code': country_code, 'acceptance_status': {'$in': ['accepted', 'pending']}})

    async def get_accounts(self) -> List[Dict]:
        return await self.accounts.find({}).to_list(length=None)

    async def delete_account_by_phone(self, phone: str):
        await self.accounts.delete_one({'phone_number': phone})

    async def get_users_with_stats(self) -> List[Dict]:
        pipeline = [
            {
                '$lookup': {
                    'from': 'accounts',
                    'localField': 'user_id',
                    'foreignField': 'user_id',
                    'as': 'user_accounts'
                }
            },
            {
                '$addFields': {
                    'total_accounts': {'$size': '$user_accounts'},
                    'accepted_accounts': {
                        '$size': {
                            '$filter': {
                                'input': '$user_accounts',
                                'as': 'acc',
                                'cond': {'$eq': ['$$acc.acceptance_status', 'accepted']}
                            }
                        }
                    },
                    'pending_accounts': {
                        '$size': {
                            '$filter': {
                                'input': '$user_accounts',
                                'as': 'acc',
                                'cond': {'$in': ['$$acc.acceptance_status', ['rejected', 'expired']]}
                            }
                        }
                    }
                }
            },
            {
                '$project': {
                    'user_id': 1,
                    'first_name': 1,
                    'username': 1,
                    'balance': 1,
                    'total_accounts': 1,
                    'accepted_accounts': 1,
                    'pending_accounts': 1
                }
            }
        ]
        cursor = self.users.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def get_country_stats(self) -> Dict[str, int]:
        pipeline = [
            {'$match': {'acceptance_status': {'$in': ['accepted', 'withdrawn']}}},
            {'$group': {'_id': '$country_code', 'count': {'$sum': 1}}}
        ]
        cursor = self.accounts.aggregate(pipeline)
        result = await cursor.to_list(length=None)
        stats = {}
        for doc in result:
            if doc.get('_id') and doc.get('count', 0) > 0:
                stats[doc['_id']] = doc['count']
        return stats

    async def get_active_accounts_count(self) -> int:
        return await self.accounts.count_documents({'acceptance_status': {'$in': ['accepted', 'withdrawn']}})

    async def log_balance_transaction(self, user_id: int, amount: float, reason: str, by_admin: bool = False):
        transaction = {
            'user_id': user_id,
            'amount': amount,
            'reason': reason,
            'by_admin': by_admin,
            'timestamp': datetime.now()
        }
        await self.transactions.insert_one(transaction)

    async def get_recent_transactions(self, limit: int = 50) -> List[Dict]:
        cursor = self.transactions.find({}).sort('timestamp', -1).limit(limit)
        transactions = await cursor.to_list(length=limit)
        enriched = []
        for tx in transactions:
            user = await self.get_user(tx.get('user_id'))
            name = user.get('first_name', 'Unknown') if user else 'Unknown'
            username = user.get('username') if user else None
            username_str = f"@{username}" if username else ''
            display_name = f"{name} {username_str}".strip()
            
            ts = tx.get('timestamp')
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if isinstance(ts, datetime) else str(ts)
            
            enriched.append({
                'display_name': display_name or 'Unknown User',
                'amount': tx.get('amount', 0.0),
                'reason': tx.get('reason', ''),
                'by_admin': tx.get('by_admin', False),
                'timestamp': ts_str
            })
        return enriched

    async def get_session_counts_by_folder(self, country_code: str, folder_type: str) -> int:
        query = {'country_code': country_code}
        query['admin_downloaded'] = {'$ne': True}
        if folder_type == 'all_valid':
            query['acceptance_status'] = {'$in': ['accepted', 'withdrawn']}
            query['multiple_sessions_detected'] = {'$ne': True}
        elif folder_type == 'multi_session':
            query['multiple_sessions_detected'] = True
        elif folder_type == 'frozen':
            query['acceptance_status'] = 'rejected'
            if 'admin_downloaded' in query:
                del query['admin_downloaded']
        else:
            query['acceptance_status'] = {'$in': ['accepted', 'withdrawn']}
            query['limit_status'] = folder_type
        return await self.accounts.count_documents(query)

    async def get_and_delete_sessions(self, country_code: str, folder_type: str, limit: int) -> List[str]:
        query = {'country_code': country_code}
        if folder_type != 'frozen':
            query['admin_downloaded'] = {'$ne': True}

        if folder_type == 'all_valid':
            query['acceptance_status'] = {'$in': ['accepted', 'withdrawn']}
            query['multiple_sessions_detected'] = {'$ne': True}
        elif folder_type == 'multi_session':
            query['multiple_sessions_detected'] = True
        elif folder_type == 'frozen':
            query['acceptance_status'] = 'rejected'
        else:
            query['acceptance_status'] = {'$in': ['accepted', 'withdrawn']}
            query['limit_status'] = folder_type

        accounts_to_fetch = await self.accounts.find(query).limit(limit).to_list(length=limit)
        files_to_send = []

        def to_digits(s):
            return ''.join(filter(str.isdigit, str(s))) if s else ''

        for acc in accounts_to_fetch:
            try:
                phone_raw = acc.get('phone_number')
                target_digits = to_digits(phone_raw)
                found_session = None
                found_json = None

                priority_dirs = [self.valid_sessions_dir, self.sessions_dir]
                if folder_type == 'multi_session':
                    priority_dirs.insert(0, self.multi_session_dir)

                filenames_to_check = [f'+{target_digits}.session', f'{target_digits}.session']

                for directory in priority_dirs:
                    if not os.path.exists(directory):
                        continue
                    for fname in filenames_to_check:
                        possible_path = os.path.join(directory, fname)
                        if os.path.exists(possible_path):
                            found_session = possible_path
                            base_name = os.path.splitext(fname)[0]
                            json_candidates = [f'{base_name}.json', f'{base_name}.JSON']
                            for j in json_candidates:
                                j_path = os.path.join(directory, j)
                                if os.path.exists(j_path):
                                    found_json = j_path
                                    break
                            break
                    if found_session:
                        break

                if not found_session:
                    for root, dirs, files in os.walk(self.sessions_dir):
                        for file in files:
                            if file.endswith('.session'):
                                file_digits = to_digits(file)
                                if file_digits and file_digits == target_digits:
                                    found_session = os.path.join(root, file)
                                    base_name = os.path.splitext(file)[0]
                                    json_candidates = [f'{base_name}.json', f'{base_name}.JSON']
                                    for j in json_candidates:
                                        j_path = os.path.join(root, j)
                                        if os.path.exists(j_path):
                                            found_json = j_path
                                            break
                                    break
                        if found_session:
                            break

                if found_session:
                    files_to_send.append(found_session)
                    if found_json:
                        files_to_send.append(found_json)
                    if folder_type == 'frozen' or acc.get('acceptance_status') == 'rejected':
                        await self.accounts.delete_one({'_id': acc['_id']})
                    else:
                        await self.accounts.update_one({'_id': acc['_id']}, {'$set': {'admin_downloaded': True}})
                else:
                    await self.accounts.delete_one({'_id': acc['_id']})

            except Exception as e:
                logger.error(f'Error searching session for {acc.get("phone_number")}: {e}')

        return files_to_send

    async def get_settings(self) -> Dict:
        return await self.settings.find_one({'_id': 'global_settings'}) or {}

    async def update_settings(self, key: str, value: Any) -> bool:
        result = await self.settings.update_one({'_id': 'global_settings'}, {'$set': {key: value}})
        return result.modified_count > 0

    async def get_countries(self) -> List[Dict]:
        return await self.countries.find({}).to_list(length=None)

    async def add_new_country(self, country_data: Dict) -> bool:
        try:
            if 'premium_price' not in country_data:
                country_data['premium_price'] = country_data.get('base_price', 0.5) * 2
            result = await self.countries.update_one({'code': country_data['code']}, {'$setOnInsert': country_data}, upsert=True)
            return result.upserted_id is not None
        except Exception as e:
            logger.error(f'Error adding new country: {e}')
            return False

    async def delete_country(self, country_code: str) -> bool:
        result = await self.countries.delete_one({'code': country_code})
        return result.deleted_count > 0

    async def update_country_config(self, country_code: str, key: str, value: Any) -> bool:
        result = await self.countries.update_one({'code': country_code}, {'$set': {key: value}})
        return result.modified_count > 0

    async def get_daily_stats(self) -> Dict:
        # আজকের সারাদিনের মোট কাজের বিবরণী বা ডেইলি স্ট্যাটাস রিপোর্ট তৈরি করে।
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day)
        
        # আজকের মোট গৃহীত একাউন্টস
        accounts_today = await self.accounts.find({'created_at': {'$gte': today_start}}).to_list(length=None)
        total_accounts = len(accounts_today)
        
        # কান্ট্রি-ওয়াইজ ব্রেকডাউন
        country_breakdown = {}
        for acc in accounts_today:
            c_code = acc.get('country_code', 'Unknown')
            status = acc.get('acceptance_status', 'pending')
            if c_code not in country_breakdown:
                country_breakdown[c_code] = {'total': 0, 'accepted': 0, 'rejected': 0}
            country_breakdown[c_code]['total'] += 1
            if status == 'accepted':
                country_breakdown[c_code]['accepted'] += 1
            elif status in ['rejected', 'expired']:
                country_breakdown[c_code]['rejected'] += 1

        # আজকের মোট সফল উইথড্রাল রিকোয়েস্টসমূহ
        today_str = now.strftime('%Y-%m-%d')
        orders_today = await self.orders.find({
            'status': 'completed',
            'created_at': {'$regex': f'^{today_str}'}
        }).to_list(length=None)
        
        total_withdrawn = sum(order.get('amount', 0.0) for order in orders_today)
        
        return {
            'total_accounts': total_accounts,
            'country_breakdown': country_breakdown,
            'total_withdrawn': total_withdrawn
        }

    async def archive_withdrawal_accounts(self, user_id: int) -> Dict[str, int]:
        pipeline = [
            {'$match': {'user_id': user_id, 'acceptance_status': 'accepted'}},
            {'$group': {'_id': '$country_code', 'count': {'$sum': 1}}}
        ]
        cursor = self.accounts.aggregate(pipeline)
        result = await cursor.to_list(length=None)
        stats = {}
        for doc in result:
            if doc.get('_id'):
                stats[doc['_id']] = doc['count']
        await self.accounts.update_many({'user_id': user_id, 'acceptance_status': 'accepted'}, {'$set': {'acceptance_status': 'withdrawn'}})
        return stats