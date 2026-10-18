// 장소 상세 — 이름 → 길찾기 → 꼭 필요한 정보(걸리는 시간 · 운영 · 온도 · 머물기) 순서.
// 점수(쾌적 · 민폐도)와 계산 근거는 '자세히 보기' 를 눌러야 펼쳐진다.

import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { stayLabel } from "../../analysis";
import { BigButton, Card, Gauge, Icon, InfoLine, MeterBar, T, Tag } from "../../components/ui";
import { categoryIcon, categoryLabel, hoursLabel } from "../../places";
import { openLine, stayLine, tags, tempCompare, tempLine, walkLine } from "../../plain";
import { useStore } from "../../store";
import { nuisanceColor, paletteFor } from "../../theme";

export default function Detail() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStore();
  const [more, setMore] = useState(false);
  const place = s.getPlace(String(id));

  if (!place) {
    return (
      <View style={[styles.fill, styles.center, { backgroundColor: s.p.bg }]}>
        <T size={17} color={s.p.textDim}>
          장소를 찾을 수 없어요.
        </T>
        <BigButton text="돌아가기" p={s.p} kind="secondary" onPress={() => router.back()} style={{ marginTop: 16 }} />
      </View>
    );
  }

  // 즐겨찾기로 들어오면 현재 모드와 다른 쉼터일 수 있다 — 장소 자신의 모드로 보여 준다
  const p = paletteFor(place.mode, s.settings.darkMode);
  const a = s.analyzePlace(place);
  const nc = nuisanceColor(p, a.nuisance.key);
  const fav = s.isFavorite(place.id);
  const open = a.openNow;
  const compare = tempCompare(a);

  return (
    <ScrollView
      style={{ backgroundColor: p.bg }}
      contentContainerStyle={[styles.page, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 32 }]}
    >
      <Pressable onPress={() => router.back()} hitSlop={10} style={styles.back}>
        <Icon name="arrow-left" size={26} color={p.text} />
        <T size={17} weight="700" color={p.text}>
          뒤로
        </T>
      </Pressable>

      <View style={styles.row}>
        <Icon name={categoryIcon(place)} size={22} color={p.accent} />
        <T size={16} weight="700" color={p.accent}>
          {categoryLabel(place)}
        </T>
      </View>
      <T size={27} weight="800" color={p.text}>
        {place.name}
      </T>
      {!!place.address && (
        <T size={15} color={p.textDim}>
          {place.address}
        </T>
      )}
      {tags(a).length > 0 && (
        <View style={styles.tags}>
          {tags(a).map((t) => (
            <Tag key={t.text} text={t.text} tone={t.tone} p={p} />
          ))}
        </View>
      )}

      <BigButton
        text="길찾기"
        icon="walk"
        p={p}
        onPress={() => router.push({ pathname: "/route/[id]", params: { id: place.id } })}
        style={{ marginTop: 6 }}
      />

      <Card p={p} style={styles.infoCard}>
        <InfoLine icon="walk" text={walkLine(a)} p={p} />
        <InfoLine icon="clock-outline" text={openLine(a, s.now)} p={p} color={open ? p.good : p.textMute} />
        <T size={14} color={p.textDim} style={styles.indent}>
          운영 시간 {hoursLabel(place)}
        </T>
        <InfoLine icon="thermometer" text={compare ? `${tempLine(a)} · ${compare}` : tempLine(a)} p={p} />
        <InfoLine icon="sofa-outline" text={stayLine(a)} p={p} />
      </Card>

      {a.nuisance.tips.length > 0 && (
        <Card p={p} style={{ gap: 8 }}>
          <T size={18} weight="800" color={p.text}>
            머물 때 알아 두세요
          </T>
          {a.nuisance.tips.map((t) => (
            <T key={t} size={16} color={p.textDim}>
              · {t}
            </T>
          ))}
        </Card>
      )}

      {place.amenities.length > 0 && (
        <Card p={p} style={{ gap: 10 }}>
          <T size={18} weight="800" color={p.text}>
            시설 정보
          </T>
          <View style={styles.tags}>
            {place.amenities.map((t) => (
              <View key={t} style={[styles.amenity, { backgroundColor: p.cardAlt, borderColor: p.border }]}>
                <T size={14} color={p.textDim}>
                  {t}
                </T>
              </View>
            ))}
          </View>
        </Card>
      )}

      <View style={styles.actions}>
        <BigButton
          text={fav ? "자주 가는 곳 ✓" : "자주 가는 곳에 저장"}
          icon={fav ? "heart" : "heart-outline"}
          p={p}
          kind="secondary"
          onPress={() => s.toggleFavorite(place)}
          style={styles.fill}
        />
        <BigButton
          text="지도"
          icon="map-outline"
          p={p}
          kind="secondary"
          onPress={() => router.navigate({ pathname: "/map", params: { focus: place.id } })}
        />
      </View>

      {/* 점수와 근거 — 궁금한 사람만 펼쳐 본다 */}
      <Pressable onPress={() => setMore(!more)} style={[styles.more, { borderColor: p.border }]}>
        <T size={16} weight="700" color={p.textDim} style={styles.fill}>
          {more ? "자세히 보기 닫기" : "자세히 보기 (점수 · 근거)"}
        </T>
        <Icon name={more ? "chevron-up" : "chevron-down"} size={24} color={p.textDim} />
      </Pressable>
      {more && (
        <Card p={p} style={{ gap: 14 }}>
          <View style={{ gap: 6 }}>
            <T size={15} weight="700" color={p.textDim}>
              쾌적 점수 (목표 온도·습도·바람을 종합)
            </T>
            <T size={30} weight="800" color={p.accent}>
              {a.comfort}
              <T size={15} color={p.textMute}>
                {" "}
                / 100
              </T>
            </T>
            <MeterBar value={a.comfort / 100} color={p.accent} track={p.cardAlt} height={8} />
          </View>
          <View style={{ alignItems: "center", gap: 4 }}>
            <T size={15} weight="700" color={p.textDim}>
              민폐도 (오래 머물 때 눈치 보이는 정도)
            </T>
            <Gauge value={a.nuisance.score} label={a.nuisance.level} color={nc} track={p.cardAlt} textColor={p.text} muteColor={p.textMute} size={160} />
            <T size={15} color={p.textDim}>
              권장 체류 {stayLabel(a.nuisance.stayMinutes)}
            </T>
          </View>
          {!!a.nuisance.reason && (
            <T size={15} color={p.textDim}>
              {a.nuisance.reason}
            </T>
          )}
          {a.nuisance.source !== "gemini" &&
            a.nuisance.factors.map(([name, value]) => (
              <View key={name} style={styles.factor}>
                <T size={14} color={p.textMute} style={styles.factorName}>
                  {name}
                </T>
                <View style={styles.fill}>
                  <MeterBar value={Math.min(1, Math.abs(value) / 40)} color={value < 0 ? p.good : nc} track={p.cardAlt} />
                </View>
                <T size={14} weight="700" color={value < 0 ? p.good : nc} style={styles.factorValue}>
                  {value > 0 ? `+${value}` : String(value)}
                </T>
              </View>
            ))}
          <T size={15} color={p.textDim}>
            체감 {a.feelsInside.toFixed(1)}°C · 습도 {place.humidity}% · 바람 {place.airflow}
          </T>
          {!!place.why && (
            <T size={15} color={p.textDim}>
              {place.why}
            </T>
          )}
          <T size={13} color={p.textMute}>
            실내 온도와 점수는 추정치예요.{" "}
            {a.nuisance.source === "gemini" ? "민폐도는 Gemini가 추정했어요." : "민폐도는 규칙으로 계산했어요."}
          </T>
        </Card>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: "center", justifyContent: "center", padding: 24 },
  page: { paddingHorizontal: 16, gap: 12 },
  back: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", paddingVertical: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  infoCard: { gap: 12 },
  indent: { marginLeft: 30, marginTop: -8 },
  amenity: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  actions: { flexDirection: "row", gap: 10 },
  more: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderRadius: 14, padding: 14, minHeight: 54 },
  factor: { flexDirection: "row", alignItems: "center", gap: 10 },
  factorName: { width: 110 },
  factorValue: { width: 38, textAlign: "right" },
});
