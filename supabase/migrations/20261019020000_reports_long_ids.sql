-- 쉼터 제보 3: 관리번호가 13~20자리인 공식 쉼터도 제보할 수 있게 한다.
--
-- 처음에는 H/C 뒤 숫자를 12자리까지만 받아서, 관리번호가 긴 쉼터(전체의 약 17%,
-- 예: H41135657132556)는 '문제 알리기' 가 'place_id 형식이 올바르지 않습니다' 로 막혔다.
-- 지금 쉼터 데이터에서 가장 긴 관리번호는 20자리 이하다.

alter table public.shelter_reports drop constraint if exists shelter_reports_place_id_check;
alter table public.shelter_reports
    add constraint shelter_reports_place_id_check
    check (place_id ~ '^([HC][0-9]{1,20}|G[nwr][0-9]{1,15})$');
