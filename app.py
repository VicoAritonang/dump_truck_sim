import streamlit as st
import heapq
import random
import pandas as pd
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------------------------
st.set_page_config(page_title="Dump Truck Simulation", layout="wide")

# ---------------------------------------------------------------------------------
# CUSTOM CSS (visual style)
# ---------------------------------------------------------------------------------
CUSTOM_CSS = """
.status-card {
    background: #0f172a;
    color: #f8fafc;
    border: 1px solid #1e293b;
    border-radius: 1rem;
    padding: 1rem 1.25rem;
    font-family: ui-rounded, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    box-shadow: 0 20px 40px rgb(0 0 0 / 0.4);
    min-height: 140px;
}
.status-title {
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: -0.03em;
    color: #94a3b8;
    text-transform: uppercase;
    margin-bottom: .25rem;
}
.status-body {
    font-size: 1rem;
    font-weight: 500;
    color: #f8fafc;
    line-height: 1.4;
    margin-bottom: .5rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
}
.badge {
    border-radius: .5rem;
    padding: .4rem .6rem;
    font-size: .8rem;
    font-weight: 500;
    line-height: 1;
    display: inline-block;
}
.badge-idle {
    background: rgba(16,185,129,.12);
    color: rgb(16,185,129);
    border: 1px solid rgba(16,185,129,.4);
}
.badge-busy {
    background: rgba(244,63,94,.12);
    color: rgb(244,63,94);
    border: 1px solid rgba(244,63,94,.4);
}
.truck-chip {
    background: rgba(96,165,250,.12);
    color: rgb(96,165,250);
    border: 1px solid rgba(96,165,250,.4);
    border-radius: .5rem;
    padding: .4rem .6rem;
    font-size: .8rem;
    font-weight: 500;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    gap: .4rem;
}
.pipeline-diagram {
    background: radial-gradient(circle at 20% 20%, #1e2638 0%, #0b0f19 60%);
    border-radius: 1rem;
    border: 1px solid #1e293b;
    padding: 1rem 1.5rem;
    box-shadow: 0 24px 48px rgb(0 0 0 / .6);
    color: #e2e8f0;
    font-family: ui-rounded, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto;
}
.stage-box {
    background: rgba(15,23,42,.6);
    border: 1px solid rgba(148,163,184,.2);
    border-radius: .75rem;
    padding: .75rem 1rem;
    flex: 1;
    min-width: 140px;
    text-align: center;
}
.stage-title {
    font-size: .8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: -0.03em;
    color: #94a3b8;
    margin-bottom: .25rem;
}
.stage-icon {
    font-size: 1.2rem;
    line-height: 1.2rem;
}
.stage-content {
    font-size: .8rem;
    line-height: 1.3;
    color: #f8fafc;
}
.arrow {
    font-size: 1.5rem;
    line-height: 2rem;
    color: #475569;
    font-weight: 500;
    padding: 0 .5rem;
}
.metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit,minmax(180px,1fr));
    gap: 1rem;
}
.metric-card {
    background: #0f172a;
    border-radius: .75rem;
    border: 1px solid #1e293b;
    padding: .75rem 1rem;
    box-shadow: 0 20px 40px rgb(0 0 0 / 0.4);
}
.metric-label {
    font-size: .7rem;
    text-transform: uppercase;
    font-weight: 600;
    color: #94a3b8;
    margin-bottom: .25rem;
    letter-spacing: -0.03em;
}
.metric-value {
    font-size: 1.4rem;
    line-height: 1.2;
    font-weight: 600;
    color: #f8fafc;
}
.metric-suffix {
    font-size: .75rem;
    font-weight: 500;
    color: #64748b;
    margin-left: .25rem;
}
"""

# ---------------------------------------------------------------------------------
# SAMPLING UTIL
# ---------------------------------------------------------------------------------
def sample_from_distribution(options):
    """
    options: list of (value, prob_percent)
    returns sampled value based on probability weights
    """
    values = [opt[0] for opt in options]
    weights = [opt[1] for opt in options]
    total_w = sum(weights)
    if total_w <= 0:
        return values[0]
    r = random.uniform(0, total_w)
    cum = 0.0
    for v, w in zip(values, weights):
        cum += w
        if r <= cum:
            return v
    return values[-1]

