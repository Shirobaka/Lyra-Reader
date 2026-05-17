from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Response
from typing import Optional
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_, func
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import json
import zipfile
import shutil
import jwt
import uuid
import re
import gettext
import hmac
import logging
import ssl
import secrets
import smtplib
from contextvars import ContextVar
from contextlib import asynccontextmanager
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from urllib.parse import urlparse
from typing import List, Dict, Any
from starlette.middleware.sessions import SessionMiddleware
import requests

_csp_nonce_ctx: ContextVar[str] = ContextVar('csp_nonce', default='')

script_dir = Path(__file__).resolve().parent
main_dir = script_dir.parent
dotenv_path = main_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)

from .database import get_db, engine, Base, User, Manga, Chapter, Setting, Partner, UserPreference, ChapterVisit, EmailVerification  # noqa: E402
from .auth import (  # noqa: E402
    get_current_user, get_current_user_optional, require_admin, create_access_token,
    get_password_hash, pwd_context
)
from .middleware.security import SecurityHeadersMiddleware  # noqa: E402

_DEFAULT_SETTINGS = [
    ("site_name", "Lyra Reader"),
    ("discord_enabled", "false"),
    ("patreon_url", ""),
    ("kofi_url", ""),
    ("discord_url", ""),
]

@asynccontextmanager
async def lifespan(app):
    # Create all tables if they don't exist yet
    Base.metadata.create_all(bind=engine)
    # Seed default settings on first run
    from .database import SessionLocal
    db = SessionLocal()
    try:
        for key, value in _DEFAULT_SETTINGS:
            if not db.query(Setting).filter(Setting.setting_key == key).first():
                db.add(Setting(setting_key=key, setting_value=value))
        db.commit()
    finally:
        db.close()
    yield

app = FastAPI(
    title="Manga Scanlation Site",
    description="A secure manga scanlation website",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/admin/docs" if os.getenv("DEBUG_MODE", "False") == "True" else None,
    redoc_url="/admin/redoc" if os.getenv("DEBUG_MODE", "False") == "True" else None
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

templates = Jinja2Templates(directory="frontend/templates")

def setup_translations():
    localedir = os.path.join('frontend/locales')
    try:
        translation = gettext.translation(
            'messages', 
            localedir=localedir, 
            languages=[os.getenv("APP_LANGUAGE", "de")],
            fallback=True
        )
        translation.install()
        return translation.gettext
    except FileNotFoundError:
        return lambda x: x

_ = setup_translations()

def translate_with_vars(message, **kwargs):
    translated = _(message)
    return translated.format(**kwargs) if kwargs else translated

templates.env.globals['_'] = _
templates.env.globals['_f'] = translate_with_vars
templates.env.globals['csp_nonce'] = _csp_nonce_ctx.get


@app.middleware("http")
async def set_csp_nonce(request: Request, call_next):
    """Generate a CSP nonce per-request via ContextVar (async-safe, always visible in templates)."""
    nonce = secrets.token_urlsafe(16)
    _csp_nonce_ctx.set(nonce)
    request.state.csp_nonce = nonce  # kept for backward compatibility
    return await call_next(request)

if os.getenv("SECURITY_HEADERS_ENABLED", "False") == "True":
    app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

os.makedirs("uploads/covers", exist_ok=True)
os.makedirs("uploads/chapters", exist_ok=True)

def get_setting(db: Session, key: str, default: str = ""):
    setting = db.query(Setting).filter(Setting.setting_key == key).first()
    return setting.setting_value if setting else default

def get_settings(db: Session):
    settings = db.query(Setting).all()
    settings_dict = {s.setting_key: s.setting_value for s in settings}
    return settings_dict

_ALLOWED_IMAGE_EXTENSIONS = {
    ext.strip().lower()
    for ext in os.getenv("ALLOWED_IMAGE_EXTENSIONS", ".jpg,.jpeg,.png,.webp,.gif").split(",")
    if ext.strip()
}
_MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(100 * 1024 * 1024)))

async def save_uploaded_file(upload_file: UploadFile, directory: str) -> str:
    file_extension = os.path.splitext(upload_file.filename)[1].lower()
    if file_extension not in _ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")

    contents = await upload_file.read(_MAX_UPLOAD_SIZE + 1)
    if len(contents) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(directory, filename)
    with open(file_path, "wb") as buffer:
        buffer.write(contents)
    return file_path

