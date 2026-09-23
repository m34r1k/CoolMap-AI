-- 기상청 단기예보 응답 캐시 (격자 nx, ny 단위).
--
-- Edge Function(weather)만 service_role 로 읽고 쓴다. 앱은 이 테이블에 직접 접근하지 않고
-- 함수를 통해서만 받는다 → anon 에는 아무 권한도 주지 않는다.

create table if not exists public.weather_cache (
    nx          int         not null,
    ny          int         not null,
    kind        text        not null check (kind in ('now', 'fcst')),   -- 실황 / 예보
    data        jsonb       not null,
    fetched_at  timestamptz not null default now(),
    primary key (nx, ny, kind)
);

-- 시간당 호출 한도 계산용
create index if not exists weather_cache_fetched_at on public.weather_cache (fetched_at);

alter table public.weather_cache enable row level security;
revoke all on public.weather_cache from anon, authenticated;
grant select, insert, update, delete on public.weather_cache to service_role;
