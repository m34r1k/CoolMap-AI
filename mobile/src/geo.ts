// 좌표 계산. coolmap/geo.py 와 같은 식을 쓴다.

const RE = 6371.00877; // 지구 반경 (km)
const GRID = 5.0; // 격자 간격 (km)
const SLAT1 = 30.0; // 표준 위도 1
const SLAT2 = 60.0; // 표준 위도 2
const OLON = 126.0; // 기준점 경도
const OLAT = 38.0; // 기준점 위도
const XO = 43; // 기준점 X 좌표
const YO = 136; // 기준점 Y 좌표

/** 위경도 → 기상청 격자 (nx, ny). Lambert 정각원추도법. */
export function latLonToKmaGrid(lat: number, lon: number): [number, number] {
  const degrad = Math.PI / 180;
  const re = RE / GRID;
  const slat1 = SLAT1 * degrad;
  const slat2 = SLAT2 * degrad;
  const olon = OLON * degrad;
  const olat = OLAT * degrad;

  let sn = Math.tan(Math.PI * 0.25 + slat2 * 0.5) / Math.tan(Math.PI * 0.25 + slat1 * 0.5);
  sn = Math.log(Math.cos(slat1) / Math.cos(slat2)) / Math.log(sn);
  let sf = Math.tan(Math.PI * 0.25 + slat1 * 0.5);
  sf = (Math.pow(sf, sn) * Math.cos(slat1)) / sn;
  let ro = Math.tan(Math.PI * 0.25 + olat * 0.5);
  ro = (re * sf) / Math.pow(ro, sn);

  let ra = Math.tan(Math.PI * 0.25 + lat * degrad * 0.5);
  ra = (re * sf) / Math.pow(ra, sn);
  let theta = lon * degrad - olon;
  if (theta > Math.PI) theta -= 2 * Math.PI;
  if (theta < -Math.PI) theta += 2 * Math.PI;
  theta *= sn;
  return [
    Math.floor(ra * Math.sin(theta) + XO + 0.5),
    Math.floor(ro - ra * Math.cos(theta) + YO + 0.5),
  ];
}

/** 두 지점 사이 거리 (m) */
export function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const a =
    Math.sin(r(lat2 - lat1) / 2) ** 2 +
    Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(r(lon2 - lon1) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(a));
}

/** coolmap/data.py distance_label 과 같다 */
export function distanceLabel(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${Math.round(m / 10) * 10}m`;
}

/** 도보 시간 (분). 평균 67m/분. */
export function walkMinutes(m: number): number {
  return Math.max(1, Math.round(m / 67));
}
