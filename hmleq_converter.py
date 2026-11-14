"""Convert Hancom equation scripts with the hmleqx Python package."""

from __future__ import annotations

try:
    import hmleqx
except ImportError:  # Keep the legacy parser available in minimal local environments.
    hmleqx = None

MAX_SCRIPT_LENGTH = 5000

class HmleqUnavailable(RuntimeError):
    """Raised when the hmleqx Python package is not installed."""

class HmleqConversionError(ValueError):
    """Raised when hmleqx cannot parse a Hancom equation script."""

def convert_hancom_to_latex(script: str) -> str:
    if not isinstance(script, str) or not script.strip():
        raise HmleqConversionError("한컴 수식 스크립트를 입력해 주세요.")
    if len(script) > MAX_SCRIPT_LENGTH:
        raise HmleqConversionError(
            f"수식 스크립트는 {MAX_SCRIPT_LENGTH}자 이내로 입력해 주세요."
        )
    if hmleqx is None:
        raise HmleqUnavailable(
            "hmleqx 패키지가 설치되지 않았습니다. requirements.txt를 설치해 주세요."
        )
    try:
        latex = hmleqx.to_latex(script)
    except ValueError as exc:
        raise HmleqConversionError(str(exc) or "한컴 수식 문법을 확인해 주세요.") from exc
    if not isinstance(latex, str) or not latex.strip():
        raise HmleqConversionError("수식 변환 결과가 비어 있습니다.")
    return latex.strip()
