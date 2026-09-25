// 장소 상세 화면 — coolmap/ui/detail.py
// 온도 3종 · AI 쾌적 점수 · 혼잡도(준비 중) · 민폐도 지수 · 편의시설 · 추천 이유

import { LinearGradient } from "expo-linear-gradient";
import { router, useLocalSearchParams } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { analysisDistance, stayLabel } from "../../analysis";
import { Card, Gauge, Icon, IconButton, MeterBar, Pill } from "../../components/ui";
import { openDirections } from "../../directions";
import { categoryIcon, categoryLabel, hoursLabel } from "../../places";
import { useStore } from "../../store";
import { nuisanceColor, PALETTES } from "../../theme";

export default function Detail() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStore();
  const place = s.getPlace(String(id));

  if (!place) {
    return (
      <View style={[styles.fill, styles.center, { backgroundColor: s.p.bg }]}>
        <Text style={{ color: s.p.textDim }}>장소를 찾을 수 없습니다.</Text>
      </View>
    );
  }

  // 즐겨찾기로 들어오면 현재 모드와 다른 쉼터일 수 있다 — 장소 자신의 모드로 보여 준다
  const p = PALETTES[place.mode];
  const a = s.analyzePlace(place);
  const nc = nuisanceColor(p, a.nuisance.key);
  const fav = s.isFavorite(place.id);

  return (
    <View style={[styles.fill, { backgroundColor: p.bg }]}>
      <ScrollView contentContainerStyle={{ paddingBottom: 110 + insets.bottom }}>
        {/* 히어로 */}
        <LinearGradient colors={[p.accentDeep, p.bg]} style={[styles.hero, { paddingTop: insets.top }]}>
          <View style={styles.heroIcon}>
            <Icon name={categoryIcon(place)} size={96} color={p.accent} />
          </View>
          <View style={[styles.heroBar, { top: insets.top + 10 }]}>
            <IconButton icon="arrow-left" p={p} onPress={() => router.back()} />
            <View style={{ flex: 1 }} />
            <IconButton icon={fav ? "heart" : "heart-outline"} p={p} active={fav} onPress={() => s.toggleFavorite(place)} />
            <IconButton
              icon="map-outline"
              p={p}
              onPress={() => router.navigate({ pathname: "/map", params: { focus: place.id } })}
            />
          </View>
        </LinearGradient>

        <View style={styles.body}>
          <View style={styles.pills}>
            <Pill text={categoryLabel(place)} icon={categoryIcon(place)} color={p.accent} bg={p.card} />
            <Pill text={`${analysisDistance(a)} · 도보 ${a.walkMin}분`} icon="walk" color={p.textDim} bg={p.bg} border={p.border} />
            {place.official && <Pill text="공식 지정 쉼터" icon="check-circle" color={p.good} bg={p.card} />}
            {/* 공식 지정이 아니라는 점을 가장 먼저 보이게 한다 */}
            {place.aiGuess && (
              <Pill text={`AI 추정 ${place.aiConfidence}% · 공식 쉼터 아님`} icon="creation" color={p.warn} bg={p.card} />
            )}
          </View>

          <Text style={[styles.h1, { color: p.text }]}>{place.name}</Text>
          <Text style={[styles.bodyText, { color: p.textDim }]}>{place.summary}</Text>
          <Text style={[styles.mono, { color: p.textMute }]}>
            {place.address ? `${place.address}  ·  ` : ""}지도에서 건물 전체가 하이라이트됩니다
          </Text>

          {/* 온도 3종 */}
          <Card p={p} style={styles.temps}>
            <Stat label="OUTDOOR" value={a.weather.live ? a.weather.outdoor.toFixed(0) : "—"} color={place.mode === "cooling" ? p.bad : p.accentBright} p={p} />
            <Stat label="INDOOR" value={a.indoor.toFixed(1)} color={p.accent} p={p} highlight />
            <Stat label="FEELS LIKE" value={a.feelsInside.toFixed(1)} color={p.text} p={p} />
          </Card>

          {/* 지표 */}
          <Card p={p} style={{ gap: 8 }}>
            <View style={styles.row}>
              <Icon name="creation" size={16} color={p.accent} />
              <Text style={[styles.label, { color: p.textDim }]}>AI 쾌적 점수</Text>
            </View>
            <Text style={[styles.big, { color: p.accent }]}>
              {a.comfort}
              <Text style={[styles.max, { color: p.textMute }]}>/100</Text>
            </Text>
            <MeterBar value={a.comfort / 100} color={p.accent} track={p.cardAlt} height={7} />
          </Card>
          <View style={styles.metrics}>
            <Mini icon="water-outline" label="HUMIDITY" value={`${place.humidity}%`} p={p} />
            <Mini icon="weather-windy" label="AIRFLOW" value={place.airflow} p={p} />
          </View>

          {/* 혼잡도 — 실시간 인구 데이터 연동 전 */}
          <Card p={p} style={{ gap: 10 }}>
            <View style={styles.row}>
              <Icon name="account-group" size={18} color={p.textMute} />
              <Text style={[styles.cardTitle, { color: p.text }]}>AI 혼잡도 예측</Text>
              <View style={styles.fill} />
              <Pill text="COMING SOON" icon="clock-outline" color={p.warn} bg={p.cardAlt} />
            </View>
            <Text style={[styles.level, { color: p.textMute }]}>준비 중</Text>
            <Text style={[styles.mono, { color: p.textMute }]}>실시간 인구 데이터 연동 후 제공됩니다</Text>
          </Card>

          {/* 민폐도 */}
          <Card p={p} style={{ gap: 12 }}>
            <View style={styles.row}>
              <Icon name="star" size={18} color={p.accent} />
              <Text style={[styles.cardTitle, { color: p.text }]}>민폐도 지수</Text>
              <View style={styles.fill} />
              <Pill text={`권장 체류 ${stayLabel(a.nuisance.stayMinutes)}`} icon="clock-outline" color={p.accent} bg={p.cardAlt} />
            </View>
            <View style={{ alignItems: "center" }}>
              <Gauge
                value={a.nuisance.score}
                label={a.nuisance.level}
                color={nc}
                track={p.cardAlt}
                textColor={p.text}
                muteColor={p.textMute}
                size={170}
              />
            </View>
            <Text style={[styles.bodyText, { color: p.textDim }]}>
              이 장소에 오래 머물 때 느껴지는 부담은 <Text style={{ fontWeight: "800", color: p.text }}>{a.nuisance.level}</Text>{" "}
              수준입니다. 권장 체류 시간은{" "}
              <Text style={{ fontWeight: "800", color: p.text }}>{stayLabel(a.nuisance.stayMinutes)}</Text>입니다.
              {a.nuisance.reason ? `\n${a.nuisance.reason}` : ""}
            </Text>
            {a.nuisance.source !== "gemini" &&
              a.nuisance.factors.map(([name, value]) => (
                <View key={name} style={styles.factor}>
                  <Text style={[styles.factorName, { color: p.textMute }]}>{name}</Text>
                  <View style={styles.fill}>
                    <MeterBar value={Math.min(1, Math.abs(value) / 40)} color={value < 0 ? p.good : nc} track={p.cardAlt} />
                  </View>
                  <Text style={[styles.factorValue, { color: value < 0 ? p.good : nc }]}>
                    {value > 0 ? `+${value}` : value}
                  </Text>
                </View>
              ))}
            <Text style={[styles.tips, { color: p.textDim }]}>{a.nuisance.tips.map((t) => `· ${t}`).join("\n")}</Text>
            <Text style={[styles.mono, { color: p.textMute }]}>
              {a.nuisance.source === "gemini" ? "Gemini 추정치 (측정값 아님)" : "규칙 기반 추정치 — AI 결과를 받는 중이거나 받지 못했습니다"}
            </Text>
          </Card>

          {/* 편의시설 */}
          <Card p={p} style={{ gap: 10 }}>
            <Text style={[styles.cardTitle, { color: p.text }]}>편의시설 · 운영</Text>
            <Text style={[styles.mono, { color: p.textDim }]}>운영 시간 {hoursLabel(place)}</Text>
            <View style={styles.tags}>
              {place.amenities.map((t) => (
                <View key={t} style={[styles.tag, { backgroundColor: p.cardAlt, borderColor: p.border }]}>
                  <Text style={[styles.tagText, { color: p.textDim }]}>{t}</Text>
                </View>
              ))}
            </View>
          </Card>

          {/* 추천 이유 */}
          <Card p={p} style={{ gap: 10 }}>
            <View style={styles.row}>
              <Icon name="lightbulb-on-outline" size={18} color={p.accent} />
              <Text style={[styles.cardTitle, { color: p.text }]}>CoolMap이 이곳을 추천하는 이유</Text>
            </View>
            <Text style={[styles.bodyText, { color: p.textDim }]}>
              {place.why}
              {a.weather.live
                ? ` 현재 외기 ${a.weather.outdoor.toFixed(0)}°C 대비 실내는 ${a.indoor.toFixed(1)}°C로 약 ${a.delta.toFixed(1)}°C 차이가 납니다.`
                : ""}
            </Text>
          </Card>
        </View>
      </ScrollView>

      {/* 하단 액션 바 */}
      <View style={[styles.bar, { paddingBottom: insets.bottom + 12, backgroundColor: p.panel, borderColor: p.border }]}>
        <Pressable onPress={() => openDirections(place)} style={[styles.primary, { backgroundColor: p.accent }]}>
          <Icon name="walk" size={20} color={p.accentInk} />
          <Text style={[styles.primaryText, { color: p.accentInk }]}>길찾기</Text>
        </Pressable>
        <Pressable
          onPress={() => router.navigate({ pathname: "/map", params: { focus: place.id } })}
          style={[styles.secondary, { borderColor: p.border, backgroundColor: p.card }]}
        >
          <Icon name="map-outline" size={20} color={p.text} />
        </Pressable>
      </View>
    </View>
  );
}

