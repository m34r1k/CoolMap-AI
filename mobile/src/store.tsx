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
import { sheltersNear, weather as fetchWeather } from "./backend";
import { mergeCandidates, nearbyCandidates } from "./candidates";
import { onNuisance } from "./nuisance";
import { type Place, shelterToPlace } from "./places";
import { load, save } from "./storage";
import { defaultMode, type Mode, type Palette, PALETTES } from "./theme";

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
  located: boolean;
  locationNotice: string;
  locate: () => Promise<LngLat | null>;
  searchCenter: LngLat;
  setSearchCenter: (c: LngLat) => void;

  weather: Weather;
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
  const [officialRes, setOfficialRes] = useState<Loaded<Place[]>>({ key: "", value: [] });
  const [guessRes, setGuessRes] = useState<Loaded<Place[]>>({ key: "", value: [] });
  // 한 번이라도 목록에 실렸던 장소 — 상세 화면은 id 로만 찾으므로, 목록이 바뀐 뒤에도 열 수 있게 둔다
  const [seen, setSeen] = useState<ReadonlyMap<string, Place>>(new Map());
  const [nuisVersion, setNuisVersion] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  const mode = settings.mode;
  const p = PALETTES[mode];
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
        .then((w) => !cancelled && setObs(w.now))
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
  const here: LngLat = me?.coord ?? origin;

  const analyzePlace = useCallback(
    (x: Place) => analyze(x, x.mode, now, x.mode === "cooling" ? settings.targetCool : settings.targetHeat, here, weatherFromObs(obs, x.mode, now)),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 좌표 값과 AI 결과 버전으로 다시 계산
    [now, settings.targetCool, settings.targetHeat, here[0], here[1], obs, nuisVersion],
  );

  const analyses = useMemo(() => {
    let out = places.map(analyzePlace);
    if (settings.onlyOfficial) out = out.filter((a) => a.place.official);
    return out.filter((a) => a.walkMin <= settings.maxWalk);
  }, [places, analyzePlace, settings.onlyOfficial, settings.maxWalk]);

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
    located,
    locationNotice,
    locate,
    searchCenter,
    setSearchCenter,
    weather,
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
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
