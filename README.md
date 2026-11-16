# 報修登記系統
供同事登記設備、網路或環境等問題，並查閱報修紀錄。
雲端任務測試
[報修欄位表（Excel）](文件/報修欄位表.xlsx)

## 網頁啟動與設定

根目錄的 `index.html` 為首頁，搭配 `style.css`、`app.js`、`config.js`，不需建置或安裝前端套件。使用 CDN 載入固定 v2 版本的 supabase-js，因此需要網路。

`config.js` 僅包含專案網址與可公開的 publishable key，請勿放入 secret 或 service_role 金鑰。上線前，需由專案管理者確認 Supabase 已套用 `supabase/schema.sql` 的資料表、GRANT、RLS 與 CHECK；本次前端開發不會自動執行 SQL。未建表或權限不符時，頁面會顯示錯誤。

本機可在儲存庫根目錄執行 `python3 -m http.server 8000`，以瀏覽器開啟 `http://localhost:8000`。GitHub Pages 請選擇由 `main` 分支的 `/ (root)` 發佈，預期網址為 https://mertonjle767-beep.github.io/repair-system/ 。

## 驗證方式

以虛構姓名及地點測試：填寫所有欄位後送出，確認成功訊息、表單清空與清單更新；清單最多 20 筆且新的在上方。新增只送五個輸入欄位，不送狀態、編號與時間。測試空白內容、離線與讀寫錯誤時的訊息及內容保留，並確認手機寬度沒有橫向捲動。清單採純文字呈現輸入內容，不提供修改或刪除操作。資料庫權限是否確實拒絕修改及刪除，仍須在已套用 SQL 的測試專案另外驗證。

## 清單緊急程度篩選

清單上方新增「全部／高／中／低」按鈕，預設為「全部」，選中的按鈕會以深綠底白字標示，並提供 `aria-pressed` 狀態。篩選只顯示網頁已讀取的最近 20 筆中的對應案件，不會額外查詢資料庫，也不代表所有歷史案件；沒有符合項目時會顯示提示。重新整理或新增成功後仍保留目前選擇的篩選，高緊急程度標籤改為紅底色系搭配紅字。

本次僅調整網頁與說明文件，沒有修改資料庫、欄位、SQL、權限或 `supabase/` 目錄。

手機驗證：開啟此分支的本機預覽，往下捲至「最近報修」，確認預設選中「全部」。依序點選「高／中／低」，確認只顯示對應緊急程度、選中按鈕明顯且「高」標籤呈紅色；再點「全部」恢復原清單。若某程度沒有案件，應顯示無符合項目的提示。篩選不會觸發網路請求；可在瀏覽器開發工具的 Network 面板確認。PR 尚未合併時，main 的 GitHub Pages 不會顯示這次變更。

[報修系統操作說明（Word）](文件/報修系統操作說明.docx)

[報修登記系統提案（PowerPoint）](文件/報修登記系統提案.pptx)

## PWA 安裝與離線使用

透過 HTTPS（例如 GitHub Pages）或 localhost 開啟網頁，首次連線載入完成後，Service Worker 會快取介面與本機 Supabase SDK。支援安裝提示的瀏覽器會出現「安裝報修系統」按鈕，也可使用瀏覽器選單安裝；iPhone／iPad 使用 Safari 分享選單的「加入主畫面」。不保證所有瀏覽器都提供安裝提示。

離線僅能開啟介面，無法新增報修或讀取最新清單；沒有離線佇列、背景同步或自動重送。輸入僅保留在目前頁面，關閉或重新載入會遺失。已載入清單只留在目前頁面的記憶體，Service Worker 不快取案件或資料庫 API。重新連線後請先重新整理清單，再手動送出，避免重複登記。

更新程式或快取資產時須同步遞增 `sw.js` 的 `CACHE` 版本；新版會等待舊版視窗全部關閉後啟用，避免中斷填表。設定與公開 publishable key 屬介面快取，金鑰變更也須更新版本。勿在前端放 secret 或 service_role。SDK v2.99.1 已收錄於 `vendor/`（附 MIT 授權），頁面不再依賴 CDN 載入 SDK。

