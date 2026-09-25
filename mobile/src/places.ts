// 장소 모델과 공식 쉼터 레코드 변환.
// coolmap/models.py 의 Place · CATEGORIES 와 coolmap/providers/shelters.py 의 record_to_place 를
// 옮겼다. 분류 규칙이나 추정치를 바꾸면 양쪽을 같이 고쳐야 한다.

import type { NearRow } from "./backend";
import type { Mode } from "./theme";

/** 카테고리 키 → [표시명, 아이콘(MaterialCommunityIcons)]. 표시명은 서버 AI 허용 목록과 같아야 한다. */
export const CATEGORIES: Record<string, [string, string]> = {
  library: ["도서관", "bookshelf"],
  dept: ["백화점", "shopping"],
  underground: ["지하상가", "store"],
  subway: ["지하철역", "subway-variant"],
  gov: ["주민센터", "office-building"],
  bank: ["은행", "bank"],
  cafe: ["카페", "coffee"],
  cinema: ["영화관", "filmstrip"],
  market: ["전통시장", "storefront"],
  hospital: ["병원 로비", "hospital-building"],
  mall: ["복합쇼핑몰", "domain"],
  center: ["복지관", "home-group"],
  store: ["편의점", "shopping-outline"],
  bookstore: ["서점", "book-open-variant"],
  museum: ["미술관", "palette"],
  park: ["야외 쉼터", "tree"],
  senior: ["경로당·마을회관", "home-heart"],
  busstop: ["버스정류장", "bus"],
  mart: ["대형마트", "cart"],
};

export type Place = {
  id: string;
  name: string;
  category: string;
  address: string;
  lat: number;
  lon: number;
  mode: Mode;
  summary: string;
  why: string;

  // 운영
  openFrom: number; // 시(hour)
  openTo: number; // 24 이상이면 익일까지
  official: boolean; // 공식 지정 무더위/한파 쉼터
  alwaysOpen: boolean;
  aiGuess: boolean; // 공식 목록에는 없지만 지도의 상호를 보고 AI 가 추정한 쉼터
  aiConfidence: number; // 0..100
  weekendClosed: boolean;

  // 규모 / 환경
  seats: number;
  capacity: number;
  baseCrowd: number;
  indoorCool: number;
  indoorHeat: number;
  humidity: number;
  airflow: string;
  aqi: number;

  // 사회적 요소 (민폐도 계산용)
  purchaseRequired: boolean;
  staffPressure: number; // 0..1
  quiet: number; // 0..1

  amenities: string[];
};

export const categoryLabel = (p: Pick<Place, "category">) => (CATEGORIES[p.category] ?? ["기타"])[0];
export const categoryIcon = (p: Pick<Place, "category">) => (CATEGORIES[p.category] ?? ["", "map-marker"])[1];

export const indoorTemp = (p: Place, mode: Mode) => (mode === "cooling" ? p.indoorCool : p.indoorHeat);

const pad2 = (n: number) => String(n).padStart(2, "0");

export function hoursLabel(p: Place): string {
  if (p.alwaysOpen) return "24시간 운영";
  const label = `${pad2(p.openFrom)}:00 – ${pad2(p.openTo % 24)}:00`;
  return p.weekendClosed ? `${label} (주말 휴관)` : label;
}

/** weekday 는 파이썬과 같이 월=0 … 일=6 */
export function isOpen(p: Place, hour: number, weekday?: number): boolean {
  if (p.alwaysOpen) return true;
  if (p.weekendClosed && weekday !== undefined && weekday >= 5) return false;
  if (p.openTo <= 24) return p.openFrom <= hour && hour < p.openTo;
  return hour >= p.openFrom || hour < p.openTo - 24;
}

/** 마감까지 남은 분. 24시간 운영이면 null. */
export function closingIn(p: Place, hour: number, minute = 0): number | null {
  if (p.alwaysOpen || !isOpen(p, hour)) return null;
  const end = p.openTo > hour ? p.openTo : p.openTo + 24;
  return Math.round((end - hour) * 60 - minute);
}

// ---------------------------------------------------------------------------
// 공식 쉼터 레코드 → Place (shelters.py record_to_place)
// ---------------------------------------------------------------------------

const TY_PUBLIC = "001"; // 행정복지센터 · 주민센터 · 복지관
const TY_OUTDOOR = "002"; // 야외 쉼터 · 공원 정자
const TY_SENIOR = "003"; // 경로당 · 마을회관 (전체의 약 83%)
const TY_BANK = "004"; // 금융기관 (새마을금고 · 농협 등)

// 유형별 기본 운영시간 (데이터에 값이 없을 때): [시작, 끝, 주말 휴무]
const DEFAULT_HOURS: Record<string, [number, number, boolean]> = {
  [TY_PUBLIC]: [9, 18, true],
  [TY_SENIOR]: [9, 18, false],
  [TY_BANK]: [9, 16, true],
  [TY_OUTDOOR]: [0, 24, false],
};

