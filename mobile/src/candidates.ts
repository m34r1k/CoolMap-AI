// 지도에 이름만 떠 있는 장소 → AI 추정 쉼터.
// coolmap/providers/candidates.py · overpass.py 와 catalog.py 의 병합 규칙을 옮겼다.
//
// 원칙
//   · 공식 지정 쉼터와 절대 섞지 않는다 (official=false, aiGuess=true)
//   · 애매하면 표시하지 않는다 — 헛걸음이 미표시보다 나쁘다
//   · 판단은 상호 단위로 캐시한다 (서버도 캐시하므로 같은 상호는 두 번 묻지 않는다)

import { aiJudge, type Judgment } from "./backend";
import { haversine } from "./geo";
import { assumedIndoor, CATEGORIES, type Place } from "./places";
import { load, removeByPrefix, save } from "./storage";
import type { Mode } from "./theme";

const CACHE_VERSION = 1; // ALLOW 나 질의를 바꾸면 올린다 (오래된 셀 캐시를 버린다)

const CELL = 0.01; // 약 1.1km × 0.9km
const MAX_CELLS = 42;
const MAX_NEW_CELLS = 12; // 한 번에 새로 요청할 셀 수 (가까운 곳부터 채운다)
const SCAN_LIMIT = 140; // 한 번에 판단 대상으로 올릴 POI 수
const BATCH = 25; // 서버에 한 번에 물어볼 개수
const MAX_INFLIGHT = 3;
export const MIN_CONFIDENCE = 62; // 이 아래는 지도에 올리지 않는다
const ASK_COOLDOWN = 120_000; // 판단 요청이 실패한 뒤 다시 물어보기까지

// Overpass — 자원봉사로 운영되는 공용 서버라 요청 간격을 지킨다
const ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
  "https://overpass.private.coffee/api/interpreter",
  "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
];
const MIN_INTERVAL = 1200;
// 주 서버는 과부하로 504 를 내거나 느린 일이 잦지만 몇 초 뒤엔 대개 통과한다.
// 예비 미러는 망에 따라 아예 닿지 않기도 하므로 짧게만 기다린다.
const PREFERRED_TIMEOUT = 25_000;
const MIRROR_TIMEOUT = 8_000;
const RETRY_PAUSE = 3_000;
const RETRY_TIMEOUT = 40_000;

// 질의는 키 단위로만 건다 — 값까지 정규식으로 거르면 공개 미러가 504 를 낸다.
const QUERY_KEYS = ["shop", "amenity", "tourism"];
const QUERY_EXTRA = [
  'way["name"]["building"~"^(retail|commercial|public|civic)$"]{bbox};',
  'node["name"]["railway"="station"]{bbox};',
  'way["name"]["railway"="station"]{bbox};',
  'way["name"]["leisure"~"^(sports_centre|fitness_centre)$"]{bbox};',
  'way["name"]["office"="government"]{bbox};',
];

// 여기 없는 값은 물어보지도 않는다. 기준은 '볼일 없이 들어가 있어도 되는가'.
// 편의점·카페·은행·식당은 구매나 용무가 사실상 전제라 뺐다.
// 서버(supabase/functions/ai)의 POI_KINDS 와 같아야 한다.
const ALLOW: Record<string, Set<string>> = {
  shop: new Set(["supermarket", "department_store", "mall", "wholesale", "variety_store", "books", "doityourself"]),
  amenity: new Set(["library", "community_centre", "townhall", "social_facility", "arts_centre", "theatre",
    "cinema", "marketplace", "public_bath", "college", "university", "post_office"]),
  tourism: new Set(["museum", "gallery", "aquarium"]),
  leisure: new Set(["sports_centre"]),
  office: new Set(["government"]),
  railway: new Set(["station"]),
  public_transport: new Set(["station"]),
  building: new Set(["retail", "commercial", "public", "civic"]),
};
// building 은 가장 뒤 — shop/amenity 가 있으면 그쪽이 훨씬 구체적이다.
const KIND_KEYS = ["shop", "amenity", "tourism", "leisure", "railway", "public_transport", "office", "building"];

