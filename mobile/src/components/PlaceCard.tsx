// 추천 목록 · 즐겨찾기 카드 (coolmap/ui/placecard.py) 와 지도 목록 한 줄 (mapview.py PlaceRow).

import { Pressable, StyleSheet, Text, View } from "react-native";

import { type Analysis, analysisDistance, stayLabel } from "../analysis";
import { categoryIcon, categoryLabel } from "../places";
import { nuisanceColor, type Palette } from "../theme";
import { Icon, MeterBar, Pill } from "./ui";

export function PlaceCard({
  a,
  p,
  favorite,
  onOpen,
  onFavorite,
}: {
  a: Analysis;
  p: Palette;
  favorite: boolean;
  onOpen: () => void;
  onFavorite: () => void;
}) {
  const nc = nuisanceColor(p, a.nuisance.key);
  return (
    <Pressable onPress={onOpen} style={[styles.card, { backgroundColor: p.card, borderColor: p.border }]}>
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.name, { color: p.text }]} numberOfLines={2}>
            {a.place.name}
          </Text>
          <View style={styles.meta}>
            <Icon name="walk" size={13} color={p.textMute} />
            <Text style={[styles.metaText, { color: p.textMute }]}>
              {analysisDistance(a)} ({a.walkMin}분) · {categoryLabel(a.place)}
            </Text>
          </View>
        </View>
        <View style={[styles.catIcon, { backgroundColor: p.cardAlt }]}>
          <Icon name={categoryIcon(a.place)} size={20} color={p.accent} />
        </View>
      </View>

      {(a.place.aiGuess || a.place.official) && (
        <View style={styles.pills}>
          {a.place.official && <Pill text="공식 지정 쉼터" icon="check-circle" color={p.good} bg={p.cardAlt} />}
          {a.place.aiGuess && (
            <Pill text={`AI 추정 ${a.place.aiConfidence}% · 공식 쉼터 아님`} icon="creation" color={p.warn} bg={p.cardAlt} />
          )}
        </View>
      )}

      <View style={[styles.inner, { backgroundColor: p.cardAlt, borderColor: p.border }]}>
        <View style={[styles.tempBox, { backgroundColor: a.crowd.openNow ? p.accentSoft : p.card }]}>
          <Text style={[styles.temp, { color: a.crowd.openNow ? p.accent : p.textMute }]}>
            {a.crowd.openNow ? `${Math.round(a.indoor)}°C` : "—"}
          </Text>
          <Text style={[styles.tempLabel, { color: p.textMute }]}>{a.crowd.openNow ? "실내" : "운영종료"}</Text>
        </View>
        <View style={{ flex: 1, gap: 6 }}>
          <View style={styles.scoreRow}>
            <Text style={[styles.scoreLabel, { color: p.textDim }]}>쾌적 점수</Text>
            <Text style={[styles.score, { color: p.accent }]}>{a.comfort}/100</Text>
          </View>
          <MeterBar value={a.comfort / 100} color={p.accent} track={p.card} />
          <View style={styles.chips}>
            <Pill text="혼잡도 준비 중" color={p.textMute} bg={p.card} border={p.border} />
            <Pill text={`민폐도 ${a.nuisance.score}`} color={nc} bg={p.card} border={p.border} />
          </View>
        </View>
      </View>

      <View style={styles.foot}>
        <Icon name="star" size={16} color="#FBBF24" />
        <Text style={[styles.footText, { color: p.textDim }]} numberOfLines={1}>
          {a.nuisance.level} · 권장 체류 {stayLabel(a.nuisance.stayMinutes)}
        </Text>
        <Pressable onPress={onFavorite} hitSlop={10}>
          <Icon name={favorite ? "heart" : "heart-outline"} size={20} color={favorite ? p.accent : p.textDim} />
        </Pressable>
        <View style={[styles.arrow, { backgroundColor: p.cardAlt }]}>
          <Icon name="arrow-right" size={16} color={p.text} />
        </View>
      </View>
    </Pressable>
  );
}

export function PlaceRow({ a, p, selected, onPress }: { a: Analysis; p: Palette; selected: boolean; onPress: () => void }) {
  const temp = a.crowd.openNow ? `실내 ${Math.round(a.indoor)}°C` : "운영 종료";
  return (
    <Pressable
      onPress={onPress}
      style={[styles.row, { borderColor: p.border, backgroundColor: selected ? p.accentSoft : "transparent" }]}
    >
      <View style={[styles.rowIcon, { backgroundColor: p.cardAlt, borderStyle: a.place.aiGuess ? "dashed" : "solid", borderColor: a.place.aiGuess ? p.warn : p.cardAlt }]}>
        <Icon name={categoryIcon(a.place)} size={16} color={a.crowd.openNow ? p.accent : p.textMute} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowName, { color: p.text }]} numberOfLines={1}>
          {a.place.name}
        </Text>
        <Text style={[styles.rowMeta, { color: p.textMute }]} numberOfLines={1}>
          {a.place.aiGuess ? "AI 추정 · " : ""}
          {temp} · 도보 {a.walkMin}분 · {analysisDistance(a)}
        </Text>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <Text style={[styles.rowScore, { color: p.accent }]}>쾌적 {a.comfort}</Text>
        <Text style={[styles.rowNuis, { color: nuisanceColor(p, a.nuisance.key) }]}>민폐 {a.nuisance.score}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 18, borderWidth: 1, padding: 16, gap: 12 },
  head: { flexDirection: "row", gap: 12 },
  name: { fontSize: 17, fontWeight: "800" },
  meta: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  metaText: { fontSize: 12, fontWeight: "600" },
  catIcon: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  inner: { flexDirection: "row", gap: 12, borderRadius: 14, borderWidth: 1, padding: 12, alignItems: "center" },
  tempBox: { borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, alignItems: "center", minWidth: 64 },
  temp: { fontSize: 22, fontWeight: "800" },
  tempLabel: { fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  scoreRow: { flexDirection: "row", justifyContent: "space-between" },
  scoreLabel: { fontSize: 12, fontWeight: "700" },
  score: { fontSize: 12, fontWeight: "800" },
  chips: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  foot: { flexDirection: "row", alignItems: "center", gap: 8 },
  footText: { flex: 1, fontSize: 13, fontWeight: "600" },
  arrow: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 10,
    paddingHorizontal: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderRadius: 10,
  },
  rowIcon: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center", borderWidth: 1.5 },
  rowName: { fontSize: 15, fontWeight: "700" },
  rowMeta: { fontSize: 12, marginTop: 2 },
  rowScore: { fontSize: 13, fontWeight: "800" },
  rowNuis: { fontSize: 12, fontWeight: "700", marginTop: 2 },
});