def extract_zip_to_chapter(zip_path: str, chapter_id: int) -> List[str]:
    extract_dir = os.path.realpath(f"uploads/chapters/{chapter_id}")
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.infolist():
            member_path = os.path.realpath(os.path.join(extract_dir, member.filename))
            if not member_path.startswith(extract_dir + os.sep):
                raise HTTPException(status_code=400, detail="Invalid archive: path traversal detected")
            zip_ref.extract(member, extract_dir)
    
    image_files = []
    allowed_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
    
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.lower().endswith(allowed_extensions):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, extract_dir)
                image_files.append(rel_path)
    
    def natural_sort_key(text):
        import re
        def atoi(text):
            return int(text) if text.isdigit() else text
        return [atoi(c) for c in re.split(r'(\d+)', text)]
    
    image_files.sort(key=natural_sort_key)
    
    for i, file_path in enumerate(image_files):
        current_path = os.path.join(extract_dir, file_path)
        if os.path.dirname(file_path):
            extension = os.path.splitext(file_path)[1]
            new_filename = f"{i+1:03d}{extension}"
            new_path = os.path.join(extract_dir, new_filename)
            
            shutil.move(current_path, new_path)
            image_files[i] = new_filename
    
    return image_files

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    
    if current_user is None:
        recent_chapters = db.query(Chapter).join(Manga).filter(
            Chapter.release_date_regular <= datetime.now(),
            Manga.hidden_status.like("All"),
        ).order_by(desc(Chapter.release_date_regular)).limit(10).all()
    elif user_has_rights(request, db, "Manga Manage") or user_has_rights(request, db, "Chapter Upload"):
        recent_chapters = db.query(Chapter).join(Manga).filter(
            Chapter.release_date_regular <= datetime.now(),
            or_(Manga.hidden_status.like("All"),
            Manga.hidden_status.like("Logged-In"),
            Manga.hidden_status.like("Patreon"),
            Manga.hidden_status.like("Licensed"))
        ).order_by(desc(Chapter.release_date_regular)).limit(10).all()
    elif user_has_rights(request, db, "Patreon"):
        recent_chapters = db.query(Chapter).join(Manga).filter(
            Chapter.release_date_regular <= datetime.now(),
            or_(Manga.hidden_status.like("All"),
            Manga.hidden_status.like("Logged-In"),
            Manga.hidden_status.like("Patreon"))
        ).order_by(desc(Chapter.release_date_regular)).limit(10).all()
    else:
        recent_chapters = db.query(Chapter).join(Manga).filter(
            Chapter.release_date_regular <= datetime.now(),
            or_(Manga.hidden_status.like("All"),
            Manga.hidden_status.like("Logged-In"))
        ).order_by(desc(Chapter.release_date_regular)).limit(10).all()

    
    settings = get_settings(db)
    
    return templates.TemplateResponse(request, "index.html", {
        "recent_chapters": recent_chapters,
        "settings": settings,
        "current_user": current_user,
    })

@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    settings = get_settings(db)
    manga_list = db.query(Manga).all()
    
    return templates.TemplateResponse(request, "projects.html", {
        "manga_list": manga_list,
        "settings": settings,
        "current_user": current_user,
    })

@app.get('/mangas/{slug}', response_class=HTMLResponse)
@app.get("/project/{slug}", response_class=HTMLResponse)
async def project_page(request: Request, slug: str, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)

    if slug.isdigit():
        manga = db.query(Manga).filter(Manga.id == int(slug)).first()
    else:        
        manga = db.query(Manga).filter(Manga.url_slug == slug).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    if current_user is None:
        chapters = db.query(Chapter).join(Manga).filter(
            Chapter.manga_id == manga.id,
            Chapter.release_date_regular <= datetime.now(),
            Manga.hidden_status == "All"
            ).order_by(Chapter.volume_number, desc(Chapter.chapter_number)).all()
    elif (user_has_rights(request, db, "Chapter Upload") or user_has_rights(request, db, "Manga Manage") or user_has_rights(request, db, "Admin")):
        chapters = db.query(Chapter).filter(
            Chapter.manga_id == manga.id
            ).order_by(Chapter.volume_number, desc(Chapter.chapter_number)).all()
    elif "Patreon" in current_user.rights:
        chapters = db.query(Chapter).join(Manga).filter(
            Chapter.manga_id == manga.id,
            or_(Chapter.release_date_regular <= datetime.now(),
                Chapter.release_date_patreon <= datetime.now()),
            or_(Manga.hidden_status == "All",
                Manga.hidden_status == "Logged-In",
                Manga.hidden_status == "Patreon")
                ).order_by(Chapter.volume_number, desc(Chapter.chapter_number)).all()
    else:
        chapters = db.query(Chapter).join(Manga).filter(
            Chapter.manga_id == manga.id,
            Chapter.release_date_regular <= datetime.now(),
            or_(Manga.hidden_status == "All",
                Manga.hidden_status == "Logged-In")
            ).order_by(Chapter.volume_number, desc(Chapter.chapter_number)).all()

    first_release = db.query(Chapter).filter(Chapter.manga_id == manga.id, Chapter.release_date_regular <= datetime.now()).order_by(Chapter.release_date_regular).first()
    last_release = db.query(Chapter).filter(Chapter.manga_id == manga.id, Chapter.release_date_regular <= datetime.now()).order_by(desc(Chapter.release_date_regular)).first()
    
    settings = get_settings(db)    
    
    notification = request.session.pop("notification", None)

    return templates.TemplateResponse(request, "project.html", {
        "manga": manga,
        "chapters": chapters,
        "first_release": first_release if first_release is not None else None,
        "last_release": last_release if last_release is not None else None,
        "current_user": current_user,
        "settings": settings,
        "notification": notification,
    })

