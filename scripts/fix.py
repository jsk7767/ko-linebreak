# -*- coding: utf-8 -*-
"""한국어 줄바꿈 자동 적용기. 문구는 절대 바꾸지 않고 개행 위치(<br>)·의미 청킹(<span class="nb">)만 넣는다.

사용:
  py -3 fix.py FILE.html                       # 기본: --sentences. 변경 미리보기(diff)만 출력
  py -3 fix.py FILE.html --write               # 백업(FILE.bak.kolb_시각) 후 적용
  py -3 fix.py FILE.html --sentences --clauses 45 --nb "h1,.lede,.glance-lead" --css --write

--sentences : 디스플레이 블록(p·figcaption·dd·small·blockquote)에서 문장 2개+ 인데 <br> 없으면 문장 경계에 <br>
--clauses N : <br> 사이 한 줄이 N자 넘고 한 문장이면, 가운데에 가장 가까운 절 경계(쉼표·연결어미)에 <br> 하나
--nb SEL    : 선택자(태그명 또는 .클래스, 쉼표 구분)에 해당하는 요소의 텍스트를 의미 덩어리 <span class="nb">로 감싼다
              (이미 nb 가 있거나 덩어리 안에 태그가 있는 줄은 건너뛴다)
--css       : 1단계 CSS(keep-all·overflow-wrap·text-wrap·.nb)가 없으면 첫 <style> 앞머리에 주석 달아 주입
안전장치: 기계용 텍스트(title·meta·JSON-LD·script·style)는 건드리지 않는다. --write 없이는 파일을 바꾸지 않는다.
"""
from __future__ import annotations

import argparse
import difflib
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kolb  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SENTENCE_TAGS = ("p", "figcaption", "dd", "small", "blockquote")
BASE_CSS = ("/* ko-linebreak 1단계: 한국어 줄바꿈 기본기 */\n"
            "body{word-break:keep-all;overflow-wrap:break-word}\n"
            "p,li,dd,dt,figcaption,summary,small,span{text-wrap:pretty}\n"
            "h1,h2,h3{text-wrap:balance}\n"
            ".nb{white-space:nowrap}\n")


def protect_ranges(html: str) -> list[tuple[int, int]]:
    """건드리면 안 되는 구간: script·style·title·JSON-LD·주석"""
    rngs = []
    for pat in (r"<script\b.*?</script>", r"<style\b.*?</style>", r"<title\b.*?</title>", r"<!--.*?-->"):
        for m in re.finditer(pat, html, re.S | re.I):
            rngs.append((m.start(), m.end()))
    return rngs


def in_protected(pos: int, rngs) -> bool:
    return any(a <= pos < b for a, b in rngs)


def insert_br_at_text_offsets(inner: str, offsets: list[int]) -> str:
    """텍스트 오프셋(경계 직후, 공백 앞) 위치에 <br> 삽입. 뒤따르는 공백 하나는 <br> 뒤 개행으로 대체해 소스 가독성을 유지한다."""
    text, pos = kolb.html_text_map(inner)
    out = inner
    for off in sorted(offsets, reverse=True):
        if off >= len(pos):
            continue
        hp = pos[off]  # 경계 직후 글자(공백)의 HTML 위치
        # 공백이면 그 공백을 "<br>\n" 로 치환, 아니면 그 앞에 삽입
        if out[hp] in " \t":
            out = out[:hp] + "<br>\n" + out[hp + 1:]
        else:
            out = out[:hp] + "<br>\n" + out[hp:]
    return out


def fix_sentences(html: str, rngs, log: list[str]) -> str:
    edits = []  # (start, end, new_inner) — 뒤에서부터 적용
    for tag, attrs, inner, start, end in kolb.iter_display_blocks(html, SENTENCE_TAGS):
        if in_protected(start, rngs):
            continue
        if "<br" in inner or kolb.BLOCKISH_RE.search(inner):
            continue
        text, _ = kolb.html_text_map(inner)
        flat = re.sub(r"\s+", " ", text)
        if not re.search(r"[가-힣]", flat) or len(kolb.split_sentences(flat, use_kss=False)) < 2:
            continue
        offs = kolb.sentence_boundaries(text)
        if not offs:
            continue
        new_inner = insert_br_at_text_offsets(inner, offs)
        head = html.rfind(">", start, start + len(f"<{tag}") + len(attrs) + 2) + 1
        edits.append((start + (head - start), end - len(f"</{tag}>"), new_inner, tag, flat[:50]))
    for s0, e0, new_inner, tag, ev in sorted(edits, key=lambda x: -x[0]):
        html = html[:s0] + new_inner + html[e0:]
        log.append(f"[문장] <{tag}> {ev}…")
    return html


