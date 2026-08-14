import logging
import sys

# লগিং কনফিগারেশন
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # FIX: Added encoding='utf-8' for log file to prevent UnicodeEncodeError
        logging.FileHandler("bot.log", encoding='utf-8'), 
        logging.StreamHandler(sys.stdout)         # কনসোলেও দেখাবে
    ]
)

logger = logging.getLogger("TeleBot")