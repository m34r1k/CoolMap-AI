// 재난문자 — 행정안전부 긴급재난문자(재난안전데이터공유플랫폼 DSSP-IF-00247) 프록시 + 캐시.
//
// 호출:  GET /functions/v1/alerts?region=경기도 성남시 분당구
// 응답:  { alerts: [{sn, at, step, kind, text, area}], age: 초 }   ← 이 지역의 최근 24시간, 최신순 10건
//
// region 은 앱이 가장 가까운 공식 쉼터 주소에서 뽑은 '시도 시군구 (구)'.
// 문자의 수신 지역이 시도 전체('서울특별시')면 그 시도 모두에, 동 단위('서울특별시 강동구 암사동')면
// 그 시군구에 보여 준다.
//
// 전국 문자를 REFRESH_S 에 한 번만 받아 alert_cache 한 줄에 둔다. 실패해도 받은 시각을
// 갱신해 두므로, 저쪽이 고장 나도 이쪽에서 계속 두드리지 않는다 (그동안은 저장된 문자를 준다).
//
// 필요한 Secrets:  DISASTER_MSG_KEY  재난안전데이터공유플랫폼(safetydata.go.kr) 서비스 키
// SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 는 플랫폼이 자동으로 넣어 준다.

import { createClient } from "npm:@supabase/supabase-js@2";

const API = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247";
const REFRESH_S = 5 * 60;
const KEEP_H = 24;
const LIMIT = 10;

type Alert = { sn: number; at: string; step: string; kind: string; regions: string[]; text: string };

const pad = (n: number) => String(n).padStart(2, "0");
// 한국 시각 기준 날짜. Edge Function 은 UTC 로 돈다.
const kstDay = (ms: number) => {
  const d = new Date(ms + 9 * 3600_000);
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
};

/** "2026/10/19 00:31:11" (한국 시각) → ISO */
function kstIso(s: string): string | null {
  const m = /^(\d{4})\/(\d{2})\/(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(s.trim());
  if (!m) return null;
  return new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}+09:00`).toISOString();
}

async function fetchAlerts(): Promise<Alert[]> {
  const key = Deno.env.get("DISASTER_MSG_KEY") ?? "";
  if (!key) throw new Error("DISASTER_MSG_KEY 가 설정되지 않았습니다");
  const since = Date.now() - KEEP_H * 3600_000;
  const out: Alert[] = [];
  // crtDt 날짜 이후에 만들어진 문자. 어제부터 받으면 24시간이 다 들어온다. 하루 전국 100~300건.
  for (let page = 1; page <= 5; page++) {
    const q = new URLSearchParams({
      serviceKey: key, returnType: "json", pageNo: String(page), numOfRows: "1000", crtDt: kstDay(since),
    });
    const res = await fetch(`${API}?${q}`, { signal: AbortSignal.timeout(20_000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    if (d?.header?.resultCode !== "00") throw new Error(`[${d?.header?.resultCode}] ${d?.header?.errorMsg ?? d?.header?.resultMsg}`);
    const body = (Array.isArray(d.body) ? d.body : []) as Record<string, unknown>[];
    for (const r of body) {
      const at = kstIso(String(r.CRT_DT ?? ""));
      if (!at || Date.parse(at) < since) continue;
      out.push({
        sn: Number(r.SN),
        at,
        step: String(r.EMRG_STEP_NM ?? "").trim(),
        kind: String(r.DST_SE_NM ?? "").trim(),
        regions: String(r.RCPTN_RGN_NM ?? "").split(",").map((x) => x.trim().replace(/\s+/g, " ")).filter(Boolean),
        text: String(r.MSG_CN ?? "").replace(/\r\n?/g, "\n").trim(),
      });
    }
    if (body.length < 1000) break;
  }
  return out.sort((a, b) => b.at.localeCompare(a.at));
}

// 시도 이름이 바뀌었거나(강원도 → 강원특별자치도) 합쳐진 곳은 같은 이름으로 본다.
const SIDO: Record<string, string> = {
  강원도: "강원", 강원특별자치도: "강원",
  전라북도: "전북", 전북특별자치도: "전북",
  제주도: "제주", 제주특별자치도: "제주",
  전라남도: "전남광주", 광주광역시: "전남광주", 전남광주통합특별시: "전남광주",
};
const tokens = (s: string) => {
  const t = s.trim().split(/\s+/).filter(Boolean);
  if (t.length) t[0] = SIDO[t[0]] ?? t[0];
  return t;
};

/** 수신 지역과 내 지역이 겹치는지 — 짧은 쪽이 긴 쪽의 앞부분이면 겹친다 */
function overlaps(area: string[], mine: string[]): boolean {
  if (!area.length || !mine.length) return false;
  for (let i = 0; i < Math.min(area.length, mine.length); i++) if (area[i] !== mine[i]) return false;
  return true;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  const region = (new URL(req.url).searchParams.get("region") ?? "").trim().replace(/\s+/g, " ");
  if (!/^[가-힣]{2,12}( [가-힣]{1,12}){0,2}$/.test(region)) {
    return json({ error: "region 이 올바르지 않습니다 (예: 서울특별시 강남구)" }, 400);
  }

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: row, error } = await db.from("alert_cache").select("data,fetched_at,note").eq("id", 1).maybeSingle();
  if (error) return json({ error: error.message }, 500);

  let list = (row?.data ?? []) as Alert[];
  let fetchedAt = row ? Date.parse(row.fetched_at) : 0;
  let note = row?.note ?? "";
  if (Date.now() - fetchedAt > REFRESH_S * 1000) {
    try {
      list = await fetchAlerts();
      note = "";
    } catch (e) {
      note = e instanceof Error ? e.message : String(e);
      console.error(`alerts: ${note}`);
    }
    fetchedAt = Date.now();
    const { error } = await db.from("alert_cache")
      .upsert({ id: 1, data: list, fetched_at: new Date(fetchedAt).toISOString(), note });
    if (error) console.error(`alert_cache 기록 실패: ${error.message}`);
  }

  const mine = tokens(region);
  const since = Date.now() - KEEP_H * 3600_000;
  const alerts = list
    .filter((a) => Date.parse(a.at) >= since)
    .map((a) => ({ a, area: a.regions.find((r) => overlaps(tokens(r), mine)) }))
    .filter((x) => x.area)
    .slice(0, LIMIT)
    .map(({ a, area }) => ({ sn: a.sn, at: a.at, step: a.step, kind: a.kind, text: a.text, area }));

  return json({ alerts, age: Math.round((Date.now() - fetchedAt) / 1000), ...(note ? { note } : {}) });
});
