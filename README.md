# 영수증봇 MVP — 백엔드 스캐폴드

`SaaS_비즈니스모델_설계서_영수증정리.docx`의 5장(제품 정의) MVP 범위를 실제로 동작하는
코드로 구현한 것입니다. 카카오톡 채널에 영수증 사진을 보내면 자동으로 상호명·금액·카테고리를
추출해 분류하고, "이번달"이라고 물으면 요약을, 신고철엔 세무사 전달용 엑셀을 만들어줍니다.

## 구조

```
receipt-bot-mvp/
  app/
    main.py            FastAPI 웹훅 서버 (카카오 스킬서버 엔드포인트)
    kakao_adapter.py    카카오 payload 파싱 + 응답 포맷
    extractor.py         영수증 이미지 -> 정형 데이터 (Mock / Claude Vision / Google Vision)
    storage.py            SQLite 저장
    report.py              월간 요약 텍스트 + 엑셀 내보내기
  demo/
    run_demo.py         카카오 계정 없이 전체 흐름을 검증하는 데모 스크립트
```

## 동작 흐름

1. 사용자가 카카오톡 채널에 영수증 사진 전송
2. 카카오 i 오픈빌더가 등록된 스킬서버(`/kakao/webhook`)를 호출
3. `extractor.py`가 이미지에서 상호명/금액/일자/카테고리/사업·개인 여부를 한 번에 추출
   (전통적인 "OCR API + 별도 분류 LLM" 2단계 대신, Claude Vision 한 번 호출로 단순화)
4. SQLite에 저장, 카카오톡으로 분류 결과 즉시 회신
5. "이번달" 발화 시 월간 요약, "신고파일" 관련 발화 시 엑셀 다운로드 안내

## 로컬에서 데모 실행 (계정/API 키 불필요)

```bash
pip install -r requirements.txt
EXTRACTOR=mock python demo/run_demo.py
```

가짜 영수증 5건이 처리되는 과정, 월간 요약, 엑셀 생성까지 한 번에 확인할 수 있습니다.
(실행 확인 완료 — 정상 동작합니다.)

엣지케이스(비정상 요청/추출 실패/웹훅 시크릿/.env 로딩/엑셀 다운로드)도 별도로 검증했습니다:

```bash
EXTRACTOR=mock python demo/edge_case_check.py
```

## 실제 서버로 띄우기

```bash
pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY 채워넣기
EXTRACTOR=claude uvicorn app.main:app --host 0.0.0.0 --port 8000
```

카카오 오픈빌더가 이 서버를 호출하려면 공인 HTTPS 주소가 필요합니다.
(Render / Railway / Fly.io 무료 티어로 충분히 시작 가능)

## 무료로 시작하기: Google Cloud Vision (Anthropic 크레딧 없이)

Claude Vision은 유료(크레딧 필요)입니다. 크레딧 결제 전이거나 비용을 아예 안 쓰고
싶다면 Google Cloud Vision OCR(월 1,000건 무료 티어)로 대체할 수 있습니다.