@app.get("/reader/{chapter_id}", response_class=HTMLResponse)
async def reader_page(request: Request, chapter_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    # manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()
    next_chapter = db.query(Chapter).filter(Chapter.id == chapter_id+1, Chapter.manga_id == chapter.manga.id).first()
    prev_chapter = db.query(Chapter).filter(Chapter.id == chapter_id-1, Chapter.manga_id == chapter.manga.id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    now = datetime.now()
        
    if next_chapter and now < next_chapter.release_date_regular:
        next_chapter = None
        
    if prev_chapter and now < prev_chapter.release_date_regular:
        prev_chapter = None
        
    if not chapter.manga:
        raise HTTPException(status_code=404, detail="Manga not found")
    
    if (
        (chapter.manga.hidden_status in ("Logged-In", "Patreon", "Licensed") and not current_user)
        or (chapter.manga.hidden_status == "Patreon" and not user_has_rights(request, db, "Patreon"))
        or (chapter.manga.hidden_status == "Licensed"and not user_has_rights(request, db, "Manga Manage"))
        or (now < chapter.release_date_patreon and now < chapter.release_date_regular)
        or (now >= chapter.release_date_patreon and now < chapter.release_date_regular and not user_has_rights(request, db, "Patreon"))
    ):
        request.session["notification"] = "This chapter is not available"
        return RedirectResponse(f"/project/{chapter.manga.url_slug}", 302)
    
    if current_user:
        today = datetime.now().date()
        existing_visit = db.query(ChapterVisit).filter(
            and_(
                ChapterVisit.user_id == current_user.id,
                ChapterVisit.chapter_id == chapter_id,
                func.date(ChapterVisit.visited_at) == today
            )
        ).first()
        
        if not existing_visit:
            visit = ChapterVisit(user_id=current_user.id, chapter_id=chapter_id)
            db.add(visit)

    chapter.clicks += 1
    db.commit()

    settings = get_settings(db)
    
    chapter_dir = f"{chapter.file_path}"
    pages = []
    
    if os.path.exists(chapter_dir):
        image_files = []
        allowed_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        
        for file in os.listdir(chapter_dir):
            if file.lower().endswith(allowed_extensions):
                image_files.append(file)
        
        def natural_sort_key(text):
            def atoi(text):
                return int(text) if text.isdigit() else text
            return [atoi(c) for c in re.split(r'(\d+)', text)]
        
        image_files.sort(key=natural_sort_key)
        
        for file in image_files:
            pages.append(f"/{chapter.file_path}/{file}")
        
    return templates.TemplateResponse(request, "reader.html", {
        "chapter": chapter,
        "prev_chapter": prev_chapter,
        "next_chapter": next_chapter,
        "pages": pages,
        "current_user": current_user,
        "settings": settings,
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)

    if current_user:
        return RedirectResponse(url="/", status_code=302)
    
    settings = get_settings(db)    
    
    return templates.TemplateResponse(request, "auth/login.html", {
        "current_user": current_user,
        "settings": settings,
    })

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    if current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    settings = get_settings(db)
    if settings.get('allow_registration', True) is False:
        return RedirectResponse(url="/", status_code=302)
    
    
    
    return templates.TemplateResponse(request, "auth/register.html", {
        "current_user": current_user,
        "RECAPTCHA_SITE_KEY": os.getenv("RECAPTCHA_SITE_KEY"),
        "RECAPTCHA_ENABLED": os.getenv("RECAPTCHA_ENABLED"),
        "settings": settings,
    })

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)

    if current_user is None or (not user_has_rights(request, db, "Admin") and not user_has_rights(request, db, "Manga Manage") and not user_has_rights(request, db, "Chapter Upload")):
        return RedirectResponse(url="/login?redirect=/admin", status_code=302)
    
    settings = get_settings(db)    
    
    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "current_user": current_user,
        "settings": settings,
    })

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, db: Session = Depends(get_db)):
    try:
        current_user = require_admin(request, db)
    except HTTPException:
        return RedirectResponse(url="/login?redirect=/admin/users", status_code=302)
    
    settings = get_settings(db)    
    
    users = db.query(User).all()
    return templates.TemplateResponse(request, "admin/users.html", {
        "users": users, 
        "current_user": current_user,
        "settings": settings,
    })

@app.get("/admin/manga", response_class=HTMLResponse)
async def admin_manga(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    
    if not (user_has_rights(request, db, "Admin") or
            user_has_rights(request, db, "Manga Manage") or
            user_has_rights(request, db, "Chapter Upload")):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    settings = get_settings(db)    
    manga_list = db.query(Manga).all()  

    return templates.TemplateResponse(request, "admin/manga.html", {
        "manga_list": manga_list, 
        "current_user": current_user,
        "settings": settings,
    })

@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request, db: Session = Depends(get_db)):
    try:
        current_user = require_admin(request, db)
    except HTTPException:
        return RedirectResponse(url="/login?redirect=/admin/settings", status_code=302)
    
    settings = get_settings(db)
    settings_raw = db.query(Setting).all()
    
    return templates.TemplateResponse(request, "admin/settings.html", {
        "settings": settings,
        "settings_raw": settings_raw,
        "current_user": current_user,
    })

@app.get("/partner/{partner_id}")
async def redirect_partner(request: Request, partner_id: int, db: Session = Depends(get_db)):
    partner = db.query(Partner).filter(Partner.id == partner_id).limit(1).first()
    if partner and is_safe_url(partner.url):
        partner.clicks += 1
        db.commit()
        return RedirectResponse(partner.url)
    return {"message": "Partner not found"}

@app.get("/profile", response_class=HTMLResponse)
@app.get("/profile/{user}", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db), user: str|int = None):
    current_user = get_current_user(request, db)
    settings = get_settings(db)
    if user is not None:
        if user.isdigit():
            profile_user = db.query(User).filter(User.id == user).first()
            print(profile_user)
        else:
            print("string")
            profile_user = db.query(User).filter(User.username == user).first()

    if "profile_user" not in locals():
        profile_user = current_user

    if current_user.id != profile_user.id and not user_has_rights(request, db, "User Manage") and not user_has_rights(request, db, "Admin"):
        profile_user.email = None
        profile_user.password_hash = None
            
    
    preferences = db.query(UserPreference).filter(UserPreference.user_id == profile_user.id).first()
    if not preferences:
        preferences = UserPreference(user_id=profile_user.id)
        db.add(preferences)
        db.commit()
        db.refresh(preferences)
    
    visit_count = db.query(func.count(ChapterVisit.id)).filter(ChapterVisit.user_id == profile_user.id).scalar() or 0
    
    recent_visits = db.query(ChapterVisit).join(Chapter).join(Manga).filter(
        ChapterVisit.user_id == profile_user.id
    ).order_by(ChapterVisit.visited_at.desc()).limit(10).all()
    
    return templates.TemplateResponse(request, "profile.html", {
        "current_user": current_user,
        "user": profile_user,
        "settings": settings,
        "visit_count": visit_count,
        "recent_visits": recent_visits
    })


