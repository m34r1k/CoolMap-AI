// 즐겨찾기 화면 — coolmap/ui/favorites.py

import { router } from "expo-router";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { PlaceCard } from "../../components/PlaceCard";
import { Icon } from "../../components/ui";
import { useStore } from "../../store";
import { MODE_LABEL, PALETTES } from "../../theme";

export default function Favorites() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, mode } = s;
  const favs = s.settings.favorites;
  const other = favs.filter((f) => f.mode !== mode).length;

  return (
    <ScrollView style={{ backgroundColor: p.bg }} contentContainerStyle={[styles.page, { paddingTop: insets.top + 16 }]}>
      <View style={styles.head}>
        <Text style={[styles.h1, { color: p.text }]}>즐겨찾기</Text>
        <Text style={[styles.count, { color: p.textMute }]}>{favs.length}곳</Text>
      </View>
      <Text style={[styles.sub, { color: p.textDim }]}>
        자주 가는 쉼터를 모아 실시간 상태를 확인하세요.
        {other ? ` (${other}곳은 ${MODE_LABEL[mode === "cooling" ? "heating" : "cooling"]} 모드 쉼터라 그 모드 기준으로 표시됩니다)` : ""}
      </Text>

      {!favs.length ? (
        <View style={[styles.empty, { borderColor: p.border }]}>
          <Icon name="heart-outline" size={40} color={p.textMute} />
          <Text style={[styles.emptyTitle, { color: p.text }]}>아직 즐겨찾기가 없어요</Text>
          <Text style={[styles.sub, { color: p.textDim, textAlign: "center" }]}>
            장소 상세 화면이나 추천 카드의 하트 버튼을 눌러 추가해 보세요.
          </Text>
        </View>
      ) : (
        <View style={{ gap: 14, marginTop: 16 }}>
          {favs.map((f) => {
            const a = s.analyzePlace(f);
            return (
              <PlaceCard
                key={f.id}
                a={a}
                p={PALETTES[f.mode]}
                favorite
                onOpen={() => router.push({ pathname: "/place/[id]", params: { id: f.id } })}
                onFavorite={() => s.toggleFavorite(f)}
              />
            );
          })}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { paddingHorizontal: 16, paddingBottom: 32 },
  head: { flexDirection: "row", alignItems: "baseline", gap: 10 },
  h1: { fontSize: 28, fontWeight: "800" },
  count: { fontSize: 13, fontWeight: "700" },
  sub: { fontSize: 13, marginTop: 6, lineHeight: 19 },
  empty: { marginTop: 30, borderWidth: 1, borderStyle: "dashed", borderRadius: 18, padding: 28, alignItems: "center", gap: 8 },
  emptyTitle: { fontSize: 17, fontWeight: "800" },
});