// 유형별 기본 운영시간 (OSM opening_hours 는 형식이 제각각이라 쓰지 않는다)
const HOURS: Record<string, [number, number, boolean]> = {
  mart: [10, 23, false], store: [0, 24, false], dept: [10, 20, false], mall: [10, 22, false],
  underground: [10, 21, false], bookstore: [10, 22, false], cafe: [8, 22, false], cinema: [10, 24, false],
  market: [9, 20, false], subway: [5, 24, false], library: [9, 21, false], museum: [10, 18, false],
  gov: [9, 18, true], bank: [9, 16, true], hospital: [9, 18, false], center: [9, 21, false],
  senior: [9, 18, false], park: [0, 24, false], busstop: [0, 24, false],
};

// 공식 쉼터에는 없는 유형이라 추정표에 빠져 있는 것들 [냉방, 난방]
const EXTRA_INDOOR: Record<string, [number, number]> = {
  dept: [23.5, 23.0], mall: [24.0, 23.0], underground: [25.0, 21.0], bookstore: [24.5, 23.0],
  cinema: [23.5, 23.0], museum: [24.0, 23.0], cafe: [24.0, 23.0],
  subway: [25.5, 20.0], // 대합실 기준
  park: [29.0, 5.0],
};

const indoor = (category: string, mode: Mode) => {
  const extra = EXTRA_INDOOR[category];
  if (extra) return mode === "cooling" ? extra[0] : extra[1];
  return assumedIndoor(category, mode);
};

// '구매가 사실상 전제'인 곳만. 대형마트·백화점·서점은 사지 않고 둘러봐도 된다.
const PURCHASE = new Set(["store", "cafe"]);
const STAFF: Record<string, number> = {
  bank: 0.5, store: 0.6, cafe: 0.65, mart: 0.35, dept: 0.3, mall: 0.3, gov: 0.15, library: 0.15,
  museum: 0.25, hospital: 0.5, senior: 0.4, subway: 0.1, underground: 0.15, park: 0.05, busstop: 0.05,
};
const QUIET: Record<string, number> = {
  library: 0.9, museum: 0.8, gov: 0.6, bank: 0.6, hospital: 0.7, cafe: 0.4, mart: 0.2, store: 0.2,
  market: 0.15, subway: 0.15, busstop: 0.15, park: 0.25,
};

// 이름이 같고 이 거리 안이면 같은 시설로 본다. 역은 출입구·노선별로 따로 등록돼 멀리 떨어져 나온다.
const DUPE_M = 600;
const DUPE_M_STATION = 2500;

export type Poi = { id: string; name: string; kind: string; lat: number; lon: number; addr: string };
type Cell = [number, number];

// -- Overpass ---------------------------------------------------------------

