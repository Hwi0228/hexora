from flask import render_template
from markupsafe import Markup


def render_sidebar():
    """Render the shared sidebar with the active request's Flask/Jinja context."""
    return Markup(render_template("partials/sidebar.html"))