驗證方式：在 localhost／HTTPS 首次開啟，確認 manifest 與 Service Worker 註冊成功；離線重新開啟首頁應可見表單與離線提示，按送出不應有 API 寫入。恢復連線後確認可手動重新整理與送出。以 `/repair-system/` 子路徑測試安裝範圍，並確認快取只有介面資產，沒有資料庫回應。實際新增與 RLS 權限仍需在設定完成的 Supabase 測試專案驗證。

## 每日台股追蹤（附加功能）

`stock-tracker/` 為與報修系統無關的獨立小工具，每個交易日追蹤加權指數收盤，以及 00878、00919、0056、0050、00713、2330、00929、00406A 的收盤價、除息日與每股配息。追蹤清單在 `stock-tracker/watchlist.json` 修改。

- 資料來源：臺灣證券交易所公開資料（FMTQIK 加權指數、STOCK_DAY 收盤價、TWT49U 已除息紀錄、TWT48U 除權除息預告）。交易所資料只有除息日，配息發放日請以各投信公告為準。加權指數本身不配息。
- 排程：`.github/workflows/stock-tracker.yml` 於週一至週五台灣時間 16:17 執行，結果提交至 `stock-tracker/data/`（`taiex.csv`、`prices.csv`、`dividends.csv`、`summary.json`；CSV 含 BOM，可直接用 Excel 開啟）。排程只在預設分支執行；首次可在 Actions 頁面手動執行「每日台股追蹤」並把月數填 12 回補一年。
- 檢視：GitHub Pages 發佈後開啟 `/repair-system/stock-tracker/`；本機可在儲存庫根目錄執行 `python3 -m http.server 8000` 後開啟 `http://localhost:8000/stock-tracker/`。
- 手動更新：`python3 stock-tracker/fetch_twse.py --months 1`（只用 Python 標準函式庫）；加 `--date YYYY-MM-DD` 可查詢指定日期。
- 收盤價以查詢日為準：加權指數另以 MI_INDEX 抓取查詢當天收盤。若查詢日休市或尚未收盤，頁面顯示前一個交易日並在日期旁標 `*`。Actions 手動執行時也可填「查詢日」。
- 測試：`python3 -m unittest discover -s stock-tracker/tests`（使用虛構回應，不需連網）。

## 東京散策地圖

`tokyo-map/index.html` 是獨立的東京旅遊互動地圖，與報修系統無關，不使用 Supabase，也不在 Service Worker 快取範圍內。GitHub Pages 發佈後網址為 https://mertonjle767-beep.github.io/repair-system/tokyo-map/ ，本機預覽則開啟 `http://localhost:8000/tokyo-map/`。

- 地圖：收錄 JR 山手線、中央線快速、中央・總武線、東京 Metro 銀座／丸之內／日比谷／半藏門線、都營淺草線與百合海鷗號，可縮放、拖曳；點車站會顯示站號與附近景點。
- 景點：22 個景點（含「哆啦A夢」分類：台場的哆啦A夢未來百貨公司，以及位於川崎、地圖範圍外的藤子・F・不二雄博物館），可依分類篩選或搜尋，點選後顯示介紹、最近車站或交通方式、週邊推薦與小提示。
- 路線查詢：輸入出發與抵達站，以最短估算時間規劃（含每次轉乘約 5 分鐘），並在地圖上標示路線。時間為依距離估算的參考值。

頁面採哆啦A夢配色：藍色頁首、紅色項圈分隔線與黃色鈴鐺，景點標記為紅色、選取時變成黃色；各鐵路線仍使用官方代表色。頁面圖示為哆啦A夢藍底、掛著紅色項圈與金色鈴鐺的行李箱（`tokyo-map/icon.svg`，iPhone 加入主畫面使用 `icon-180.png`）。

驗證方式：開啟頁面，確認地圖與景點清單出現；在「路線查詢」輸入「新宿 → 淺草」，應顯示中央線快速轉銀座線的路線並在地圖標示；點選任一景點應跳至介紹並放大地圖。手機寬度下不應有橫向捲動。只需要網路載入 Google Fonts，離線時會改用系統字型。