// 순서가 곧 우선순위. '무엇에 붙어 있는가'보다 '무엇인가'를 먼저 판정한다.
const NAME_RULES: [string[], string][] = [
  [["정류장", "정류소", "승강장", "버스쉼터"], "busstop"],
  [["금고", "농협", "은행", "뱅크", "신협", "수협", "축협", "저축은행"], "bank"],
  [["이마트24", "GS25", "CU편", "세븐일레븐", "편의점"], "store"],
  [["이마트", "홈플러스", "롯데마트", "코스트코", "하나로마트", "농협마트"], "mart"],
  [["도서관"], "library"],
  [["경로당", "마을회관", "노인정", "어르신", "경로복지", "사랑채"], "senior"],
  [["보건진료소", "진료소", "보건지소", "보건소", "병원", "의원"], "hospital"],
  // '○○동행정복지센터' 는 주민센터다. 아래 center 의 '복지센터' 보다 먼저 본다.
  [["행정복지센터", "주민센터", "주민자치센터"], "gov"],
  [
    ["복지관", "복지회관", "복지센터", "문화의집", "체육센터", "체육관", "청소년센터",
     "문화센터", "기념관", "박물관", "미술관", "문예회관", "평생학습",
     "이동노동자", "교회", "성당", "사찰"],
    "center",
  ],
  [["구청", "시청", "군청", "면사무소", "읍사무소", "동사무소", "민원센터", "우체국", "청사"], "gov"],
  [["전통시장", "상가"], "market"],
  // '쉼터' 는 실내에도 흔히 붙으므로 야외 판정에서 제외한다
  [["야외", "공원", "정자", "그늘막", "파고라", "물놀이"], "park"],
];

// 냉방설비 정보가 비어 있을 때 쓰는 유형별 실내 온도 추정치
const ASSUMED_INDOOR: Record<string, number> = {
  bank: 24.5, gov: 24.5, library: 24.5, center: 25.0,
  store: 24.0, mart: 23.5, hospital: 24.0, market: 26.5,
  senior: 26.0, busstop: 25.5,
};

// 한파쉼터에는 난방설비 정보가 없어 유형만으로 추정한다
const ASSUMED_INDOOR_HEAT: Record<string, number> = {
  senior: 24.5, // 경로당은 대체로 따뜻하게 유지한다
  gov: 23.0, library: 23.0, center: 23.5, hospital: 23.5,
  bank: 23.0, mart: 22.5, store: 22.5, market: 21.5,
  busstop: 18.0, // 밀폐형 스마트쉼터 기준
};

/** 유형만 아는 시설의 실내 온도 추정치 (AI 추정 쉼터와 같은 기준) */
export function assumedIndoor(category: string, mode: Mode): number {
  return mode === "heating" ? (ASSUMED_INDOOR_HEAT[category] ?? 23.0) : (ASSUMED_INDOOR[category] ?? 26.0);
}

function classify(name: string, ty: string): string {
  for (const [keys, cat] of NAME_RULES) {
    if (keys.some((k) => name.includes(k))) return cat;
  }
  return { [TY_PUBLIC]: "gov", [TY_OUTDOOR]: "park", [TY_SENIOR]: "senior", [TY_BANK]: "bank" }[ty] ?? "center";
}

/** '0900' / '090000' 둘 다 시(hour)로 바꾼다. 한파쉼터는 평일 4자리, 토·일 6자리로 섞여 들어온다. */
function hhmmToHour(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const s = String(v).trim();
  if ((s.length !== 4 && s.length !== 6) || !/^\d+$/.test(s)) return null;
  const h = Number(s.slice(0, 2));
  return h >= 0 && h <= 24 ? h : null;
}

const STAFF: Record<string, number> = {
  bank: 0.45, store: 0.55, mart: 0.3, gov: 0.05, senior: 0.25, park: 0.0, busstop: 0.0,
};
const QUIET: Record<string, number> = {
  library: 0.9, gov: 0.6, senior: 0.4, park: 0.25, bank: 0.6, busstop: 0.15, mart: 0.2,
};

