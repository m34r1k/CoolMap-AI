// 화면에 보여 줄 쉬운 말. 점수·영어·전문 용어 대신 누구나 바로 알아듣는 문장으로 바꾼다.
// coolmap/plain.py 와 같은 문장을 쓴다 — 한쪽을 고치면 다른 쪽도 고친다.

import { type Analysis, analysisDistance, type Now, stayLabel } from "./analysis";
import { closingIn } from "./places";
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
