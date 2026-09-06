# -*- coding: utf-8 -*-
"""ko-linebreak 회귀 테스트 (표준 라이브러리만). 실행: py -3 -m unittest discover -s tests -v"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kolb  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "sample_bad.html"


class SentenceSplit(unittest.TestCase):
    def test_basic_endings(self):
        t = "첫 문장입니다. 둘째 문장이에요! 셋째는 어때요? 넷째네요…"
        self.assertEqual(4, len(kolb.split_sentences(t, use_kss=False)))

    def test_decimal_and_phone_not_split(self):
        t = "가격은 3.5만 원부터. 문의는 010-0000-0000 으로 주세요."
        self.assertEqual(["가격은 3.5만 원부터.", "문의는 010-0000-0000 으로 주세요."], kolb.split_sentences(t, use_kss=False))

    def test_quote_then_speech_verb_merges(self):
        t = '"네." 라고 했다. 그리고 갔다.'
        self.assertEqual(['"네." 라고 했다.', "그리고 갔다."], kolb.split_sentences(t, use_kss=False))

    def test_quoted_sentence_end(self):
        t = '가장 많이 남긴 말이 "원하는 디자인을 잘해줘요"예요. 증거를 모았습니다.'
        self.assertEqual(2, len(kolb.split_sentences(t, use_kss=False)))

    def test_boundaries_offsets_point_at_space(self):
        t = "첫 문장입니다. 둘째 문장이에요."
        offs = kolb.sentence_boundaries(t)
        self.assertEqual([8], offs)
        self.assertEqual(" ", t[offs[0]])


class ClauseSplit(unittest.TestCase):
    def test_comma_and_connective(self):
        t = "그런데도 가게가 돌아가는 건, 다녀간 분들이 곁의 사람을 한 명씩 데려와 주셨고 그래서 계속됩니다."
        parts = kolb.split_clauses(t)
        self.assertEqual("그런데도 가게가 돌아가는 건,", parts[0])
        self.assertTrue(parts[-1].startswith("그래서"), parts)  # 접속부사는 뒷절 머리에 붙는다
        self.assertEqual(t, " ".join(parts))  # 문구 불변


class Chunking(unittest.TestCase):
    """사용자가 손으로 확정한 덩어리와 일치해야 한다 (2026-09 네일샵 홈페이지 조판)."""

    def test_hero_lede(self):
        self.assertEqual(["반월당역 지하상가에서", "예약제로 문을 여는", "네일샵이에요."],
                         kolb.chunk_phrases("반월당역 지하상가에서 예약제로 문을 여는 네일샵이에요."))

    def test_lede_two_lines(self):
        self.assertEqual(["손톱연장도 자석네일도,", "결국 하는 일은 하나예요."], kolb.chunk_phrases("손톱연장도 자석네일도, 결국 하는 일은 하나예요."))
        self.assertEqual(["원하는 디자인을 같이 찾아서,", "그대로 만들어드리는 것."], kolb.chunk_phrases("원하는 디자인을 같이 찾아서, 그대로 만들어드리는 것."))

    def test_numeric_stays_with_noun(self):
        chunks = kolb.chunk_phrases("네일 자격증을 가진 16년 경력의 음윤혜 원장이 직접 시술하고, 21개 전 메뉴 가격을 공개합니다.")
        joined = " | ".join(chunks)
        self.assertIn("16년 경력의", joined)
        self.assertIn("21개 전 메뉴", joined)
        self.assertEqual("네일 자격증을 가진 16년 경력의 음윤혜 원장이 직접 시술하고, 21개 전 메뉴 가격을 공개합니다.", " ".join(chunks))

    def test_no_orphan_tail(self):
        chunks = kolb.chunk_phrases("손톱이라는 작은 도화지에, 행복을 만들어드립니다")
        self.assertTrue(all(kolb._nlen(c) >= 4 for c in chunks), chunks)


class CheckCLI(unittest.TestCase):
    def run_check(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "check.py"), str(FIX), *args], capture_output=True, text=True, encoding="utf-8")

    def test_fixture_fails_with_expected_kinds(self):
        r = self.run_check()
        self.assertEqual(1, r.returncode)
        for kind in ("CSS", "문장개행", "줄머리", "절후보", "다문장검토"):
            self.assertIn(kind, r.stdout, kind)
        self.assertNotIn("<title>", r.stdout)  # title·JSON-LD 의 두 문장은 건드리지 않는다

    def test_json_output(self):
        r = self.run_check("--json")
        import json
        j = json.loads(r.stdout)
        self.assertFalse(j["pass"])
        self.assertGreaterEqual(j["must"], 5)


class FixCLI(unittest.TestCase):
    def test_fix_preview_keeps_words_and_adds_breaks(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fix.py"), str(FIX), "--sentences", "--clauses", "40", "--nb", "h1,.lede", "--css"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("[문장]", r.stdout)
        self.assertIn("[절]", r.stdout)
        self.assertIn("[nb] <h1>", r.stdout)
        self.assertIn("[css]", r.stdout)
        self.assertIn('<span class="nb">반월당역 지하상가에서</span>', r.stdout)
        self.assertIn("가격은 3.5만 원부터 시작합니다.<br>", r.stdout)
        self.assertNotIn("bak.kolb", r.stdout)  # 미리보기는 파일을 바꾸지 않는다
        self.assertTrue(FIX.read_text(encoding="utf-8").count("<br>") == 2)

    def test_fix_then_check_passes(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "x.html"
            shutil.copy(FIX, tmp)
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fix.py"), str(tmp), "--sentences", "--css", "--write"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, r.returncode, r.stdout)
            self.assertTrue(any(p.name.startswith("x.html.bak.kolb_") for p in Path(d).iterdir()))
            r2 = subprocess.run([sys.executable, str(ROOT / "scripts" / "check.py"), str(tmp), "--json"], capture_output=True, text=True, encoding="utf-8")
            import json
            j = json.loads(r2.stdout)
            kinds = {x["kind"] for x in j["issues"] if x["must"]}
            self.assertEqual({"줄머리"}, kinds, j["issues"])  # 수동 <br> 오배치만 남는다(사람 판단)


if __name__ == "__main__":
    unittest.main()
