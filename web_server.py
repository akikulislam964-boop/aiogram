import os
import socket
import urllib.request
import urllib.parse
import time
import asyncio
from aiohttp import web
import config
from config import COUNTRY_FLAGS

DOWNLOAD_TOKENS = {}
ACTIVE_LOGIN_PHONES = set()

# --- HTML Templates ---
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Admin Login</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f6f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); width: 100%; max-width: 340px; text-align: center; }
        h2 { color: #0088cc; margin-top: 0; margin-bottom: 20px; }
        input[type="password"] { width: 100%; padding: 12px; margin: 10px 0 20px 0; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background-color: #0088cc; color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; }
        .error { color: #f44336; font-size: 14px; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>🔐 Web Admin Panel</h2>
        <form action="/admin/login" method="POST">
            <input type="password" name="password" placeholder="Enter Admin Password" required>
            <button type="submit">Login</button>
        </form>
        {error_msg}
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Web Admin Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 10px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: white; padding: 12px 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); }
        h1 { margin: 0; font-size: 18px; color: #0088cc; }
        .logout-btn { background-color: #f44336; color: white; padding: 6px 12px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 12px; }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; }
        @media (min-width: 768px) { .stats-grid { grid-template-columns: repeat(4, 1fr); } }
        .stat-card { background: white; padding: 12px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); text-align: center; }
        .stat-card h3 { margin: 0 0 6px 0; color: #888; font-size: 11px; text-transform: uppercase; }
        .stat-card p { margin: 0; font-size: 22px; font-weight: 700; color: #333; }
        
        /* ২-কলাম মোবাইল ও ৩-কলাম পিসি গ্রিড লেআউট */
        .main-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; }
        @media (min-width: 1024px) { .main-grid { grid-template-columns: repeat(3, 1fr); gap: 20px; } }
        
        .card { background: white; padding: 12px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); display: flex; flex-direction: column; justify-content: space-between; }
        @media (min-width: 768px) { .card { padding: 22px; border-radius: 10px; } }
        h2 { margin-top: 0; font-size: 13px; color: #444; border-bottom: 2px solid #f0f2f5; padding-bottom: 8px; margin-bottom: 12px; }
        @media (min-width: 768px) { h2 { font-size: 17px; } }
        
        .wd-item { display: flex; flex-direction: column; padding: 10px 0; border-bottom: 1px solid #f0f2f5; gap: 8px; width: 100%; }
        .wd-item:last-child { border-bottom: none; }
        .wd-details { line-height: 1.5; font-size: 11px; color: #444; }
        .wd-actions { display: flex; gap: 6px; }
        
        .btn { padding: 6px 12px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; text-decoration: none; text-align: center; font-size: 11px; }
        .btn-pay { background-color: #2e7d32; color: white; }
        .btn-rej { background-color: #c62828; color: white; }
        .btn-update { background-color: #0088cc; color: white; width: 100%; margin-top: 10px; padding: 8px; }
        .btn-delete { background-color: #c62828; color: white; padding: 5px 8px; font-size: 10px; }
        
        .alert { padding: 12px 15px; background-color: #e8f5e9; color: #2e7d32; border-left: 5px solid #2e7d32; border-radius: 6px; margin-bottom: 15px; font-weight: 500; font-size: 13px; }
        .no-data { text-align: center; padding: 15px; color: #888; font-style: italic; font-size: 12px; }
        .form-group { margin-bottom: 10px; }
        .form-group label { display: block; font-weight: 600; margin-bottom: 4px; font-size: 11px; color: #555; }
        .form-control { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; font-size: 11px; }
        .checkbox-group { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
        .checkbox-group input { width: 16px; height: 18px; cursor: pointer; }
        .checkbox-group label { font-weight: 600; font-size: 12px; color: #555; cursor: pointer; }
        
        .table-responsive { overflow-x: auto; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); padding: 15px; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }
        th { background-color: #f8f9fa; padding: 10px; font-weight: 600; color: #555; border-bottom: 2px solid #dee2e6; }
        td { padding: 8px 10px; border-bottom: 1px solid #dee2e6; vertical-align: middle; }
        .tbl-input { width: 55px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Web Admin Dashboard</h1>
            <a href="/admin/logout" class="logout-btn">Logout</a>
        </div>
        
        {alert_box}

        <div class="stats-grid">
            <div class="stat-card">
                <h3>👥 Total Users</h3>
                <p>{total_users}</p>
            </div>
            <div class="stat-card">
                <h3>📱 Active Sessions</h3>
                <p>{total_active}</p>
            </div>
            <div class="stat-card">
                <h3>🏦 Pending Withdraw</h3>
                <p>{pending_wd_count}</p>
            </div>
            <div class="stat-card">
                <h3>🌍 Total Countries</h3>
                <p>{total_countries}</p>
            </div>
        </div>

        <div class="main-grid">
            <div class="card">
                <h2>🏦 Pending Withdrawal Requests</h2>
                {withdraw_items}
            </div>
            
            <div class="card">
                <h2>📥 Session Download Manager</h2>
                <form action="/admin/download_sessions" method="POST">
                    <div class="form-group">
                        <label>Select Country</label>
                        <select name="code" class="form-control" required>
                            {country_options}
                        </select>
                    </div>
                    <div style="display: grid; grid-template-columns: 1.2fr 1fr; gap: 10px;">
                        <div class="form-group">
                            <label>Category</label>
                            <select name="cat" class="form-control" required>
                                <option value="premium">💎 Premium</option>
                                <option value="free">🟢 Free</option>
                                <option value="register">🔵 Register</option>
                                <option value="limit">🔴 Limit</option>
                                <option value="all_valid">📂 All Valid Sessions</option>
                                <option value="multi_session">💻 Multi-Session</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Pcs</label>
                            <input type="number" name="amount" class="form-control" value="10" min="1" required>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-update" style="background-color: #0088cc;">Download ZIP</button>
                </form>
            </div>

            <div class="card">
                <h2>💰 User Balance & Finance Manager</h2>
                <form action="/admin/update_balance" method="POST">
                    <div class="form-group">
                        <label>User Telegram ID</label>
                        <input type="number" name="user_id" class="form-control" placeholder="e.g. 123456789" required>
                    </div>
                    <div class="form-group">
                        <label>Amount to Add/Deduct ($)</label>
                        <input type="number" step="0.01" name="amount" class="form-control" placeholder="Use negative (-) to deduct" required>
                    </div>
                    <div class="form-group">
                        <label>Reason / Description</label>
                        <input type="text" name="reason" class="form-control" placeholder="Web Admin Update" required>
                    </div>
                    <button type="submit" class="btn btn-update" style="background-color: #2e7d32;">Update Balance</button>
                </form>
            </div>

            <div class="card">
                <h2>🚫 User Ban/Unban Manager</h2>
                <form action="/admin/ban_unban" method="POST">
                    <div class="form-group">
                        <label>User Telegram ID</label>
                        <input type="number" name="user_id" class="form-control" placeholder="e.g. 123456789" required>
                    </div>
                    <div class="form-group">
                        <label>Action</label>
                        <select name="action" class="form-control" required>
                            <option value="ban">🚫 Ban User</option>
                            <option value="unban">✅ Unban User</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-update" style="background-color: #c62828;">Apply Action</button>
                </form>
            </div>

            <div class="card">
                <h2>⚙️ Bot Configuration</h2>
                <form action="/admin/update_settings" method="POST">
                    <div class="checkbox-group">
                        <input type="checkbox" id="bot_mode" name="bot_mode" {bot_mode_checked}>
                        <label for="bot_mode">Bot Mode (Bot Active)</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="add_account_mode" name="add_account_mode" {add_account_checked}>
                        <label for="add_account_mode">Add Account Active</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="wd_mode" name="wd_mode" {wd_mode_checked}>
                        <label for="wd_mode">Withdrawal Active</label>
                    </div>
                    <hr style="border: 0; border-top: 1px solid #f0f2f5; margin: 10px 0;">
                    <div class="form-group">
                        <label>Min Withdrawal ($)</label>
                        <input type="number" step="0.1" name="wd_min" class="form-control" value="{wd_min_val}" required>
                    </div>
                    <div class="form-group">
                        <label>Global 2FA Password</label>
                        <input type="text" name="twofa_password" class="form-control" value="{twofa_val}" placeholder="admin password">
                    </div>
                    <button type="submit" class="btn btn-update">Update Settings</button>
                </form>
            </div>

            <div class="card">
                <h2>📢 Send Broadcast Message</h2>
                <form action="/admin/broadcast" method="POST">
                    <div class="form-group">
                        <label>Your Message (HTML Supported)</label>
                        <textarea name="message" class="form-control" rows="3" placeholder="Write broadcast message here..." required></textarea>
                    </div>
                    <button type="submit" class="btn btn-update" style="background-color: #3f51b5;">Send Broadcast</button>
                </form>
            </div>

            <div class="card">
                <h2>➕ Add New Country</h2>
                <form action="/admin/add_country" method="POST">
                    <div class="form-group">
                        <label>Country Code</label>
                        <input type="text" name="code" class="form-control" placeholder="+880" required>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group">
                            <label>Free Price ($)</label>
                            <input type="number" step="0.01" name="free_price" class="form-control" placeholder="0.40" required>
                        </div>
                        <div class="form-group">
                            <label>New Price ($)</label>
                            <input type="number" step="0.01" name="register_price" class="form-control" placeholder="0.40" required>
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group">
                            <label>Spam Price ($)</label>
                            <input type="number" step="0.01" name="limit_price" class="form-control" placeholder="0.20" required>
                        </div>
                        <div class="form-group">
                            <label>Capacity</label>
                            <input type="number" name="capacity" class="form-control" placeholder="1000" required>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Confirm Time (Seconds)</label>
                        <input type="number" name="confirm_time" class="form-control" placeholder="120" required>
                    </div>
                    <button type="submit" class="btn btn-update">Add Country</button>
                </form>
            </div>
        </div>

        <div class="card">
            <h2>📜 Recent Transactions (Last 5 Logs)</h2>
            <div class="table-responsive">
                <table style="font-size: 13px;">
                    <thead>
                        <tr>
                            <th>Date & Time</th>
                            <th>User Name</th>
                            <th>Amount</th>
                            <th>Reason / Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        {transaction_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h2>🌍 Active Country Settings & Price Manager</h2>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Flag</th>
                            <th>Code</th>
                            <th>Name</th>
                            <th>Free Price</th>
                            <th>Register</th>
                            <th>Spam/Limit</th>
                            <th>Capacity</th>
                            <th>Timer (s)</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {country_table_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_public_ip():
    try:
        return urllib.request.urlopen('https://api.ipify.org', timeout=5).read().decode('utf8')
    except:
        return None

# --- Web App Routes ---

async def login_get_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie == 'valid':
        return web.HTTPFound('/admin')
    return web.Response(text=LOGIN_HTML.replace('{error_msg}', ''), content_type='text/html')

async def login_post_handler(request):
    data = await request.post()
    password = data.get('password')
    tgt_pass = getattr(config, 'ADMIN_PASSWORD', 'admin123')
    
    if password == tgt_pass:
        response = web.HTTPFound('/admin')
        response.set_cookie('admin_session', 'valid', max_age=3600)
        return response
    else:
        err = '<p class="error">❌ Incorrect password. Please try again.</p>'
        return web.Response(text=LOGIN_HTML.replace('{error_msg}', err), content_type='text/html')

async def logout_handler(request):
    response = web.HTTPFound('/admin/login')
    response.del_cookie('admin_session')
    return response

async def admin_dashboard_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    
    users = await db.get_users()
    total_users_count = len(users)
    active_count = await db.get_active_accounts_count()
    pending_orders = await db.get_pending_withdrawal_orders()
    countries = await db.get_countries()
    settings = await db.get_settings()
    
    alert_val = request.query.get('alert', '')
    alert_box = f'<div class="alert">{urllib.parse.unquote(alert_val)}</div>' if alert_val else ''
    
    wd_items_html = ""
    if not pending_orders:
        wd_items_html = '<div class="no-data">No pending withdrawal requests found! 🎉</div>'
    else:
        for order in pending_orders:
            order_id = order.get('order_id')
            wd_items_html += f"""
            <div class="wd-item">
                <div class="wd-details">
                    👤 <b>User ID:</b> <code>{order.get('user_id')}</code><br>
                    💰 <b>Amount:</b> <span style="color:#2e7d32; font-weight:bold;">${order.get('amount', 0.0):.2f}</span><br>
                    💳 <b>Wallet:</b> <code>{order.get('address')}</code><br>
                    📅 <b>Date:</b> {order.get('created_at')}
                </div>
                <div class="wd-actions">
                    <a href="/admin/action?action=pay&id={order_id}" class="btn btn-pay">✅ Pay</a>
                    <a href="/admin/action?action=rej&id={order_id}" class="btn btn-rej">❌ Reject</a>
                </div>
            </div>
            """
            
    country_options = ""
    for c in countries:
        code = c.get('code')
        flag = c.get('flag', COUNTRY_FLAGS.get(code, "🌐"))
        country_options += f'<option value="{code}">{flag} {c.get("name", "Unknown")} ({code})</option>'
        
    txs = await db.get_recent_transactions(5)
    transaction_rows = ""
    if not txs:
        transaction_rows = '<tr><td colspan="4" style="text-align:center;">No recent transactions.</td></tr>'
    else:
        for tx in txs:
            sign = "+" if tx.get('amount', 0.0) > 0 else ""
            color = "#2e7d32" if tx.get('amount', 0.0) > 0 else "#c62828"
            transaction_rows += f"""
            <tr>
                <td><code>{tx.get('timestamp', 'N/A')}</code></td>
                <td><b>{tx.get('display_name', 'Unknown')}</b></td>
                <td style="color:{color}; font-weight:bold;">{sign}${abs(tx.get('amount', 0.0)):.2f}</td>
                <td>{tx.get('reason', '')}</td>
            </tr>
            """

    country_table_rows = ""
    if not countries:
        country_table_rows = '<tr><td colspan="9" style="text-align:center;">No countries added yet. Use the form above to add!</td></tr>'
    else:
        try: countries.sort(key=lambda x: int(str(x.get("code", "0")).replace('+', '') or 0))
        except: pass
        
        for c in countries:
            code = c.get('code')
            flag = c.get('flag', COUNTRY_FLAGS.get(code, "🌐"))
            country_table_rows += f"""
            <tr>
                <form action="/admin/update_country" method="POST">
                    <input type="hidden" name="code" value="{code}">
                    <td style="font-size: 20px;">{flag}</td>
                    <td><b>{code}</b></td>
                    <td>{c.get('name', 'Unknown')}</td>
                    <td>$<input type="number" step="0.01" name="free_price" class="tbl-input" value="{c.get('free_price', 0.0):.2f}"></td>
                    <td>$<input type="number" step="0.01" name="register_price" class="tbl-input" value="{c.get('register_price', 0.0):.2f}"></td>
                    <td>$<input type="number" step="0.01" name="limit_price" class="tbl-input" value="{c.get('limit_price', 0.0):.2f}"></td>
                    <td><input type="number" name="capacity" class="tbl-input" value="{c.get('capacity', 0)}"></td>
                    <td><input type="number" name="confirm_time" class="tbl-input" value="{c.get('confirm_time', 120)}"></td>
                    <td>
                        <button type="submit" name="action" value="update" class="btn btn-pay" style="padding: 5px 10px; font-size:11px;">Update</button>
                        <button type="submit" name="action" value="delete" class="btn btn-delete" onclick="return confirm('Are you sure you want to delete {code}?')">Delete</button>
                    </td>
                </form>
            </tr>
            """
            
    bot_mode_checked = "checked" if settings.get('bot_mode', True) else ""
    add_account_checked = "checked" if settings.get('add_account_mode', True) else ""
    wd_mode_checked = "checked" if settings.get('wd_mode', True) else ""
    
    text = DASHBOARD_HTML.replace('{alert_box}', alert_box)
    text = text.replace('{total_users}', str(total_users_count))
    text = text.replace('{total_active}', str(active_count))
    text = text.replace('{pending_wd_count}', str(len(pending_orders)))
    text = text.replace('{total_countries}', str(len(countries)))
    text = text.replace('{withdraw_items}', wd_items_html)
    text = text.replace('{country_options}', country_options)
    text = text.replace('{transaction_rows}', transaction_rows)
    text = text.replace('{country_table_rows}', country_table_rows)
    
    text = text.replace('{bot_mode_checked}', bot_mode_checked)
    text = text.replace('{add_account_checked}', add_account_checked)
    text = text.replace('{wd_mode_checked}', wd_mode_checked)
    text = text.replace('{wd_min_val}', f"{settings.get('wd_min', 3.0):.1f}")
    text = text.replace('{twofa_val}', str(settings.get('twofa_password', '')))
    
    return web.Response(text=text, content_type='text/html')

async def admin_action_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    bot = request.app['bot']
    
    action = request.query.get('action')
    order_id = request.query.get('id')
    
    alert_msg = "No action taken."
    order = await db.get_order(order_id)
    
    if order and order.get('status') == 'pending':
        user_id = order.get('user_id')
        amount = order.get('amount', 0.0)
        address = order.get('address')
        
        if action == 'pay':
            await db.update_order_status(order_id, "completed")
            alert_msg = f"✅ Payout of ${amount:.2f} marked as COMPLETED!"
            try:
                txt = f"🎉 **Withdrawal Paid Successfully!**\n\n💰 **Amount:** `${amount:.2f}`\n💳 **To Address:** `{address}`\n⚙️ **Status:** Completed (Paid)"
                await bot.send_message(user_id, txt, parse_mode='md')
            except: pass
            
        elif action == 'rej':
            await db.update_order_status(order_id, "rejected")
            await db.update_balance(user_id, amount)
            await db.log_balance_transaction(user_id, amount, "Withdrawal Rejected (Refunded via Web Dashboard)", by_admin=True)
            alert_msg = f"❌ Payout of ${amount:.2f} successfully REJECTED and refunded!"
            try:
                txt = f"❌ **Withdrawal Rejected!**\n\n💰 **Amount:** `${amount:.2f}`\n⚠️ Your withdrawal was rejected and refunded to your balance."
                await bot.send_message(user_id, txt, parse_mode='md')
            except: pass
            
    return web.HTTPFound(f'/admin?alert={urllib.parse.quote(alert_msg)}')

async def add_country_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    data = await request.post()
    
    code = data.get('code', '').strip()
    if not code.startswith('+'): 
        code = '+' + code
        
    try:
        free_price = float(data.get('free_price', 0.0))
        register_price = float(data.get('register_price', 0.0))
        limit_price = float(data.get('limit_price', 0.0))
        capacity = int(data.get('capacity', 0))
        confirm_time = int(data.get('confirm_time', 120))
    except:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ Invalid numeric values!'))
        
    from bot_utils import COUNTRY_FLAGS
    import config
    c_name = config.COUNTRY_NAMES.get(code, "Unknown")
    flag = COUNTRY_FLAGS.get(code, "🌐")
    
    country_data = {
        'code': code,
        'free_price': free_price,
        'register_price': register_price,
        'limit_price': limit_price,
        'premium_price': free_price * 2,
        'capacity': capacity,
        'confirm_time': confirm_time,
        'base_price': free_price,
        'price': free_price,
        'status': True,
        'cspam': "V2",
        'api_type': "Desktop",
        'name': c_name,
        'flag': flag,
        'proxy': None
    }
    
    await db.add_new_country(country_data)
    return web.HTTPFound(f'/admin?alert=' + urllib.parse.quote(f'✅ Country {code} added successfully!'))

async def update_country_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    data = await request.post()
    
    code = data.get('code')
    action = data.get('action')
    
    if action == 'delete':
        await db.delete_country(code)
        return web.HTTPFound(f'/admin?alert=' + urllib.parse.quote(f'🗑️ Country {code} successfully deleted!'))
        
    try:
        free_price = float(data.get('free_price', 0.0))
        register_price = float(data.get('register_price', 0.0))
        limit_price = float(data.get('limit_price', 0.0))
        capacity = int(data.get('capacity', 0))
        confirm_time = int(data.get('confirm_time', 120))
    except:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ Invalid numeric values!'))
        
    await db.update_country_config(code, 'free_price', free_price)
    await db.update_country_config(code, 'base_price', free_price)
    await db.update_country_config(code, 'price', free_price)
    await db.update_country_config(code, 'register_price', register_price)
    await db.update_country_config(code, 'limit_price', limit_price)
    await db.update_country_config(code, 'premium_price', free_price * 2)
    await db.update_country_config(code, 'capacity', capacity)
    await db.update_country_config(code, 'confirm_time', confirm_time)
    
    return web.HTTPFound(f'/admin?alert=' + urllib.parse.quote(f'✅ Country {code} rates successfully updated!'))

async def update_settings_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    data = await request.post()
    
    bot_mode = 'bot_mode' in data
    add_account_mode = 'add_account_mode' in data
    wd_mode = 'wd_mode' in data
    
    try: wd_min = float(data.get('wd_min', 3.0))
    except: wd_min = 3.0
    
    twofa_password = data.get('twofa_password', '').strip()
    twofa_val = twofa_password if twofa_password else None
    
    await db.update_settings('bot_mode', bot_mode)
    await db.update_settings('add_account_mode', add_account_mode)
    await db.update_settings('wd_mode', wd_mode)
    await db.update_settings('wd_min', wd_min)
    await db.update_settings('twofa_password', twofa_val)
    
    return web.HTTPFound(f'/admin?alert=' + urllib.parse.quote('✅ Global configurations successfully updated!'))

async def broadcast_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    bot = request.app['bot']
    data = await request.post()
    
    message = data.get('message', '').strip()
    if not message:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ Broadcast message is empty!'))
        
    async def run_broadcast():
        users = await db.get_users()
        sent = 0
        for u in users:
            try:
                await bot.send_message(u['user_id'], message, parse_mode='html')
                sent += 1
                await asyncio.sleep(0.33)
            except: pass
        print(f"📢 Web Broadcast completed! Sent to {sent} users.")
        
    asyncio.create_task(run_broadcast())
    return web.HTTPFound('/admin?alert=' + urllib.parse.quote('📢 Broadcast started in background! Sending...'))

async def download_sessions_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    data = await request.post()
    
    code = data.get('code')
    cat = data.get('cat')
    try:
        amount = int(data.get('amount', 10))
    except:
        amount = 10
        
    files = await db.get_and_delete_sessions(code, cat, amount)
    if not files:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ No active sessions found in this folder!'))
        
    # ZIP ফাইল তৈরি
    zip_name = f"{code}_{cat}_{amount}_{int(time.time())}.zip"
    temp_download_dir = os.path.join(config.SESSIONS_DIR, 'temp_downloads')
    os.makedirs(temp_download_dir, exist_ok=True)
    zip_path = os.path.join(temp_download_dir, zip_name)
    
    with zipfile.ZipFile(zip_path, 'w') as z:
        for f in files:
            if os.path.exists(f):
                z.write(f, os.path.basename(f))
                os.remove(f)
                
    response = web.FileResponse(zip_path, headers={
        'Content-Disposition': f'attachment; filename="{zip_name}"'
    })
    return response

async def update_balance_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    data = await request.post()
    
    try:
        user_id = int(data.get('user_id', 0))
        amount = float(data.get('amount', 0.0))
        reason = data.get('reason', 'Web Admin Update').strip()
    except:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ Invalid User ID or amount!'))
        
    user = await db.get_user(user_id)
    if not user:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ User not found in database!'))
        
    new_bal = await db.update_balance(user_id, amount)
    await db.log_balance_transaction(user_id, amount, reason, by_admin=True)
    
    return web.HTTPFound('/admin?alert=' + urllib.parse.quote(f'✅ Balance for {user.get("first_name", "User")} successfully updated! New Balance: ${new_bal:.2f}'))

async def ban_unban_handler(request):
    cookie = request.cookies.get('admin_session')
    if cookie != 'valid':
        return web.HTTPFound('/admin/login')
        
    db = request.app['db']
    bot = request.app['bot']
    data = await request.post()
    
    try:
        user_id = int(data.get('user_id', 0))
        action = data.get('action')
    except:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ Invalid User ID!'))
        
    user = await db.get_user(user_id)
    if not user:
        return web.HTTPFound('/admin?alert=' + urllib.parse.quote('❌ User not found in database!'))
        
    alert_msg = ""
    if action == 'ban':
        await db.ban_user(user_id)
        alert_msg = f"🚫 User {user.get('first_name', 'User')} ({user_id}) successfully BANNED!"
        try:
            await bot.send_message(user_id, "❌ <b>You have been banned from using this bot by the administrator.</b>", parse_mode='html')
        except: pass
    elif action == 'unban':
        await db.unban_user(user_id)
        alert_msg = f"✅ User {user.get('first_name', 'User')} ({user_id}) successfully UNBANNED!"
        try:
            await bot.send_message(user_id, "🎉 <b>Congratulations! You have been unbanned by the administrator.</b>", parse_mode='html')
        except: pass
        
    return web.HTTPFound(f'/admin?alert=' + urllib.parse.quote(alert_msg))

async def download_handler(request):
    token = request.match_info.get('token')
    token_data = DOWNLOAD_TOKENS.get(token)
    if not token_data or time.time() > token_data['expires_at']:
        return web.Response(text="❌ Link Expired or Invalid!", status=410)
    
    file_path = token_data['file_path']
    if not os.path.exists(file_path):
        return web.Response(text="❌ File not found on server!", status=404)
    
    return web.FileResponse(file_path, headers={
        'Content-Disposition': f'attachment; filename="{os.path.basename(file_path)}"'
    })

async def clean_expired_tokens_loop():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        to_delete = []
        for token, data in list(DOWNLOAD_TOKENS.items()):
            if now > data['expires_at']:
                to_delete.append(token)
                if os.path.exists(data['file_path']):
                    try: os.remove(data['file_path'])
                    except: pass
        for token in to_delete:
            del DOWNLOAD_TOKENS[token]

async def start_web_server(bot, db):
    app = web.Application()
    app['db'] = db
    app['bot'] = bot
    
    app.router.add_get('/admin/login', login_get_handler)
    app.router.add_post('/admin/login', login_post_handler)
    app.router.add_get('/admin/logout', logout_handler)
    app.router.add_get('/admin', admin_dashboard_handler)
    app.router.add_get('/admin/action', admin_action_handler)
    app.router.add_post('/admin/add_country', add_country_handler)
    app.router.add_post('/admin/update_country', update_country_handler)
    app.router.add_post('/admin/update_settings', update_settings_handler)
    app.router.add_post('/admin/broadcast', broadcast_handler)
    app.router.add_post('/admin/download_sessions', download_sessions_handler)
    app.router.add_post('/admin/update_balance', update_balance_handler)
    app.router.add_post('/admin/ban_unban', ban_unban_handler)
    app.router.add_get('/download/{token}', download_handler)
    app.router.add_get('/', lambda r: web.HTTPFound('/admin'))
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    local_ip = get_local_ip()
    pub_ip = get_public_ip()
    
    print("==================================================")
    print("🌐 WEB ADMIN DASHBOARD STARTED SUCCESSFULLY!")
    print(f"🔗 Local Dashboard Link: http://{local_ip}:8080/admin")
    if pub_ip:
        print(f"🔗 Public Dashboard Link: http://{pub_ip}:8080/admin")
    print("==================================================")
    
    asyncio.create_task(clean_expired_tokens_loop())
