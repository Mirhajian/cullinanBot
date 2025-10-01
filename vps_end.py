from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import base64
import io
from urllib.parse import urljoin

app = Flask(__name__)

BASE = "https://self.birjandut.ac.ir"
LOGIN_URL = BASE + "/Login.aspx"
RESERVE_URL = BASE + "/Reservation/Reservation.aspx"

# نگهداری سشن لاگین‌شده به‌ازای یوزرنیم
user_sessions = {}  # username -> requests.Session()

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

def find_captcha_info(html):
    """بررسی وجود فیلد کپچا و تلاش برای پیدا کردن URL تصویر کپچا"""
    soup = BeautifulSoup(html, "html.parser")
    captcha_input = soup.find("input", {"name": "txtCaptcha"})
    if not captcha_input:
        return None
    # تلاش برای یافتن تگ img مرتبط (انواع احتمالی)
    img = None
    # نمونه: <img id="imgCaptcha" src="...">
    img = soup.find("img", id=lambda x: x and "captcha" in x.lower()) or \
          soup.find("img", src=lambda x: x and "captcha" in x.lower()) or \
          soup.find("img")
    if img and img.has_attr("src"):
        return {"has_captcha": True, "img_src": img["src"]}
    return {"has_captcha": True, "img_src": None}

def fetch_captcha_image(session, img_src):
    if not img_src:
        return None
    img_url = urljoin(BASE, img_src)
    try:
        r = session.get(img_url, stream=True, timeout=10)
        if r.status_code == 200:
            data = r.content
            b64 = base64.b64encode(data).decode('ascii')
            return "data:{};base64,{}".format(r.headers.get("Content-Type","image/png"), b64)
    except Exception as e:
        return None
    return None

def attempt_login(username, password):
    session = requests.Session()
    session.trust_env = False
    debug = {}
    try:
        r = session.get(LOGIN_URL, timeout=15)
    except Exception as e:
        debug['error'] = f"GET login failed: {e}"
        return None, debug

    debug['login_get_status'] = r.status_code
    debug['login_get_url'] = r.url
    debug['login_get_head_snippet'] = r.text[:800]

    hidden = get_hidden_fields(r.text)
    captcha_info = find_captcha_info(r.text)
    debug['has_captcha'] = bool(captcha_info)

    # اگر کپچا داشته باشیم، سعی می‌کنیم تصویر را بگیریم و بازگردانیم (بدون لاگین)
    if captcha_info and captcha_info.get("img_src"):
        img_b64 = fetch_captcha_image(session, captcha_info["img_src"])
        debug['captcha_img'] = img_b64

    # اگر کپچا هست، اینجا لاگین خودکار را انجام نمی‌دهیم؛ caller باید captcha را ارسال کند.
    if captcha_info:
        return session, debug

    # بدون کپچا --> تلاش به لاگین معمولی
    payload = {**hidden,
               "txtUsername": username,
               "txtPassword": password,
               "txtCaptcha": "",
               "btnLogin": "ورود"}
    try:
        r2 = session.post(LOGIN_URL, data=payload, allow_redirects=True, timeout=15)
    except Exception as e:
        debug['error'] = f"POST login failed: {e}"
        return None, debug

    debug['login_post_status'] = r2.status_code
    debug['login_post_url'] = r2.url
    debug['login_post_head_snippet'] = r2.text[:800]

    # اگر ریدایرکت به Reservation یا صفحه‌ای که منو دارد رخ دهد
    if "Reservation.aspx" in r2.url or "Reservation" in r2.url:
        return session, debug

    # احتمالاً لاگین شکست خورده یا کپچا/صفحه دیگری برگشته
    # بررسی مجدد وجود captcha پس از POST
    captcha_after = find_captcha_info(r2.text)
    if captcha_after and captcha_after.get("img_src"):
        debug['has_captcha_after_post'] = True
        debug['captcha_img_after'] = fetch_captcha_image(session, captcha_after["img_src"])
        return session, debug

    # در غیر این صورت لاگین ناموفق
    return None, debug

def get_all_menus(session):
    r = session.get(RESERVE_URL, timeout=15)
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
            menus.append({"title": title, "foods": foods})
    return menus

@app.route("/menu", methods=["GET"])
def menu():
    username = request.args.get("username")
    password = request.args.get("password")
    if not username or not password:
        return jsonify({"error": "username & password required"}), 400

    # اگر session از قبل داریم و ظاهراً لاگین است، از آن استفاده کن
    if username in user_sessions:
        session = user_sessions[username]
        menus = get_all_menus(session)
        if menus:
            return jsonify({"ok": True, "menus": menus})
        # اگر session موجود اما منو خالیه، سعی می‌کنیم مجدد login کنیم
    # تلاش لاگین (یا بررسی کپچا)
    session, debug = attempt_login(username, password)
    # اگر attempt_login فقط session برگرداند ولی کپچا داشت، session برگشته ولی باید کپچا حل شود
    if debug.get('has_captcha') or debug.get('has_captcha_after_post'):
        # نگهداری session برای ادامه (کاربر باید کپچا را حل کند)
        user_sessions[username] = session
        return jsonify({"ok": False, "reason": "captcha_required", "debug": debug}), 200

    if session is None:
        # لاگین شکست خورده، debug را برگردان
        return jsonify({"ok": False, "reason": "login_failed", "debug": debug}), 200

    # لاگین موفق
    user_sessions[username] = session
    menus = get_all_menus(session)
    return jsonify({"ok": True, "menus": menus, "debug": debug})

@app.route("/captcha", methods=["POST"])
def solve_captcha():
    """
    وقتی سروِر قبلاً کپچا را برگردانده، این endpoint را صدا بزن:
    payload JSON:
    { "username": "xxx", "captcha_answer": "abcd" }
    """
    data = request.get_json() or {}
    username = data.get("username")
    captcha_answer = data.get("captcha_answer")
    if not username or not captcha_answer:
        return jsonify({"error": "username & captcha_answer required"}), 400
    if username not in user_sessions:
        return jsonify({"error": "no session for this user; start /menu first to get captcha"}), 400

    session = user_sessions[username]
    # دوباره GET login page تا hidden fields بگیریم
    r = session.get(LOGIN_URL, timeout=15)
    hidden = get_hidden_fields(r.text)
    # لازم است password را (یا ذخیره کرده باشیم) داشته باشیم؛ برای امنیت نگه نداشتیم.
    # این تابع فرض می‌کند رمز را در same user_sessions ذخیره کرده‌ایم یا کاربر قبلاً آن را فرستاده.
    # اگر رمز نگهداری نشده، خطا می‌دیم.
    # (توصیه: این مثال برای تست است. در تولید، رمز را امن ذخیره کن.)
    pwd = request.args.get("password") or data.get("password")
    if not pwd:
        return jsonify({"error": "password required in this request to complete login"}), 400

    payload = {**hidden,
               "txtUsername": username,
               "txtPassword": pwd,
               "txtCaptcha": captcha_answer,
               "btnLogin": "ورود"}
    r2 = session.post(LOGIN_URL, data=payload, allow_redirects=True, timeout=15)
    debug = {"post_status": r2.status_code, "post_url": r2.url}
    if "Reservation.aspx" in r2.url or "Reservation" in r2.url:
        menus = get_all_menus(session)
        return jsonify({"ok": True, "menus": menus, "debug": debug})
    else:
        debug['head_snippet'] = r2.text[:800]
        return jsonify({"ok": False, "reason": "captcha_wrong_or_login_failed", "debug": debug}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000")

