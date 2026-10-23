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
    
    try: cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE"); conn.commit()
    except: conn.rollback()
    try: cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS monthly_id INTEGER"); conn.commit()
    except: conn.rollback()
    try: cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS file_unique_ids TEXT"); conn.commit()
    except: conn.rollback()
        
    cursor.execute("UPDATE orders SET monthly_id = id WHERE monthly_id IS NULL")
    
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('300_code', '300 code', 30000) ON CONFLICT (id) DO NOTHING")
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('1k_code', '1k code', 95000) ON CONFLICT (id) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('payment_info', '<code>09XXXXXXXXX</code> (KBZ Pay)\\n<code>09XXXXXXXXX</code> (Wave Pay)') ON CONFLICT (key) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('shop_status', 'open') ON CONFLICT (key) DO NOTHING")
    
    cursor.execute("INSERT INTO settings (key, value) VALUES ('exchange_rate', '4670') ON CONFLICT (key) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('profit_percentage', '5') ON CONFLICT (key) DO NOTHING")
    
    conn.commit()
    conn.close()

init_db()

# --- Memory tracking ---
user_carts = {}
admin_states = {}
user_states = {}
media_groups = defaultdict(list)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban_and_shop(update, context): return
    user_id = update.effective_user.id
    context.user_data["username"] = update.effective_user.username
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
    conn.commit()
    conn.close()
    
    welcome_text = "🌟 <b>Digital Product Shop မှ လှိုက်လှဲစွာ ကြိုဆိုပါတယ်။</b> 🌟\n\n💳 သင့်အတွက် အကောင်းဆုံး ဝန်ဆောင်မှုပေးရန် အဆင်သင့်ရှိနေပါသည်။\n👇 အောက်ပါ Menu ခလုတ်များကို အသုံးပြု၍ အလွယ်တကူ ဝယ်ယူနိုင်ပါသည်။"
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(user_id))

