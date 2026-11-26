# app.py — web Flask: Controller nối giao diện với thuật toán, hiển thị trạng thái An toàn / Bế tắc
import html
import os
import sys

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.banker import RequestStatus, request_resources, status_text
from models.detection import detect_deadlock
from models.rag import detect_by_rag
from models.recovery import suggest_recovery
from models.safety import Stepper, check_safety, describe_step
from report import build_html_report
from utility import (InvalidInputError, Logger, SystemState, join_processes, less_equal, p_name, parse_int,
                     read_state, sample_list, validate_state, vec_to_string, write_state)

app = Flask(__name__)

NEUTRAL, GOOD, BAD = 0, 1, 2
DEFAULT_N, DEFAULT_M = 5, 3
MAX_N, MAX_M = 20, 10  # giới hạn khi tự tạo bảng; file mở vào được tới 50 x 20


def parse_table(rows, field_name, has_row_names=True):
    # Ô trống = 0
    table = []
    for i, row in enumerate(rows):
        values = []
        for j, cell in enumerate(row):
            text = str(cell).strip()
            value = parse_int(text) if text else 0
            if value is None:
                where = f"{field_name} của {p_name(i)}" if has_row_names else field_name
                raise InvalidInputError(f"{where}, cột R{j}: '{text}' không phải số nguyên", field_name, i, j)
            values.append(value)
        table.append(values)
    return table


