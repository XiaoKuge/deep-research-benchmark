"""第五阶段评委提示词存档：从会话记录取出提示词、逐字比对，以及存档内容是否齐全。

运行：python3 -I -m unittest discover -s tests -v
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "judge_prompts.py")

# 一段带中文、反引号、空行、行尾空格、结尾没有换行的提示词，用来检验"不改一字"
PROMPT_ONE = (
    "你在一项小规模检验中担任评委。\n"
    "\n"
    "工作目录：/Users/someone/research-plan  \n"
    "输出写到 `stage5-pilot/out/rating-opus-1.json`，必须是合法的 JSON。\n"
    "{\"judge\":\"opus-1\",\"reports\":{\"A\":{…}}}\n"
    "最后只回复一句话。"
)
PROMPT_TWO = "你负责重核 15 条断言。\n| id | 报告 |\n|---|---|\n| E-c2 | E.md |"


def agent_call(tool_id, description, prompt, model=None):
    data = {"description": description, "prompt": prompt}
    if model:
        data["model"] = model
    return {"type": "tool_use", "id": tool_id, "name": "Agent", "input": data}


def write_fixture(tmp):
    """在临时目录里造一份小会话记录和一个试评目录，返回 (会话记录路径, 评委目录)。"""
    transcript = os.path.join(tmp, "session.jsonl")
    lines = [
        {"type": "user", "timestamp": "2026-10-29T22:20:00.000Z",
         "message": {"role": "user", "content": "开始试评"}},
        {"type": "assistant", "timestamp": "2026-10-29T22:23:41.976Z",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "派出评委"},
             agent_call("toolu_ONE", "Rating run opus 1", PROMPT_ONE)]}},
        # 同一条调用的第二份副本，没有时间戳
        {"type": "api-request-blob",
         "message": {"role": "user", "content": [
             agent_call("toolu_ONE", "Rating run opus 1", PROMPT_ONE)]}},
        {"type": "assistant", "timestamp": "2026-10-29T22:42:45.566Z",
         "message": {"role": "assistant", "content": [
             agent_call("toolu_TWO", "Re-verify 15 claims with sonnet", PROMPT_TWO, "sonnet")]}},
    ]
    with open(transcript, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    pilot = os.path.join(tmp, "stage5-pilot")
    judges = os.path.join(pilot, "judges")
    os.makedirs(os.path.join(pilot, "out"))
    os.makedirs(judges)
    manifest = {
        "transcript": transcript,
        "runs": [
            {"output": "out/rating-opus-1.json", "prompt": "judges/prompts/rating-opus-1.txt",
             "description": "Rating run opus 1", "tool_use_id": "toolu_ONE",
             "model_requested": None, "dispatched_at": "2026-10-29T22:23:41.976Z",
             "date": "2026-10-29"},
            {"output": "out/verify-sonnet-subset.json",
             "prompt": "judges/prompts/verify-sonnet-subset.txt",
             "description": "Re-verify 15 claims with sonnet", "tool_use_id": "toolu_TWO",
             "model_requested": "sonnet", "dispatched_at": "2026-10-29T22:42:45.566Z",
             "date": "2026-10-29"},
        ],
    }
    with open(os.path.join(judges, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return transcript, judges


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", TOOL, *args],
                          capture_output=True, text=True, encoding="utf-8")


class ExtractFromTranscript(unittest.TestCase):
    def test_extract_writes_each_prompt_exactly_as_in_the_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript, judges = write_fixture(tmp)
            result = run_tool("extract", "--transcript", transcript, "--judges", judges)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(os.path.join(judges, "prompts", "rating-opus-1.txt"), "rb") as f:
                self.assertEqual(f.read(), PROMPT_ONE.encode("utf-8"))
            with open(os.path.join(judges, "prompts", "verify-sonnet-subset.txt"), "rb") as f:
                self.assertEqual(f.read(), PROMPT_TWO.encode("utf-8"))


class CheckAgainstTranscript(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.transcript, self.judges = write_fixture(self._tmp.name)
        run_tool("extract", "--transcript", self.transcript, "--judges", self.judges)

    def tearDown(self):
        self._tmp.cleanup()

    def check(self):
        return run_tool("check", "--transcript", self.transcript, "--judges", self.judges)

    def test_check_passes_when_saved_prompts_match(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_fails_and_names_the_file_when_one_character_differs(self):
        path = os.path.join(self.judges, "prompts", "rating-opus-1.txt")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(PROMPT_ONE.replace("评委", "评审", 1))
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("rating-opus-1.txt", result.stdout)

    def edit_manifest(self, index, **changes):
        path = os.path.join(self.judges, "manifest.json")
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["runs"][index].update(changes)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

    def test_check_fails_when_the_manifest_names_the_wrong_model(self):
        # 会话记录里第二次运行指定了 sonnet，清单却写成未指定
        self.edit_manifest(1, model_requested=None)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify-sonnet-subset", result.stdout)

    def test_check_fails_when_the_manifest_names_the_wrong_date(self):
        self.edit_manifest(0, date="2026-10-30")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("rating-opus-1", result.stdout)

    def test_check_fails_when_a_run_is_missing_from_the_transcript(self):
        self.edit_manifest(0, tool_use_id="toolu_NOT_THERE")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("rating-opus-1", result.stdout)


class ActualModelFromJudgeTranscript(unittest.TestCase):
    """评委实际用的模型只记在评委自己的会话记录里（会话记录旁的 subagents/ 目录）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.transcript, self.judges = write_fixture(self._tmp.name)
        run_tool("extract", "--transcript", self.transcript, "--judges", self.judges)
        sub = os.path.join(self._tmp.name, "session", "subagents")
        os.makedirs(sub)
        for name, tool_id, model in [("agent-one", "toolu_ONE", "claude-opus-5-5"),
                                     ("agent-two", "toolu_TWO", "claude-sonnet-5-5")]:
            with open(os.path.join(sub, name + ".meta.json"), "w", encoding="utf-8") as f:
                json.dump({"toolUseId": tool_id, "description": "x"}, f)
            with open(os.path.join(sub, name + ".jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
                f.write(json.dumps({"type": "assistant", "message": {
                    "role": "assistant", "model": model, "content": []}}) + "\n")

    def tearDown(self):
        self._tmp.cleanup()

    def set_models(self, first, second):
        path = os.path.join(self.judges, "manifest.json")
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["runs"][0]["model"] = first
        manifest["runs"][1]["model"] = second
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

    def check(self):
        return run_tool("check", "--transcript", self.transcript, "--judges", self.judges)

    def test_check_passes_when_the_manifest_names_the_model_each_judge_ran_on(self):
        self.set_models("claude-opus-5-5", "claude-sonnet-5-5")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_fails_when_the_manifest_names_another_model(self):
        self.set_models("claude-opus-5-5", "claude-opus-5-5")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify-sonnet-subset", result.stdout)


PILOT = os.path.join(ROOT, "research-plan", "stage5-pilot")
JUDGES = os.path.join(PILOT, "judges")


def load_real_manifest():
    with open(os.path.join(JUDGES, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


class ManifestCoversEveryOutputFile(unittest.TestCase):
    def test_every_file_under_out_has_exactly_one_entry(self):
        listed = [run["output"] for run in load_real_manifest()["runs"]]
        on_disk = ["out/" + name for name in os.listdir(os.path.join(PILOT, "out"))]
        self.assertEqual(sorted(listed), sorted(on_disk))

    def test_each_entry_has_a_saved_prompt_or_says_why_not(self):
        for run in load_real_manifest()["runs"]:
            with self.subTest(output=run["output"]):
                if run.get("prompt"):
                    self.assertTrue(os.path.isfile(os.path.join(PILOT, run["prompt"])))
                else:
                    self.assertTrue(run.get("note"), "找不到提示词的条目要写明原因")

    def test_each_entry_names_a_model_and_a_date(self):
        for run in load_real_manifest()["runs"]:
            with self.subTest(output=run["output"]):
                self.assertTrue(run.get("model"))
                self.assertRegex(run.get("date", ""), r"^\d{4}-\d{2}-\d{2}$")


SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{20,}",                        # 常见的接口密钥前缀
    r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|password)\b\s*[:=]\s*['\"][^'\"]{8,}",
    r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{16,}",
    r"AKIA[0-9A-Z]{16}",                              # 云服务访问密钥
    r"gh[pousr]_[A-Za-z0-9]{36}",                     # 代码托管平台令牌
]


class HelperScriptsAndExplanation(unittest.TestCase):
    def read_readme(self):
        with open(os.path.join(JUDGES, "README.md"), encoding="utf-8") as f:
            return f.read()

    def test_the_three_helper_scripts_are_archived(self):
        for name in ["build_rating.py", "build_verify.py", "write_pairs.py"]:
            with self.subTest(script=name):
                self.assertTrue(os.path.isfile(os.path.join(JUDGES, "scripts", name)))

    def test_every_script_the_manifest_mentions_is_archived(self):
        for run in load_real_manifest()["runs"]:
            for path in re.findall(r"judges/scripts/[\w.-]+\.py", run.get("written_by", "")):
                with self.subTest(script=path):
                    self.assertTrue(os.path.isfile(os.path.join(PILOT, path)))

    def test_the_explanation_names_every_script_and_every_output_file(self):
        readme = self.read_readme()
        for name in os.listdir(os.path.join(JUDGES, "scripts")):
            with self.subTest(script=name):
                self.assertIn(name, readme)
        for run in load_real_manifest()["runs"]:
            with self.subTest(output=run["output"]):
                self.assertIn(os.path.basename(run["output"]), readme)

    def test_local_links_in_the_explanation_open(self):
        for target in re.findall(r"\]\(([^)#\s]+)\)", self.read_readme()):
            if "://" in target:
                continue
            with self.subTest(link=target):
                self.assertTrue(os.path.exists(os.path.join(JUDGES, target)), target)

    def test_nothing_in_the_judge_folder_looks_like_a_secret(self):
        for folder, _, files in os.walk(JUDGES):
            for name in files:
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                for pattern in SECRET_PATTERNS:
                    with self.subTest(file=os.path.relpath(path, JUDGES), pattern=pattern):
                        self.assertIsNone(re.search(pattern, text))


class DesignDocumentPointsToTheJudgeFolder(unittest.TestCase):
    def test_the_judge_runs_section_links_to_the_judge_folder(self):
        with open(os.path.join(PILOT, "design.md"), encoding="utf-8") as f:
            design = f.read()
        section = design.split("## 评委运行", 1)[1].split("\n## ", 1)[0]
        self.assertIn("](judges/", section)


REAL_TRANSCRIPT = os.path.expanduser(load_real_manifest()["transcript"]) if os.path.exists(
    os.path.join(JUDGES, "manifest.json")) else ""


@unittest.skipUnless(REAL_TRANSCRIPT and os.path.exists(REAL_TRANSCRIPT),
                     "本机没有第五阶段的会话记录，跳过")
class SavedPromptsMatchTheRealTranscript(unittest.TestCase):
    def test_every_saved_prompt_and_its_facts_match_the_session_transcript(self):
        result = run_tool("check", "--judges", JUDGES)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