def fix_clauses(html: str, rngs, max_len: int, log: list[str]) -> str:
    """<br> 사이 한 줄이 길고 한 문장이면 절 경계 하나에서 끊는다(가운데에 가장 가까운 경계)."""
    edits = []
    for tag, attrs, inner, start, end in kolb.iter_display_blocks(html, SENTENCE_TAGS + ("li", "summary", "h2", "h3")):
        if in_protected(start, rngs) or 'class="nb"' in inner:
            continue
        parts = re.split(r"(<br\s*/?>)", inner)
        changed = False
        for i in range(0, len(parts), 2):
            seg = parts[i]
            text, pos = kolb.html_text_map(seg)
            flat = re.sub(r"\s+", " ", text).strip()
            if len(flat) <= max_len or len(kolb.split_sentences(flat, use_kss=False)) != 1:
                continue
            # 절 경계 후보(텍스트 오프셋): CLAUSE_RE 매치 끝 = 공백 뒤 → 공백 위치는 end-1
            cands = [m.end() - 1 for m in kolb.CLAUSE_RE.finditer(text) if text[m.end() - 1].isspace()]
            cands = [c for c in cands if 8 <= c <= len(text) - 8]
            if not cands:
                continue
            mid = len(text) / 2
            best = min(cands, key=lambda c: abs(c - mid))
            # 접속부사로 시작하는 뒷절은 앞절과 붙여 두지 않는다(정상) — 경계 그대로
            parts[i] = insert_br_at_text_offsets(seg, [best])
            changed = True
            log.append(f"[절] <{tag}> {flat[:50]}…")
        if changed:
            head = html.rfind(">", start, start + len(f"<{tag}") + len(attrs) + 2) + 1
            edits.append((head, end - len(f"</{tag}>"), "".join(parts)))
    for s0, e0, new_inner in sorted(edits, key=lambda x: -x[0]):
        html = html[:s0] + new_inner + html[e0:]
    return html


def _selector_matches(tag: str, attrs: str, sel: str) -> bool:
    sel = sel.strip()
    if sel.startswith("."):
        return re.search(r'class="[^"]*\b%s\b' % re.escape(sel[1:]), attrs) is not None
    return tag.lower() == sel.lower()


def wrap_nb(segment_html: str, max_len: int) -> str | None:
    """태그 없는 텍스트 구간만 청킹. 태그가 섞여 있으면 None(건너뜀)."""
    if "<" in segment_html:
        return None
    lead = re.match(r"^\s*", segment_html).group(0)
    trail = re.search(r"\s*$", segment_html).group(0)
    core = segment_html.strip()
    if not core or not re.search(r"[가-힣]", core):
        return None
    chunks = kolb.chunk_phrases(core, max_len=max_len)
    if len(chunks) < 2:
        return None
    return lead + " ".join(f'<span class="nb">{c}</span>' for c in chunks) + trail


def fix_nb(html: str, rngs, selectors: list[str], max_len: int, log: list[str]) -> str:
    edits = []
    tags = tuple({s.lstrip(".").lower() for s in selectors if not s.startswith(".")} | {"h1", "h2", "h3", "p", "dd", "small", "figcaption", "li", "blockquote"})
    for tag, attrs, inner, start, end in kolb.iter_display_blocks(html, tags):
        if in_protected(start, rngs) or 'class="nb"' in inner or "nb\"" in inner:
            continue
        if not any(_selector_matches(tag, attrs, s) for s in selectors):
            continue
        parts = re.split(r"(<br\s*/?>)", inner)
        changed = False
        for i in range(0, len(parts), 2):
            new = wrap_nb(parts[i], max_len)
            if new is not None:
                parts[i] = new
                changed = True
        if changed:
            head = html.rfind(">", start, start + len(f"<{tag}") + len(attrs) + 2) + 1
            edits.append((head, end - len(f"</{tag}>"), "".join(parts)))
            log.append(f"[nb] <{tag}{' ' + attrs.strip() if attrs.strip() else ''}> {re.sub(r'<[^>]+>', '', inner)[:40]}…")
    for s0, e0, new_inner in sorted(edits, key=lambda x: -x[0]):
        html = html[:s0] + new_inner + html[e0:]
    return html


