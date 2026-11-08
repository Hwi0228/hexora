# HWP equation converter benchmark

This branch contains an isolated GitHub Actions benchmark for candidate Hancom HWP equation-script converters.

Candidates:
- `hmleq`: Rust AST parser and LaTeX emitter.
- `unhwp`: Rust HWP equation-to-LaTeX module.
- `easyconvert`: TypeScript parser that emits LaTeX and MathML.
- `krx-rule-markdown`: Python best-effort converter.
- LibreOffice: source inspection only; its converter is coupled to the LibreOffice C++ HWP filter.

The executable candidates are checked against the same basic cases: a simple fraction, grouped fraction, nested square root/fraction, scripts, and a matrix where supported. These are smoke tests, not a complete semantic-equivalence evaluation. The LibreOffice source is not compiled independently by this workflow.

This branch is intentionally separate from `dev`; no production application code or dependency configuration is changed.
