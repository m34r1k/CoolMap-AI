-- 도보 길 안내(T맵 보행자 경로) 캐시 + 호출 기록.
--
-- Edge Function(route)만 service_role 로 읽고 쓴다. 앱은 함수를 통해서만 받는다.
-- 같은 출발지(약 10m 단위)에서 같은 쉼터로 가는 경로는 한 번만 T맵에 묻는다.

create table if not exists public.route_cache (
    key         text        primary key,
    data        jsonb       not null,
    created_at  timestamptz not null default now()
);
create index if not exists route_cache_created_at on public.route_cache (created_at);

-- T맵 호출 1회 = 1행. 시간당 한도 계산에 쓴다.
create table if not exists public.route_calls (
    id    bigint      generated always as identity primary key,
    at    timestamptz not null default now(),
    ip    text        not null default ''
);
create index if not exists route_calls_at on public.route_calls (at);

alter table public.route_cache enable row level security;
alter table public.route_calls enable row level security;
revoke all on public.route_cache, public.route_calls from anon, authenticated;
grant select, insert, update, delete on public.route_cache, public.route_calls to service_role;

-- 호출 기록은 하루, 경로 캐시는 30일만 둔다 (길이 바뀔 수 있으므로). 매일 04:10 (KST).
select cron.unschedule(jobname) from cron.job where jobname = 'prune-route';
select cron.schedule('prune-route', '10 19 * * *',
                     $$ delete from public.route_calls where at < now() - interval '1 day';
                        delete from public.route_cache where created_at < now() - interval '30 days' $$);
