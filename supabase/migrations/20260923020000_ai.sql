-- Gemini 판단 결과 캐시 + 호출 기록.
--
-- Edge Function(ai)만 service_role 로 읽고 쓴다. 앱은 함수를 통해서만 받는다.
-- 캐시는 모든 사용자가 공유한다 — 같은 시설 유형·같은 상호는 한 번만 Gemini 에 묻는다.

create table if not exists public.ai_cache (
    task        text        not null check (task in ('nuisance', 'judge')),
    key         text        not null,
    data        jsonb       not null,
    created_at  timestamptz not null default now(),
    primary key (task, key)
);

-- Gemini 호출 1회 = 1행. 시간당 한도 계산에 쓴다.
create table if not exists public.ai_calls (
    id    bigint      generated always as identity primary key,
    at    timestamptz not null default now(),
    ip    text        not null default '',
    task  text        not null default ''
);
create index if not exists ai_calls_at on public.ai_calls (at);

alter table public.ai_cache enable row level security;
alter table public.ai_calls enable row level security;
revoke all on public.ai_cache, public.ai_calls from anon, authenticated;
grant select, insert, update, delete on public.ai_cache, public.ai_calls to service_role;

-- 호출 기록은 하루치만 있으면 된다. 매일 04:00 (KST) 에 지운다.
select cron.unschedule(jobname) from cron.job where jobname = 'prune-ai-calls';
select cron.schedule('prune-ai-calls', '0 19 * * *',
                     $$ delete from public.ai_calls where at < now() - interval '1 day' $$);
