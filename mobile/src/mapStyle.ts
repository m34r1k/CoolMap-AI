// 지도 스타일. OpenFreeMap 은 키가 없고 사용량 제한도 없다.
// 기본 스타일은 지명을 '영문 + 한글' 두 줄로 쓰므로, 한글 이름만 보이도록 고쳐서 쓴다.
// 라이트 테마는 밝고 담백한 positron, 다크 테마는 dark 스타일을 쓴다.

import type { StyleSpecification } from "@maplibre/maplibre-react-native";

const STYLE_URL = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};

const KOREAN_LABEL = ["coalesce", ["get", "name:ko"], ["get", "name"]];

// 냉방·난방 어느 테마에도 어울리도록 무채색으로 둔다
const BUILDING = {
  // 기본 건물 색(rgb 10)이 배경(rgb 12)과 거의 같아 외곽선이 보이지 않는다
  dark: { fill: "#1D2027", edge: "#3E4451" },
  light: { fill: "#E3E6EA", edge: "#C3C9D1" },
};

const cache: Partial<Record<"light" | "dark", Promise<StyleSpecification | string>>> = {};

export function loadMapStyle(dark: boolean): Promise<StyleSpecification | string> {
  const variant = dark ? "dark" : "light";
  cache[variant] ??= fetchStyle(variant);
  return cache[variant];
}

async function fetchStyle(variant: "light" | "dark"): Promise<StyleSpecification | string> {
  const url = STYLE_URL[variant];
  try {
    const res = await fetch(url);
    if (!res.ok) return url;
    const style = (await res.json()) as StyleSpecification;
    for (const layer of style.layers) {
      if (layer.id === "building" && layer.type === "fill") {
        const b = BUILDING[variant];
        layer.paint = { ...layer.paint, "fill-color": b.fill, "fill-outline-color": b.edge };
        continue;
      }
      if (layer.type !== "symbol" || !layer.layout?.["text-field"]) continue;
      // 도로 번호 같은 ref 라벨은 그대로 둔다
      if (!JSON.stringify(layer.layout["text-field"]).includes("name")) continue;
      (layer.layout as Record<string, unknown>)["text-field"] = KOREAN_LABEL;
      delete (layer.layout as Record<string, unknown>)["text-transform"];
    }
    return style;
  } catch {
    // 고치지 못하면 원래 스타일을 그대로 쓴다 (다음에 다시 시도하도록 캐시에서 뺀다)
    delete cache[variant];
    return url;
  }
}
