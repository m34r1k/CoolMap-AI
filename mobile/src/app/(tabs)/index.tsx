// 홈 화면 — coolmap/ui/home.py (모드 전환 · 목표 온도 · 지도 미리보기 · AI 추천)

import { Camera, GeoJSONSource, Layer, Map, type StyleSpecification } from "@maplibre/maplibre-react-native";
import { router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { clockLabel, rank } from "../../analysis";
import { PlaceCard } from "../../components/PlaceCard";
import { Card, Icon, Logo, SectionTitle } from "../../components/ui";
import { loadMapStyle } from "../../mapStyle";
import { useStore } from "../../store";
import { type Mode, PALETTES } from "../../theme";

export default function Home() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, mode } = s;
  const ranked = useMemo(() => rank(s.analyses), [s.analyses]);
  const w = s.weather;

  return (
    <ScrollView style={{ backgroundColor: p.bg }} contentContainerStyle={[styles.page, { paddingTop: insets.top + 12 }]}>
      <View style={styles.header}>
        <Logo p={p} />
        <View style={[styles.outdoor, { borderColor: p.border, backgroundColor: p.card }]}>
          <Text style={[styles.outdoorLabel, { color: p.textMute }]}>OUTDOOR</Text>
          <Text style={[styles.outdoorValue, { color: mode === "cooling" ? p.bad : p.accentBright }]}>
            {w.live ? `${w.outdoor.toFixed(0)}°C` : "—"}
          </Text>
          {w.live && !!w.alert && <Text style={[styles.alert, { color: p.warn }]}>{w.alert}</Text>}
        </View>
      </View>

      <Text style={[styles.h1, { color: p.text }]}>
        {mode === "cooling" ? "가장 시원한 장소를 찾아보세요." : "가장 따뜻한 장소를 찾아보세요."}
      </Text>
      <Text style={[styles.sub, { color: p.textDim }]}>
        {mode === "cooling" ? "Find the coolest place nearby." : "Find the warmest place nearby."}
      </Text>

      <ModeCard />
      <MapPreview />

      <SectionTitle
        p={p}
        text="AI 추천"
        icon="creation"
        right={
          <Text style={[styles.count, { color: p.textMute }]}>
            {ranked.length}곳 분석 · {clockLabel(s.now)}
          </Text>
        }
      />
      {s.loading && !ranked.length ? (
        <ActivityIndicator color={p.accent} style={{ marginTop: 20 }} />
      ) : !ranked.length ? (
        <Text style={[styles.sub, { color: p.textDim }]}>
          {s.error ? `쉼터 목록을 받지 못했습니다 (${s.error})` : "주변에 추천할 쉼터가 없습니다."}
        </Text>
      ) : (
        <View style={{ gap: 14 }}>
          {ranked.slice(0, 6).map((a) => (
            <PlaceCard
              key={a.place.id}
              a={a}
              p={p}
              favorite={s.isFavorite(a.place.id)}
              onOpen={() => router.push({ pathname: "/place/[id]", params: { id: a.place.id } })}
              onFavorite={() => s.toggleFavorite(a.place)}
            />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

/** 냉방/난방 전환 + 목표 온도 */
function ModeCard() {
  const s = useStore();
  const { p, mode } = s;
  const key = mode === "cooling" ? "targetCool" : "targetHeat";
  const setTarget = (v: number) => s.update({ [key]: Math.max(16, Math.min(30, v)) });

  return (
    <Card p={p} style={{ marginTop: 18 }}>
      <Text style={[styles.cardTitle, { color: p.text }]}>Active Mode</Text>
      <Text style={[styles.cardSub, { color: p.textDim }]}>{p.tagline}</Text>
      <View style={{ gap: 10, marginTop: 14 }}>
        {(["cooling", "heating"] as Mode[]).map((m) => {
          const on = m === mode;
          const mp = PALETTES[m];
          return (
            <Pressable
              key={m}
              onPress={() => s.update({ mode: m })}
              style={[
                styles.modeBtn,
                { backgroundColor: on ? mp.accent : p.cardAlt, borderColor: on ? mp.accent : p.border },
              ]}
            >
              <Icon name={m === "cooling" ? "snowflake" : "fire"} size={22} color={on ? mp.accentInk : p.textDim} />
              <Text style={[styles.modeText, { color: on ? mp.accentInk : p.textDim }]}>
                {m === "cooling" ? "냉방 Cooling" : "난방 Heating"}
              </Text>
              {on && <Icon name="check-circle-outline" size={20} color={mp.accentInk} />}
            </Pressable>
          );
        })}
      </View>
      <View style={styles.targetRow}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.targetLabel, { color: p.textMute }]}>TARGET TEMP</Text>
          <Text style={[styles.targetValue, { color: p.accent }]}>{Math.round(s.target)}°C</Text>
        </View>
        <Pressable onPress={() => setTarget(s.target - 1)} style={[styles.stepper, { borderColor: p.border }]}>
          <Icon name="minus" size={20} color={p.text} />
        </Pressable>
        <Pressable onPress={() => setTarget(s.target + 1)} style={[styles.stepper, { borderColor: p.border }]}>
          <Icon name="plus" size={20} color={p.text} />
        </Pressable>
      </View>
      <Text style={[styles.cardSub, { color: p.textMute }]}>
        목표 온도를 기준으로 쾌적 점수를 계산합니다.
        {mode === "heating" ? " 난방 모드에서는 목표보다 따뜻한 곳을 높게 평가합니다." : ""}
      </Text>
    </Card>
  );
}

/** 홈 화면의 지도 미리보기 — 누르면 전체 지도로 */
function MapPreview() {
  const s = useStore();
  const { p } = s;
  const [style, setStyle] = useState<StyleSpecification | string | null>(null);
  useEffect(() => {
    loadMapStyle().then(setStyle);
  }, []);

  const features = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: s.analyses.map((a) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [a.place.lon, a.place.lat] },
        properties: { ai: a.place.aiGuess, open: a.crowd.openNow },
      })),
    }),
    [s.analyses],
  );

  return (
    <View style={[styles.preview, { borderColor: p.border, backgroundColor: p.card }]}>
      {style && (
        <Map
          style={StyleSheet.absoluteFill}
          mapStyle={style}
          logo={false}
          compass={false}
          attributionPosition={{ bottom: 4, right: 4 }}
          dragPan={false}
          touchZoom={false}
          doubleTapZoom={false}
          touchRotate={false}
          touchPitch={false}
        >
          <Camera center={s.searchCenter} zoom={13} />
          <GeoJSONSource id="preview" data={features}>
            <Layer
              type="circle"
              id="preview-dots"
              paint={{
                "circle-radius": 5,
                "circle-color": ["case", ["get", "ai"], p.bg, ["get", "open"], p.accent, p.textMute],
                "circle-stroke-width": ["case", ["get", "ai"], 2, 1.5],
                "circle-stroke-color": ["case", ["get", "ai"], p.warn, p.bg],
              }}
            />
          </GeoJSONSource>
        </Map>
      )}
      <Pressable style={StyleSheet.absoluteFill} onPress={() => router.navigate("/map")} />
      <View style={[styles.live, { backgroundColor: p.bg + "CC" }]}>
        <View style={[styles.liveDot, { backgroundColor: p.accent }]} />
        <Text style={[styles.liveText, { color: p.text }]}>Live Scan Active</Text>
      </View>
      <Pressable onPress={() => router.navigate("/map")} style={[styles.openMap, { backgroundColor: p.accent }]}>
        <Icon name="compass-outline" size={18} color={p.accentInk} />
        <Text style={[styles.openMapText, { color: p.accentInk }]}>전체 지도 열기</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { paddingHorizontal: 16, paddingBottom: 32 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  outdoor: { borderWidth: 1, borderRadius: 18, paddingHorizontal: 14, paddingVertical: 8, alignItems: "flex-end" },
  outdoorLabel: { fontSize: 10, fontWeight: "700", letterSpacing: 1.5 },
  outdoorValue: { fontSize: 24, fontWeight: "800" },
  alert: { fontSize: 11, fontWeight: "700" },
  h1: { fontSize: 24, fontWeight: "800", marginTop: 22 },
  sub: { fontSize: 13, marginTop: 4 },
  cardTitle: { fontSize: 19, fontWeight: "800" },
  cardSub: { fontSize: 12, marginTop: 4 },
  modeBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 13,
  },
  modeText: { flex: 1, fontSize: 17, fontWeight: "700" },
  targetRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 18 },
  targetLabel: { fontSize: 11, fontWeight: "700", letterSpacing: 1.5 },
  targetValue: { fontSize: 30, fontWeight: "800" },
  stepper: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  preview: { height: 220, borderRadius: 18, borderWidth: 1, overflow: "hidden", marginTop: 16 },
  live: {
    position: "absolute",
    top: 12,
    left: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  liveDot: { width: 8, height: 8, borderRadius: 4 },
  liveText: { fontSize: 11, fontWeight: "700" },
  openMap: {
    position: "absolute",
    right: 12,
    bottom: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  openMapText: { fontSize: 14, fontWeight: "800" },
  count: { fontSize: 11, fontWeight: "600" },
});
