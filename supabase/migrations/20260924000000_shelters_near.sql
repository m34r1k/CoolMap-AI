-- 주변 쉼터만 돌려주는 RPC (모바일 앱용).
--
-- 데스크톱 앱은 전국 목록을 통째로 받아 캐시하지만, 폰에서 11만 건을 받기는 무겁다.
-- 모바일은 POST /rest/v1/rpc/shelters_near 로 현재 위치 주변만 받는다.
--
-- 좌표는 rec(jsonb) 안에 문자열로 들어 있으므로 숫자 컬럼으로 뽑아 인덱스를 건다.
-- 원본에 이상한 값('' 등)이 섞여도 동기화가 깨지지 않도록 변환 실패는 null 로 둔다.

create or replace function public.to_float_or_null(v text)
returns double precision
language plpgsql
immutable
as $$
begin
    return v::double precision;
exception when others then
    return null;
end;
$$;

alter table public.shelters
    add column if not exists lat double precision
        generated always as (public.to_float_or_null(rec->>'lat')) stored,
    add column if not exists lon double precision
        generated always as (public.to_float_or_null(rec->>'lon')) stored;

create index if not exists shelters_mode_lat_lon on public.shelters (mode, lat, lon);


create or replace function public.shelters_near(
    p_lat      double precision,
    p_lon      double precision,
    p_mode     text,
    p_radius_m double precision default 3000,
    p_limit    int default 80
)
returns table (no text, rec jsonb, dist_m double precision)
language sql
stable
security invoker          -- 테이블 RLS(읽기 전용)를 그대로 따른다
set search_path = ''
as $$
    with q as (
        select least(greatest(p_radius_m, 100), 20000)              as r,
               least(greatest(p_limit, 1), 200)                     as n
    ),
    box as (
        select q.r, q.n,
               q.r / 111000.0                                       as dlat,
               q.r / (111320.0 * cos(radians(p_lat)))               as dlon
          from q
    )
    select s.no, s.rec, d.m
      from public.shelters s
     cross join box
     cross join lateral (
            select 2 * 6371000 * asin(sqrt(
                       power(sin(radians(s.lat - p_lat) / 2), 2)
                     + cos(radians(p_lat)) * cos(radians(s.lat))
                     * power(sin(radians(s.lon - p_lon) / 2), 2))) as m
         ) d
     where s.mode = p_mode
       and s.lat between p_lat - box.dlat and p_lat + box.dlat
       and s.lon between p_lon - box.dlon and p_lon + box.dlon
       and d.m <= box.r
     order by d.m
     limit (select n from box);
$$;

revoke all on function public.shelters_near(double precision, double precision, text, double precision, int) from public;
grant execute on function public.shelters_near(double precision, double precision, text, double precision, int)
    to anon, authenticated;
