// 화면에 보여 줄 쉬운 말. 점수·영어·전문 용어 대신 누구나 바로 알아듣는 문장으로 바꾼다.
// coolmap/plain.py 와 같은 문장을 쓴다 — 한쪽을 고치면 다른 쪽도 고친다.

import { type Analysis, analysisDistance, type Now, stayLabel } from "./analysis";
import type { ChatContext, SkyHour } from "./backend";
import { categoryLabel, closingIn } from "./places";
import type { Mode } from "./theme";

/** 모드를 부르는 쉬운 이름 */
export const MODE_TITLE: Record<Mode, string> = { cooling: "더위 피하기", heating: "추위 피하기" };
export const SHELTER_WORD: Record<Mode, string> = { cooling: "무더위쉼터", heating: "한파쉼터" };

/** 0~24시 → '오전 9시', '오후 6시', '밤 12시' */
export function hourWord(h: number): string {
  const x = ((h % 24) + 24) % 24;
  if (x === 0) return "밤 12시";
  if (x < 12) return `오전 ${x}시`;
  if (x === 12) return "낮 12시";
  return `오후 ${x - 12}시`;
}

/** 지금 열려 있는지와 언제까지인지 */
export function openLine(a: Analysis, now: Now): string {
  const p = a.place;
  if (p.alwaysOpen) return "24시간 열려 있어요";
  if (!a.openNow) {
    if (p.weekendClosed && now.weekday >= 5) return "주말이라 문을 닫았어요";
    return `지금 문 닫음 · ${hourWord(p.openFrom)}에 열어요`;
  }
  const left = closingIn(p, now.hour, now.minute);
  if (left !== null && left <= 60) return `곧 문 닫아요 · ${left}분 남음`;
  return `지금 열려 있어요 · ${hourWord(p.openTo)}까지`;
}

export const walkLine = (a: Analysis) => `걸어서 ${Math.max(1, a.walkMin)}분 (${analysisDistance(a)})`;

export const tempLine = (a: Analysis) => `실내 약 ${Math.round(a.indoor)}°C`;

/** 실내가 바깥보다 얼마나 시원한지(따뜻한지). 실측 기온이 없으면 빈 문자열 */
export function tempCompare(a: Analysis): string {
  if (!a.weather.live) return "";
  const d = Math.round(Math.abs(a.weather.outdoor - a.indoor));
  if (d < 1) return "바깥과 비슷해요";
  const cooler = a.indoor < a.weather.outdoor;
  return `바깥보다 ${d}°C ${cooler ? "시원해요" : "따뜻해요"}`;
}

/** 민폐도(눈치)를 쉬운 말로 */
export function stayLine(a: Analysis): string {
  switch (a.nuisance.key) {
    case "very_low":
    case "low":
      return "오래 머물러도 괜찮아요";
    case "normal":
      return `${stayLabel(a.nuisance.stayMinutes)} 정도 쉬기 좋아요`;
    default:
      return "잠깐 쉬어 가기 좋아요";
  }
}

/** 공식 쉼터인지 · AI 추정인지 · 물건을 사야 하는지 — 카드에 붙는 표시 */
export function tags(a: Analysis): { text: string; tone: "good" | "warn" | "mute" }[] {
  const out: { text: string; tone: "good" | "warn" | "mute" }[] = [];
  if (a.place.official) out.push({ text: "공식 쉼터", tone: "good" });
  if (a.place.aiGuess) out.push({ text: "AI 추정 · 공식 아님", tone: "warn" });
  if (a.place.purchaseRequired) out.push({ text: "물건 구매 필요", tone: "mute" });
  return out;
}

/**
 * AI 추정 쉼터는 이만큼(m) 더 먼 것처럼 친다. 비슷한 거리면 공식 쉼터를 먼저 권하고,
 * AI 추정 쉼터는 확실히 더 가까울 때만 앞에 온다 (공식 쉼터가 아니고 운영 여부도 추정이라서).
 */
export const AI_GUESS_PENALTY_M = 300;

/** 지금 열려 있는 곳 먼저, 그다음 가까운 순 */
export function nearestFirst(list: Analysis[]): Analysis[] {
  const dist = (a: Analysis) => a.meters + (a.place.aiGuess ? AI_GUESS_PENALTY_M : 0);
  return [...list].sort((x, y) => Number(y.openNow) - Number(x.openNow) || dist(x) - dist(y));
}

