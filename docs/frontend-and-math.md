# HEXORA (헥소라) 종합 문서 - 5. 프론트엔드 디자인 및 수식 시스템

이 문서는 Academic Blue 디자인 시스템 기반의 UI 레이아웃, Quill 2 WYSIWYG 편집기 구성, KaTeX 렌더러 및 한컴 수식 변환 엔진을 설명합니다.

---

## 1. Academic Blue 디자인 시스템 (`static/styles/`)

HEXORA는 일관된 학술적(Academic) 도메인 경험을 위해 디자인 토큰 기반의 CSS 아키텍처를 채택하고 있습니다.

### 1.1 CSS 토큰 및 레이아웃 구조

```
static/styles/
├── tokens.css              # 디자인 토큰 (색상, 글꼴, 간격, 그림자 변수)
├── base.css                # 글로벌 리셋 및 Typography
├── layout.css              # 2컬럼 라이트바/메인 레이아웃 및 서브헤더
├── components.css          # 버튼, 입력창, 카드, 배지, 모달 등 재사용 공통 컴포넌트
├── math-rendering.css      # KaTeX 수식 블록 및 수식 편집창 전용 스타일
├── shared.css              # 페이지 공통 유틸리티 클래스
└── pages/                  # 화면별 전용 레이아웃 CSS
    ├── question-bank.css   # 문제 DB 메인 목록 및 필터 뷰
    ├── question-editor.css # Quill 편집기 및 수식 입력 모달
    ├── workbooks.css       # 문제집 및 문항 수록 관리
    ├── dashboard.css       # 메인 대시보드 위젯
    ├── history.css         # 버전 비교 diff 뷰
    ├── hwp-import.css      # HWP 파싱 업로드 폼 및 로그
    └── auth.css            # 로그인 / 회원가입 폼
```

### 1.2 핵심 디자인 토큰 (`tokens.css`)

```css
:root {
  --color-primary: #1e3a8a;       /* Academic Navy Blue */
  --color-primary-hover: #1e40af;
  --color-accent: #2563eb;        /* Academic Blue Accent */
  --color-surface: #ffffff;
  --color-background: #f8fafc;
  --color-border: #e2e8f0;
  --color-text-main: #0f172a;
  --color-text-muted: #64748b;
  --radius-md: 8px;
  --shadow-card: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
}
```

---

## 2. Quill 2 WYSIWYG 문항 편집기

문항 작성 및 수정 화면(`/questions/new`, `/questions/<id>/edit`)은 Quill 2.0.3 라이브러리를 기반으로 문항 편집 경험을 제공합니다.

### 2.1 커스텀 수식 Embed Blot (`FormulaBlot`)
- **수식 객체화**: LaTeX 구문(`$...$`)을 WYSIWYG 에디터 내부에서 단순 텍스트가 아닌 독립된 HTML inline element(`span.ql-formula-embed`)로 표현합니다.
- **클릭 편집**: 에디터 내에서 수식 객체를 더블클릭하면 전용 수식 편집 모달이 열려 LaTeX 구문 및 렌더링을 미리보며 수정할 수 있습니다.
- **지문 / 보기 박스 템플릿**:
  - 편집기 툴바의 전용 버튼을 클릭하면 `passage-box` (공통 지문 박스) 및 `options-box` (보기 박스) HTML 구조가 에디터에 삽입됩니다.

---

## 3. KaTeX 수식 렌더링 시스템 (`katex-render.js`)

문제 DB 카드, 문항 상세보기, HWP 파싱 결과 및 버전 이력 화면에서 LaTeX 수식을 브라우저 측에서 고속 렌더링하기 위해 KaTeX (jsDelivr CDN) 모듈을 사용합니다.

### 3.1 렌더링 구분자 (Delimiters)
`katex-render.js`의 `renderMathInElement` 설정은 다음 4가지 구분자를 자동 인식합니다:

- Block Formula: `$$ ... $$` 또는 `\[ ... \]`
- Inline Formula: `$ ... $` 또는 `\( ... \)`

```javascript
document.addEventListener("DOMContentLoaded", function () {
    if (typeof renderMathInElement === "function") {
        renderMathInElement(document.body, {
            delimiters: [
                { left: "$$", right: "$$", display: true },
                { left: "\\[", right: "\\]", display: true },
                { left: "$", right: "$", display: false },
                { left: "\\(", right: "\\)", display: false }
            ],
            throwOnError: false
        });
    }
});
```

---

## 4. 한컴 수식 변환 (`hmleqx` API)

문항 작성 화면의 한컴 수식 입력은 브라우저에서 별도 JavaScript 파서로 변환하지 않습니다. 편집기에서 입력한 스크립트를 `POST /api/math/hancom-to-latex`로 전송하고, 서버가 PyPI 패키지 `hmleqx`의 `to_latex()`를 호출해 LaTeX로 변환합니다.

- 브라우저: 입력 검증, API 요청, 변환 오류 표시, KaTeX 미리보기
- 서버: 입력 길이 검증 및 `hmleqx.to_latex(script)` 실행
- 요청 헤더: 로그인 세션과 CSRF 토큰 포함
- 요청 본문: `{"script": "{a} over {b}"}`
- 응답 본문: `{"latex": "\\frac{a}{b}"}`

이 구조는 브라우저와 HWP 가져오기 경로가 동일한 `hmleqx` 변환 엔진을 사용하게 하며, 별도의 브라우저용 변환 규칙이 서로 달라지는 문제를 방지합니다.
