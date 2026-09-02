"""
Beckhoff Data Viewer — Streamlit app for Beckhoff operational CSV data.

Launch via:
    streamlit run Beckhoff_view.py -- --root_folder /path/to/data
Or from SOCEIS GUI: click the "Data viewer" button.
"""

import os
import sys
import argparse
import zipfile
import subprocess
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.colors as pc
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.colors as mcolors
from matplotlib import colormaps
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional
from collections import defaultdict


# ── Suppress Streamlit email prompt ──────────────────────────────────────────
def ensure_email_prompt_disabled():
    try:
        config_path = Path.home() / ".streamlit" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            content = config_path.read_text(encoding="utf-8")
            if "showEmailPrompt = false" in content:
                return
            if "showEmailPrompt = true" in content:
                content = content.replace("showEmailPrompt = true", "showEmailPrompt = false")
            else:
                content += (
                    "\n[general]\nshowEmailPrompt = false\n"
                    if "[general]" not in content
                    else "\nshowEmailPrompt = false\n"
                )
            config_path.write_text(content, encoding="utf-8")
        else:
            config_path.write_text("[general]\nshowEmailPrompt = false\n", encoding="utf-8")
    except Exception:
        pass


ensure_email_prompt_disabled()

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--root_folder", type=str, default="")
try:
    args, _ = parser.parse_known_args()
    parsed_path = args.root_folder
except SystemExit:
    parsed_path = ""

DEFAULT_ROOT_FOLDER = Path(parsed_path) if parsed_path else Path.cwd()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Beckhoff Data Viewer", layout="wide")

# ── tkinter ───────────────────────────────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import filedialog
    TK_AVAILABLE = True
except Exception:
    tk = None
    filedialog = None
    TK_AVAILABLE = False

# ═════════════════════════════════════════════════════════════════════════════
# Color palette system — identical to SOCEIS_view.py / IV_view.py
# ═════════════════════════════════════════════════════════════════════════════

DEFAULT_COLOR_PALETTE = [
    "#4C78A8", "#F58518", "#54A24B", "#E45756", "#B279A2",
    "#FF9DA6", "#9D755D", "#BAB0AC", "#72B7B2", "#F2CF5B",
]

PLOTLY_SEQ = {
    "Viridis (perceptual)":          pc.sequential.Viridis,
    "Cividis (colorblind-friendly)": pc.sequential.Cividis,
    "Plasma (perceptual)":           pc.sequential.Plasma,
    "Inferno (perceptual)":          pc.sequential.Inferno,
    "Magma (perceptual)":            pc.sequential.Magma,
    "Turbo (high-contrast)":         pc.sequential.Turbo,
}

PALETTE_LIBRARY = {
    "Default":                       "SOCEIS_DEFAULT",
    "Viridis (perceptual)":          "viridis",
    "Cividis (colorblind-friendly)": "cividis",
    "Plasma (perceptual)":           "plasma",
    "Inferno (perceptual)":          "inferno",
    "Magma (perceptual)":            "magma",
    "Turbo (high-contrast)":         "turbo",
    "Matplotlib tab10":              "tab10",
    "Matplotlib tab20":              "tab20",
    "Matplotlib Set2 (pastel)":      "Set2",
    "Matplotlib Dark2":              "Dark2",
    "Matplotlib Paired":             "Paired",
}

PALETTE_PREVIEW_N = 10


def _rgb_str_to_hex(s: str) -> str:
    nums = (
        s.strip().lower()
        .replace("rgba(", "").replace("rgb(", "").replace(")", "")
        .split(",")
    )
    r, g, b = [int(float(x)) for x in nums[:3]]
    return f"#{r:02x}{g:02x}{b:02x}"


def sample_plotly_sequential(palette_choice: str, n: int,
                              lo: float = 0.10, hi: float = 0.95) -> List[str]:
    scale = PLOTLY_SEQ[palette_choice]
    t_vals = np.linspace(lo, hi, max(n, 1))
    return [_rgb_str_to_hex(c) for c in pc.sample_colorscale(scale, t_vals)]


