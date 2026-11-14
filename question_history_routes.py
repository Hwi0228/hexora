import json
import re
from difflib import SequenceMatcher
from html import escape
from html.parser import HTMLParser

from flask import abort, g, redirect, render_template, request, url_for

from constants import NAV_ITEMS
from question_constants import QUESTION_CONTENT_FIELDS, QUESTION_FIELD_LABELS
from question_ids import format_question_number
from database import begin_write_transaction, get_db
from question_revisions import _ensure_initial_question_revision, _insert_question_revision
from question_repository import _question_row, _update_question_content




class _RevisionTextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "li", "blockquote", "pre", "br", "h1", "h2", "h3"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "ql-math-inline" in classes or "ql-math-block" in classes:
            self.parts.append("$" + (attributes.get("data-latex") or "") + "$")
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def _plain_revision_text(value):
    if value is None:
        return ""
    parser = _RevisionTextExtractor()
    parser.feed(str(value))
    parser.close()
    text = "".join(parser.parts).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _render_diff_side(before, after, side):
    token_pattern = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$\n]+\$|\s+|[^\s$]+")
    before_tokens = token_pattern.findall(before)
    after_tokens = token_pattern.findall(after)
    matcher = SequenceMatcher(None, before_tokens, after_tokens, autojunk=False)
    parts = []
    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if side == "before":
            value = "".join(before_tokens[before_start:before_end])
            changed = tag in {"replace", "delete"}
            wrapper = "del"
            css_class = "diff-removed"
        else:
            value = "".join(after_tokens[after_start:after_end])
            changed = tag in {"replace", "insert"}
            wrapper = "ins"
            css_class = "diff-added"
        if not value:
            continue
        safe_value = escape(value, quote=False).replace("\n", "<br>")
        if changed:
            parts.append(f'<{wrapper} class="{css_class}">{safe_value}</{wrapper}>')
        else:
            parts.append(safe_value)
    return "".join(parts)
def question_history(question_id):
    question = _question_row(question_id)
    connection = get_db()
    _ensure_initial_question_revision(connection, question)
    connection.commit()
    revisions = connection.execute(
        """
        SELECT question_revisions.revision_number, question_revisions.summary,
               question_revisions.created_at, users.display_name AS editor_name
        FROM question_revisions
        LEFT JOIN users ON users.uuid = question_revisions.editor_uuid
        WHERE question_revisions.question_id = ?
        ORDER BY question_revisions.revision_number DESC
        """,
        (question_id,),
    ).fetchall()

    compare_from = request.args.get("from", type=int)
    compare_to = request.args.get("to", type=int)
    if compare_from is None or compare_to is None:
        if len(revisions) >= 2:
            compare_from = revisions[1]["revision_number"]
            compare_to = revisions[0]["revision_number"]
        else:
            compare_from = compare_to = revisions[0]["revision_number"]

    comparison = []
    if compare_from != compare_to:
        rows = connection.execute(
            """
            SELECT revision_number, snapshot_json
            FROM question_revisions
            WHERE question_id = ? AND revision_number IN (?, ?)
            """,
            (question_id, compare_from, compare_to),
        ).fetchall()
        snapshots = {
            row["revision_number"]: json.loads(row["snapshot_json"])
            for row in rows
        }
        if compare_from not in snapshots or compare_to not in snapshots:
            abort(404)
        for field in QUESTION_CONTENT_FIELDS:
            before = snapshots[compare_from].get(field)
            after = snapshots[compare_to].get(field)
            if field == "choices":
                before = "\n".join(before or [])
                after = "\n".join(after or [])
            before_text = _plain_revision_text(before)
            after_text = _plain_revision_text(after)
            # Ignore markup-only differences; compare visible text and TeX payloads.
            if before_text != after_text:
                comparison.append({
                    "field": QUESTION_FIELD_LABELS[field],
                    "before_html": _render_diff_side(before_text, after_text, "before"),
                    "after_html": _render_diff_side(before_text, after_text, "after"),
                })

    return render_template(
        "question_history.html", nav_items=NAV_ITEMS, question=question,
        question_number=format_question_number(question["id"]),
        revisions=revisions, compare_from=compare_from, compare_to=compare_to,
        comparison=comparison, latest_revision=revisions[0]["revision_number"],
        saved=request.args.get("saved") == "1",
        restored=request.args.get("restored") == "1",
    )


def restore_question(question_id, revision_number):
    question = _question_row(question_id)
    connection = get_db()
    try:
        begin_write_transaction(connection, lock_table="questions")
        question = _question_row(question_id)
        _ensure_initial_question_revision(connection, question)
        target = connection.execute(
            """
            SELECT snapshot_json FROM question_revisions
            WHERE question_id = ? AND revision_number = ?
            """,
            (question_id, revision_number),
        ).fetchone()
        latest = connection.execute(
            "SELECT MAX(revision_number) FROM question_revisions WHERE question_id = ?",
            (question_id,),
        ).fetchone()[0]
        if target is None:
            connection.rollback()
            abort(404)
        snapshot = json.loads(target["snapshot_json"])
        defaults = {
            "title": "",
            "course": "",
            "curriculum": "2015 개정 교육과정",
            "achievement_standard": "",
            "difficulty": "중",
            "question_type": "단답형",
            "points": 4,
            "source_type": "기타",
            "exam": "",
            "original_question_number": "",
            "source_url": "",
            "license": "",
        }
        for field, default in defaults.items():
            snapshot.setdefault(field, default)
        next_revision = latest + 1
        _update_question_content(connection, question_id, snapshot)
        _insert_question_revision(
            connection, question_id, next_revision, g.user["uuid"],
            f"이전 버전 v{revision_number} 복원", snapshot,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return redirect(url_for("question_history", question_id=question_id, restored=1))
