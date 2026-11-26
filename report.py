# report.py — xuất báo cáo mô phỏng ra HTML (mở bằng trình duyệt hoặc Word)
import html
from datetime import datetime

from models.banker import RequestStatus, status_text
from utility import join_processes, p_name, vec_to_string

STYLE = (
    "body{font-family:'Times New Roman',serif;font-size:13pt;max-width:1000px;margin:24px auto;color:#000}"
    "table{border-collapse:collapse;margin:8px 0 16px}th,td{border:1px solid #000;padding:3px 8px;text-align:center}"
    "th{background:#e7e6e6}tr.ok td{background:#eaf4ea}.safe{color:#1b5e20;font-weight:bold}"
    ".bad{color:#b71c1c;font-weight:bold}pre{font-size:11pt;background:#f5f5f5;padding:8px;white-space:pre-wrap}"
)


def _esc(text):
    return html.escape(text, quote=False)


def _matrix_table(out, s):
    out.append("<table><tr><th rowspan=2>Tiến trình</th>")
    for title in ("Allocation", "Max", "Need", "Request", "Available"):
        out.append(f"<th colspan={s.m}>{title}</th>")
    out.append("</tr><tr>")
    out.append("".join(f"<th>R{j}</th>" for j in range(s.m)) * 5)
    out.append("</tr>")
    for i in range(s.n):
        out.append(f"<tr><td>{p_name(i)}</td>")
        for matrix in (s.allocation, s.max, s.need, s.request):
            out.extend(f"<td>{x}</td>" for x in matrix[i])
        out.extend(f"<td>{s.available[j] if i == 0 else ''}</td>" for j in range(s.m))
        out.append("</tr>")
    out.append("</table>")


def _scan_table(out, r, col):
    out.append(f"<table><tr><th>Lần tìm</th><th>Tiến trình</th><th>{col}(i)</th><th>Work</th>"
               f"<th>{col}(i) &lt;= Work</th><th>Kết quả</th></tr>")
    for st in r.steps:
        result = (f"Finish({st.process}) := true, Work := {vec_to_string(st.work_after)}"
                  if st.satisfied else f"{p_name(st.process)} đợi")
        out.append(f"<tr{' class=ok' if st.satisfied else ''}><td>{st.round}</td><td>{p_name(st.process)}</td>"
                   f"<td>{vec_to_string(st.compared)}</td><td>{vec_to_string(st.work_before)}</td>"
                   f"<td>{'Có' if st.satisfied else 'Không'}</td><td>{result}</td></tr>")
    out.append("</table>")


def build_html_report(state, safety=None, request=None, detection=None, recovery=None, rag=None, log=None):
    # Phần nào chưa chạy (None) thì không xuất hiện trong báo cáo
    s = state
    when = datetime.now().strftime("%d/%m/%Y %H:%M")
    out = ["<!DOCTYPE html><html lang=vi><head><meta charset=utf-8><title>Báo cáo mô phỏng bế tắc</title>",
           f"<style>{STYLE}</style></head><body>",
           f"<h2>Báo cáo mô phỏng các phương pháp kiểm tra xác định bế tắc</h2><p>Thời điểm xuất: {when}</p>",
           f"<h3>1. Trạng thái hệ thống</h3><p>Số tiến trình n = {s.n}, số kiểu tài nguyên m = {s.m}. "
           f"Tổng tài nguyên của hệ: {vec_to_string(s.total_resources())}.</p>"]
    _matrix_table(out, s)

    if safety:
        out.append("<h3>2. Thuật toán kiểm tra tính an toàn</h3>")
        _scan_table(out, safety, "Need")
        if safety.all_finished:
            out.append(f"<p class=safe>Hệ ở trạng thái an toàn. Dãy an toàn: {join_processes(safety.order)}.</p>")
        else:
            out.append("<p class=bad>Hệ ở trạng thái không an toàn. Các tiến trình chưa kết thúc được: "
                       f"{join_processes(safety.unfinished)}.</p>")

    if request:
        out.append("<h3>3. Thuật toán chuyển hệ sang trạng thái an toàn (Banker)</h3>"
                   f"<p>{p_name(request.process)} yêu cầu Request = {vec_to_string(request.request)}.</p>")
        if request.reached_step4:
            out.append("<p>Step 3 - trạng thái dự định:</p>")
            _matrix_table(out, request.tentative)
            out.append("<p>Step 4 - kiểm tra tính an toàn của trạng thái dự định:</p>")
            _scan_table(out, request.safety, "Need")
        css = "safe" if request.status == RequestStatus.GRANTED else "bad"
        out.append(f"<p class={css}>{_esc(status_text(request.status))}</p>")

    if detection:
        out.append("<h3>4. Thuật toán phát hiện bế tắc</h3>")
        _scan_table(out, detection.scan, "Request")
        if detection.deadlock:
            out.append("<p class=bad>Hệ thống gặp bế tắc. Các tiến trình bị bế tắc: "
                       f"{join_processes(detection.deadlocked)}.</p>")
        else:
            out.append("<p class=safe>Hệ thống không bị bế tắc.</p>")
        if recovery and recovery.steps:
            out.append("<p>Gợi ý xử lý:</p><ul>")
            out.extend(f"<li>{_esc(n)}</li>" for n in recovery.notes)
            out.append("</ul>")

    if rag:
        out.append("<h3>5. Phát hiện bế tắc qua đồ thị RAG (tài nguyên đơn thể)</h3>")
        if not rag.applicable:
            out.append(f"<p>{_esc(rag.reason)}</p>")
        else:
            edges = ", ".join(f"{p_name(a)} -&gt; {p_name(b)}" for a, b in rag.wait_edges)
            out.append(f"<p>Cạnh của đồ thị chờ: {edges or 'không có'}.</p>")
            if rag.deadlock:
                for cycle in rag.cycles:
                    out.append(f"<p class=bad>Chu trình: {' -&gt; '.join(p_name(p) for p in cycle)}</p>")
                out.append(f"<p>Tiến trình bị treo: {join_processes(rag.deadlocked)}.</p>")
            else:
                out.append("<p class=safe>Đồ thị không có chu trình: hệ không bị bế tắc.</p>")

    if log and log.entries:
        out.append(f"<h3>6. Nhật ký thực thi</h3><pre>{_esc(log.to_text())}</pre>")
    out.append("</body></html>")
    return "".join(out)
