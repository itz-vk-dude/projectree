import os
import uuid
import logging
import urllib.parse
from datetime import datetime, timedelta

import requests
import pandas as pd
from flask import Flask, render_template, redirect, url_for, request, abort, jsonify, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv

load_dotenv()

# --- LOGGING (replaces scattered print() debug statements) ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("projectree")

# --- APP FACTORY BASICS ---
app = Flask(__name__)

# SECRET_KEY is required in production. Fail fast instead of silently using a
# guessable default (the old fallback "projectree-secret-key-2026" was
# committed to source control and must never be used again).
SECRET_KEY = os.getenv("SECRET_KEY")
IS_PRODUCTION = os.getenv("VERCEL") == "1" or os.getenv(
    "FLASK_ENV") == "production"
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production.")
    SECRET_KEY = "dev-only-insecure-key"
    logger.warning(
        "SECRET_KEY not set - using an insecure dev-only key. Set SECRET_KEY in .env for real use.")
app.secret_key = SECRET_KEY

# --- DATABASE CONFIG ---
# Supabase gives you a `postgres://...` URI. SQLAlchemy 1.4+/psycopg2 wants
# `postgresql+psycopg2://...`. Normalize whatever we're given so the same
# code works locally (sqlite fallback) and in production (Supabase Postgres).
raw_db_url = os.getenv("DATABASE_URL", "").strip()
if raw_db_url:
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace(
            "postgres://", "postgresql+psycopg2://", 1)
    elif raw_db_url.startswith("postgresql://"):
        raw_db_url = raw_db_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1)
    # Supabase requires SSL; make sure it's set if the caller didn't add it.
    if "sslmode" not in raw_db_url:
        sep = "&" if "?" in raw_db_url else "?"
        raw_db_url = f"{raw_db_url}{sep}sslmode=require"
    db_uri = raw_db_url
else:
    if IS_PRODUCTION:
        raise RuntimeError(
            "DATABASE_URL environment variable is required in production.")
    db_uri = "sqlite:///dev.db"
    logger.warning(
        "DATABASE_URL not set - falling back to local sqlite:///dev.db for development only.")

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
    # Supabase's pooler (pgbouncer) + serverless functions play best with a
    # small pool and no persistent connections held open between invocations.
    "pool_size": int(os.getenv("DB_POOL_SIZE", "3")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "2")),
}

# --- COOKIE / SESSION HARDENING ---
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SECURE'] = IS_PRODUCTION

db = SQLAlchemy(app)

# --- CSRF PROTECTION ---
# Applies to all standard HTML <form> posts (login, register, admin panel).
# The JSON API endpoints below are same-origin fetch() calls guarded by
# login_required + SameSite=Lax cookies, so they're exempted here to avoid
# having to thread a CSRF token through every fetch() call in the templates.
csrf = CSRFProtect(app)

# --- RATE LIMITING (protects paid AI endpoints + auth from abuse) ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URL", "memory://"),
)

# --- FLASK-LOGIN ---
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please login to access this page.'
login_manager.login_message_category = 'warning'


# --- MODELS ---
class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    interest = db.Column(db.String(50))
    type = db.Column(db.String(50))
    level = db.Column(db.String(50))
    language = db.Column(db.String(50))
    status = db.Column(db.String(20), default='Available')
    expected_output = db.Column(db.Text)
    duration_days = db.Column(db.Integer)
    steps = db.Column(db.Text)
    cached_guide = db.Column(db.Text)
    cached_explanation = db.Column(db.Text)

    def steps_list(self):
        if not self.steps:
            return []
        result = []
        for chunk in self.steps.split('|'):
            parts = chunk.strip().split('[:]')
            result.append({
                'title': parts[0].strip() if len(parts) > 0 else '',
                'desc': parts[1].strip() if len(parts) > 1 else '',
            })
        return result


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# NOTE ON MULTI-USER FIX:
# The original build stored XP/level/streak/badges/step-completion in
# singleton or session-only records (e.g. UserStats id=1) which meant every
# visitor to the site shared ONE global XP total and ONE global badge shelf.
# That's fine for a single-user demo but breaks the moment a second real
# person signs up. Every gamification table below is now scoped by user_id
# and requires login, so progress is truly personal.

class UserStats(db.Model):
    __tablename__ = 'user_stats'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), unique=True, nullable=False)
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    streak_days = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.Date, nullable=True)
    trees_grown = db.Column(db.Integer, default=0)


class Achievement(db.Model):
    __tablename__ = 'achievements'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), nullable=False)
    badge_id = db.Column(db.String(50))
    title = db.Column(db.String(100))
    description = db.Column(db.String(200))
    emoji = db.Column(db.String(10))
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint(
        'user_id', 'badge_id', name='uq_user_badge'),)


