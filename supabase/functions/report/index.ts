// 쉼터 제보 — 이용자가 현장에서 알려 주는 문제(문 닫힘 · 없어짐 · 냉난방 안 됨).
//
// 호출:  POST /functions/v1/report
//   { "task": "add", "place_id": "H12345", "kind": "closed" | "gone" | "no_hvac" }
//     → { ok: true }
//   { "task": "recent", "place_ids": ["H12345", ...] }          (최대 300개)
//     → { reports: { "H12345": { kind, at, count } } }          (최근 48시간, kind · at 은 가장 최근 제보)
//
// 공개 키만 있으면 누구나 부를 수 있으므로:
//   · 같은 IP 가 같은 쉼터에 10분 안에 다시 제보하면 받지 않는다
//   · IP 당 시간당 20건까지만 받는다
//   · 장소 id · 종류는 허용된 형식만 받는다 (테이블 check 와 같다)

import { createClient } from "npm:@supabase/supabase-js@2";

const KINDS = new Set(["closed", "gone", "no_hvac"]);
const PLACE_ID = /^([HC][0-9]{1,12}|G[nwr][0-9]{1,15})$/;
const SAME_PLACE_MIN = 10;
const IP_PER_HOUR = 20;
const RECENT_HOURS = 48;
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

async function add(ip: string, body: Record<string, unknown>) {
  const placeId = String(body.place_id ?? "");
  const kind = String(body.kind ?? "");
  if (!PLACE_ID.test(placeId)) throw new HttpError(400, "place_id 형식이 올바르지 않습니다");
  if (!KINDS.has(kind)) throw new HttpError(400, "kind 는 closed · gone · no_hvac 중 하나여야 합니다");

  const same = await db.from("shelter_reports").select("id", { count: "exact", head: true })
    .eq("ip", ip).eq("place_id", placeId).gt("at", ago(SAME_PLACE_MIN));
  if ((same.count ?? 0) > 0) throw new HttpError(429, "이미 알려 주셨어요. 고마워요!");
  const mine = await db.from("shelter_reports").select("id", { count: "exact", head: true })
    .eq("ip", ip).gt("at", ago(60));
  if ((mine.count ?? 0) >= IP_PER_HOUR) throw new HttpError(429, "제보가 너무 많아요. 조금 뒤에 다시 해 주세요");

  const { error } = await db.from("shelter_reports").insert({ place_id: placeId, kind, ip });
  if (error) throw new HttpError(500, error.message);
  return { ok: true };
}

async function recent(body: Record<string, unknown>) {
  const ids = Array.isArray(body.place_ids) ? body.place_ids.map(String).filter((x) => PLACE_ID.test(x)) : [];
  if (!ids.length) return { reports: {} };
  const { data, error } = await db.from("shelter_reports").select("place_id, kind, at")
    .in("place_id", ids.slice(0, MAX_IDS)).gt("at", ago(RECENT_HOURS * 60))
    .order("at", { ascending: false }).limit(2000);
  if (error) throw new HttpError(500, error.message);

  const reports: Record<string, { kind: string; at: string; count: number }> = {};
  for (const row of data ?? []) {
    const r = reports[row.place_id];
    if (r) r.count += 1;
    else reports[row.place_id] = { kind: row.kind, at: row.at, count: 1 };
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
    if (body.task === "recent") return json(await recent(body));
    return json({ error: "task 는 add 또는 recent 여야 합니다" }, 400);
  } catch (e) {
    if (e instanceof HttpError) return json({ error: e.message }, e.status);
    console.error(e);
    return json({ error: String(e) }, 500);
  }
});
