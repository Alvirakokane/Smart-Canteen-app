"""SmartCanteen backend: Flask + SQLite. Run: python app.py  ->  http://localhost:5000"""
import base64, csv, io, math, os, random, re, secrets, socket, sqlite3, time, datetime as dt
from functools import wraps
from flask import Flask, request, jsonify, g, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder="static", static_url_path="")
DB = "canteen.db"
TOKENS = {}  # token -> {id, name, role}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, pw TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS menu(id INTEGER PRIMARY KEY, name TEXT UNIQUE, category TEXT, price REAL, stock INTEGER DEFAULT 0, emoji TEXT DEFAULT '🍽️', cal INTEGER DEFAULT 0, protein REAL DEFAULT 0, carbs REAL DEFAULT 0, fat REAL DEFAULT 0, fiber REAL DEFAULT 0, ingredients TEXT DEFAULT '', image TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER, item_id INTEGER, qty INTEGER, total REAL, created TEXT, method TEXT DEFAULT 'cash', status TEXT DEFAULT 'unpaid', txn TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS ratings(id INTEGER PRIMARY KEY, user_id INTEGER, item_id INTEGER, stars INTEGER, comment TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, date TEXT, item TEXT, qty INTEGER, price REAL);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()

def init_db():
    if os.path.exists(DB):  # old database without nutrition columns -> rebuild with demo data
        t = sqlite3.connect(DB)
        old = 'image' not in [r[1] for r in t.execute('PRAGMA table_info(menu)')]
        t.close()
        if old:
            os.remove(DB)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    if not c.execute("SELECT 1 FROM users").fetchone():
        for n, e, p, r in [("Canteen Admin", "admin@canteen.edu", "admin123", "admin"),
                           ("Shweta", "student@canteen.edu", "student123", "student")]:
            c.execute("INSERT INTO users(name,email,pw,role) VALUES(?,?,?,?)", (n, e, generate_password_hash(p), r))
        items = [("Misal Pav", "Breakfast", 50, 80, 82, "🍲", 420, 14, 58, 15, 9, "Sprouted moth beans, spicy curry, farsan, pav"),
                 ("Vada Pav", "Snacks", 25, 60, 70, "🍔", 290, 7, 41, 11, 3, "Potato fritter, pav, garlic chutney"),
                 ("Poha", "Breakfast", 30, 50, 45, "🍚", 250, 6, 42, 6, 3, "Flattened rice, peanuts, onion, turmeric"),
                 ("Veg Biryani", "Lunch", 90, 40, 55, "🍛", 450, 10, 70, 13, 4, "Basmati rice, vegetables, saffron, spices"),
                 ("Masala Dosa", "Lunch", 60, 40, 48, "🥞", 380, 8, 55, 14, 4, "Rice-lentil batter, spiced potato, chutney"),
                 ("Dal Tadka Rice", "Lunch", 70, 40, 60, "🥘", 390, 13, 62, 8, 7, "Toor dal, rice, ghee tadka, cumin")]
        random.seed(7)
        today = dt.date.today()
        for n, cat, price, stock, base, *nut in items:
            c.execute("INSERT INTO menu(name,category,price,stock,emoji,cal,protein,carbs,fat,fiber,ingredients,image) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (n, cat, price, stock, *nut, '/img/' + n.lower().replace(' ', '-') + '.jpg'))
            for d in range(60, 0, -1):
                day = today - dt.timedelta(days=d)
                boost = 1.25 if day.weekday() in (0, 4) else (0.6 if day.weekday() == 6 else 1)
                c.execute("INSERT INTO history(date,item,qty,price) VALUES(?,?,?,?)",
                          (day.isoformat(), n, max(5, int(base * boost + random.randint(-8, 8))), price))
        c.commit()
    c.close()

def auth(role=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = TOKENS.get(request.headers.get("Authorization", "").replace("Bearer ", ""))
            if not u or (role and u["role"] != role):
                return jsonify(error="Please sign in with the right account."), 401
            g.user = u
            return f(*a, **k)
        return w
    return deco

def now():
    return dt.datetime.now().isoformat(timespec="seconds")

@app.get("/")
def home():
    return app.send_static_file("index.html")

@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    u = db().execute("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),)).fetchone()
    if not u or not check_password_hash(u["pw"], d.get("password") or ""):
        return jsonify(error="Wrong email or password."), 401
    tok = secrets.token_hex(16)
    TOKENS[tok] = {"id": u["id"], "name": u["name"], "role": u["role"]}
    return jsonify(token=tok, user=TOKENS[tok])

@app.get("/api/menu")
@auth()
def menu():
    rows = db().execute("""SELECT m.*, ROUND(AVG(r.stars),1) AS rating FROM menu m
                           LEFT JOIN ratings r ON r.item_id=m.id GROUP BY m.id ORDER BY m.category, m.name""").fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/menu")
@auth("admin")
def add_menu():
    d = request.get_json(silent=True) or {}
    try:
        name, price, stock = d["name"].strip(), float(d["price"]), int(d.get("stock", 0))
        assert name and price >= 0 and stock >= 0
        nu = [float(d.get(k) or 0) for k in ("cal", "protein", "carbs", "fat", "fiber")]
        db().execute("INSERT INTO menu(name,category,price,stock,emoji,cal,protein,carbs,fat,fiber,ingredients) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (name, d.get("category") or "Snacks", price, stock, (d.get("emoji") or "🍽️")[:4], int(nu[0]), *nu[1:], (d.get("ingredients") or "")[:200]))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That food item already exists."), 400
    except (KeyError, ValueError, AssertionError, AttributeError):
        return jsonify(error="Enter a name, a price and a stock number."), 400
    return jsonify(ok=True)

@app.delete("/api/menu/<int:i>")
@auth("admin")
def del_menu(i):
    db().execute("DELETE FROM menu WHERE id=?", (i,))
    db().commit()
    return jsonify(ok=True)

MERCHANT = {"vpa": "yourname@ybl", "name": "SmartCanteen"}  # <-- PUT THE CANTEEN'S REAL PHONEPE / UPI ID HERE

def release_stale():
    """A PhonePe order that is not confirmed within 15 minutes is cancelled and its stock returned."""
    cut = (dt.datetime.now() - dt.timedelta(minutes=15)).isoformat(timespec="seconds")
    for o in db().execute("SELECT id,item_id,qty FROM orders WHERE status='pending' AND created<?", (cut,)).fetchall():
        db().execute("UPDATE menu SET stock=stock+? WHERE id=?", (o["qty"], o["item_id"]))
        db().execute("UPDATE orders SET status='cancelled' WHERE id=?", (o["id"],))
    db().commit()

@app.post("/api/orders")
@auth("student")
def order():
    """Creates an order after the payment choice. Online payment is confirmed by the student's UTR;
    for automatic verification use a real gateway (Razorpay / PhonePe PG)."""
    release_stale()
    d = request.get_json(silent=True) or {}
    try:
        qty = int(d.get("qty", 1))
        assert 1 <= qty <= 10
    except (ValueError, AssertionError):
        return jsonify(error="Choose a quantity between 1 and 10."), 400
    method = d.get("method")
    if method not in ("cash", "phonepe"):
        return jsonify(error="Choose a payment method."), 400
    it = db().execute("SELECT * FROM menu WHERE id=?", (d.get("item_id"),)).fetchone()
    if not it:
        return jsonify(error="Item not found."), 404
    if it["stock"] < qty:
        return jsonify(error=f"Only {it['stock']} left of {it['name']}."), 400
    status, txn = ("pending", "") if method == "phonepe" else ("unpaid", "")
    db().execute("UPDATE menu SET stock=stock-? WHERE id=?", (qty, it["id"]))
    cur = db().execute("INSERT INTO orders(user_id,item_id,qty,total,created,method,status,txn) VALUES(?,?,?,?,?,?,?,?)",
                       (g.user["id"], it["id"], qty, qty * it["price"], now(), method, status, txn))
    if method == "cash":  # PhonePe orders are added to the sales history once payment is confirmed
        db().execute("INSERT INTO history(date,item,qty,price) VALUES(?,?,?,?)",
                     (dt.date.today().isoformat(), it["name"], qty, it["price"]))
    db().commit()
    res = dict(ok=True, id=cur.lastrowid, total=qty * it["price"], status=status, txn=txn)
    if method == "phonepe":
        res["pay"] = dict(vpa=MERCHANT["vpa"], name=MERCHANT["name"], note=f"SmartCanteen order {cur.lastrowid}")
    return jsonify(res)

@app.post("/api/orders/<int:i>/confirm")
@auth("student")
def confirm_order(i):
    """Student enters the 12-digit UTR shown in PhonePe; admin can match it with the bank statement."""
    utr = re.sub(r"\s", "", (request.get_json(silent=True) or {}).get("utr", ""))
    if not re.fullmatch(r"\d{12}", utr):
        return jsonify(error="Enter the 12-digit UTR (reference number) shown in PhonePe."), 400
    if db().execute("SELECT 1 FROM orders WHERE txn=?", (utr,)).fetchone():
        return jsonify(error="This reference number was already used."), 400
    o = db().execute("""SELECT o.id, o.qty, o.total, m.name, m.price FROM orders o JOIN menu m ON m.id=o.item_id
                        WHERE o.id=? AND o.user_id=? AND o.status='pending'""", (i, g.user["id"])).fetchone()
    if not o:
        return jsonify(error="No pending order found. It may have expired."), 404
    db().execute("UPDATE orders SET status='paid', txn=? WHERE id=?", (utr, i))
    db().execute("INSERT INTO history(date,item,qty,price) VALUES(?,?,?,?)",
                 (dt.date.today().isoformat(), o["name"], o["qty"], o["price"]))
    db().commit()
    return jsonify(ok=True, id=i, total=o["total"], status="paid", txn=utr)

@app.post("/api/orders/<int:i>/cancel")
@auth("student")
def cancel_order(i):
    o = db().execute("SELECT item_id, qty FROM orders WHERE id=? AND user_id=? AND status='pending'", (i, g.user["id"])).fetchone()
    if not o:
        return jsonify(error="No pending order found."), 404
    db().execute("UPDATE menu SET stock=stock+? WHERE id=?", (o["qty"], o["item_id"]))
    db().execute("UPDATE orders SET status='cancelled' WHERE id=?", (i,))
    db().commit()
    return jsonify(ok=True)

@app.get("/api/orders")
@auth("student")
def my_orders():
    rows = db().execute("""SELECT o.id, o.item_id, m.name, o.qty, o.total, o.created, o.method, o.status, o.txn FROM orders o
                           JOIN menu m ON m.id=o.item_id WHERE o.user_id=? ORDER BY o.id DESC LIMIT 30""",
                        (g.user["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.get("/api/admin/orders")
@auth("admin")
def admin_orders():
    rows = db().execute("""SELECT o.id, m.name item, u.name student, o.qty, o.total, o.method, o.status, o.txn, o.created
                           FROM orders o JOIN menu m ON m.id=o.item_id JOIN users u ON u.id=o.user_id ORDER BY o.id DESC LIMIT 50""").fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/admin/orders/<int:i>/paid")
@auth("admin")
def mark_paid(i):
    db().execute("UPDATE orders SET status='paid' WHERE id=? AND method='cash'", (i,))
    db().commit()
    return jsonify(ok=True)

@app.get("/api/public/menu")
def public_menu():
    rows = db().execute("""SELECT id,name,category,price,stock,emoji,cal,protein,carbs,fat,fiber,
                           ingredients,image FROM menu ORDER BY id""").fetchall()
    return jsonify([dict(r) for r in rows])

ITEM_Q = """SELECT m.id,m.name,m.category,m.price,m.stock,m.emoji,m.cal,m.protein,m.carbs,m.fat,m.fiber,
            m.ingredients,m.image, ROUND(AVG(r.stars),1) AS rating
            FROM menu m LEFT JOIN ratings r ON r.item_id=m.id WHERE m.id=? GROUP BY m.id"""

@app.get("/api/public/menu/<int:i>")
def public_item(i):
    r = db().execute(ITEM_Q, (i,)).fetchone()
    if not r:
        return jsonify(error="Item not found."), 404
    return jsonify(dict(r))

@app.get("/api/server-info")
def server_info():
    """Admin page uses this to build QR links with the Wi-Fi IP (not localhost)."""
    return jsonify(base=f"http://{lan_ip()}:5000")

ITEM_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ r.name }}</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#f6f7fb;color:#1f2430}
.card{max-width:420px;margin:0 auto;background:#fff;min-height:100vh;padding:20px;box-sizing:border-box}
img{width:100%;height:210px;object-fit:cover;border-radius:14px}
.emoji{font-size:64px;text-align:center}
h1{margin:12px 0 2px}.sub{color:#6b7280}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:18px 0}
.n{background:#f1f3f9;border-radius:12px;padding:12px;text-align:center}
.n b{display:block;font-size:22px}.n span{font-size:12px;color:#6b7280}
.cal{grid-column:span 2;background:#fff3e6}
</style></head><body><div class="card">
{% if r.image %}<img src="{{ r.image }}" alt="" onerror="this.style.display='none'">{% else %}<div class="emoji">{{ r.emoji }}</div>{% endif %}
<h1>{{ r.emoji }} {{ r.name }}</h1>
<div class="sub">{{ r.category }}{% if r.rating %} · ⭐ {{ r.rating }}{% endif %}</div>
<div class="grid">
  <div class="n"><b>₹{{ '%g' % r.price }}</b><span>Price</span></div>
  <div class="n"><b style="color:{{ '#0e5a52' if r.stock > 0 else '#b3261e' }}">{{ 'Available' if r.stock > 0 else 'Sold out' }}</b><span>{{ r.stock ~ ' left' if r.stock > 0 else 'Not in stock' }}</span></div>
  <div class="n cal"><b>{{ r.cal }} kcal</b><span>Calories</span></div>
  <div class="n"><b>{{ '%g' % r.protein }} g</b><span>Protein</span></div>
  <div class="n"><b>{{ '%g' % r.carbs }} g</b><span>Carbs</span></div>
  <div class="n"><b>{{ '%g' % r.fat }} g</b><span>Fat</span></div>
  <div class="n"><b>{{ '%g' % r.fiber }} g</b><span>Fiber</span></div>
</div>
{% if r.ingredients %}<h3>Ingredients</h3><p>{{ r.ingredients }}</p>{% endif %}
<p style="text-align:center;font-weight:700;padding:12px;border-radius:12px;background:{{ '#dcefe9' if r.stock > 0 else '#fde4e1' }};color:{{ '#0e5a52' if r.stock > 0 else '#b3261e' }}">{{ 'Available · ' ~ r.stock ~ ' left' if r.stock > 0 else 'Currently sold out' }}</p>
</div></body></html>"""

@app.get("/item/<int:i>")
def item_page(i):
    r = db().execute(ITEM_Q, (i,)).fetchone()
    if not r:
        return "Item not found.", 404
    return render_template_string(ITEM_PAGE, r=r)

QR_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Menu QR codes</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<style>
body{font-family:system-ui,sans-serif;margin:0;padding:20px;background:#f6f7fb;color:#1f2430}
h1{margin:0 0 4px}.sub{color:#6b7280;margin-bottom:18px}
.wrap{display:flex;flex-wrap:wrap;gap:16px}
.c{background:#fff;border-radius:14px;padding:16px;text-align:center;width:200px}
.c b{display:block;margin-top:10px}
.qr{display:flex;justify-content:center}
</style></head><body>
<h1>Scan to see nutrition</h1>
<div class="sub">Scanning shows price, calories, protein, carbs, fat, fiber and availability directly (no Wi-Fi needed). Stock is as of printing.</div>
<div class="wrap" id="wrap"></div>
<script>
var DATA = {{ items|tojson }};
var wrap = document.getElementById('wrap');
DATA.forEach(function(it){
  var card = document.createElement('div'); card.className = 'c';
  var q = document.createElement('div'); q.className = 'qr';
  var t = document.createElement('b'); t.textContent = it.name;
  card.appendChild(q); card.appendChild(t); wrap.appendChild(card);
  new QRCode(q, {text: it.text, width: 200, height: 200, correctLevel: QRCode.CorrectLevel.L});
});
</script></body></html>"""

def qr_items():
    """Plain ASCII text for every dish: Google Lens shows it directly, and the in-app scanner reads the SC-id line."""
    rows = db().execute("SELECT id,name,category,price,stock,cal,protein,carbs,fat,fiber,ingredients FROM menu ORDER BY id").fetchall()
    items = []
    for r in rows:
        avail = f"Available ({r['stock']} left)" if r["stock"] > 0 else "Sold out"
        text = (f"{r['name']} ({r['category']}) - Rs {r['price']:g}\n"
                f"Availability: {avail}\n"
                f"Protein: {r['protein']:g} g\nFat: {r['fat']:g} g\nCarbs: {r['carbs']:g} g\n"
                f"Fiber: {r['fiber']:g} g\nCalories: {r['cal']} kcal")
        if r["ingredients"]:
            text += f"\nIngredients: {r['ingredients']}"
        text += f"\nSC-{r['id']}"
        items.append(dict(id=r["id"], name=r["name"], text=text))
    return items

@app.get("/qr")
def qr_page():
    return render_template_string(QR_PAGE, items=qr_items())

@app.get("/api/qr-data")
@auth("admin")
def qr_data():
    """Admin QR codes page reads the QR text from here, so it always matches the database."""
    return jsonify(items=qr_items())

@app.post("/api/menu/<int:i>/image")
@auth("admin")
def menu_image(i):
    m = re.match(r"data:image/(jpeg|png|webp);base64,(.+)$", (request.get_json(silent=True) or {}).get("data", ""), re.S)
    try:
        raw = base64.b64decode(m.group(2)) if m else b""
    except ValueError:
        raw = b""
    if not raw or len(raw) > 2_000_000:
        return jsonify(error="Upload a JPG, PNG or WebP photo under 2 MB."), 400
    folder = os.path.join(app.root_path, "static", "img")
    os.makedirs(folder, exist_ok=True)
    ext = "jpg" if m.group(1) == "jpeg" else m.group(1)
    with open(os.path.join(folder, f"{i}.{ext}"), "wb") as f:
        f.write(raw)
    db().execute("UPDATE menu SET image=? WHERE id=?", (f"/img/{i}.{ext}?v={int(time.time())}", i))
    db().commit()
    return jsonify(ok=True)

@app.post("/api/ratings")
@auth("student")
def rate():
    d = request.get_json(silent=True) or {}
    try:
        stars = int(d["stars"])
        assert 1 <= stars <= 5
        db().execute("INSERT INTO ratings(user_id,item_id,stars,comment,created) VALUES(?,?,?,?,?)",
                     (g.user["id"], int(d["item_id"]), stars, (d.get("comment") or "")[:300], now()))
        db().commit()
    except (KeyError, ValueError, AssertionError):
        return jsonify(error="Pick 1 to 5 stars."), 400
    return jsonify(ok=True)

@app.get("/api/feedback")
@auth("admin")
def feedback():
    rows = db().execute("""SELECT m.name item, r.stars, r.comment, r.created, u.name student FROM ratings r
                           JOIN menu m ON m.id=r.item_id JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT 50""").fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/upload")
@auth("admin")
def upload():
    text = (request.get_json(silent=True) or {}).get("csv", "").lstrip("\ufeff")
    rd = csv.DictReader(io.StringIO(text))
    ok = bad = 0
    for r in rd:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        try:
            day = dt.date.fromisoformat(r["date"])
            item, qty = r.get("food item") or r["item"], int(float(r.get("quantity sold") or r["qty"]))
            price = float(r.get("price") or 0)
            assert item and qty >= 0
            db().execute("INSERT INTO history(date,item,qty,price) VALUES(?,?,?,?)", (day.isoformat(), item, qty, price))
            ok += 1
        except (KeyError, ValueError, AssertionError):
            bad += 1
    db().commit()
    return jsonify(imported=ok, skipped=bad)

def fit(y):
    """Least-squares line y = a + b*t (pure Python, no libraries)."""
    n = len(y); mx = (n - 1) / 2; my = sum(y) / n
    b = sum((i - mx) * (v - my) for i, v in enumerate(y)) / (sum((i - mx) ** 2 for i in range(n)) or 1)
    return my - b * mx, b

def forecast(safety=10):
    """Demand model: linear trend x weekday seasonality. Confidence = 100 - in-sample MAPE."""
    target = dt.date.today() + dt.timedelta(days=1)
    out = []
    for m in db().execute("SELECT * FROM menu").fetchall():
        days = db().execute("SELECT date, SUM(qty) q FROM history WHERE item=? GROUP BY date ORDER BY date",
                            (m["name"],)).fetchall()
        if len(days) < 7:
            out.append(dict(id=m["id"], name=m["name"], predicted=0, prepare=0, confidence=0, stock=m["stock"]))
            continue
        ds = [dt.date.fromisoformat(d["date"]).weekday() for d in days]
        qs = [d["q"] for d in days]
        mean = sum(qs) / len(qs)
        season = {}
        for w in range(7):
            v = [q for q, x in zip(qs, ds) if x == w]
            season[w] = min(1.6, max(0.5, (sum(v) / len(v)) / mean)) if v else 1
        flat = [q / season[x] for q, x in zip(qs, ds)][-28:]
        a, b = fit(flat)
        pred = max(0, round((a + b * len(flat)) * season[target.weekday()]))
        errs = [abs(q - (a + b * i) * season[x]) / max(q, 1) for i, (q, x) in enumerate(zip(qs[-28:], ds[-28:]))]
        out.append(dict(id=m["id"], name=m["name"], predicted=pred, prepare=math.ceil(pred * (1 + safety / 100)),
                        confidence=max(50, min(97, round(100 - 100 * sum(errs) / len(errs)))), stock=m["stock"]))
    return sorted(out, key=lambda x: -x["predicted"]), target.isoformat()

@app.get("/api/predict")
@auth("admin")
def predict():
    res, day = forecast()
    return jsonify(date=day, items=res)

@app.post("/api/predict/apply")
@auth("admin")
def apply_predict():
    res, _ = forecast()
    for r in res:
        db().execute("UPDATE menu SET stock=? WHERE id=?", (r["prepare"], r["id"]))
    db().commit()
    return jsonify(ok=True)

@app.get("/api/stats")
@auth("admin")
def stats():
    today = dt.date.today().isoformat()
    o = db().execute("SELECT COUNT(*) n, COALESCE(SUM(total),0) s FROM orders WHERE created LIKE ?", (today + "%",)).fetchone()
    st = db().execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
    res, _ = forecast()
    return jsonify(orders=o["n"], sales=o["s"], students=st, predicted=sum(r["predicted"] for r in res))

@app.get("/api/analytics")
@auth("admin")
def analytics():
    daily = db().execute("SELECT date, SUM(qty) q, SUM(qty*price) rev FROM history GROUP BY date ORDER BY date DESC LIMIT 56").fetchall()
    cat = db().execute("""SELECT COALESCE(m.category,'Other') c, SUM(h.qty*h.price) rev FROM history h
                          LEFT JOIN menu m ON m.name=h.item GROUP BY c""").fetchall()
    wd = {i: [] for i in range(7)}
    for d in daily:
        wd[dt.date.fromisoformat(d["date"]).weekday()].append(d["q"])
    return jsonify(daily=[dict(d) for d in daily[:14]][::-1], categories=[dict(c) for c in cat],
                   weekday=[round(sum(v) / len(v)) if v else 0 for v in wd.values()])

@app.get("/api/export")
@auth("admin")
def export():
    """Flat table for Power BI: Get Data -> Text/CSV."""
    rows = db().execute("""SELECT h.date, h.item, COALESCE(m.category,'Other') category, h.qty, h.price, h.qty*h.price revenue
                           FROM history h LEFT JOIN menu m ON m.name=h.item ORDER BY h.date""").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Food Item", "Category", "Quantity", "Price", "Revenue", "Weekday"])
    for r in rows:
        w.writerow([*tuple(r), dt.date.fromisoformat(r["date"]).strftime("%A")])
    return app.response_class(out.getvalue(), mimetype="text/csv",
                              headers={"Content-Disposition": "attachment; filename=smartcanteen_powerbi.csv"})

def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no data is sent; this only finds the Wi-Fi address of this computer
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

if __name__ == "__main__":
    init_db()
    print(f"\n  Laptop : http://localhost:5000\n  Phone  : http://{lan_ip()}:5000   (phone and laptop must be on the same Wi-Fi)\n")
    app.run(host="0.0.0.0", port=5000, debug=False)  # 0.0.0.0 lets your phone connect