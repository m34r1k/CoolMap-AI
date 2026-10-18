// 도보 길 안내 — T맵 보행자 경로 API 프록시.
//
// 호출:  POST /functions/v1/route
//   { "from": [lat, lon], "to": [lat, lon], "to_name": "쉼터 이름" }
//     → { distance_m, time_s, path: [[lon, lat], ...], steps: [{ text, at: [lon, lat] }], cached }
//
// 카카오·네이버 길찾기 API 는 자동차 경로만 공개해서, 도보 경로는 T맵을 쓴다.
// 공개 키만 있으면 누구나 부를 수 있으므로:
//   · 한국 안 · 직선 10km 이내만 받는다 (쉼터까지 걸어가는 용도)
//   · 결과는 route_cache 에 저장해 모든 사용자가 공유한다 (출발지는 약 10m 단위로 묶는다)
//   · T맵 호출을 전체 시간당 GLOBAL_BUDGET, IP 당 IP_BUDGET 회로 제한한다
//
// 필요한 Secrets:  TMAP_APP_KEY  (SK open API · TMAP · 보행자 경로안내)

import { createClient } from "npm:@supabase/supabase-js@2";

const TMAP = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json";
const GLOBAL_BUDGET = 300; // 시간당 T맵 호출 (전체)
const IP_BUDGET = 30; // 시간당 T맵 호출 (IP 하나)
const MAX_STRAIGHT_M = 10_000;
const WALK_M_PER_MIN = 67; // 앱의 '걸어서 n분' 과 같은 속도

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type LatLon = [number, number];

function point(v: unknown, label: string): LatLon {
  const ok = Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number" && Number.isFinite(x));
  if (!ok) throw new HttpError(400, `${label} 는 [위도, 경도] 여야 합니다`);
  const [lat, lon] = v as LatLon;
  // 제주 ~ 독도까지 넉넉히
  if (lat < 32.5 || lat > 39.5 || lon < 124 || lon > 132.5) throw new HttpError(400, `${label} 가 한국 밖입니다`);
  return [lat, lon];
}

function haversine([lat1, lon1]: LatLon, [lat2, lon2]: LatLon): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const a = Math.sin(r(lat2 - lat1) / 2) ** 2 + Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(r(lon2 - lon1) / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(a));
}

async function checkBudget(ip: string) {
  const since = new Date(Date.now() - 3600_000).toISOString();
  const all = await db.from("route_calls").select("*", { count: "exact", head: true }).gt("at", since);
  if ((all.count ?? 0) >= GLOBAL_BUDGET) throw new HttpError(429, "길 안내 요청이 많아 잠시 쉬고 있어요. 조금 뒤에 다시 시도해 주세요");
  const mine = await db.from("route_calls").select("*", { count: "exact", head: true }).gt("at", since).eq("ip", ip);
  if ((mine.count ?? 0) >= IP_BUDGET) throw new HttpError(429, "길 안내 요청이 너무 많아요. 조금 뒤에 다시 시도해 주세요");
}

type Feature = {
  geometry?: { type?: string; coordinates?: unknown };
  properties?: Record<string, unknown>;
};

/** T맵 GeoJSON → 앱이 쓰는 간단한 형태. 필드가 빠져 있어도 선 길이로 거리·시간을 계산한다. */
function simplify(features: Feature[]) {
  const path: [number, number][] = [];
  const steps: { text: string; at: [number, number] | null }[] = [];
  let total = { distance: NaN, time: NaN };

  for (const f of features) {
    const g = f.geometry ?? {};
    const p = f.properties ?? {};
    if (Number.isFinite(Number(p.totalDistance))) total = { distance: Number(p.totalDistance), time: Number(p.totalTime) };
    let at: [number, number] | null = null;
    if (g.type === "LineString" && Array.isArray(g.coordinates)) {
      for (const c of g.coordinates as number[][]) {
        const pt: [number, number] = [Number(c[0]), Number(c[1])];
        const last = path[path.length - 1];
        if (!last || last[0] !== pt[0] || last[1] !== pt[1]) path.push(pt);
      }
    } else if (g.type === "Point" && Array.isArray(g.coordinates)) {
      const c = g.coordinates as number[];
      at = [Number(c[0]), Number(c[1])];
    }
    // 안내 문구는 회전 지점(Point)에서만 쓴다. 선(LineString)의 문구는 '○○m 이동' 이라 중복된다.
    const text = typeof p.description === "string" ? p.description.trim() : "";
    if (g.type === "Point" && text && steps[steps.length - 1]?.text !== text) steps.push({ text, at });
  }

  let length = 0;
  for (let i = 1; i < path.length; i++) {
    length += haversine([path[i - 1][1], path[i - 1][0]], [path[i][1], path[i][0]]);
  }
  const distance = Number.isFinite(total.distance) ? total.distance : Math.round(length);
  const time = Number.isFinite(total.time) ? total.time : Math.round((distance / WALK_M_PER_MIN) * 60);
  return { distance_m: distance, time_s: time, path, steps };
}

async function route(ip: string, body: Record<string, unknown>) {
  const from = point(body.from, "from");
  const to = point(body.to, "to");
  if (haversine(from, to) > MAX_STRAIGHT_M) throw new HttpError(400, "걸어가기에는 너무 멀어요 (10km 초과)");
  const toName = String(body.to_name ?? "도착지").slice(0, 60);

  // 출발지는 약 10m, 도착지는 약 1m 단위로 묶어 캐시를 함께 쓴다
  const key = `${from[0].toFixed(4)},${from[1].toFixed(4)}>${to[0].toFixed(5)},${to[1].toFixed(5)}`;
  const hit = await db.from("route_cache").select("data").eq("key", key).maybeSingle();
  if (hit.data) return { ...(hit.data.data as object), cached: true };

  await checkBudget(ip);
  const appKey = Deno.env.get("TMAP_APP_KEY");
  if (!appKey) throw new HttpError(500, "TMAP_APP_KEY 가 설정되지 않았습니다");
  await db.from("route_calls").insert({ ip });

  const res = await fetch(TMAP, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", appKey },
    body: JSON.stringify({
      startX: from[1],
      startY: from[0],
      endX: to[1],
      endY: to[0],
      startName: "현재 위치",
      endName: toName,
      reqCoordType: "WGS84GEO",
      resCoordType: "WGS84GEO",
    }),
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 200);
    throw new HttpError(502, `T맵 응답 ${res.status}: ${detail}`);
  }
  const raw = await res.json();
  const features = Array.isArray(raw?.features) ? (raw.features as Feature[]) : [];
  if (!features.length) throw new HttpError(502, "T맵이 경로를 주지 않았습니다");
  const data = simplify(features);
  if (data.path.length < 2) throw new HttpError(502, "경로를 찾지 못했습니다");
  await db.from("route_cache").upsert({ key, data });
  return { ...data, cached: false };
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "POST 만 받습니다" }, 405);
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim();
  try {
    const body = await req.json().catch(() => null);
    if (!body || typeof body !== "object") throw new HttpError(400, "본문이 JSON 이 아닙니다");
    return json(await route(ip, body as Record<string, unknown>));
  } catch (e) {
    if (e instanceof HttpError) return json({ error: e.message }, e.status);
    console.error(e);
    return json({ error: String(e) }, 500);
  }
});