class UserProject(db.Model):
    """Replaces the old session['active_ids']/session['done_ids'] approach.

    Session-only tracking meant progress vanished on a new device/browser or
    when cookies were cleared. Persisting it in the DB per-user fixes that
    and is required once you have real accounts.
    """
    __tablename__ = 'user_projects'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey(
        'projects.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='active')  # active | done
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint(
        'user_id', 'project_id', name='uq_user_project'),)


class StepCompletion(db.Model):
    __tablename__ = 'step_completions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey(
        'projects.id', ondelete='CASCADE'), nullable=False)
    step_index = db.Column(db.Integer, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint(
        'user_id', 'project_id', 'step_index', name='uq_user_proj_step'),)


class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    id = db.Column(db.String(36), primary_key=True,
                   default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), default="New Conversation")
    context_project_id = db.Column(
        db.Integer, db.ForeignKey('projects.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship(
        'ChatMessage',
        backref='session',
        lazy=True,
        cascade='all, delete-orphan')


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey(
        'chat_sessions.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# --- XP / LEVEL SYSTEM ---
LEVEL_THRESHOLDS = [0, 50, 150, 300, 500, 800, 1200, 1800, 2500, 3500]
LEVEL_NAMES = [
    "Seedling", "Sprout", "Sapling", "Young Tree",
    "Tall Tree", "Forest Guard", "Ancient Oak",
    "Grove Master", "Forest Elder", "Forest Legend"
]


def xp_to_level(xp):
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
    level = min(level, len(LEVEL_NAMES))
    current_floor = LEVEL_THRESHOLDS[level - 1]
    next_floor = LEVEL_THRESHOLDS[level] if level < len(
        LEVEL_THRESHOLDS) else current_floor + 1000
    progress_pct = int((xp - current_floor) /
                       max(1, next_floor - current_floor) * 100)
    return {"level": level,
            "name": LEVEL_NAMES[level - 1],
            "xp": xp,
            "current_floor": current_floor,
            "next_floor": next_floor,
            "progress_pct": progress_pct}


def update_streak(stats):
    today = date.today()
    if stats.last_activity is None:
        stats.streak_days = 1
    elif stats.last_activity == today - timedelta(days=1):
        stats.streak_days += 1
    elif stats.last_activity < today - timedelta(days=1):
        stats.streak_days = 1
    stats.last_activity = today


def get_or_create_stats(user_id):
    stats = UserStats.query.filter_by(user_id=user_id).first()
    if not stats:
        stats = UserStats(user_id=user_id, xp=0, level=1,
                          streak_days=0, trees_grown=0)
        db.session.add(stats)
        db.session.commit()
    return stats


def get_my_active_ids():
    return [up.project_id for up in UserProject.query.filter_by(
        user_id=current_user.id, status='active').all()]


def get_my_done_ids():
    return [up.project_id for up in UserProject.query.filter_by(
        user_id=current_user.id, status='done').all()]


def add_active(pid):
    existing = UserProject.query.filter_by(
        user_id=current_user.id, project_id=pid).first()
    if not existing:
        db.session.add(UserProject(user_id=current_user.id,
                       project_id=pid, status='active'))
        db.session.commit()


def move_to_done(pid):
    up = UserProject.query.filter_by(
        user_id=current_user.id, project_id=pid).first()
    if not up:
        up = UserProject(user_id=current_user.id, project_id=pid)
        db.session.add(up)
    up.status = 'done'
    up.completed_at = datetime.utcnow()
    db.session.commit()


def check_achievements(stats, xp_before, user_id):
    unlocks = []
    checks = [
        ("first_step", "First Leaf",
         "Completed your first task step", "🌿", lambda: True),
        ("xp_100", "Century Grower", "Earned 100 XP",
         "💯", lambda: stats.xp >= 100),
        ("xp_500", "Power Gardener", "Earned 500 XP",
         "⚡", lambda: stats.xp >= 500),
        ("xp_1000", "XP Legend", "Earned 1000 XP",
         "🏆", lambda: stats.xp >= 1000),
        ("streak_3", "3-Day Streak", "Active 3 days in a row",
         "🔥", lambda: stats.streak_days >= 3),
        ("streak_7", "Week Warrior", "Active 7 days in a row",
         "🗓️", lambda: stats.streak_days >= 7),
        ("first_tree", "First Tree", "Completed your first project",
         "🌳", lambda: stats.trees_grown >= 1),
        ("forest_5", "Forest Starter", "Completed 5 projects",
         "🌲", lambda: stats.trees_grown >= 5),
        ("forest_10", "Forest Builder", "Completed 10 projects",
         "🏕️", lambda: stats.trees_grown >= 10),
    ]
    for badge_id, title, desc, emoji, condition in checks:
        if condition() and not Achievement.query.filter_by(
                user_id=user_id, badge_id=badge_id).first():
            db.session.add(
                Achievement(
                    user_id=user_id,
                    badge_id=badge_id,
                    title=title,
                    description=desc,
                    emoji=emoji))
            unlocks.append({"emoji": emoji, "title": title})
    db.session.commit()
    return unlocks


# --- ML ENGINE ---
# Trained lazily on first use rather than at import time, since a serverless
# function has no long-lived `if __name__ == "__main__"` startup hook. The
# module-level globals persist across warm invocations of the same instance,
# so most requests still hit the cached matrix.
vectorizer = TfidfVectorizer(stop_words='english')
project_tfidf_matrix = None
all_projects_df = None


def train_engine():
    global project_tfidf_matrix, all_projects_df
    logger.info("Training ML recommendation engine...")
    rows = Project.query.all()
    if not rows:
        logger.warning(
            "No projects in DB yet - recommendation engine not trained.")
        return
    data = [{"id": p.id, "title": p.title, "description": p.description or "",
             "language": p.language or "", "level": p.level or "",
             "interest": p.interest or "", "type": p.type or "",
             "content": f"{p.interest} {p.type} {p.level} {p.language} {p.description}"}
            for p in rows]
    all_projects_df = pd.DataFrame(data)
    project_tfidf_matrix = vectorizer.fit_transform(all_projects_df['content'])
    logger.info("ML Engine trained on %d projects.", len(data))


def ensure_engine_trained():
    if project_tfidf_matrix is None:
        train_engine()


# --- AI HELPERS ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


def explain_project_ai(project):
    if not OPENROUTER_API_KEY:
        return "AI explanation is currently unavailable. (Missing OPENROUTER_API_KEY.)"
    prompt = (
        f"Project Title: {project.title}\nDescription: {project.description}\n"
        f"Level: {project.level} | Language: {project.language}\n\n"
        "Explain this project to a student in simple, friendly language. "
        "Include: what they will build, what they will learn, and a simple getting-started tip. "
        "Keep it under 200 words.")
    try:
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": os.getenv("PUBLIC_APP_URL", "https://projectree.app"),
                     "X-Title": "Projectree Explainer"},
            json={"model": "mistralai/mistral-7b-instruct:free",
                  "messages": [{"role": "user", "content": prompt}], "max_tokens": 300},
            timeout=20)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.exception("AI explanation error")
        return "⚠ Sorry, the AI explanation service is temporarily unavailable. Please try again shortly."


