import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
admin_states = {} # Tracks what admin is currently doing (e.g., adding code, changing price)

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Cancel any pending admin states if they press /start
    if user_id in admin_states:
        del admin_states[user_id]

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Code (Smile One)", callback_data="shop_menu")],
        [InlineKeyboardButton("🧾 My Orders / History", callback_data="my_orders")]
    ]
    
    if user_id == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("မင်္ဂလာပါ! Digital Product Shop မှ ကြိုဆိုပါတယ်။\nဝယ်ယူလိုသော ဝန်ဆောင်မှုကို ရွေးချယ်ပါ👇", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text("မင်္ဂလာပါ! Digital Product Shop မှ ကြိုဆိုပါတယ်။\nဝယ်ယူလိုသော ဝန်ဆောင်မှုကို ရွေးချယ်ပါ👇", reply_markup=reply_markup)

# --- CALLBACK HANDLER (BUTTONS) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()

    # Shop Menu
    if data == "shop_menu":
        cursor.execute("SELECT id, name, price FROM products")
        products = cursor.fetchall()
        keyboard = []
        for p in products:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=?", (p[0],))
            stock_count = cursor.fetchone()[0]
            keyboard.append([InlineKeyboardButton(f"{p[1]} - {p[2]} MMK (Stock: {stock_count})", callback_data=f"buy_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        await query.edit_message_text("🛒 ဝယ်ယူလိုသော Product ကို ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    # Add to Cart
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

    # Checkout & Show Payment Info
    elif data == "checkout":
        if user_id not in user_carts or not user_carts[user_id]:
            await query.edit_message_text("ခြင်းတောင်းထဲမှာ ဘာမှမရှိပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="shop_menu")]]))
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
        cart_text += f"🏦 **ငွေလွှဲရမည့် အကောင့်များ:**\n{payment_info}\n\n"
        cart_text += "⚠️ **အရေးကြီး:** ကျေးဇူးပြု၍ ငွေလွှဲပြေစာ (Screenshot) ကို ဤနေရာသို့ ပို့ပေးပါ။ ပြေစာပို့ပြီးပါက Admin မှ စစ်ဆေးပြီး Code များ ပို့ပေးပါမည်။"
        
        details_str = ", ".join(details)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO orders (user_id, username, details, total_price, status, date) VALUES (?, ?, ?, ?, ?, ?)", 
                       (user_id, update.effective_user.username, details_str, total_price, "pending", date_str))
        conn.commit()
        
        user_carts[user_id] = {} # Clear cart
        await query.edit_message_text(cart_text)

    # ===== ADMIN PANEL BUTTONS =====
    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
        keyboard = [
            [InlineKeyboardButton("📦 Stock စီမံရန် (Add Codes)", callback_data="manage_stock")],
            [InlineKeyboardButton("💵 ဈေးနှုန်း ပြင်ဆင်ရန်", callback_data="manage_price")],
            [InlineKeyboardButton("🏦 ငွေပေးချေမှုစနစ် ပြင်ရန်", callback_data="manage_payment")],
            [InlineKeyboardButton("📊 ယနေ့ အရောင်းစာရင်း", callback_data="admin_sales")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text("👑 **Admin Management Panel**\nလုပ်ဆောင်လိုသော အရာကို ရွေးချယ်ပါ:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_stock" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name FROM products")
        products = cursor.fetchall()
        keyboard = []
        for p in products:
            cursor.execute("SELECT COUNT(*) FROM stock WHERE product_id=?", (p[0],))
            count = cursor.fetchone()[0]
            keyboard.append([InlineKeyboardButton(f"➕ Add Code ({p[1]}) - ကျန် {count} ခု", callback_data=f"addcode_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
        await query.edit_message_text("📦 ဘယ် Product အတွက် Code အသစ်ထည့်မလဲ ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_price" and user_id == ADMIN_USER_ID:
        cursor.execute("SELECT id, name, price FROM products")
        products = cursor.fetchall()
        keyboard = []
        for p in products:
            keyboard.append([InlineKeyboardButton(f"💵 Edit Price ({p[1]} - {p[2]} MMK)", callback_data=f"editprice_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
        await query.edit_message_text("💵 ဘယ် Product ရဲ့ ဈေးနှုန်းကို ပြင်ဆင်မလဲ ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "manage_payment" and user_id == ADMIN_USER_ID:
        admin_states[user_id] = {"action": "set_payment"}
        await query.edit_message_text("🏦 **Payment Info အသစ်ကို အောက်တွင် ရိုက်ထည့်ပါ။**\n\n(ဥပမာ - KBZ Pay: 09...)\n\n❌ မပြင်တော့ပါက /cancel ဟု ရိုက်ပါ။")

    elif data.startswith("addcode_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("addcode_", "")
        admin_states[user_id] = {"action": "add_code", "product_id": prod_id}
        await query.edit_message_text(f"✏️ `{prod_id}` အတွက် Code ရိုက်ထည့်ပါ။\n\n(အများကြီး တစ်ခါတည်း ထည့်လိုပါက တစ်ကြောင်းလျှင် တစ်ခုစီ ခွဲ၍ ရိုက်ပို့ပါ)\n\n❌ မထည့်တော့ပါက /cancel ဟု ရိုက်ပါ။")

    elif data.startswith("editprice_") and user_id == ADMIN_USER_ID:
        prod_id = data.replace("editprice_", "")
        admin_states[user_id] = {"action": "set_price", "product_id": prod_id}
        await query.edit_message_text(f"💵 `{prod_id}` အတွက် ဈေးနှုန်းအသစ်ကို ဂဏန်းဖြင့် ရိုက်ထည့်ပါ။\n\n(ဥပမာ - 35000)\n\n❌ မပြင်တော့ပါက /cancel ဟု ရိုက်ပါ။")

    elif data == "admin_sales" and user_id == ADMIN_USER_ID:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE status='accepted' AND date LIKE ?", (f"{today}%",))
        sales = cursor.fetchone()
        count = sales[0] if sales[0] else 0
        total = sales[1] if sales[1] else 0
        
        text = f"📊 **ယနေ့ အရောင်းစာရင်း ({today}):**\n\n"
        text += f"✅ ရောင်းရသော အရေအတွက်: {count} ကြိမ်\n"
        text += f"💰 စုစုပေါင်း ဝင်ငွေ: {total} MMK\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]))

    elif data == "main_menu":
        await start(update, context)

    # Order History
    elif data == "my_orders":
        cursor.execute("SELECT id, details, total_price, status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
        orders = cursor.fetchall()
        if not orders:
            text = "သင် ဝယ်ယူထားသော မှတ်တမ်း မရှိသေးပါ။"
        else:
            text = "🧾 **နောက်ဆုံး ဝယ်ယူထားသော ၅ ကြိမ်:**\n\n"
            for o in orders:
                text += f"Order #{o[0]} | {o[1]} | {o[2]} MMK | Status: {o[3].upper()}\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]))

    # ===== ADMIN ACCEPT & REJECT (ORDER PROCESSING) =====
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
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n⚠️ **Stock မလောက်ပါ! Admin Panel မှ Code အသစ် အရင်ဖြည့်ပါ။**")
            else:
                cursor.execute("UPDATE orders SET status='accepted' WHERE id=?", (order_id,))
                codes_text = "\n".join(codes_to_send)
                await context.bot.send_message(chat_id=buyer_id, text=f"✅ သင့်ရဲ့ Order #{order_id} အောင်မြင်ပါတယ်။\n\n🎁 **သင်ဝယ်ယူထားသော Codes များ:**\n{codes_text}\n\nအားပေးမှုကို ကျေးဇူးတင်ပါတယ်။")
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ **Order Accepted & Codes Sent!**")
        else:
             await query.answer("ဤ Order အား ဖြေရှင်းပြီးပါပြီ။", show_alert=True)

    elif data.startswith("reject_") and user_id == ADMIN_USER_ID:
        order_id = data.split("_")[1]
        cursor.execute("SELECT user_id, status FROM orders WHERE id=?", (order_id,))
        order = cursor.fetchone()
        
        if order and order[1] == "pending":
            cursor.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
            await context.bot.send_message(chat_id=order[0], text=f"❌ သင့်ရဲ့ Order #{order_id} ကို Admin မှ ငြင်းပယ်လိုက်ပါသည်။\n(အကြောင်းရင်း - ငွေလွှဲပြေစာ မမှန်ကန်၍ သို့မဟုတ် လက်ကျန် Stock ကုန်နေ၍ ဖြစ်နိုင်ပါသည်)")
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ **Order Rejected!**")
        else:
            await query.answer("ဤ Order အား ဖြေရှင်းပြီးပါပြီ။", show_alert=True)
            
    conn.commit()
    conn.close()

# --- PHOTO HANDLER (RECEIPT) ---
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
            [
                InlineKeyboardButton("✅ Accept & Send Codes", callback_data=f"accept_{order_id}"),
            ],
            [
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}")
            ]
        ]
        caption = f"🔔 **New Order #{order_id}**\n👤 Buyer: @{update.effective_user.username} (ID: {user_id})\n📦 Details: {details}\n💰 Total: {total} MMK"
        await context.bot.send_photo(chat_id=ADMIN_USER_ID, photo=photo_file, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
        
        await update.message.reply_text("✅ ငွေလွှဲပြေစာ လက်ခံရရှိပါပြီ။ Admin မှ စစ်ဆေးပြီးပါက Code များကို ဤနေရာသို့ ပို့ပေးပါမည်။")
    else:
        await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ Product ကို အရင်ရွေးချယ်ပြီး Checkout လုပ်ပေးပါ။")
        
    conn.close()

# --- TEXT MESSAGES HANDLER (FOR ADMIN INPUTS) ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == '/cancel':
        if user_id in admin_states:
            del admin_states[user_id]
            await update.message.reply_text("❌ လုပ်ဆောင်ချက်ကို ဖျက်သိမ်းလိုက်ပါပြီ။ /start ကို နှိပ်၍ ပြန်စပါ။")
        return

    # Check if admin is currently in a "waiting for input" state
    if user_id in admin_states:
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
            await update.message.reply_text(f"✅ Product `{prod_id}` အတွက် Code အသစ် {added} ခု သွင်းပြီးပါပြီ။\n(/start နှိပ်၍ Menu သို့ပြန်သွားပါ)")
            del admin_states[user_id]
            
        elif action == "set_price":
            prod_id = state["product_id"]
            try:
                price = int(text)
                cursor.execute("UPDATE products SET price=? WHERE id=?", (price, prod_id))
                conn.commit()
                await update.message.reply_text(f"✅ Product `{prod_id}` ၏ ဈေးနှုန်းကို {price} MMK သို့ ပြောင်းလဲလိုက်ပါပြီ။\n(/start နှိပ်၍ Menu သို့ပြန်သွားပါ)")
                del admin_states[user_id]
            except ValueError:
                await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ ဂဏန်း (Numbers) သာ ရိုက်ထည့်ပါ။ သို့မဟုတ် မပြင်တော့ပါက /cancel နှိပ်ပါ။")
                
        elif action == "set_payment":
            cursor.execute("UPDATE settings SET value=? WHERE key='payment_info'", (text,))
            conn.commit()
            await update.message.reply_text("✅ Payment Info ကို အောင်မြင်စွာ ပြောင်းလဲလိုက်ပါပြီ။\n(/start နှိပ်၍ Menu သို့ပြန်သွားပါ)")
            del admin_states[user_id]
            
        conn.close()
        return

    # If it's just normal text and not an admin action
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("ဝယ်ယူရန် /start ကို နှိပ်ပါ။")

# --- CANCEL COMMAND ---
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admin_states:
        del admin_states[user_id]
    await update.message.reply_text("❌ လုပ်ဆောင်ချက်ကို ဖျက်သိမ်းလိုက်ပါပြီ။ /start ကို နှိပ်၍ ပြန်စပါ။")

# --- MAIN RUN ---
if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('cancel', cancel_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)) # Handle pure texts
    
    application.run_polling()
