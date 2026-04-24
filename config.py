from dotenv import load_dotenv
import os

load_dotenv()

OWNER_ID = os.getenv('OWNER_ID')
if OWNER_ID:
    OWNER_ID = int(OWNER_ID)
else:
    OWNER_ID = None
    print("OWNER_ID не указан в .env — уведомления владельцу отключены")
    
REFERRALS_FOR_GIFT = int(os.getenv("REFERRALS_FOR_GIFT", "3"))

# Реферальная админка
REFERRAL_REVIEW_THRESHOLD = int(os.getenv("REFERRAL_REVIEW_THRESHOLD", "50"))
DAILY_REFERRAL_LIMIT      = int(os.getenv("DAILY_REFERRAL_LIMIT", "15"))

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    print("[WARNING] ADMIN_TOKEN не задан в .env — admin-эндпоинты незащищены!")