// 설정 — 자주 바꾸는 것(글씨 크기 · 쉼터 찾기 · 내 위치 · 업데이트)만 먼저 보이고,
// 목표 온도 · 데이터 상태 · 캐시는 '고급 설정' 을 펼쳐야 보인다. (coolmap/ui/settings_view.py)

import Constants from "expo-constants";
import { useEffect, useState } from "react";
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Switch, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { clearCandidateCache, judgeStats, MIN_CONFIDENCE } from "../../candidates";
import { BigButton, Card, Icon, T } from "../../components/ui";
import { clearNuisanceCache, nuisanceStatus } from "../../nuisance";
import { useStore } from "../../store";
import type { Palette } from "../../theme";
import { currentVersion, updatesSupported, useUpdate } from "../../update";

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, settings } = s;
  const [advanced, setAdvanced] = useState(false);

  return (
    <ScrollView style={{ backgroundColor: p.bg }} contentContainerStyle={[styles.page, { paddingTop: insets.top + 16 }]}>
      <T size={28} weight="800" color={p.text}>
        설정
      </T>

      <Section p={p} title="보기">
        <Toggle p={p} label="다크 모드" desc="어두운 화면으로 보여 줘요" value={settings.darkMode}
          onChange={(v) => s.update({ darkMode: v })} />
        <Toggle p={p} label="큰 글씨" desc="모든 글씨를 크게 보여 줘요" value={settings.bigText}
          onChange={(v) => s.update({ bigText: v })} />
      </Section>

      <Section p={p} title="쉼터 찾기">
        <Toggle p={p} label="공식 쉼터만 보기" desc="정부가 지정한 무더위·한파 쉼터만 보여 줘요"
          value={settings.onlyOfficial} onChange={(v) => s.update({ onlyOfficial: v })} />
        <Toggle p={p} label="AI 추정 쉼터도 보기"
          desc="도서관·마트처럼 쉼터로 등록되진 않았지만 쉬어 갈 만한 곳을 AI가 골라 함께 보여 줘요. 운영 여부는 현장에서 확인하세요."
          value={settings.aiCandidates} onChange={(v) => s.update({ aiCandidates: v })} />
        <Stepper p={p} label="걸어서 최대" value={settings.maxWalk} unit="분" min={5} max={60} step={5}
          onChange={(v) => s.update({ maxWalk: v })} />
        <Stepper p={p} label="찾는 범위" value={settings.searchRadius / 1000} unit="km" min={1} max={5} step={0.5}
          onChange={(v) => s.update({ searchRadius: Math.round(v * 1000) })} />
      </Section>

      <Section p={p} title="내 위치">
        <T size={16} color={s.located ? p.text : p.warn}>
          {s.located ? "내 위치를 찾았어요" : "내 위치를 찾지 못했어요 (서울시청 기준으로 보여 줘요)"}
        </T>
        {!!s.locationNotice && (
          <T size={15} color={p.warn}>
            {s.locationNotice}
          </T>
        )}
        <BigButton p={p} icon="crosshairs-gps" text="내 위치 다시 찾기" kind="secondary" onPress={() => s.locate()} />
      </Section>

      {updatesSupported && <UpdateSection p={p} />}

      <Pressable onPress={() => setAdvanced(!advanced)} style={[styles.more, { borderColor: p.border }]}>
        <T size={17} weight="700" color={p.textDim} style={{ flex: 1 }}>
          고급 설정
        </T>
        <Icon name={advanced ? "chevron-up" : "chevron-down"} size={24} color={p.textDim} />
      </Pressable>
      {advanced && <Advanced />}
    </ScrollView>
  );
}

function Advanced() {
  const s = useStore();
  const { p, settings } = s;
  const [judge, setJudge] = useState<[number, number]>([0, 0]);
  const nuis = nuisanceStatus();
  const acc = s.me ? ` · 정확도 ±${Math.round(s.me.accuracyM)}m` : "";

  useEffect(() => {
    judgeStats().then(setJudge);
  }, [s.aiCount, s.aiLoading]);

  return (
    <>
      <Section p={p} title="목표 온도" desc="목표 온도에 가까운 곳일수록 쾌적 점수가 높아져요.">
        <Stepper p={p} label="더위 피하기" value={settings.targetCool} unit="°C" min={16} max={30} step={1}
          onChange={(v) => s.update({ targetCool: v })} />
        <Stepper p={p} label="추위 피하기" value={settings.targetHeat} unit="°C" min={16} max={30} step={1}
          onChange={(v) => s.update({ targetHeat: v })} />
      </Section>

      <Section p={p} title="데이터 상태">
        <Status p={p} ok={!s.error} label="쉼터 (행정안전부)"
          value={s.error ? `오류: ${s.error}` : `${s.officialCount}곳 · CoolMap 서버`} />
        <Status p={p} ok={s.weather.live} label="날씨 (기상청)"
          value={s.weather.live ? `실측 ${s.weather.outdoor}°C · 습도 ${s.weather.humidity}%` : "실측값 없음"} />
        <Status p={p} ok={!nuis.error} label="민폐도 (Gemini)"
          value={nuis.error ? `규칙 기반으로 대체 중 — ${nuis.error}` : `유형 ${nuis.cached}종 저장 · 대기 ${nuis.pending}`} />
        <Status p={p} ok={settings.aiCandidates} label="AI 추정 쉼터"
          value={settings.aiCandidates
            ? `판단 ${judge[0]}곳 중 ${judge[1]}곳 인정 (확신 ${MIN_CONFIDENCE}% 이상) · 지금 ${s.aiCount}곳${s.aiLoading ? " · 판단 중…" : ""}`
            : "꺼짐"} />
        <Status p={p} ok={s.located} label="위치" value={s.located ? `GPS·Wi-Fi${acc}` : "기본값 (서울시청)"} />
        <BigButton p={p} icon="refresh" text="쉼터 새로 받기" kind="secondary" onPress={s.reload} />
        <BigButton p={p} icon="delete-outline" text="AI 판단 기록 지우기" kind="secondary" onPress={() =>
          Alert.alert("AI 판단 기록 지우기", "저장해 둔 민폐도·추정 쉼터 판단을 지웁니다. 다시 받는 동안 규칙 기반으로 표시됩니다.", [
            { text: "취소", style: "cancel" },
            { text: "지우기", style: "destructive", onPress: async () => {
              await Promise.all([clearNuisanceCache(), clearCandidateCache()]);
              s.reload();
            } },
          ])} />
      </Section>

      <Section p={p} title="CoolMap 정보">
        <T size={14} color={p.textDim}>
          CoolMap AI · 냉난방 쉼터 지도 ({Platform.OS === "ios" ? "iOS" : "Android"} {Constants.expoConfig?.version ?? ""}){"\n\n"}
          · 쉼터: 행정안전부 재난안전데이터공유플랫폼 (더위 피하기 = 무더위쉼터, 추위 피하기 = 한파쉼터){"\n"}
          · 날씨: 기상청 초단기실황 실측값{"\n"}
          · 지도: OpenFreeMap (OpenStreetMap){"\n"}
          · 민폐도·AI 추정 쉼터: Gemini 추정치이며 측정값이 아니에요. 서버에 연결할 수 없으면 규칙으로 계산해요.{"\n"}
          · 실내 온도는 시설 종류로 추정한 값이에요.
        </T>
      </Section>
    </>
  );
}