# ---------------------------------------------------------------------------------
# SIMULATION CORE (1 replikasi, menghasilkan timeline event-by-event)
# ---------------------------------------------------------------------------------
def run_simulation_with_timeline(
    dist_loader_A,
    dist_loader_B,
    dist_scale,
    travel_time_value,
    total_time,
    n_trucks=6,
):
    # Tidak ada random.seed() di sini -> biarkan RNG default Python (acak tiap run)

    clock = 0.0

    loader_queue = [i for i in range(n_trucks)]
    scale_queue = []

    loaderA_busy = False
    loaderB_busy = False
    scale_busy = False

    loaderA_truck = None
    loaderB_truck = None
    scale_truck = None

    trucks = []
    for i in range(n_trucks):
        trucks.append({
            "id": i,
            "state": "QUEUE_LOADER",
            "last_queue_enter_loader": 0.0,
            "total_wait_loader": 0.0,
            "loader_visits": 0,

            "last_queue_enter_scale": None,
            "total_wait_scale": 0.0,
            "scale_visits": 0,

            "travel_end_time": None,
        })

    loaderA_busy_time = 0.0
    loaderB_busy_time = 0.0
    scale_busy_time   = 0.0

    fel = []
    _ev_counter = 0

    event_log = []
    timeline_steps = []

    def schedule(time, ev_type, truck_id):
        nonlocal _ev_counter
        if time > total_time:
            return
        heapq.heappush(fel, (time, _ev_counter, ev_type, truck_id))
        _ev_counter += 1

    def avg_wait_so_far(trucks_list, target="loader"):
        total_wait = 0.0
        total_visit = 0
        if target == "loader":
            for tr in trucks_list:
                total_wait += tr["total_wait_loader"]
                total_visit += tr["loader_visits"]
        else:
            for tr in trucks_list:
                total_wait += tr["total_wait_scale"]
                total_visit += tr["scale_visits"]
        if total_visit == 0:
            return 0.0
        return total_wait / total_visit

    def log_event(ev_type, t_id, note=""):
        event_log.append({
            "time": clock,
            "event": ev_type,
            "truck": t_id,
            "note": note,
            "loader_queue": list(loader_queue),
            "scale_queue": list(scale_queue),
            "loaderA_busy": loaderA_busy,
            "loaderB_busy": loaderB_busy,
            "scale_busy": scale_busy,
            "loaderA_truck": loaderA_truck,
            "loaderB_truck": loaderB_truck,
            "scale_truck": scale_truck,
        })

    def snapshot_state():
        snap = {
            "clock": clock,
            "event": event_log[-1]["event"] if event_log else None,
            "truck": event_log[-1]["truck"] if event_log else None,
            "note": event_log[-1]["note"] if event_log else "",

            "loader_queue": list(loader_queue),
            "scale_queue": list(scale_queue),
            "traveling": [tr["id"] for tr in trucks if tr["state"] == "TRAVEL"],

            "loaderA_busy": loaderA_busy,
            "loaderB_busy": loaderB_busy,
            "scale_busy": scale_busy,

            "loaderA_truck": loaderA_truck,
            "loaderB_truck": loaderB_truck,
            "scale_truck": scale_truck,

            "loaderA_busy_time": loaderA_busy_time,
            "loaderB_busy_time": loaderB_busy_time,
            "scale_busy_time":   scale_busy_time,

            "avg_loader_wait_so_far": avg_wait_so_far(trucks, "loader"),
            "avg_scale_wait_so_far":  avg_wait_so_far(trucks, "scale"),
        }
        timeline_steps.append(snap)

    def try_assign_loader():
        nonlocal loaderA_busy, loaderA_truck, loaderB_busy, loaderB_truck, clock

        # Loader A
        if (not loaderA_busy) and len(loader_queue) > 0:
            t_id = loader_queue.pop(0)
            loaderA_busy = True
            loaderA_truck = t_id

            truck = trucks[t_id]
            if truck["state"] == "QUEUE_LOADER":
                wait = clock - truck["last_queue_enter_loader"]
                truck["total_wait_loader"] += wait
            truck["loader_visits"] += 1
            truck["state"] = "LOADING_A"

            service = sample_from_distribution(dist_loader_A)
            schedule(clock + service, "END_LOAD_A", t_id)
            log_event("START_LOAD_A", t_id, f"svc={service}m")

        # Loader B
        if (not loaderB_busy) and len(loader_queue) > 0:
            t_id = loader_queue.pop(0)
            loaderB_busy = True
            loaderB_truck = t_id

            truck = trucks[t_id]
            if truck["state"] == "QUEUE_LOADER":
                wait = clock - truck["last_queue_enter_loader"]
                truck["total_wait_loader"] += wait
            truck["loader_visits"] += 1
            truck["state"] = "LOADING_B"

            service = sample_from_distribution(dist_loader_B)
            schedule(clock + service, "END_LOAD_B", t_id)
            log_event("START_LOAD_B", t_id, f"svc={service}m")

    def try_assign_scale():
        nonlocal scale_busy, scale_truck, clock

        if (not scale_busy) and len(scale_queue) > 0:
            t_id = scale_queue.pop(0)
            scale_busy = True
            scale_truck = t_id

            truck = trucks[t_id]
            if truck["state"] == "QUEUE_SCALE":
                wait = clock - truck["last_queue_enter_scale"]
                truck["total_wait_scale"] += wait
            truck["scale_visits"] += 1
            truck["state"] = "SCALING"

            service = sample_from_distribution(dist_scale)
            schedule(clock + service, "END_SCALE", t_id)
            log_event("START_SCALE", t_id, f"svc={service}m")

    # Seed event awal
    schedule(0.0, "CHECK_ASSIGN", None)

    while fel:
        ev_time, _, ev_type, t_id = heapq.heappop(fel)
        if ev_time > total_time:
            break

        # Update akumulasi busy time untuk utilization
        dt = ev_time - clock
        if dt < 0:
            dt = 0
        if loaderA_busy:
            loaderA_busy_time += dt
        if loaderB_busy:
            loaderB_busy_time += dt
        if scale_busy:
            scale_busy_time += dt

        # Maju clock
        clock = ev_time

        # Proses event
        if ev_type == "CHECK_ASSIGN":
            try_assign_loader()
            try_assign_scale()
            log_event("CHECK_ASSIGN", None, "")

        elif ev_type == "END_LOAD_A":
            log_event("END_LOAD_A", t_id, "")
            loaderA_busy = False
            loaderA_truck = None

            trucks[t_id]["state"] = "QUEUE_SCALE"
            trucks[t_id]["last_queue_enter_scale"] = clock
            scale_queue.append(t_id)

            schedule(clock, "CHECK_ASSIGN", None)
            try_assign_scale()

        elif ev_type == "END_LOAD_B":
            log_event("END_LOAD_B", t_id, "")
            loaderB_busy = False
            loaderB_truck = None

            trucks[t_id]["state"] = "QUEUE_SCALE"
            trucks[t_id]["last_queue_enter_scale"] = clock
            scale_queue.append(t_id)

            schedule(clock, "CHECK_ASSIGN", None)
            try_assign_scale()

        elif ev_type == "END_SCALE":
            log_event("END_SCALE", t_id, "")
            scale_busy = False
            scale_truck = None

            trucks[t_id]["state"] = "TRAVEL"
            travel_end = clock + travel_time_value
            trucks[t_id]["travel_end_time"] = travel_end
            schedule(travel_end, "END_TRAVEL", t_id)

            schedule(clock, "CHECK_ASSIGN", None)

        elif ev_type == "END_TRAVEL":
            log_event("END_TRAVEL", t_id, "")
            trucks[t_id]["state"] = "QUEUE_LOADER"
            trucks[t_id]["last_queue_enter_loader"] = clock
            trucks[t_id]["travel_end_time"] = None
            loader_queue.append(t_id)

            schedule(clock, "CHECK_ASSIGN", None)

        # simpan snapshot kondisi setelah event diproses
        snapshot_state()

    # Kalkulasi final metrics dari run ini
    sim_runtime = max(clock, 1e-9)
    util_A = loaderA_busy_time / sim_runtime
    util_B = loaderB_busy_time / sim_runtime
    util_scale = scale_busy_time / sim_runtime

    total_loader_wait = 0.0
    total_loader_visits = 0
    total_scale_wait = 0.0
    total_scale_visits = 0
    for tr in trucks:
        total_loader_wait += tr["total_wait_loader"]
        total_loader_visits += tr["loader_visits"]
        total_scale_wait += tr["total_wait_scale"]
        total_scale_visits += tr["scale_visits"]

    avg_loader_wait_final = (total_loader_wait / total_loader_visits) if total_loader_visits > 0 else 0.0
    avg_scale_wait_final = (total_scale_wait / total_scale_visits) if total_scale_visits > 0 else 0.0

    final_metrics = {
        "avg_loader_queue_wait": avg_loader_wait_final,
        "avg_scale_queue_wait": avg_scale_wait_final,
        "util_loader_A": util_A,
        "util_loader_B": util_B,
        "util_scale": util_scale,
        "sim_end_time": clock,
    }

    return final_metrics, timeline_steps, event_log, trucks


