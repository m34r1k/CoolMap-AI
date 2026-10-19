// 홈 — "지금 어디로 가면 돼?" 에 바로 답한다.
// 바깥 기온 → 가장 가까운 쉼터 한 곳(길찾기) → 자주 가는 곳 → 다른 쉼터 몇 곳.

import { router } from "expo-router";
import { useMemo } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { Analysis } from "../../analysis";
import { AlertCard } from "../../components/Alerts";
import { PlaceRow, TopCard } from "../../components/PlaceCard";
import { BigButton, Icon, Logo, T } from "../../components/ui";
import { UpdateBanner } from "../../components/UpdateBanner";
import { MODE_TITLE, nearestFirst, SHELTER_WORD, type SkyIcon } from "../../plain";
import { useStore } from "../../store";
import { type Mode, paletteFor, rainColor } from "../../theme";

const open = (a: Analysis) => router.push({ pathname: "/place/[id]", params: { id: a.place.id } });

export default function Home() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, mode } = s;
  const list = useMemo(() => nearestFirst(s.analyses), [s.analyses]);
  const [best, ...rest] = list;
  const favorites = s.settings.favorites.filter((f) => f.mode === mode).map(s.analyzePlace);

  return (
    <ScrollView style={{ backgroundColor: p.bg }} contentContainerStyle={[styles.page, { paddingTop: insets.top + 12 }]}>
      <UpdateBanner p={p} />
      <Logo p={p} subtitle={false} />

      <Weather />
      <AlertCard alerts={s.alerts} p={p} />
      <ModeSwitch />

      {!s.located && !!s.locationNotice && (
        <View style={[styles.notice, { borderColor: p.warn }]}>
          <T size={15} color={p.text} style={{ flex: 1 }}>
            {s.locationNotice}
          </T>
          <Pressable onPress={() => s.locate()} hitSlop={8}>
            <T size={15} weight="800" color={p.accent}>
              다시 찾기
            </T>
          </Pressable>
        </View>
      )}

      <T size={22} weight="800" color={p.text} style={styles.h2}>
        가장 가까운 {SHELTER_WORD[mode]}
      </T>
      {s.loading && !best ? (
        <View style={styles.center}>
          <ActivityIndicator color={p.accent} size="large" />
          <T size={16} color={p.textDim}>
            주변 쉼터를 찾고 있어요…
          </T>
        </View>
      ) : !best ? (
        <T size={16} color={p.textDim}>
          {s.error
            ? "쉼터 목록을 받지 못했어요. 인터넷 연결을 확인해 주세요."
            : "가까운 곳에 쉼터가 없어요. 지도에서 다른 곳을 찾아보세요."}
        </T>
      ) : (
        <>
          {!best.openNow && (
            <T size={16} weight="700" color={p.warn} style={{ marginBottom: 10 }}>
              지금 문을 연 쉼터가 주변에 없어요. 가장 가까운 곳을 보여 드려요.
            </T>
          )}
          <TopCard a={best} p={p} onOpen={() => open(best)} />
        </>
      )}

      {favorites.length > 0 && (
        <>
          <T size={20} weight="800" color={p.text} style={styles.h2}>
            자주 가는 곳
          </T>
          <View>
            {favorites.map((a) => (
              <PlaceRow key={a.place.id} a={a} p={p} onPress={() => open(a)} />
            ))}
          </View>
        </>
      )}

      {rest.length > 0 && (
        <>
          <T size={20} weight="800" color={p.text} style={styles.h2}>
            다른 쉼터
          </T>
          <View>
            {rest.slice(0, 5).map((a) => (
              <PlaceRow key={a.place.id} a={a} p={p} onPress={() => open(a)} />
            ))}
          </View>
          <BigButton
            text={`지도에서 모두 보기 (${list.length}곳)`}
            icon="map-outline"
            kind="secondary"
            p={p}
            onPress={() => router.navigate("/map")}
            style={{ marginTop: 12 }}
          />
        </>
      )}
    </ScrollView>
  );
}

