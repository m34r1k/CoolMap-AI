// 하단 탭 — 홈 · 지도 · 물어보기 · 설정. 즐겨찾기는 홈의 '자주 가는 곳' 에 있다.
// 데스크톱 사이드바(coolmap/ui/sidebar.py)와 같은 구성.

import { Tabs } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Icon, useFontScale } from "../../components/ui";
import { useStore } from "../../store";

const TABS: [string, string, string][] = [
  ["index", "홈", "home-variant"],
  ["map", "지도", "map-outline"],
  ["chat", "물어보기", "chat-question-outline"],
  ["settings", "설정", "cog-outline"],
];

export default function TabLayout() {
  const { p } = useStore();
  const k = useFontScale();
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: p.accent,
        tabBarInactiveTintColor: p.textDim,
        tabBarStyle: { backgroundColor: p.panel, borderTopColor: p.border, height: 68 + insets.bottom, paddingTop: 6 },
        tabBarLabelStyle: { fontSize: 14 * k, fontWeight: "700" },
        sceneStyle: { backgroundColor: p.bg },
      }}
    >
      {TABS.map(([name, title, icon]) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{ title, tabBarIcon: ({ color }) => <Icon name={icon} size={28} color={String(color)} /> }}
        />
      ))}
    </Tabs>
  );
}
