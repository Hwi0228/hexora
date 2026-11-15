# P1 구현 노트

이 문서는 HEXORA의 안정화·운영·제작 경험 개선 항목을 실제 구현 기준으로 정리합니다. 상세한 변경은 P1 항목을 하나의 통합 PR로 검토하며, PR 병합 전에는 로드맵의 완료 체크를 변경하지 않습니다.

## 요청 제한과 프록시 신뢰

- 로그인, 회원가입, 권리침해 신고 POST 요청에 IP 및 계정 식별자 기반 rate limit을 적용합니다.
- Retry-After와 Cache-Control: no-store를 반환하며, 입력 검증이나 비밀번호 검증보다 먼저 제한을 확인합니다.
- ProxyFix는 설정된 TRUSTED_PROXY_HOPS만큼의 프록시 헤더만 신뢰합니다. Render 기본 프록시 구성은 1을 사용합니다. 프록시를 추가했다면 실제 홉 수를 확인해야 하며, 임의의 X-Forwarded-For 값을 신뢰하면 안 됩니다.

## 관측성 및 헬스 체크

- 요청마다 X-Request-ID를 생성하거나 전달받은 유효 ID를 유지합니다.
- JSON 로그에는 요청 ID, HTTP 메서드, 경로, 응답 상태, 처리 시간과 HWP 파싱 시간을 기록합니다.
- 요청 본문, 쿼리 문자열, 비밀번호 및 DB 연결 문자열은 로그 필드에 포함하지 않습니다.
- GET /health/live는 프로세스 생존을, GET /health/ready는 DB 연결을 확인합니다.

## DB 백엔드와 재현 가능한 빌드

- SQLite와 PostgreSQL을 계속 선택 가능하게 유지합니다. 특정 DB 제공자를 필수화하지 않습니다.
- 공통 CRUD, 외래 키 cascade, rollback 및 검색 동작을 두 백엔드에서 검증합니다.
- .python-version은 Python 3.11을 지정합니다.
- requirements.in은 직접 런타임 의존성, requirements.lock은 런타임 전체 고정 버전, requirements-dev.txt는 Ruff·coverage·pip-tools 도구를 관리합니다.
- requirements.txt는 기존 설치 경로와의 호환을 위해 lock 파일을 포함합니다.
- 의존성 변경은 bash scripts/update-dependencies.sh로 lock을 갱신한 뒤 diff와 CI 결과를 검토합니다.

## HWP 가져오기 보정

- 미리보기에서 원본 문항 번호, 문제, 선택지, 정답, 해설을 직접 수정할 수 있습니다.
- 커서 위치에서 문항을 분리하고 다음 문항과 병합할 수 있습니다.
- 원본 값과 수정 필드 목록을 저장 payload에 포함하고, 수동 보정된 문항은 최초 버전의 import_provenance에 기록합니다.
- 구조 검증 경고가 있으면 확인 체크 후 등록합니다.
- 업로드 처리 단계 로그는 사용자 화면에 표시하지 않습니다. 진단 정보는 요청 ID와 처리 시간 중심의 서버 JSON 로그로 남깁니다.

## HWPX 수식 객체

- 텍스트는 HWPX hp:t로, 수식은 한컴 수식 스크립트를 포함한 네이티브 hp:equation 객체로 기록합니다.
- 현재 LaTeX 변환기는 분수(frac, dfrac, tfrac, cfrac), 근호와 차수, 첨자, 그리스 문자, 기본 연산자, 일부 행렬·정렬 환경 등 명시된 부분집합을 지원합니다.
- 알 수 없는 명령이나 지원하지 않는 환경은 원문 TeX를 수식 객체인 것처럼 저장하지 않고 422 변환 오류로 거부합니다.
- 범용 LaTeX 엔진은 아닙니다. 실제 한컴오피스에서의 수식 크기·줄 배치·행렬 레이아웃은 배포 전 시각 검증이 필요합니다.

## 작성·수정 흐름

- 문제 편집기의 입력 변경은 1.5초 디바운스로 기존 비공개 Draft 경로에 자동 저장합니다.
- 새로고침 후 마지막으로 저장된 초안을 복구합니다. 초안은 공개 문제나 수정 이력에 바로 반영되지 않습니다.
- 수정 이력은 HTML 태그 차이를 제거한 표시 텍스트를 비교하고, 변경된 필드를 del / ins로 표시합니다.
- 복원은 문제 행을 잠근 트랜잭션 안에서 현재 revision을 다시 확인하고 새 revision을 생성해, 동시 수정 중 과거 버전이 최신 내용을 덮어쓰지 않도록 합니다.

## 고급 문항 검색

- 키워드, 교육과정, 교과, 학년, 문항 유형, 출처 유형, 연도, 라이선스, 성취기준 필터를 제공합니다.
- 최신 등록순, 최근 수정순, 검색 관련도순을 지원합니다.
- 성취기준 코드는 Ⅱ 같은 비ASCII 문자를 포함할 수 있으므로 SQLite와 PostgreSQL의 대소문자 검색 차이를 고려해 backend별 LIKE 연산자를 사용합니다.
- 검색 필터 조합 및 정렬은 SQLite와 PostgreSQL 양쪽에서 회귀 테스트합니다.

## CI 검사

GitHub Actions는 다음 검사를 독립 작업으로 실행합니다.

1. Python 3.11에서 lock 기반 설치 및 unittest
2. Ruff 정적 분석
3. SQLite/PostgreSQL 서비스 DB를 사용하는 coverage 테스트

로컬 실행:

    python -m unittest discover -s tests -v
    python -m pip install -r requirements-dev.txt
    ruff check . --select E4,E7,E9,F --ignore E501,F401,F841
    coverage run --rcfile=.coveragerc -m unittest discover -s tests -v
    coverage report --rcfile=.coveragerc -m

스키마 마이그레이션 체계는 추가하지 않습니다. DB 구조 변경이 필요한 작업은 별도 승인 없이 이 범위에 포함하지 않습니다.
