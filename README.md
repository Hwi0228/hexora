# HEXORA (헥소라)

문제를 등록하고 과목·폴더별로 관리하는 웹 앱입니다.

## 계정

이메일과 비밀번호로 회원가입/로그인합니다. 비밀번호는 12자 이상이어야 하고 단방향 해시로 저장됩니다. 일반 회원가입으로는 관리자 권한이 부여되지 않습니다. 운영자는 `flask --app app create-admin` 명령으로 첫 관리자를 명시적으로 생성합니다. 문제는 모든 로그인 회원에게 공개되는 공동 문제 은행으로 운영하고, 원작성자 정보는 기여 이력으로 보존합니다. 폴더는 사용자별 개인 분류로 유지합니다. 관리자는 **작성자별 문항 현황**에서 원작성자별 등록 문항 수를 확인하고 작성자 기준으로 문제를 필터링할 수 있습니다.

운영 배포에서는 `HEXORA_ENV=production`과 충분히 긴 무작위 `FLASK_SECRET_KEY`를 반드시 설정해야 합니다. Render에서는 `RENDER=true`가 자동 감지되므로 `HEXORA_ENV`를 별도로 지정하지 않아도 키가 필수입니다. 키가 없거나 길이·문자 다양성 검증을 통과하지 못하면 앱 시작이 실패합니다. 개발 환경에서는 키를 `instance/.secret_key`에 자동 생성하고 Git에서 제외합니다. HTTPS 운영에서는 보안 쿠키를 사용합니다. Render 기본 프록시 환경은 `TRUSTED_PROXY_HOPS=1`을 사용하며, 다른 프록시 토폴로지에서는 실제 신뢰 프록시 홉 수를 확인해 명시해야 합니다.

## 최초 관리자 계정 설정

일반 회원가입으로는 관리자 권한이 부여되지 않습니다. 새 DB를 처음 운영할 때는 배포 환경에서 다음 명령을 실행하세요.

```bash
flask --app app create-admin
```

명령이 이메일, 표시 이름, 비밀번호를 대화형으로 요청합니다. 기존 일반 계정의 이메일을 입력하면 해당 계정을 명시적으로 관리자로 승격하고 비밀번호를 재설정합니다. 이미 관리자가 존재하면 중복 부트스트랩은 거부됩니다. 운영 배포 전에는 관리자 계정 생성 절차를 완료하고, 공개 회원가입을 통해 권한을 얻을 수 없음을 확인하세요.

## 문제 DB

Flask 앱을 실행한 다음 **문제 DB 등록**을 눌러 과목, 학년, 단원, 지문, 문제 내용, 보기, 선택지, 답, 출처를 입력할 수 있습니다. 수식은 `$...$`, `\(...\)`, `$$...$$`, `\[...\]` 형식으로 작성하며 KaTeX로 미리 보고 렌더링합니다. KaTeX는 jsDelivr CDN에서 불러옵니다.

로그인 후 대시보드에서 전체 공개 문항 수와 과목·단원별 현황, 최근 등록 문제를 확인할 수 있습니다. 개인 폴더 수는 본인 계정 기준으로 표시합니다.

문제 DB에서 문항 카드를 선택한 뒤 오른쪽 **시험지 만들기**에서 제목을 지정하면 선택 문항을 HWPX 시험지로 다운로드할 수 있습니다. 기본 시험지에는 정답과 해설이 포함되지 않으며, 교사용 문서가 필요하면 **정답·해설 포함**을 선택합니다. 시험지는 현재 문제 DB 목록에 표시된 순서로 구성되며, 한 번에 최대 100문항까지 내보낼 수 있습니다.

등록된 문제는 설정한 데이터베이스에 저장됩니다. 기본값은 SQLite의 `instance/probocr.sqlite3`이며 기존 SQLite 마이그레이션 동작을 그대로 사용합니다. PostgreSQL을 선택하면 동일한 문제 은행·회원·폴더·수정 이력·임시 저장·개인 메모 스키마를 자동으로 준비합니다. DB 종류는 실행 환경 변수 DATABASE_TYPE으로 선택하며, SQLite와 PostgreSQL은 서로 별도의 데이터 저장소입니다. DB 종류를 바꿔도 기존 데이터가 자동 복사되지는 않으므로 실제 데이터를 옮기려면 별도 백업·이관 절차가 필요합니다.

