import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- CONFIGURATIONS ---
TELEGRAM_BOT_TOKEN = "8969723597:AAH1A0p6LcoLdk71MKSrA3Avz6yAR2vQ_QM"
ADMIN_USER_ID = 6069279282

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT, price INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, code TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, details TEXT, total_price INTEGER, status TEXT, date TEXT)''')
    
    cursor.execute("INSERT OR IGNORE INTO products VALUES ('smile_300', 'Smile One 300 BRL', 30000)")
    cursor.execute("INSERT OR IGNORE INTO products VALUES ('smile_1k', 'Smile One 1K BRL', 95000)")
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('payment_info', 'KBZ Pay: 09XXXXX (Name: U XXX)\\nWave Pay: 09XXXXX')")
    conn.commit()
    conn.close()

init_db()

# Memory tracking
user_carts = {}
admin_states = {}

# --- PERSISTENT BOTTOM KEYBOARD ---
def get_main_keyboard(user_id):
    keyboard = [
        [KeyboardButton("🛒 ကတ်ဝယ်ယူမည် (Shop)"), KeyboardButton("🧾 ဝယ်ယူမှုမှတ်တမ်း")]
    ]
    if user_id == ADMIN_USER_ID:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admin_states:
        del admin_states[user_id]
    
    welcome_text = "🌟 **Digital Product Shop မှ လှိုက်လှဲစွာ ကြိုဆိုပါတယ်။** 🌟\n\nအောက်ပါ Menu ခလုတ်များကို အသုံးပြု၍ အလွယ်တကူ ဝယ်ယူနိုင်ပါသည်။ 👇"
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# --- HELPER FUNCTIONS ---
async def show_shop_menu(context, chat_id, message_id=None):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products")
    products = cursor.fetchall()
    keyboard = []
    for p in products:
        cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=?", (p[0],))
        stock_count = cursor.fetchone()[0]
        keyboard.append([InlineKeyboardButton(f"💎 {p[1]} - {p[2]} MMK (Stock: {stock_count})", callback_data=f"buy_{p[0]}")])
    conn.close()
    
    text = "🛒 **ဝယ်ယူလိုသော Product ကို ရွေးချယ်ပါ။**"
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_orders(context, chat_id, user_id, message_id=None):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, details, total_price, status, date FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        text = "⚠️ သင် ဝယ်ယူထားသော မှတ်တမ်း မရှိသေးပါ။"
    else:
        text = "🧾 **နောက်ဆုံး ဝယ်ယူထားသော ၅ ကြိမ်:**\n\n"
        for o in orders:
            status_emoji = "✅" if o[3] == "accepted" else ("❌" if o[3] == "rejected" else "⏳")
            text += f"🔖 Order #{o[0]} | 💰 {o[2]} MMK\n{status_emoji} Status: {o[3].upper()} | 📅 {o[4]}\n\n"
            
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

async def show_admin_panel(context, chat_id, message_id=None):
    keyboard = [
        [InlineKeyboardButton("📦 Stock ထည့်ရန် (Add Codes)", callback_data="manage_stock")],
        [InlineKeyboardButton("💵 ဈေးနှုန်း ပြင်ဆင်ရန်", callback_data="manage_price")],
        [InlineKeyboardButton("🏦 Payment Info ပြင်ရန်", callback_data="manage_payment")],
        [InlineKeyboardButton("📊 ယနေ့ အရောင်းစာရင်း", callback_data="admin_sales")]
    ]
    text = "👑 **Admin Management Panel**\n\nလုပ်ဆောင်လိုသော အရာကို အောက်ပါခလုတ်များမှ ရွေးချယ်ပါ:"
    reply_markup = InlineKeyboardMarkup(keyboard)
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")

# --- TEXT HANDLER (BOTTOM BUTTONS & ADMIN INPUT) ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    chat_id = update.effective_chat.id

    # Persistent Bottom Button Clicks
    if text == "🛒 ကတ်ဝယ်ယူမည် (Shop)":
        if user_id in admin_states: del admin_states[user_id]
        await show_shop_menu(context, chat_id)
        return
    elif text == "🧾 ဝယ်ယူမှုမှတ်တမ်း":
        if user_id in admin_states: del admin_states[user_id]
        await show_orders(context, chat_id, user_id)
        return
    elif text == "👑 Admin Panel" and user_id == ADMIN_USER_ID:
        if user_id in admin_states: del admin_states[user_id]
        await show_admin_panel(context, chat_id)
        return

    # If Admin is typing input (Code, Price, etc)
    if user_id in admin_states and user_id == ADMIN_USER_ID:
        state = admin_states[user_id]
        action = state["action"]
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        
        if action == "add_code":
            prod_id = state["product_id"]
            codes = text.split('\n')
            added = 0
            for code in codes:
                if code.strip():
                    cursor.execute("INSERT INTO stock (product_id, code) VALUES (?, ?)", (prod_id, code.strip()))
                    added += 1
            conn.commit()
            await update.message.reply_text(f"✅ Product `{prod_id}` အတွက် Code အသစ် {added} ခု အောင်မြင်စွာ သွင်းပြီးပါပြီ။", parse_mode="Markdown")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        elif action == "set_price":
            prod_id = state["product_id"]
            try:
                price = int(text)
                cursor.execute("UPDATE products SET price=? WHERE id=?", (price, prod_id))
                conn.commit()
                await update.message.reply_text(f"✅ Product `{prod_id}` ၏ ဈေးနှုန်းကို {price} MMK သို့ ပြောင်းလဲလိုက်ပါပြီ။", parse_mode="Markdown")
                del admin_states[user_id]
                await show_admin_panel(context, chat_id)
            except ValueError:
                cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel (ဖျက်သိမ်းမည်)", callback_data="cancel_action")]])
                await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ ဂဏန်း (Numbers) သာ ရိုက်ထည့်ပါ။ သို့မဟုတ် မပြင်တော့ပါက အောက်ပါ Cancel ကို နှိပ်ပါ။", reply_markup=cancel_btn)
                
        elif action == "set_payment":
            cursor.execute("UPDATE settings SET value=? WHERE key='payment_info'", (text,))
            conn.commit()
            await update.message.reply_text("✅ Payment Info ကို အောင်မြင်စွာ ပြောင်းလဲလိုက်ပါပြီ။")
            del admin_states[user_id]
            await show_admin_panel(context, chat_id)
            
        conn.close()
        return

    # Normal user typing random text
    await update.message.reply_text("ကျေးဇူးပြု၍ အောက်ပါ Menu ခလုတ်များကိုသာ အသုံးပြုပါ။ 👇", reply_markup=get_main_keyboard(user_id))

# --- INLINE BUTTONS HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = query.message.chat.id
    msg_id = query.message.message_id

    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()

    # Cancel any action
    if data == "cancel_action":
        if user_id in admin_states:
            del admin_states[user_id]
        await query.edit_message_text("❌ လုပ်ဆောင်ချက်ကို ဖျက်သိမ်းလိုက်ပါပြီ။")
        if user_id == ADMIN_USER_ID:
            await show_admin_panel(context, chat_id)

    elif data == "shop_menu":
        await show_shop_menu(context, chat_id, msg_id)

    elif data.startswith("buy_"):
        prod_id = data.replace("buy_", "")
        if user_id not in user_carts:
            user_carts[user_id] = {}
        if prod_id in user_carts[user_id]:
            user_carts[user_id][prod_id] += 1
        else:
            user_carts[user_id][prod_id] = 1
        
        keyboard = [
            [InlineKeyboardButton("🛒 ဆက်ဝယ်မည်", callback_data="shop_menu")],
            [InlineKeyboardButton("💳 ငွေရှင်းမည် (Checkout)", callback_data="checkout")]
        ]
        await query.edit_message_text("✅ ခြင်းတောင်းထဲသို့ ထည့်လိုက်ပါပြီ။ ဆက်လုပ်မည့် အဆင့်ကို ရွေးပါ။", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "checkout":
        if user_id not in user_carts or not user_carts[user_id]:
            await query.edit_message_text("🛒 ခြင်းတောင်းထဲမှာ ဘာမှမရှိပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Shop သို့ ပြန်သွားရန်", callback_data="shop_menu")]]))
            return
        
        total_price = 0
        cart_text = "🛒 **သင့်ရဲ့ Order စာရင်း:**\n\n"
        details = []
        for pid, qty in user_carts[user_id].items():
            cursor.execute("SELECT name, price FROM products WHERE id=?", (pid,))
            prod = cursor.fetchone()
            price = prod[1] * qty
            total_price += price
            cart_text += f"🔹 {prod[0]} x {qty} ခု = {price} MMK\n"
            details.append(f"{pid}:{qty}")
            
        cart_text += f"\n💰 **စုစုပေါင်း ကျသင့်ငွေ - {total_price} MMK**\n\n"
        
        cursor.execute("SELECT value FROM settings WHERE key='payment_info'")
        payment_info = cursor.fetchone()[0]
        cart_text += f"🏦 **ငွေလွှဲရမည့် အကောင့်များ:**\n`{payment_info}`\n\n"
        cart_text += "⚠️ **အရေးကြီး:** ကျေးဇူးပြု၍ ငွေလွှဲပြေစာ (Screenshot) ကို ဤနေရာသို့ ပို့ပေးပါ။ Admin မှ စစ်ဆေးပြီး Code များ ချက်ချင်း ပို့ပေးပါမည်။"
        
        details_str = ", ".join(details)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO orders (user_id, username, details, total_price, status, date) VALUES (?, ?, ?, ?, ?, ?)", 
                       (user_id, update.effective_user.username, details_str, total_price, "pending", date_str))
        conn.commit()
        
        user_carts[user_id] = {} # Clear cart
        await query.edit_message_text(cart_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ပယ်ဖျက်မည် (Cancel)", callback_data="shop_menu")]]))

    # Admin sub-menus
    elif data == "manage_stock" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name FROM products")
        products = cursor.fetchall()
        keyboard = []
        for p in products:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=?", (p[0],))
            count = cursor.fetchone()[0]
            keyboard.append([InlineKeyboardButton(f"➕ Add {p[1]} (ကျန် {count} ခု)", callback_data=f"addcode_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
        await query.edit_message_text("📦 ဘယ် Product အတွက် Code အသစ်ထည့်မလဲ ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_price" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name, price FROM products")
        products = cursor.fetchall()
        keyboard = []
        for p in products:
            keyboard.append([InlineKeyboardButton(f"💵 Edit {p[1]} ({p[2]} MMK)", callback_data=f"editprice_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
        await query.edit_message_text("💵 ဘယ် Product ရဲ့ ဈေးနှုန်းကို ပြင်ဆင်မလဲ ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_payment" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "set_payment"}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel (ဖျက်သိမ်းမည်)", callback_data="cancel_action")]])
        await query.edit_message_text("🏦 **Payment Info အသစ်ကို အောက်တွင် ရိုက်ထည့်ပါ။**\n\n(ဥပမာ - KBZ Pay: 09...)", parse_mode="Markdown", reply_markup=cancel_btn)

    elif data.startswith("addcode_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("addcode_", "")
        admin_states[user_id] = {"action": "add_code", "product_id": prod_id}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel (ဖျက်သိမ်းမည်)", callback_data="cancel_action")]])
        await query.edit_message_text(f"✏️ `{prod_id}` အတွက် Code အသစ်များကို ရိုက်ထည့်ပါ။\n\n(အများကြီး တစ်ခါတည်း ထည့်လိုပါက တစ်ကြောင်းလျှင် တစ်ခုစီ ခွဲ၍ ရိုက်ပို့ပါ)", parse_mode="Markdown", reply_markup=cancel_btn)

    elif data.startswith("editprice_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("editprice_", "")
        admin_states[user_id] = {"action": "set_price", "product_id": prod_id}
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel (ဖျက်သိမ်းမည်)", callback_data="cancel_action")]])
        await query.edit_message_text(f"💵 `{prod_id}` အတွက် ဈေးနှုန်းအသစ်ကို ဂဏန်းဖြင့် ရိုက်ထည့်ပါ။\n\n(ဥပမာ - 35000)", parse_mode="Markdown", reply_markup=cancel_btn)

    elif data == "admin_sales" and user_id == ADMIN_USER_ID:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE status='accepted' AND date LIKE ?", (f"{today}%",))
        sales = cursor.fetchone()
        count = sales[0] if sales[0] else 0
        total = sales[1] if sales[1] else 0
        
        text = f"📊 **ယနေ့ အရောင်းစာရင်း ({today}):**\n\n✅ ရောင်းရသော အရေအတွက်: {count} ကြိမ်\n💰 စုစုပေါင်း ဝင်ငွေ: {total} MMK\n"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]))

    # Accept & Reject Orders
    elif data.startswith("accept_") and user_id == ADMIN_USER_ID:
        order_id = data.split("_")[1]
        cursor.execute("SELECT user_id, details, status FROM orders WHERE id=?", (order_id,))
        order = cursor.fetchone()
        
        if order and order[2] == "pending":
            buyer_id, details = order[0], order[1]
            items = details.split(", ")
            codes_to_send = []
            insufficient = False
            
            for item in items:
                prod_id, qty_str = item.split(":")
                qty = int(qty_str)
                cursor.execute("SELECT id, code FROM stock WHERE product_id=? LIMIT ?", (prod_id, qty))
                rows = cursor.fetchall()
                if len(rows) < qty:
                    insufficient = True
                    break
                for r in rows:
                    codes_to_send.append(f"🔹 {prod_id.upper()} Code: `{r[1]}`")
                    cursor.execute("DELETE FROM stock WHERE id=?", (r[0],))
                    
            if insufficient:
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n⚠️ **Stock မလောက်ပါ! Admin Panel မှ Code အသစ် အရင်ဖြည့်ပါ။**", parse_mode="Markdown")
            else:
                cursor.execute("UPDATE orders SET status='accepted' WHERE id=?", (order_id,))
                codes_text = "\n".join(codes_to_send)
                await context.bot.send_message(chat_id=buyer_id, text=f"✅ **သင့်ရဲ့ Order #{order_id} အောင်မြင်ပါတယ်။**\n\n🎁 **သင်ဝယ်ယူထားသော Codes များ:**\n{codes_text}\n\nအားပေးမှုကို ကျေးဇူးတင်ပါတယ်။", parse_mode="Markdown")
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ **Order Accepted & Codes Sent!**", parse_mode="Markdown")
        else:
             await query.answer("ဤ Order အား ဖြေရှင်းပြီးပါပြီ။", show_alert=True)

    elif data.startswith("reject_") and user_id == ADMIN_USER_ID:
        order_id = data.split("_")[1]
        cursor.execute("SELECT user_id, status FROM orders WHERE id=?", (order_id,))
        order = cursor.fetchone()
        if order and order[1] == "pending":
            cursor.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
            await context.bot.send_message(chat_id=order[0], text=f"❌ **သင့်ရဲ့ Order #{order_id} ကို Admin မှ ငြင်းပယ်လိုက်ပါသည်။**\n\n(အကြောင်းရင်း - ငွေလွှဲပြေစာ မမှန်ကန်၍ သို့မဟုတ် လက်ကျန် Stock ကုန်နေ၍ ဖြစ်နိုင်ပါသည်)", parse_mode="Markdown")
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ **Order Rejected!**", parse_mode="Markdown")
        else:
            await query.answer("ဤ Order အား ဖြေရှင်းပြီးပါပြီ။", show_alert=True)
            
    conn.commit()
    conn.close()

# --- RECEIPT HANDLER ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, details, total_price FROM orders WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (user_id,))
    order = cursor.fetchone()
    
    if order:
        order_id, details, total = order
        photo_file = update.message.photo[-1].file_id
        
        keyboard = [
            [InlineKeyboardButton("✅ Accept & Send Codes", callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}")]
        ]
        caption = f"🔔 **New Order #{order_id}**\n👤 Buyer: @{update.effective_user.username} (ID: {user_id})\n📦 Details: {details}\n💰 Total: {total} MMK"
        await context.bot.send_photo(chat_id=ADMIN_USER_ID, photo=photo_file, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        await update.message.reply_text("✅ ငွေလွှဲပြေစာ လက်ခံရရှိပါပြီ။ Admin မှ စစ်ဆေးပြီးပါက Code များကို ဤနေရာသို့ ချက်ချင်း ပို့ပေးပါမည်။", reply_markup=get_main_keyboard(user_id))
    else:
        await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ အောက်ပါ '🛒 ကတ်ဝယ်ယူမည်' ကို နှိပ်၍ Product အရင်ရွေးချယ်ပြီးမှ ပြေစာပို့ပေးပါ။", reply_markup=get_main_keyboard(user_id))
        
    conn.close()

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    application.run_polling()
