class HybridRow(dict):
    """Mapping-style row that also preserves sqlite3.Row-style integer indexing."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)



class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @staticmethod
    def _wrap(row):
        return HybridRow(row) if isinstance(row, dict) else row

    def fetchone(self):
        return self._wrap(self._cursor.fetchone())

    def fetchall(self):
        return [self._wrap(row) for row in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [self._wrap(row) for row in rows]

    def __iter__(self):
        for row in self._cursor:
            yield self._wrap(row)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def _translate_qmark_placeholders(statement):
    """Translate qmark binds without changing question marks inside SQL text."""
    output = []
    quote = None
    line_comment = False
    block_comment = False
    index = 0

    while index < len(statement):
        char = statement[index]
        next_char = statement[index + 1] if index + 1 < len(statement) else ""

        if line_comment:
            output.append(char)
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment:
            output.append(char)
            if char == "*" and next_char == "/":
                output.append(next_char)
                index += 2
                block_comment = False
            else:
                index += 1
            continue

        if quote:
            output.append(char)
            if char == quote:
                if next_char == quote:
                    output.append(next_char)
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char == "-" and next_char == "-":
            output.extend((char, next_char))
            index += 2
            line_comment = True
        elif char == "/" and next_char == "*":
            output.extend((char, next_char))
            index += 2
            block_comment = True
        elif char in {"'", '"'}:
            output.append(char)
            quote = char
            index += 1
        elif char == "?":
            output.append("%s")
            index += 1
        else:
            output.append(char)
            index += 1

    return "".join(output)


class PostgresConnection:
    """Small psycopg adapter for the existing sqlite3-style execute API."""

    backend = "postgresql"

    def __init__(self, connection):
        self.raw = connection

    def execute(self, statement, parameters=()):
        # Application SQL uses qmark placeholders. psycopg uses %s.
        cursor = self.raw.execute(_translate_qmark_placeholders(statement), tuple(parameters or ()))
        return PostgresCursor(cursor)

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.raw.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name):
        return getattr(self.raw, name)


