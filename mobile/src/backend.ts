// CoolMap 서버 (Supabase). coolmap/providers/backend.py 와 같은 서버를 쓴다.
//
// 여기에는 공개용 키(publishable)만 둔다. 원래 앱에 넣어 배포하는 키라 저장소에
// 올라가도 된다 — 서버 테이블은 RLS 로 읽기만 허용돼 있다.
// service_role / secret 키는 절대 여기에 넣지 않는다.

import { latLonToKmaGrid } from "./geo";
import type { Mode } from "./theme";

const SUPABASE_URL = "https://kgquzsmtjrlneveddaqv.supabase.co";
const SUPABASE_KEY = "sb_publishable_XZ6EgdFDKkjHA5xbeixGtA_sZVkbW1V";

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 20_000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${SUPABASE_URL}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: {
        apikey: SUPABASE_KEY,
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
    if (!res.ok) throw new Error(`서버 응답 ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/** sync-shelters 가 정규화한 레코드 (앱 캐시와 같은 형태) */
export type ShelterRecord = Record<string, string | number | undefined>;

export type NearRow = { no: string; rec: ShelterRecord; dist_m: number };

/** 현재 위치 주변 쉼터를 가까운 순으로. supabase/migrations/..._shelters_near.sql */
export function sheltersNear(lat: number, lon: number, mode: Mode, radiusM = 3000, limit = 80) {
  return request<NearRow[]>("/rest/v1/rpc/shelters_near", {
    method: "POST",
    body: JSON.stringify({ p_lat: lat, p_lon: lon, p_mode: mode, p_radius_m: radiusM, p_limit: limit }),
  });
}

export type WeatherResponse = {
  now: Record<string, string> | null;
  fcst: Record<string, number> | null;
};

/** 기상청 초단기실황·단기예보 (weather Edge Function 경유) */
export function weather(lat: number, lon: number) {
  const [nx, ny] = latLonToKmaGrid(lat, lon);
  return request<WeatherResponse>(`/functions/v1/weather?nx=${nx}&ny=${ny}`);
}
