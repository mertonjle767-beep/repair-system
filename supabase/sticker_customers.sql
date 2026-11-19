-- 客戶貼紙查詢：共用「新增客戶」資料表。僅供人工審閱後於 Supabase SQL Editor 執行一次。
-- Excel 轉入的 135 筆原始資料仍放在 sticker-lookup/data.json，本表只存網頁上新增的客戶。
-- 重複執行會因資料表已存在而報錯，避免掩蓋結構差異。
begin;

create table public.sticker_customers (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    name text not null,                    -- 客戶名稱
    sticker text not null default '',      -- 貼紙公司名
    paste text not null default '',        -- 張貼位置
    roll text not null default '',         -- 滾字位置
    qty text not null default '',          -- 數量
    mold text not null default '',         -- 字模
    mold_l text not null default '',       -- 廠商字模（大 64.5×30mm）
    mold_m text not null default '',       -- 年字模（中 46.5×30mm）
    mold_s text not null default '',       -- 月字模（小 35×30mm）
    note text not null default '',         -- 備註
    images jsonb not null default '[]'::jsonb, -- 貼紙樣式圖片（網頁縮小後的 data URL 陣列）

    -- 客戶名稱 1–40 字且不可只有空白。
    constraint sticker_customers_name_check check (
        char_length(name) between 1 and 40 and name ~ '[^[:space:]]'
    ),
    constraint sticker_customers_text_len_check check (
        char_length(sticker) <= 60 and char_length(paste) <= 80 and char_length(roll) <= 80
        and char_length(qty) <= 20 and char_length(mold) <= 40 and char_length(mold_l) <= 40
        and char_length(note) <= 300
    ),
    constraint sticker_customers_mold_ms_check check (
        mold_m in ('', 'V', 'X') and mold_s in ('', 'V', 'X')
    ),
    -- 圖片：最多 3 張、合計約 1.5MB 以內，且只接受 JPEG／PNG／WebP 的 base64 data URL，
    -- 避免任意網址或腳本內容被當成圖片顯示。
    constraint sticker_customers_images_check check (
        jsonb_typeof(images) = 'array'
        and jsonb_array_length(images) <= 3
        and octet_length(images::text) <= 1500000
        and not jsonb_path_exists(images, '$[*] ? (@.type() != "string")')
        and not jsonb_path_exists(images, '$[*] ? (!(@ like_regex "^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$"))')
    )
);

create index sticker_customers_created_at_idx on public.sticker_customers (created_at desc);

-- GRANT：未登入訪客（anon）只能讀取，以及新增可填寫的欄位；不能寫入 id、created_at，
-- 也不授予修改或刪除。修正或刪除請由管理者在 Supabase 後台處理。
revoke all privileges on table public.sticker_customers from public, anon, authenticated;
grant usage on schema public to anon;
grant select on table public.sticker_customers to anon;
grant insert (name, sticker, paste, roll, qty, mold, mold_l, mold_m, mold_s, note, images)
    on table public.sticker_customers to anon;

-- RLS：啟用後只建立讀取與新增政策，沒有 UPDATE／DELETE 政策。
alter table public.sticker_customers enable row level security;

create policy sticker_customers_anon_select
    on public.sticker_customers for select to anon using (true);

create policy sticker_customers_anon_insert
    on public.sticker_customers for insert to anon with check (true);

commit;
