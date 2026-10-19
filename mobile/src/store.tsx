// 앱 전체 상태. 데스크톱의 config.AppState + catalog.places_for 에 해당한다.
//
// 모든 화면이 같은 쉼터 목록·분석 결과를 보도록 여기 한 곳에서 불러오고 계산한다.

import * as Location from "expo-location";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { type Analysis, analyze, type Now, nowParts, type Weather, weatherFromObs } from "./analysis";
import {
  cancelReport,
  type DisasterAlert,
  disasterAlerts,
  recentReports,
  type Report,
  type ReportKind,
  reportShelter,
  sheltersNear,
  type SkyHour,
  weather as fetchWeather,
} from "./backend";
import { mergeCandidates, nearbyCandidates } from "./candidates";
import { haversine, walkMinutes } from "./geo";
import { onNuisance } from "./nuisance";
import { regionOf, type SkyIcon, skyLine } from "./plain";
import { type Place, shelterToPlace } from "./places";
import { load, save } from "./storage";
import { defaultMode, type Mode, type Palette, paletteFor } from "./theme";

/** 내가 보낸 제보 (취소 버튼용) */
export type MyReport = { id: number; kind: ReportKind; at: number };

export type LngLat = [number, number];
export type Fix = { coord: LngLat; accuracyM: number };

// 위치 권한이 없을 때 기준점 (서울시청)
export const FALLBACK: LngLat = [126.9784, 37.5667];
const SHELTER_LIMIT = 60;

export type Settings = {
  mode: Mode;
  targetCool: number;
  targetHeat: number;
  onlyOfficial: boolean;
  aiCandidates: boolean; // 지도의 상호를 AI 로 판단해 추가 하이라이트
  maxWalk: number; // 분
  searchRadius: number; // m
  favorites: Place[]; // 반경 밖으로 나가도 열 수 있도록 장소를 통째로 보관한다
  bigText: boolean; // 글씨를 크게 (어르신용)
  darkMode: boolean; // 기본은 라이트
};

const DEFAULTS: Settings = {
  mode: defaultMode(),
  targetCool: 22,
  targetHeat: 23,
  onlyOfficial: false,
  aiCandidates: true,
  maxWalk: 40,
  searchRadius: 2500,
  favorites: [],
  bigText: false,
  darkMode: false,
};

// 쉼터 데이터는 국내뿐이다
const inKorea = (lat: number, lon: number) => lat >= 33 && lat <= 39.5 && lon >= 124 && lon <= 132;

/** 어떤 조회에 대한 결과인지 함께 보관한다 — 조회 조건이 바뀌면 자동으로 '불러오는 중'이 된다 */
type Loaded<T> = { key: string; value: T; error?: string };

const toFix = (pos: Location.LocationObject): Fix => ({
  coord: [pos.coords.longitude, pos.coords.latitude],
  accuracyM: pos.coords.accuracy ?? 0,
});

type Store = {
  ready: boolean;
  settings: Settings;
  update: (patch: Partial<Settings>) => void;
  mode: Mode;
  p: Palette;
  target: number;
  now: Now;

  me: Fix | null;
  origin: LngLat; // 거리 계산 기준 (내 위치, 없으면 서울시청)
  here: LngLat | null; // 실제로 확인된 내 위치 (길찾기 출발지). 못 찾았으면 null
  located: boolean;
  locationNotice: string;
  locate: () => Promise<LngLat | null>;
  searchCenter: LngLat;
  setSearchCenter: (c: LngLat) => void;

  weather: Weather;
  /** 내 시군구 (가장 가까운 공식 쉼터 주소로 정한다). 모르면 '' */
  region: string;
  /** 내 지역의 최근 24시간 재난문자, 최신순 */
  alerts: DisasterAlert[];
  /** 하늘 — 아이콘 · '비가 와요' · '오후 5시쯤 그칠 것 같아요' (모르면 빈 글자) */
  sky: { icon: SkyIcon; text: string; hint: string };
  loading: boolean;
  aiLoading: boolean;
  error: string;
  officialCount: number;
  aiCount: number;
  analyses: Analysis[]; // 필터(공식만·최대 도보)까지 적용한 결과
  analyzePlace: (p: Place) => Analysis;
  getPlace: (id: string) => Place | undefined;
  isFavorite: (id: string) => boolean;
  toggleFavorite: (p: Place) => void;
  reload: () => void;
  /** 최근 48시간 이용자 제보 (쉼터 id → 가장 최근 제보) */
  reports: Record<string, Report>;
  /** 쉼터에 문제가 있다고(또는 괜찮다고) 알린다. 실패하면 쉬운 말 오류를 던진다 */
  report: (placeId: string, kind: ReportKind) => Promise<void>;
  /** 이 쉼터에 내가 48시간 안에 보낸 제보 (취소 버튼용) */
  myReport: (placeId: string) => MyReport | undefined;
  /** 내 제보 취소 */
  cancelMyReport: (placeId: string) => Promise<void>;
};

