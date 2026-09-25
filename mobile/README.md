# CoolMap 모바일 (Android · iOS)

데스크톱 앱과 같은 CoolMap 서버(Supabase)를 쓰는 Android·iOS 앱입니다. Expo(React Native) + Expo Router + MapLibre.
화면 구성과 계산은 데스크톱 앱(`../coolmap`)을 그대로 옮겼습니다.

| 화면 | 데스크톱 원본 |
|---|---|
| 홈 (모드 전환 · 목표 온도 · 지도 미리보기 · AI 추천) | `ui/home.py` |
| 지도 (공식 쉼터 · AI 추정 쉼터 · 건물 하이라이트 · 5가지 정렬) | `ui/mapview.py` |
| 장소 상세 (온도 · AI 쾌적 점수 · 혼잡도 준비 중 · 민폐도 · 추천 이유) | `ui/detail.py` |
| AI 추천 대화 | `ui/chat.py`, `assistant.py` |
| 즐겨찾기 · 설정 | `ui/favorites.py`, `ui/settings_view.py` |

| 항목 | 출처 | 코드 |
|---|---|---|
| 지도 | OpenFreeMap (키 불필요) | `src/mapStyle.ts` |
| 쉼터 | `shelters_near` RPC — 현재 위치 반경 (기본 2.5km) | `src/places.ts` |
| 기온 | `weather` Edge Function | `src/analysis.ts` |
| 민폐도 | `ai` Edge Function (Gemini) → 실패 시 규칙 기반 | `src/nuisance.ts`, `src/analysis.ts` |
| AI 추정 쉼터 | Overpass(OSM 상호) + `ai` Edge Function 판단 | `src/candidates.ts` |
| 현재 위치 | `expo-location` | `src/store.tsx` |

분류 규칙·추정치·루브릭 허용값은 데스크톱 코드와 같아야 합니다. 한쪽을 고치면 다른 쪽도 고칩니다.
혼잡도는 데스크톱처럼 'COMING SOON' 이고, 행사(이벤트) 정보는 데스크톱에서도 데모 데이터라 옮기지 않았습니다.

## 처음 한 번

1. **서버에 RPC 적용** — `../supabase/migrations/20260924000000_shelters_near.sql` 을
   Supabase 대시보드 SQL Editor 에서 실행합니다.
2. **Android Studio 설치** — 설치 마법사에서 Android SDK 와 에뮬레이터를 함께 설치합니다.
3. **환경변수** (Windows 설정 → 시스템 환경 변수)
   - `JAVA_HOME` = **JDK 17** 경로 (예: `C:\dev\jdk17`, [Temurin 17](https://adoptium.net/) zip 을 풀어 둔 곳)
     — Android Studio 에 들어 있는 JDK(`jbr`, 24 이상)는 쓰지 않습니다. prefab 이 출력하는
     'restricted method' 경고 때문에 `configureCMakeDebug` 단계에서 빌드가 실패합니다.
   - `ANDROID_HOME` = `%LOCALAPPDATA%\Android\Sdk`
   - `Path` 에 `%ANDROID_HOME%\platform-tools` 추가
4. **경로에 한글·공백이 없는 곳에서 빌드** — Android 네이티브 빌드(CMake)는 경로에 한글이나
   공백이 있으면 실패합니다. 예: `git clone … C:\dev\coolmap` 후 `C:\dev\coolmap\mobile` 에서 실행.

## 실행

```bash
npm install
npx expo run:android      # 연결된 폰(USB 디버깅) 또는 켜 둔 에뮬레이터에 설치·실행
```

MapLibre 는 네이티브 모듈이라 Expo Go 로는 열리지 않습니다. 위 명령이 개발 빌드를 만들어 설치합니다.
한 번 설치한 뒤에는 JS 만 바꿨다면 `npx expo start` 로 다시 띄우면 됩니다.

`android/` 폴더는 빌드할 때 자동으로 만들어지며 저장소에 올리지 않습니다. 네이티브 설정은 `app.json` 에서 바꿉니다.

## APK 만들기 (지인 배포용)

```bash
npx expo prebuild --platform android      # android/ 가 없을 때만
cd android
./gradlew app:assembleRelease -PreactNativeArchitectures=armeabi-v7a,arm64-v8a,x86_64
# → android/app/build/outputs/apk/release/app-release.apk
```

`npx expo run:android --variant release` 는 **연결된 기기의 CPU 용으로만** 빌드하므로
(에뮬레이터면 x86_64 전용) 배포용으로 쓰지 않습니다.

받은 사람은 휴대폰에서 '출처를 알 수 없는 앱 설치'를 허용해야 설치됩니다.

지금은 Expo 템플릿의 테스트용 키(`debug.keystore`)로 서명합니다. 지인 배포에는 충분하지만
Play 스토어에 올리려면 전용 서명 키를 만들어야 합니다.

## iOS (Mac 에서)

iOS 빌드는 Mac + Xcode 에서만 됩니다. Supabase 주소·키는 코드에 들어 있어 따로 설정할 것은 없습니다.

1. **App Store 에서 Xcode 설치** → 한 번 실행해 추가 구성요소 설치를 끝냅니다.
   Xcode → Settings → Components 에서 iOS 시뮬레이터도 받습니다.
2. **도구 설치** (터미널)
   ```bash
   xcode-select --install          # 명령줄 도구 (이미 있으면 건너뜀)
   brew install node cocoapods     # Homebrew 가 없으면 https://brew.sh 먼저
   ```
3. **코드 받기**
   ```bash
   git clone https://github.com/m34r1k/CoolMap-AI.git ~/dev/coolmap
   cd ~/dev/coolmap/mobile
   npm install
   ```
4. **시뮬레이터에서 실행** — `npx expo run:ios`
   (시뮬레이터 위치는 Features → Location → Custom Location 에서 바꿉니다)
5. **내 아이폰에서 실행** — 아이폰을 USB 로 연결하고 `npx expo run:ios --device`
   - 처음에는 `open ios/CoolMap.xcworkspace` → CoolMap 타깃 → Signing & Capabilities 에서
     Team 에 내 Apple ID 를 넣습니다.
   - 아이폰: 설정 → 개인정보 보호 및 보안 → 개발자 모드 켜기,
     설정 → 일반 → VPN 및 기기 관리 에서 내 Apple ID 를 신뢰.
   - 무료 Apple ID 로 설치한 앱은 7일 뒤 열리지 않습니다. 다시 설치하면 됩니다.

`ios/` 폴더도 `android/` 처럼 자동으로 만들어지며 저장소에 올리지 않습니다.

### 다른 사람 아이폰에 나눠 주기

Apple Developer Program(연 $99)이 필요합니다. 가입 후 TestFlight 로 초대하는 것이 가장 간단합니다.

```bash
npm install -g eas-cli
eas login
eas build -p ios --profile production   # 인증서·프로비저닝은 EAS 가 물어보며 만들어 줌
eas submit -p ios                       # App Store Connect 로 업로드 → TestFlight 에서 초대
```
