import os, uuid, sqlite3, secrets, base64, json
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(APP_DIR, "sellai.db")

RECEIVE_ADDRESS = os.getenv("SELLAI_TRON_ADDRESS", "TExSinZWkudCW7PhLbFnrWFbTpSJ3P8DoX")
USDT_CONTRACT = os.getenv("USDT_TRON_CONTRACT", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
TRONGRID_URL = os.getenv("TRONGRID_URL", "https://api.trongrid.io").rstrip("/")
TRONGRID_KEY = os.getenv("TRONGRID_API_KEY", "")
PRO_PRICE_USDT = float(os.getenv("PRO_PRICE_USDT", "5"))
PRO_DAYS = int(os.getenv("PRO_DAYS", "30"))

# AI provider configuration. OpenRouter is the primary provider for SellAI.
# OpenAI variables are kept as a fallback for compatibility.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-5")
ADMIN_KEY = os.getenv("SELLAI_ADMIN_KEY", "")

app = FastAPI(title="SellAI v10 Production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET","POST","OPTIONS"],
    allow_headers=["*"],
)

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      credits INTEGER DEFAULT 5,
      plan TEXT DEFAULT 'free',
      pro_until TEXT
    );
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS orders(
      id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, amount_usdt REAL NOT NULL,
      address TEXT NOT NULL, status TEXT DEFAULT 'pending',
      tx_hash TEXT UNIQUE, created_at TEXT NOT NULL, paid_at TEXT
    );
    """)
    c.commit(); c.close()

init()

class Auth(BaseModel):
    email: EmailStr
    password: str

class GenerateReq(BaseModel):
    token: str
    image_data_url: str
    language: str = "fa"

class OrderReq(BaseModel):
    token: str

class VerifyReq(BaseModel):
    token: str
    order_id: str
    tx_hash: str

def now(): return datetime.now(timezone.utc)

def ph(password: str) -> str:
    # PBKDF2-HMAC with a per-password random salt; stdlib-only for easy deployment.
    salt = secrets.token_bytes(16)
    digest = __import__("hashlib").pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return "pbkdf2$210000$" + salt.hex() + "$" + digest.hex()

def verify_ph(password: str, stored: str) -> bool:
    try:
        import hashlib, hmac
        kind, rounds, salt_hex, digest_hex = stored.split("$", 3)
        if kind != "pbkdf2": return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False

def token_for(uid):
    t = secrets.token_urlsafe(32)
    c=db(); c.execute("INSERT INTO sessions VALUES(?,?,?)",(t,uid,now().isoformat())); c.commit(); c.close()
    return t

def user_from_token(t):
    if not t: raise HTTPException(401,"Login required")
    c=db()
    r=c.execute("""SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
                   WHERE s.token=?""",(t,)).fetchone()
    c.close()
    if not r: raise HTTPException(401,"Invalid session")
    return r

@app.get("/health")
def health(): return {"ok": True, "service": "SellAI"}

@app.get("/")
def home(): return FileResponse(os.path.join(APP_DIR,"index.html"))

@app.get("/manifest.webmanifest")
def manifest(): return FileResponse(os.path.join(APP_DIR,"manifest.webmanifest"), media_type="application/manifest+json")

@app.get("/sw.js")
def sw(): return FileResponse(os.path.join(APP_DIR,"sw.js"), media_type="application/javascript")

@app.post("/register")
def register(a:Auth):
    if len(a.password) < 8: raise HTTPException(400,"Password must be at least 8 characters")
    email=a.email.lower().strip()
    c=db()
    try:
        c.execute("INSERT INTO users(email,password_hash,credits) VALUES(?,?,5)",(email,ph(a.password)))
        c.commit(); uid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        raise HTTPException(400,"Email already registered")
    finally: c.close()
    return {"token":token_for(uid)}

@app.post("/login")
def login(a:Auth):
    email=a.email.lower().strip()
    c=db(); r=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone(); c.close()
    if not r or not verify_ph(a.password, r["password_hash"]):
        raise HTTPException(401,"Wrong email or password")
    return {"token":token_for(r["id"])}

@app.get("/me")
def me(token: str):
    u=user_from_token(token)
    pro = u["plan"]=="pro" and u["pro_until"] and u["pro_until"] > now().isoformat()
    return {"email":u["email"],"credits":u["credits"],"plan":"pro" if pro else "free","pro_until":u["pro_until"]}

def demo_copy(lang):
    if lang=="fa":
        return {"title":"محصول جذاب و باکیفیت","description":"یک محصول کاربردی و خوش‌ساخت با طراحی جذاب؛ مناسب برای فروشگاه آنلاین و شبکه‌های اجتماعی.","instagram":"✨ این محصول را برای سبک زندگی بهتر انتخاب کنید. برای سفارش پیام بدهید.","hashtags":"#فروشگاه #محصول #خرید_آنلاین #SellAI"}
    return {"title":"Premium Product","description":"A practical, well-designed product with an attractive presentation, ready for your online store.","instagram":"✨ Upgrade your everyday style with this product. Message us to order.","hashtags":"#product #onlineshop #shopping #SellAI"}

def ai_generate(image_data_url, lang):
    # Prefer OpenRouter. Its free router can select a vision-capable free model.
    if OPENROUTER_API_KEY:
        prompt = (
            "Analyze this product image and create concise ecommerce copy. "
            "Return ONLY valid JSON with exactly these keys: title, description, instagram, hashtags. "
            "Do not invent specifications that are not visible. "
            + ("Write in Persian." if lang=="fa" else "Write in English.")
        )
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type":"text","text":prompt},
                    {"type":"image_url","image_url":{"url":image_data_url}}
                ]
            }],
            "response_format": {"type": "json_object"}
        }
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://sellal.onrender.com",
            "X-Title": "SellAI"
        }
        r = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=90)
        if r.status_code >= 400:
            detail = r.text[:300].replace("\n", " ")
            raise HTTPException(502, f"AI provider error ({r.status_code}): {detail}")
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"]
            if isinstance(text, list):
                text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
            return json.loads(text)
        except Exception:
            raise HTTPException(502, "AI returned invalid JSON")

    # OpenAI fallback, retained for compatibility if an OpenAI key is configured.
    if OPENAI_API_KEY:
        prompt = (
            "Analyze this product image and create concise ecommerce copy. "
            "Return ONLY valid JSON with keys: title, description, instagram, hashtags. "
            "Do not invent specifications that are not visible. "
            + ("Write in Persian." if lang=="fa" else "Write in English.")
        )
        payload = {
            "model": AI_MODEL,
            "input": [{
                "role": "user",
                "content": [
                    {"type":"input_text","text":prompt},
                    {"type":"input_image","image_url":image_data_url}
                ]
            }]
        }
        headers={"Authorization":f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"}
        r=requests.post(f"{OPENAI_BASE_URL}/responses", headers=headers, json=payload, timeout=60)
        if r.status_code >= 400:
            raise HTTPException(502, f"AI provider error ({r.status_code})")
        data=r.json()
        text=data.get("output_text")
        if not text:
            parts=[]
            for item in data.get("output",[]):
                for content in item.get("content",[]):
                    if content.get("type") in ("output_text","text") and content.get("text"):
                        parts.append(content["text"])
            text="".join(parts).strip()
        try:
            return json.loads(text)
        except Exception:
            raise HTTPException(502,"AI returned invalid JSON")

    return demo_copy(lang)

@app.post("/generate")
def generate(x:GenerateReq):
    u=user_from_token(x.token)
    pro = u["plan"]=="pro" and u["pro_until"] and u["pro_until"] > now().isoformat()
    if not pro and u["credits"] <= 0:
        raise HTTPException(402,"No free credits. Upgrade to Pro.")
    if not x.image_data_url.startswith("data:image/"):
        raise HTTPException(400,"Invalid image")
    if len(x.image_data_url) > 8_000_000:
        raise HTTPException(413,"Image is too large")
    out=ai_generate(x.image_data_url, "fa" if x.language=="fa" else "en")
    if not all(k in out for k in ("title","description","instagram","hashtags")):
        raise HTTPException(502,"AI response missing required fields")
    if not pro:
        c=db(); c.execute("UPDATE users SET credits=credits-1 WHERE id=? AND credits>0",(u["id"],)); c.commit(); c.close()
    return out

@app.post("/orders")
def create_order(x:OrderReq):
    u=user_from_token(x.token)
    oid=uuid.uuid4().hex
    c=db(); c.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)",
        (oid,u["id"],PRO_PRICE_USDT,RECEIVE_ADDRESS,"pending",None,now().isoformat(),None))
    c.commit(); c.close()
    return {"order_id":oid,"amount_usdt":PRO_PRICE_USDT,"network":"TRON","token":"USDT","address":RECEIVE_ADDRESS,"expires_minutes":30}

def get_transfers(address):
    url=f"{TRONGRID_URL}/v1/accounts/{address}/transactions/trc20"
    headers={"TRON-PRO-API-KEY":TRONGRID_KEY} if TRONGRID_KEY else {}
    params={"only_confirmed":"true","limit":200,"contract_address":USDT_CONTRACT,"only_to":"true"}
    r=requests.get(url,headers=headers,params=params,timeout=15)
    r.raise_for_status()
    return r.json().get("data",[])

@app.post("/orders/verify")
def verify(x:VerifyReq):
    u=user_from_token(x.token)
    tx=x.tx_hash.strip()
    if len(tx) < 20 or len(tx) > 100: raise HTTPException(400,"Invalid transaction hash")
    c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND user_id=?",(x.order_id,u["id"])).fetchone()
    if not o: c.close(); raise HTTPException(404,"Order not found")
    if o["status"]=="paid": c.close(); return {"status":"paid","message":"Already verified"}
    if c.execute("SELECT 1 FROM orders WHERE tx_hash=?",(tx,)).fetchone():
        c.close(); raise HTTPException(400,"Transaction already used")
    c.close()
    try: transfers=get_transfers(RECEIVE_ADDRESS)
    except Exception as e: raise HTTPException(502,f"Blockchain lookup failed: {e}")
    match=None
    for t in transfers:
        if str(t.get("transaction_id","")).lower()!=tx.lower(): continue
        if str(t.get("to","")).lower()!=RECEIVE_ADDRESS.lower(): continue
        if str(t.get("token_info",{}).get("address","")).lower()!=USDT_CONTRACT.lower(): continue
        decimals=int(t.get("token_info",{}).get("decimals",6))
        amount=int(t.get("value","0"))/(10**decimals)
        if amount + 1e-9 >= float(o["amount_usdt"]):
            match=t; break
    if not match: raise HTTPException(400,"No matching confirmed USDT payment found")
    paid_at=now().isoformat()
    until=now()+timedelta(days=PRO_DAYS)
    c=db(); c.execute("UPDATE orders SET status='paid',tx_hash=?,paid_at=? WHERE id=?",(tx,paid_at,o["id"]))
    c.execute("UPDATE users SET plan='pro',pro_until=? WHERE id=?",(until.isoformat(),u["id"]))
    c.commit(); c.close()
    return {"status":"paid","pro_until":until.isoformat()}

def admin_guard(x_admin_key):
    if not ADMIN_KEY or not secrets.compare_digest(x_admin_key or "", ADMIN_KEY):
        raise HTTPException(403,"Forbidden")

@app.get("/admin/stats")
def stats(x_admin_key: str = Header(default="")):
    admin_guard(x_admin_key)
    c=db()
    users=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    paid=c.execute("SELECT COUNT(*) n FROM orders WHERE status='paid'").fetchone()["n"]
    revenue=c.execute("SELECT COALESCE(SUM(amount_usdt),0) n FROM orders WHERE status='paid'").fetchone()["n"]
    pending=c.execute("SELECT COUNT(*) n FROM orders WHERE status='pending'").fetchone()["n"]
    c.close()
    return {"users":users,"paid_orders":paid,"revenue_usdt":revenue,"pending_orders":pending}

@app.get("/admin/orders")
def admin_orders(x_admin_key: str = Header(default="")):
    admin_guard(x_admin_key)
    c=db(); rows=[dict(r) for r in c.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100")]; c.close()
    return rows