```bash
EXTRACTOR=google GOOGLE_VISION_API_KEY=발급받은키 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Claude Vision과의 차이점 (중요)**: Google Vision API는 이미지에서 텍스트만
뽑아줄 뿐, "이게 상호명이고 이게 금액이고 이 카테고리다"까지 판단해주지 않습니다.
그래서 OCR로 뽑은 텍스트를 `extractor.py`의 `parse_receipt_text()`가 정규식/키워드
규칙으로 파싱합니다 (상호명 = 첫 줄, 금액 = "합계/총액" 키워드가 있는 줄의 숫자,
카테고리 = 업종 키워드 사전 매칭). 규칙 기반이라 다음과 같은 한계가 있습니다.

- 영수증 레이아웃이 특이하면(세로 영수증, 로고만 있고 상호명 텍스트가 없는 경우 등)
  상호명을 잘못 뽑을 수 있습니다.
- 키워드 사전에 없는 업종(예: "네이버클라우드" 같은 IT 서비스)은 전부 "기타"로
  분류됩니다. `extractor.py`의 `_CATEGORY_KEYWORDS` 딕셔너리에 키워드를 추가해서
  개선할 수 있습니다.
- 그래서 이 경로로 추출한 결과는 confidence를 항상 0.5로 고정해뒀습니다 —
  카카오톡 응답에 "확인 필요" 안내가 항상 붙습니다 (main.py 로직).

**API 키 발급 방법** (직접 진행 필요, 계정/결제 정보라 대신 해드릴 수 없습니다):
1. console.cloud.google.com에서 새 프로젝트 생성
2. "Cloud Vision API" 사용 설정
3. API 및 서비스 → 사용자 인증 정보 → API 키 생성
4. (권장) 키 제한사항에서 "Cloud Vision API"만 허용하도록 제한
5. 무료 티어는 결제 계정 등록이 필요할 수 있지만, 월 1,000건까지는 과금되지 않습니다

## 실서비스 전환 전 준비해야 할 것 (체크리스트)

이 코드는 뼈대입니다. 실제로 카카오톡에서 동작하게 하려면 아래를 직접 준비해야 합니다.

- [ ] **카카오 비즈니스 채널** 개설 (사업자 인증 필요, 이전에 안내드린 항목)
- [ ] **카카오 i 오픈빌더**에서 챗봇 생성 → 스킬 등록 → 스킬 URL을 위 서버의
      `/kakao/webhook` 주소로 연결. 이 과정에서 실제 이미지 전송 payload를
      한 번 테스트 전송 해보고 `kakao_adapter.py`의 `extract_image_url()`이 맞는
      필드를 읽고 있는지 확인·수정 필요 (공식 문서가 로그인 후에만 전체 공개되어
      정확한 필드 경로는 실제 등록 후 확정해야 합니다).
- [ ] **Anthropic API 키** 발급 (console.anthropic.com) — 영수증 이미지 추출에 사용
- [ ] **호스팅**: Render/Railway 등에 배포해 공인 URL 확보
- [ ] **월간 요약 자동 발송**: 현재는 사용자가 "이번달"이라고 물어야 응답하는
      수동(reactive) 방식입니다. 설계서처럼 매달 1회 먼저 보내려면 카카오톡
      채널의 "친구톡/알림톡" API(별도 심사·템플릿 승인 필요)를 추가 연동해야 합니다.
- [ ] **개인정보 마스킹**: 영수증에 카드번호 뒷자리 등이 찍혀있을 수 있어
      저장 전 마스킹 처리가 필요합니다 (현재 미구현, 설계서 FAQ에 안내된 항목).
- [ ] **DB 교체**: SQLite는 데모용입니다. 사용자가 늘면 Postgres 등으로 교체 권장.
- [ ] **웹훅 보호**: `.env`에 `WEBHOOK_SECRET` 값을 넣으면, 요청 헤더
      `X-Webhook-Secret`이 일치할 때만 처리하도록 최소한의 보호가 걸립니다
      (미설정 시에는 검증을 건너뜁니다 — 로컬 데모 편의). 카카오 오픈빌더가
      커스텀 헤더를 스킬 서버로 전달할 수 있는지 등록 화면에서 확인 후 값을
      맞춰 넣으세요.

## 코드 점검 중 발견해서 고친 문제 (2차 리뷰)

1분기 코드를 다시 검토하면서 실제로 있었던 버그 3개를 고쳤습니다.

- **모델명 오류**: `ClaudeVisionExtractor` 기본 모델을 `claude-sonnet-4-5`로 잘못
  써뒀습니다. 존재하지 않는 모델 문자열이라 `EXTRACTOR=claude`로 전환하는 순간
  API가 에러를 냈을 것입니다. `claude-sonnet-5`로 수정했습니다.
- **추출 실패 시 500 에러**: Claude가 JSON이 아닌 답을 주거나 이미지 다운로드가
  실패하면 서버가 그대로 죽어서(500) 카카오톡에 아무 응답도 못 가는 상태였습니다.
  지금은 실패해도 사용자에게 "다시 시도해주세요" 같은 정상 답장이 가도록 고쳤습니다.
- **Mock 추출기 재시작 버그**: 요청마다 `MockReceiptExtractor`를 새로 만들어서
  항상 첫 번째 샘플만 반환하던 문제 — 데모 스크립트를 처음 돌렸을 때 실제로
  발견했습니다. 프로세스당 하나만 재사용하도록 고쳤습니다.

추가로 `.env` 파일이 실제로 로드되게 `python-dotenv`를 연결했고, 위 모든 수정 사항은
`demo/edge_case_check.py`로 재현·검증했습니다.

## 알려진 제약 (아직 안 고친 것)

- `MockReceiptExtractor`는 실제 이미지 내용을 보지 않고 샘플 5개를 순환 반환합니다
  (API 키 없이 파이프라인 로직만 검증하기 위함).
- `GoogleVisionExtractor`(무료 대안)는 정규식/키워드 기반 파싱이라 Claude Vision보다
  정확도가 낮습니다 — 위 "무료로 시작하기" 섹션의 한계 참고.
- 이미지 URL 파싱(`extract_image_url`)은 카카오 실제 계정 연동 후 검증 필요합니다.
- `/report/{user_id}/excel` 다운로드 엔드포인트는 인증이 없어 user_id를 알면 누구나
  접근 가능합니다. 실사용자 데이터가 쌓이기 전에 인증/서명된 링크로 교체가 필요합니다.
