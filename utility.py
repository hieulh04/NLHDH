# utility.py — phần dùng chung: kiểu dữ liệu, kiểm tra đầu vào, đọc/ghi file, nhật ký, dữ liệu mẫu
import copy
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

INT_MIN, INT_MAX = -2**31, 2**31 - 1


class InvalidInputError(Exception):
    # row/col = vị trí ô bị lỗi (-1 nếu không xác định) để giao diện tô đỏ
    def __init__(self, message, field="", row=-1, col=-1):
        super().__init__(message)
        self.field = field
        self.row = row
        self.col = col


# ------------------------------ Vector tiện ích ------------------------------
def less_equal(a, b):
    # a <= b theo từng thành phần
    return all(a[j] <= b[j] for j in range(len(a)))


def add(a, b):
    return [a[j] + b[j] for j in range(len(a))]


def sub(a, b):
    return [a[j] - b[j] for j in range(len(a))]


def is_zero(a):
    return all(x == 0 for x in a)


def vec_to_string(v):
    return "(" + ", ".join(str(x) for x in v) + ")"


def p_name(i):
    return f"P{i}"


def join_processes(ids):
    return ", ".join(p_name(i) for i in ids)


def parse_int(token):
    # int() của Python nhận cả "1_000" và chữ số Unicode nên phải lọc trước; trả về None nếu sai
    if not re.fullmatch(r"[+-]?[0-9]+", token):
        return None
    value = int(token)
    return value if INT_MIN <= value <= INT_MAX else None


# ------------------------------ Trạng thái hệ thống ------------------------------
@dataclass
class SystemState:
    n: int = 0                                      # số tiến trình
    m: int = 0                                      # số kiểu tài nguyên
    available: list = field(default_factory=list)   # 1 x m
    max: list = field(default_factory=list)         # n x m
    allocation: list = field(default_factory=list)  # n x m
    need: list = field(default_factory=list)        # n x m, Need = Max - Allocation
    request: list = field(default_factory=list)     # n x m, dùng cho phát hiện bế tắc

    @classmethod
    def create(cls, available, max, allocation, request=None):
        # Tạo trạng thái, kiểm tra hợp lệ và tính Need. request rỗng -> toàn 0.
        s = cls(n=len(max), m=len(available), available=copy.deepcopy(available),
                max=copy.deepcopy(max), allocation=copy.deepcopy(allocation))
        s.request = copy.deepcopy(request) if request else [[0] * s.m for _ in range(s.n)]
        ensure_valid(s)
        s.recompute_need()
        return s

    def copy(self):
        return copy.deepcopy(self)

    def recompute_need(self):
        self.need = [sub(self.max[i], self.allocation[i]) for i in range(self.n)]

    def total_resources(self):
        # Available + tổng các dòng Allocation
        total = list(self.available)
        for row in self.allocation:
            total = add(total, row)
        return total

    def is_single_instance(self):
        return all(x == 1 for x in self.total_resources())


# ------------------------------ Kiểm tra đầu vào ------------------------------
@dataclass
class ValidationIssue:
    field: str  # "Available", "Max", "Allocation", "Request", "n", "m"
    row: int
    col: int
    message: str


def _check_vector(out, v, m, field_name, row, label):
    if len(v) != m:
        out.append(ValidationIssue(field_name, row, -1, f"{label} phải có đúng {m} phần tử, đang có {len(v)}"))
        return
    for j in range(m):
        if v[j] < 0:
            out.append(ValidationIssue(field_name, row, j, f"{label} có giá trị âm ở cột {j} ({v[j]})"))


def _check_matrix(out, a, n, m, field_name):
    if len(a) != n:
        out.append(ValidationIssue(field_name, -1, -1,
                                   f"Ma trận {field_name} phải có {n} dòng, đang có {len(a)}"))
        return
    for i in range(n):
        _check_vector(out, a[i], m, field_name, i, f"{field_name} của {p_name(i)}")