def generate_full_guide(project):
    """Generate a complete start-to-deploy guide for a project using Groq AI."""
    if not GROQ_API_KEY:
        logger.warning("Missing GROQ_API_KEY - cannot generate guide.")
        return None

    encoded_title = urllib.parse.quote(
        project.title + " " + project.interest + " HQ")
    img_url = f"https://image.pollinations.ai/prompt/{encoded_title}?width=1200&height=600&nologo=true"

    prompt = f"""You are an absolute expert 10x senior developer mentoring a junior who has ZERO prior knowledge. Generate a gorgeous, extremely comprehensive, MASTERCLASS step-by-step tutorial for this project.

Project Title: {project.title}
Language: {project.language}
Level: {project.level}
Domain: {project.interest}

CRITICAL RULES:
1. EXTREME DETAIL: The user is a complete beginner. Explain everything clearly from scratch to final deployment. Do not hold back on content, make it a full guide.
2. Provide the FULL, complete, working code for EVERY file you mention. Do NOT abbreviate code. Never use `# rest of the code`.
3. Structure the response strictly in Markdown. Use headings (##), lists, and bold text.
4. Your very first line MUST be this exact image Markdown:
![Project Image]({img_url})
5. Follow this strict structure. Adapt it depending on whether the project is SOFTWARE or HARDWARE:

   - **Introduction**: Quick overview of what the user will build and how it works.
   - **Prerequisites & Requirements**:
     - *If Software*: List all required software (IDE, Python, Node.js, databases etc.) and libraries.
     - *If Hardware/IoT*: Detail the exact microcontrollers (e.g., Arduino, Raspberry Pi, ESP32), components, and sensors needed. Briefly explain what each sensor does and what it looks like.
   - **Hardware Connections (Hardware/IoT ONLY)**: Provide the EXACT pin numbers in a clean Markdown table (e.g., ESP32 GPIO 4 -> DHT11 Data). Then, provide a click-able YouTube search link for the user so they can watch a video on how to connect these specific components.
   - **Architecture Diagram**: Provide a `mermaid` code block showing how the system flows. CRITICAL MERMAID RULE: You MUST use a simple `graph TD`. DO NOT use complex state or sequence diagrams. Keep labels simple (letters/spaces only).
   - **Folder Structure**: Define the exact directory layout required.
   - **Setup & Installation**: Precise commands to install dependencies and setup the environment.
   - **Complete Source Code**: Provide every file using syntax-highlighted code blocks.
   - **How to Run & Deploy**: Step-by-step instructions on running locally and deploying to production.

6. For web/UI code, you MUST use Bootstrap 5 to make the UI look incredibly premium, deeply styled, with proper buttons and colors.

Write your entire response in beautifully formatted GitHub Flavored Markdown. Do NOT wrap your whole response in a JSON block or a ```markdown wrapper. Just write the Markdown directly.
"""
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 8000,
                  "temperature": 0.7},
            timeout=55)
        res.raise_for_status()
        raw = res.json()["choices"][0]["message"]["content"].strip()
        return {"markdown": raw}
    except requests.exceptions.HTTPError:
        logger.exception("Guide Groq HTTP error")
        return None
    except requests.exceptions.Timeout:
        logger.error("Guide Groq request timed out")
        return None
    except Exception:
        logger.exception("Guide Groq error")
        return None