/** 받침이 있으면 '이에요', 없으면 '예요' */
export function eyo(word: string): string {
  const c = word.trim().charCodeAt(word.trim().length - 1);
  if (c >= 0xac00 && c <= 0xd7a3) return word + ((c - 0xac00) % 28 ? "이에요" : "예요");
  return `${word}이에요`;
}

/** 받침에 따라 '은/는' */
export function eunNeun(word: string): string {
  const c = word.trim().charCodeAt(word.trim().length - 1);
  if (c >= 0xac00 && c <= 0xd7a3) return word + ((c - 0xac00) % 28 ? "은" : "는");
  return `${word}은`;
}

/** 받침에 따라 '이/가' */
export function iGa(word: string): string {
  const c = word.trim().charCodeAt(word.trim().length - 1);
  if (c >= 0xac00 && c <= 0xd7a3) return word + ((c - 0xac00) % 28 ? "이" : "가");
  return `${word}가`;
}

/** 제보 종류 — 사이렌 버튼을 누르면 고르는 문제 */
export const REPORT_KINDS: { kind: "closed" | "gone" | "no_hvac"; label: string; past: string; icon: string }[] = [
  { kind: "closed", label: "문이 닫혀 있어요", past: "문이 닫혀 있었어요", icon: "door-closed-lock" },
  { kind: "gone", label: "쉼터가 없어졌어요", past: "쉼터가 없어졌어요", icon: "map-marker-remove-outline" },
  { kind: "no_hvac", label: "냉난방이 안 돼요", past: "냉난방이 안 됐어요", icon: "thermometer-alert" },
];

