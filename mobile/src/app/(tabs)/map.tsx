// 지도 화면 — coolmap/ui/mapview.py.
// 공식 쉼터는 채운 점, AI 추정 쉼터는 빈 원(점선 대신)으로 구분하고,
// 선택한 쉼터가 들어 있는 건물을 지도 타일의 건물 외곽선으로 하이라이트한다.

import {
  Camera,
  type CameraRef,
  type CircleLayerSpecification,
  GeoJSONSource,
  Layer,
  type LngLat,
  Map,
  type MapRef,
  type StyleSpecification,
} from "@maplibre/maplibre-react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { type Analysis, analysisDistance, type Prefer, rank, stayLabel } from "../../analysis";
import { PlaceRow } from "../../components/PlaceCard";
import { Icon, Pill } from "../../components/ui";
import { openDirections } from "../../directions";
import { haversine } from "../../geo";
import { loadMapStyle } from "../../mapStyle";
import { categoryLabel } from "../../places";
import { useStore } from "../../store";
import { MODE_LABEL, type Mode, nuisanceColor, PALETTES } from "../../theme";

// 지도를 이만큼 옮기면 '이 지역에서 다시 찾기' 를 띄운다
const RESEARCH_DISTANCE_M = 800;
const ME_COLOR = "#4C8DF6";

const SORTS: [Prefer, string][] = [
  ["balanced", "추천순"],
  ["close", "가까운순"],
  ["cool", "온도순"],
  ["quiet", "조용한순"],
  ["free", "눈치없는순"],
];

type CircleRadius = NonNullable<NonNullable<CircleLayerSpecification["paint"]>["circle-radius"]>;

type Ring = number[][];

/** 점이 고리(다각형 바깥선) 안에 있는지 — 반직선 교차 판정 */
function inRing([x, y]: number[], ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/**
 * 쉼터가 들어 있는 건물 하나를 고른다.
 * 벡터 타일은 이웃한 건물 여러 채를 한 도형(MultiPolygon)으로 묶어 두기도 해서,
 * 받은 도형을 통째로 칠하면 동네 전체가 하이라이트된다. 좌표를 품은 조각만 꺼낸다.
 */
function buildingAt(features: GeoJSON.Feature[], lon: number, lat: number): GeoJSON.Feature | null {
  for (const f of features) {
    const g = f.geometry;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
    for (const poly of polys) {
      if (poly[0] && inRing([lon, lat], poly[0])) {
        return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: poly } };
      }
    }
  }
  return null;
}

/** 미터 → 화면 픽셀 반지름. 줌이 1 오를 때마다 2배가 된다 (512px 타일 기준). */
function metersToPixels(m: number, lat: number): CircleRadius {
  const atZoom0 = m / ((40_075_016.686 * Math.cos((lat * Math.PI) / 180)) / 512);
  return ["interpolate", ["exponential", 2], ["zoom"], 0, atZoom0, 22, atZoom0 * 2 ** 22];
}

