# Claude Code 인수인계

## 1. 프로젝트 목적

영수증봇은 카카오톡으로 받은 영수증을 OCR 처리하고, 사용자가 확인·수정·저장한
내역을 월별 Excel 보고서로 제공하는 FastAPI 서비스입니다. 같은 FastAPI 배포에서
리로웍스 회사 홈페이지와 테스트 문의 접수 기능도 제공합니다.

## 2. 현재 배포 상태

- 운영 서비스: `https://receipt-bot-mvp-sg.onrender.com`
- GitHub: `braveload/receipt-bot-mvp`
- 브랜치: `main`
- 배포 커밋: `2cd5db3`
- Render 자동 배포: 활성화
- 배포 전 커밋 기준 검증: `37 passed`
- 엣지케이스 데모 및 `site/script.js` 문법 검사: 통과
- 운영 HTTP 검증:
  - `/`
  - `/health`
  - `/privacy.html`
  - `/terms.html`
  - `/robots.txt`
  - `/sitemap.xml`
  - `/og.png`
  - 모두 HTTP 200

## 3. 주요 구조

| 경로 | 역할 |
|---|---|
| `app/main.py` | FastAPI 라우트, 홈페이지, 카카오 웹훅 |
| `app/contact.py` | 문의 검증, 제한, SMTP 알림 |
| `app/storage.py` | SQLite/PostgreSQL 저장소 |
| `app/extractor.py` | OCR 공급자 인터페이스와 이미지 처리 |
| `app/report.py` | Excel 보고서와 금액·공급가액·부가세 합계 |
| `site/` | 홈페이지, 정책 페이지, 로고, 공유 이미지 |
| `tests/` | 회귀·보안·문의·홈페이지 테스트 |
| `render.yaml` | 신규 Render 구성 참고용 Blueprint |

## 4. 문의 접수 계약

`POST /api/contact`

```json
{
  "name": "2~80자",
  "contact": "전화번호 또는 이메일, 5~120자",
  "message": "10~2000자",
  "privacy_consent": true,
  "website": ""
}
```

- 정상: HTTP 201, `{"ok": true, "reference": "RW-..."}`
- 입력 오류: HTTP 422
- 반복 제한: HTTP 429
- DB 저장 후 SMTP 알림을 실행합니다.
- SMTP 실패는 문의 API 성공을 취소하지 않으며 `email_status=failed`로 남습니다.
- IP 원문은 저장하지 않고 HMAC 해시만 저장합니다.

## 5. Render 환경변수

확인된 기존 값:

- `DATABASE_URL`
- `EXTRACTOR`
- `GOOGLE_VISION_API_KEY`
- `REPORT_SIGNING_SECRET`
- `STORE_RECEIPT_IMAGES`

2026-07-25 추가한 값:

- `PUBLIC_BASE_URL=https://receipt-bot-mvp-sg.onrender.com`
- `CONTACT_EMAIL_TO=reromoon@naver.com`
- `SMTP_HOST=smtp.naver.com`
- `SMTP_PORT=465`
- `CONTACT_HASH_SECRET` — Render 비밀값
- `REPORT_LINK_TTL_SECONDS=600`

아직 사용자 입력이 필요한 값:

- `SMTP_USERNAME`
- `SMTP_PASSWORD`

네이버 SMTP를 실제 발송 상태로 전환하려면 위 두 값을 Render 비밀 환경변수로
추가하고 재배포해야 합니다. 비밀번호는 저장소나 문서에 기록하지 않습니다.

## 6. 로컬 작업 시 주의

현재 OneDrive 작업 폴더에는 운영 배포에 포함하지 않은 수정 파일과 산출물 폴더가
남아 있을 수 있습니다. 다음 작업 전 반드시 `git status --short`로 범위를 확인하고,
`git add .`, 강제 reset, 일괄 삭제를 사용하지 마세요. 필요한 파일만 명시적으로
스테이징합니다.

특히 운영 최신 커밋에 포함된 Kakao CDN 이미지 판별, Pillow 리사이즈,
`tests/test_kakao_adapter.py` 회귀 테스트를 퇴행시키지 않아야 합니다.

## 7. 다음 권장 작업

1. 사용자에게 네이버 SMTP 아이디와 앱 비밀번호의 Render 직접 입력을 요청합니다.
2. SMTP 설정 후 테스트 문의 1건으로 DB 저장, 접수번호, 메일 수신을 확인합니다.
3. 실제 카카오 영수증 이미지로 OCR·확인·저장·삭제·Excel 다운로드를 재검증합니다.
4. 도메인 구매가 확정되면 `PUBLIC_BASE_URL`, canonical, sitemap을 새 도메인으로
   변경합니다.

