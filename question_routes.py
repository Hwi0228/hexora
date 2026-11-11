"""Compatibility facade for question-related Flask routes.

Route implementations live in focused modules; this module keeps the
historical imports and URL registration entry point stable.
"""

from auth import admin_required, login_required

from question_browse_routes import (
    get_selected_owner, get_question_page_data, main,
    admin_users, question_by_code, delete_question, restore_deleted_question,
)
from curriculum_routes import curriculum_standards
from question_edit_routes import render_question_form, new_question, edit_question
from question_history_routes import question_history, restore_question
from question_folder_routes import new_folder, save_question_note, move_question
import question_conversion_routes as _conversion_routes
from flask import jsonify, request
from hmleq_converter import (
    HmleqConversionError, HmleqUnavailable,
    convert_hancom_to_latex as run_hmleq,
)
from constants import NAV_ITEMS, SUBJECTS, LICENSE_CHOICES, SOURCE_TYPES
from question_constants import (
    QUESTION_CONTENT_FIELDS, QUESTION_FIELD_LABELS, QUESTION_TYPES, DIFFICULTIES,
    COURSE_OPTIONS, SUBJECT_COURSE_OPTIONS, CURRICULUM_STANDARDS,
)
from database import begin_write_transaction, get_db
from question_validation import _collect_question_data, _form_values_from_data
from question_repository import _question_form_values, _question_row
from question_drafts import _delete_question_draft, _load_question_draft, _save_question_draft
from question_revisions import _ensure_initial_question_revision, _insert_question_revision, _question_snapshot
from folder_service import get_folder_data

from question_ids import (
    BASE36_ALPHABET, BASE36_WIDTH, format_question_number, parse_question_number,
)
from rich_text import sanitize_rich_html, _rich_text_has_content, render_rich_html
from parse_hwp import normalize_katex_markup, strip_choice_label


def hancom_to_latex():
    return _conversion_routes.hancom_to_latex(converter=run_hmleq)


def convert_hancom_math():
    return _conversion_routes.convert_hancom_math(converter=run_hmleq)


def register_question_routes(app):
    app.add_url_rule(
        "/api/math/hancom-to-latex",
        endpoint="hancom_to_latex",
        view_func=login_required(hancom_to_latex),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/math/convert-hancom",
        endpoint="convert_hancom_math",
        view_func=login_required(convert_hancom_math),
        methods=["POST"],
    )
    app.add_url_rule(
        "/curriculum/standards",
        endpoint="curriculum_standards",
        view_func=login_required(curriculum_standards),
        methods=["GET"],
    )
    app.add_url_rule(
        "/questions", endpoint="main", view_func=login_required(main), methods=["GET"]
    )
    app.add_url_rule(
        "/questions/code", endpoint="question_by_code",
        view_func=login_required(question_by_code), methods=["GET"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/delete", endpoint="delete_question",
        view_func=login_required(delete_question), methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/undelete", endpoint="restore_deleted_question",
        view_func=login_required(restore_deleted_question), methods=["POST"],
    )
    app.add_url_rule(
        "/admin/users",
        endpoint="admin_users",
        view_func=admin_required(admin_users),
        methods=["GET"],
    )
    app.add_url_rule(
        "/folders/new",
        endpoint="new_folder",
        view_func=login_required(new_folder),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/new",
        endpoint="new_question",
        view_func=login_required(new_question),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/notes",
        endpoint="save_question_note",
        view_func=login_required(save_question_note),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/folder",
        endpoint="move_question",
        view_func=login_required(move_question),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/edit",
        endpoint="edit_question",
        view_func=login_required(edit_question),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/history",
        endpoint="question_history",
        view_func=login_required(question_history),
        methods=["GET"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/restore/<int:revision_number>",
        endpoint="restore_question",
        view_func=login_required(restore_question),
        methods=["POST"],
    )