def generate_project_ideas(domain, level, technologies):
    if not OPENROUTER_API_KEY:
        return "⚠️ AI idea generation is currently unavailable."
    prompt = f"""Generate 5 unique project ideas.
Domain: {domain}
Level: {level}
Technologies: {technologies}

Return strictly in this format:
1. Project Title:
   Description:
   Technologies:
2. Project Title:
   Description:
   Technologies:"""
    try:
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": os.getenv("PUBLIC_APP_URL", "https://projectree.app"),
                     "X-Title": "Projectree Idea Generator"},
            json={"model": "mistralai/mistral-7b-instruct:free",
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30)
        if res.status_code != 200:
            logger.error("OpenRouter idea gen error %s: %s",
                         res.status_code, res.text[:300])
            return "⚠️ The AI idea generator is temporarily unavailable. Please try again."
        result = res.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        return "⚠️ No ideas returned."
    except requests.exceptions.Timeout:
        return "⚠️ Request timed out. Try again."
    except Exception:
        logger.exception("Idea generation error")
        return "⚠️ Something went wrong generating ideas. Please try again."


def get_github_trending(topic="python"):
    try:
        url = "https://api.github.com/search/repositories"
        res = requests.get(
            url,
            params={
                "q": topic,
                "sort": "stars",
                "order": "desc",
                "per_page": 5},
            timeout=8,
            headers={
                "Accept": "application/vnd.github+json"})
        res.raise_for_status()
        return [{"title": r.get("name", ""), "desc": r.get("description") or "No description.",
                 "url": r.get("html_url", "#"), "stars": r.get("stargazers_count", 0),
                 "language": r.get("language") or "N/A"}
                for r in res.json().get("items", [])[:5]]
    except Exception:
        logger.warning("GitHub trending fetch failed", exc_info=True)
        return []


# --- RESOURCES ---
RESOURCES = {
    'Web': 'https://developer.mozilla.org',
    'AI': 'https://tensorflow.org',
    'IoT': 'https://arduino.cc',
    'Security': 'https://owasp.org',
    'Blockchain': 'https://ethereum.org',
    'Data': 'https://pandas.pydata.org'
}


# --- ROUTES ---
@app.route('/')
@login_required
def home():
    return render_template('index.html', total_projects=Project.query.count())


@app.route('/services')
@login_required
def services():
    return render_template('services.html')


@app.route('/quiz')
def quiz():
    return render_template('quiz.html')


@app.route('/recommend', methods=['POST'])
@limiter.limit("30 per hour")
def recommend():
    interest = request.form.get('interest', '').strip()
    ptype = request.form.get('type', '').strip()
    level = request.form.get('level', '').strip()
    language = request.form.get('language', '').strip()
    ensure_engine_trained()
    if project_tfidf_matrix is None:
        return render_template(
            'results.html',
            projects=[],
            github_projects=[],
            error="No projects in database yet.")
    user_vec = vectorizer.transform([f"{interest} {ptype} {level} {language}"])
    scores = cosine_similarity(user_vec, project_tfidf_matrix)[0]
    results_df = all_projects_df.copy()
    results_df['score'] = (scores * 100).round(1)
    top = results_df.sort_values('score', ascending=False).head(12)
    return render_template(
        'results.html',
        projects=top.to_dict('records'),
        github_projects=get_github_trending(
            interest.lower() or 'python'),
        query={
            "interest": interest,
            "type": ptype,
            "level": level,
            "language": language})


