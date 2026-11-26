# Kiểm thử module lõi (không cần Flask). Chạy: python3 tests/test_all.py
#   Test case 1: bài tập trang 52 - hệ có an toàn không
#   Test case 2: bài tập trang 54 - P4 yêu cầu (1, 2, 2)
#   Test case 3, 4: câu 5 và câu 6 trang 57
#   Mở rộng: phát hiện bế tắc qua RAG (tài nguyên đơn thể)
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.banker import RequestStatus, request_resources
from models.detection import detect_deadlock
from models.rag import detect_by_rag
from models.recovery import suggest_recovery
from models.safety import ScanMode, Stepper, check_safety
from report import build_html_report
from utility import InvalidInputError, Logger, SystemState, read_state, sample_list, write_state


def trang52():
    return sample_list()[0].state


class DeadlockTest(unittest.TestCase):
    def test_case_1_safety(self):
        s = trang52()
        self.assertEqual(s.need, [[4, 0, 1], [7, 1, 2], [2, 4, 2], [4, 3, 0], [1, 2, 2]])
        r = check_safety(s)
        self.assertTrue(r.all_finished)
        self.assertEqual(r.order, [4, 0, 1, 2, 3])
        self.assertEqual(r.final_work, [10, 5, 7])
        self.assertEqual(len(r.steps), 9)

    def test_case_2_request(self):
        s = trang52()
        res = request_resources(s, 4, [1, 2, 2])
        self.assertEqual(res.status, RequestStatus.GRANTED)
        self.assertEqual(res.tentative.available, [2, 1, 0])
        self.assertEqual(res.tentative.allocation[4], [3, 2, 2])
        self.assertEqual(res.tentative.need[4], [0, 0, 0])
        self.assertEqual(res.safety.order, [4, 0, 1, 2, 3])
        self.assertEqual(res.safety.final_work, [10, 5, 7])  # giáo trình in nhầm (12, 5, 5)
        self.assertEqual(s.available, [2, 1, 0])

    def test_case_3_cau_5(self):
        s = sample_list()[1].state
        self.assertEqual(s.need, [[0, 0, 0, 0], [0, 7, 5, 0], [1, 0, 0, 2], [0, 0, 2, 0], [0, 6, 4, 2]])
        r = check_safety(s)
        self.assertTrue(r.all_finished)
        self.assertEqual(r.order, [0, 2, 1, 3, 4])
        res = request_resources(s, 1, [0, 4, 2, 0])
        self.assertEqual(res.status, RequestStatus.GRANTED)
        self.assertEqual(res.safety.order, [0, 2, 1, 3, 4])

    def test_case_4_cau_6(self):
        s = sample_list()[2].state
        d = detect_deadlock(s)
        self.assertFalse(d.deadlock)
        self.assertEqual(d.scan.order, [0, 1, 2, 3, 4])
        self.assertTrue(check_safety(s).all_finished)
        requests = sample_list()[2].state.request
        for i in range(s.n):  # lần lượt đáp ứng yêu cầu của từng tiến trình
            self.assertEqual(request_resources(s, i, requests[i]).status, RequestStatus.GRANTED)

    def test_deadlock_and_recovery(self):
        s = sample_list()[3].state
        d = detect_deadlock(s)
        self.assertTrue(d.deadlock)
        self.assertEqual(d.deadlocked, [0, 1, 2])
        p = suggest_recovery(s)
        self.assertTrue(p.steps)
        self.assertEqual(p.steps[-1].still_deadlocked, [])
        self.assertEqual(p.terminate_all_released, [2, 2, 2])

    def test_rag(self):
        s = sample_list()[4].state
        self.assertTrue(s.is_single_instance())
        r = detect_by_rag(s)
        self.assertTrue(r.applicable)
        self.assertTrue(r.deadlock)
        self.assertEqual(r.cycles[0], [0, 1, 2, 0])
        self.assertEqual(r.in_cycle, [0, 1, 2])
        self.assertEqual(r.deadlocked, [0, 1, 2, 3])  # P3 bị kéo theo
        self.assertEqual(detect_deadlock(s).deadlocked, [0, 1, 2, 3])  # khớp thuật toán ma trận
        self.assertFalse(detect_by_rag(trang52()).applicable)

    def test_unsafe_keeps_state(self):
        self.assertFalse(check_safety(sample_list()[5].state).all_finished)
        s = trang52()
        before = s.copy()
        self.assertEqual(request_resources(s, 1, [8, 0, 0]).status, RequestStatus.ERROR_EXCEEDS_NEED)
        self.assertEqual(request_resources(s, 0, [4, 0, 0]).status, RequestStatus.WAIT_NOT_AVAILABLE)
        self.assertEqual(request_resources(s, 0, [0, 0, 1]).status, RequestStatus.WAIT_UNSAFE)
        self.assertEqual(s, before)

    def test_stepper(self):
        st = Stepper(check_safety(trang52()))
        self.assertIsNone(st.current())
        st.next()
        st.next()
        self.assertEqual(st.current().process, 1)
        st.back()
        self.assertEqual(st.current().process, 0)
        st.reset()
        self.assertFalse(st.has_back())
        st.run_to_end()
        self.assertTrue(st.finished())
        self.assertTrue(check_safety(trang52(), ScanMode.FAST).all_finished)

    def test_file_and_report(self):
        s = sample_list()[2].state
        self.assertEqual(read_state(write_state(s)), s)
        log = Logger()
        log.info("thử")
        page = build_html_report(s, safety=check_safety(s), log=log)
        self.assertIn("Dãy an toàn", page)

    def test_data_files_match_samples(self):
        data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        names = ["vidu_trang52", "cau5_trang57", "cau6_trang57", "be_tac_da_the", "rag_don_the",
                 "khong_an_toan"]
        for name, sample in zip(names, sample_list()):
            with open(os.path.join(data, name + ".txt"), encoding="utf-8") as f:
                self.assertEqual(read_state(f.read()), sample.state, name)

    def test_invalid_input(self):
        def request(i, vector):
            request_resources(trang52(), i, vector)

        cases = {
            "giá trị âm": lambda: SystemState.create([3, -1, 2], [[1, 1, 1]], [[0, 0, 0]]),
            "Allocation > Max": lambda: SystemState.create([3, 3, 2], [[1, 1, 1]], [[2, 0, 0]]),
            "số dòng sai": lambda: SystemState.create([3, 3, 2], [[1, 1, 1], [1, 1, 1]], [[0, 0, 0]]),
            "tiến trình không tồn tại": lambda: request(7, [1, 0, 0]),
            "yêu cầu bằng 0": lambda: request(1, [0, 0, 0]),
            "ký tự không phải số": lambda: read_state("2 2\n1 1\n0 0\n0 x\n"),
            "file thiếu dòng": lambda: read_state("2 2\n1 1\n0 0\n"),
        }
        for name, action in cases.items():
            with self.subTest(name), self.assertRaises(InvalidInputError):
                action()


if __name__ == "__main__":
    unittest.main()
