-- 報修登記系統初始建表腳本：僅供人工審閱，尚未執行。
-- 適用於尚無此資料表的 Supabase 專案；重複執行會報錯，避免掩蓋結構差異。
-- 本次只建立 SQL 檔；未來人工套用時，以交易確保建表與權限設定一併完成。
begin;

-- 資料表與預設值：編號、建立時間及初始狀態由資料庫自動產生。
-- 所有欄位皆必填；時間使用含時區型別，便於跨時區顯示。
create table public.repair_requests (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    reporter_name text not null,
    location text not null,
    category text not null,
    description text not null,
    urgency text not null default '中',
    status text not null default '待處理',

    -- CHECK 第一層資料驗證：姓名 1–100 字、地點 1–200 字、說明 1–5000 字。
    -- 字數按原始字串計算；排除僅含空白的內容，避免以空白規避必填要求。
    constraint repair_requests_reporter_name_check check (
        char_length(reporter_name) between 1 and 100
        and reporter_name ~ '[^[:space:]]'
    ),
    constraint repair_requests_location_check check (
        char_length(location) between 1 and 200
        and location ~ '[^[:space:]]'
    ),
    constraint repair_requests_description_check check (
        char_length(description) between 1 and 5000
        and description ~ '[^[:space:]]'
    ),

    -- CHECK 固定選項：只接受指定的繁體中文值，亦同時限制選項文字長度。
    constraint repair_requests_category_check
        check (category in ('設備', '網路', '環境', '其他')),
    constraint repair_requests_urgency_check
        check (urgency in ('低', '中', '高')),
    constraint repair_requests_status_check
        check (status in ('待處理', '處理中', '已完成'))
);

-- GRANT 權限層：清除公用及前端角色可能繼承的資料表預設授權。
-- 僅對 anon 開放讀取及五個輸入欄位的新增權限，不授予修改或刪除。
-- 不開放寫入 id、created_at、status，防止訪客偽造系統欄位。
revoke all privileges on table public.repair_requests from public, anon, authenticated;
grant usage on schema public to anon;
grant select on table public.repair_requests to anon;
grant insert (reporter_name, location, category, description, urgency)
    on table public.repair_requests to anon;

-- RLS 資料列層：啟用後，讀取清單不限制資料列。
-- 此示範不需登入，「任何人」透過 Supabase 未登入角色 anon 存取。
alter table public.repair_requests enable row level security;

create policy repair_requests_anon_select
    on public.repair_requests
    for select
    to anon
    using (true);

-- RLS 新增規則：即使將來調整欄位授權，訪客仍只能新增待處理案件。
-- 不建立 UPDATE 或 DELETE 政策，配合 GRANT 拒絕訪客修改及刪除。
create policy repair_requests_anon_insert
    on public.repair_requests
    for insert
    to anon
    with check (status = '待處理');

-- 完成交易；本檔尚未套用至任何資料庫。
commit;
