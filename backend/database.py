import os
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, JSON, DECIMAL, Enum, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from dotenv import load_dotenv
from sqlalchemy.engine import URL

script_dir = Path(__file__).resolve().parent
main_dir = script_dir.parent
dotenv_path = main_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

url_object = URL.create(
    "mysql+pymysql",
    username=os.getenv('DATABASE_USER'),
    password=os.getenv('DATABASE_PASSWORD'),
    host=os.getenv('DATABASE_HOST', 'db'),
    port=int(os.getenv('DATABASE_PORT', '3306')),
    database=os.getenv('DATABASE_NAME')
)

engine = create_engine(url_object, pool_recycle=3600, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    password_hash = Column(String(255))
    rights = Column(JSON, default=[])
    email_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    preferences = relationship("UserPreference", back_populates="user", uselist=False)

class UserPreference(Base):
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    accent_color = Column(String(7), default="#6366f1")  # Hex color
    theme = Column(Enum('light', 'dark', 'auto'), default='auto')
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="preferences")

class ChapterVisit(Base):
    __tablename__ = "chapter_visits"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    chapter_id = Column(Integer, ForeignKey("chapters.id"))
    visited_at = Column(DateTime, default=func.now())
    
    user = relationship("User")
    chapter = relationship("Chapter")

class EmailVerification(Base):
    __tablename__ = "email_verifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    email = Column(String(100))
    verification_token = Column(String(255), unique=True)
    expires_at = Column(DateTime)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

class Partner(Base):
    __tablename__ = "partners_table"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    url = Column(String(255))
    clicks = Column(Integer, default=0)

class Manga(Base):
    __tablename__ = "manga"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    reader_mode = Column(Enum('single_page', 'long_stripe'), default='single_page')
    cover_path = Column(String(500))
    url_slug = Column(String(255), unique=True, index=True)
    tags = Column(JSON, default=[])
    description = Column(Text)
    age_rating = Column(Integer, default=0)
    status = Column(Enum('Active', 'Cancelled', 'Planned', 'On Hold', 'Finished', 'Licensed'), default='Active')
    hidden_status = Column(Enum('All', 'Logged-In', 'Patreon', 'Licensed'), default='All')
    created_at = Column(DateTime, default=func.now())
    
    chapters = relationship("Chapter", back_populates="manga")

class Chapter(Base):
    __tablename__ = "chapters"
    
    id = Column(Integer, primary_key=True, index=True)
    manga_id = Column(Integer, ForeignKey("manga.id"))
    name = Column(String(255))
    chapter_number = Column(DECIMAL(5,2))
    volume_number = Column(Integer, default=0)
    release_date_regular = Column(DateTime)
    release_date_patreon = Column(DateTime)
    clicks = Column(Integer, default=0)
    downloads = Column(Integer, default=0)
    file_path = Column(String(500))
    created_at = Column(DateTime, default=func.now())
    
    manga = relationship("Manga", back_populates="chapters")

class Setting(Base):
    __tablename__ = "settings"
    
    setting_key = Column(String(100), primary_key=True)
    setting_value = Column(Text)

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    session_token = Column(String(255), unique=True)
    expires_at = Column(DateTime)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()