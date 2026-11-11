# -*- coding: utf-8 -*-
"""
Скрипт съёмки скриншотов для ДЗ № 08 (notes_homework).

Строит HTML-страницы, имитирующие окно редактора (для кода main.py /
utils.py / database.py) и окно терминала (реальный прогон main.py),
и снимает их в PNG через headless Chromium (playwright).

Запуск из корня репозитория:
    ../venv/Scripts/python.exe reports/homework_08_notes/make_screenshots.py
"""

import html
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]          # корень репозитория
PROJECT = ROOT / "notes_homework"
SESSION = Path(r"C:\Users\fedan\AppData\Local\Temp\notes_session.txt")
OUT = ROOT / "reports" / "screenshots" / "homework_08_notes"

# --- Подсветка синтаксиса Python (упрощённая, в палитре VS Code dark+) ----

KEYWORDS = {
    "def", "return", "import", "from", "if", "elif", "else", "while", "for",
    "in", "not", "and", "or", "break", "continue", "True", "False", "None",
    "is", "try", "except", "pass", "as",
}
BUILTINS = {
    "print", "input", "len", "int", "str", "float", "list", "dict", "bool",
    "enumerate", "range",
}

COLOR = {
    "comment": "#6a9955",
    "string": "#ce9178",
    "keyword": "#569cd6",
    "builtin": "#dcdcaa",
    "number": "#b5cea8",
}

TRIPLE_QUOTES = r"'''[\s\S]*?'''" + "|" + r'"""[\s\S]*?"""'
SINGLE_QUOTE_STRING = r"'(?:[^'\\\n]|\\.)*'"
DOUBLE_QUOTE_STRING = r'"(?:[^"\\\n]|\\.)*"'

TOKEN_RE = re.compile(
    r"(?P<comment>\#.*)"
    r"|(?P<string>f?r?b?(?:" + TRIPLE_QUOTES
    + "|" + SINGLE_QUOTE_STRING + "|" + DOUBLE_QUOTE_STRING + r"))"
    r"|(?P<word>\b[A-Za-z_][A-Za-z_0-9]*\b)"
    r"|(?P<number>\b\d+\b)"
)


def _kind_of(match: re.Match) -> str | None:
    """Определяет тип токена; None = не подсвечивать."""
    if match.group("comment"):
        return "comment"
    if match.group("string"):
        return "string"
    if match.group("word"):
        word = match.group("word")
        if word in KEYWORDS:
            return "keyword"
        if word in BUILTINS:
            return "builtin"
        return None
    if match.group("number"):
        return "number"
    return None


def highlight_python(source: str) -> str:
    """Подсвечивает весь исходник сразу (docstring'и — многострочные).

    Синтаксис вне подсвечиваемых токенов (скобки, знаки сравнения и т. п.)
    экранируется как обычный HTML.
    """
    out: list[str] = []
    pos = 0
    for match in TOKEN_RE.finditer(source):
        if match.start() > pos:
            out.append(html.escape(source[pos:match.start()]))
        kind = _kind_of(match)
        escaped = html.escape(match.group(0))
        out.append(
            f'<span style="color:{COLOR[kind]}">{escaped}</span>'
            if kind is not None
            else escaped
        )
        pos = match.end()
    out.append(html.escape(source[pos:]))
    return "".join(out)


def render_code(source: str) -> str:
    """Собирает HTML области кода: номера строк + подсветка."""
    rows = []
    for i, line in enumerate(highlight_python(source).split("\n"), start=1):
        rows.append(
            f'<div class="lrow"><span class="ln">{i}</span>'
            f'<span class="code">{line or "&nbsp;"}</span></div>'
        )
    return "\n".join(rows)


# --- Оформление «окна» редактора и терминала --------------------------------

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#1e1e1e; font-family:Consolas,'Cascadia Mono',monospace; }
.shot { width:900px; border-radius:8px; overflow:hidden; margin:0 auto 40px;
        box-shadow:0 8px 32px rgba(0,0,0,.55); }
