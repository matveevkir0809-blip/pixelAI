from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    subscription = Column(String, default="free")
    subscription_expires = Column(DateTime, nullable=True)
    generations_count = Column(Integer, default=0)
    generations_limit = Column(Integer, default=10)
    
    designs = relationship("Design", back_populates="owner")
    payments = relationship("Payment", back_populates="user")

class Design(Base):
    __tablename__ = "designs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    type = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    style = Column(String, nullable=False)
    image_url = Column(String, nullable=False)
    uploaded_image = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="designs")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, default="pending")
    payment_id = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="payments")