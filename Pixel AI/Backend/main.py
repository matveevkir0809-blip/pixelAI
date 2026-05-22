from fastapi import FastAPI, Depends, HTTPException, Form, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import os
import requests
import base64
import hashlib
import secrets
import subprocess
import json
from dotenv import load_dotenv

load_dotenv()

# ===== НАСТРОЙКА ПРИЛОЖЕНИЯ =====
app = FastAPI(title="Pixel AI — Токенная Система")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== БАЗА ДАННЫХ =====
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pixelai.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ===== МОДЕЛИ БД =====
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    email = Column(String, unique=True, nullable=True)
    password_hash = Column(String, nullable=True)
    tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    designs = relationship("Design", back_populates="owner")
    videos = relationship("Video", back_populates="owner")
    payments = relationship("Payment", back_populates="owner")

class Design(Base):
    __tablename__ = "designs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String)
    prompt = Column(Text)
    image_url = Column(Text)
    tokens_spent = Column(Integer, default=4)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="designs")

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String, default="slideshow")
    prompt = Column(Text)
    video_url = Column(Text)
    images_count = Column(Integer, default=1)
    tokens_spent = Column(Integer, default=7)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="videos")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    tokens = Column(Integer)
    status = Column(String, default="pending")
    payment_id = Column(String, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="payments")

# Создание таблиц
Base.metadata.create_all(bind=engine)

# ===== AI СЕРВИСЫ =====
STABILITY_API_KEY = os.getenv("sk-rVukIxlovqXT3meBN1pSvSekSFspjFySlY1c9lYvYXLayOoe")
STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"

ROBOKASSA_LOGIN = os.getenv("ROBOKASSA_LOGIN")
ROBOKASSA_PASSWORD1 = os.getenv("ROBOKASSA_PASSWORD1")
ROBOKASSA_PASSWORD2 = os.getenv("ROBOKASSA_PASSWORD2")
ROBOKASSA_IS_TEST = os.getenv("ROBOKASSA_IS_TEST", "true").lower() == "true"

# ===== ЦЕНЫ В ТОКЕНАХ =====
TOKEN_PRICES = {
    "design": 4,
    "video": 7,
    "regenerate": 2,
    "download": 0,
    "effect": 1
}

TOKEN_PACKAGES = {
    30: 105,
    100: 350,
    300: 999,
    1000: 2999
}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_stability_image(prompt: str):
    """Генерация изображения через Stability AI"""
    if not STABILITY_API_KEY:sk-rVukIxlovqXT3meBN1pSvSekSFspjFySlY1c9lYvYXLayOoe
        return None
    
    headers = {
        "Authorization": f"Bearer {STABILITY_API_KEY}",
        "Accept": "image/*"
    }
    
    data = {
        "prompt": prompt,
        "output_format": "png"
    }
    
    try:
        response = requests.post(STABILITY_URL, headers=headers, data=data)
        
        if response.status_code == 200:
            os.makedirs("uploads", exist_ok=True)
            filename = f"uploads/{secrets.token_hex(16)}.png"
            
            with open(filename, "wb") as f:
                f.write(response.content)
            
            return f"/{filename}"
        else:
            print(f"Stability AI error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Stability AI exception: {e}")
        return None

def create_slideshow_video(image_paths: List[str], output_path: str, duration: int = 3):
    """Создание слайд-шоу видео через ffmpeg"""
    try:
        # Создаём список файлов
        list_file = f"temp_{secrets.token_hex(8)}.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for img in image_paths:
                f.write(f"file '{img}'\n")
                f.write(f"duration {duration}\n")
        
        # FFmpeg команда
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-vf", "scale=1024:768:force_original_aspect_ratio=decrease,pad=1024:768:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            output_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        os.remove(list_file)
        
        return True
    except Exception as e:
        print(f"Video creation error: {e}")
        return False