class Controller:
    def __init__(self):
        self.new_log = []
        self.logger = Logger(lambda e: self.new_log.append(e.to_line()))
        self.state = None
        self.marks = []
        self.extra = {}  # dữ liệu chỉ gửi một lần: input, download, status, tab, clear_log
        self.set_size(DEFAULT_N, DEFAULT_M)

    def view(self):
        data = {
            "banner": self.banner,
            "need": self.need,
            "request_result": self.request_view,
            "safety": step_view(self.safety, "Need"),
            "detection": step_view(self.detect, "Request"),
            "deadlock": self.deadlock_view,
            "rag": self.rag_view,
            "marks": self.marks,
            "log": self.new_log[:],
            **self.extra,
        }
        self.new_log.clear()
        self.marks = []
        self.extra = {}
        return data

    # ------------------------------- Tiện ích ----------------------------------
    def set_size(self, n, m):
        self.need = [[0] * m for _ in range(n)]
        self.clear_results()
        self.extra["input"] = {
            "n": n, "m": m,
            "available": [[0] * m],
            "allocation": [[0] * m for _ in range(n)],
            "max": [[0] * m for _ in range(n)],
            "request": [[0] * m for _ in range(n)],
            "request_process": 0,
            "request_vector": [0] * m,
        }

    def load_input(self, s):
        self.set_size(s.n, s.m)
        self.extra["input"].update(available=[s.available], allocation=s.allocation, max=s.max, request=s.request)

    def preset_request(self, process, vector):
        self.extra["input"].update(request_process=process, request_vector=vector)

    def clear_results(self):
        self.safety = None  # Stepper
        self.detect = None  # Stepper
        self.deadlock_view = None
        self.rag_view = None
        self.request_view = None
        self.last_safety = None
        self.last_request = None
        self.last_detection = None
        self.last_recovery = None
        self.last_rag = None
        self.show_banner("Nhập dữ liệu hoặc tải dữ liệu mẫu, sau đó chọn chức năng ở các tab bên phải.", NEUTRAL)

    def show_banner(self, text, kind):
        self.banner = {"text": text, "kind": kind}

    def show_error(self, message):
        self.logger.error(message)
        self.show_banner("Lỗi dữ liệu: " + message, BAD)
        self.extra["status"] = message

    def mark(self, field_name, row, col):
        # row = -1: cả bảng, col = -1: cả dòng
        if field_name == "Available":
            row = 0
        if field_name in ("Available", "Allocation", "Max", "Request", "RequestInput"):
            self.marks.append({"table": field_name, "row": row, "col": col})

    def apply_input(self, tables):
        # Đọc bảng nhập -> self.state; tô đỏ TẤT CẢ ô lỗi, báo lỗi đầu tiên
        try:
            available = parse_table(tables["available"], "Available", has_row_names=False)[0]
            allocation = parse_table(tables["allocation"], "Allocation")
            maximum = parse_table(tables["max"], "Max")
            req = parse_table(tables["request"], "Request")
            s = SystemState(n=len(allocation), m=len(allocation[0]), available=available,
                            max=maximum, allocation=allocation, request=req)
            issues = validate_state(s)
            for e in issues:
                self.mark(e.field, e.row, e.col)
            if issues:
                first = issues[0]
                raise InvalidInputError(first.message, first.field, first.row, first.col)
            s.recompute_need()
        except InvalidInputError as e:
            self.mark(e.field, e.row, e.col)
            self.show_error(str(e))
            return False
        self.state = s
        self.need = [list(r) for r in s.need]
        return True

    # --------------------------- Các chức năng chính ---------------------------
    def run_safety(self, tables):
        if not self.apply_input(tables):
            return
        self.logger.info("Chạy thuật toán kiểm tra tính an toàn")
        self.last_safety = check_safety(self.state)
        self.safety = self.start_stepper(self.last_safety)
        self.show_banner("Đã chạy thuật toán kiểm tra tính an toàn: bấm Next để xem từng bước "
                         "hoặc \"Chạy hết\" để xem kết luận.", NEUTRAL)

    def run_detection(self, tables):
        if not self.apply_input(tables):
            return
        self.logger.info("Chạy thuật toán phát hiện bế tắc")
        self.last_detection = detect_deadlock(self.state)
        self.last_recovery = suggest_recovery(self.state)
        self.detect = self.start_stepper(self.last_detection.scan)
        self.deadlock_view = None
        self.show_banner("Đã chạy thuật toán phát hiện bế tắc: bấm Next để xem từng bước "
                         "hoặc \"Chạy hết\" để xem kết luận.", NEUTRAL)

    def start_stepper(self, result):
        self.logger.step(f"Step 1: khởi tạo Work := Available = {vec_to_string(result.initial_work)}, "
                         "Finish(i) := false")
        return Stepper(result)

    def step(self, panel, action):
        stepper = self.safety if panel == "safety" else self.detect
        if stepper is None:
            return
        if action == "next":
            self.next_step(panel, stepper)
        elif action == "all":
            while stepper.has_next():
                self.next_step(panel, stepper)
        elif action == "back":
            stepper.back()
        elif action == "reset":
            stepper.reset()

    def next_step(self, panel, stepper):
        if not stepper.has_next():
            return
        st = stepper.next()
        self.logger.step(describe_step(st, "Need" if panel == "safety" else "Request"))
        if stepper.finished():
            if panel == "safety":
                self.on_safety_finished(stepper.result)
            else:
                self.on_detection_finished()

    def on_safety_finished(self, r):
        if r.all_finished:
            self.show_banner("HỆ Ở TRẠNG THÁI AN TOÀN  -  Dãy an toàn (Safe Sequence): "
                             + join_processes(r.order), GOOD)
            self.logger.result("Hệ an toàn, dãy an toàn: " + join_processes(r.order))
        else:
            self.show_banner("HỆ Ở TRẠNG THÁI KHÔNG AN TOÀN  -  Không kết thúc được: "
                             + join_processes(r.unfinished), BAD)
            self.logger.result("Hệ không an toàn, các tiến trình không kết thúc được: "
                               + join_processes(r.unfinished))

    def on_detection_finished(self):
        if not self.last_detection:
            return
        d = self.last_detection
        self.deadlock_view = deadlock_view(self.state, d, self.last_recovery)
        if d.deadlock:
            self.show_banner("HỆ THỐNG GẶP BẾ TẮC  -  Các tiến trình bị bế tắc: "
                             + join_processes(d.deadlocked), BAD)
            self.logger.result("Bế tắc: " + join_processes(d.deadlocked))
            for note in self.last_recovery.notes:
                self.logger.info(note)
        else:
            self.show_banner("HỆ THỐNG KHÔNG BỊ BẾ TẮC", GOOD)
            self.logger.result("Không có bế tắc")

    def submit_request(self, tables, process, cells):
        try:
            vector = parse_table([cells], "Request", has_row_names=False)[0]
        except InvalidInputError as e:
            self.mark("RequestInput", 0, e.col)
            self.show_error(str(e))
            return
        if not self.apply_input(tables):
            return
        try:
            self.logger.info(f"{p_name(process)} yêu cầu {vec_to_string(vector)}")
            res = request_resources(self.state, process, vector)
        except InvalidInputError as e:
            self.show_error(str(e))
            return
        if res.reached_step4:
            for st in res.safety.steps:
                self.logger.step(describe_step(st, "Need"))
        self.logger.result(status_text(res.status))
        if res.status == RequestStatus.GRANTED:
            self.load_input(self.state)  # cập nhật Available, Allocation; đồng thời xóa kết quả cũ
            self.need = [list(r) for r in self.state.need]
            self.preset_request(process, vector)
            self.show_banner(f"ĐÃ PHÂN BỔ cho {p_name(process)}  -  hệ vẫn an toàn, dãy an toàn: "
                             + join_processes(res.safety.order), GOOD)
        else:
            self.show_banner(status_text(res.status), BAD)
        self.last_request = res
        self.request_view = request_view(res)
        self.extra["tab"] = 1  # tab Banker

    def run_rag(self, tables):
        if not self.apply_input(tables):
            return
        self.logger.info("Phát hiện bế tắc qua đồ thị RAG")
        r = self.last_rag = detect_by_rag(self.state)
        self.rag_view = rag_view(self.state.n, r)
        if not r.applicable:
            self.logger.warning(r.reason)
            self.show_banner("Không áp dụng được RAG: dữ liệu có tài nguyên nhiều thể hiện", NEUTRAL)
            return
        for line in r.log:
            self.logger.step(line)
        if r.deadlock:
            self.show_banner("ĐỒ THỊ CÓ CHU TRÌNH - HỆ BỊ BẾ TẮC  -  Tiến trình bị treo: "
                             + join_processes(r.deadlocked), BAD)
            self.logger.result("RAG: có chu trình, bế tắc " + join_processes(r.deadlocked))
        else:
            self.show_banner("ĐỒ THỊ KHÔNG CÓ CHU TRÌNH - HỆ KHÔNG BỊ BẾ TẮC", GOOD)
            self.logger.result("RAG: không có chu trình")

    # ------------------------------ Tiện ích (file) -------------------------------
    def load_sample(self, index):
        sample = sample_list()[index]
        self.load_input(sample.state)
        self.state = sample.state
        self.need = [list(r) for r in sample.state.need]
        if sample.request_process >= 0:
            self.preset_request(sample.request_process, sample.request_vector)
        self.logger.info("Tải dữ liệu mẫu: " + sample.name)
        self.show_banner(f"Đã tải: {sample.name}. {sample.description}", NEUTRAL)

    def open_file(self, name, content):
        try:
            s = read_state(content)
        except InvalidInputError as e:
            self.show_error(str(e))
            return
        self.load_input(s)
        self.state = s
        self.need = [list(r) for r in s.need]
        self.logger.info("Đã mở file " + name)
        self.show_banner("Đã mở file " + name, NEUTRAL)

    def save_file(self, tables):
        if not self.apply_input(tables):
            return
        self.extra["download"] = {"name": "du_lieu.txt", "type": "text/plain", "content": write_state(self.state)}
        self.logger.info("Đã lưu file du_lieu.txt")

    def reset(self):
        self.set_size(DEFAULT_N, DEFAULT_M)
        self.state = None
        self.logger.clear()
        self.new_log.clear()
        self.extra["clear_log"] = True
        self.extra["status"] = "Đã xóa toàn bộ dữ liệu"

    def export_report(self, tables):
        if not self.apply_input(tables):
            return
        content = build_html_report(self.state, safety=self.last_safety, request=self.last_request,
                                    detection=self.last_detection, recovery=self.last_recovery,
                                    rag=self.last_rag, log=self.logger)
        name = "bao_cao_mo_phong.html"
        self.extra["download"] = {"name": name, "type": "text/html", "content": content}
        self.extra["status"] = "Đã xuất báo cáo: " + name
        self.logger.info("Đã xuất báo cáo: " + name)


