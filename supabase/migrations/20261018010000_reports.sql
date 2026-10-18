-- 쉼터 제보 — 이용자가 현장에서 알려 주는 '문이 닫혀 있어요 · 없어졌어요 · 냉난방이 안 돼요'.
--
-- Edge Function(report)만 service_role 로 읽고 쓴다. 앱은 함수를 통해서만 제보하고 읽는다.
-- place_id 는 앱의 장소 id 와 같다: 공식 쉼터 H/C + 관리번호, AI 추정 쉼터 G + OSM 종류·번호.

create table if not exists public.shelter_reports (
    id        bigint      generated always as identity primary key,
    place_id  text        not null check (place_id ~ '^([HC][0-9]{1,12}|G[nwr][0-9]{1,15})$'),
    kind      text        not null check (kind in ('closed', 'gone', 'no_hvac')),
    at        timestamptz not null default now(),
    ip        text        not null default ''
);
create index if not exists shelter_reports_place_at on public.shelter_reports (place_id, at desc);
create index if not exists shelter_reports_ip_at on public.shelter_reports (ip, at);

alter table public.shelter_reports enable row level security;
revoke all on public.shelter_reports from anon, authenticated;
grant select, insert, delete on public.shelter_reports to service_role;

-- 오래된 제보는 의미가 없으니 30일 뒤 지운다. 매일 04:20 (KST).
select cron.unschedule(jobname) from cron.job where jobname = 'prune-reports';
select cron.schedule('prune-reports', '20 19 * * *',
                     $$ delete from public.shelter_reports where at < now() - interval '30 days' $$);
