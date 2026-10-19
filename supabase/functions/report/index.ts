// 쉼터 제보 — 이용자가 현장에서 알려 주는 문제(문 닫힘 · 없어짐 · 냉난방 안 됨)와 '지금은 괜찮아요'.
//
// 호출:  POST /functions/v1/report
//   { "task": "add", "place_id": "H12345", "kind": "closed" | "gone" | "no_hvac" | "ok", "device": "<기기 표식>" }
//     → { ok: true, id }
//   { "task": "cancel", "id": 123, "device": "<기기 표식>" }          (본인 제보만, 24시간 안)
//     → { ok: true }
//   { "task": "recent", "place_ids": ["H12345", ...] }                (최대 300개)
//     → { reports: { "H12345": { kind, at, count } } }
//        · 최근 24시간 기준 (하루 지난 제보는 보이지 않는다). 가장 최근이 'ok' 면 { kind: "ok", at, count: 0 } (앞선 문제 제보는 가린다)
//        · 아니면 가장 최근 문제 제보의 kind · at 과, 마지막 'ok' 이후 문제 제보 건수
//
// 공개 키만 있으면 누구나 부를 수 있으므로:
//   · 같은 기기가 같은 쉼터에 같은 종류를 10분 안에 다시 제보하면 받지 않는다
//     (IP 로 막으면 쉼터 와이파이를 같이 쓰는 여러 사람이 서로 막힌다)
//   · IP 당 시간당 IP_PER_HOUR 건까지만 받는다 (장난 제보 방지)
//   · 장소 id · 종류 · 기기 표식은 허용된 형식만 받는다
//   · 기기 표식은 해시로만 저장하고, 취소는 그 해시가 맞을 때만 된다

import { createClient } from "npm:@supabase/supabase-js@2";

const KINDS = new Set(["closed", "gone", "no_hvac", "ok"]);
const PLACE_ID = /^([HC][0-9]{1,20}|G[nwr][0-9]{1,15})$/;
const DEVICE = /^[A-Za-z0-9-]{16,64}$/;
const SAME_PLACE_MIN = 10;
const IP_PER_HOUR = 40; // 쉼터 와이파이처럼 여러 사람이 한 IP 를 쓰는 경우를 생각해 넉넉히
const RECENT_HOURS = 24;
const MAX_IDS = 300;

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const ago = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

async function deviceHash(v: unknown): Promise<string> {
  const raw = String(v ?? "");
  if (!DEVICE.test(raw)) throw new HttpError(400, "device 형식이 올바르지 않습니다");
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`coolmap-report:${raw}`));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function add(ip: string, body: Record<string, unknown>) {
  const placeId = String(body.place_id ?? "");
  const kind = String(body.kind ?? "");
  if (!PLACE_ID.test(placeId)) throw new HttpError(400, "place_id 형식이 올바르지 않습니다");
  if (!KINDS.has(kind)) throw new HttpError(400, "kind 는 closed · gone · no_hvac · ok 중 하나여야 합니다");
  const device = await deviceHash(body.device);

  const same = await db.from("shelter_reports").select("id", { count: "exact", head: true })
    .eq("place_id", placeId).eq("device", device).eq("kind", kind).gt("at", ago(SAME_PLACE_MIN));
  if ((same.count ?? 0) > 0) throw new HttpError(429, "이미 알려 주셨어요. 고마워요!");
  const mine = await db.from("shelter_reports").select("id", { count: "exact", head: true })
    .eq("ip", ip).gt("at", ago(60));
  if ((mine.count ?? 0) >= IP_PER_HOUR) throw new HttpError(429, "제보가 너무 많아요. 조금 뒤에 다시 해 주세요");

  const { data, error } = await db.from("shelter_reports")
    .insert({ place_id: placeId, kind, ip, device }).select("id").single();
  if (error) throw new HttpError(500, error.message);
  return { ok: true, id: data.id };
}

async function cancel(body: Record<string, unknown>) {
  const id = Number(body.id);
  if (!Number.isInteger(id) || id <= 0) throw new HttpError(400, "id 가 올바르지 않습니다");
  const device = await deviceHash(body.device);
  const { data, error } = await db.from("shelter_reports").delete()
    .eq("id", id).eq("device", device).gt("at", ago(RECENT_HOURS * 60)).select("id");
  if (error) throw new HttpError(500, error.message);
  if (!data?.length) throw new HttpError(404, "취소할 제보를 찾지 못했어요 (이미 취소했거나 하루가 지났어요)");
  return { ok: true };
}

async function recent(body: Record<string, unknown>) {
  const ids = Array.isArray(body.place_ids) ? body.place_ids.map(String).filter((x) => PLACE_ID.test(x)) : [];
  if (!ids.length) return { reports: {} };
  const { data, error } = await db.from("shelter_reports").select("place_id, kind, at")
    .in("place_id", ids.slice(0, MAX_IDS)).gt("at", ago(RECENT_HOURS * 60))
    .order("at", { ascending: false }).limit(2000);
  if (error) throw new HttpError(500, error.message);

  // 최신 순으로 훑으며, 'ok' 를 만나면 그 앞(더 오래된) 제보는 세지 않는다
  const reports: Record<string, { kind: string; at: string; count: number }> = {};
  const settled = new Set<string>();
  for (const row of data ?? []) {
    if (settled.has(row.place_id)) continue;
    const r = reports[row.place_id];
    if (row.kind === "ok") {
      if (!r) reports[row.place_id] = { kind: "ok", at: row.at, count: 0 };
      settled.add(row.place_id);
    } else if (r) {
      r.count += 1;
    } else {
      reports[row.place_id] = { kind: row.kind, at: row.at, count: 1 };
    }
  }
  return { reports };
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "POST 만 받습니다" }, 405);
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim();
  try {
    const body = await req.json().catch(() => null);
    if (!body || typeof body !== "object") throw new HttpError(400, "본문이 JSON 이 아닙니다");
    if (body.task === "add") return json(await add(ip, body));
    if (body.task === "cancel") return json(await cancel(body));
    if (body.task === "recent") return json(await recent(body));
    return json({ error: "task 는 add · cancel · recent 중 하나여야 합니다" }, 400);
  } catch (e) {
    if (e instanceof HttpError) return json({ error: e.message }, e.status);
    console.error(e);
    return json({ error: String(e) }, 500);
  }
});