# ------------------------------ Dữ liệu hiển thị cho từng khung ------------------------------
def step_view(stepper, compared_name):
    if stepper is None:
        return None
    r = stepper.result
    shown = stepper.position
    rows = []
    for k, st in enumerate(r.steps[:shown]):
        new_round = k == 0 or r.steps[k - 1].round != st.round
        result = (f"Finish({st.process}) := true, Work := {vec_to_string(st.work_after)}"
                  if st.satisfied else f"{p_name(st.process)} đợi")
        rows.append({"satisfied": st.satisfied, "cells": [
            str(st.round) if new_round else "", p_name(st.process), vec_to_string(st.compared),
            vec_to_string(st.work_before), "Có" if st.satisfied else "Không", result]})

    cur = stepper.current()
    if cur is None:
        work = r.initial_work
        finish = [False] * (len(r.order) + len(r.unfinished))
    else:
        work = cur.work_after if cur.satisfied else cur.work_before
        finish = cur.finish

    conclusion = None
    if stepper.finished():
        if compared_name == "Need":
            text = ("Step 4: Finish(i) = true với mọi i => hệ ở trạng thái AN TOÀN. Dãy an toàn: "
                    + join_processes(r.order) if r.all_finished else
                    f"Step 4: còn tiến trình có Finish = false ({join_processes(r.unfinished)}) "
                    "=> hệ ở trạng thái KHÔNG AN TOÀN (có nguy cơ bế tắc)")
        else:
            text = ("Step 3: không có i nào có Finish(i) = false => hệ thống KHÔNG bị bế tắc"
                    if r.all_finished else
                    "Step 3: tồn tại Finish(i) = false => hệ thống GẶP BẾ TẮC: " + join_processes(r.unfinished))
        conclusion = {"text": text, "ok": r.all_finished}

    return {
        "rows": rows,
        "work": f"Bước {shown}/{stepper.total}   |   Work = {vec_to_string(work)}",
        "finish": finish,
        "has_next": stepper.has_next(),
        "has_back": stepper.has_back(),
        "conclusion": conclusion,
    }