@app.route('/project/<int:id>')
def project_details(id):
    p = db.session.get(Project, id)
    if not p:
        abort(404)
    roadmap = Project.query.filter_by(interest=p.interest).filter(
        Project.id != p.id).limit(3).all()
    res = RESOURCES.get(p.interest, 'https://google.com')
    return render_template(
        'details.html',
        project=p,
        steps=p.steps_list(),
        roadmap=roadmap,
        resource=res)


@app.route('/start/<int:id>')
@login_required
def start(id):
    p = db.session.get(Project, id)
    if not p:
        abort(404)
    add_active(p.id)
    return redirect(url_for('dashboard'))


@app.route('/complete/<int:id>')
@login_required
def complete(id):
    p = db.session.get(Project, id)
    if not p:
        abort(404)
    move_to_done(p.id)
    stats = get_or_create_stats(current_user.id)
    xp_before = stats.xp
    stats.xp += 100
    stats.trees_grown += 1
    update_streak(stats)
    db.session.commit()
    check_achievements(stats, xp_before, current_user.id)
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    active_ids = get_my_active_ids()
    done_ids = get_my_done_ids()
    active = Project.query.filter(Project.id.in_(
        active_ids)).all() if active_ids else []
    done = Project.query.filter(Project.id.in_(
        done_ids)).all() if done_ids else []
    project_progress = {}
    for p in active:
        steps = p.steps_list()
        total = len(steps)
        done_count = StepCompletion.query.filter_by(
            user_id=current_user.id,
            project_id=p.id,
            completed=True).count() if total else 0
        pct = round(done_count / total * 100, 1) if total else 0
        completed = {sc.step_index for sc in StepCompletion.query.filter_by(
            user_id=current_user.id, project_id=p.id, completed=True).all()}
        project_progress[p.id] = {"total": total,
                                  "done": done_count,
                                  "pct": pct,
                                  "completed_indices": list(completed)}
    stats = get_or_create_stats(current_user.id)
    lvl_info = xp_to_level(stats.xp)
    badges = Achievement.query.filter_by(user_id=current_user.id).order_by(
        Achievement.unlocked_at.desc()).all()
    return render_template('dashboard.html', active=active, done=done,
                           project_progress=project_progress, stats=stats,
                           lvl_info=lvl_info, badges=badges)


@app.route('/forest')
@login_required
def forest():
    done_ids = get_my_done_ids()
    done = Project.query.filter(Project.id.in_(
        done_ids)).all() if done_ids else []
    stats = get_or_create_stats(current_user.id)
    lvl_info = xp_to_level(stats.xp)
    badges = Achievement.query.filter_by(user_id=current_user.id).all()
    return render_template(
        'forest.html',
        done=done,
        stats=stats,
        lvl_info=lvl_info,
        badges=badges)


@app.route('/explain/<int:id>')
@login_required
def explain(id):
    p = db.session.get(Project, id)
    if not p:
        abort(404)
    if p.cached_explanation:
        explanation = p.cached_explanation
    else:
        explanation = explain_project_ai(p)
        p.cached_explanation = explanation
        db.session.commit()
    return render_template('explain.html', project=p, explanation=explanation)


@app.route('/guide/<int:id>')
@login_required
def guide(id):
    p = db.session.get(Project, id)
    if not p:
        abort(404)
    if p.cached_guide:
        guide_data = {"markdown": p.cached_guide}
    else:
        guide_data = generate_full_guide(p)
        if guide_data and "markdown" in guide_data:
            p.cached_guide = guide_data["markdown"]
            db.session.commit()
    return render_template('guide.html', project=p, guide=guide_data)


