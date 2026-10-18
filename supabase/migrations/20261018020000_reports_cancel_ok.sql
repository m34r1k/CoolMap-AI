-- 쉼터 제보 2: 내 제보 취소 · '지금은 괜찮아요'.
--
-- · device: 앱이 기기마다 만든 무작위 표식의 해시. 본인 제보만 취소할 수 있게 한다
--   (표식 원본은 저장하지 않는다. IP 는 이동·공유기 때문에 본인 확인에 쓸 수 없다)
-- · kind 'ok': 현장에서 문제가 풀린 걸 본 사람이 남긴다. 그보다 앞선 문제 제보는 가린다.

alter table public.shelter_reports add column if not exists device text not null default '';
create index if not exists shelter_reports_device on public.shelter_reports (device);

alter table public.shelter_reports drop constraint if exists shelter_reports_kind_check;
alter table public.shelter_reports
    add constraint shelter_reports_kind_check check (kind in ('closed', 'gone', 'no_hvac', 'ok'));