/** 정규화된 레코드 → Place. 좌표가 없으면 버린다. */
export function shelterToPlace(row: NearRow, mode: Mode): Place | null {
  const rec = row.rec;
  const lat = Number(rec.lat);
  const lon = Number(rec.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (!(lat >= 33 && lat <= 39.5 && lon >= 124 && lon <= 132)) return null;

  const cold = mode === "heating";
  const name = String(rec.name || (cold ? "한파쉼터" : "무더위쉼터")).trim();
  const ty = String(rec.type || TY_SENIOR);
  const category = classify(name, ty);

  const ac = Number(rec.ac) || 0;
  const fan = Number(rec.fan) || 0;
  // 버스정류장은 두 종류다.
  //  · 냉방설비가 있는 '스마트쉼터/스마트승강장' — 밀폐형 부스라 실내로 본다
  //  · 그늘막만 있는 일반 정류장 — 야외
  const outdoor = ty === TY_OUTDOOR || category === "park" || (category === "busstop" && !ac);
  const people = Number(rec.capacity) || 0;
  const area = Number(rec.area) || 0;

  const [dFrom, dTo, dWeekendClosed] = DEFAULT_HOURS[ty] ?? [9, 18, false];
  const openFrom = hhmmToHour(rec.wkday_from) ?? dFrom;
  let openTo = hhmmToHour(rec.wkday_to);
  if (openTo === null || openTo <= openFrom) openTo = Math.max(dTo, openFrom + 1);

  let weekendClosed: boolean;
  let night: boolean;
  let weekendFlag: string | undefined;
  if (cold) {
    // 한파쉼터는 요일별 운영시간이 따로 있다 → 토·일 값이 있으면 주말도 연다
    const sat = hhmmToHour(rec.sat_to);
    const sun = hhmmToHour(rec.sun_to);
    weekendClosed = !(sat || sun);
    night = false;
    weekendFlag = sat || sun ? "Y" : "N";
  } else {
    weekendFlag = rec.weekend_open ? String(rec.weekend_open) : undefined;
    weekendClosed = weekendFlag ? weekendFlag === "N" : dWeekendClosed;
    night = rec.night_open === "Y";
  }
  // 0000~2400 처럼 하루 전체가 적힌 경우는 상시 개방으로 본다
  const alwaysOpen =
    outdoor || category === "busstop" || openTo - openFrom >= 23 || (night && openTo - openFrom >= 20);

  // 실내 온도는 언제나 '추정치'다. 설비 대수는 신뢰도가 낮아 보유 여부만 참고한다.
  const hasCooling = Boolean(ac) || Boolean(fan);
  const indoorCool = outdoor ? 29.0 : (ASSUMED_INDOOR[category] ?? 26.0) - (ac ? 1.0 : 0.0);
  const indoorHeat = outdoor ? 5.0 : (ASSUMED_INDOOR_HEAT[category] ?? 23.0);
  const airflow = ac ? "양호" : fan ? "보통" : "정보 없음";

  const amenities: string[] = [];
  if (cold) amenities.push("난방설비 정보 없음");
  else amenities.push(hasCooling ? "냉방설비 있음" : "냉방설비 정보 없음");
  if (area) amenities.push(`${area}㎡`);
  if (night) amenities.push("야간 개방");
  if (weekendFlag === "Y") amenities.push("주말·공휴일 개방");
  if (rec.stay_ok === "Y") amenities.push("숙박 가능");
  const remark = String(rec.remark ?? "").trim();
  if (remark) amenities.push(remark);
  amenities.push("실내 온도는 추정치");

  const seats = Math.max(4, people ? Math.trunc(people) : 20);

  let summary: string;
  let why: string;
  if (cold) {
    summary =
      "행정안전부 지정 한파쉼터입니다. " +
      (people ? `약 ${people}명이 이용할 수 있습니다.` : "한파 시 개방되는 실내 공간입니다.");
    why = "공식 지정 한파쉼터라 무료이며, 추위를 피하러 들어가도 눈치가 보이지 않습니다.";
  } else if (category === "busstop") {
    summary =
      "행정안전부 지정 무더위쉼터로 등록된 버스정류장입니다. " +
      (ac ? "냉방설비를 갖춘 밀폐형 스마트쉼터입니다." : "그늘막 형태의 야외 정류장입니다.");
    why = "공식 지정 무더위쉼터라 무료이며, 이용에 눈치가 보이지 않습니다.";
  } else {
    summary =
      "행정안전부 지정 무더위쉼터입니다. " +
      (hasCooling ? "냉방설비를 갖추고 있습니다." : "냉방설비 정보는 등록되어 있지 않습니다.");
    why = "공식 지정 무더위쉼터라 무료이며, 이용에 눈치가 보이지 않습니다.";
  }

  return {
    id: `${cold ? "C" : "H"}${row.no}`,
    name,
    category,
    address: String(rec.road_addr || rec.addr || "").trim(),
    lat,
    lon,
    mode,
    summary,
    why,
    openFrom,
    openTo,
    official: true,
    alwaysOpen,
    aiGuess: false,
    aiConfidence: 0,
    weekendClosed,
    seats,
    capacity: Math.max(seats, people ? Math.trunc(people) : 40),
    baseCrowd: 0.3,
    indoorCool,
    indoorHeat,
    humidity: 50,
    airflow,
    aqi: 28,
    purchaseRequired: category === "store" || category === "mart",
    staffPressure: STAFF[category] ?? 0.15,
    quiet: QUIET[category] ?? 0.5,
    amenities,
  };
}
