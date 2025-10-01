import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)
import requests
from bs4 import BeautifulSoup

# ---- تنظیمات ----
BOT_TOKEN = "8470631705:AAEQQzw8GmdqsCRhi05hav4zGxXMTiZM2zs"
BASE = "https://self.birjandut.ac.ir"
LOGIN_URL = BASE + "/Login.aspx"
RESERVE_URL = BASE + "/Reservation/Reservation.aspx"

# ---- لاگ ها ----
logging.basicConfig(level=logging.INFO)

# ---- وضعیت گفتگو ----
ASK_USERNAME, ASK_PASSWORD, ASK_CAPTCHA = range(3)

# ---- حافظه کاربران ----
user_sessions = {}  # user_id → {"session": requests.Session(), "username": ..., "password": ...}

# ---- توابع کمکی ----
def get_hidden_fields(html):
    soup = BeautifulSoup(html, "html.parser")
    def val(name):
        el = soup.find("input", {"name": name})
        return el["value"] if el and el.has_attr("value") else ""
    return {
        "__VIEWSTATE": val("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": val("__EVENTVALIDATION"),
        "__VIEWSTATEENCRYPTED": val("__VIEWSTATEENCRYPTED"),
        "__EVENTTARGET": val("__EVENTTARGET"),
        "__EVENTARGUMENT": val("__EVENTARGUMENT"),
    }

def login(session, username, password, captcha=None):
    r = session.get(LOGIN_URL)
    soup = BeautifulSoup(r.text, "html.parser")
    hidden = get_hidden_fields(r.text)

    payload = {}
    payload.update(hidden)
    payload.update({
        "txtUsername": username,
        "txtPassword": password,
        "txtCaptcha": captcha or "",
        "btnLogin": "ورود",
    })

    r2 = session.post(LOGIN_URL, data=payload, allow_redirects=True)
    return r2

def get_all_menus(session):
    r = session.get(RESERVE_URL)
    soup = BeautifulSoup(r.text, "html.parser")
    menus = []
    tables = soup.select("table.GridView")
    for tbl in tables:
        title_el = tbl.find_previous("span") or tbl.find_previous("h3")
        title = title_el.get_text(strip=True) if title_el else "سلف ناشناخته"

        rows = tbl.find_all("tr")
        foods = []
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if cols:
                foods.append(" | ".join(cols))
        if foods:
            menus.append((title, foods))
    return menus

# ---- هندلرها ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! شماره دانشجویی‌ت رو بفرست:")
    return ASK_USERNAME

async def ask_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["username"] = update.message.text.strip()
    await update.message.reply_text("رمز عبورت رو بفرست:")
    return ASK_PASSWORD

async def ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["password"] = update.message.text.strip()

    # ساخت session
    session = requests.Session()
    resp = login(session, context.user_data["username"], context.user_data["password"])

    if "Reservation.aspx" in resp.url:
        # موفق
        user_sessions[update.effective_user.id] = {
            "session": session,
            "username": context.user_data["username"],
            "password": context.user_data["password"],
        }
        await update.message.reply_text("✅ ورود موفق! حالا /menu رو بزن تا غذاها رو ببینی.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ ورود ناموفق. دوباره /start رو بزن.")
        return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("اول باید /start بزنی و لاگین کنی.")
        return

    session = user_sessions[user_id]["session"]
    menus = get_all_menus(session)

    if not menus:
        await update.message.reply_text("منوی غذا پیدا نشد ❌")
        return

    text = ""
    for title, foods in menus:
        text += f"🍽 {title}:\n"
        for f in foods:
            text += f" - {f}\n"
        text += "\n"

    await update.message.reply_text(text)

# ---- main ----
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_username)],
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_password)],
        },
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("menu", menu))

    app.run_polling()

if __name__ == "__main__":
    main()

