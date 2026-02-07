# Log Tail Collector (Windows 단일 서버)

## 프로젝트 개요 (비전공자용)
이 프로젝트는 Windows 단일 서버에서 로그 파일이 추가될 때마다 내용을 읽어(SQLite에 저장) 웹 화면에서 실시간으로 보여주는 시스템입니다. 운영자가 문제를 빠르게 파악할 수 있도록 규칙 기반 파싱, Admin 화면, Slack 알림까지 포함한 운영형 구성을 제공합니다.

## Windows 설치/실행 절차
1. **Python 3.10+ 설치**
2. 프로젝트 루트에서 의존성 설치
   ```powershell
   python -m venv .venv
   # 실행 정책에 막히는 경우 현재 세션만 허용
   Set-ExecutionPolicy -Scope Process Bypass
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```
3. `.env.example`을 복사하여 `.env` 생성 후 환경 변수 설정
   ```powershell
   Copy-Item .env.example .env
   ```
4. 실행
   - PowerShell에서 실행 파일이 메모장으로 열리는 경우가 있으니 반드시 **PowerShell에서 직접 실행**합니다.
   ```powershell
   # 실행 정책에 막히는 경우 Bypass로 실행
   powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
   ```
   - 이미 PowerShell 세션 내라면 다음처럼 실행합니다.
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\run.ps1
   ```
   - `uvicorn` 인식 오류가 나면 venv가 활성화되지 않은 상태일 수 있습니다. 다음을 확인하세요.
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
   ```
   - `No module named uvicorn` 오류가 나면 의존성이 설치되지 않은 상태입니다.
   ```powershell
   python -m pip install -r requirements.txt
   ```
5. 방화벽에서 TCP 8000 포트 허용
   ```powershell
   New-NetFirewallRule -DisplayName "LogTail 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
   ```

## 사용자 페이지 사용법
- 브라우저에서 `http://localhost:8000/` 접속
- device, grp, file, parse_ok 필터 적용 가능
- raw 체크 시 원본 라인 표시
- SSE 연결 실패 시 10초 폴링으로 자동 폴백

## 관리자 페이지 사용법
- `http://localhost:8000/admin` 접속 (Basic Auth)
- ADMIN 전용 기능: 규칙/라벨/알림/Export/Import
- 조회 계정은 VIEWER 계정 사용

## 예외규칙 예시 8개
1. IGNORE_LINE_REGEX: `^#` 주석 무시
2. FORCE_HEADER_REGEX: `^HEADER:` 라인을 헤더로 강제
3. DEVICE_REWRITE_REGEX: `^noise` 제거
4. LINE_REPLACE_REGEX: `;` → 탭 치환
5. DELIMITER_OVERRIDE: 특정 파일에 delimiter `;` 강제
6. VALUECOUNT_RANGE_ENFORCE: 3~10 사이 값만 허용
7. DROP_VALUE_INDEXES: [0, 3] 인덱스 제거
8. COERCE_NUMERIC: 모든 값을 float로 강제

## Slack Incoming Webhook 설정
1. Slack 앱 생성
2. Incoming Webhooks 활성화
3. Add New Webhook to Workspace 클릭
4. 채널 선택 후 Webhook URL 발급
5. `.env`에 `WEBHOOK_URL` 설정

## .env 설정 예시
```text
DB_PATH=./data.db
LOG_DIR=./sample_logs
INCLUDE_FILES=*
ADMIN_USER=admin
ADMIN_PASS=admin
VIEWER_USER=viewer
VIEWER_PASS=viewer
WEBHOOK_URL=https://hooks.slack.com/services/...
WEBHOOK_TIMEOUT_SEC=5
WEBHOOK_DISABLE=0
ALERT_COOLDOWN_DEFAULT=60
```

## PowerShell로 Slack Webhook 테스트 방법
```powershell
$body = @{ text = "[INFO] 테스트 알림" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $Env:WEBHOOK_URL -Body $body -ContentType "application/json"
```

## 레이트리밋/쿨다운/중복방지 설명
- 정책별 `cooldown_sec` 동안 동일 dedup_key는 재발송 금지
- Slack 429 시 `Retry-After` 헤더를 존중하여 재시도

## 알림 실패 시 동작
- Slack 전송 실패 시 `alerts.status=FAILED`로 기록
- `/admin` 페이지에서 상태 확인 가능

## sqlite 운영 점검 쿼리 예시
```sql
SELECT record_type, COUNT(*) FROM events GROUP BY record_type;
SELECT status, COUNT(*) FROM alerts GROUP BY status;
SELECT * FROM audit_log ORDER BY id DESC LIMIT 20;
```

## 참고 (Windows 환경 이슈)
- 파일 잠금이 있는 경우 ingest가 해당 파일을 스킵하고 다음 주기에 재시도합니다.
- UTF-8 디코딩 실패 시 CP949로 자동 폴백합니다.
