// Giao diện chỉ đọc bảng nhập, gửi lên server và vẽ lại theo dữ liệu trả về
const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";
const MARK_TABLES = {
    Available: "t-available", Allocation: "t-allocation", Max: "t-max",
    Request: "t-request", RequestInput: "t-reqinput",
};

function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
}

// Gửi lần lượt để bấm nhanh nhiều lần không làm kết quả về sai thứ tự
let queue = Promise.resolve();

function post(url, makeBody) {
    queue = queue.then(async () => {
        const res = await fetch(url, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(makeBody ? makeBody() : {}),
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        render(await res.json());
    }).catch((e) => { $("status").textContent = "Lỗi máy chủ: " + e.message; });
}

// ------------------------------- Bảng ma trận ----------------------------------
function buildTable(id, rows, rowNames, editable) {
    const table = el("table", undefined, "grid matrix");
    const head = table.createTHead().insertRow();
    if (rowNames) head.appendChild(el("th", ""));
    rows[0].forEach((_, j) => head.appendChild(el("th", "R" + j)));
    const tbody = table.createTBody();
    rows.forEach((row, i) => {
        const tr = tbody.insertRow();
        if (rowNames) tr.appendChild(el("th", "P" + i));
        row.forEach((value, j) => {
            const td = tr.insertCell();
            td.dataset.row = i;
            td.dataset.col = j;
            if (editable) {
                const input = el("input");
                input.value = value;
                input.addEventListener("focus", () => input.select());
                td.appendChild(input);
            } else {
                td.textContent = value;
            }
        });
    });
    $(id).replaceChildren(table);
}

function readTable(id) {
    return [...$(id).querySelectorAll("tbody tr")]
        .map((tr) => [...tr.querySelectorAll("input")].map((input) => input.value));
}

const readTables = () => ({
    available: readTable("t-available"),
    allocation: readTable("t-allocation"),
    max: readTable("t-max"),
    request: readTable("t-request"),
});

function applyMarks(marks) {
    document.querySelectorAll("td.error").forEach((td) => td.classList.remove("error"));
    for (const m of marks) {
        for (const td of $(MARK_TABLES[m.table]).querySelectorAll("td")) {
            if ((m.row < 0 || m.row === +td.dataset.row) && (m.col < 0 || m.col === +td.dataset.col)) {
                td.classList.add("error");
            }
        }
    }
}

function loadInput(input) {
    $("size-n").value = input.n;
    $("size-m").value = input.m;
    buildTable("t-available", input.available, false, true);
    buildTable("t-allocation", input.allocation, true, true);
    buildTable("t-max", input.max, true, true);
    buildTable("t-request", input.request, true, true);
    buildTable("t-reqinput", [input.request_vector], false, true);
    $("process").replaceChildren(...input.allocation.map((_, i) => new Option("P" + i, i)));
    $("process").value = input.request_process;
}

// ------------------------------- Từng khung ----------------------------------
function showResult(node, text, ok) {
    node.hidden = !text;
    node.textContent = text || "";
    node.classList.toggle("good", ok === true);
    node.classList.toggle("bad", ok === false);
}

function renderRequest(r) {
    showResult($("request-status"), r && r.status, r ? r.ok : undefined);
    $("request-detail").innerHTML = r ? r.detail : "";
}

function renderSteps(panel, view) {
    const q = (selector) => panel.querySelector(selector);
    const button = (action) => q(`[data-action="${action}"]`);
    button("next").disabled = button("all").disabled = !(view && view.has_next);
    button("back").disabled = button("reset").disabled = !(view && view.has_back);

    q(".work").textContent = view ? view.work : "Bấm \"Chạy thuật toán\" rồi dùng Next / Back để xem từng bước.";
    q(".finish").replaceChildren();
    if (view) {
        q(".finish").append("Finish = [");
        view.finish.forEach((done, i) => {
            if (i) q(".finish").append(", ");
            q(".finish").append(done ? el("b", "T", "true") : "F");
        });
        q(".finish").append("]");
    }

    const rows = view ? view.rows : [];
    q("tbody").replaceChildren(...rows.map((row, k) => {
        const tr = el("tr", undefined, row.satisfied ? "ok" : "");
        if (k === rows.length - 1) tr.classList.add("current");
        tr.append(...row.cells.map((c) => el("td", c)));
        return tr;
    }));
    const wrap = q(".table-wrap");
    wrap.scrollTop = wrap.scrollHeight;

    const c = view && view.conclusion;
    showResult(q(".conclusion"), c && c.text, c ? c.ok : undefined);
}

function renderDeadlock(view) {
    const box = $("deadlock");
    if (!view) {
        box.replaceChildren(el("p", "Chạy thuật toán phát hiện bế tắc để xem danh sách tiến trình bị bế tắc và gợi ý xử lý."));
        return;
    }
    if (!view.deadlock) {
        box.replaceChildren(el("p", view.summary, "text-good"));
        return;
    }
    const held = el("ul", undefined, "text-bad");
    held.append(...view.held.map((t) => el("li", t)));
    const table = el("table", undefined, "grid");
    const head = table.createTHead().insertRow();
    head.append(...["Bước đình chỉ", "Tiến trình", "Thu hồi tài nguyên", "Còn bế tắc"].map((t) => el("th", t)));
    const tbody = table.createTBody();
    for (const row of view.rows) tbody.insertRow().append(...row.map((c) => el("td", c)));
    const notes = el("ul");
    notes.append(...view.notes.map((t) => el("li", t)));
    box.replaceChildren(el("p", view.summary, "text-bad strong"), held, table,
        el("p", "Gợi ý phương án xử lý:", "strong"), notes);
}

function svg(tag, attrs, text) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
}

