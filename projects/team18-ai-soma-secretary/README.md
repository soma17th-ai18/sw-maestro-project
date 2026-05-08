# AI Soma Secretary

Webex로 들어오는 메시지를 감지해서 Upstage Solar가 일정/마감 여부를 분석하고, 웹 관리 콘솔에서 `등록 / 수정 / 무시`를 확인한 뒤 Google Calendar에 일정을 등록하는 MVP입니다.

## 0. 전체 구조

```text
Webex DM/Space
  -> Webex Webhook
  -> FastAPI Backend
  -> Upstage Solar 분석
  -> Next.js 관리 콘솔 승인/수정/무시
  -> Google Calendar 등록
  -> Webex Bot 리마인드
```

이 프로젝트는 두 서버를 사용합니다.

- Backend: FastAPI, 기본 포트 `8000`
- Frontend: Next.js 관리 콘솔, 기본 포트 `3000`

Webex 웹훅은 외부 서비스가 내 로컬 서버로 요청을 보내는 구조라서 `localhost`만으로는 실제 DM 자동 감지가 안 됩니다. 실제 Webex 연동 테스트에는 ngrok 같은 공개 HTTPS 주소가 필요합니다.

## 1. 준비물

먼저 계정과 도구를 준비합니다.

- Python 3.11 이상: <https://www.python.org/downloads/>
- Node.js 20 이상: <https://nodejs.org/>
- ngrok: <https://ngrok.com/downloads>
- Webex Developer 계정: <https://developer.webex.com/>
- Google Cloud Console 계정: <https://console.cloud.google.com/>
- Upstage Console 계정: <https://console.upstage.ai/>

## 2. 로컬 서버 먼저 실행

Backend를 설치하고 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

다른 터미널에서 확인합니다.

```bash
curl http://127.0.0.1:8000/health
```

정상 응답:

```json
{"ok":true,"service":"ai-soma-secretary"}
```

웹 관리 콘솔을 실행합니다.

```bash
cd frontend
npm install
npm run dev
```

관리 콘솔 주소:

```text
http://localhost:3000
```

## 3. ngrok으로 공개 HTTPS 주소 만들기

Webex와 Google OAuth 콜백, Webex 웹훅을 받으려면 공개 HTTPS URL이 필요합니다.

Backend 포트 `8000`을 외부에 공개합니다.

```bash
ngrok http 8000
```

예를 들어 ngrok이 이런 주소를 보여주면:

```text
https://abc123.ngrok-free.app
```

이 값을 `.env`에서 `PUBLIC_BASE_URL`로 사용합니다.

```env
PUBLIC_BASE_URL=https://abc123.ngrok-free.app
WEBEX_REDIRECT_URI=https://abc123.ngrok-free.app/oauth/webex/callback
GOOGLE_REDIRECT_URI=https://abc123.ngrok-free.app/oauth/google/callback
```

ngrok 주소가 바뀌면 Webex Integration, Google OAuth Client, `.env` 값을 모두 같은 주소로 다시 맞춰야 합니다.

처음 사용하는 ngrok에서 로그인/authtoken을 요구하면 아래 페이지 안내에 따라 한 번만 등록하면 됩니다.

```text
https://dashboard.ngrok.com/get-started/your-authtoken
```

## 4. Webex Bot 만들기

Bot은 사용자에게 Webex DM 알림과 리마인드를 보내는 역할입니다. 계정 연결과 후보 처리는 웹 관리 콘솔에서 진행합니다.

1. Webex Developer My Apps로 이동합니다.

   ```text
   https://developer.webex.com/my-apps
   ```

2. `Create a New App`을 클릭합니다.

3. `Create a Bot`을 선택합니다.

   공식 안내:

   ```text
   https://developer.webex.com/create/docs/bots
   ```

4. Bot 이름, 아이콘, 설명을 입력합니다.

5. Bot username을 정합니다. 보통 이런 형태입니다.

   ```text
   soma-secretary@webex.bot
   ```

6. 생성 후 `Bot Access Token`을 복사합니다.

7. `.env`에 넣습니다.

   ```env
   WEBEX_BOT_TOKEN=복사한_Bot_Access_Token
   ```

8. Bot username을 기록해 둡니다.

그룹 Space에서 쓰려면 Space의 사람 추가 메뉴에서 Bot username을 사람 초대하듯 추가하면 됩니다.

## 5. Webex Integration 만들기

