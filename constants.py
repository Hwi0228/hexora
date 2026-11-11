NAV_ITEMS = [
    {"icon": "⌂", "label": "대시보드", "endpoint": "dashboard"},
    {"icon": "▤", "label": "문제 DB", "endpoint": "main"},
    {"icon": "◇", "label": "HWP 파싱", "endpoint": "hwp_parser_page"},
    {"icon": "＋", "label": "문제 등록", "endpoint": "new_question"},
]

SUBJECTS = ["수학", "과학", "국어", "영어", "사회", "기타"]


GRADE_OPTIONS = (
    "초1", "초2", "초3", "초4", "초5", "초6",
    "중1", "중2", "중3", "고1", "고2", "고3", "대학", "기타",
)

LICENSE_CHOICES = {
    "ORIGINAL": "직접 제작 (권리 보유)",
    "CC-BY-4.0": "CC BY 4.0",
    "CC-BY-SA-4.0": "CC BY-SA 4.0",
    "CC0-1.0": "CC0 1.0 / 퍼블릭 도메인",
    "PERMISSION": "권리자로부터 공개 허가 받음",
}

SOURCE_TYPES = (
    "직접 제작", "교재 및 참고서", "학교 시험", "수능 및 모의평가",
    "공개 데이터셋", "기타",
)
