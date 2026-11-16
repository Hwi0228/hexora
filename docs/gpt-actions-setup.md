# HEXORA GPT Actions 설정

이 방식은 MCP 서버를 사용하지 않고 ChatGPT GPT Actions가 HEXORA Flask REST API를 직접 호출합니다.

## OAuth 환경 변수

Render의 HEXORA 웹 서비스에 다음 환경 변수를 설정합니다.

- `HEXORA_ACTIONS_CLIENT_ID`: 무작위 클라이언트 식별자
- `HEXORA_ACTIONS_CLIENT_SECRET`: 충분히 긴 무작위 비밀값
- `HEXORA_ACTIONS_REDIRECT_URIS`: GPT 편집기의 OAuth Callback URL. 여러 URL은 줄바꿈으로 구분

클라이언트 비밀값은 Git, OpenAPI 문서, GPT 지침에 넣지 않습니다. GPT 편집기의 OAuth 설정에 입력하는 값과 Render 환경 변수 값이 일치해야 합니다.

## GPT 편집기

1. 새 GPT를 만들고 Actions에서 새 작업을 추가합니다.
2. `openapi/hexora-actions.yaml` 내용을 붙여넣습니다.
3. Authentication을 OAuth로 설정합니다.
4. Client ID와 Client Secret은 Render 환경 변수에 등록한 값으로 입력합니다.
5. Authorization URL: `https://hexora.kro.kr/actions/oauth/authorize`
6. Token URL: `https://hexora.kro.kr/actions/oauth/token`
7. Scope: `questions:read questions:write`
8. Token exchange method: POST
9. 저장 후 표시되는 OAuth Callback URL을 복사해 Render의 `HEXORA_ACTIONS_REDIRECT_URIS`에 정확히 등록합니다. 환경 변수 변경 후 서비스를 재배포합니다.

## 제공 작업

- `searchQuestions`: 문항 검색
- `getQuestion`: 문항 상세 조회
- `getAchievementStandards`: 성취기준 조회
- `validateQuestion`: 문항 등록 전 검증
- `createQuestion`: 공개 문제 은행에 문항 등록

## 운영 원칙

- 문항 검색과 조회에는 `questions:read` 권한을 사용합니다.
- 문항 검증과 등록에는 `questions:write` 권한이 필요합니다.
- `createQuestion`은 사용자가 문항 등록을 명시적으로 요청했을 때만 실행합니다.
- 문항 등록 시 현재 로그인한 HEXORA 계정이 작성자로 기록됩니다.
- 기존 회원 계정과 문제 DB를 그대로 사용합니다.
- 이 API는 HTTPS Bearer OAuth 토큰을 직접 검증하며 MCP 서버나 MCP 전용 서비스 토큰을 사용하지 않습니다.

## 엔드포인트

- Base URL: `https://hexora.kro.kr/api/v1`
- OAuth authorize: `https://hexora.kro.kr/actions/oauth/authorize`
- OAuth token: `https://hexora.kro.kr/actions/oauth/token`
- OpenAPI: 저장소의 `openapi/hexora-actions.yaml`
