# Phát hiện bế tắc qua đồ thị cấp phát tài nguyên / đồ thị chờ, tài nguyên đơn thể (mục 1.3.1)
from dataclasses import dataclass, field

from utility import p_name


@dataclass
class RagResult:
    applicable: bool = False  # False nếu có kiểu tài nguyên khác 1 thể hiện
    reason: str = ""
    holder: list = field(default_factory=list)      # holder[j] = tiến trình giữ Rj (-1 nếu rảnh)
    wait_edges: list = field(default_factory=list)  # cạnh đồ thị chờ (i, k): Pi -> Pk
    cycles: list = field(default_factory=list)      # chu trình khép kín: v ... u v
    in_cycle: list = field(default_factory=list)
    deadlocked: list = field(default_factory=list)  # gồm cả tiến trình bị kéo theo
    log: list = field(default_factory=list)         # vết DFS từng bước

    @property
    def deadlock(self):
        return bool(self.cycles)


def detect_by_rag(s):
    r = RagResult()
    total = s.total_resources()
    for j in range(s.m):
        if total[j] != 1:
            r.reason = (f"Kiểu tài nguyên R{j} có {total[j]} thể hiện. Phương pháp RAG chỉ áp dụng khi mọi "
                        "kiểu tài nguyên có đúng 1 thể hiện; hãy dùng thuật toán phát hiện bế tắc (ma trận).")
            return r
    r.applicable = True

    r.holder = [-1] * s.m
    for i in range(s.n):
        for j in range(s.m):
            if s.allocation[i][j] > 0:
                r.holder[j] = i

    # Pi -> Pk nếu Pi yêu cầu Rj và Rj đang bị Pk giữ
    adj = [[] for _ in range(s.n)]
    for i in range(s.n):
        for j in range(s.m):
            k = r.holder[j]
            if s.request[i][j] > 0 and k >= 0 and k != i and k not in adj[i]:
                adj[i].append(k)
                r.wait_edges.append((i, k))

    # DFS ba màu: 0 = TRẮNG, 1 = XÁM, 2 = ĐEN
    color = [0] * s.n
    parent = [-1] * s.n

    def dfs(u):
        color[u] = 1
        r.log.append(f"DFS({p_name(u)}): {p_name(u)} chuyển sang XÁM")
        for v in adj[u]:
            edge = f"  Cạnh {p_name(u)} -> {p_name(v)}: {p_name(v)}"
            if color[v] == 0:
                parent[v] = u
                r.log.append(f"{edge} TRẮNG, duyệt tiếp")
                dfs(v)
            elif color[v] == 1:
                cycle = [u]
                x = u
                while x != v:
                    x = parent[x]
                    cycle.insert(0, x)
                cycle.append(v)
                r.cycles.append(cycle)
                text = " -> ".join(p_name(p) for p in cycle)
                r.log.append(f"{edge} đang XÁM => cạnh ngược, có chu trình {text}")
            else:
                r.log.append(f"{edge} đã ĐEN, bỏ qua")
        color[u] = 2
        r.log.append(f"  {p_name(u)} duyệt xong, chuyển sang ĐEN")

    for i in range(s.n):
        if color[i] == 0:
            dfs(i)

    r.in_cycle = sorted({p for cycle in r.cycles for p in cycle})

    # Rút gọn đồ thị: loại dần tiến trình không chờ ai; còn lại là tập bị treo
    outdeg = [len(a) for a in adj]
    done = [False] * s.n
    queue = [i for i in range(s.n) if outdeg[i] == 0]
    while queue:
        k = queue.pop()
        done[k] = True
        for i in range(s.n):
            if not done[i] and k in adj[i]:
                outdeg[i] -= 1
                if outdeg[i] == 0:
                    queue.append(i)
    r.deadlocked = [i for i in range(s.n) if not done[i]]
    return r