function Stat({ label, value, color, p, highlight }: { label: string; value: string; color: string; p: typeof PALETTES.cooling; highlight?: boolean }) {
  return (
    <View style={[styles.stat, { backgroundColor: highlight ? p.accentSoft : p.bg }]}>
      <Text style={[styles.statLabel, { color: highlight ? p.accent : p.textDim }]}>{label}</Text>
      <Text style={[styles.statValue, { color }]}>
        {value}
        <Text style={styles.statUnit}>°C</Text>
      </Text>
    </View>
  );
}

function Mini({ icon, label, value, p }: { icon: string; label: string; value: string; p: typeof PALETTES.cooling }) {
  return (
    <Card p={p} style={{ flex: 1, gap: 8 }}>
      <View style={styles.row}>
        <Icon name={icon} size={16} color={p.textDim} />
        <Text style={[styles.label, { color: p.textDim }]}>{label}</Text>
      </View>
      <Text style={[styles.miniValue, { color: p.text }]}>{value}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  hero: { height: 230, justifyContent: "center", alignItems: "center" },
  heroIcon: { opacity: 0.9 },
  heroBar: { position: "absolute", left: 16, right: 16, flexDirection: "row", gap: 10 },
  body: { paddingHorizontal: 16, gap: 14, marginTop: -10 },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  h1: { fontSize: 26, fontWeight: "800" },
  bodyText: { fontSize: 14, lineHeight: 21 },
  mono: { fontSize: 11, fontWeight: "600", letterSpacing: 0.4 },
  temps: { flexDirection: "row", gap: 8, padding: 8 },
  stat: { flex: 1, borderRadius: 12, paddingVertical: 12, alignItems: "center", gap: 4 },
  statLabel: { fontSize: 10, fontWeight: "700", letterSpacing: 1.2 },
  statValue: { fontSize: 22, fontWeight: "800" },
  statUnit: { fontSize: 11, fontWeight: "600" },
  label: { fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  big: { fontSize: 42, fontWeight: "800" },
  max: { fontSize: 14, fontWeight: "600" },
  metrics: { flexDirection: "row", gap: 12 },
  miniValue: { fontSize: 22, fontWeight: "800" },
  cardTitle: { fontSize: 16, fontWeight: "800", flexShrink: 1 },
  level: { fontSize: 24, fontWeight: "800" },
  factor: { flexDirection: "row", alignItems: "center", gap: 10 },
  factorName: { width: 110, fontSize: 11 },
  factorValue: { width: 34, textAlign: "right", fontSize: 11, fontWeight: "700" },
  tips: { fontSize: 13, lineHeight: 20 },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  tag: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  tagText: { fontSize: 12 },
  bar: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: "row",
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 12,
    borderTopWidth: 1,
  },
  primary: {
    flex: 1,
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 26,
    paddingVertical: 14,
  },
  primaryText: { fontSize: 16, fontWeight: "800" },
  secondary: { width: 52, height: 52, borderRadius: 26, borderWidth: 1, alignItems: "center", justifyContent: "center" },
});
