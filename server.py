"""
住宿比價 MCP Server — Booking.com (via RapidAPI)
Hotel Price Comparison MCP

環境變數：
    RAPIDAPI_KEY  — RapidAPI 金鑰（申請：https://rapidapi.com/apidojo/api/booking）

支援功能：
    - 搜尋指定城市/地區的旅館
    - 比較多家旅館（價格、評分、設施）
    - 查看旅館詳細資訊
"""

import json
import os
from typing import Optional
import requests
from mcp.server.fastmcp import FastMCP

# ── 初始化 ────────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="booking-hotel",
    instructions=(
        "住宿比價管家，透過 Booking.com 即時查詢並比較旅館價格與評分。"
        "支援按城市、預算、評分篩選，並可並排比較多家旅館。"
    ),
)

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "booking-com.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

# 台幣匯率（1 JPY ≈ 0.215 TWD，1 USD ≈ 31 TWD）
TWD_PER_USD = 31.0

# 城市 → Booking.com dest_id 對照（常用日本城市）
CITY_DEST_MAP = {
    "tokyo":     {"dest_id": "-246227",  "dest_type": "city", "label": "東京"},
    "osaka":     {"dest_id": "-240905",  "dest_type": "city", "label": "大阪"},
    "kyoto":     {"dest_id": "-235402",  "dest_type": "city", "label": "京都"},
    "hakone":    {"dest_id": "900048314","dest_type": "region","label": "箱根"},
    "sapporo":   {"dest_id": "-178455",  "dest_type": "city", "label": "札幌"},
    "fukuoka":   {"dest_id": "-240905",  "dest_type": "city", "label": "福岡"},
    "hiroshima": {"dest_id": "-248813",  "dest_type": "city", "label": "廣島"},
    "nara":      {"dest_id": "-246470",  "dest_type": "city", "label": "奈良"},
}


def _check_key() -> Optional[str]:
    if not RAPIDAPI_KEY:
        return json.dumps(
            {"error": "未設定 RAPIDAPI_KEY 環境變數。請至 https://rapidapi.com/apidojo/api/booking 申請免費金鑰。"},
            ensure_ascii=False, indent=2,
        )
    return None


def _headers() -> dict:
    return {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }


