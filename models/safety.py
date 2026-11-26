# Thuật toán kiểm tra tính an toàn (mục 4.2.2c, Hình 4.2) + bộ điều khiển Next/Back/Reset
from dataclasses import dataclass, field
from enum import Enum

from utility import add, less_equal, p_name, vec_to_string


@dataclass
class ScanStep:
    # Một lần xét tiến trình ở Step 2 (dùng chung cho kiểm tra an toàn và phát hiện bế tắc)
    round: int              # lần tìm thứ mấy
    process: int            # tiến trình đang xét
    compared: list          # Need(i) hoặc Request(i)
    work_before: list
    satisfied: bool         # compared <= Work ?
    work_after: list = field(default_factory=list)  # chỉ có khi satisfied
    finish: list = field(default_factory=list)      # mảng Finish sau bước này


@dataclass
class ScanResult:
    all_finished: bool
    order: list             # thứ tự Finish(i) := true (dãy an toàn)
    unfinished: list
    initial_work: list
    final_work: list
    steps: list


class ScanMode(Enum):
    # TEXTBOOK: tìm được tiến trình thỏa mãn thì quay lại xét từ P0 (giống bài giải giáo trình)
    # FAST    : xét tiếp các tiến trình phía sau rồi mới quay vòng (ít phép so sánh hơn)
    TEXTBOOK = 1
    FAST = 2


def run_finish_scan(available, allocation, compared, mode=ScanMode.TEXTBOOK):
    # Work := Available; lặp tìm i có Finish(i) = false và compared(i) <= Work
    n = len(allocation)
    # Step 1
    work = list(available)
    finish = [False] * n
    order, steps = [], []

    round_no, start = 1, 0
    while True:
        # Step 2
        found = -1
        for k in range(n):
            i = (start + k) % n if mode == ScanMode.FAST else k
            if finish[i]:
                continue
            st = ScanStep(round_no, i, list(compared[i]), list(work), less_equal(compared[i], work))
            if st.satisfied:
                # Step 3: Work := Work + Allocation(i); Finish(i) := true
                work = add(work, allocation[i])
                finish[i] = True
                order.append(i)
                st.work_after = list(work)
                found = i
            st.finish = list(finish)
            steps.append(st)
            if found >= 0:
                break
        if found < 0:
            break
        start = found + 1
        round_no += 1

    # Step 4
    unfinished = [i for i in range(n) if not finish[i]]
    return ScanResult(not unfinished, order, unfinished, list(available), list(work), steps)


def check_safety(s, mode=ScanMode.TEXTBOOK):
    # all_finished = True -> an toàn, order là dãy an toàn
    return run_finish_scan(s.available, s.allocation, s.need, mode)


def describe_step(st, compared_name):
    text = (f"Lần tìm {st.round}: xét {p_name(st.process)}, {compared_name}({st.process}) = "
            f"{vec_to_string(st.compared)}, Work = {vec_to_string(st.work_before)}")
    if st.satisfied:
        return text + (f" -> thỏa mãn: Finish({st.process}) := true, "
                       f"Work := {vec_to_string(st.work_after)}")
    return text + f" -> không thỏa mãn, {p_name(st.process)} đợi"


class Stepper:
    def __init__(self, result):
        self.result = result
        self.position = 0  # số bước đã hiển thị

    @property
    def total(self):
        return len(self.result.steps)

    def has_next(self):
        return self.position < self.total

    def has_back(self):
        return self.position > 0

    def next(self):
        st = self.result.steps[self.position]
        self.position += 1
        return st

    def back(self):
        if self.position > 0:
            self.position -= 1

    def reset(self):
        self.position = 0

    def run_to_end(self):
        self.position = self.total

    def current(self):
        return self.result.steps[self.position - 1] if self.position > 0 else None

    def finished(self):
        return self.position == self.total