/** '3시간 전' 같은 쉬운 시간 */
export function agoWord(iso: string, now = Date.now()): string {
  const min = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.round(h / 24)}일 전`;
}

/** 최근 제보 한 줄. 예) '3시간 전 이용자 제보: 문이 닫혀 있었어요 (2건)' */
export function reportLine(r: { kind: string; at: string; count: number }): string {
  if (r.kind === "ok") return `${agoWord(r.at)} 이용자 확인: 지금은 괜찮아요`;
  const what = REPORT_KINDS.find((k) => k.kind === r.kind)?.past ?? "문제가 있었어요";
  return `${agoWord(r.at)} 이용자 제보: ${what}${r.count > 1 ? ` (${r.count}건)` : ""}`;
}

// -- 하늘 (비 · 눈 · 맑음) — coolmap/plain.py sky_line ----------------------------
// 실황 PTY: 0 없음 · 1 비 · 2 비/눈 · 3 눈 · 5 빗방울 · 6 빗방울눈날림 · 7 눈날림
// 예보 PTY: 0 없음 · 1 비 · 2 비/눈 · 3 눈 · 4 소나기,  예보 SKY: 1 맑음 · 3 구름많음 · 4 흐림
export type SkyIcon = "sunny" | "night" | "partly" | "partly_night" | "cloudy" | "rain" | "sleet" | "snow" | "";
type Wet = "rain" | "sleet" | "snow";
const NOW_WET: Record<number, Wet> = { 1: "rain", 2: "sleet", 3: "snow", 5: "rain", 6: "sleet", 7: "snow" };
const FCST_WET: Record<number, Wet> = { 1: "rain", 2: "sleet", 3: "snow", 4: "rain" };
const WET_WORD: Record<Wet, string> = { rain: "비", sleet: "비와 눈", snow: "눈" };

const pad2 = (n: number) => String(n).padStart(2, "0");

/** 아이콘 · '비가 와요' · '오후 5시쯤 그칠 것 같아요'. 모르면 빈 글자. */
export function skyLine(
  obs: Record<string, string> | null | undefined,
  sky: SkyHour[] | null | undefined,
  d = new Date(),
): { icon: SkyIcon; text: string; hint: string } {
  const key = `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}${pad2(d.getHours())}`;
  const n = new Date(d.getTime() + 3600_000);
  const nxt = `${n.getFullYear()}${pad2(n.getMonth() + 1)}${pad2(n.getDate())}${pad2(n.getHours())}`;
  const hours = (sky ?? []).filter((h) => String(h.at) >= key);
  // 단기예보는 발표 시각의 다음 시간부터 나온다 → 지금 시각이 없으면 바로 다음 시간 것을 쓴다
  const cur = hours[0] && (hours[0].at === key || hours[0].at === nxt) ? hours[0] : undefined;
  const ahead = hours.filter((h) => String(h.at) > key).slice(0, 6);
  const night = d.getHours() >= 19 || d.getHours() < 6;
  const at = (h: SkyHour) => hourWord(Number(String(h.at).slice(8, 10)));

  const wet: Wet | undefined =
    obs && obs.PTY !== undefined ? NOW_WET[Math.trunc(Number(obs.PTY))] : cur ? FCST_WET[cur.pty] : undefined;
  if (wet) {
    const heavy = wet === "rain" && Number(String(obs?.RN1 ?? 0).replace("mm", "")) >= 3;
    const text = heavy ? "비가 많이 와요" : `${WET_WORD[wet]}${wet === "rain" ? "가" : "이"} 와요`;
    const stop = ahead.find((h) => !FCST_WET[h.pty]);
    return { icon: wet, text, hint: "우산 챙기세요" + (stop ? ` · ${at(stop)}쯤 그칠 것 같아요` : "") };
  }

  const [icon, text]: [SkyIcon, string] =
    cur?.sky === 1
      ? [night ? "night" : "sunny", "맑아요"]
      : cur?.sky === 3
        ? [night ? "partly_night" : "partly", "구름이 많아요"]
        : cur?.sky === 4
          ? ["cloudy", "흐려요"]
          : ["", ""];
  const coming = ahead.find((h) => FCST_WET[h.pty]);
  return { icon, text, hint: coming ? `${at(coming)}쯤 ${WET_WORD[FCST_WET[coming.pty]]} 소식 · 우산 챙기세요` : "" };
}

// -- 재난문자 — coolmap/plain.py region_of · alert_head --------------------------

/** 주소 → '시도 시군구 (구)'. 예) '경기도 성남시 분당구 판교역로 …' → '경기도 성남시 분당구'. 모르면 '' */
export function regionOf(address: string): string {
  const t = address.trim().split(/\s+/);
  if (!t[0] || !/^[가-힣]+(시|도)$/.test(t[0])) return "";
  const out = [t[0]];
  for (const x of t.slice(1, 3)) {
    if (!/^[가-힣]+(시|군|구)$/.test(x)) break;
    out.push(x);
  }
  return out.join(" ");
}

/** 위급·긴급 재난이면 빨강으로 보인다 */
export const alertUrgent = (step: string) => step.includes("위급") || step.includes("긴급");

/** 재난문자 머리줄. 예) '10분 전 · 호우 · 안전안내' */
export function alertHead(a: { at: string; kind: string; step: string }): string {
  return [agoWord(a.at), a.kind && a.kind !== "기타" ? a.kind : "", a.step].filter(Boolean).join(" · ");
}

// -- 물어보기 (Gemini) — coolmap/plain.py chat_context --------------------------------

/** supabase/functions/chat 에 질문과 함께 보낼 '지금 상황'. 가까운 20곳. 좌표는 보내지 않는다. */
export function chatContext(
  analyses: Analysis[],
  mode: Mode,
  now: Now,
  weather: { outdoor: number; alert: string; live: boolean },
  sky: { text: string; hint: string },
  alerts: { at: string; kind: string; step: string; text: string }[],
  reports: Record<string, { kind: string; at: string; count: number }>,
): ChatContext {
  return {
    mode,
    now: `${"월화수목금토일"[now.weekday]}요일 ${String(now.hour).padStart(2, "0")}:${String(now.minute).padStart(2, "0")}`,
    weather: {
      temp: weather.live ? `${weather.outdoor.toFixed(0)}°C` : "",
      sky: sky.text,
      hint: sky.hint,
      alert: weather.live ? weather.alert : "",
    },
    alerts: alerts.slice(0, 3).map((a) => `${alertHead(a)}: ${a.text}`),
    places: nearestFirst(analyses)
      .slice(0, 20)
      .map((a) => ({
        id: a.place.id,
        name: a.place.name,
        category: categoryLabel(a.place),
        kind: a.place.official ? "공식 쉼터" : "AI 추정 (공식 아님)",
        walk: walkLine(a),
        open: openLine(a, now),
        indoor: tempLine(a),
        stay: stayLine(a),
        report: reports[a.place.id] ? reportLine(reports[a.place.id]) : "",
      })),
  };
}
