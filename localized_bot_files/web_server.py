import os
import socket
import urllib.request
import time
import asyncio
from aiohttp import web
import config

# টেম্পোরারি ডাউনলোড লিংকগুলোর মেমোরি স্টোরেজ
DOWNLOAD_TOKENS = {} # token: {"file_path": path, "expires_at": timestamp}

def get_local_ip():
    # সার্ভারের লোকাল আইপি অ্যাড্রেস বের করে।
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_public_ip():
    # সার্ভারের পাবলিক আইপি অ্যাড্রেস বের করে।
    try:
        return urllib.request.urlopen('https://api.ipify.org', timeout=5).read().decode('utf8')
    except:
        return None

async def download_handler(request):
    # টেম্পোরারি লিংক রিকোয়েস্ট হ্যান্ডল করে ফাইল ডাউনলোড করায়।
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
    # প্রতি ১ মিনিটে জিপ ফাইল এবং টোকেনগুলো সার্ভার থেকে ডিলিট করে।
    while True:
        await asyncio.sleep(60)
        now = time.time()
        to_delete = []
        for token, data in list(DOWNLOAD_TOKENS.items()):
            if now > data['expires_at']:
                to_delete.append(token)
                if os.path.exists(data['file_path']):
                    try: 
                        os.remove(data['file_path'])
                    except: 
                        pass
        for token in to_delete:
            del DOWNLOAD_TOKENS[token]

async def start_web_server():
    # ৮০৮০ পোর্টে এসিঙ্ক্রোনাস ওয়েব সার্ভার চালু করে।
    app = web.Application()
    app.router.add_get('/download/{token}', download_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # ৮০৮০ পোর্ট বাইন্ড করা হচ্ছে
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("🌐 Async Download Web Server started on port 8080!")
    asyncio.create_task(clean_expired_tokens_loop())