function drawGraph(view) {
    const canvas = $("rag-view");
    canvas.replaceChildren();
    if (!view || !view.applicable) {
        canvas.append(svg("text", {x: 300, y: 210, class: "placeholder"},
            view ? "Không áp dụng được đồ thị RAG cho dữ liệu này." : "Bấm \"Vẽ đồ thị và kiểm tra\" để dựng đồ thị chờ."));
        return;
    }
    // Đặt các tiến trình trên một đường tròn
    const R = 420 * 0.36, node = 22;
    const pos = Array.from({length: view.n}, (_, i) => {
        const a = -Math.PI / 2 + 2 * Math.PI * i / view.n;
        return [300 + R * Math.cos(a), 200 + R * Math.sin(a)];
    });
    const onCycle = (a, b) => view.cycles.some((c) => c.some((p, k) => p === a && c[k + 1] === b));

    for (const [a, b] of view.wait_edges) {
        const dx = pos[b][0] - pos[a][0], dy = pos[b][1] - pos[a][1];
        const len = Math.hypot(dx, dy);
        if (len < 1) continue;
        const ux = dx / len, uy = dy / len;
        const sx = pos[a][0] + ux * node, sy = pos[a][1] + uy * node;
        const ex = pos[b][0] - ux * node, ey = pos[b][1] - uy * node;
        const kind = onCycle(a, b) ? "edge cycle" : "edge";
        canvas.append(svg("line", {x1: sx, y1: sy, x2: ex, y2: ey, class: kind}));
        const left = `${ex - ux * 12 - uy * 6},${ey - uy * 12 + ux * 6}`;
        const right = `${ex - ux * 12 + uy * 6},${ey - uy * 12 - ux * 6}`;
        canvas.append(svg("polygon", {points: `${ex},${ey} ${left} ${right}`, class: kind}));
    }
    pos.forEach(([x, y], i) => {
        const kind = view.in_cycle.includes(i) ? "cycle" : view.deadlocked.includes(i) ? "blocked" : "";
        canvas.append(svg("circle", {cx: x, cy: y, r: node, class: "node " + kind}));
        canvas.append(svg("text", {x: x, y: y, class: "node-label"}, "P" + i));
    });
    canvas.append(svg("text", {x: 10, y: 410, class: "legend"},
        "Đỏ: tiến trình/cạnh trên chu trình   Cam: bị treo do chờ chu trình   Xanh: bình thường"));
}

