# ko-linebreak

한국어 문서·웹페이지·PPT의 **줄바꿈 교정** 도구이자 [Claude Code](https://claude.com/claude-code) 스킬.

"기록입니/다"처럼 단어 중간에서 꺾이는 줄바꿈, 마지막 줄에 한 글자만 남는 외톨이,
의미와 무관하게 갈리는 줄 — 브라우저와 문서 도구의 기본값이 한국어를 글자 단위로 꺾기 때문에 생기는 문제를 3단계로 잡는다.

## 3단계 규칙

**1단계 — CSS 기본기** (웹, 기계적)
```css
body{word-break:keep-all;overflow-wrap:break-word}
p,li,dd,dt,figcaption,summary,small,span{text-wrap:pretty}
h1,h2,h3{text-wrap:balance}
```

**2단계 — 문장 단위 개행**: 소개문·캡션·FAQ·감성 문단은 자동 wrap에 맡기지 않고 문장 경계에서 끊는다.

**3단계 — 절 단위 호흡**: 긴 문장은 쉼표·연결어미("~하는 건,", "~했고,") 뒤에서 한 번 더.

```
그런데도 가게가 돌아가는 건,
다녀간 분들이 곁의 사람을 한 명씩 데려와 주신 덕분입니다.
```

핵심 원칙: **줄바꿈 작업에서 문구는 절대 수정하지 않는다** — 개행 위치만 바꾼다.
그리고 **입력 원문에 이미 있는 개행은 조판 의도**이므로 문단으로 합치지 않는다.

## 점검기

```bash
python scripts/check.py 파일.html            # CSS 누락·미개행 블록·절 분리 후보 리포트
python scripts/check.py 파일.html --suggest  # 문장 단위 개행 제안본까지 출력
```

exit 0 = 필수 위반 없음. `[검토]`(절 분리 후보)는 판단 영역이라 verdict에 포함하지 않는다.

## Claude Code 스킬로 쓰기

```bash
git clone https://github.com/jsk7767/ko-linebreak "$HOME/.claude/skills/ko-linebreak"
```

이후 세션에서 `/ko-linebreak` 또는 "줄바꿈 정리해줘"로 호출. `SKILL.md`에 적용 절차와
HTML·Markdown·PPTX·DOCX별 방법이 들어 있다.

## 왜 라이브러리가 없나

[google/budoux](https://github.com/google/budoux)(Chrome의 `word-break: auto-phrase`)는 일본어·중국어·태국어용이고,
한국어는 공백이 있어 keep-all로 충분하다는 입장이라 모델이 없다. 하지만 keep-all은 "어디서 끊어도 되는가"만 해결할 뿐,
"어디서 끊어야 읽기 좋은가"(문장·절 단위 조판)는 판단의 영역이라 도구가 없었다 — 이 스킬이 그 빈자리를 채운다.

## License

MIT
