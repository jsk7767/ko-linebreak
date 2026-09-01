# -*- coding: utf-8 -*-
"""한국어 줄바꿈 점검기. 사용: py -3 check.py FILE.html [--min-sentences 2]"""
import sys, re, argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--min-sentences", type=int, default=2)
ap.add_argument("--clause-len", type=int, default=45)
ap.add_argument("--suggest", action="store_true", help="미개행 블록의 문장 단위 개행 제안본 출력")
a = ap.parse_args()

s = open(a.file, encoding="utf-8").read()
issues = []

# 1) CSS 기본기
css_checks = [
    ("word-break:keep-all", "body에 word-break:keep-all 누락 — 단어 중간 꺾임 발생"),
    ("text-wrap:pretty", "text-wrap:pretty 누락 — 외톨이 글자 위험"),
    ("text-wrap:balance", "제목 text-wrap:balance 누락"),
]
for needle, msg in css_checks:
    if needle.replace(":", ": ") not in s and needle not in s:
        issues.append(("CSS", msg, ""))

# 2) 문장 단위 개행: 디스플레이성 블록에서 문장 2개+인데 <br> 없음
SENT_END = re.compile(r"[다요죠까네]\.")
BLOCK = re.compile(r"<(p|figcaption|summary|dd)\b[^>]*>(.*?)</\1>", re.S)
for m in BLOCK.finditer(s):
    inner = m.group(2)
    if "<script" in inner or len(inner) > 2000:
        continue
    text = re.sub(r"<[^>]+>", " ", inner)
    text = re.sub(r"\s+", " ", text).strip()
    n_sent = len(SENT_END.findall(text + " "))
    # <br> 또는 pre-line용 수동 개행(개행 직후 들여쓰기 없이 본문이 이어짐)을 개행으로 인정
    has_br = "<br" in inner or re.search(r"\n(?=\S)", inner.strip()) is not None
    if n_sent >= a.min_sentences and not has_br:
        issues.append(("문장개행", f"문장 {n_sent}개인데 <br> 없음", text[:70]))
        if a.suggest:
            # 문장 종결 뒤에 개행 제안 (↵ 표시) — 문구 불변, 위치만 제안
            prop = re.sub(r"([다요죠까네]\.)\s+", r"\1 ↵\n  ", text)
            print("  [제안]\n  " + prop)

# 3) 절 단위 후보: <br> 사이/블록 내 한 줄이 길고 쉼표 포함
for m in BLOCK.finditer(s):
    inner = m.group(2)
    if "<script" in inner:
        continue
    for seg in re.split(r"<br\s*/?>", inner):
        t = re.sub(r"<[^>]+>", " ", seg)
        t = re.sub(r"\s+", " ", t).strip()
        # 문장 1개 & 길이 초과 & 쉼표 존재 -> 절 분리 후보
        if t and len(t) > a.clause_len and ", " in t.replace("·", "") and len(SENT_END.findall(t + " ")) <= 1:
            issues.append(("절후보", f"{len(t)}자 한 줄, 쉼표에서 분리 검토", t[:70]))

if not issues:
    print("PASS — CSS 기본기 OK, 미개행 블록 0")
else:
    order = {"CSS": 0, "문장개행": 1, "절후보": 2}
    for kind, msg, ev in sorted(issues, key=lambda x: order[x[0]]):
        tag = {"CSS": "[필수]", "문장개행": "[필수]", "절후보": "[검토]"}[kind]
        print(f"{tag} {kind}: {msg}" + (f"  ← {ev}…" if ev else ""))
    n_must = sum(1 for k, _, _ in issues if k != "절후보")
    print(f"\n합계: 필수 {n_must} · 검토 {len(issues) - n_must}")
    sys.exit(1 if n_must else 0)
