# -*- coding: utf-8 -*-
"""한국어 줄바꿈 점검기 v2. 사용: py -3 check.py FILE.html [--min-sentences 2] [--clause-len 45] [--nb-max 14] [--suggest] [--json]

필수(exit 1): CSS 기본기 누락 · 디스플레이 블록 미개행 · <br> 뒤 줄머리 조사/문장부호 · 기계용 텍스트 안 <br>
검토(exit 0): nb 덩어리 길이 · 절 분리 후보 · 외톨이 마지막 줄 · &nbsp; 남용 · 목록/표/제목의 다문장
문장 경계는 kss(있으면) → 정규식. 문구는 절대 바꾸지 않는다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kolb  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MUST_TAGS = {"p", "figcaption", "dd", "small", "blockquote"}  # 2문장+ 미개행 = 필수
REVIEW_TAGS = {"li", "td", "h1", "h2", "h3", "summary"}  # 정보성·제목성일 수 있어 검토
ORDER = {"CSS": 0, "문장개행": 1, "줄머리": 2, "nb길이": 3, "금지위치": 4, "절후보": 5, "외톨이": 6, "nbsp": 7, "다문장검토": 8}
MUST = {"CSS", "문장개행", "줄머리", "금지위치"}  # nb길이는 글꼴 크기에 따라 달라 정적 판정은 검토, 실측은 render_check.py


def css_present(s: str, prop: str, values: tuple[str, ...]) -> bool:
    pat = re.compile(prop.replace("-", r"\-") + r"\s*:\s*(" + "|".join(re.escape(v) for v in values) + r")", re.I)
    return bool(pat.search(s))


def run(path: str, min_sentences: int, clause_len: int, nb_max: int, suggest: bool, use_kss: bool = True) -> dict:
    s = open(path, encoding="utf-8").read()
    issues: list[dict] = []

    def add(kind, msg, ev="", extra=None):
        item = {"kind": kind, "must": kind in MUST, "msg": msg, "evidence": ev[:90]}
        if extra:
            item.update(extra)
        issues.append(item)

    is_html = "<" in s and ">" in s
    # ── 1) CSS 기본기 ─────────────────────────────────────────────────
    if is_html:
        if not css_present(s, "word-break", ("keep-all",)):
            add("CSS", "body에 word-break:keep-all 누락 — 단어 중간 꺾임 발생")
        if not css_present(s, "overflow-wrap", ("break-word", "anywhere")) and not css_present(s, "word-wrap", ("break-word",)):
            add("CSS", "overflow-wrap:break-word(또는 anywhere) 누락 — keep-all 상태에서 긴 URL·영단어가 넘친다")
        if not css_present(s, "text-wrap", ("pretty",)):
            add("CSS", "text-wrap:pretty 누락 — 외톨이 글자 위험 (미지원 브라우저는 nb 청킹·text-balancer 폴백)")
        if not css_present(s, "text-wrap", ("balance",)):
            add("CSS", "제목 text-wrap:balance 누락")
        if re.search(r"<html\b", s, re.I) and not re.search(r"<html\b[^>]*\blang\s*=\s*[\"']?ko", s, re.I):
            add("CSS", '<html lang="ko"> 누락 — 브라우저 줄바꿈·글꼴 규칙이 언어를 모른다')
        if re.search(r'class="[^"]*\bnb\b', s) and not re.search(r"\.nb\s*\{[^}]*white-space\s*:\s*nowrap", s):
            add("CSS", ".nb 클래스를 쓰는데 .nb{white-space:nowrap} 정의가 없다")

    # ── 2·3·5) 블록 단위 검사 ─────────────────────────────────────────
    nb_spans = re.findall(r'<span\b[^>]*class="[^"]*\bnb\b[^"]*"[^>]*>(.*?)</span>', s, re.S)
    for inner in nb_spans:
        t = re.sub(r"\s+", " ", kolb.strip_tags(inner)).strip()
        if kolb._nlen(t) > nb_max:
            add("nb길이", f"nb 덩어리 {kolb._nlen(t)}자 (기준 {nb_max}) — 좁은 화면에서 넘칠 수 있음", t)

    seen = set()
    for tag, _attrs, inner, start, _end in kolb.iter_display_blocks(s):
        if start in seen:
            continue
        seen.add(start)
        text = re.sub(r"\s+", " ", kolb.strip_tags(inner).replace("\n", " ")).strip()
        if not text or not re.search(r"[가-힣]", text):
            continue
        sents = kolb.split_sentences(text, use_kss=use_kss)
        has_br = "<br" in inner or kolb.BLOCKISH_RE.search(inner) is not None or re.search(r"\n(?=\S)", inner.strip()) is not None
        if len(sents) >= min_sentences and not has_br:
            if tag in MUST_TAGS:
                add("문장개행", f"<{tag}> 문장 {len(sents)}개인데 <br> 없음", text, {"suggest": " ↵\n  ".join(sents) if suggest else None})
            elif tag in REVIEW_TAGS:
                add("다문장검토", f"<{tag}> 문장 {len(sents)}개 — 정보성이면 표/리스트로, 감성이면 <br>", text)
        # <br> 로 나뉜 줄 단위 검사
        lines = [re.sub(r"\s+", " ", seg).strip() for seg in kolb.strip_tags(inner).split("\n")]
        lines = [ln for ln in lines if ln]
        for j, ln in enumerate(lines):
            if j > 0 and kolb.BAD_LINE_START_RE.match(ln):
                add("줄머리", "줄이 조사·문장부호로 시작 — 앞 줄과 의미가 끊김", f"…{lines[j-1][-20:]} ⏎ {ln[:40]}")
            if len(ln) > clause_len and len(kolb.split_sentences(ln, use_kss=use_kss)) <= 1 and len(kolb.split_clauses(ln)) >= 2:
                add("절후보", f"{len(ln)}자 한 줄, 절 경계에서 분리 검토", ln, {"clauses": kolb.split_clauses(ln) if suggest else None})
        if len(lines) >= 2:
            last = lines[-1]
            if len(last.split()) == 1 and kolb._nlen(last) <= 3 and "nb" not in inner[-200:]:
                add("외톨이", "마지막 줄이 짧은 한 어절 — 앞 줄과 묶거나 nb 청킹", f"…{lines[-2][-20:]} ⏎ {last}")

    # ── 6) 기계용 텍스트 안 <br> ─────────────────────────────────────
    for m in re.finditer(r"<title>(.*?)</title>", s, re.S | re.I):
        if "<br" in m.group(1):
            add("금지위치", "<title> 안에 <br>", m.group(1))
    for m in re.finditer(r'<meta\b[^>]*content="([^"]*)"', s, re.I):
        if "<br" in m.group(1).lower():
            add("금지위치", "meta content 안에 <br>", m.group(1))
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', s, re.S | re.I):
        if "<br" in m.group(1).lower():
            add("금지위치", "JSON-LD 안에 <br> — 기계용 텍스트에는 가시 개행을 넣지 않는다")

    # ── 8) &nbsp; 남용 ───────────────────────────────────────────────
    n_nbsp = s.count("&nbsp;") + s.count(" ")
    if n_nbsp > 3 and re.search(r"[가-힣]", s):
        add("nbsp", f"&nbsp;/U+00A0 {n_nbsp}개 — 한국어 어절 붙이기는 .nb 청킹으로 (nbsp 는 keep-all 과 충돌·검색 색인 혼선)")

    issues.sort(key=lambda x: ORDER[x["kind"]])
    n_must = sum(1 for x in issues if x["must"])
    return {"file": path, "kss": kolb._load_kss() is not None, "issues": issues, "must": n_must, "review": len(issues) - n_must, "pass": n_must == 0}


def main() -> int:
    ap = argparse.ArgumentParser(description="한국어 줄바꿈 점검기 v2")
    ap.add_argument("file")
    ap.add_argument("--min-sentences", type=int, default=2)
    ap.add_argument("--clause-len", type=int, default=45)
    ap.add_argument("--nb-max", type=int, default=18, help="nb 덩어리 최대 글자 수(공백 제외). 기본 18 ≈ 390px·15px 본문 기준. 실제 넘침은 render_check.py 로")
    ap.add_argument("--suggest", action="store_true", help="미개행 블록의 문장/절 분리 제안본 출력")
    ap.add_argument("--no-kss", action="store_true", help="kss 가 있어도 정규식만 사용")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = run(a.file, a.min_sentences, a.clause_len, a.nb_max, a.suggest, use_kss=not a.no_kss)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["pass"] else 1
    if not r["issues"]:
        print(f"PASS — CSS 기본기 OK, 필수 위반 0 (문장 경계: {'kss' if r['kss'] else '정규식'})")
        return 0
    for x in r["issues"]:
        tag = "[필수]" if x["must"] else "[검토]"
        print(f"{tag} {x['kind']}: {x['msg']}" + (f"  ← {x['evidence']}…" if x["evidence"] else ""))
        if x.get("suggest"):
            print("  [제안]\n  " + x["suggest"])
        if x.get("clauses"):
            print("  [절 제안]\n  " + "\n  ".join(x["clauses"]))
    print(f"\n합계: 필수 {r['must']} · 검토 {r['review']}  (문장 경계: {'kss' if r['kss'] else '정규식'})")
    return 1 if r["must"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
