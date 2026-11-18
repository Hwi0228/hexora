"""Compatibility facade for question-related Flask routes.

Route implementations live in focused modules; this module keeps the
historical imports and URL registration entry point stable.
"""

from auth import admin_required, login_required
from question_validation import _collect_question_data
from question_revisions import _insert_question_revision, _question_snapshot
from rich_text import sanitize_rich_html

from question_browse_routes import (
    get_selected_owner, get_question_page_data, main,
    admin_users, question_by_code, delete_question, restore_deleted_question,
)
from curriculum_routes import curriculum_standards
from question_edit_routes import render_question_form, new_question, edit_question
from question_history_routes import question_history, restore_question
from question_folder_routes import new_folder, save_question_note, move_question
import question_conversion_routes as _conversion_routes
from flask import Response, abort, g, jsonify, redirect, render_template_string, request, url_for
from werkzeug.datastructures import MultiDict
import html
import json
import re
import unicodedata
import uuid
from functools import wraps
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
        view_func=_acl_required("questions.view")(curriculum_standards),
        methods=["GET"],
    )
    app.add_url_rule(
        "/questions", endpoint="main", view_func=_acl_required("questions.view")(main), methods=["GET"]
    )
    app.add_url_rule(
        "/questions/code", endpoint="question_by_code",
        view_func=_acl_required("questions.view")(question_by_code), methods=["GET"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/delete", endpoint="delete_question",
        view_func=_question_acl_required("questions.delete.own", "questions.delete.any")(delete_question), methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/undelete", endpoint="restore_deleted_question",
        view_func=_question_acl_required("questions.restore.own", "questions.restore.any")(restore_deleted_question), methods=["POST"],
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
        view_func=_acl_required("questions.create")(new_question),
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
        view_func=_question_acl_required("questions.edit.own", "questions.edit.any")(edit_question),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/history",
        endpoint="question_history",
        view_func=_acl_required("questions.view")(question_history),
        methods=["GET"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/restore/<int:revision_number>",
        endpoint="restore_question",
        view_func=_question_acl_required("questions.edit.own", "questions.edit.any")(restore_question),
        methods=["POST"],
    )
    _register_bulk_and_acl_routes(app)


# Permission codes are deliberately granular. Existing admin/user roles remain
# valid; per-user overrides and role policies extend them without changing auth.
ACL_PERMISSIONS = (
    ("questions.view", "문항 조회", "문항"),
    ("questions.create", "문항 작성", "문항"),
    ("questions.edit.own", "본인 문항 수정", "문항"),
    ("questions.edit.any", "전체 문항 수정", "문항"),
    ("questions.delete.own", "본인 문항 삭제", "문항"),
    ("questions.delete.any", "전체 문항 삭제", "문항"),
    ("questions.restore.own", "본인 문항 복구", "문항"),
    ("questions.restore.any", "전체 문항 복구", "문항"),
    ("questions.bulk_import", "JSON 일괄 등록", "문항"),
    ("questions.bulk_import_partial", "오류 문항 제외 등록", "문항"),
    ("questions.bulk_export", "JSON 일괄 내보내기", "문항"),
    ("hwp.import", "HWP 문항 가져오기", "문항"),
    ("workbooks.manage", "문제집 관리", "문제집"),
    ("users.view", "사용자 조회", "사용자"),
    ("users.manage", "사용자 관리", "사용자"),
    ("permissions.manage", "ACL 권한 관리", "보안"),
    ("database.backup", "DB 백업", "시스템"),
    ("database.restore", "DB 복구", "시스템"),
    ("database.reset", "DB 초기화", "시스템"),
    ("mcp.questions.read", "MCP 문항 조회", "연동"),
    ("mcp.questions.write", "MCP 문항 작성", "연동"),
)
ACL_DEFAULT_USER_PERMISSIONS = (
    "questions.view", "questions.create", "questions.edit.own",
    "questions.delete.own", "questions.restore.own",
)
ACL_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS acl_permissions (
        code TEXT PRIMARY KEY, label TEXT NOT NULL, category TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS acl_role_permissions (
        role TEXT NOT NULL, permission_code TEXT NOT NULL,
        effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(role, permission_code)
    )""",
    """CREATE TABLE IF NOT EXISTS acl_user_permissions (
        user_uuid TEXT NOT NULL REFERENCES users(uuid) ON DELETE CASCADE,
        permission_code TEXT NOT NULL,
        effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
        granted_by TEXT REFERENCES users(uuid) ON DELETE SET NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_uuid, permission_code)
    )""",
    """CREATE TABLE IF NOT EXISTS acl_audit_log (
        id TEXT PRIMARY KEY, actor_uuid TEXT REFERENCES users(uuid) ON DELETE SET NULL,
        target_user_uuid TEXT REFERENCES users(uuid) ON DELETE SET NULL,
        target_role TEXT, permission_code TEXT NOT NULL, action TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE TABLE IF NOT EXISTS acl_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
)

def _ensure_acl_schema(connection):
    for statement in ACL_SCHEMA_STATEMENTS:
        connection.execute(statement)
    for code, label, category in ACL_PERMISSIONS:
        connection.execute(
            "INSERT INTO acl_permissions(code,label,category) VALUES (?,?,?) "
            "ON CONFLICT(code) DO NOTHING",
            (code, label, category),
        )
    seeded = connection.execute(
        "SELECT value FROM acl_meta WHERE key = ?", ("default_policies_seeded",)
    ).fetchone()
    if seeded is None:
        for code in ACL_DEFAULT_USER_PERMISSIONS:
            connection.execute(
                "INSERT INTO acl_role_permissions(role,permission_code,effect) "
                "VALUES ('user',?,'allow') ON CONFLICT(role,permission_code) DO NOTHING",
                (code,),
            )
        connection.execute(
            "INSERT INTO acl_meta(key,value) VALUES (?,?)",
            ("default_policies_seeded", "1"),
        )
    connection.commit()

def _has_acl_permission(user, permission_code):
    if user is None:
        return False
    if user["role"] == "admin":
        return True
    connection = get_db()
    _ensure_acl_schema(connection)
    override = connection.execute(
        "SELECT effect FROM acl_user_permissions "
        "WHERE user_uuid = ? AND permission_code = ?",
        (user["uuid"], permission_code),
    ).fetchone()
    if override is not None:
        return override["effect"] == "allow"
    role_policy = connection.execute(
        "SELECT effect FROM acl_role_permissions WHERE role = ? AND permission_code = ?",
        (user["role"], permission_code),
    ).fetchone()
    return role_policy is not None and role_policy["effect"] == "allow"

def _require_acl(permission_code):
    if not _has_acl_permission(g.get("user"), permission_code):
        abort(403, description="이 기능을 사용할 권한이 없습니다.")


def _acl_required(permission_code):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.get("user") is None:
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            _require_acl(permission_code)
            return view(*args, **kwargs)
        return wrapped
    return decorate

def _question_acl_required(own_permission, any_permission):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.get("user") is None:
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            question_id = kwargs.get("question_id")
            question = get_db().execute(
                "SELECT user_uuid FROM questions WHERE id = ?", (question_id,)
            ).fetchone()
            if question is None:
                abort(404)
            is_owner = question["user_uuid"] == g.user["uuid"]
            if not (
                (is_owner and _has_acl_permission(g.user, own_permission))
                or _has_acl_permission(g.user, any_permission)
            ):
                abort(403, description="이 문항을 수정할 권한이 없습니다.")
            return view(*args, **kwargs)
        return wrapped
    return decorate

def _normalize_duplicate_text(value):
    text = html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

def _check_math_delimiters(value):
    tokens = re.findall(r"(?<!\\)\$\$|(?<!\\)\$|\\\(|\\\)|\\\[|\\\]", str(value or ""))
    stack = []
    pairs = {"\\)": "\\(", "\\]": "\\["}
    for token in tokens:
        if token in ("$", "$$"):
            if stack and stack[-1] == token:
                stack.pop()
            else:
                stack.append(token)
        elif token in ("\\(", "\\["):
            stack.append(token)
        elif token in pairs:
            if not stack or stack[-1] != pairs[token]:
                return "수식 구분자 짝이 맞지 않습니다."
            stack.pop()
    return "수식 구분자가 닫히지 않았습니다." if stack else None

def _question_payload_to_data(payload):
    from question_constants import QUESTION_CONTENT_FIELDS
    if not isinstance(payload, dict):
        return None, ["문항은 JSON 객체여야 합니다."]
    allowed = set(QUESTION_CONTENT_FIELDS) | {"base_question_number"}
    unknown = sorted(set(payload) - allowed)
    errors = [f"지원하지 않는 필드: {', '.join(unknown)}"] if unknown else []
    values = {}
    for key, value in payload.items():
        if key == "choices":
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                errors.append("choices는 문자열 배열이어야 합니다.")
                value = []
            else:
                value = "\n".join(value)
        elif value is None:
            value = ""
        elif not isinstance(value, (str, int, float)):
            errors.append(f"{key} 필드의 데이터 형식이 올바르지 않습니다.")
            value = ""
        values[key] = str(value)
    values.setdefault("curriculum", "2015 개정 교육과정")
    values.setdefault("difficulty", "중")
    values.setdefault("question_type", "단답형")
    values.setdefault("points", "4")
    values.setdefault("source_type", "기타")
    values.setdefault("source", "")
    values.setdefault("license", "")
    values.setdefault("grade", "")
    values.setdefault("unit", "")
    values.setdefault("subject", "")
    values.setdefault("prompt", "")
    values.setdefault("answer", "")
    form = MultiDict(values)
    data, validation_errors = _collect_question_data(form)
    data["folder_uuid"] = None
    data["passage"] = sanitize_rich_html(str(payload.get("passage") or ""))
    data["examples"] = sanitize_rich_html(str(payload.get("examples") or ""))
    for field in ("passage", "prompt", "examples", "answer", "explanation"):
        math_error = _check_math_delimiters(data.get(field, ""))
        if math_error:
            validation_errors.append(f"{field}: {math_error}")
    errors.extend(validation_errors)
    return data, errors

def _validate_bulk_document(document):
    if not isinstance(document, dict) or document.get("version") != "1.0":
        return [], ["JSON version은 '1.0'이어야 합니다."]
    questions = document.get("questions")
    if not isinstance(questions, list) or not questions:
        return [], ["questions는 비어 있지 않은 배열이어야 합니다."]
    if len(questions) > 500:
        return [], ["한 번에 최대 500개 문항까지 등록할 수 있습니다."]
    prepared, errors = [], []
    existing_rows = get_db().execute(
        "SELECT subject, prompt FROM questions WHERE deleted_at IS NULL"
    ).fetchall()
    existing = {
        (row["subject"], _normalize_duplicate_text(row["prompt"]))
        for row in existing_rows
    }
    incoming = set()
    for index, payload in enumerate(questions, start=1):
        data, item_errors = _question_payload_to_data(payload)
        if data is not None:
            key = (data["subject"], _normalize_duplicate_text(data["prompt"]))
            duplicate = key in existing or key in incoming
            incoming.add(key)
            prepared.append({"index": index, "data": data, "errors": item_errors,
                             "duplicate": duplicate})
        else:
            prepared.append({"index": index, "data": None, "errors": item_errors,
                             "duplicate": False})
        errors.extend([f"{index}번 문항: {message}" for message in item_errors])
    return prepared, errors

_BULK_TEMPLATE = r"""
<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JSON 일괄 등록 | HEXORA</title>
<link rel="stylesheet" href="{{ url_for('static', filename='styles/shared.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='styles/tokens.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='styles/base.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='styles/layout.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='styles/components.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='styles/math-rendering.css') }}">
</head><body><div class="app app-standard">{{ render_sidebar() }}<main>
<header class="page-header"><p>QUESTION BANK / DATA TOOLS</p><h1>JSON 일괄 등록</h1>
<p>HEXORA 문항 스키마 v1.0 · 최대 500문항</p><details><summary>JSON 형식 예시</summary><pre>{
  "version": "1.0",
  "questions": [{
    "subject": "수학", "grade": "고2", "course": "수학Ⅱ",
    "curriculum": "2015 개정 교육과정", "unit": "적분",
    "prompt": "다음 적분을 계산하시오. $\\int x\\,dx$",
    "answer": "$\\frac{x^2}{2}+C$", "explanation": "",
    "choices": [], "source_type": "직접 제작", "license": "ORIGINAL"
  }]
}</pre></details></header>
{% if errors %}<section class="notice warning"><strong>검증 결과</strong><ul>{% for e in errors %}<li>{{ e }}</li>{% endfor %}</ul></section>{% endif %}
{% if imported is not none %}<section class="notice success">등록 완료: {{ imported }}개 문항</section>{% endif %}
{% if prepared is none %}
<form method="post" enctype="multipart/form-data" class="card" style="padding:24px">
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<label for="file">questions.json</label><input id="file" name="file" type="file" accept=".json,application/json" required>
<p>문항을 검증하고 미리보기를 확인한 뒤 등록할 수 있습니다.</p><button type="submit">검증 및 미리보기</button>
</form>
{% else %}
<section class="card" style="padding:20px"><h2>등록 미리보기</h2>
<p>전체 {{ prepared|length }}개 · 정상 {{ valid_count }}개 · 오류 {{ invalid_count }}개 · 중복 경고 {{ duplicate_count }}개</p>
{% for item in prepared %}<article style="border:1px solid var(--border);border-radius:10px;padding:14px;margin:10px 0">
<h3>{{ item.index }}번 문항 {% if item.errors %}<span>오류 {{ item.errors|length }}건</span>{% elif item.duplicate %}<span>중복 경고</span>{% else %}<span>정상</span>{% endif %}</h3>
{% if item.data %}<p><strong>{{ item.data.subject }} / {{ item.data.course }} / {{ item.data.unit }}</strong></p>
<div class="math-content">{{ item.data.prompt|safe }}</div><p>정답: <span class="math-content">{{ item.data.answer|safe }}</span></p>
{% endif %}{% for e in item.errors %}<p class="error">{{ e }}</p>{% endfor %}</article>{% endfor %}
<form method="post" class="card" style="padding:20px">
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="mode" value="import">
<textarea name="payload" hidden>{{ payload }}</textarea>
<label><input type="checkbox" name="allow_duplicates" value="1"> 중복 경고 문항도 등록</label>
{% if can_partial %}<label><input type="checkbox" name="partial" value="1"> 오류가 있는 문항은 제외하고 나머지만 등록</label>{% endif %}
<button type="submit">일괄 등록</button>
<a href="{{ url_for('questions_bulk') }}">다시 업로드</a>
</form></section>
{% endif %}
<script src="{{ url_for('static', filename='scripts/katex-render.js') }}" defer></script>
</main></div></body></html>
"""

_ACL_TEMPLATE = r"""
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACL 권한 관리 | HEXORA</title>
<link rel="stylesheet" href="{{ url_for('static', filename='styles/shared.css') }}"><link rel="stylesheet" href="{{ url_for('static', filename='styles/tokens.css') }}"><link rel="stylesheet" href="{{ url_for('static', filename='styles/base.css') }}"><link rel="stylesheet" href="{{ url_for('static', filename='styles/layout.css') }}"><link rel="stylesheet" href="{{ url_for('static', filename='styles/components.css') }}">
</head><body><div class="app app-standard">{{ render_sidebar() }}<main>
<header class="page-header"><p>ADMINISTRATION / SECURITY</p><h1>ACL 권한 관리</h1><p>역할 기본 권한과 사용자별 허용·거부 규칙을 관리합니다.</p></header>
{% if saved %}<div class="notice success">권한 변경이 저장되었습니다.</div>{% endif %}
<section class="card" style="padding:20px"><h2>사용자별 권한</h2>
<form method="post"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<label>대상 유형 <select name="target_type"><option value="user">사용자별 권한</option><option value="role">역할 기본 권한</option></select></label>
<label>사용자 <select name="user_uuid"><option value="">선택 안 함</option>{% for user in users %}<option value="{{ user.uuid }}">{{ user.display_name }} ({{ user.email }}) · {{ user.role }}</option>{% endfor %}</select></label>
<label>역할 <select name="target_role"><option value="user">일반 사용자</option></select></label>
<label>권한 <select name="permission_code" required>{% for p in permissions %}<option value="{{ p.code }}">{{ p.category }} · {{ p.label }} ({{ p.code }})</option>{% endfor %}</select></label>
<label>정책 <select name="effect"><option value="allow">허용</option><option value="deny">명시적 거부</option><option value="none">개별 설정 제거</option></select></label>
<button type="submit">권한 저장</button></form></section>
<section class="card" style="padding:20px"><h2>현재 사용자별 설정</h2>
<table><thead><tr><th>사용자</th><th>권한</th><th>정책</th></tr></thead><tbody>
{% for row in assignments %}<tr><td>{{ row.display_name }}</td><td><code>{{ row.permission_code }}</code></td><td>{{ '허용' if row.effect == 'allow' else '거부' }}</td></tr>{% else %}<tr><td colspan="3">개별 설정이 없습니다.</td></tr>{% endfor %}
</tbody></table></section>
<section class="card" style="padding:20px"><h2>역할 기본 정책</h2><table><thead><tr><th>역할</th><th>권한</th><th>정책</th></tr></thead><tbody>{% for row in role_assignments %}<tr><td>{{ row.role }}</td><td><code>{{ row.permission_code }}</code></td><td>{{ "허용" if row.effect == "allow" else "거부" }}</td></tr>{% else %}<tr><td colspan="3">별도 역할 정책이 없습니다.</td></tr>{% endfor %}</tbody></table></section>
</main></div></body></html>
"""

def _register_bulk_and_acl_routes(app):
    @app.route("/admin/acl", methods=["GET", "POST"])
    @admin_required
    def admin_acl():
        connection = get_db()
        _ensure_acl_schema(connection)
        if request.method == "POST":
            target_type = request.form.get("target_type", "user")
            target_uuid = request.form.get("user_uuid", "")
            target_role = request.form.get("target_role", "")
            code = request.form.get("permission_code", "")
            effect = request.form.get("effect", "")
            target = connection.execute(
                "SELECT uuid, role FROM users WHERE uuid = ?", (target_uuid,)
            ).fetchone() if target_type == "user" else None
            known = {item[0] for item in ACL_PERMISSIONS}
            valid_target = (target is not None) if target_type == "user" else (target_type == "role" and target_role == "user")
            if not valid_target or code not in known or effect not in {"allow", "deny", "none"}:
                abort(400, description="권한 변경 요청이 올바르지 않습니다.")
            if code == "permissions.manage":
                abort(400, description="권한 관리자 권한은 사용자에게 직접 부여할 수 없습니다.")
            try:
                begin_write_transaction(connection)
                if target_type == "role":
                    if effect == "none":
                        connection.execute(
                            "DELETE FROM acl_role_permissions WHERE role = ? AND permission_code = ?",
                            (target_role, code),
                        )
                    else:
                        connection.execute(
                            """INSERT INTO acl_role_permissions(role,permission_code,effect,updated_at)
                            VALUES (?,?,?,CURRENT_TIMESTAMP)
                            ON CONFLICT(role,permission_code) DO UPDATE SET
                            effect=excluded.effect, updated_at=CURRENT_TIMESTAMP""",
                            (target_role, code, effect),
                        )
                    target_uuid = None
                    audit_role = target_role
                else:
                    if effect == "none":
                        connection.execute(
                            "DELETE FROM acl_user_permissions WHERE user_uuid = ? AND permission_code = ?",
                            (target_uuid, code),
                        )
                    else:
                        connection.execute(
                            """INSERT INTO acl_user_permissions
                            (user_uuid, permission_code, effect, granted_by, updated_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(user_uuid, permission_code) DO UPDATE SET
                            effect=excluded.effect, granted_by=excluded.granted_by,
                            updated_at=CURRENT_TIMESTAMP""",
                            (target_uuid, code, effect, g.user["uuid"]),
                        )
                    audit_role = None
                action = "remove" if effect == "none" else effect
                connection.execute(
                    """INSERT INTO acl_audit_log
                    (id, actor_uuid, target_user_uuid, target_role, permission_code, action)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), g.user["uuid"], target_uuid, audit_role, code, action),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            return redirect(url_for("admin_acl", saved=1))
        users = connection.execute(
            "SELECT uuid,email,display_name,role FROM users ORDER BY display_name,email"
        ).fetchall()
        permissions = connection.execute(
            "SELECT code,label,category FROM acl_permissions ORDER BY category,code"
        ).fetchall()
        assignments = connection.execute(
            """SELECT u.display_name, p.permission_code, p.effect
            FROM acl_user_permissions p JOIN users u ON u.uuid=p.user_uuid
            ORDER BY u.display_name,p.permission_code"""
        ).fetchall()
        role_assignments = connection.execute(
            "SELECT role,permission_code,effect FROM acl_role_permissions ORDER BY role,permission_code"
        ).fetchall()
        return render_template_string(
            _ACL_TEMPLATE, users=users, permissions=permissions,
            assignments=assignments, role_assignments=role_assignments,
            saved=request.args.get("saved") == "1",
        )

    @app.route("/questions/bulk", methods=["GET", "POST"])
    @login_required
    def questions_bulk():
        _require_acl("questions.bulk_import")
        connection = get_db()
        _ensure_acl_schema(connection)
        if request.method == "GET":
            return render_template_string(
                _BULK_TEMPLATE, prepared=None, errors=[], imported=None,
                can_partial=_has_acl_permission(g.user, "questions.bulk_import_partial"),
            )
        mode = request.form.get("mode", "preview")
        if mode == "import":
            raw = request.form.get("payload", "")
        else:
            uploaded = request.files.get("file")
            if uploaded is None or not uploaded.filename.lower().endswith(".json"):
                abort(400, description="JSON 파일을 선택해 주세요.")
            try:
                raw = uploaded.read(8 * 1024 * 1024 + 1).decode("utf-8-sig", errors="strict")
            except UnicodeDecodeError:
                abort(400, description="JSON 파일은 UTF-8 인코딩이어야 합니다.")
        if len(raw.encode("utf-8")) > 8 * 1024 * 1024:
            abort(413, description="JSON 파일은 8 MiB 이하여야 합니다.")
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            abort(400, description="UTF-8 JSON 파일을 확인해 주세요.")
        prepared, errors = _validate_bulk_document(document)
        allow_partial = request.form.get("partial") == "1"
        if allow_partial:
            _require_acl("questions.bulk_import_partial")
        valid_items = [item for item in prepared if item["data"] is not None and not item["errors"]]
        if mode != "import":
            return render_template_string(
                _BULK_TEMPLATE, prepared=prepared, errors=errors, imported=None,
                payload=json.dumps(document, ensure_ascii=False),
                valid_count=len(valid_items), invalid_count=len(prepared)-len(valid_items),
                duplicate_count=sum(1 for item in prepared if item["duplicate"]),
                can_partial=_has_acl_permission(g.user, "questions.bulk_import_partial"),
            )
        if errors and not allow_partial:
            return render_template_string(
                _BULK_TEMPLATE, prepared=prepared, errors=errors, imported=None,
                payload=json.dumps(document, ensure_ascii=False),
                valid_count=len(valid_items), invalid_count=len(prepared)-len(valid_items),
                duplicate_count=sum(1 for item in prepared if item["duplicate"]),
                can_partial=_has_acl_permission(g.user, "questions.bulk_import_partial"),
            ), 400
        allow_duplicates = request.form.get("allow_duplicates") == "1"
        rows_to_insert = [
            item for item in valid_items
            if allow_duplicates or not item["duplicate"]
        ]
        from question_constants import QUESTION_CONTENT_FIELDS
        inserted = 0
        try:
            begin_write_transaction(connection, lock_table="questions")
            for item in rows_to_insert:
                data = item["data"]
                cursor = connection.execute(
                    """INSERT INTO questions (
                    user_uuid,folder_uuid,subject,grade,unit,passage,prompt,examples,
                    choices,answer,explanation,source,year,page,difficulty,question_type,
                    points,course,curriculum,achievement_standard,source_type,exam,
                    original_question_number,source_url,license,title
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    RETURNING id""",
                    (g.user["uuid"], None, data["subject"], data["grade"], data["unit"],
                     data["passage"], data["prompt"], data["examples"],
                     json.dumps(data["choices"], ensure_ascii=False), data["answer"],
                     data["explanation"], data["source"], data["year"], data["page"],
                     data["difficulty"], data["question_type"], data["points"],
                     data["course"], data["curriculum"], data["achievement_standard"],
                     data["source_type"], data["exam"], data["original_question_number"],
                     data["source_url"], data["license"], data["title"]),
                )
                question_id = cursor.fetchone()["id"]
                question = connection.execute(
                    "SELECT * FROM questions WHERE id = ?", (question_id,)
                ).fetchone()
                _insert_question_revision(
                    connection, question_id, 1, g.user["uuid"], "JSON 일괄 등록",
                    _question_snapshot(question),
                )
                inserted += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return render_template_string(
            _BULK_TEMPLATE, prepared=None, errors=[], imported=inserted,
            can_partial=_has_acl_permission(g.user, "questions.bulk_import_partial"),
        )

    @app.get("/questions/export.json")
    @login_required
    def questions_bulk_export():
        _require_acl("questions.bulk_export")
        from question_constants import QUESTION_CONTENT_FIELDS
        columns = ", ".join(QUESTION_CONTENT_FIELDS)
        rows = get_db().execute(
            f"SELECT {columns} FROM questions WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall()
        questions = []
        for row in rows:
            item = dict(row)
            try:
                item["choices"] = json.loads(item.get("choices") or "[]")
            except (TypeError, json.JSONDecodeError):
                item["choices"] = []
            questions.append(item)
        payload = {
            "version": "1.0",
            "metadata": {"format": "HEXORA questions", "count": len(questions)},
            "questions": questions,
        }
        return Response(
            json.dumps(payload, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": 'attachment; filename="questions.json"'},
        )
