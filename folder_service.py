from database import get_db


def get_folder_data(subject, owner_uuid):
    connection = get_db()
    folders = connection.execute(
        """
        SELECT uuid, name, parent_uuid
        FROM folders
        WHERE user_uuid = ?
        ORDER BY LOWER(name), uuid
        """,
        (owner_uuid,),
    ).fetchall()
    question_counts = connection.execute(
        """
        SELECT folder_uuid, COUNT(*) AS count
        FROM questions
        WHERE user_uuid = ? AND subject = ?
        GROUP BY folder_uuid
        """,
        (owner_uuid, subject),
    ).fetchall()

    nodes = {
        folder["uuid"]: {
            "uuid": folder["uuid"],
            "name": folder["name"],
            "parent_uuid": folder["parent_uuid"],
            "children": [],
            "count": 0,
        }
        for folder in folders
    }
    roots = []
    for folder in folders:
        node = nodes[folder["uuid"]]
        parent = nodes.get(folder["parent_uuid"])
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)

    direct_counts = {
        row["folder_uuid"]: row["count"]
        for row in question_counts
        if row["folder_uuid"] is not None
    }

    def count_descendants(node):
        node["count"] = direct_counts.get(node["uuid"], 0) + sum(
            count_descendants(child) for child in node["children"]
        )
        return node["count"]

    for root in roots:
        count_descendants(root)

    options = []

    def append_options(folder_nodes, depth=0):
        for folder in folder_nodes:
            options.append(
                {
                    "uuid": folder["uuid"],
                    "name": folder["name"],
                    "depth": depth,
                }
            )
            append_options(folder["children"], depth + 1)

    append_options(roots)
    return roots, options
