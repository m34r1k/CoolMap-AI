// Gemini 프록시 — 민폐도(nuisance) · AI 추정 쉼터 판단(judge).
//
// 호출:  POST /functions/v1/ai
//   { "task": "nuisance", "profile": {mode, category, official, purchase, capacity, always_open, quiet} }
//     → { result: {score, stay_minutes, reason, tips}, model }
//   { "task": "judge", "items": [{name, kind}, ...] }       (최대 25개)
//     → { results: [{i, usable, category, confidence, note} | null, ...], model }
//
// 이 함수는 공개 키만 있으면 누구나 부를 수 있다. 아무 질문이나 받아 주면 남의 돈으로
// Gemini 를 쓰는 통로가 되므로:
//   · 프롬프트(루브릭)는 서버가 정하고, 앱은 정해진 형태의 값만 보낸다 (허용 목록 검사)
//   · 결과는 ai_cache 에 저장해 모든 사용자가 공유한다
//   · Gemini 호출을 전체 시간당 GLOBAL_BUDGET, IP 당 IP_BUDGET 회로 제한한다
//
// 필요한 Secrets:  GEMINI_API_KEY
//
// 아래 루브릭·스키마·허용 목록은 coolmap/providers/gemini.py, candidates.py 에서
// 그대로 옮긴 것이다. 그쪽을 고치면 여기도 같이 고친다.

import { createClient } from "npm:@supabase/supabase-js@2";

const API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent";
const MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"];
const GLOBAL_BUDGET = 120;   // 시간당 Gemini 호출 (전체)
const IP_BUDGET = 40;        // 시간당 Gemini 호출 (IP 하나)
const BATCH = 25;

