// 행정안전부 무더위·한파쉼터 전량 동기화.
//
// safetydata.go.kr 에서 전체 페이지를 받아 공통 필드명으로 정규화한 뒤
// public.shelters 에 넣는다. 앱은 키 없이 그 테이블을 읽는다.
//
// 호출:  POST /functions/v1/sync-shelters?mode=cooling|heating
//        헤더 x-sync-secret 이 SYNC_SECRET 과 같아야 한다 (pg_cron 이 붙여 준다).
//
// 필요한 Secrets:
//   SHELTER_SERVICE_KEY       무더위쉼터 (DSSP-IF-10942) 인증키
//   COLD_SHELTER_SERVICE_KEY  한파쉼터   (DSSP-IF-10804) 인증키
//   SYNC_SECRET               아무 긴 난수 문자열
// SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 는 플랫폼이 자동으로 넣어 준다.

import { createClient } from "npm:@supabase/supabase-js@2";

declare const EdgeRuntime: { waitUntil(p: Promise<unknown>): void };

const BASE = "https://www.safetydata.go.kr/V2/api";
const PAGE_SIZE = 1000;
const CONCURRENCY = 4;
const UPSERT_CHUNK = 1000;

type Dataset = { serviceId: string; keyEnv: string; fields: Record<string, string> };

// coolmap/providers/shelters.py 의 HEAT_SHELTERS / COLD_SHELTERS 와 반드시 같아야 한다.
// 앱은 여기서 만든 레코드를 그대로 캐시에 넣는다.
const DATASETS: Record<string, Dataset> = {
  cooling: {
    serviceId: "DSSP-IF-10942",
    keyEnv: "SHELTER_SERVICE_KEY",
    fields: {
      no: "RSTR_FCLTY_NO", name: "RSTR_NM",
      lat: "LA", lon: "LO",
      road_addr: "RN_DTL_ADRES", addr: "DTL_ADRES",
      type: "FCLTY_TY", capacity: "USE_PSBL_NMPR", area: "AR",
      ac: "COLR_HOLD_ARCNDTN", fan: "COLR_HOLD_ELEFN",
      wkday_from: "WKDAY_OPER_BEGIN_TIME", wkday_to: "WKDAY_OPER_END_TIME",
      weekend_open: "CHCK_MATTER_WKEND_HDAY_OPN_AT",
      night_open: "CHCK_MATTER_NIGHT_OPN_AT",
      stay_ok: "CHCK_MATTER_STAYNG_PSBL_AT",
    },
  },
  heating: {
    serviceId: "DSSP-IF-10804",
    keyEnv: "COLD_SHELTER_SERVICE_KEY",
    fields: {
      no: "REARE_FCLT_NO", name: "REARE_NM",
      lat: "LAT", lon: "LOT",
      road_addr: "RONA_DADDR", addr: "DADDR",
      type: "FCLT_TYPE", capacity: "UTZTN_PSBLTY_TNOP",
      wkday_from: "WKDY_OPER_BGNG_HR", wkday_to: "WKDY_OPER_END_HR",
      sat_from: "STDY_OPER_BGNG_HR", sat_to: "STDY_OPER_END_HR",
      sun_from: "SNDY_OPER_BGNG_HR", sun_to: "SNDY_OPER_END_HR",
      holiday_from: "LHLDY_OPER_BGNG_HR", holiday_to: "LHLDY_OPER_END_HR",
      remark: "RMRK",
    },
  },
};

// 재시도해도 소용없는 응답 코드. 특히 22(일일 한도 초과)에서 재시도하면 남은 한도만 갉아먹는다.
const FATAL_CODES = new Set(["20", "22", "30", "31"]);

class ApiRefused extends Error {}

type Rec = Record<string, unknown>;

function normalize(raw: Rec, ds: Dataset): Rec {
  const out: Rec = {};
  for (const [canon, src] of Object.entries(ds.fields)) {
    const v = raw[src];
    if (v !== null && v !== undefined) out[canon] = v;
  }
  return out;
}

