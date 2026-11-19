-- 客戶貼紙查詢：共用資料表、修改功能與編輯密碼。於 Supabase SQL Editor 執行。
-- 本檔可重複執行：第一次會建立資料表；已執行過舊版本也可直接再執行一次以加入修改功能。
-- 重新執行時資料不會被清除，但會以下方 pw 的值重設編輯密碼。
--
-- ★ 執行前請先把最下方 pw 的值改成你們的共用編輯密碼（至少 6 個字）。
--
-- 資料分兩種：
--   1. base_id 為空：網頁上新增的客戶。
--   2. base_id 有值（例如 x34）：修改過的 Excel 原有客戶，網頁以這筆取代 data.json 中同編號的資料。
begin;

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

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
-- 不直接授予修改或刪除，修改一律經由下方檢查密碼的函式。
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

-- 編輯密碼：只存 bcrypt 雜湊，放在 API 不公開的 private schema。
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table if not exists private.sticker_admin (
    id int primary key default 1 check (id = 1),
    password_hash text not null,
    updated_at timestamptz not null default now()
);
revoke all on table private.sticker_admin from public, anon, authenticated;

create or replace function private.sticker_password_ok(p_password text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare h text;
begin
    select password_hash into h from private.sticker_admin where id = 1;
    if h is null or p_password is null or extensions.crypt(p_password, h) <> h then
        perform pg_sleep(1);  -- 減緩猜密碼
        return false;
    end if;
    return true;
end $$;
revoke all on function private.sticker_password_ok(text) from public, anon, authenticated;

-- 檢查密碼（網頁進入編輯前使用）。
create or replace function public.sticker_check_password(p_password text)
returns boolean language sql security definer set search_path = '' as $$
    select private.sticker_password_ok(p_password);
$$;

-- 儲存修改：p_id 為資料庫中的資料列；p_base_id 為 Excel 原有客戶（第一次修改時新增覆寫列）。
create or replace function public.sticker_save(p_password text, p_id uuid, p_base_id text, p_data jsonb)
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_id uuid;
begin
    if not private.sticker_password_ok(p_password) then
        raise exception '編輯密碼錯誤' using errcode = '28P01';
    end if;
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
create or replace function public.sticker_delete(p_password text, p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if not private.sticker_password_ok(p_password) then
        raise exception '編輯密碼錯誤' using errcode = '28P01';
    end if;
    delete from public.sticker_customers where id = p_id;
end $$;

revoke all on function public.sticker_check_password(text) from public;
revoke all on function public.sticker_save(text, uuid, text, jsonb) from public;
revoke all on function public.sticker_delete(text, uuid) from public;
grant execute on function public.sticker_check_password(text) to anon;
grant execute on function public.sticker_save(text, uuid, text, jsonb) to anon;
grant execute on function public.sticker_delete(text, uuid) to anon;

-- ★ 設定／變更共用編輯密碼：把 pw 的值改成至少 6 個字的密碼再執行。
-- 之後若要換密碼，只要單獨再執行這一段 do $$ … $$; 即可。
do $$
declare pw text := '請在這裡輸入編輯密碼';
begin
    if pw = '請在這裡輸入編輯密碼' or char_length(pw) < 6 then
        raise exception '請先把 pw 改成至少 6 個字的編輯密碼，再執行本檔';
    end if;
    insert into private.sticker_admin (id, password_hash)
    values (1, extensions.crypt(pw, extensions.gen_salt('bf')))
    on conflict (id) do update set password_hash = excluded.password_hash, updated_at = now();
end $$;

commit;
