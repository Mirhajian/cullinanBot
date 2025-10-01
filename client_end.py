import requests
import re
import base64
import sys
from pathlib import Path

SERVER = "http://89.42.199.5:5000"
USERNAME = "4021311150"
PASSWORD = "Abmir1382"

def save_data_uri(data_uri, out_path: Path):
    # data:image/<type>;base64,<data>
    m = re.match(r"data:(?P<mime>[^;]+);base64,(?P<b64>.+)", data_uri)
    if not m:
        raise ValueError("invalid data uri")
    b = base64.b64decode(m.group("b64"))
    out_path.write_bytes(b)
    
    # تشخیص extension از mime
    mime = m.group("mime")
    ext = {"image/png":"png", "image/gif":"gif", "image/jpeg":"jpg"}.get(mime, "png")
    out_with_ext = out_path.with_suffix("." + ext)
    out_path.rename(out_with_ext)
    
    return out_with_ext

def get_menu():
    r = requests.get(f"{SERVER}/menu", params={"username": USERNAME, "password": PASSWORD}, timeout=30)
    return r.json()

def post_captcha(captcha_answer):
    payload = {"username": USERNAME, "password": PASSWORD, "captcha_answer": captcha_answer}
    r = requests.post(f"{SERVER}/captcha", json=payload, timeout=30)
    return r.json()

def main():
    print("Requesting /menu ...")
    res = get_menu()
    print("Response:", res.get("ok", None), res.get("reason", "no-reason"))
    
    if res.get("ok"):
        print("✅ Login successful!")
        menus = res.get("menus", [])
        
        if menus:
            print("\n📋 Menus received:")
            for m in menus:
                print(f"\n🍽  {m.get('title')}")
                for f in m.get("foods", []):
                    print(f"   • {f}")
        else:
            print("\n⚠️  Login successful but no menus available.")
            debug = res.get("debug", {})
            if "ChangePassword" in debug.get("redirect_url", ""):
                print("❗ Your account requires a password change.")
                print("   Please login via web browser and change your password first:")
                print("   https://self.birjandut.ac.ir/Login.aspx")
            else:
                print("   This might mean there are no meals scheduled yet.")
        return

    # not ok -> maybe captcha_required
    debug = res.get("debug") or {}
    
    if debug.get("captcha_img"):
        print("\n🔐 Captcha detected. Saving image...")
        try:
            out_path = save_data_uri(debug["captcha_img"], Path("./captcha_img"))
            print(f"✅ Saved captcha image to: {out_path.resolve()}")
            print(f"📷 Captcha source: {debug.get('captcha_src', 'unknown')}")
            print("\n👉 لطفاً فایل تصویر را باز کن و متن کپچا را دقیق وارد کن.")
            print("   (معمولاً ۴ رقم است و case-sensitive ممکن است باشد)")
        except Exception as e:
            print(f"❌ Failed to save captcha image: {e}")
            sys.exit(1)

        captcha_answer = input("\n🔢 Captcha answer: ").strip()
        
        if not captcha_answer:
            print("❌ Captcha answer cannot be empty!")
            sys.exit(1)
            
        print("📤 Sending captcha answer to server...")
        res2 = post_captcha(captcha_answer)
        
        print(f"\n📥 Response: {res2.get('ok', False)} - {res2.get('reason', 'no-reason')}")
        
        if res2.get("ok"):
            print("✅ Login successful after captcha!")
            menus = res2.get("menus", [])
            
            if menus:
                print("\n📋 Menus:")
                for m in menus:
                    print(f"\n🍽  {m.get('title')}")
                    for f in m.get("foods", []):
                        print(f"   • {f}")
            else:
                print("\n⚠️  Login successful but no menus available.")
                msg = res2.get("message", "")
                if msg:
                    print(f"   {msg}")
                debug2 = res2.get("debug", {})
                if "ChangePassword" in debug2.get("redirect_url", ""):
                    print("\n❗ Your account requires a password change.")
                    print("   Please login via web browser first:")
                    print("   https://self.birjandut.ac.ir/Login.aspx")
        else:
            reason = res2.get("reason", "unknown")
            print(f"❌ Login failed: {reason}")
            
            if reason == "captcha_wrong":
                print("   The captcha answer was incorrect. Try again with /menu")
                debug2 = res2.get("debug", {})
                if debug2.get("new_captcha_img"):
                    print("   A new captcha is available - run the script again.")
            else:
                print("   Debug info:", res2.get("debug"))
    else:
        print("❌ No captcha image found but login failed.")
        print("Debug:", debug)

if __name__ == "__main__":
    main()
