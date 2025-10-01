import requests

r = requests.get(
    "http://89.42.199.5:5000/menu",
    params={"username": "4021311150", "password": "Abmir1382"}
)
print(r.json())

