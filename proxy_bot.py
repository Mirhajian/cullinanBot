from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

BASE = "https://self.birjandut.ac.ir"
RESERVE_URL = BASE + "/Reservation/Reservation.aspx"

@app.route("/menu", methods=["GET"])
def get_menu():
    # دریافت session cookies یا پارامترها از درخواست (اختیاری)
    # ساده‌ترین حالت: بدون login (یا اگر login لازم است، اینجا اضافه کن)
    
    session = requests.Session()
    session.trust_env = False
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
            menus.append({"title": title, "foods": foods})
    return jsonify(menus)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