@app.route('/guide/<int:id>/pdf')
@login_required
def guide_pdf(id):
    """PDF export, rewritten to avoid Playwright + a headless Chromium binary.

    The original implementation launched a full Chromium browser via
    Playwright to screenshot the rendered guide page. That does not work on
    Vercel's serverless Python runtime (no browser binary, restrictive
    function size/time limits, no way to hit "127.0.0.1:5000" since there is
    no long-running local server). xhtml2pdf is pure-Python and renders
    simple HTML/CSS to PDF in-process, which is what serverless needs.
    """
    import markdown as md
    from xhtml2pdf import pisa
    from io import BytesIO

    p = db.session.get(Project, id)
    if not p:
        abort(404)

    if not p.cached_guide:
        guide_data = generate_full_guide(p)
        if guide_data and "markdown" in guide_data:
            p.cached_guide = guide_data["markdown"]
            db.session.commit()

    if not p.cached_guide:
        flash("Could not generate PDF guide. Please try again.", "warning")
        return redirect(url_for('guide', id=id))

    body_html = md.markdown(p.cached_guide, extensions=[
                            "fenced_code", "tables"])
    html = f"""
    <html><head><meta charset="utf-8">
    <style>
      body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11px; line-height: 1.5; }}
      h1, h2, h3 {{ color: #1a5d32; }}
      pre {{ background: #f4f4f4; padding: 8px; font-size: 9px; white-space: pre-wrap; }}
      code {{ background: #f4f4f4; padding: 1px 3px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      td, th {{ border: 1px solid #ccc; padding: 4px; }}
    </style></head>
    <body><h1>{p.title}</h1>{body_html}</body></html>
    """

    pdf_buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=pdf_buffer)
    if result.err:
        flash("Could not generate PDF guide. Please try again.", "warning")
        return redirect(url_for('guide', id=id))

    pdf_buffer.seek(0)
    safe_name = p.title.replace(' ', '_')
    return Response(
        pdf_buffer.read(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=Projectree_Masterclass_{safe_name}.pdf"}
    )


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    projects = []
    if query:
        projects = Project.query.filter(
            Project.title.ilike(f'%{query}%') | Project.description.ilike(f'%{query}%') |
            Project.interest.ilike(
                f'%{query}%') | Project.language.ilike(f'%{query}%')
        ).limit(24).all()
    return render_template('search.html', projects=projects, query=query)


@app.route('/category/<n>')
def category(n):
    projects = Project.query.filter_by(interest=n).limit(24).all()
    return render_template('category.html', projects=projects, category=n)


@app.route('/chat_page')
@login_required
def chat_page():
    return redirect(url_for('chat'))


@app.route('/chat')
@login_required
def chat():
    context_id = request.args.get('context_project_id', '')
    return render_template('chat.html', context_project_id=context_id)


@app.route('/export_portfolio')
@login_required
def export_portfolio():
    done_ids = get_my_done_ids()
    done = Project.query.filter(Project.id.in_(
        done_ids)).all() if done_ids else []
    return render_template('portfolio.html', projects=done)


@app.route('/global_forest')
def global_forest():
    return redirect(url_for('forest'))


@app.route('/ai_form')
@login_required
def ai_form():
    return render_template('ai_form.html')


@app.route('/generate_ai', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def generate_ai():
    domain = request.form.get('domain', '')
    level = request.form.get('level', '')
    tech_list = request.form.getlist('technologies')
    technologies = ', '.join(tech_list) if tech_list else 'Any'
    ideas = generate_project_ideas(domain, level, technologies)
    return render_template('ai_result.html', ideas=ideas)


# --- API ROUTES ---
# Exempted from CSRF because they're JSON fetch() calls guarded by
# login_required + SameSite=Lax session cookies (see CSRFProtect note above).

@app.route('/api/step-check', methods=['POST'])
@login_required
@csrf.exempt
def api_step_check():
    data = request.get_json(force=True, silent=True) or {}
    project_id = data.get('project_id')
    step_index = data.get('step_index')
    checked = data.get('checked', True)
    if project_id is None or step_index is None:
        return jsonify({"ok": False, "error": "Missing fields"}), 400
    p = db.session.get(Project, project_id)
    if not p:
        return jsonify({"ok": False, "error": "Project not found"}), 404
    if project_id not in get_my_active_ids():
        return jsonify({"ok": False, "error": "Project not active"}), 404
    sc = StepCompletion.query.filter_by(
        user_id=current_user.id,
        project_id=project_id,
        step_index=step_index).first()
    if not sc:
        sc = StepCompletion(user_id=current_user.id,
                            project_id=project_id, step_index=step_index)
        db.session.add(sc)
    sc.completed = checked
    sc.completed_at = datetime.utcnow() if checked else None
    xp_earned = 0
    new_badges = []
    stats = get_or_create_stats(current_user.id)
    if checked:
        xp_before = stats.xp
        stats.xp += 10
        xp_earned = 10
        update_streak(stats)
        db.session.commit()
        new_badges = check_achievements(stats, xp_before, current_user.id)
    else:
        db.session.commit()
    steps = p.steps_list()
    total = len(steps)
    done_count = StepCompletion.query.filter_by(
        user_id=current_user.id, project_id=project_id, completed=True).count()
    pct = round(done_count / total * 100, 1) if total else 0
    return jsonify({"ok": True,
                    "xp_earned": xp_earned,
                    "total_xp": stats.xp,
                    "level_info": xp_to_level(stats.xp),
                    "progress": {"pct": pct,
                                 "done": done_count,
                                 "total": total},
                    "new_badges": new_badges})


@app.route('/api/chat_sessions', methods=['GET', 'POST'])
@login_required
@csrf.exempt
def api_chat_sessions():
    if request.method == 'GET':
        sessions = ChatSession.query.filter_by(
            user_id=current_user.id).order_by(
            ChatSession.created_at.desc()).all()
        return jsonify([{"id": s.id, "title": s.title,
                       "created_at": s.created_at.isoformat()} for s in sessions])
    data = request.get_json(force=True, silent=True) or {}
    context_id = data.get('context_project_id')
    context_id = int(context_id) if str(context_id).isdigit() else None
    new_sess = ChatSession(user_id=current_user.id,
                           context_project_id=context_id)
    db.session.add(new_sess)
    db.session.commit()
    return jsonify({"id": new_sess.id})


@app.route('/api/chat_history/<session_id>', methods=['GET'])
@login_required
@csrf.exempt
def api_chat_history(session_id):
    sess = db.session.get(ChatSession, session_id)
    if not sess or sess.user_id != current_user.id:
        return jsonify({"error": "Not found"}), 404
    msgs = [{"role": m.role, "content": m.content} for m in ChatMessage.query.filter_by(
        session_id=session_id).order_by(ChatMessage.timestamp.asc()).all()]
    return jsonify({"messages": msgs})


@app.route('/api/chat', methods=['POST'])
@login_required
@csrf.exempt
@limiter.limit("60 per hour")
def api_chat():
    if not GROQ_API_KEY:
        return jsonify({"error": "Chat is temporarily unavailable."}), 503

    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get('session_id')
    user_msg_text = (data.get('new_message') or '').strip()

    if not session_id or not user_msg_text:
        return jsonify(
            {"error": "session_id and new_message are required"}), 400

    sess = db.session.get(ChatSession, session_id)
    if not sess or sess.user_id != current_user.id:
        return jsonify({"error": "Session not found"}), 404

    user_db_msg = ChatMessage(session_id=session_id,
                              role='user', content=user_msg_text)
    db.session.add(user_db_msg)
    db.session.commit()

    system = (
        "You are Projectree AI — a friendly project mentor and career coach for students and developers. "
        "You help users find project ideas, explain concepts, review code, and give career advice.\n"
        "CRITICAL: The user wants you to speak in Tanglish (Tamil spoken using English words like 'unaku puriyudha', 'oru project start pannalam'). "
        "Solve their doubts cleanly. If they have a doubt, explain step-by-step.")

    if sess.context_project_id:
        p = db.session.get(Project, sess.context_project_id)
        if p:
            system += f"\n\nCURRENT PROJECT CONTEXT:\nUser is currently exploring this project:\nTitle: {p.title}\nDescription: {p.description}\nLanguage: {p.language}\n\nHelp them build, understand, or troubleshoot this specific project."

    history_msgs = ChatMessage.query.filter_by(session_id=session_id).order_by(
        ChatMessage.timestamp.desc()).limit(10).all()
    history_msgs = history_msgs[::-1]

    api_messages = [{"role": "system", "content": system}]
    for m in history_msgs:
        api_messages.append({"role": m.role, "content": m.content})

    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": api_messages, "max_tokens": 1000},
            timeout=25)
        res.raise_for_status()
        reply = res.json()["choices"][0]["message"]["content"].strip()

        if sess.title == "New Conversation":
            sess.title = user_msg_text[:30] + \
                "..." if len(user_msg_text) > 30 else user_msg_text

        bot_db_msg = ChatMessage(
            session_id=session_id, role='assistant', content=reply)
        db.session.add(bot_db_msg)
        db.session.commit()

        return jsonify({"reply": reply})
    except Exception:
        logger.exception("Chat completion failed")
        return jsonify(
            {"error": "The AI assistant is temporarily unavailable. Please try again."}), 502


@app.route('/api/user-stats')
@login_required
@csrf.exempt
def api_user_stats():
    stats = get_or_create_stats(current_user.id)
    badges = [{"emoji": a.emoji, "title": a.title}
              for a in Achievement.query.filter_by(user_id=current_user.id).all()]
    return jsonify({"ok": True, "level_info": xp_to_level(stats.xp),
                    "streak": stats.streak_days, "badges": badges})


@app.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({"status": "ok" if db_ok else "degraded",
                   "db": db_ok}), (200 if db_ok else 503)


# --- AUTH ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("20 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not username or not email or not password:
            flash('All fields are required.', 'warning')
            return render_template('register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'warning')
            return render_template('register.html')
        existing = User.query.filter(
            (User.username == username) | (User.email == email)).first()
        if existing:
            flash('Username or Email already exists.', 'warning')
            return render_template('register.html')
        user = User(username=username, email=email)
        user.set_password(password)
        # NOTE: auto-promoting the very first registered account to admin is
        # convenient for a fresh dev database, but on a public production
        # deployment anyone who registers first (e.g. before you do) becomes
        # admin. Consider removing this once you've created your own admin
        # account, or gate it behind an ADMIN_SETUP_TOKEN env var instead.
        if User.query.count() == 0:
            user.is_admin = True
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Registration DB error")
            flash('A database error occurred during registration.', 'danger')
            return render_template('register.html')
        login_user(user)
        flash(f'Welcome to Projectree, {username}! 🌱', 'success')
        return redirect(url_for('home'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'Welcome back, {user.username}! 🌳', 'success')
            next_url = request.args.get('next')
            # Only allow relative redirects to avoid open-redirect via `next`.
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('home'))
        flash('Invalid email or password.', 'warning')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))


