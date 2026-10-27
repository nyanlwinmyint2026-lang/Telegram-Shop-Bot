import os
import psycopg2
import asyncio
import requests
from datetime import datetime
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- CONFIGURATIONS ---
TELEGRAM_BOT_TOKEN = "8969723597:AAFaDiVSxy6TTNipwMWm5hUs2v_YEkrKBmM"
ADMIN_USER_ID = 6069279282
DATABASE_URL = "postgresql://neondb_owner:npg_Xv5HWOA4hxPV@ep-long-dew-b4z0dkg4-pooler.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
CHANNEL_USERNAME = "@MSTGAMESHOP"
BOT_LINK = "https://t.me/MSTCODESHOPBOT"

# G2Bulk API Key
G2BULK_API_KEY = "g2b_2de2af3455055d7a975ffd6fceadce2b42b0c4458a369ff7e69fb02bee134fa3"

# Smile One Coin Rates (Name, Coins, Product_ID)
SMILE_RATES = {
    "passes": [
        ("Weekly Pass", 76, "mlbb_weekly_pass"),
        ("Twilight Pass", 402.5, "mlbb_twilight_pass"),
        ("Weekly Elite Package", 39, "mlbb_weekly_elite"),
        ("Monthly Epic Package", 196.5, "mlbb_monthly_epic")
    ],
    "bonus_dia": [
        ("50+50 Dia", 39, "mlbb_50_50"),
        ("150+150 Dia", 116.9, "mlbb_150_150"),
        ("250+250 Dia", 187.5, "mlbb_250_250"),
        ("500+500 Dia", 385, "mlbb_500_500")
    ],
    "normal_dia": [
        ("78+8 Dia", 61.5, "mlbb_78_8"),
        ("156+16 Dia", 122, "mlbb_156_16"),
        ("234+23 Dia", 177.5, "mlbb_234_23"),
        ("625+81 Dia", 480, "mlbb_625_81"),
        ("1860+335 Dia", 1453, "mlbb_1860_335"),
        ("3099+589 Dia", 2424, "mlbb_3099_589"),
        ("4649+883 Dia", 3660, "mlbb_4649_883"),
        ("7740+1548 Dia", 6079, "mlbb_7740_1548")
    ]
}

