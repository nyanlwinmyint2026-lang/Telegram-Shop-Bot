import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- CONFIGURATIONS ---
TELEGRAM_BOT_TOKEN = 8969723597:AAH1A0p6LcoLdk71MKSrA3Avz6yAR2vQ_QM
ADMIN_USER_ID = 6069279282

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (id TEXT PRIMARY KEY, name TEXT, price INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, code TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, 
                       details TEXT, total_price INTEGER, status TEXT, date TEXT)''')
    
    # Default Products & Payment info
    cursor.execute("INSERT OR IGNORE INTO products VALUES ('smile_300', 'Smile One 300 BRL', 30000)")
    cursor.execute("INSERT OR IGNORE INTO products VALUES ('smile_1k', 'Smile One 1K BRL', 95000)")
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('payment_info', 'KBZ Pay: 09XXXXX (Name: U XXX)\nWave Pay: 09XXXXX')")
    
    conn.commit()
    conn.close()

init_db()

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🛒 Buy Code (Smile One)", callback_data="shop_menu")],
        [InlineKeyboardButton("📊 My Orders / History", callback_data="my_orders")]
    ]
    if update.effective_user.id == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("မင်္ဂလာပါ! Digital Product Shop မှ ကြိုဆိုပါတယ်။", reply_markup=reply_markup)

# --- SHOP & BUY FLOW ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "shop_menu":
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price FROM products")
        products = cursor.fetchall()
        conn.close()

        keyboard = []
        for p in products:
            keyboard.append([InlineKeyboardButton(f"{p[1]} - {p[2]} MMK", callback_data=f"buy_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        
        await query.edit_message_text("ရရှိနိုင်သော Product များကို ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_"):
        context.user_data['qty_300'] = 0
        context.user_data['qty_1k'] = 0
        await show_cart_builder(query, context)

    elif data in ["add_300", "add_1k", "sub_300", "sub_1k"]:
        p_type = data.split("_")[1]
        action = data.split("_")[0]
        key = f"qty_{p_type}"
        
        if action == "add":
            context.user_data[key] = context.user_data.get(key, 0) + 1
        elif action == "sub" and context.user_data.get(key, 0) > 0:
            context.user_data[key] -= 1
            
        await show_cart_builder(query, context)

    elif data == "checkout":
        q300 = context.user_data.get('qty_300', 0)
        q1k = context.user_data.get('qty_1k', 0)
        
        if q300 == 0 and q1k == 0:
            await query.answer("ကျေးဇူးပြု၍ ပမာဏအနည်းဆုံး တစ်ခုခု ရွေးချယ်ပါ။", show_alert=True)
            return

        total = (q300 * 30000) + (q1k * 95000)
        context.user_data['total_price'] = total
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key='payment_info'")
        pay_info = cursor.fetchone()[0]
        conn.close()

        text = (f"🛒 **ဝယ်ယူမည့်စာရင်း:**\n"
                f"- Smile One 300 BRL: {q300} ခု\n"
                f"- Smile One 1K BRL: {q1k} ခု\n"
                f"💰 **စုစုပေါင်းကျသင့်ငွေ:** {total:,} MMK\n\n"
                f"ငွေလွှဲရန် အကောင့်များ:\n{pay_info}\n\n"
                f"ငွေလွှဲပြီးပါက **ငွေလွှဲပြေစာ (Screenshot)** ကို Bot ဆီသို့ ပုံပို့ပေးပါရန်။")
        
        await query.edit_message_text(text, parse_mode="Markdown")
        context.user_data['waiting_for_payment'] = True

    elif data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("🛒 Buy Code (Smile One)", callback_data="shop_menu")],
            [InlineKeyboardButton("📊 My Orders / History", callback_data="my_orders")]
        ]
        if update.effective_user.id == ADMIN_USER_ID:
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text("ပင်မမီနူးသို့ ပြန်ရောက်ပါပြီ။", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_panel" and update.effective_user.id == ADMIN_USER_ID:
        keyboard = [
            [InlineKeyboardButton("🏆 Top 5 Buyers (This Month)", callback_data="adm_top5")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        await query.edit_message_text("👑 **Admin Management Panel**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "adm_top5" and update.effective_user.id == ADMIN_USER_ID:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute('''SELECT username, SUM(total_price) as total, COUNT(*) FROM orders 
                          WHERE status='Approved' GROUP BY user_id ORDER BY total DESC LIMIT 5''')
        top5 = cursor.fetchall()
        conn.close()
        
        text = "🏆 **Top 5 Buyers (Month Leaderboard)**\n\n"
        for i, row in enumerate(top5, 1):
            text += f"{i}. @{row[0]} - စုစုပေါင်း သုံးငွေ: {row[1]:,} MMK ({row[2]} orders)\n"
        if not top5:
            text += "ဝယ်ယူမှု မှတ်တမ်း မရှိသေးပါ။"
            
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_cart_builder(query, context):
    q300 = context.user_data.get('qty_300', 0)
    q1k = context.user_data.get('qty_1k', 0)
    total = (q300 * 30000) + (q1k * 95000)
    
    text = (f"🛠 **ပမာဏ ရွေးချယ်ပါ (Flexible Buy):**\n\n"
            f"1️⃣ 300 BRL Code (30,000 MMK) - ခုရေ: {q300}\n"
            f"2️⃣ 1K BRL Code (95,000 MMK) - ခုရေ: {q1k}\n\n"
            f"💰 စုစုပေါင်း: **{total:,} MMK**")
            
    keyboard = [
        [InlineKeyboardButton("➕ 300 (+1)", callback_data="add_300"), InlineKeyboardButton("➖ 300 (-1)", callback_data="sub_300")],
        [InlineKeyboardButton("➕ 1K (+1)", callback_data="add_1k"), InlineKeyboardButton("➖ 1K (-1)", callback_data="sub_1k")],
        [InlineKeyboardButton("✅ ပြီးဆုံးပြီ (Checkout)", callback_data="checkout")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="shop_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- MESSAGE & RECEIPT HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if context.user_data.get('waiting_for_payment') and update.message.photo:
        context.user_data['waiting_for_payment'] = False
        photo_file = update.message.photo[-1].file_id
        
        q300 = context.user_data.get('qty_300', 0)
        q1k = context.user_data.get('qty_1k', 0)
        total = context.user_data.get('total_price', 0)
        details = f"300 BRL: {q300}, 1K BRL: {q1k}"
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, username, details, total_price, status, date) VALUES (?, ?, ?, ?, ?, ?)",
                       (user.id, user.username or user.first_name, details, total, "Pending", datetime.now().strftime("%Y-%m-%d")))
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        await update.message.reply_text("✅ Order လက်ခံရရှိပါပြီ။ Admin မှ ငွေလွှဲစစ်ဆေးနေစဉ် ခဏစောင့်ဆိုင်းပေးပါ။")
        
        admin_keyboard = [
            [InlineKeyboardButton(f"✅ Accept #{order_id}", callback_data=f"adm_acc_{order_id}_{user.id}")],
            [InlineKeyboardButton(f"❌ Reject #{order_id}", callback_data=f"adm_rej_{order_id}_{user.id}")]
        ]
        await context.bot.send_photo(
            chat_id=ADMIN_USER_ID,
            photo=photo_file,
            caption=f"🔔 **New Order #{order_id}**\n👤 Buyer: @{user.username} (ID: {user.id})\n📦 Details: {details}\n💰 Total: {total:,} MMK",
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("ကျေးဇူးပြု၍ မီနူးမှတစ်ဆင့် ဝယ်ယူမှုကို ဆောင်ရွက်ပေးပါ။")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("Shop Bot is running...")
    app.run_polling()
