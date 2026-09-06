# -*- coding: utf-8 -*-
"""ko-linebreak 공용 모듈 — 문장 경계·절 경계·의미 청킹의 단일 구현. check.py / fix.py / render_check.py 가 공유한다.

- 문장 분리: kss(hyunwoongko/kss, 순수 파이썬 backend 'punct')가 설치돼 있으면 사용, 없으면 한국어 종결 패턴 정규식.
- 절 분리: 쉼표·연결어미(~고, ~며, ~는데, ~지만, ~라서, ~니까 …) 뒤.
- 의미 청킹(nb): 어절을 조사·어미 경계에서 덩어리로 묶는다. budoux 가 일본어에 하는 '구 단위 줄바꿈'을 한국어 규칙으로.
문구는 절대 바꾸지 않는다 — 경계 위치만 계산한다.
"""
from __future__ import annotations

import re
from typing import Iterable

# 종결 부호(+ 닫는 인용부호). "~습니다." "~해요!" "~죠?" "~네요…" "~함." 등. 숫자 사이 점(3.5)은 보호한다.
SENT_END_RE = re.compile(r"(?<=[가-힣A-Za-z0-9)\]”’\"'])([.!?…]+)")
_NUM_DOT = re.compile(r"(?<=\d)\.(?=\d)")
_PLACEHOLDER = chr(1)  # 소수점 보호용 자리표시자(제어문자, 본문에 나올 수 없음)
# 절 경계: 한글 뒤 쉼표, 또는 연결어미(휴리스틱) 뒤 공백. 파이썬 re 는 가변폭 lookbehind 를 못 써서 어미를 매치에 포함한다.
CLAUSE_RE = re.compile(
    r"[가-힣],\s+"
    r"|[가-힣](?:자마자|라서|지만|는데|면서|더니|다가|거나|려고|도록|이라|고|며|서|면|데|만|나|니|까)\s+(?=[가-힣])"
)
# 조사(어절 끝) — 강한 경계(부사격·보조사)는 덩어리가 조금만 커도 끊고,
# 약한 경계(주격·목적격·관형격)는 뒤 말과 붙어야 자연스러워 덩어리가 충분히 커야 끊는다
JOSA_STRONG_RE = re.compile(r"(?:에서|으로|에게|까지|부터|처럼|보다|마다|조차|밖에|이나|이며|이라|라고|하고|하며|로|에|와|과|도|만|든|서)$")
JOSA_WEAK_RE = re.compile(r"(?:을|를|은|는|이|가|의)$")
# 끝 글자가 조사처럼 보이지만 조사가 아닌 부사(같이·거의·굳이…) — 약한 경계로 세지 않는다
ADVERB_NOT_JOSA = {"같이", "거의", "굳이", "많이", "높이", "깊이", "멀리", "특히", "일찍이", "달리", "이미", "아니", "거기", "여기", "저기", "우리", "너희", "그러니"}
# 접속부사 — 절 '끝'이 아니라 '시작'이므로 절 경계로 세지 않는다
CONJ_ADVERBS = {"그래서", "그러나", "그러면", "그런데", "하지만", "그리고", "그러니까", "그래도", "그러므로", "어디서", "여기서", "거기서", "따라서", "게다가", "다만", "또는"}
# 줄 머리에 오면 의미가 끊기는 것들(수동 <br> 오배치 감지): 문장부호, 홀로 선 조사
BAD_LINE_START_RE = re.compile(r"^(?:[,.!?…)\]”’]|(?:에서|으로|에게|까지|부터|처럼|보다|이라|라고|로|에|의|을|를|은|는|이|가|와|과|도|만)(?=\s|$))")  # 하고/하며 는 동사(하고 싶은)일 때가 많아 제외

_kss_split = None
_KSS_TRIED = False