def deadlock_view(s, d, plan):
    if not d.deadlock:
        return {"deadlock": False, "summary": "Không có tiến trình nào bị bế tắc."}
    return {
        "deadlock": True,
        "summary": "Các tiến trình bị bế tắc: " + join_processes(d.deadlocked),
        "held": [f"{p_name(i)}: đang giữ {vec_to_string(s.allocation[i])}, "
                 f"đang yêu cầu {vec_to_string(s.request[i])}" for i in d.deadlocked],
        "rows": [[str(k + 1), p_name(st.victim), vec_to_string(st.released),
                  join_processes(st.still_deadlocked) or "Hết bế tắc"] for k, st in enumerate(plan.steps)],
        "notes": plan.notes + ["Hoặc thông báo cho người điều hành (Operator) để tự xử lý."],
    }


def request_view(r):
    # Trả về HTML: mọi nội dung động đều do chương trình sinh từ số nguyên
    i = r.process
    before = r.before
    verdict = {True: "Thỏa mãn", False: "<b>Không</b>"}
    lines = [
        f"<b>{p_name(i)} yêu cầu Request = {vec_to_string(r.request)}</b>",
        f"Step 1: Request({i}) = {vec_to_string(r.request)} &lt;= Need = {vec_to_string(before.need[i])} ? "
        + verdict[less_equal(r.request, before.need[i])],
    ]
    if r.status != RequestStatus.ERROR_EXCEEDS_NEED:
        lines.append(f"Step 2: Request &lt;= Available = {vec_to_string(before.available)} ? "
                     + verdict[less_equal(r.request, before.available)])
    if r.reached_step4:
        t = r.tentative
        lines.append(f"Step 3: dự định phân bổ: Available = {vec_to_string(t.available)}, "
                     f"Allocation({i}) = {vec_to_string(t.allocation[i])}, Need({i}) = {vec_to_string(t.need[i])}")
        lines.append(f"Step 4: kiểm tra tính an toàn với Work = {vec_to_string(t.available)}:")
        lines.extend("&nbsp;&nbsp;- " + html.escape(describe_step(st, "Need")) for st in r.safety.steps)
        if r.safety.all_finished:
            lines.append("=&gt; An toàn, dãy an toàn: " + join_processes(r.safety.order))
        else:
            lines.append(f"=&gt; Không an toàn, {join_processes(r.safety.unfinished)} không kết thúc được. "
                         "Khôi phục trạng thái cũ.")
    return {"status": status_text(r.status), "ok": r.status == RequestStatus.GRANTED, "detail": "<br>".join(lines)}


