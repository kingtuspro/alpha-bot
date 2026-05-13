import requests

url = "https://api.bybit.com/v5/market/tickers?category=linear"

try:

    r = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    print("STATUS:", r.status_code)

    print("TEXT:")
    print(r.text[:2000])

except Exception as e:

    print("ERROR:", e)
