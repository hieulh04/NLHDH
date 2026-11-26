# Thuật toán phát hiện bế tắc, tài nguyên đa thể (mục 4.2.3): so sánh Request(i) với Work
from dataclasses import dataclass

from models.safety import ScanMode, ScanResult, run_finish_scan
from utility import add


@dataclass
class DetectionResult:
    deadlock: bool
    deadlocked: list
    scan: ScanResult


def detect_deadlock(s, mode=ScanMode.TEXTBOOK):
    scan = run_finish_scan(s.available, s.allocation, s.request, mode)
    # Step 3: tồn tại i có Finish(i) = false thì hệ thống gặp bế tắc
    return DetectionResult(bool(scan.unfinished), list(scan.unfinished), scan)


def detect_deadlock_excluding(s, removed):
    # Tiến trình bị đình chỉ: tài nguyên trả về Available, không còn yêu cầu gì
    t = s.copy()
    for i in range(s.n):
        if removed[i]:
            t.available = add(t.available, t.allocation[i])
            t.allocation[i] = [0] * s.m
            t.request[i] = [0] * s.m
    d = detect_deadlock(t)
    d.deadlocked = [i for i in d.deadlocked if not removed[i]]
    d.deadlock = bool(d.deadlocked)
    return d
