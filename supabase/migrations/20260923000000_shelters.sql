-- 무더위·한파쉼터 원본을 서버에서 대신 받아 두는 테이블.
--
-- 앱은 공개용 키(anon / publishable)로 이 테이블을 '읽기만' 한다.
-- 쓰기는 Edge Function(sync-shelters)이 service_role 로만 한다.

create table if not exists public.shelters (
    mode       text        not null check (mode in ('cooling', 'heating')),
    no         text        not null,          -- 원본 시설 번호
    rec        jsonb       not null,          -- 공통 필드명으로 정규화된 레코드 (앱 캐시와 같은 형태)
    synced_at  timestamptz not null default now(),
    primary key (mode, no)
);

-- 대시보드의 'Automatically expose new tables' / 'automatic RLS' 설정과 상관없이
-- 같은 결과가 나오도록 권한을 여기서 직접 정한다: 앱은 읽기만, 쓰기는 service_role 만.
-- (자동 노출을 끄면 service_role 도 권한을 못 받으므로 반드시 명시한다)
alter table public.shelters enable row level security;
revoke all on public.shelters from anon, authenticated;
grant select on public.shelters to anon, authenticated;
grant select, insert, update, delete on public.shelters to service_role;

drop policy if exists "shelters are public" on public.shelters;
create policy "shelters are public"
    on public.shelters for select
    to anon, authenticated
    using (true);


-- 동기화 결과 기록 (대시보드에서 상태 확인용)
create table if not exists public.shelter_sync (
    mode         text        primary key,
    finished_at  timestamptz not null default now(),
    total        int         not null default 0,   -- API 가 알려준 전체 건수
    received     int         not null default 0,   -- 실제로 저장한 건수
    missing      int[]       not null default '{}',-- 받지 못한 페이지
    error        text        not null default ''
);

alter table public.shelter_sync enable row level security;
revoke all on public.shelter_sync from anon, authenticated;
grant select on public.shelter_sync to anon, authenticated;
grant select, insert, update, delete on public.shelter_sync to service_role;

drop policy if exists "sync status is public" on public.shelter_sync;
create policy "sync status is public"
    on public.shelter_sync for select
    to anon, authenticated
    using (true);


-- 매주 월요일 03:00 (KST) 에 동기화한다.
-- 무더위/한파를 따로 호출해 각자 Edge Function 실행 시간 한도를 온전히 쓰게 한다.
--
-- URL 과 호출 비밀값은 Vault 에서 읽는다. 아래 두 값을 SQL Editor 에서 한 번 등록해야 한다
-- (저장소에 남기지 않는다):
--   select vault.create_secret('https://<project-ref>.supabase.co', 'project_url');
--   select vault.create_secret('<SYNC_SECRET 과 같은 값>', 'sync_secret');
create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function public.trigger_shelter_sync(target text)
returns bigint
language sql
security definer
set search_path = ''
as $$
    select net.http_post(
        url := (select decrypted_secret from vault.decrypted_secrets where name = 'project_url')
               || '/functions/v1/sync-shelters?mode=' || target,
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'x-sync-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'sync_secret')
        ),
        body := '{}'::jsonb
    );
$$;

-- 외부에서 호출하지 못하게 막는다 (cron 은 postgres 권한으로 돈다)
revoke all on function public.trigger_shelter_sync(text) from public, anon, authenticated;

select cron.unschedule(jobname) from cron.job
 where jobname in ('sync-shelters-cooling', 'sync-shelters-heating');

select cron.schedule('sync-shelters-cooling', '0 18 * * 0',
                     $$ select public.trigger_shelter_sync('cooling') $$);
select cron.schedule('sync-shelters-heating', '30 18 * * 0',
                     $$ select public.trigger_shelter_sync('heating') $$);
