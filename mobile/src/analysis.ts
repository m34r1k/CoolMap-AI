// CoolMap 예측 엔진. coolmap/ai.py 를 옮겼다.
//
// - 민폐도: Gemini 결과가 있으면 그것, 없으면 규칙 기반
// - 쾌적 점수: 온도/습도/공기흐름/공기질 가중 합
// - 혼잡도(사람 수) 예측은 데스크톱과 같이 비활성 — 화면에는 'COMING SOON'
//   (내부적으로는 민폐도 규칙·체감 온도 계산에 쓰이므로 시간대·요일·외기만으로 추정해 둔다)
//
// 행사(이벤트) 영향은 데스크톱에서도 데모 데이터라 옮기지 않았다.

import { distanceLabel, haversine, walkMinutes } from "./geo";
import { getNuisance } from "./nuisance";
import { closingIn, indoorTemp, isOpen, type Place } from "./places";
import type { Mode } from "./theme";

export const CROWD_ENABLED = false;

export type Weather = {
  outdoor: number;
  feels: number;
  humidity: number;
  condition: string;
  alert: string;
  live: boolean; // 기상청 실측이면 true, 모의 곡선이면 false
};

export type Crowd = { ratio: number; openNow: boolean };

export type Nuisance = {
  score: number;
  level: string;
  key: string;
  stayMinutes: number;
  factors: [string, number][];
  tips: string[];
  reason: string;
  source: "gemini" | "rule";
};

export type Analysis = {
  place: Place;
  mode: Mode;
  weather: Weather;
  crowd: Crowd;
  nuisance: Nuisance;
  comfort: number;
  indoor: number;
  feelsInside: number;
  delta: number;
  meters: number;
  walkMin: number;
};

export type Now = { hour: number; minute: number; weekday: number }; // weekday: 월=0 … 일=6

export function nowParts(d = new Date()): Now {
  return { hour: d.getHours(), minute: d.getMinutes(), weekday: (d.getDay() + 6) % 7 };
}

export function clockLabel(n: Now): string {
  return `${"월화수목금토일"[n.weekday]}요일 ${String(n.hour).padStart(2, "0")}:${String(n.minute).padStart(2, "0")}`;
}