def _load_kss():
    """kss 가 있으면 split_sentences(backend='punct') 를 돌려준다. 없으면 None. (선택 의존성, 형태소 분석기 불필요)"""
    global _kss_split, _KSS_TRIED
    if _KSS_TRIED:
        return _kss_split
    _KSS_TRIED = True
    try:
        from kss import split_sentences as _kss  # type: ignore

        def _split(text: str) -> list[str]:
            try:
                out = _kss(text, backend="punct", strip=True)
            except TypeError:
                out = _kss(text)
            return [str(s) for s in (out if isinstance(out, list) else [out]) if str(s).strip()]

        _kss_split = _split
    except Exception:  # noqa: BLE001 - 어떤 이유로든 없으면 정규식으로
        _kss_split = None
    return _kss_split


BLOCKISH_RE = re.compile(r"</?(?:small|p|div|li|ul|ol|dl|dt|dd|h[1-6]|blockquote|figcaption|tr|td|th)\b[^>]*>", re.I)


def strip_tags(html: str) -> str:
    """태그 제거. <br> 와 블록 성격 태그(small·p·li·dd…) 경계는 개행으로 남겨 줄 단위 검사가 가능하게 한다."""
    t = re.sub(r"<br\s*/?>", "\n", html)
    t = BLOCKISH_RE.sub("\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def _nlen(t: str) -> int:
    """시각 길이 근사: 공백과 문장부호를 뺀 글자 수"""
    return len(re.sub(r"[\s,.!?…\"'”’()\[\]]", "", t))


def split_sentences(text: str, use_kss: bool = True) -> list[str]:
    """문장 목록. 공백 정규화만 하고 문구는 바꾸지 않는다."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    if not text:
        return []
    if use_kss:
        f = _load_kss()
        if f:
            try:
                out = f(text)
                if out:
                    return out
            except Exception:  # noqa: BLE001
                pass
    protected = _NUM_DOT.sub(_PLACEHOLDER, text)
    parts, last = [], 0
    for m in SENT_END_RE.finditer(protected):
        end = m.end()
        while end < len(protected) and protected[end] in "\"'”’)]":  # 닫는 인용부호 포함
            end += 1
        if end < len(protected) and not protected[end].isspace():
            continue  # 뒤에 공백이 없으면 문장 끝이 아니다 (URL 등)
        seg = protected[last:end].strip()
        if seg:
            parts.append(seg)
        last = end
    tail = protected[last:].strip()
    if tail:
        parts.append(tail)
    merged: list[str] = []  # "…" 라고 했다 — 인용 뒤 서술은 앞 문장에 붙인다
    for p in parts:
        if merged and re.match(r"^(?:이?라고|이?라는|하고|하며|고|며)(?=\s|$)", p):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return [p.replace(_PLACEHOLDER, ".") for p in merged]


def count_sentences(text: str, use_kss: bool = True) -> int:
    return len(split_sentences(text, use_kss=use_kss))


def sentence_boundaries(text: str) -> list[int]:
    """원문(공백 그대로) 기준 문장 경계 오프셋 — 종결부호(+닫는 인용부호) 바로 뒤, 뒤에 공백이 있는 자리만. 마지막 문장 끝은 제외.
    fix.py 가 이 위치에 <br> 을 넣는다. 정규식 전용(kss 는 오프셋을 돌려주지 않는다)."""
    protected = _NUM_DOT.sub(_PLACEHOLDER, text)
    out: list[int] = []
    for m in SENT_END_RE.finditer(protected):
        end = m.end()
        while end < len(protected) and protected[end] in "\"'”’)]":
            end += 1
        if end >= len(protected) or not protected[end].isspace():
            continue
        nxt = protected[end:].lstrip()
        if re.match(r"^(?:이?라고|이?라는|하고|하며|고|며)(?=\s|$)", nxt):
            continue  # "…" 라고 했다
        if nxt:
            out.append(end)
    return out


def html_text_map(inner: str) -> tuple[str, list[int]]:
    """inner HTML → (텍스트, 텍스트 각 글자의 HTML 오프셋). 태그는 건너뛰고 엔티티는 그대로 둔다."""
    text_chars: list[str] = []
    pos: list[int] = []
    for m in re.finditer(r"<[^>]+>|[^<]+", inner):
        seg = m.group(0)
        if seg.startswith("<"):
            continue
        for k, ch in enumerate(seg):
            text_chars.append(ch)
            pos.append(m.start() + k)
    return "".join(text_chars), pos


def split_clauses(sentence: str) -> list[str]:
    """절 후보 분리: 쉼표·연결어미 뒤. 결과를 공백 1개로 이어 붙이면 원문과 같다(문구 불변)."""
    parts, last = [], 0
    for m in CLAUSE_RE.finditer(sentence):
        parts.append(sentence[last:m.end()].rstrip())
        last = m.end()
    parts.append(sentence[last:].strip())
    parts = [p for p in parts if p]
    out: list[str] = []
    for p in parts:
        if out and (out[-1] in CONJ_ADVERBS or _nlen(out[-1]) < 4):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


def chunk_phrases(text: str, max_len: int = 12, min_len: int = 6, weak_len: int = 8) -> list[str]:
    """어절을 의미 덩어리로 묶는다(길이는 공백 제외 글자 수).
    - 쉼표 뒤·강한 조사(에서·으로·에·와·도…) 뒤: 덩어리가 min_len 이상이면 끊는다
    - 약한 조사(을·를·은·는·이·가·의) 뒤: 뒤 말과 붙는 게 자연스러워 weak_len 이상일 때만 끊는다
    - max_len 을 넘기기 직전에는 무조건 끊는다
    - 마지막 덩어리가 외톨이(min_len 미만)면 앞 덩어리와 합친다"""
    words = text.split()
    chunks: list[str] = []
    cur: list[str] = []

    def flush():
        if cur:
            chunks.append(" ".join(cur))
            cur.clear()

    numeric = re.compile(r"^\d[\d,.]*[가-힣A-Za-z%]{0,3}$")  # 16년 · 28,000원 · 10ea — 뒤 명사와 떨어지면 어색
    for i, w in enumerate(words):
        if cur and _nlen(" ".join(cur + [w])) > max_len:
            if len(cur) > 1 and numeric.match(cur[-1]):
                carry = cur.pop()  # 숫자 어절은 다음 덩어리로 넘겨 뒤 명사와 붙인다
                flush()
                cur.append(carry)
            else:
                flush()
        cur.append(w)
        if i + 1 >= len(words):
            break
        if numeric.match(w):
            continue  # 숫자 어절 뒤에서는 끊지 않는다
        core = re.sub(r"[,.!?…\"'”’)]+$", "", w)
        cur_len = _nlen(" ".join(cur))
        strong = w.endswith(",") or bool(JOSA_STRONG_RE.search(core))
        weak = bool(JOSA_WEAK_RE.search(core)) and core not in ADVERB_NOT_JOSA
        if (strong and cur_len >= min_len) or (weak and cur_len >= weak_len):
            flush()
    flush()
    if len(chunks) >= 2 and _nlen(chunks[-1]) < min_len and _nlen(chunks[-2] + chunks[-1]) <= max_len + 3:
        chunks[-2:] = [chunks[-2] + " " + chunks[-1]]
    return chunks


def iter_display_blocks(html: str, tags: Iterable[str] = ("p", "figcaption", "summary", "dd", "li", "small", "h1", "h2", "h3", "blockquote", "td")):
    """디스플레이성 블록 (tag, attrs, inner, start, end). 태그별로 따로 훑어 <dd> 안의 <small> 처럼 중첩된 블록도 잡는다.
    같은 태그가 중첩되면(p 안의 p) lazy 매칭이라 안쪽만 잡힌다."""
    found = []
    for tag in tags:
        pat = re.compile(r"<(%s)\b([^>]*)>(.*?)</\1>" % tag, re.S | re.I)
        for m in pat.finditer(html):
            inner = m.group(3)
            if "<script" in inner or "<style" in inner or len(inner) > 4000:
                continue
            found.append((m.start(), m.group(1).lower(), m.group(2), inner, m.end()))
    for start, tag, attrs, inner, end in sorted(found):
        yield tag, attrs, inner, start, end
