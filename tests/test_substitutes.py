"""模拟出题和模拟评审共用的挑厂商办法（tools/substitutes.py）的测试。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import models  # noqa: E402
import substitutes  # noqa: E402


class PickTest(unittest.TestCase):
    def setUp(self):
        self.vendors = substitutes.Vendors()

    def test_the_first_vendor_in_order_is_used_when_nothing_stands_in_the_way(self):
        self.assertEqual(self.vendors.pick(["codex", "claude"], models.MATERIALS_ONLY), ("codex", []))

    def test_a_vendor_that_cannot_serve_the_tier_is_skipped_but_stays_available(self):
        vendor, skipped = self.vendors.pick(["google", "claude"], models.WEB_READ_ONLY)
        self.assertEqual(vendor, "claude")
        self.assertEqual(skipped, [("google", models.unusable_reason("google", models.WEB_READ_ONLY))])
        self.assertEqual(self.vendors.unavailable, {})
        self.assertEqual(self.vendors.pick(["google", "claude"], models.MATERIALS_ONLY), ("google", []))

    def test_an_unavailable_vendor_is_skipped_for_the_rest_of_the_run(self):
        self.assertTrue(self.vendors.mark_unavailable("kimi", "401"))
        self.assertFalse(self.vendors.mark_unavailable("kimi", "又失败了"))
        self.assertEqual(self.vendors.unavailable, {"kimi": "401"})
        vendor, skipped = self.vendors.pick(["kimi", "codex"], models.MATERIALS_ONLY)
        self.assertEqual(vendor, "codex")
        self.assertEqual(skipped, [("kimi", substitutes.ALREADY_UNAVAILABLE)])

    def test_a_reason_given_for_this_call_replaces_the_general_one(self):
        self.vendors.mark_unavailable("kimi", "401")
        _, skipped = self.vendors.pick(["kimi", "codex"], models.MATERIALS_ONLY,
                                       failed={"kimi": "调用失败：401"})
        self.assertEqual(skipped, [("kimi", "调用失败：401")])

    def test_the_caller_can_exclude_vendors_and_nothing_left_gives_none(self):
        exclude = {"claude": "写过本题的深度地图"}.get
        vendor, skipped = self.vendors.pick(["claude", "google"], models.WEB_READ_ONLY, exclude=exclude)
        self.assertIsNone(vendor)
        self.assertEqual([v for v, _ in skipped], ["claude", "google"])
        self.assertEqual(skipped[0][1], "写过本题的深度地图")

    def test_a_vendor_listed_twice_is_looked_at_once(self):
        self.vendors.mark_unavailable("claude", "额度用完")
        _, skipped = self.vendors.pick(["claude", "claude", "codex"], models.MATERIALS_ONLY)
        self.assertEqual(skipped, [("claude", substitutes.ALREADY_UNAVAILABLE)])


class RecordTest(unittest.TestCase):
    def test_one_format_with_five_fields(self):
        item = substitutes.record("断言核验", "评审-断言核验：报告 A，只读网页，评委 3", "google", "codex",
                                  [("google", "不能用于只读网页一档")])
        self.assertEqual(list(item), list(substitutes.FIELDS))
        self.assertEqual(list(item), ["步骤", "任务", "原来的厂商", "改用的厂商", "原因"])
        self.assertEqual(item["原因"], "google：不能用于只读网页一档")
        self.assertEqual(substitutes.reasons([("kimi", "401"), ("google", "没有登录")]),
                         "kimi：401；google：没有登录")


if __name__ == "__main__":
    unittest.main()