/** 하늘 아이콘 → 머티리얼 아이콘 이름 */
const SKY_ICON: Record<Exclude<SkyIcon, "">, string> = {
  sunny: "weather-sunny",
  night: "weather-night",
  partly: "weather-partly-cloudy",
  partly_night: "weather-night-partly-cloudy",
  cloudy: "weather-cloudy",
  rain: "weather-rainy",
  sleet: "weather-snowy-rainy",
  snow: "weather-snowy",
};

/** 바깥 기온 · 하늘(비·눈·맑음) · 특보 */
function Weather() {
  const { p, weather: w, mode, sky } = useStore();
  const hot = mode === "cooling";
  const wet = sky.icon === "rain" || sky.icon === "sleet" || sky.icon === "snow";
  const rain = rainColor(p.dark);
  const iconColor = wet ? rain : sky.icon === "sunny" ? p.warn : sky.icon ? p.textDim : hot ? p.bad : p.accentBright;
  return (
    <View style={[styles.weather, { backgroundColor: p.card, borderColor: p.border }]}>
      <View style={styles.weatherRow}>
        <Icon name={sky.icon ? SKY_ICON[sky.icon] : hot ? "white-balance-sunny" : "snowflake"} size={44} color={iconColor} />
        <View style={{ flex: 1 }}>
          <T size={15} color={p.textDim}>
            지금 바깥
          </T>
          <View style={styles.tempRow}>
            <T size={34} weight="800" color={p.text}>
              {w.live ? `${w.outdoor.toFixed(0)}°C` : "확인 중"}
            </T>
            {!!sky.text && (
              <T size={20} weight="800" color={wet ? rain : p.text}>
                {sky.text}
              </T>
            )}
          </View>
        </View>
        {w.live && !!w.alert && (
          <View style={[styles.alert, { backgroundColor: p.warn }]}>
            <T size={15} weight="800" color={p.bg}>
              {w.alert}
            </T>
          </View>
        )}
      </View>
      {!!sky.hint && (
        <View style={[styles.hint, { backgroundColor: p.cardAlt }]}>
          <Icon name="umbrella-outline" size={22} color={rain} />
          <T size={16} weight="700" color={p.text} style={{ flex: 1 }}>
            {sky.hint}
          </T>
        </View>
      )}
    </View>
  );
}

/** 더위 피하기 / 추위 피하기 */
function ModeSwitch() {
  const s = useStore();
  return (
    <View style={styles.modes}>
      {(["cooling", "heating"] as Mode[]).map((m) => {
        const on = m === s.mode;
        const mp = paletteFor(m, s.settings.darkMode);
        return (
          <Pressable
            key={m}
            onPress={() => s.update({ mode: m })}
            accessibilityState={{ selected: on }}
            style={[styles.mode, { backgroundColor: on ? mp.accent : s.p.card, borderColor: on ? mp.accent : s.p.border }]}
          >
            <Icon name={m === "cooling" ? "snowflake" : "fire"} size={22} color={on ? mp.accentInk : s.p.textDim} />
            <T size={17} weight="800" color={on ? mp.accentInk : s.p.textDim}>
              {MODE_TITLE[m]}
            </T>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { paddingHorizontal: 16, paddingBottom: 36 },
  h2: { marginTop: 26, marginBottom: 12 },
  center: { alignItems: "center", gap: 10, paddingVertical: 24 },
  weather: {
    gap: 12,
    borderRadius: 20,
    borderWidth: 1,
    padding: 16,
    marginTop: 16,
  },
  weatherRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  tempRow: { flexDirection: "row", alignItems: "baseline", flexWrap: "wrap", columnGap: 12 },
  hint: { flexDirection: "row", alignItems: "center", gap: 10, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 10 },
  alert: { borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6 },
  modes: { flexDirection: "row", gap: 10, marginTop: 12 },
  mode: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    minHeight: 54,
    borderRadius: 16,
    borderWidth: 1.5,
  },
  notice: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1.5,
    borderRadius: 14,
    padding: 12,
    marginTop: 12,
  },
});
