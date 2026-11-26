# Gợi ý xử lý bế tắc: đình chỉ tiến trình / thu hồi tài nguyên (mục 4.2.4)
from dataclasses import dataclass, field

from models.detection import detect_deadlock, detect_deadlock_excluding
from utility import add, join_processes, p_name, vec_to_string


@dataclass
class RecoveryStep:
    victim: int             # tiến trình bị đình chỉ / thu hồi
    released: list
    still_deadlocked: list


@dataclass
class RecoveryPlan:
    deadlocked: list = field(default_factory=list)
    terminate_all_released: list = field(default_factory=list)  # cách 1
    steps: list = field(default_factory=list)                   # cách 2
    notes: list = field(default_factory=list)


def suggest_recovery(s):
    # Cách 2 chọn nạn nhân: (1) giải quyết nhiều bế tắc nhất, (2) giữ ít tài nguyên nhất, (3) chỉ số nhỏ hơn
    plan = RecoveryPlan()
    d = detect_deadlock(s)
    plan.deadlocked = d.deadlocked
    if not d.deadlock:
        plan.notes.append("Hệ thống không bị bế tắc, không cần xử lý.")
        return plan

    plan.terminate_all_released = [0] * s.m
    for i in d.deadlocked:
        plan.terminate_all_released = add(plan.terminate_all_released, s.allocation[i])
    plan.notes.append(
        f"Cách 1 - Đình chỉ hoạt động của mọi tiến trình bế tắc ({join_processes(d.deadlocked)}), "
        f"thu hồi {vec_to_string(plan.terminate_all_released)}. "
        "Đơn giản nhưng mất toàn bộ kết quả của các tiến trình này.")

    removed = [False] * s.n
    current = d.deadlocked
    while current:
        trials = []
        for cand in current:
            trial = list(removed)
            trial[cand] = True
            t = detect_deadlock_excluding(s, trial)
            trials.append((len(t.deadlocked), sum(s.allocation[cand]), cand, t.deadlocked))
        # min() giữ phần tử đầu tiên khi bằng nhau -> ưu tiên chỉ số nhỏ hơn
        _, _, best, remain = min(trials, key=lambda x: (x[0], x[1]))
        removed[best] = True
        plan.steps.append(RecoveryStep(best, list(s.allocation[best]), remain))
        current = remain

    seq = ", ".join(p_name(st.victim) for st in plan.steps)
    plan.notes.append(
        f"Cách 2 - Đình chỉ lần lượt từng tiến trình cho tới khi thoát bế tắc: {seq}. "
        "Mỗi lần chọn tiến trình giải quyết được nhiều bế tắc nhất, nếu bằng nhau thì chọn "
        "tiến trình đang giữ ít tài nguyên hơn.")
    plan.notes.append(
        "Thu hồi tài nguyên: có thể ngắt tài nguyên của các tiến trình trên thay vì đình chỉ hẳn, "
        "sau đó kiểm tra lại tình trạng bế tắc. Cần xem xét độ ưu tiên, thời gian đã chạy, khả năng "
        "phục hồi trạng thái và tránh để một tiến trình bị chọn mãi (không bao giờ được cấp đủ).")
    return plan
