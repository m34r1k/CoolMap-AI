// 공용 컴포넌트. coolmap/ui/common.py 의 Pill · MeterBar · Card · GaugeArc 에 해당한다.

import { MaterialCommunityIcons } from "@expo/vector-icons";
import type { ComponentProps, ReactNode } from "react";
import { Image, Pressable, StyleSheet, Text, type TextStyle, View, type ViewStyle } from "react-native";
import Svg, { Path } from "react-native-svg";

import type { Palette } from "../theme";

export type IconName = ComponentProps<typeof MaterialCommunityIcons>["name"];

export function Icon({ name, size = 18, color }: { name: string; size?: number; color: string }) {
  return <MaterialCommunityIcons name={name as IconName} size={size} color={color} />;
}

export function Card({ p, children, style }: { p: Palette; children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, { backgroundColor: p.card, borderColor: p.border }, style]}>{children}</View>;
}

export function Pill({
  text,
  icon,
  color,
  bg,
  border,
}: {
  text: string;
  icon?: string;
  color: string;
  bg: string;
  border?: string;
}) {
  return (
    <View style={[styles.pill, { backgroundColor: bg, borderColor: border ?? bg }]}>
      {icon && <Icon name={icon} size={12} color={color} />}
      <Text style={[styles.pillText, { color }]}>{text}</Text>
    </View>
  );
}

export function MeterBar({ value, color, track, height = 6 }: { value: number; color: string; track: string; height?: number }) {
  return (
    <View style={{ height, borderRadius: height / 2, backgroundColor: track, overflow: "hidden" }}>
      <View style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, height, backgroundColor: color }} />
    </View>
  );
}

export function SectionTitle({ p, text, icon, right }: { p: Palette; text: string; icon?: string; right?: ReactNode }) {
  return (
    <View style={styles.section}>
      {icon && <Icon name={icon} size={20} color={p.accent} />}
      <Text style={[styles.sectionText, { color: p.text }]}>{text}</Text>
      <View style={{ flex: 1 }} />
      {right}
    </View>
  );
}

/** <b>굵게</b> 와 \n 만 해석한다 (assistant.ts 의 답변 형식) */
export function RichText({ text, style, boldColor }: { text: string; style: TextStyle; boldColor: string }) {
  const parts = text.split(/(<b>.*?<\/b>)/g).filter(Boolean);
  return (
    <Text style={style}>
      {parts.map((part, i) =>
        part.startsWith("<b>") ? (
          <Text key={i} style={{ fontWeight: "700", color: boldColor }}>
            {part.slice(3, -4)}
          </Text>
        ) : (
          part
        ),
      )}
    </Text>
  );
}

/** 민폐도 게이지 (반원 아크) */
export function Gauge({
  value,
  label,
  color,
  track,
  textColor,
  muteColor,
  size = 150,
}: {
  value: number;
  label: string;
  color: string;
  track: string;
  textColor: string;
  muteColor: string;
  size?: number;
}) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  // 225° → -45° 로 도는 270° 아크
  const arc = (from: number, to: number) => {
    const rad = (d: number) => (d * Math.PI) / 180;
    const x1 = cx + r * Math.cos(rad(from));
    const y1 = cy - r * Math.sin(rad(from));
    const x2 = cx + r * Math.cos(rad(to));
    const y2 = cy - r * Math.sin(rad(to));
    const large = Math.abs(from - to) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  };
  const v = Math.max(0.001, Math.min(1, value / 100));
  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Path d={arc(225, -45)} stroke={track} strokeWidth={stroke} strokeLinecap="round" fill="none" />
        <Path d={arc(225, 225 - 270 * v)} stroke={color} strokeWidth={stroke} strokeLinecap="round" fill="none" />
      </Svg>
      <Text style={{ color: textColor, fontSize: 38, fontWeight: "800" }}>{value}</Text>
      <Text style={{ color, fontSize: 13, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: muteColor, fontSize: 10, marginTop: 2 }}>0=편함 · 100=눈치</Text>
    </View>
  );
}

export function IconButton({ icon, onPress, p, active }: { icon: string; onPress: () => void; p: Palette; active?: boolean }) {
  return (
    <Pressable onPress={onPress} hitSlop={8} style={[styles.iconBtn, { backgroundColor: p.card, borderColor: p.border }]}>
      <Icon name={icon} size={20} color={active ? p.accent : p.text} />
    </Pressable>
  );
}

/** 앱 로고 (designs/logo.png 의 핀 + 글자) */
export function Logo({ p, subtitle = true }: { p: Palette; subtitle?: boolean }) {
  return (
    <View style={styles.logoRow}>
      <Image source={require("../../assets/logo-pin.png")} style={styles.logoPin} resizeMode="contain" />
      <View>
        <Text style={styles.logoText}>
          <Text style={{ color: "#3A8DDE" }}>Cool</Text>
          <Text style={{ color: "#E0473C" }}>Map</Text>
          <Text style={{ color: p.accent }}> AI</Text>
        </Text>
        {subtitle && <Text style={[styles.logoSub, { color: p.textMute }]}>CLIMATE CONTROL CENTER</Text>}
      </View>
    </View>
  );
}

export const styles = StyleSheet.create({
  card: { borderRadius: 18, borderWidth: 1, padding: 16 },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  pillText: { fontSize: 11, fontWeight: "700" },
  section: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 22, marginBottom: 12 },
  sectionText: { fontSize: 20, fontWeight: "800" },
  iconBtn: {
    width: 42,
    height: 42,
    borderRadius: 21,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  logoRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  logoPin: { width: 34, height: 44 },
  logoText: { fontSize: 22, fontWeight: "800" },
  logoSub: { fontSize: 9, fontWeight: "700", letterSpacing: 1.5, marginTop: 1 },
});