# ---------------------------------------------------------------------------------
# SESSION STATE INIT (termasuk distribusi dinamis & hasil simulasi)
# ---------------------------------------------------------------------------------

# Distribusi default (set sekali)
if "loaderA_dist" not in st.session_state:
    st.session_state.loaderA_dist = [
        {"time": 4.0, "prob": 25.0},
        {"time": 5.0, "prob": 40.0},
        {"time": 6.0, "prob": 35.0},
    ]
if "loaderB_dist" not in st.session_state:
    st.session_state.loaderB_dist = [
        {"time": 4.0, "prob": 35.0},
        {"time": 5.0, "prob": 40.0},
        {"time": 6.0, "prob": 25.0},
    ]
if "scale_dist" not in st.session_state:
    st.session_state.scale_dist = [
        {"time": 4.0, "prob": 30.0},
        {"time": 5.0, "prob": 45.0},
        {"time": 6.0, "prob": 25.0},
    ]

# state hasil simulasi
if "timeline_steps" not in st.session_state:
    st.session_state.timeline_steps = []
if "final_metrics_avg" not in st.session_state:
    st.session_state.final_metrics_avg = {}
if "event_log" not in st.session_state:
    st.session_state.event_log = []
if "trucks_final" not in st.session_state:
    st.session_state.trucks_final = []
