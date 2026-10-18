// 길 안내 — 앱 안에서 쉼터까지 걷는 길을 보여 준다 (T맵 보행자 경로, supabase/functions/route).
// 지도에 길을 선으로 그리고, 아래에 '걸어서 약 n분 · 남은 거리' 와 단계 안내를 큰 글씨로 보여 준다.
// 카카오맵·네이버 지도 같은 앱이 없어도 쓸 수 있고, 원하면 다른 지도 앱으로 열 수도 있다.

import {
  Camera,
  GeoJSONSource,
  Layer,
  type LngLatBounds,
  Map,
  type StyleSpecification,
} from "@maplibre/maplibre-react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { type WalkRoute, walkRoute } from "../../backend";
import { BigButton, Icon, T } from "../../components/ui";
import { openDirections } from "../../directions";
import { distanceLabel, haversine } from "../../geo";
import { loadMapStyle } from "../../mapStyle";
import type { Place } from "../../places";
import { useStore } from "../../store";

const ME_COLOR = "#4C8DF6";
/** 쉼터에 이만큼(m) 가까워지면 도착으로 본다 */
const ARRIVED_M = 30;

type LngLat = [number, number];
type Result = { key: string; route?: WalkRoute; error?: string };

export default function RouteScreen() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStore();
  const { p } = s;
  const place = s.getPlace(String(id));

  // 출발지는 화면을 열 때의 내 위치로 고정한다 (걸으면서 경로를 계속 다시 받지 않도록)
  const [start, setStart] = useState<LngLat | null>(() => s.here);
  const [result, setResult] = useState<Result | null>(null);
  const [mapStyle, setMapStyle] = useState<StyleSpecification | string | null>(null);

  const key = start && place ? `${start[0]},${start[1]}>${place.id}` : "";

  useEffect(() => {
    let alive = true;
    loadMapStyle(p.dark).then((style) => alive && setMapStyle(style));
    return () => {
      alive = false;
    };
  }, [p.dark]);

  useEffect(() => {
    if (!start || !place) return;
    let alive = true;
    walkRoute([start[1], start[0]], [place.lat, place.lon], place.name)
      .then((route) => alive && setResult({ key, route }))
      .catch((e: unknown) => alive && setResult({ key, error: e instanceof Error ? e.message : String(e) }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key 가 출발지·도착지를 모두 담고 있다
  }, [key]);

  const current = result?.key === key ? result : null;
  const route = current?.route;

  const pathFeature = useMemo<GeoJSON.Feature | null>(
    () => (route ? { type: "Feature", geometry: { type: "LineString", coordinates: route.path }, properties: {} } : null),
    [route],
  );

  if (!place) {
    return (
      <View style={[styles.fill, styles.center, { backgroundColor: p.bg }]}>
        <T size={17} color={p.textDim}>
          장소를 찾을 수 없어요.
        </T>
        <BigButton text="돌아가기" p={p} kind="secondary" onPress={() => router.back()} style={{ marginTop: 16 }} />
      </View>
    );
  }

  const me = s.me?.coord ?? null;
  const left = me ? haversine(me[1], me[0], place.lat, place.lon) : null;
  const arrived = left !== null && left <= ARRIVED_M;
  const retry = () => {
    setResult(null);
    setStart(s.here);
  };

  const bounds: LngLatBounds | null = route
    ? (() => {
        const pts = [...route.path, [place.lon, place.lat] as LngLat, ...(me ? [me] : [])];
        const xs = pts.map((q) => q[0]);
        const ys = pts.map((q) => q[1]);
        return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
      })()
    : null;

  return (
    <View style={[styles.fill, { backgroundColor: p.bg }]}>
      {/* 지도 */}
      <View style={styles.mapBox}>
        {mapStyle && bounds && pathFeature ? (
          <Map style={styles.fill} mapStyle={mapStyle} logo={false} compass={false} attributionPosition={{ bottom: 8, right: 8 }}>
            <Camera
              initialViewState={{
                bounds,
                padding: { top: insets.top + 70, bottom: 40, left: 40, right: 40 },
              }}
            />
            <GeoJSONSource id="route" data={pathFeature}>
              <Layer
                type="line"
                id="route-casing"
                layout={{ "line-cap": "round", "line-join": "round" }}
                paint={{ "line-color": p.dark ? "#000000" : "#FFFFFF", "line-width": 11, "line-opacity": 0.8 }}
              />
              <Layer
                type="line"
                id="route-line"
                layout={{ "line-cap": "round", "line-join": "round" }}
                paint={{ "line-color": p.accent, "line-width": 6 }}
              />
            </GeoJSONSource>
            <GeoJSONSource
              id="dest"
              data={{ type: "Feature", geometry: { type: "Point", coordinates: [place.lon, place.lat] }, properties: {} }}
            >
              <Layer
                type="circle"
                id="dest-dot"
                paint={{ "circle-radius": 11, "circle-color": p.accent, "circle-stroke-width": 3, "circle-stroke-color": "#FFFFFF" }}
              />
            </GeoJSONSource>
            {me && (
              <GeoJSONSource id="me" data={{ type: "Feature", geometry: { type: "Point", coordinates: me }, properties: {} }}>
                <Layer
                  type="circle"
                  id="me-dot"
                  paint={{ "circle-radius": 8, "circle-color": ME_COLOR, "circle-stroke-width": 3, "circle-stroke-color": "#FFFFFF" }}
                />
              </GeoJSONSource>
            )}
          </Map>
        ) : (
          <View style={[styles.fill, styles.center]}>
            {start && !current && <ActivityIndicator color={p.accent} size="large" />}
          </View>
        )}
        <Pressable
          onPress={() => router.back()}
          hitSlop={10}
          style={[styles.back, { top: insets.top + 10, backgroundColor: p.card, borderColor: p.border }]}
        >
          <Icon name="arrow-left" size={24} color={p.text} />
          <T size={16} weight="700" color={p.text}>
            뒤로
          </T>
        </Pressable>
      </View>

      {/* 안내 */}
      <View style={[styles.panel, { backgroundColor: p.card, borderColor: p.border, paddingBottom: insets.bottom + 12 }]}>
        <T size={21} weight="800" color={p.text} numberOfLines={2}>
          {place.name}까지
        </T>

        {!start ? (
          <Message
            text="내 위치를 찾지 못해 길을 안내할 수 없어요. 위치 서비스가 켜져 있는지 확인해 주세요."
            onRetry={retry}
            place={place}
          />
        ) : !current ? (
          <T size={17} color={p.textDim}>
            걸어가는 길을 찾고 있어요…
          </T>
        ) : current.error || !route ? (
          <Message text={`길을 찾지 못했어요. (${current.error ?? "경로 없음"})`} onRetry={retry} place={place} />
        ) : (
          <>
            <T size={26} weight="800" color={p.accent}>
              걸어서 약 {Math.max(1, Math.round(route.time_s / 60))}분 · {distanceLabel(route.distance_m)}
            </T>
            {arrived ? (
              <View style={[styles.arrived, { backgroundColor: p.accentSoft, borderColor: p.accent }]}>
                <Icon name="check-circle" size={26} color={p.good} />
                <T size={18} weight="800" color={p.text} style={styles.fill}>
                  도착했어요. 편하게 쉬어 가세요.
                </T>
              </View>
            ) : (
              left !== null && (
                <T size={16} color={p.textDim}>
                  남은 거리 약 {distanceLabel(left)} (직선)
                </T>
              )
            )}
            <ScrollView style={styles.steps} contentContainerStyle={{ gap: 10, paddingVertical: 6 }}>
              {route.steps.map((step, i) => (
                <View key={`${i}-${step.text}`} style={styles.step}>
                  <View style={[styles.num, { backgroundColor: p.accentSoft }]}>
                    <T size={15} weight="800" color={p.accent}>
                      {i + 1}
                    </T>
                  </View>
                  <T size={17} color={p.text} style={styles.fill}>
                    {step.text}
                  </T>
                </View>
              ))}
            </ScrollView>
            <BigButton
              text="다른 지도 앱으로 열기"
              icon="open-in-new"
              p={p}
              kind="secondary"
              onPress={() => openDirections(place, s.here)}
            />
          </>
        )}
      </View>
    </View>
  );
}

function Message({ text, onRetry, place }: { text: string; onRetry: () => void; place: Place }) {
  const s = useStore();
  const { p } = s;
  return (
    <View style={{ gap: 10 }}>
      <T size={17} color={p.textDim}>
        {text}
      </T>
      <View style={styles.row}>
        <BigButton text="다시 시도" icon="refresh" p={p} onPress={onRetry} style={styles.fill} />
        <BigButton text="다른 지도 앱" p={p} kind="secondary" onPress={() => openDirections(place, s.here)} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", gap: 10 },
  mapBox: { flex: 1 },
  back: {
    position: "absolute",
    left: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderRadius: 22,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  panel: {
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    borderWidth: 1,
    paddingHorizontal: 18,
    paddingTop: 16,
    gap: 10,
    maxHeight: "55%",
  },
  arrived: { flexDirection: "row", alignItems: "center", gap: 10, borderWidth: 1.5, borderRadius: 14, padding: 12 },
  steps: { flexGrow: 0 },
  step: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  num: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center" },
});