문제 DB 왼쪽의 **＋ 새 폴더**에서 폴더와 하위 폴더를 만들 수 있습니다. 폴더는 UUID로 식별되고 사용자별로 분리됩니다. 문항을 공개한 뒤 문제 카드의 **문제 더보기**에서 본인 소유 폴더로 이동할 수 있습니다. 개인 메모도 같은 메뉴에서 관리하며, 해당 메모는 작성한 사용자에게만 표시됩니다. 폴더를 선택하면 그 아래 하위 폴더의 문제도 함께 조회됩니다.

## 협업형 공개 문제 DB

기존 `questions` 테이블을 그대로 공개 문제의 단일 원본으로 사용합니다. 개인 문제를 별도 위키 테이블에 복제하지 않으며, 새 문제와 기존 문제 모두 모든 로그인 회원이 조회하고 편집할 수 있습니다. 원작성자(`user_uuid`)는 유지되고 개인 폴더 관리 권한은 원작성자에게만 있습니다.

문제 카드의 **편집**에서 누구나 문항을 수정할 수 있습니다. 수정 요약, 편집자, 저장 시각과 전체 문항 스냅샷은 버전 이력으로 기록하며, 버전 비교와 이전 버전 복원을 지원합니다. 다른 사용자가 먼저 수정한 문서를 오래된 화면에서 덮어쓰지 않도록 기준 버전 번호를 검사합니다.

기존 문항 행은 이동하거나 복제하지 않습니다. 앱 시작 시 `question_revisions` 테이블을 `CREATE TABLE IF NOT EXISTS`로 추가하고, 이력이 없는 기존 문항은 이력 페이지를 처음 열거나 수정할 때 원본 버전을 자동 기록합니다. 따라서 기존 `questions` 테이블을 다시 만들거나 기존 문제 데이터를 마이그레이션할 필요가 없습니다.

문항을 공개 문제 은행에 등록하거나 수정할 때는 원본 자료를 공유·수정할 권리가 있는지 확인해야 합니다. 특히 변경금지(ND) 조건이 붙은 자료는 문항을 분리·각색해 공동 편집용으로 게시할 수 있다고 가정하지 않습니다.

## HWP 문항 파싱

로그인한 뒤 사이드바의 **HWP 파싱**에서 `.hwp` 또는 `.hwpx`를 업로드하면 `rhwp-python` Reader와 `hwp_engine`의 Detector·Adapter·Assembler·Validator를 거쳐 문항을 추출합니다. `1.`, `1)`, `1번`, `Q1.` 형식의 문단형 문항과 표 기반 문항을 지원합니다. 미리보기에서 원본 문항 번호, 문제, 선택지, 정답, 해설을 직접 보정하고 문항 경계를 분리하거나 병합할 수 있습니다. 원본 값과 수정 필드는 최초 버전의 가져오기 출처 정보로 보존하며, 구조 검증 경고가 있으면 확인 동의 후 등록합니다. 업로드 파일은 서버에 보관하지 않습니다.

한컴 수식 스크립트는 PyPI `hmleqx`의 Python API `to_latex()`로 LaTeX 변환합니다. 문제 편집기의 한컴 입력 모드도 동일한 서버 변환 API를 사용합니다. 그림 블록은 위치 표시자로 남기며, 실제 그림 파일을 문제 DB에 저장하는 기능은 포함하지 않습니다. 사용자 화면에는 추출 결과와 필요한 오류만 표시하고, 진단 정보는 요청 ID·처리 시간과 함께 서버의 구조화 JSON 로그에 기록합니다.

에듀넷 등 외부 자료는 내려받을 수 있다는 사실만으로 재배포 권한이 생기지 않습니다. 특히 출처표시·비영리·변경금지 조건이 있는 자료는 추출 결과를 외부에 공개하기 전에 원본 제공자의 이용 조건과 별도 허락 필요 여부를 확인해야 합니다.

## 화면 디자인

전체 화면은 Academic Blue 기반의 Academic Knowledge Workspace 디자인을 공유합니다. `static/styles/tokens.css`, `static/styles/base.css`, `static/styles/layout.css`, `static/styles/components.css`가 디자인 토큰과 공통 요소를 담당하며, `static/styles/pages/` 아래 파일은 화면별 레이아웃을 정의합니다. 공통 사이드바와 페이지 헤더는 `static/templates/partials/`의 Jinja partial로 재사용합니다.

