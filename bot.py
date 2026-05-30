import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
DATA_FILE = "data.json"
GOAL = 400000

# ─── КАТЕГОРИИ ───────────────────────────────────────────────
CATS_EXPENSE = {
    "food":      "🍔 Еда",
    "transport": "🚗 Транспорт",
    "sport":     "💪 Спорт",
    "fun":       "🎮 Развлечения",
    "health":    "💊 Здоровье",
    "shopping":  "🛍 Покупки",
    "home":      "🏠 Жильё",
    "other":     "📦 Прочее",
}
CATS_INCOME = {
    "work":      "💼 Работа",
    "freelance": "🎨 Фриланс",
    "client":    "🤝 Клиент",
    "other":     "📦 Прочее",
}

# ─── ХРАНИЛИЩЕ ────────────────────────────────────────────────
def load_data(user_id: int) -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        all_data = json.load(f)
    return all_data.get(str(user_id), {"transactions": [], "pending": None})

def save_data(user_id: int, data: dict):
    all_data = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    all_data[str(user_id)] = data
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

# ─── ВСПОМОГАТЕЛЬНЫЕ ──────────────────────────────────────────
def fmt(n: float) -> str:
    return f"{int(n):,}".replace(",", " ") + " ₽"

def current_month() -> str:
    return datetime.now().strftime("%Y-%m")

def month_name(ym: str) -> str:
    months = {"01":"январь","02":"февраль","03":"март","04":"апрель",
              "05":"май","06":"июнь","07":"июль","08":"август",
              "09":"сентябрь","10":"октябрь","11":"ноябрь","12":"декабрь"}
    y, m = ym.split("-")
    return f"{months[m]} {y}"

def get_month_txs(txs: list, month: str = None) -> list:
    if month is None:
        month = current_month()
    return [t for t in txs if t["date"].startswith(month)]

def totals(txs: list) -> dict:
    inc = sum(t["amount"] for t in txs if t["type"] == "income")
    exp = sum(t["amount"] for t in txs if t["type"] == "expense")
    return {"income": inc, "expense": exp, "balance": inc - exp}

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["➕ Доход", "➖ Расход"],
        ["📊 Статистика", "📋 История"],
        ["🎯 Цель"],
    ], resize_keyboard=True)

# ─── КОМАНДЫ ──────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {name}! 👋\n\n"
        "Я твой финансовый трекер.\n\n"
        "Как добавить операцию:\n"
        "• Нажми кнопку ➕ Доход или ➖ Расход\n"
        "• Или напиши быстро: `кофе 350` или `зарплата 80000`\n\n"
        "Поехали 🚀",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data(user_id)
    txs = get_month_txs(data.get("transactions", []))
    t = totals(txs)
    
    inc, exp, bal = t["income"], t["expense"], t["balance"]
    pct = round(inc / GOAL * 100) if GOAL > 0 else 0
    bar_filled = round(pct / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    
    # Расходы по категориям
    by_cat = {}
    for tx in txs:
        if tx["type"] == "expense":
            by_cat[tx["cat"]] = by_cat.get(tx["cat"], 0) + tx["amount"]
    
    cat_lines = ""
    if by_cat:
        sorted_cats = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)
        for cat_id, val in sorted_cats[:5]:
            label = CATS_EXPENSE.get(cat_id, cat_id)
            cat_lines += f"  {label}: {fmt(val)}\n"
    
    text = (
        f"📊 *Статистика за {month_name(current_month())}*\n\n"
        f"💚 Доходы: *{fmt(inc)}*\n"
        f"❤️ Расходы: *{fmt(exp)}*\n"
        f"{'💰' if bal >= 0 else '😬'} Баланс: *{fmt(bal)}*\n\n"
        f"🎯 Цель 400 000 ₽/мес\n"
        f"`{bar}` {pct}%\n"
        f"Получено {fmt(inc)} из {fmt(GOAL)}\n"
        f"Осталось: {fmt(max(0, GOAL - inc))}\n"
    )
    if cat_lines:
        text += f"\n📂 *Топ расходов:*\n{cat_lines}"
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data(user_id)
    txs = sorted(get_month_txs(data.get("transactions", [])), key=lambda x: x["date"], reverse=True)
    
    if not txs:
        await update.message.reply_text("Пока нет операций за этот месяц.", reply_markup=main_keyboard())
        return
    
    lines = []
    for tx in txs[:15]:
        cat_dict = CATS_INCOME if tx["type"] == "income" else CATS_EXPENSE
        cat_label = cat_dict.get(tx["cat"], tx["cat"])
        sign = "+" if tx["type"] == "income" else "−"
        date_str = tx["date"][8:10] + "." + tx["date"][5:7]
        lines.append(f"{date_str} {cat_label} {sign}{fmt(tx['amount'])} — {tx['desc']}")
    
    text = f"📋 *История за {month_name(current_month())}*\n\n" + "\n".join(lines)
    if len(txs) > 15:
        text += f"\n\n_...и ещё {len(txs)-15} операций_"
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def goal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data(user_id)
    txs = get_month_txs(data.get("transactions", []))
    t = totals(txs)
    inc = t["income"]
    pct = round(inc / GOAL * 100)
    left = max(0, GOAL - inc)
    days_left = (datetime.now().replace(day=1, month=datetime.now().month % 12 + 1) - datetime.now()).days
    
    text = (
        f"🎯 *Прогресс к цели*\n\n"
        f"Цель: {fmt(GOAL)}/мес\n"
        f"Получено: {fmt(inc)} ({pct}%)\n"
        f"Осталось: {fmt(left)}\n"
        f"Дней в месяце: ~{days_left}\n\n"
    )
    if left > 0 and days_left > 0:
        text += f"Нужно зарабатывать ~{fmt(left // days_left)}/день"
    else:
        text += "🎉 Цель достигнута!"
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