@app.get("/api/profile/stats/{userid}")
async def get_profile_stats(request: Request, userid: int, db: Session = Depends(get_db)):
    get_current_user(request, db)

    total_visits = db.query(func.count(ChapterVisit.id)).filter(ChapterVisit.user_id == userid).scalar() or 0
    
    unique_chapters = db.query(func.count(func.distinct(ChapterVisit.chapter_id))).filter(
        ChapterVisit.user_id == userid
    ).scalar() or 0
    
    unique_manga = db.query(func.count(func.distinct(Manga.id))).select_from(
        ChapterVisit
    ).join(Chapter).join(Manga).filter(
        ChapterVisit.user_id == userid
    ).scalar() or 0
    
    most_read = db.query(
        Manga.name,
        func.count(ChapterVisit.id).label('visit_count'),
        Manga.url_slug
    ).select_from(ChapterVisit).join(Chapter).join(Manga).filter(
        ChapterVisit.user_id == userid
    ).group_by(Manga.id, Manga.name).order_by(
        func.count(ChapterVisit.id).desc()
    ).limit(5).all()
    
    return {
        "total_visits": total_visits,
        "unique_chapters": unique_chapters,
        "unique_manga": unique_manga,
        "most_read": [{"name": name, "visits": count, 'url_slug': url_slug} for name, count, url_slug in most_read]
    }

