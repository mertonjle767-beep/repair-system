#!/usr/bin/env python3
"""每日台股追蹤：從臺灣證券交易所（TWSE）公開資料抓取

- 發行量加權股價指數（加權指數）每日收盤指數
- watchlist.json 追蹤標的每日收盤價
- 追蹤標的的除息日與每股配息（已除息紀錄＋除權除息預告）

結果寫入 data/ 的 CSV 與 data/summary.json（給 index.html 顯示）。
只使用 Python 標準函式庫，不需安裝套件。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WATCHLIST = ROOT / "watchlist.json"
BASE = "https://www.twse.com.tw/rwd/zh"
TW_TZ = dt.timezone(dt.timedelta(hours=8))
PAUSE_SECONDS = 2.5  # TWSE 有頻率限制，每次請求後暫停

TAIEX_FIELDS = ["日期", "收盤指數", "漲跌點數"]
PRICE_FIELDS = ["日期", "代號", "名稱", "收盤價", "漲跌"]
DIVIDEND_FIELDS = ["除息日", "代號", "名稱", "類型", "每股配息", "除息前收盤價", "除息參考價", "狀態"]
CONFIRMED, ANNOUNCED = "已除息", "預告"


# ---------- 解析工具 ----------

def parse_date(text: str) -> str:
    """把 TWSE 常見日期格式轉成 YYYY-MM-DD（民國年自動加 1911）。"""
    s = re.sub(r"<[^>]+>", "", str(text)).strip().replace(" ", "")
    m = re.fullmatch(r"(\d{2,3})[/年](\d{1,2})[/月](\d{1,2})日?", s)
    if m:
        y, mo, d = int(m[1]) + 1911, int(m[2]), int(m[3])
    elif m := re.fullmatch(r"(\d{3})(\d{2})(\d{2})", s):  # 民國 1151113
        y, mo, d = int(m[1]) + 1911, int(m[2]), int(m[3])
    elif m := re.fullmatch(r"(\d{4})(?:[-/](\d{1,2})[-/](\d{1,2})|(\d{2})(\d{2}))", s):
        y, mo, d = int(m[1]), int(m[2] or m[4]), int(m[3] or m[5])
    else:
        raise ValueError(f"無法解析日期：{text!r}")
    return dt.date(y, mo, d).isoformat()


def parse_number(text) -> str:
    """去除 HTML、千分位與註記符號，回傳數字字串；無資料回傳空字串。"""
    s = re.sub(r"<[^>]+>", "", str(text)).replace(",", "").strip()
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return ""
    value = m[0].lstrip("+")
    return str(float(value)) if "." in value else value


def signed_change(sign_cell, value_cell) -> str:
    """MI_INDEX 類資料把漲跌符號與點數分兩欄，合併成帶正負號的數字。"""
    value = parse_number(value_cell)
    sign = re.sub(r"<[^>]+>", "", str(sign_cell)).strip()
    if value and sign == "-" and not value.startswith("-"):
        value = "-" + value
    return value


def tables(payload: dict):
    """依序產生回應中的 (欄位, 資料列)，相容 fields/data、tables[]、fieldsN/dataN 三種格式。"""
    stat = str(payload.get("stat", "OK"))
    if stat.upper() != "OK":
        return
    if "fields" in payload and "data" in payload:
        yield payload["fields"], payload["data"]
    for table in payload.get("tables") or []:
        if table.get("fields") and table.get("data") is not None:
            yield table["fields"], table["data"]
    for key in sorted(payload):
        m = re.fullmatch(r"fields(\d+)", key)
        if m and f"data{m[1]}" in payload:
            yield payload[key], payload[f"data{m[1]}"]


def column(fields, *keywords, required=True):
    clean = [re.sub(r"<[^>]+>|\s", "", str(f)) for f in fields]
    for kw in keywords:
        for i, name in enumerate(clean):
            if kw in name:
                return i
    if required:
        raise KeyError(f"找不到欄位 {keywords}，實際欄位：{clean}")
    return None


# ---------- 網路 ----------

def fetch_json(path: str, **params) -> dict:
    params["response"] = "json"
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (daily-tw-stock-tracker)",
        "Accept": "application/json",
    })
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            time.sleep(PAUSE_SECONDS)
            return payload
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(PAUSE_SECONDS * (attempt + 2))
    raise RuntimeError(f"讀取失敗：{url}（{last_error}）")


# ---------- 資料來源 ----------

def fetch_taiex_month(month: dt.date, fetch=fetch_json) -> list[dict]:
    """FMTQIK：每日市場成交資訊（含當月每日加權指數收盤）。"""
    payload = fetch("afterTrading/FMTQIK", date=month.strftime("%Y%m01"))
    rows = []
    for fields, data in tables(payload):
        i_date = column(fields, "日期")
        i_close = column(fields, "發行量加權股價指數", "加權指數")
        i_change = column(fields, "漲跌點數", required=False)
        for row in data:
            close = parse_number(row[i_close])
            if close:
                rows.append({"日期": parse_date(row[i_date]), "收盤指數": close,
                             "漲跌點數": parse_number(row[i_change]) if i_change is not None else ""})
    return rows


def fetch_taiex_day(day: dt.date, fetch=fetch_json) -> list[dict]:
    """MI_INDEX：指定日期的收盤指數。收盤後比 FMTQIK 更早更新，用來取得查詢當天的加權指數。"""
    payload = fetch("afterTrading/MI_INDEX", date=day.strftime("%Y%m%d"), type="IND")
    reported = str(payload.get("date") or "")
    if reported and reported != day.strftime("%Y%m%d"):
        return []  # 回傳的不是查詢當天（休市或尚未收盤）
    for fields, data in tables(payload):
        i_close = column(fields, "收盤指數", required=False)
        if i_close is None:
            continue
        i_sign = column(fields, "漲跌(+/-)", required=False)
        i_points = column(fields, "漲跌點數", required=False)
        for row in data:
            if re.sub(r"<[^>]+>|\s", "", str(row[0])) != "發行量加權股價指數":
                continue
            close = parse_number(row[i_close])
            if not close:
                return []
            points = row[i_points] if i_points is not None else ""
            change = signed_change(row[i_sign], points) if i_sign is not None else parse_number(points)
            return [{"日期": day.isoformat(), "收盤指數": close, "漲跌點數": change}]
    return []


def fetch_stock_month(code: str, name: str, month: dt.date, fetch=fetch_json) -> list[dict]:
    """STOCK_DAY：個股（含 ETF）當月每日成交資訊。"""
    payload = fetch("afterTrading/STOCK_DAY", date=month.strftime("%Y%m01"), stockNo=code)
    if not name:  # watchlist 沒填名稱時，從標題「115年11月 2330 台積電 各日成交資訊」取得
        m = re.search(rf"\b{re.escape(code)}\s+(.+?)\s+各日成交資訊", str(payload.get("title", "")))
        name = m[1].strip() if m else ""
    rows = []
    for fields, data in tables(payload):
        i_date = column(fields, "日期")
        i_close = column(fields, "收盤價")
        i_change = column(fields, "漲跌價差", "漲跌", required=False)
        for row in data:
            close = parse_number(row[i_close])
            if close:
                rows.append({"日期": parse_date(row[i_date]), "代號": code, "名稱": name, "收盤價": close,
                             "漲跌": parse_number(row[i_change]) if i_change is not None else ""})
    return rows


def dividend_type(text: str) -> str:
    text = re.sub(r"<[^>]+>|\s", "", str(text))
    return {"息": "除息", "權": "除權", "權息": "除權息"}.get(text, text or "")


def fetch_ex_dividends(start: dt.date, end: dt.date, names: dict, fetch=fetch_json) -> list[dict]:
    """TWT49U：除權除息計算結果表（已實際除息的紀錄）。"""
    payload = fetch("exRight/TWT49U", startDate=start.strftime("%Y%m%d"), endDate=end.strftime("%Y%m%d"))
    rows = []
    for fields, data in tables(payload):
        i_date = column(fields, "資料日期", "日期")
        i_code = column(fields, "股票代號", "代號")
        i_amount = column(fields, "權值+息值", "權值", "息值")
        i_kind = column(fields, "權/息", required=False)
        i_before = column(fields, "除權息前收盤價", required=False)
        i_ref = column(fields, "除權息參考價", required=False)
        for row in data:
            code = str(row[i_code]).strip()
            if code not in names:
                continue
            rows.append({
                "除息日": parse_date(row[i_date]), "代號": code, "名稱": names[code],
                "類型": dividend_type(row[i_kind]) if i_kind is not None else "",
                "每股配息": parse_number(row[i_amount]),
                "除息前收盤價": parse_number(row[i_before]) if i_before is not None else "",
                "除息參考價": parse_number(row[i_ref]) if i_ref is not None else "",
                "狀態": CONFIRMED,
            })
    return rows


def fetch_announced_dividends(names: dict, fetch=fetch_json) -> list[dict]:
    """TWT48U：除權除息預告表（即將除息的標的與現金股利）。"""
    payload = fetch("exRight/TWT48U")
    rows = []
    for fields, data in tables(payload):
        i_date = column(fields, "除權除息日期", "日期")
        i_code = column(fields, "股票代號", "代號")
        i_kind = column(fields, "除權息", required=False)
        i_cash = column(fields, "現金股利")
        for row in data:
            code = str(row[i_code]).strip()
            if code not in names:
                continue
            rows.append({
                "除息日": parse_date(row[i_date]), "代號": code, "名稱": names[code],
                "類型": dividend_type(row[i_kind]) if i_kind is not None else "",
                "每股配息": parse_number(row[i_cash]),
                "除息前收盤價": "", "除息參考價": "", "狀態": ANNOUNCED,
            })
    return rows


# ---------- 儲存 ----------

def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # 含 BOM，Excel 開啟不亂碼
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def upsert(existing: list[dict], new: list[dict], key_fields: list[str], keep=None) -> list[dict]:
    """以 key 合併；keep(old, new) 回傳 False 時保留舊資料。"""
    merged = {tuple(r[k] for k in key_fields): r for r in existing}
    for row in new:
        key = tuple(row[k] for k in key_fields)
        if key in merged and keep and not keep(merged[key], row):
            continue
        merged[key] = row
    return [merged[k] for k in sorted(merged)]


def keep_dividend(old: dict, new: dict) -> bool:
    # 已除息的實際紀錄不會被預告資料覆蓋
    return not (old.get("狀態") == CONFIRMED and new.get("狀態") == ANNOUNCED)


def months_back(today: dt.date, count: int) -> list[dt.date]:
    months, y, m = [], today.year, today.month
    for _ in range(max(count, 1)):
        months.append(dt.date(y, m, 1))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return list(reversed(months))


def to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def build_summary(taiex, prices, dividends, tracked, today: dt.date, recent_days=20) -> dict:
    day = today.isoformat()
    taiex = [r for r in taiex if r["日期"] <= day]  # 以查詢日為準，不顯示之後的資料
    prices = [r for r in prices if r["日期"] <= day]
    latest_taiex = taiex[-1] if taiex else None
    year_ago = (today - dt.timedelta(days=365)).isoformat()
    items = []
    for t in tracked:
        code = t["code"]
        own = [p for p in prices if p["代號"] == code]
        latest = own[-1] if own else None
        divs = [d for d in dividends if d["代號"] == code]
        past = [d for d in divs if d["狀態"] == CONFIRMED and d["除息日"] <= today.isoformat()]
        upcoming = [d for d in divs if d["除息日"] > today.isoformat()
                    or (d["狀態"] == ANNOUNCED and d["除息日"] == today.isoformat())]
        trailing = sum(to_float(d["每股配息"]) or 0 for d in past if d["除息日"] > year_ago)
        close = to_float(latest["收盤價"]) if latest else None
        items.append({
            "代號": code, "名稱": t.get("name", ""),
            "日期": latest["日期"] if latest else None,
            "收盤價": latest["收盤價"] if latest else None,
            "漲跌": latest["漲跌"] if latest else None,
            "最近除息": past[-1] if past else None,
            "下次除息": upcoming[0] if upcoming else None,
            "近12月配息": round(trailing, 4) if past else None,
            "殖利率": round(trailing / close * 100, 2) if past and close else None,
        })
    dates = sorted({r["日期"] for r in taiex} | {r["日期"] for r in prices}, reverse=True)[:recent_days]
    taiex_by_date = {r["日期"]: r for r in taiex}
    price_by_key = {(r["日期"], r["代號"]): r["收盤價"] for r in prices}
    recent = [{"日期": d, "加權指數": taiex_by_date.get(d, {}).get("收盤指數"),
               **{t["code"]: price_by_key.get((d, t["code"])) for t in tracked}} for d in dates]
    return {
        "查詢日": day,
        "更新時間": dt.datetime.now(TW_TZ).isoformat(timespec="seconds"),
        "資料來源": "臺灣證券交易所 www.twse.com.tw（FMTQIK、STOCK_DAY、TWT49U、TWT48U）",
        "加權指數": latest_taiex,
        "追蹤標的": items,
        "近期收盤": recent,
        "配息紀錄": sorted(dividends, key=lambda d: (d["除息日"], d["代號"]), reverse=True),
    }


def update(today: dt.date, month_count: int, fetch=fetch_json, data_dir: Path = DATA,
           watchlist: Path = WATCHLIST) -> dict:
    tracked = json.loads(watchlist.read_text(encoding="utf-8"))["tracked"]
    names = {t["code"]: t.get("name", "") for t in tracked}
    errors, warnings, calls = [], [], [0]

    def attempt(label, func, *args):
        calls[0] += 1
        try:
            return func(*args, fetch=fetch)
        except Exception as error:  # 單一來源失敗不影響其他資料
            errors.append(f"{label}：{error}")
            print(f"[警告] {label}：{error}", file=sys.stderr)
            return []

    new_taiex, new_prices = [], []
    for month in months_back(today, month_count):
        new_taiex += attempt(f"加權指數 {month:%Y-%m}", fetch_taiex_month, month)
        for code, name in names.items():
            new_prices += attempt(f"{code} {month:%Y-%m}", fetch_stock_month, code, name, month)

    # 查詢當天的加權指數另外抓，避免 FMTQIK 尚未更新時停在前一個交易日
    new_taiex += attempt(f"加權指數 {today}", fetch_taiex_day, today)

    # 補上 watchlist 未填的名稱，並標出查不到收盤資料的代號
    existing_codes = {r["代號"] for r in read_csv(data_dir / "prices.csv")}
    for t in tracked:
        found = [r for r in new_prices if r["代號"] == t["code"]]
        if found and not t.get("name"):
            t["name"] = names[t["code"]] = found[-1]["名稱"]
        if not found and t["code"] not in existing_codes:
            warnings.append(f"{t['code']}：查無收盤資料（代號可能有誤，或不是證交所上市證券）")
            print(f"[警告] {t['code']} 查無收盤資料", file=sys.stderr)

    new_divs = []
    start = today - dt.timedelta(days=400)  # 近 12 個月配息需要約一年資料，分段查詢
    while start <= today:
        end = min(start + dt.timedelta(days=89), today)
        new_divs += attempt(f"除息紀錄 {start}~{end}", fetch_ex_dividends, start, end, names)
        start = end + dt.timedelta(days=1)
    new_divs += attempt("除權除息預告", fetch_announced_dividends, names)

    taiex = upsert(read_csv(data_dir / "taiex.csv"), new_taiex, ["日期"])
    prices = upsert(read_csv(data_dir / "prices.csv"), new_prices, ["日期", "代號"])
    old_divs = [d for d in read_csv(data_dir / "dividends.csv") if d["代號"] in names]
    dividends = upsert(old_divs, new_divs, ["除息日", "代號"], keep=keep_dividend)
    prices = [p for p in prices if p["代號"] in names]

    write_csv(data_dir / "taiex.csv", TAIEX_FIELDS, taiex)
    write_csv(data_dir / "prices.csv", PRICE_FIELDS, prices)
    write_csv(data_dir / "dividends.csv", DIVIDEND_FIELDS, dividends)
    summary = build_summary(taiex, prices, dividends, tracked, today)
    summary["錯誤"] = errors
    summary["警告"] = warnings
    summary["請求數"] = calls[0]
    (data_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="更新每日台股指數、收盤價與配息資料")
    parser.add_argument("--months", type=int, default=1, help="抓取最近幾個月的每日收盤（預設 1，回補可設 12）")
    parser.add_argument("--date", help="以指定日期（YYYY-MM-DD，台灣時間）為今天，預設為現在")
    args = parser.parse_args(argv)
    if not 1 <= args.months <= 60:
        parser.error("--months 需介於 1 到 60")
    today = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(TW_TZ).date()
    # 月初幾天也一併更新上個月，避免漏掉月底最後交易日
    months = max(args.months, 2) if today.day <= 5 else args.months
    summary = update(today, months)
    taiex = summary["加權指數"]
    print(f"查詢日：{today}")
    print(f"加權指數：{taiex['日期']} 收盤 {taiex['收盤指數']}" if taiex else "加權指數：尚無資料")
    for item in summary["追蹤標的"]:
        print(f"{item['代號']} {item['名稱']}：{item['日期']} 收盤 {item['收盤價']}，"
              f"下次除息 {(item['下次除息'] or {}).get('除息日', '—')}")
    # 全部請求都失敗（例如被拒絕連線）時回傳錯誤碼，讓排程顯示失敗
    return 1 if len(summary["錯誤"]) >= summary["請求數"] else 0


if __name__ == "__main__":
    sys.exit(main())
