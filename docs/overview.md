# HEXORA (헥소라) 종합 문서 - 1. 프로젝트 개요

HEXORA는 수학 및 다양한 교과 문제 문항을 수집, 작성, 관리하고 공유하는 **협업형 웹 기반 문제 은행(Question Bank) 시스템**입니다.

---

## 1. 개요 및 비전

HEXORA는 교사, 강사, 출제자, 학습자가 문제를 손쉽게 관리하고 공유할 수 있도록 개발되었습니다. 단일 사용자의 단순 문제 저장을 넘어 다음과 같은 핵심 가치를 제공합니다:

1. **협업형 공개 문제 위키**: 중앙 문제 데이터베이스에 등록된 모든 문항은 서비스 이용 회원이 함께 조회하고 수정할 수 있는 단일 원본(Single Source of Truth)으로 관리됩니다.
2. **버전 관리 및 추적**: 문항의 모든 수정 내역은 전체 스냅샷 기반의 버전 이력으로 보존되며, 버전 간 diff 비교 및 이전 버전 복원을 지원합니다.
3. **HWP/HWPX 가져오기 및 HWPX 시험지 내보내기**: 한글 문서(`.hwp`, `.hwpx`)에서 문항, 정답, 해설, 선택지 및 한컴 수식을 자동으로 파싱하고, 선택한 문항을 HWPX 시험지 파일로 조합하여 내보낼 수 있습니다.
4. **유연한 데이터베이스 어댑터**: 로컬 단일 파일 환경을 위한 SQLite와 cloud-native 운용을 위한 PostgreSQL(Neon)을 동일한 애플리케이션 코드로 지원합니다.

---

## 2. 주요 기능 요약

### 2.1 계정 및 권한 관리
- 이메일 및 비밀번호 기반 회원가입/로그인 (비밀번호 12자 이상, `werkzeug.security` 단방향 해시 저장).
- **최초 가입자 관리자 승격**: 가장 처음 가입한 계정은 자동으로 `admin` 역할을 부여받아 전체 사용자 현황 조회 및 작성자별 문제 필터링 권한을 가집니다.
- **원작성자 보존**: 공동 편집이 진행되더라도 문항의 최초 작성자(`user_uuid`) 정보는 기여 이력으로 영구히 보존됩니다.

### 2.2 공동 문제 은행 및 개인 관리 기능
- **공개 위키 모델**: 등록된 모든 문제는 모든 로그인 사용자에게 공유됩니다.
- **6자리 Base36 문항 식별자**: 각 문제는 내부 `id`와 더불어 6자리 알파벳/숫자 조합 식별자(예: `000001` -> `00000A`)로 가독성 있게 표기됩니다.
- **개인 폴더 관리**: 사용자별로 계정 고유의 폴더 및 하위 폴더(UUID 식별)를 생성하고 문항을 이동시킬 수 있습니다.
- **개인 메모 및 임시 저장**: 다른 회원의 수정에 영향을 주지 않는 비공개 문항 메모 기능과 작성 중인 문항의 자동/수동 임시 저장(Draft) 기능을 제공합니다.
- **성취기준 및 교육과정 매핑**: 과목, 학년, 교육과정(성취기준) 코드를 문항에 분류 매핑할 수 있습니다.

### 2.3 WYSIWYG 수식 편집 및 KaTeX 렌더링
- **Quill 2 WYSIWYG 편집기**: 굵게, 기울임, 밑줄, 목록 서식과 더불어 문제 지문 박스, 보기 박스 구조를 지원합니다.
- **수식 서식 지원**: Inline `$ ... $` 및 Block `$$ ... $$` LaTeX 구문을 지원하며, Quill 편집기 내에서는 단일 수식 Blot 객체로 취급되어 복사/붙여넣기 및 편집이 용이합니다.
- **한컴 수식 변환 API**: 편집기 및 파서에서 한글 한컴 수식 스크립트를 즉시 LaTeX 구문으로 변환해 주는 브라우저/서버 변환기를 내장하고 있습니다.