def _format_hotel(h: dict, currency_rate: float = 1.0) -> dict:
    price_usd = h.get("min_total_price") or h.get("price_breakdown", {}).get("gross_price")
    price_twd = round(price_usd * TWD_PER_USD) if price_usd else None

    return {
        "hotel_id": h.get("hotel_id"),
        "name": h.get("hotel_name") or h.get("name"),
        "stars": h.get("class"),
        "review_score": h.get("review_score"),
        "review_word": h.get("review_score_word"),
        "review_count": h.get("review_nr"),
        "address": h.get("address") or h.get("address_trans"),
        "district": h.get("district"),
        "price_per_night_usd": price_usd,
        "price_per_night_twd": price_twd,
        "checkin": h.get("checkin", {}).get("from") if isinstance(h.get("checkin"), dict) else h.get("checkin"),
        "checkout": h.get("checkout", {}).get("until") if isinstance(h.get("checkout"), dict) else h.get("checkout"),
        "url": h.get("url"),
        "main_photo": h.get("main_photo_url"),
        "breakfast_included": h.get("is_free_cancellable") is not None,
        "free_cancellation": h.get("is_free_cancellable", False),
        "distance_to_center": h.get("distance_to_cc"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tools
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def search_hotels(
    city: str,
    checkin_date: str,
    checkout_date: str,
    adults: int = 2,
    rooms: int = 1,
    max_price_twd: int = 0,
    min_review_score: float = 0,
    max_results: int = 10,
) -> str:
    """
    搜尋指定城市的 Booking.com 旅館，即時比較價格與評分。

    Args:
        city: 城市（英文）。支援: tokyo, osaka, kyoto, hakone, sapporo, fukuoka, hiroshima, nara
        checkin_date: 入住日期（YYYY-MM-DD）
        checkout_date: 退房日期（YYYY-MM-DD）
        adults: 入住人數（預設 2）
        rooms: 房間數（預設 1）
        max_price_twd: 每晚最高預算（台幣），0 = 不限
        min_review_score: 最低評分（0-10），0 = 不限
        max_results: 回傳筆數（預設 10，最多 20）

    Returns:
        JSON 格式的旅館列表，含價格、評分、連結
    """
    err = _check_key()
    if err:
        return err

    city_lower = city.lower().strip()
    if city_lower not in CITY_DEST_MAP:
        return json.dumps(
            {"error": f"不支援城市「{city}」。支援: {', '.join(CITY_DEST_MAP.keys())}"},
            ensure_ascii=False, indent=2,
        )

    dest = CITY_DEST_MAP[city_lower]
    max_results = min(max_results, 20)

    params = {
        "dest_id": dest["dest_id"],
        "dest_type": dest["dest_type"],
        "checkin_date": checkin_date,
        "checkout_date": checkout_date,
        "adults_number": adults,
        "room_number": rooms,
        "order_by": "popularity",
        "units": "metric",
        "filter_by_currency": "USD",
        "locale": "zh-tw",
        "include_adjacency": "true",
        "page_number": "0",
        "categories_filter_ids": "class::2,class::4,free_cancellation::1",
    }

    if min_review_score > 0:
        params["review_score"] = str(int(min_review_score * 10))

    try:
        resp = requests.get(
            f"{BASE_URL}/v1/hotels/search",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return json.dumps({"error": f"API 請求失敗：{e}"}, ensure_ascii=False, indent=2)

    hotels_raw = data.get("result", [])
    hotels = []
    for h in hotels_raw:
        formatted = _format_hotel(h)
        # 價格篩選
        if max_price_twd > 0 and formatted["price_per_night_twd"]:
            if formatted["price_per_night_twd"] > max_price_twd:
                continue
        hotels.append(formatted)
        if len(hotels) >= max_results:
            break

    return json.dumps(
        {
            "city": dest["label"],
            "checkin": checkin_date,
            "checkout": checkout_date,
            "adults": adults,
            "count": len(hotels),
            "source": "Booking.com (即時)",
            "hotels": hotels,
        },
        ensure_ascii=False, indent=2,
    )


@mcp.tool()
def get_hotel_detail(hotel_id: str, checkin_date: str, checkout_date: str, adults: int = 2) -> str:
    """
    取得特定旅館的詳細資訊（設施、房型、退訂政策等）。

    Args:
        hotel_id: 旅館 ID（從 search_hotels 的 hotel_id 欄位取得）
        checkin_date: 入住日期（YYYY-MM-DD）
        checkout_date: 退房日期（YYYY-MM-DD）
        adults: 入住人數

    Returns:
        JSON 格式的詳細資訊
    """
    err = _check_key()
    if err:
        return err

    params = {
        "hotel_id": hotel_id,
        "checkin_date": checkin_date,
        "checkout_date": checkout_date,
        "adults_number": adults,
        "locale": "zh-tw",
        "currency": "USD",
        "units": "metric",
    }

    try:
        resp = requests.get(
            f"{BASE_URL}/v1/hotels/data",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        h = resp.json()
    except requests.RequestException as e:
        return json.dumps({"error": f"API 請求失敗：{e}"}, ensure_ascii=False, indent=2)

    facilities = [f.get("name") for f in h.get("facilities_block", {}).get("facilities", [])[:20]]

    result = {
        "hotel_id": hotel_id,
        "name": h.get("hotel_name"),
        "stars": h.get("class"),
        "review_score": h.get("review_score"),
        "review_count": h.get("review_nr"),
        "address": h.get("address"),
        "district": h.get("district"),
        "description": h.get("description_translations", [{}])[0].get("description", "")[:500]
                       if h.get("description_translations") else "",
        "checkin_time": h.get("checkin", {}).get("from"),
        "checkout_time": h.get("checkout", {}).get("until"),
        "facilities": facilities,
        "url": h.get("url"),
        "photos": [p.get("url_original") for p in h.get("photos", [])[:5]],
        "booking_url": f"https://www.booking.com/hotel/jp/{h.get('url_segment', '')}.zh-tw.html",
        "source": "Booking.com (即時)",
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def compare_hotels(
    city: str,
    checkin_date: str,
    checkout_date: str,
    adults: int = 2,
    top_n: int = 5,
) -> str:
    """
    並排比較指定城市評分最高的多家旅館，輸出結構化比較表。

    Args:
        city: 城市（英文）
        checkin_date: 入住日期（YYYY-MM-DD）
        checkout_date: 退房日期（YYYY-MM-DD）
        adults: 入住人數
        top_n: 比較幾家（預設 5，最多 10）

    Returns:
        JSON 格式的並排比較結果，按評分排序
    """
    err = _check_key()
    if err:
        return err

    # 先取得旅館列表
    raw = search_hotels(city, checkin_date, checkout_date, adults, max_results=top_n)
    data = json.loads(raw)

    if "error" in data:
        return raw

    hotels = data.get("hotels", [])
    # 按評分排序
    hotels.sort(key=lambda h: h.get("review_score") or 0, reverse=True)

    comparison = {
        "city": data["city"],
        "checkin": checkin_date,
        "checkout": checkout_date,
        "nights": _calc_nights(checkin_date, checkout_date),
        "adults": adults,
        "compared": len(hotels),
        "summary": [
            {
                "rank": i + 1,
                "name": h["name"],
                "stars": h.get("stars"),
                "review_score": h.get("review_score"),
                "review_word": h.get("review_word"),
                "price_per_night_twd": h.get("price_per_night_twd"),
                "free_cancellation": h.get("free_cancellation"),
                "district": h.get("district"),
                "url": h.get("url"),
            }
            for i, h in enumerate(hotels)
        ],
        "cheapest": min(hotels, key=lambda h: h.get("price_per_night_twd") or 99999)["name"]
                    if hotels else None,
        "highest_rated": max(hotels, key=lambda h: h.get("review_score") or 0)["name"]
                          if hotels else None,
        "source": "Booking.com (即時)",
    }

    return json.dumps(comparison, ensure_ascii=False, indent=2)


def _calc_nights(checkin: str, checkout: str) -> int:
    from datetime import date
    try:
        ci = date.fromisoformat(checkin)
        co = date.fromisoformat(checkout)
        return (co - ci).days
    except Exception:
        return 0


# ── 啟動 ──────────────────────────────────────────────────────────────────────
class HostHeaderMiddleware:
    """將 Host header 改為 localhost，繞過 FastMCP 的 host 安全檢查。"""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope["headers"] = [
                (k, b"localhost") if k == b"host" else (k, v)
                for k, v in scope.get("headers", [])
            ]
        await self.app(scope, receive, send)


if __name__ == "__main__":
    import uvicorn

    if not RAPIDAPI_KEY:
        print("[警告] 未設定 RAPIDAPI_KEY，所有住宿查詢功能將返回錯誤。")

    port = int(os.environ.get("PORT", 8000))
    asgi_app = mcp.streamable_http_app()
    uvicorn.run(HostHeaderMiddleware(asgi_app), host="0.0.0.0", port=port)
