// 홈 화면 맨 위 '새 버전' 알림. 새 버전이 있을 때만 보인다 (Android).

import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import type { Palette } from "../theme";
import { useUpdate } from "../update";
import { Icon } from "./ui";

export function UpdateBanner({ p }: { p: Palette }) {
  const { update, state, install } = useUpdate();
  if (!update) return null;
  const busy = state === "downloading";
  return (
    <Pressable
      onPress={install}
      disabled={busy}
      style={[styles.banner, { backgroundColor: p.accentSoft, borderColor: p.accent }]}
    >
      <Icon name="download-circle" size={26} color={p.accent} />
      <View style={styles.fill}>
        <Text style={[styles.title, { color: p.text }]}>새 버전 {update.version} 이 있어요</Text>
        <Text style={[styles.desc, { color: p.textDim }]}>
          {busy
            ? "받는 중… 끝나면 설치 화면이 열립니다"
            : state === "error"
              ? "받지 못했어요. 눌러서 다시 시도하세요"
              : `눌러서 업데이트 (${update.sizeMB.toFixed(0)}MB)`}
        </Text>
      </View>
      {busy && <ActivityIndicator color={p.accent} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
    marginBottom: 14,
  },
  fill: { flex: 1 },
  title: { fontSize: 15, fontWeight: "800" },
  desc: { fontSize: 12, marginTop: 2 },
});