def generate_robokassa_payment(amount: float, tokens: int, user_id: int):
    """Генерация ссылки на оплату Robokassa"""
    import hashlib
    from urllib.parse import urlencode
    
    inv_id = int(datetime.now().timestamp() * 1000)
    
    signature_string = f"{ROBOKASSA_LOGIN}:{amount}:{inv_id}:{ROBOKASSA_PASSWORD1}"
    signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
    
    base_url = "https://auth.robokassa.ru/Merchant/Index.aspx" if ROBOKASSA_IS_TEST else "https://merchant.robokassa.ru/Index.aspx"
    
    params = {
        "MrchLogin": ROBOKASSA_LOGIN,
        "OutSum": f"{amount:.2f}",
        "InvId": inv_id,
        "Desc": f"Pixel AI — {tokens} токенов",
        "SignatureValue": signature,
        "IsTest": "1" if ROBOKASSA_IS_TEST else "0",
        "Culture": "ru"
    }
    
    payment_url = f"{base_url}?{urlencode(params)}"
    
    return payment_url, str(inv_id)

# ===== API МОДЕЛИ =====
class TokenPackage(BaseModel):
    tokens: int
    price: float

class GenerateRequest(BaseModel):
    prompt: str
    type: str = "design"

# ===== API ЭНДПОИНТЫ =====

@app.get("/")
async def root():
    """Главная страница"""
    return HTMLResponse(content=open("frontend/index.html", "r", encoding="utf-8").read())

@app.get("/api/health")
async def health_check():
    """Проверка статуса сервиса"""
    return {
        "status": "ok",
        "services": {
            "stability_ai": "✅" if STABILITY_API_KEY else "❌",
            "database": "✅"
        },
        "token_prices": TOKEN_PRICES,
        "token_packages": TOKEN_PACKAGES
    }

