// 기기 안 저장소. 설정·즐겨찾기·AI 판단 캐시를 둔다 (데스크톱의 %APPDATA%\CoolMap 에 해당).

import AsyncStorage from "@react-native-async-storage/async-storage";

export async function load<T>(key: string, fallback: T): Promise<T> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export async function save(key: string, value: unknown): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장 실패는 다음 실행 때 다시 받으면 되므로 무시한다
  }
}

export async function removeByPrefix(prefix: string): Promise<void> {
  try {
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(prefix));
    if (keys.length) await AsyncStorage.multiRemove(keys);
  } catch {
    // 무시
  }
}
