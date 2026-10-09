import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- CONFIGURATIONS ---
TELEGRAM_BOT_TOKEN = "8969723597:AAFaDiVSxy6TTNipwMWm5hUs2v_YEkrKBmM"
ADMIN_USER_ID = 6069279282
DATABASE_URL = "postgresql://neondb_owner:npg_Xv5HWOA4hxPV@ep-long-dew-b4z0dkg4-pooler.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT, price INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock (id SERIAL PRIMARY KEY, product_id TEXT, code TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT, details TEXT, total_price INTEGER, status TEXT, date TEXT)''')
    
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('smile_300', 'Smile One 300 BRL', 30000) ON CONFLICT (id) DO NOTHING")
    cursor.execute("INSERT INTO products (id, name, price) VALUES ('smile_1k', 'Smile One 1K BRL', 95000) ON CONFLICT (id) DO NOTHING")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('payment_info', 'KBZ Pay: 09XXXXX (Name: U XXX)\\nWave Pay: 09XXXXX') ON CONFLICT (key) DO NOTHING")
    conn.commit()
    conn.close()

init_db()

# Memory tracking
user_carts = {}
admin_states = {}

def get_main_keyboard(user_id):
    keyboard = [
        [KeyboardButton("🛒 ဝယ်ယူမည်"), KeyboardButton("🧾 ဝယ်ယူမှုမှတ်တမ်း")]
    ]
    if user_id == ADMIN_USER_ID:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
    conn.commit()
    conn.close()

    if user_id in admin_states:
        del admin_states[user_id]
    
    welcome_text = "🌟 <b>Digital Product Shop မှ လှိုက်လှဲစွာ ကြိုဆိုပါတယ်။</b> 🌟\n\nအောက်ပါ Menu ခလုတ်များကို အသုံးပြု၍ အလွယ်တကူ ဝယ်ယူနိုင်ပါသည်။ 👇"
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(user_id))

async def show_shop_menu(context, chat_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products")
    products = cursor.fetchall()
    keyboard = []
    for p in products:
        cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (p[0],))
        stock_count = cursor.fetchone()[0]
        # Professional UI for product buttons
        keyboard.append([InlineKeyboardButton(f"🟢 {p[1]} - {p[2]:,} MMK (Stock: {stock_count})", callback_data=f"buy_{p[0]}")])
    conn.close()
    
    text = "🛒 <b>ဝယ်ယူလိုသော Product ကို ရွေးချယ်ပါ။</b>"
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")

