-- 물어보기(chat) 호출 기록 — 시간당 한도 계산용. Gemini 호출 1회 = 1행.
--
-- ai_calls 와 따로 둔다: 물어보기를 많이 써도 민폐도 · AI 추정 쉼터 판단 한도를 먹지 않게.
-- Edge Function(chat)만 service_role 로 읽고 쓴다.

create table if not exists public.chat_calls (
    id    bigint      generated always as identity primary key,
    at    timestamptz not null default now(),
    ip    text        not null default ''
);
create index if not exists chat_calls_at on public.chat_calls (at);
create index if not exists chat_calls_ip_at on public.chat_calls (ip, at);

alter table public.chat_calls enable row level security;
revoke all on public.chat_calls from anon, authenticated;
grant select, insert, delete on public.chat_calls to service_role;

-- 한도 계산에는 최근 1시간만 쓴다. 매일 04:30 (KST) 하루 지난 기록을 지운다.
select cron.unschedule(jobname) from cron.job where jobname = 'prune-chat';
select cron.schedule('prune-chat', '30 19 * * *',
                     $$ delete from public.chat_calls where at < now() - interval '1 day' $$);