Integration은 “내 Webex 계정으로 받은 DM/Space 메시지를 읽는 권한”을 받기 위해 필요합니다.

1. Webex Developer My Apps로 이동합니다.

   ```text
   https://developer.webex.com/my-apps
   ```

2. `Create a New App` 클릭

3. `Create an Integration` 선택

4. 기본 정보를 입력합니다.

   - Integration name: `AI Soma Secretary`
   - Icon: 아무 아이콘
   - Description: `Webex messages schedule assistant`

5. Redirect URI에 ngrok 콜백 주소를 정확히 입력합니다.

   ```text
   https://abc123.ngrok-free.app/oauth/webex/callback
   ```

6. Scopes는 아래 4개만 선택합니다.

   ```text
   spark:messages_read
   spark:rooms_read
   spark:people_read
   spark:memberships_read
   ```

   이유:

   - `spark:messages_read`: DM/Space 메시지 읽기와 메시지 웹훅
   - `spark:rooms_read`: room 정보 확인
   - `spark:people_read`: `/people/me`로 사용자 식별
   - `spark:memberships_read`: 사용자가 속한 room/member 확인

   User OAuth로 메시지를 보내지는 않으므로 `spark:messages_write`는 필요 없습니다. 메시지 전송은 Bot Token이 담당합니다.

7. 생성 후 `Client ID`, `Client Secret`을 복사합니다.

8. `.env`에 넣습니다.

   ```env
   WEBEX_CLIENT_ID=복사한_Client_ID
   WEBEX_CLIENT_SECRET=복사한_Client_Secret
   WEBEX_REDIRECT_URI=https://abc123.ngrok-free.app/oauth/webex/callback
   ```

## 6. Google Calendar OAuth 만들기

Google OAuth는 사용자의 Google Calendar에 일정을 등록하기 위해 필요합니다.

1. Google Cloud Console로 이동합니다.

   ```text
   https://console.cloud.google.com/
   ```

2. 새 프로젝트를 만들거나 기존 프로젝트를 선택합니다.

3. Google Calendar API를 사용 설정합니다.

   ```text
   https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
   ```

   `Enable` 또는 `사용 설정`을 누릅니다.

4. OAuth 동의 화면을 설정합니다.

   ```text
   https://console.cloud.google.com/auth/overview
   ```

   기본값:

   - User type: `External`
   - App name: `AI Soma Secretary`
   - User support email: 본인 이메일
   - Developer contact email: 본인 이메일

5. 테스트 사용자에 본인 Google 계정을 추가합니다.

   앱을 Production으로 승인받지 않았다면 테스트 사용자만 로그인할 수 있습니다.

6. OAuth Client를 만듭니다.

   ```text
   https://console.cloud.google.com/auth/clients
   ```

   또는:

   ```text
   https://console.cloud.google.com/apis/credentials
   ```

7. `Create Client` 또는 `Create Credentials -> OAuth client ID` 선택

8. Application type은 `Web application` 선택

9. Authorized redirect URI에 아래 값을 추가합니다.

   ```text
   https://abc123.ngrok-free.app/oauth/google/callback
   ```

   로컬 OAuth만 테스트할 때는 이것도 추가할 수 있습니다.

   ```text
   http://localhost:8000/oauth/google/callback
   ```

10. 생성 후 `Client ID`, `Client Secret`을 복사합니다.

11. `.env`에 넣습니다.

   ```env
   GOOGLE_CLIENT_ID=복사한_Google_Client_ID
   GOOGLE_CLIENT_SECRET=복사한_Google_Client_Secret
   GOOGLE_REDIRECT_URI=https://abc123.ngrok-free.app/oauth/google/callback
   ```

Google Redirect URI는 Google Console에 등록한 값과 `.env` 값이 한 글자도 다르면 안 됩니다.

## 7. Upstage Solar API Key 만들기

Solar API는 Webex 메시지가 일정/마감인지 분석하고 JSON으로 구조화하는 역할입니다.

1. Upstage Console로 이동합니다.

   ```text
   https://console.upstage.ai/
   ```

2. API Keys 페이지로 이동합니다.

   ```text
   https://console.upstage.ai/api-keys?api=chat
   ```

3. API Key를 생성합니다.

4. `.env`에 넣습니다.

   ```env
   UPSTAGE_API_KEY=복사한_Upstage_API_Key
   ```

현재 코드는 OpenAI 호환 방식으로 Solar를 호출합니다.

```text
base_url=https://api.upstage.ai/v1
model=solar-pro3
```