## 테스트

전체 자동 테스트는 다음 명령으로 실행합니다.

```powershell
python -m unittest discover -s tests -v
python -m pip install -r requirements-dev.txt
ruff check . --select E4,E7,E9,F --ignore E501,F401,F841
coverage run --rcfile=.coveragerc -m unittest discover -s tests -v
coverage report --rcfile=.coveragerc -m
```

테스트는 SQLite 회귀 테스트와 PostgreSQL 연결 어댑터 테스트를 포함합니다. `HEXORA_TEST_POSTGRES_URL`이 설정되면 동일한 CRUD·외래 키·트랜잭션 시나리오를 실제 PostgreSQL에서도 실행합니다. GitHub Actions는 격리된 PostgreSQL 서비스를 제공하며, unittest·Ruff 정적 분석·coverage 보고를 별도 작업으로 수행합니다.

### Windows 로컬 실행

PR 브랜치를 내려받은 뒤 Python 3.11 가상환경에서 의존성을 설치합니다.

```powershell
# GitHub CLI가 설치되어 있고 인증된 경우
git switch dev
git pull --ff-only origin dev

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
```

개발용 세션 키를 별도로 지정하려면 다음 명령으로 무작위 키를 생성할 수 있습니다. 운영 환경에서는 생성한 값을 Render의 `FLASK_SECRET_KEY` 환경 변수에 등록하고, 저장소나 로그에 남기지 마세요.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

PowerShell에서 가상환경 활성화가 차단되면 현재 터미널에 한해 다음을 실행한 뒤 다시 활성화합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

기본 SQLite 설정으로 테스트와 웹 앱을 실행합니다.

```powershell
$env:DATABASE_TYPE = "sqlite"
$env:DATABASE_PATH = "instance/probocr.sqlite3"
$env:FLASK_SECRET_KEY = "local-development-only-change-me"

python -m unittest discover -s tests -v
python app.py
```

브라우저에서 `http://127.0.0.1:5000`을 열고 회원가입 후 문제 등록, 편집, 폴더, 임시 저장, HWP 가져오기를 확인합니다. SQLite DB 파일은 `instance/probocr.sqlite3`에 생성됩니다.

### Neon PostgreSQL로 로컬 실행

운영 데이터와 분리해서 확인하려면 Neon 콘솔에서 `production` 브랜치의 자식 브랜치(예: `local-test`)를 만든 뒤 그 브랜치의 **pooled connection string**을 복사합니다. 아래 환경 변수는 현재 PowerShell 창에만 적용됩니다.

```powershell
$env:DATABASE_TYPE = "postgresql"
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
$env:FLASK_SECRET_KEY = "local-development-only-change-me"

python -m unittest discover -s tests -v
python app.py
```

PostgreSQL 백엔드를 선택하면 첫 요청 때 HEXORA 테이블과 인덱스가 생성됩니다. 별도 테스트 브랜치를 사용하면 실제 `production` 데이터에 영향을 주지 않고 회원가입·문제 등록·수정 이력을 확인할 수 있습니다. 테스트가 끝나고 SQLite로 돌아갈 때는 새 PowerShell 창을 열거나 다음처럼 환경 변수를 바꿉니다.

```powershell
$env:DATABASE_TYPE = "sqlite"
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
python app.py
```

`.env.example`은 설정 예시 파일이며 앱이 자동으로 읽지는 않습니다. 접속 문자열을 코드나 Git에 저장하지 말고, 로컬 환경 변수 또는 배포 플랫폼의 비밀 환경 변수로 설정하세요.

## 의존성 및 실행

```powershell
python -m pip install -r requirements.lock
python app.py
```

Flask 진입점은 `app.py`이며, DB, 인증, 문제/폴더, HWP 파싱은 각각 `database.py`, `auth.py`, `question_routes.py`, `hwp_routes.py`에 있습니다.

> 본 제품은 한글과컴퓨터의글 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.


## 데이터베이스 설정

데이터베이스 종류는 앱 화면이 아니라 배포 환경 변수로 설정합니다. 별도 설정이 없으면 기존 SQLite가 기본값입니다.

