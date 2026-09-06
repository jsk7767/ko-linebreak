# -*- coding: utf-8 -*-
"""렌더 실측 점검기 — Chromium(Playwright)으로 실제로 어디서 줄이 꺾이는지 잰다. 정적 점검(check.py)이 못 보는 것:
  · 어절 중간 꺾임(keep-all 누락·overflow-wrap:anywhere 부작용)            → 필수
  · .nb 덩어리가 두 줄로 갈림 / 덩어리가 상자를 넘침(가로 overflow)        → 필수
  · 자동 wrap 으로 조사·문장부호가 줄머리에 옴("문을/여는" 류 의미 파괴)      → 검토 (nb 청킹 대상)
  · 마지막 줄 외톨이(한 어절 ≤3자)                                        → 검토
사용: py -3 render_check.py FILE.html|URL [--widths 390,768,1280] [--font-scale 1] [--outline OUT.png] [--json]
설치: py -3 -m pip install playwright && py -3 -m playwright install chromium
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kolb  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BLOCK_SEL = "p, h1, h2, h3, dd, dt, small, figcaption, li, summary, blockquote, td"

JS_LINES = r"""(sel) => {
  const out = [];
  const els = Array.from(document.querySelectorAll(sel)).filter(e => e.offsetParent !== null || e.tagName === 'SUMMARY');
  let idx = 0;
  for (const el of els) {
    if (idx > 400) break;
    const text = (el.innerText || '').trim();
    if (!/[가-힣]/.test(text) || text.length < 4) continue;
    // 글자 단위 위치 → 줄 재구성
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const lines = [];  // {top, chars:[{ch, node, i}]}
    let node; let midBreaks = [];
    while ((node = walker.nextNode())) {
      const s = node.nodeValue; if (!s.trim()) continue;
      if (node.parentElement && node.parentElement.closest('script,style')) continue;
      let prevTop = null, prevCh = null;
      for (let i = 0; i < s.length; i++) {
        const ch = s[i]; if (ch === '\n') continue;
        const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + 1);
        const rects = r.getClientRects(); if (!rects.length) continue;
        const top = Math.round(rects[0].top);
        let line = lines.find(l => Math.abs(l.top - top) <= 3);
        if (!line) { line = {top, text: ''}; lines.push(line); }
        line.text += ch;
        // 같은 텍스트 노드 안에서 공백 없이 줄이 바뀌면 어절 중간 꺾임
        if (prevTop !== null && top !== prevTop && prevCh !== ' ' && ch !== ' ' && /[가-힣A-Za-z0-9]/.test(prevCh) && /[가-힣A-Za-z0-9]/.test(ch)) {
          midBreaks.push(s.slice(Math.max(0, i - 6), i) + '|' + s.slice(i, i + 6));
        }
        prevTop = top; prevCh = ch;
      }
    }
    lines.sort((a, b) => a.top - b.top);
    // nb 덩어리 갈림·넘침
    const nbBroken = [], nbOverflow = [];
    for (const nb of el.querySelectorAll('.nb')) {
      const rs = Array.from(nb.getClientRects());
      // 인라인 자식(<em> 등) 때문에 rect 가 여러 개일 수 있다 — 세로 위치가 다른 rect 가 있을 때만 '갈림'
      const tops = new Set(rs.map(r => Math.round(r.top / 4)));
      if (tops.size > 1) nbBroken.push(nb.innerText.trim().slice(0, 40));
      const pr = el.getBoundingClientRect(); const nr = nb.getBoundingClientRect();
      if (nr.right > pr.right + 1) nbOverflow.push(nb.innerText.trim().slice(0, 40));
    }
    const overflow = el.scrollWidth > el.clientWidth + 1;
    out.push({idx: idx++, tag: el.tagName.toLowerCase(), cls: (el.className || '').toString().slice(0, 40),
              lines: lines.map(l => l.text.trim()).filter(Boolean), midBreaks, nbBroken, nbOverflow, overflow});
  }
  return out;
}"""

OUTLINE_CSS = ".nb{outline:1px dashed rgba(220,60,120,.8);outline-offset:1px} br::after{content:'⏎';color:rgba(60,120,220,.7);font-size:.7em}"


async def run(target: str, widths: list[int], font_scale: float, outline: str | None):
    from playwright.async_api import async_playwright  # type: ignore

    url = target if re.match(r"^https?://", target) else Path(target).resolve().as_uri()
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for w in widths:
            page = await browser.new_page(viewport={"width": w, "height": 900}, device_scale_factor=1)
            await page.goto(url, wait_until="load")
            await page.wait_for_timeout(500)
            if font_scale != 1:
                await page.add_style_tag(content=f"html{{font-size:{font_scale * 100:.0f}%}}")
            data = await page.evaluate(JS_LINES, BLOCK_SEL)
            results[w] = data
            if outline:
                await page.add_style_tag(content=OUTLINE_CSS)
                await page.screenshot(path=str(Path(outline).with_name(f"{Path(outline).stem}_{w}{Path(outline).suffix or '.png'}")), full_page=True)
            await page.close()
        await browser.close()
    return results


def analyze(results: dict) -> dict:
    issues = []
    for w, blocks in results.items():
        for b in blocks:
            where = f"{w}px <{b['tag']}{'.' + b['cls'].split()[0] if b['cls'] else ''}>"
            for mb in b["midBreaks"]:
                issues.append({"must": True, "kind": "어절중간", "w": w, "msg": f"{where} 어절 중간에서 꺾임", "evidence": mb})
            for nb in b["nbBroken"]:
                issues.append({"must": True, "kind": "nb갈림", "w": w, "msg": f"{where} nb 덩어리가 두 줄로 갈림 (nowrap 누락 또는 상위 너비 제한)", "evidence": nb})
            for nb in b["nbOverflow"]:
                issues.append({"must": True, "kind": "nb넘침", "w": w, "msg": f"{where} nb 덩어리가 상자를 넘침 — 덩어리를 더 잘게", "evidence": nb})
            if b["overflow"]:
                issues.append({"must": True, "kind": "가로넘침", "w": w, "msg": f"{where} 요소 가로 넘침(scrollWidth > clientWidth)", "evidence": (b["lines"] or [""])[0][:40]})
            lines = b["lines"]
            for j in range(1, len(lines)):
                if kolb.BAD_LINE_START_RE.match(lines[j]):
                    issues.append({"must": False, "kind": "줄머리", "w": w, "msg": f"{where} 자동 wrap 으로 조사·부호가 줄머리에 옴 → nb 청킹 대상", "evidence": f"…{lines[j-1][-14:]} ⏎ {lines[j][:16]}"})
            if len(lines) >= 2:
                last = lines[-1]
                if len(last.split()) == 1 and kolb._nlen(last) <= 3:
                    issues.append({"must": False, "kind": "외톨이", "w": w, "msg": f"{where} 마지막 줄 외톨이", "evidence": f"…{lines[-2][-14:]} ⏎ {last}"})
    n_must = sum(1 for x in issues if x["must"])
    return {"issues": issues, "must": n_must, "review": len(issues) - n_must, "pass": n_must == 0,
            "blocks": {str(w): len(v) for w, v in results.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description="한국어 줄바꿈 렌더 실측 점검기")
    ap.add_argument("target", help="HTML 파일 경로 또는 URL")
    ap.add_argument("--widths", default="390,768,1280")
    ap.add_argument("--font-scale", type=float, default=1.0, help="html font-size 배율 (접근성 큰 글씨 시뮬레이션, 예: 1.25)")
    ap.add_argument("--outline", help="nb 경계·<br> 를 표시한 전체 스크린샷 저장 경로(너비별 접미어 붙음)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    widths = [int(x) for x in a.widths.split(",") if x.strip()]
    try:
        results = asyncio.run(run(a.target, widths, a.font_scale, a.outline))
    except ImportError:
        print("playwright 가 없습니다: py -3 -m pip install playwright && py -3 -m playwright install chromium")
        return 2
    rep = analyze(results)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if rep["pass"] else 1
    if not rep["issues"]:
        print(f"PASS — 어절 중간 꺾임 0 · nb 갈림/넘침 0 · 가로 넘침 0  (블록 {rep['blocks']})")
        return 0
    for x in rep["issues"]:
        print(f"{'[필수]' if x['must'] else '[검토]'} {x['kind']}: {x['msg']}  ← {x['evidence']}")
    print(f"\n합계: 필수 {rep['must']} · 검토 {rep['review']}  (블록 {rep['blocks']})")
    return 1 if rep["must"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
