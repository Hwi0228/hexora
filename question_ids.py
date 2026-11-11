BASE36_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE36_WIDTH = 6


def format_question_number(question_id):
    value = int(question_id)
    if value < 0 or value >= 36 ** BASE36_WIDTH:
        raise ValueError("문항 번호가 6자리 Base36 범위를 초과했습니다.")
    encoded = "0" if value == 0 else ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = BASE36_ALPHABET[remainder] + encoded
    return encoded.rjust(BASE36_WIDTH, "0")


def parse_question_number(value):
    value = (value or "").strip().upper()
    if len(value) != BASE36_WIDTH or any(char not in BASE36_ALPHABET for char in value):
        return None
    try:
        question_id = int(value, 36)
    except ValueError:
        return None
    return question_id if format_question_number(question_id) == value else None