const NUISANCE_RUBRIC = "당신은 '민폐도' 평가자입니다.\n민폐도 = 볼일 없이 더위만 피하러 들어가 오래 머무를 때 느끼는 눈치·부담 (0~100 정수).\n낮을수록 마음 편히 오래 있을 수 있습니다.\n\n**가장 중요한 원칙: 공식 지정 무더위쉼터라 하더라도, 시설의 '본래 목적'과\n방문 목적(더위 피하기)이 어긋나면 실제로는 눈치가 보입니다.**\n공식 지정 여부만 보고 무조건 낮게 주지 마세요. 그 공간에 낯선 사람이 볼일 없이\n한 시간 앉아 있을 때 직원과 다른 이용객이 어떻게 느낄지를 기준으로 판단하세요.\n\n유형별 현실적인 기준:\n  · 도서관, 주민센터·행정복지센터, 복지관, 공공 라운지\n      → 누구나 머무르라고 만든 공간. 10~25.\n  · 야외 그늘 쉼터·정자\n      → 애초에 쉬는 곳. 0~15.\n  · 버스정류장 (그늘막 정류장 · 냉방되는 스마트쉼터 포함)\n      → 길가의 공용 시설이라 누가 서 있든 아무도 신경 쓰지 않는다. 0~10.\n        다만 좁고 버스를 기다리는 사람이 오가므로 장시간 점유는 피해야 한다.\n        직원도 안내데스크도 없으니 그런 조언은 하지 말 것.\n  · 대형마트\n      → 매장 안 고객 휴게공간은 비교적 자유롭지만 상업시설이다. 40~60.\n  · 경로당·마을회관\n      → 공식 쉼터여도 사실상 지역 어르신들의 사랑방. 외부인이나 젊은 층이\n        불쑥 들어가 오래 있기는 어색하다. 40~60.\n  · 은행·새마을금고·농협 등 금융기관\n      → 창구 업무를 보러 오는 곳. 볼일 없이 로비 소파에서 바람만 쐬고 있으면\n        직원 시선이 분명히 느껴진다. 짧게 더위를 식히는 정도만 무난하다. 55~75.\n  · 편의점·상점·카페\n      → 구매가 사실상 전제. 65~85.\n  · 병원 로비\n      → 환자 동선이라 배려가 필요하다. 50~70.\n\n난방(한파 대피) 모드에서는 폭염 때와 사회적 맥락이 조금 다릅니다.\n한파는 생명과 직결된다는 인식이 있어 공공시설의 수용 태도가 더 관대하고,\n특히 경로당·주민센터는 한파 시 적극적으로 개방합니다. 같은 시설이라도\n난방 모드에서는 냉방 모드보다 5~15점 낮게 잡으세요.\n다만 은행·상점처럼 본래 목적이 다른 곳은 여전히 부담이 큽니다.\n\nstay_minutes 는 '이 정도면 무난하다'고 볼 수 있는 권장 체류 시간(분)입니다.\n민폐도가 높으면 짧게(10~30분), 낮으면 길게(2~5시간) 잡으세요.\nreason 은 한 문장, tips 는 실용적인 조언 2~3개. 모두 한국어 존댓말.";
const NUISANCE_SCHEMA = {"type": "object", "properties": {"score": {"type": "integer"}, "stay_minutes": {"type": "integer"}, "reason": {"type": "string"}, "tips": {"type": "array", "items": {"type": "string"}}}, "required": ["score", "stay_minutes", "reason", "tips"]};
const JUDGE_RUBRIC = "당신은 지도에 찍힌 상호를 보고 '더위·추위를 피할 수 있는 곳'을\n골라내는 심사자입니다.\n\n상호명과 OSM 시설 종류 목록을 받습니다. 각 항목이\n'공식 지정 쉼터는 아니지만, 일반인이 잠시 더위나 추위를 피해 머무를 수 있는\n냉난방되는 실내 공간인가'를 판단하세요.\n\n**핵심 기준: 아무것도 사지 않고, 볼일도 없이 들어가 앉아 있어도\n괜찮은 곳인가.** 여기에 해당해야 usable=true 입니다.\n\nusable = true 로 볼 만한 곳\n  · 대형마트·하나로마트·백화점·복합쇼핑몰·지하상가·대형서점\n      → 매장이 넓어 둘러보는 사람과 구분되지 않고, 냉난방이 확실하다\n  · 도서관·주민센터·행정복지센터·복지관·문화센터·박물관·미술관\n      → 누구나 들어가도 되는 공공 공간\n  · 지하철역·기차역 대합실\n      → 냉난방되고 통행이 자유롭다\n  · 공공 체육센터·구민회관\n\nusable = false 로 두어야 할 곳\n  · 구매나 용무가 사실상 전제인 곳 — 편의점, 카페, 식당, 주점, 은행,\n    병원, 미용실, 학원. 잠깐은 되지만 '쉼터'라고 안내할 수는 없다\n  · 실내가 아닌 것 — 야외 주차장, 공터, 도로, 교량, 야외 운동장\n  · 외부인이 들어갈 수 없는 곳 — 사무실 전용 빌딩, 공장, 창고, 물류센터,\n    학교, 유치원, 군부대, 관사, 연구소, 회원제 시설\n  · 주거시설 — 아파트, 빌라, 오피스텔, 기숙사\n  · 종교시설 중 상시 개방이 아닌 곳\n  · 상호만으로 무엇인지 알 수 없는 곳 (예: '○○빌딩', '○○프라자',\n    '○○타워' 처럼 업종을 알 수 없는 이름)\n\n**추측으로 usable=true 를 남발하지 마세요.**\n이 결과는 지도에 '여기 들어가면 시원해요' 로 표시됩니다.\n사용자가 찾아갔는데 못 들어가면 그냥 안 띄운 것보다 나쁩니다.\n확신이 서지 않으면 usable=false 로 두세요.\n\nconfidence 는 판단의 확신도(0~100)입니다.\n전국구 브랜드처럼 무엇인지 분명하면 높게, 지역 상호라 짐작만 되면 낮게 주세요.\n\ncategory 는 주어진 목록에서 가장 가까운 것 하나를 고르세요.\nnote 는 왜 그렇게 판단했는지 한국어 한 문장(40자 이내)으로 적으세요.";
const JUDGE_SCHEMA = {"type": "object", "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {"i": {"type": "integer"}, "usable": {"type": "boolean"}, "category": {"type": "string", "enum": ["bank", "bookstore", "busstop", "cafe", "center", "cinema", "dept", "gov", "hospital", "library", "mall", "market", "mart", "museum", "park", "senior", "store", "subway", "underground"]}, "confidence": {"type": "integer"}, "note": {"type": "string"}}, "required": ["i", "usable", "category", "confidence", "note"]}}}, "required": ["results"]};

// 입력 허용 목록
const CATEGORY_LABELS = new Set<string>(["기타", "경로당·마을회관", "대형마트", "도서관", "미술관", "백화점", "버스정류장", "병원 로비", "복지관", "복합쇼핑몰", "서점", "야외 쉼터", "영화관", "은행", "전통시장", "주민센터", "지하상가", "지하철역", "카페", "편의점"]);
const POI_KINDS = new Set<string>(["amenity=arts_centre", "amenity=cinema", "amenity=college", "amenity=community_centre", "amenity=library", "amenity=marketplace", "amenity=post_office", "amenity=public_bath", "amenity=social_facility", "amenity=theatre", "amenity=townhall", "amenity=university", "building=civic", "building=commercial", "building=public", "building=retail", "leisure=sports_centre", "office=government", "public_transport=station", "railway=station", "shop=books", "shop=department_store", "shop=doityourself", "shop=mall", "shop=supermarket", "shop=variety_store", "shop=wholesale", "tourism=aquarium", "tourism=gallery", "tourism=museum"]);
const MODES = new Set(["냉방(폭염 대피)", "난방(한파 대피)"]);
const YES_NO = new Set(["예", "아니오"]);
const CAPACITY = new Set(["소형(20명 이하)", "중형(20~60명)", "대형(60~200명)", "초대형(200명 초과)"]);

type Json = Record<string, unknown>;

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function sha1(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 20);
}