function renderRag(view) {
    drawGraph(view);
    const summary = $("rag-summary");
    summary.textContent = view ? view.summary : "";
    summary.className = !view ? "" : !view.applicable ? "text-warn" : view.deadlock ? "text-bad" : "text-good";
    $("rag-log").textContent = view ? view.log.join("\n") : "";
}

function selectTab(index) {
    document.querySelectorAll(".tab-btn").forEach((t, i) => t.classList.toggle("active", i === index));
    document.querySelectorAll(".tab-content").forEach((p, i) => p.classList.toggle("hidden", i !== index));
}

function download(file) {
    const link = el("a");
    link.href = URL.createObjectURL(new Blob([file.content], {type: file.type + ";charset=utf-8"}));
    link.download = file.name;
    link.click();
    URL.revokeObjectURL(link.href);
}

function render(view) {
    if (view.input) loadInput(view.input);
    buildTable("t-need", view.need, true, false);
    applyMarks(view.marks);

    $("banner").textContent = view.banner.text;
    $("banner").className = "banner kind-" + view.banner.kind;

    renderRequest(view.request_result);
    document.querySelectorAll(".step-panel").forEach((p) => renderSteps(p, view[p.dataset.panel]));
    renderDeadlock(view.deadlock);
    renderRag(view.rag);

    const log = $("log");
    if (view.clear_log) log.textContent = "";
    log.append(...view.log.map((line) => line + "\n"));
    log.scrollTop = log.scrollHeight;

    $("status").textContent = view.status || "";
    if (view.tab !== undefined) selectTab(view.tab);
    // Ô lỗi của bảng nhập nằm ở tab Dữ liệu -> chuyển sang đó để thấy ô tô đỏ
    if (view.marks.some((m) => m.table !== "RequestInput")) selectTab(0);
    if (view.download) download(view.download);
}

// ------------------------------- Sự kiện ----------------------------------
document.querySelectorAll(".step-panel").forEach((panel) => {
    panel.appendChild($("step-template").content.cloneNode(true));
    const name = panel.dataset.name;
    panel.querySelector("thead tr").append(
        ...["Lần tìm", "Tiến trình", name + "(i)", "Work", name + "(i) <= Work", "Kết quả"].map((t) => el("th", t)));
    panel.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
        const action = button.dataset.action;
        if (action === "run") post(panel.dataset.run, () => ({tables: readTables()}));
        else post("/step", () => ({panel: panel.dataset.panel, action}));
    }));
});

document.querySelectorAll(".tab-btn").forEach((t, i) => t.addEventListener("click", () => selectTab(i)));

$("btn-load-sample").addEventListener("click", () => post("/load_sample", () => ({index: $("sample").value})));
$("btn-new-table").addEventListener("click",
    () => post("/new_table", () => ({n: $("size-n").value, m: $("size-m").value})));
$("btn-save").addEventListener("click", () => post("/save_file", () => ({tables: readTables()})));
$("btn-export").addEventListener("click", () => post("/export_report", () => ({tables: readTables()})));
$("btn-reset").addEventListener("click", () => post("/reset"));
$("btn-rag").addEventListener("click", () => post("/run_rag", () => ({tables: readTables()})));
$("btn-request").addEventListener("click", () => post("/request", () => ({
    tables: readTables(), process: $("process").value, request: readTable("t-reqinput")[0],
})));

$("btn-open").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", async () => {
    const file = $("file-input").files[0];
    if (!file) return;
    const content = await file.text();
    $("file-input").value = "";
    post("/open_file", () => ({name: file.name, content}));
});

post("/init");
