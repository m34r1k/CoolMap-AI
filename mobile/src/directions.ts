// 길찾기.
//
// 구글 지도는 국내 지도 데이터 반출 제한 때문에 한국에서 자동차·도보 경로를 주지 않는다
// (대중교통만 된다). 그냥 geo: 로 넘기면 구글 지도가 기본 경로를 찾다가 실패하므로,
// 도보 경로가 되는 카카오맵·네이버 지도를 먼저 권하고 구글 지도는 대중교통으로 연다.

import { Alert, Linking } from "react-native";

import type { Place } from "./places";

const APP_ID = "com.m34r1k.coolmap";

/** 앱 주소를 먼저 열어 보고, 앱이 없으면 웹 주소로 연다 */
async function openFirst(urls: string[]): Promise<void> {
  for (const url of urls) {
    try {
      await Linking.openURL(url);
      return;
    } catch {
      // 처리할 앱이 없으면 다음 주소로
    }
  }
  Alert.alert("길찾기", "지도를 열 수 없습니다.");
}

/**
 * from 은 내 현재 위치 [경도, 위도]. 넘기지 않으면 지도 앱이 알아서 출발지를 정하는데,
 * 카카오맵은 출발지 없이 열면 비워 둔 채로 입력을 기다린다.
 */
export function openDirections(p: Place, from: [number, number] | null): void {
  const name = encodeURIComponent(p.name);
  const here = encodeURIComponent("현재 위치");
  const [fromLon, fromLat] = from ?? [0, 0];
  // 카카오맵 웹 길찾기 — 앱이 없을 때도 브라우저에서 도보 경로를 볼 수 있다
  const kakaoWeb = from
    ? `https://map.kakao.com/link/from/${here},${fromLat},${fromLon}/to/${name},${p.lat},${p.lon}`
    : `https://map.kakao.com/link/to/${name},${p.lat},${p.lon}`;
  const kakaoApp =
    `kakaomap://route?${from ? `sp=${fromLat},${fromLon}&` : ""}ep=${p.lat},${p.lon}&by=FOOT`;
  const naverApp =
    `nmap://route/walk?${from ? `slat=${fromLat}&slng=${fromLon}&sname=${here}&` : ""}` +
    `dlat=${p.lat}&dlng=${p.lon}&dname=${name}&appname=${APP_ID}`;

  Alert.alert("길찾기", `${p.name}까지 어떤 지도로 안내할까요?`, [
    {
      text: "카카오맵 (도보)",
      onPress: () => openFirst([kakaoApp, kakaoWeb]),
    },
    {
      text: "네이버 지도 (도보)",
      onPress: () => openFirst([naverApp, kakaoWeb]),
    },
    {
      text: "구글 지도 (대중교통)",
      onPress: () =>
        openFirst([
          `https://www.google.com/maps/dir/?api=1${from ? `&origin=${fromLat},${fromLon}` : ""}` +
            `&destination=${p.lat},${p.lon}&travelmode=transit`,
        ]),
    },
  ]);
}