@app.post("/api/profile/preferences")
async def update_preferences(
    request: Request,
    accent_color: str = Form(...),
    theme: str = Form("auto"),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    
    import re
    if not re.match(r'^#[0-9A-Fa-f]{6}$', accent_color):
        raise HTTPException(status_code=400, detail="Invalid color format")
    
    if theme not in ['auto', 'light', 'dark']:
        raise HTTPException(status_code=400, detail="Invalid theme")
    
    preferences = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not preferences:
        preferences = UserPreference(user_id=current_user.id)
        db.add(preferences)
    
    preferences.accent_color = accent_color
    preferences.theme = theme
    preferences.updated_at = datetime.now()
    
    db.commit()
    
    return {"message": "Preferences updated successfully"}

@app.post("/api/profile/password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    
    if not pwd_context.verify(current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")
    
    current_user.password_hash = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Password updated successfully"}

@app.post("/api/profile/email")
async def change_email(
    request: Request,
    new_email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    
    if not pwd_context.verify(password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    
    if db.query(User).filter(User.email == new_email, User.id != current_user.id).first():
        raise HTTPException(status_code=400, detail="Email is already in use")
    
    verification_token = secrets.token_urlsafe(32)
    verification = EmailVerification(
        user_id=current_user.id,
        email=new_email,
        verification_token=verification_token,
        expires_at=datetime.now() + timedelta(hours=24)
    )
    db.add(verification)
    db.commit()
    
    send_email_change_verification(new_email, verification_token, db)
    
    return {"message": "Verification email sent to new address. Please verify to complete the change."}

@app.get("/verify-email-change")
async def verify_email_change(request: Request, token: str, db: Session = Depends(get_db)):
    verification = db.query(EmailVerification).filter(
        EmailVerification.verification_token == token,
        EmailVerification.expires_at > datetime.now(),
        EmailVerification.verified.is_(False)
    ).first()

    if not verification:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user = db.query(User).filter(User.id == verification.user_id).first()
    user.email = verification.email
    verification.verified = True
    
    db.commit()
    
    return RedirectResponse(url="/profile?email_changed=true", status_code=302)

@app.post("/api/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.email_verified:
        raise HTTPException(status_code=401, detail="Please verify your email address before logging in")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Your account has been deactivated")
    
    if remember_me:
        access_token_expires = timedelta(days=90)
        cookie_max_age = 90 * 24 * 60 * 60 
    else:
        access_token_expires = timedelta(days=7)
        cookie_max_age = 7 * 24 * 60 * 60 
    
    access_token = create_access_token(
        data={"sub": user.username}, 
        expires_delta=access_token_expires
    )
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=cookie_max_age,
        expires=cookie_max_age,
        path="/",
        domain=None,
        secure=True,
        httponly=True,
        samesite="lax"
    )
    
    return {
        "message": "Login successful",
        "user": {
            "username": user.username,
            "rights": user.rights
        },
        "expires_in_days": 90 if remember_me else 7
    }

@app.post("/api/refresh-token")
async def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    if not current_user:
        return
    
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No token found")
    
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM", "HS256")])
        exp = payload.get("exp")
        
        if exp:
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            days_until_expiry = (expires_at - datetime.now(timezone.utc)).days
            
            if days_until_expiry <= 7:
                new_token = create_access_token(
                    data={"sub": current_user.username},
                    expires_delta=timedelta(days=30)
                )
                
                response.set_cookie(
                    key="access_token",
                    value=new_token,
                    max_age=30 * 24 * 60 * 60,
                    expires=30 * 24 * 60 * 60,
                    path="/",
                    httponly=True,
                    secure=True,
                    samesite="lax"
                )
                
                return {"message": "Token refreshed", "expires_in_days": 30}
            else:
                return {"message": "Token still valid", "expires_in_days": days_until_expiry}
                
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/",
        domain=None
    )
    return {"message": "Logged out successfully"}

@app.post("/api/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    recaptcha_token: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    if os.getenv("RECAPTCHA_ENABLED", "False") == "True" and os.getenv("RECAPTCHA_SITE_KEY", "your_recaptcha_site_key_here") != "your_recaptcha_site_key_here" and not verify_recaptcha(recaptcha_token):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed")
    
    if db.query(User).filter(or_(User.username == username, User.email == email)).first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    
    hashed_password = get_password_hash(password)
    email_verified = False
    is_active=False
    rights = []

    if db.query(User).count() == 0:
        email_verified = True
        is_active=True
        rights = ["Admin", "Team Member", "Chapter Upload", "Manga Manage", "User Manage"]
    
    new_user = User(
        username=username,
        email=email,
        password_hash=hashed_password,
        rights=rights,
        email_verified=email_verified,
        is_active=is_active
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    preferences = UserPreference(user_id=new_user.id)
    db.add(preferences)
    
    verification_token = secrets.token_urlsafe(32)
    verification = EmailVerification(
        user_id=new_user.id,
        email=email,
        verification_token=verification_token,
        expires_at=datetime.now() + timedelta(hours=24)
    )
    db.add(verification)
    db.commit()
    
    send_verification_email(email, verification_token, db)
    
    return {"message": "Registration successful. Please check your email to verify your account."}

@app.get("/verify-email")
async def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    verification = db.query(EmailVerification).filter(
        EmailVerification.verification_token == token,
        EmailVerification.expires_at > datetime.now(),
        EmailVerification.verified.is_(False)
    ).first()

    if not verification:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user = db.query(User).filter(User.id == verification.user_id).first()
    user.email_verified = True
    user.is_active = True
    verification.verified = True
    
    db.commit()
    
    return RedirectResponse(url="/login?verified=true", status_code=302)


@app.post("/api/users")
async def create_user_api(
    request: Request,
    user_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    require_admin(request, db)

    if db.query(User).filter(or_(User.username == user_data['username'], User.email == user_data['email'])).first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_password = get_password_hash(user_data['password'])
    new_user = User(
        username=user_data['username'],
        email=user_data['email'],
        password_hash=hashed_password,
        rights=user_data.get('rights', [])
    )
    db.add(new_user)
    db.commit()
    
    return {"message": "User created successfully", "id": new_user.id}

@app.get("/api/users/{user_id}")
async def get_user_api(request: Request, user_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "rights": user.rights,
        "created_at": user.created_at
    }

@app.put("/api/users/{user_id}")
async def update_user_api(
    request: Request,
    user_id: int,
    user_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    require_admin(request, db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.username = user_data.get('username', user.username)
    user.email = user_data.get('email', user.email)
    user.rights = user_data.get('rights', user.rights)
    
    if 'password' in user_data and user_data['password']:
        user.password_hash = get_password_hash(user_data['password'])
    
    db.commit()
    return {"message": "User updated successfully"}

@app.delete("/api/users/{user_id}")
async def delete_user_api(request: Request, user_id: int, db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}

@app.post("/api/partners")
async def create_partner_api(
    request: Request,
    partner_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    require_admin(request, db)

    new_partner = Partner(
        name=partner_data['name'],
        url=partner_data.get('url', '')
    )
    db.add(new_partner)
    db.commit()
    
    return {"message": "Partner created successfully", "id": new_partner.id}

@app.get("/api/partners")
async def get_partners_api(request: Request, db: Session = Depends(get_db)):
    partners = db.query(Partner).all()
    
    return [
        {
            "id": partner.id,
            "name": partner.name,
            "url": partner.url,
            "clicks": partner.clicks
        }
        for partner in partners
    ]

@app.delete("/api/partners/{partner_id}")
async def delete_partner_api(request: Request, partner_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    
    db.delete(partner)
    db.commit()
    return {"message": "Partner deleted successfully"}

@app.post("/api/settings")
async def update_settings_api(
    request: Request,
    settings_data: Dict[str, str],
    db: Session = Depends(get_db)
):
    require_admin(request, db)

    for key, value in settings_data.items():
        setting = db.query(Setting).filter(Setting.setting_key == key).first()
        if setting:
            setting.setting_value = value
        else:
            new_setting = Setting(setting_key=key, setting_value=value)
            db.add(new_setting)
    
    db.commit()
    return {"message": "Settings updated successfully"}

@app.delete("/api/settings/{setting_key}")
async def delete_setting_api(request: Request, setting_key: str, db: Session = Depends(get_db)):
    require_admin(request, db)
    setting = db.query(Setting).filter(Setting.setting_key == setting_key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    db.delete(setting)
    db.commit()
    return {"message": "Setting deleted successfully"}

@app.post("/api/manga")
async def create_manga(
    request: Request,
    name: str = Form(...),
    url_slug: str = Form(...),
    description: str = Form(""),
    tags: str = Form("[]"),
    age_rating: int = Form(0),
    status: str = Form("Active"),
    hidden_status: str = Form("All"),
    reader_mode: str = Form("single_page"),
    cover: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    get_current_user(request, db)
    if user_has_rights(request, db, "Manga Manage") is False:
        return {"message": "Error: Manga Manage right required"}
    
    cover_path = None
    if cover:
        cover_path = await save_uploaded_file(cover, "uploads/covers")
    
    new_manga = Manga(
        name=name,
        url_slug=url_slug,
        description=description,
        tags=json.loads(tags),
        age_rating=age_rating,
        status=status,
        hidden_status=hidden_status,
        reader_mode=reader_mode, 
        cover_path="/"+cover_path
    )
    db.add(new_manga)
    db.commit()
    
    return {"message": "Manga created successfully", "id": new_manga.id}

@app.get("/api/manga/{manga_id}")
async def get_manga_api(request: Request, manga_id: int, db: Session = Depends(get_db)):
    manga = db.query(Manga).filter(Manga.id == manga_id).first()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")
    
    return {
        "id": manga.id,
        "name": manga.name,
        "url_slug": manga.url_slug,
        "description": manga.description,
        "tags": manga.tags,
        "age_rating": manga.age_rating,
        "status": manga.status,
        "hidden_status": manga.hidden_status,
        "reader_mode": manga.reader_mode,
        "cover_path": manga.cover_path
    }

@app.put("/api/manga/{manga_id}")
async def update_manga_api(
    request: Request,
    manga_id: int,
    name: str = Form(...),
    url_slug: str = Form(...),
    description: str = Form(""),
    tags: str = Form("[]"),
    age_rating: int = Form(0),
    status: str = Form("Active"),
    hidden_status: str = Form("All"),
    reader_mode: str = Form("single_page"),
    cover: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    require_admin(request, db)
    manga = db.query(Manga).filter(Manga.id == manga_id).first()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    manga.name = name
    manga.url_slug = url_slug
    manga.description = description
    manga.tags = json.loads(tags)
    manga.age_rating = age_rating
    manga.status = status
    manga.hidden_status = hidden_status
    manga.reader_mode = reader_mode
    
    if cover and cover.filename:
        if manga.cover_path and os.path.exists(manga.cover_path):
            os.remove(manga.cover_path)
        
        manga.cover_path = await save_uploaded_file(cover, "uploads/covers")
    
    db.commit()
    return {"message": "Manga updated successfully"}

@app.delete("/api/manga/{manga_id}")
async def delete_manga_api(request: Request, manga_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    manga = db.query(Manga).filter(Manga.id == manga_id).first()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")
    
    if manga.cover_path:
        cover_file = manga.cover_path.lstrip("/")
        if os.path.exists(cover_file):
            os.remove(cover_file)
    
    db.delete(manga)
    db.commit()
    return {"message": "Manga deleted successfully"}

@app.post("/api/chapter")
async def create_chapter(
    request: Request,
    manga_id: int = Form(...),
    chapter_number: float = Form(...),
    volume_number: int = Form(0),
    name: str = Form(""),
    release_date_regular: str = Form(...),
    release_date_patreon: str = Form(None),
    chapter_files: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    current_user = require_admin(request, db)
    
    try:
        existing_chapter = db.query(Chapter).filter(
            Chapter.manga_id == manga_id,
            Chapter.chapter_number == chapter_number
        ).first()
        
        if existing_chapter:
            raise HTTPException(
                status_code=400, 
                detail=f"Chapter {chapter_number} already exists for this manga"
            )
        
        regular_date = datetime.fromisoformat(release_date_regular.replace('Z', '+00:00'))
        
        if release_date_patreon:
            patreon_date = datetime.fromisoformat(release_date_patreon.replace('Z', '+00:00'))
        else:
            patreon_date = regular_date - timedelta(days=7)
        
        print(f"Creating chapter {chapter_number} for manga {manga_id}")
        
        new_chapter = Chapter(
            manga_id=manga_id,
            name=name,
            chapter_number=chapter_number,
            volume_number=volume_number,
            release_date_regular=regular_date,
            release_date_patreon=patreon_date
        )
        db.add(new_chapter)
        db.commit()
        db.refresh(new_chapter)
        
        print(f"Chapter record created with ID: {new_chapter.id}")
        
        chapter_dir = f"uploads/chapters/{new_chapter.id}"
        os.makedirs(chapter_dir, exist_ok=True)
        
        if chapter_files.filename.lower().endswith('.zip'):
            temp_zip_path = f"uploads/temp/{uuid.uuid4()}.zip"
            os.makedirs("uploads/temp", exist_ok=True)
            
            with open(temp_zip_path, "wb") as buffer:
                shutil.copyfileobj(chapter_files.file, buffer)
            
            try:
                image_files = extract_zip_to_chapter(temp_zip_path, new_chapter.id)
                print(f"Extracted {len(image_files)} images for chapter {new_chapter.id}")
            finally:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
        else:
            file_extension = os.path.splitext(chapter_files.filename)[1]
            filename = f"001{file_extension}"
            file_path = os.path.join(chapter_dir, filename)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(chapter_files.file, buffer)
        
        new_chapter.file_path = f"uploads/chapters/{new_chapter.id}"
        db.commit()
        
        print(f"Chapter {new_chapter.id} created successfully")
        
        return {"message": "Chapter created successfully", "id": new_chapter.id}
        
    except HTTPException:
        raise
    except Exception as e:
        if 'new_chapter' in locals() and hasattr(new_chapter, 'id') and new_chapter.id:
            chapter_dir = f"uploads/chapters/{new_chapter.id}"
            if os.path.exists(chapter_dir):
                shutil.rmtree(chapter_dir)
            try:
                db.delete(new_chapter)
                db.commit()
            except Exception:
                db.rollback()
        
        print(f"Chapter creation error: {e}")
        logger.error("Chapter creation error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create chapter. Please try again.")

@app.delete("/api/chapter/{chapter_id}")
async def delete_chapter_api(request: Request, chapter_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    chapter_dir = f"uploads/chapters/{chapter_id}"
    if os.path.exists(chapter_dir):
        shutil.rmtree(chapter_dir)
    
    db.query(ChapterVisit).filter(ChapterVisit.chapter_id == chapter_id).delete()
    db.delete(chapter)
    db.commit()
    return {"message": "Chapter deleted successfully"}

@app.get("/api/manga/{manga_id}/chapters")
async def get_manga_chapters_api(request: Request, manga_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)

    if not current_user:
        chapters = db.query(Chapter).join(Manga).filter(
            Chapter.release_date_regular <= datetime.now(),
            Chapter.manga_id == manga_id,
            Manga.hidden_status == "All"
            ).order_by(desc(Chapter.chapter_number)).all()
    else:
        if user_has_rights(request, db, "Manga Manage") or user_has_rights(request, db, "Admin") or user_has_rights(request, db, "Manga Manage"):
            chapters = db.query(Chapter).join(Manga).filter(
                Chapter.manga_id == manga_id
                ).order_by(desc(Chapter.chapter_number)).all()
        elif user_has_rights(request, db, "Patreon"):
            chapters = db.query(Chapter).join(Manga).filter(
                Chapter.release_date_regular <= datetime.now(),
                Chapter.manga_id == manga_id,
                or_(Manga.hidden_status == "All",            
                Manga.hidden_status == "Logged-In",            
                Manga.hidden_status == "Patreon")
                ).order_by(desc(Chapter.chapter_number)).all()
        else:
            chapters = db.query(Chapter).join(Manga).filter(
                Chapter.release_date_regular <= datetime.now(),
                Chapter.manga_id == manga_id,
                or_(Manga.hidden_status == "All",            
                Manga.hidden_status == "Logged-In")
                ).order_by(desc(Chapter.chapter_number)).all()            


    
    return [
        {
            "id": chapter.id,
            "chapter_number": float(chapter.chapter_number),
            "name": chapter.name,
            "release_date_regular": chapter.release_date_regular.isoformat(),
            "clicks": chapter.clicks
        }
        for chapter in chapters
    ]

@app.get("/api/download/{chapter_id}")
async def download_chapter(request: Request, chapter_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    if datetime.now() < chapter.release_date_regular:
        if "Patreon" not in current_user.rights or datetime.now() < chapter.release_date_patreon:
            raise HTTPException(status_code=403, detail="Access denied")
    
    zip_path = f"uploads/temp/{chapter_id}.zip"
    os.makedirs("uploads/temp", exist_ok=True)
    
    chapter_dir = f"uploads/chapters/{chapter_id}"
    if os.path.exists(chapter_dir):
        shutil.make_archive(zip_path[:-4], 'zip', chapter_dir)        
        chapter.downloads += 1
        db.commit()
        safe_name = re.sub(r'[^\w\s-]', '', chapter.manga.name).strip().replace(' ', '-')
        return FileResponse(
            zip_path,
            filename=f"{safe_name}-chapter-{chapter.chapter_number}.zip",
            background=BackgroundTask(os.remove, zip_path)
        )
    
    
    raise HTTPException(status_code=404, detail="Chapter files not found")

@app.get("/api/admin/stats")
async def get_stats(
    request: Request,
    db: Session = Depends(get_db)
):
    if not user_has_rights(request, db, "Admin") and not user_has_rights(request, db, "Manga Manage") and not user_has_rights(request, db, "Chapter Upload"):
        raise HTTPException( status_code=401, detail="Not authenticated")

    manga_count = db.query(func.count(Manga.id)).scalar() or 0
    chapter_count = db.query(func.count(Chapter.id)).scalar() or 0
    user_count = db.query(func.count(User.id)).scalar() or 0
    total_views = db.query(func.sum(Chapter.clicks)).scalar() or 0
    total_downloads = db.query(func.sum(Chapter.downloads)).scalar() or 0

    return {
        "manga_count": manga_count,
        "chapter_count": chapter_count,
        "user_count": user_count,
        "total_views": total_views,
        "total_downloads": total_downloads
    }

@app.get("/api/latest_releases")
async def latest_releases(
    request: Request,
    db: Session = Depends(get_db),
    token: str = "",
    release_type: str = "regular"
):
    if token == "" or not check_api_token(db, token):
        raise HTTPException(status_code=403, detail="API-Token is not correct.")
    
    if release_type == "regular":
        releases = db.query(Chapter).filter(Chapter.release_date_regular <= datetime.now()).order_by(desc(Chapter.release_date_regular)).limit(10).all()
    elif release_type == "patreon":
        releases = db.query(Chapter).filter(Chapter.release_date_patreon <= datetime.now(), Chapter.release_date_regular >= datetime.now()).order_by(desc(Chapter.release_date_patreon)).all()

    data = []
    for release in releases:
        data.append({
            "id": release.id,
            "chapter_number": release.chapter_number,
            "manga": release.manga.name,
            "volume": release.volume_number,
            "type": release_type,
            "cover": release.manga.cover_path,
            "title": release.name
        })

    return data

@app.get("/privacy-policy")
def policy(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    settings = get_settings(db)

    return templates.TemplateResponse(request, "privacy-policy.html", {
        "settings": settings,
        "current_user": current_user,
    })

@app.get("/imprint")
def imprint(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    settings = get_settings(db)

    return templates.TemplateResponse(request, "imprint.html", {
        "settings": settings,
        "current_user": current_user,
    })

@app.get("/api/test-email")
def test_email(request: Request, db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    site_name = get_setting(db, 'site_name', 'Lyra Reader')
    subject = f"Test Email from {site_name}"
    html_body = f"<p>This is a test email from <strong>{site_name}</strong>. Your email configuration is working correctly.</p>"
    text_body = f"This is a test email from {site_name}. Your email configuration is working correctly."
    success = send_email_smtp(current_user.email, subject, html_body, text_body, db)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send test email")
    return {"status": "success"}

def check_api_token(db, token):
    setting = db.query(Setting).filter(Setting.setting_key == "api_token").first()
    if setting and setting.setting_value:
        return hmac.compare_digest(setting.setting_value, token)
    return False

def user_has_rights(request, db, right: str):
    current_user = get_current_user_optional(request, db)

    if current_user and right in current_user.rights:
        return True
    return False

def get_smtp_settings(db: Session):
    settings_keys = [
        'smtp_server', 'smtp_port', 'smtp_username', 'smtp_password',
        'smtp_use_tls', 'smtp_use_ssl', 'smtp_from_email', 'smtp_from_name'
    ]
    
    settings = {}
    for key in settings_keys:
        setting = db.query(Setting).filter(Setting.setting_key == key).first()
        if setting:
            # Convert boolean strings
            if key in ['smtp_use_tls', 'smtp_use_ssl']:
                settings[key] = setting.setting_value.lower() in ['true', '1', 'yes', 'on']
            # Convert port to int
            elif key == 'smtp_port':
                try:
                    settings[key] = int(setting.setting_value)
                except ValueError:
                    settings[key] = 587  # Default port
            else:
                settings[key] = setting.setting_value
        else:
            # Set defaults
            defaults = {
                'smtp_server': 'localhost',
                'smtp_port': 587,
                'smtp_username': '',
                'smtp_password': '',
                'smtp_use_tls': True,
                'smtp_use_ssl': False,
                'smtp_from_email': 'noreply@localhost',
                'smtp_from_name': 'Lyra Reader'
            }
            settings[key] = defaults.get(key, '')
    
    return settings

def send_email_smtp(to_email: str, subject: str, html_body: str, text_body: str, db: Session):
    try:
        # Get SMTP settings
        smtp_settings = get_smtp_settings(db)
        
        # Validate required settings
        if not smtp_settings.get('smtp_server'):
            print("SMTP server not configured")
            return False
        
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = formataddr((smtp_settings['smtp_from_name'], smtp_settings['smtp_from_email']))
        message["To"] = to_email
        
        # Add both plain text and HTML versions
        text_part = MIMEText(text_body, "plain")
        html_part = MIMEText(html_body, "html")
        
        message.attach(text_part)
        message.attach(html_part)
        
        # Create SMTP session
        if smtp_settings['smtp_use_ssl']:
            # Use SSL
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(smtp_settings['smtp_server'], smtp_settings['smtp_port'], context=context)
        else:
            # Use regular SMTP
            server = smtplib.SMTP(smtp_settings['smtp_server'], smtp_settings['smtp_port'])
            
            # Use TLS if enabled
            if smtp_settings['smtp_use_tls']:
                context = ssl.create_default_context()
                server.starttls(context=context)
        
        # Login if credentials provided
        if smtp_settings['smtp_username'] and smtp_settings['smtp_password']:
            server.login(smtp_settings['smtp_username'], smtp_settings['smtp_password'])
        
        # Send email
        server.sendmail(smtp_settings['smtp_from_email'], to_email, message.as_string())
        server.quit()
        
        print(f"Email sent successfully to {to_email}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"SMTP Authentication failed: {e}")
        return False
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection failed: {e}")
        return False
    except smtplib.SMTPException as e:
        print(f"SMTP Error: {e}")
        return False
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False

def send_verification_email(email: str, token: str, db: Session):
    site_name = get_setting(db, 'site_name', 'Lyra Reader')
    base_url = get_setting(db, 'base_url', 'http://localhost:8000')

    verification_url = f"{base_url}/verify-email?token={token}"
    ctx = {"site_name": site_name, "verification_url": verification_url}

    subject = translate_with_vars("Verify your email address - {site_name}", site_name=site_name)
    html_body = templates.env.get_template("email/verify_email.html").render(**ctx)
    text_body = templates.env.get_template("email/verify_email.txt").render(**ctx)

    return send_email_smtp(email, subject, html_body, text_body, db)

def send_email_change_verification(email: str, token: str, db: Session):
    site_name = get_setting(db, 'site_name', 'Lyra Reader')
    base_url = get_setting(db, 'base_url', 'http://localhost:8000')

    verification_url = f"{base_url}/verify-email-change?token={token}"
    ctx = {"site_name": site_name, "verification_url": verification_url}

    subject = translate_with_vars("Verify your new email address - {site_name}", site_name=site_name)
    html_body = templates.env.get_template("email/verify_email_change.html").render(**ctx)
    text_body = templates.env.get_template("email/verify_email_change.txt").render(**ctx)

    return send_email_smtp(email, subject, html_body, text_body, db)

def verify_recaptcha(token: str) -> bool:
    secret_key = os.getenv("RECAPTCHA_SECRET_KEY", "")
    
    payload = {
        'secret': secret_key,
        'response': token
    }
    
    try:
        response = requests.post('https://www.google.com/recaptcha/api/siteverify', data=payload)
        result = response.json()
        return result.get('success', False)
    except Exception:
        return False

def get_setting_value(db: Session, key: str, default: str = ""):
    setting = db.query(Setting).filter(Setting.setting_key == key).first()
    return setting.setting_value if setting else default

def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)