## 8. 최종 `.env` 예시

`abc123.ngrok-free.app` 부분은 본인 ngrok 주소로 바꿉니다.

```env
WEBEX_BOT_TOKEN=...
WEBEX_CLIENT_ID=...
WEBEX_CLIENT_SECRET=...
WEBEX_REDIRECT_URI=https://abc123.ngrok-free.app/oauth/webex/callback

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://abc123.ngrok-free.app/oauth/google/callback

UPSTAGE_API_KEY=...
PUBLIC_BASE_URL=https://abc123.ngrok-free.app

FRONTEND_BASE_URL=http://localhost:3000
DATABASE_PATH=./soma_secretary.db
SESSION_COOKIE_NAME=soma_session
SESSION_DAYS=7
TIMEZONE=Asia/Seoul
CONFIDENCE_THRESHOLD=0.65
PROCESS_OWN_MESSAGES=false
PROCESS_USER_GROUP_MESSAGES=true
```

옵션 설명:

- `CONFIDENCE_THRESHOLD=0.65`: Solar 분석 신뢰도가 이 값보다 낮으면 일정 후보를 만들지 않습니다.
- `PROCESS_OWN_MESSAGES=false`: 내가 직접 보낸 DM은 기본적으로 무시합니다. 테스트 중 내 메시지도 분석하려면 `true`.
- `PROCESS_USER_GROUP_MESSAGES=true`: User OAuth로 내가 볼 수 있는 그룹 Space 메시지도 처리합니다. DM만 먼저 테스트하려면 `false`.

`.env`를 수정했다면 Backend 서버를 껐다가 다시 켜야 합니다.

## 9. 서버 실행

터미널 1: Backend

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

터미널 2: ngrok

```bash
ngrok http 8000
```

터미널 3: Frontend 관리 콘솔

```bash
cd frontend
npm run dev
```

## 10. 웹 콘솔에서 최초 연결

1. Backend, ngrok, Frontend를 모두 실행합니다.

2. 브라우저에서 관리 콘솔에 접속합니다.

   ```text
   http://localhost:3000
   ```

3. `Webex로 로그인`을 눌러 Webex OAuth 권한을 승인합니다.

4. 로그인 후 `/dashboard`로 돌아오면 `/settings`로 이동합니다.

   ```text
   http://localhost:3000/settings
   ```

5. `Google 연결`을 눌러 Google Calendar 권한을 승인합니다.

6. `/settings`에서 Webex / Google 연결 상태와 누락된 환경 변수를 확인합니다.

7. Backend는 시작 시 `PUBLIC_BASE_URL`이 `https://`이고 `WEBEX_BOT_TOKEN`이 있으면 Webex webhook 등록을 자동으로 시도합니다. 수동으로 다시 등록해야 하면 아래 API를 호출합니다.

   ```bash
   curl -X POST http://127.0.0.1:8000/admin/webhooks/register
   ```

## 11. 동작 테스트

웹 콘솔에서 Webex / Google 연결을 마친 뒤, Webex에서 일정이 담긴 메시지를 보냅니다.

```text
이번 주 목요일 오후 3시에 멘토링 가능할까요?
```

정상 흐름:

1. Webex 웹훅이 FastAPI로 들어옵니다.
2. 서버가 메시지를 Webex API로 조회합니다.
3. Solar가 일정 후보로 분석합니다.
4. 웹 관리 콘솔 `/candidates`에 일정 후보가 표시됩니다.
5. 웹 관리 콘솔에서 `등록`, `수정`, `무시` 중 하나를 선택합니다.
6. Google Calendar에 일정이 생성됩니다.
7. 등록 상태와 최근 후보는 `/dashboard`에서 확인합니다.

애매한 메시지 예시:

```text
내일 9시에 회의하자
```

오전/오후가 애매하면 바로 캘린더에 등록하지 않고 `/candidates`에서 `수정 필요` 상태로 보여야 합니다.

### 혼자 셀프테스트하기

팀원이나 테스트용 Webex 계정이 없으면, 웹 콘솔로 먼저 로그인/연결한 뒤 본인이 볼 수 있는 테스트 Space에서 직접 일정 메시지를 보내 확인할 수 있습니다.

1. `.env`에서 본인 메시지도 처리하도록 바꿉니다.

   ```env
   PROCESS_OWN_MESSAGES=true
   ```

2. Backend 서버를 재시작합니다.

3. Webex에서 새 테스트 Space를 만들거나 기존 테스트 Space를 엽니다.

