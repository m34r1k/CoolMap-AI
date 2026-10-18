import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { StoreProvider, useStore } from "../store";

function Root() {
  const { p } = useStore();
  return (
    <>
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: p.bg } }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="place/[id]" options={{ animation: "slide_from_right" }} />
        <Stack.Screen name="route/[id]" options={{ animation: "slide_from_bottom" }} />
      </Stack>
      <StatusBar style={p.dark ? "light" : "dark"} />
    </>
  );
}

export default function Layout() {
  return (
    <SafeAreaProvider>
      <StoreProvider>
        <Root />
      </StoreProvider>
    </SafeAreaProvider>
  );
}
