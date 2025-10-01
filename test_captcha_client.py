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
    return out_path

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
        print("Menus received:")
        for m in res.get("menus", []):
            print("==", m.get("title"))
            for f in m.get("foods", []):
                print("  -", f)
        return

    # not ok -> maybe captcha_required
    debug = res.get("debug") or {}
    if debug.get("captcha_img"):
        print("Captcha detected. Saving image to ./captcha_img.*")
        try:
            out = save_data_uri(debug["captcha_img"], Path("./captcha_img"))
            # ensure extension by sniffing mime
            mime = debug["captcha_img"].split(";")[0].split(":")[1]
            ext = {"image/png":"png", "image/gif":"gif", "image/jpeg":"jpg"}.get(mime, "bin")
            out_with_ext = out.with_suffix("." + ext)
            out.rename(out_with_ext)
            print("Saved captcha image to:", out_with_ext.resolve())
            print("لطفاً فایل را باز کن (یا ببین) و متن کپچا را وارد کن.")
        except Exception as e:
            print("Failed to save captcha image:", e)
            sys.exit(1)

        captcha_answer = input("Captcha answer: ").strip()
        print("Sending captcha answer to server...")
        res2 = post_captcha(captcha_answer)
        print("Response after captcha:", res2)
        if res2.get("ok"):
            print("Login + menus OK:")
            for m in res2.get("menus", []):
                print("==", m.get("title"))
                for f in m.get("foods", []):
                    print("  -", f)
        else:
            print("Login failed after captcha. Debug:", res2.get("debug"))
    else:
        print("No captcha image found. Debug:", debug)
        print("Maybe login failed for other reasons. Print full response:")
        print(res)

if __name__ == "__main__":
    main()