def validate_state(s):
    # Trả về TẤT CẢ lỗi tìm thấy (để giao diện tô đỏ nhiều ô cùng lúc). Rỗng = hợp lệ.
    out = []
    if s.n <= 0:
        out.append(ValidationIssue("n", -1, -1, "Số tiến trình n phải lớn hơn 0"))
    if s.m <= 0:
        out.append(ValidationIssue("m", -1, -1, "Số kiểu tài nguyên m phải lớn hơn 0"))
    if out:
        return out

    _check_vector(out, s.available, s.m, "Available", -1, "Available")
    _check_matrix(out, s.max, s.n, s.m, "Max")
    _check_matrix(out, s.allocation, s.n, s.m, "Allocation")
    _check_matrix(out, s.request, s.n, s.m, "Request")
    if out:
        return out

    for i in range(s.n):
        for j in range(s.m):
            if s.allocation[i][j] > s.max[i][j]:
                out.append(ValidationIssue(
                    "Allocation", i, j,
                    f"Allocation({i}, {j}) = {s.allocation[i][j]} lớn hơn Max = {s.max[i][j]}: "
                    f"{p_name(i)} đang giữ nhiều hơn nhu cầu tối đa đã khai báo"))
    return out


def ensure_valid(s):
    issues = validate_state(s)
    if issues:
        e = issues[0]
        raise InvalidInputError(e.message, e.field, e.row, e.col)


def validate_request(s, i, request):
    # Kiểm tra Request(i) trước khi chạy thuật toán Banker
    if i < 0 or i >= s.n:
        raise InvalidInputError(f"Tiến trình {p_name(i)} không tồn tại (chỉ có P0..{p_name(s.n - 1)})")
    out = []
    _check_vector(out, request, s.m, "Request", i, f"Yêu cầu của {p_name(i)}")
    if out:
        raise InvalidInputError(out[0].message, "RequestInput", -1, out[0].col)
    if is_zero(request):
        raise InvalidInputError(f"Yêu cầu của {p_name(i)} đang bằng 0, không có gì để cấp phát")


# ------------------------------ Đọc / ghi file ------------------------------
# Định dạng (phần sau dấu # là chú thích):
#   n m
#   Available          (1 dòng, m số)
#   Allocation         (n dòng)
#   Max                (n dòng)
#   Request            (n dòng, có thể bỏ qua -> toàn 0)
class _LineReader:
    def __init__(self, text):
        self.lines = text.split("\n")
        if self.lines[-1] == "":
            self.lines.pop()  # dấu xuống dòng cuối file không tính là một dòng
        self.line_no = 0

    def next_row(self, what, expected, optional=False):
        while self.line_no < len(self.lines):
            line = self.lines[self.line_no].split("#", 1)[0]
            self.line_no += 1
            if not line.strip(" \t\r"):
                continue
            row = []
            for token in line.split():
                value = parse_int(token)
                if value is None:
                    raise InvalidInputError(f"Dòng {self.line_no} ({what}): '{token}' không phải số nguyên")
                row.append(value)
            if len(row) != expected:
                raise InvalidInputError(f"Dòng {self.line_no} ({what}): cần {expected} số, đang có {len(row)}")
            return row
        if optional:
            return None
        raise InvalidInputError(f"Thiếu dữ liệu: chưa đọc được {what} (file kết thúc ở dòng {self.line_no})")


def read_state(text):
    reader = _LineReader(text)
    n, m = reader.next_row("n m", 2)
    if n <= 0 or m <= 0 or n > 50 or m > 20:
        raise InvalidInputError("n phải trong 1..50 và m trong 1..20")
    available = reader.next_row("Available", m)
    allocation = [reader.next_row(f"Allocation của {p_name(i)}", m) for i in range(n)]
    maximum = [reader.next_row(f"Max của {p_name(i)}", m) for i in range(n)]
    request = []
    first = reader.next_row("Request của P0", m, optional=True)
    if first is not None:
        request.append(first)
        for i in range(1, n):
            request.append(reader.next_row(f"Request của {p_name(i)}", m))
    return SystemState.create(available, maximum, allocation, request)


def write_state(s):
    def row(v):
        return " ".join(str(v[j]) for j in range(s.m))

    lines = ["# n m", f"{s.n} {s.m}", "# Available", row(s.available)]
    for title, matrix in (("# Allocation", s.allocation), ("# Max", s.max), ("# Request", s.request)):
        lines.append(title)
        lines.extend(row(r) for r in matrix)
    return "\n".join(lines) + "\n"


# ------------------------------ Nhật ký ------------------------------
class LogLevel(Enum):
    INFO = "THÔNG TIN"
    STEP = "BƯỚC"
    RESULT = "KẾT QUẢ"
    WARNING = "CẢNH BÁO"
    ERROR = "LỖI"


@dataclass
class LogEntry:
    time: str  # HH:MM:SS
    level: LogLevel
    message: str

    def to_line(self):
        return f"[{self.time}] [{self.level.value}] {self.message}"