### 2.4 HWP / HWPX 가져오기 및 내보내기
- **구조화 파싱**: `rhwp-python` 라이브러리를 사용해 HWP/HWPX 문서 내 표(Table) 구조 및 문단형 시험지(`1.`, `1)`, `1번` 등)에서 문항, 선택지, 정답, 해설을 자동 파싱합니다.
- **수식 파싱**: HWP 수식 스크립트를 Rust로 작성된 `hmleq` CLI로 정밀 변환하여 LaTeX 구문으로 추출합니다.
- **HWPX 시험지 내보내기**: 문제 DB 목록에서 문항 카드를 선택하여 제목 및 정답/해설 포함 여부를 지정하면, 표준 HWPX 압축 패키지 구조로 시험지를 자동 생성합니다 (한 번에 최대 100문항).

---

## 3. 기술 스택 (Technology Stack)

| 구분 | 기술 / 라이브러리 | 용도 |
| --- | --- | --- |
| **Backend Framework** | Python 3.11, Flask 3.0.3 | Web HTTP Server, Routing, Session, Template Engine |
| **WSGI Server** | Gunicorn 23.0.0 | Production Application Server (Procfile) |
| **Database** | SQLite3 / PostgreSQL (psycopg 3.2+) | 이중 지원 DB 어댑터 |
| **Document Parser** | `rhwp-python` 0.8.1, `hml-equation-parser` 1.0.12 | HWP/HWPX 문서 구조 분석 및 HWPML 표/수식 추출 |
| **Math Converter** | `hmleq` (Rust CLI) | HWP Equation Script -> LaTeX Translator |
| **Frontend Renderer** | Jinja2, KaTeX 0.16.x | HTML Server-side Rendering & Client-side Math Latex Rendering |
| **Rich Text Editor** | Quill 2.0.3 | WYSIWYG HTML & Inline Formula Editor |
| **CSS System** | Academic Blue (Design Tokens) | Design System (`static/styles/tokens.css`, `layout.css` 등) |
| **CI / CD** | GitHub Actions | Automated Unit Tests & GitHub Releases Automation |
| **Hosting Platform** | Render (Docker/Native Python) | Cloud PaaS (`build.sh`, `hexora.kro.kr` Custom Domain) |

---

## 4. 저장소 빠른 시작 (Quick Start)

### 4.1 필수 요구 사항
- Python 3.11+
- Rust toolchain (`cargo` - `hmleq` 빌드용, `build.sh` 실행 시 자동 처리)

### 4.2 로컬 개발 환경 구축 (Windows PowerShell)

```powershell
# 1. 저장소 클론 및 이동
git clone https://github.com/Hwi0228/aleph_math.git
cd hexora

# 2. 가상환경 생성 및 활성화
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 의존성 패키지 및 hmleq CLI 설치
bash build.sh

# 4. 환경 변수 설정 및 앱 실행 (SQLite 기본값)
$env:DATABASE_TYPE = "sqlite"
$env:FLASK_SECRET_KEY = "local-dev-secret-key"
python app.py
```

웹 브라우저에서 `http://127.0.0.1:5000`에 접속하여 서비스를 사용할 수 있습니다.

### 4.3 단위 테스트 실행

```powershell
python -m unittest discover -s tests -v
```

---

## 5. 문서 구성

HEXORA 프로젝트의 세부 문서는 `docs/` 하위의 다음 문서들로 구체화되어 있습니다:

- [1. 프로젝트 개요 (`docs/overview.md`)](overview.md) — 본 문서
- [2. 시스템 아키텍처 및 DB 스키마 (`docs/architecture-and-database.md`)](architecture-and-database.md) — 어댑터 패턴, 9개 스키마 상세
- [3. 핵심 모듈 및 라우트 (`docs/core-modules-and-routes.md`)](core-modules-and-routes.md) — 라우터, 위키 이력, 보안 및 로직
- [4. HWP 파싱 및 시험지 내보내기 (`docs/hwp-parsing-and-export.md`)](hwp-parsing-and-export.md) — HWP/HWPX 문서 처리 메커니즘
- [5. 프론트엔드 및 수식 시스템 (`docs/frontend-and-math.md`)](frontend-and-math.md) — 디자인 토큰, Quill 수식 blot, KaTeX
- [6. 배포 및 CI/CD 워크플로 (`docs/deployment-and-cicd.md`)](deployment-and-cicd.md) — Render 배포, GitHub Actions, SemVer 규칙
