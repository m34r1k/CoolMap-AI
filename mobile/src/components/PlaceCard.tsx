// 쉼터 카드. 점수 대신 '걸어서 몇 분 · 지금 열렸는지 · 얼마나 머물러도 되는지' 를 쉬운 말로 보여 준다.
//   TopCard  — 가장 먼저 갈 곳 (홈 · 지도에서 고른 곳). 큰 길찾기 버튼이 있다.
//   PlaceRow — 목록 한 줄. 누르면 상세로 간다.

import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";

import type { Analysis } from "../analysis";
import { categoryIcon, categoryLabel } from "../places";
import { openLine, stayLine, tags, tempLine, walkLine } from "../plain";
import { useStore } from "../store";
import type { Palette } from "../theme";
import { ReportNotice } from "./Report";
import { BigButton, Icon, InfoLine, T, Tag } from "./ui";

export function TopCard({
  a,
  p,
  onOpen,
  onClose,
}: {
  a: Analysis;
  p: Palette;
  onOpen: () => void;
  onClose?: () => void;
}) {
  const s = useStore();
  const open = a.openNow;
  return (
    <View style={[styles.top, { backgroundColor: p.card, borderColor: p.accent }]}>
      <Pressable onPress={onOpen} style={{ gap: 10 }}>
        <View style={styles.head}>
          <View style={[styles.catIcon, { backgroundColor: p.accentSoft }]}>
            <Icon name={categoryIcon(a.place)} size={24} color={p.accent} />
          </View>
          <View style={styles.fill}>
            <T size={21} weight="800" color={p.text} numberOfLines={2}>
              {a.place.name}
            </T>
            <T size={14} color={p.textDim}>
              {categoryLabel(a.place)}
            </T>
          </View>
          {onClose && (
            <Pressable onPress={onClose} hitSlop={14} accessibilityLabel="닫기">
              <Icon name="close" size={26} color={p.textMute} />
            </Pressable>
          )}
        </View>
        {tags(a).length > 0 && (
          <View style={styles.tags}>
            {tags(a).map((t) => (
              <Tag key={t.text} text={t.text} tone={t.tone} p={p} />
            ))}
          </View>
        )}
        <View style={{ gap: 8 }}>
          <ReportNotice placeId={a.place.id} p={p} />
          <InfoLine icon="walk" text={walkLine(a)} p={p} />
          <InfoLine
            icon="clock-outline"
            text={openLine(a, s.now)}
            p={p}
            color={open ? p.good : p.textMute}
          />
          {open && <InfoLine icon="thermometer" text={tempLine(a)} p={p} />}
          {open && <InfoLine icon="sofa-outline" text={stayLine(a)} p={p} />}
        </View>
      </Pressable>
      <View style={styles.actions}>
        <BigButton
          text="길찾기"
          icon="walk"
          p={p}
          onPress={() => router.push({ pathname: "/route/[id]", params: { id: a.place.id } })}
          style={styles.fill}
        />
        <BigButton text="자세히" p={p} kind="secondary" onPress={onOpen} />
      </View>
    </View>
  );
}

export function PlaceRow({ a, p, onPress }: { a: Analysis; p: Palette; onPress: () => void }) {
  const s = useStore();
  const open = a.openNow;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.row, { borderColor: p.border, backgroundColor: pressed ? p.cardAlt : "transparent" }]}
    >
      <View
        style={[
          styles.rowIcon,
          {
            backgroundColor: p.cardAlt,
            borderStyle: a.place.aiGuess ? "dashed" : "solid",
            borderColor: a.place.aiGuess ? p.warn : p.cardAlt,
          },
        ]}
      >
        <Icon name={categoryIcon(a.place)} size={20} color={open ? p.accent : p.textMute} />
      </View>
      <View style={styles.fill}>
        <T size={17} weight="700" color={open ? p.text : p.textDim} numberOfLines={1}>
          {a.place.name}
        </T>
        <T size={14} color={p.textDim} numberOfLines={1}>
          걸어서 {Math.max(1, a.walkMin)}분 ·{" "}
          <T size={14} weight="700" color={open ? p.good : p.textMute}>
            {open ? "지금 열림" : "문 닫음"}
          </T>
          {a.place.aiGuess ? " · AI 추정" : ""}
          {s.reports[a.place.id] && (
            <T size={14} weight="700" color={p.bad}>
              {" "}· 제보 있음
            </T>
          )}
        </T>
        {!open && (
          <T size={13} color={p.textMute} numberOfLines={1}>
            {openLine(a, s.now)}
          </T>
        )}
      </View>
      <Icon name="chevron-right" size={24} color={p.textMute} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  top: { borderRadius: 20, borderWidth: 2, padding: 16, gap: 14 },
  head: { flexDirection: "row", alignItems: "center", gap: 12 },
  catIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  actions: { flexDirection: "row", gap: 10 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    minHeight: 64,
    paddingVertical: 10,
    paddingHorizontal: 6,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderRadius: 10,
  },
  rowIcon: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", borderWidth: 1.5 },
});