if "event_idx" not in st.session_state:
    st.session_state.event_idx = 0

# ---------------------------------------------------------------------------------
# SIDEBAR INPUT FORM
# ---------------------------------------------------------------------------------

st.title("🚧 Dump Truck Cyclic Haulage Simulation (Step Replay + Multi-Run Avg)")
st.caption(
    "Run Simulation untuk 1 atau lebih replikasi.\n"
    "• Slider / Next = lihat urutan event dari replikasi pertama.\n"
    "• Final Performance = rata-rata dari semua replikasi.\n"
    "• Nilai ditampilkan (as-is) → (dibulatkan)."
)

st.sidebar.header("Simulation Inputs")

def render_distribution_editor(label, state_key):
    st.sidebar.markdown(f"### {label} Time Distribution")
    with st.sidebar.expander(f"{label} Durasi (menit) dan Prob (%)", expanded=False):
        dist_list = st.session_state[state_key]

        to_delete_idx = None
        for i, row in enumerate(dist_list):
            c1, c2, c3 = st.columns([1,1,0.4])
            with c1:
                new_time = st.number_input(
                    f"{label} Durasi {i+1} (menit)",
                    key=f"{state_key}_time_{i}",
                    min_value=0.0,
                    value=float(row["time"]),
                    step=0.5,
                )
            with c2:
                new_prob = st.number_input(
                    f"Prob {i+1} (%)",
                    key=f"{state_key}_prob_{i}",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(row["prob"]),
                    step=1.0,
                )
            with c3:
                if st.button("🗑️", key=f"{state_key}_del_{i}"):
                    to_delete_idx = i

            row["time"] = new_time
            row["prob"] = new_prob

        # hapus baris jika tombol delete dipencet (tapi jangan kalau tinggal 1 baris)
        if to_delete_idx is not None and len(dist_list) > 1:
            dist_list.pop(to_delete_idx)

        # tombol tambah baris baru
        if st.button(f"➕ Add Option {label}", key=f"{state_key}_add"):
            dist_list.append({"time": 0.0, "prob": 0.0})

