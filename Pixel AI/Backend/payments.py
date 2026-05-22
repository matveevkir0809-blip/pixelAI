import hashlib
import requests
import os
from dotenv import load_dotenv
from urllib.parse import urlencode

load_dotenv()

ROBOKASSA_LOGIN = os.getenv("ROBOKASSA_LOGIN")
ROBOKASSA_PASSWORD1 = os.getenv("ROBOKASSA_PASSWORD1")
ROBOKASSA_PASSWORD2 = os.getenv("ROBOKASSA_PASSWORD2")
ROBOKASSA_IS_TEST = os.getenv("ROBOKASSA_IS_TEST", "true").lower() == "true"

ROBOKASSA_URL = "https://auth.robokassa.ru/Merchant/Index.aspx" if ROBOKASSA_IS_TEST else "https://merchant.robokassa.ru/Index.aspx"

def generate_signature(values: dict, password: str) -> str:
    """Генерация подписи для Robokassa"""
    signature_string = ":".join([
        values.get("MrchLogin", ""),
        str(values.get("OutSum", "")),
        str(values.get("InvId", "")),
        password
    ])
    return hashlib.md5(signature_string.encode('utf-8')).hexdigest()

def verify_signature(params: dict, password: str) -> bool:
    """Проверка подписи от Robokassa"""
    expected = hashlib.md5(
        f"{params.get('OutSum')}:{params.get('InvId')}:{params.get('SignatureValue')}:{password}".encode('utf-8')
    ).hexdigest().upper()
    return params.get('SignatureValue', '').upper() == expected

async def create_payment(amount: float, description: str, user_email: str, user_id: int):
    """Создание платежа через Robokassa"""
    try:
        import time
        inv_id = int(time.time() * 1000)  # Уникальный номер заказа
        
        # Параметры для формы
        values = {
            "MrchLogin": ROBOKASSA_LOGIN,
            "OutSum": f"{amount:.2f}",
            "InvId": inv_id,
            "Desc": description,
            "Email": user_email,
            "IsTest": "1" if ROBOKASSA_IS_TEST else "0",
            "Culture": "ru"
        }
        
        # Генерируем подпись
        signature = generate_signature(values, ROBOKASSA_PASSWORD1)
        values["SignatureValue"] = signature
        
        # Формируем ссылку на оплату
        payment_url = f"{ROBOKASSA_URL}?{urlencode(values)}"
        
        return {
            "success": True,
            "payment_id": str(inv_id),
            "payment_url": payment_url
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_payment_status(payment_id: str):
    """Проверка статуса платежа (через Result URL)"""
    # Robokassa сам отправляет уведомления на Result URL
    # Здесь можно добавить проверку в БД
    return {"success": True, "status": "pending", "payment_id": payment_id}