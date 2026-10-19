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
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      throw new Error(body?.error || `서버 응답 ${res.status}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/** sync-shelters 가 정규화한 레코드 (앱 캐시와 같은 형태) */
export type ShelterRecord = Record<string, string | number | undefined>;

export type NearRow = { no: string; rec: ShelterRecord; dist_m: number };

/** 현재 위치 주변 쉼터를 가까운 순으로. supabase/migrations/..._shelters_near.sql */
export function sheltersNear(lat: number, lon: number, mode: Mode, radiusM: number, limit: number) {
  return request<NearRow[]>("/rest/v1/rpc/shelters_near", {
    method: "POST",
    body: JSON.stringify({ p_lat: lat, p_lon: lon, p_mode: mode, p_radius_m: radiusM, p_limit: limit }),
  });
}

/** 한 시간의 하늘 예보. at: "2026101815" (한국 시각 YYYYMMDDHH), sky: 1 맑음 · 3 구름많음 · 4 흐림, pty: 0 없음 · 1 비 · 2 비/눈 · 3 눈 · 4 소나기 */
export type SkyHour = { at: string; sky: number; pty: number; pop: number };

export type WeatherResponse = {
  now: Record<string, string> | null;
  fcst: Record<string, number> | null;
  sky?: SkyHour[] | null; // 지금부터 12시간 (예전 서버는 없음)
};

/** 기상청 초단기실황·단기예보 (weather Edge Function 경유) */
export function weather(lat: number, lon: number) {
  const [nx, ny] = latLonToKmaGrid(lat, lon);
  return request<WeatherResponse>(`/functions/v1/weather?nx=${nx}&ny=${ny}`);
}

// -- 재난문자 (supabase/functions/alerts) -------------------------------------

/** 행정안전부 재난문자 한 건. step: 위급재난 · 긴급재난 · 안전안내, kind: 호우 · 폭염 · 한파 · 기타 …, area: 받은 지역 */
export type DisasterAlert = { sn: number; at: string; step: string; kind: string; text: string; area: string };

/** 이 지역(예: '경기도 성남시 분당구')의 최근 24시간 재난문자, 최신순 */
export function disasterAlerts(region: string) {
  return request<{ alerts: DisasterAlert[] }>(`/functions/v1/alerts?region=${encodeURIComponent(region)}`);
}

// -- AI (supabase/functions/ai) ---------------------------------------------

/** 민폐도를 좌우하는 '시설 성격'. 값은 서버의 허용 목록과 같아야 한다. */
export type NuisanceProfile = {
  mode: string;
  category: string;
  official: string;
  purchase: string;
  capacity: string;
  always_open: string;
  quiet: number;
};

export type NuisanceResult = { score: number; stay_minutes: number; reason: string; tips: string[] };

export async function aiNuisance(profile: NuisanceProfile): Promise<NuisanceResult> {
  const d = await request<{ result: NuisanceResult }>(
    "/functions/v1/ai",
    { method: "POST", body: JSON.stringify({ task: "nuisance", profile }) },
    60_000,
  );
  return d.result;
}

export type Judgment = { usable: boolean; category: string; confidence: number; note: string };

/** 지도 상호가 쉼터로 쓸 만한지. 입력 순서대로 돌려주며, 판단하지 못한 항목은 null. */
export async function aiJudge(items: { name: string; kind: string }[]): Promise<(Judgment | null)[]> {
  const d = await request<{ results: (Judgment | null)[] }>(
    "/functions/v1/ai",
    { method: "POST", body: JSON.stringify({ task: "judge", items }) },
    90_000,
  );
  return d.results ?? [];
}

// -- 길 안내 (supabase/functions/route · T맵 보행자 경로) ----------------------------

export type WalkRoute = {
  distance_m: number;
  time_s: number;
  path: [number, number][]; // [경도, 위도]
  steps: { text: string; at: [number, number] | null }[];
};

/** 내 위치에서 쉼터까지 걷는 길. from · to 는 [위도, 경도]. */
export function walkRoute(from: [number, number], to: [number, number], toName: string): Promise<WalkRoute> {
  return request<WalkRoute>(
    "/functions/v1/route",
    { method: "POST", body: JSON.stringify({ from, to, to_name: toName }) },
    30_000,
  );
}

// -- 쉼터 제보 (supabase/functions/report) -----------------------------------------

export type ReportKind = "closed" | "gone" | "no_hvac" | "ok";
export type Report = { kind: ReportKind; at: string; count: number };

/**
 * 이 쉼터에 문제가 있다고(또는 '지금은 괜찮아요' 라고) 알린다. 제보 id 를 돌려준다 — 취소할 때 쓴다.
 * 같은 쉼터에 10분 안에 다시 알리면 서버가 거절한다. device 는 본인 확인용 기기 표식.
 */
export async function reportShelter(placeId: string, kind: ReportKind, device: string): Promise<number> {
  const d = await request<{ ok: boolean; id: number }>("/functions/v1/report", {
    method: "POST",
    body: JSON.stringify({ task: "add", place_id: placeId, kind, device }),
  });
  return d.id;
}

/** 내가 보낸 제보를 취소한다 (24시간 안, 같은 기기에서만) */
export async function cancelReport(id: number, device: string): Promise<void> {
  await request<{ ok: boolean }>("/functions/v1/report", {
    method: "POST",
    body: JSON.stringify({ task: "cancel", id, device }),
  });
}

/** 최근 24시간 제보 (쉼터별 가장 최근 제보와 건수) */
export async function recentReports(placeIds: string[]): Promise<Record<string, Report>> {
  if (!placeIds.length) return {};
  const d = await request<{ reports: Record<string, Report> }>("/functions/v1/report", {
    method: "POST",
    body: JSON.stringify({ task: "recent", place_ids: placeIds.slice(0, 300) }),
  });
  return d.reports ?? {};
}
