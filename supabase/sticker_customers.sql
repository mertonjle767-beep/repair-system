-- 客戶貼紙查詢：共用資料表與修改功能。於 Supabase SQL Editor 執行。
-- 本檔可重複執行：第一次會建立資料表；已執行過舊版本（含編輯密碼版本）也可直接再執行一次升級，資料不會被清除。
--
-- 示範版不需密碼：任何能開啟網頁的人都可以新增、修改、刪除或還原資料。
-- 修改一律經由下方函式，只能改可填寫的欄位；資料格式仍由 CHECK 把關。
--
-- 資料分兩種：
--   1. base_id 為空：網頁上新增的客戶。
--   2. base_id 有值（例如 x34）：修改過的 Excel 原有客戶，網頁以這筆取代 data.json 中同編號的資料。
begin;

create table if not exists public.sticker_customers (
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
    images jsonb not null default '[]'::jsonb  -- 貼紙樣式圖片
);
alter table public.sticker_customers add column if not exists base_id text;      -- 對應 Excel 資料編號
alter table public.sticker_customers add column if not exists updated_at timestamptz;
create unique index if not exists sticker_customers_base_id_key on public.sticker_customers (base_id);
create index if not exists sticker_customers_created_at_idx on public.sticker_customers (created_at desc);

-- CHECK：先移除再重建，讓重新執行時規則保持最新。
alter table public.sticker_customers
    drop constraint if exists sticker_customers_name_check,
    drop constraint if exists sticker_customers_text_len_check,
    drop constraint if exists sticker_customers_mold_ms_check,
    drop constraint if exists sticker_customers_images_check,
    drop constraint if exists sticker_customers_base_id_check;
alter table public.sticker_customers
    -- 客戶名稱 1–40 字且不可只有空白。
    add constraint sticker_customers_name_check check (
        char_length(name) between 1 and 40 and name ~ '[^[:space:]]'
    ),
    add constraint sticker_customers_text_len_check check (
        char_length(sticker) <= 60 and char_length(paste) <= 80 and char_length(roll) <= 80
        and char_length(qty) <= 20 and char_length(mold) <= 40 and char_length(mold_l) <= 40
        and char_length(note) <= 300
    ),
    add constraint sticker_customers_mold_ms_check check (
        mold_m in ('', 'V', 'X') and mold_s in ('', 'V', 'X')
    ),
    -- 圖片：最多 5 張、合計約 2.5MB；只接受 JPEG／PNG／WebP 的 base64 data URL，
    -- 或網站內 Excel 原有圖片的路徑（img/015.jpg），避免任意網址或腳本被當成圖片。
    add constraint sticker_customers_images_check check (
        jsonb_typeof(images) = 'array'
        and jsonb_array_length(images) <= 5
        and octet_length(images::text) <= 2500000
        and not jsonb_path_exists(images, '$[*] ? (@.type() != "string")')
        and not jsonb_path_exists(images, '$[*] ? (!(@ like_regex "^(data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+|img/[0-9]{3}\\.jpg)$"))')
    ),
    add constraint sticker_customers_base_id_check check (base_id is null or base_id ~ '^x[0-9]{1,4}$');

-- GRANT：未登入訪客（anon）可讀取，並可新增客戶（不含 base_id、id、時間欄位）；
-- 不直接授予修改或刪除，修改一律經由下方函式，避免改動 id、base_id 或建立時間。
revoke all privileges on table public.sticker_customers from public, anon, authenticated;
grant usage on schema public to anon;
grant select on table public.sticker_customers to anon;
grant insert (name, sticker, paste, roll, qty, mold, mold_l, mold_m, mold_s, note, images)
    on table public.sticker_customers to anon;

-- RLS：只有讀取與新增政策，沒有 UPDATE／DELETE 政策。
alter table public.sticker_customers enable row level security;
drop policy if exists sticker_customers_anon_select on public.sticker_customers;
drop policy if exists sticker_customers_anon_insert on public.sticker_customers;
create policy sticker_customers_anon_select
    on public.sticker_customers for select to anon using (true);
create policy sticker_customers_anon_insert
    on public.sticker_customers for insert to anon with check (base_id is null);

-- 移除舊版的編輯密碼函式與資料（若曾執行過密碼版本）。
drop function if exists public.sticker_check_password(text);
drop function if exists public.sticker_save(text, uuid, text, jsonb);
drop function if exists public.sticker_delete(text, uuid);
drop function if exists private.sticker_password_ok(text);
drop table if exists private.sticker_admin;

-- 儲存修改：p_id 為資料庫中的資料列；p_base_id 為 Excel 原有客戶（第一次修改時新增覆寫列）。
create or replace function public.sticker_save(p_id uuid, p_base_id text, p_data jsonb)
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_id uuid;
begin
    if p_id is not null then
        update public.sticker_customers set
            name = coalesce(p_data->>'name', ''), sticker = coalesce(p_data->>'sticker', ''),
            paste = coalesce(p_data->>'paste', ''), roll = coalesce(p_data->>'roll', ''),
            qty = coalesce(p_data->>'qty', ''), mold = coalesce(p_data->>'mold', ''),
            mold_l = coalesce(p_data->>'mold_l', ''), mold_m = coalesce(p_data->>'mold_m', ''),
            mold_s = coalesce(p_data->>'mold_s', ''), note = coalesce(p_data->>'note', ''),
            images = coalesce(p_data->'images', '[]'::jsonb), updated_at = now()
        where id = p_id
        returning id into v_id;
        if v_id is null then raise exception '找不到要修改的資料，可能已被刪除'; end if;
    elsif p_base_id is not null then
        insert into public.sticker_customers
            (base_id, name, sticker, paste, roll, qty, mold, mold_l, mold_m, mold_s, note, images, updated_at)
        values (p_base_id, coalesce(p_data->>'name', ''), coalesce(p_data->>'sticker', ''),
            coalesce(p_data->>'paste', ''), coalesce(p_data->>'roll', ''), coalesce(p_data->>'qty', ''),
            coalesce(p_data->>'mold', ''), coalesce(p_data->>'mold_l', ''), coalesce(p_data->>'mold_m', ''),
            coalesce(p_data->>'mold_s', ''), coalesce(p_data->>'note', ''),
            coalesce(p_data->'images', '[]'::jsonb), now())
        on conflict (base_id) do update set
            name = excluded.name, sticker = excluded.sticker, paste = excluded.paste, roll = excluded.roll,
            qty = excluded.qty, mold = excluded.mold, mold_l = excluded.mold_l, mold_m = excluded.mold_m,
            mold_s = excluded.mold_s, note = excluded.note, images = excluded.images, updated_at = now()
        returning id into v_id;
    else
        raise exception '缺少要修改的資料編號';
    end if;
    return v_id;
end $$;

-- 刪除：網頁新增的客戶會被刪除；修改過的 Excel 客戶則還原成 Excel 原始資料。
create or replace function public.sticker_delete(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
    delete from public.sticker_customers where id = p_id;
end $$;

revoke all on function public.sticker_save(uuid, text, jsonb) from public;
revoke all on function public.sticker_delete(uuid) from public;
grant execute on function public.sticker_save(uuid, text, jsonb) to anon;
grant execute on function public.sticker_delete(uuid) to anon;

commit;