# editor distribusi service time
render_distribution_editor("Loader A", "loaderA_dist")
render_distribution_editor("Loader B", "loaderB_dist")
render_distribution_editor("Scale", "scale_dist")

st.sidebar.markdown("### Traveling & Runtime")
travel_time_value = st.sidebar.number_input(
    "Travel Time (menit, deterministik)",
    min_value=0.0,
    value=10.0,
    step=0.5,
    key="travel_time_value_input"
)
total_time = st.sidebar.number_input(
    "Total Simulation Time (menit)",
    min_value=1.0,
    value=120.0,
    step=10.0,
    key="total_time_input"
)

st.sidebar.markdown("### Replications")
num_runs = st.sidebar.number_input(
    "Jumlah replikasi (n)",
    min_value=1,
    value=1,
    step=1,
    key="num_runs_input"
)

run_button = st.sidebar.button("▶ Run Simulation")

# ---------------------------------------------------------------------------------
# KETIKA RUN SIMULATION DIKLIK
# ---------------------------------------------------------------------------------

if run_button:
    # Siapkan distribusi (list of (time,prob)) dari sidebar editable state
    dist_loader_A = [(row["time"], row["prob"]) for row in st.session_state.loaderA_dist]
    dist_loader_B = [(row["time"], row["prob"]) for row in st.session_state.loaderB_dist]
    dist_scale    = [(row["time"], row["prob"]) for row in st.session_state.scale_dist]

    # akumulator untuk rata-rata
    sum_avg_loader_wait = 0.0
    sum_avg_scale_wait  = 0.0
    sum_util_A          = 0.0
    sum_util_B          = 0.0
    sum_util_scale      = 0.0
    sum_sim_end_time    = 0.0

    timeline_steps_first = None
    event_log_first = None
    trucks_final_first = None
    final_metrics_first = None

    for run_i in range(num_runs):
        final_metrics_i, timeline_steps_i, event_log_i, trucks_final_i = run_simulation_with_timeline(
            dist_loader_A=dist_loader_A,
            dist_loader_B=dist_loader_B,
            dist_scale=dist_scale,
            travel_time_value=travel_time_value,
            total_time=total_time,
            n_trucks=6,
        )

        # kumpulkan statistik untuk averaging
        sum_avg_loader_wait += final_metrics_i["avg_loader_queue_wait"]
        sum_avg_scale_wait  += final_metrics_i["avg_scale_queue_wait"]
        sum_util_A          += final_metrics_i["util_loader_A"]
        sum_util_B          += final_metrics_i["util_loader_B"]
        sum_util_scale      += final_metrics_i["util_scale"]
        sum_sim_end_time    += final_metrics_i["sim_end_time"]

        # simpan run pertama agar bisa divisualisasikan step-by-step
        if run_i == 0:
            timeline_steps_first = timeline_steps_i
            event_log_first = event_log_i
            trucks_final_first = trucks_final_i
            final_metrics_first = final_metrics_i

    # hitung rata-rata
    n = float(num_runs)
    final_metrics_avg = {
        "avg_loader_queue_wait": sum_avg_loader_wait / n,
        "avg_scale_queue_wait":  sum_avg_scale_wait  / n,
        "util_loader_A":         sum_util_A          / n,
        "util_loader_B":         sum_util_B          / n,
        "util_scale":            sum_util_scale      / n,
        "sim_end_time":          sum_sim_end_time    / n,
        "replications":          num_runs,
    }

    # update session_state agar UI pakai data ini
    st.session_state.timeline_steps = timeline_steps_first
    st.session_state.final_metrics_avg = final_metrics_avg
    st.session_state.event_log = event_log_first
    st.session_state.trucks_final = trucks_final_first
    st.session_state.event_idx = 0


# ---------------------------------------------------------------------------------
# HELPER RENDER
# ---------------------------------------------------------------------------------

def trucks_to_html(truck_ids, icon="🚚"):
    if not truck_ids:
        return '<span style="color:#475569;font-size:.8rem;">(empty)</span>'
    chips = []
    for t in truck_ids:
        chips.append(f'<span class="truck-chip">{icon} T{t}</span>')
    return " ".join(chips)

