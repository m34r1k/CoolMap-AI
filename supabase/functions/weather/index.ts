// 기상청 단기예보 프록시 + 캐시.
//
// 호출:  GET /functions/v1/weather?nx=60&ny=127
// 응답:  { now: {T1H, REH, WSD, ...} | null, now_age: 초,
//          fcst: {"0": 24.0, ..., "23": 27.0} | null, fcst_age: 초 }
//
// 격자 단위로 weather_cache 에 저장해 두고, 실황은 30분·예보는 3시간 동안 재사용한다.
// 이 함수는 공개 키만 있으면 누구나 부를 수 있으므로, 기상청을 새로 부르는 횟수를
// 시간당 FETCH_BUDGET 회로 제한해 일일 한도를 지킨다. 한도를 넘으면 저장된 값만 준다.
//
// 필요한 Secrets:  KMA_SERVICE_KEY  공공데이터포털(data.go.kr) 인증키
// SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 는 플랫폼이 자동으로 넣어 준다.
//
// 기상청 호출 방식은 coolmap/providers/weather.py 와 같다.

import { createClient } from "npm:@supabase/supabase-js@2";

const BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0";
const NOW_TTL = 30 * 60;           // 실황 30분
const FCST_TTL = 3 * 60 * 60;      // 예보 3시간
const FETCH_BUDGET = 150;          // 시간당 기상청 신규 조회 (격자·종류 단위)

// 단기예보 발표 시각
const FCST_BASE_TIMES = [2, 5, 8, 11, 14, 17, 20, 23];

type Row = { kind: "now" | "fcst"; data: Record<string, unknown>; fetched_at: string };

const pad = (n: number) => String(n).padStart(2, "0");

// 기상청은 한국 시간 기준이다. Edge Function 은 UTC 로 돌므로 9시간을 더해 계산한다.
function kst(offsetMin = 0): Date {
  return new Date(Date.now() + 9 * 3600_000 - offsetMin * 60_000);
}
const ymd = (d: Date) => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;

function fcstBase(): [string, string] {
  // 가장 최근의 단기예보 발표 시각 (발표 후 15분 여유)
  const t = kst(15);
  const hours = FCST_BASE_TIMES.filter((h) => h <= t.getUTCHours());
  if (hours.length) return [ymd(t), `${pad(hours[hours.length - 1])}00`];
  return [ymd(kst(15 + 24 * 60)), "2300"];
}

async function kma(path: string, params: Record<string, string | number>) {
  let key = Deno.env.get("KMA_SERVICE_KEY") ?? "";
  if (key.includes("%")) key = decodeURIComponent(key);   // Encoding 키를 넣어도 되도록
  if (!key) throw new Error("KMA_SERVICE_KEY 가 설정되지 않았습니다");
  const q = new URLSearchParams({ serviceKey: key, dataType: "JSON" });
  for (const [k, v] of Object.entries(params)) q.set(k, String(v));
  const res = await fetch(`${BASE}/${path}?${q}`, {
    headers: { "User-Agent": "CoolMapAI/1.0" },
    signal: AbortSignal.timeout(15_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const d = await res.json();
  if (d?.response?.header?.resultCode !== "00") {
    throw new Error(`[${d?.response?.header?.resultCode}] ${d?.response?.header?.resultMsg}`);
  }
  const item = d.response.body?.items?.item ?? [];
  return (Array.isArray(item) ? item : [item]) as Record<string, string>[];
}

async function fetchNow(nx: number, ny: number) {
  // 실황 — 매시 40분에 갱신되므로 45분 전 기준이 안전
  const t = kst(45);
  const items = await kma("getUltraSrtNcst", {
    base_date: ymd(t), base_time: `${pad(t.getUTCHours())}00`,
    nx, ny, pageNo: 1, numOfRows: 100,
  });
  const values: Record<string, string> = {};
  for (const i of items) values[i.category] = i.obsrValue;
  return values;
}

async function fetchFcst(nx: number, ny: number) {
  const [bd, bt] = fcstBase();
  const items = await kma("getVilageFcst", {
    base_date: bd, base_time: bt, nx, ny, pageNo: 1, numOfRows: 300,
  });
  const temps: Record<string, number> = {};
  for (const i of items) {
    if (i.category !== "TMP") continue;
    const v = Number(i.fcstValue);
    if (Number.isFinite(v)) temps[String(Number(i.fcstTime.slice(0, 2)))] = v;
  }
  return temps;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  const u = new URL(req.url);
  const nx = Number(u.searchParams.get("nx"));
  const ny = Number(u.searchParams.get("ny"));
  // 기상청 격자 범위 (한반도 전체)
  if (!Number.isInteger(nx) || !Number.isInteger(ny) || nx < 1 || nx > 149 || ny < 1 || ny > 253) {
    return json({ error: "nx, ny 가 올바르지 않습니다" }, 400);
  }

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: rows, error } = await db
    .from("weather_cache").select("kind,data,fetched_at").eq("nx", nx).eq("ny", ny);
  if (error) return json({ error: error.message }, 500);

  const cached: Partial<Record<Row["kind"], Row>> = {};
  for (const r of (rows ?? []) as Row[]) cached[r.kind] = r;
  const age = (r?: Row) => (r ? (Date.now() - Date.parse(r.fetched_at)) / 1000 : Infinity);

  const todo: Row["kind"][] = [];
  if (age(cached.now) > NOW_TTL) todo.push("now");
  if (age(cached.fcst) > FCST_TTL) todo.push("fcst");

  let note = "";
  if (todo.length) {
    const since = new Date(Date.now() - 3600_000).toISOString();
    const { count } = await db
      .from("weather_cache").select("*", { count: "exact", head: true }).gt("fetched_at", since);
    if ((count ?? 0) + todo.length > FETCH_BUDGET) {
      note = "hourly budget exceeded";
      todo.length = 0;
    }
  }

  for (const kind of todo) {
    try {
      const data = kind === "now" ? await fetchNow(nx, ny) : await fetchFcst(nx, ny);
      if (!Object.keys(data).length) continue;
      const row = { nx, ny, kind, data, fetched_at: new Date().toISOString() };
      const { error } = await db.from("weather_cache").upsert(row);
      if (error) console.error(`weather_cache 기록 실패: ${error.message}`);
      cached[kind] = row;
    } catch (e) {
      // 기상청 실패 → 저장된 값이 있으면 그걸 준다
      note = e instanceof Error ? e.message : String(e);
      console.error(`kma ${kind} ${nx},${ny}: ${note}`);
    }
  }

  return json({
    now: cached.now?.data ?? null,
    now_age: Number.isFinite(age(cached.now)) ? Math.round(age(cached.now)) : null,
    fcst: cached.fcst?.data ?? null,
    fcst_age: Number.isFinite(age(cached.fcst)) ? Math.round(age(cached.fcst)) : null,
    ...(note ? { note } : {}),
  });
});
