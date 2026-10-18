// 쉼터 제보 — 사이렌 버튼을 누르면 '어떤 문제가 있나요?' 를 큰 버튼으로 고른다 (supabase/functions/report).
// 버튼 여러 개를 늘어놓는 대신 사이렌 하나로 '문제를 알린다' 는 뜻을 전한다.

import { useState } from "react";
import { ActivityIndicator, Alert, Modal, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { ReportKind } from "../backend";
import { REPORT_KINDS, reportLine } from "../plain";
import { useStore } from "../store";
import type { Palette } from "../theme";
import { Icon, InfoLine, T } from "./ui";

/** 사이렌 아이콘 + '알리기'. 누르면 제보 창이 뜬다. */
export function SirenButton({ placeId, placeName, p }: { placeId: string; placeName: string; p: Palette }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        hitSlop={10}
        accessibilityLabel="이 쉼터 문제 알리기"
        style={({ pressed }) => [styles.siren, { opacity: pressed ? 0.6 : 1 }]}
      >
        <Icon name="alarm-light-outline" size={30} color={p.bad} />
        <T size={12} weight="700" color={p.bad}>
          알리기
        </T>
      </Pressable>
      {open && <ReportSheet placeId={placeId} placeName={placeName} p={p} onClose={() => setOpen(false)} />}
    </>
  );
}

function ReportSheet({ placeId, placeName, p, onClose }: { placeId: string; placeName: string; p: Palette; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const [busy, setBusy] = useState<ReportKind | null>(null);
  const current = s.reports[placeId];

  const send = async (kind: ReportKind) => {
    setBusy(kind);
    try {
      await s.report(placeId, kind);
      onClose();
      Alert.alert(
        "알려 주셔서 고마워요",
        kind === "ok" ? "다른 분들께 '지금은 괜찮아요' 로 보여 드릴게요." : "다른 분들께도 함께 보여 드릴게요.\n잘못 눌렀다면 '내 제보 취소' 를 누르세요.",
      );
    } catch (e) {
      setBusy(null);
      Alert.alert("알리지 못했어요", e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={[styles.sheet, { backgroundColor: p.card, borderColor: p.border, paddingBottom: insets.bottom + 16 }]}>
        <View style={styles.head}>
          <Icon name="alarm-light" size={28} color={p.bad} />
          <T size={20} weight="800" color={p.text} style={styles.fill}>
            어떤 문제가 있나요?
          </T>
        </View>
        <T size={15} color={p.textDim} numberOfLines={2}>
          {placeName}
        </T>
        {/* 문제 제보가 올라와 있으면, 현장에서 괜찮은 걸 본 사람이 풀어 줄 수 있다 */}
        {current && current.kind !== "ok" && (
          <Pressable
            disabled={busy !== null}
            onPress={() => send("ok")}
            style={({ pressed }) => [
              styles.option,
              { borderColor: p.good, backgroundColor: pressed ? p.cardAlt : p.card, opacity: busy && busy !== "ok" ? 0.5 : 1 },
            ]}
          >
            <Icon name="check-circle-outline" size={26} color={p.good} />
            <T size={18} weight="700" color={p.text} style={styles.fill}>
              지금은 괜찮아요
            </T>
            {busy === "ok" && <ActivityIndicator color={p.good} />}
          </Pressable>
        )}
        {REPORT_KINDS.map((k) => (
          <Pressable
            key={k.kind}
            disabled={busy !== null}
            onPress={() => send(k.kind)}
            style={({ pressed }) => [
              styles.option,
              { borderColor: p.border, backgroundColor: pressed ? p.cardAlt : p.card, opacity: busy && busy !== k.kind ? 0.5 : 1 },
            ]}
          >
            <Icon name={k.icon} size={26} color={p.bad} />
            <T size={18} weight="700" color={p.text} style={styles.fill}>
              {k.label}
            </T>
            {busy === k.kind && <ActivityIndicator color={p.bad} />}
          </Pressable>
        ))}
        <Pressable onPress={onClose} style={[styles.option, styles.cancel, { borderColor: p.border }]}>
          <T size={17} weight="700" color={p.textDim}>
            취소
          </T>
        </Pressable>
      </View>
    </Modal>
  );
}

/** 최근 제보 한 줄 — 문제는 빨강, '지금은 괜찮아요' 는 초록. 내가 보낸 제보면 취소 버튼을 붙인다 */
export function ReportNotice({ placeId, p }: { placeId: string; p: Palette }) {
  const s = useStore();
  const [busy, setBusy] = useState(false);
  const r = s.reports[placeId];
  const mine = s.myReport(placeId);
  if (!r && !mine) return null;
  const cancel = () =>
    Alert.alert("내 제보 취소", "이 쉼터에 보낸 제보를 취소할까요?", [
      { text: "아니요", style: "cancel" },
      {
        text: "취소하기",
        style: "destructive",
        onPress: async () => {
          setBusy(true);
          try {
            await s.cancelMyReport(placeId);
          } catch (e) {
            Alert.alert("취소하지 못했어요", e instanceof Error ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        },
      },
    ]);
  return (
    <View style={{ gap: 6 }}>
      {r && (
        <InfoLine
          icon={r.kind === "ok" ? "check-circle" : "alarm-light"}
          text={reportLine(r)}
          p={p}
          color={r.kind === "ok" ? p.good : p.bad}
        />
      )}
      {mine && (
        <Pressable onPress={cancel} disabled={busy} hitSlop={8} style={styles.cancelMine}>
          {busy ? <ActivityIndicator size="small" color={p.textDim} /> : <Icon name="undo" size={18} color={p.textDim} />}
          <T size={14} weight="700" color={p.textDim}>
            내 제보 취소
          </T>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  siren: { alignItems: "center", justifyContent: "center", minWidth: 48 },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)" },
  sheet: { borderTopLeftRadius: 22, borderTopRightRadius: 22, borderWidth: 1, padding: 18, gap: 12 },
  head: { flexDirection: "row", alignItems: "center", gap: 10 },
  option: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    minHeight: 58,
    borderWidth: 1.5,
    borderRadius: 16,
    paddingHorizontal: 16,
  },
  cancel: { justifyContent: "center" },
  cancelMine: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", marginLeft: 30, paddingVertical: 4 },
});
