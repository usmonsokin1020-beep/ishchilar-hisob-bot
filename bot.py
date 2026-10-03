import os
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMINS = {5453158658, 6993164338, 1492765331}
DB = "hisob.db"

NAME, WORK_QTY, PAYMENT, ADD_WORK, EDIT_PRICE, DELETE_WORK = range(6)

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        tg_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS works(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        price INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS entries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER NOT NULL,
        work_id INTEGER NOT NULL,
        qty REAL NOT NULL,
        price INTEGER NOT NULL,
        total INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    defaults = ["Svarka", "Bukish", "Kraska", "Yig‘ish"]
    for w in defaults:
        con.execute("INSERT OR IGNORE INTO works(name,price) VALUES(?,0)", (w,))
    con.commit()
    con.close()

def is_admin(uid): return uid in ADMINS

def user_name(uid):
    con=db(); r=con.execute("SELECT name FROM users WHERE tg_id=?", (uid,)).fetchone(); con.close()
    return r["name"] if r else None

def balance(uid):
    con=db()
    earned=con.execute("SELECT COALESCE(SUM(total),0) s FROM entries WHERE tg_id=?", (uid,)).fetchone()["s"]
    paid=con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE tg_id=?", (uid,)).fetchone()["s"]
    con.close()
    return int(earned), int(paid), int(earned-paid)

def money(n): return f"{int(n):,}".replace(",", " ") + " so‘m"
def menu(uid):
    rows = [["➕ Ish qo‘shish", "💵 Pul oldim"], ["💰 Qoldiq", "📋 Tarixim"]]
    if is_admin(uid):
        rows += [["📊 HAMMA ISHCHILAR HISOBI"], ["⚙️ Ishlar va narxlar"], ["🗑 Hisobni o‘chirish"]]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)
       

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if not user_name(uid):
        await update.message.reply_text("Ismingizni yozing. Masalan: Akmal")
        return NAME
    await update.message.reply_text(f"Assalomu alaykum, {user_name(uid)}!", reply_markup=menu(uid))
    return ConversationHandler.END

