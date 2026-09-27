// 설정 화면 — coolmap/ui/settings_view.py 에서 모바일에 맞는 항목만.

import Constants from "expo-constants";
import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { clearCandidateCache, judgeStats, MIN_CONFIDENCE } from "../../candidates";
import { Card, Icon } from "../../components/ui";
import { clearNuisanceCache, nuisanceStatus } from "../../nuisance";
import { useStore } from "../../store";
import type { Palette } from "../../theme";
import { currentVersion, updatesSupported, useUpdate } from "../../update";

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, settings } = s;
  const [judge, setJudge] = useState<[number, number]>([0, 0]);
  const nuis = nuisanceStatus();

  useEffect(() => {
    judgeStats().then(setJudge);
  }, [s.aiCount, s.aiLoading]);

  const acc = s.me ? ` · 정확도 ±${Math.round(s.me.accuracyM)}m` : "";

  return (
    <ScrollView style={{ backgroundColor: p.bg }} contentContainerStyle={[styles.page, { paddingTop: insets.top + 16 }]}>
      <Text style={[styles.h1, { color: p.text }]}>설정</Text>

      <Section p={p} title="모드 · 목표 온도" desc="목표 온도에 가까울수록 쾌적 점수가 높아집니다.">
        <Stepper p={p} label="냉방 목표 온도" value={settings.targetCool} unit="°C" min={16} max={30} step={1}
          onChange={(v) => s.update({ targetCool: v })} />
        <Stepper p={p} label="난방 목표 온도" value={settings.targetHeat} unit="°C" min={16} max={30} step={1}
          onChange={(v) => s.update({ targetHeat: v })} />
      </Section>

      <Section p={p} title="추천 필터">
        <Toggle p={p} label="공식 지정 무더위·한파 쉼터만 보기" value={settings.onlyOfficial}
          onChange={(v) => s.update({ onlyOfficial: v })} />
        <Toggle p={p} label="지도에 이름이 있는 곳을 AI로 추가 판단" value={settings.aiCandidates}
          onChange={(v) => s.update({ aiCandidates: v })} />
        <Text style={[styles.desc, { color: p.textMute }]}>
          하나로마트·도서관처럼 지도에 상호는 떠 있지만 공식 쉼터로 등록되지 않은 곳을 Gemini가 판단해
          빈 원으로 함께 표시합니다. 확신도 {MIN_CONFIDENCE}% 미만은 표시하지 않습니다. 추정이므로 운영시간과
          이용 가능 여부는 현장에서 확인하세요.
        </Text>
        <Stepper p={p} label="최대 도보 시간" value={settings.maxWalk} unit="분" min={5} max={60} step={5}
          onChange={(v) => s.update({ maxWalk: v })} />
        <Stepper p={p} label="쉼터 검색 반경" value={settings.searchRadius / 1000} unit="km" min={1} max={5} step={0.5}
          onChange={(v) => s.update({ searchRadius: Math.round(v * 1000) })} />
        <Text style={[styles.desc, { color: p.textMute }]}>
          전국 11만여 곳 중 현재 위치 주변만 불러옵니다. 넓힐수록 목록이 길어집니다.
        </Text>
      </Section>

      <Section p={p} title="현재 위치">
        <Text style={[styles.value, { color: p.textDim }]}>
          {s.located ? `GPS·Wi-Fi 위치${acc}` : "기본값 (서울시청)"}
        </Text>
        {!!s.locationNotice && <Text style={[styles.desc, { color: p.warn }]}>{s.locationNotice}</Text>}
        <Button p={p} icon="crosshairs-gps" text="현재 위치 다시 확인" onPress={() => s.locate()} />
      </Section>

      <Section p={p} title="데이터 연동 상태">
        <Status p={p} ok={!s.error} label="쉼터 (행정안전부)"
          value={s.error ? `오류: ${s.error}` : `${s.officialCount}곳 · CoolMap 서버`} />
        <Status p={p} ok={s.weather.live} label="날씨 (기상청)"
          value={s.weather.live ? `실측 ${s.weather.outdoor}°C · 습도 ${s.weather.humidity}%` : "실측값 없음"} />
        <Status p={p} ok={!nuis.error} label="민폐도 (Gemini)"
          value={nuis.error ? `규칙 기반으로 대체 중 — ${nuis.error}` : `유형 ${nuis.cached}종 캐시 · 대기 ${nuis.pending}`} />
        <Status p={p} ok={settings.aiCandidates} label="AI 추정 쉼터"
          value={settings.aiCandidates ? `판단 ${judge[0]}곳 중 ${judge[1]}곳 인정 · 지금 ${s.aiCount}곳 표시${s.aiLoading ? " · 판단 중…" : ""}` : "꺼짐"} />
        <View style={styles.buttons}>
          <Button p={p} icon="refresh" text="쉼터 새로 받기" onPress={s.reload} />
          <Button p={p} icon="delete-outline" text="AI 판단 캐시 비우기" onPress={() =>
            Alert.alert("AI 판단 캐시 비우기", "저장해 둔 민폐도·추정 쉼터 판단을 지웁니다. 다시 받는 동안 규칙 기반으로 표시됩니다.", [
              { text: "취소", style: "cancel" },
              { text: "비우기", style: "destructive", onPress: async () => {
                await Promise.all([clearNuisanceCache(), clearCandidateCache()]);
                s.reload();
              } },
            ])} />
        </View>
      </Section>

      {updatesSupported && <UpdateSection p={p} />}

      <Section p={p} title="CoolMap 정보">
        <Text style={[styles.desc, { color: p.textDim }]}>
          CoolMap AI · 냉난방 쉼터 지도 ({Platform.OS === "ios" ? "iOS" : "Android"} {Constants.expoConfig?.version ?? ""}){"\n\n"}
          · 지도: OpenFreeMap(OpenStreetMap) 벡터 타일과 건물 외곽선을 사용합니다.{"\n"}
          · 날씨: 기상청 초단기실황의 실측값입니다.{"\n"}
          · 민폐도: Gemini가 시설 성격·구매 필요 여부·규모·공식 쉼터 지정 여부를 근거로 0~100으로 추정합니다.
          측정값이 아닌 추정치이며, 서버에 연결할 수 없으면 규칙 기반으로 계산합니다.{"\n"}
          · 혼잡도: 실시간 인구 데이터 연동 전이라 비활성 상태입니다.{"\n"}
          · 쉼터: 행정안전부 재난안전데이터공유플랫폼을 사용합니다. 냉방 모드는 무더위쉼터, 난방 모드는 한파쉼터입니다.
        </Text>
      </Section>
    </ScrollView>
  );
}