def round_to_50(amount):
    return int(round(amount / 50.0)) * 50

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, is_banned BOOLEAN DEFAULT FALSE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT, price INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock (id SERIAL PRIMARY KEY, product_id TEXT, code TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT, details TEXT, total_price INTEGER, status TEXT, date TEXT, monthly_id INTEGER, file_unique_ids TEXT)''')
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_date ON orders(user_id, date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_product_id ON stock(product_id)")
    
    try: cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE"); conn.commit()
    except: conn.rollback()
    try: cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS monthly_id INTEGER"); conn.commit()
    except: conn.rollback()
    try: cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS file_unique_ids TEXT"); conn.commit()
    except: conn.rollback()
        
    cursor.execute("UPDATE orders SET monthly_id = id WHERE monthly_id IS NULL")
    
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('300_code', '300 Code (300 Coins)', 27400) ON CONFLICT (id) DO NOTHING")
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('1k_code', '1k Code (1000 Coins)', 91500) ON CONFLICT (id) DO NOTHING")
    
    for category in SMILE_RATES.values():
        for name, coins, pid in category:
            is_dia = "Dia" in name
            prefix = "💎" if is_dia else "🎟️"
            full_name = f"{prefix} {name}"
            cursor.execute("INSERT INTO products (id, name, price) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING", (pid, full_name, 0))
    
    cursor.execute("INSERT INTO settings (key, value) VALUES ('payment_info', '<code>09400477963</code>\\nKpay/Wave နှစ်ခုလုံးရပါတယ်') ON CONFLICT (key) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('shop_status', 'open') ON CONFLICT (key) DO NOTHING")
    
    conn.commit()
    conn.close()

init_db()

# --- Memory tracking ---
user_carts = {}
admin_states = {}
user_states = {}
media_groups = defaultdict(list)
media_group_tasks = {}

def is_user_banned(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id=%s", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res and res[0]

def is_shop_open():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='shop_status'")
    res = cursor.fetchone()
    conn.close()
    return res[0] == 'open' if res else True

def get_main_keyboard(user_id):
    keyboard = [
        [KeyboardButton("🛍️ ဝယ်ယူမည် (Products)"), KeyboardButton("🔍 ML Acc Region စစ်မယ်")],
        [KeyboardButton("🧮 Smile Coin ဈေးတွက်မယ်"), KeyboardButton("👤 ကျွန်ုပ်၏ အကောင့်")]
    ]
    if user_id == ADMIN_USER_ID:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def check_ban_and_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return True
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        if update.callback_query: await update.callback_query.answer("🚫 သင့်အကောင့်အား ပိတ်ပင်ထားပါသည်။", show_alert=True)
        else: await update.effective_message.reply_text("🚫 <b>သင့်အကောင့်သည် စည်းကမ်းဖောက်ဖျက်မှုကြောင့် ပိတ်ပင်ခံထားရပါသည်။</b>", parse_mode="HTML")
        return True
    if not is_shop_open() and user_id != ADMIN_USER_ID:
        msg = "🌙 <b>ယခုအချိန်တွင် ဆိုင်ပိတ်ထားပါသဖြင့် နောက်မှ ပြန်လည်ဝယ်ယူပေးပါခင်ဗျာ။</b>"
        if update.callback_query: await update.callback_query.answer("ဆိုင်ပိတ်ထားပါသည်", show_alert=True)
        else: await update.effective_message.reply_text(msg, parse_mode="HTML")
        return True
    return False

# --- Hybrid MLBB Checker ---
def verify_mlbb_account(uid, server):
    try:
        url = f"https://yanjiestore.com/submitt.php?ID={uid}&server={server}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if res.status_code == 200:
            try:
                data = res.json()
                name = data.get("name") or data.get("username") or data.get("nickname") or data.get("result", {}).get("username")
                region = data.get("region") or data.get("country") or data.get("result", {}).get("region")
                if name: return True, name, region or "Global"
            except: pass
    except: pass

    try:
        headers = {"X-API-Key": G2BULK_API_KEY, "Content-Type": "application/json"}
        g2_url = "https://api.g2bulk.com/v1/games/checkPlayerId"
        payload = {"game": "mlbb", "user_id": str(uid), "server_id": str(server)}
        res = requests.post(g2_url, headers=headers, json=payload, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data.get("valid") == "valid" and data.get("name"):
                return True, data.get("name"), "Global / Verified"
    except: pass
    return False, None, None

# --- Category Menu for Cart ---
async def show_buy_categories_menu(context, chat_id, message_id=None):
    text = "🛍️ <b>ဝယ်ယူလိုသော အမျိုးအစားကို ရွေးချယ်ပါ:</b>"
    keyboard = [
        [InlineKeyboardButton("🎟️ Smile One Code ဝယ်မည်", callback_data="cat|Codes")],
        [InlineKeyboardButton("💎 MLBB Diamond & Pass ဝယ်မည်", callback_data="cat|MLBB")]
    ]
    if message_id:
        try: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except: pass
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# --- Cart Selector (Bug Fixed) ---
async def show_cart_selector(context, chat_id, user_id, message_id=None, page=1, cat_type="Codes"):
    if user_id not in user_carts: user_carts[user_id] = {}
    conn = get_db()
    cursor = conn.cursor()
    
    ITEMS_PER_PAGE = 8
    offset = (page - 1) * ITEMS_PER_PAGE
    
    if cat_type == "Codes":
        cursor.execute("SELECT COUNT(*) FROM products WHERE id NOT LIKE %s", ('mlbb_%',))
        total_products = cursor.fetchone()[0]
        cursor.execute("SELECT id, name, price FROM products WHERE id NOT LIKE %s ORDER BY price ASC LIMIT %s OFFSET %s", ('mlbb_%', ITEMS_PER_PAGE, offset))
        header_text = f"🛒 <b>Smile One Codes (စာမျက်နှာ {page}):</b>\n\n"
    else:
        cursor.execute("SELECT COUNT(*) FROM products WHERE id LIKE %s", ('mlbb_%',))
        total_products = cursor.fetchone()[0]
        cursor.execute("SELECT id, name, price FROM products WHERE id LIKE %s ORDER BY id ASC LIMIT %s OFFSET %s", ('mlbb_%', ITEMS_PER_PAGE, offset))
        header_text = f"💎 <b>MLBB Diamonds & Passes (စာမျက်နှာ {page}):</b>\n\n"

    total_pages = (total_products + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if total_pages == 0: total_pages = 1
    products = cursor.fetchall()

    total_amount = 0
    total_items = 0
    
    for cart_pid, qty in user_carts[user_id].items():
        if qty > 0:
            cursor.execute("SELECT price FROM products WHERE id=%s", (cart_pid,))
            res = cursor.fetchone()
            if res:
                total_amount += res[0] * qty
                total_items += qty

    keyboard = []
    text = header_text

    for p in products:
        p_id, p_name, p_price = p
        
        is_mlbb = str(p_id).startswith("mlbb_")
        if is_mlbb:
            stock_count = 99999
            stock_badge = ""
        else:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (p_id,))
            stock_count = cursor.fetchone()[0]
            stock_badge = f"(✅ Stock: {stock_count})" if stock_count > 0 else "(❌ Out of Stock)"

        current_qty = user_carts[user_id].get(p_id, 0)
        if current_qty > stock_count: current_qty = stock_count
        user_carts[user_id][p_id] = current_qty
        item_total = current_qty * p_price

        text += f"🔹 <b>{p_name}</b> {stock_badge}\n   💵 စျေးနှုန်း: <b>{p_price:,}</b> MMK\n   📦 ရွေးထားသည်: <b>{current_qty}</b> ခု = <b>{item_total:,}</b> MMK\n\n"
        
        keyboard.append([InlineKeyboardButton(f"🟦 {p_name} ({p_price:,} MMK)", callback_data="noop")])
        keyboard.append([
            InlineKeyboardButton("➖ 1", callback_data=f"m|{p_id}|-1|{page}|{cat_type}"),
            InlineKeyboardButton(f"🔢 {current_qty} ခု", callback_data="noop"),
            InlineKeyboardButton("➕ 1", callback_data=f"m|{p_id}|1|{page}|{cat_type}")
        ])

    conn.close()

    text += f"━━━━━━━━━━━━━━━━━━\n💰 <b>စုစုပေါင်း ကျသင့်ငွေ: {total_amount:,} MMK</b> ({total_items} ခု)"
    
    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton("⬅️ ယခင်", callback_data=f"page|{page-1}|{cat_type}"))
    if page < total_pages: nav_row.append(InlineKeyboardButton("နောက်သို့ ➡️", callback_data=f"page|{page+1}|{cat_type}"))
    if nav_row: keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🔙 အမျိုးအစား ပြန်ရွေးမည်", callback_data="open_categories")])

    action_row = []
    if total_amount > 0: action_row.append(InlineKeyboardButton(f"🟩 ငွေရှင်းမည် ({total_amount:,} MMK)", callback_data="checkout_cart"))
    action_row.append(InlineKeyboardButton("🟥 မဝယ်တော့ပါ", callback_data="cancel_cart"))
    keyboard.append(action_row)

    if message_id:
        try: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except: pass
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban_and_shop(update, context): return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    context.user_data["username"] = update.effective_user.username
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
    conn.commit()
    conn.close()
    
    if context.args and len(context.args) > 0 and context.args[0] == "buy":
        await update.message.reply_text("🛍️ <b>ဝယ်ယူရန် ရောက်ရှိလာပါပြီခင်ဗျာ။</b>", reply_markup=get_main_keyboard(user_id), parse_mode="HTML")
        await show_buy_categories_menu(context, chat_id)
        return
    
    welcome_text = (
        "🌟 <b>MST Game Shop မှ လှိုက်လှဲစွာ ကြိုဆိုပါတယ်။</b> 🌟\n\n"
        "💳 သင့်အတွက် အကောင်းဆုံး Smile One Voucher Code နှင့် MLBB Package များကို အဆင်သင့် ရောင်းချပေးနေပါသည်။\n"
        "👇 အောက်ပါ Menu ခလုတ်များကို အသုံးပြု၍ အလွယ်တကူ ဝယ်ယူနိုင်ပါသည်။"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(user_id))

async def start_calculator_flow(context, chat_id, message_id=None):
    text = "🧮 <b>Smile Coin Reseller ဈေးနှုန်းတွက်ရန်</b>\n\nသင်ဝယ်ယူထားသော Code အမျိုးအစားကို ရွေးချယ်ပါ:"
    keyboard = [
        [InlineKeyboardButton("🎟️ 300 Code (300 Coins)", callback_data="calc_code_300")],
        [InlineKeyboardButton("🎟️ 1k Code (1000 Coins)", callback_data="calc_code_1000")],
        [InlineKeyboardButton("🟥 မတွက်တော့ပါ (Cancel)", callback_data="cancel_calc")]
    ]
    if message_id:
        try: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except: pass
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def show_user_dashboard(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username
    display_uname = f"@{username}" if username else "No_Username"
    current_year = datetime.now().year
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT details, date FROM orders WHERE user_id=%s AND status='accepted' AND date LIKE %s", (user_id, f"{current_year}%"))
    orders = cursor.fetchall()
    conn.close()

    total_orders = len(orders)
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_stats = {m: {"300": 0, "1k": 0, "mlbb": 0} for m in range(1, 13)}

    for details_str, dt_str in orders:
        try: m = int(dt_str[5:7])
        except: continue
        for item in details_str.split(", "):
            if ":" in item:
                parts = item.split(":")
                pid = parts[0]
                try: qty = int(parts[1])
                except: qty = 0
                if pid in ("300_code", "smile_300"): month_stats[m]["300"] += qty
                elif pid in ("1k_code", "smile_1k"): month_stats[m]["1k"] += qty
                elif str(pid).startswith("mlbb_"): month_stats[m]["mlbb"] += qty

    text = (
        f"👤 <b>ဝယ်ယူသူ:</b> {display_uname} (ID: <code>{user_id}</code>)\n"
        f"🛍️ <b>စုစုပေါင်း အောင်မြင်ထားသော Order:</b> {total_orders} ကြိမ်\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>{current_year} ခုနှစ် လအလိုက် ဝယ်ယူမှုမှတ်တမ်း:</b>\n\n"
    )

    for m in range(1, 13):
        m_name = month_names[m-1]
        c300, c1k, cmlbb = month_stats[m]["300"], month_stats[m]["1k"], month_stats[m]["mlbb"]
        text += f"• <b>{m_name} {current_year}</b> : 300(<b>{c300}</b>) | 1k(<b>{c1k}</b>) | MLBB(<b>{cmlbb}</b>) \n"

    await update.message.reply_text(text, parse_mode="HTML")

async def show_admin_panel(context, chat_id, message_id=None):
    shop_status = "🔴 ဆိုင်ပိတ်မည် (Close)" if is_shop_open() else "🟢 ဆိုင်ဖွင့်မည် (Open)"
    keyboard = [
        [InlineKeyboardButton("💎 MLBB Bulk Update (အစုလိုက် ဈေးပြင်ရန်)", callback_data="admin_bulk_start")],
        [InlineKeyboardButton("📦 Stock စာရင်းနှင့် Code စီမံရန်", callback_data="manage_stock_menu")],
        [InlineKeyboardButton("🟨 ဈေးပြင်ရန် (Manual)", callback_data="manage_price"), InlineKeyboardButton("🏦 Payment Info", callback_data="manage_payment")],
        [InlineKeyboardButton("📈 အမြတ်ငွေစာရင်း", callback_data="profit_report"), InlineKeyboardButton("📊 ယနေ့ အရောင်း", callback_data="admin_sales")],
        [InlineKeyboardButton("🏆 Top Buyers (10 ဦး)", callback_data="top_buyers"), InlineKeyboardButton("📝 Channel သို့ Post", callback_data="admin_post_channel")],
        [InlineKeyboardButton("📢 Broadcast ပို့ရန်", callback_data="admin_broadcast"), InlineKeyboardButton(shop_status, callback_data="toggle_shop_status")],
        [InlineKeyboardButton("🚫 Banned Users", callback_data="view_banned")]
    ]
    text = "👑 <b>Admin Management Panel</b>\n\nလုပ်ဆောင်လိုသော အရာကို ရွေးချယ်ပါ:"
    if message_id: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else: await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def process_checkout(context, chat_id, user_id, msg_id=None, player_id_input=None):
    if user_id not in user_carts or not any(user_carts.get(user_id, {}).values()):
        if msg_id:
            try: await context.bot.edit_message_text("အရေအတွက် ရွေးချယ်ပေးပါ။", chat_id=chat_id, message_id=msg_id)
            except: pass
        return

    conn = get_db()
    cursor = conn.cursor()
    total_price = 0
    cart_text = "🛒 <b>သင့်ရဲ့ Order စာရင်း:</b>\n\n"
    details = []

    for pid, qty in list(user_carts[user_id].items()):
        if qty <= 0: continue
        cursor.execute("SELECT name, price FROM products WHERE id=%s", (pid,))
        prod = cursor.fetchone()
        if not prod: continue
        
        is_mlbb = str(pid).startswith("mlbb_")
        if not is_mlbb:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (pid,))
            stock_count = cursor.fetchone()[0]
            if qty > stock_count:
                msg = f"⚠️ {prod[0]} Stock မလောက်တော့ပါ။"
                if msg_id: await context.bot.edit_message_text(msg, chat_id=chat_id, message_id=msg_id)
                else: await context.bot.send_message(chat_id, msg)
                conn.close()
                return

        price = prod[1] * qty
        total_price += price
        cart_text += f"🔹 <b>{prod[0]}</b> ( {qty} ) ခု = {price:,} MMK\n"
        details.append(f"{pid}:{qty}")

    if player_id_input:
        cart_text += f"\n🎮 <b>Player ID Info:</b> <code>{player_id_input}</code>\n"
        details_str = ", ".join(details) + f" | UID: {player_id_input}"
    else:
        details_str = ", ".join(details)

    cart_text += f"\n💰 <b>စုစုပေါင်း ကျသင့်ငွေ - {total_price:,} MMK</b>\n\n"
    cursor.execute("SELECT value FROM settings WHERE key='payment_info'")
    payment_info = cursor.fetchone()[0]
    cart_text += f"🏦 <b>ငွေလွှဲရမည့် အကောင့်များ:</b>\n{payment_info}\n\n"
    cart_text += "⚠️ <b>အရေးကြီး:</b> ငွေလွှဲပြေစာ (Screenshot) ကို ဤနေရာသို့ တိုက်ရိုက် ပို့ပေးပါ။ <b>(ပုံဟောင်း ပြန်ပို့ပါက အလိုအလျောက် ပယ်ချခံရပါမည်)</b>"

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_month = date_str[:7]
    
    cursor.execute("SELECT COALESCE(MAX(monthly_id), 0) FROM orders WHERE date LIKE %s", (f"{current_month}%",))
    next_monthly_id = cursor.fetchone()[0] + 1
    
    raw_username = context.user_data.get("username")
    save_username = raw_username if raw_username else "No_Username"

    cursor.execute("DELETE FROM orders WHERE user_id=%s AND status='pending'", (user_id,))
    cursor.execute(
        "INSERT INTO orders (user_id, username, details, total_price, status, date, monthly_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (user_id, save_username, details_str, total_price, "pending", date_str, next_monthly_id)
    )
    conn.commit()
    conn.close()
    
    user_carts[user_id] = {} 
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_cart")]])
    
    if msg_id:
        await context.bot.edit_message_text(cart_text, chat_id=chat_id, message_id=msg_id, parse_mode="HTML", reply_markup=markup)
    else:
        await context.bot.send_message(chat_id, cart_text, parse_mode="HTML", reply_markup=markup)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message or not update.message.text: return
    user_id = update.effective_user.id
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    context.user_data["username"] = update.effective_user.username

    if user_id in user_states and user_states[user_id] == "waiting_ml_check":
        del user_states[user_id]
        parts = text.replace("(", " ").replace(")", " ").split()
        if len(parts) < 2:
            await update.message.reply_text("⚠️ <b>User ID နှင့် Zone ID ကို ခြားပြီး ရိုက်ထည့်ပေးပါ။</b>\nဥပမာ - <code>12345678 1234</code>", parse_mode="HTML")
            return
        uid, server = parts[0], parts[1]
        wait_msg = await update.message.reply_text("🔍 MLBB Account အား စစ်ဆေးနေပါသည်... ခေတ္တစောင့်ပါ။")
        
        is_valid, name, region = verify_mlbb_account(uid, server)
        if is_valid:
            res_text = (f"✅ <b>MLBB Account အချက်အလက်</b>\n━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 <b>In-game Name:</b> <code>{name}</code>\n"
                        f"🌍 <b>Account Region:</b> <b>{region}</b>\n"
                        f"🆔 <b>Account ID:</b> <code>{uid}</code>\n"
                        f"🌐 <b>Zone/Server:</b> <code>{server}</code>\n━━━━━━━━━━━━━━━━━━━")
            keyboard = [[InlineKeyboardButton("🔍 နောက်တစ်ခု ထပ်စစ်မည်", callback_data="check_ml_acc_btn")]]
            await wait_msg.edit_text(res_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            fail_text = "❌ <b>Account ရှာမတွေ့ပါ!</b>\nUser ID သို့မဟုတ် Zone ID မှားယွင်းနေပါသည်။ ပြန်လည်စမ်းသပ်ပါ။"
            keyboard = [[InlineKeyboardButton("🔄 ပြန်လည်စစ်ဆေးမည်", callback_data="check_ml_acc_btn")]]
            await wait_msg.edit_text(fail_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if user_id in user_states and user_states[user_id] == "waiting_checkout_player_id":
        parts = text.replace("(", " ").replace(")", " ").split()
        if len(parts) < 2:
            await update.message.reply_text("⚠️ <b>User ID နှင့် Zone ID ကို ခြားပြီး ရိုက်ထည့်ပေးပါ။</b>\nဥပမာ - <code>12345678 1234</code>", parse_mode="HTML")
            return
        uid, server = parts[0], parts[1]
        wait_msg = await update.message.reply_text("🔍 MLBB Account အား စစ်ဆေးနေပါသည်... ခေတ္တစောင့်ပါ။")
        
        is_valid, name, region = verify_mlbb_account(uid, server)
        if is_valid:
            user_states[user_id] = {"action": "confirm_checkout_mlbb", "uid": uid, "server": server, "name": name, "region": region}
            res_text = (f"✅ <b>အကောင့်အချက်အလက် စစ်ဆေးပြီးပါပြီ</b>\n━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 <b>Name:</b> <code>{name}</code>\n"
                        f"🌍 <b>Region:</b> <b>{region}</b>\n"
                        f"🆔 <b>ID:</b> <code>{uid} ({server})</code>\n━━━━━━━━━━━━━━━━━━━\n"
                        f"အထက်ပါ အကောင့်အချက်အလက် မှန်ကန်ပါသလား?")
            keyboard = [[InlineKeyboardButton("✅ မှန်ကန်ပါသည် (ဆက်သွားမည်)", callback_data="mlbb_checkout_confirm")],
                        [InlineKeyboardButton("❌ ပြန်ပြင်မည်", callback_data="mlbb_checkout_retry")]]
            await wait_msg.edit_text(res_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            fail_text = "❌ <b>Account ရှာမတွေ့ပါ!</b>\nUser ID သို့မဟုတ် Zone ID မှားယွင်းနေပါသည်။ သေချာစစ်ဆေးပြီး ပြန်လည်ရိုက်ထည့်ပါ။"
            keyboard = [[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_cart")]]
            await wait_msg.edit_text(fail_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if user_id in user_states and user_states[user_id].get("action") == "waiting_calc_price":
        try:
            cost = float(text.replace(",", ""))
            if cost <= 0: raise ValueError
            user_states[user_id]["cost"] = cost
            coins = user_states[user_id]["coins"]
            prompt = (f"📈 <b>အမြတ်တင်လိုသော ရာခိုင်နှုန်း (%) ကို ရွေးချယ်ပါ:</b>\n\n"
                      f"🎟️ Code: <b>{coins} Coins</b>\n"
                      f"💵 ဝယ်ရင်းဈေး: <b>{int(cost):,} MMK</b>\n"
                      f"🪙 1 Coin တန်ဖိုး: <b>{(cost/coins):.2f} MMK</b>")
            keyboard = [
                [InlineKeyboardButton("3% အမြတ်", callback_data="calc_pct_3"), InlineKeyboardButton("4% အမြတ်", callback_data="calc_pct_4"), InlineKeyboardButton("5% အမြတ်", callback_data="calc_pct_5")],
                [InlineKeyboardButton("6% အမြတ်", callback_data="calc_pct_6"), InlineKeyboardButton("7% အမြတ်", callback_data="calc_pct_7")],
                [InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_calc")]
            ]
            await update.message.reply_text(prompt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        except:
            await update.message.reply_text("⚠️ ဈေးနှုန်းကို ဂဏန်းသီးသန့်ဖြင့် မှန်ကန်စွာ ရိုက်ထည့်ပေးပါ။")
            return

    if user_id in user_states and user_states[user_id].get("action") == "waiting_admin_bulk_cost":
        try:
            cost = float(text.replace(",", ""))
            if cost <= 0: raise ValueError
            user_states[user_id]["cost"] = cost
            coins = user_states[user_id]["coins"]
            prompt = (f"📈 <b>အမြတ်တင်လိုသော ရာခိုင်နှုန်း (%) ကို ရွေးချယ်ပါ:</b>\n\n"
                      f"🎟️ အခြေခံ Code: <b>{coins} Coins</b>\n"
                      f"💵 ဝယ်ရင်းဈေး: <b>{int(cost):,} MMK</b>\n")
            keyboard = [
                [InlineKeyboardButton("3%", callback_data="admin_bulk_pct_3"), InlineKeyboardButton("4%", callback_data="admin_bulk_pct_4"), InlineKeyboardButton("5%", callback_data="admin_bulk_pct_5")],
                [InlineKeyboardButton("6%", callback_data="admin_bulk_pct_6"), InlineKeyboardButton("7%", callback_data="admin_bulk_pct_7")],
                [InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]
            ]
            await update.message.reply_text(prompt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        except:
            await update.message.reply_text("⚠️ ဈေးနှုန်းကို ဂဏန်းသီးသန့်ဖြင့် မှန်ကန်စွာ ရိုက်ထည့်ပေးပါ။")
            return

    if text == "👤 ကျွန်ုပ်၏ အကောင့်":
        await show_user_dashboard(update, context)
        return

    elif text == "🔍 ML Acc Region စစ်မယ်":
        if await check_ban_and_shop(update, context): return
        user_states[user_id] = "waiting_ml_check"
        await update.message.reply_text("🔍 <b>Mobile Legends Account & Region စစ်ဆေးရန်</b>\n\nကျေးဇူးပြု၍ သင့်ရဲ့ <b>User ID</b> နှင့် <b>Zone/Server ID</b> ကို ခြားပြီး ရိုက်ထည့်ပေးပါ။\n\n(ဥပမာ - <code>12345678 1234</code>)", parse_mode="HTML")
        return

    elif text == "🧮 Smile Coin ဈေးတွက်မယ်":
        if await check_ban_and_shop(update, context): return
        if user_id in user_states: del user_states[user_id]
        await start_calculator_flow(context, chat_id)
        return

    elif text == "🛍️ ဝယ်ယူမည် (Products)":
        if await check_ban_and_shop(update, context): return
        if user_id in admin_states: del admin_states[user_id]
        if user_id in user_states: del user_states[user_id]
        await show_buy_categories_menu(context, chat_id)
        return

    elif "Admin Panel" in text and user_id == ADMIN_USER_ID:
        if user_id in admin_states: del admin_states[user_id]
        await show_admin_panel(context, chat_id)
        return

    elif user_id in admin_states and user_id == ADMIN_USER_ID:
        state = admin_states[user_id]
        action = state["action"]
        conn = get_db()
        cursor = conn.cursor()
        
        if action == "manual_ban":
            try:
                target_id = int(text)
                cursor.execute("INSERT INTO users (user_id, is_banned) VALUES (%s, TRUE) ON CONFLICT (user_id) DO UPDATE SET is_banned=TRUE", (target_id,))
                conn.commit()
                await update.message.reply_text(f"✅ User ID <code>{target_id}</code> အား အောင်မြင်စွာ Ban လိုက်ပါပြီ။", parse_mode="HTML")
                del admin_states[user_id]
                await show_admin_panel(context, chat_id)
            except:
                await update.message.reply_text("⚠️ User ID ကို ဂဏန်းသီးသန့်ဖြင့်သာ ရိုက်ထည့်ပါ။")

        elif action == "add_code":
            prod_id = state["product_id"]
            codes = text.split('\n')
            added = 0
            for code in codes:
                if code.strip():
                    cursor.execute("INSERT INTO stock (product_id, code) VALUES (%s, %s)", (prod_id, code.strip()))
                    added += 1
            conn.commit()
            await update.message.reply_text(f"✅ Product <code>{prod_id}</code> အတွက် Code အသစ် {added} ခု အောင်မြင်စွာ သွင်းပြီးပါပြီ。", parse_mode="HTML")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        elif action == "set_price":
            try:
                price = int(text)
                cursor.execute("UPDATE products SET price=%s WHERE id=%s", (price, state["product_id"]))
                conn.commit()
                await update.message.reply_text(f"✅ ဈေးနှုန်းကို {price:,} MMK သို့ ပြောင်းလဲလိုက်ပါပြီ။", parse_mode="HTML")
                del admin_states[user_id]
                await show_admin_panel(context, chat_id)
            except:
                await update.message.reply_text("⚠️ ဂဏန်းဖြင့်သာ ရိုက်ထည့်ပါ။")
                
        elif action == "set_payment":
            cursor.execute("UPDATE settings SET value=%s WHERE key='payment_info'", (text,))
            conn.commit()
            await update.message.reply_text("✅ Payment Info ကို ပြောင်းလဲလိုက်ပါပြီ။")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        elif action == "broadcast":
            cursor.execute("SELECT user_id FROM users WHERE is_banned=FALSE")
            users = cursor.fetchall()
            count = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u[0], text=f"📢 <b>ကြေညာချက်:</b>\n\n{text}", parse_mode="HTML")
                    count += 1
                except: pass
            await update.message.reply_text(f"✅ ကြေညာချက် ( {count} ) ဦးထံ ပို့ပြီးပါပြီ။")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        elif action == "post_channel":
            channel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🟩 Code ဝယ်ယူရန် နှိပ်ပါ ↗", url=f"{BOT_LINK}?start=buy")]])
            try:
                await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=text, parse_mode="HTML", reply_markup=channel_btn)
                await update.message.reply_text("✅ Channel သို့ Post တင်ပြီးပါပြီ။ (အောက်တွင် Code တန်းဝယ်နိုင်မည့် ခလုတ် ပါဝင်ပြီး ဖြစ်ပါသည်)")
            except Exception as e:
                await update.message.reply_text(f"⚠️ Channel သို့ တင်ရန် ကျရှုံးပါသည်။ Bot အား Channel Admin ပေးထားခြင်း ရှိ/မရှိ စစ်ဆေးပါ။")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        conn.close()
        return

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not update.effective_user:
        await query.answer()
        return
        
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = query.message.chat.id
    msg_id = query.message.message_id

    conn = get_db()
    cursor = conn.cursor()

    if data == "noop": pass
    elif data == "cancel_cart":
        if user_id in user_carts: del user_carts[user_id]
        if user_id in user_states: del user_states[user_id]
        await query.edit_message_text("❌ ဝယ်ယူမှုကို ပယ်ဖျက်လိုက်ပါပြီ။")
    elif data == "cancel_action":
        if user_id in admin_states: del admin_states[user_id]
        await query.edit_message_text("🚫 လုပ်ဆောင်ချက် ဖျက်သိမ်းလိုက်ပါပြီ။")
        if user_id == ADMIN_USER_ID: await show_admin_panel(context, chat_id)

    elif data == "check_ml_acc_btn":
        user_states[user_id] = "waiting_ml_check"
        await query.edit_message_text("🔍 <b>User ID နှင့် Zone ID ကို ခြားပြီး ရိုက်ထည့်ပေးပါ:</b>\n(ဥပမာ - <code>12345678 1234</code>)", parse_mode="HTML")

    elif data == "mlbb_checkout_retry":
        user_states[user_id] = "waiting_checkout_player_id"
        await query.edit_message_text("✏️ <b>User ID နှင့် Zone ID ကို အောက်တွင် ပြန်လည်ရိုက်ထည့်ပေးပါ:</b>\n(ဥပမာ - <code>12345678 1234</code>)", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_cart")]]))

    elif data == "mlbb_checkout_confirm":
        state = user_states.get(user_id, {})
        if state.get("action") == "confirm_checkout_mlbb":
            full_id = f"{state['uid']} {state['server']} ({state['name']})"
            del user_states[user_id]
            await process_checkout(context, chat_id, user_id, msg_id=msg_id, player_id_input=full_id)
        else:
            await query.answer("Error: အချိန်လွန်သွားပါပြီ။", show_alert=True)

    elif data == "admin_bulk_start" and user_id == ADMIN_USER_ID:
        text = "💎 <b>MLBB ဈေးနှုန်းများ အစုလိုက် ပြင်မည်</b>\n\nတွက်ချက်မည့် အခြေခံ Code ကို ရွေးပါ:"
        keyboard = [
            [InlineKeyboardButton("🎟️ 300 Code အခြေခံ", callback_data="admin_bulk_code_300")],
            [InlineKeyboardButton("🎟️ 1k Code အခြေခံ", callback_data="admin_bulk_code_1000")],
            [InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data in ("admin_bulk_code_300", "admin_bulk_code_1000") and user_id == ADMIN_USER_ID:
        coins = 300 if "300" in data else 1000
        user_states[user_id] = {"action": "waiting_admin_bulk_cost", "coins": coins}
        await query.edit_message_text(f"💵 <b>{coins} Code ဝယ်ရင်းဈေး (MMK) ကို ရိုက်ထည့်ပါ:</b>\n(ဥပမာ - <code>27400</code>)", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data.startswith("admin_bulk_pct_") and user_id == ADMIN_USER_ID:
        pct = int(data.split("_")[3])
        state = user_states.get(user_id, {})
        coins = state.get("coins", 300)
        cost = state.get("cost", 0)

        if cost <= 0:
            await query.edit_message_text("⚠️ အချိန်လွန်သွားပါသဖြင့် ပြန်လည်စတင်ပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin သို့ ပြန်သွားရန်", callback_data="admin_panel")]]))
            return

        coin_cost = cost / coins
        profit_multiplier = 1 + (pct / 100)
        new_prices = {}
        
        preview_text = f"✅ <b>အတည်ပြုရန် - ဈေးနှုန်းပြောင်းလဲမှု စာရင်း (အမြတ် {pct}%)</b>\n━━━━━━━━━━━━━━━━━━\n"
        
        def add_to_bulk(name, c_val, pid, is_dia=False):
            item_sell = round_to_50(round(c_val * coin_cost) * profit_multiplier)
            new_prices[pid] = item_sell
            prefix = "💎 " if is_dia else "• "
            return f"{prefix}{name} = <b>{item_sell:,}</b> Ks\n"
            
        preview_text += "🎟️ <b>Passes & Packages</b>\n"
        for name, c_val, pid in SMILE_RATES["passes"]: preview_text += add_to_bulk(name, c_val, pid, False)
        
        preview_text += "\n💎 <b>Double Diamonds (1+1)</b>\n"
        for name, c_val, pid in SMILE_RATES["bonus_dia"]: preview_text += add_to_bulk(name, c_val, pid, True)
        
        preview_text += "\n💎 <b>Normal Diamonds</b>\n"
        for name, c_val, pid in SMILE_RATES["normal_dia"]: preview_text += add_to_bulk(name, c_val, pid, True)
        
        user_states[user_id]["new_prices"] = new_prices
        user_states[user_id]["action"] = "confirm_admin_bulk"
        
        keyboard = [
            [InlineKeyboardButton("✅ ဤဈေးနှုန်းများအားလုံးကို အတည်ပြုပြောင်းလဲမည်", callback_data="confirm_bulk_update")],
            [InlineKeyboardButton("🟥 မပြောင်းတော့ပါ (Cancel)", callback_data="cancel_action")]
        ]
        await query.edit_message_text(preview_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "confirm_bulk_update" and user_id == ADMIN_USER_ID:
        state = user_states.get(user_id, {})
        if state.get("action") == "confirm_admin_bulk" and "new_prices" in state:
            new_prices = state["new_prices"]
            for pid, price in new_prices.items():
                cursor.execute("UPDATE products SET price=%s WHERE id=%s", (price, pid))
            conn.commit()
            del user_states[user_id]
            await query.edit_message_text("✅ <b>MLBB Product အားလုံး၏ ဈေးနှုန်းများကို တစ်ပြိုင်နက် ပြောင်းလဲသတ်မှတ်ပြီးပါပြီ!</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin သို့ ပြန်သွားရန်", callback_data="admin_panel")]]))
        else:
            await query.answer("Error: အချိန်လွန်သွားပါပြီ။", show_alert=True)

    elif data == "cancel_calc":
        if user_id in user_states: del user_states[user_id]
        await query.edit_message_text("🚫 ဈေးနှုန်းတွက်ချက်မှုကို ပယ်ဖျက်လိုက်ပါပြီ။")

    elif data == "start_calc":
        await start_calculator_flow(context, chat_id, message_id=msg_id)

    elif data in ("calc_code_300", "calc_code_1000"):
        coins = 300 if data == "calc_code_300" else 1000
        user_states[user_id] = {"action": "waiting_calc_price", "coins": coins}
        await query.edit_message_text(
            f"💵 <b>{coins} Code ဝယ်ယူခဲ့သော ဈေးနှုန်း (MMK) ကို အောက်တွင် ရိုက်ထည့်ပေးပါ:</b>\n\n(ဥပမာ - <code>27400</code>)",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_calc")]])
        )

    elif data.startswith("calc_pct_"):
        pct = int(data.split("_")[2])
        state = user_states.get(user_id, {})
        coins = state.get("coins", 300)
        cost = state.get("cost", 0)

        if cost <= 0:
            await query.edit_message_text("⚠️ အချိန်လွန်သွားပါသဖြင့် ပြန်လည်စတင်ပေးပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 အသစ်ပြန်တွက်မည်", callback_data="start_calc")]]))
            return

        user_states[user_id]["pct"] = pct
        coin_cost = cost / coins
        profit_multiplier = 1 + (pct / 100)

        def fmt_row(name, item_coins, is_dia=False):
            item_cost = round(item_coins * coin_cost)
            item_sell = round_to_50(item_cost * profit_multiplier)
            prefix = "💎 " if is_dia else "• "
            return f"{prefix}<b>{name}</b> ({item_coins} Coins)\n  အရင်း: {item_cost:,} Ks | ရောင်း: <b>{item_sell:,} Ks</b>\n"

        calc_text = (
            f"🧮 <b>Smile Coin Reseller ဈေးနှုန်းတွက်ချက်မှု</b>\n\n"
            f"🎟️ Code: <b>{coins} Coins</b>\n"
            f"💵 ဝယ်ရင်းဈေး: <b>{int(cost):,} MMK</b>\n"
            f"🪙 1 Coin တန်ဖိုး: <b>{coin_cost:.2f} MMK</b>\n"
            f"📈 အမြတ်တင်နှုန်း: <b>{pct}%</b> (အနီးစပ်ဆုံး ၅၀ ကျပ်ညှိထားသည်)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎟️ <b>Passes & Packages</b>\n"
        )
        for name, c, pid in SMILE_RATES["passes"]: calc_text += fmt_row(name, c, is_dia=False)
        calc_text += f"\n💎 <b>Double Diamonds (1+1)</b>\n"
        for name, c, pid in SMILE_RATES["bonus_dia"]: calc_text += fmt_row(name, c, is_dia=True)
        calc_text += f"\n💎 <b>Normal Diamonds</b>\n"
        for name, c, pid in SMILE_RATES["normal_dia"]: calc_text += fmt_row(name, c, is_dia=True)
        calc_text += "━━━━━━━━━━━━━━━━━━"

        keyboard = [
            [InlineKeyboardButton("📋 Price List ထုတ်မည်", callback_data="gen_pricelist")],
            [InlineKeyboardButton("🔄 အသစ်ပြန်တွက်မည်", callback_data="start_calc")]
        ]
        await query.edit_message_text(calc_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "gen_pricelist":
        state = user_states.get(user_id, {})
        coins = state.get("coins", 300)
        cost = state.get("cost", 0)
        pct = state.get("pct", 5)

        if cost <= 0:
            await query.edit_message_text("⚠️ အချက်အလက် မရှိတော့ပါ။ ပြန်လည်စတင်ပေးပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 အသစ်ပြန်တွက်မည်", callback_data="start_calc")]]))
            return

        coin_cost = cost / coins
        profit_multiplier = 1 + (pct / 100)

        plist_text = f"✨ <b>MLBB DIAMOND PRICE LIST</b> ✨\n━━━━━━━━━━━━━━━━━━━\n\n🎟️ <b>Passes & Packages</b>\n"
        for name, c, pid in SMILE_RATES["passes"]:
            sell_price = round_to_50(round(c * coin_cost) * profit_multiplier)
            plist_text += f"• {name} — <b>{sell_price:,} MMK</b>\n"

        plist_text += f"\n💎 <b>Double Diamonds (1+1)</b>\n"
        for name, c, pid in SMILE_RATES["bonus_dia"]:
            sell_price = round_to_50(round(c * coin_cost) * profit_multiplier)
            plist_text += f"• 💎 {name} — <b>{sell_price:,} MMK</b>\n"

        plist_text += f"\n💎 <b>Normal Diamonds</b>\n"
        for name, c, pid in SMILE_RATES["normal_dia"]:
            sell_price = round_to_50(round(c * coin_cost) * profit_multiplier)
            plist_text += f"• 💎 {name} — <b>{sell_price:,} MMK</b>\n"

        plist_text += f"\n━━━━━━━━━━━━━━━━━━━\n⚡ <i>အမြန်ဆုံး ဝန်ဆောင်မှုဖြင့် ယုံကြည်စိတ်ချစွာ ဝယ်ယူနိုင်ပါသည်။</i>"

        keyboard = [
            [InlineKeyboardButton("🔙 တွက်ချက်မှုသို့ ပြန်သွားရန်", callback_data=f"calc_pct_{pct}")],
            [InlineKeyboardButton("🔄 အသစ်ပြန်တွက်မည်", callback_data="start_calc")]
        ]
        await query.edit_message_text(plist_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "open_categories":
        await show_buy_categories_menu(context, chat_id, message_id=msg_id)

    elif data.startswith("cat|"):
        cat_type = data.split("|")[1]
        await show_cart_selector(context, chat_id, user_id, message_id=msg_id, page=1, cat_type=cat_type)

    elif data.startswith("page|"):
        parts = data.split("|")
        target_page = int(parts[1])
        cat_type = parts[2].replace("_", " ")
        await show_cart_selector(context, chat_id, user_id, message_id=msg_id, page=target_page, cat_type=cat_type)

    elif data.startswith("m|"):
        parts = data.split("|")
        prod_id = parts[1]
        delta = int(parts[2])
        page = int(parts[3])
        cat_type = parts[4].replace("_", " ")
         
        is_mlbb = str(prod_id).startswith("mlbb_")
        if is_mlbb:
            stock_count = 99999
        else:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (prod_id,))
            stock_count = cursor.fetchone()[0]

        if user_id not in user_carts: user_carts[user_id] = {}
        new_qty = user_carts[user_id].get(prod_id, 0) + delta
        if new_qty < 0: new_qty = 0
        elif new_qty > stock_count:
            await query.answer(f"⚠️ Stock မလောက်တော့ပါ။", show_alert=True)
            new_qty = stock_count
        user_carts[user_id][prod_id] = new_qty
        await show_cart_selector(context, chat_id, user_id, message_id=msg_id, page=page, cat_type=cat_type)

    elif data == "checkout_cart":
        if user_id not in user_carts or not any(user_carts[user_id].values()):
            await query.answer("အရေအတွက် ရွေးချယ်ပေးပါ။", show_alert=True)
            return
        
        has_mlbb = any(str(pid).startswith("mlbb_") and qty > 0 for pid, qty in user_carts[user_id].items())
        if has_mlbb:
            user_states[user_id] = "waiting_checkout_player_id"
            prompt_text = (
                "🎮 <b>MLBB Diamond/Pass ပါဝင်နေပါသည်။</b>\n\n"
                "ကျေးဇူးပြု၍ သင့်ရဲ့ <b>User ID</b> နှင့် <b>Zone/Server ID</b> ကို အောက်တွင် ရိုက်ထည့်ပေးပါ။\n"
                "(ဥပမာ - <code>12345678 1234</code>)"
            )
            await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_cart")]]))
        else:
            await process_checkout(context, chat_id, user_id, msg_id=msg_id)

    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
        if user_id in admin_states: del admin_states[user_id]
        await show_admin_panel(context, chat_id, msg_id)

    elif data == "toggle_shop_status" and user_id == ADMIN_USER_ID:
        new_status = 'closed' if is_shop_open() else 'open'
        cursor.execute("UPDATE settings SET value=%s WHERE key='shop_status'", (new_status,))
        conn.commit()
        await show_admin_panel(context, chat_id, msg_id)

    elif data == "manage_stock_menu" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name FROM products WHERE id NOT LIKE %s", ('mlbb_%',))
        products = cursor.fetchall()
        text = "📦 <b>Stock စာရင်းနှင့် Code စီမံရန် (Manual Products)</b>\n\n"
        keyboard = []
        for p in products:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (p[0],))
            count = cursor.fetchone()[0]
            text += f"🔹 {p[1]} : <b>{count}</b> ခု\n"
            keyboard.append([InlineKeyboardButton(f"➕ Add {p[1]}", callback_data=f"addcode_{p[0]}"),
                             InlineKeyboardButton(f"➖ Remove {p[1]}", callback_data=f"delcodelist_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Admin သို့ ပြန်သွားရန်", callback_data="admin_panel")])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("delcodelist_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("delcodelist_", "")
        cursor.execute("SELECT id, code FROM stock WHERE product_id=%s LIMIT 80", (prod_id,))
        codes = cursor.fetchall()
        if not codes:
            await query.answer("ဖျက်ရန် Code မရှိပါ။", show_alert=True)
            return
        keyboard = []
        for c in codes: keyboard.append([InlineKeyboardButton(f"❌ {c[1]}", callback_data=f"rmcode_{c[0]}_{prod_id}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="manage_stock_menu")])
        await query.edit_message_text("👇 ဖျက်လိုသော Code အား တစ်ချက်နှိပ်လိုက်ပါ။", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("rmcode_") and user_id == ADMIN_USER_ID:
        parts = data.split("_")
        code_id, prod_id = parts[1], f"{parts[2]}_{parts[3]}"
        cursor.execute("DELETE FROM stock WHERE id=%s", (code_id,))
        conn.commit()
        await query.answer("Code ဖျက်လိုက်ပါပြီ။")
        cursor.execute("SELECT id, code FROM stock WHERE product_id=%s LIMIT 80", (prod_id,))
        codes = cursor.fetchall()
        keyboard = []
        for c in codes: keyboard.append([InlineKeyboardButton(f"❌ {c[1]}", callback_data=f"rmcode_{c[0]}_{prod_id}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="manage_stock_menu")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "view_banned" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT user_id FROM users WHERE is_banned=TRUE")
        banned_users = cursor.fetchall()
        text = "🚫 <b>Banned Users စာရင်း:</b>\n\n"
        keyboard = [[InlineKeyboardButton("➕ ID ဖြင့် Ban မည်", callback_data="admin_manual_ban")]]
        if not banned_users: text += "Banned User မရှိသေးပါ။"
        else:
            for b in banned_users:
                text += f"ID: <code>{b[0]}</code>\n"
                keyboard.append([InlineKeyboardButton(f"🔓 Unban {b[0]}", callback_data=f"unban_{b[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_manual_ban" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "manual_ban"}
        await query.edit_message_text("🚫 <b>Ban လိုသော User ID (Telegram ID) ကို ဂဏန်းဖြင့် ရိုက်ထည့်ပါ:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data.startswith("unban_") and user_id == ADMIN_USER_ID:
        target_id = int(data.split("_")[1])
        cursor.execute("UPDATE users SET is_banned=FALSE WHERE user_id=%s", (target_id,))
        conn.commit()
        await query.answer("Ban ဖြုတ်ပေးလိုက်ပါပြီ။", show_alert=True)
        try: await context.bot.send_message(chat_id=target_id, text="✅ သင့်အကောင့်အား ပြန်လည်အသုံးပြုခွင့် ပေးလိုက်ပါပြီ။")
        except: pass
        await show_admin_panel(context, chat_id, msg_id)

    elif data.startswith("addcode_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("addcode_", "")
        admin_states[user_id] = {"action": "add_code", "product_id": prod_id}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
        await query.edit_message_text(f"✏️ <code>{prod_id}</code> အတွက် Code အသစ်များကို ရိုက်ထည့်ပါ။\n\n(တစ်ကြောင်းလျှင် တစ်ခုစီ ခွဲ၍ ရိုက်ပို့ပါ)", parse_mode="HTML", reply_markup=cancel_btn)

    elif data == "admin_post_channel" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "post_channel"}
        await query.edit_message_text("📝 <b>Channel သို့ တင်မည့် Post စာသားများကို ရိုက်ထည့်ပါ။</b>\n(စာသားအောက်တွင် Code တန်းဝယ်နိုင်သော Button ကို အလိုအလျောက် တပ်ဆင်ပေးပါမည်)", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data == "profit_report" and user_id == ADMIN_USER_ID:
        current_month = datetime.now().strftime("%Y-%m")
        current_year = datetime.now().strftime("%Y")
        cursor.execute("SELECT details, date FROM orders WHERE status='accepted'")
        all_orders = cursor.fetchall()
        month_300 = month_1k = year_300 = year_1k = 0

        for o in all_orders:
            details_str, date_str = o[0], o[1]
            if not (date_str.startswith(current_month) or date_str.startswith(current_year)): continue
            for item in details_str.split(", "):
                if ":" in item:
                    pid, qty = item.split(":")
                    qty = int(qty)
                    if pid in ("smile_300", "300_code"):
                        if date_str.startswith(current_month): month_300 += qty
                        if date_str.startswith(current_year): year_300 += qty
                    elif pid in ("smile_1k", "1k_code"):
                        if date_str.startswith(current_month): month_1k += qty
                        if date_str.startswith(current_year): year_1k += qty

        m_prof = (month_300 * 300) + (month_1k * 500)
        y_prof = (year_300 * 300) + (year_1k * 500)

        text = (f"📈 <b>အမြတ်ငွေစာရင်း အစီရင်ခံစာ (Smile One Codes)</b>\n\n📅 <b>ဒီလအတွက် ({current_month})</b>\n🔹 300 code: <b>{month_300}</b> ခု\n🔹 1k code: <b>{month_1k}</b> ခု\n💰 <b>အမြတ်ငွေ: {m_prof:,} MMK</b>\n\n"
                f"🗓️ <b>ဒီနှစ်အတွက် ({current_year})</b>\n🔹 300 code: <b>{year_300}</b> ခု\n🔹 1k code: <b>{year_1k}</b> ခု\n💰 <b>အမြတ်ငွေ: {y_prof:,} MMK</b>")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data == "manage_price" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name, price FROM products WHERE id NOT LIKE %s", ('mlbb_%',))
        products = cursor.fetchall()
        keyboard = []
        for p in products: keyboard.append([InlineKeyboardButton(f"🟨 Edit {p[1]} ({p[2]:,} MMK)", callback_data=f"editprice_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")])
        await query.edit_message_text("💲 ဘယ် Product ရဲ့ ဈေးနှုန်းကို ပြင်ဆင်မလဲ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_payment" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "set_payment"}
        await query.edit_message_text("🏦 Payment Info အသစ်ကို ရိုက်ထည့်ပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data == "admin_broadcast" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "broadcast"}
        await query.edit_message_text("📢 ပို့လိုသော ကြေညာချက်ကို ရိုက်ထည့်ပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data == "top_buyers" and user_id == ADMIN_USER_ID:
        current_month = datetime.now().strftime("%Y-%m")
        cursor.execute("SELECT user_id, username, details, total_price FROM orders WHERE status='accepted' AND date LIKE %s", (f"{current_month}%",))
        orders = cursor.fetchall()
        buyer_stats = {}
        for o in orders:
            uid, uname, details_str, price = o
            if uid not in buyer_stats:
                buyer_stats[uid] = {"username": uname, "spent": 0, "code_300": 0, "code_1k": 0, "mlbb": 0}
            buyer_stats[uid]["spent"] += price
            for item in details_str.split(", "):
                if ":" in item:
                    p_parts = item.split(":")
                    pid = p_parts[0]
                    try: qty = int(p_parts[1])
                    except: qty = 0
                    if pid in ("300_code", "smile_300"): buyer_stats[uid]["code_300"] += qty
                    elif pid in ("1k_code", "smile_1k"): buyer_stats[uid]["code_1k"] += qty
                    elif str(pid).startswith("mlbb_"): buyer_stats[uid]["mlbb"] += qty

        sorted_buyers = sorted(buyer_stats.items(), key=lambda x: x[1]["spent"], reverse=True)[:10]
        text = f"🏆 <b>Top 10 Buyers ({current_month}):</b>\n\n"
        if not sorted_buyers: text += "ဝယ်ယူသူ မရှိသေးပါ။"
        else:
            for i, (uid, stats) in enumerate(sorted_buyers):
                raw_u = stats.get('username')
                uname = f"@{raw_u}" if raw_u and raw_u != "No_Username" else f"ID: <code>{uid}</code>"
                text += (
                    f"<b>{i+1}. {uname}</b>\n"
                    f"   📦 300 Code: <b>{stats['code_300']}</b> ခု | 1k Code: <b>{stats['code_1k']}</b> ခု | MLBB: <b>{stats['mlbb']}</b> ခု\n"
                    f"   💰 စုစုပေါင်းတန်ဖိုး: <b>{stats['spent']:,}</b> MMK\n\n"
                )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data.startswith("editprice_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("editprice_", "")
        admin_states[user_id] = {"action": "set_price", "product_id": prod_id}
        await query.edit_message_text(f"💲 <code>{prod_id}</code> အတွက် ဈေးနှုန်းအသစ် ရိုက်ထည့်ပါ။", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data == "admin_sales" and user_id == ADMIN_USER_ID:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE status='accepted' AND date LIKE %s", (f"{today}%",))
        sales = cursor.fetchone()
        count, total = sales[0] or 0, sales[1] or 0
        text = f"📊 <b>ယနေ့ အရောင်းစာရင်း ({today}):</b>\n\n✅ အရေအတွက်: {count} ကြိမ်\n💰 ဝင်ငွေ: {total:,} MMK\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data.startswith(("accept_", "reject_", "ban_")) and user_id == ADMIN_USER_ID:
        action_type, order_id_str = data.split("_")
        order_id = int(order_id_str)
        cursor.execute("SELECT user_id, details, status, monthly_id FROM orders WHERE id=%s", (order_id,))
        order = cursor.fetchone()
        
        if order and order[2] == "pending":
            buyer_id, details, _, monthly_id = order
            display_order_id = monthly_id if monthly_id else order_id
            
            if action_type == "ban":
                cursor.execute("UPDATE orders SET status='rejected' WHERE id=%s", (order_id,))
                cursor.execute("UPDATE users SET is_banned=TRUE WHERE user_id=%s", (buyer_id,))
                conn.commit()
                try: await context.bot.send_message(chat_id=buyer_id, text="🚫 <b>သင့်အကောင့်သည် ပိတ်ပင်ခံလိုက်ရပါသည်။</b>", parse_mode="HTML")
                except: pass
                msg = "🚫 <b>Order Rejected & User Banned!</b>\n\n" + (query.message.caption or query.message.text)
                await (query.edit_message_caption if query.message.caption else query.edit_message_text)(msg, parse_mode="HTML")

            elif action_type == "reject":
                cursor.execute("UPDATE orders SET status='rejected' WHERE id=%s", (order_id,))
                conn.commit()
                try: await context.bot.send_message(chat_id=buyer_id, text=f"❌ <b>သင့်ရဲ့ Order #{display_order_id} ကို Admin မှ ငြင်းပယ်လိုက်ပါသည်။</b>", parse_mode="HTML")
                except: pass
                msg = "❌ <b>Order Rejected!</b>\n\n" + (query.message.caption or query.message.text)
                await (query.edit_message_caption if query.message.caption else query.edit_message_text)(msg, parse_mode="HTML")

            elif action_type == "accept":
                items = details.split(", ")
                codes_to_send = []
                insufficient = False
                
                for item in items:
                    if ":" not in item: continue
                    pid, qty = item.split(":")
                    qty = int(qty)
                    
                    is_mlbb = str(pid).startswith("mlbb_")
                    if is_mlbb:
                        cursor.execute("SELECT name FROM products WHERE id=%s", (pid,))
                        prod = cursor.fetchone()
                        p_name = prod[0] if prod else pid
                        codes_to_send.append(f"🔸 <b>{p_name}</b> : (✅ အကောင့်ထဲသို့ တိုက်ရိုက်ထည့်သွင်းပေးပြီးပါပြီ)")
                    else:
                        cursor.execute("SELECT id, code FROM stock WHERE product_id=%s LIMIT %s", (pid, qty))
                        rows = cursor.fetchall()
                        if len(rows) < qty:
                            insufficient = True
                            break
                        for r in rows:
                            codes_to_send.append(f"🔸 <b>{pid.upper()}</b> : <code>{r[1]}</code>")
                            cursor.execute("DELETE FROM stock WHERE id=%s", (r[0],))
                        
                if insufficient:
                    msg = (query.message.caption or query.message.text) + "\n\n⚠️ <b>Stock မလောက်ပါ! Admin Panel မှ Code အသစ် အရင်ဖြည့်ပါ။</b>"
                    await (query.edit_message_caption if query.message.caption else query.edit_message_text)(msg, parse_mode="HTML")
                else: 
                    cursor.execute("UPDATE orders SET status='accepted' WHERE id=%s", (order_id,))
                    conn.commit()
                    codes_text = "\n".join(codes_to_send)
                    try: await context.bot.send_message(chat_id=buyer_id, text=f"✅ <b>သင့်ရဲ့ Order #{display_order_id} အောင်မြင်ပါတယ်။</b>\n\n🎁 <b>သင်ဝယ်ယူထားသော ပစ္စည်းများ:</b>\n{codes_text}", parse_mode="HTML")
                    except: pass
                    
                    msg = (query.message.caption or query.message.text) + f"\n\n✅ <b>Order Accepted!</b>\n📦 <b>Delivered:</b>\n{codes_text}"
                    await (query.edit_message_caption if query.message.caption else query.edit_message_text)(msg, parse_mode="HTML")
        else:
            await query.answer("ဤ Order အား ဖြေရှင်းပြီးပါပြီ။", show_alert=True)
            
    conn.commit()
    conn.close()

async def process_photos_group(context, user_id, chat_id, order, photos_list):
    order_id, details, total, monthly_id = order
    display_order_id = monthly_id if monthly_id else order_id
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT file_unique_ids FROM orders WHERE status IN ('pending', 'accepted')")
    all_f_ids_raw = cursor.fetchall()
    existing_f_ids = []
    for f in all_f_ids_raw:
        if f[0]: existing_f_ids.extend(f[0].split(","))

    current_unique_ids = [p["unique_id"] for p in photos_list]
    for c_id in current_unique_ids:
        if c_id in existing_f_ids:
            cursor.execute("UPDATE orders SET status='rejected' WHERE id=%s", (order_id,))
            conn.commit()
            conn.close()
            await context.bot.send_message(chat_id=chat_id, text="🚫 <b>ဤပြေစာအား အသုံးပြုပြီးဖြစ်ပါသည်။</b> ငွေရှင်းခြင်းကို ပယ်ချလိုက်ပါသည်။", parse_mode="HTML", reply_markup=get_main_keyboard(user_id))
            return
            
    u_ids_str = ",".join(current_unique_ids)
    cursor.execute("UPDATE orders SET file_unique_ids=%s WHERE id=%s", (u_ids_str, order_id))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🟩 လက်ခံမည် (Accept)", callback_data=f"accept_{order_id}")],
        [InlineKeyboardButton("🟥 ငြင်းပယ်မည် (Reject)", callback_data=f"reject_{order_id}")],
        [InlineKeyboardButton("🚫 Reject & Ban", callback_data=f"ban_{order_id}")]
    ]
    
    display_details = []
    items = details.split(", ")
    for item in items:
        if ":" in item:
            pid, q = item.split(":")
            display_details.append(f"🔹 {pid} ( {q} ) ခု")
    
    raw_username = context.user_data.get("username")
    display_uname = f"@{raw_username}" if raw_username else "No_Username"
    
    caption = f"🔔 <b>New Order #{display_order_id}</b>\n👤 Buyer: {display_uname} (ID: <code>{user_id}</code>)\n📦 Details:\n{chr(10).join(display_details)}\n💰 Total: {total:,} MMK"
    
    try:
        if len(photos_list) > 1:
            media = [InputMediaPhoto(photos_list[0]["id"], caption=caption, parse_mode="HTML")] + [InputMediaPhoto(p["id"]) for p in photos_list[1:]]
            await context.bot.send_media_group(chat_id=ADMIN_USER_ID, media=media)
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"👆 အထက်ပါ Order #{display_order_id} အတွက် ဆုံးဖြတ်ချက်ချပါ:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_photo(chat_id=ADMIN_USER_ID, photo=photos_list[0]["id"], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            
        await context.bot.send_message(chat_id=chat_id, text="✅ <b>ငွေလွှဲပြေစာ လက်ခံရရှိပါပြီ။</b> Admin မှ စစ်ဆေးပြီးပါက Code များကို ဤနေရာသို့ ချက်ချင်း ပို့ပေးပါမည်။", parse_mode="HTML", reply_markup=get_main_keyboard(user_id))
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ စနစ် ချို့ယွင်းနေပါသည်။", reply_markup=get_main_keyboard(user_id))

async def delayed_media_group_worker(context, user_id, chat_id, order, media_group_id):
    await asyncio.sleep(2.0)
    photos = media_groups.pop(media_group_id, [])
    media_group_tasks.pop(media_group_id, None)
    if photos:
        await process_photos_group(context, user_id, chat_id, order, photos)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message or not update.message.photo: return
    if await check_ban_and_shop(update, context): return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    context.user_data["username"] = update.effective_user.username
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, details, total_price, monthly_id FROM orders WHERE user_id=%s AND status='pending' ORDER BY id DESC LIMIT 1", (user_id,))
    order = cursor.fetchone()
    conn.close()
    
    if not order:
        await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ '🛍️ ဝယ်ယူမည်' ကို နှိပ်၍ အရင်ရွေးချယ်ပြီးမှ ပြေစာပို့ပေးပါ။", reply_markup=get_main_keyboard(user_id))
        return

    photo_obj = update.message.photo[-1]
    photo_data = {"id": photo_obj.file_id, "unique_id": photo_obj.file_unique_id}
    media_group_id = update.message.media_group_id
    
    if media_group_id:
        media_groups[media_group_id].append(photo_data)
        if media_group_id not in media_group_tasks:
            media_group_tasks[media_group_id] = asyncio.create_task(
                delayed_media_group_worker(context, user_id, chat_id, order, media_group_id)
            )
    else:
        await process_photos_group(context, user_id, chat_id, order, [photo_data])

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()
