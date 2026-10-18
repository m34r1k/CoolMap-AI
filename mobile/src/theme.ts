// 냉방·난방 × 라이트·다크 테마. coolmap/theme.py 의 팔레트와 같은 값이다.
// 기본은 라이트, 다크는 설정에서 켠다.

export type Mode = "cooling" | "heating";

export type Palette = {
  key: Mode;
  dark: boolean;
  label: string;
  tagline: string;
  accent: string;
  accentBright: string;
  accentDeep: string;
  accentInk: string;
  accentSoft: string;
  bg: string;
  panel: string;
  card: string;
  cardAlt: string;
  hover: string;
  border: string;
  borderSoft: string;
  text: string;
  textDim: string;
  textMute: string;
  good: string;
  warn: string;
  bad: string;
};

const DARK_PALETTES: Record<Mode, Palette> = {
  cooling: {
    key: "cooling",
    dark: true,
    label: "냉방 모드",
    tagline: "폭염 대응 · 시원한 쉼터를 찾습니다",
    accent: "#22D3EE",
    accentBright: "#7DE9F8",
    accentDeep: "#0E7490",
    accentInk: "#032630",
    accentSoft: "#123243",
    bg: "#070C14",
    panel: "#0B111C",
    card: "#111A28",
    cardAlt: "#16202F",
    hover: "#1A2637",
    border: "#1E2A3D",
    borderSoft: "#152030",
    text: "#E9F2F9",
    textDim: "#9FB3C8",
    textMute: "#63788E",
    good: "#34D399",
    warn: "#FBBF24",
    bad: "#F87171",
  },
  heating: {
    key: "heating",
    dark: true,
    label: "난방 모드",
    tagline: "한파 대응 · 따뜻한 쉼터를 찾습니다",
    accent: "#FF7043",
    accentBright: "#FFA981",
    accentDeep: "#B2401C",
    accentInk: "#2C0B03",
    accentSoft: "#3D1B12",
    bg: "#100708",
    panel: "#170B0C",
    card: "#211112",
    cardAlt: "#2A1719",
    hover: "#331D1E",
    border: "#3B2225",
    borderSoft: "#2C1719",
    text: "#FCEEE9",
    textDim: "#D2AEA4",
    textMute: "#9A736B",
    good: "#7BC96F",
    warn: "#F7C948",
    bad: "#FF6B6B",
  },
};

const LIGHT_PALETTES: Record<Mode, Palette> = {
  cooling: {
    key: "cooling",
    dark: false,
    label: "냉방 모드",
    tagline: "폭염 대응 · 시원한 쉼터를 찾습니다",
    accent: "#0284C7",
    accentBright: "#0EA5E9",
    accentDeep: "#075985",
    accentInk: "#FFFFFF",
    accentSoft: "#E0F2FE",
    bg: "#F3F6F9",
    panel: "#FFFFFF",
    card: "#FFFFFF",
    cardAlt: "#EEF3F8",
    hover: "#E4ECF4",
    border: "#CFDAE5",
    borderSoft: "#E1E8EF",
    text: "#0F1B2A",
    textDim: "#45576B",
    textMute: "#76889B",
    good: "#047857",
    warn: "#B45309",
    bad: "#DC2626",
  },
  heating: {
    key: "heating",
    dark: false,
    label: "난방 모드",
    tagline: "한파 대응 · 따뜻한 쉼터를 찾습니다",
    accent: "#DC4A16",
    accentBright: "#F2672F",
    accentDeep: "#9A3412",
    accentInk: "#FFFFFF",
    accentSoft: "#FDEBE3",
    bg: "#FAF6F4",
    panel: "#FFFFFF",
    card: "#FFFFFF",
    cardAlt: "#F6EFEC",
    hover: "#F0E5E1",
    border: "#E6D5CF",
    borderSoft: "#EFE5E1",
    text: "#2A1512",
    textDim: "#6B4D46",
    textMute: "#9A7E76",
    good: "#3F7F2F",
    warn: "#B45309",
    bad: "#D12F2F",
  },
};

export function paletteFor(mode: Mode, dark: boolean): Palette {
  return (dark ? DARK_PALETTES : LIGHT_PALETTES)[mode];
}

export const MODE_LABEL: Record<Mode, string> = { cooling: "냉방", heating: "난방" };

/** 폭염이 아닌 달(10~4월)은 난방 모드로 시작한다 */
export function defaultMode(now = new Date()): Mode {
  const m = now.getMonth() + 1;
  return m >= 5 && m <= 9 ? "cooling" : "heating";
}

// ai.py 의 NUISANCE_LEVELS 키 → 색 (common.py NUISANCE_COLOR_KEYS)
export function nuisanceColor(p: Palette, key: string): string {
  if (key === "very_low" || key === "low") return p.good;
  if (key === "normal" || key === "high") return p.warn;
  return p.bad;
}
