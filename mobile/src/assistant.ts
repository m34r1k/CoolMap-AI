// CoolMap Intelligence — 규칙 기반 추천 어시스턴트. coolmap/assistant.py 를 옮겼다.
// 사용자의 질문을 의도로 분해한 뒤, 예측 엔진 결과를 근거로 답한다.
// 답의 굵은 글씨는 <b>…</b>, 줄바꿈은 \n 으로 표시한다.

import { type Analysis, type Prefer, rank, stayLabel } from "./analysis";
import type { Mode } from "./theme";

export const QUICK_PROMPTS: [string, string, string][] = [
  ["저혼잡", "지금 사람 적은 곳 알려줘", "account-group"],
  ["15분 휴식", "15분만 쉬어갈 곳 추천해줘", "clock-outline"],
  ["눈치 없는 곳", "오래 있어도 눈치 안 보이는 곳", "star-outline"],
  ["조용한 곳", "조용한 곳 추천해줘", "volume-off"],
  ["늦게까지", "밤 9시 이후에도 여는 곳", "weather-night"],
];

const KEYWORDS: [string[], Prefer][] = [
  [["조용", "정숙", "집중", "공부", "quiet"], "quiet"],
  [["눈치", "민폐", "오래", "장시간", "부담", "free"], "free"],
  [["가까", "근처", "빨리", "제일 가까", "close"], "close"],
  [["시원", "추운", "차가", "cool", "더위", "폭염"], "cool"],
  [["따뜻", "온기", "난방", "추위", "한파", "warm"], "cool"],
];

export type ChatReply = { text: string; places: Analysis[]; note?: string };

const openLate = (a: Analysis) => a.place.alwaysOpen || a.place.openTo >= 22;

export function respond(query: string, analyses: Analysis[], mode: Mode): ChatReply {
  const low = query.trim().toLowerCase();
  const openNow = analyses.filter((a) => a.crowd.openNow);

  let prefer: Prefer = "balanced";
  for (const [keys, key] of KEYWORDS) {
    if (keys.some((k) => low.includes(k))) {
      prefer = key;
      break;
    }
  }

  let pool = openNow.length ? openNow : analyses;
  let note = "";

  if (["이벤트", "행사", "축제", "붐비", "혼잡", "사람 적", "저혼잡"].some((k) => low.includes(k))) {
    // 데스크톱의 행사 데이터는 데모라 옮기지 않았다. 혼잡도도 아직 준비 중이다.
    note = "실시간 혼잡도·행사 정보는 준비 중이에요. 쾌적도와 민폐도를 기준으로 골랐어요.";
  }

  if (["밤", "늦게", "9시", "10시", "야간", "심야", "새벽"].some((k) => low.includes(k))) {
    const late = analyses.filter(openLate);
    if (late.length) pool = late;
    note = "22시 이후에도 운영하는 곳만 추렸어요.";
  }

  if (["15분", "잠깐", "잠시", "짧게"].some((k) => low.includes(k))) {
    pool = pool.filter((a) => a.walkMin <= 12);
    prefer = "close";
    note = "도보 12분 이내, 짧은 휴식에 적합한 곳입니다.";
  }

  if (["무료", "공공", "공식", "지정"].some((k) => low.includes(k))) {
    const official = pool.filter((a) => a.place.official);
    if (official.length) pool = official;
    note = "공식 지정 쉼터만 추렸어요.";
  }

  if (!pool.length) return { text: "조건에 맞는 쉼터를 찾지 못했어요. 조건을 조금 넓혀볼까요?", places: [] };

  const top = rank(pool, prefer).slice(0, 3);
  const best = top[0];
  const modeWord = mode === "cooling" ? "시원한" : "따뜻한";
  const reason: Record<Prefer, string> = {
    quiet: "정숙도가 높은 순으로 골랐어요.",
    free: "눈치 부담(민폐도)이 가장 낮은 순입니다.",
    close: "현재 위치에서 가까운 순입니다.",
    cool: "실내외 온도 격차가 큰 순입니다.",
    balanced: "쾌적도·민폐도·거리를 종합했어요.",
  };
  const outdoor = best.weather.live ? `현재 외기 ${best.weather.outdoor}°C 기준으로 ` : "";
  const lines = [
    `${outdoor}가장 ${modeWord} 곳은 <b>${best.place.name}</b>입니다.`,
    `실내 ${best.indoor.toFixed(1)}°C · 쾌적 ${best.comfort}점 · ` +
      `민폐도 ${best.nuisance.score}(${best.nuisance.level}), 권장 체류 ${stayLabel(best.nuisance.stayMinutes)}.`,
    reason[prefer],
  ];
  return { text: lines.join("\n"), places: top, note };
}

export function greeting(analyses: Analysis[], mode: Mode): ChatReply {
  const open = analyses.filter((a) => a.crowd.openNow);
  const ranked = rank(open.length ? open : analyses);
  const w = ranked[0]?.weather;
  const modeWord = mode === "cooling" ? "폭염" : "한파";
  const outdoor =
    w && w.live ? `지금 외기는 <b>${w.outdoor}°C</b>${w.alert ? ` (${w.alert})` : ""}입니다. ` : "";
  return {
    text:
      `안녕하세요. ${outdoor}${modeWord} 대응 쉼터를 실시간으로 분석하고 있어요.\n` +
      "아래 버튼을 누르거나 원하는 조건을 직접 입력해 보세요.",
    places: ranked.slice(0, 2),
  };
}