### SQLite (기본값)

```env
DATABASE_TYPE=sqlite
DATABASE_PATH=instance/probocr.sqlite3
```

DATABASE_PATH는 선택 항목이며 생략하면 instance/probocr.sqlite3를 사용합니다. 기존 SQLite 파일과 자동 마이그레이션 코드는 그대로 유지됩니다.

### PostgreSQL / Neon

```env
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Neon에서는 웹 앱의 일반 쿼리용 pooled connection string을 DATABASE_URL에 설정합니다. 연결 정보는 Git에 올리지 말고 Render의 Environment Variables에 비밀값으로 등록하세요. PostgreSQL 선택 시 최초 요청에서 HEXORA 테이블과 인덱스를 자동 생성합니다.

Render 배포 명령은 Build Command: `bash build.sh`, Start Command: `gunicorn app:app`을 사용합니다. 빌드 스크립트는 Python 의존성과 Rust `hmleq` CLI를 배포 아티팩트의 `.render-tools`에 설치합니다. FLASK_SECRET_KEY도 Render 환경 변수에 고정해 두어야 합니다.

### 변경 이력 페이지

로그인 후 사이드바의 **변경 이력** 또는 `/changelog`에서 버전별 변경 사항을 확인할 수 있습니다. 페이지는 GitHub 저장소의 `CHANGELOG.md`를 기준으로 표시하며, GitHub 원문으로 이동하는 링크도 제공합니다. 기본 조회 브랜치는 `master`이고, Render 환경 변수 `CHANGELOG_GITHUB_REF`로 조회할 브랜치를 지정할 수 있습니다. GitHub에 현재 실행 버전의 변경 이력이 아직 반영되지 않았거나 GitHub에 연결할 수 없으면 배포된 코드에 포함된 `CHANGELOG.md`를 대신 표시합니다.

### 공개 서비스 주소

HEXORA 공개 서비스는 다음 주소에서 이용할 수 있습니다.

- 서비스 주소: https://hexora.kro.kr
- 문제 DB: https://hexora.kro.kr/questions

Render 서비스의 Custom Domains에 `hexora.kro.kr`을 등록하고 DNS를 연결합니다. DNS의 루트 도메인 A 레코드는 Render에서 안내하는 값(현재 설정: `216.24.57.1`)을 가리키도록 구성합니다. IPv6 AAAA 레코드는 등록하지 않습니다. DNS 전파와 도메인 검증이 완료되면 Render가 HTTPS 인증서를 자동으로 발급·갱신합니다. 도메인 설정을 변경할 때는 Render 대시보드에 표시되는 현재 DNS 안내를 우선 확인하세요.

**주의:** SQLite와 PostgreSQL은 같은 데이터를 공유하지 않습니다. DATABASE_TYPE을 바꾸면 앱이 다른 저장소를 사용하며 기존 DB 데이터는 자동 이관되지 않습니다.

## 버전 관리

현재 버전은 `VERSION` 파일을 단일 기준으로 사용합니다. 기존 개발 이력은 기준 버전 `0.0.0`으로 간주하고, 이 버전부터 Semantic Versioning을 적용합니다. 기능 단위 변경은 버전별 PR 하나로 관리하며, 버전 변경 PR에는 `VERSION`과 `CHANGELOG.md`를 함께 갱신합니다. 기능 추가는 MINOR, 하위 호환 수정은 PATCH, 호환성이 깨지는 변경은 MAJOR 버전을 올립니다.

PR을 검토한 뒤 `master`에 병합하면 GitHub Actions가 `VERSION`의 변경 여부를 확인하고, 해당 버전의 `CHANGELOG.md` 항목을 릴리즈 노트로 사용해 `vX.Y.Z` 태그와 GitHub Release를 자동 생성합니다. PR 승인만으로는 릴리즈하지 않으며, 병합이 완료된 뒤에만 실행됩니다. 별도 PAT 없이 워크플로의 `GITHUB_TOKEN`을 사용합니다.

앱 공통 사이드바 하단의 버전 표시는 실행 시 `VERSION` 파일에서 읽습니다. 따라서 `master` 병합 후 호스팅 서비스가 새 코드를 배포하면 사이트에도 동일한 버전이 표시됩니다.
