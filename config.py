from dotenv import load_dotenv
import os

load_dotenv()

OWNER_ID = os.getenv('OWNER_ID')
if OWNER_ID:
    OWNER_ID = int(OWNER_ID)
else:
    OWNER_ID = None
    print("OWNER_ID не указан в .env — уведомления владельцу отключены")