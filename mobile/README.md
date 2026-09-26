# CoolMap 모바일 (Android · iOS)

데스크톱 앱과 같은 CoolMap 서버(Supabase)를 쓰는 Android · iOS 앱입니다. 코드는 하나이고 두 플랫폼에서 같이 돌아갑니다. Expo(React Native) + Expo Router + MapLibre.
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

## 처음 한 번 (Android)

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

## 실행 (Android)

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

Mac 에서 빌드할 때는 Android Studio 의 SDK Manager 에서 **SDK Platform 36 · NDK 27.1.12297006 · CMake 3.22.1**
을 받고, 아래처럼 환경변수를 붙여 실행합니다.

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17) ANDROID_HOME=$HOME/Library/Android/sdk
```

### 새 버전 배포 (앱 안 업데이트)

앱은 켤 때 GitHub 릴리스를 보고 새 버전이 있으면 홈 맨 위에 알림을 띄웁니다 (`src/update.ts`).

1. `app.json` 의 `version` 과 `android.versionCode` 를 올립니다 (versionCode 는 반드시 커져야 설치됨).
2. 위 방법으로 APK 를 빌드합니다.
3. GitHub 에 **`mobile-v<version>`** 태그로 릴리스를 만들고 `.apk` 를 첨부합니다.
   (예: `mobile-v0.2.6`. 데스크톱 릴리스 `v0.x` 와 섞이지 않게 `mobile-` 을 붙입니다.)
   릴리스 설명은 앱에 보이지 않으니 자유롭게 씁니다.

서명 키가 바뀌면 기존 앱 위에 설치되지 않습니다. 계속 같은 `debug.keystore`(Expo 템플릿 기본)로 서명합니다.
0.2.4 이하를 쓰는 사람은 업데이트 기능이 없으므로 0.2.5 APK 를 한 번 직접 설치해야 합니다.

지금은 Expo 템플릿의 테스트용 키(`debug.keystore`)로 서명합니다. 지인 배포에는 충분하지만
Play 스토어에 올리려면 전용 서명 키를 만들어야 합니다.

## iOS (Mac 필요)

iOS 빌드는 Mac 에서만 됩니다. 서버 RPC(위 1번)는 Android 와 같이 한 번만 적용하면 됩니다.

### 처음 한 번

1. **Xcode** 를 App Store 에서 설치하고 한 번 실행해 추가 구성요소를 설치합니다.
2. **iOS 시뮬레이터 런타임** — Xcode → Settings → Components 에서 iOS 를 받거나
   `xcodebuild -downloadPlatform iOS` 를 실행합니다. (`xcrun simctl list runtimes` 에 iOS 가 보이면 됨)
3. **CocoaPods** — `brew install cocoapods`

### 시뮬레이터에서 실행

```bash
npm install
npx expo run:ios            # 시뮬레이터를 띄우고 개발 빌드를 설치·실행
```

위치는 시뮬레이터 메뉴 Features → Location → Custom Location 에서 위도·경도를 넣어 바꿉니다
(예: 서울시청 37.5663, 126.9779).

`ios/` 폴더도 빌드할 때 자동으로 만들어지며 저장소에 올리지 않습니다. 설정은 `app.json` 의 `ios` 에서 바꿉니다.

iOS 27 SDK(Xcode 27)로 빌드한 앱은 UIScene 생명주기를 쓰지 않으면 실행하자마자 멈춥니다.
Expo SDK 57 템플릿은 아직 그렇게 되어 있지 않아 `plugins/withSceneLifecycle.js` 가 `ios/` 를 만들 때
SDK 58 템플릿과 같게 고칩니다. Expo SDK 58 이상으로 올리면 이 플러그인을 지웁니다.

### 내 아이폰에 설치 (무료 Apple ID)

1. 아이폰을 Mac 에 케이블로 연결하고 '이 컴퓨터를 신뢰' 를 누릅니다.
2. 아이폰 설정 → 개인정보 보호 및 보안 → **개발자 모드** 를 켭니다 (재시동됨).
3. `open ios/CoolMap.xcworkspace` → CoolMap 타깃 → Signing & Capabilities 에서
   Team 에 본인 Apple ID 를 추가·선택합니다. (번들 ID 가 겹친다고 하면 `app.json` 의
   `ios.bundleIdentifier` 끝에 아무 글자나 붙입니다)
4. `npx expo run:ios --device --configuration Release` 로 설치합니다.
   Release 로 설치하면 Mac 의 개발 서버 없이도 앱이 열립니다.
5. 처음 열 때 막히면 아이폰 설정 → 일반 → VPN 및 기기 관리 에서 본인 계정을 신뢰합니다.

무료 Apple ID 로 설치한 앱은 **7일 뒤에 열리지 않습니다.** 다시 연결해 4번을 실행하면
7일이 연장되고, 지우지 않고 덮어 설치하므로 즐겨찾기·설정은 남습니다.
친구 아이폰도 같은 방법으로 설치할 수 있지만 7일마다 Mac 에 연결해야 합니다.

### 여러 사람에게 배포

iOS 에는 APK 처럼 파일로 나눠 주는 방법이 없습니다.
Apple Developer Program(연 $99)에 가입한 뒤 TestFlight(초대 링크로 설치, 빌드당 90일)나
App Store 로 배포합니다.
