"""Patch line breaks into existing daily HTML reports."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_html(path: Path) -> bool:
    if not path.exists():
        return False
    html = path.read_text(encoding="utf-8")
    orig = html

    html = re.sub(
        r"<p>(\d{4}-\d{2}-\d{2} 종가 기준 · 당일 시세는 반영하지 않습니다)\. "
        r"(LLM·증권사 API 없이 시세·기술지표·뉴스 헤드라인으로 만든 참고용 리포트입니다)\. "
        r"(투자 자문이 아니며, 최종 판단은 본인에게 있습니다)\.</p>",
        r"<p>\1.<br>\n      \2.<br>\n      \3.</p>",
        html,
        count=1,
    )

    html = re.sub(
        r"<p class=\"term-hint\">(요약 행을 <strong>클릭</strong>하면 오른쪽에 종목 리포트가 열립니다)\. "
        r"(점선 밑줄 용어를 클릭하면 초보자용 설명이 뜹니다)\.\s*\n\s*(점수대별 향후 수익률:)",
        r'<p class="term-hint">\1.<br>\n        \2.<br>\n        \3',
        html,
        count=1,
    )

    html = re.sub(
        r"(순매수</button> 가중합)\. (<button type=\"button\" class=\"term\"[^>]*>매수관심</button>)",
        r"\1.<br>\n      \2",
        html,
        count=1,
    )

    if ".hero p {" in html and "line-height: 1.55" not in html.split(".hero p {", 1)[1].split("}", 1)[0]:
        html = html.replace(
            ".hero p {\n      margin: 0;\n      color: var(--muted);\n      max-width: 42rem;\n    }",
            ".hero p {\n      margin: 0 0 0.4rem;\n      color: var(--muted);\n      max-width: 42rem;\n      line-height: 1.55;\n    }\n    .hero p:last-of-type {\n      margin-bottom: 0;\n    }",
            1,
        )

    if ".term-hint {" in html and "line-height: 1.55" not in html.split(".term-hint {", 1)[1].split("}", 1)[0]:
        html = re.sub(
            r"(\.term-hint \{[^}]*color: var\(--muted\);)\s*(\})",
            r"\1\n      line-height: 1.55;\n    \2",
            html,
            count=1,
        )

    if ".note {" in html and "line-height: 1.55" not in html.split(".note {", 1)[1].split("}", 1)[0]:
        html = re.sub(
            r"(\.note \{[^}]*font-size: 0\.88rem;)\s*(\})",
            r"\1\n      line-height: 1.55;\n      max-width: 42rem;\n    \2",
            html,
            count=1,
        )

    if html != orig:
        path.write_text(html, encoding="utf-8")
        return True
    return False


def main() -> int:
    targets = [
        ROOT / "reports" / "daily" / "latest.html",
        ROOT / "reports" / "daily" / "2026" / "07" / "15" / "report.html",
    ]
    for path in targets:
        if patch_html(path):
            print(f"patched {path}")
        else:
            print(f"skip {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
