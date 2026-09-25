// AI 추천 화면 — coolmap/ui/chat.py (CoolMap Intelligence)

import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { type Analysis, analysisDistance, clockLabel } from "../../analysis";
import { type ChatReply, greeting, QUICK_PROMPTS, respond } from "../../assistant";
import { Icon, RichText } from "../../components/ui";
import { categoryIcon } from "../../places";
import { useStore } from "../../store";
import { nuisanceColor } from "../../theme";

type Message = { id: number; from: "user" | "ai"; text: string; reply?: ChatReply };

export default function Chat() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, mode } = s;
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const scroll = useRef<ScrollView>(null);
  const nextId = useRef(1);

  // 모드가 바뀌거나 쉼터 목록이 처음 준비되면 인사부터 다시
  const ready = !s.loading && s.analyses.length > 0;
  useEffect(() => {
    if (!ready) return;
    const g = greeting(s.analyses, mode);
    setMessages([{ id: nextId.current++, from: "ai", text: g.text, reply: g }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 분석 결과가 바뀔 때마다 대화를 지우지 않는다
  }, [mode, ready]);

  const ask = (q: string) => {
    const text = q.trim();
    if (!text) return;
    const reply = respond(text, s.analyses, mode);
    setMessages((m) => [
      ...m,
      { id: nextId.current++, from: "user", text },
      { id: nextId.current++, from: "ai", text: reply.text, reply },
    ]);
    setInput("");
    setTimeout(() => scroll.current?.scrollToEnd({ animated: true }), 100);
  };

  return (
    <KeyboardAvoidingView behavior="height" style={[styles.fill, { backgroundColor: p.bg }]}>
      <View style={[styles.header, { paddingTop: insets.top + 12, borderColor: p.border, backgroundColor: p.panel }]}>
        <View style={[styles.avatar, { borderColor: p.accent, backgroundColor: p.accentSoft }]}>
          <Icon name="creation" size={22} color={p.accent} />
        </View>
        <View>
          <Text style={[styles.title, { color: p.accent }]}>CoolMap Intelligence</Text>
          <Text style={[styles.status, { color: p.textDim }]}>
            <Text style={{ color: p.warn }}>●</Text> 실시간 열·이동 데이터 분석 중 · {clockLabel(s.now)}
          </Text>
        </View>
      </View>

      <ScrollView ref={scroll} contentContainerStyle={styles.messages}>
        <Text style={[styles.today, { color: p.textMute }]}>TODAY</Text>
        {!ready && (
          <Text style={[styles.status, { color: p.textDim, textAlign: "center" }]}>
            {s.error ? `쉼터 목록을 받지 못했습니다 (${s.error})` : "주변 쉼터를 분석하는 중…"}
          </Text>
        )}
        {messages.map((m) =>
          m.from === "user" ? (
            <View key={m.id} style={[styles.user, { backgroundColor: p.cardAlt, borderColor: p.border }]}>
              <Text style={[styles.userText, { color: p.text }]}>{m.text}</Text>
            </View>
          ) : (
            <View key={m.id} style={[styles.ai, { backgroundColor: p.card, borderColor: p.accentSoft }]}>
              <RichText text={m.text} style={{ ...styles.aiText, color: p.text }} boldColor={p.accent} />
              {m.reply?.places.map((a, i) =>
                i === 0 ? <BigCard key={a.place.id} a={a} /> : <SmallCard key={a.place.id} a={a} />,
              )}
              {!!m.reply?.note && <Text style={[styles.note, { color: p.textMute }]}>{m.reply.note}</Text>}
            </View>
          ),
        )}
      </ScrollView>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.noShrink} contentContainerStyle={styles.quick}>
        {QUICK_PROMPTS.map(([label, prompt, icon]) => (
          <Pressable
            key={label}
            onPress={() => ask(prompt)}
            disabled={!ready}
            style={[styles.quickChip, { borderColor: p.border, backgroundColor: p.card }]}
          >
            <Icon name={icon} size={15} color={p.accent} />
            <Text style={[styles.quickText, { color: p.textDim }]}>{label}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <View style={[styles.inputRow, { borderColor: p.border, backgroundColor: p.card }]}>
        <TextInput
          value={input}
          onChangeText={setInput}
          onSubmitEditing={() => ask(input)}
          placeholder="CoolMap AI에게 물어보세요… 예) 지금 조용하고 시원한 곳"
          placeholderTextColor={p.textMute}
          style={[styles.input, { color: p.text }]}
          returnKeyType="send"
          editable={ready}
        />
        <Pressable onPress={() => ask(input)} style={[styles.send, { backgroundColor: p.accent }]} disabled={!ready}>
          <Icon name="send" size={20} color={p.accentInk} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const open = (a: Analysis) => router.push({ pathname: "/place/[id]", params: { id: a.place.id } });

/** 대화 안에 들어가는 장소 카드 */
function BigCard({ a }: { a: Analysis }) {
  const { p } = useStore();
  const nc = nuisanceColor(p, a.nuisance.key);
  const hours = a.place.alwaysOpen ? "24시간 운영" : `${a.place.openTo % 24}시까지 운영`;
  return (
    <Pressable onPress={() => open(a)} style={[styles.big, { backgroundColor: p.cardAlt, borderColor: p.border }]}>
      <View style={styles.bigHead}>
        <Icon name={categoryIcon(a.place)} size={28} color={p.accent} />
        <View style={[styles.tempBadge, { backgroundColor: p.accent }]}>
          <Icon name="thermometer" size={12} color={p.accentInk} />
          <Text style={[styles.tempBadgeText, { color: p.accentInk }]}>{Math.round(a.indoor)}°C</Text>
        </View>
      </View>
      <Text style={[styles.bigName, { color: p.text }]}>{a.place.name}</Text>
      <Text style={[styles.note, { color: p.textDim }]}>
        {a.place.aiGuess ? `AI 추정 ${a.place.aiConfidence}% · ` : ""}
        {hours}
      </Text>
      <View style={styles.bigStats}>
        <View style={styles.fill}>
          <Text style={[styles.statLabel, { color: p.textMute }]}>NUISANCE</Text>
          <Text style={[styles.statValue, { color: nc }]}>
            ● {a.nuisance.score} · {a.nuisance.level}
          </Text>
        </View>
        <View style={styles.fill}>
          <Text style={[styles.statLabel, { color: p.textMute }]}>COMFORT</Text>
          <Text style={[styles.statValue, { color: p.accent }]}>
            ● {a.comfort >= 80 ? "매우 좋음" : a.comfort >= 60 ? "좋음" : "보통"} ({a.comfort})
          </Text>
        </View>
      </View>
    </Pressable>
  );
}

function SmallCard({ a }: { a: Analysis }) {
  const { p } = useStore();
  return (
    <Pressable onPress={() => open(a)} style={[styles.small, { backgroundColor: p.cardAlt, borderColor: p.border }]}>
      <View style={[styles.smallIcon, { backgroundColor: p.card }]}>
        <Icon name={categoryIcon(a.place)} size={18} color={p.textDim} />
      </View>
      <View style={styles.fill}>
        <Text style={[styles.smallName, { color: p.text }]} numberOfLines={1}>
          {a.place.name}
        </Text>
        <Text style={[styles.note, { color: p.textDim }]}>
          {Math.round(a.indoor)}°C · {analysisDistance(a)} · 민폐도 {a.nuisance.score}
        </Text>
      </View>
      <Icon name="chevron-right" size={20} color={p.textMute} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1 },
  avatar: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 19, fontWeight: "800" },
  status: { fontSize: 12 },
  messages: { padding: 16, gap: 14 },
  today: { textAlign: "center", fontSize: 11, fontWeight: "700", letterSpacing: 2 },
  user: { alignSelf: "flex-end", maxWidth: "85%", borderRadius: 16, borderWidth: 1, padding: 12 },
  userText: { fontSize: 15 },
  ai: { alignSelf: "flex-start", maxWidth: "95%", borderRadius: 16, borderWidth: 1, padding: 14, gap: 10 },
  aiText: { fontSize: 15, lineHeight: 22 },
  note: { fontSize: 12 },
  big: { borderRadius: 14, borderWidth: 1, padding: 14, gap: 4 },
  bigHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  tempBadge: { flexDirection: "row", alignItems: "center", gap: 3, borderRadius: 12, paddingHorizontal: 8, paddingVertical: 3 },
  tempBadgeText: { fontSize: 12, fontWeight: "800" },
  bigName: { fontSize: 19, fontWeight: "800" },
  bigStats: { flexDirection: "row", gap: 10, marginTop: 10 },
  statLabel: { fontSize: 10, fontWeight: "700", letterSpacing: 1.5 },
  statValue: { fontSize: 13, fontWeight: "700", marginTop: 2 },
  small: { flexDirection: "row", alignItems: "center", gap: 10, borderRadius: 14, borderWidth: 1, padding: 12 },
  smallIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  smallName: { fontSize: 15, fontWeight: "700" },
  noShrink: { flexGrow: 0, flexShrink: 0 },
  quick: { gap: 8, paddingHorizontal: 16, paddingVertical: 8 },
  quickChip: { flexDirection: "row", alignItems: "center", gap: 5, borderRadius: 18, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 7 },
  quickText: { fontSize: 13, fontWeight: "600" },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 18,
    borderWidth: 1,
    paddingLeft: 14,
    padding: 6,
  },
  input: { flex: 1, fontSize: 14, paddingVertical: 8 },
  send: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
});
