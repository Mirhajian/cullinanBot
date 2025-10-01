from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import base64
from urllib.parse import urljoin

app = Flask(__name__)

BASE = "https://self.birjandut.ac.ir"
LOGIN_URL = BASE + "/Login.aspx"
RESERVE_URL = BASE + "/Reservation/Reservation.aspx"

# نگهداری session و hidden fields به‌ازای username
user_sessions = {}  # username -> {"session": Session(), "hidden": {}, "password": ""}

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
    
    # تلاش برای یافتن تگ img مرتبط
    img = soup.find("img", id=lambda x: x and "captcha" in x.lower()) or \
          soup.find("img", src=lambda x: x and "captcha" in x.lower())
    
    # اگر img پیدا نشد، همه img ها را چک کن
    if not img:
        for potential_img in soup.find_all("img"):
            if potential_img.has_attr("src"):
                src = potential_img["src"].lower()
                if "captcha" in src or "botdetect" in src:
                    img = potential_img
                    break
    
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
            # تشخیص نوع تصویر
            content_type = r.headers.get("Content-Type", "")
            if not content_type or content_type == "application/octet-stream":
                if data[:4] == b'\x89PNG':
                    content_type = "image/png"
                elif data[:3] == b'GIF':
                    content_type = "image/gif"
                elif data[:2] == b'\xff\xd8':
                    content_type = "image/jpeg"
                else:
                    content_type = "image/png"
            return "data:{};base64,{}".format(content_type, b64)
    except Exception as e:
        print(f"Error fetching captcha: {e}")
        return None
    return None

def is_logged_in(url, html):
    """چک کردن اینکه آیا لاگین موفق بوده"""
    # URL های موفقیت
    success_urls = ["Reservation.aspx", "ChangePassword.aspx", "MyCullinan"]
    for success_url in success_urls:
        if success_url in url:
            return True
    
    # اگر در HTML صفحه لاگین نباشیم
    if "txtUsername" not in html and "txtPassword" not in html:
        return True
    
    return False

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

    hidden = get_hidden_fields(r.text)
    captcha_info = find_captcha_info(r.text)
    debug['has_captcha'] = bool(captcha_info)

    # اگر کپچا داشته باشیم، session و hidden fields را ذخیره کن
    if captcha_info:
        img_b64 = None
        if captcha_info.get("img_src"):
            img_b64 = fetch_captcha_image(session, captcha_info["img_src"])
            debug['captcha_img'] = img_b64
            debug['captcha_src'] = captcha_info["img_src"]
        
        # ذخیره session، hidden fields و password برای استفاده بعدی
        user_sessions[username] = {
            "session": session,
            "hidden": hidden,
            "password": password
        }
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

    # چک موفقیت لاگین
    if is_logged_in(r2.url, r2.text):
        user_sessions[username] = {
            "session": session,
            "hidden": {},
            "password": password
        }
        debug['login_success'] = True
        return session, debug

    # چک مجدد کپچا
    captcha_after = find_captcha_info(r2.text)
    if captcha_after:
        debug['has_captcha_after_post'] = True
        if captcha_after.get("img_src"):
            debug['captcha_img_after'] = fetch_captcha_image(session, captcha_after["img_src"])
        user_sessions[username] = {
            "session": session,
            "hidden": get_hidden_fields(r2.text),
            "password": password
        }
        return session, debug

    return None, debug

def get_all_menus(session):
    try:
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
    except Exception as e:
        print(f"Error getting menus: {e}")
        return []

@app.route("/menu", methods=["GET"])
def menu():
    username = request.args.get("username")
    password = request.args.get("password")
    if not username or not password:
        return jsonify({"error": "username & password required"}), 400

    # چک session موجود
    if username in user_sessions:
        session_data = user_sessions[username]
        session = session_data["session"]
        try:
            menus = get_all_menus(session)
            if menus:
                return jsonify({"ok": True, "menus": menus})
        except:
            pass  # session منقضی شده، ادامه به login جدید

    # تلاش لاگین
    session, debug = attempt_login(username, password)
    
    if debug.get('has_captcha') or debug.get('has_captcha_after_post'):
        return jsonify({"ok": False, "reason": "captcha_required", "debug": debug}), 200

    if session is None:
        return jsonify({"ok": False, "reason": "login_failed", "debug": debug}), 200

    # لاگین موفق
    menus = get_all_menus(session)
    if menus:
        return jsonify({"ok": True, "menus": menus, "debug": debug})
    else:
        # لاگین موفق ولی منو نیست - ممکن است تغییر رمز لازم باشد
        debug['warning'] = 'Login succeeded but no menus found. May need password change.'
        return jsonify({"ok": True, "menus": [], "debug": debug})

@app.route("/captcha", methods=["POST"])
def solve_captcha():
    """
    حل کپچا با استفاده از session و hidden fields ذخیره‌شده
    payload JSON:
    { "username": "xxx", "password": "xxx", "captcha_answer": "abcd" }
    """
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    captcha_answer = data.get("captcha_answer")
    
    if not username or not captcha_answer:
        return jsonify({"error": "username & captcha_answer required"}), 400
    
    if username not in user_sessions:
        return jsonify({"error": "no session for this user; call /menu first to get captcha"}), 400

    session_data = user_sessions[username]
    session = session_data["session"]
    hidden = session_data["hidden"]
    saved_password = session_data["password"]
    
    # استفاده از password ذخیره‌شده یا password جدید
    pwd = password if password else saved_password
    if not pwd:
        return jsonify({"error": "password required"}), 400

    # استفاده از hidden fields ذخیره‌شده (همان صفحه‌ای که کپچا از آن آمده)
    payload = {**hidden,
               "txtUsername": username,
               "txtPassword": pwd,
               "txtCaptcha": captcha_answer,
               "btnLogin": "ورود"}
    
    try:
        r2 = session.post(LOGIN_URL, data=payload, allow_redirects=True, timeout=15)
    except Exception as e:
        return jsonify({"ok": False, "reason": f"POST failed: {e}"}), 500
    
    debug = {
        "post_status": r2.status_code,
        "post_url": r2.url,
        "final_url": r2.url
    }
    
    # چک موفقیت لاگین با تابع جدید
    if is_logged_in(r2.url, r2.text):
        # موفق!
        user_sessions[username] = {
            "session": session,
            "hidden": {},
            "password": pwd
        }
        debug['login_success'] = True
        
        # تلاش برای گرفتن منو
        menus = get_all_menus(session)
        
        if menus:
            return jsonify({"ok": True, "menus": menus, "debug": debug})
        else:
            # لاگین موفق اما منو خالی - احتمالاً باید رمز عوض شود
            debug['warning'] = 'Login successful but redirected to password change. No menus available.'
            debug['redirect_url'] = r2.url
            return jsonify({
                "ok": True, 
                "menus": [], 
                "debug": debug,
                "message": "Login successful but you may need to change your password via web browser first."
            })
    else:
        # شکست - احتمالاً کپچا اشتباه
        debug['head_snippet'] = r2.text[:1000]
        # چک کنیم کپچای جدید هست یا نه
        captcha_check = find_captcha_info(r2.text)
        if captcha_check:
            debug['new_captcha_detected'] = True
            if captcha_check.get("img_src"):
                debug['new_captcha_img'] = fetch_captcha_image(session, captcha_check["img_src"])
            # به‌روزرسانی hidden fields
            user_sessions[username]["hidden"] = get_hidden_fields(r2.text)
            return jsonify({"ok": False, "reason": "captcha_wrong", "debug": debug}), 200
        
        return jsonify({"ok": False, "reason": "login_failed", "debug": debug}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