# --- ADMIN ROUTES ---
@app.route('/admin')
@login_required
@admin_required
def admin():
    projects = Project.query.order_by(Project.id.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', projects=projects, users=users)


@app.route('/admin/project/add', methods=['POST'])
@login_required
@admin_required
def admin_add_project():
    try:
        duration_days = int(request.form.get('duration_days', 7) or 7)
    except ValueError:
        duration_days = 7
    p = Project(
        title=request.form.get('title', '').strip(),
        description=request.form.get('description', '').strip(),
        interest=request.form.get('interest', '').strip(),
        type=request.form.get('type', '').strip(),
        level=request.form.get('level', '').strip(),
        language=request.form.get('language', '').strip(),
        duration_days=duration_days,
        steps=request.form.get('steps', '').strip(),
    )
    db.session.add(p)
    db.session.commit()
    global project_tfidf_matrix
    project_tfidf_matrix = None  # force ML engine retrain on next use
    flash(f'Project "{p.title}" added! 🌱', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/project/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_project(id):
    p = db.session.get(Project, id)
    if p:
        db.session.delete(p)
        db.session.commit()
        global project_tfidf_matrix
        project_tfidf_matrix = None
        flash('Project deleted.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/user/toggle_admin/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_toggle_admin(id):
    u = db.session.get(User, id)
    if u and u.id != current_user.id:
        u.is_admin = not u.is_admin
        db.session.commit()
        flash(f'Admin status updated for {u.username}.', 'success')
    return redirect(url_for('admin'))


# --- CONTEXT PROCESSOR ---
@app.context_processor
def inject_global_stats():
    try:
        if current_user.is_authenticated:
            stats = get_or_create_stats(current_user.id)
            return {
                "g_stats": stats,
                "g_lvl": xp_to_level(
                    stats.xp),
                "current_user": current_user}
    except Exception:
        pass
    return {"g_stats": None, "g_lvl": None, "current_user": current_user}


# --- ERROR HANDLERS ---
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled server error")
    db.session.rollback()
    return render_template('500.html'), 500


@app.errorhandler(429)
def rate_limited(e):
    return jsonify(
        {"ok": False, "error": "Too many requests. Please slow down and try again shortly."}), 429


# --- TEMPLATE GLOBALS ---
@app.template_global()
def levelemoji(level):
    emojis = ["🌱", "🌿", "🪴", "🌲", "🌳", "🏕️", "🏔️", "🌏", "🌌", "🏆"]
    return emojis[min(level - 1, len(emojis) - 1)]


@app.template_global()
def treestage(pct):
    stages = [(0, "🌱 Seed"), (1, "🌿 Sprouting"), (20, "🪴 Sapling"), (40, "🌲 Young Tree"),
              (60, "🌳 Growing"), (80, "🌳 Flourishing"), (100, "🏆 Mastered!")]
    label = stages[0][1]
    for threshold, name in stages:
        if pct >= threshold:
            label = name
    return label


# --- LOCAL DEV ENTRYPOINT ---
# In production (Vercel), this file is imported by api/index.py and this
# block never runs. Schema creation/migration for Supabase should be done
# once via scripts/init_db.py, not on every cold start of a serverless
# function (db.create_all() racing across concurrent invocations is unsafe,
# and re-running the "reset stuck projects" UPDATE on every request/import
# would be wasteful and wrong in a multi-instance deployment anyway).
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        train_engine()
    app.run(debug=not IS_PRODUCTION, host='0.0.0.0', port=int(
        os.getenv("PORT", 5000)), use_reloader=False)