def render_step_ui(current, final_metrics_avg, steps_len):
    # nilai live: gunakan hasil run pertama (yang lagi ditampilkan)
    clock_now = round(current["clock"], 2)

    utilA_now = (current["loaderA_busy_time"] / max(current["clock"], 1e-9)) * 100.0
    utilB_now = (current["loaderB_busy_time"] / max(current["clock"], 1e-9)) * 100.0
    utilS_now = (current["scale_busy_time"]   / max(current["clock"], 1e-9)) * 100.0

    utilA_now_disp = round(utilA_now, 2)
    utilB_now_disp = round(utilB_now, 2)
    utilS_now_disp = round(utilS_now, 2)

    avg_loader_wait_now = round(current["avg_loader_wait_so_far"], 2)
    avg_scale_wait_now  = round(current["avg_scale_wait_so_far"], 2)

    loader_queue_html = trucks_to_html(current["loader_queue"], "🚚")
    scale_queue_html = trucks_to_html(current["scale_queue"], "🚚")
    traveling_html = trucks_to_html(current["traveling"], "🚚")

    loaderA_status = "BUSY" if current["loaderA_busy"] else "IDLE"
    loaderB_status = "BUSY" if current["loaderB_busy"] else "IDLE"
    scale_status   = "BUSY" if current["scale_busy"]   else "IDLE"

    loaderA_badge = f'<span class="badge {"badge-busy" if loaderA_status=="BUSY" else "badge-idle"}">{loaderA_status}</span>'
    loaderB_badge = f'<span class="badge {"badge-busy" if loaderB_status=="BUSY" else "badge-idle"}">{loaderB_status}</span>'
    scale_badge   = f'<span class="badge {"badge-busy" if scale_status=="BUSY" else "badge-idle"}">{scale_status}</span>'

    loaderA_truck_html = trucks_to_html(
        [current["loaderA_truck"]] if current["loaderA_truck"] is not None else [], "🚚"
    )
    loaderB_truck_html = trucks_to_html(
        [current["loaderB_truck"]] if current["loaderB_truck"] is not None else [], "🚚"
    )
    scale_truck_html   = trucks_to_html(
        [current["scale_truck"]]   if current["scale_truck"]   is not None else [], "🚚"
    )

    # METRICS SNAPSHOT (run pertama, live)
    metrics_html = f"""
    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-label">Sim Clock (now)</div>
            <div class="metric-value">{clock_now}<span class="metric-suffix"> min</span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">Event</div>
            <div class="metric-value">{current["event"] if current["event"] else "-"}<span class="metric-suffix"></span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">Truck</div>
            <div class="metric-value">{("T"+str(current["truck"])) if current["truck"] is not None else "-"}<span class="metric-suffix"></span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">Avg Wait Loader (so far)</div>
            <div class="metric-value">{avg_loader_wait_now}<span class="metric-suffix"> min</span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">Avg Wait Scale (so far)</div>
            <div class="metric-value">{avg_scale_wait_now}<span class="metric-suffix"> min</span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">LoaderA Util (so far)</div>
            <div class="metric-value">{utilA_now_disp}<span class="metric-suffix"> %</span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">LoaderB Util (so far)</div>
            <div class="metric-value">{utilB_now_disp}<span class="metric-suffix"> %</span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">Scale Util (so far)</div>
            <div class="metric-value">{utilS_now_disp}<span class="metric-suffix"> %</span></div>
        </div>

        <div class="metric-card">
            <div class="metric-label">Step</div>
            <div class="metric-value">{st.session_state.event_idx}<span class="metric-suffix"> / {steps_len-1}</span></div>
        </div>
    </div>
    """
    components.html(
        f"""
        <html>
        <head><style>{CUSTOM_CSS}</style></head>
        <body style="background-color:transparent;margin:0;">
        {metrics_html}
        </body>
        </html>
        """,
        height=270,
    )

    st.markdown("---")

    # PIPELINE SNAPSHOT (run pertama)
    pipeline_html = f"""
    <div class="pipeline-diagram">
        <div style="display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:center; gap:.75rem;">

            <div class="stage-box">
                <div class="stage-title">Loader Queue</div>
                <div class="stage-icon">🚚⏳</div>
                <div class="stage-content">{loader_queue_html}</div>
            </div>

            <div class="arrow">➡</div>

            <div class="stage-box" style="min-width:160px;">
                <div class="stage-title">Loader A</div>
                <div class="stage-icon">🏗</div>
                <div class="stage-content">
                    {loaderA_badge}<br/>
                    {loaderA_truck_html}
                </div>
            </div>

            <div class="stage-box" style="min-width:160px;">
                <div class="stage-title">Loader B</div>
                <div class="stage-icon">🏗</div>
                <div class="stage-content">
                    {loaderB_badge}<br/>
                    {loaderB_truck_html}
                </div>
            </div>

            <div class="arrow">➡</div>

            <div class="stage-box">
                <div class="stage-title">Scale Queue</div>
                <div class="stage-icon">🚚⏳</div>
                <div class="stage-content">{scale_queue_html}</div>
            </div>

            <div class="arrow">➡</div>

            <div class="stage-box" style="min-width:160px;">
                <div class="stage-title">Scale</div>
                <div class="stage-icon">⚖️</div>
                <div class="stage-content">
                    {scale_badge}<br/>
                    {scale_truck_html}
                </div>
            </div>

            <div class="arrow">➡</div>

            <div class="stage-box">
                <div class="stage-title">Traveling</div>
                <div class="stage-icon">🔄</div>
                <div class="stage-content">{traveling_html}</div>
            </div>

            <div class="arrow">↩</div>

            <div class="stage-box" style="opacity:.6;">
                <div class="stage-title">Back to Loader Queue</div>
                <div class="stage-icon">🚚</div>
                <div class="stage-content" style="font-size:.7rem; color:#94a3b8;">
                    setelah travel selesai → join Loader Queue lagi
                </div>
            </div>

        </div>
    </div>
    """
    components.html(
        f"""
        <html>
        <head><style>{CUSTOM_CSS}</style></head>
        <body style="background-color: transparent; margin:0;">
        {pipeline_html}
        </body>
        </html>
        """,
        height=420,
        scrolling=True
    )

    st.markdown("---")

    # RESOURCE STATUS CARDS (run pertama)
    status_cards_html = f"""
    <div style="display:flex; flex-wrap:wrap; gap:1rem;">

        <div class="status-card" style="flex:1; min-width:250px;">
            <div class="status-title">Loader A 🏗</div>
            <div class="status-body">
                {('<span class="badge badge-busy">BUSY</span>' if loaderA_status=="BUSY" else '<span class="badge badge-idle">IDLE</span>')}
                <div class="truck-chip">🚚 Active:
                    {("T"+str(current["loaderA_truck"])) if current["loaderA_truck"] is not None else "None"}
                </div>
            </div>
            <div style="font-size:.75rem;color:#94a3b8;line-height:1.4;">
                Util (so far): <b>{utilA_now_disp}%</b><br/>
                Role: Muat material.
            </div>
        </div>

        <div class="status-card" style="flex:1; min-width:250px;">
            <div class="status-title">Loader B 🏗</div>
            <div class="status-body">
                {('<span class="badge badge-busy">BUSY</span>' if loaderB_status=="BUSY" else '<span class="badge badge-idle">IDLE</span>')}
                <div class="truck-chip">🚚 Active:
                    {("T"+str(current["loaderB_truck"])) if current["loaderB_truck"] is not None else "None"}
                </div>
            </div>
            <div style="font-size:.75rem;color:#94a3b8;line-height:1.4;">
                Util (so far): <b>{utilB_now_disp}%</b><br/>
                Kapasitas paralel.
            </div>
        </div>

        <div class="status-card" style="flex:1; min-width:250px;">
            <div class="status-title">Scale ⚖️</div>
            <div class="status-body">
                {('<span class="badge badge-busy">BUSY</span>' if scale_status=="BUSY" else '<span class="badge badge-idle">IDLE</span>')}
                <div class="truck-chip">🚚 Active:
                    {("T"+str(current["scale_truck"])) if current["scale_truck"] is not None else "None"}
                </div>
            </div>
            <div style="font-size:.75rem;color:#94a3b8;line-height:1.4;">
                Util (so far): <b>{utilS_now_disp}%</b><br/>
                Bottleneck potensial.
            </div>
        </div>

    </div>
    """
    components.html(
        f"""
        <html>
        <head><style>{CUSTOM_CSS}</style></head>
        <body style="background-color: transparent; margin:0;">
        {status_cards_html}
        </body>
        </html>
        """,
        height=260,
    )

    st.markdown("---")

    # FINAL PERFORMANCE (AVERAGE ACROSS N RUNS)
    avg_loader_wait_val = final_metrics_avg['avg_loader_queue_wait']
    avg_scale_wait_val  = final_metrics_avg['avg_scale_queue_wait']
    utilA_val           = final_metrics_avg['util_loader_A'] * 100.0
    utilB_val           = final_metrics_avg['util_loader_B'] * 100.0
    utilS_val           = final_metrics_avg['util_scale'] * 100.0
    sim_end_clock_val   = final_metrics_avg['sim_end_time']
    reps                = final_metrics_avg['replications']

    avg_loader_wait_round = round(avg_loader_wait_val)
    avg_scale_wait_round  = round(avg_scale_wait_val)
    utilA_round           = round(utilA_val)
    utilB_round           = round(utilB_val)
    utilS_round           = round(utilS_val)
    sim_end_clock_round   = round(sim_end_clock_val)

    st.markdown(f"### ✅ Final Performance (Averaged over {reps} run{'s' if reps>1 else ''})")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "Avg Loader Queue Wait (final)",
            f"{round(avg_loader_wait_val,2)} min  →  {avg_loader_wait_round} min"
        )
        st.metric(
            "Loader A Util (final)",
            f"{round(utilA_val,1)} %  →  {utilA_round} %"
        )
    with c2:
        st.metric(
            "Avg Weighing Queue Wait (final)",
            f"{round(avg_scale_wait_val,2)} min  →  {avg_scale_wait_round} min"
        )
        st.metric(
            "Loader B Util (final)",
            f"{round(utilB_val,1)} %  →  {utilB_round} %"
        )
    with c3:
        st.metric(
            "Scale Util (final)",
            f"{round(utilS_val,1)} %  →  {utilS_round} %"
        )
        st.metric(
            "Sim End Clock",
            f"{round(sim_end_clock_val,2)} min  →  {sim_end_clock_round} min"
        )

    st.markdown("---")


