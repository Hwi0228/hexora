"""Run the hmleq Hancom equation-script converter."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


MAX_SCRIPT_LENGTH = 4096
CONVERSION_TIMEOUT_SECONDS = 5


class HmleqUnavailable(RuntimeError):
    """Raised when the hmleq executable is not installed."""


class HmleqConversionError(ValueError):
    """Raised when hmleq cannot parse a Hancom equation script."""


def _executable() -> str | None:
    configured = os.environ.get("HMLEQ_BIN", "").strip()
    if configured:
        return configured

    executable = shutil.which("hmleq")
    if executable:
        return executable

    cargo_executable = "hmleq.exe" if os.name == "nt" else "hmleq"
    cargo_path = Path.home() / ".cargo" / "bin" / cargo_executable
    return str(cargo_path) if cargo_path.is_file() else None


def convert_hancom_to_latex(script: str) -> str:
    if not isinstance(script, str) or not script.strip():
        raise HmleqConversionError("한컴 수식 스크립트를 입력해 주세요.")
    if len(script) > MAX_SCRIPT_LENGTH:
        raise HmleqConversionError(
            f"수식 스크립트는 {MAX_SCRIPT_LENGTH}자 이내로 입력해 주세요."
        )

    executable = _executable()
    if not executable:
        raise HmleqUnavailable("수식 변환기가 설치되지 않았습니다.")

    try:
        result = subprocess.run(
            [executable],
            input=script,
            text=True,
            capture_output=True,
            timeout=CONVERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HmleqConversionError("수식 변환 시간이 초과되었습니다.") from exc
    except OSError as exc:
        raise HmleqUnavailable("수식 변환기를 실행할 수 없습니다.") from exc

    if result.returncode:
        detail = result.stderr.strip()
        raise HmleqConversionError(detail or "한컴 수식 문법을 확인해 주세요.")

    latex = result.stdout.strip()
    if not latex:
        raise HmleqConversionError("수식 변환 결과가 비어 있습니다.")
    return latex
