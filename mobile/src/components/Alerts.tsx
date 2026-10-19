// 재난문자 — 내 시군구의 최근 24시간 행정안전부 재난문자 (supabase/functions/alerts).
// 홈 날씨 아래에 가장 최근 한 건을 보이고, '더 보기' 로 나머지를 펼친다. coolmap/ui/home.py AlertCard 와 같다.

import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import type { DisasterAlert } from "../backend";
import { alertHead, alertUrgent } from "../plain";
import type { Palette } from "../theme";
import { Icon, T } from "./ui";

export function AlertCard({ alerts, p }: { alerts: DisasterAlert[]; p: Palette }) {
  const [open, setOpen] = useState(false);
  if (!alerts.length) return null;
  const shown = open ? alerts : alerts.slice(0, 1);
  const color = alertUrgent(alerts[0].step) ? p.bad : p.warn;
  return (
    <View style={[styles.card, { backgroundColor: p.card, borderColor: color }]}>
      <View style={styles.head}>
        <Icon name="message-alert-outline" size={24} color={color} />
        <T size={18} weight="800" color={p.text} style={styles.fill}>
          재난문자
        </T>
      </View>
      {shown.map((a, i) => (
        <View key={a.sn} style={[styles.item, i > 0 && { borderTopColor: p.border, borderTopWidth: 1, paddingTop: 10 }]}>
          <T size={14} weight="700" color={alertUrgent(a.step) ? p.bad : p.textDim}>
            {alertHead(a)}
          </T>
          <T size={16} color={p.text} numberOfLines={open ? undefined : 4}>
            {a.text}
          </T>
        </View>
      ))}
      {(alerts.length > 1 || !open) && (
        <Pressable onPress={() => setOpen(!open)} hitSlop={8} style={styles.more}>
          <T size={15} weight="800" color={p.accent}>
            {open ? "접기" : alerts.length > 1 ? `더 보기 (${alerts.length}건)` : "전체 보기"}
          </T>
          <Icon name={open ? "chevron-up" : "chevron-down"} size={20} color={p.accent} />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  card: { borderWidth: 2, borderRadius: 20, padding: 16, gap: 10, marginTop: 12 },
  head: { flexDirection: "row", alignItems: "center", gap: 8 },
  item: { gap: 4 },
  more: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", paddingVertical: 2 },
});