# ---------------------------------------------------------------------------------
# NAVIGATION CONTROLS (Next + Slider) UNTUK REPLIKASI PERTAMA
# ---------------------------------------------------------------------------------

if len(st.session_state.timeline_steps) == 0:
    st.info("Isi parameter → klik ▶ Run Simulation untuk mulai.")
else:
    steps = st.session_state.timeline_steps
    final_metrics_avg = st.session_state.final_metrics_avg

    # Kontrol replay
    col_next, col_slider = st.columns([1,3])
    with col_next:
        next_clicked = st.button("➡ Next", use_container_width=True)
    with col_slider:
        manual_idx = st.slider(
            "Manual Step Control (Run #1)",
            min_value=0,
            max_value=len(steps)-1,
            value=st.session_state.event_idx,
            step=1,
        )

    # slider override
    if manual_idx != st.session_state.event_idx:
        st.session_state.event_idx = manual_idx

    # next -> maju 1 event (masih run pertama)
    if next_clicked:
        if st.session_state.event_idx < len(steps)-1:
            st.session_state.event_idx += 1

    # render snapshot untuk step aktif
    current_step = steps[st.session_state.event_idx]
    render_step_ui(current_step, final_metrics_avg, len(steps))

    # tabel per truck DARI RUN PERTAMA (bukan average)
    st.markdown("### 🚚 Statistik per Truck (Run #1)")
    truck_table = []
    for tr in st.session_state.trucks_final:
        truck_table.append({
            "Truck": f"T{tr['id']}",
            "Total Wait @ Loader (min)": round(tr["total_wait_loader"], 2),
            "Total Wait @ Scale (min)": round(tr["total_wait_scale"], 2),
            "#Times Loaded": tr["loader_visits"],
            "#Times Weighed": tr["scale_visits"],
            "Final State (end of run #1)": tr["state"],
        })
    st.table(pd.DataFrame(truck_table))

    # event log terakhir dari run pertama
    st.markdown("### 📝 Event Log (Run #1, last 30 events)")
    to_show = st.session_state.event_log[-30:]
    st.dataframe(pd.DataFrame(to_show))
