-- 재난문자 캐시 — 행정안전부 긴급재난문자(재난안전데이터공유플랫폼)를 최근 24시간치 저장해 둔다.
--
-- Edge Function(alerts)만 service_role 로 읽고 쓴다. 전국 문자를 5분에 한 번만 받아
-- 한 줄(id = 1)에 담아 두고, 앱이 보낸 지역에 맞는 것만 골라 준다.

create table if not exists public.alert_cache (
    id          int         primary key check (id = 1),
    data        jsonb       not null default '[]'::jsonb,   -- [{sn, at, step, kind, regions, text}]
    fetched_at  timestamptz not null default now(),          -- 마지막으로 받으려 한 시각 (실패해도 갱신)
    note        text        not null default ''              -- 마지막 실패 이유
);

alter table public.alert_cache enable row level security;
revoke all on public.alert_cache from anon, authenticated;
grant select, insert, update on public.alert_cache to service_role;
