from flask import jsonify, request

from hmleq_converter import HmleqConversionError, HmleqUnavailable, convert_hancom_to_latex as run_hmleq


def hancom_to_latex(converter=None):
    payload = request.get_json(silent=True)
    script = payload.get("script") if isinstance(payload, dict) else None
    try:
        latex = (converter or run_hmleq)(script)
    except HmleqConversionError as exc:
        return jsonify(error=str(exc)), 422
    except HmleqUnavailable as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(latex=latex)


def convert_hancom_math(converter=None):
    payload = request.get_json(silent=True) or {}
    expression = str(payload.get("expression", "")).strip()
    if not expression:
        return jsonify(error="수식 코드를 입력해 주세요."), 400
    if len(expression) > 5000:
        return jsonify(error="수식 코드는 5,000자 이내로 입력해 주세요."), 400
    try:
        latex = (converter or run_hmleq)(expression)
    except HmleqConversionError as error:
        return jsonify(error=f"한컴 수식을 변환하지 못했습니다: {error}"), 400
    except HmleqUnavailable as error:
        return jsonify(error=f"수식 변환기를 사용할 수 없습니다: {error}"), 503
    return jsonify(latex=latex)
