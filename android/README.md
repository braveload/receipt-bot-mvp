# 영수증 정리 어플 - Android (Kotlin + Jetpack Compose)

웹앱(`app/static/webapp.html`)과 동일한 REST API(`app/web_api.py`, `https://receipt-bot-mvp-sg.onrender.com/api/`)를 사용하는 네이티브 안드로이드 앱입니다.

## 스택
- Kotlin, Jetpack Compose (Material 3), MVVM
- Retrofit + OkHttp (네트워킹), Gson
- AndroidX DataStore Preferences (JWT 토큰 저장)
- minSdk 26 / targetSdk 34

## 열기
1. Android Studio (최신 버전, JDK 17 필요)에서 `android/` 폴더를 "Open" 으로 연다.
2. Gradle sync 자동 진행 (첫 sync 시 Compose BOM 2024.06.00, AGP 8.5.2 등 다운로드).
3. 에뮬레이터 또는 실기기 연결 후 Run.

기본 `API_BASE_URL`은 배포된 Render 서버(`https://receipt-bot-mvp-sg.onrender.com/api/`)로 설정되어 있습니다. 로컬 백엔드로 테스트하려면:

```
./gradlew assembleDebug -PapiBaseUrl=http://10.0.2.2:8000/api/
```

(에뮬레이터에서 `10.0.2.2`는 호스트 PC의 `localhost`를 가리킵니다.)

## 권한
- INTERNET (API 통신)
- CAMERA (영수증 촬영)

## 빌드 검증 상태
- `compileDebugKotlin`까지 실제로 실행하여 컴파일 에러 4건(아이콘 미해결 참조, ExposedDropdownMenu 임포트 오류, `Modifier.size` 임포트 누락, ExperimentalMaterial3Api 범위 문제)을 발견하고 모두 수정 완료.
- 수정 후 `compileDebugKotlin`이 에러 없이 완료되고 dexing 단계(`mergeExtDexDebug`)까지 정상 진행되는 것을 확인함.
- 다만 이 작업 환경(샌드박스)은 CPU 자원이 제한적이라 `assembleDebug` 전체(리소스 링킹 + APK 패키징)를 끝까지 완주하지는 못했습니다. 소스 코드 자체의 컴파일 오류는 없는 것으로 확인되었으나, **최종 APK 생성 및 기기에서의 정상 실행 확인은 Android Studio에서 직접 진행해주셔야 합니다.**
