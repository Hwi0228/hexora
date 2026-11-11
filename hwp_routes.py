import json
import xml.etree.ElementTree as ET
from pathlib import Path

from flask import abort, g, redirect, render_template, request, url_for

from auth import login_required
from constants import NAV_ITEMS, SUBJECTS, LICENSE_CHOICES, SOURCE_TYPES
from database import get_db
from parse_hwp import parse_questions_from_xml
from parse_rhwp import MAX_DOCUMENT_BYTES, parse_questions_from_rhwp_bytes
from hwp_import_validation import MAX_IMPORTED_QUESTIONS, MAX_SECTION_XML_SIZE, _get_section_xml, _validated_import
from exam_export_routes import export_exam_hwpx, register_exam_export_routes


def _render_page(questions=None, result_json=None, error=None, form_data=None):
    folders = get_db().execute(
        "SELECT uuid, name FROM folders WHERE user_uuid = ? ORDER BY LOWER(name), uuid",
        (g.user["uuid"],),
    ).fetchall()
    return render_template(
        "hwp_parser.html",
        nav_items=NAV_ITEMS,
        subjects=SUBJECTS,
        folders=folders,
        license_choices=LICENSE_CHOICES,
        source_types=SOURCE_TYPES,
        questions=questions,
        result_json=result_json,
        error=error,
        form_data=form_data or {},
    )


def hwp_parser_page():
    questions = None
    result_json = None
    error = None

    if request.method == "POST":
        if request.form.get("action") == "save":
            result_json = request.form.get("questions_json", "")
            questions, selection, errors, error = _validated_import(request.form)
            if not error and errors:
                error = " ".join(errors)
            elif not error:
                metadata, selected_indices = selection
                connection = get_db()
                with connection:
                    for index in selected_indices:
                        imported = questions[index]
                        cursor = connection.execute(
                            """
                            INSERT INTO questions (
                                user_uuid, folder_uuid, subject, grade, unit, title,
                                prompt, choices, answer, explanation, source, year,
                                source_type, license
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            RETURNING id
                            """,
                            (
                                g.user["uuid"], None, metadata["subject"],
                                metadata["grade"], metadata["unit"], "",
                                imported["question"],
                                json.dumps(imported["choices"], ensure_ascii=False),
                                imported["answer"], imported["explanation"],
                                metadata["source"], metadata["year"],
                                metadata["source_type"], metadata["license"],
                            ),
                        )
                        question_id = cursor.fetchone()["id"]
                        snapshot = {
                            "title": "",
                            "subject": metadata["subject"],
                            "grade": metadata["grade"],
                            "course": "",
                            "curriculum": "2015 개정 교육과정",
                            "unit": metadata["unit"],
                            "achievement_standard": "",
                            "difficulty": "중",
                            "question_type": "객관식" if imported["choices"] else "단답형",
                            "points": 4,
                            "passage": "",
                            "prompt": imported["question"],
                            "examples": "",
                            "choices": imported["choices"],
                            "answer": imported["answer"],
                            "explanation": imported["explanation"],
                            "source_type": metadata["source_type"],
                            "source": metadata["source"],
                            "year": metadata["year"],
                            "exam": "",
                            "original_question_number": str(imported["number"]),
                            "page": None,
                            "source_url": "",
                            "license": metadata["license"],
                        }
                        connection.execute(
                            """
                            INSERT INTO question_revisions (
                                question_id, revision_number, editor_uuid,
                                summary, snapshot_json
                            )
                            VALUES (?, 1, ?, ?, ?)
                            """,
                            (
                                question_id, g.user["uuid"], "HWP 문서에서 가져옴",
                                json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                            ),
                        )
                return redirect(
                    url_for(
                        "main",
                        added=1,
                        subject=metadata["subject"],
                        folder=metadata["folder_uuid"],
                    )
                )
            form_data = request.form
            return _render_page(
                questions=questions,
                result_json=result_json,
                error=error,
                form_data=form_data,
            )

        uploaded = request.files.get("document")
        if uploaded is None or not uploaded.filename:
            error = "파싱할 HWP, HWPX 또는 section0.xml 파일을 선택해 주세요."
        else:
            try:
                content = uploaded.read(MAX_DOCUMENT_BYTES + 1)
                if len(content) > MAX_DOCUMENT_BYTES:
                    raise ValueError("문서 크기가 허용 한도(12MB)를 초과합니다.")

                extension = Path(uploaded.filename).suffix.lower()
                if extension in {".hwp", ".hwpx"}:
                    questions = parse_questions_from_rhwp_bytes(
                        content,
                        filename=Path(uploaded.filename).name,
                    )
                elif extension == ".xml":
                    xml_content = _get_section_xml(uploaded.filename, content)
                    questions = parse_questions_from_xml(xml_content)
                else:
                    raise ValueError("HWP, HWPX 또는 HWPML section0.xml 파일만 업로드할 수 있습니다.")

                result_json = json.dumps(
                    {"questions": questions},
                    ensure_ascii=False,
                    indent=2,
                )
            except (ValueError, RuntimeError, ET.ParseError) as exc:
                error = str(exc)

    return _render_page(questions=questions, result_json=result_json, error=error)



def register_hwp_routes(app):
    app.add_url_rule(
        "/hwp",
        endpoint="hwp_parser_page",
        view_func=login_required(hwp_parser_page),
        methods=["GET", "POST"],
    )
    register_exam_export_routes(app)
