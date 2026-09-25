// 하단 탭 — 데스크톱 사이드바(홈 · 지도 · 즐겨찾기 · AI 추천 · 설정)와 같은 구성.

import { Tabs } from "expo-router";

import { Icon } from "../../components/ui";
import { useStore } from "../../store";

const TABS: [string, string, string][] = [
  ["index", "홈", "home-variant"],
  ["map", "지도", "map-outline"],
  ["favorites", "즐겨찾기", "heart-outline"],
  ["chat", "AI 추천", "creation"],
  ["settings", "설정", "cog-outline"],
];

export default function TabLayout() {
  const { p } = useStore();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: p.accent,
        tabBarInactiveTintColor: p.textMute,
        tabBarStyle: { backgroundColor: p.panel, borderTopColor: p.border },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "700" },
        sceneStyle: { backgroundColor: p.bg },
      }}
    >
      {TABS.map(([name, title, icon]) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{ title, tabBarIcon: ({ color }) => <Icon name={icon} size={24} color={String(color)} /> }}
        />
      ))}
    </Tabs>
  );
}