const Ctx = createContext<Store | null>(null);

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("StoreProvider 밖에서 useStore 를 불렀습니다");
  return s;
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [now, setNow] = useState<Now>(nowParts);

  const [me, setMe] = useState<Fix | null>(null);
  const [origin, setOrigin] = useState<LngLat>(FALLBACK);
  const [located, setLocated] = useState(false);
  const [permitted, setPermitted] = useState(false);
  // 이번 '위치 확인'에서 아직 기준점을 못 잡았으면 다음에 들어오는 위치를 기준점으로 삼는다
  const needOrigin = useRef(true);
  const [locationNotice, setLocationNotice] = useState("");
  const [searchCenter, setSearchCenter] = useState<LngLat>(FALLBACK);

  const [obs, setObs] = useState<Record<string, string> | null>(null);
  const [skyHours, setSkyHours] = useState<SkyHour[] | null>(null);
  const [region, setRegion] = useState("");
  const [alerts, setAlerts] = useState<DisasterAlert[]>([]);
  const [officialRes, setOfficialRes] = useState<Loaded<Place[]>>({ key: "", value: [] });
  const [guessRes, setGuessRes] = useState<Loaded<Place[]>>({ key: "", value: [] });
  // 한 번이라도 목록에 실렸던 장소 — 상세 화면은 id 로만 찾으므로, 목록이 바뀐 뒤에도 열 수 있게 둔다
  const [seen, setSeen] = useState<ReadonlyMap<string, Place>>(new Map());
  const [nuisVersion, setNuisVersion] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  const mode = settings.mode;
  const p = paletteFor(mode, settings.darkMode);
  const target = mode === "cooling" ? settings.targetCool : settings.targetHeat;

  // -- 설정 ------------------------------------------------------------------
  useEffect(() => {
    load<Partial<Settings>>("settings", {}).then((saved) => {
      setSettings({ ...DEFAULTS, ...saved });
      setReady(true);
    });
  }, []);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((s) => {
      const next = { ...s, ...patch };
      save("settings", next);
      return next;
    });
  }, []);

  // 시각은 1분마다 (운영 여부·마감 임박이 바뀐다)
  useEffect(() => {
    const t = setInterval(() => setNow(nowParts()), 60_000);
    return () => clearInterval(t);
  }, []);

  // 민폐도 AI 결과가 도착하면 다시 계산한다 (짧은 시간에 몰려 오므로 묶는다)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const off = onNuisance(() => {
      if (!timer) timer = setTimeout(() => ((timer = null), setNuisVersion((v) => v + 1)), 300);
    });
    return () => {
      off();
      if (timer) clearTimeout(timer);
    };
  }, []);

  // -- 위치 ------------------------------------------------------------------
  /** 위치 하나를 반영한다. 기준점이 필요하면 쉼터 검색 중심까지 옮기고, 아니면 내 위치 표시만 옮긴다. */
  const applyFix = useCallback((pos: Location.LocationObject): LngLat | null => {
    const { latitude, longitude } = pos.coords;
    if (!inKorea(latitude, longitude)) {
      setLocationNotice("현재 위치가 국내가 아니라 서울시청 주변을 보여줍니다");
      return null;
    }
    const here: LngLat = [longitude, latitude];
    setMe(toFix(pos));
    if (needOrigin.current) {
      needOrigin.current = false;
      setLocated(true);
      setLocationNotice("");
      setOrigin(here);
      setSearchCenter(here);
    }
    return here;
  }, []);

  const locate = useCallback(async (): Promise<LngLat | null> => {
    const perm = await Location.requestForegroundPermissionsAsync();
    if (!perm.granted) {
      setLocationNotice("위치 권한이 없어 서울시청 주변을 보여줍니다");
      return null;
    }
    setPermitted(true);
    needOrigin.current = true;
    let found: LngLat | null = null;
    // 새 GPS 값은 늦게 오거나 안 올 수 있으므로, 최근에 알려진 위치로 먼저 보여 준다
    const last = await Location.getLastKnownPositionAsync({ maxAge: 10 * 60_000 }).catch(() => null);
    if (last) found = applyFix(last);
    try {
      const pos = await Promise.race([
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error("timeout")), 15_000)),
      ]);
      needOrigin.current = true; // 더 정확한 현재 위치로 기준점을 다시 잡는다
      found = applyFix(pos) ?? found;
    } catch {
      // 늦게라도 위치가 잡히면 아래 추적이 기준점으로 삼는다
      if (!found) setLocationNotice("현재 위치를 찾는 중입니다. 위치 서비스가 켜져 있는지 확인해 주세요");
    }
    return found;
  }, [applyFix]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- locate() 는 권한 요청(await) 뒤에서만 상태를 바꾼다
    locate();
  }, [locate]);

  // 권한을 받은 뒤로는 계속 위치를 따라간다. 첫 위치가 늦게 잡혀도 여기서 기준점이 된다.
  useEffect(() => {
    if (!permitted) return;
    let sub: Location.LocationSubscription | null = null;
    let stopped = false;
    Location.watchPositionAsync(
      { accuracy: Location.Accuracy.Balanced, distanceInterval: 10, timeInterval: 5_000 },
      (pos) => applyFix(pos),
    )
      .then((s) => (stopped ? s.remove() : (sub = s)))
      .catch(() => {});
    return () => {
      stopped = true;
      sub?.remove();
    };
  }, [permitted, applyFix]);

  // -- 날씨 (내 위치 기준, 10분마다) ----------------------------------------------
  useEffect(() => {
    let cancelled = false;
    const get = () =>
      fetchWeather(origin[1], origin[0])
        .then((w) => {
          if (cancelled) return;
          setObs(w.now);
          setSkyHours(w.sky ?? null);
        })
        .catch(() => {});
    get();
    const t = setInterval(get, 10 * 60_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [origin]);

  // -- 쉼터 ------------------------------------------------------------------
  const queryKey = [...searchCenter, mode, settings.searchRadius, reloadKey].join(",");

  const remember = useCallback((list: Place[]) => {
    setSeen((prev) => {
      const next = new Map(prev);
      for (const x of list) next.set(x.id, x);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const [lon, lat] = searchCenter;
    sheltersNear(lat, lon, mode, settings.searchRadius, SHELTER_LIMIT)
      .then((rows) => {
        if (cancelled) return;
        let list = rows.map((r) => shelterToPlace(r, mode)).filter((x): x is Place => x !== null);
        // 야외 쉼터는 난방 모드에서 의미가 없다
        if (mode === "heating") list = list.filter((x) => x.category !== "park");
        setOfficialRes({ key: queryKey, value: list });
        remember(list);
      })
      .catch((e: unknown) => {
        if (!cancelled) setOfficialRes({ key: queryKey, value: [], error: e instanceof Error ? e.message : String(e) });
      });

    // AI 추정 쉼터는 느리므로(지도 상호 수집 + AI 판단) 따로 받아 나중에 합친다
    if (settings.aiCandidates) {
      // 받는 도중에도 찾은 만큼 지도에 올린다. 끝나면 '판단 중' 표시를 내린다.
      const show = (g: Place[], done: boolean) => {
        if (cancelled) return;
        setGuessRes({ key: done ? queryKey : `${queryKey}#partial`, value: g });
        remember(g);
      };
      nearbyCandidates(
        [lat, lon],
        mode,
        settings.searchRadius,
        Math.max(20, SHELTER_LIMIT / 2),
        (g) => show(g, false),
        () => cancelled,
      )
        .then((g) => show(g, true))
        .catch(() => !cancelled && setGuessRes({ key: queryKey, value: [] }));
    }
    return () => {
      cancelled = true;
    };
  }, [ready, queryKey, searchCenter, mode, settings.searchRadius, settings.aiCandidates, remember]);

  const loading = officialRes.key !== queryKey;
  const error = loading ? "" : (officialRes.error ?? "");
  const aiLoading = settings.aiCandidates && guessRes.key !== queryKey;
  const guessesNow = guessRes.key === queryKey || guessRes.key === `${queryKey}#partial`;

  const places = useMemo(() => {
    const official = officialRes.key === queryKey ? officialRes.value : [];
    const guesses = settings.aiCandidates && guessesNow ? guessRes.value : [];
    return mergeCandidates(official, guesses, mode);
  }, [officialRes, guessRes, guessesNow, queryKey, settings.aiCandidates, mode]);
  const officialCount = places.filter((x) => x.official).length;

  const weather = useMemo(() => weatherFromObs(obs, mode, now), [obs, mode, now]);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- now 가 바뀔 때(매분) 지금 시각으로 다시 고른다
  const sky = useMemo(() => skyLine(obs, skyHours), [obs, skyHours, now]);
  const here: LngLat = me?.coord ?? origin;

  const analyzePlace = useCallback(
    (x: Place) => analyze(x, x.mode, now, x.mode === "cooling" ? settings.targetCool : settings.targetHeat, here, weatherFromObs(obs, x.mode, now)),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 좌표 값과 AI 결과 버전으로 다시 계산
    [now, settings.targetCool, settings.targetHeat, here[0], here[1], obs, nuisVersion],
  );

  const analyses = useMemo(() => {
    let out = places.map(analyzePlace);
    if (settings.onlyOfficial) out = out.filter((a) => a.place.official);
    // 도보 제한은 검색한 곳 기준으로 건다. 내 위치 기준으로 걸면 '이 지역에서 다시 찾기' 로
    // 멀리 옮긴 곳의 쉼터가 모두 걸러진다. 표시하는 거리·도보 시간은 그대로 내 위치 기준이다.
    const [lon, lat] = searchCenter;
    return out.filter((a) => walkMinutes(haversine(lat, lon, a.place.lat, a.place.lon)) <= settings.maxWalk);
  }, [places, analyzePlace, settings.onlyOfficial, settings.maxWalk, searchCenter]);

  // -- 재난문자 (내 시군구, 5분마다) ------------------------------------------------
  // 내 위치에서 3km 안의 가장 가까운 공식 쉼터 주소로 시군구를 정한다. 한 번 정하면 새로 못 찾아도 유지한다.
  useEffect(() => {
    const [lon, lat] = here;
    let best: { d: number; r: string } | null = null;
    for (const x of places) {
      if (!x.official) continue;
      const r = regionOf(x.address);
      if (!r) continue;
      const d = haversine(lat, lon, x.lat, x.lon);
      if (d <= 3000 && (!best || d < best.d)) best = { d, r };
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 쉼터 목록이 바뀌었을 때만 다시 정한다
    if (best) setRegion(best.r);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 좌표 값으로 비교
  }, [places, here[0], here[1]]);

  useEffect(() => {
    if (!region) return;
    let cancelled = false;
    const get = () =>
      disasterAlerts(region)
        .then((d) => !cancelled && setAlerts(d.alerts ?? []))
        .catch(() => {});
    get();
    const t = setInterval(get, 5 * 60_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [region]);

  const getPlace = useCallback(
    (id: string) => seen.get(id) ?? settings.favorites.find((f) => f.id === id),
    [seen, settings.favorites],
  );

  const isFavorite = useCallback((id: string) => settings.favorites.some((f) => f.id === id), [settings.favorites]);

  const toggleFavorite = useCallback(
    (x: Place) => {
      const has = settings.favorites.some((f) => f.id === x.id);
      update({ favorites: has ? settings.favorites.filter((f) => f.id !== x.id) : [...settings.favorites, x] });
    },
    [settings.favorites, update],
  );

  // -- 이용자 제보 -------------------------------------------------------------
  // 화면에 나오는 쉼터와 자주 가는 곳의 제보만 받는다. id 목록이 그대로면 다시 받지 않는다.
  const [reports, setReports] = useState<Record<string, Report>>({});
  const [reportsTick, setReportsTick] = useState(0);
  const idsKey = useMemo(
    () => [...new Set([...analyses.map((a) => a.place.id), ...settings.favorites.map((f) => f.id)])].sort().join(","),
    [analyses, settings.favorites],
  );
  useEffect(() => {
    if (!idsKey) return;
    let alive = true;
    const t = setTimeout(() => {
      recentReports(idsKey.split(","))
        .then((r) => alive && setReports(r))
        .catch(() => {
          // 제보를 못 받아도 앱은 그대로 쓸 수 있다
        });
    }, 600);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [idsKey, reportsTick]);
  useEffect(() => {
    const iv = setInterval(() => setReportsTick((k) => k + 1), 5 * 60_000);
    return () => clearInterval(iv);
  }, []);
  // 내가 보낸 제보 — 취소 버튼을 띄우려고 48시간 동안 기억한다. 기기 표식은 본인 확인용이다.
  const [myReports, setMyReports] = useState<Record<string, MyReport>>({});
  const device = useRef("");
  useEffect(() => {
    load<string>("device_id", "").then((id) => {
      if (id) {
        device.current = id;
        return;
      }
      const fresh = Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
      device.current = fresh;
      save("device_id", fresh);
    });
    load<Record<string, MyReport>>("my_reports", {}).then((all) => {
      const cut = Date.now() - 48 * 3600_000;
      setMyReports(Object.fromEntries(Object.entries(all).filter(([, r]) => r.at > cut)));
    });
  }, []);
  const rememberMine = useCallback((next: Record<string, MyReport>) => {
    setMyReports(next);
    save("my_reports", next);
  }, []);

  const report = useCallback(
    async (placeId: string, kind: ReportKind) => {
      const id = await reportShelter(placeId, kind, device.current);
      if (kind !== "ok") rememberMine({ ...myReports, [placeId]: { id, kind, at: Date.now() } });
      setReportsTick((k) => k + 1);
    },
    [myReports, rememberMine],
  );
  const myReport = useCallback(
    (placeId: string) => {
      const r = myReports[placeId];
      return r && r.at > Date.now() - 48 * 3600_000 ? r : undefined;
    },
    [myReports],
  );
  const cancelMyReport = useCallback(
    async (placeId: string) => {
      const r = myReports[placeId];
      if (!r) return;
      try {
        await cancelReport(r.id, device.current);
      } finally {
        // 이미 취소됐거나 시간이 지난 제보여도 내 목록에서는 지운다
        const next = { ...myReports };
        delete next[placeId];
        rememberMine(next);
        setReportsTick((k) => k + 1);
      }
    },
    [myReports, rememberMine],
  );

  const value: Store = {
    ready,
    settings,
    update,
    mode,
    p,
    target,
    now,
    me,
    origin,
    here: me?.coord ?? (located ? origin : null),
    located,
    locationNotice,
    locate,
    searchCenter,
    setSearchCenter,
    weather,
    sky,
    region,
    alerts,
    loading,
    aiLoading,
    error,
    officialCount,
    aiCount: places.length - officialCount,
    analyses,
    analyzePlace,
    getPlace,
    isFavorite,
    toggleFavorite,
    reload: () => setReloadKey((k) => k + 1),
    reports,
    report,
    myReport,
    cancelMyReport,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
