// 서버 레코드 → 화면에 보여줄 쉼터.
// coolmap/providers/shelters.py 의 record_to_place 에서 모바일 화면에 쓰는 부분만 옮겼다.
// 분류 규칙이나 기본 운영시간을 바꾸면 양쪽을 같이 고쳐야 한다.

import type { NearRow } from "./backend";
import type { Mode } from "./theme";

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
  [["행정복지센터", "주민센터", "주민자치센터"], "gov"],
  [
    ["복지관", "복지회관", "복지센터", "문화의집", "체육센터", "체육관", "청소년센터",
     "문화센터", "기념관", "박물관", "미술관", "문예회관", "평생학습",
     "이동노동자", "교회", "성당", "사찰"],
    "center",
  ],
  [["구청", "시청", "군청", "면사무소", "읍사무소", "동사무소", "민원센터", "우체국", "청사"], "gov"],
  [["전통시장", "상가"], "market"],
  [["야외", "공원", "정자", "그늘막", "파고라", "물놀이"], "park"],
];

export const CATEGORY_LABEL: Record<string, string> = {
  gov: "주민센터",
  bank: "은행",
  market: "전통시장",
  hospital: "병원 로비",
  center: "복지관",
  store: "편의점",
  library: "도서관",
  park: "야외 쉼터",
  senior: "경로당·마을회관",
  busstop: "버스정류장",
  mart: "대형마트",
};

export type Shelter = {
  id: string;
  name: string;
  category: string;
  address: string;
  lat: number;
  lon: number;
  distM: number;
  hours: string;
  alwaysOpen: boolean;
  weekendClosed: boolean;
  openFrom: number;
  openTo: number;
  capacity: number;
  amenities: string[];
  summary: string;
};

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

const pad2 = (n: number) => String(n).padStart(2, "0");

export function toShelter(row: NearRow, mode: Mode): Shelter | null {
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
  // 냉방설비가 있는 스마트쉼터 정류장은 밀폐형 부스라 실내로 본다
  const outdoor = ty === TY_OUTDOOR || category === "park" || (category === "busstop" && !ac);
  const people = Number(rec.capacity) || 0;
  const area = Number(rec.area) || 0;

  const [dFrom, dTo, dWeekendClosed] = DEFAULT_HOURS[ty] ?? [9, 18, false];
  let openFrom = hhmmToHour(rec.wkday_from) ?? dFrom;
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

  const hasCooling = Boolean(ac) || Boolean(fan);
  const amenities: string[] = [];
  if (cold) amenities.push("난방설비 정보 없음");
  else amenities.push(hasCooling ? "냉방설비 있음" : "냉방설비 정보 없음");
  if (area) amenities.push(`${area}㎡`);
  if (night) amenities.push("야간 개방");
  if (weekendFlag === "Y") amenities.push("주말·공휴일 개방");
  if (rec.stay_ok === "Y") amenities.push("숙박 가능");
  const remark = String(rec.remark ?? "").trim();
  if (remark) amenities.push(remark);

  let summary: string;
  if (cold) {
    summary =
      "행정안전부 지정 한파쉼터입니다. " +
      (people ? `약 ${people}명이 이용할 수 있습니다.` : "한파 시 개방되는 실내 공간입니다.");
  } else if (category === "busstop") {
    summary =
      "행정안전부 지정 무더위쉼터로 등록된 버스정류장입니다. " +
      (ac ? "냉방설비를 갖춘 밀폐형 스마트쉼터입니다." : "그늘막 형태의 야외 정류장입니다.");
  } else {
    summary =
      "행정안전부 지정 무더위쉼터입니다. " +
      (hasCooling ? "냉방설비를 갖추고 있습니다." : "냉방설비 정보는 등록되어 있지 않습니다.");
  }

  const hours = alwaysOpen
    ? "상시 개방"
    : `평일 ${pad2(openFrom)}:00–${pad2(openTo)}:00` + (weekendClosed ? " · 주말 휴무" : "");

  return {
    id: `${cold ? "C" : "H"}${row.no}`,
    name,
    category,
    address: String(rec.road_addr || rec.addr || "").trim(),
    lat,
    lon,
    distM: row.dist_m,
    hours,
    alwaysOpen,
    weekendClosed,
    openFrom,
    openTo,
    capacity: people,
    amenities,
    summary,
  };
}

/** 지금 열려 있는지 (공휴일은 모른다) */
export function isOpenNow(s: Shelter, now = new Date()): boolean {
  if (s.alwaysOpen) return true;
  const day = now.getDay();
  if (s.weekendClosed && (day === 0 || day === 6)) return false;
  const h = now.getHours();
  return h >= s.openFrom && h < s.openTo;
}