let lastRequest = 0;
let gate: Promise<void> = Promise.resolve();
let preferred = 0;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function overpass(query: string): Promise<{ elements?: Record<string, unknown>[] }> {
  // 요청 간격은 앞선 요청이 끝날 때까지 기다린 뒤에 잰다
  const turn = gate.then(async () => {
    const wait = MIN_INTERVAL - (Date.now() - lastRequest);
    if (wait > 0) await sleep(wait);
    lastRequest = Date.now();
  });
  gate = turn.catch(() => {});
  await turn;

  const others = ENDPOINTS.map((_, i) => i).filter((i) => i !== preferred);
  const plan: [number, number, number][] = [
    [preferred, PREFERRED_TIMEOUT, 0],
    ...others.map((i): [number, number, number] => [i, MIRROR_TIMEOUT, 0]),
    [preferred, RETRY_TIMEOUT, RETRY_PAUSE],
  ];
  let error = "";
  for (const [i, timeout, pause] of plan) {
    if (pause) await sleep(pause);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(ENDPOINTS[i], {
        method: "POST",
        // overpass-api.de 는 User-Agent 가 없거나 흔한 값이면 406 으로 거절한다
        headers: { "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "CoolMapAI/1.0 (mobile)" },
        body: `data=${encodeURIComponent(query)}`,
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const parsed = await res.json();
      preferred = i;
      return parsed;
    } catch (e) {
      error = `${ENDPOINTS[i].split("/")[2]} ${e instanceof Error ? e.message : e}`;
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error(error || "overpass unreachable");
}

const cellOf = (lat: number, lon: number): Cell => [Math.floor(lat / CELL), Math.floor(lon / CELL)];
const cellCenter = ([la, lo]: Cell): [number, number] => [(la + 0.5) * CELL, (lo + 0.5) * CELL];

function cellQuery([la, lo]: Cell): string {
  const bbox = `(${la * CELL},${lo * CELL},${(la + 1) * CELL},${(lo + 1) * CELL})`;
  const parts: string[] = [];
  for (const key of QUERY_KEYS) {
    parts.push(`node["name"]["${key}"]${bbox};`, `way["name"]["${key}"]${bbox};`);
  }
  parts.push(...QUERY_EXTRA.map((t) => t.replace("{bbox}", bbox)));
  return `[out:json][timeout:50];(${parts.join("")});out center 600;`;
}

/** '무엇인가'를 하나 뽑는다. 허용 목록에 없으면 빈 문자열. */
function kindOf(tags: Record<string, string>): string {
  for (const k of KIND_KEYS) {
    const v = tags[k];
    if (v && ALLOW[k]?.has(v)) return `${k}=${v}`;
  }
  return "";
}

function parsePois(data: { elements?: Record<string, unknown>[] }): Poi[] {
  const out: Poi[] = [];
  const seen = new Set<string>();
  for (const el of data.elements ?? []) {
    const tags = (el.tags ?? {}) as Record<string, string>;
    const name = (tags.name ?? "").trim();
    if (!name || name.length > 60) continue;
    const c = (el.type === "node" ? el : el.center) as { lat?: number; lon?: number } | undefined;
    if (c?.lat === undefined || c?.lon === undefined) continue;
    const kind = kindOf(tags);
    if (!kind) continue; // 식당·약국처럼 쉼터로 볼 수 없는 종류
    const id = `G${String(el.type ?? "n")[0]}${el.id}`;
    if (seen.has(id)) continue;
    seen.add(id);
    const addr = [tags["addr:province"] || tags["addr:city"], tags["addr:district"], tags["addr:street"],
      tags["addr:housenumber"]].filter(Boolean).join(" ");
    out.push({ id, name, kind, lat: Number(c.lat), lon: Number(c.lon), addr });
  }
  return out;
}

// -- 셀 · 판단 캐시 -----------------------------------------------------------

const cells = new Map<string, Poi[]>();
const cellFailed = new Map<string, number>();
const CELL_FAIL_COOLDOWN = 180_000;

const cellKey = ([la, lo]: Cell) => `${la}_${lo}`;
const storageCellKey = (c: Cell) => `poi:${cellKey(c)}`;

async function cellItems(c: Cell): Promise<Poi[] | null> {
  const got = cells.get(cellKey(c));
  if (got) return got;
  const raw = await load<{ v: number; items: Poi[] } | null>(storageCellKey(c), null);
  if (!raw || raw.v !== CACHE_VERSION) return null;
  cells.set(cellKey(c), raw.items);
  return raw.items;
}

async function fetchCell(c: Cell): Promise<void> {
  if (Date.now() - (cellFailed.get(cellKey(c)) ?? 0) < CELL_FAIL_COOLDOWN) return;
  try {
    const items = parsePois(await overpass(cellQuery(c)));
    cells.set(cellKey(c), items);
    cellFailed.delete(cellKey(c));
    await save(storageCellKey(c), { v: CACHE_VERSION, items });
  } catch {
    cellFailed.set(cellKey(c), Date.now());
  }
}

type Judged = Judgment & { name: string };
let judged: Record<string, Judged> | null = null;
let failUntil = 0;
const asking = new Set<string>();

const judgeKey = (name: string, kind: string) => `${name}|${kind}`;

async function judgments(): Promise<Record<string, Judged>> {
  if (!judged) judged = await load<Record<string, Judged>>("judgments", {});
  return judged;
}

/** 아직 판단하지 않은 상호를 배치로 물어본다. */
async function ask(pois: Poi[]): Promise<void> {
  if (Date.now() < failUntil) return;
  const all = await judgments();
  const todo = new Map<string, Poi>();
  for (const poi of pois) {
    const key = judgeKey(poi.name, poi.kind);
    if (!all[key] && !asking.has(key)) todo.set(key, poi);
  }
  const batches: [string, Poi][][] = [];
  const entries = [...todo.entries()];
  for (let i = 0; i < entries.length && batches.length < MAX_INFLIGHT; i += BATCH) {
    batches.push(entries.slice(i, i + BATCH));
  }
  await Promise.all(
    batches.map(async (batch) => {
      batch.forEach(([k]) => asking.add(k));
      try {
        const results = await aiJudge(batch.map(([, poi]) => ({ name: poi.name, kind: poi.kind })));
        results.forEach((r, i) => {
          if (!r || !batch[i]) return;
          all[batch[i][0]] = {
            usable: Boolean(r.usable),
            category: String(r.category || "center"),
            confidence: Math.max(0, Math.min(100, Math.round(Number(r.confidence) || 0))),
            note: String(r.note ?? "").trim().slice(0, 120),
            name: batch[i][1].name,
          };
        });
        failUntil = 0;
      } catch {
        // 키가 잘못됐거나 한도를 넘긴 경우 계속 두들기지 않도록 잠시 쉰다
        failUntil = Date.now() + ASK_COOLDOWN;
      } finally {
        batch.forEach(([k]) => asking.delete(k));
      }
    }),
  );
  await save("judgments", all);
}

export async function judgeStats(): Promise<[number, number]> {
  const all = Object.values(await judgments());
  return [all.length, all.filter((j) => j.usable && j.confidence >= MIN_CONFIDENCE).length];
}

export async function clearCandidateCache(): Promise<void> {
  cells.clear();
  cellFailed.clear();
  judged = {};
  await removeByPrefix("poi:");
  await save("judgments", {});
}

// -- Place 합성 ----------------------------------------------------------------

/** 역은 OSM 에 '판교', '성남' 처럼 역 이름만 들어 있어서 그대로 쓰면 무엇인지 알 수 없다. */
function displayName(name: string, kind: string): string {
  if (kind.endsWith("=station") && !/(역|Station|station)$/.test(name)) return `${name}역`;
  return name;
}

function isDupe(poi: Poi, taken: Place[]): boolean {
  const name = displayName(poi.name, poi.kind).replace(/\s/g, "");
  const limit = poi.kind.endsWith("=station") ? DUPE_M_STATION : DUPE_M;
  return taken.some((p) => p.name.replace(/\s/g, "") === name && haversine(poi.lat, poi.lon, p.lat, p.lon) <= limit);
}

function poiToPlace(poi: Poi, j: Judgment, mode: Mode): Place {
  const category = CATEGORIES[j.category] ? j.category : "center";
  const conf = j.confidence;
  const [openFrom, openTo, weekendClosed] = HOURS[category] ?? [9, 21, false];
  const label = CATEGORIES[category][0];
  return {
    id: poi.id,
    name: displayName(poi.name, poi.kind),
    category,
    address: poi.addr,
    lat: poi.lat,
    lon: poi.lon,
    mode,
    summary:
      `지도에 표시된 상호를 보고 AI 가 추정한 ${label}입니다. ` +
      "공식 지정 쉼터가 아니므로 운영시간과 이용 가능 여부는 현장에서 확인하세요.",
    why: j.note || "냉난방되는 실내 공간으로 판단했습니다.",
    openFrom,
    openTo,
    official: false,
    alwaysOpen: openTo - openFrom >= 23,
    aiGuess: true,
    aiConfidence: conf,
    weekendClosed,
    seats: 30,
    capacity: 80,
    baseCrowd: 0.4,
    indoorCool: indoor(category, "cooling"),
    indoorHeat: indoor(category, "heating"),
    humidity: 50,
    airflow: "정보 없음",
    aqi: 30,
    purchaseRequired: PURCHASE.has(category),
    staffPressure: STAFF[category] ?? 0.35,
    quiet: QUIET[category] ?? 0.5,
    amenities: [`AI 추정 (확신도 ${conf}%)`, "공식 지정 쉼터 아님", `지도 분류: ${poi.kind}`, "실내 온도는 추정치"],
  };
}

/**
 * 반경 안에서 AI 가 쉼터로 인정한 장소.
 * 비어 있는 구역은 가까운 곳부터 하나씩 받아 오고, 받을 때마다 새로 나온 상호를 서버에 물어본 뒤
 * onProgress 로 그때까지의 결과를 알린다 (다 받을 때까지 지도가 비어 있지 않도록).
 */
export async function nearbyCandidates(
  origin: [number, number], // [lat, lon]
  mode: Mode,
  radiusM: number,
  limit: number,
  onProgress: (places: Place[]) => void,
  cancelled: () => boolean,
): Promise<Place[]> {
  const [lat0, lon0] = origin;
  const dlat = radiusM / 111_000;
  const dlon = radiusM / 88_000;
  const c0 = cellOf(lat0 - dlat, lon0 - dlon);
  const c1 = cellOf(lat0 + dlat, lon0 + dlon);
  if ((c1[0] - c0[0] + 1) * (c1[1] - c0[1] + 1) > MAX_CELLS) return [];

  const collect = async () => {
    const pois: [number, Poi][] = [];
    const missing: [number, Cell][] = [];
    for (let la = c0[0]; la <= c1[0]; la++) {
      for (let lo = c0[1]; lo <= c1[1]; lo++) {
        const c: Cell = [la, lo];
        const items = await cellItems(c);
        if (!items) {
          const [cla, clo] = cellCenter(c);
          missing.push([haversine(lat0, lon0, cla, clo), c]);
          continue;
        }
        for (const poi of items) {
          const d = haversine(lat0, lon0, poi.lat, poi.lon);
          if (d <= radiusM) pois.push([d, poi]);
        }
      }
    }
    pois.sort((a, b) => a[0] - b[0]);
    missing.sort((a, b) => a[0] - b[0]);
    return { scan: pois.slice(0, SCAN_LIMIT).map(([, p]) => p), missing };
  };

  const build = async (scan: Poi[]) => {
    const all = await judgments();
    const places: Place[] = [];
    for (const poi of scan) {
      const j = all[judgeKey(poi.name, poi.kind)];
      if (!j || !j.usable || j.confidence < MIN_CONFIDENCE) continue;
      // 같은 시설이 node 와 way 로 두 번 들어오는 일이 흔하다
      if (isDupe(poi, places)) continue;
      if (places.length < limit) places.push(poiToPlace(poi, j, mode));
    }
    return places;
  };

  // 이미 받아 둔 구역부터 보여 준다
  let { scan, missing } = await collect();
  await ask(scan);
  let places = await build(scan);
  onProgress(places);

  for (const [, c] of missing.slice(0, MAX_NEW_CELLS)) {
    if (cancelled()) return places;
    await fetchCell(c);
    ({ scan } = await collect());
    await ask(scan);
    places = await build(scan);
    if (!cancelled()) onProgress(places);
  }
  return places;
}

// -- 공식 목록과 병합 (catalog.py) ---------------------------------------------

const DEDUPE_SAME_M = 800;
const DEDUPE_PART_M = 300;
const DEDUPE_RATIO = 0.5;

const squash = (name: string) => name.replace(/[\s()[\]\-·,.'"]/g, "");

/**
 * 두 장소가 같은 시설인지. 거리만 보면 안 된다 — 큰 건물 안에 다른 시설이 입점한 경우가
 * 흔해서, 홈플러스가 그 안의 농협 지점(16m)과 같은 곳으로 묶여 사라진 적이 있다.
 */
function samePlace(a: Place, b: Place): boolean {
  const an = squash(a.name);
  const bn = squash(b.name);
  if (!an || !bn) return false;
  const dist = haversine(a.lat, a.lon, b.lat, b.lon);
  if (an === bn) return dist <= DEDUPE_SAME_M;
  if (an.includes(bn) || bn.includes(an)) {
    const ratio = Math.min(an.length, bn.length) / Math.max(an.length, bn.length);
    return ratio >= DEDUPE_RATIO && dist <= DEDUPE_PART_M;
  }
  return false;
}

/** AI 추정 쉼터를 공식 목록 뒤에 덧붙인다. 겹치면 공식 쪽만 남긴다. */
export function mergeCandidates(official: Place[], guesses: Place[], mode: Mode): Place[] {
  const out = [...official];
  for (const g of guesses) {
    if (mode === "heating" && g.category === "park") continue; // 야외 쉼터는 난방 모드에서 의미가 없다
    if (!official.some((p) => samePlace(g, p))) out.push(g);
  }
  return out;
}
