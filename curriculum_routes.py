"""Curriculum achievement-standard lookup endpoint."""

from pathlib import Path

from flask import current_app, jsonify, request

from question_constants import CURRICULUM_STANDARDS
from curriculum_data import (
    DATASET_URL as CURRICULUM_DATASET_URL,
    DATASET_VERSION as CURRICULUM_DATASET_VERSION,
    CurriculumDataError,
    load_2022_standards,
    select_2022_standards,
)


def curriculum_standards():
    curriculum = request.args.get("curriculum", "2015 개정 교육과정")
    course = request.args.get("course", "").strip()
    unit = request.args.get("unit", "").strip()

    if curriculum == "2022 개정 교육과정":
        cache_path = (
            Path(current_app.instance_path)
            / "curriculum"
            / f"standards-{CURRICULUM_DATASET_VERSION}.json"
        )
        try:
            records = load_2022_standards(cache_path)
        except (CurriculumDataError, OSError):
            current_app.logger.exception("2022 curriculum dataset could not be loaded")
            return jsonify({
                "standards": [],
                "courses": [],
                "areas": [],
                "matched": False,
                "error": (
                    "2022 개정 교육과정 데이터를 불러오지 못했습니다. "
                    "잠시 후 다시 시도하거나 성취기준을 직접 입력해 주세요."
                ),
            }), 503

        result = select_2022_standards(
            records,
            subject=request.args.get("subject", "").strip(),
            grade=request.args.get("grade", "").strip(),
            course=course,
            area=request.args.get("area", "").strip(),
        )
        return jsonify({
            **result,
            "units": [],
            "dataset": {
                "version": CURRICULUM_DATASET_VERSION,
                "url": CURRICULUM_DATASET_URL,
            },
        })

    course_data = CURRICULUM_STANDARDS.get(curriculum, {}).get(course, {})
    if unit:
        standards = course_data.get(unit, [])
    else:
        standards = [
            standard
            for unit_standards in course_data.values()
            for standard in unit_standards
        ]
    return jsonify({
        "standards": standards,
        "units": list(course_data.keys()),
        "matched": bool(standards),
    })
