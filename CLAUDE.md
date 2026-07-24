# 영수증봇 / RERO WORKS 작업 지침

이 파일은 Claude Code가 저장소를 열었을 때 가장 먼저 읽어야 하는 프로젝트 안내입니다.
세부 인수인계는 `docs/CLAUDE_HANDOFF.md`, 공통 개발 규칙은 `AGENTS.md`를 함께 확인하세요.

## 현재 운영 기준

- GitHub: `https://github.com/braveload/receipt-bot-mvp`
- 기준 브랜치: `main`
- Render 서비스: `receipt-bot-mvp-sg`
- 운영 URL: `https://receipt-bot-mvp-sg.onrender.com`
- 홈페이지 배포 기준 커밋: `2cd5db3`
- 2026-07-25 운영 확인: `/`, `/health`, 정책 페이지, `robots.txt`,
  `sitemap.xml`, `og.png` 모두 HTTP 200

## 시작 전 필수 확인

1. `git status --short`와 `git log -5 --oneline`을 먼저 확인합니다.
2. 이 로컬 작업 폴더에는 배포 커밋에 포함되지 않은 사용자 파일과 수정사항이 남아 있을 수 있습니다.
3. 요청 범위 밖 파일을 일괄 스테이징하거나 되돌리지 않습니다.
4. `AGENTS.md`의 Ponytail gate를 적용하고 기존 FastAPI·표준 라이브러리·설치된
   의존성을 우선 재사용합니다.
5. 완료 전 전체 테스트와 관련 데모를 실행합니다.

## 자주 쓰는 명령

```powershell
python -m pytest -q
python demo/edge_case_check.py
node --check site/script.js
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

로컬 기본 홈페이지는 `http://127.0.0.1:8000/`, 헬스체크는
`http://127.0.0.1:8000/health`입니다.

## 변경 금지 계약

- `/kakao/webhook`
- `/report/{user_id}/excel`
- `/health`

위 기존 공개 계약은 명시적인 요청 없이 변경하지 않습니다. 문의 API는
`POST /api/contact`이며 DB 저장이 SMTP 알림보다 먼저 완료되어야 합니다.

## 배포 원칙

- Render는 GitHub `main` 푸시를 감지해 자동 배포합니다.
- 푸시 전 깨끗한 커밋 기준으로 테스트합니다.
- 배포 완료 후 Render의 성공 상태만 보지 말고 운영 URL의 `/health`와 변경된
  기능을 직접 확인합니다.
- 비밀값은 코드, 문서, 커밋, 로그에 기록하지 않습니다.
- 현재 SMTP 로그인 값은 아직 설정되지 않았을 수 있으므로
  `docs/CLAUDE_HANDOFF.md`의 환경변수 상태를 확인합니다.

