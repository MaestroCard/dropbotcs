# cardlink_payment.py - интеграция с Cardlink для оплаты рублями

import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

CARDLINK_SHOP_ID = os.getenv('CARDLINK_SHOP_ID')
CARDLINK_TOKEN = os.getenv('CARDLINK_TOKEN')
CARDLINK_API_URL = "https://cardlink.link/api/v1"

if not CARDLINK_SHOP_ID or not CARDLINK_TOKEN:
    print("[CARDLINK] Предупреждение: CARDLINK_SHOP_ID или CARDLINK_TOKEN не найдены в .env")


async def create_payment(amount: float, description: str, order_id: str, base_url: str = None):
    """
    Создает ссылку на оплату через Cardlink
    
    Args:
        amount: Сумма в валюте (USD или RUB)
        description: Описание платежа
        order_id: Уникальный ID заказа
        base_url: Базовый URL для редиректов (опционально). Будут добавлены /success, /fail, /result
    
    Returns:
        dict: {"success": True, "payment_url": "...", "payment_id": "..."} или {"success": False, "error": "..."}
    """
    url = f"{CARDLINK_API_URL}/bill/create"
    
    # Формируем данные как form-data (как в curl)
    data = {
        "amount": str(amount),
        "order_id": order_id,
        "description": description,
        "type": "normal",
        "shop_id": CARDLINK_SHOP_ID,
        "currency": "RUB",
        "currency_in": "RUB",
        "currency_out": "RUB",
        "payer_pays_commission": "0",
        "name": "CS2 Skin Purchase"
    }
    
    if base_url:
        # Отдельные URL для каждого типа callback
        data["success_url"] = f"{base_url}/success"
        data["fail_url"] = f"{base_url}/fail"
        data["result_url"] = f"{base_url}/result"
        data["custom"] = base_url  # Для дополнительной информации
    
    headers = {
        "Authorization": f"Bearer {CARDLINK_TOKEN}"
        # Content-Type не указываем - aiohttp сам установит для form-data
    }
    
    # === ПОДРОБНОЕ ЛОГИРОВАНИЕ ДЛЯ ОТЛАДКИ ===
    import json
    debug_log = f"""
=== CARDLINK API REQUEST DEBUG ===
URL: {url}
Method: POST

HEADERS:
{json.dumps(headers, indent=2)}

FORM DATA:
{json.dumps(data, indent=2, ensure_ascii=False)}

CARDLINK_SHOP_ID: {CARDLINK_SHOP_ID}
CARDLINK_TOKEN (first 20 chars): {CARDLINK_TOKEN[:20] if CARDLINK_TOKEN else 'NOT SET'}...
==================================
"""
    print(debug_log)
    
    try:
        async with aiohttp.ClientSession() as session:
            print(f"[CARDLINK] Sending POST request to: {url}")
            print(f"[CARDLINK] Data keys: {list(data.keys())}")
            print(f"[CARDLINK] Success URL: {data.get('success_url', 'NOT SET')}")
            print(f"[CARDLINK] Fail URL: {data.get('fail_url', 'NOT SET')}")
            print(f"[CARDLINK] Result URL: {data.get('result_url', 'NOT SET')}")
            
            async with session.post(url, data=data, headers=headers, timeout=30) as resp:
                response_text = await resp.text()
                print(f"[CARDLINK] Status: {resp.status}, Response: {response_text[:1000]}")
                print(f"[CARDLINK] Response headers: {dict(resp.headers)}")
                
                # Парсим JSON из текста (тело уже прочитано)
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    response_data = {"text": response_text}
                
                if resp.status in (200, 201):
                    # Проверяем, не вернул ли Cardlink ошибку внутри success=false
                    success_val = response_data.get("success")
                    if success_val == "false" or success_val == False:
                        error_msg = response_data.get("message", "Unknown error")
                        print(f"[CARDLINK] API returned error: {error_msg}")
                        print(f"[CARDLINK] Full error response: {response_text}")
                        return {
                            "success": False,
                            "error": error_msg,
                            "details": response_data
                        }
                    
                    # Проверяем структуру ответа от Cardlink
                    # Исправляем экранированные слэши в URL
                    link_url = response_data.get("link_url", "").replace("\\/", "/")
                    link_page_url = response_data.get("link_page_url", "").replace("\\/", "/") if response_data.get("link_page_url") else None
                    
                    if link_url:
                        # Формат: {"success":"true","bill_id":"...","link_url":"...","link_page_url":"..."}
                        return {
                            "success": True,
                            "payment_url": link_url,
                            "payment_page_url": link_page_url,  # /transfer/ для СБП
                            "payment_id": response_data.get("bill_id"),
                            "status": "created"
                        }
                    elif response_data.get("data") and response_data["data"].get("link"):
                        return {
                            "success": True,
                            "payment_url": response_data["data"]["link"],
                            "payment_id": response_data["data"].get("id"),
                            "status": response_data.get("status")
                        }
                    elif response_data.get("link"):
                        return {
                            "success": True,
                            "payment_url": response_data["link"],
                            "payment_id": response_data.get("id"),
                            "status": response_data.get("status")
                        }
                    else:
                        return {
                            "success": False,
                            "error": "Неверный формат ответа",
                            "details": response_data
                        }
                else:
                    return {
                        "success": False,
                        "error": response_data.get("message", f"HTTP {resp.status}"),
                        "details": response_data
                    }
    except Exception as e:
        print(f"[CARDLINK ERROR] {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


async def check_payment_status(payment_id: str):
    """
    Проверяет статус платежа
    
    Args:
        payment_id: ID платежа от Cardlink
    
    Returns:
        dict: {"success": True, "status": "paid|pending|cancelled", ...} или {"success": False, "error": "..."}
    """
    url = f"{CARDLINK_API_URL}/bill/{payment_id}"
    
    headers = {
        "Authorization": f"Bearer {CARDLINK_TOKEN}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                try:
                    data = await resp.json()
                except:
                    data = {"text": await resp.text()}
                
                if resp.status == 200:
                    bill_data = data.get("data", data)
                    return {
                        "success": True,
                        "status": bill_data.get("status"),
                        "amount": bill_data.get("amount"),
                        "order_id": bill_data.get("order_id"),
                        "data": data
                    }
                else:
                    return {
                        "success": False,
                        "error": data.get("message", f"HTTP {resp.status}")
                    }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Тест функции
if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await create_payment(
            amount=1.50,
            description="Тестовый платеж за скин CS2",
            order_id="test_001"
        )
        print("Result:", result)
    
    asyncio.run(test())