export default function MapScreen() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, mode } = s;
  const camera = useRef<CameraRef>(null);
  const map = useRef<MapRef>(null);
  const { focus } = useLocalSearchParams<{ focus?: string }>();

  const [mapStyle, setMapStyle] = useState<StyleSpecification | string | null>(null);
  const [mapCenter, setMapCenter] = useState<LngLat>(s.searchCenter);
  const [sheetHeight, setSheetHeight] = useState(0);
  const [sort, setSort] = useState<Prefer>("balanced");
  // 모드를 바꾸면 선택이 풀리도록 어느 모드에서 고른 것인지 함께 둔다
  const [selection, setSelection] = useState<{ id: string; mode: Mode } | null>(null);
  const [building, setBuilding] = useState<GeoJSON.FeatureCollection | null>(null);
  const selectedId = selection?.mode === mode ? selection.id : null;
  const setSelectedId = (id: string | null) => setSelection(id ? { id, mode } : null);

  useEffect(() => {
    loadMapStyle().then(setMapStyle);
  }, []);

  const ranked = useMemo(() => rank(s.analyses, sort), [s.analyses, sort]);
  const selected = ranked.find((a) => a.place.id === selectedId) ?? null;

  const select = (a: Analysis) => {
    setSelectedId(a.place.id);
    setBuilding(null);
    camera.current?.easeTo({ center: [a.place.lon, a.place.lat], zoom: 16.2, duration: 450 });
    // 이동이 끝난 뒤 그 지점에 그려진 건물 외곽선을 찾아 하이라이트한다 (데스크톱의 건물 하이라이트)
    setTimeout(async () => {
      try {
        const pt = await map.current?.project([a.place.lon, a.place.lat]);
        if (!pt) return;
        const found = await map.current?.queryRenderedFeatures(pt, { layers: ["building"] });
        const hit = buildingAt(found ?? [], a.place.lon, a.place.lat);
        if (hit) setBuilding({ type: "FeatureCollection", features: [hit] });
      } catch {
        // 건물을 못 찾으면 점만 강조한다
      }
    }, 650);
  };

  // 지도는 스타일을 받은 뒤에 그려지므로, 그 전에 찾은 위치로 이동하라는 명령은 버려진다.
  // 하단 패널 높이가 처음 정해지는 시점(= 지도가 그려진 직후)에 검색 중심으로 다시 맞춘다.
  const sheetReady = sheetHeight > 0;
  useEffect(() => {
    if (sheetReady) camera.current?.jumpTo({ center: s.searchCenter, zoom: 14 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 처음 한 번만
  }, [sheetReady]);

  // 위치를 새로 찾으면 그곳으로 이동한다
  useEffect(() => {
    camera.current?.flyTo({ center: s.origin, zoom: 14, duration: 800 });
  }, [s.origin]);

  // 다른 화면에서 '지도에서 보기' 로 들어온 경우
  useEffect(() => {
    if (!focus || !sheetReady) return;
    const a = ranked.find((x) => x.place.id === focus);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 다른 화면에서 넘어온 요청(내비게이션 파라미터)에 반응한다
    if (a) select(a);
    else {
      const place = s.getPlace(focus);
      if (place) camera.current?.flyTo({ center: [place.lon, place.lat], zoom: 16, duration: 600 });
    }
    router.setParams({ focus: undefined });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, sheetReady]);

  const features = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: ranked.map((a) => ({
        type: "Feature",
        id: a.place.id,
        geometry: { type: "Point", coordinates: [a.place.lon, a.place.lat] },
        properties: { id: a.place.id, name: a.place.name, open: a.crowd.openNow, ai: a.place.aiGuess },
      })),
    }),
    [ranked],
  );

  const meFeature = useMemo<GeoJSON.Feature | null>(
    () => s.me && { type: "Feature", geometry: { type: "Point", coordinates: s.me.coord }, properties: {} },
    [s.me],
  );

  const moved =
    haversine(s.searchCenter[1], s.searchCenter[0], mapCenter[1], mapCenter[0]) > RESEARCH_DISTANCE_M;

  const locate = async () => {
    const c = await s.locate();
    if (c) camera.current?.flyTo({ center: c, zoom: 14, duration: 800 });
    else camera.current?.flyTo({ center: s.origin, zoom: 14, duration: 800 });
  };

  if (!mapStyle) {
    return (
      <View style={[styles.fill, styles.center, { backgroundColor: p.bg }]}>
        <ActivityIndicator color={p.accent} />
      </View>
    );
  }

  const selColor = selected?.place.aiGuess ? p.warn : p.accent;

  return (
    <View style={[styles.fill, { backgroundColor: p.bg }]}>
      <Map
        ref={map}
        style={styles.fill}
        mapStyle={mapStyle}
        logo={false}
        compass={false}
        attributionPosition={{ bottom: 8, right: 8 }}
        // 상단 바와 하단 패널에 가리지 않는 영역을 지도의 중심으로 삼는다
        contentInset={{ top: insets.top + 96, bottom: sheetHeight }}
        onPress={() => {
          setSelectedId(null);
          setBuilding(null);
        }}
        onRegionDidChange={(e) => setMapCenter(e.nativeEvent.center)}
      >
        <Camera ref={camera} initialViewState={{ center: s.searchCenter, zoom: 14 }} />

        {building && (
          <GeoJSONSource id="building-hl" data={building}>
            <Layer type="fill" id="building-hl-fill" paint={{ "fill-color": selColor, "fill-opacity": 0.28 }} />
            <Layer
              type="line"
              id="building-hl-line"
              paint={{
                "line-color": selColor,
                "line-width": 2.5,
                ...(selected?.place.aiGuess ? { "line-dasharray": [2, 1.5] } : {}),
              }}
            />
          </GeoJSONSource>
        )}

        <GeoJSONSource
          id="places"
          data={features}
          onPress={(e) => {
            e.stopPropagation();
            const id = e.nativeEvent.features[0]?.properties?.id;
            const a = ranked.find((x) => x.place.id === id);
            if (a) select(a);
          }}
        >
          {/* 공식 지정 쉼터 — 채운 점 */}
          <Layer
            type="circle"
            id="official-dots"
            filter={["!", ["get", "ai"]]}
            paint={{
              "circle-radius": ["case", ["==", ["get", "id"], selectedId ?? ""], 11, 7],
              "circle-color": ["case", ["get", "open"], p.accent, p.textMute],
              "circle-stroke-width": 2,
              "circle-stroke-color": p.bg,
            }}
          />
          {/* AI 추정 쉼터 — 빈 원 (공식 쉼터와 섞이지 않게) */}
          <Layer
            type="circle"
            id="ai-dots"
            filter={["get", "ai"]}
            paint={{
              "circle-radius": ["case", ["==", ["get", "id"], selectedId ?? ""], 11, 7],
              "circle-color": p.bg,
              "circle-opacity": 0.85,
              "circle-stroke-width": 2.5,
              "circle-stroke-color": ["case", ["get", "open"], p.warn, p.textMute],
            }}
          />
          <Layer
            type="symbol"
            id="place-labels"
            minzoom={15}
            layout={{
              "text-field": ["get", "name"],
              // 스타일 서버(OpenFreeMap)에 있는 글꼴이어야 한다. 기본값(Open Sans)은 없어서 404 가 난다.
              "text-font": ["Noto Sans Regular"],
              "text-size": 11,
              "text-offset": [0, 1.3],
              "text-anchor": "top",
              "text-max-width": 9,
              "text-optional": true,
            }}
            paint={{ "text-color": p.text, "text-halo-color": p.bg, "text-halo-width": 1.5 }}
          />
        </GeoJSONSource>

        {s.me && meFeature && (
          <GeoJSONSource id="me" data={meFeature}>
            <Layer
              type="circle"
              id="me-accuracy"
              paint={{
                "circle-radius": metersToPixels(s.me.accuracyM, s.me.coord[1]),
                "circle-color": ME_COLOR,
                "circle-opacity": 0.15,
                "circle-stroke-width": 1,
                "circle-stroke-color": ME_COLOR,
                "circle-stroke-opacity": 0.4,
              }}
            />
            <Layer
              type="circle"
              id="me-dot"
              paint={{ "circle-radius": 8, "circle-color": ME_COLOR, "circle-stroke-width": 3, "circle-stroke-color": "#FFFFFF" }}
            />
          </GeoJSONSource>
        )}
      </Map>

      {/* 상단: 모드 전환 · 기온 · 범례 */}
      <View style={[styles.topBar, { top: insets.top + 8 }]}>
        <View style={[styles.segment, { backgroundColor: p.card, borderColor: p.border }]}>
          {(["cooling", "heating"] as Mode[]).map((m) => {
            const on = m === mode;
            return (
              <Pressable
                key={m}
                onPress={() => s.update({ mode: m })}
                style={[styles.segmentItem, on && { backgroundColor: PALETTES[m].accent }]}
              >
                <Text style={[styles.segmentText, { color: on ? PALETTES[m].accentInk : p.textDim }]}>{MODE_LABEL[m]}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={[styles.chip, { backgroundColor: p.card, borderColor: p.border }]}>
          <Text style={[styles.chipText, { color: p.text }]}>
            {s.weather.live ? `${s.weather.outdoor.toFixed(1)}°C` : "기온 —"}
          </Text>
        </View>
      </View>
      <View style={[styles.legend, { top: insets.top + 60, backgroundColor: p.card, borderColor: p.border }]}>
        <View style={[styles.dot, { backgroundColor: p.accent }]} />
        <Text style={[styles.legendText, { color: p.textDim }]}>공식 쉼터</Text>
        <View style={[styles.dot, { borderWidth: 2, borderColor: p.warn }]} />
        <Text style={[styles.legendText, { color: p.textDim }]}>AI 추정</Text>
        {s.aiLoading && <ActivityIndicator size="small" color={p.warn} />}
      </View>

      {(moved || !!s.locationNotice) && (
        <View style={[styles.floatCenter, { top: insets.top + 100 }]}>
          {moved ? (
            <Pressable onPress={() => s.setSearchCenter(mapCenter)} style={[styles.pill, { backgroundColor: p.accent }]}>
              <Text style={[styles.pillText, { color: p.accentInk }]}>이 지역에서 다시 찾기</Text>
            </Pressable>
          ) : (
            <View style={[styles.pill, { backgroundColor: p.card, borderColor: p.border, borderWidth: 1 }]}>
              <Text style={[styles.noticeText, { color: p.textDim }]}>{s.locationNotice}</Text>
            </View>
          )}
        </View>
      )}

      {/* 내 위치 — 패널 밖에 두어야 Android 에서 눌린다 */}
      <Pressable
        onPress={locate}
        style={[styles.locateBtn, { bottom: sheetHeight + 12, backgroundColor: p.card, borderColor: p.border }]}
      >
        <Icon name="crosshairs-gps" size={22} color={p.accent} />
      </Pressable>

      {/* 하단 패널 */}
      <View
        onLayout={(e) => setSheetHeight(e.nativeEvent.layout.height)}
        style={[styles.sheet, { backgroundColor: p.card, borderColor: p.border }]}
      >
        {selected ? (
          <Summary
            a={selected}
            onClose={() => {
              setSelectedId(null);
              setBuilding(null);
            }}
          />
        ) : (
          <NearbyList ranked={ranked} sort={sort} setSort={setSort} onSelect={select} />
        )}
      </View>
    </View>
  );
}

function NearbyList({
  ranked,
  sort,
  setSort,
  onSelect,
}: {
  ranked: Analysis[];
  sort: Prefer;
  setSort: (s: Prefer) => void;
  onSelect: (a: Analysis) => void;
}) {
  const s = useStore();
  const { p } = s;
  const kind = s.mode === "heating" ? "한파쉼터" : "무더위쉼터";
  const open = ranked.filter((a) => a.crowd.openNow).length;

  return (
    <View>
      <View style={styles.listHead}>
        <Text style={[styles.title, { color: p.text }]}>
          주변 쉼터 {ranked.length}곳<Text style={{ color: p.good }}>  · 지금 열림 {open}</Text>
        </Text>
        {s.loading && <ActivityIndicator color={p.accent} />}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.noShrink} contentContainerStyle={styles.sorts}>
        {SORTS.map(([key, label]) => {
          const on = key === sort;
          return (
            <Pressable
              key={key}
              onPress={() => setSort(key)}
              style={[styles.sortChip, { borderColor: on ? p.accent : p.border, backgroundColor: on ? p.accentSoft : "transparent" }]}
            >
              <Text style={[styles.sortText, { color: on ? p.accent : p.textDim }]}>{label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
      {s.error ? (
        <Text style={[styles.dim, { color: p.bad }]}>쉼터 목록을 받지 못했습니다 ({s.error})</Text>
      ) : !s.loading && !ranked.length ? (
        <Text style={[styles.dim, { color: p.textDim }]}>
          반경 {s.settings.searchRadius / 1000}km · 도보 {s.settings.maxWalk}분 안에 {kind}가 없습니다
        </Text>
      ) : (
        <ScrollView style={styles.list}>
          {ranked.slice(0, 40).map((a) => (
            <PlaceRow key={a.place.id} a={a} p={p} selected={false} onPress={() => onSelect(a)} />
          ))}
        </ScrollView>
      )}
    </View>
  );
}

/** 지도에서 선택한 장소의 요약 패널 (mapview.py 선택 패널) */
function Summary({ a, onClose }: { a: Analysis; onClose: () => void }) {
  const { p, here } = useStore();
  const where = categoryLabel(a.place);
  const nc = nuisanceColor(p, a.nuisance.key);
  return (
    <View>
      <View style={styles.row}>
        <Text style={[styles.title, styles.fill, { color: p.text }]} numberOfLines={2}>
          {a.place.name}
        </Text>
        <Pressable onPress={onClose} hitSlop={12}>
          <Icon name="close" size={22} color={p.textMute} />
        </Pressable>
      </View>
      <Text style={[styles.dim, { color: p.textDim }]}>
        {a.place.aiGuess ? `AI 추정 ${a.place.aiConfidence}% · ` : ""}
        {where} · {analysisDistance(a)} · 건물 하이라이트
      </Text>
      <View style={styles.chips}>
        <Pill
          text={a.crowd.openNow ? `실내 ${Math.round(a.indoor)}°C` : "운영 종료"}
          icon="thermometer"
          color={a.crowd.openNow ? p.accent : p.textMute}
          bg={p.cardAlt}
        />
        <Pill text={`쾌적 ${a.comfort}`} icon="creation" color={p.accent} bg={p.cardAlt} />
        <Pill text={`민폐도 ${a.nuisance.score}`} icon="star" color={nc} bg={p.cardAlt} />
        {a.place.official && <Pill text="공식 지정" icon="check-circle" color={p.good} bg={p.cardAlt} />}
      </View>
      <Text style={[styles.dim, { color: p.textDim, marginTop: 8 }]}>
        {a.nuisance.level}
        {"\n"}권장 체류 {stayLabel(a.nuisance.stayMinutes)} · 도보 {a.walkMin}분
      </Text>
      <View style={styles.actions}>
        <Pressable
          onPress={() => router.push({ pathname: "/place/[id]", params: { id: a.place.id } })}
          style={[styles.primary, { backgroundColor: p.accent }]}
        >
          <Text style={[styles.pillText, { color: p.accentInk }]}>상세 보기</Text>
        </Pressable>
        <Pressable onPress={() => openDirections(a.place, here)} style={[styles.secondary, { borderColor: p.border }]}>
          <Icon name="walk" size={18} color={p.text} />
          <Text style={[styles.pillText, { color: p.text }]}>길찾기</Text>
        </Pressable>
      </View>
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
  legend: {
    position: "absolute",
    left: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  legendText: { fontSize: 11, fontWeight: "600", marginRight: 4 },
  dot: { width: 10, height: 10, borderRadius: 5 },
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
    paddingTop: 14,
    paddingBottom: 12,
    maxHeight: "48%",
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
  listHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { fontSize: 17, fontWeight: "800", marginBottom: 4 },
  dim: { fontSize: 13 },
  noShrink: { flexGrow: 0, flexShrink: 0 },
  sorts: { gap: 6, paddingVertical: 6 },
  sortChip: { borderWidth: 1, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 5 },
  sortText: { fontSize: 12, fontWeight: "700" },
  list: { marginTop: 4 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10 },
  actions: { flexDirection: "row", gap: 10, marginTop: 14 },
  primary: { flex: 1, borderRadius: 12, paddingVertical: 12 },
  secondary: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 16,
  },
});