// -- 한도 ------------------------------------------------------------------

async function checkBudget(ip: string) {
  const since = new Date(Date.now() - 3600_000).toISOString();
  const all = await db.from("ai_calls").select("*", { count: "exact", head: true }).gt("at", since);
  if ((all.count ?? 0) >= GLOBAL_BUDGET) throw new HttpError(429, "서버 전체 AI 호출 한도를 넘었습니다");
  const mine = await db.from("ai_calls").select("*", { count: "exact", head: true })
    .gt("at", since).eq("ip", ip);
  if ((mine.count ?? 0) >= IP_BUDGET) throw new HttpError(429, "AI 호출 한도를 넘었습니다. 잠시 후 다시 시도하세요");
}

// -- Gemini ----------------------------------------------------------------

async function gemini(ip: string, task: string, rubric: string, prompt: string, schema: Json) {
  await checkBudget(ip);
  const key = Deno.env.get("GEMINI_API_KEY");
  if (!key) throw new HttpError(500, "GEMINI_API_KEY 가 설정되지 않았습니다");
  await db.from("ai_calls").insert({ ip, task });

  const body = JSON.stringify({
    systemInstruction: { parts: [{ text: rubric }] },
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0, responseMimeType: "application/json", responseSchema: schema },
  });
  let last = "";
  for (const model of MODELS) {
    try {
      const res = await fetch(API.replace("{model}", model), {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": key },
        body,
        signal: AbortSignal.timeout(60_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await res.json();
      return { data: JSON.parse(raw.candidates[0].content.parts[0].text) as Json, model };
    } catch (e) {
      last = `${model}: ${e instanceof Error ? e.message : e}`;
    }
  }
  throw new HttpError(502, `Gemini 호출 실패 (${last})`);
}

// -- 민폐도 ----------------------------------------------------------------

function sanitizeNuisance(d: Json) {
  const num = (v: unknown, dflt: number) => (Number.isFinite(Number(v)) ? Math.round(Number(v)) : dflt);
  const tips = Array.isArray(d.tips) ? d.tips : d.tips ? [d.tips] : [];
  return {
    score: Math.max(0, Math.min(100, num(d.score, 50))),
    stay_minutes: Math.max(5, Math.min(480, num(d.stay_minutes, 60))),
    reason: String(d.reason ?? "").trim().slice(0, 300),
    tips: tips.slice(0, 4).map((t) => String(t).trim().slice(0, 200)).filter(Boolean),
  };
}

async function nuisance(ip: string, p: Json) {
  const quiet = Number(p?.quiet);
  if (!p || !MODES.has(p.mode as string) || !CATEGORY_LABELS.has(p.category as string) ||
      !YES_NO.has(p.official as string) || !YES_NO.has(p.purchase as string) ||
      !YES_NO.has(p.always_open as string) || !CAPACITY.has(p.capacity as string) ||
      !(quiet >= 0 && quiet <= 1)) {
    throw new HttpError(400, "profile 이 올바르지 않습니다");
  }
  const profile = {
    mode: p.mode, category: p.category, official: p.official, purchase: p.purchase,
    capacity: p.capacity, always_open: p.always_open, quiet: Math.round(quiet * 10) / 10,
  };
  const key = await sha1(Object.keys(profile).sort().map((k) => `${k}=${profile[k as keyof typeof profile]}`).join("|"));

  const hit = await db.from("ai_cache").select("data").eq("task", "nuisance").eq("key", key).maybeSingle();
  if (hit.data) return { result: hit.data.data, model: "cache" };

  // gemini.py 의 _describe() 와 같은 문장
  const prompt =
    `시설 유형: ${profile.category}\n` +
    `이용 목적: ${profile.mode} 쉼터\n` +
    `공식 지정 무더위·한파 쉼터: ${profile.official}\n` +
    `음료·물품 구매 필요: ${profile.purchase}\n` +
    `규모: ${profile.capacity}\n` +
    `24시간 개방: ${profile.always_open}\n` +
    `정숙도(0~1): ${profile.quiet}\n\n` +
    "개별 시설이 아니라 이 '유형'의 일반적인 특성을 기준으로 평가하세요.";
  const { data, model } = await gemini(ip, "nuisance", NUISANCE_RUBRIC, prompt, NUISANCE_SCHEMA);
  const result = sanitizeNuisance(data);
  await db.from("ai_cache").upsert({ task: "nuisance", key, data: result });
  return { result, model };
}

// -- 추정 쉼터 판단 ----------------------------------------------------------

async function judge(ip: string, items: unknown) {
  if (!Array.isArray(items) || items.length === 0 || items.length > BATCH) {
    throw new HttpError(400, `items 는 1~${BATCH}개여야 합니다`);
  }
  const clean = items.map((it) => {
    const name = String((it as Json)?.name ?? "").trim();
    const kind = String((it as Json)?.kind ?? "");
    if (!name || name.length > 60 || !POI_KINDS.has(kind)) throw new HttpError(400, "item 이 올바르지 않습니다");
    return { name, kind };
  });
  const keys = await Promise.all(clean.map((c) => sha1(`${c.name}|${c.kind}`)));

  const results: (Json | null)[] = clean.map(() => null);
  const hits = await db.from("ai_cache").select("key,data").eq("task", "judge").in("key", keys);
  const byKey = new Map((hits.data ?? []).map((r) => [r.key as string, r.data as Json]));
  const unknown: number[] = [];
  keys.forEach((k, i) => {
    const d = byKey.get(k);
    if (d) results[i] = { ...d, i };
    else unknown.push(i);
  });
  if (!unknown.length) return { results, model: "cache" };

  // candidates.py 의 _judge() 와 같은 문장
  const listing = unknown.map((idx, n) => `${n}. 상호: ${clean[idx].name} / 지도 분류: ${clean[idx].kind}`).join("\n");
  const prompt = `다음 ${unknown.length}곳을 판단하세요. i 는 아래 번호와 같아야 합니다.\n\n${listing}`;
  const { data, model } = await gemini(ip, "judge", JUDGE_RUBRIC, prompt, JUDGE_SCHEMA);

  const rows: Json[] = [];
  for (const item of (Array.isArray(data.results) ? data.results : []) as Json[]) {
    const n = Number(item?.i);
    if (!Number.isInteger(n) || n < 0 || n >= unknown.length) continue;
    const idx = unknown[n];
    const category = String(item.category ?? "center");
    const d = {
      usable: Boolean(item.usable),
      category,
      confidence: Math.max(0, Math.min(100, Math.round(Number(item.confidence) || 0))),
      note: String(item.note ?? "").trim().slice(0, 120),
    };
    results[idx] = { ...d, i: idx };
    rows.push({ task: "judge", key: keys[idx], data: d });
  }
  if (rows.length) await db.from("ai_cache").upsert(rows);
  return { results, model };
}

// -- 진입점 ----------------------------------------------------------------

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "POST 만 받습니다" }, 405);
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim();
  try {
    const body = await req.json().catch(() => null);
    if (body?.task === "nuisance") return json(await nuisance(ip, body.profile));
    if (body?.task === "judge") return json(await judge(ip, body.items));
    return json({ error: "task 는 nuisance 또는 judge 여야 합니다" }, 400);
  } catch (e) {
    if (e instanceof HttpError) return json({ error: e.message }, e.status);
    console.error(e);
    return json({ error: String(e) }, 500);
  }
});