def fix_css(html: str, log: list[str]) -> str:
    need = []
    if not re.search(r"word-break\s*:\s*keep-all", html, re.I):
        need.append("keep-all")
    if not re.search(r"text-wrap\s*:\s*pretty", html, re.I):
        need.append("pretty")
    if 'class="nb"' in html and not re.search(r"\.nb\s*\{[^}]*white-space\s*:\s*nowrap", html):
        need.append(".nb")
    if not need:
        return html
    m = re.search(r"<style\b[^>]*>", html, re.I)
    if m:
        html = html[:m.end()] + "\n" + BASE_CSS + html[m.end():]
    elif re.search(r"</head>", html, re.I):
        html = re.sub(r"</head>", "<style>\n" + BASE_CSS + "</style>\n</head>", html, count=1, flags=re.I)
    else:
        html = "<style>\n" + BASE_CSS + "</style>\n" + html
    log.append(f"[css] 기본기 주입 ({', '.join(need)} 누락)")
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description="한국어 줄바꿈 자동 적용기 (문구 불변)")
    ap.add_argument("file")
    ap.add_argument("--sentences", action="store_true", help="문장 경계 <br> (다른 옵션이 없으면 기본)")
    ap.add_argument("--clauses", type=int, metavar="N", help="N자 넘는 한 문장 줄을 절 경계에서 한 번 끊기")
    ap.add_argument("--nb", metavar="SEL", help='의미 청킹 대상 선택자 (예: "h1,.lede,.glance-lead")')
    ap.add_argument("--nb-max", type=int, default=12, help="nb 덩어리 최대 글자(공백·문장부호 제외). 기본 12")
    ap.add_argument("--css", action="store_true", help="1단계 CSS 누락 시 주입")
    ap.add_argument("--write", action="store_true", help="백업 후 파일에 적용 (없으면 diff 미리보기)")
    a = ap.parse_args()
    if not (a.sentences or a.clauses or a.nb or a.css):
        a.sentences = True

    path = Path(a.file)
    src = path.read_text(encoding="utf-8")
    html = src
    log: list[str] = []
    rngs = protect_ranges(html)
    if a.css:
        html = fix_css(html, log)
    if a.sentences:
        html = fix_sentences(html, protect_ranges(html), log)
    if a.clauses:
        html = fix_clauses(html, protect_ranges(html), a.clauses, log)
    if a.nb:
        html = fix_nb(html, protect_ranges(html), [s for s in a.nb.split(",") if s.strip()], a.nb_max, log)

    # 불변 검증: 태그·<br>·nb span 을 제거한 순수 텍스트(공백 정규화)가 같아야 한다
    def bare(h: str) -> str:
        t = re.sub(r"<br\s*/?>", " ", h)
        t = re.sub(r"</?span[^>]*>", "", t)
        t = re.sub(r"<style\b.*?</style>", "", t, flags=re.S | re.I)
        return re.sub(r"\s+", " ", t).strip()
    if bare(src) != bare(html):
        print("중단: 문구 불변 검증 실패 — 적용하지 않습니다.")
        return 2

    if html == src:
        print("변경 없음.")
        return 0
    for line in log:
        print(line)
    if a.write:
        bak = path.with_name(path.name + f".bak.kolb_{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(path, bak)
        path.write_text(html, encoding="utf-8", newline="\n")
        print(f"적용 {len(log)}건 · 백업 {bak.name}")
    else:
        diff = difflib.unified_diff(src.splitlines(), html.splitlines(), "before", "after", lineterm="", n=1)
        shown = 0
        for ln in diff:
            print(ln)
            shown += 1
            if shown > 120:
                print("… (diff 생략)")
                break
        print(f"\n미리보기 {len(log)}건 — 적용은 --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