# ─── ДОБАВЛЕНИЕ ОПЕРАЦИЙ ──────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    data = load_data(user_id)

    # Кнопки меню
    if text == "📊 Статистика":
        return await stats_cmd(update, ctx)
    if text == "📋 История":
        return await history_cmd(update, ctx)
    if text == "🎯 Цель":
        return await goal_cmd(update, ctx)

    # Кнопки добавления
    if text == "➕ Доход":
        data["pending"] = {"type": "income"}
        save_data(user_id, data)
        await update.message.reply_text(
            "Введи сумму и описание:\nНапример: `80000 зарплата` или просто `80000`",
            parse_mode="Markdown"
        )
        return

    if text == "➖ Расход":
        data["pending"] = {"type": "expense"}
        save_data(user_id, data)
        await update.message.reply_text(
            "Введи сумму и описание:\nНапример: `350 кофе` или просто `350`",
            parse_mode="Markdown"
        )
        return

    # Быстрый ввод: "кофе 350" или "350 кофе" или "зарплата 80000"
    parts = text.split()
    amount = None
    desc_parts = []

    for p in parts:
        try:
            amount = float(p.replace(",", "."))
        except:
            desc_parts.append(p)

    if amount and amount > 0:
        desc = " ".join(desc_parts) if desc_parts else ""
        pending_type = data.get("pending", {}).get("type") if data.get("pending") else None

        # Определяем тип если не задан — по ключевым словам
        if pending_type is None:
            income_words = ["зарплата", "доход", "получил", "оплата", "клиент", "фриланс", "заработал", "перевод"]
            pending_type = "income" if any(w in desc.lower() for w in income_words) else "expense"

        # Показываем кнопки категорий
        cats = CATS_INCOME if pending_type == "income" else CATS_EXPENSE
        data["pending"] = {"type": pending_type, "amount": amount, "desc": desc}
        save_data(user_id, data)

        buttons = []
        cat_items = list(cats.items())
        for i in range(0, len(cat_items), 2):
            row = [InlineKeyboardButton(cat_items[i][1], callback_data=f"cat_{cat_items[i][0]}")]
            if i + 1 < len(cat_items):
                row.append(InlineKeyboardButton(cat_items[i+1][1], callback_data=f"cat_{cat_items[i+1][0]}"))
            buttons.append(row)

        sign = "+" if pending_type == "income" else "−"
        await update.message.reply_text(
            f"{'💚' if pending_type == 'income' else '❤️'} {sign}{fmt(amount)}"
            + (f" — {desc}" if desc else "") + "\n\nВыбери категорию:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # Если ничего не поняли
    await update.message.reply_text(
        "Не понял 🤔\n\nПопробуй так:\n`350 кофе` — расход\n`80000 зарплата` — доход\n\nИли используй кнопки ниже 👇",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# ─── ВЫБОР КАТЕГОРИИ ──────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = load_data(user_id)
    pending = data.get("pending")

    if not pending or "amount" not in pending:
        await query.edit_message_text("Что-то пошло не так, попробуй ещё раз.")
        return

    if query.data.startswith("cat_"):
        cat_id = query.data[4:]
        tx = {
            "id": int(datetime.now().timestamp() * 1000),
            "type": pending["type"],
            "cat": cat_id,
            "desc": pending.get("desc") or (CATS_INCOME if pending["type"] == "income" else CATS_EXPENSE).get(cat_id, ""),
            "amount": pending["amount"],
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        if "transactions" not in data:
            data["transactions"] = []
        data["transactions"].append(tx)
        data["pending"] = None
        save_data(user_id, data)

        cats = CATS_INCOME if tx["type"] == "income" else CATS_EXPENSE
        cat_label = cats.get(cat_id, cat_id)
        sign = "+" if tx["type"] == "income" else "−"

        # Считаем новый баланс месяца
        month_txs = get_month_txs(data["transactions"])
        t = totals(month_txs)
        pct = round(t["income"] / GOAL * 100)

        await query.edit_message_text(
            f"✅ Записано!\n\n"
            f"{cat_label} {sign}{fmt(tx['amount'])}\n"
            f"{'📝 ' + tx['desc'] if tx['desc'] else ''}\n\n"
            f"📊 Месяц: доходы {fmt(t['income'])} / расходы {fmt(t['expense'])}\n"
            f"🎯 Прогресс к цели: {pct}%"
        )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("goal", goal_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
