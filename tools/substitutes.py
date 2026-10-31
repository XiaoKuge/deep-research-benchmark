"""模拟出题和模拟评审共用的挑厂商办法，以及替代记录的格式。

挑厂商：按调用方给的先后顺序看每一家，跳过三种：
- 这一家不能用于这一档（models.unusable_reason，目前只有 google 不能用于只读网页一档）。
  只是这一次不用它，它在别的档里照常可用，不算整次运行都不可用；
- 在本次运行里已经不可用（前面的一次调用失败、超时或找不到命令行）；
- 调用方另外排除的（例如闭卷对照不能用写过深度地图的厂商）。
第一家不被跳过的就是这次用的。先后顺序由调用方定：模拟出题按角色排，模拟评审按配置的替代顺序排。

替代记录：计划的厂商没被用上、换了一家时记一条，字段固定为 FIELDS 这五个。
只用 Python 自带的标准库。
"""
import threading

import models

FIELDS = ("步骤", "任务", "原来的厂商", "改用的厂商", "原因")
ALREADY_UNAVAILABLE = "在本次运行前面的调用里已经不可用"


class Vendors:
    """一次运行里各家的状态：哪几家已经不可用（整次运行不再用），为什么。多个线程可以同时用。"""

    def __init__(self):
        self.unavailable = {}  # 厂商 -> 原因
        self._lock = threading.Lock()

    def mark_unavailable(self, vendor, reason):
        """记下这一家在本次运行里不可用；第一次记下时返回 True，已经记过返回 False（原因不改）。"""
        with self._lock:
            if vendor in self.unavailable:
                return False
            self.unavailable[vendor] = reason
            return True

    def is_unavailable(self, vendor):
        with self._lock:
            return vendor in self.unavailable

    def pick(self, order, tools, exclude=None, failed=None):
        """按 order 的先后挑第一家能用的。返回 (厂商, 跳过的 [(厂商, 原因)])；一家也挑不出时厂商为 None。

        exclude(厂商) 返回原因时也跳过这一家；failed 是 {厂商: 原因}，这次调用里已经失败过的厂商，
        跳过它时用这里的原因（例如"调用失败：……"），不用笼统的"已经不可用"。
        """
        skipped = []
        for vendor in dict.fromkeys(order):
            reason = models.unusable_reason(vendor, tools)
            if reason is None and self.is_unavailable(vendor):
                reason = (failed or {}).get(vendor) or ALREADY_UNAVAILABLE
            if reason is None and exclude is not None:
                reason = exclude(vendor)
            if reason is None:
                return vendor, skipped
            skipped.append((vendor, reason))
        return None, skipped


def reasons(skipped):
    """跳过的各家和原因写成一句：「kimi：……；google：……」。"""
    return "；".join("%s：%s" % pair for pair in skipped)


def record(step, task, planned, used, skipped):
    """一条替代记录。step 是步骤（模拟评审：断言核验等；模拟出题：评委版、深度地图等），task 是任务名。"""
    return {"步骤": step, "任务": task, "原来的厂商": planned, "改用的厂商": used, "原因": reasons(skipped)}
