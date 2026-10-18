// 물어보기 — 규칙 기반 대화. coolmap/assistant.py 와 같은 규칙·문장을 쓴다 (한쪽을 고치면 다른 쪽도).
// 질문에서 '무엇을 찾는지(가까운 곳 · 열린 곳 · 밤늦게 · 오래 · 조용 · 시원/따뜻 · 공식 · 시설 종류 · 장소 이름 · 날씨)'
// 를 읽어, 지금 분석된 주변 쉼터 중에서 골라 쉬운 말로 답한다.
// 답의 굵은 글씨는 <b>…</b>, 줄바꿈은 \n 으로 표시한다.

import type { Analysis, Now, Weather } from "./analysis";
import { categoryLabel, hoursLabel } from "./places";
import { eunNeun, eyo, hourWord, iGa, nearestFirst, openLine, SHELTER_WORD, stayLine, tempCompare, walkLine } from "./plain";
import type { Mode } from "./theme";

export type ChatReply = { text: string; places: Analysis[] };

/** 누르기만 하면 되는 질문 */
export function suggestions(mode: Mode): string[] {
  return [
    "가장 가까운 쉼터는 어디야?",
    "지금 열려 있는 곳 알려줘",
    mode === "cooling" ? "가장 시원한 곳은?" : "가장 따뜻한 곳은?",
    "오래 쉬어도 되는 곳은?",
    "밤늦게까지 여는 곳은?",
    "지금 바깥 날씨 어때?",
  ];
}

/** 질문에 나오는 말 → 시설 종류 (places.ts CATEGORIES) */
const CATEGORY_WORDS: [string[], string][] = [
  [["도서관"], "library"],
  [["은행", "금고", "농협", "우체국"], "bank"],
  [["주민센터", "행정복지센터", "동사무소", "구청", "시청", "면사무소"], "gov"],
  [["경로당", "마을회관", "노인정"], "senior"],
  [["복지관"], "center"],
  [["지하철", "전철"], "subway"],
  [["편의점"], "store"],
  [["카페", "커피"], "cafe"],
  [["마트", "하나로"], "mart"],
  [["백화점"], "dept"],
  [["쇼핑몰"], "mall"],
  [["영화관", "극장"], "cinema"],
  [["병원"], "hospital"],
  [["서점", "책방"], "bookstore"],
  [["시장"], "market"],
  [["지하상가"], "underground"],
  [["미술관", "박물관"], "museum"],
  [["공원", "야외"], "park"],
  [["정류장", "버스"], "busstop"],
];

const openLate = (a: Analysis) => a.place.alwaysOpen || a.place.openTo >= 22;

/** '<b>이름</b>이에요' — 조사는 굵게 하지 않는다 */
const named = (name: string) => `<b>${name}</b>${eyo(name).slice(name.length)}`;

/** 열린 곳을 앞에 두고 key 가 작은 순 */
const byOpenThen = (list: Analysis[], key: (a: Analysis) => number) =>
  [...list].sort((x, y) => Number(y.openNow) - Number(x.openNow) || key(x) - key(y));

/** 하늘 한 줄 (plain.ts skyLine) */
type Sky = { text: string; hint: string };