export const stayLabel = (minutes: number) => {
  if (minutes >= 120) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}시간` + (m ? ` ${m}분` : "");
  }
  return `${minutes}분`;
};

export const analysisDistance = (a: Analysis) => distanceLabel(a.meters);

// -- 날씨 ----------------------------------------------------------------------

/** 기상청 실황(T1H·REH·WSD) → Weather. coolmap/providers/weather.py weather() */
export function weatherFromObs(obs: Record<string, string> | null | undefined, mode: Mode, n: Now): Weather {
  const temp = Number(obs?.T1H);
  if (!obs || !Number.isFinite(temp)) return mockWeather(mode, n);
  const humid = Number.isFinite(Number(obs.REH)) ? Math.trunc(Number(obs.REH)) : 50;
  const wind = Number.isFinite(Number(obs.WSD)) ? Number(obs.WSD) : 1.0;
  let feels: number;
  let alert: string;
  let condition: string;
  if (mode === "cooling") {
    // 열지수 근사 (Steadman 계열 단순화)
    feels = temp >= 27 ? temp + 0.05 * humid - 2.0 : temp;
    alert = temp >= 35 ? "폭염경보" : temp >= 33 ? "폭염주의보" : "";
    condition = temp >= 34 ? "매우 더움" : temp >= 30 ? "더움" : "보통";
  } else {
    // 풍속 냉각 (체감온도)
    const v = Math.max(wind * 3.6, 1.0) ** 0.16;
    feels = temp <= 10 ? 13.12 + 0.6215 * temp - 11.37 * v + 0.3965 * temp * v : temp;
    alert = temp <= -12 ? "한파경보" : temp <= -5 ? "한파주의보" : "";
    condition = temp <= -8 ? "매우 추움" : temp <= 3 ? "추움" : "보통";
  }
  return {
    outdoor: Math.round(temp * 10) / 10,
    feels: Math.round(feels * 10) / 10,
    humidity: Math.max(0, Math.min(100, humid)),
    condition,
    alert,
    live: true,
  };
}

/** 실측이 없을 때 계산에만 쓰는 곡선 (coolmap/data.py weather_for). 화면에는 실측이 아니라고 표시한다. */
function mockWeather(mode: Mode, n: Now): Weather {
  const t = n.hour + n.minute / 60;
  if (mode === "cooling") {
    const s = Math.sin(((t - 9.0) / 24.0) * 2 * Math.PI);
    const temp = 32.2 + 4.3 * s;
    const humid = Math.trunc(62 - 14 * s);
    return {
      outdoor: Math.round(temp * 10) / 10,
      feels: Math.round((temp + (humid - 45) * 0.09) * 10) / 10,
      humidity: Math.max(15, Math.min(95, humid)),
      condition: temp >= 34 ? "매우 더움" : "더움",
      alert: "",
      live: false,
    };
  }
  const temp = -6.6 + 4.6 * Math.sin(((t - 8.5) / 24.0) * 2 * Math.PI);
  const humid = Math.trunc(48 + 10 * Math.sin(((t - 3.0) / 24.0) * 2 * Math.PI));
  return {
    outdoor: Math.round(temp * 10) / 10,
    feels: Math.round((temp - 4.2) * 10) / 10,
    humidity: Math.max(15, Math.min(95, humid)),
    condition: temp <= -8 ? "매우 추움" : "추움",
    alert: "",
    live: false,
  };
}

// -- 혼잡도 (비활성, 내부 계산용) ------------------------------------------------

const PEAKS: Record<string, [number, number][]> = {
  library: [[11, 0.7], [15, 1.0], [19, 0.72]],
  dept: [[13, 0.72], [17, 1.0], [19, 0.82]],
  underground: [[12, 0.85], [18, 1.0]],
  subway: [[8, 1.0], [12, 0.5], [18, 1.0]],
  gov: [[10, 0.92], [14, 1.0]],
  bank: [[11, 1.0], [14, 0.78]],
  cafe: [[9, 0.62], [14, 1.0], [20, 0.72]],
  cinema: [[15, 0.62], [20, 1.0]],
  market: [[11, 0.9], [17, 1.0]],
  hospital: [[10, 1.0], [14, 0.82]],
  mall: [[14, 0.82], [18, 1.0]],
  center: [[10, 0.92], [14, 1.0]],
  store: [[12, 0.78], [19, 1.0], [22, 0.66]],
  bookstore: [[15, 0.88], [19, 1.0]],
  museum: [[11, 0.7], [14, 1.0]],
  park: [[7, 0.58], [19, 1.0]],
};

const WEEKEND: Record<string, number> = {
  dept: 1.3, mall: 1.32, cinema: 1.34, market: 1.24, museum: 1.28, park: 1.3, underground: 1.12,
  bookstore: 1.18, library: 1.1, cafe: 1.15, store: 1.05, hospital: 0.72, subway: 0.78,
  gov: 0.1, bank: 0.1, center: 0.55,
};

function daypart(category: string, hour: number): number {
  const peaks = PEAKS[category] ?? [[12, 1.0], [18, 0.8]];
  const sigma = 2.7;
  let val = 0;
  for (const [ph, w] of peaks) {
    const d = Math.min(Math.abs(hour - ph), 24 - Math.abs(hour - ph));
    val = Math.max(val, w * Math.exp(-(d * d) / (2 * sigma * sigma)));
  }
  return 0.45 + val * 0.7;
}

function weatherPull(mode: Mode, w: Weather): number {
  if (mode === "cooling") return 1.0 + Math.max(0, Math.min(0.52, (w.outdoor - 30.0) * 0.058));
  return 1.0 + Math.max(0, Math.min(0.52, -w.outdoor * 0.048));
}

function predictCrowd(p: Place, mode: Mode, n: Now, w: Weather): Crowd {
  const openNow = isOpen(p, n.hour, n.weekday);
  if (!openNow) return { ratio: 0, openNow };
  let pull = weatherPull(mode, w);
  if (p.category === "park" && mode === "cooling" && w.outdoor >= 35) pull *= 0.78;
  const week = n.weekday >= 5 ? (WEEKEND[p.category] ?? 1.0) : 1.0;
  const ratio = p.baseCrowd * daypart(p.category, n.hour) * pull * week;
  return { ratio: Math.max(0.02, Math.min(1.0, ratio)), openNow };
}

// -- 민폐도 ----------------------------------------------------------------------

const NUISANCE_LEVELS: [number, string, string][] = [
  [20, "매우 자연스러움", "very_low"],
  [38, "자연스러움", "low"],
  [58, "보통", "normal"],
  [76, "눈치 보임", "high"],
  [101, "매우 눈치 보임", "very_high"],
];

function nuisanceLevel(score: number): [string, string] {
  for (const [limit, label, key] of NUISANCE_LEVELS) if (score < limit) return [label, key];
  return [NUISANCE_LEVELS[4][1], NUISANCE_LEVELS[4][2]];
}

const BASE_STAY: Record<string, number> = {
  library: 180, gov: 150, center: 150, museum: 100, mall: 90, dept: 70, underground: 60, market: 60,
  park: 60, cafe: 90, bookstore: 45, hospital: 45, cinema: 40, subway: 30, bank: 25, store: 20,
};

/** 규칙 기반 민폐도: 높을수록 '오래 있으면 눈치 보이는' 장소 */
function scoreNuisance(p: Place, crowd: Crowd, n: Now): Nuisance {
  const factors: [string, number][] = [];
  let score = 18;
  if (p.purchaseRequired) {
    score += 30;
    factors.push(["구매 필요", 30]);
  }
  const press = Math.round(p.staffPressure * 30);
  if (press) {
    score += press;
    factors.push(["직원·주변 시선", press]);
  }
  const crowdPen = Math.round(Math.max(0, crowd.ratio - 0.45) * 74);
  if (crowdPen) {
    score += crowdPen;
    factors.push(["현재 혼잡도", crowdPen]);
  }
  if (p.seats < 30) {
    score += 13;
    factors.push(["좌석 부족", 13]);
  } else if (p.seats < 60) {
    score += 6;
    factors.push(["좌석 여유 낮음", 6]);
  }
  if (p.official) {
    score -= 14;
    factors.push(["공식 지정 쉼터", -14]);
  }
  const remain = closingIn(p, n.hour, n.minute);
  if (remain !== null && remain <= 45) {
    score += 9;
    factors.push(["마감 임박", 9]);
  }
  if (p.category === "hospital") {
    score += 8;
    factors.push(["이용 목적 배려 필요", 8]);
  }
  score = Math.trunc(Math.max(3, Math.min(97, Math.round(score))));
  const [level, key] = nuisanceLevel(score);

  let stay = (BASE_STAY[p.category] ?? 60) * (1 - score / 165.0) * (1.15 - crowd.ratio * 0.5);
  stay = Math.trunc(Math.max(10, Math.round(stay / 5) * 5));
  if (remain !== null) stay = Math.min(stay, Math.max(10, remain));

  const tips: string[] = [];
  if (p.official) tips.push("공식 지정 쉼터입니다. 눈치 보지 말고 이용하세요.");
  if (p.purchaseRequired) tips.push("음료 1잔 주문 후 이용하면 부담이 크게 줄어요.");
  if (crowd.ratio >= 0.7) tips.push("좌석 경쟁이 심한 시간대예요. 1인석 위주로 찾아보세요.");
  if (p.staffPressure >= 0.5) tips.push("직원 동선을 피해 창가·구석 좌석을 이용하는 편이 좋아요.");
  if (p.quiet >= 0.75) tips.push("정숙이 요구되는 공간이에요. 통화는 로비에서 하세요.");
  if (remain !== null && remain <= 45) tips.push(`마감까지 약 ${remain}분 남았어요.`);
  if (!tips.length) tips.push("특별히 주의할 점은 없어요. 편하게 머무르셔도 됩니다.");

  return { score, level, key, stayMinutes: stay, factors, tips, reason: "", source: "rule" };
}

/** Gemini 결과가 준비돼 있으면 그것으로, 아니면 규칙 기반 */
function aiNuisance(p: Place, mode: Mode, fallback: Nuisance): Nuisance {
  const d = getNuisance(p, mode);
  if (!d) return fallback;
  const [level, key] = nuisanceLevel(d.score);
  return {
    score: d.score,
    level,
    key,
    stayMinutes: d.stay_minutes,
    factors: fallback.factors,
    tips: d.tips.length ? d.tips : fallback.tips,
    reason: d.reason,
    source: "gemini",
  };
}

// -- 쾌적 점수 ----------------------------------------------------------------------

function comfortScore(p: Place, mode: Mode, w: Weather, crowd: Crowd, target: number): number {
  const indoor = indoorTemp(p, mode);
  const diff = indoor - target;
  // 냉방: 목표보다 시원한 것은 관대하게, 더운 것은 엄격하게 감점 (난방은 반대)
  const tempS =
    mode === "cooling"
      ? 100 - (diff < 0 ? Math.abs(diff) * 7.0 : diff * 11.5)
      : 100 - (diff < 0 ? Math.abs(diff) * 11.5 : diff * 7.0);
  const humidS = 100 - Math.abs(p.humidity - 45) * 2.2;
  const airS = ({ 우수: 96, 양호: 76, 보통: 56 } as Record<string, number>)[p.airflow] ?? 66;
  const aqiS = 100 - p.aqi * 1.5;
  // 혼잡도 비활성 — 해당 가중치를 제외하고 정규화
  let total = (tempS * 0.32 + airS * 0.14 + humidS * 0.13 + aqiS * 0.15) / 0.74;
  // 외기와의 격차 보너스 (쉼터로서의 가치)
  total +=
    mode === "cooling"
      ? Math.max(0, Math.min(5, (w.outdoor - indoor) * 0.42))
      : Math.max(0, Math.min(5, (indoor - w.outdoor) * 0.16));
  if (!crowd.openNow) total *= 0.55;
  return Math.trunc(Math.max(0, Math.min(100, Math.round(total))));
}

export function analyze(
  p: Place,
  mode: Mode,
  n: Now,
  target: number,
  origin: [number, number], // [lon, lat]
  weather: Weather,
): Analysis {
  const crowd = predictCrowd(p, mode, n, weather);
  const nuisance = aiNuisance(p, mode, scoreNuisance(p, crowd, n));
  const comfort = comfortScore(p, mode, weather, crowd, target);
  const indoor = indoorTemp(p, mode);
  // 실내 체감: 혼잡할수록 체감 온도가 올라간다(냉방)/내려간다(난방)
  const feels =
    mode === "cooling" ? indoor + crowd.ratio * 2.4 + (p.humidity - 45) * 0.04 : indoor - crowd.ratio * 0.6 + 0.4;
  const meters = haversine(origin[1], origin[0], p.lat, p.lon);
  return {
    place: p,
    mode,
    weather,
    crowd,
    nuisance,
    comfort,
    indoor,
    feelsInside: Math.round(feels * 10) / 10,
    delta: Math.round(Math.abs(weather.outdoor - indoor) * 10) / 10,
    meters,
    walkMin: walkMinutes(meters),
  };
}

export type Prefer = "balanced" | "cool" | "quiet" | "close" | "free";

/** 추천 정렬 */
export function rank(analyses: Analysis[], prefer: Prefer = "balanced"): Analysis[] {
  const key = (a: Analysis) => {
    let s = a.comfort;
    s -= a.nuisance.score * 0.35;
    s -= Math.min(a.walkMin, 40) * 0.55;
    if (!a.crowd.openNow) s -= 60;
    if (prefer === "cool") {
      s += (a.weather.outdoor - a.indoor) * (a.mode === "cooling" ? 1.4 : 0);
      s += (a.indoor - a.weather.outdoor) * (a.mode === "heating" ? 0.5 : 0);
    } else if (prefer === "quiet") {
      s += a.place.quiet * 26;
    } else if (prefer === "close") {
      s -= a.walkMin * 2.4;
    } else if (prefer === "free") {
      s -= a.nuisance.score * 0.75;
      s += a.place.official ? 18 : 0;
    }
    return -s;
  };
  return [...analyses].sort((a, b) => key(a) - key(b));
}