class Logger:
    def __init__(self, listener=None):
        self.entries = []
        self.listener = listener  # giao diện đăng ký để nhận log mới

    def info(self, message):
        self._add(LogLevel.INFO, message)

    def step(self, message):
        self._add(LogLevel.STEP, message)

    def result(self, message):
        self._add(LogLevel.RESULT, message)

    def warning(self, message):
        self._add(LogLevel.WARNING, message)

    def error(self, message):
        self._add(LogLevel.ERROR, message)

    def clear(self):
        self.entries.clear()

    def to_text(self):
        return "".join(e.to_line() + "\n" for e in self.entries)

    def _add(self, level, message):
        entry = LogEntry(datetime.now().strftime("%H:%M:%S"), level, message)
        self.entries.append(entry)
        if self.listener:
            self.listener(entry)


# ------------------------------ Dữ liệu mẫu (giáo trình) ------------------------------
@dataclass
class SampleData:
    name: str
    description: str
    state: SystemState
    request_process: int = -1  # yêu cầu gợi ý để thử Banker (-1 nếu không có)
    request_vector: list = field(default_factory=list)


def sample_list():
    # Thứ tự tham số của create: available, max, allocation, request
    return [
        SampleData(
            "Giáo trình trang 52-54 (5 tiến trình, 3 tài nguyên)",
            "Ví dụ mục 4.2.2: (a) hệ có an toàn không? (b) P4 yêu cầu (1, 2, 2).",
            SystemState.create([3, 3, 2],
                               [[7, 0, 3], [9, 2, 2], [2, 5, 3], [4, 3, 2], [3, 2, 2]],
                               [[3, 0, 2], [2, 1, 0], [0, 1, 1], [0, 0, 2], [2, 0, 0]]),
            4, [1, 2, 2]),
        SampleData(
            "Câu 5 trang 57 (5 tiến trình, 4 tài nguyên)",
            "Tính Need, kiểm tra an toàn, P1 yêu cầu (0, 4, 2, 0).",
            SystemState.create([1, 5, 2, 0],
                               [[0, 0, 1, 2], [1, 7, 5, 0], [2, 3, 5, 6], [0, 6, 5, 2], [0, 6, 5, 6]],
                               [[0, 0, 1, 2], [1, 0, 0, 0], [1, 3, 5, 4], [0, 6, 3, 2], [0, 0, 1, 4]]),
            1, [0, 4, 2, 0]),
        SampleData(
            "Câu 6 trang 57 (có ma trận Request)",
            "Có thể phân bổ tài nguyên cho các tiến trình không? Dùng phát hiện bế tắc và Banker.",
            SystemState.create([9, 6, 5],
                               [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]],
                               [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]],
                               [[1, 2, 0], [1, 0, 2], [2, 0, 0], [0, 0, 1], [2, 2, 0]]),
            0, [1, 2, 0]),
        SampleData(
            "Bế tắc tài nguyên đa thể (3 tiến trình)",
            "P0, P1, P2 chờ vòng; dùng thuật toán phát hiện bế tắc và gợi ý xử lý.",
            SystemState.create([0, 0, 0],
                               [[2, 1, 1], [1, 2, 1], [1, 1, 2]],
                               [[1, 0, 1], [1, 1, 0], [0, 1, 1]],
                               [[1, 1, 0], [0, 1, 1], [1, 0, 1]])),
        SampleData(
            "Tài nguyên đơn thể - đồ thị RAG (mục 1.3.1)",
            "P1 -> P2 -> P3 -> P1 tạo chu trình; P4 bị kéo theo; P5 bình thường (đánh số từ P0).",
            SystemState.create(
                [0, 0, 0, 0, 0],
                [[1, 1, 0, 0, 0], [0, 1, 1, 0, 0], [1, 0, 1, 0, 0], [1, 0, 0, 1, 0], [0, 0, 0, 0, 1]],
                [[1, 0, 0, 0, 0], [0, 1, 0, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 1, 0], [0, 0, 0, 0, 1]],
                [[0, 1, 0, 0, 0], [0, 0, 1, 0, 0], [1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [0, 0, 0, 0, 0]])),
        SampleData(
            "Trạng thái không an toàn",
            "Không sắp xếp được dãy an toàn: hệ có nguy cơ bế tắc.",
            SystemState.create([1, 0], [[3, 2], [2, 3], [3, 3]], [[1, 1], [1, 1], [1, 1]])),
    ]
