// Gemini 민폐도 (CoolMap 서버 경유). coolmap/providers/gemini.py 의 NuisanceAI 를 옮겼다.
//
// 쉼터가 6만 곳이라 장소마다 물어볼 수 없어, 민폐도를 좌우하는 '시설 성격'
// (유형·공식지정·구매필요·규모…) 단위로 캐시한다. 서버도 같은 키로 캐시해 모든 사용자가 공유한다.

import { aiNuisance, type NuisanceProfile, type NuisanceResult } from "./backend";
import { categoryLabel, type Place } from "./places";
import { load, removeByPrefix, save } from "./storage";
import type { Mode } from "./theme";

const CONCURRENCY = 3;
const FAIL_COOLDOWN = 120_000;

/** 수용 인원을 구간으로 뭉갠다 (캐시 재사용률을 높이기 위해) */
function capacityBand(n: number): string {
  if (n <= 20) return "소형(20명 이하)";
  if (n <= 60) return "중형(20~60명)";
  if (n <= 200) return "대형(60~200명)";
  return "초대형(200명 초과)";
}

/** 민폐도를 좌우하는 '시설 성격'만 뽑는다. 개별 시설명은 제외한다. */
export function nuisanceProfile(p: Place, mode: Mode): NuisanceProfile {
  return {
    mode: mode === "cooling" ? "냉방(폭염 대피)" : "난방(한파 대피)",
    category: categoryLabel(p),
    official: p.official ? "예" : "아니오",
    purchase: p.purchaseRequired ? "예" : "아니오",
    capacity: capacityBand(p.capacity),
    always_open: p.alwaysOpen ? "예" : "아니오",
    quiet: Math.round(p.quiet * 10) / 10,
  };
}

const keyOf = (profile: NuisanceProfile) =>
  Object.keys(profile)
    .sort()
    .map((k) => `${k}=${profile[k as keyof NuisanceProfile]}`)
    .join("|");

const mem = new Map<string, NuisanceResult>();
const pending = new Set<string>();
const queue: [string, NuisanceProfile][] = [];
let running = 0;
let failUntil = 0;
let calls = 0;
let lastError = "";
const listeners = new Set<() => void>();

/** 결과가 새로 도착할 때마다 불린다 (화면을 다시 계산하도록) */
export function onNuisance(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const nuisanceStatus = () => ({ cached: mem.size, pending: pending.size, calls, error: lastError });

function pump() {
  while (running < CONCURRENCY && queue.length && Date.now() >= failUntil) {
    const [key, profile] = queue.shift()!;
    running++;
    aiNuisance(profile)
      .then(async (r) => {
        mem.set(key, r);
        calls++;
        lastError = "";
        await save(`nuis:${key}`, r);
        listeners.forEach((fn) => fn());
      })
      .catch((e: unknown) => {
        lastError = e instanceof Error ? e.message : String(e);
        failUntil = Date.now() + FAIL_COOLDOWN;
      })
      .finally(() => {
        pending.delete(key);
        running--;
        pump();
      });
  }
}

/** 캐시된 결과. 없으면 백그라운드로 요청하고 null (그동안은 규칙 기반으로 보여 준다). */
export function getNuisance(p: Place, mode: Mode): NuisanceResult | null {
  const profile = nuisanceProfile(p, mode);
  const key = keyOf(profile);
  const hit = mem.get(key);
  if (hit) return hit;
  if (pending.has(key) || Date.now() < failUntil) return null;
  pending.add(key);
  // 기기에 저장해 둔 값이 있으면 그걸 쓰고, 없으면 서버에 묻는다
  load<NuisanceResult | null>(`nuis:${key}`, null).then((saved) => {
    if (saved) {
      mem.set(key, saved);
      pending.delete(key);
      listeners.forEach((fn) => fn());
      return;
    }
    queue.push([key, profile]);
    pump();
  });
  return null;
}

export async function clearNuisanceCache(): Promise<void> {
  mem.clear();
  await removeByPrefix("nuis:");
}