.bar { height:34px; background:#3c3c3c; display:flex; align-items:center;
       padding-left:14px; }
.dot { width:12px; height:12px; border-radius:50%; margin-right:8px; }
.filetab { height:30px; background:#2d2d2d; display:flex; align-items:center;
           padding-left:16px; border-top:1px solid #252526; }
.filetab .active { background:#1e1e1e; color:#e8e8e8; padding:6px 16px;
                   font-size:12.5px; border-top:1px solid #0e639c; }
.codearea { background:#1e1e1e; padding:12px 0; font-size:14px;
            line-height:20px; }
.lrow { display:flex; }
.ln { width:50px; text-align:right; padding-right:20px; color:#858585;
      flex:none; user-select:none; }
.code { color:#d4d4d4; white-space:pre; }
.term { background:#0c0c0c; font-size:14px; line-height:20px;
        padding:12px 18px; }
.term pre { color:#cccccc; white-space:pre-wrap; word-break:break-word;
            font-family:inherit; }
.titletab { height:36px; background:#2b2b2b; display:flex; align-items:center;
            padding-left:16px; color:#cccccc; font-size:12.5px; }
"""

# Строка запуска показывается над выводом сессии (stdin перенаправлен,
# поэтому в самой сессии приглашённого ввода с echo нет).
PROMPT_LINE = (
    "PS C:\\Users\\fedan\\OneDrive\\Desktop\\VIBE-Coder\\Курс\\notes_homework>"
    " python main.py\n"
)


def vs_window(shot_id: str, filename: str, inner: str) -> str:
    """Единая «обёртка» окна: панель заголовка, вкладка файла, код."""
    return (
        f'<div class="shot" id="{shot_id}">'
        '<div class="bar">'
        '<span class="dot" style="background:#ff5f57"></span>'
        '<span class="dot" style="background:#febc2e"></span>'
        '<span class="dot" style="background:#28c840"></span>'
        "</div>"
        f'<div class="filetab"><span class="active">{filename}</span></div>'
        f'<div class="codearea"><pre style="font-family:inherit">{inner}</pre></div>'
        "</div>"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    sources = {name: (PROJECT / name).read_text(encoding="utf-8")
               for name in ("main.py", "utils.py", "database.py")}
    session = SESSION.read_text(encoding="utf-8").replace("\ufeff", "")

    terminal_html = (
        '<div class="shot" id="shot-terminal">'
        '<div class="titletab">Windows PowerShell</div>'
        f'<div class="term"><pre>'
        f"{html.escape(PROMPT_LINE + session)}</pre></div>"
        "</div>"
    )

    shots = {
        "shot-main": vs_window(
            "shot-main", "main.py", render_code(sources["main.py"])
        ),
        "shot-utils": vs_window(
            "shot-utils", "utils.py", render_code(sources["utils.py"])
        ),
        "shot-database": vs_window(
            "shot-database", "database.py", render_code(sources["database.py"])
        ),
        "shot-terminal": terminal_html,
    }

    page_html = (
        "<!doctype html><meta charset='utf-8'>"
        f"<style>{CSS}</style><body>"
        + "".join(shots.values())
        + "</body>"
    )

    work = Path(__file__).parent / "_render"
    work.mkdir(exist_ok=True)
    (work / "shots.html").write_text(page_html, encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1000, "height": 800},
            device_scale_factor=2,
        )
        page.goto((work / "shots.html").as_uri())
        page.wait_for_timeout(300)
        for shot_id, path_name in [
            ("shot-main", "01_main_py_code.png"),
            ("shot-utils", "02_utils_py_code.png"),
            ("shot-database", "03_database_py_code.png"),
            ("shot-terminal", "04_terminal_run.png"),
        ]:
            page.locator(f"#{shot_id}").screenshot(path=str(OUT / path_name))
            print("ok:", path_name)
        browser.close()


if __name__ == "__main__":
    main()
