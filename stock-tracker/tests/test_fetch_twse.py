"""以虛構的 TWSE 回應格式測試解析、合併與摘要（不連網）。"""
import csv
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_twse as ft  # noqa: E402

FIXTURES = {
    "afterTrading/FMTQIK": {
        "stat": "OK",
        "fields": ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"],
        "data": [["115/11/12", "1", "1", "1", "21,000.50", "-12.30"],
                 ["115/11/13", "1", "1", "1", "21,100.00", "99.50"]],
    },
    "afterTrading/STOCK_DAY": {
        "stat": "OK",
        "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數"],
        "data": [["115/11/12", "1", "1", "1", "1", "1", "180.10", "X0.00", "1"],
                 ["115/11/13", "1", "1", "1", "1", "1", "181.25", "+1.15", "1"]],
    },
    "exRight/TWT49U": {
        "stat": "OK",
        "fields": ["資料日期", "股票代號", "股票名稱", "除權息前收盤價", "除權息參考價", "權值+息值", "權/息"],
        "data": [["115年07月16日", "0050", "元大台灣50", "182.00", "180.90", "1.10", "息"],
                 ["115年07月16日", "2330", "台積電", "1000", "995", "5.00", "息"]],
    },
    "exRight/TWT48U": {
        "stat": "OK",
        "fields": ["除權除息日期", "股票代號", "名稱", "除權息", "無償配股率", "現金股利"],
        "data": [["115年07月16日", "0050", "元大台灣50", "息", "", "1.1"],
                 ["115年12月17日", "0050", "元大台灣50", "息", "", "0.95"]],
    },
}


def fake_fetch(path, **params):
    return FIXTURES[path]


class ParseTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(ft.parse_date("115/11/13"), "2026-11-13")
        self.assertEqual(ft.parse_date("115年07月16日"), "2026-07-16")
        self.assertEqual(ft.parse_date("1151113"), "2026-11-13")
        self.assertEqual(ft.parse_date("20261113"), "2026-11-13")

    def test_numbers(self):
        self.assertEqual(ft.parse_number("21,000.50"), "21000.5")
        self.assertEqual(ft.parse_number("X0.00"), "0.0")
        self.assertEqual(ft.parse_number("+1.15"), "1.15")
        self.assertEqual(ft.parse_number("--"), "")
        self.assertEqual(ft.signed_change("<p style='color:green'>-</p>", "12.3"), "-12.3")

    def test_no_data_stat(self):
        self.assertEqual(list(ft.tables({"stat": "很抱歉，沒有符合條件的資料!"})), [])

    def test_multi_table_formats(self):
        payload = {"stat": "OK", "tables": [{"fields": ["a"], "data": [[1]]}], "fields1": ["b"], "data1": [[2]]}
        self.assertEqual(len(list(ft.tables(payload))), 2)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.watch = self.dir / "watchlist.json"
        self.watch.write_text(json.dumps({"tracked": [{"code": "0050", "name": "元大台灣50"}]}), encoding="utf-8")
        ft.PAUSE_SECONDS = 0

    def tearDown(self):
        self.tmp.cleanup()

    def run_update(self):
        return ft.update(dt.date(2026, 11, 16), 1, fetch=fake_fetch, data_dir=self.dir / "data", watchlist=self.watch)

    def test_update_writes_csv_and_summary(self):
        summary = self.run_update()
        self.assertEqual(summary["錯誤"], [])
        self.assertEqual(summary["加權指數"], {"日期": "2026-11-13", "收盤指數": "21100.0", "漲跌點數": "99.5"})
        item = summary["追蹤標的"][0]
        self.assertEqual((item["日期"], item["收盤價"]), ("2026-11-13", "181.25"))
        self.assertEqual(item["最近除息"]["除息日"], "2026-07-16")
        self.assertEqual(item["最近除息"]["狀態"], "已除息")  # 預告不覆蓋實際紀錄
        self.assertEqual(item["最近除息"]["除息參考價"], "180.9")
        self.assertEqual(item["下次除息"]["除息日"], "2026-12-17")
        self.assertEqual(item["近12月配息"], 1.1)
        self.assertEqual(item["殖利率"], round(1.1 / 181.25 * 100, 2))
        with (self.dir / "data" / "dividends.csv").open(encoding="utf-8-sig") as f:
            codes = {r["代號"] for r in csv.DictReader(f)}
        self.assertEqual(codes, {"0050"})  # 未追蹤的 2330 不寫入

    def test_update_is_idempotent(self):
        self.run_update()
        first = (self.dir / "data" / "prices.csv").read_text(encoding="utf-8-sig")
        self.run_update()
        self.assertEqual(first, (self.dir / "data" / "prices.csv").read_text(encoding="utf-8-sig"))

    def test_failures_are_reported(self):
        def broken(path, **params):
            raise RuntimeError("連線被拒")
        summary = ft.update(dt.date(2026, 11, 16), 1, fetch=broken, data_dir=self.dir / "data", watchlist=self.watch)
        self.assertEqual(len(summary["錯誤"]), summary["請求數"])
        self.assertIsNone(summary["加權指數"])


if __name__ == "__main__":
    unittest.main()
