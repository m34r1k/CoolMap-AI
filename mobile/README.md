# CoolMap 모바일 (Android)

데스크톱 앱과 같은 CoolMap 서버(Supabase)를 쓰는 Android 앱입니다. Expo(React Native) + MapLibre.

| 항목 | 출처 |
|---|---|
| 지도 | OpenFreeMap (키 불필요) |
| 쉼터 | `shelters_near` RPC — 현재 위치 반경 3km |
| 기온 | `weather` Edge Function |
| 현재 위치 | `expo-location` |

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
