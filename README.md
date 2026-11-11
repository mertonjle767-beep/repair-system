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
