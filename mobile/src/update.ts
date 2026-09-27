// 앱 안 업데이트 (Android 전용).
//
// 새 APK 는 GitHub 릴리스에 올린다. 데스크톱 릴리스(v0.2.0 …)와 섞이지 않게 모바일은
// 태그를 'mobile-v0.2.5' 처럼 붙이고 .apk 파일을 첨부한다.
// 앱은 켤 때 한 번 릴리스 목록을 보고, 지금 버전보다 새것이 있으면 받아서 설치 화면을 띄운다.
// iOS 는 APK 를 설치할 수 없으므로 아무것도 하지 않는다.

import Constants from "expo-constants";
import { Directory, File, Paths } from "expo-file-system";
import { startActivityAsync } from "expo-intent-launcher";
import { useEffect, useState } from "react";
import { Platform } from "react-native";

const RELEASES = "https://api.github.com/repos/m34r1k/CoolMap-AI/releases?per_page=30";
const TAG_PREFIX = "mobile-v";
const APK_MIME = "application/vnd.android.package-archive";
const FLAG_GRANT_READ_URI_PERMISSION = 1;

export const currentVersion = Constants.expoConfig?.version ?? "0.0.0";
export const updatesSupported = Platform.OS === "android";

export type Update = { version: string; notes: string; apkUrl: string; sizeMB: number };

type Release = {
  tag_name: string;
  body: string | null;
  draft: boolean;
  prerelease: boolean;
  assets: { name: string; browser_download_url: string; size: number }[];
};

/** "0.2.10" > "0.2.9" 처럼 숫자로 비교한다 */
export function newer(a: string, b: string): boolean {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d > 0;
  }
  return false;
}

export async function checkForUpdate(): Promise<Update | null> {
  if (!updatesSupported) return null;
  const res = await fetch(RELEASES, { headers: { Accept: "application/vnd.github+json" } });
  if (!res.ok) throw new Error(`GitHub 응답 ${res.status}`);
  let best: Update | null = null;
  for (const r of (await res.json()) as Release[]) {
    if (r.draft || r.prerelease || !r.tag_name.startsWith(TAG_PREFIX)) continue;
    const apk = r.assets.find((a) => a.name.endsWith(".apk"));
    const version = r.tag_name.slice(TAG_PREFIX.length);
    if (!apk || !newer(version, best?.version ?? currentVersion)) continue;
    best = { version, notes: (r.body ?? "").trim(), apkUrl: apk.browser_download_url, sizeMB: apk.size / 1e6 };
  }
  return best;
}

/** APK 를 받아 Android 설치 화면을 띄운다. 처음 한 번은 '이 출처 허용' 을 물어본다. */
export async function installUpdate(u: Update): Promise<void> {
  const dir = new Directory(Paths.cache, "updates");
  if (dir.exists) dir.delete(); // 지난번에 받다 만 파일까지 치운다
  dir.create();
  const apk = await File.downloadFileAsync(u.apkUrl, new File(dir, `CoolMap-${u.version}.apk`));
  await startActivityAsync("android.intent.action.VIEW", {
    data: apk.contentUri,
    type: APK_MIME,
    flags: FLAG_GRANT_READ_URI_PERMISSION,
  });
}

// 앱을 켤 때 한 번만 확인하고, 홈·설정 화면이 결과를 같이 쓴다
let checked: Promise<Update | null> | null = null;

type State = "checking" | "latest" | "available" | "error" | "downloading";

export function useUpdate() {
  const [update, setUpdate] = useState<Update | null>(null);
  const [state, setState] = useState<State>("checking");

  const follow = (p: Promise<Update | null>) =>
    p
      .then((u) => {
        setUpdate(u);
        setState(u ? "available" : "latest");
      })
      .catch(() => {
        checked = null; // 다음에 다시 시도한다
        setState("error");
      });

  useEffect(() => {
    if (!updatesSupported) return;
    checked ??= checkForUpdate();
    follow(checked);
  }, []);

  const check = () => {
    setState("checking");
    checked = checkForUpdate();
    follow(checked);
  };

  const install = async () => {
    if (!update) return;
    setState("downloading");
    try {
      await installUpdate(update);
      setState("available"); // 설치를 취소하고 돌아와도 다시 누를 수 있게
    } catch {
      setState("error");
    }
  };

  return { update, state, check, install };
}
