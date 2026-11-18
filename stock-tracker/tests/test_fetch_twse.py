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
    "afterTrading/MI_INDEX": {
        "stat": "OK", "date": "20261116",
        "tables": [
            {"title": "價格指數(臺灣證券交易所)",
             "fields": ["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"],
             "data": [["寶島股價指數", "50,000.00", "<p style='color:red'>+</p>", "1.00", "0.01", ""],
                      ["發行量加權股價指數", "21,050.00", "<p style='color:green'>-</p>", "50.00", "-0.24", ""]]},
        ],
    },
    "afterTrading/STOCK_DAY_ALL": {
        "stat": "OK", "date": "20261116",
        "fields": ["證券代號", "證券名稱", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數"],
        "data": [["0050", "元大台灣50", "1", "1", "1", "1", "1", "181.25", "1.15", "1"],
                 ["2330", "台積電", "1", "1", "1", "1", "1", "1,000.00", "-15.00", "1"],
                 ["9998", "停牌示範", "0", "0", "--", "--", "--", "--", "0.00", "0"]],
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
        self.assertEqual(summary["查詢日"], "2026-11-16")
        # 查詢當天的指數來自 MI_INDEX，跌點帶負號
        self.assertEqual(summary["加權指數"], {"日期": "2026-11-16", "收盤指數": "21050.0", "漲跌點數": "-50.0"})
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

    def test_taiex_day_ignores_other_dates(self):
        holiday = dict(FIXTURES["afterTrading/MI_INDEX"], date="20261113")
        self.assertEqual(ft.fetch_taiex_day(dt.date(2026, 11, 15), fetch=lambda *a, **k: holiday), [])
        self.assertEqual(ft.fetch_taiex_day(dt.date(2026, 11, 15),
                                            fetch=lambda *a, **k: {"stat": "很抱歉，沒有符合條件的資料!"}), [])

    def test_past_query_date_hides_later_data(self):
        summary = ft.update(dt.date(2026, 11, 12), 1, fetch=fake_fetch, data_dir=self.dir / "data",
                            watchlist=self.watch)
        self.assertEqual(summary["加權指數"]["日期"], "2026-11-12")
        self.assertEqual(summary["追蹤標的"][0]["日期"], "2026-11-12")

    def test_name_from_title_and_missing_code(self):
        self.watch.write_text(json.dumps({"tracked": [{"code": "0050", "name": ""}, {"code": "9999X", "name": ""}]}),
                              encoding="utf-8")
        titled = dict(FIXTURES["afterTrading/STOCK_DAY"], title="115年11月 0050 元大台灣50         各日成交資訊")

        def fetch(path, **params):
            if path == "afterTrading/STOCK_DAY":
                return titled if params["stockNo"] == "0050" else {"stat": "很抱歉，沒有符合條件的資料!"}
            return fake_fetch(path, **params)
        summary = ft.update(dt.date(2026, 11, 16), 1, fetch=fetch, data_dir=self.dir / "data", watchlist=self.watch)
        self.assertEqual(summary["追蹤標的"][0]["名稱"], "元大台灣50")
        self.assertEqual(summary["配息紀錄"][0]["名稱"], "元大台灣50")
        self.assertEqual(summary["錯誤"], [])
        self.assertEqual(len(summary["警告"]), 1)
        self.assertIn("9999X", summary["警告"][0])

    def test_market_snapshot_covers_untracked_codes(self):
        self.run_update()
        market = json.loads((self.dir / "data" / "market.json").read_text(encoding="utf-8"))
        cols = market["欄位"]
        tsmc = dict(zip(cols, market["標的"]["2330"]))
        self.assertEqual((tsmc["名稱"], tsmc["收盤價"], tsmc["漲跌"]), ("台積電", "1000.0", "-15.0"))
        self.assertEqual((tsmc["最近除息日"], tsmc["最近配息"]), ("2026-07-16", "5.0"))  # 未追蹤也有配息
        self.assertEqual(tsmc["殖利率"], 0.5)
        self.assertNotIn("9998", market["標的"])  # 無收盤價的不列入
        self.assertEqual(market["收盤日"], "2026-11-16")

    def test_market_snapshot_kept_on_holiday(self):
        self.run_update()

        def holiday(path, **params):
            if path == "afterTrading/STOCK_DAY_ALL":
                return {"stat": "很抱歉，沒有符合條件的資料!"}
            return fake_fetch(path, **params)
        ft.update(dt.date(2026, 11, 17), 1, fetch=holiday, data_dir=self.dir / "data", watchlist=self.watch)
        market = json.loads((self.dir / "data" / "market.json").read_text(encoding="utf-8"))
        self.assertEqual((market["查詢日"], market["收盤日"]), ("2026-11-17", "2026-11-16"))
        self.assertIn("2330", market["標的"])

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
