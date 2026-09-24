import {
  Camera,
  type CameraRef,
  GeoJSONSource,
  Layer,
  type LngLat,
  Map,
  type StyleSpecification,
  UserLocation,
} from "@maplibre/maplibre-react-native";
import * as Location from "expo-location";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";

import { sheltersNear, weather } from "./src/backend";
import { formatDistance, haversine } from "./src/geo";
import { loadMapStyle } from "./src/mapStyle";
import { CATEGORY_LABEL, isOpenNow, type Shelter, toShelter } from "./src/shelter";
import { defaultMode, MODE_LABEL, type Mode, PALETTES, type Palette } from "./src/theme";

// 위치 권한이 없을 때 기준점 (서울시청)
const FALLBACK: LngLat = [126.9784, 37.5667];
const SEARCH_RADIUS_M = 3000;
// 지도를 이만큼 옮기면 '이 지역에서 다시 찾기' 를 띄운다
const RESEARCH_DISTANCE_M = 800;

export default function App() {
  return (
    <SafeAreaProvider>
      <Main />
    </SafeAreaProvider>
  );
}

function Main() {
  const insets = useSafeAreaInsets();
  const camera = useRef<CameraRef>(null);

  const [mode, setMode] = useState<Mode>(defaultMode);
  const p = PALETTES[mode];

  const [mapStyle, setMapStyle] = useState<StyleSpecification | string | null>(null);
  const [located, setLocated] = useState(false);
  const [origin, setOrigin] = useState<LngLat>(FALLBACK);
  const [searchCenter, setSearchCenter] = useState<LngLat>(FALLBACK);
  const [mapCenter, setMapCenter] = useState<LngLat>(FALLBACK);

  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [temp, setTemp] = useState<number | null>(null);
  const [sheetHeight, setSheetHeight] = useState(0);

  useEffect(() => {
    loadMapStyle().then(setMapStyle);
  }, []);

  const locate = useCallback(async () => {
    const perm = await Location.requestForegroundPermissionsAsync();
    if (!perm.granted) {
      setNotice("위치 권한이 없어 서울시청 주변을 보여줍니다");
      return;
    }
    try {
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const here: LngLat = [pos.coords.longitude, pos.coords.latitude];
      setLocated(true);
      setNotice("");
      setOrigin(here);
      setSearchCenter(here);
      camera.current?.flyTo({ center: here, zoom: 14, duration: 800 });
    } catch {
      setNotice("현재 위치를 찾지 못했습니다. 위치 서비스가 켜져 있는지 확인해 주세요");
    }
  }, []);

  useEffect(() => {
    locate();
  }, [locate]);

  // 검색 중심이나 모드가 바뀌면 주변 쉼터를 다시 받는다
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const [lon, lat] = searchCenter;
    sheltersNear(lat, lon, mode, SEARCH_RADIUS_M)
      .then((rows) => {
        if (cancelled) return;
        setShelters(rows.map((r) => toShelter(r, mode)).filter((s): s is Shelter => s !== null));
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setShelters([]);
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [searchCenter, mode]);

  useEffect(() => {
    setSelectedId(null);
  }, [mode]);

  // 기온은 내 위치 기준
  useEffect(() => {
    const [lon, lat] = origin;
    weather(lat, lon)
      .then((w) => {
        const t = Number(w.now?.T1H);
        setTemp(Number.isFinite(t) ? t : null);
      })
      .catch(() => setTemp(null));
  }, [origin]);

  // 서버는 검색 중심에서의 거리를 주므로, 지도를 옮겨 다시 찾았을 때도 '내 위치'에서의 거리로 바꾼다
  const listed = useMemo(
    () =>
      shelters
        .map((s) => ({ ...s, distM: haversine(origin[1], origin[0], s.lat, s.lon) }))
        .sort((a, b) => a.distM - b.distM),
    [shelters, origin],
  );
  const selected = listed.find((s) => s.id === selectedId) ?? null;

  const features = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: listed.map((s) => ({
        type: "Feature",
        id: s.id,
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        properties: { id: s.id, open: isOpenNow(s) },
      })),
    }),
    [listed],
  );

  const moved =
    haversine(searchCenter[1], searchCenter[0], mapCenter[1], mapCenter[0]) > RESEARCH_DISTANCE_M;

  const select = (s: Shelter) => {
    setSelectedId(s.id);
    camera.current?.easeTo({ center: [s.lon, s.lat], duration: 400 });
  };

  if (!mapStyle) {
    return (
      <View style={[styles.fill, styles.center, { backgroundColor: p.bg }]}>
        <ActivityIndicator color={p.accent} />
        <StatusBar style="light" />
      </View>
    );
  }

  return (
    <View style={[styles.fill, { backgroundColor: p.bg }]}>
      <Map
        style={styles.fill}
        mapStyle={mapStyle}
        logo={false}
        compass={false}
        attributionPosition={{ bottom: 8, right: 8 }}
        onPress={() => setSelectedId(null)}
        onRegionDidChange={(e) => setMapCenter(e.nativeEvent.center)}
      >
        <Camera ref={camera} initialViewState={{ center: FALLBACK, zoom: 14 }} />
        {located && <UserLocation />}
        <GeoJSONSource
          id="shelters"
          data={features}
          onPress={(e) => {
            e.stopPropagation();
            const id = e.nativeEvent.features[0]?.properties?.id;
            const s = listed.find((x) => x.id === id);
            if (s) select(s);
          }}
        >
          <Layer
            type="circle"
            id="shelter-dots"
            paint={{
              "circle-radius": ["case", ["==", ["get", "id"], selectedId ?? ""], 11, 7],
              "circle-color": ["case", ["get", "open"], p.accent, p.textMute],
              "circle-stroke-width": 2,
              "circle-stroke-color": p.bg,
            }}
          />
        </GeoJSONSource>
      </Map>

      {/* 상단: 모드 전환 · 기온 */}
      <View style={[styles.topBar, { top: insets.top + 8 }]}>
        <View style={[styles.segment, { backgroundColor: p.card, borderColor: p.border }]}>
          {(["cooling", "heating"] as Mode[]).map((m) => {
            const on = m === mode;
            return (
              <Pressable
                key={m}
                onPress={() => setMode(m)}
                style={[styles.segmentItem, on && { backgroundColor: PALETTES[m].accent }]}
              >
                <Text style={[styles.segmentText, { color: on ? PALETTES[m].accentInk : p.textDim }]}>
                  {MODE_LABEL[m]}
                </Text>
              </Pressable>
            );
          })}
        </View>
        <View style={[styles.chip, { backgroundColor: p.card, borderColor: p.border }]}>
          <Text style={[styles.chipText, { color: p.text }]}>
            {temp === null ? "기온 —" : `${temp.toFixed(1)}°C`}
          </Text>
        </View>
      </View>

      {(moved || notice) && (
        <View style={[styles.floatCenter, { top: insets.top + 64 }]}>
          {moved ? (
            <Pressable
              onPress={() => setSearchCenter(mapCenter)}
              style={[styles.pill, { backgroundColor: p.accent }]}
            >
              <Text style={[styles.pillText, { color: p.accentInk }]}>이 지역에서 다시 찾기</Text>
            </Pressable>
          ) : (
            <View style={[styles.pill, { backgroundColor: p.card, borderColor: p.border, borderWidth: 1 }]}>
              <Text style={[styles.noticeText, { color: p.textDim }]}>{notice}</Text>
            </View>
          )}
        </View>
      )}

      {/* 내 위치 — 패널 밖에 두어야 Android 에서 눌린다 */}
      <Pressable
        onPress={locate}
        style={[styles.locateBtn, { bottom: sheetHeight + 12, backgroundColor: p.card, borderColor: p.border }]}
      >
        <Text style={[styles.locateText, { color: p.accent }]}>◎</Text>
      </Pressable>

      {/* 하단 패널 */}
      <View
        onLayout={(e) => setSheetHeight(e.nativeEvent.layout.height)}
        style={[styles.sheet, { backgroundColor: p.card, borderColor: p.border, paddingBottom: insets.bottom + 12 }]}
      >
        {selected ? (
          <Detail s={selected} p={p} onClose={() => setSelectedId(null)} />
        ) : (
          <Nearby shelters={listed} loading={loading} error={error} mode={mode} p={p} onSelect={select} />
        )}
      </View>

      <StatusBar style="light" />
    </View>
  );
}