async def show_orders(context, chat_id, user_id, message_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, details, total_price, status, date FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 5", (user_id,))
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        text = "⚠️ သင် ဝယ်ယူထားသော မှတ်တမ်း မရှိသေးပါ။"
    else:
        text = "🧾 <b>နောက်ဆုံး ဝယ်ယူထားသော ၅ ကြိမ်:</b>\n\n"
        for o in orders:
            status_emoji = "✅" if o[3] == "accepted" else ("❌" if o[3] == "rejected" else "⏳")
            text += f"🔖 Order #{o[0]} | 💰 {o[2]:,} MMK\n{status_emoji} Status: {o[3].upper()} | 📅 {o[4]}\n\n"
            
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

async def show_admin_panel(context, chat_id, message_id=None):
    keyboard = [
        [InlineKeyboardButton("➕ Stock ထည့်ရန်", callback_data="manage_stock"), InlineKeyboardButton("💲 ဈေးပြင်ရန်", callback_data="manage_price")],
        [InlineKeyboardButton("🏦 Payment Info ပြင်ရန်", callback_data="manage_payment")],
        [InlineKeyboardButton("📊 ယနေ့ အရောင်း", callback_data="admin_sales"), InlineKeyboardButton("🏆 Top Buyers", callback_data="top_buyers")],
        [InlineKeyboardButton("👀 Code များကြည့်ရန်", callback_data="view_codes"), InlineKeyboardButton("🗑️ Code ဖျက်ရန်", callback_data="remove_code")],
        [InlineKeyboardButton("📢 ကြေညာချက်ပို့ရန် (Broadcast)", callback_data="admin_broadcast")]
    ]
    text = "👑 <b>Admin Management Panel</b>\n\nလုပ်ဆောင်လိုသော အရာကို အောက်ပါခလုတ်များမှ ရွေးချယ်ပါ:"
    reply_markup = InlineKeyboardMarkup(keyboard)
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    chat_id = update.effective_chat.id

    if "ဝယ်ယူမည်" in text and "မှတ်တမ်း" not in text:
        if user_id in admin_states: del admin_states[user_id]
        await show_shop_menu(context, chat_id)
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
            await update.message.reply_text(f"✅ Product <code>{prod_id}</code> အတွက် Code အသစ် {added} ခု အောင်မြင်စွာ သွင်းပြီးပါပြီ။", parse_mode="HTML")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        elif action == "set_price":
            prod_id = state["product_id"]
            try:
                price = int(text)
                cursor.execute("UPDATE products SET price=%s WHERE id=%s", (price, prod_id))
                conn.commit()
                await update.message.reply_text(f"✅ Product <code>{prod_id}</code> ၏ ဈေးနှုန်းကို {price:,} MMK သို့ ပြောင်းလဲလိုက်ပါပြီ။", parse_mode="HTML")
                del admin_states[user_id]
                await show_admin_panel(context, chat_id)
            except ValueError:
                cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
                await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ ဂဏန်း (Numbers) သာ ရိုက်ထည့်ပါ။", reply_markup=cancel_btn)
                
        elif action == "set_payment":
            cursor.execute("UPDATE settings SET value=%s WHERE key='payment_info'", (text,))
            conn.commit()
            await update.message.reply_text("✅ Payment Info ကို အောင်မြင်စွာ ပြောင်းလဲလိုက်ပါပြီ။")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        elif action == "broadcast":
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()
            success_count = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u[0], text=f"📢 <b>ကြေညာချက်:</b>\n\n{text}", parse_mode="HTML")
                    success_count += 1
                except:
                    pass
            await update.message.reply_text(f"✅ ကြေညာချက်ကို လူ ( {success_count} ) ဦးထံ အောင်မြင်စွာ ပို့ဆောင်ပြီးပါပြီ။")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        elif action == "remove_code":
            exact_code = text.strip()
            cursor.execute("SELECT id, product_id FROM stock WHERE code=%s", (exact_code,))
            found = cursor.fetchone()
            
            if found:
                cursor.execute("DELETE FROM stock WHERE id=%s", (found[0],))
                conn.commit()
                await update.message.reply_text(f"✅ Product <code>{found[1]}</code> ၏ Code <code>{exact_code}</code> ကို အောင်မြင်စွာ ဖျက်လိုက်ပါပြီ။", parse_mode="HTML")
            else:
                cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
                await update.message.reply_text("⚠️ အဆိုပါ Code မရှိပါ။ အတိအကျ မှန်ကန်အောင် ပြန်စစ်ပါ။", reply_markup=cancel_btn)
                return 
                
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        conn.close()
        return

    await update.message.reply_text("ကျေးဇူးပြု၍ အောက်ပါ Menu ခလုတ်များကိုသာ အသုံးပြုပါ။ 👇", reply_markup=get_main_keyboard(user_id))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = query.message.chat.id
    msg_id = query.message.message_id

    conn = get_db()
    cursor = conn.cursor()

    if data == "cancel_action":
        if user_id in admin_states:
            del admin_states[user_id]
        await query.edit_message_text("🚫 လုပ်ဆောင်ချက်ကို ဖျက်သိမ်းလိုက်ပါပြီ။")
        if user_id == ADMIN_USER_ID:
            await show_admin_panel(context, chat_id)

    elif data == "shop_menu":
        await show_shop_menu(context, chat_id, msg_id)
        
    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
        if user_id in admin_states:
            del admin_states[user_id]
        await show_admin_panel(context, chat_id, msg_id)

    elif data.startswith("buy_"):
        prod_id = data.replace("buy_", "")
        
        # 1. Feature: Check Stock Limit
        cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (prod_id,))
        total_stock = cursor.fetchone()[0]
        
        if user_id not in user_carts:
            user_carts[user_id] = {}
            
        current_qty = user_carts[user_id].get(prod_id, 0)
        
        if current_qty >= total_stock:
            await query.answer(f"⚠️ Stock {total_stock} ခုသာ ကျန်ပါတော့သည်။ ထပ်မံထည့်၍မရပါ။", show_alert=True)
        else:
            user_carts[user_id][prod_id] = current_qty + 1
            keyboard = [
                [InlineKeyboardButton("🛍️ ဆက်ဝယ်မည်", callback_data="shop_menu")],
                [InlineKeyboardButton("💳 ငွေရှင်းမည် (Checkout)", callback_data="checkout")]
            ]
            await query.edit_message_text("✅ ခြင်းတောင်းထဲသို့ ထည့်လိုက်ပါပြီ။ ဆက်လုပ်မည့် အဆင့်ကို ရွေးပါ။", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "checkout":
        if user_id not in user_carts or not user_carts[user_id]:
            await query.edit_message_text("🛒 ခြင်းတောင်းထဲမှာ ဘာမှမရှိပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Shop သို့ ပြန်သွားရန်", callback_data="shop_menu")]]))
            return
        
        total_price = 0
        cart_text = "🛒 <b>သင့်ရဲ့ Order စာရင်း:</b>\n\n"
        details = []
        for pid, qty in user_carts[user_id].items():
            cursor.execute("SELECT name, price FROM products WHERE id=%s", (pid,))
            prod = cursor.fetchone()
            price = prod[1] * qty
            total_price += price
            cart_text += f"🔹 {prod[0]} x {qty} ခု = {price:,} MMK\n"
            details.append(f"{pid}:{qty}")
            
        cart_text += f"\n💰 <b>စုစုပေါင်း ကျသင့်ငွေ - {total_price:,} MMK</b>\n\n"
        
        cursor.execute("SELECT value FROM settings WHERE key='payment_info'")
        payment_info = cursor.fetchone()[0]
        cart_text += f"🏦 <b>ငွေလွှဲရမည့် အကောင့်များ:</b>\n<code>{payment_info}</code>\n\n"
        cart_text += "⚠️ <b>အရေးကြီး:</b> ကျေးဇူးပြု၍ ငွေလွှဲပြေစာ (Screenshot) ကို ဤနေရာသို့ ပို့ပေးပါ။ Admin မှ စစ်ဆေးပြီး Code များ ချက်ချင်း ပို့ပေးပါမည်။"
        
        details_str = ", ".join(details)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO orders (user_id, username, details, total_price, status, date) VALUES (%s, %s, %s, %s, %s, %s)", 
                       (user_id, update.effective_user.username, details_str, total_price, "pending", date_str))
        conn.commit()
        
        user_carts[user_id] = {} 
        await query.edit_message_text(cart_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="shop_menu")]]))

    elif data == "manage_stock" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name FROM products")
        products = cursor.fetchall()
        keyboard = []
        for p in products:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=%s", (p[0],))
            count = cursor.fetchone()[0]
            keyboard.append([InlineKeyboardButton(f"➕ Add {p[1]} (ကျန် {count})", callback_data=f"addcode_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")])
        await query.edit_message_text("📦 ဘယ် Product အတွက် Code အသစ်ထည့်မလဲ ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_price" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name, price FROM products")
        products = cursor.fetchall()
        keyboard = []
        for p in products:
            keyboard.append([InlineKeyboardButton(f"💲 Edit {p[1]} ({p[2]:,} MMK)", callback_data=f"editprice_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")])
        await query.edit_message_text("💲 ဘယ် Product ရဲ့ ဈေးနှုန်းကို ပြင်ဆင်မလဲ ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_payment" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "set_payment"}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
        await query.edit_message_text("🏦 <b>Payment Info အသစ်ကို အောက်တွင် ရိုက်ထည့်ပါ။</b>\n\n(ဥပမာ - KBZ Pay: 09...)", parse_mode="HTML", reply_markup=cancel_btn)

    elif data == "admin_broadcast" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "broadcast"}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
        await query.edit_message_text("📢 <b>ပို့လိုသော ကြေညာချက် စာသားများကို ရိုက်ထည့်ပါ။</b>\n(ဤစာများကို အသုံးပြုသူ အားလုံးထံသို့ ပေးပို့သွားမည်ဖြစ်ပါသည်)", parse_mode="HTML", reply_markup=cancel_btn)

    elif data == "top_buyers" and user_id == ADMIN_USER_ID:
        # 2. Feature: Top 5 Buyers based on spent amount
        current_month = datetime.now().strftime("%Y-%m")
        cursor.execute("SELECT user_id, username, SUM(total_price) as spent FROM orders WHERE status='accepted' AND date LIKE %s GROUP BY user_id, username ORDER BY spent DESC LIMIT 5", (f"{current_month}%",))
        top_buyers = cursor.fetchall()
        
        text = f"🏆 <b>ဒီလအတွက် Top 5 Buyers ({current_month}):</b>\n\n"
        if not top_buyers:
            text += "ဝယ်ယူသူ မရှိသေးပါ။"
        else:
            for i, buyer in enumerate(top_buyers):
                uname = f"@{buyer[1]}" if buyer[1] and buyer[1] != "No_Username" else f"ID: {buyer[0]}"
                text += f"{i+1}. {uname} - 💰 {buyer[2]:,} MMK\n"
                
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data == "view_codes" and user_id == ADMIN_USER_ID:
        # 3. Feature: View all available codes
        cursor.execute("SELECT product_id, code FROM stock ORDER BY product_id")
        stocks = cursor.fetchall()
        
        if not stocks:
            text = "📦 လက်ရှိတွင် Code တစ်ခုမှ မရှိပါ။"
        else:
            text = "👀 <b>လက်ရှိ Code များအားလုံး:</b>\n\n"
            current_prod = ""
            for s in stocks:
                if s[0] != current_prod:
                    text += f"\n💎 <b>{s[0]}</b>:\n"
                    current_prod = s[0]
                text += f"<code>{s[1]}</code>\n"
                
        if len(text) > 4000:
            text = text[:4000] + "\n... (စာလုံးရေများနေသဖြင့် အချို့ကိုဖြတ်ထားသည်)"
            
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data == "remove_code" and user_id == ADMIN_USER_ID:
        # 4. Feature: Remove specific code
        admin_states[user_id] = {"action": "remove_code"}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
        await query.edit_message_text("🗑️ <b>ဖျက်လိုသော Code စာသားကို အတိအကျ ရိုက်ထည့်ပါ။</b>\n\n(Code များကြည့်ရန် မှ Code ကို Copy ကူးပြီး ဒီမှာ Paste ချပေးပါ)", parse_mode="HTML", reply_markup=cancel_btn)

    elif data.startswith("addcode_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("addcode_", "")
        admin_states[user_id] = {"action": "add_code", "product_id": prod_id}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
        await query.edit_message_text(f"✏️ <code>{prod_id}</code> အတွက် Code အသစ်များကို ရိုက်ထည့်ပါ။\n\n(အများကြီး တစ်ခါတည်း ထည့်လိုပါက တစ်ကြောင်းလျှင် တစ်ခုစီ ခွဲ၍ ရိုက်ပို့ပါ)", parse_mode="HTML", reply_markup=cancel_btn)

    elif data.startswith("editprice_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("editprice_", "")
        admin_states[user_id] = {"action": "set_price", "product_id": prod_id}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 ပယ်ဖျက်မည် (Cancel)", callback_data="cancel_action")]])
        await query.edit_message_text(f"💲 <code>{prod_id}</code> အတွက် ဈေးနှုန်းအသစ်ကို ဂဏန်းဖြင့် ရိုက်ထည့်ပါ။\n\n(ဥပမာ - 35000)", parse_mode="HTML", reply_markup=cancel_btn)

    elif data == "admin_sales" and user_id == ADMIN_USER_ID:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE status='accepted' AND date LIKE %s", (f"{today}%",))
        sales = cursor.fetchone()
        count = sales[0] if sales[0] else 0
        total = sales[1] if sales[1] else 0
        
        text = f"📊 <b>ယနေ့ အရောင်းစာရင်း ({today}):</b>\n\n✅ ရောင်းရသော အရေအတွက်: {count} ကြိမ်\n💰 စုစုပေါင်း ဝင်ငွေ: {total:,} MMK\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="admin_panel")]]))

    elif data.startswith("accept_") and user_id == ADMIN_USER_ID:
        order_id = int(data.split("_")[1])
        cursor.execute("SELECT user_id, details, status FROM orders WHERE id=%s", (order_id,))
        order = cursor.fetchone()
        
        if order and order[2] == "pending":
            buyer_id, details = order[0], order[1]
            items = details.split(", ")
            codes_to_send = []
            insufficient = False
            
            for item in items:
                prod_id, qty_str = item.split(":")
                qty = int(qty_str)
                cursor.execute("SELECT id, code FROM stock WHERE product_id=%s LIMIT %s", (prod_id, qty))
                rows = cursor.fetchall()
                if len(rows) < qty:
                    insufficient = True
                    break
                for r in rows:
                    codes_to_send.append(f"🔸 {prod_id.upper()} : <code>{r[1]}</code>")
                    cursor.execute("DELETE FROM stock WHERE id=%s", (r[0],))
                    
            if insufficient:
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n⚠️ <b>Stock မလောက်ပါ! Admin Panel မှ Code အသစ် အရင်ဖြည့်ပါ။</b>", parse_mode="HTML")
            else:
                cursor.execute("UPDATE orders SET status='accepted' WHERE id=%s", (order_id,))
                codes_text = "\n".join(codes_to_send)
                
                # Send to Buyer
                await context.bot.send_message(chat_id=buyer_id, text=f"✅ <b>သင့်ရဲ့ Order #{order_id} အောင်မြင်ပါတယ်။</b>\n\n🎁 <b>သင်ဝယ်ယူထားသော Codes များ:</b>\n{codes_text}\n\nအားပေးမှုကို ကျေးဇူးတင်ပါတယ်။", parse_mode="HTML")
                
                # 5. Feature: Update Admin Panel Message with sent codes detail
                admin_caption = f"{query.message.caption}\n\n✅ <b>Order Accepted & Codes Sent!</b>\n\n📦 <b>ပို့လိုက်သော Codes များ:</b>\n{codes_text}"
                await query.edit_message_caption(caption=admin_caption, parse_mode="HTML")
        else:
             await query.answer("ဤ Order အား ဖြေရှင်းပြီးပါပြီ။", show_alert=True)

    elif data.startswith("reject_") and user_id == ADMIN_USER_ID:
        order_id = int(data.split("_")[1])
        cursor.execute("SELECT user_id, status FROM orders WHERE id=%s", (order_id,))
        order = cursor.fetchone()
        if order and order[1] == "pending":
            cursor.execute("UPDATE orders SET status='rejected' WHERE id=%s", (order_id,))
            await context.bot.send_message(chat_id=order[0], text=f"❌ <b>သင့်ရဲ့ Order #{order_id} ကို Admin မှ ငြင်းပယ်လိုက်ပါသည်။</b>\n\n(အကြောင်းရင်း - ငွေလွှဲပြေစာ မမှန်ကန်၍ သို့မဟုတ် လက်ကျန် Stock ကုန်နေ၍ ဖြစ်နိုင်ပါသည်)", parse_mode="HTML")
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ <b>Order Rejected!</b>", parse_mode="HTML")
        else:
            await query.answer("ဤ Order အား ဖြေရှင်းပြီးပါပြီ။", show_alert=True)
            
    conn.commit()
    conn.close()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, details, total_price FROM orders WHERE user_id=%s AND status='pending' ORDER BY id DESC LIMIT 1", (user_id,))
    order = cursor.fetchone()
    
    if order:
        order_id, details, total = order
        photo_file = update.message.photo[-1].file_id
        
        keyboard = [
            [InlineKeyboardButton("✅ လက်ခံမည် (Accept)", callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton("❌ ငြင်းပယ်မည် (Reject)", callback_data=f"reject_{order_id}")]
        ]
        
        username = update.effective_user.username if update.effective_user.username else "No_Username"
        caption = f"🔔 <b>New Order #{order_id}</b>\n👤 Buyer: @{username} (ID: {user_id})\n📦 Details: {details}\n💰 Total: {total:,} MMK"
        
        try:
            await context.bot.send_photo(chat_id=ADMIN_USER_ID, photo=photo_file, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            await update.message.reply_text("✅ ငွေလွှဲပြေစာ လက်ခံရရှိပါပြီ။ Admin မှ စစ်ဆေးပြီးပါက Code များကို ဤနေရာသို့ ချက်ချင်း ပို့ပေးပါမည်။", reply_markup=get_main_keyboard(user_id))
        except Exception as e:
            await update.message.reply_text("⚠️ စနစ် ချို့ယွင်းနေပါသည်။", reply_markup=get_main_keyboard(user_id))
            print(f"Error: {e}")
    else:
        await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ အောက်ပါ '🛒 ဝယ်ယူမည်' ကို နှိပ်၍ Product အရင်ရွေးချယ်ပြီးမှ ပြေစာပို့ပေးပါ။", reply_markup=get_main_keyboard(user_id))
        
    conn.close()

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    application.run_polling()