function UpdateSection({ p }: { p: Palette }) {
  const { update, state, check, install } = useUpdate();
  const busy = state === "checking" || state === "downloading";
  const status =
    state === "checking" ? "확인하는 중…"
    : state === "downloading" ? "받는 중… 끝나면 설치 화면이 열려요"
    : state === "error" && update ? "받지 못했어요. 다시 눌러 주세요"
    : state === "error" ? "확인하지 못했어요. 인터넷 연결을 확인해 주세요"
    : update ? `새 버전 ${update.version}이 있어요 (${update.sizeMB.toFixed(0)}MB)`
    : state === "latest" ? "최신 버전이에요"
    : "";
  return (
    <Section p={p} title="앱 업데이트" desc={`지금 버전 ${currentVersion}`}>
      {!!status && (
        <T size={16} color={update ? p.accent : p.textDim}>
          {status}
        </T>
      )}
      <BigButton
        p={p}
        kind={update ? "primary" : "secondary"}
        icon={update ? "download" : "refresh"}
        text={update ? "업데이트 설치" : "업데이트 확인"}
        busy={busy}
        onPress={update ? install : check}
      />
    </Section>
  );
}

function Section({ p, title, desc, children }: { p: Palette; title: string; desc?: string; children: React.ReactNode }) {
  return (
    <Card p={p} style={{ marginTop: 16, gap: 14 }}>
      <T size={19} weight="800" color={p.text}>
        {title}
      </T>
      {desc && (
        <T size={14} color={p.textMute}>
          {desc}
        </T>
      )}
      {children}
    </Card>
  );
}

function Toggle({ p, label, desc, value, onChange }: {
  p: Palette; label: string; desc?: string; value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <Pressable onPress={() => onChange(!value)} style={styles.row} accessibilityRole="switch" accessibilityState={{ checked: value }}>
      <View style={{ flex: 1, gap: 2 }}>
        <T size={17} weight="700" color={p.text}>
          {label}
        </T>
        {desc && (
          <T size={14} color={p.textDim}>
            {desc}
          </T>
        )}
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: p.accentDeep, false: p.cardAlt }} thumbColor={value ? p.accent : p.textMute} />
    </Pressable>
  );
}

function Stepper({ p, label, value, unit, min, max, step, onChange }: {
  p: Palette; label: string; value: number; unit: string; min: number; max: number; step: number; onChange: (v: number) => void;
}) {
  const set = (v: number) => onChange(Math.max(min, Math.min(max, Math.round(v / step) * step)));
  return (
    <View style={styles.row}>
      <T size={17} weight="700" color={p.text} style={{ flex: 1 }}>
        {label}
      </T>
      <Pressable onPress={() => set(value - step)} accessibilityLabel={`${label} 줄이기`} style={[styles.step, { borderColor: p.border }]}>
        <Icon name="minus" size={22} color={p.text} />
      </Pressable>
      <T size={18} weight="800" color={p.accent} style={styles.stepValue}>
        {value}
        {unit}
      </T>
      <Pressable onPress={() => set(value + step)} accessibilityLabel={`${label} 늘리기`} style={[styles.step, { borderColor: p.border }]}>
        <Icon name="plus" size={22} color={p.text} />
      </Pressable>
    </View>
  );
}

function Status({ p, ok, label, value }: { p: Palette; ok: boolean; label: string; value: string }) {
  return (
    <View style={styles.status}>
      <Icon name={ok ? "check-circle" : "alert-circle-outline"} size={20} color={ok ? p.good : p.warn} />
      <View style={{ flex: 1 }}>
        <T size={16} weight="700" color={p.text}>
          {label}
        </T>
        <T size={14} color={p.textDim}>
          {value}
        </T>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { paddingHorizontal: 16, paddingBottom: 40 },
  row: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 48 },
  step: { width: 48, height: 48, borderRadius: 24, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  stepValue: { minWidth: 64, textAlign: "center" },
  status: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  more: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderRadius: 14, padding: 14, minHeight: 54, marginTop: 16 },
});
