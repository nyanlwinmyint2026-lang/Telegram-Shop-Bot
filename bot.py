import os
import psycopg2
import asyncio
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
    
    # Safely Add Columns if missing
    try: cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE"); conn.commit()
    except: conn.rollback()
    try: cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS monthly_id INTEGER"); conn.commit()
    except: conn.rollback()
    try: cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS file_unique_ids TEXT"); conn.commit()
    except: conn.rollback()
        
    cursor.execute("UPDATE orders SET monthly_id = id WHERE monthly_id IS NULL")
    
    # Initialize Defaults
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('300_code', '300 code', 30000) ON CONFLICT (id) DO NOTHING")
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('1k_code', '1k code', 95000) ON CONFLICT (id) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('payment_info', '<code>09XXXXXXXXX</code> (KBZ Pay)\\n<code>09XXXXXXXXX</code> (Wave Pay)') ON CONFLICT (key) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('shop_status', 'open') ON CONFLICT (key) DO NOTHING")
    
    conn.commit()
    conn.close()

init_db()

# Memory tracking
user_carts = {}
admin_states = {}
media_groups = defaultdict(list)

# --- Helper Functions ---
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
        [KeyboardButton("🛍️ ဝယ်ယူမည် (Products)"), KeyboardButton("🧾 ဝယ်ယူမှုမှတ်တမ်း")],
        [KeyboardButton("👤 ကျွန်ုပ်၏ အကောင့်")]
    ]
    if user_id == ADMIN_USER_ID:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def check_ban_and_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban_and_shop(update, context): return
    user_id = update.effective_user.id
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
    conn.commit()
    conn.close()
    
    welcome_text = (
        "🌟 <b>Digital Product Shop မှ လှိုက်လှဲစွာ ကြိုဆိုပါတယ်။</b> 🌟\n\n"
        "💳 သင့်အတွက် အကောင်းဆုံး ဝန်ဆောင်မှုပေးရန် အဆင်သင့်ရှိနေပါသည်။\n"
        "👇 အောက်ပါ Menu ခလုတ်များကို အသုံးပြု၍ အလွယ်တကူ ဝယ်ယူနိုင်ပါသည်။"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(user_id))

