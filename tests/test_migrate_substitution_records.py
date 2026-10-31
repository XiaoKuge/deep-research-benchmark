"""一次性迁移程序 tools/migrate_substitution_records.py 的测试：旧格式的替代记录改成统一的五个字段，
文件的其余部分和格式（缩进、末尾换行）不变，重复运行没有影响。"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import migrate_substitution_records as migrate  # noqa: E402

STEPS = {"claims_list": ["claude"], "verify": ["claude", "codex", "kimi"], "extract": ["claude"],
         "merge": ["claude"], "reach": ["claude"], "judge": ["claude", "codex", "kimi"],
         "rating": ["claude", "codex"], "pairwise": ["claude", "codex"], "direct": ["claude"]}
OLD_RUN = {
    "run_id": "旧的一次", "status": "中止",
    "config": {"steps": {k: {"vendors": v, "times": 1} for k, v in STEPS.items()}},
    "unavailable": [{"vendor": "kimi", "company": "月之暗面", "first_failed_task": "评审-断言核验：报告 A，评委 3",
                     "error": "401", "noticed_at": "2026-10-30T20:00:00-07:00"}],
    "substitutions": [
        {"step": "断言核验", "slot": 3, "task": "评审-断言核验：报告 A，评委 3", "planned_vendor": "kimi", "vendor": "claude"},
        {"step": "要点判定", "slot": 3, "task": "评审-要点判定：评委 3", "planned_vendor": "kimi", "vendor": "claude"}],
    "notes": {},
}
CALLS = [{"task": "评审-断言核验：报告 A，评委 %d" % n, "vendor": v, "status": "成功"}
         for n, v in ((1, "claude"), (2, "codex"), (3, "claude"))]
CALLS.append({"task": "评审-断言核验：报告 A，评委 3", "vendor": "kimi", "status": "失败"})
OLD_META = {"题目标识": "旧题", "角色": {"乙": {"配置的厂商": "kimi", "替代": [
    {"角色": "乙", "步骤": "出题-深度地图-乙-第1轮", "配置的厂商": "kimi", "原来用的厂商": "kimi", "改用": "claude",
     "原因": "kimi：调用失败：401"}]}, "甲": {"配置的厂商": "claude", "替代": []}}}


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sim = self._tmp.name
        self.run_json = os.path.join(self.sim, "reviews", "旧的一次", "run.json")
        self.meta_json = os.path.join(self.sim, "questions", "旧题", "元数据.json")
        os.makedirs(os.path.dirname(self.run_json))
        os.makedirs(os.path.dirname(self.meta_json))
        self.write(self.run_json, json.dumps(OLD_RUN, ensure_ascii=False, indent=1) + "\n")
        self.write(self.meta_json, json.dumps(OLD_META, ensure_ascii=False, indent=2) + "\n")
        self.write(os.path.join(self.sim, "reviews", "旧的一次", "calls.jsonl"),
                   "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in CALLS))

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def migrate(self):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = migrate.main(["--simulation", self.sim])
        return code, printed.getvalue()

    def test_old_records_become_the_one_format_and_the_rest_is_kept(self):
        code, _ = self.migrate()
        self.assertEqual(code, 0)
        text = self.read(self.run_json)
        run = json.loads(text)
        self.assertEqual(text, json.dumps(run, ensure_ascii=False, indent=1) + "\n")
        self.assertEqual(run["substitutions"], [
            {"步骤": "断言核验", "任务": "评审-断言核验：报告 A，评委 3", "原来的厂商": "kimi", "改用的厂商": "claude",
             "原因": "kimi：调用失败：401"},
            {"步骤": "要点判定", "任务": "评审-要点判定：评委 3", "原来的厂商": "kimi", "改用的厂商": "claude",
             "原因": "kimi：在本次运行前面的调用里已经不可用"}])
        self.assertEqual([(i["step"], i["used_vendors"]) for i in run["too_few_vendors"]],
                         [("断言核验", ["claude", "codex"])])
        self.assertEqual({k: run[k] for k in ("run_id", "status", "unavailable", "notes")},
                         {k: OLD_RUN[k] for k in ("run_id", "status", "unavailable", "notes")})
        meta = json.loads(self.read(self.meta_json))
        self.assertEqual(meta["角色"]["乙"]["替代"], [
            {"步骤": "深度地图", "任务": "出题-深度地图-乙-第1轮", "原来的厂商": "kimi", "改用的厂商": "claude",
             "原因": "kimi：调用失败：401"}])
        self.assertEqual(meta["角色"]["甲"], OLD_META["角色"]["甲"])

    def test_running_it_again_changes_nothing(self):
        self.migrate()
        before = (self.read(self.run_json), self.read(self.meta_json))
        code, printed = self.migrate()
        self.assertEqual(code, 0)
        self.assertIn("没有要迁移的文件", printed)
        self.assertEqual((self.read(self.run_json), self.read(self.meta_json)), before)

    def test_a_file_in_another_format_is_left_alone(self):
        self.write(self.run_json, json.dumps(OLD_RUN, ensure_ascii=False, indent=4))
        code, printed = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("没有改", printed)
        self.assertEqual(self.read(self.run_json), json.dumps(OLD_RUN, ensure_ascii=False, indent=4))

    def test_the_committed_data_is_already_in_the_one_format(self):
        sim = os.path.join(ROOT, "simulation")
        for folder, _, names in os.walk(sim):
            for name in names:
                if name not in ("run.json", "元数据.json"):
                    continue
                data = json.loads(self.read(os.path.join(folder, name)))
                items = data.get("substitutions", []) if name == "run.json" else [
                    item for info in (data.get("角色") or {}).values() for item in info.get("替代", [])]
                for item in items:
                    with self.subTest(file=os.path.relpath(os.path.join(folder, name), sim)):
                        self.assertEqual(list(item), ["步骤", "任务", "原来的厂商", "改用的厂商", "原因"])
                if name == "run.json":
                    self.assertIn("too_few_vendors", data)


if __name__ == "__main__":
    unittest.main()