@app.post("/api/user/create")
async def create_user(
    telegram_id: Optional[int] = Form(None),
    email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Создание нового пользователя"""
    
    # Проверка существующего
    if telegram_id:
        existing = db.query(User).filter(User.telegram_id == telegram_id).first()
        if existing:
            return {"success": True, "user_id": existing.id, "tokens": existing.tokens}
    
    if email:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            return {"success": True, "user_id": existing.id, "tokens": existing.tokens}
    
    # Создаём нового
    user = User(telegram_id=telegram_id, email=email, tokens=0)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {"success": True, "user_id": user.id, "tokens": user.tokens}

@app.get("/api/user/{user_id}/tokens")
async def get_user_tokens(user_id: int, db: Session = Depends(get_db)):
    """Получить баланс токенов"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    return {"success": True, "tokens": user.tokens}

@app.post("/api/design/generate")
async def generate_design(
    user_id: int = Form(...),
    prompt: str = Form(...),
    design_type: str = Form("web"),
    db: Session = Depends(get_db)
):
    """Генерация дизайна (стоимость: 4 токена)"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверка токенов
    if user.tokens < TOKEN_PRICES["design"]:
        raise HTTPException(
            status_code=402,
            detail=f"Недостаточно токенов! Нужно {TOKEN_PRICES['design']} 🪙, у вас {user.tokens} 🪙"
        )
    
    # Генерация изображения
    enhanced_prompt = f"Professional {design_type} design. {prompt}. High quality, modern, detailed, 4k."
    image_url = generate_stability_image(enhanced_prompt)
    
    if not image_url:
        # Тестовое изображение если API не работает
        import random
        image_url = f"https://picsum.photos/seed/{random.randint(1, 10000)}/1024/768"
    
    # Списываем токены
    user.tokens -= TOKEN_PRICES["design"]
    
    # Сохраняем дизайн
    design = Design(
        user_id=user_id,
        type=design_type,
        prompt=prompt,
        image_url=image_url,
        tokens_spent=TOKEN_PRICES["design"]
    )
    db.add(design)
    db.commit()
    db.refresh(design)
    
    return {
        "success": True,
        "image_url": image_url,
        "tokens_left": user.tokens,
        "design_id": design.id
    }

@app.post("/api/video/create")
async def create_video(
    user_id: int = Form(...),
    image_ids: str = Form(...),  # JSON список ID изображений
    db: Session = Depends(get_db)
):
    """Создание слайд-шоу видео (стоимость: 7 токенов)"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверка токенов
    if user.tokens < TOKEN_PRICES["video"]:
        raise HTTPException(
            status_code=402,
            detail=f"Недостаточно токенов! Нужно {TOKEN_PRICES['video']} 🪙, у вас {user.tokens} 🪙"
        )
    
    # Получаем изображения
    try:
        ids = json.loads(image_ids)
    except:
        raise HTTPException(status_code=400, detail="Неверный формат image_ids")
    
    designs = db.query(Design).filter(Design.id.in_(ids)).all()
    if not designs:
        raise HTTPException(status_code=404, detail="Изображения не найдены")
    
    image_paths = [d.image_url.lstrip("/") for d in designs]
    
    # Создаём видео
    os.makedirs("videos", exist_ok=True)
    output_filename = f"videos/{secrets.token_hex(16)}.mp4"
    output_path = os.path.join(os.getcwd(), output_filename)
    
    success = create_slideshow_video(image_paths, output_path)
    
    if not success:
        raise HTTPException(status_code=500, detail="Ошибка создания видео")
    
    # Списываем токены
    user.tokens -= TOKEN_PRICES["video"]
    
    # Сохраняем видео
    video = Video(
        user_id=user_id,
        type="slideshow",
        prompt=f"Слайд-шоу из {len(designs)} изображений",
        video_url=f"/{output_filename}",
        images_count=len(designs),
        tokens_spent=TOKEN_PRICES["video"]
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    
    return {
        "success": True,
        "video_url": f"/{output_filename}",
        "tokens_left": user.tokens,
        "video_id": video.id
    }

@app.post("/api/design/{design_id}/regenerate")
async def regenerate_design(
    design_id: int,
    user_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Регенерация дизайна (стоимость: 2 токена)"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if user.tokens < TOKEN_PRICES["regenerate"]:
        raise HTTPException(
            status_code=402,
            detail=f"Недостаточно токенов! Нужно {TOKEN_PRICES['regenerate']} 🪙"
        )
    
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Дизайн не найден")
    
    # Генерируем новое изображение
    image_url = generate_stability_image(design.prompt)
    
    if not image_url:
        import random
        image_url = f"https://picsum.photos/seed/{random.randint(1, 10000)}/1024/768"
    
    # Списываем токены
    user.tokens -= TOKEN_PRICES["regenerate"]
    
    # Обновляем дизайн
    design.image_url = image_url
    design.tokens_spent = TOKEN_PRICES["regenerate"]
    db.commit()
    
    return {
        "success": True,
        "image_url": image_url,
        "tokens_left": user.tokens
    }

@app.get("/api/design/{design_id}/download")
async def download_design(design_id: int, db: Session = Depends(get_db)):
    """Скачивание дизайна (БЕСПЛАТНО!)"""
    
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Дизайн не найден")
    
    file_path = design.image_url.lstrip("/")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(file_path, media_type="image/png", filename=f"pixel-design-{design_id}.png")

@app.get("/api/video/{video_id}/download")
async def download_video(video_id: int, db: Session = Depends(get_db)):
    """Скачивание видео (БЕСПЛАТНО!)"""
    
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    file_path = video.video_url.lstrip("/")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(file_path, media_type="video/mp4", filename=f"pixel-video-{video_id}.mp4")

@app.post("/api/payment/create")
async def create_payment(
    user_id: int = Form(...),
    tokens: int = Form(...),
    db: Session = Depends(get_db)
):
    """Создание платежа для покупки токенов"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверка доступных пакетов
    if tokens not in TOKEN_PACKAGES:
        raise HTTPException(status_code=400, detail="Недоступный пакет токенов")
    
    price = TOKEN_PACKAGES[tokens]
    payment_url, payment_id = generate_robokassa_payment(price, tokens, user_id)
    
    # Сохраняем платёж
    payment = Payment(
        user_id=user_id,
        amount=price,
        tokens=tokens,
        payment_id=payment_id,
        status="pending"
    )
    db.add(payment)
    db.commit()
    
    return {
        "success": True,
        "payment_url": payment_url,
        "payment_id": payment_id,
        "tokens": tokens,
        "price": price
    }

@app.post("/api/payment/webhook")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook от Robokassa об успешной оплате"""
    
    try:
        form_data = await request.form()
        params = dict(form_data)
        
        # Проверка подписи
        signature = params.get("SignatureValue", "")
        out_sum = params.get("OutSum", "")
        inv_id = params.get("InvId", "")
        
        expected_signature = hashlib.md5(
            f"{out_sum}:{inv_id}:{ROBOKASSA_PASSWORD2}".encode("utf-8")
        ).hexdigest()
        
        if signature.upper() != expected_signature.upper():
            return JSONResponse(status_code=400, content={"status": "error"})
        
        # Находим платёж
        payment = db.query(Payment).filter(Payment.payment_id == inv_id).first()
        if not payment:
            return JSONResponse(status_code=404, content={"status": "not_found"})
        
        # Обновляем статус
        payment.status = "completed"
        
        # Начисляем токены
        user = db.query(User).filter(User.id == payment.user_id).first()
        if user:
            user.tokens += payment.tokens
            db.commit()
        
        return JSONResponse(content={"status": "OK"})
    
    except Exception as e:
        print(f"Webhook error: {e}")
        return JSONResponse(status_code=500, content={"status": "error"})

@app.get("/api/user/{user_id}/history")
async def get_user_history(user_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """История генераций пользователя"""
    
    designs = db.query(Design).filter(Design.user_id == user_id).order_by(Design.created_at.desc()).limit(limit).all()
    videos = db.query(Video).filter(Video.user_id == user_id).order_by(Video.created_at.desc()).limit(limit).all()
    
    history = []
    
    for d in designs:
        history.append({
            "id": d.id,
            "type": "design",
            "subtype": d.type,
            "url": d.image_url,
            "prompt": d.prompt,
            "tokens_spent": d.tokens_spent,
            "created_at": d.created_at.isoformat()
        })
    
    for v in videos:
        history.append({
            "id": v.id,
            "type": "video",
            "subtype": v.type,
            "url": v.video_url,
            "prompt": v.prompt,
            "tokens_spent": v.tokens_spent,
            "created_at": v.created_at.isoformat()
        })
    
    # Сортировка по дате
    history.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {
        "success": True,
        "history": history[:limit]
    }

@app.get("/api/token-packages")
async def get_token_packages():
    """Получить доступные пакеты токенов"""
    return {
        "success": True,
        "packages": [
            {"tokens": tokens, "price": price, "price_per_token": round(price/tokens, 2)}
            for tokens, price in TOKEN_PACKAGES.items()
        ],
        "prices": TOKEN_PRICES
    }

# ===== СТАТИКА =====
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

# ===== ЗАПУСК =====
if __name__ == "__main__":
    import uvicorn
    
    # Создаём папки
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("videos", exist_ok=True)
    
    print("""
╔══════════════════════════════════════════╗
║     🎨 PIXEL AI — TOKEN SYSTEM          ║
╠══════════════════════════════════════════╣
║  🪙 Токены:                              ║
║     Фото: 4 🪙                           ║
║     Видео: 7 🪙                          
║     Скачать: 0 🪙 БЕСПЛАТНО!             ║
║                                          ║
║  💵 Пакеты:                              ║
║     30 🪙 = 105₽                         ║
║     100 🪙 = 350₽ 🔥                     ║
║     300 🪙 = 999₽                        ║
║     1000 🪙 = 2999₽                      ║
╚══════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))