async function fetchPage(ds: Dataset, key: string, page: number): Promise<{ body: Rec[]; total: number }> {
  const q = new URLSearchParams({
    serviceKey: key,
    returnType: "json",
    pageNo: String(page),
    numOfRows: String(PAGE_SIZE),
  });
  const res = await fetch(`${BASE}/${ds.serviceId}?${q}`, {
    headers: { "User-Agent": "CoolMapAI/1.0" },
    signal: AbortSignal.timeout(45_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const d = await res.json();
  const code = d?.header?.resultCode;
  if (code !== "00") {
    const msg = d?.header?.errorMsg || d?.header?.resultMsg || "unknown error";
    if (FATAL_CODES.has(code)) throw new ApiRefused(`[${code}] ${msg}`);
    throw new Error(`[${code}] ${msg}`);
  }
  return { body: d.body ?? [], total: Number(d.totalCount ?? 0) };
}

async function fetchWithRetry(ds: Dataset, key: string, page: number) {
  let last: unknown;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await fetchPage(ds, key, page);
    } catch (e) {
      if (e instanceof ApiRefused) throw e;
      last = e;
      await new Promise((r) => setTimeout(r, 800 * (attempt + 1)));
    }
  }
  throw last;
}

async function sync(mode: string): Promise<Rec> {
  const ds = DATASETS[mode];
  let key = Deno.env.get(ds.keyEnv) ?? "";
  if (key.includes("%")) key = decodeURIComponent(key);   // Encoding 키를 넣어도 되도록
  if (!key) throw new Error(`${ds.keyEnv} 가 설정되지 않았습니다`);

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const startedAt = new Date().toISOString();

  const first = await fetchWithRetry(ds, key, 1);
  const total = first.total;
  const pages = Math.ceil(total / PAGE_SIZE);
  const bodies: Rec[][] = [first.body];
  const missing: number[] = [];
  let refused = "";

  // 페이지를 CONCURRENCY 개씩 병렬로 받는다
  const todo = Array.from({ length: Math.max(0, pages - 1) }, (_, i) => i + 2);
  let cursor = 0;
  async function worker() {
    while (cursor < todo.length && !refused) {
      const page = todo[cursor++];
      try {
        bodies.push((await fetchWithRetry(ds, key, page)).body);
      } catch (e) {
        missing.push(page);
        if (e instanceof ApiRefused) refused = e.message;
      }
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  if (refused) missing.push(...todo.slice(cursor));

  // 같은 시설 번호가 두 번 오면 upsert 가 실패하므로 여기서 한 번 거른다
  const rows = new Map<string, Rec>();
  for (const body of bodies) {
    for (const raw of body) {
      const rec = normalize(raw, ds);
      const no = rec.no != null ? String(rec.no) : `${rec.lat},${rec.lon},${rec.name}`;
      rows.set(no, { mode, no, rec, synced_at: startedAt });
    }
  }

  const all = [...rows.values()];
  for (let i = 0; i < all.length; i += UPSERT_CHUNK) {
    const { error } = await db.from("shelters").upsert(all.slice(i, i + UPSERT_CHUNK), { onConflict: "mode,no" });
    if (error) throw new Error(`upsert: ${error.message}`);
  }

  // 전부 받았을 때만 사라진 시설을 지운다. 일부만 받았는데 지우면 멀쩡한 쉼터가 빠진다.
  if (missing.length === 0 && all.length > 0) {
    const { error } = await db.from("shelters").delete().eq("mode", mode).lt("synced_at", startedAt);
    if (error) throw new Error(`delete: ${error.message}`);
  }

  const status = {
    mode,
    finished_at: new Date().toISOString(),
    total,
    received: all.length,
    missing: missing.sort((a, b) => a - b),
    error: refused || (missing.length ? `${missing.length}개 페이지 실패` : ""),
  };
  const { error } = await db.from("shelter_sync").upsert(status);
  if (error) throw new Error(`shelter_sync 기록 실패: ${error.message}`);
  return status;
}

async function run(mode: string) {
  try {
    console.log(JSON.stringify(await sync(mode)));
  } catch (e) {
    const error = e instanceof Error ? e.message : String(e);
    console.error(`sync ${mode} failed: ${error}`);
    const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const res = await db.from("shelter_sync").upsert({ mode, finished_at: new Date().toISOString(), error });
    if (res.error) console.error(`shelter_sync 기록 실패: ${res.error.message}`);
  }
}

Deno.serve((req) => {
  const secret = Deno.env.get("SYNC_SECRET");
  if (!secret || req.headers.get("x-sync-secret") !== secret) {
    return new Response("forbidden", { status: 403 });
  }
  const mode = new URL(req.url).searchParams.get("mode") ?? "";
  if (!(mode in DATASETS)) {
    return new Response("mode must be cooling or heating", { status: 400 });
  }
  // 호출한 쪽(pg_net)은 몇 초 만에 끊으므로, 응답은 바로 주고 작업은 뒤에서 계속한다
  EdgeRuntime.waitUntil(run(mode));
  return new Response(JSON.stringify({ started: mode }), {
    status: 202,
    headers: { "Content-Type": "application/json" },
  });
});
