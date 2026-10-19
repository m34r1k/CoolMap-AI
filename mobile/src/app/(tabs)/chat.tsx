// 물어보기 — 쉼터에 대해 말로 묻고 답을 듣는다 (coolmap/ui/chat.py).
// 타자가 어려운 사람도 쓸 수 있게, 대화 끝에 '누르기만 하면 되는 질문' 을 늘 보여 준다.

import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { Analysis } from "../../analysis";
import { type ChatReply, greeting, respond, suggestions } from "../../assistant";
import { askChat } from "../../backend";
import { PlaceRow, TopCard } from "../../components/PlaceCard";
import { Icon, RichText, T, useFontScale } from "../../components/ui";
import { chatContext } from "../../plain";
import { useStore } from "../../store";

type Message = { id: number; from: "user" | "ai"; text: string; reply?: ChatReply; thinking?: boolean };

const open = (a: Analysis) => router.push({ pathname: "/place/[id]", params: { id: a.place.id } });

export default function Chat() {
  const insets = useSafeAreaInsets();
  const s = useStore();
  const { p, mode } = s;
  const k = useFontScale();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const scroll = useRef<ScrollView>(null);
  const nextId = useRef(1);
  // 새로 물은 질문. 그 말풍선이 자리를 잡으면 거기로 스크롤해 질문과 답의 첫 줄이 보이게 한다
  // (맨 끝으로 내리면 답 문장이 장소 카드에 밀려 화면 위로 사라진다)
  const askedId = useRef(0);

  // 모드가 바뀌면 인사부터 다시
  useEffect(() => {
    const g = greeting(mode, s.weather, s.sky);
    setMessages([{ id: nextId.current++, from: "ai", text: g.text, reply: g }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 날씨가 갱신될 때마다 대화를 지우지 않는다
  }, [mode]);

  // 누르기만 하면 되는 질문은 규칙으로 바로 답한다 (빠르고, AI 호출 한도를 아낀다).
  // 직접 쓴 질문은 Gemini 에게 묻고, 한도 초과 · 인터넷 끊김이면 규칙 답으로 대신한다.
  const ask = (q: string, quick = false) => {
    const text = q.trim();
    if (!text) return;
    const userId = nextId.current++;
    const aiId = nextId.current++;
    askedId.current = userId;
    setInput("");
    const rules = () => respond(text, s.analyses, mode, s.now, s.weather, s.sky);
    if (quick) {
      const reply = rules();
      setMessages((m) => [...m, { id: userId, from: "user", text }, { id: aiId, from: "ai", text: reply.text, reply }]);
      return;
    }
    // 직전 대화 두 쌍 — '거기 몇 시까지야?' 같은 이어지는 질문을 알아듣게
    const history: { q: string; a: string }[] = [];
    for (let i = 0; i + 1 < messages.length; i++) {
      const [u, a] = [messages[i], messages[i + 1]];
      if (u.from === "user" && a.from === "ai" && !a.thinking) history.push({ q: u.text, a: a.text });
    }
    setMessages((m) => [
      ...m,
      { id: userId, from: "user", text },
      { id: aiId, from: "ai", text: "생각하고 있어요…", thinking: true },
    ]);
    const ctx = chatContext(s.analyses, mode, s.now, s.weather, s.sky, s.alerts, s.reports);
    const byId = new Map(s.analyses.map((a) => [a.place.id, a]));
    askChat(text, ctx, history.slice(-2))
      .then((d) => {
        const places = d.place_ids.map((id) => byId.get(id)).filter((a): a is Analysis => !!a);
        return { text: d.answer, places };
      })
      .catch(() => rules())
      .then((reply) =>
        setMessages((m) => m.map((x) => (x.id === aiId ? { id: aiId, from: "ai", text: reply.text, reply } : x))),
      );
  };

  return (
    <KeyboardAvoidingView
      // iOS 는 키보드가 화면 위에 덮이므로 그만큼 아래 여백을 넣어 입력창을 밀어 올린다
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={[styles.fill, { backgroundColor: p.bg }]}
    >
      <View style={[styles.header, { paddingTop: insets.top + 12, borderColor: p.border, backgroundColor: p.panel }]}>
        <T size={24} weight="800" color={p.text}>
          물어보기
        </T>
        <T size={15} color={p.textDim}>
          쉼터 · 날씨 · 앱 쓰는 법을 물어보세요
        </T>
      </View>

      <ScrollView
        ref={scroll}
        contentContainerStyle={styles.messages}
      >
        {messages.map((m) =>
          m.from === "user" ? (
            <View
              key={m.id}
              style={[styles.user, { backgroundColor: p.accent }]}
              onLayout={(e) => {
                if (m.id !== askedId.current) return;
                askedId.current = 0;
                scroll.current?.scrollTo({ y: Math.max(0, e.nativeEvent.layout.y - 12), animated: true });
              }}
            >
              <T size={17} weight="600" color={p.accentInk}>
                {m.text}
              </T>
            </View>
          ) : (
            <View key={m.id} style={[styles.ai, { backgroundColor: p.card, borderColor: p.border }]}>
              {m.thinking && <ActivityIndicator color={p.accent} style={{ alignSelf: "flex-start" }} />}
              <RichText
                text={m.text}
                style={{ fontSize: 17 * k, lineHeight: Math.round(17 * k * 1.5), color: p.text }}
                boldColor={p.accent}
              />
              {m.reply?.places[0] && <TopCard a={m.reply.places[0]} p={p} onOpen={() => open(m.reply!.places[0])} />}
              {m.reply?.places.slice(1).map((a) => (
                <PlaceRow key={a.place.id} a={a} p={p} onPress={() => open(a)} />
              ))}
            </View>
          ),
        )}

        {/* 누르기만 하면 되는 질문 */}
        <View style={styles.suggestions}>
          {suggestions(mode).map((q) => (
            <Pressable
              key={q}
              onPress={() => ask(q, true)}
              style={({ pressed }) => [
                styles.suggestion,
                { borderColor: p.accent, backgroundColor: pressed ? p.accentSoft : p.card },
              ]}
            >
              <T size={16} weight="700" color={p.accent}>
                {q}
              </T>
            </Pressable>
          ))}
        </View>
      </ScrollView>

      <View style={[styles.inputRow, { borderColor: p.border, backgroundColor: p.card }]}>
        <TextInput
          value={input}
          onChangeText={setInput}
          onSubmitEditing={() => ask(input)}
          placeholder="예) 가장 가까운 쉼터는 어디야?"
          placeholderTextColor={p.textMute}
          style={[styles.input, { color: p.text, fontSize: 17 * k }]}
          returnKeyType="send"
        />
        <Pressable
          onPress={() => ask(input)}
          accessibilityLabel="보내기"
          style={[styles.send, { backgroundColor: input.trim() ? p.accent : p.cardAlt }]}
        >
          <Icon name="send" size={24} color={input.trim() ? p.accentInk : p.textMute} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  header: { paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, gap: 2 },
  messages: { padding: 16, gap: 14 },
  user: { alignSelf: "flex-end", maxWidth: "85%", borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10 },
  ai: { alignSelf: "stretch", borderRadius: 18, borderWidth: 1, padding: 14, gap: 12 },
  suggestions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  suggestion: { borderWidth: 1.5, borderRadius: 22, paddingHorizontal: 14, paddingVertical: 10 },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginHorizontal: 12,
    marginBottom: 12,
    borderRadius: 20,
    borderWidth: 1,
    paddingLeft: 14,
    padding: 6,
  },
  input: { flex: 1, paddingVertical: 10 },
  send: { width: 52, height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center" },
});