export function respond(query: string, analyses: Analysis[], mode: Mode, now: Now, weather: Weather, sky?: Sky): ChatReply {
  const q = query.replace(/\s+/g, "").toLowerCase();
  const has = (...words: string[]) => words.some((w) => q.includes(w));

  if (has("고마", "감사", "땡큐")) {
    return { text: `천만에요. ${mode === "cooling" ? "더위" : "추위"} 조심하세요!`, places: [] };
  }
  if (has("안녕", "하이") && q.length <= 8) return greeting(mode, weather, sky);

  // 날씨만 묻는 질문 ('시원한 곳' 처럼 장소를 찾는 질문은 아래에서)
  const askSky = has("비와", "비오", "비가", "비올", "우산", "눈와", "눈오", "눈이와", "눈올", "하늘", "맑");
  if ((askSky || has("날씨", "몇도", "기온", "바깥온도", "밖에온도", "덥나", "춥나")) && !has("곳", "쉼터", "어디")) {
    if (!weather.live) return { text: "지금 날씨를 받아오지 못했어요. 잠시 뒤에 다시 물어봐 주세요.", places: [] };
    const alert = weather.alert ? ` <b>${weather.alert}</b>가 내려져 있어요.` : "";
    const skyText = sky?.text ? ` <b>${sky.text}</b>.` : askSky ? " 하늘 상태는 아직 받아오지 못했어요." : "";
    const tip = sky?.hint || (mode === "cooling" ? "물을 자주 마시고 그늘에서 쉬세요." : "따뜻하게 입고 실내에서 쉬세요.");
    return { text: `지금 바깥은 <b>${weather.outdoor.toFixed(0)}°C</b>예요.${skyText}${alert}\n${tip}`, places: [] };
  }

  if (!analyses.length) {
    return { text: "주변 쉼터를 아직 찾지 못했어요. 잠시 뒤에 다시 물어봐 주세요.", places: [] };
  }

  // 장소 이름을 콕 집어 물은 경우 — "○○도서관 몇 시까지야?"
  const byName = analyses
    .filter((a) => {
      const n = a.place.name.replace(/\s+/g, "").toLowerCase();
      return n.length >= 2 && q.includes(n);
    })
    .sort((x, y) => y.place.name.length - x.place.name.length)[0];
  if (byName) {
    return {
      text:
        `${named(byName.place.name)}.\n${walkLine(byName)} 거리예요. ${openLine(byName, now)}.\n` +
        `운영 시간은 ${hoursLabel(byName.place)}이에요.`,
      places: [byName],
    };
  }

  let pool = analyses;
  const notes: string[] = [];

  // 시설 종류
  const cat = CATEGORY_WORDS.find(([words]) => has(...words));
  if (cat) {
    const found = pool.filter((a) => a.place.category === cat[1]);
    const label = cat[0][0];
    if (!found.length) {
      const near = nearestFirst(pool);
      return {
        text: `주변에 ${iGa(label)} 없어요.\n대신 가장 가까운 쉼터는 ${named(near[0].place.name)}.`,
        places: near.slice(0, 3),
      };
    }
    pool = found;
  }

  // 조건 (여러 개를 함께 쓸 수 있다)
  if (has("밤", "늦게", "야간", "새벽", "24시간", "심야")) {
    const late = pool.filter(openLate);
    if (!late.length) {
      const near = nearestFirst(pool);
      return {
        text: `밤 10시 넘어서까지 여는 쉼터가 주변에 없어요.\n가장 가까운 곳은 ${named(near[0].place.name)}. ${openLine(near[0], now)}.`,
        places: near.slice(0, 3),
      };
    }
    pool = late;
    notes.push("late");
  }
  if (has("열려", "열린", "지금열", "문연", "문열", "영업중", "운영중")) {
    const open = pool.filter((a) => a.openNow);
    if (!open.length) {
      const near = nearestFirst(pool);
      return {
        text: `지금 열려 있는 쉼터가 주변에 없어요.\n가장 가까운 ${named(near[0].place.name)}. ${openLine(near[0], now)}.`,
        places: near.slice(0, 3),
      };
    }
    pool = open;
    notes.push("open");
  }
  if (has("공식", "무료", "공짜", "돈안", "돈없")) {
    const official = pool.filter((a) => a.place.official);
    if (official.length) pool = official;
    notes.push("official");
  }

  // 무엇을 기준으로 고를지
  const warmWords = has("따뜻", "따듯", "난방", "히터", "덜추운");
  const coolWords = has("시원", "에어컨", "냉방");
  let kind: "near" | "long" | "quiet" | "temp" = "near";
  let ordered: Analysis[];
  if (has("오래", "눈치", "편하게", "종일", "하루", "부담")) {
    kind = "long";
    ordered = byOpenThen(pool, (a) => a.nuisance.score);
  } else if (has("조용", "공부", "책읽", "집중")) {
    kind = "quiet";
    ordered = byOpenThen(pool, (a) => -a.place.quiet);
  } else if (coolWords || warmWords) {
    kind = "temp";
    const warm = warmWords || (!coolWords && mode === "heating");
    ordered = byOpenThen(pool, (a) => (warm ? -a.indoor : a.indoor));
  } else {
    ordered = nearestFirst(pool);
  }

  const best = ordered[0];
  const understood =
    kind !== "near" || cat || notes.length || has("가까", "근처", "주변", "어디", "쉼터", "잠깐", "잠시", "가야", "갈곳", "갈만");
  const lines: string[] = [];
  if (!understood) lines.push("질문을 잘 알아듣지 못했어요. 가까운 쉼터를 알려 드릴게요.");

  const what = cat ? cat[0][0] : SHELTER_WORD[mode];
  if (!best.openNow) lines.push("지금 열려 있는 곳이 없어서, 문 닫은 곳 중에서 골랐어요.");
  if (kind === "long") {
    lines.push(`오래 머물러도 눈치가 덜 보이는 곳은 ${named(best.place.name)}.`, `${stayLine(best)}. ${walkLine(best)}이에요.`);
  } else if (kind === "quiet") {
    lines.push(`조용히 쉬기 좋은 곳은 ${named(best.place.name)} (${categoryLabel(best.place)}).`, `${walkLine(best)}이에요.`);
  } else if (kind === "temp") {
    const warm = warmWords || (!coolWords && mode === "heating");
    const cmp = tempCompare(best);
    lines.push(
      `가장 ${warm ? "따뜻한" : "시원한"} 곳은 ${named(best.place.name)}.`,
      `실내 약 ${Math.round(best.indoor)}°C${cmp ? `로 ${cmp}` : "예요"}. ${walkLine(best)}이에요.`,
    );
  } else if (notes.includes("late")) {
    const until = best.place.alwaysOpen ? "24시간 열려 있어요" : `${hourWord(best.place.openTo)}까지 열어요`;
    lines.push(`밤늦게까지 여는 곳은 ${named(best.place.name)}.`, `${until}. ${walkLine(best)}이에요.`);
  } else if (notes.includes("open")) {
    lines.push(
      `지금 열려 있는 ${iGa(what)} ${pool.length}곳 있어요.`,
      `가장 가까운 곳은 ${named(best.place.name)}. ${walkLine(best)}, ${openLine(best, now)}.`,
    );
  } else {
    const prefix = notes.includes("official") ? "공식 쉼터 중 " : "";
    lines.push(
      `${prefix}가장 가까운 ${eunNeun(what)} ${named(best.place.name)}.`,
      `${walkLine(best)} 거리예요. ${openLine(best, now)}.`,
    );
  }
  if (ordered.length > 1) lines.push("다른 곳도 아래에 함께 보여 드릴게요.");
  return { text: lines.join("\n"), places: ordered.slice(0, 3) };
}

export function greeting(mode: Mode, weather: Weather, sky?: Sky): ChatReply {
  const outdoor = weather.live
    ? `지금 바깥은 <b>${weather.outdoor.toFixed(0)}°C</b>예요${weather.alert ? ` (${weather.alert})` : ""}.${sky?.text ? ` ${sky.text}.` : ""}\n`
    : "";
  return {
    text: `안녕하세요! ${outdoor}${SHELTER_WORD[mode]}에 대해 궁금한 걸 물어보세요.\n아래 질문을 눌러도 돼요.`,
    places: [],
  };
}
