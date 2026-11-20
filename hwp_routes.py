import json
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from pathlib import Path

from flask import abort, g, redirect, render_template, request, url_for

from auth import login_required
from constants import NAV_ITEMS, SUBJECTS, LICENSE_CHOICES, SOURCE_TYPES
from database import get_db
from parse_hwp import parse_questions_from_xml
from parse_rhwp import MAX_DOCUMENT_BYTES, parse_questions_from_rhwp_bytes
from pdf_parser import MAX_PDF_BYTES, parse_questions_from_pdf_bytes
from hwp_import_validation import MAX_IMPORTED_QUESTIONS, MAX_SECTION_XML_SIZE, _get_section_xml, _validated_import
from hwp_engine.adapters import default_registry
from hwp_engine.assembly import assemble_document
from hwp_engine.core import HwpCoreExtractor
from hwp_engine.detection import detect_templates
from hwp_engine.models import QuestionTemplate
from exam_export_routes import export_exam_hwpx, register_exam_export_routes
from rich_text import sanitize_rich_html


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
                                user_uuid, folder_uuid, subject, grade, unit,
                                prompt, choices, answer, explanation, source, year,
                                source_type, license
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            RETURNING id
                            """,
                            (
                                g.user["uuid"], None, metadata["subject"],
                                metadata["grade"], metadata["unit"],
                                imported["question"],
                                json.dumps(imported["choices"], ensure_ascii=False),
                                imported["answer"], imported["explanation"],
                                metadata["source"], metadata["year"],
                                metadata["source_type"], metadata["license"],
                            ),
                        )
                        question_id = cursor.fetchone()["id"]
                        snapshot = {
                            "subject": metadata["subject"],
                            "grade": metadata["grade"],
                            "course": "",
                            "curriculum": "2015 개정 교육과정",
                            "unit": metadata["unit"],
                            "achievement_standard": "",
                            "question_type": "객관식" if imported["choices"] else "단답형",
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
                            "original_question_number": str(imported.get("source_number", imported["number"])),
                            "page": imported.get("source_page"),
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
            error = "파싱할 HWP, HWPX, PDF 또는 section0.xml 파일을 선택해 주세요."
        else:
            try:
                extension = Path(uploaded.filename).suffix.lower()
                file_limit = (
                    MAX_SECTION_XML_SIZE if extension == ".xml"
                    else MAX_PDF_BYTES if extension == ".pdf"
                    else MAX_DOCUMENT_BYTES
                )
                content = uploaded.read(file_limit + 1)
                if len(content) > file_limit:
                    limit_label = "16 MiB" if extension == ".xml" else "12 MiB"
                    raise ValueError(
                        f"문서 크기가 허용 한도({limit_label})를 초과합니다."
                    )

                if extension in {".hwp", ".hwpx"}:
                    filename = Path(uploaded.filename).name
                    document_ir = None
                    try:
                        document_ir = HwpCoreExtractor().extract_bytes(
                            content, filename=filename
                        )
                    except (ValueError, RuntimeError):
                        # Preserve the established parser as a compatibility fallback
                        # when the structural reader cannot open a legacy document.
                        document_ir = None

                    detection = detect_templates(document_ir) if document_ir else None
                    if (
                        detection is not None
                        and detection.question_template != QuestionTemplate.UNKNOWN
                    ):
                        assembled = assemble_document(
                            document_ir, default_registry(), detection=detection
                        )
                        payload = assembled.as_payload()
                        questions = payload["questions"]
                        result_json = json.dumps(
                            payload, ensure_ascii=False, indent=2
                        )
                        validation_errors = [
                            issue.message for issue in assembled.issues
                            if issue.severity == "error"
                        ]
                        if validation_errors:
                            error = (
                                "문항·정답 구조 검증이 필요합니다: "
                                + " / ".join(validation_errors)
                            )
                    else:
                        questions = parse_questions_from_rhwp_bytes(
                            content, filename=filename
                        )
                elif extension == ".pdf":
                    filename = Path(uploaded.filename).name
                    questions = parse_questions_from_pdf_bytes(
                        content, filename=filename
                    )
                elif extension == ".xml":
                    xml_content = _get_section_xml(uploaded.filename, content)
                    questions = parse_questions_from_xml(xml_content)
                else:
                    raise ValueError("HWP, HWPX, PDF 또는 HWPML section0.xml 파일만 업로드할 수 있습니다.")

                # Normalize parser-produced Quill/TeX HTML to the same
                # dollar-delimited storage format used by JSON question import.
                for question in questions or []:
                    if not isinstance(question, dict):
                        continue
                    for field in ("question", "answer", "explanation", "passage", "examples"):
                        value = question.get(field)
                        if isinstance(value, str):
                            question[field] = sanitize_rich_html(value)
                    choices = question.get("choices")
                    if isinstance(choices, list):
                        question["choices"] = [
                            sanitize_rich_html(choice) if isinstance(choice, str) else choice
                            for choice in choices
                        ]

                if result_json is None:
                    payload = {"questions": questions}
                else:
                    payload = json.loads(result_json)
                    if isinstance(payload, dict):
                        payload["questions"] = questions
                result_json = json.dumps(
                    payload, ensure_ascii=False, indent=2
                )
            except (ValueError, RuntimeError, ET.ParseError, DefusedXmlException) as exc:
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