def sample_palette_colors(palette_choice: str, n: int) -> List[str]:
    if palette_choice == "Default":
        base = DEFAULT_COLOR_PALETTE
        if n <= len(base):
            return base[:n]
        return (base * ((n + len(base) - 1) // len(base)))[:n]
    if palette_choice in PLOTLY_SEQ:
        return sample_plotly_sequential(palette_choice, n=n, lo=0.10, hi=0.95)
    cmap_name = PALETTE_LIBRARY.get(palette_choice, "tab10")
    cmap = colormaps.get_cmap(cmap_name)
    if hasattr(cmap, "colors") and cmap.colors is not None:
        base = [mcolors.to_hex(c) for c in cmap.colors]
        if n <= len(base):
            return base[:n]
        return (base * ((n + len(base) - 1) // len(base)))[:n]
    return DEFAULT_COLOR_PALETTE[:n]


def render_palette_preview(colors: List[str]) -> str:
    swatches = "".join(
        f"<span style='display:inline-block;width:18px;height:18px;"
        f"margin-right:6px;border-radius:4px;border:1px solid rgba(255,255,255,0.35);"
        f"background:{c};'></span>"
        for c in colors
    )
    return f"<div style='margin-top:6px;margin-bottom:4px;'>{swatches}</div>"


# ═════════════════════════════════════════════════════════════════════════════
# Folder picker — identical to IV_view.py
# ═════════════════════════════════════════════════════════════════════════════

def _resolve_initial_dir(current_dir: Optional[str],
                          fallback_dir: Optional[Path]) -> Optional[Path]:
    for candidate in [current_dir, fallback_dir]:
        if candidate is None:
            continue
        try:
            p = Path(candidate).expanduser()
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass
    return None


def pick_folder_dialog(current_dir: Optional[str] = None,
                       fallback_dir: Optional[Path] = None) -> Optional[str]:
    initial_dir = _resolve_initial_dir(current_dir, fallback_dir)
    if sys.platform == "darwin":
        try:
            choose_expr = "choose folder with prompt \"Select folder\""
            if initial_dir is not None:
                posix_dir = initial_dir.as_posix().replace('"', '\\"')
                choose_expr += f' default location (POSIX file "{posix_dir}")'
            cmd = ["osascript", "-e", "try",
                   "-e", f"POSIX path of ({choose_expr})",
                   "-e", "on error number -128",
                   "-e", "return \"\"",
                   "-e", "end try"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            folder = (result.stdout or "").strip()
            return folder if folder else None
        except Exception:
            return None
    if not TK_AVAILABLE:
        return None
    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    ask_kwargs = {}
    if initial_dir is not None:
        ask_kwargs["initialdir"] = str(initial_dir)
    folder = filedialog.askdirectory(**ask_kwargs)
    root_tk.destroy()
    return folder if folder else None


# ═════════════════════════════════════════════════════════════════════════════
# Legend position presets
# ═════════════════════════════════════════════════════════════════════════════

LEGEND_POSITIONS = {
    "Outside right":       dict(orientation='v', x=1.02,  y=1.0,   xanchor='left',   yanchor='top'),
    "Inside top-right":    dict(orientation='v', x=0.98,  y=0.98,  xanchor='right',  yanchor='top'),
    "Inside top-left":     dict(orientation='v', x=0.02,  y=0.98,  xanchor='left',   yanchor='top'),
    "Inside bottom-right": dict(orientation='v', x=0.98,  y=0.02,  xanchor='right',  yanchor='bottom'),
    "Outside bottom":      dict(orientation='h', x=0.5,   y=-0.18, xanchor='center', yanchor='top'),
}

# ═════════════════════════════════════════════════════════════════════════════
# Time axis helpers
# ═════════════════════════════════════════════════════════════════════════════

TIME_UNITS = {
    "Hours":   (3600.0, "Time [h]"),
    "Minutes": (60.0,   "Time [min]"),
    "Seconds": (1.0,    "Time [s]"),
}

# Quick-select presets per plot
QUICK_PRESETS = {
    "Temperature":     lambda cols: [c for c in cols if "temp" in c.lower()],
    "Cell electrical": lambda cols: [c for c in cols if
                                     any(k in c.lower() for k in ("voltage", "current"))
                                     and "mfc" not in c.lower()],
    "Gas flows":       lambda cols: [c for c in cols if "actualflowrate" in c.lower()],
}


def compute_time_axis(data: pd.DataFrame,
                      use_abs: bool, epoch_str: str,
                      time_unit: str):
    """Return (time_x Series, time_label str)."""
    if use_abs:
        try:
            epoch_dt = pd.Timestamp(epoch_str)
            time_x   = epoch_dt + pd.to_timedelta(data["Timestamp"] / 1e9, unit="s")
            return time_x, "Date / Time"
        except Exception:
            pass  # fall through to elapsed
    divisor, label = TIME_UNITS[time_unit]
    return data["_elapsed_s"] / divisor, label


def _hours_to_axis(h: float, use_abs: bool, epoch_str: str, time_unit: str):
    """Convert elapsed hours to the current x-axis display value (datetime or numeric)."""
    if use_abs:
        return pd.Timestamp(epoch_str) + pd.Timedelta(hours=h)
    return h * 3600.0 / TIME_UNITS[time_unit][0]


def _is_datetime_like(series) -> bool:
    return pd.api.types.is_datetime64_any_dtype(series)


def _range_from(vmin, vmax):
    """Return [vmin, vmax] only when both bounds are provided, else None (auto-scale)."""
    if vmin is not None and vmax is not None:
        return [float(vmin), float(vmax)]
    return None


# ═════════════════════════════════════════════════════════════════════════════
# Data loading
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner="Loading CSV files…")
def load_beckhoff_folder(folder_str: str) -> Optional[pd.DataFrame]:
    """Read and merge all Beckhoff CSV files (';' separated) in the folder."""
    folder = Path(folder_str)
    seen: dict = {}
    for f in sorted(folder.glob("*.csv")) + sorted(folder.glob("*.CSV")):
        seen.setdefault(f.name.lower(), f)
    csv_files = list(seen.values())

    if not csv_files:
        return None

    all_data = []
    for f in csv_files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                header_line = fh.readline().strip()
            original_cols = header_line.split(";")

            name_count: dict = defaultdict(int)
            col_names = []
            for name in original_cols:
                name_count[name] += 1
                col_names.append(
                    name if name_count[name] == 1 else f"{name}{name_count[name]}"
                )

            df = pd.read_csv(f, sep=";", skiprows=1, names=col_names,
                             encoding="utf-8", engine="python", on_bad_lines="skip")
            all_data.append(df)
        except Exception as exc:
            print(f"[Beckhoff_view] Could not read {f.name}: {exc}")

    if not all_data:
        return None

    data = pd.concat(all_data, ignore_index=True)

    for col in data.columns:
        if col != "Timestamp":
            data[col] = pd.to_numeric(data[col], errors="coerce")

    if "Timestamp" in data.columns and len(data) > 0:
        data["Timestamp"] = pd.to_numeric(data["Timestamp"], errors="coerce")
        data.sort_values("Timestamp", inplace=True)
        data.reset_index(drop=True, inplace=True)
        t0 = data["Timestamp"].iloc[0]
        data["_elapsed_s"] = (data["Timestamp"] - t0) / 1e9
    else:
        data["_elapsed_s"] = np.arange(len(data), dtype=float)

    return data


def _plot_cols(data: pd.DataFrame) -> List[str]:
    return [c for c in data.columns if not c.startswith("_") and c != "Timestamp"]


# ═════════════════════════════════════════════════════════════════════════════
# Figure builders
# ═════════════════════════════════════════════════════════════════════════════

def build_beckhoff_figure(data, time_x, y1_cols, y2_cols, colors, time_label,
                          legend_pos_cfg, show_legend, legend_font_size, line_width,
                          legend_names=None, x_range=None, y1_title="", y2_title="",
                          y1_range=None, y2_range=None):
    if legend_names is None:
        legend_names = {}
    has_y2 = bool(y2_cols)
    fig = make_subplots(specs=[[{"secondary_y": True}]]) if has_y2 else go.Figure()

    for i, col in enumerate(y1_cols):
        trace = go.Scatter(x=time_x, y=data[col], mode="lines",
                           name=legend_names.get(col, col),
                           line=dict(color=colors[i % len(colors)], width=line_width))
        fig.add_trace(trace, secondary_y=False) if has_y2 else fig.add_trace(trace)

    for i, col in enumerate(y2_cols):
        fig.add_trace(
            go.Scatter(x=time_x, y=data[col], mode="lines",
                       name=legend_names.get(col, col),
                       line=dict(color=colors[(len(y1_cols) + i) % len(colors)],
                                 width=line_width, dash="dot")),
            secondary_y=True,
        )

    auto_y1 = ", ".join(y1_cols[:3]) + ("…" if len(y1_cols) > 3 else "")
    auto_y2 = ", ".join(y2_cols[:3]) + ("…" if len(y2_cols) > 3 else "")
    eff_y1  = y1_title.strip() or auto_y1
    eff_y2  = y2_title.strip() or auto_y2
    if has_y2:
        fig.update_yaxes(title_text=eff_y1, secondary_y=False)
        fig.update_yaxes(title_text=eff_y2, secondary_y=True)
    elif eff_y1:
        fig.update_yaxes(title_text=eff_y1)

    fig.update_layout(
        xaxis_title=time_label,
        template="plotly_white",
        showlegend=show_legend,
        legend=dict(**legend_pos_cfg, font=dict(size=legend_font_size)),
        margin=dict(l=65, r=80 if has_y2 else 20, t=30, b=65),
        height=480,
    )
    if x_range is not None:
        fig.update_xaxes(range=x_range)

    if has_y2:
        if y1_range is not None:
            fig.update_yaxes(range=y1_range, secondary_y=False)
        if y2_range is not None:
            fig.update_yaxes(range=y2_range, secondary_y=True)
    elif y1_range is not None:
        fig.update_yaxes(range=y1_range)
    return fig


def _mpl_fig_to_bytes(mpl_fig, fmt: str) -> bytes:
    buf = BytesIO()
    mpl_fig.savefig(buf, format=fmt if fmt != "jpg" else "jpeg",
                    bbox_inches="tight", dpi=300,
                    **({"pad_inches": 0.2} if fmt == "pdf" else {}))
    return buf.getvalue()


def _build_mpl_figure(data, time_x, y1_cols, y2_cols, colors, time_label,
                      show_legend, legend_font_size, line_width, legend_names=None,
                      x_range=None, y1_title="", y2_title="",
                      y1_range=None, y2_range=None):
    if legend_names is None:
        legend_names = {}
    has_y2 = bool(y2_cols)
    is_dt  = _is_datetime_like(time_x)
    fig, ax1 = plt.subplots(figsize=(10, 4.5), dpi=300)

    t = time_x.values if is_dt else time_x

    for i, col in enumerate(y1_cols):
        ax1.plot(t, data[col].values, color=colors[i % len(colors)],
                 linewidth=line_width, label=legend_names.get(col, col))

    ax1.set_xlabel(time_label, fontsize=11)
    auto_y1 = ", ".join(y1_cols[:2]) + ("…" if len(y1_cols) > 2 else "")
    if y1_cols:
        ax1.set_ylabel(y1_title.strip() or auto_y1, fontsize=9)
    ax1.grid(True, alpha=0.3)

    if is_dt:
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate(rotation=30)

    if has_y2:
        ax2 = ax1.twinx()
        for i, col in enumerate(y2_cols):
            ax2.plot(t, data[col].values,
                     color=colors[(len(y1_cols) + i) % len(colors)],
                     linewidth=line_width, linestyle="dotted",
                     label=legend_names.get(col, col))
        auto_y2 = ", ".join(y2_cols[:2]) + ("…" if len(y2_cols) > 2 else "")
        ax2.set_ylabel(y2_title.strip() or auto_y2, fontsize=9)
        if y2_range is not None:
            ax2.set_ylim(y2_range[0], y2_range[1])
        if show_legend:
            h1, l1 = ax1.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            ax1.legend(h1 + h2, l1 + l2, fontsize=legend_font_size)
    else:
        if show_legend:
            ax1.legend(fontsize=legend_font_size)

    if x_range is not None:
        ax1.set_xlim(x_range[0], x_range[1])
    if y1_range is not None:
        ax1.set_ylim(y1_range[0], y1_range[1])

    fig.tight_layout()
    return fig


# ═════════════════════════════════════════════════════════════════════════════
# Streamlit UI
# ═════════════════════════════════════════════════════════════════════════════

st.title("Beckhoff Data Viewer")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Data folder ───────────────────────────────────────────────────────────
    if "bk_root_input" not in st.session_state:
        st.session_state.bk_root_input = str(DEFAULT_ROOT_FOLDER)

    col_left, col_right = st.columns([0.82, 0.18], vertical_alignment="bottom")
    with col_left:
        st.session_state.bk_root_input = st.text_input(
            "Data folder", value=st.session_state.bk_root_input,
        )
    with col_right:
        if st.button("📁", width="stretch", key="bk_browse"):
            chosen = pick_folder_dialog(
                current_dir=st.session_state.bk_root_input,
                fallback_dir=DEFAULT_ROOT_FOLDER,
            )
            if chosen:
                st.session_state.bk_root_input = chosen
                st.rerun()

    # Auto-sync export path when data folder changes
    _cur_root = st.session_state.bk_root_input
    if st.session_state.get("bk_last_root") != _cur_root:
        st.session_state["bk_export_input"] = str(Path(_cur_root) / "Beckhoff_figures")
        st.session_state["bk_last_root"] = _cur_root

    st.markdown("---")

    # ── Time axis ─────────────────────────────────────────────────────────────
    st.markdown("### Time axis")
    use_abs_time = st.checkbox("Absolute time", value=False, key="bk_abs_time")
    if use_abs_time:
        epoch_str = st.text_input(
            "Epoch (UTC)", value="2000-01-01 00:00:00", key="bk_epoch",
            help="Start of the Beckhoff timestamp counter. "
                 "TwinCAT systems commonly use 2000-01-01.",
        )
        time_unit = "Hours"  # unused but needed for fallback
    else:
        epoch_str = "2000-01-01 00:00:00"
        time_unit = st.selectbox("Elapsed unit", list(TIME_UNITS.keys()), key="bk_time_unit")

    st.markdown("---")

    # ── X-axis bounds ─────────────────────────────────────────────────────────
    st.markdown("### X-axis bounds")
    use_xlim = st.checkbox("Limit x-axis", value=False, key="bk_xlim")
    if use_xlim:
        xb_col1, xb_col2 = st.columns(2)
        with xb_col1:
            st.number_input("From (h)", min_value=0.0, value=0.0,
                            step=0.5, format="%.2f", key="bk_xmin")
        with xb_col2:
            st.number_input("To (h)", min_value=0.0, value=24.0,
                            step=0.5, format="%.2f", key="bk_xmax")

    st.markdown("---")

    # ── Color palette ─────────────────────────────────────────────────────────
    if "bk_palette" not in st.session_state:
        st.session_state.bk_palette = "Default"
    st.markdown("### Colors")
    st.selectbox("Color palette", options=list(PALETTE_LIBRARY.keys()), key="bk_palette")
    preview_colors = sample_palette_colors(st.session_state.bk_palette, n=PALETTE_PREVIEW_N)
    st.markdown(render_palette_preview(preview_colors), unsafe_allow_html=True)

    st.markdown("---")

    # ── Legend & style ────────────────────────────────────────────────────────
    st.markdown("### Legend & style")
    show_legend      = st.checkbox("Show legend", value=True, key="bk_show_legend")
    legend_position  = st.selectbox("Position", list(LEGEND_POSITIONS.keys()),
                                    index=0, disabled=not show_legend)
    legend_font_size = st.number_input("Font size", min_value=8, max_value=28,
                                       value=12, step=1, disabled=not show_legend)
    line_width       = st.slider("Line width", min_value=1.0, max_value=5.0,
                                 value=1.5, step=0.5)

    st.markdown("---")

    # ── Export ────────────────────────────────────────────────────────────────
    st.markdown("### Export")
    _root_for_export = Path(st.session_state.bk_root_input)

    col_left2, col_right2 = st.columns([0.82, 0.18], vertical_alignment="bottom")
    with col_left2:
        st.session_state.bk_export_input = st.text_input(
            "Export folder", value=st.session_state.bk_export_input,
        )
    with col_right2:
        if st.button("📁", key="bk_browse_export", width="stretch"):
            chosen = pick_folder_dialog(
                current_dir=st.session_state.bk_export_input,
                fallback_dir=_root_for_export,
            )
            if chosen:
                st.session_state.bk_export_input = chosen
                st.rerun()

    export_folder  = Path(st.session_state.bk_export_input)
    export_formats = st.multiselect(
        "Formats", ["png", "jpg", "pdf"], default=["png"], key="bk_export_fmts",
    )
    if not export_formats:
        st.session_state["bk_export_fmts"] = ["png"]
    save_zip = st.button("💾 Save ZIP")

# ── Guards ────────────────────────────────────────────────────────────────────
root = Path(st.session_state.bk_root_input)
if not root.is_dir():
    st.warning(f"Folder not found: {root}")
    st.stop()

data = load_beckhoff_folder(str(root))
if data is None or data.empty:
    st.info("No Beckhoff CSV files (.csv) found in the selected folder.")
    st.stop()

plottable = _plot_cols(data)

# ── Compute shared time axis ──────────────────────────────────────────────────
time_x, time_label = compute_time_axis(
    data, use_abs_time, epoch_str, time_unit
)

# ── Info caption ──────────────────────────────────────────────────────────────
duration_h = float(data["_elapsed_s"].iloc[-1]) / 3600 if len(data) > 1 else 0.0
st.caption(
    f"{len(data):,} rows  ·  {duration_h:.2f} h ({duration_h * 60:.0f} min)  ·  "
    f"{len(plottable)} channels available"
)

# ── X-axis range (from sidebar bounds) ───────────────────────────────────────
_x_range = None
if st.session_state.get("bk_xlim"):
    _xmin_h = float(st.session_state.get("bk_xmin", 0.0))
    _xmax_h = float(st.session_state.get("bk_xmax", 24.0))
    if use_abs_time:
        _x_range = [
            _hours_to_axis(_xmin_h, use_abs_time, epoch_str, time_unit),
            _hours_to_axis(_xmax_h, use_abs_time, epoch_str, time_unit),
        ]
    else:
        # Elapsed mode: re-base the axis so the lower bound reads 0 on the tick labels
        _xmin_axis = _hours_to_axis(_xmin_h, False, epoch_str, time_unit)
        _xmax_axis = _hours_to_axis(_xmax_h, False, epoch_str, time_unit)
        time_x = time_x - _xmin_axis
        _x_range = [0.0, _xmax_axis - _xmin_axis]

# ── Multi-plot state ──────────────────────────────────────────────────────────
if "bk_n_plots" not in st.session_state:
    st.session_state.bk_n_plots = 1
n_plots = st.session_state.bk_n_plots

# Ensure session-state keys exist for every active plot
for _i in range(n_plots):
    st.session_state.setdefault(f"bk_y1_{_i}", [])
    st.session_state.setdefault(f"bk_use_y2_{_i}", False)
    st.session_state.setdefault(f"bk_y2_{_i}", [])

# ── Per-plot panel ────────────────────────────────────────────────────────────
def _plot_panel(i: int, data: pd.DataFrame, time_x, plottable: List[str],
                n_plots: int, palette: str, legend_pos_cfg: dict,
                show_legend: bool, legend_font_size: int,
                line_width: float, time_label: str,
                x_range=None) -> None:

    h_left, h_right = st.columns([0.85, 0.15])
    with h_left:
        st.markdown(f"#### Plot {i + 1}")
    with h_right:
        if n_plots > 1 and st.button("✕ Remove", key=f"bk_rm_{i}", use_container_width=True):
            for j in range(i, n_plots - 1):
                st.session_state[f"bk_y1_{j}"]     = st.session_state.get(f"bk_y1_{j+1}", [])
                st.session_state[f"bk_use_y2_{j}"] = st.session_state.get(f"bk_use_y2_{j+1}", False)
                st.session_state[f"bk_y2_{j}"]     = st.session_state.get(f"bk_y2_{j+1}", [])
            for k in [f"bk_y1_{n_plots-1}", f"bk_use_y2_{n_plots-1}", f"bk_y2_{n_plots-1}"]:
                st.session_state.pop(k, None)
            st.session_state.bk_n_plots -= 1
            st.rerun()

    preset_labels = ["Temp.", "Electrical", "Gas flows"]
    p_cols = st.columns(len(QUICK_PRESETS) + 1)
    for (pname, pfn), plabel, pcol in zip(QUICK_PRESETS.items(), preset_labels, p_cols):
        with pcol:
            if st.button(plabel, key=f"bk_preset_{i}_{pname}", use_container_width=True):
                selection = pfn(plottable)
                current = list(st.session_state.get(f"bk_y1_{i}", []))
                st.session_state[f"bk_y1_{i}"] = current + [c for c in selection if c not in current]
                st.rerun()
    with p_cols[-1]:
        if st.button("Clear", key=f"bk_clear_{i}", use_container_width=True):
            st.session_state[f"bk_y1_{i}"] = []
            st.session_state[f"bk_y2_{i}"] = []
            st.rerun()

    sel_left, sel_right = st.columns(2)
    with sel_left:
        y1_cols_i = st.multiselect("Left Y-axis", options=plottable, key=f"bk_y1_{i}")
    with sel_right:
        use_y2_i = st.checkbox("Secondary Y-axis (right)", key=f"bk_use_y2_{i}")
        y2_cols_i: List[str] = []
        if use_y2_i:
            y2_cols_i = st.multiselect("Right Y-axis", options=plottable, key=f"bk_y2_{i}")

    all_cols_i = y1_cols_i + y2_cols_i

    yt_left, yt_right = st.columns(2)
    with yt_left:
        y1_title_i = st.text_input(
            "Left Y-axis title",
            placeholder=", ".join(y1_cols_i[:2]) + ("…" if len(y1_cols_i) > 2 else "") if y1_cols_i else "",
            key=f"bk_ytitle1_{i}",
        )
    with yt_right:
        y2_title_i = st.text_input(
            "Right Y-axis title",
            placeholder=", ".join(y2_cols_i[:2]) + ("…" if len(y2_cols_i) > 2 else "") if y2_cols_i else "",
            disabled=not use_y2_i,
            key=f"bk_ytitle2_{i}",
        )

    with st.expander("Y-axis limits", expanded=False):
        st.caption("Leave blank for auto-scaling")
        yl_c1, yl_c2 = st.columns(2)
        y1_min_i = yl_c1.number_input("Left Y min", value=None, placeholder="auto", key=f"bk_y1min_{i}")
        y1_max_i = yl_c2.number_input("Left Y max", value=None, placeholder="auto", key=f"bk_y1max_{i}")
        yr_c1, yr_c2 = st.columns(2)
        y2_min_i = yr_c1.number_input("Right Y min", value=None, placeholder="auto",
                                      disabled=not use_y2_i, key=f"bk_y2min_{i}")
        y2_max_i = yr_c2.number_input("Right Y max", value=None, placeholder="auto",
                                      disabled=not use_y2_i, key=f"bk_y2max_{i}")

    y1_range_i = _range_from(y1_min_i, y1_max_i)
    y2_range_i = _range_from(y2_min_i, y2_max_i) if use_y2_i else None

    legend_names_i: dict = {
        col: st.session_state.get(f"bk_lgnd_{i}_{col}", col) for col in all_cols_i
    }

    if all_cols_i:
        with st.expander("Legend names", expanded=False):
            for col in all_cols_i:
                st.text_input(col, value=legend_names_i[col], key=f"bk_lgnd_{i}_{col}")
        legend_names_i = {col: st.session_state.get(f"bk_lgnd_{i}_{col}", col) for col in all_cols_i}

    n_ch = max(2, len(all_cols_i)) if all_cols_i else 1
    colors_i = sample_palette_colors(palette, n=n_ch)
    if y1_cols_i or y2_cols_i:
        fig_i = build_beckhoff_figure(
            data, time_x, y1_cols_i, y2_cols_i, colors_i, time_label,
            legend_pos_cfg, show_legend, legend_font_size, line_width, legend_names_i,
            x_range=x_range, y1_title=y1_title_i, y2_title=y2_title_i,
            y1_range=y1_range_i, y2_range=y2_range_i,
        )
    else:
        fig_i = go.Figure()
        fig_i.update_layout(
            template="plotly_white", height=180,
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            annotations=[dict(text="Select channels above to plot",
                              showarrow=False, font=dict(size=13, color="gray"))],
            margin=dict(l=20, r=20, t=20, b=20),
        )
    st.plotly_chart(fig_i, use_container_width=True, key=f"bk_chart_{i}")


# ── Render plot panels ────────────────────────────────────────────────────────
for i in range(n_plots):
    st.markdown("---")
    _plot_panel(
        i, data, time_x, plottable, n_plots,
        st.session_state.bk_palette,
        LEGEND_POSITIONS[legend_position],
        show_legend, int(legend_font_size), line_width, time_label,
        x_range=_x_range,
    )

# ── Add plot button ───────────────────────────────────────────────────────────
st.markdown("---")
if st.button("➕  Add plot", use_container_width=False):
    st.session_state.bk_n_plots += 1
    st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# ZIP export  (plot_configs built from session state — fragments run before this)
# ═════════════════════════════════════════════════════════════════════════════
_plot_configs = []
for _i in range(n_plots):
    _y1      = list(st.session_state.get(f"bk_y1_{_i}", []))
    _y2      = list(st.session_state.get(f"bk_y2_{_i}", []))
    _lgnd    = {col: st.session_state.get(f"bk_lgnd_{_i}_{col}", col) for col in _y1 + _y2}
    _ytitle1 = st.session_state.get(f"bk_ytitle1_{_i}", "")
    _ytitle2 = st.session_state.get(f"bk_ytitle2_{_i}", "")
    _y1rng   = _range_from(st.session_state.get(f"bk_y1min_{_i}"),
                           st.session_state.get(f"bk_y1max_{_i}"))
    _y2rng   = (_range_from(st.session_state.get(f"bk_y2min_{_i}"),
                            st.session_state.get(f"bk_y2max_{_i}"))
                if st.session_state.get(f"bk_use_y2_{_i}", False) else None)
    _plot_configs.append((_y1, _y2, _lgnd, _ytitle1, _ytitle2, _y1rng, _y2rng))

if save_zip:
    active = [(i, y1, y2, lgnd, yt1, yt2, y1r, y2r)
              for i, (y1, y2, lgnd, yt1, yt2, y1r, y2r) in enumerate(_plot_configs) if y1 or y2]
    if not active:
        st.warning("No channels selected — nothing to export.")
    else:
        try:
            export_folder.mkdir(parents=True, exist_ok=True)
            ts_str   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            zip_path = export_folder / f"Beckhoff_figures_{ts_str}.zip"

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, y1, y2, lgnd, yt1, yt2, y1r, y2r in active:
                    n_ch     = max(2, len(y1) + len(y2))
                    colors_i = sample_palette_colors(st.session_state.bk_palette, n=n_ch)
                    mpl_fig  = _build_mpl_figure(
                        data, time_x, y1, y2, colors_i,
                        time_label, show_legend, int(legend_font_size), line_width, lgnd,
                        x_range=_x_range, y1_title=yt1, y2_title=yt2,
                        y1_range=y1r, y2_range=y2r,
                    )
                    suffix = f"_plot{idx+1}" if len(active) > 1 else ""
                    for fmt in export_formats:
                        zf.writestr(f"Beckhoff_timeseries{suffix}.{fmt}",
                                    _mpl_fig_to_bytes(mpl_fig, fmt))
                    plt.close(mpl_fig)

            st.success(f"ZIP saved at: {zip_path.resolve()}")
        except Exception as e:
            st.error(f"Export failed: {e}")
