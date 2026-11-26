# Thuật toán Banker (Resource-Request) — mục 4.2.2b, Hình 4.3
import copy
from dataclasses import dataclass
from enum import Enum

from models.safety import ScanMode, ScanResult, check_safety
from utility import SystemState, add, less_equal, sub, validate_request


class RequestStatus(Enum):
    GRANTED = 1             # Step 4: an toàn -> phân bổ
    ERROR_EXCEEDS_NEED = 2  # Step 1 sai: Request(i) > Need(i)
    WAIT_NOT_AVAILABLE = 3  # Step 2 sai: Request(i) > Available
    WAIT_UNSAFE = 4         # Step 4: không an toàn -> giữ trạng thái cũ, Pi đợi


STATUS_TEXT = {
    RequestStatus.GRANTED: "Phân bổ được: sau khi phân bổ, hệ vẫn ở trạng thái an toàn",
    RequestStatus.ERROR_EXCEEDS_NEED: "Lỗi: tiến trình yêu cầu tài nguyên vượt quá quy định (Request > Need)",
    RequestStatus.WAIT_NOT_AVAILABLE: "Tiến trình phải đợi: không đủ tài nguyên để phân bổ (Request > Available)",
    RequestStatus.WAIT_UNSAFE: "Tiến trình phải đợi: nếu phân bổ thì hệ không an toàn, đã khôi phục trạng thái cũ",
}


@dataclass
class RequestResult:
    process: int
    request: list
    before: SystemState      # trạng thái trước khi yêu cầu
    tentative: SystemState   # trạng thái dự định sau Step 3
    status: RequestStatus = RequestStatus.GRANTED
    safety: ScanResult = None  # chỉ có khi đến Step 4
    reached_step4: bool = False


def request_resources(s, i, request, mode=ScanMode.TEXTBOOK):
    # GRANTED thì s được cập nhật tại chỗ; các trường hợp còn lại s giữ nguyên
    validate_request(s, i, request)
    res = RequestResult(i, list(request), s.copy(), s.copy())

    # Step 1
    if not less_equal(request, s.need[i]):
        res.status = RequestStatus.ERROR_EXCEEDS_NEED
        return res
    # Step 2
    if not less_equal(request, s.available):
        res.status = RequestStatus.WAIT_NOT_AVAILABLE
        return res

    # Step 3: dự định phân bổ trên bản sao -> không cần code khôi phục
    t = s.copy()
    t.available = sub(t.available, request)
    t.allocation[i] = add(t.allocation[i], request)
    t.need[i] = sub(t.need[i], request)
    res.tentative = t

    # Step 4
    res.reached_step4 = True
    res.safety = check_safety(t, mode)
    if res.safety.all_finished:
        s.available, s.allocation, s.need = copy.deepcopy((t.available, t.allocation, t.need))
        res.status = RequestStatus.GRANTED
    else:
        res.status = RequestStatus.WAIT_UNSAFE
    return res


def status_text(status):
    return STATUS_TEXT[status]