async def show_cart_selector(context, chat_id, user_id, message_id=None, page=1):
    if user_id not in user_carts: user_carts[user_id] = {}
    conn = get_db()
    cursor = conn.cursor()
    
    ITEMS_PER_PAGE = 10
    offset = (page - 1) * ITEMS_PER_PAGE
    
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]
    total_pages = (total_products + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if total_pages == 0: total_pages = 1

    cursor.execute("""
        SELECT id, name, price 
        FROM products 
        ORDER BY CASE WHEN id LIKE 'g2_%%' THEN 1 ELSE 0 END ASC, price ASC 
        LIMIT %s OFFSET %s
    """, (ITEMS_PER_PAGE, offset))
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
    text = f"🛒 <b>ဝယ်ယူလိုသော Product ကို ရွေးချယ်ပါ (စာမျက်နှာ {page}/{total_pages}):</b>\n\n"

    for p in products:
        p_id, p_name, p_price = p
        
        is_g2bulk = str(p_id).startswith("g2_")
        if is_g2bulk:
            stock_count = 99999
            stock_badge = "(✅ In Stock)"
        else:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (p_id,))
            stock_count = cursor.fetchone()[0]
            stock_badge = f"(✅ Stock: {stock_count})" if stock_count > 0 else "(❌ Out of Stock)"

        current_qty = user_carts[user_id].get(p_id, 0)
        if current_qty > stock_count: current_qty = stock_count
        user_carts[user_id][p_id] = current_qty

        item_total = current_qty * p_price

        text += f"🔹 <b>{p_name}</b> {stock_badge}\n   💵 စျေးနှုန်း: <b>{p_price:,}</b> MMK\n   📦 ရွေးထားသည်: <b>{current_qty}</b> ခု = <b>{item_total:,}</b> MMK\n\n"
        keyboard.append([InlineKeyboardButton(f"🟦 {p_name[:30]} ({p_price:,} MMK)", callback_data="noop")])
        keyboard.append([
            InlineKeyboardButton("➖ 1", callback_data=f"mod|{p_id}|-1|{page}"),
            InlineKeyboardButton(f"🔢 {current_qty} ခု", callback_data="noop"),
            InlineKeyboardButton("➕ 1", callback_data=f"mod|{p_id}|1|{page}")
        ])

    conn.close()

    text += f"━━━━━━━━━━━━━━━━━━\n💰 <b>စုစုပေါင်း ကျသင့်ငွေ: {total_amount:,} MMK</b> ({total_items} ခု)"
    
    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton("⬅️ ယခင်စာမျက်နှာ", callback_data=f"page_{page-1}"))
    if page < total_pages: nav_row.append(InlineKeyboardButton("နောက်စာမျက်နှာ ➡️", callback_data=f"page_{page+1}"))
    if nav_row: keyboard.append(nav_row)

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
    text = f"👤 <b>ဝယ်ယူသူ:</b> @{username} (ID: <code>{user_id}</code>)\n🛍️ <b>စုစုပေါင်း အောင်မြင်ထားသော Order:</b> {total_orders} ကြိမ်\n\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def show_admin_panel(context, chat_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='exchange_rate'")
    ex_rate = cursor.fetchone()[0]
    cursor.execute("SELECT value FROM settings WHERE key='profit_percentage'")
    profit_pct = cursor.fetchone()[0]
    conn.close()

    shop_status = "🔴 ဆိုင်ပိတ်မည် (Close)" if is_shop_open() else "🟢 ဆိုင်ဖွင့်မည် (Open)"
    keyboard = [
        [InlineKeyboardButton("🔄 Products များကို ဆွဲယူရန် (Sync API)", callback_data="sync_g2bulk")],
        [InlineKeyboardButton(f"💱 ငွေလဲနှုန်း ပြင်ရန် (1$={ex_rate})", callback_data="set_exchange"), InlineKeyboardButton(f"📈 အမြတ်ရာခိုင်နှုန်း ({profit_pct}%)", callback_data="set_profit")],
        [InlineKeyboardButton("📦 Stock စာရင်းနှင့် Code စီမံရန်", callback_data="manage_stock_menu")],
        [InlineKeyboardButton("🟨 ဈေးပြင်ရန်", callback_data="manage_price"), InlineKeyboardButton("🏦 Payment Info", callback_data="manage_payment")],
        [InlineKeyboardButton("📈 အမြတ်ငွေစာရင်း", callback_data="profit_report"), InlineKeyboardButton("📊 ယနေ့ အရောင်း", callback_data="admin_sales")],
        [InlineKeyboardButton("🏆 Top Buyers", callback_data="top_buyers"), InlineKeyboardButton("📝 Channel သို့ Post", callback_data="admin_post_channel")],
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
        
        is_g2bulk = str(pid).startswith("g2_")
        if not is_g2bulk:
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

    cursor.execute("DELETE FROM orders WHERE user_id=%s AND status='pending'", (user_id,))
    cursor.execute(
        "INSERT INTO orders (user_id, username, details, total_price, status, date, monthly_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (user_id, context.user_data.get("username", "No_Username"), details_str, total_price, "pending", date_str, next_monthly_id)
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
    text = update.message.text
    chat_id = update.effective_chat.id
    context.user_data["username"] = update.effective_user.username

    if user_id in user_states and user_states[user_id] == "waiting_player_id":
        player_id_input = text
        del user_states[user_id]
        await process_checkout(context, chat_id, user_id, msg_id=None, player_id_input=player_id_input)
        return

    if text == "👤 ကျွန်ုပ်၏ အကောင့်":
        await show_user_dashboard(update, context)
        return

    if "ဝယ်ယူမည်" in text and "မှတ်တမ်း" not in text:
        if await check_ban_and_shop(update, context): return
        if user_id in admin_states: del admin_states[user_id]
        if user_id in user_carts: del user_carts[user_id]
        if user_id in user_states: del user_states[user_id]
        await show_cart_selector(context, chat_id, user_id, page=1)
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
        
        if action == "set_exchange":
            try:
                rate = float(text)
                cursor.execute("UPDATE settings SET value=%s WHERE key='exchange_rate'", (str(rate),))
                conn.commit()
                await update.message.reply_text(f"✅ USD ငွေလဲနှုန်းကို 1$ = {rate} Ks သို့ ပြောင်းလဲလိုက်ပါပြီ။\n(ဈေးနှုန်းအသစ်များ အသက်ဝင်ရန် Admin Panel မှ 'Sync API' ကို ပြန်နှိပ်ပေးပါ။)")
                del admin_states[user_id]
                await show_admin_panel(context, chat_id)
            except: await update.message.reply_text("⚠️ ဂဏန်းဖြင့်သာ ရိုက်ထည့်ပါ။ (ဥပမာ - 4670)")

        elif action == "set_profit":
            try:
                profit_pct = float(text)
                cursor.execute("UPDATE settings SET value=%s WHERE key='profit_percentage'", (str(profit_pct),))
                conn.commit()
                await update.message.reply_text(f"✅ အမြတ်ငွေရာခိုင်နှုန်းကို {profit_pct}% သို့ ပြောင်းလဲလိုက်ပါပြီ။\n(ဈေးနှုန်းအသစ်များ အသက်ဝင်ရန် Admin Panel မှ 'Sync API' ကို ပြန်နှိပ်ပေးပါ။)")
                del admin_states[user_id]
                await show_admin_panel(context, chat_id)
            except: await update.message.reply_text("⚠️ ဂဏန်းဖြင့်သာ ရိုက်ထည့်ပါ။ (ဥပမာ - 5)")

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

    elif data.startswith("page_"):
        target_page = int(data.split("_")[1])
        await show_cart_selector(context, chat_id, user_id, message_id=msg_id, page=target_page)

    elif data.startswith("mod|"):
        parts = data.split("|")
        prod_id = parts[1]
        delta = int(parts[2])
        page = int(parts[3])
         
        is_g2bulk = str(prod_id).startswith("g2_")
        if is_g2bulk: stock_count = 99999
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
        await show_cart_selector(context, chat_id, user_id, message_id=msg_id, page=page)

    elif data == "sync_g2bulk" and user_id == ADMIN_USER_ID:
        await query.edit_message_text("🔄 API မှ Product များကို ဆွဲယူနေပါသည်... ခေတ္တစောင့်ပါ။")
        try:
            cursor.execute("SELECT value FROM settings WHERE key='exchange_rate'")
            rate = float(cursor.fetchone()[0])
            cursor.execute("SELECT value FROM settings WHERE key='profit_percentage'")
            profit_pct = float(cursor.fetchone()[0])

            headers = {"X-API-Key": G2BULK_API_KEY}
            url = "https://api.g2bulk.com/v1/products"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 404:
                url = "https://api.g2bulk.com/v1/games"
                response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                json_data = response.json()
                api_products = []
                
                if isinstance(json_data, list):
                    api_products = json_data
                elif isinstance(json_data, dict):
                    for key in ['data', 'products', 'games', 'services']:
                        if key in json_data and isinstance(json_data[key], list):
                            api_products = json_data[key]
                            break
                    if not api_products:
                        for k, v in json_data.items():
                            if isinstance(v, list):
                                api_products = v
                                break

                added_count = 0
                for p in api_products:
                    raw_id = p.get('id') or p.get('code') or p.get('service') or None
                    p_name = p.get('title') or p.get('name') or p.get('catalogue_name') or "Unknown"
                    raw_price = p.get('unit_price') or p.get('price') or p.get('rate') or 0
                    
                    if raw_id and float(raw_price) > 0:
                        p_usd = float(raw_price)
                        base_mmk = p_usd * rate
                        final_mmk = int(base_mmk + (base_mmk * (profit_pct / 100)))
                        p_id = f"g2_{raw_id}"
                        
                        cursor.execute("""
                            INSERT INTO products (id, name, price) 
                            VALUES (%s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET price = EXCLUDED.price, name = EXCLUDED.name
                        """, (p_id, str(p_name), final_mmk))
                        added_count += 1
                conn.commit()

                if added_count == 0:
                    debug_txt = str(json_data)[:800]
                    err_msg = f"⚠️ <b>API ချိတ်ဆက်မှု အောင်မြင်သော်လည်း Product မတွေ့ပါ။</b>\n\n<b>URL:</b> {url}\n<b>Data:</b>\n<code>{debug_txt}</code>"
                    await query.edit_message_text(err_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin သို့ ပြန်သွားရန်", callback_data="admin_panel")]]))
                else:
                    await query.edit_message_text(f"✅ စနစ်ထဲသို့ Product ( {added_count} ) ခုကို ဆွဲယူပြီး ဈေးနှုန်း(MMK) တွက်ချက်ထည့်သွင်းပြီးပါပြီ။\n\n📌 1$ = {rate} Ks | Profit = {profit_pct}%", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin သို့ ပြန်သွားရန်", callback_data="admin_panel")]]))
            else:
                await query.edit_message_text(f"⚠️ API Error: {response.status_code}\n{response.text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin သို့ ပြန်သွားရန်", callback_data="admin_panel")]]))
        except Exception as e:
            await query.edit_message_text(f"⚠️ ချို့ယွင်းချက်ဖြစ်ပေါ်နေပါသည်။ Error: {str(e)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin သို့ ပြန်သွားရန်", callback_data="admin_panel")]]))

    elif data == "set_exchange" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "set_exchange"}
        await query.edit_message_text("💱 <b>USD ၁ ဒေါ်လာလျှင် ရှိမည့် မြန်မာငွေလဲနှုန်း (Exchange Rate) ကို ဂဏန်းဖြင့် ရိုက်ထည့်ပါ။</b>\nဥပမာ - 4670", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data == "set_profit" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "set_profit"}
        await query.edit_message_text("📈 <b>Product တစ်ခုအတွက် ယူမည့် အမြတ်ရာခိုင်နှုန်း (%) ကို ရိုက်ထည့်ပါ။</b>\nဥပမာ - 5", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🟥 ပယ်ဖျက်မည်", callback_data="cancel_action")]]))

    elif data == "checkout_cart":
        if user_id not in user_carts or not any(user_carts[user_id].values()):
            await query.answer("အရေအတွက် ရွေးချယ်ပေးပါ။", show_alert=True)
            return

        has_g2bulk = any(str(pid).startswith("g2_") and qty > 0 for pid, qty in user_carts[user_id].items())
        
        if has_g2bulk:
            user_states[user_id] = "waiting_player_id"
            prompt_text = (
                "🎮 <b>Game Top-up များ ပါဝင်နေပါသည်။</b>\n\n"
                "ကျေးဇူးပြု၍ သင့်ရဲ့ <b>Player ID</b> (လိုအပ်ပါက <b>Server ID</b>) ကို အောက်တွင် ရိုက်ထည့်ပေးပါ။\n"
                "(ဥပမာ - <code>12345678 1234</code>)\n\n"
                "*(အကယ်၍ Gift Card သီးသန့်ဖြစ်ပါက 'No' ဟု ရိုက်ထည့်ပါ။)*"
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
        cursor.execute("SELECT id, name FROM products WHERE id NOT LIKE 'g2_%'")
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

        text = (f"📈 <b>အမြတ်ငွေစာရင်း အစီရင်ခံစာ (Manual Codes)</b>\n\n📅 <b>ဒီလအတွက် ({current_month})</b>\n🔹 300 code: <b>{month_300}</b> ခု\n🔹 1k code: <b>{month_1k}</b> ခု\n💰 <b>အမြတ်ငွေ: {m_prof:,} MMK</b>\n\n"
                f"🗓️ <b>ဒီနှစ်အတွက် ({current_year})</b>\n🔹 300 code: <b>{year_300}</b> ခု\n🔹 1k code: <b>{year_1k}</b> ခု\n💰 <b>အမြတ်ငွေ: {y_prof:,} MMK</b>")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data == "manage_price" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name, price FROM products WHERE id NOT LIKE 'g2_%'")
        products = cursor.fetchall()
        keyboard = []
        for p in products: keyboard.append([InlineKeyboardButton(f"🟨 Edit {p[1]} ({p[2]:,} MMK)", callback_data=f"editprice_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")])
        await query.edit_message_text("💲 ဘယ် Manual Product ရဲ့ ဈေးနှုန်းကို ပြင်ဆင်မလဲ -", reply_markup=InlineKeyboardMarkup(keyboard))

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
            if uid not in buyer_stats: buyer_stats[uid] = {"username": uname, "spent": 0, "qty": 0}
            buyer_stats[uid]["spent"] += price
            for item in details_str.split(", "):
                if ":" in item:
                    buyer_stats[uid]["qty"] += int(item.split(":")[1])

        sorted_buyers = sorted(buyer_stats.items(), key=lambda x: x[1]["spent"], reverse=True)[:5]
        text = f"🏆 <b>Top 5 Buyers ({current_month}):</b>\n\n"
        if not sorted_buyers: text += "ဝယ်ယူသူ မရှိသေးပါ။"
        else:
            for i, (uid, stats) in enumerate(sorted_buyers):
                uname = f"@{stats['username']}" if stats['username'] and stats['username'] != "No_Username" else f"ID: <code>{uid}</code>"
                text += f"<b>{i+1}. {uname}</b>\n   🔹 ဝယ်ယူမှု: {stats['qty']} ကြိမ်\n   💰 စုစုပေါင်း: <b>{stats['spent']:,}</b> MMK\n\n"
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
                uid_str = ""
                if " | UID: " in details:
                    details_part, uid_str = details.split(" | UID: ")
                    items = details_part.split(", ")
                else:
                    items = details.split(", ")
                    
                codes_to_send = []
                insufficient = False
                api_errors = []
                
                for item in items:
                    pid, qty = item.split(":")
                    qty = int(qty)
                    
                    is_g2bulk = str(pid).startswith("g2_")
                    if is_g2bulk:
                        raw_id = pid.replace("g2_", "")
                        cursor.execute("SELECT name FROM products WHERE id=%s", (pid,))
                        prod_name = cursor.fetchone()[0]
                        
                        uid_parts = uid_str.strip().split()
                        p_id_val = uid_parts[0] if len(uid_parts) > 0 and uid_parts[0].lower() != 'no' else ""
                        s_id_val = uid_parts[1] if len(uid_parts) > 1 else ""
                        
                        for _ in range(qty):
                            payload = {
                                "catalogue_name": prod_name,
                                "player_id": p_id_val,
                                "server_id": s_id_val
                            }
                            headers = {"X-API-Key": G2BULK_API_KEY, "Content-Type": "application/json"}
                            try:
                                order_url = f"https://api.g2bulk.com/v1/games/{raw_id}/order"
                                resp = requests.post(order_url, headers=headers, json=payload)
                                
                                if resp.status_code in [200, 201]:
                                    codes_to_send.append(f"🔸 {prod_name} : အောင်မြင်စွာ ဖြည့်သွင်းပြီးပါပြီ။")
                                else:
                                    api_errors.append(f"❌ {prod_name} Error: {resp.text}")
                            except Exception as e:
                                api_errors.append(f"❌ {prod_name} API Fail: {str(e)}")
                    else:
                        cursor.execute("SELECT id, code FROM stock WHERE product_id=%s LIMIT %s", (pid, qty))
                        rows = cursor.fetchall()
                        if len(rows) < qty:
                            insufficient = True
                            break
                        for r in rows:
                            codes_to_send.append(f"🔸 {pid.upper()} : <code>{r[1]}</code>")
                            cursor.execute("DELETE FROM stock WHERE id=%s", (r[0],))
                        
                if insufficient:
                    msg = (query.message.caption or query.message.text) + "\n\n⚠️ <b>Stock မလောက်ပါ! Admin Panel မှ Code အသစ် အရင်ဖြည့်ပါ။</b>"
                    await (query.edit_message_caption if query.message.caption else query.edit_message_text)(msg, parse_mode="HTML")
                
                elif api_errors: 
                    cursor.execute("UPDATE orders SET status='accepted' WHERE id=%s", (order_id,))
                    conn.commit()
                    
                    codes_text = "\n".join(codes_to_send) if codes_to_send else "Top-up တင်နေဆဲဖြစ်ပါသည်။ (Admin မှ ဆက်လက်စစ်ဆေးပေးပါမည်)"
                    # Buyer ကိုပြမည့်စာတွင် G2Bulk ဟူသော စကားလုံး လုံးဝမပါဝင်စေရန် ပြင်ဆင်ထားပါသည်
                    try: await context.bot.send_message(chat_id=buyer_id, text=f"✅ <b>သင့်ရဲ့ Order #{display_order_id} ကို လက်ခံရရှိပါသည်။</b>\n\n🎁 <b>Status:</b>\n{codes_text}\n*(Server ကြန့်ကြာမှုကြောင့် အနည်းငယ် စောင့်ဆိုင်းရနိုင်ပါသည်။)*", parse_mode="HTML")
                    except: pass
                    
                    error_msg = "\n".join(api_errors)
                    msg = (query.message.caption or query.message.text) + f"\n\n❌ <b>API အလိုအလျောက်ချိတ်ဆက်မှု ကျရှုံးပါသည်!</b>\n<i>(Customer ထံသို့ Manual သွားရောက်ဖြည့်သွင်းပေးပါ။)</i>\n\n<b>Errors:</b>\n<code>{error_msg}</code>"
                    await (query.edit_message_caption if query.message.caption else query.edit_message_text)(msg, parse_mode="HTML")

                else: 
                    cursor.execute("UPDATE orders SET status='accepted' WHERE id=%s", (order_id,))
                    conn.commit()
                    codes_text = "\n".join(codes_to_send)
                    try: await context.bot.send_message(chat_id=buyer_id, text=f"✅ <b>သင့်ရဲ့ Order #{display_order_id} အောင်မြင်ပါတယ်။</b>\n\n🎁 <b>သင်ဝယ်ယူထားသော Codes/Top-ups:</b>\n{codes_text}", parse_mode="HTML")
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
    uid_info = ""
    
    if " | UID: " in details:
        details_part, uid_str = details.split(" | UID: ")
        items = details_part.split(", ")
        uid_info = f"\n🎮 UID Info: <code>{uid_str}</code>"
    else:
        items = details.split(", ")
        
    for item in items:
        if ":" in item:
            pid, q = item.split(":")
            display_details.append(f"🔹 {pid} ( {q} ) ခု")
    
    username = context.user_data.get("username", "No_Username")
    caption = f"🔔 <b>New Order #{display_order_id}</b>\n👤 Buyer: @{username} (ID: <code>{user_id}</code>)\n📦 Details:\n{chr(10).join(display_details)}{uid_info}\n💰 Total: {total:,} MMK"
    
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