async def show_cart_selector(context, chat_id, user_id, message_id=None):
    if user_id not in user_carts: user_carts[user_id] = {}
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products ORDER BY price ASC")
    products = cursor.fetchall()

    keyboard = []
    text = "🛒 <b>ဝယ်ယူလိုသော Product အရေအတွက်များကို ရွေးချယ်ပါ:</b>\n\n"
    total_amount = total_items = 0

    for p in products:
        p_id, p_name, p_price = p
        cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (p_id,))
        stock_count = cursor.fetchone()[0]

        current_qty = user_carts[user_id].get(p_id, 0)
        if current_qty > stock_count: current_qty = stock_count
        user_carts[user_id][p_id] = current_qty

        item_total = current_qty * p_price
        total_amount += item_total
        total_items += current_qty

        stock_badge = f"(✅ Stock: {stock_count})" if stock_count > 0 else "(❌ Out of Stock)"
        text += f"🔹 <b>{p_name}</b> {stock_badge}\n   💵 တစ်ကုဒ်စျေး: <b>{p_price:,}</b> MMK\n   📦 ရွေးထားသည်: <b>{current_qty}</b> ခု = <b>{item_total:,}</b> MMK\n\n"
        keyboard.append([InlineKeyboardButton(f"🟦 {p_name} ({p_price:,} MMK)", callback_data="noop")])
        keyboard.append([
            InlineKeyboardButton("➖ 1", callback_data=f"mod_{p_id}_-1"),
            InlineKeyboardButton(f"🔢 {current_qty} ခု", callback_data="noop"),
            InlineKeyboardButton("➕ 1", callback_data=f"mod_{p_id}_1")
        ])
    conn.close()

    text += f"━━━━━━━━━━━━━━━━━━\n💰 <b>စုစုပေါင်း ကျသင့်ငွေ: {total_amount:,} MMK</b> ({total_items} ခု)"
    action_row = []
    if total_amount > 0: action_row.append(InlineKeyboardButton(f"🟩 ငွေရှင်းမည် ({total_amount:,} MMK)", callback_data="checkout_cart"))
    action_row.append(InlineKeyboardButton("🟥 မဝယ်တော့ပါ (Cancel)", callback_data="cancel_cart"))
    keyboard.append(action_row)

    if message_id:
        try: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except: pass
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def show_orders(context, chat_id, user_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, details, total_price, status, date, monthly_id FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 5", (user_id,))
    orders = cursor.fetchall()
    conn.close()
    
    if not orders: text = "⚠️ သင် ဝယ်ယူထားသော မှတ်တမ်း မရှိသေးပါ။"
    else:
        text = "🧾 <b>နောက်ဆုံး ဝယ်ယူထားသော ၅ ကြိမ်:</b>\n\n"
        for o in orders:
            status_emoji = "✅" if o[3] == "accepted" else ("❌" if o[3] == "rejected" else "⏳")
            display_id = o[5] if o[5] else o[0]
            text += f"🔖 Order #{display_id} | 💰 {o[2]:,} MMK\n{status_emoji} Status: {o[3].upper()} | 📅 {o[4]}\n\n"
            
    if message_id: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML")
    else: await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

async def show_user_dashboard(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or "No_Username"
    current_year = datetime.now().year
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT details, date, total_price FROM orders WHERE user_id=%s AND status='accepted' AND date LIKE %s", (user_id, f"{current_year}%"))
    orders = cursor.fetchall()
    conn.close()

    total_orders = len(orders)
    months_data = {m: {"300": 0, "1k": 0, "mmk": 0} for m in range(1, 13)}
    
    for o in orders:
        details, date_str, price = o
        month = int(date_str[5:7])
        months_data[month]["mmk"] += price
        for item in details.split(", "):
            if ":" in item:
                pid, qty = item.split(":")
                qty = int(qty)
                if pid in ("smile_300", "300_code"): months_data[month]["300"] += qty
                elif pid in ("smile_1k", "1k_code"): months_data[month]["1k"] += qty

    text = f"👤 <b>ဝယ်ယူသူ:</b> @{username} (ID: <code>{user_id}</code>)\n🛍️ <b>စုစုပေါင်း အောင်မြင်ထားသော Order:</b> {total_orders} ကြိမ်\n\n"
    text += f"📅 <b>{current_year} ခုနှစ် ဝယ်ယူမှုမှတ်တမ်းများ:</b>\n\n"
    
    month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    
    for m in range(1, 13):
        data = months_data[m]
        text += f"📆 <b>{month_names[m-1]} {current_year}</b>\n"
        text += f"🔹 300 code: {data['300']} ခု\n"
        text += f"🔹 1k code: {data['1k']} ခု\n"
        text += f"💰 ကျသင့်ငွေ: {data['mmk']:,} MMK\n\n"

    await update.message.reply_text(text, parse_mode="HTML")

async def show_admin_panel(context, chat_id, message_id=None):
    shop_status = "🔴 ဆိုင်ပိတ်မည် (Close)" if is_shop_open() else "🟢 ဆိုင်ဖွင့်မည် (Open)"
    keyboard = [
        [InlineKeyboardButton("📦 Stock စာရင်းနှင့် Code စီမံရန်", callback_data="manage_stock_menu")],
        [InlineKeyboardButton("🟨 ဈေးပြင်ရန်", callback_data="manage_price"), InlineKeyboardButton("🏦 Payment Info", callback_data="manage_payment")],
        [InlineKeyboardButton("📈 အမြတ်ငွေစာရင်း", callback_data="profit_report"), InlineKeyboardButton("📊 ယနေ့ အရောင်း", callback_data="admin_sales")],
        [InlineKeyboardButton("🏆 Top Buyers", callback_data="top_buyers"), InlineKeyboardButton("📝 Channel သို့ Post", callback_data="admin_post_channel")],
        [InlineKeyboardButton("📢 Broadcast ပို့ရန်", callback_data="admin_broadcast"), InlineKeyboardButton(shop_status, callback_data="toggle_shop_status")],
        [InlineKeyboardButton("🚫 Banned Users စာရင်း & Unban", callback_data="view_banned")]
    ]
    text = "👑 <b>Admin Management Panel</b>\n\nလုပ်ဆောင်လိုသော အရာကို အောက်ပါခလုတ်များမှ ရွေးချယ်ပါ:"
    if message_id: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else: await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    chat_id = update.effective_chat.id

    if text == "👤 ကျွန်ုပ်၏ အကောင့်":
        await show_user_dashboard(update, context)
        return

    if "ဝယ်ယူမည်" in text and "မှတ်တမ်း" not in text:
        if await check_ban_and_shop(update, context): return
        if user_id in admin_states: del admin_states[user_id]
        if user_id in user_carts: del user_carts[user_id]
        await show_cart_selector(context, chat_id, user_id)
        return
    elif "မှတ်တမ်း" in text:
        if user_id in admin_states: del admin_states[user_id]
        await show_orders(context, chat_id, user_id)
        return
    elif "Admin Panel" in text and user_id == ADMIN_USER_ID:
        if user_id in admin_states: del admin_states[user_id]
        await show_admin_panel(context, chat_id)
        return

    if user_id in admin_states and user_id == ADMIN_USER_ID:
        state = admin_states[user_id]
        action = state["action"]
        conn = get_db()
        cursor = conn.cursor()
        
        if action == "add_code":
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
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🟩 code ဝယ်မည် ↗", url=BOT_LINK)]])
            try:
                await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=text, parse_mode="HTML", reply_markup=keyboard)
                await update.message.reply_text("✅ Channel သို့ Post တင်ပြီးပါပြီ။")
            except Exception as e:
                await update.message.reply_text(f"⚠️ Channel သို့ တင်ရန် ကျရှုံးပါသည်။ Admin ပေးထားခြင်း ရှိ/မရှိ စစ်ဆေးပါ။")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        conn.close()
        return

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = query.message.chat.id
    msg_id = query.message.message_id

    if "admin" not in data and not data.startswith(("accept_", "reject_", "ban_", "manage_", "addcode_", "delcode_", "view_banned", "unban_")):
        if await check_ban_and_shop(update, context): return

    conn = get_db()
    cursor = conn.cursor()

    if data == "noop": pass
    elif data == "cancel_cart":
        if user_id in user_carts: del user_carts[user_id]
        await query.edit_message_text("❌ ဝယ်ယူမှုကို ပယ်ဖျက်လိုက်ပါပြီ။")
    elif data == "cancel_action":
        if user_id in admin_states: del admin_states[user_id]
        await query.edit_message_text("🚫 လုပ်ဆောင်ချက် ဖျက်သိမ်းလိုက်ပါပြီ။")
        if user_id == ADMIN_USER_ID: await show_admin_panel(context, chat_id)
        
    elif data.startswith("mod_"):
        parts = data.split("_")
        prod_id = f"{parts[1]}_{parts[2]}"
        delta = int(parts[3])
        cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (prod_id,))
        stock_count = cursor.fetchone()[0]
        if user_id not in user_carts: user_carts[user_id] = {}
        new_qty = user_carts[user_id].get(prod_id, 0) + delta
        if new_qty < 0: new_qty = 0
        elif new_qty > stock_count:
            await query.answer(f"⚠️ Stock {stock_count} ခုသာ ကျန်ပါတော့သည်။", show_alert=True)
            new_qty = stock_count
        user_carts[user_id][prod_id] = new_qty
        await show_cart_selector(context, chat_id, user_id, message_id=msg_id)

    elif data == "checkout_cart":
        if user_id not in user_carts or not any(user_carts[user_id].values()):
            await query.answer("အရေအတွက် ရွေးချယ်ပေးပါ။", show_alert=True)
            return

        total_price = 0
        cart_text = "🛒 <b>သင့်ရဲ့ Order စာရင်း:</b>\n\n"
        details = []

        for pid, qty in list(user_carts[user_id].items()):
            if qty <= 0: continue
            cursor.execute("SELECT name, price FROM products WHERE id=%s", (pid,))
            prod = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (pid,))
            stock_count = cursor.fetchone()[0]
            if qty > stock_count:
                await query.answer(f"⚠️ {prod[0]} Stock မလောက်တော့ပါ။", show_alert=True)
                await show_cart_selector(context, chat_id, user_id, message_id=msg_id)
                return
            price = prod[1] * qty
            total_price += price
            pid_name = "300 code" if pid in ("smile_300", "300_code") else ("1k code" if pid in ("smile_1k", "1k_code") else prod[0])
            cart_text += f"🔹 <b>{pid_name}</b> ( {qty} ) ခု = {price:,} MMK\n"
            details.append(f"{pid}:{qty}")

        cart_text += f"\n💰 <b>စုစုပေါင်း ကျသင့်ငွေ - {total_price:,} MMK</b>\n\n"
        cursor.execute("SELECT value FROM settings WHERE key='payment_info'")
        payment_info = cursor.fetchone()[0]
        cart_text += f"🏦 <b>ငွေလွှဲရမည့် အကောင့်များ:</b>\n{payment_info}\n\n"
        cart_text += "⚠️ <b>အရေးကြီး:</b> ငွေလွှဲပြေစာ (Screenshot) ကို ဤနေရာသို့ တိုက်ရိုက် ပို့ပေးပါ။ <b>(ပုံဟောင်း ပြန်ပို့ပါက အလိုအလျောက် ပယ်ချခံရပါမည်)</b>"

        details_str = ", ".join(details)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_month = date_str[:7]
        
        cursor.execute("SELECT COALESCE(MAX(monthly_id), 0) FROM orders WHERE date LIKE %s", (f"{current_month}%",))
        next_monthly_id = cursor.fetchone()[0] + 1

        cursor.execute("DELETE FROM orders WHERE user_id=%s AND status='pending'", (user_id,))
        cursor.execute(
            "INSERT INTO orders (user_id, username, details, total_price, status, date, monthly_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, update.effective_user.username, details_str, total_price, "pending", date_str, next_monthly_id)
        )
        conn.commit()
        user_carts[user_id] = {}
        await query.edit_message_text(cart_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_cart")]]))

    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
        if user_id in admin_states: del admin_states[user_id]
        await show_admin_panel(context, chat_id, msg_id)

    # --- Admin Features ---
    elif data == "toggle_shop_status" and user_id == ADMIN_USER_ID:
        new_status = 'closed' if is_shop_open() else 'open'
        cursor.execute("UPDATE settings SET value=%s WHERE key='shop_status'", (new_status,))
        conn.commit()
        await show_admin_panel(context, chat_id, msg_id)

    elif data == "manage_stock_menu" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name FROM products")
        products = cursor.fetchall()
        text = "📦 <b>Stock စာရင်းနှင့် Code စီမံရန်</b>\n\n"
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
        # Refresh list
        cursor.execute("SELECT id, code FROM stock WHERE product_id=%s LIMIT 80", (prod_id,))
        codes = cursor.fetchall()
        keyboard = []
        for c in codes: keyboard.append([InlineKeyboardButton(f"❌ {c[1]}", callback_data=f"rmcode_{c[0]}_{prod_id}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="manage_stock_menu")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "view_banned" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT user_id FROM users WHERE is_banned=TRUE")
        banned_users = cursor.fetchall()
        if not banned_users:
            await query.edit_message_text("🚫 Banned User မရှိသေးပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))
            return
        text = "🚫 <b>Banned Users စာရင်း:</b>\n\n"
        keyboard = []
        for b in banned_users:
            text += f"ID: <code>{b[0]}</code>\n"
            keyboard.append([InlineKeyboardButton(f"🔓 Unban {b[0]}", callback_data=f"unban_{b[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

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
        await query.edit_message_text("📝 <b>Channel သို့ တင်မည့် Post စာသားများကို ရိုက်ထည့်ပါ။</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

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

        text = (f"📈 <b>အမြတ်ငွေစာရင်း အစီရင်ခံစာ</b>\n\n📅 <b>ဒီလအတွက် ({current_month})</b>\n🔹 300 code: <b>{month_300}</b> ခု\n🔹 1k code: <b>{month_1k}</b> ခု\n💰 <b>အမြတ်ငွေ: {m_prof:,} MMK</b>\n\n"
                f"🗓️ <b>ဒီနှစ်အတွက် ({current_year})</b>\n🔹 300 code: <b>{year_300}</b> ခု\n🔹 1k code: <b>{year_1k}</b> ခု\n💰 <b>အမြတ်ငွေ: {y_prof:,} MMK</b>")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data == "manage_price" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name, price FROM products")
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
            if uid not in buyer_stats: buyer_stats[uid] = {"username": uname, "spent": 0, "300_qty": 0, "1k_qty": 0}
            buyer_stats[uid]["spent"] += price
            for item in details_str.split(", "):
                if ":" in item:
                    pid, qty = item.split(":")
                    if pid in ("smile_300", "300_code"): buyer_stats[uid]["300_qty"] += int(qty)
                    elif pid in ("smile_1k", "1k_code"): buyer_stats[uid]["1k_qty"] += int(qty)

        sorted_buyers = sorted(buyer_stats.items(), key=lambda x: x[1]["spent"], reverse=True)[:5]
        text = f"🏆 <b>Top 5 Buyers ({current_month}):</b>\n\n"
        if not sorted_buyers: text += "ဝယ်ယူသူ မရှိသေးပါ။"
        else:
            for i, (uid, stats) in enumerate(sorted_buyers):
                uname = f"@{stats['username']}" if stats['username'] and stats['username'] != "No_Username" else f"ID: <code>{uid}</code>"
                text += f"<b>{i+1}. {uname}</b>\n   🔹 300 code: {stats['300_qty']} ခု | 1k code: {stats['1k_qty']} ခု\n   💰 စုစုပေါင်း: <b>{stats['spent']:,}</b> MMK\n\n"
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

    # Accept / Reject / Ban Action from Receipt
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
                    pid, qty = item.split(":")
                    qty = int(qty)
                    cursor.execute("SELECT id, code FROM stock WHERE product_id=%s LIMIT %s", (pid, qty))
                    rows = cursor.fetchall()
                    if len(rows) < qty:
                        insufficient = True
                        break
                    for r in rows:
                        pid_name = "300 code" if pid in ("smile_300", "300_code") else ("1k code" if pid in ("smile_1k", "1k_code") else pid.upper())
                        codes_to_send.append(f"🔸 {pid_name} : <code>{r[1]}</code>")
                        cursor.execute("DELETE FROM stock WHERE id=%s", (r[0],))
                        
                if insufficient:
                    msg = (query.message.caption or query.message.text) + "\n\n⚠️ <b>Stock မလောက်ပါ! Admin Panel မှ Code အသစ် အရင်ဖြည့်ပါ။</b>"
                    await (query.edit_message_caption if query.message.caption else query.edit_message_text)(msg, parse_mode="HTML")
                else:
                    cursor.execute("UPDATE orders SET status='accepted' WHERE id=%s", (order_id,))
                    conn.commit()
                    codes_text = "\n".join(codes_to_send)
                    try: await context.bot.send_message(chat_id=buyer_id, text=f"✅ <b>သင့်ရဲ့ Order #{display_order_id} အောင်မြင်ပါတယ်။</b>\n\n🎁 <b>သင်ဝယ်ယူထားသော Codes များ:</b>\n{codes_text}", parse_mode="HTML")
                    except: pass
                    
                    msg = (query.message.caption or query.message.text) + f"\n\n✅ <b>Order Accepted!</b>\n📦 <b>Codes:</b>\n{codes_text}"
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

    # Fake Slip Method 1: Check File Unique IDs
    cursor.execute("SELECT file_unique_ids FROM orders WHERE status IN ('pending', 'accepted')")
    all_f_ids_raw = cursor.fetchall()
    existing_f_ids = []
    for f in all_f_ids_raw:
        if f[0]: existing_f_ids.extend(f[0].split(","))

    # Extract unique IDs from current photos
    current_unique_ids = [p["unique_id"] for p in photos_list]
    for c_id in current_unique_ids:
        if c_id in existing_f_ids:
            cursor.execute("UPDATE orders SET status='rejected' WHERE id=%s", (order_id,))
            conn.commit()
            conn.close()
            await context.bot.send_message(chat_id=chat_id, text="🚫 <b>ဤပြေစာအား အသုံးပြုပြီးဖြစ်ပါသည်။</b> ငွေရှင်းခြင်းကို ပယ်ချလိုက်ပါသည်။", parse_mode="HTML", reply_markup=get_main_keyboard(user_id))
            return
            
    # Save unique ids
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
    for item in details.split(", "):
        if ":" in item:
            pid, q = item.split(":")
            pid_name = "300 code" if pid in ("smile_300", "300_code") else ("1k code" if pid in ("smile_1k", "1k_code") else pid)
            display_details.append(f"🔹 {pid_name} ( {q} ) ခု")
    
    username = context.user_data.get("username", "No_Username")
    caption = f"🔔 <b>New Order #{display_order_id}</b>\n👤 Buyer: @{username} (ID: <code>{user_id}</code>)\n📦 Details:\n{chr(10).join(display_details)}\n💰 Total: {total:,} MMK"
    
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

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        if len(media_groups[media_group_id]) == 1:
            context.job_queue.run_once(lambda ctx: asyncio.create_task(process_photos_group(context, user_id, chat_id, order, media_groups[media_group_id])), when=2.0)
    else:
        await process_photos_group(context, user_id, chat_id, order, [photo_data])

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()
