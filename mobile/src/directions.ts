import { Linking } from "react-native";

import type { Place } from "./places";

/** Android 는 geo: 주소를 받으면 설치된 지도 앱 중에서 고르게 해 준다 */
export function openDirections(p: Place) {
  return Linking.openURL(`geo:${p.lat},${p.lon}?q=${p.lat},${p.lon}(${encodeURIComponent(p.name)})`);
}