4. 필요하면 Space의 사람 추가 메뉴에서 Bot username을 추가합니다. User OAuth group webhook으로 테스트하는 경우 핵심 조건은 “연결한 Webex 사용자가 해당 Space 메시지를 볼 수 있음”입니다.

5. Backend 시작 시 webhook 자동 등록이 실패했거나 ngrok 주소를 바꿨다면 아래 명령으로 다시 등록합니다.

   ```bash
   curl -X POST http://127.0.0.1:8000/admin/webhooks/register
   ```

6. 테스트 Space에 직접 일정이 담긴 메시지를 보냅니다.

   ```text
   다음 주 월요일 오후 2시에 기획 회의하자
   ```

7. 웹 관리 콘솔에서 후보를 확인합니다.

   ```text
   http://localhost:3000/candidates
   ```

주의: 기본값 `PROCESS_OWN_MESSAGES=false`에서는 내가 직접 보낸 메시지는 무시됩니다. 셀프테스트가 끝나면 다시 `false`로 돌려두는 편이 좋습니다.

## 12. 관리 콘솔 사용

웹 관리 콘솔이 기본 조작 UI입니다. Webex는 메시지 수집 채널이고, 후보 승인/수정/무시는 웹에서 처리합니다.

주소:

```text
http://localhost:3000
```

주요 화면:

- `/dashboard`: 후보 수, 최근 후보
- `/candidates`: 후보 목록, 승인/수정/무시
- `/settings`: Webex / Google 연결 상태, 재연결, 누락 env 확인

로그인은 Webex OAuth를 사용합니다.

```text
http://localhost:3000
```

접속 후 Webex 로그인을 진행하면 Backend의 `/auth/webex/login`으로 이동합니다.

## 13. 자주 나는 문제

### Webex OAuth에서 redirect 오류가 남

- Webex Integration의 Redirect URI와 `.env`의 `WEBEX_REDIRECT_URI`가 완전히 같은지 확인합니다.
- `http`와 `https`, 마지막 `/` 차이도 오류 원인이 됩니다.

### Google OAuth에서 `redirect_uri_mismatch`가 남

- Google OAuth Client의 Authorized redirect URI와 `.env`의 `GOOGLE_REDIRECT_URI`가 완전히 같은지 확인합니다.
- ngrok 주소가 바뀌었으면 Google Console에도 새 주소를 다시 등록해야 합니다.

### Webex DM이 자동 감지되지 않음

- ngrok이 켜져 있는지 확인합니다.
- `/admin/webhooks/register`를 호출했는지 확인합니다.
- Webex 연결 OAuth가 완료됐는지 확인합니다.
- 본인이 직접 보낸 메시지를 테스트 중이라면 `PROCESS_OWN_MESSAGES=true`로 바꿉니다.

### Google Calendar 등록이 안 됨

- Google 연결 OAuth를 완료했는지 확인합니다.
- Google Calendar API를 Enable 했는지 확인합니다.
- 테스트 사용자에 본인 Google 계정이 들어가 있는지 확인합니다.

### Solar 분석이 안 됨

- `UPSTAGE_API_KEY`가 들어갔는지 확인합니다.
- Upstage Console에서 API Key가 활성 상태인지 확인합니다.
- 서버 로그에서 Upstage API 오류 메시지를 확인합니다.

## 14. 로컬 검증 명령

```bash
source .venv/bin/activate
python -m pytest -q
python -m compileall app tests
curl http://127.0.0.1:8000/health
```

Frontend 빌드 확인:

```bash
cd frontend
npm run build
```

## 15. 공식 문서 링크

- Webex Developer: <https://developer.webex.com/>
- Webex My Apps: <https://developer.webex.com/my-apps>
- Webex Bot 생성: <https://developer.webex.com/create/docs/bots>
- Webex Webhooks: <https://developer.webex.com/messaging/docs/api/guides/webhooks>
- ngrok 다운로드: <https://ngrok.com/downloads>
- ngrok authtoken: <https://dashboard.ngrok.com/get-started/your-authtoken>
- Google Cloud Console: <https://console.cloud.google.com/>
- Google Calendar API: <https://console.cloud.google.com/apis/library/calendar-json.googleapis.com>
- Google OAuth Clients: <https://console.cloud.google.com/auth/clients>
- Upstage Console: <https://console.upstage.ai/>
- Upstage API Keys: <https://console.upstage.ai/api-keys?api=chat>
