# ko-linebreak

한국어 문서·웹페이지·PPT의 **줄바꿈 교정** 도구이자 [Claude Code](https://claude.com/claude-code) 스킬.

"기록입니/다"처럼 단어 중간에서 꺾이는 줄바꿈, 마지막 줄에 한 글자만 남는 외톨이,
"문을 / 여는"처럼 의미와 무관하게 갈리는 줄 — 브라우저와 문서 도구의 기본값이 한국어를 글자 단위로 꺾기 때문에 생기는 문제를 4단계로 잡는다.

핵심 원칙 둘: **줄바꿈 작업에서 문구는 절대 수정하지 않는다**(개행 위치만 바꾼다). **입력 원문의 개행은 조판 의도**다(문단으로 합치지 않는다).

## 4단계 규칙

| 단계 | 무엇을 | 어떻게 |
|---|---|---|
| 1 CSS 기본기 | 어절 단위 줄바꿈·외톨이 방지 | `body{word-break:keep-all;overflow-wrap:break-word}` `p,li,dd,…{text-wrap:pretty}` `h1,h2,h3{text-wrap:balance}` `<html lang="ko">` |
| 2 문장 단위 | 소개문·캡션·FAQ·감성 문단 | 문장 경계마다 `<br>`(웹) / 개행(문서·PPT) |
| 3 절 단위 | 긴 문장 | 쉼표·연결어미("~하는 건,", "~했고,") 뒤에서 한 번 더 |
| 4 의미 청킹 | 좁은 화면에서 다시 접히는 히어로·리드 | 의미 덩어리를 `<span class="nb">`(`white-space:nowrap`)로 묶어 덩어리 사이에서만 꺾이게 |

```
그런데도 가게가 돌아가는 건,
다녀간 분들이 곁의 사람을 한 명씩 데려와 주신 덕분입니다.
```
```html
<span class="nb">반월당역 지하상가에서</span> <span class="nb">예약제로 문을 여는</span> <span class="nb">네일샵이에요.</span>
```

## 도구 3종 (v2, 표준 라이브러리만 · Python 3.10+)

```bash
python scripts/check.py 파일.html [--suggest] [--json]        # 정적 점검 — exit 1 = 필수 위반
python scripts/fix.py   파일.html --sentences --clauses 45 --nb "h1,.lede" --css [--write]   # 자동 적용(미리보기 diff → --write 로 백업 후 적용)
python scripts/render_check.py 파일.html|URL --widths 390,768,1280 [--outline shot.png] [--font-scale 1.25]   # Chromium 실측
```

| 도구 | 잡는 것 |
|---|---|
| `check.py` | CSS 기본기 누락(keep-all·overflow-wrap·text-wrap·lang·.nb 정의) · 문장 2개+ 인데 개행 없는 블록 · `<br>` 뒤 줄이 조사/부호로 시작(의미 끊김) · 기계용 텍스트(title·meta·JSON-LD) 안 `<br>` · [검토] nb 덩어리 길이·절 분리 후보·외톨이·`&nbsp;` 남용·목록/제목의 다문장 |
| `fix.py` | 문장 경계 `<br>` · 긴 한 문장의 절 경계 `<br>` 하나 · 지정 요소의 의미 청킹 `<span class="nb">` · 1단계 CSS 주입. **적용 전 순수 텍스트 동일성 검증**, 실패 시 중단. 소수점(3.5)·전화번호·인용 뒤 "라고 했다" 보호 |
| `render_check.py` | 실제 렌더에서 **어절 중간 꺾임** · **nb 덩어리 갈림/넘침** · 요소 가로 넘침(필수) · 자동 wrap 으로 조사가 줄머리에 옴 · 외톨이(검토). `--outline` 은 nb 경계(점선)·`<br>`(⏎)를 표시한 스크린샷 |

문장 경계는 [hyunwoongko/kss](https://github.com/hyunwoongko/kss)가 설치돼 있으면 자동으로 쓰고(`pip install kss`, 순수 파이썬 backend), 없으면 내장 정규식(종결부호+닫는 인용부호, 소수점·URL 보호)으로 동작한다. `render_check.py` 만 [Playwright](https://playwright.dev/python/) 가 필요하다.

### 청킹 규칙 (`kolb.chunk_phrases`)

어절을 조사·어미 경계에서 덩어리로 묶는다. 쉼표·강한 조사(에서·으로·에·와·도·까지…) 뒤는 6자 이상이면 끊고, 약한 조사(을·를·은·는·이·가·의) 뒤는 8자 이상일 때만 끊는다(뒤 말과 붙는 게 자연스럽다). 숫자 어절(16년·28,000원)은 뒤 명사와 붙이고, 끝 글자만 조사처럼 보이는 부사(같이·거의·굳이)는 경계로 세지 않는다. 최장 12자(공백·부호 제외), 외톨이 꼬리는 앞 덩어리와 합친다. 사용자가 손으로 확정한 조판 예시가 테스트다(`tests/test_kolb.py`).

## Claude Code 스킬로 쓰기

```bash
git clone https://github.com/jsk7767/ko-linebreak "$HOME/.claude/skills/ko-linebreak"
```

이후 세션에서 `/ko-linebreak` 또는 "줄바꿈 정리해줘"로 호출. `SKILL.md`에 의도 파악 규칙, 적용 절차, HTML·Markdown·PPTX·DOCX별 방법, 실측에서 나온 함정이 있다.

## 왜 이 도구가 필요한가 — 관련 프로젝트

- [google/budoux](https://github.com/google/budoux) (Chrome `word-break: auto-phrase`) — 일본어·중국어·태국어 구 단위 줄바꿈 모델. **한국어 모델은 없다**(2026-09 확인). 한국어는 공백이 있어 keep-all 로 "어디서 끊어도 되는가"는 풀리지만, "어디서 끊어야 읽기 좋은가"는 남는다 — `chunk_phrases` 가 그 자리를 규칙으로 채운다. budoux-extension 의 '구 경계 가시화' 아이디어는 `render_check.py --outline` 으로 가져왔다.
- [hyunwoongko/kss](https://github.com/hyunwoongko/kss) — 한국어 문장 분리. 있으면 자동 사용.
- [adobe/balance-text](https://github.com/adobe/balance-text) · [nytimes/text-balancer](https://github.com/nytimes/text-balancer) — `text-wrap: balance` 미지원 브라우저용 JS 폴백. `text-wrap: pretty/balance` 지원은 브라우저마다 다르니 [caniuse](https://caniuse.com/?search=text-wrap) 를 확인하고, 미지원 환경의 외톨이 통제는 nb 청킹으로.

## 테스트

```bash
python -m unittest discover -s tests -v
```

## License

MIT