async def save_name(update, context):
    name=update.message.text.strip()
    if len(name)<2:
        await update.message.reply_text("Ismni to‘liqroq yozing.")
        return NAME
    con=db(); con.execute("INSERT OR REPLACE INTO users(tg_id,name) VALUES(?,?)",(update.effective_user.id,name)); con.commit(); con.close()
    await update.message.reply_text(f"✅ Saqlandi: {name}", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END

async def work_begin(update, context):
    con=db(); works=con.execute("SELECT * FROM works ORDER BY name").fetchall(); con.close()
    if not works:
        await update.message.reply_text("Hozircha ish turi yo‘q.")
        return ConversationHandler.END
    kb=[[InlineKeyboardButton(f"{r['name']} — {money(r['price'])}", callback_data=f"work:{r['id']}")] for r in works]
    await update.message.reply_text("Ish turini tanlang:", reply_markup=InlineKeyboardMarkup(kb))
    return WORK_QTY

async def work_selected(update, context):
    q=update.callback_query; await q.answer()
    wid=int(q.data.split(":")[1]); context.user_data["work_id"]=wid
    con=db(); r=con.execute("SELECT * FROM works WHERE id=?",(wid,)).fetchone(); con.close()
    context.user_data["work_name"]=r["name"]; context.user_data["price"]=r["price"]
    await q.message.reply_text(f"{r['name']} tanlandi.\nNechta qilganingizni yozing:")
    return WORK_QTY

async def qty_save(update, context):
    try: qty=float(update.message.text.replace(",","."))
    except: 
        await update.message.reply_text("Miqdorni raqam bilan yozing. Masalan: 10")
        return WORK_QTY
    if qty<=0:
        await update.message.reply_text("Miqdor 0 dan katta bo‘lsin."); return WORK_QTY
    price=int(context.user_data["price"]); total=int(qty*price)
    con=db(); con.execute("INSERT INTO entries(tg_id,work_id,qty,price,total,created_at) VALUES(?,?,?,?,?,?)",
        (update.effective_user.id,context.user_data["work_id"],qty,price,total,datetime.now().strftime("%Y-%m-%d %H:%M")))
    con.commit(); con.close()
    await update.message.reply_text(f"✅ {context.user_data['work_name']}: {qty:g} ta × {money(price)} = {money(total)}", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END

async def payment_begin(update, context):
    await update.message.reply_text("Qancha pul olganingizni yozing. Masalan: 200000")
    return PAYMENT

async def payment_save(update, context):
    try: amount=int(update.message.text.replace(" ","").replace(".",""))
    except:
        await update.message.reply_text("Summani raqam bilan yozing."); return PAYMENT
    if amount<=0:
        await update.message.reply_text("Summa 0 dan katta bo‘lsin."); return PAYMENT
    con=db(); con.execute("INSERT INTO payments(tg_id,amount,created_at) VALUES(?,?,?)",
        (update.effective_user.id,amount,datetime.now().strftime("%Y-%m-%d %H:%M"))); con.commit(); con.close()
    e,p,b=balance(update.effective_user.id)
    await update.message.reply_text(f"✅ Pul olindi: {money(amount)}\nQoldiq: {money(b)}", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END

async def show_balance(update, context):
    e,p,b=balance(update.effective_user.id)
    status="Qoldiq" if b>=0 else "Qarz"
    await update.message.reply_text(f"💰 Ishlangan: {money(e)}\n💵 Olingan: {money(p)}\n📌 {status}: {money(abs(b))}")

async def history(update, context):
    uid=update.effective_user.id; con=db()
    rows=con.execute("""SELECT e.*,w.name FROM entries e JOIN works w ON w.id=e.work_id
                       WHERE e.tg_id=? ORDER BY e.id DESC LIMIT 20""",(uid,)).fetchall()
    pays=con.execute("SELECT * FROM payments WHERE tg_id=? ORDER BY id DESC LIMIT 10",(uid,)).fetchall(); con.close()
    lines=["📋 Oxirgi ishlar:"]
    lines += [f"• {r['created_at']} — {r['name']}: {r['qty']:g} × {money(r['price'])} = {money(r['total'])}" for r in rows] or ["• Hali ish kiritilmagan"]
    lines += ["\n💵 Olingan pullar:"]
    lines += [f"• {r['created_at']} — {money(r['amount'])}" for r in pays] or ["• Hali pul kiritilmagan"]
    await update.message.reply_text("\n".join(lines))

async def all_workers(update, context):
    if not is_admin(update.effective_user.id): return
    con=db(); users=con.execute("SELECT * FROM users ORDER BY name").fetchall(); con.close()
    lines=["📊 HAMMA ISHCHILAR HISOBI\n"]
    te=tp=tb=0
    for u in users:
        e,p,b=balance(u["tg_id"]); te+=e; tp+=p; tb+=b
        mark="Qoldiq" if b>=0 else "Qarz"
        lines.append(f"👤 {u['name']}\nIsh: {money(e)} | Olgan: {money(p)} | {mark}: {money(abs(b))}\n")
    lines.append(f"JAMI — Ish: {money(te)} | Olgan: {money(tp)} | Farq: {money(tb)}")
    await update.message.reply_text("\n".join(lines))

async def settings(update, context):
    if not is_admin(update.effective_user.id): return
    kb=[
        [InlineKeyboardButton("➕ Ish turi qo‘shish", callback_data="adm:add")],
        [InlineKeyboardButton("💰 Narxni o‘zgartirish", callback_data="adm:price")],
        [InlineKeyboardButton("🗑 Ish turini o‘chirish", callback_data="adm:delete")]
    ]
    await update.message.reply_text("⚙️ Ishlar va narxlar:", reply_markup=InlineKeyboardMarkup(kb))

async def admin_action(update, context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    action=q.data.split(":")[1]
    if action=="add":
        await q.message.reply_text("Yangi ish nomini yozing:"); return ADD_WORK
    con=db(); works=con.execute("SELECT * FROM works ORDER BY name").fetchall(); con.close()
    prefix="price" if action=="price" else "del"
    kb=[[InlineKeyboardButton(f"{w['name']} — {money(w['price'])}", callback_data=f"{prefix}:{w['id']}")] for w in works]
    await q.message.reply_text("Ish turini tanlang:", reply_markup=InlineKeyboardMarkup(kb))
    return EDIT_PRICE if action=="price" else DELETE_WORK

async def add_work_save(update, context):
    name=update.message.text.strip()
    con=db()
    try: con.execute("INSERT INTO works(name,price) VALUES(?,0)",(name,)); con.commit()
    except sqlite3.IntegrityError:
        con.close(); await update.message.reply_text("Bu ish turi oldin qo‘shilgan."); return ConversationHandler.END
    con.close(); await update.message.reply_text(f"✅ {name} qo‘shildi.", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END

async def price_choose(update, context):
    q=update.callback_query; await q.answer()
    context.user_data["edit_work_id"]=int(q.data.split(":")[1])
    await q.message.reply_text("Yangi narxni yozing. Masalan: 15000")
    return EDIT_PRICE

async def price_save(update, context):
    if "edit_work_id" not in context.user_data: return ConversationHandler.END
    try: price=int(update.message.text.replace(" ","").replace(".",""))
    except:
        await update.message.reply_text("Narxni raqam bilan yozing."); return EDIT_PRICE
    con=db(); con.execute("UPDATE works SET price=? WHERE id=?",(price,context.user_data["edit_work_id"])); con.commit(); con.close()
    await update.message.reply_text(f"✅ Narx {money(price)} qilib o‘zgartirildi.", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END

async def delete_choose(update, context):
    q=update.callback_query; await q.answer()
    wid=int(q.data.split(":")[1]); con=db()
    used=con.execute("SELECT COUNT(*) c FROM entries WHERE work_id=?",(wid,)).fetchone()["c"]
    w=con.execute("SELECT name FROM works WHERE id=?",(wid,)).fetchone()
    if used:
        con.close(); await q.message.reply_text("Bu ish turi tarixda ishlatilgan, shuning uchun o‘chirilmadi."); return ConversationHandler.END
    con.execute("DELETE FROM works WHERE id=?",(wid,)); con.commit(); con.close()
    await q.message.reply_text(f"🗑 {w['name']} o‘chirildi.", reply_markup=menu(q.from_user.id))
    return ConversationHandler.END

async def delete_account_menu(update, context):
    if not is_admin(update.effective_user.id):
        return

    con = db()
    rows = con.execute("""
        SELECT e.id, e.qty, e.total, e.created_at, w.name, u.name AS worker
        FROM entries e
        JOIN works w ON w.id = e.work_id
        LEFT JOIN users u ON u.tg_id = e.tg_id
        ORDER BY e.id DESC LIMIT 30
    """).fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("O‘chirish uchun hisob yo‘q.")
        return

    kb = [
        [InlineKeyboardButton(
            f"{r['worker']} | {r['name']} | {r['qty']:g} ta | {money(r['total'])}",
            callback_data=f"delentry:{r['id']}"
        )]
        for r in rows
    ]

    await update.message.reply_text(
        "🗑 O‘chirmoqchi bo‘lgan hisobni tanlang:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def delete_account(update, context):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return

    entry_id = int(q.data.split(":")[1])
    con = db()
    con.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    con.commit()
    con.close()

    await q.edit_message_text("✅ Hisob o‘chirildi.")
async def cancel(update, context):
    await update.message.reply_text("Bekor qilindi.", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi.")
    init_db()
    app=Application.builder().token(TOKEN).build()
    conv=ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^➕ Ish qo‘shish$"), work_begin),
            MessageHandler(filters.Regex("^💵 Pul oldim$"), payment_begin),
            CallbackQueryHandler(admin_action, pattern=r"^adm:"),
        ],
        states={
            NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
            WORK_QTY:[
                CallbackQueryHandler(work_selected, pattern=r"^work:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, qty_save)
            ],
            PAYMENT:[MessageHandler(filters.TEXT & ~filters.COMMAND, payment_save)],
            ADD_WORK:[MessageHandler(filters.TEXT & ~filters.COMMAND, add_work_save)],
            EDIT_PRICE:[
                CallbackQueryHandler(price_choose, pattern=r"^price:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, price_save)
            ],
            DELETE_WORK:[CallbackQueryHandler(delete_choose, pattern=r"^del:\d+$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^💰 Qoldiq$"), show_balance))
    app.add_handler(MessageHandler(filters.Regex("^📋 Tarixim$"), history))
    app.add_handler(MessageHandler(filters.Regex("^📊 HAMMA ISHCHILAR HISOBI$"), all_workers))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Ishlar va narxlar$"), settings))
    app.add_handler(MessageHandler(filters.Regex("^🗑 Hisobni o‘chirish$"), delete_account_menu))
    app.add_handler(CallbackQueryHandler(delete_account, pattern=r"^delentry:\d+$"))
    print("Bot ishlayapti...")
    app.run_polling()

if __name__=="__main__":
    main()
