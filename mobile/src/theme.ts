// 냉방·난방 테마. coolmap/theme.py 의 팔레트에서 모바일에 필요한 색만 가져왔다.

export type Mode = "cooling" | "heating";

export type Palette = {
  accent: string;
  accentBright: string;
  accentInk: string;
  bg: string;
  card: string;
  border: string;
  text: string;
  textDim: string;
  textMute: string;
  good: string;
  warn: string;
  bad: string;
};

export const PALETTES: Record<Mode, Palette> = {
  cooling: {
    accent: "#22D3EE",
    accentBright: "#7DE9F8",
    accentInk: "#032630",
    bg: "#070C14",
    card: "#111A28",
    border: "#1E2A3D",
    text: "#E9F2F9",
    textDim: "#9FB3C8",
    textMute: "#63788E",
    good: "#34D399",
    warn: "#FBBF24",
    bad: "#F87171",
  },
  heating: {
    accent: "#FF7043",
    accentBright: "#FFA981",
    accentInk: "#2C0B03",
    bg: "#100708",
    card: "#211112",
    border: "#3B2225",
    text: "#FCEEE9",
    textDim: "#D2AEA4",
    textMute: "#9A736B",
    good: "#7BC96F",
    warn: "#F7C948",
    bad: "#FF6B6B",
  },
};

export const MODE_LABEL: Record<Mode, string> = { cooling: "냉방", heating: "난방" };

/** 폭염이 아닌 달(10~4월)은 난방 모드로 시작한다 */
export function defaultMode(now = new Date()): Mode {
  const m = now.getMonth() + 1;
  return m >= 5 && m <= 9 ? "cooling" : "heating";
}