def rag_view(n, r):
    view = {
        "n": n, "applicable": r.applicable, "reason": r.reason, "deadlock": r.deadlock,
        "wait_edges": r.wait_edges, "cycles": r.cycles, "in_cycle": r.in_cycle, "deadlocked": r.deadlocked,
        "summary": r.reason, "log": [],
    }
    if not r.applicable:
        return view
    edges = ", ".join(f"{p_name(a)} -> {p_name(b)}" for a, b in r.wait_edges)
    view["log"] = ["Cạnh đồ thị chờ: " + (edges or "không có")] + r.log
    if r.deadlock:
        cycles = "; ".join(" -> ".join(p_name(p) for p in c) for c in r.cycles)
        view["summary"] = f"Có bế tắc. Chu trình: {cycles}. Tiến trình bị treo: {join_processes(r.deadlocked)}"
    else:
        view["summary"] = "Đồ thị không có chu trình: hệ không bị bế tắc."
    return view


# ------------------------------------------ Route ------------------------------------------
# Một người dùng trên máy cá nhân: giữ trạng thái trong biến toàn cục, giống cửa sổ chính của bản Qt
controller = Controller()


def body():
    return request.get_json(silent=True) or {}


def reply():
    return jsonify(controller.view())


@app.route("/")
def index():
    return render_template("index.html", samples=[s.name for s in sample_list()])


@app.route("/init", methods=["POST"])
def init():
    global controller
    controller = Controller()
    controller.load_sample(0)  # mở chương trình với ví dụ giáo trình trang 52
    controller.extra["clear_log"] = True
    return reply()


@app.route("/new_table", methods=["POST"])
def new_table():
    data = body()
    n = parse_int(str(data.get("n", "")))
    m = parse_int(str(data.get("m", "")))
    n = DEFAULT_N if n is None else min(max(n, 1), MAX_N)
    m = DEFAULT_M if m is None else min(max(m, 1), MAX_M)
    controller.set_size(n, m)
    return reply()


@app.route("/load_sample", methods=["POST"])
def load_sample():
    controller.load_sample(int(body()["index"]))
    return reply()


@app.route("/open_file", methods=["POST"])
def open_file():
    data = body()
    controller.open_file(data["name"], data["content"])
    return reply()


@app.route("/save_file", methods=["POST"])
def save_file():
    controller.save_file(body()["tables"])
    return reply()


@app.route("/reset", methods=["POST"])
def reset():
    controller.reset()
    return reply()


@app.route("/export_report", methods=["POST"])
def export_report():
    controller.export_report(body()["tables"])
    return reply()


@app.route("/run_safety", methods=["POST"])
def run_safety():
    controller.run_safety(body()["tables"])
    return reply()


@app.route("/run_detection", methods=["POST"])
def run_detection():
    controller.run_detection(body()["tables"])
    return reply()


@app.route("/step", methods=["POST"])
def step():
    data = body()
    controller.step(data["panel"], data["action"])
    return reply()


@app.route("/request", methods=["POST"])
def submit_request():
    data = body()
    controller.submit_request(data["tables"], int(data["process"]), data["request"])
    return reply()


@app.route("/run_rag", methods=["POST"])
def run_rag():
    controller.run_rag(body()["tables"])
    return reply()


if __name__ == "__main__":
    print("App is running on: http://localhost:5000")
    app.run(port=5000)