function Nearby(props: {
  shelters: Shelter[];
  loading: boolean;
  error: string;
  mode: Mode;
  p: Palette;
  onSelect: (s: Shelter) => void;
}) {
  const { shelters, loading, error, mode, p, onSelect } = props;
  const kind = mode === "heating" ? "한파쉼터" : "무더위쉼터";

  if (loading) {
    return (
      <View style={styles.row}>
        <ActivityIndicator color={p.accent} />
        <Text style={[styles.dim, { color: p.textDim, marginLeft: 8 }]}>주변 {kind}를 찾는 중…</Text>
      </View>
    );
  }
  if (error) {
    return <Text style={[styles.dim, { color: p.bad }]}>쉼터 목록을 받지 못했습니다 ({error})</Text>;
  }
  if (!shelters.length) {
    return (
      <Text style={[styles.dim, { color: p.textDim }]}>
        반경 {SEARCH_RADIUS_M / 1000}km 안에 {kind}가 없습니다
      </Text>
    );
  }

  const open = shelters.filter((s) => isOpenNow(s)).length;
  return (
    <View>
      <Text style={[styles.title, { color: p.text }]}>
        주변 {kind} {shelters.length}곳
        <Text style={{ color: p.good }}>  · 지금 열림 {open}</Text>
      </Text>
      <ScrollView style={styles.list}>
        {shelters.slice(0, 20).map((s) => (
          <Pressable key={s.id} onPress={() => onSelect(s)} style={[styles.listItem, { borderColor: p.border }]}>
            <View style={styles.fill}>
              <Text style={[styles.itemName, { color: p.text }]} numberOfLines={1}>
                {s.name}
              </Text>
              <Text style={[styles.dim, { color: p.textMute }]} numberOfLines={1}>
                {CATEGORY_LABEL[s.category] ?? "쉼터"} · {s.hours}
              </Text>
            </View>
            <Text style={[styles.dist, { color: isOpenNow(s) ? p.accent : p.textMute }]}>
              {formatDistance(s.distM)}
            </Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function Detail({ s, p, onClose }: { s: Shelter; p: Palette; onClose: () => void }) {
  const open = isOpenNow(s);
  // Android 는 geo: 주소를 받으면 설치된 지도 앱 중에서 고르게 해 준다
  const navigate = () =>
    Linking.openURL(`geo:${s.lat},${s.lon}?q=${s.lat},${s.lon}(${encodeURIComponent(s.name)})`);

  return (
    <View>
      <View style={styles.row}>
        <Text style={[styles.title, styles.fill, { color: p.text }]} numberOfLines={2}>
          {s.name}
        </Text>
        <Pressable onPress={onClose} hitSlop={12}>
          <Text style={[styles.close, { color: p.textMute }]}>✕</Text>
        </Pressable>
      </View>
      <Text style={[styles.dim, { color: p.textDim }]}>
        {CATEGORY_LABEL[s.category] ?? "쉼터"} · {formatDistance(s.distM)}
        {s.capacity ? ` · ${s.capacity}명` : ""}
      </Text>
      <Text style={[styles.dim, { color: open ? p.good : p.warn, marginTop: 6 }]}>
        {open ? "지금 열림" : "지금 닫힘"} · {s.hours}
      </Text>
      {!!s.address && <Text style={[styles.dim, { color: p.textDim, marginTop: 4 }]}>{s.address}</Text>}
      <View style={styles.tags}>
        {s.amenities.map((a) => (
          <View key={a} style={[styles.tag, { borderColor: p.border }]}>
            <Text style={[styles.tagText, { color: p.textDim }]}>{a}</Text>
          </View>
        ))}
      </View>
      <Text style={[styles.dim, { color: p.textMute, marginTop: 8 }]}>{s.summary}</Text>
      <Pressable onPress={navigate} style={[styles.navBtn, { backgroundColor: p.accent }]}>
        <Text style={[styles.pillText, { color: p.accentInk }]}>길찾기</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center" },
  topBar: {
    position: "absolute",
    left: 16,
    right: 16,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  segment: { flexDirection: "row", borderRadius: 20, borderWidth: 1, padding: 3 },
  segmentItem: { paddingHorizontal: 18, paddingVertical: 7, borderRadius: 17 },
  segmentText: { fontSize: 14, fontWeight: "700" },
  chip: { borderRadius: 20, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 9 },
  chipText: { fontSize: 14, fontWeight: "700" },
  floatCenter: { position: "absolute", left: 16, right: 16, alignItems: "center" },
  pill: { borderRadius: 20, paddingHorizontal: 16, paddingVertical: 9 },
  pillText: { fontSize: 14, fontWeight: "700", textAlign: "center" },
  noticeText: { fontSize: 13 },
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingTop: 16,
    maxHeight: "45%",
  },
  locateBtn: {
    position: "absolute",
    right: 16,
    width: 46,
    height: 46,
    borderRadius: 23,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  locateText: { fontSize: 22, fontWeight: "700" },
  title: { fontSize: 17, fontWeight: "700", marginBottom: 4 },
  dim: { fontSize: 13 },
  list: { marginTop: 6 },
  listItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  itemName: { fontSize: 15, fontWeight: "600" },
  dist: { fontSize: 14, fontWeight: "700", marginLeft: 12 },
  close: { fontSize: 18, paddingLeft: 12 },
  tags: { flexDirection: "row", flexWrap: "wrap", marginTop: 10, gap: 6 },
  tag: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  tagText: { fontSize: 12 },
  navBtn: { marginTop: 14, borderRadius: 12, paddingVertical: 12 },
});