function UpdateSection({ p }: { p: Palette }) {
  const { update, state, check, install } = useUpdate();
  const status =
    state === "checking" ? "확인하는 중…"
    : state === "downloading" ? "받는 중… 끝나면 설치 화면이 열립니다"
    : state === "error" && update ? "받지 못했습니다. 다시 눌러 주세요"
    : state === "error" ? "확인하지 못했습니다. 인터넷 연결을 확인해 주세요"
    : update ? `새 버전 ${update.version} 이 있습니다 (${update.sizeMB.toFixed(0)}MB)`
    : state === "latest" ? "최신 버전입니다"
    : "";
  return (
    <Section p={p} title="앱 업데이트" desc={`지금 버전 ${currentVersion}. 새 버전은 GitHub 에서 받아 바로 설치합니다.`}>
      {!!status && <Text style={[styles.desc, { color: update ? p.accent : p.textDim }]}>{status}</Text>}
      <Pressable
        onPress={update ? install : check}
        disabled={state === "checking" || state === "downloading"}
        style={[styles.updateBtn, { backgroundColor: update ? p.accent : "transparent", borderColor: update ? p.accent : p.border }]}
      >
        {(state === "checking" || state === "downloading") && <ActivityIndicator color={update ? p.accentInk : p.accent} />}
        <Text style={[styles.updateText, { color: update ? p.accentInk : p.text }]}>
          {update ? "업데이트 설치" : "업데이트 확인"}
        </Text>
      </Pressable>
    </Section>
  );
}

function Section({ p, title, desc, children }: { p: Palette; title: string; desc?: string; children: React.ReactNode }) {
  return (
    <Card p={p} style={{ marginTop: 16, gap: 12 }}>
      <Text style={[styles.title, { color: p.text }]}>{title}</Text>
      {desc && <Text style={[styles.desc, { color: p.textMute }]}>{desc}</Text>}
      {children}
    </Card>
  );
}

function Toggle({ p, label, value, onChange }: { p: Palette; label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={styles.row}>
      <Text style={[styles.label, { color: p.text }]}>{label}</Text>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: p.accentDeep, false: p.cardAlt }} thumbColor={value ? p.accent : p.textMute} />
    </View>
  );
}

function Stepper({ p, label, value, unit, min, max, step, onChange }: {
  p: Palette; label: string; value: number; unit: string; min: number; max: number; step: number; onChange: (v: number) => void;
}) {
  const set = (v: number) => onChange(Math.max(min, Math.min(max, Math.round(v / step) * step)));
  return (
    <View style={styles.row}>
      <Text style={[styles.label, { color: p.text }]}>{label}</Text>
      <Pressable onPress={() => set(value - step)} style={[styles.step, { borderColor: p.border }]}>
        <Icon name="minus" size={18} color={p.text} />
      </Pressable>
      <Text style={[styles.stepValue, { color: p.accent }]}>{value}{unit}</Text>
      <Pressable onPress={() => set(value + step)} style={[styles.step, { borderColor: p.border }]}>
        <Icon name="plus" size={18} color={p.text} />
      </Pressable>
    </View>
  );
}

function Status({ p, ok, label, value }: { p: Palette; ok: boolean; label: string; value: string }) {
  return (
    <View style={styles.status}>
      <Icon name={ok ? "check-circle" : "alert-circle-outline"} size={18} color={ok ? p.good : p.warn} />
      <View style={{ flex: 1 }}>
        <Text style={[styles.label, { color: p.text }]}>{label}</Text>
        <Text style={[styles.desc, { color: p.textDim }]}>{value}</Text>
      </View>
    </View>
  );
}

function Button({ p, icon, text, onPress }: { p: Palette; icon: string; text: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.button, { borderColor: p.border, backgroundColor: p.cardAlt }]}>
      <Icon name={icon} size={18} color={p.accent} />
      <Text style={[styles.buttonText, { color: p.text }]}>{text}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  page: { paddingHorizontal: 16, paddingBottom: 32 },
  updateBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderWidth: 1,
    borderRadius: 12,
    paddingVertical: 11,
  },
  updateText: { fontSize: 14, fontWeight: "700" },
  h1: { fontSize: 28, fontWeight: "800" },
  title: { fontSize: 17, fontWeight: "800" },
  desc: { fontSize: 12, lineHeight: 18 },
  value: { fontSize: 14 },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  label: { flex: 1, fontSize: 14, fontWeight: "600" },
  step: { width: 36, height: 36, borderRadius: 18, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  stepValue: { minWidth: 56, textAlign: "center", fontSize: 15, fontWeight: "800" },
  status: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  buttons: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  button: { flexDirection: "row", alignItems: "center", gap: 6, borderRadius: 12, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 9 },
  buttonText: { fontSize: 13, fontWeight: "700" },
});
