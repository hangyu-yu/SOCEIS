#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
_________________________________________________________________

                REQUIREMENTS & USAGE
_________________________________________________________________

This application is designed to analyze SOCEIS data.
Created date: 11.February.2026

Folder structure requirement:
You must have a main root folder (e.g. EIS/SIM/) containing
subfolders named "EIS", and optionally sibling folders
"DRT" and "CNLS", automatically generated from SOCEIS code.

The program automatically:
 - Detects all .xlsx files inside any "EIS" folder
 - Looks for matching filenames inside sibling "DRT"
   and "CNLS" folders (if present)

Required Python packages (install once):
   pip install streamlit pandas numpy plotly matplotlib openpyxl ast tkinter

 How to run the application:
   Open a terminal (PowerShell on Windows) in the folder
   containing this script and execute:

       streamlit run SOCEIS_view.py

The app will open automatically in your default browser.
_________________________________________________________________

"""

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from io import BytesIO
import zipfile
import re
import subprocess
import sys
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib import colormaps
import plotly.colors as pc
from pathlib import Path
import argparse
import os

try:
    import tkinter as tk
    from tkinter import filedialog
    TK_AVAILABLE = True
except Exception:
    tk = None
    filedialog = None
    TK_AVAILABLE = False

# ===============================
# Helper function for Windows long path support
# ===============================
def _normalize_path(path_obj):
    """Handle Windows long path (260+ chars) by adding \\\\?\\ prefix."""
    path_str = str(path_obj)
    if sys.platform == 'win32' and os.path.isabs(path_str) and not path_str.startswith('\\\\'):
        return '\\\\?' + os.path.sep + os.path.abspath(path_str)
    return path_str

# ===============================
# Configuration
# ===============================


def ensure_email_prompt_disabled():
    try:
        config_path = Path.home() / ".streamlit" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if config_path.exists():
            content = config_path.read_text(encoding="utf-8")

            # If already set to false, do nothing
            if "showEmailPrompt = false" in content:
                return

            # If explicitly set to true, replace it
            if "showEmailPrompt = true" in content:
                content = content.replace(
                    "showEmailPrompt = true",
                    "showEmailPrompt = false"
                )
            else:
                # If the field does not exist, append it
                if "[general]" in content:
                    content += "\nshowEmailPrompt = false\n"
                else:
                    content += "\n[general]\nshowEmailPrompt = false\n"

            config_path.write_text(content, encoding="utf-8")

        else:
            # If config file does not exist, create it
            config_path.write_text(
                "[general]\nshowEmailPrompt = false\n",
                encoding="utf-8"
            )

    except Exception:
        # Fail silently to avoid breaking Streamlit startup
        pass


# Call before any Streamlit UI code
ensure_email_prompt_disabled()

parser = argparse.ArgumentParser()
parser.add_argument("--root_folder", type=str, default="")

try:
    args, _ = parser.parse_known_args()
    parsed_path = args.root_folder
except SystemExit:
    parsed_path = ""

if parsed_path:
    DEFAULT_ROOT_FOLDER = Path(parsed_path)
else:
    DEFAULT_ROOT_FOLDER = Path("EIS/SIM")

DEFAULT_EXPORT_FOLDER = Path(os.path.join(DEFAULT_ROOT_FOLDER, "SOCEIS_figures"))

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "axes.linewidth": 1.0,
    "lines.linewidth": 1.5,
    "figure.dpi": 300,
})

DEFAULT_COLOR_PALETTE = [
    "#4C78A8",  # blue
    "#F58518",  # orange
    "#54A24B",  # green
    "#E45756",  # red
    "#B279A2",  # purple
    "#FF9DA6",  # pink
    "#9D755D",  # brown
    "#BAB0AC",  # grey
    "#72B7B2",  # teal
    "#F2CF5B",  # yellow
]


# ===============================

EIS_PARAMETERS_SHEET = "EIS_Parameters"
DRT_PARAMETERS_SHEET = "DRT_Parameters"


NYQUIST_TYPES = [
    "Original",
    "Truncated",
    "LC corrected",
    "Linear Kramers-Kroning",
    "Smooth",
    "Extended",
]

DEFAULT_NYQUIST = ["Original", "Truncated"]

BODE_TYPES = NYQUIST_TYPES

DRT_TYPES = ["Truncated", "Smooth", "LCcorrect", "Extrapolation", "Z-HIT",
             "RBF", "RBF Smooth", "RBF LCcorrect", "RBF Extrapolation", "RBF Z-HIT"]
DRT_SHEET_MAP = {
    "Truncated": "Tknv_ReIm",
    "Smooth": "Tknv_ReIm_s",
    "LCcorrect": "Tknv_ReIm_crct",
    "Extrapolation": "Tknv_ReIm_e",
    "Z-HIT": "Tknv_ReIm_z",
    "RBF": "RBF_ReIm",
    "RBF Smooth": "RBF_s_ReIm",
    "RBF LCcorrect": "RBF_crct_ReIm",
    "RBF Extrapolation": "RBF_e_ReIm",
    "RBF Z-HIT": "RBF_z_ReIm",
}

# CNLS
CNLS_ENABLED_DEFAULT = False
CNLS_SHEET = "Elements"

def nyquist_fit_plotly(datasets):

    fig = go.Figure()
    show_legend = len(datasets) > 1
    for i, (name, df) in enumerate(datasets):

        x = pd.to_numeric(df.iloc[:, 2], errors="coerce")   # Re
        y = -pd.to_numeric(df.iloc[:, 3], errors="coerce")  # Im

        fig.add_scatter(
            x=x,
            y=y,
            mode="markers+lines",
            name=name,
            line=dict(color=COLOR_PALETTE[i % len(COLOR_PALETTE)])
        )

        fig.update_layout(
            title="Nyquist – DRT Smooth Fit",
            xaxis=dict(
                title="Z′ [Ω·cm²]",
                scaleanchor="y",
                scaleratio=1
            ),
            yaxis=dict(
                title="−Z″ [Ω·cm²]"
            ),
            template="plotly_dark",
            legend=dict(
                orientation="v",
                y=1,
                yanchor="top",
                x=1.02,
                xanchor="left",
                font=dict(size=11)
            ) if show_legend else dict(visible=False)
        )

    return fig

def cnls_line_plotly(df_cnls: pd.DataFrame, param: str, ylim=None):

    x = np.arange(1, len(df_cnls) + 1)
    y = df_cnls[param].values
    x_labels = [str(idx) for idx in df_cnls.index.tolist()]

    mean_val = np.nanmean(y)
    std_val = np.nanstd(y)

    fig = go.Figure()

    # ---- Main resistance line (NO legend) ----
    fig.add_scatter(
        x=x,
        y=y,
        mode="lines",
        line=dict(width=3, color="white"),
        showlegend=False
    )

    # ---- Points + Legend mapping ----
    for i, (idx, val) in enumerate(zip(df_cnls.index.tolist(), y)):

        label = latex_label(idx)

        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        fig.add_scatter(
            x=[i+1],
            y=[val],
            mode="markers",
            marker=dict(
                size=10,
                color="white",
                line=dict(width=2, color=color)
            ),
            name=f"{i+1} - {label}",
            showlegend=True
        )

    if param.startswith("tau"):
        _ylabel = "τ [s]"
    elif param.startswith("alpha"):
        _ylabel = "Dispersion factor"
    elif param == "L_hf" or re.fullmatch(r"L\d+", param):
        _ylabel = "L [H·cm²]"
    else:
        _ylabel = "R [Ω·cm²]"

    yaxis_cfg = {}
    if ylim is not None and ylim[0] is not None and ylim[1] is not None:
        yaxis_cfg["range"] = [ylim[0], ylim[1]]
    if param.startswith("tau"):
        yaxis_cfg["exponentformat"] = "e"
        yaxis_cfg["tickformat"] = ".2e"

    fig.update_layout(
        title=f"{param} — Mean value: {mean_val:.3g} | Std value: {std_val:.3g}",
        xaxis_title="File index",
        yaxis_title=_ylabel,
        template="plotly_dark",
        legend=dict(
            orientation="v",
            font=dict(size=11)
        ),
        xaxis=dict(
            tickmode="array",
            tickvals=x.tolist(),
            ticktext=x_labels,
            tickangle=30,
            automargin=True,
        ),
        yaxis=yaxis_cfg,
    )

    return fig




# EIS parameter mapping (restored)
EIS_PARAM_ORDER = [
    ("Cell area [cm²]", "CellArea/cm2"),
    ("Cell No.", "n_cell"),
    ("Instrument", "instrument_type"),
    ("Upper cut", "Nfh_cut"),
    ("Lower cut", "Nfl_cut"),
    ("Max. KK res. [%]", "kk_threshold"),
    ("Remove high KK resid.", "RmNonKK"),
    ("Remove outliers", "Rmoutliers"),
    ("Manual removal enabled", "ManualRemoval"),
    ("Manual removed indices", "ManualRemoval_Indices"),
    ("Rm significance", "rm_significance"),
    ("Z-HIT enabled", "ZHIT_enable"),
]


# ===============================
# Helpers
# ===============================

def _sync_multiselect_state(key: str, options: List[str]) -> None:
    """Drop stale selections from a keyed multiselect's session_state when its
    options change (e.g. after switching root folder), so the widget doesn't
    crash and the still-valid part of the previous selection survives."""
    if key in st.session_state:
        st.session_state[key] = [v for v in st.session_state[key] if v in options]

# ===============================
# Color palette selection
# ===============================

def _rgb_str_to_hex(s: str) -> str:
    # "rgb(12,34,56)" or "rgba(12,34,56,0.5)" -> "#0c2238"
    nums = s.strip().lower().replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")
    r, g, b = [int(float(x)) for x in nums[:3]]
    return f"#{r:02x}{g:02x}{b:02x}"

PLOTLY_SEQ = {
    "Viridis (perceptual)": pc.sequential.Viridis,
    "Cividis (colorblind-friendly)": pc.sequential.Cividis,
    "Plasma (perceptual)": pc.sequential.Plasma,
    "Inferno (perceptual)": pc.sequential.Inferno,
    "Magma (perceptual)": pc.sequential.Magma,
    "Turbo (high-contrast)": pc.sequential.Turbo,
}

def sample_plotly_sequential(palette_choice: str, n: int, lo: float = 0.10, hi: float = 0.95) -> List[str]:
    """
    Sample a Plotly sequential colorscale to n HEX colors.
    lo/hi trim avoids the extreme darkest/brightest ends.
    """
    scale = PLOTLY_SEQ[palette_choice]  # list of "rgb(...)"
    if n <= 1:
        t_vals = [0.5]
    else:
        t_vals = np.linspace(lo, hi, n)
    rgb_list = pc.sample_colorscale(scale, t_vals)
    return [_rgb_str_to_hex(c) for c in rgb_list]

PALETTE_LIBRARY = {
    "Default": "SOCEIS_DEFAULT",
    "Viridis (perceptual)": "viridis",
    "Cividis (colorblind-friendly)": "cividis",
    "Plasma (perceptual)": "plasma",
    "Inferno (perceptual)": "inferno",
    "Magma (perceptual)": "magma",
    "Turbo (high-contrast)": "turbo",
    "Matplotlib tab10": "tab10",
    "Matplotlib tab20": "tab20",
    "Matplotlib Set2 (pastel)": "Set2",
    "Matplotlib Dark2": "Dark2",
    "Matplotlib Paired": "Paired",

}


def sample_palette_colors(palette_choice: str, n: int) -> List[str]:
    # Default
    if palette_choice == "Default":
        base = DEFAULT_COLOR_PALETTE
        if n <= len(base):
            return base[:n]
        return (base * ((n + len(base) - 1) // len(base)))[:n]

    # Plotly scientific sequential palettes
    if palette_choice in PLOTLY_SEQ:
        return sample_plotly_sequential(palette_choice, n=n, lo=0.10, hi=0.95)

    # Matplotlib qualitative (tab10/tab20/Set2/Dark2/Paired)
    cmap_name = PALETTE_LIBRARY.get(palette_choice, "tab10")
    cmap = colormaps.get_cmap(cmap_name)
    if hasattr(cmap, "colors") and cmap.colors is not None:
        base = [mcolors.to_hex(c) for c in cmap.colors]
        if n <= len(base):
            return base[:n]
        return (base * ((n + len(base) - 1) // len(base)))[:n]

    # fallback (shouldn't usually hit)
    return DEFAULT_COLOR_PALETTE[:n]

def render_palette_preview(colors: List[str]) -> str:
    swatches = "".join(
        f"<span style='display:inline-block;width:18px;height:18px;"
        f"margin-right:6px;border-radius:4px;border:1px solid rgba(255,255,255,0.35);"
        f"background:{c};'></span>"
        for c in colors
    )
    return f"<div style='margin-top:6px;margin-bottom:4px;'>{swatches}</div>"

def latex_label(text: str) -> str:

    # Explicit LaTeX patterns
    if (
        "\\" in text or
        "_{" in text or
        "^{" in text
    ):
        # Avoid double wrapping
        if text.startswith("$") and text.endswith("$"):
            return text
        return f"${text}$"

    return text


def _resolve_initial_dir(current_dir: Optional[str], fallback_dir: Optional[Path]) -> Optional[Path]:
    """Resolve initial dialog directory: current path first, then fallback path."""
    if current_dir:
        try:
            p = Path(current_dir).expanduser()
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass

    if fallback_dir is not None:
        try:
            fb = Path(fallback_dir).expanduser()
            if fb.exists() and fb.is_dir():
                return fb
        except Exception:
            pass

    return None


def pick_folder_dialog(current_dir: Optional[str] = None,
                       fallback_dir: Optional[Path] = None) -> Optional[str]:
    """Open a native folder picker and return selected path or None."""
    initial_dir = _resolve_initial_dir(current_dir, fallback_dir)

    # On macOS, Finder chooser via AppleScript is usually more reliable
    # than tkinter inside Streamlit's runtime.
    if sys.platform == "darwin":
        try:
            choose_expr = "choose folder with prompt \"Select project folder\""
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
            # On macOS, canceling the Finder dialog should simply return None.
            # Do not fall back to tkinter in this case, as it can terminate the
            # Streamlit process in some runtime environments.
            return folder if folder else None
        except Exception:
            return None

    if not TK_AVAILABLE:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # bring dialog to front
    ask_kwargs = {}
    if initial_dir is not None:
        ask_kwargs["initialdir"] = str(initial_dir)
    folder = filedialog.askdirectory(**ask_kwargs)
    root.destroy()

    return folder if folder else None

def yes_no(v) -> str:
    return "Yes" if str(v).lower() in ("1", "true", "yes") else "No"


def discover_eis_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for eis_dir in root.rglob("EIS"):
        if eis_dir.is_dir():
            files.extend(sorted(eis_dir.glob("*.xlsx")))
    return files


def compress_indices(value) -> str:
    """
    Convert '1,2,3,4,5,6,7,8,9,10,37,41,42,43'
    -> '1-10,37,41-43'
    """

    if pd.isna(value):
        return ""

    try:
        nums = sorted(int(x.strip()) for x in str(value).split(",") if x.strip().isdigit())
    except Exception:
        return str(value)

    if not nums:
        return ""

    ranges = []
    start = nums[0]
    prev = nums[0]

    for n in nums[1:]:
        if n == prev + 1:
            prev = n
        else:
            ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = prev = n

    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")

    return ",".join(ranges)



def natural_key(s: str):
    """
    Natural sort key: 's2' < 's10', case-insensitive.
    Splits into text + number chunks.
    """
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def sibling_file(eis_file: Path, sibling_folder: str) -> Path:
    """
    sibling_folder is e.g. "DRT" or "CNLS".
    Assumption: .../<parent>/EIS/<file>.xlsx and .../<parent>/<sibling_folder>/<file>.xlsx
    """
    eis_dir = eis_file.parent          # .../EIS
    parent_dir = eis_dir.parent        # .../
    return parent_dir / sibling_folder / eis_file.name


def extract_eis_parameters(xls: pd.ExcelFile, fname: str) -> Dict:
    row = {"File": fname}
    if EIS_PARAMETERS_SHEET not in xls.sheet_names:
        for label, _ in EIS_PARAM_ORDER:
            row[label] = None
        return row

    df = pd.read_excel(xls, EIS_PARAMETERS_SHEET)
    for label, key in EIS_PARAM_ORDER:
        if key in df.columns:
            val = df[key].iloc[0]

            if key in ("RmNonKK", "Rmoutliers", "ManualRemoval", "rm_significance", "ZHIT_enable"):
                val = yes_no(val)

            if key == "ManualRemoval_Indices":
                val = compress_indices(val)

            row[label] = val
        else:
            row[label] = None
    return row

def has_drt_fit(files_to_process: List[Path]) -> bool:
    """
    True if at least one selected EIS file has a sibling DRT file
    containing the DRT-fit sheet 'Tknv_ReIm_s' with >= 4 columns.
    """
    for eis_file in files_to_process:
        drt_file = sibling_file(eis_file, "DRT")
        if not drt_file.exists():
            continue
        try:
            xls = pd.ExcelFile(_normalize_path(drt_file))
            if "Tknv_ReIm_s" in xls.sheet_names:
                df = pd.read_excel(xls, "Tknv_ReIm_s")
                if df.shape[1] >= 4:
                    return True
        except Exception:
            continue
    return False

def extract_drt_lambda(drt_xls: pd.ExcelFile, fname: str) -> Optional[Dict]:

    if DRT_PARAMETERS_SHEET not in drt_xls.sheet_names:
        return None

    df = pd.read_excel(drt_xls, DRT_PARAMETERS_SHEET)

    if not len(df):
        return None

    lam = df["lambda"].iloc[0] if "lambda" in df.columns else None

    # --- Read tknv_pos ---
    if "tknv_pos" in df.columns:
        tknv_pos_raw = df["tknv_pos"].iloc[0]
        tknv_pos = bool(tknv_pos_raw)
    else:
        tknv_pos = False

    rbf_enabled = bool(df["rbf_enabled"].iloc[0]) if "rbf_enabled" in df.columns else False

    return {
        "File": fname,
        "lambda": lam,
        "tknv_pos": tknv_pos,
        "rbf_enabled": rbf_enabled,
    }

def _drt_ymax_from_datasets(datasets) -> float:
    global_max = 0.0
    for _, df in datasets:
        if df.shape[1] < 2:
            continue
        gamma = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        gamma = gamma[np.isfinite(gamma)]
        if len(gamma):
            m = float(gamma.max())
            if m > global_max:
                global_max = m
    return 1.15 * global_max if global_max > 0 else 1.0


def _build_plotly_colorscale(colors: List[str]) -> list:
    n = len(colors)
    if n == 1:
        return [[0.0, colors[0]], [1.0, colors[0]]]
    return [[i / (n - 1), c] for i, c in enumerate(colors)]


def _add_colorbar(fig, datasets):
    """Replace legend with a continuous colorbar; show 4 tick labels from dataset names."""
    n = len(datasets)
    if n == 0:
        return
    colors = [COLOR_PALETTE[i % len(COLOR_PALETTE)] for i in range(n)]
    colorscale = _build_plotly_colorscale(colors)

    if n == 1:
        tick_indices = [0]
    elif n <= 4:
        tick_indices = list(range(n))
    else:
        tick_indices = [round(i * (n - 1) / 3) for i in range(4)]

    tickvals = [i / (n - 1) if n > 1 else 0.5 for i in tick_indices]
    ticktext = [datasets[i][0] for i in tick_indices]

    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(
            colorscale=colorscale,
            showscale=True,
            cmin=0,
            cmax=1,
            color=[0.5],
            colorbar=dict(
                tickvals=tickvals,
                ticktext=ticktext,
                thickness=15,
                len=0.75,
                outlinewidth=0,
            )
        ),
        showlegend=False,
        hoverinfo='skip'
    ))
    fig.update_layout(showlegend=False)


def _add_colorbar_3d(fig, datasets):
    """Add a continuous colorbar to a 3D figure, replacing the legend."""
    n = len(datasets)
    if n == 0:
        return
    colors = [COLOR_PALETTE[i % len(COLOR_PALETTE)] for i in range(n)]
    colorscale = _build_plotly_colorscale(colors)

    if n == 1:
        tick_indices = [0]
    elif n <= 4:
        tick_indices = list(range(n))
    else:
        tick_indices = [round(i * (n - 1) / 3) for i in range(4)]

    tickvals = [i / (n - 1) if n > 1 else 0.5 for i in tick_indices]
    ticktext = [datasets[i][0] for i in tick_indices]

    fig.add_trace(go.Scatter3d(
        x=[None], y=[None], z=[None],
        mode='markers',
        marker=dict(
            colorscale=colorscale,
            showscale=True,
            cmin=0,
            cmax=1,
            color=[0.5],
            size=0.001,
            colorbar=dict(
                tickvals=tickvals,
                ticktext=ticktext,
                thickness=15,
                len=0.75,
                outlinewidth=0,
            )
        ),
        showlegend=False,
        hoverinfo='skip'
    ))
    fig.update_layout(showlegend=False)


def _add_mpl_colorbar(fig, ax, datasets):
    """Add a matplotlib colorbar (4 tick labels) replacing the legend in saved plots."""
    n = len(datasets)
    if n == 0:
        return
    colors = [mcolors.to_rgba(COLOR_PALETTE[i % len(COLOR_PALETTE)]) for i in range(n)]
    cmap = mcolors.LinearSegmentedColormap.from_list("_palette", colors, N=256)
    norm = mcolors.Normalize(vmin=0, vmax=max(n - 1, 1))
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])

    if n == 1:
        tick_indices = [0]
    elif n <= 4:
        tick_indices = list(range(n))
    else:
        tick_indices = [round(i * (n - 1) / 3) for i in range(4)]

    cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_ticks([i for i in tick_indices])
    cbar.set_ticklabels([datasets[i][0] for i in tick_indices])
    cbar.outline.set_visible(False)


# ===============================
# CNLS topology helpers
# ===============================
def _parse_summary_elements(xls: pd.ExcelFile):
    """Return (names, type_map) from a CNLS 'Summary' sheet.

    names follow the order stored in ElementsNames; type_map maps each name to
    its ElementsType string (e.g. 'Resistor', 'Inductor', 'RQ'). Robust to the
    list being stored as a Python-list repr in a single cell.
    """
    if "Summary" not in xls.sheet_names:
        return [], {}
    summary = pd.read_excel(xls, "Summary", header=None)
    if summary.shape[0] < 2:
        return [], {}

    names_raw = str(summary.iloc[1, 0])
    names = re.findall(r"'([^']*)'", names_raw)
    if not names:
        # Fall back to bare tokens (e.g. RQ3, R8, L1).
        names = re.findall(r"[A-Za-z]+\d+", names_raw)

    types = []
    if summary.shape[1] > 1:
        types = re.findall(r"'([^']*)'", str(summary.iloc[1, 1]))
    type_map = {}
    for i, n in enumerate(names):
        type_map[n] = types[i] if i < len(types) else None
    return names, type_map


def cnls_topology_elements(xls: pd.ExcelFile):
    """Resolve every CNLS element to its Z/DRT columns by header name.

    Returns an ordered list of dicts (order from Summary.ElementsNames):
        {name, type, z_re, z_im, drt}
    where z_re/z_im are 'Z'-sheet column labels and drt is a 'DRT'-sheet column
    label; any may be None when the corresponding column is absent. Robust to
    arbitrary custom topologies (no fixed offsets, no RQ-only assumption).
    """
    names, type_map = _parse_summary_elements(xls)
    if not names:
        return []

    z_cols = []
    if "Z" in xls.sheet_names:
        z_cols = list(pd.read_excel(xls, "Z", nrows=0).columns)
    drt_cols = []
    if "DRT" in xls.sheet_names:
        drt_cols = list(pd.read_excel(xls, "DRT", nrows=0).columns)

    def _find(cols, pattern):
        for c in cols:
            if re.match(pattern, str(c)):
                return c
        return None

    elements = []
    for name in names:
        esc = re.escape(name)
        elements.append({
            "name": name,
            "type": type_map.get(name),
            "z_re": _find(z_cols, rf"{esc}_Re(/|$)"),
            "z_im": _find(z_cols, rf"{esc}_Im(/|$)"),
            "drt": _find(drt_cols, rf"DRT{esc}(/|$)"),
        })
    return elements


def _element_index(name: str):
    """Trailing integer index of an element name (e.g. 'RQ3' -> 3); None if absent."""
    m = re.search(r"(\d+)$", str(name))
    return int(m.group(1)) if m else None


# ===============================
# Equivalent-circuit schematic
# ===============================
# Self-contained copy of the topology grammar (see src/Methods/CNLS/Utils/Topology.py)
# so the standalone viewer has no import-path dependency.
#   '+'  series      '//' parallel (binds tighter)      () grouping
# AST nodes: ('leaf', name) | ('series', (..)) | ('parallel', (..))
def _topo_tokenize(expr):
    tokens, i, n = [], 0, len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
        elif c in "()+":
            tokens.append(c); i += 1
        elif c == "/":
            if i + 1 < n and expr[i + 1] == "/":
                tokens.append("//"); i += 2
            else:
                raise ValueError("Use '//' for parallel.")
        elif c.isalnum() or c == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append(expr[i:j]); i = j
        else:
            raise ValueError(f"Unexpected character '{c}'.")
    return tokens


def parse_topology_ast(expr):
    """Parse a topology string into a (kind, ...) AST. Raises ValueError on bad syntax."""
    tokens = _topo_tokenize(expr)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def expr_rule():
        nonlocal pos
        terms = [term_rule()]
        while peek() == "+":
            pos += 1
            terms.append(term_rule())
        return terms[0] if len(terms) == 1 else ("series", tuple(terms))

    def term_rule():
        nonlocal pos
        factors = [factor_rule()]
        while peek() == "//":
            pos += 1
            factors.append(factor_rule())
        return factors[0] if len(factors) == 1 else ("parallel", tuple(factors))

    def factor_rule():
        nonlocal pos
        tok = peek()
        if tok is None:
            raise ValueError("Unexpected end of expression.")
        if tok == "(":
            pos += 1
            node = expr_rule()
            if peek() != ")":
                raise ValueError("Missing ')'.")
            pos += 1
            return node
        if tok in ("+", "//", ")"):
            raise ValueError(f"Unexpected '{tok}'.")
        pos += 1
        return ("leaf", tok)

    node = expr_rule()
    if pos != len(tokens):
        raise ValueError(f"Unexpected token '{tokens[pos]}'.")
    return node


def get_cnls_topology(xls: pd.ExcelFile):
    """Return the topology string from a CNLS 'Summary' sheet (or a series fallback)."""
    names, _ = _parse_summary_elements(xls)
    if "Summary" in xls.sheet_names:
        summary = pd.read_excel(xls, "Summary", header=None)
        if summary.shape[0] >= 2:
            headers = [str(h) for h in summary.iloc[0].tolist()]
            if "topology" in headers:
                topo = summary.iloc[1, headers.index("topology")]
                if isinstance(topo, str) and topo.strip():
                    return topo.strip()
    # Fallback: all elements in series.
    return " + ".join(names) if names else ""


# --- Schematic rendering (matplotlib port of the CNLS Selector preview) ---
# The Selector window (src/GUI/Utils/cnls_functions.py) draws the equivalent
# circuit on a dearpygui drawlist using pixel coordinates with y pointing down.
# This block reproduces that exact visual style on a matplotlib axis: we work in
# the same pixel/y-down space and invert the y-axis at the end. Colours match the
# Selector (light-blue symbols on a dark canvas, light-grey wires).
_SCH_DPI = 150.0
_SCH_WIRE_COLOR = (0, 0, 0, 255)
_SCH_SYMBOL_COLOR = (0, 0, 0, 255)
_SCH_SYMBOL_FILL = (255, 255, 255, 255)
_SCH_RESISTOR_FILL = (255, 255, 255, 255)
_SCH_LABEL_COLOR = (0, 0, 0, 255)
_SCH_BG_COLOR = (255, 255, 255, 255)
_SCH_SYMBOL_W = 84.0


def _sch_rgba(c):
    """Convert a 0-255 RGBA tuple to a matplotlib 0-1 RGBA tuple."""
    if len(c) == 3:
        return (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1.0)
    return (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, c[3] / 255.0)


class _SchDraw:
    """dearpygui-style draw adapter over a matplotlib axis (pixel/y-down units)."""

    def __init__(self, ax):
        self.ax = ax

    def _lw(self, thickness):
        return max(0.6, float(thickness) * 72.0 / _SCH_DPI)

    def line(self, p0, p1, color, thickness):
        self.ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=_sch_rgba(color),
                     lw=self._lw(thickness), solid_capstyle="round")

    def polyline(self, points, color, thickness):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self.ax.plot(xs, ys, color=_sch_rgba(color), lw=self._lw(thickness),
                     solid_capstyle="round", solid_joinstyle="round")

    def rect(self, p0, p1, color, fill, thickness):
        x = min(p0[0], p1[0])
        y = min(p0[1], p1[1])
        w = abs(p1[0] - p0[0])
        h = abs(p1[1] - p0[1])
        self.ax.add_patch(mpatches.Rectangle(
            (x, y), w, h, linewidth=self._lw(thickness),
            edgecolor=_sch_rgba(color),
            facecolor=_sch_rgba(fill) if fill is not None else "none",
        ))

    def circle(self, center, radius, color, fill, thickness):
        self.ax.add_patch(mpatches.Circle(
            center, radius, linewidth=self._lw(thickness),
            edgecolor=_sch_rgba(color),
            facecolor=_sch_rgba(fill) if fill is not None else "none",
        ))

    def text(self, pos, text, color, size):
        # dearpygui anchors text at its top-left; replicate with va='top'.
        self.ax.text(pos[0], pos[1], str(text), color=_sch_rgba(color),
                     fontsize=size * 72.0 / _SCH_DPI, ha="left", va="top")


def _estimate_text_width(label, font_size):
    """Estimate drawlist text width (ported from the Selector)."""
    width_units = 0.0
    for ch in str(label):
        if ch in "WwMm@#%&":
            width_units += 0.88
        elif ch in "firtjlI1|":
            width_units += 0.38
        elif ch.isupper():
            width_units += 0.66
        elif ch.islower():
            width_units += 0.56
        elif ch.isdigit():
            width_units += 0.58
        else:
            width_units += 0.60
    return max(6.0, width_units * float(font_size))


def _sch_resistor(D, x0, x1, y, color, thickness):
    width = max(12.0, x1 - x0)
    mid = (x0 + x1) / 2.0
    lead_target = 15.0
    max_body_from_lead = max(8.0, width - 2.0 * lead_target)
    body_w = min(42.0, max(14.0, width * 0.34), max_body_from_lead)
    r0 = mid - body_w / 2.0
    r1 = mid + body_w / 2.0
    rect_h = min(7.0, max(4.6, body_w * 0.16))
    D.line((x0, y), (r0, y), color, thickness)
    D.line((r1, y), (x1, y), color, thickness)
    D.rect((r0, y - rect_h), (r1, y + rect_h), color, _SCH_RESISTOR_FILL, 1.8)


def _sch_capacitor(D, x0, x1, y, color, thickness):
    mid = (x0 + x1) / 2.0
    gap = min(7.0, max(4.0, (x1 - x0) / 6.0))
    plate_h = 16
    D.line((x0, y), (mid - gap, y), color, thickness)
    D.line((mid - gap, y - plate_h), (mid - gap, y + plate_h), color, thickness)
    D.line((mid + gap, y - plate_h), (mid + gap, y + plate_h), color, thickness)
    D.line((mid + gap, y), (x1, y), color, thickness)


def _sch_inductor(D, x0, x1, y, color, thickness):
    coil_count = 4
    span = max(20.0, x1 - x0)
    radius = span / (coil_count * 2.0)
    left = (x0 + x1) / 2.0 - coil_count * radius
    D.line((x0, y), (left, y), color, thickness)
    for i in range(coil_count):
        cx = left + radius * (2 * i + 1)
        D.circle((cx, y), radius, color, None, thickness)
    D.line((left + coil_count * 2.0 * radius, y), (x1, y), color, thickness)


def _sch_cpe(D, x0, x1, y, color, thickness):
    width = max(14.0, x1 - x0)
    min_inner_span = 6.0
    max_lead = max(2.0, (width - min_inner_span) / 2.0)
    lead = min(max_lead, max(15.0, width * 0.20))
    c0 = x0 + lead
    c1 = x1 - lead
    D.line((x0, y), (c0, y), color, thickness)
    D.line((c1, y), (x1, y), color, thickness)
    span = max(10.0, c1 - c0)
    h = min(6.8, max(4.2, span * 0.19))
    left_center = c0 + span * 0.40
    right_center = c0 + span * 0.60
    half = max(2.4, span * 0.10)
    D.polyline([(left_center + half, y - h), (left_center - half, y), (left_center + half, y + h)], color, thickness)
    D.polyline([(right_center + half, y - h), (right_center - half, y), (right_center + half, y + h)], color, thickness)


def _sch_abbrev_series(D, x0, x1, y, color, label, thickness=2):
    width = max(12.0, x1 - x0)
    min_inner_span = 6.0
    max_lead = max(2.0, (width - min_inner_span) / 2.0)
    lead = min(max_lead, max(15.0, width * 0.20))
    t0 = x0 + lead
    t1 = x1 - lead
    D.line((x0, y), (t0, y), color, thickness)
    D.line((t1, y), (x1, y), color, thickness)
    label_str = str(label)
    inner_span = max(8.0, t1 - t0)
    if label_str in ["W", "G", "FLW", "fFLW"]:
        factor = 0.52 if label_str == "W" else 0.56
        font_size = int(max(18, min(24, inner_span * factor)))
    elif len(label_str) <= 2:
        font_size = int(max(16, min(22, inner_span * 0.40)))
    elif len(label_str) <= 4:
        font_size = int(max(14, min(19, inner_span * 0.31)))
    else:
        font_size = int(max(12, min(17, inner_span * 0.25)))
    text_w = _estimate_text_width(label_str, font_size)
    tx = (x0 + x1) / 2.0 - text_w / 2.0
    ty = y - font_size * 0.46
    D.text((tx, ty), label_str, _SCH_LABEL_COLOR, font_size)


def _sch_generic_block(D, x0, x1, y, color, fill):
    D.rect((x0, y - 13), (x1, y + 13), color, fill, 1.5)


def _sch_label_block(D, x0, x1, y, color, fill, label):
    _sch_generic_block(D, x0, x1, y, color, fill)
    tx = (x0 + x1) / 2.0 - 5
    D.text((tx, y - 7), str(label), _SCH_LABEL_COLOR, 13)


def _sch_parallel_branch(D, x0, x1, y, color, fill, lower_type):
    top_y = y - 16
    bot_y = y + 16
    D.line((x0, top_y), (x0, bot_y), color, 2)
    D.line((x1, top_y), (x1, bot_y), color, 2)
    D.circle((x0, y), 1.8, color, color, 1)
    D.circle((x1, y), 1.8, color, color, 1)
    _sch_resistor(D, x0, x1, top_y, color, 2)
    if lower_type == "capacitor":
        _sch_capacitor(D, x0, x1, bot_y, color, 2)
    elif lower_type == "cpe":
        _sch_cpe(D, x0, x1, bot_y, color, 2)
    elif lower_type == "label_w":
        _sch_label_block(D, x0 + 4, x1 - 4, bot_y, color, fill, "W")
    elif lower_type == "label_g":
        _sch_label_block(D, x0 + 4, x1 - 4, bot_y, color, fill, "G")
    else:
        _sch_generic_block(D, x0 + 4, x1 - 4, bot_y, color, fill)


def _sch_randle_symbol(D, x0, x1, y, color, fill, cpe=False, warburg_is_fractal=False):
    width = max(44.0, x1 - x0)
    lead = min(8.0, max(4.0, width * 0.08))
    core0 = x0 + lead
    core1 = x1 - lead
    core_w = max(24.0, core1 - core0)
    top_y = y - 16
    bot_y = y + 16
    D.line((x0, y), (core0, y), color, 2)
    D.line((core1, y), (x1, y), color, 2)
    D.line((core0, top_y), (core0, bot_y), color, 2)
    D.line((core1, top_y), (core1, bot_y), color, 2)
    D.circle((core0, y), 1.8, color, color, 1)
    D.circle((core1, y), 1.8, color, color, 1)
    if cpe:
        _sch_cpe(D, core0, core1, top_y, color, 2)
    else:
        _sch_capacitor(D, core0, core1, top_y, color, 2)
    r_end = core0 + core_w * 0.46
    w_start = r_end + core_w * 0.08
    _sch_resistor(D, core0, r_end, bot_y, color, 2)
    D.line((r_end, bot_y), (w_start, bot_y), color, 2)
    if w_start < core1 - 2:
        warburg_label = "fFLW" if warburg_is_fractal else "FLW"
        _sch_abbrev_series(D, w_start, core1, bot_y, color, warburg_label, thickness=2)
    else:
        D.line((w_start, bot_y), (core1, bot_y), color, 2)


def _sch_element_symbol(D, element_type, x0, x1, y, color, fill):
    sx0, sx1 = x0, x1
    width = max(1.0, x1 - x0)
    pad = min(8.0, max(2.0, width * 0.08))
    x0 = x0 + pad
    x1 = x1 - pad
    D.line((sx0, y), (x0, y), color, 2)
    D.line((x1, y), (sx1, y), color, 2)
    thickness = 2
    et = str(element_type)
    if et == "Resistor":
        _sch_resistor(D, x0, x1, y, color, thickness)
    elif et == "RC":
        _sch_parallel_branch(D, x0, x1, y, color, fill, lower_type="capacitor")
    elif et == "RQ":
        _sch_parallel_branch(D, x0, x1, y, color, fill, lower_type="cpe")
    elif et == "Gerisher":
        _sch_abbrev_series(D, x0, x1, y, color, "G", thickness=thickness)
    elif et == "FLW":
        _sch_abbrev_series(D, x0, x1, y, color, "FLW", thickness=thickness)
    elif et == "fFLW":
        _sch_abbrev_series(D, x0, x1, y, color, "fFLW", thickness=thickness)
    elif et in ["Capacitor", "CPE"]:
        if et == "CPE":
            _sch_cpe(D, x0, x1, y, color, thickness)
        else:
            _sch_capacitor(D, x0, x1, y, color, thickness)
    elif et in ["Inductor", "Inductor_a"]:
        _sch_inductor(D, x0, x1, y, color, thickness)
    elif et == "Warburg":
        _sch_abbrev_series(D, x0, x1, y, color, "W", thickness=thickness)
    elif et == "RandleC":
        _sch_randle_symbol(D, x0, x1, y, color, fill, cpe=False, warburg_is_fractal=False)
    elif et == "RandleCPE":
        _sch_randle_symbol(D, x0, x1, y, color, fill, cpe=True, warburg_is_fractal=False)
    elif et == "RandleCfFLW":
        _sch_randle_symbol(D, x0, x1, y, color, fill, cpe=False, warburg_is_fractal=True)
    elif et == "RandleCPEfFLW":
        _sch_randle_symbol(D, x0, x1, y, color, fill, cpe=True, warburg_is_fractal=True)
    else:
        _sch_generic_block(D, x0, x1, y, color, fill)


def _sch_measure(node, units_by_name):
    """Return (width_units, height_units). Series: widths add, height max.
    Parallel: heights add, width max. (Ported from the Selector.)"""
    if node[0] == "leaf":
        return (units_by_name.get(node[1], 1.0), 1.0)
    sizes = [_sch_measure(c, units_by_name) for c in node[1]]
    if node[0] == "series":
        return (sum(w for w, _ in sizes), max(h for _, h in sizes))
    return (max(w for w, _ in sizes), sum(h for _, h in sizes))


def _sch_draw(D, node, x0, x1, yc, branch_h, ctx):
    """Recursively draw an AST node into [x0, x1] centered at yc (Selector port)."""
    if node[0] == "leaf":
        name = node[1]
        etype = ctx["type_by_name"].get(name, "Resistor")
        units = ctx["units_by_name"].get(name, 1.0)
        sym_w = min(x1 - x0, ctx["symbol_w"] * units)
        cx = (x0 + x1) / 2.0
        bx0, bx1 = cx - sym_w / 2.0, cx + sym_w / 2.0
        if bx0 > x0:
            D.line((x0, yc), (bx0, yc), ctx["wire_color"], ctx["wire_thickness"])
        if bx1 < x1:
            D.line((bx1, yc), (x1, yc), ctx["wire_color"], ctx["wire_thickness"])
        _sch_element_symbol(D, etype, bx0, bx1, yc, ctx["symbol_color"], ctx["symbol_fill"])
        font = ctx["label_font"]
        label_y = min(ctx["draw_h"] - font - 4.0, yc + branch_h * 0.30)
        label_w = max(18.0, len(name) * (font * 0.52))
        D.text((cx - label_w / 2.0, label_y), name, _SCH_LABEL_COLOR, font)
        return

    children = node[1]
    sizes = [_sch_measure(c, ctx["units_by_name"]) for c in children]

    if node[0] == "series":
        total_w = max(1e-9, sum(w for w, _ in sizes))
        gap = ctx["gap"]
        inner = (x1 - x0) - gap * (len(children) - 1)
        cursor = x0
        for idx, (child, (cw, _)) in enumerate(zip(children, sizes)):
            seg = inner * (cw / total_w)
            cx0, cx1 = cursor, cursor + seg
            _sch_draw(D, child, cx0, cx1, yc, branch_h, ctx)
            if idx < len(children) - 1:
                D.line((cx1, yc), (cx1 + gap, yc), ctx["wire_color"], ctx["wire_thickness"])
            cursor = cx1 + gap
        return

    # parallel: stack children vertically, join with left/right vertical buses.
    total_h = max(1e-9, sum(h for _, h in sizes))
    H_px = total_h * branch_h
    lead_w = min(22.0, max(10.0, (x1 - x0) * 0.10))
    xL, xR = x0 + lead_w, x1 - lead_w
    top = yc - H_px / 2.0
    centers, cum = [], 0.0
    for _, ch in sizes:
        band = ch * branch_h
        centers.append(top + cum + band / 2.0)
        cum += band
    D.line((x0, yc), (xL, yc), ctx["wire_color"], ctx["wire_thickness"])
    D.line((xR, yc), (x1, yc), ctx["wire_color"], ctx["wire_thickness"])
    D.line((xL, centers[0]), (xL, centers[-1]), ctx["wire_color"], ctx["wire_thickness"])
    D.line((xR, centers[0]), (xR, centers[-1]), ctx["wire_color"], ctx["wire_thickness"])
    for child, cyc in zip(children, centers):
        _sch_draw(D, child, xL, xR, cyc, branch_h, ctx)


def cnls_circuit_figure(cnls_file: Path):
    """Build a matplotlib equivalent-circuit schematic matching the CNLS Selector."""
    if not cnls_file.exists():
        return None
    try:
        xls = pd.ExcelFile(_normalize_path(cnls_file))
    except Exception:
        return None

    topo = get_cnls_topology(xls)
    if not topo:
        return None
    try:
        ast_root = parse_topology_ast(topo)
    except ValueError:
        return None

    _, type_map = _parse_summary_elements(xls)
    type_by_name = {str(n): str(t or "") for n, t in type_map.items()}
    units_by_name = {n: (2.0 if t.startswith("Randle") else 1.0) for n, t in type_by_name.items()}

    W, H = _sch_measure(ast_root, units_by_name)

    margin = 26.0
    term_lead = 16.0
    top_pad = 18.0
    label_room = 30.0
    gap = 18.0
    symbol_w = _SCH_SYMBOL_W
    branch_h = 72.0

    # Size the canvas so symbols keep their natural width and wires fill the rest.
    draw_w = 2.0 * (margin + term_lead) + W * (symbol_w + gap)
    draw_h = top_pad + H * branch_h + label_room

    fig, ax = plt.subplots(figsize=(draw_w / _SCH_DPI, draw_h / _SCH_DPI), dpi=_SCH_DPI)
    fig.patch.set_facecolor(_sch_rgba(_SCH_BG_COLOR))
    ax.set_facecolor(_sch_rgba(_SCH_BG_COLOR))

    H_px = H * branch_h
    yc = max(top_pad + H_px / 2.0, (draw_h - label_room) / 2.0)

    ctx = {
        "type_by_name": type_by_name,
        "units_by_name": units_by_name,
        "wire_color": _SCH_WIRE_COLOR,
        "symbol_color": _SCH_SYMBOL_COLOR,
        "symbol_fill": _SCH_SYMBOL_FILL,
        "wire_thickness": 2.0,
        "gap": gap,
        "label_font": 14,
        "draw_h": draw_h,
        "symbol_w": symbol_w,
    }

    D = _SchDraw(ax)
    x0 = margin + term_lead
    x1 = draw_w - margin - term_lead
    D.line((margin, yc), (x0, yc), _SCH_WIRE_COLOR, 2.0)
    D.line((x1, yc), (draw_w - margin, yc), _SCH_WIRE_COLOR, 2.0)
    _sch_draw(D, ast_root, x0, x1, yc, branch_h, ctx)

    ax.set_xlim(0, draw_w)
    ax.set_ylim(0, draw_h)
    ax.invert_yaxis()  # match dearpygui's y-down convention
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    return fig


def extract_cnls_parameters(cnls_file: Path) -> Optional[Dict[str, float]]:

    if not cnls_file.exists():
        return None

    try:
        xls = pd.ExcelFile(_normalize_path(cnls_file))
    except Exception:
        return None

    if CNLS_SHEET not in xls.sheet_names:
        return None

    df = pd.read_excel(xls, CNLS_SHEET)

    if df.shape[1] < 2:
        return None

    names = df.iloc[:, 0].astype(str).str.strip()
    vals = pd.to_numeric(df.iloc[:, 1], errors="coerce")

    result: Dict[str, float] = {}

    # Element name for each parameter is the name minus its trailing suffix
    # (e.g. 'RQ3_tau0' -> 'RQ3', 'R8_R' -> 'R8', 'L1_L' -> 'L1').
    element_names = {n.rsplit("_", 1)[0] for n in names if "_" in n}

    # Ohmic resistor = lowest-index pure series resistor (matches the R2 convention);
    # HF inductor = lowest-index inductor (the L1 convention). All other R/L elements
    # are extra standalone elements introduced by custom topology.
    pure_resistors = sorted(
        (e for e in element_names if re.fullmatch(r"R\d+", e)),
        key=lambda e: _element_index(e) or 0,
    )
    inductors = sorted(
        (e for e in element_names if re.fullmatch(r"L\d+", e)),
        key=lambda e: _element_index(e) or 0,
    )
    ohmic_name = pure_resistors[0] if pure_resistors else None
    hf_inductor_name = inductors[0] if inductors else None

    result["R_ohmic"] = np.nan
    if hf_inductor_name is not None:
        result["L_hf"] = np.nan

    for name, value in zip(names, vals):
        if pd.isna(value) or "_" not in name:
            continue
        element, suffix = name.rsplit("_", 1)
        idx = _element_index(element)

        if suffix == "R":
            if element == ohmic_name:
                result["R_ohmic"] = float(value)
            elif idx is not None:
                # RQ resistances and extra standalone resistors (e.g. R8).
                result[f"R{idx}"] = float(value)
        elif suffix == "tau0" and idx is not None:
            result[f"tau{idx}"] = float(value)
        elif suffix == "alpha" and idx is not None:
            result[f"alpha{idx}"] = float(value)
        elif suffix == "L":
            if element == hf_inductor_name:
                result["L_hf"] = float(value)
            elif idx is not None:
                result[f"L{idx}"] = float(value)

    # ---- R_pol = whole-circuit resistance except ohmic (R2) and HF inductance (L1) ----
    # i.e. every R{idx}: RQ resistances and extra standalone resistors.
    rq_values = [v for k, v in result.items() if re.fullmatch(r"R\d+", k)]
    result["R_pol"] = float(np.nansum(rq_values)) if rq_values else np.nan

    # ---- ASR = R_ohmic + R_pol ----
    asr_values = [result.get("R_ohmic", np.nan)] + rq_values
    result["ASR"] = float(np.nansum(asr_values)) if not all(pd.isna(v) for v in asr_values) else np.nan

    return result


def extract_eis_resistances(xls: pd.ExcelFile) -> Optional[Dict[str, float]]:
    """R_ohm / R_pol from the KK 'Resistance' sheet of an EIS file. ASR = R_ohm + R_pol."""
    if "Resistance" not in xls.sheet_names:
        return None
    df = pd.read_excel(xls, "Resistance")
    if df.empty:
        return None
    row = df.iloc[0]
    res: Dict[str, float] = {}
    for col in df.columns:
        c = str(col).strip()
        if c.startswith("Rohm"):
            res["R_ohm"] = float(pd.to_numeric(row[col], errors="coerce"))
        elif c.startswith("Rp"):
            res["R_pol"] = float(pd.to_numeric(row[col], errors="coerce"))
    if not res:
        return None
    res["ASR"] = float(np.nansum([res.get("R_ohm", np.nan), res.get("R_pol", np.nan)]))
    return res


DRT_RES_SHEET_MAP = {
    "Truncated": "Resistance_truncated",
    "Smooth": "Resistance_smooth",
    "LCcorrect": "Resistance_LCcorrect",
    "Extrapolation": "Resistance_extrapolation",
    "Z-HIT": "Resistance_zhit",
    "RBF": "RBF_Resistance_truncated",
    "RBF Smooth": "RBF_Resistance_smooth",
    "RBF LCcorrect": "RBF_Resistance_LCcorrect",
    "RBF Extrapolation": "RBF_Resistance_extrapolation",
    "RBF Z-HIT": "RBF_Resistance_zhit",
}


def extract_drt_resistances(xls: pd.ExcelFile, method: str, mode: str = "ReIm") -> Optional[Dict[str, float]]:
    """R_ohm / R_pol from a DRT 'Resistance_<method>' sheet (DRT_<mode> columns). ASR = R_ohm + R_pol."""
    sheet = DRT_RES_SHEET_MAP.get(method)
    if sheet is None or sheet not in xls.sheet_names:
        return None
    df = pd.read_excel(xls, sheet)
    if df.empty:
        return None
    row = df.iloc[0]
    suffix = f"- DRT_{mode}"
    res: Dict[str, float] = {}
    for col in df.columns:
        c = str(col).strip()
        if not c.endswith(suffix):
            continue
        if c.startswith("Rohm"):
            res["R_ohm"] = float(pd.to_numeric(row[col], errors="coerce"))
        elif c.startswith("Rp"):
            res["R_pol"] = float(pd.to_numeric(row[col], errors="coerce"))
    if not res:
        return None
    res["ASR"] = float(np.nansum([res.get("R_ohm", np.nan), res.get("R_pol", np.nan)]))
    return res


def render_resistance_table(df_res: pd.DataFrame, columns, rename=None):
    """Render a table with the file label as the first column + the given resistance columns."""
    cols = [c for c in columns if c in df_res.columns]
    if not cols:
        return
    tbl = df_res[cols].copy()
    if rename:
        tbl = tbl.rename(columns=rename)
    tbl.insert(0, "Label", df_res.index)
    st.dataframe(tbl, width="stretch", hide_index=True)


# ===============================
# Plotly builders (interactive)
# ===============================
def nyquist_plotly(datasets, title):

    fig = go.Figure()

    for i, (name, df) in enumerate(datasets):
        fig.add_scatter(
            x=pd.to_numeric(df.iloc[:, 1], errors="coerce"),
            y=-pd.to_numeric(df.iloc[:, 2], errors="coerce"),
            mode="markers+lines",
            name=name,
            line=dict(color=COLOR_PALETTE[i % len(COLOR_PALETTE)]),
        )

    fig.update_layout(
        title=title,
        xaxis=dict(
            title="Z′ [Ω·cm²]",
            scaleanchor="y",
            scaleratio=1
        ),
        yaxis=dict(
            title="−Z″ [Ω·cm²]"
        ),
        template="plotly_dark",
        height=650  # enforce square aspect visually
    )

    if st.session_state.get("colorbar_mode", False):
        _add_colorbar(fig, datasets)

    return fig

def nyquist_compare_plotly(compare_mode, files_to_process, display_name_map):

    fig = go.Figure()

    mapping = {
        "Truncated vs Original": ("Truncated", "Original"),
        "Smooth vs Truncated": ("Truncated", "Smooth"),
        "LC corrected vs Truncated": ("Truncated", "LC corrected"),
        "Extended vs Truncated": ("Truncated", "Extended"),
        "DRT Fit vs Truncated": ("Truncated", "DRT Fit"),
        "CNLS Fit vs Truncated": ("Truncated", "CNLS Fit"),
    }

    sheet_trunc, sheet_other = mapping[compare_mode]

    for i, eis_file in enumerate(files_to_process):

        fname = eis_file.name
        label = latex_label(display_name_map.get(fname, fname))
        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        xls = pd.ExcelFile(_normalize_path(eis_file))

        # -------------------------
        # Load Truncated (always needed)
        # -------------------------
        df_trunc = None
        if sheet_trunc in xls.sheet_names:
            df_trunc = pd.read_excel(xls, sheet_trunc)

        # -------------------------
        # Load comparison dataset
        # -------------------------
        df_other = None

        if sheet_other == "DRT Fit":
            drt_file = sibling_file(eis_file, "DRT")
            if drt_file.exists():
                drt_xls = pd.ExcelFile(_normalize_path(drt_file))
                if "Tknv_ReIm_s" in drt_xls.sheet_names:
                    df_other = pd.read_excel(drt_xls, "Tknv_ReIm_s")
        elif sheet_other == "CNLS Fit":
            cnls_file = sibling_file(eis_file, "CNLS")
            if cnls_file.exists():
                cnls_xls = pd.ExcelFile(_normalize_path(cnls_file))
                if "Z" in cnls_xls.sheet_names:
                    df_other = pd.read_excel(cnls_xls, "Z")
        else:
            if sheet_other in xls.sheet_names:
                df_other = pd.read_excel(xls, sheet_other)

        if df_trunc is None:
            continue

        # ============================================================
        # CASE 1 → Truncated vs Original
        # ============================================================
        if compare_mode == "Truncated vs Original":

            # ---- Original FIRST (transparent hollow circles)
            if df_other is not None:
                fig.add_scatter(
                    x=pd.to_numeric(df_other.iloc[:, 1], errors="coerce"),
                    y=-pd.to_numeric(df_other.iloc[:, 2], errors="coerce"),
                    mode="markers",
                    marker=dict(
                        size=7,
                        symbol="circle",
                        color="rgba(0,0,0,0)",      # transparent fill
                        line=dict(width=2, color=color),
                        opacity=0.5
                    ),
                    name=f"{label} - Original"
                )

            # ---- Truncated SECOND (solid filled circles)
            fig.add_scatter(
                x=pd.to_numeric(df_trunc.iloc[:, 1], errors="coerce"),
                y=-pd.to_numeric(df_trunc.iloc[:, 2], errors="coerce"),
                mode="markers",
                marker=dict(
                    size=7,
                    symbol="circle",
                    color=color,
                    opacity=1.0,
                    line=dict(width=1, color=color)
                ),
                name=f"{label} - Truncated"
            )

        # ============================================================
        # CASE 2 → X vs Truncated
        # ============================================================
        else:

            # ---- Truncated (filled markers, NO legend)
            fig.add_scatter(
                x=pd.to_numeric(df_trunc.iloc[:, 1], errors="coerce"),
                y=-pd.to_numeric(df_trunc.iloc[:, 2], errors="coerce"),
                mode="markers",
                marker=dict(
                    size=6,
                    symbol="circle",
                    color=color,
                    opacity=1.0,
                    line=dict(width=1, color=color)
                ),
                showlegend=False  # <-- important
            )

            if df_other is not None:

                if sheet_other == "DRT Fit":
                    xcol = 2
                    ycol = 3
                elif sheet_other == "CNLS Fit":
                    # CNLS 'Z' sheet: Ztot_Re (col 3), Ztot_Im (col 4).
                    xcol = 3
                    ycol = 4
                else:
                    xcol = 1
                    ycol = 2

                # ---- Comparison curve (LINE only, appears in legend)
                fig.add_scatter(
                    x=pd.to_numeric(df_other.iloc[:, xcol], errors="coerce"),
                    y=-pd.to_numeric(df_other.iloc[:, ycol], errors="coerce"),
                    mode="lines",
                    line=dict(width=3, color=color),
                    name=label  # <-- ONLY filename in legend
                )

    fig.update_layout(
        title=f"Nyquist Compare – {compare_mode}",
        xaxis=dict(
            title="Z′ [Ω·cm²]",
            scaleanchor="y",
            scaleratio=1
        ),
        yaxis=dict(title="−Z″ [Ω·cm²]"),
        template="plotly_dark"
    )

    if st.session_state.get("colorbar_mode", False):
        pseudo = [
            (latex_label(display_name_map.get(f.name, f.stem)), None)
            for f in files_to_process
        ]
        _add_colorbar(fig, pseudo)

    return fig

def bode_plotly(datasets, title, real=True):
    fig = go.Figure()
    for i, (name, df) in enumerate(datasets):
        x = pd.to_numeric(df.iloc[:, 0], errors="coerce")
        y = pd.to_numeric(df.iloc[:, 1], errors="coerce") if real else -pd.to_numeric(df.iloc[:, 2], errors="coerce")
        fig.add_scatter(
            x=x,
            y=y,
            mode="lines",
            name=name,
            line=dict(color=COLOR_PALETTE[i % len(COLOR_PALETTE)]),
        )
    fig.update_layout(
        title="",
        xaxis=dict(title="Frequency [Hz]", type="log"),
        yaxis_title="Z′ [Ω·cm²]" if real else "−Z″ [Ω·cm²]",
        template="plotly_dark",
    )

    if st.session_state.get("colorbar_mode", False):
        _add_colorbar(fig, datasets)

    return fig


def zhit_plotly(datasets, mode: str = "modulus"):
    """
    Plot Z-HIT results.
    mode: "modulus"  → |Z| measured (markers) vs Z-HIT reconstructed (line)
          "phase"    → φ measured (markers) vs φ smoothed (dashed line)
          "delta"    → Δln|Z| deviation [%] per frequency
    ZHIT sheet columns:
      0 Frequency/Hz, 1 omega/rad/s, 2 Z_mod_meas/ohm·cm2,
      3 Z_mod_zhit/ohm·cm2, 4 phi_deg, 5 phi_smooth_deg,
      6 phase_integral, 7 correction, 8 delta_lnZ, 9 delta_lnZ_pct
    """
    fig = go.Figure()
    for i, (name, df) in enumerate(datasets):
        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
        freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")

        if mode == "modulus":
            y_meas = pd.to_numeric(df.iloc[:, 2], errors="coerce")
            y_zhit = pd.to_numeric(df.iloc[:, 3], errors="coerce")
            fig.add_scatter(
                x=freq, y=y_meas, mode="markers",
                name=f"{name} – meas",
                legendgroup=name,
                marker=dict(size=4, color=color, opacity=0.6),
            )
            fig.add_scatter(
                x=freq, y=y_zhit, mode="lines",
                name=f"{name} – Z-HIT",
                legendgroup=name,
                line=dict(color=color, width=2),
            )
        elif mode == "phase":
            phi_meas   = pd.to_numeric(df.iloc[:, 4], errors="coerce")
            phi_smooth = pd.to_numeric(df.iloc[:, 5], errors="coerce")
            fig.add_scatter(
                x=freq, y=phi_meas, mode="markers",
                name=f"{name} – φ meas",
                legendgroup=name,
                marker=dict(size=4, color=color, opacity=0.6),
            )
            fig.add_scatter(
                x=freq, y=phi_smooth, mode="lines",
                name=f"{name} – φ smooth",
                legendgroup=name,
                line=dict(color=color, width=2, dash="dash"),
            )
        elif mode == "delta":
            delta_pct = pd.to_numeric(df.iloc[:, 9], errors="coerce")
            fig.add_scatter(
                x=freq, y=delta_pct, mode="lines+markers",
                name=name,
                line=dict(color=color, width=2),
                marker=dict(size=4, color=color),
            )

    if mode == "modulus":
        fig.update_layout(
            title="Z-HIT – |Z| comparison",
            xaxis=dict(title="Frequency [Hz]", type="log"),
            yaxis=dict(title="|Z| [Ω·cm²]", type="log"),
            template="plotly_dark",
        )
    elif mode == "phase":
        fig.update_layout(
            title="Z-HIT – Phase",
            xaxis=dict(title="Frequency [Hz]", type="log"),
            yaxis=dict(title="φ [°]"),
            template="plotly_dark",
        )
    elif mode == "delta":
        fig.update_layout(
            title="Z-HIT – ln|Z| deviation [%]",
            xaxis=dict(title="Frequency [Hz]", type="log"),
            yaxis=dict(title="Δln|Z| [%]"),
            template="plotly_dark",
        )
    return fig


def drt_plotly(datasets, title):
    fig = go.Figure()
    ymax = _drt_ymax_from_datasets(datasets)

    for i, (name, df) in enumerate(datasets):
        freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
        gamma = pd.to_numeric(df.iloc[:, 1], errors="coerce")

        fig.add_scatter(
            x=freq,
            y=gamma,
            mode="lines",
            name=name,
            line=dict(color=COLOR_PALETTE[i % len(COLOR_PALETTE)]),
        )

    _yaxis = dict(title="γ [Ω·s·cm²]")
    if st.session_state.get("drt_y_from_zero", True):
        _yaxis["range"] = [0, ymax]

    fig.update_layout(
        title=f"DRT – {title}",
        xaxis=dict(title="Frequency [Hz]", type="log"),
        yaxis=_yaxis,
        template="plotly_dark",
    )

    if st.session_state.get("colorbar_mode", False):
        _add_colorbar(fig, datasets)

    return fig

def nyquist_3d_plotly(datasets, title):
    fig = go.Figure()

    # --- gather global ranges for true equal-unit scaling ---
    all_x = []
    all_z = []
    for _, df in datasets:
        x = pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy()
        z = (-pd.to_numeric(df.iloc[:, 2], errors="coerce")).to_numpy()
        all_x.append(x)
        all_z.append(z)

    all_x = np.concatenate([v[np.isfinite(v)] for v in all_x]) if all_x else np.array([])
    all_z = np.concatenate([v[np.isfinite(v)] for v in all_z]) if all_z else np.array([])

    # avoid zero ranges
    xmin, xmax = (float(np.min(all_x)), float(np.max(all_x))) if all_x.size else (0.0, 1.0)
    zmin, zmax = (float(np.min(all_z)), float(np.max(all_z))) if all_z.size else (0.0, 1.0)


    # --- plot traces ---
    for i, (name, df) in enumerate(datasets):
        x = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        z = -pd.to_numeric(df.iloc[:, 2], errors="coerce")
        y_spacing = 1.0
        y = np.full_like(x, i * y_spacing)

        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        # markers
        if not st.session_state.get("export_no_nyquist_markers", False):
            fig.add_trace(go.Scatter3d(
                x=x, y=y, z=z,
                mode="markers",
                marker=dict(size=3, color=color, opacity=0.6),
                showlegend=False
            ))

        # line
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode="lines",
            name=name,
            line=dict(color=color, width=4)
        ))
    x_range = max(xmax - xmin, 1e-12)
    z_range = max(zmax - zmin, 1e-12)    
    fig.update_layout(
        title=title,
        template="plotly_dark",
        scene=dict(
            xaxis=dict(title="Z′ [Ω·cm²]",autorange="reversed"),
            yaxis=dict(title="", showticklabels=False),
            zaxis=dict(title="−Z″ [Ω·cm²]"),
            aspectmode="manual",
            aspectratio=dict(
                x=1,
                y=0.05 * len(datasets),                     # arbitrary thin stacking axis
                z=z_range / x_range         # THIS enforces equal units
            ),

            camera=dict(
                eye=dict(
                    x=-1.7,
                    y=1.7,
                    z=1.7
                )
            )
        ),
        margin=dict(l=0, r=0, b=0, t=40)
    )

    if st.session_state.get("colorbar_mode", False):
        _add_colorbar_3d(fig, datasets)

    return fig

def nyquist_3d_plotly_cols(datasets, title, x_col: int, y_col: int, negate_y: bool = True):
    fig = go.Figure()

    # gather global ranges for equal-unit scaling
    all_x = []
    all_z = []
    for _, df in datasets:
        x = pd.to_numeric(df.iloc[:, x_col], errors="coerce").to_numpy()
        zraw = pd.to_numeric(df.iloc[:, y_col], errors="coerce").to_numpy()
        z = (-zraw) if negate_y else zraw
        all_x.append(x)
        all_z.append(z)

    all_x = np.concatenate([v[np.isfinite(v)] for v in all_x]) if all_x else np.array([])
    all_z = np.concatenate([v[np.isfinite(v)] for v in all_z]) if all_z else np.array([])

    xmin, xmax = (float(np.min(all_x)), float(np.max(all_x))) if all_x.size else (0.0, 1.0)
    zmin, zmax = (float(np.min(all_z)), float(np.max(all_z))) if all_z.size else (0.0, 1.0)

    # plot traces
    for i, (name, df) in enumerate(datasets):
        x = pd.to_numeric(df.iloc[:, x_col], errors="coerce")
        zraw = pd.to_numeric(df.iloc[:, y_col], errors="coerce")
        z = -zraw if negate_y else zraw
        y_spacing = 1.0
        y = np.full_like(x, i * y_spacing)

        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        if not st.session_state.get("export_no_nyquist_markers", False):
            fig.add_trace(go.Scatter3d(
                x=x, y=y, z=z,
                mode="markers",
                marker=dict(size=3, color=color, opacity=0.6),
                showlegend=False
            ))

        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode="lines",
            name=name,
            line=dict(color=color, width=4)
        ))
    x_range = max(xmax - xmin, 1e-12)
    z_range = max(zmax - zmin, 1e-12)    
    fig.update_layout(
        title=title,
        template="plotly_dark",
        scene=dict(
            xaxis=dict(title="Z′ [Ω·cm²]",autorange="reversed"),
            yaxis=dict(title="", showticklabels=False),
            zaxis=dict(title="−Z″ [Ω·cm²]"),
            aspectmode="manual",
            aspectratio=dict(
                x=1,
                y=0.05*len(datasets),                     # arbitrary thin stacking axis
                z=z_range / x_range         # THIS enforces equal units
            ),

            camera=dict(
                eye=dict(
                    x=-1.7,
                    y=1.7,
                    z=1.7
                )
            )
        ),
        margin=dict(l=0, r=0, b=0, t=40)
    )

    if st.session_state.get("colorbar_mode", False):
        _add_colorbar_3d(fig, datasets)

    return fig

def drt_3d_plotly(datasets, title):

    fig = go.Figure()

    for i, (name, df) in enumerate(datasets):

        freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
        gamma = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        y = np.full_like(freq, i)

        fig.add_trace(go.Scatter3d(
            x=freq,
            y=y,
            z=gamma,
            showlegend=True,
            mode="lines",  #  no markers
            name=name,
            line=dict(
                color=COLOR_PALETTE[i % len(COLOR_PALETTE)],
                width=4
            )
        ))

    fig.update_layout(
        title=title,
        template="plotly_dark",

        scene=dict(
            xaxis=dict(
                title="Frequency [Hz]",
                type="log",

                # Clean scientific ticks
                dtick=1,                 # one tick per decade
                tickformat=".1g",        # clean numeric format
                exponentformat="power",  # 10^x style if needed
                showexponent="all",
                autorange="reversed",
            ),

            yaxis=dict(
                title="",
                showticklabels=False
            ),
            zaxis=dict(
                title="γ [Ω·cm²·s]"
            ),

            #  Match Nyquist 3D proportions
            aspectmode="manual",
            aspectratio=dict(x=1.2, y=0.05*len(datasets), z=0.9),

            #  Same camera as Nyquist
            camera=dict(
                eye=dict(x=-1.4, y=1.4, z=1.4)
            )
        ),
        margin=dict(l=0, r=0, b=0, t=40)
    )

    if st.session_state.get("colorbar_mode", False):
        _add_colorbar_3d(fig, datasets)

    return fig


# Element types whose real part anchors the inductor offset (ported from the
# dearpygui element-Nyquist view).
_RESISTOR_LIKE_TYPES = {"Resistor", "Gerisher", "fFLW", "FLW"}


def cnls_nyquist_fit_plotly(cnls_file: Path, fname: str, xlim=None, ylim=None):

    if not cnls_file.exists():
        return None

    xls = pd.ExcelFile(_normalize_path(cnls_file))

    if "Z" not in xls.sheet_names:
        return None

    df = pd.read_excel(xls, "Z")

    # Every element resolved to its Z columns by header name (any topology).
    elements = [
        e for e in cnls_topology_elements(xls)
        if e["z_re"] is not None and e["z_im"] is not None
    ]

    # ---- Main Nyquist ----
    z_real_total = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    z_imag_total = -pd.to_numeric(df.iloc[:, 2], errors="coerce")

    fig = go.Figure()

    fig.add_scatter(
        x=z_real_total,
        y=z_imag_total,
        mode="lines+markers",
        marker=dict(size=4),
        name="Total Z",
        line=dict(color="white", width=3)
    )

    re_map = {e["name"]: pd.to_numeric(df[e["z_re"]], errors="coerce") for e in elements}
    im_map = {e["name"]: pd.to_numeric(df[e["z_im"]], errors="coerce") for e in elements}

    element_colors = sample_palette_colors(
        st.session_state.palette_choice,
        n=max(1, len(elements))
    )

    for i, e in enumerate(elements):
        name = e["name"]
        etype = str(e["type"] or "")
        z_r = re_map[name]
        z_i = -im_map[name]

        # Series stacking: shift each element by the cumulative real part of the
        # preceding elements. Inductors are anchored to the resistor-like elements.
        if etype == "Inductor":
            offset = float(np.nansum([
                re_map[o["name"]].iloc[0]
                for o in elements
                if str(o["type"] or "") in _RESISTOR_LIKE_TYPES
            ]))
        else:
            offset = float(np.nansum([re_map[elements[j]["name"]].iloc[-1] for j in range(i)]))

        fig.add_scatter(
            x=z_r + offset,
            y=z_i,
            mode="lines",
            name=name,
            line=dict(color=element_colors[i])
        )

    # Keep a 1:1 data aspect ratio (daspect [1 1 1]) even when manual limits are
    # applied, so circles stay circular. scaleanchor stays active alongside range.
    xaxis_cfg = dict(title="Z′ [Ω·cm²]", scaleanchor="y", scaleratio=1, constrain="domain")
    yaxis_cfg = dict(title="−Z″ [Ω·cm²]", constrain="domain")
    if xlim is not None and xlim[0] is not None and xlim[1] is not None:
        xaxis_cfg["range"] = [xlim[0], xlim[1]]
    if ylim is not None and ylim[0] is not None and ylim[1] is not None:
        yaxis_cfg["range"] = [ylim[0], ylim[1]]

    fig.update_layout(
        title=f"CNLS Nyquist Fit – {fname}",
        xaxis=xaxis_cfg,
        yaxis=yaxis_cfg,
        legend=dict(
            orientation="v",
            y=1,
            yanchor="top",
            x=1.02,
            xanchor="left",
            font=dict(size=11)
        ),
        template="plotly_dark"
    )

    return fig

def cnls_residuals_plotly(cnls_file: Path, fname: str):

    if not cnls_file.exists():
        return None

    xls = pd.ExcelFile(_normalize_path(cnls_file))

    if "Z" not in xls.sheet_names:
        return None

    df = pd.read_excel(xls, "Z")

    freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    res_real = 100 * pd.to_numeric(df.iloc[:, 7], errors="coerce")
    res_imag = 100 * pd.to_numeric(df.iloc[:, 8], errors="coerce")

    fig = go.Figure()

    fig.add_scatter(
        x=freq,
        y=res_real,
        mode="lines+markers",
        marker=dict(size=6),
        name="Real residual",
        line=dict(color=COLOR_PALETTE[0])
    )

    fig.add_scatter(
        x=freq,
        y=res_imag,
        mode="lines+markers",
        marker=dict(size=6),
        name="Imag residual",
        line=dict(color=COLOR_PALETTE[1])
    )

    fig.update_layout(
        title=f"Nyquist Residuals – {fname}",
        xaxis=dict(title="Frequency [Hz]", type="log"),
        yaxis=dict(title="Residual [%]"),
        template="plotly_dark"
    )

    return fig

def cnls_bar_plotly(series: pd.Series, ylim=None):

    # Detect all Rn columns dynamically (excluding R_ohmic)
    r_keys = sorted(
        [k for k in series.index if k.startswith("R") and k not in ("R_ohmic", "R_pol")],
        key=lambda x: int(x[1:])
    )

    # Reverse order so highest index appears first
    r_keys = list(reversed(r_keys))

    order = ["ASR", "R_ohmic"] + r_keys

    y = [series.get(k, np.nan) for k in order]

    fig = go.Figure()
    fig.add_bar(
        x=order,
        y=y,
        showlegend=False
    )

    yaxis_cfg = {}
    if ylim is not None and ylim[0] is not None and ylim[1] is not None:
        yaxis_cfg["range"] = [ylim[0], ylim[1]]

    fig.update_layout(
        title="CNLS bar plot",
        xaxis_title="Parameter",
        yaxis_title="R [Ω·cm²]",
        yaxis=yaxis_cfg,
        template="plotly_dark",
    )

    return fig

def cnls_elements_fitting_plotly(cnls_file: Path, fname: str):

    if not cnls_file.exists():
        return None

    xls = pd.ExcelFile(_normalize_path(cnls_file))

    if "DRT" not in xls.sheet_names or "Summary" not in xls.sheet_names:
        return None

    df = pd.read_excel(xls, "DRT")

    # Need at least: freq(0), total(1)
    if df.shape[1] < 2:
        return None

    # Every element resolved to its DRT contribution column by header name.
    elements = [e for e in cnls_topology_elements(xls) if e["drt"] is not None]

    freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    gamma_total = pd.to_numeric(df.iloc[:, 1], errors="coerce")

    fig = go.Figure()
    fig.add_scatter(
        x=freq,
        y=gamma_total,
        mode="lines",
        name="Total γ",
        line=dict(color="white", width=3)
    )

    element_colors = sample_palette_colors(
        st.session_state.palette_choice,
        n=max(1, len(elements))
    )

    for i, e in enumerate(elements):
        gamma_elem = pd.to_numeric(df[e["drt"]], errors="coerce")
        fig.add_scatter(
            x=freq,
            y=gamma_elem,
            mode="lines",
            name=e["name"],
            line=dict(color=element_colors[i])
        )

    fig.update_layout(
        title=f"CNLS DRT Fit – {fname}",
        xaxis=dict(title="Frequency [Hz]", type="log"),
        yaxis=dict(title="γ [Ω·s·cm²]"),
        template="plotly_dark"
    )

    return fig

def cnls_elements_im_bode_plotly(cnls_file: Path, fname: str):

    if not cnls_file.exists():
        return None

    xls = pd.ExcelFile(_normalize_path(cnls_file))

    if "Z" not in xls.sheet_names:
        return None

    df = pd.read_excel(xls, "Z")

    # Every element resolved to its imaginary column by header name.
    elements = [e for e in cnls_topology_elements(xls) if e["z_im"] is not None]

    freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    zmes_im = -pd.to_numeric(df.iloc[:, 2], errors="coerce")

    fig = go.Figure()

    fig.add_scatter(
        x=freq,
        y=zmes_im,
        mode="markers",
        marker=dict(size=5, color="white"),
        name="Measure"
    )

    element_colors = sample_palette_colors(
        st.session_state.palette_choice,
        n=max(1, len(elements))
    )

    for i, e in enumerate(elements):
        z_im = -pd.to_numeric(df[e["z_im"]], errors="coerce")
        fig.add_scatter(
            x=freq,
            y=z_im,
            mode="lines",
            name=e["name"],
            line=dict(color=element_colors[i])
        )

    fig.update_layout(
        title=f"Imaginary Bode – {fname}",
        xaxis=dict(title="Frequency [Hz]", type="log"),
        yaxis=dict(title="−Z″ [Ω·cm²]"),
        template="plotly_dark"
    )

    return fig

def cnls_heatmap_plotly(df_cnls: pd.DataFrame, palette_choice: str, param_groups=None,
                        r_limit=None, tau_limit=None, alpha_limit=None):
    """Return a list of heatmap figures for the requested param_groups.

    param_groups is a subset of ["R", "Time constant", "Alpha"].
    Defaults to all three when None.
    r_limit/tau_limit are (min, max) in linear units; converted to log10 internally.
    alpha_limit is (min, max) in linear units [0–1].
    """
    if param_groups is None:
        param_groups = ["R", "Time constant", "Alpha"]

    if palette_choice in PLOTLY_SEQ:
        colorscale = palette_choice.split(" ")[0]
    else:
        colorscale = "Viridis"

    y_labels = [latex_label(i) for i in df_cnls.index.tolist()]
    r_indices = sorted(
        {int(k[1:]) for k in df_cnls.columns if k.startswith("R") and k not in ("R_ohmic", "R_pol")}
    )

    figures = []

    # ---- Resistances ----
    if "R" in param_groups:
        r_cols = [f"R{i}" for i in r_indices if f"R{i}" in df_cnls.columns]
        r_col_order = [c for c in ["ASR", "R_ohmic"] + r_cols if c in df_cnls.columns]
        if r_col_order:
            data = df_cnls[r_col_order].values.astype(float)
            x_labels = ["R<sub>ohmic</sub>" if c == "R_ohmic" else c for c in r_col_order]
            r_zmin = r_limit[0] if (r_limit and r_limit[0] is not None) else None
            r_zmax = r_limit[1] if (r_limit and r_limit[1] is not None) else None
            fig = go.Figure(go.Heatmap(
                z=data, x=x_labels, y=y_labels,
                colorscale=colorscale, xgap=2, ygap=2,
                zmin=r_zmin, zmax=r_zmax,
                colorbar=dict(title=dict(text="R [Ω·cm²]", side="right"))
            ))
            fig.update_layout(
                title="CNLS resistances heatmap", template="plotly_dark",
                xaxis_title="Parameter", yaxis_title="File",
            )
            figures.append(fig)

    # ---- Time constants ----
    if "Time constant" in param_groups:
        tau_cols = [f"tau{i}" for i in r_indices if f"tau{i}" in df_cnls.columns]
        if tau_cols:
            data = df_cnls[tau_cols].values.astype(float)
            x_labels = [f"τ<sub>{c[3:]}</sub>" for c in tau_cols]
            tau_zmin = tau_limit[0] if (tau_limit and tau_limit[0] is not None) else None
            tau_zmax = tau_limit[1] if (tau_limit and tau_limit[1] is not None) else None
            fig = go.Figure(go.Heatmap(
                z=data, x=x_labels, y=y_labels,
                colorscale=colorscale, xgap=2, ygap=2,
                zmin=tau_zmin, zmax=tau_zmax,
                colorbar=dict(title=dict(text="τ [s]", side="right"))
            ))
            fig.update_layout(
                title="CNLS time constants heatmap", template="plotly_dark",
                xaxis_title="Parameter", yaxis_title="File",
            )
            figures.append(fig)

    # ---- Dispersion factors (linear 0–1) ----
    if "Alpha" in param_groups:
        alpha_cols = [f"alpha{i}" for i in r_indices if f"alpha{i}" in df_cnls.columns]
        if alpha_cols:
            data = df_cnls[alpha_cols].values.astype(float)
            x_labels = [f"α<sub>{c[5:]}</sub>" for c in alpha_cols]
            a_zmin = alpha_limit[0] if (alpha_limit and alpha_limit[0] is not None) else 0
            a_zmax = alpha_limit[1] if (alpha_limit and alpha_limit[1] is not None) else 1
            fig = go.Figure(go.Heatmap(
                z=data, x=x_labels, y=y_labels,
                colorscale=colorscale, zmin=a_zmin, zmax=a_zmax, xgap=2, ygap=2,
                colorbar=dict(title=dict(text="α", side="right"))
            ))
            fig.update_layout(
                title="CNLS dispersion factors heatmap", template="plotly_dark",
                xaxis_title="Parameter", yaxis_title="File",
            )
            figures.append(fig)

    return figures





# ===============================
# Matplotlib → write PNG bytes directly into ZIP
# ===============================
def _fig_to_bytes(fig, fmt: str) -> bytes:
    """
    Export matplotlib figure to selected format.
    """
    buf = BytesIO()

    if fmt == "pdf":
        fig.savefig(buf, format="pdf", bbox_inches="tight", pad_inches=0.2)
    else:
        fig.savefig(buf, format=fmt, dpi=300, bbox_inches="tight", pad_inches=0.2)

    plt.close(fig)
    return buf.getvalue()

def add_nyquist_png(zf: zipfile.ZipFile, datasets, title: str):

    fig, ax = plt.subplots(figsize=(6, 6), dpi=600)

    all_x = []
    all_y = []

    for i, (name, df) in enumerate(datasets):
        x = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        y = -pd.to_numeric(df.iloc[:, 2], errors="coerce")

        if not st.session_state.get("export_no_nyquist_markers", False):
            ax.plot(
                x, y,
                linestyle='None',
                marker='o',
                markersize=3,
                markerfacecolor=COLOR_PALETTE[i % len(COLOR_PALETTE)],
                markeredgecolor=COLOR_PALETTE[i % len(COLOR_PALETTE)],
                alpha=0.6
            )

        ax.plot(
            x, y,
            linewidth=1.5,
            color=COLOR_PALETTE[i % len(COLOR_PALETTE)],
            alpha=0.85,
            label=latex_label(name)
        )

        all_x.extend(x.dropna())
        all_y.extend(y.dropna())

    if all_x and all_y:
        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)

        margin_x = (xmax - xmin) * 0.03
        margin_y = (ymax - ymin) * 0.03

        ax.set_xlim(xmin - margin_x, xmax + margin_x)

        if ymin < 0:
            ax.set_ylim(ymin - margin_y, ymax + margin_y)
        else:
            ax.set_ylim(0, ymax + margin_y)

    ax.set_xlabel("Z′ [Ω·cm²]")
    ax.set_ylabel("−Z″ [Ω·cm²]")

    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    ax.set_aspect('equal', adjustable='box')
    if st.session_state.get("colorbar_mode", False):
        _add_mpl_colorbar(fig, ax, datasets)
    elif not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=False
        )
        fig.subplots_adjust(right=0.75)

        fig.subplots_adjust(bottom=0.22)
    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"Nyquist/{title}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )
    
def add_nyquist_compare_png(
    zf: zipfile.ZipFile,
    compare_mode: str,
    files_to_process,
    display_name_map
):

    fig, ax = plt.subplots(figsize=(6, 6), dpi=600)

    mapping = {
        "Truncated vs Original": ("Truncated", "Original"),
        "Smooth vs Truncated": ("Truncated", "Smooth"),
        "LC corrected vs Truncated": ("Truncated", "LC corrected"),
        "Extended vs Truncated": ("Truncated", "Extended"),
        "DRT Fit vs Truncated": ("Truncated", "DRT Fit"),
        "CNLS Fit vs Truncated": ("Truncated", "CNLS Fit"),
    }

    sheet_trunc, sheet_other = mapping[compare_mode]

    all_x = []
    all_y = []

    for i, eis_file in enumerate(files_to_process):

        fname = eis_file.name
        label = latex_label(display_name_map.get(fname, fname))
        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        xls = pd.ExcelFile(_normalize_path(eis_file))

        df_trunc = None
        if sheet_trunc in xls.sheet_names:
            df_trunc = pd.read_excel(xls, sheet_trunc)

        df_other = None

        if sheet_other == "DRT Fit":
            drt_file = sibling_file(eis_file, "DRT")
            if drt_file.exists():
                drt_xls = pd.ExcelFile(_normalize_path(drt_file))
                if "Tknv_ReIm_s" in drt_xls.sheet_names:
                    df_other = pd.read_excel(drt_xls, "Tknv_ReIm_s")
        elif sheet_other == "CNLS Fit":
            cnls_file = sibling_file(eis_file, "CNLS")
            if cnls_file.exists():
                cnls_xls = pd.ExcelFile(_normalize_path(cnls_file))
                if "Z" in cnls_xls.sheet_names:
                    df_other = pd.read_excel(cnls_xls, "Z")
        else:
            if sheet_other in xls.sheet_names:
                df_other = pd.read_excel(xls, sheet_other)

        if df_trunc is None:
            continue

        # --------------------------------------------------
        # Truncated vs Original
        # --------------------------------------------------
        if compare_mode == "Truncated vs Original":

            # Original FIRST (hollow circles)
            if df_other is not None:
                x = pd.to_numeric(df_other.iloc[:, 1], errors="coerce")
                y = -pd.to_numeric(df_other.iloc[:, 2], errors="coerce")

                ax.plot(
                    x, y,
                    linestyle='None',
                    marker='o',
                    markersize=6,
                    markerfacecolor='none',
                    markeredgecolor=color,
                    markeredgewidth=1.5,
                    alpha=0.5,
                    label=f"{label} - Original"
                )

                all_x.extend(x.dropna())
                all_y.extend(y.dropna())

            # Truncated SECOND (filled)
            x = pd.to_numeric(df_trunc.iloc[:, 1], errors="coerce")
            y = -pd.to_numeric(df_trunc.iloc[:, 2], errors="coerce")

            ax.plot(
                x, y,
                linestyle='None',
                marker='o',
                markersize=6,
                markerfacecolor=color,
                markeredgecolor=color,
                alpha=1.0,
                label=f"{label} - Truncated"
            )

            all_x.extend(x.dropna())
            all_y.extend(y.dropna())

        # --------------------------------------------------
        # X vs Truncated
        # --------------------------------------------------
        else:

            # Truncated (filled circles)
            x_tr = pd.to_numeric(df_trunc.iloc[:, 1], errors="coerce")
            y_tr = -pd.to_numeric(df_trunc.iloc[:, 2], errors="coerce")

            ax.plot(
                x_tr, y_tr,
                linestyle='None',
                marker='o',
                markersize=5,
                markerfacecolor=color,
                markeredgecolor=color,
                alpha=1.0
            )

            all_x.extend(x_tr.dropna())
            all_y.extend(y_tr.dropna())

            if df_other is not None:

                if sheet_other == "DRT Fit":
                    xcol = 2
                    ycol = 3
                elif sheet_other == "CNLS Fit":
                    # CNLS 'Z' sheet: Ztot_Re (col 3), Ztot_Im (col 4).
                    xcol = 3
                    ycol = 4
                else:
                    xcol = 1
                    ycol = 2

                x = pd.to_numeric(df_other.iloc[:, xcol], errors="coerce")
                y = -pd.to_numeric(df_other.iloc[:, ycol], errors="coerce")

                ax.plot(
                    x, y,
                    linewidth=1.8,
                    color=color,
                    alpha=0.9,
                    label=label  # Only filename
                )

                all_x.extend(x.dropna())
                all_y.extend(y.dropna())

    # --------------------------------------------------
    # Smart limits (same as add_nyquist_png)
    # --------------------------------------------------
    if all_x and all_y:
        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)

        margin_x = (xmax - xmin) * 0.03
        margin_y = (ymax - ymin) * 0.03

        ax.set_xlim(xmin - margin_x, xmax + margin_x)

        if ymin < 0:
            ax.set_ylim(ymin - margin_y, ymax + margin_y)
        else:
            ax.set_ylim(0, ymax + margin_y)

    ax.set_xlabel("Z′ [Ω·cm²]")
    ax.set_ylabel("−Z″ [Ω·cm²]")

    ax.set_aspect('equal', adjustable='box')

    # Grid toggle
    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    # Legend toggle
    if st.session_state.get("colorbar_mode", False):
        pseudo = [(latex_label(display_name_map.get(f.name, f.stem)), None) for f in files_to_process]
        _add_mpl_colorbar(fig, ax, pseudo)
    elif not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=False
        )
        fig.subplots_adjust(right=0.75)

    # --------------------------------------------------
    # Export formats
    # --------------------------------------------------
    safe_name = compare_mode.replace(" ", "_").replace("→", "to")

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"Nyquist_Compare/{safe_name}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )

def add_drt_3d_png(zf: zipfile.ZipFile, datasets, title: str):

    fig = drt_3d_plotly(datasets, title)
    n_files = len(datasets)
    legend_font_size = max(10, min(16, int(22 - 0.8 * n_files)))

    fig.update_layout(
        template="plotly_white",
        title=None,

        font=dict(
            family="Arial",
            size=16,
            color="black"
        ),
        scene=dict(

            xaxis=dict(
                title=dict(
                    text="Frequency [Hz]",
                    font=dict(size=16, color="black")
                ),
                type="log",
                dtick=1,
                tickformat=".1g",        # clean numeric format
                exponentformat="power",  # 10^x style if needed
                tickangle=0,
                tickfont=dict(size=12, color="black"),

                showgrid=not st.session_state.get("export_no_grid", False),
                gridcolor="lightgray",
                gridwidth=1,

                showline=True,
                linecolor="black",
                linewidth=3,

                ticks="outside",
                autorange="reversed",
            ),

            yaxis=dict(
                title="",
                tickangle=0,
                tickfont=dict(size=12, color="black"),

                showgrid=not st.session_state.get("export_no_grid", False),
                gridcolor="lightgray",
                gridwidth=1,

                showline=True,
                linecolor="black",
                linewidth=3,

                ticks="outside",
            ),

            zaxis=dict(
                title=dict(
                    text="γ [Ω·cm²·s]",
                    font=dict(size=16, color="black")
                ),
                tickangle=0,
                tickfont=dict(size=12, color="black"),

                showgrid=not st.session_state.get("export_no_grid", False),
                gridcolor="lightgray",
                gridwidth=1,

                showline=True,
                linecolor="black",
                linewidth=3,

                ticks="outside",
            ),

            aspectmode="manual",
            aspectratio=dict(x=1.2, y=0.05*len(datasets), z=0.9),

            camera=dict(
                projection=dict(type="orthographic"),
                eye=dict(
                    x=-1.4,
                    y=1.4,
                    z=1.4
                )
            )

        ),

        legend=dict(
            orientation="v",
            y=0.5,
            yanchor="middle",
            x=1.02,
            xanchor="left",
            font=dict(size=legend_font_size, color="black"),
            bgcolor="rgba(255,255,255,0.9)"
        ),
        margin=dict(l=0, r=250, b=40, t=20)
    )

    if st.session_state.get("export_no_legend", False) or st.session_state.get("colorbar_mode", False):

        fig.update_layout(
            showlegend=False,
            margin=dict(l=40, r=40, b=40, t=40)
        )

    else:

        fig.update_layout(
            legend=dict(
                orientation="v",
                y=1,
                yanchor="top",
                x=1.02,
                xanchor="left",
                font=dict(size=12, color="black"),
            ),
            margin=dict(l=40, r=220, b=40, t=40)
        )
    for fmt in st.session_state.export_formats:

        img_bytes = fig.to_image(
            format=fmt,
            scale=4,
            width=1600,
            height=1000
        )

        zf.writestr(f"DRT_3D/{title}_3D.{fmt}", img_bytes)

def add_nyquist_fit_png(zf: zipfile.ZipFile, datasets):

    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)

    all_x = []
    all_y = []

    for i, (name, df) in enumerate(datasets):

        x = pd.to_numeric(df.iloc[:, 2], errors="coerce")
        y = -pd.to_numeric(df.iloc[:, 3], errors="coerce")

        if not st.session_state.get("export_no_nyquist_markers", False):
            ax.plot(
                x, y,
                linestyle='None',
                marker='o',
                markersize=3,
                markerfacecolor=COLOR_PALETTE[i % len(COLOR_PALETTE)],
                markeredgecolor=COLOR_PALETTE[i % len(COLOR_PALETTE)],
                alpha=0.6
            )

        ax.plot(
            x, y,
            linewidth=1.5,
            color=COLOR_PALETTE[i % len(COLOR_PALETTE)],
            alpha=0.85,
            label=latex_label(name)
        )

        all_x.extend(x.dropna())
        all_y.extend(y.dropna())

    if all_x and all_y:
        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)

        margin_x = (xmax - xmin) * 0.03
        margin_y = (ymax - ymin) * 0.03

        ax.set_xlim(xmin - margin_x, xmax + margin_x)

        if ymin < 0:
            ax.set_ylim(ymin - margin_y, ymax + margin_y)
        else:
            ax.set_ylim(0, ymax + margin_y)

    ax.set_xlabel("Z′ [Ω·cm²]")
    ax.set_ylabel("−Z″ [Ω·cm²]")

    ax.set_aspect("equal", adjustable="box")

    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    if st.session_state.get("colorbar_mode", False):
        _add_mpl_colorbar(fig, ax, datasets)
    elif len(datasets) > 1 and not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=False
        )
        fig.subplots_adjust(right=0.78)

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"Nyquist/DRT_Fit.{fmt}",
            _fig_to_bytes(fig, fmt)
        )

def nyquist_fit_3d_plotly(datasets, title="Nyquist – DRT Smooth Fit (3D)"):
    """
    Nyquist-fit datasets use:
      Re  -> df.iloc[:, 2]
      Im  -> df.iloc[:, 3] (negated for -Z'')
    """
    fig = go.Figure()

    # ---- global ranges for equal scaling ----
    all_x = []
    all_z = []
    for _, df in datasets:
        x = pd.to_numeric(df.iloc[:, 2], errors="coerce").to_numpy()
        z = (-pd.to_numeric(df.iloc[:, 3], errors="coerce")).to_numpy()
        x = x[np.isfinite(x)]
        z = z[np.isfinite(z)]
        if len(x): all_x.append(x)
        if len(z): all_z.append(z)

    if all_x:
        all_x = np.concatenate(all_x)
        xmin, xmax = float(np.min(all_x)), float(np.max(all_x))
    else:
        xmin, xmax = 0.0, 1.0

    if all_z:
        all_z = np.concatenate(all_z)
        zmin, zmax = float(np.min(all_z)), float(np.max(all_z))
    else:
        zmin, zmax = 0.0, 1.0

    # ---- traces ----
    for i, (name, df) in enumerate(datasets):
        x = pd.to_numeric(df.iloc[:, 2], errors="coerce")
        z = -pd.to_numeric(df.iloc[:, 3], errors="coerce")
        y_spacing = 1.0
        y = np.full_like(x, i * y_spacing)

        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        if not st.session_state.get("export_no_nyquist_markers", False):
            fig.add_trace(go.Scatter3d(
                x=x, y=y, z=z,
                mode="markers",
                marker=dict(size=3, color=color, opacity=0.6),
                showlegend=False
            ))
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode="lines",
            name=name,
            line=dict(color=color, width=4)
        ))
    x_range = max(xmax - xmin, 1e-12)
    z_range = max(zmax - zmin, 1e-12)    
    fig.update_layout(
        title=title,
        template="plotly_dark",
        scene=dict(
            xaxis=dict(title="Z′ [Ω·cm²]",autorange="reversed"),
            yaxis=dict(title="", showticklabels=False),
            zaxis=dict(title="−Z″ [Ω·cm²]"),
            aspectmode="manual",
            aspectratio=dict(
                x=1,
                y=0.05*len(datasets),                     # arbitrary thin stacking axis
                z=z_range / x_range         # THIS enforces equal units
            ),

            camera=dict(
                eye=dict(
                    x=-1.7,
                    y=1.7,
                    z=1.7
                )
            )
        ),
        margin=dict(l=0, r=0, b=0, t=40)
    )

    if st.session_state.get("colorbar_mode", False):
        _add_colorbar_3d(fig, datasets)

    return fig

def add_nyquist_fit_3d_png(zf: zipfile.ZipFile, datasets, title: str = "Nyquist_fit"):
    """
    Export Nyquist-fit as 3D PNG using the SAME white/scientific layout
    style as add_nyquist_3d_png, but with fit columns (Re col=2, Im col=3).
    """
    fig = nyquist_fit_3d_plotly(datasets, title)

    n_files = len(datasets)
    legend_font_size = max(10, min(16, int(22 - 0.8 * n_files)))
    all_x = []
    all_z = []

    for _, df in datasets:
        x = pd.to_numeric(df.iloc[:, 2], errors="coerce").to_numpy()
        z = (-pd.to_numeric(df.iloc[:, 3], errors="coerce")).to_numpy()

        x = x[np.isfinite(x)]
        z = z[np.isfinite(z)]

        if len(x):
            all_x.append(x)
        if len(z):
            all_z.append(z)

    if all_x:
        all_x = np.concatenate(all_x)
        xmin, xmax = float(np.min(all_x)), float(np.max(all_x))
    else:
        xmin, xmax = 0.0, 1.0

    if all_z:
        all_z = np.concatenate(all_z)
        zmin, zmax = float(np.min(all_z)), float(np.max(all_z))
    else:
        zmin, zmax = 0.0, 1.0
    x_range = max(xmax - xmin, 1e-12)
    z_range = max(zmax - zmin, 1e-12)    
    
    # ---- reuse same layout style as your other 3D Nyquist export ----
    fig.update_layout(
        template="plotly_white",
        title=None,

        font=dict(
            family="Arial",
            size=16,
            color="black"
        ),

        scene=dict(
            xaxis=dict(
                title=dict(text="Z′ [Ω·cm²]", font=dict(size=16, color="black")),
                tickfont=dict(size=12, color="black"),
                showgrid=not st.session_state.get("export_no_grid", False), gridcolor="lightgray", gridwidth=1,
                showline=True, linecolor="black", linewidth=3,
                ticks="outside",
                autorange="reversed",
            ),
            yaxis=dict(
                title="",
                showticklabels=False,
                showgrid=not st.session_state.get("export_no_grid", False), gridcolor="lightgray", gridwidth=1,
                showline=True, linecolor="black", linewidth=3,
                ticks="outside",
            ),
            zaxis=dict(
                title=dict(text="−Z″ [Ω·cm²]", font=dict(size=16, color="black")),
                tickfont=dict(size=12, color="black"),
                showgrid=not st.session_state.get("export_no_grid", False), gridcolor="lightgray", gridwidth=1,
                showline=True, linecolor="black", linewidth=3,
                ticks="outside",
            ),
            aspectmode="manual",
            aspectratio=dict(
                x=1,
                y=0.05*len(datasets),                     # arbitrary thin stacking axis
                z=z_range / x_range         # THIS enforces equal units
            ),

            camera=dict(
                eye=dict(
                    x=-1.7,
                    y=1.7,
                    z=1.7
                )
            )
        ),

        legend=dict(
            orientation="v",
            y=0.5, yanchor="middle",
            x=1.02, xanchor="left",
            font=dict(size=legend_font_size, color="black"),
            bgcolor="rgba(255,255,255,0.9)"
        ),
        margin=dict(l=0, r=250, b=40, t=20)
    )
    if st.session_state.get("export_no_legend", False) or st.session_state.get("colorbar_mode", False):

        fig.update_layout(
            showlegend=False,
            margin=dict(l=40, r=40, b=40, t=40)
        )

    else:

        fig.update_layout(
            legend=dict(
                orientation="v",
                y=1,
                yanchor="top",
                x=1.02,
                xanchor="left",
                font=dict(size=12, color="black"),
            ),
            margin=dict(l=40, r=220, b=40, t=40)
        )
    for fmt in st.session_state.export_formats:

        img_bytes = fig.to_image(
            format=fmt,
            scale=4,
            width=1600,
            height=1000
        )

        zf.writestr(f"Nyquist_3D/{title}_3D.{fmt}", img_bytes)

def add_nyquist_3d_png(zf: zipfile.ZipFile, datasets, title: str):

    fig = nyquist_3d_plotly(datasets, title)
    
    # --------------------------------------------------
    # 🔎 Compute TRUE global ranges for equal scaling
    # --------------------------------------------------
    all_x = []
    all_z = []

    for _, df in datasets:
        x = pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy()
        z = (-pd.to_numeric(df.iloc[:, 2], errors="coerce")).to_numpy()

        x = x[np.isfinite(x)]
        z = z[np.isfinite(z)]

        if len(x):
            all_x.append(x)
        if len(z):
            all_z.append(z)

    if all_x:
        all_x = np.concatenate(all_x)
        xmin, xmax = float(np.min(all_x)), float(np.max(all_x))
    else:
        xmin, xmax = 0.0, 1.0

    if all_z:
        all_z = np.concatenate(all_z)
        zmin, zmax = float(np.min(all_z)), float(np.max(all_z))
    else:
        zmin, zmax = 0.0, 1.0
    x_range = max(xmax - xmin, 1e-12)
    z_range = max(zmax - zmin, 1e-12)    
    span = max(x_range, z_range)
    zoom_factor = span / 6
    # --------------------------------------------------
    # 🧪 Scientific white layout with TRUE equal scaling
    # --------------------------------------------------
    fig.update_layout(
        template="plotly_white",
        title=None,

        font=dict(
            family="Arial",
            size=16,
            color="black"
        ),

        scene=dict(
            
            xaxis=dict(
                title=dict(
                    text="Z′ [Ω·cm²]",
                    font=dict(size=16, color="black")
                ),
                tickangle=0,
                tickfont=dict(size=12, color="black"),
                showgrid=not st.session_state.get("export_no_grid", False),
                gridcolor="lightgray",
                gridwidth=1,
                showline=True,
                linecolor="black",
                linewidth=3,
                ticks="outside",
                autorange="reversed",
            ),

            yaxis=dict(
                title="",
                tickangle=0,
                tickfont=dict(size=12, color="black"),
                showgrid=not st.session_state.get("export_no_grid", False),
                gridcolor="lightgray",
                gridwidth=1,
                showline=True,
                linecolor="black",
                linewidth=3,
                ticks="outside",
            ),

            zaxis=dict(
                title=dict(
                    text="−Z″ [Ω·cm²]",
                    font=dict(size=16, color="black")
                ),
                tickangle=0,
                tickfont=dict(size=12, color="black"),
                showgrid=not st.session_state.get("export_no_grid", False),
                gridcolor="lightgray",
                gridwidth=1,
                showline=True,
                linecolor="black",
                linewidth=3,
                ticks="outside",
            ),

            # ✅ TRUE equal scaling between Z′ and Z″
            aspectmode="manual",
            aspectratio=dict(
                x=1,
                y=0.05*len(datasets),                     # arbitrary thin stacking axis
                z=z_range / x_range         # THIS enforces equal units
            ),

            camera=dict(
                eye=dict(
                    x=-1.7,
                    y=1.7,
                    z=1.7
                )
            )
        ),

        legend=dict(
            orientation="v",
            y=1,
            yanchor="top",
            x=1.02,
            xanchor="left",
            font=dict(size=12, color="black"),
        ),
        margin=dict(l=40, r=220, b=40, t=40)
    )

    if st.session_state.get("export_no_legend", False) or st.session_state.get("colorbar_mode", False):

        fig.update_layout(
            showlegend=False,
            margin=dict(l=40, r=40, b=40, t=40)
        )

    else:

        fig.update_layout(
            legend=dict(
                orientation="v",
                y=1,
                yanchor="top",
                x=1.02,
                xanchor="left",
                font=dict(size=12, color="black"),
            ),
            margin=dict(l=40, r=220, b=40, t=40)
        )

    for fmt in st.session_state.export_formats:

        img_bytes = fig.to_image(
            format=fmt,
            scale=4,
            width=1600,
            height=1000
        )

        zf.writestr(f"Nyquist_3D/{title}_3D.{fmt}", img_bytes)






def add_bode_png(zf: zipfile.ZipFile, datasets, title: str, real: bool):

    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)

    all_x = []
    all_y = []

    for i, (name, df) in enumerate(datasets):

        freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")

        if real:
            y = pd.to_numeric(df.iloc[:, 1], errors="coerce")
            ylabel = "Z′ [Ω·cm²]"
            subfolder = "Zreal"
        else:
            y = -pd.to_numeric(df.iloc[:, 2], errors="coerce")
            ylabel = "−Z″ [Ω·cm²]"
            subfolder = "Zimag"

        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        # --- markers (raw style)
        if not st.session_state.get("export_no_nyquist_markers", False):
            ax.semilogx(
                freq, y,
                linestyle='None',
                marker='o',
                markersize=3,
                markerfacecolor=color,
                markeredgecolor=color,
                alpha=0.6
            )

        # --- smooth connecting line
        ax.semilogx(
            freq, y,
            linewidth=1.5,
            color=color,
            alpha=0.85,
            label=latex_label(name)
        )

        all_x.extend(freq.dropna())
        all_y.extend(y.dropna())

    # ---- Smart limits ----
    if all_x and all_y:

        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)

        margin_y = (ymax - ymin) * 0.03 if ymax != ymin else 0.05 * ymax

        ax.set_xlim(xmin, xmax)

        if ymin < 0:
            ax.set_ylim(ymin - margin_y, ymax + margin_y)
        else:
            ax.set_ylim(0, ymax + margin_y)

    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel(ylabel)

    # Nature-style grid
    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    # ---- Legend BELOW ----
    if st.session_state.get("colorbar_mode", False):
        _add_mpl_colorbar(fig, ax, datasets)
    elif not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=False
        )
        fig.subplots_adjust(right=0.75)

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"Bode/{subfolder}/{title}_{subfolder}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )
   


def add_drt_png(zf: zipfile.ZipFile, datasets, title: str):

    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)

    all_freq = []
    ymax = 0

    for i, (name, df) in enumerate(datasets):

        freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
        gamma = pd.to_numeric(df.iloc[:, 1], errors="coerce")

        ax.semilogx(
            freq,
            gamma,
            linewidth=1.5,
            alpha=0.85,
            color=COLOR_PALETTE[i % len(COLOR_PALETTE)],
            label=latex_label(name),
        )

        all_freq.extend(freq.dropna())

        gamma_valid = gamma[np.isfinite(gamma)]
        if len(gamma_valid):
            ymax = max(ymax, gamma_valid.max())

    # ---- Smart limits ----
    if all_freq:
        ax.set_xlim(min(all_freq), max(all_freq))

    if st.session_state.get("drt_y_from_zero", True):
        ax.set_ylim(0, 1.05 * ymax if ymax > 0 else 1)

    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("γ [Ω·cm²·s]")

    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    # ---- Legend BELOW ----
    if st.session_state.get("colorbar_mode", False):
        _add_mpl_colorbar(fig, ax, datasets)
    elif not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=False
        )
        fig.subplots_adjust(right=0.75)

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"DRT/{title}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )



def add_cnls_bar_png(zf: zipfile.ZipFile, series: pd.Series, fname: str, ylim=None):

    # Detect dynamic Rn keys
    r_keys = sorted(
        [k for k in series.index if k.startswith("R") and k not in ("R_ohmic", "R_pol")],
        key=lambda x: int(x[1:])
    )

    r_keys = list(reversed(r_keys))
    order_keys = ["ASR", "R_ohmic"] + r_keys

    # Extract values using TRUE keys
    y = [series.get(k, np.nan) for k in order_keys]

    # Create display labels (LaTeX only for R_ohmic)
    display_labels = []
    for k in order_keys:
        if k == "R_ohmic":
            display_labels.append(r"$R_{\mathrm{ohmic}}$")
        else:
            display_labels.append(k)

    fig, ax = plt.subplots(figsize=(7, 4), dpi=300)

    ax.bar(display_labels, y)

    ax.set_ylabel("R [Ω·cm²]")
    if ylim is not None and ylim[0] is not None and ylim[1] is not None:
        ax.set_ylim(ylim[0], ylim[1])

    ax.grid(False)
    ax.tick_params(axis="x", rotation=30)

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"CNLS/{fname}_bar.{fmt}",
            _fig_to_bytes(fig, fmt)
        )

def add_cnls_line_png(zf: zipfile.ZipFile, df_cnls: pd.DataFrame, param: str, ylim=None,
                      folder: str = "CNLS/LinePlots"):

    x = np.arange(1, len(df_cnls) + 1)
    y = df_cnls[param].values
    x_labels = [str(idx) for idx in df_cnls.index.tolist()]

    mean_val = np.nanmean(y)
    std_val = np.nanstd(y)

    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)

    # ---- White main line (no legend) ----
    ax.plot(
        x,
        y,
        linewidth=1.5,
        color="black"
    )

    # ---- Colored hollow markers + legend ----
    legend_handles = []

    for i, (idx, val) in enumerate(zip(df_cnls.index.tolist(), y)):

        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]

        sc = ax.scatter(
            i+1,
            val,
            facecolors="white",
            edgecolors=color,
            s=80,
            linewidth=2
        )

        legend_handles.append(
            plt.Line2D(
                [0], [0],
                marker='o',
                color='white',
                markeredgecolor=color,
                markerfacecolor='white',
                markersize=8,
                linewidth=0,
                label=f"{i+1} - {latex_label(idx)}"
            )
        )

    if param.startswith("tau"):
        _ylabel = "τ [s]"
    elif param.startswith("alpha"):
        _ylabel = "Dispersion factor"
    elif param == "L_hf" or re.fullmatch(r"L\d+", param):
        _ylabel = "L [H·cm²]"
    else:
        _ylabel = "R [Ω·cm²]"

    ax.set_xlabel("File index")
    ax.set_ylabel(_ylabel)
    if param.startswith("tau"):
        import matplotlib.ticker as _ticker
        ax.yaxis.set_major_formatter(_ticker.ScalarFormatter(useMathText=True))
        ax.ticklabel_format(style="sci", axis="y", scilimits=(0, 0))
    if ylim is not None and ylim[0] is not None and ylim[1] is not None:
        ax.set_ylim(ylim[0], ylim[1])
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, rotation=30, ha="right")

    ax.set_title(
        f"Mean value: {mean_val:.3g} | Std value: {std_val:.3g}"
    )

    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    n = len(legend_handles)
    legend_font = max(6, min(10, int(12 - 0.25 * n)))

    if not st.session_state.get("export_no_legend", False):
        ax.legend(
            handles=legend_handles,
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=False,
            fontsize=legend_font
        )
        fig.subplots_adjust(right=0.78)
    
    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"{folder}/{param}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )
   
def add_cnls_elements_fitting_png(
    zf: zipfile.ZipFile,
    cnls_file: Path,
    fname: str
):

    if not cnls_file.exists():
        return

    xls = pd.ExcelFile(_normalize_path(cnls_file))

    if "DRT" not in xls.sheet_names or "Summary" not in xls.sheet_names:
        return

    df = pd.read_excel(xls, "DRT")

    if df.shape[1] < 2:
        return

    # Every element resolved to its DRT contribution column by header name.
    elements = [e for e in cnls_topology_elements(xls) if e["drt"] is not None]

    freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    gamma_total = pd.to_numeric(df.iloc[:, 1], errors="coerce")

    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)

    # ---- TOTAL γ (main DRT) ----
    ax.semilogx(
        freq,
        gamma_total,
        linewidth=1.5,
        color="black",
        alpha=0.3,
        label="Total γ"
    )

    ymax = np.nanmax(gamma_total)
    element_colors = sample_palette_colors(
        st.session_state.palette_choice,
        n=max(1, len(elements))
    )
    # ---- Individual element contributions ----
    for i, e in enumerate(elements):

        gamma_elem = pd.to_numeric(df[e["drt"]], errors="coerce")

        ax.semilogx(
            freq,
            gamma_elem,
            linewidth=1.5,
            color=element_colors[i],
            label=e["name"]
        )

        elem_max = np.nanmax(gamma_elem)
        if np.isfinite(elem_max):
            ymax = max(ymax, elem_max)

    # ---- Scientific limits ----
    ax.set_xlim(np.nanmin(freq), np.nanmax(freq))
    ax.set_ylim(0, 1.05 * ymax)

    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("γ [Ω·cm²·s]")

    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    # ---- Legend BELOW (consistent with others) ----
    if not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            ncol=1,
            frameon=False
        )
        fig.subplots_adjust(right=0.78)

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"CNLS/Fitting/{fname}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )
 

def add_cnls_nyquist_fit_png(zf, cnls_file, fname):

    fig, ax = plt.subplots(figsize=(6, 6), dpi=600)

    xls = pd.ExcelFile(_normalize_path(cnls_file))

    df = pd.read_excel(xls, "Z")

    # Every element resolved to its Z columns by header name (any topology).
    elements = [
        e for e in cnls_topology_elements(xls)
        if e["z_re"] is not None and e["z_im"] is not None
    ]

    # ---- Main Nyquist ----
    z_real_total = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    z_imag_total = -pd.to_numeric(df.iloc[:, 2], errors="coerce")

    ax.plot(
        z_real_total,
        z_imag_total,
        linewidth=1.5,
        color="black",
        alpha=0.3,
        label="Total Z"
    )

    re_map = {e["name"]: pd.to_numeric(df[e["z_re"]], errors="coerce") for e in elements}
    im_map = {e["name"]: pd.to_numeric(df[e["z_im"]], errors="coerce") for e in elements}

    element_colors = sample_palette_colors(
        st.session_state.palette_choice,
        n=max(1, len(elements))
    )

    for i, e in enumerate(elements):
        name = e["name"]
        etype = str(e["type"] or "")
        z_r = re_map[name]
        z_i = -im_map[name]

        if etype == "Inductor":
            offset = float(np.nansum([
                re_map[o["name"]].iloc[0]
                for o in elements
                if str(o["type"] or "") in _RESISTOR_LIKE_TYPES
            ]))
        else:
            offset = float(np.nansum([re_map[elements[j]["name"]].iloc[-1] for j in range(i)]))

        ax.plot(
            z_r + offset,
            z_i,
            linewidth=1.5,
            color=element_colors[i],
            label=name
        )

    ax.set_xlabel("Z′ [Ω·cm²]")
    ax.set_ylabel("−Z″ [Ω·cm²]")
    ax.set_aspect("equal", adjustable="box")

    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    if not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            ncol=1,
            frameon=False
        )
        fig.subplots_adjust(right=0.78)

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"CNLS/Fitting/Nyquist_{fname}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )

def add_cnls_residuals_png(zf, cnls_file, fname):

    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)

    xls = pd.ExcelFile(_normalize_path(cnls_file))
    df = pd.read_excel(xls, "Z")

    freq = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    res_real = 100 * pd.to_numeric(df.iloc[:, 7], errors="coerce")
    res_imag = 100 * pd.to_numeric(df.iloc[:, 8], errors="coerce")

    if st.session_state.get("export_no_nyquist_markers", False):

        ax.semilogx(
            freq, res_real,
            linewidth=1.2,
            color=COLOR_PALETTE[0],
            label="Real"
        )

        ax.semilogx(
            freq, res_imag,
            linewidth=1.2,
            color=COLOR_PALETTE[1],
            label="Imaginary"
        )

    else:

        ax.semilogx(
            freq, res_real,
            marker='o',
            markersize=4,
            linewidth=1.2,
            color=COLOR_PALETTE[0],
            label="Real"
        )

        ax.semilogx(
            freq, res_imag,
            marker='o',
            markersize=4,
            linewidth=1.2,
            color=COLOR_PALETTE[1],
            label="Imaginary"
        )

    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("Residual [%]")

    if st.session_state.get("export_no_grid", False):
        ax.grid(False)
    else:
        ax.grid(True, linewidth=0.5, alpha=0.3)

    if not st.session_state.get("export_no_legend", False):
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            ncol=1,
            frameon=False
        )
        fig.subplots_adjust(right=0.78)

    for fmt in st.session_state.export_formats:
        zf.writestr(
            f"CNLS/Fitting/Res_{fname}.{fmt}",
            _fig_to_bytes(fig, fmt)
        )


def add_cnls_compare_png(zf: zipfile.ZipFile, cnls_file: Path, fname: str, xlim=None, ylim=None):
    """Export all three CNLS compare plots (imaginary Bode, Nyquist, DRT) to CNLS/Compare/."""

    if not cnls_file.exists():
        return

    xls = pd.ExcelFile(_normalize_path(cnls_file))

    if "Z" not in xls.sheet_names or "Summary" not in xls.sheet_names:
        return

    # Every element resolved to its Z/DRT columns by header name (any topology).
    elements = cnls_topology_elements(xls)
    element_colors = sample_palette_colors(
        st.session_state.palette_choice,
        n=max(1, len(elements))
    )

    df_z = pd.read_excel(xls, "Z")
    freq = pd.to_numeric(df_z.iloc[:, 0], errors="coerce")

    # ---- 1. Imaginary Bode ----
    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)

    zmes_im = -pd.to_numeric(df_z.iloc[:, 2], errors="coerce")
    marker_kw = {} if st.session_state.get("export_no_nyquist_markers", False) else dict(marker='o', markersize=3)
    ax.semilogx(freq, zmes_im, linewidth=1.0, color="black", label="Measure", **marker_kw)

    for i, e in enumerate(elements):
        if e["z_im"] is None:
            continue
        z_im = -pd.to_numeric(df_z[e["z_im"]], errors="coerce")
        ax.semilogx(freq, z_im, linewidth=1.5, color=element_colors[i], label=e["name"])

    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("−Z″ [Ω·cm²]")

    if not st.session_state.get("export_no_grid", False):
        ax.grid(True, linewidth=0.5, alpha=0.3)
    if not st.session_state.get("export_no_legend", False):
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=1, frameon=False)
        fig.subplots_adjust(right=0.78)

    for fmt in st.session_state.export_formats:
        zf.writestr(f"CNLS/Compare/{fname}_im_bode.{fmt}", _fig_to_bytes(fig, fmt))

    # ---- 2. Nyquist with individual element arcs ----
    fig, ax = plt.subplots(figsize=(6, 6), dpi=600)

    z_real_total = pd.to_numeric(df_z.iloc[:, 1], errors="coerce")
    z_imag_total = -pd.to_numeric(df_z.iloc[:, 2], errors="coerce")
    ax.plot(z_real_total, z_imag_total, linewidth=1.5, color="black", alpha=0.3, label="Total Z")

    z_elements = [e for e in elements if e["z_re"] is not None and e["z_im"] is not None]
    re_map = {e["name"]: pd.to_numeric(df_z[e["z_re"]], errors="coerce") for e in z_elements}
    im_map = {e["name"]: pd.to_numeric(df_z[e["z_im"]], errors="coerce") for e in z_elements}

    for i, e in enumerate(z_elements):
        name = e["name"]
        etype = str(e["type"] or "")
        z_r = re_map[name]
        z_i = -im_map[name]
        if etype == "Inductor":
            offset = float(np.nansum([
                re_map[o["name"]].iloc[0]
                for o in z_elements
                if str(o["type"] or "") in _RESISTOR_LIKE_TYPES
            ]))
        else:
            offset = float(np.nansum([re_map[z_elements[j]["name"]].iloc[-1] for j in range(i)]))
        color = element_colors[elements.index(e)]
        ax.plot(z_r + offset, z_i, linewidth=1.5, color=color, label=name)

    ax.set_xlabel("Z′ [Ω·cm²]")
    ax.set_ylabel("−Z″ [Ω·cm²]")
    # Keep a 1:1 data aspect (daspect [1 1 1]); apply manual limits if provided.
    if xlim is not None and xlim[0] is not None and xlim[1] is not None:
        ax.set_xlim(xlim[0], xlim[1])
    if ylim is not None and ylim[0] is not None and ylim[1] is not None:
        ax.set_ylim(ylim[0], ylim[1])
    ax.set_aspect("equal", adjustable="box")

    if not st.session_state.get("export_no_grid", False):
        ax.grid(True, linewidth=0.5, alpha=0.3)
    if not st.session_state.get("export_no_legend", False):
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=1, frameon=False)
        fig.subplots_adjust(right=0.78)

    for fmt in st.session_state.export_formats:
        zf.writestr(f"CNLS/Compare/{fname}_nyquist.{fmt}", _fig_to_bytes(fig, fmt))

    # ---- 3. DRT with individual element contributions ----
    if "DRT" not in xls.sheet_names:
        return

    df_drt = pd.read_excel(xls, "DRT")
    if df_drt.shape[1] < 2:
        return

    freq_drt = pd.to_numeric(df_drt.iloc[:, 0], errors="coerce")
    gamma_total = pd.to_numeric(df_drt.iloc[:, 1], errors="coerce")

    fig, ax = plt.subplots(figsize=(8, 5), dpi=600)
    ax.semilogx(freq_drt, gamma_total, linewidth=1.5, color="black", alpha=0.3, label="Total γ")

    ymax = float(np.nanmax(gamma_total))
    for i, e in enumerate(elements):
        if e["drt"] is None:
            continue
        gamma_elem = pd.to_numeric(df_drt[e["drt"]], errors="coerce")
        ax.semilogx(freq_drt, gamma_elem, linewidth=1.5, color=element_colors[i], label=e["name"])
        elem_max = float(np.nanmax(gamma_elem))
        if np.isfinite(elem_max):
            ymax = max(ymax, elem_max)

    ax.set_xlim(float(np.nanmin(freq_drt)), float(np.nanmax(freq_drt)))
    ax.set_ylim(0, 1.05 * ymax)
    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("γ [Ω·cm²·s]")

    if not st.session_state.get("export_no_grid", False):
        ax.grid(True, linewidth=0.5, alpha=0.3)
    if not st.session_state.get("export_no_legend", False):
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=1, frameon=False)
        fig.subplots_adjust(right=0.78)

    for fmt in st.session_state.export_formats:
        zf.writestr(f"CNLS/Compare/{fname}_drt.{fmt}", _fig_to_bytes(fig, fmt))


def add_cnls_heatmap_png(zf: zipfile.ZipFile, df_cnls: pd.DataFrame, palette_choice: str,
                         param_groups=None, r_limit=None, tau_limit=None, alpha_limit=None):

    if param_groups is None:
        param_groups = ["R", "Time constant", "Alpha"]

    cmap_name = PALETTE_LIBRARY.get(palette_choice, "viridis") if palette_choice in PLOTLY_SEQ else "viridis"
    y_labels = [latex_label(i) for i in df_cnls.index.tolist()]
    r_indices = sorted(
        {int(k[1:]) for k in df_cnls.columns if k.startswith("R") and k not in ("R_ohmic", "R_pol")}
    )
    no_grid = st.session_state.get("export_no_grid", False)

    def _write_heatmap(data_arr, x_labels, cbar_label, zip_name, vmin=None, vmax=None):
        n_rows, n_cols = data_arr.shape
        fig, ax = plt.subplots(figsize=(1.2 * n_cols, max(3, 0.6 * n_rows)), dpi=600)
        im = ax.imshow(
            data_arr, aspect="auto", cmap=cmap_name,
            vmin=vmin if vmin is not None else np.nanmin(data_arr),
            vmax=vmax if vmax is not None else np.nanmax(data_arr),
        )
        ax.set_xticks(np.arange(n_cols))
        ax.set_xticklabels(x_labels, rotation=30, ha="right")
        ax.set_yticks(np.arange(n_rows))
        ax.set_yticklabels(y_labels)
        ax.set_xticks(np.arange(-.5, n_cols, 1), minor=True)
        ax.set_yticks(np.arange(-.5, n_rows, 1), minor=True)
        if not no_grid:
            ax.grid(which="minor", color="white", linestyle="-", linewidth=1.2)
        ax.tick_params(which="minor", bottom=False, left=False)
        fig.colorbar(im, ax=ax).set_label(cbar_label)
        fig.tight_layout()
        for fmt in st.session_state.export_formats:
            zf.writestr(f"CNLS/{zip_name}.{fmt}", _fig_to_bytes(fig, fmt))

    # ---- Resistances ----
    if "R" in param_groups:
        r_cols = [f"R{i}" for i in r_indices if f"R{i}" in df_cnls.columns]
        r_col_order = [c for c in ["ASR", "R_ohmic"] + r_cols if c in df_cnls.columns]
        if r_col_order:
            data = df_cnls[r_col_order].values.astype(float)
            x_labels = [r"$R_{\mathrm{ohmic}}$" if c == "R_ohmic" else c for c in r_col_order]
            r_vmin = r_limit[0] if (r_limit and r_limit[0] is not None) else None
            r_vmax = r_limit[1] if (r_limit and r_limit[1] is not None) else None
            _write_heatmap(data, x_labels, "R [Ω·cm²]", "CNLS_heatmap_R", vmin=r_vmin, vmax=r_vmax)

    # ---- Time constants ----
    if "Time constant" in param_groups:
        tau_cols = [f"tau{i}" for i in r_indices if f"tau{i}" in df_cnls.columns]
        if tau_cols:
            data = df_cnls[tau_cols].values.astype(float)
            x_labels = [fr"$\tau_{{{c[3:]}}}$" for c in tau_cols]
            tau_vmin = tau_limit[0] if (tau_limit and tau_limit[0] is not None) else None
            tau_vmax = tau_limit[1] if (tau_limit and tau_limit[1] is not None) else None
            _write_heatmap(data, x_labels, "τ [s]", "CNLS_heatmap_tau", vmin=tau_vmin, vmax=tau_vmax)

    # ---- Dispersion factors (linear 0–1) ----
    if "Alpha" in param_groups:
        alpha_cols = [f"alpha{i}" for i in r_indices if f"alpha{i}" in df_cnls.columns]
        if alpha_cols:
            data = df_cnls[alpha_cols].values.astype(float)
            x_labels = [fr"$\alpha_{{{c[5:]}}}$" for c in alpha_cols]
            a_vmin = alpha_limit[0] if (alpha_limit and alpha_limit[0] is not None) else 0
            a_vmax = alpha_limit[1] if (alpha_limit and alpha_limit[1] is not None) else 1
            _write_heatmap(data, x_labels, "α", "CNLS_heatmap_alpha", vmin=a_vmin, vmax=a_vmax)



# ===============================
# App
# ===============================
st.set_page_config(page_title="SOCEIS Data Viewer", layout="wide")
st.title("SOCEIS Data Viewer")

with st.sidebar:
    # --- Root folder input + browse button (manual typing preserved) ---
    if "root_input" not in st.session_state:
        st.session_state.root_input = str(DEFAULT_ROOT_FOLDER)

    col_left, col_right = st.columns([0.82, 0.18], vertical_alignment="bottom")

    with col_left:
        st.session_state.root_input = st.text_input(
            "Root folder (auto-discover EIS)",
            value=st.session_state.root_input
        )

    with col_right:
        browse = st.button("📁", width='stretch')

    if browse:
        selected_folder = pick_folder_dialog(
            current_dir=st.session_state.root_input,
            fallback_dir=DEFAULT_ROOT_FOLDER,
        )
        if selected_folder:
            st.session_state.root_input = selected_folder
            st.rerun()
        else:
            if not TK_AVAILABLE:
                st.warning("Folder picker unavailable. On macOS, please allow Terminal/Python automation access to Finder, or type the path manually.")
            # If user canceled dialog, do nothing.

    root_path = Path(st.session_state.root_input)

    # Detect root folder change so the export path can follow it
    _root_changed = st.session_state.get("_last_root_input") != st.session_state.root_input
    st.session_state["_last_root_input"] = st.session_state.root_input

    eis_files = discover_eis_files(root_path) if root_path.exists() else []
    if not eis_files:
        st.warning("No EIS folders/files found under the given root.")
        st.stop()

    display_map = {str(f.relative_to(root_path)): f for f in eis_files}
    

   # ---- init palette choice BEFORE any read ----
    if "palette_choice" not in st.session_state:
        st.session_state.palette_choice = "Viridis (perceptual)"

    PALETTE_PREVIEW_N = 10  # keep preview squares fixed

    # ---- Initialize state ----
    if "selected_files" not in st.session_state:
        st.session_state.selected_files = []

    # Drop selections that no longer exist under the (possibly new) root folder
    _sync_multiselect_state("selected_files", list(display_map.keys()))

    st.markdown("### Select EIS files")

    col_left, col_right = st.columns([0.88, 0.12], vertical_alignment="bottom")

    # ---- Button FIRST ----
    with col_right:
        if st.button("All", width='stretch'):
            st.session_state.selected_files = list(display_map.keys())

    # ---- Then create the widget ----
    with col_left:
        selected = st.multiselect(
            " ",
            options=list(display_map.keys()),
            key="selected_files"
        )
    # ---- Optional alphabetical ordering ----
    sort_mode = st.selectbox(
        "File ordering",
        [
            "Original selection order",
            "Alphabetical by filename (A → Z)",
            "Alphabetical by filename (Z → A)",
            "Alphabetical by full path (A → Z)",
            "Alphabetical by full path (Z → A)"
        ],
        index=1
    )
    show_legend_table = st.checkbox(
        "Show personalized legend table",
        value=True,
        key="show_legend_table"
    )

    selected_keys = st.session_state.selected_files

    if sort_mode == "Alphabetical by filename (A → Z)":
        selected_keys = sorted(
            selected_keys,
            key=lambda k: natural_key(Path(k).name)
        )

    elif sort_mode == "Alphabetical by filename (Z → A)":
        selected_keys = sorted(
            selected_keys,
            key=lambda k: natural_key(Path(k).name),
            reverse=True
        )

    elif sort_mode == "Alphabetical by full path (A → Z)":
        selected_keys = sorted(
            selected_keys,
            key=lambda k: natural_key(k)
        )

    elif sort_mode == "Alphabetical by full path (Z → A)":
        selected_keys = sorted(
            selected_keys,
            key=lambda k: natural_key(k),
            reverse=True
        )

# else: Original selection order → do nothing
# else: keep original selection order

    files_to_process = [display_map[s] for s in selected_keys]
    # --- Always initialize custom_names once ---
    if "custom_names" not in st.session_state:
        st.session_state["custom_names"] = {}

    # Ensure every selected file has a default label
    for f in files_to_process:
        st.session_state["custom_names"].setdefault(f.name, f.stem)

    n_files = max(2, len(files_to_process))
    st.markdown("### Colors")

    # (2) Palette selector (single widget with one key)
    st.selectbox(
        "Color palette",
        options=list(PALETTE_LIBRARY.keys()),
        key="palette_choice",
    )

    # (3) Actual colors used in plots (adapts to number of selected files)
    COLOR_PALETTE = sample_palette_colors(st.session_state.palette_choice, n=n_files)

    # (4) Preview (fixed number of squares, but correct palette range)
    preview_colors = sample_palette_colors(st.session_state.palette_choice, n=PALETTE_PREVIEW_N)
    st.markdown(render_palette_preview(preview_colors), unsafe_allow_html=True)
    

    st.header("Nyquist")
    # Build Nyquist options dynamically
    NYQUIST_TYPES_DYNAMIC = list(NYQUIST_TYPES)  # Original, Truncated, etc.
    drt_fit_available = has_drt_fit(files_to_process)
    if drt_fit_available:
        NYQUIST_TYPES_DYNAMIC.append("DRT Fit")
    # If "DRT Fit" was selected previously but now not available, remove it
    prev = st.session_state.get("nyquist_selected", [])
    if (not drt_fit_available) and ("DRT Fit" in prev):
        st.session_state["nyquist_selected"] = [x for x in prev if x != "DRT Fit"]
    nyquist_selected = st.multiselect(
        "Nyquist types",
        NYQUIST_TYPES_DYNAMIC,
        default=[x for x in DEFAULT_NYQUIST if x in NYQUIST_TYPES_DYNAMIC],
        key="nyquist_selected"
    )
    # -------------------------
    # Nyquist Compare
    # -------------------------

    compare_options = [
        "Truncated vs Original",
        "Smooth vs Truncated",
        "LC corrected vs Truncated",
        "Extended vs Truncated"
    ]

    if drt_fit_available:
        compare_options.append("DRT Fit vs Truncated")

    cnls_fit_available = any(sibling_file(f, "CNLS").exists() for f in files_to_process)
    if cnls_fit_available:
        compare_options.append("CNLS Fit vs Truncated")

    _sync_multiselect_state("nyquist_compare_selected", compare_options)
    nyquist_compare_selected = st.multiselect(
        "Compare",
        compare_options,
        default=["Smooth vs Truncated"],
        key="nyquist_compare_selected"
    )

    nyquist_show_params = st.checkbox("Parameters", value=False, key="nyq_params")

    eis_res_plot = st.multiselect(
        "Resistances across files (KK)",
        ["R_ohm", "R_pol", "ASR"],
        default=[],
        key="eis_res_plot",
        help="Plots each selected resistance across the selected files (from the KK 'Resistance' sheet) and shows a table with your custom labels."
    )

    st.header("Bode")
    bode_selected = st.multiselect("Bode types", BODE_TYPES, default=[])
    zhit_show = st.checkbox("Z-HIT", value=False, key="zhit_show")

    st.header("DRT")
    drt_selected = st.multiselect("DRT types", DRT_TYPES, default=["Truncated"])
    drt_show_params = st.checkbox("Parameters", value=False, key="drt_params")
    st.checkbox(
        "DRT y-axis from 0",
        value=True,
        key="drt_y_from_zero",
        help="When enabled, the DRT γ-axis starts at 0. Disable for a loose (auto-scaled) y-axis.",
    )

    drt_res_plot = st.multiselect(
        "Resistances across files (DRT, ReIm)",
        ["R_ohm", "R_pol", "ASR"],
        default=[],
        key="drt_res_plot",
        help="Plots each selected resistance across the selected files (DRT ReIm result) and shows a table with your custom labels."
    )
    if drt_res_plot:
        drt_res_method = st.selectbox(
            "Resistance method",
            DRT_TYPES,
            index=0,
            key="drt_res_method",
        )
    else:
        drt_res_method = None


    st.header("CNLS")

    if len(selected) == 1:
        # Single file
        cnls_plot_modes = st.multiselect(
            "CNLS plot types",
            ["Bar plot", "Elements fitting", "CNLS compare"],
            default=[],
            key="cnls_plot_modes_single"
        )
        cnls_line_selection = []
        cnls_heatmap_params = []
    else:
        # Multiple files
        cnls_plot_modes = st.multiselect(
            "CNLS plot types",
            ["Heatmap", "Line plots", "CNLS compare"],
            default=[],
            key="cnls_plot_modes_multi"
        )
        cnls_line_selection = []
        cnls_heatmap_params = (
            st.multiselect(
                "Heatmap parameters",
                ["R", "Time constant", "Alpha"],
                default=["R", "Time constant", "Alpha"],
                key="cnls_heatmap_params"
            )
            if "Heatmap" in cnls_plot_modes
            else []
        )

    cnls_show_params = st.checkbox("Parameters", value=False, key="cnls_params")

    with st.expander("Y-axis limits", expanded=False):
        st.caption("Leave blank for auto-scaling")
        _c1, _c2 = st.columns(2)
        cnls_r_lim_lo = _c1.number_input("R min", value=None, placeholder="auto", key="cnls_r_lim_lo")
        cnls_r_lim_hi = _c2.number_input("R max", value=None, placeholder="auto", key="cnls_r_lim_hi")
        _c3, _c4 = st.columns(2)
        cnls_tau_lim_lo = _c3.number_input("τ min", value=None, placeholder="auto", key="cnls_tau_lim_lo")
        cnls_tau_lim_hi = _c4.number_input("τ max", value=None, placeholder="auto", key="cnls_tau_lim_hi")
        _c5, _c6 = st.columns(2)
        cnls_alpha_lim_lo = _c5.number_input("α min", value=None, placeholder="auto", key="cnls_alpha_lim_lo")
        cnls_alpha_lim_hi = _c6.number_input("α max", value=None, placeholder="auto", key="cnls_alpha_lim_hi")

    cnls_r_limit = (cnls_r_lim_lo, cnls_r_lim_hi) if (cnls_r_lim_lo is not None and cnls_r_lim_hi is not None) else None
    cnls_tau_limit = (cnls_tau_lim_lo, cnls_tau_lim_hi) if (cnls_tau_lim_lo is not None and cnls_tau_lim_hi is not None) else None
    cnls_alpha_limit = (cnls_alpha_lim_lo, cnls_alpha_lim_hi) if (cnls_alpha_lim_lo is not None and cnls_alpha_lim_hi is not None) else None

    with st.expander("CNLS compare axis limits", expanded=False):
        st.caption("Applies to the CNLS compare Nyquist fit plot. Leave blank for auto-scaling.")
        _cx1, _cx2 = st.columns(2)
        cnls_cmp_x_lo = _cx1.number_input("Z′ min", value=None, placeholder="auto", key="cnls_cmp_x_lo")
        cnls_cmp_x_hi = _cx2.number_input("Z′ max", value=None, placeholder="auto", key="cnls_cmp_x_hi")
        _cy1, _cy2 = st.columns(2)
        cnls_cmp_y_lo = _cy1.number_input("−Z″ min", value=None, placeholder="auto", key="cnls_cmp_y_lo")
        cnls_cmp_y_hi = _cy2.number_input("−Z″ max", value=None, placeholder="auto", key="cnls_cmp_y_hi")

    cnls_cmp_xlim = (cnls_cmp_x_lo, cnls_cmp_x_hi) if (cnls_cmp_x_lo is not None and cnls_cmp_x_hi is not None) else None
    cnls_cmp_ylim = (cnls_cmp_y_lo, cnls_cmp_y_hi) if (cnls_cmp_y_lo is not None and cnls_cmp_y_hi is not None) else None

    analyze_cnls = bool(cnls_plot_modes) or cnls_show_params

    st.header("3D Visualization")
    nyquist_3d = st.checkbox("3D Nyquist", value=False)
    drt_3d = st.checkbox("3D DRT", value=False)
    st.checkbox(
        "Colorbar instead of legend",
        value=False,
        key="colorbar_mode",
        help="Replaces the legend on all EIS and DRT plots with a continuous colorbar (4 tick labels)."
    )

    st.header("Export")
    export_no_nyquist_markers = st.checkbox(
        "Remove markers",
        value=False,
        key="export_no_nyquist_markers"
    )

    export_no_grid = st.checkbox(
        "Remove grid lines",
        value=False,
        key="export_no_grid"
    )

    export_no_legend = st.checkbox(
        "Remove legends",
        value=False,
        key="export_no_legend"
    )

    if "export_input" not in st.session_state or _root_changed:
        st.session_state.export_input = str(Path(st.session_state.root_input) / "SOCEIS_figures")

    col_left, col_right = st.columns([0.82, 0.18], vertical_alignment="bottom")

    with col_left:
        st.session_state.export_input = st.text_input(
            "Export folder path",
            value=st.session_state.export_input
        )

    with col_right:
        browse_export = st.button("📁", key="browse_export", width='stretch')

    if browse_export:
        selected_folder = pick_folder_dialog(
            current_dir=st.session_state.export_input,
            fallback_dir=DEFAULT_EXPORT_FOLDER,
        )
        if selected_folder:
            st.session_state.export_input = selected_folder
            st.rerun()

    export_folder = Path(st.session_state.export_input)
    # ------------------------------
    # Export file types
    # ------------------------------

    export_formats = st.multiselect(
        "Select formats",
        options=["png", "jpg", "pdf"],
        default=["png"],
        key="export_formats"
    )

    # Safety fallback
    if not export_formats:
        st.session_state.export_formats = ["png"]
    save_zip = st.button("💾 Save ZIP")
    # --- Export styling toggles ---

if not files_to_process:
    st.info("Select at least one EIS file.")
    st.stop()

# --- Always build display_name_map (even if legend table is hidden) ---
if show_legend_table:
    display_name_map = {
        f.name: st.session_state["custom_names"].get(f.name, f.stem)
        for f in files_to_process
    }
else:
    # fallback to filename without extension
    display_name_map = {f.name: f.stem for f in files_to_process}


# ===============================
# File Label Editor (Main Page)
# ===============================
if show_legend_table:
    st.subheader("Selected Files")

    # Build current table from session_state (source of truth)
    rows = []
    for idx, f in enumerate(files_to_process, start=1):
        fname = f.name
        rows.append({
            "Index": idx,
            "File name": fname,
            "Personalized name (LaTeX-friendly)": st.session_state.custom_names.get(fname, Path(fname).stem),
        })

    df_labels = pd.DataFrame(rows)

    # ---- EDITOR INSIDE A FORM (only commits on Apply) ----
    with st.form("legend_editor_form", clear_on_submit=False):
        edited_df = st.data_editor(
            df_labels,
            key="legend_editor",  # IMPORTANT: stable key
            column_config={
                "Index": st.column_config.NumberColumn(disabled=True),
                "File name": st.column_config.TextColumn(disabled=True),
                "Personalized name (LaTeX-friendly)": st.column_config.TextColumn(),
            },
            hide_index=True,
            width='stretch',
        )

        colA, colB = st.columns([0.25, 0.75])
        with colA:
            apply_labels = st.form_submit_button("✅ Apply labels")

        # Optional: reset inside the form
        with colB:
            reset_labels = st.form_submit_button("↩ Reset to filenames")

    # ---- APPLY / RESET (only here, after button press) ----
    if apply_labels:
        for _, row in edited_df.iterrows():
            st.session_state.custom_names[row["File name"]] = row["Personalized name (LaTeX-friendly)"]
        st.rerun()

    if reset_labels:
        for f in files_to_process:
            st.session_state.custom_names[f.name] = f.stem
        st.rerun()

# ===============================
# Load data
# ===============================
eis_param_rows: List[Dict] = []
drt_param_rows: List[Dict] = []
cnls_rows: List[Dict] = []
eis_res_rows: List[Dict] = []
drt_res_rows: List[Dict] = []

nyquist_data: Dict[str, List[Tuple[str, pd.DataFrame]]] = {p: [] for p in nyquist_selected}
bode_data: Dict[str, List[Tuple[str, pd.DataFrame]]] = {p: [] for p in bode_selected}
drt_data: Dict[str, List[Tuple[str, pd.DataFrame]]] = {p: [] for p in drt_selected}
zhit_data: List[Tuple[str, pd.DataFrame]] = []

for eis_file in files_to_process:
    fname = eis_file.name
    xls = pd.ExcelFile(_normalize_path(eis_file))

    # EIS parameters
    eis_param_rows.append(extract_eis_parameters(xls, fname))

    # EIS resistances (KK) across files
    if eis_res_plot:
        eis_res = extract_eis_resistances(xls)
        if eis_res:
            eis_res_rows.append({"Label": display_name_map.get(fname, fname), **eis_res})

    # Nyquist
    for p in nyquist_selected:
        if p in xls.sheet_names:
            df = pd.read_excel(xls, p)
            if df.shape[1] >= 3:
                label = display_name_map.get(fname, fname)
                nyquist_data[p].append((latex_label(label), df))

    # Bode 
    for p in bode_selected:
        if p in xls.sheet_names:
            df = pd.read_excel(xls, p)
            if df.shape[1] >= 3:
                label = display_name_map.get(fname, fname)
                bode_data[p].append((latex_label(label), df))

    # Z-HIT
    if zhit_show and "ZHIT" in xls.sheet_names:
        df_zhit = pd.read_excel(xls, "ZHIT")
        if df_zhit.shape[1] >= 6:
            label = display_name_map.get(fname, fname)
            zhit_data.append((latex_label(label), df_zhit))

    # DRT from sibling DRT file
    drt_file = sibling_file(eis_file, "DRT")
    if drt_file.exists():
        drt_xls = pd.ExcelFile(_normalize_path(drt_file))

        lam_row = extract_drt_lambda(drt_xls, fname)
        if lam_row is not None:
            drt_param_rows.append(lam_row)

        # DRT resistances (ReIm) across files
        if drt_res_plot and drt_res_method:
            drt_res = extract_drt_resistances(drt_xls, drt_res_method, "ReIm")
            if drt_res:
                drt_res_rows.append({"Label": display_name_map.get(fname, fname), **drt_res})

        for p in drt_selected:
            sheet = DRT_SHEET_MAP[p]
            if sheet in drt_xls.sheet_names:
                df = pd.read_excel(drt_xls, sheet)
                if df.shape[1] >= 2:
                    label = display_name_map.get(fname, fname)
                    drt_data[p].append((latex_label(label), df))

        # ---- Nyquist "DRT Fit" (from DRT file) ----
        if "DRT Fit" in nyquist_selected:
            if "Tknv_ReIm_s" in drt_xls.sheet_names:
                df_fit = pd.read_excel(drt_xls, "Tknv_ReIm_s")
                if df_fit.shape[1] >= 4:
                    label = display_name_map.get(fname, fname)
                    nyquist_data.setdefault("DRT Fit", [])
                    nyquist_data["DRT Fit"].append((latex_label(label), df_fit))

    # CNLS from sibling CNLS file (optional)
        if analyze_cnls:
            cnls_file = sibling_file(eis_file, "CNLS")
            params = extract_cnls_parameters(cnls_file)
            if params is not None:
                display_label = display_name_map.get(fname, fname)
                params_row = {"File": display_label, **params}
                cnls_rows.append(params_row)


# ===============================
# Plot display
# ===============================
if nyquist_show_params:
    st.subheader("Nyquist")
    eis_cols = ["File"] + [lbl for (lbl, _) in EIS_PARAM_ORDER]
    df_eis_params = pd.DataFrame(eis_param_rows).reindex(columns=eis_cols)
    df_eis_params.index = np.arange(1, len(df_eis_params) + 1)
    df_eis_params.index.name = "Index"
    st.dataframe(df_eis_params, width="stretch")

if nyquist_selected:
    if not nyquist_show_params:
        st.subheader("Nyquist")
    
    for p, data in nyquist_data.items():
        if not data:
            continue

        if nyquist_3d:
            if p == "DRT Fit":
                st.plotly_chart(
                    nyquist_3d_plotly_cols(data, "Nyquist - DRT Fit", x_col=2, y_col=3, negate_y=True),
                    width="stretch"
                )
            else:
                st.plotly_chart(nyquist_3d_plotly(data, p), width="stretch")
        else:
            if p == "DRT Fit":
                st.plotly_chart(nyquist_fit_plotly(data), width="stretch")
            else:
                st.plotly_chart(nyquist_plotly(data, p), width="stretch")

# ===============================
# Nyquist Compare Plots
# ===============================

if nyquist_compare_selected:

    if not nyquist_show_params and not nyquist_selected:
        st.subheader("Nyquist")

    for mode in nyquist_compare_selected:
        fig = nyquist_compare_plotly(
            mode,
            files_to_process,
            display_name_map
        )
        st.plotly_chart(fig, width="stretch")

# ---- EIS resistances (KK) across files: one figure per resistance + table ----
if eis_res_plot:
    st.subheader("EIS resistances (KK)")
    if eis_res_rows:
        df_eis_res = pd.DataFrame(eis_res_rows).set_index("Label")
        for param in eis_res_plot:
            if param in df_eis_res.columns:
                st.plotly_chart(cnls_line_plotly(df_eis_res, param), width="stretch", key=f"eis_res_{param}")
        render_resistance_table(df_eis_res, eis_res_plot)
    else:
        st.info("No KK 'Resistance' sheet found in the selected EIS files.")

if bode_selected:
    st.subheader("Bode")

    for p, data in bode_data.items():
        if data:
            # One title per Bode type
            st.markdown(f"**{p}**")

            # Real part
            st.plotly_chart(
                bode_plotly(data, p, real=True),
                width="stretch",
                key=f"bode_{p}_real"
            )

            # Imaginary part
            st.plotly_chart(
                bode_plotly(data, p, real=False),
                width="stretch",
                key=f"bode_{p}_imag"
            )

if zhit_show and zhit_data:
    st.subheader("Z-HIT")
    st.plotly_chart(zhit_plotly(zhit_data, mode="modulus"), width="stretch", key="zhit_modulus")
    st.plotly_chart(zhit_plotly(zhit_data, mode="phase"),   width="stretch", key="zhit_phase")
    st.plotly_chart(zhit_plotly(zhit_data, mode="delta"),   width="stretch", key="zhit_delta")

if drt_show_params and drt_param_rows:
    st.subheader("DRT")
    df_drt_params = pd.DataFrame(drt_param_rows)
    df_drt_params.index = np.arange(1, len(df_drt_params) + 1)
    df_drt_params.index.name = "Index"
    st.data_editor(
        df_drt_params,
        column_config={
            "tknv_pos": st.column_config.CheckboxColumn(
                "Tikhonov positive definite",
                help="True if positivity constraint enabled"
            ),
            "rbf_enabled": st.column_config.CheckboxColumn(
                "RBF-DRT enabled",
                help="True if RBF-DRT was computed"
            ),
        },
        disabled=True,
        hide_index=False,
        width="stretch"
    )
if drt_selected:
    if not drt_show_params:
        st.subheader("DRT")

    for p, data in drt_data.items():
        if data:
            if drt_3d:
                st.plotly_chart(drt_3d_plotly(data, p), width="stretch")
            else:
                st.plotly_chart(drt_plotly(data, p), width="stretch")

# ---- DRT resistances (ReIm) across files: one figure per resistance + table ----
if drt_res_plot:
    st.subheader(f"DRT resistances ({drt_res_method}, ReIm)")
    if drt_res_rows:
        df_drt_res = pd.DataFrame(drt_res_rows).set_index("Label")
        for param in drt_res_plot:
            if param in df_drt_res.columns:
                st.plotly_chart(cnls_line_plotly(df_drt_res, param), width="stretch", key=f"drt_res_{param}")
        render_resistance_table(df_drt_res, drt_res_plot)
    else:
        st.info(f"No '{DRT_RES_SHEET_MAP.get(drt_res_method, drt_res_method)}' resistance sheet found in the selected DRT files.")

# CNLS section
df_cnls = None
if analyze_cnls:
    st.subheader("CNLS")

    if cnls_rows:
        df_cnls = pd.DataFrame(cnls_rows).set_index("File")

        # ---- Equivalent circuit schematic (from the first CNLS file's topology) ----
        _ecm_file = sibling_file(files_to_process[0], "CNLS")
        _ecm_fig = cnls_circuit_figure(_ecm_file)
        if _ecm_fig is not None:
            st.markdown("**Equivalent circuit model**")
            if len(df_cnls) > 1:
                st.caption(f"Topology shown for {display_name_map.get(files_to_process[0].name, files_to_process[0].name)} (first selected file).")
            st.pyplot(_ecm_fig)
            plt.close(_ecm_fig)

        if len(df_cnls) > 1:
            _r_idx_set = sorted(
                {int(k[1:]) for k in df_cnls.columns if k.startswith("R") and k not in ("R_ohmic", "R_pol")}
            )
            plotable_columns = ["ASR", "R_pol", "R_ohmic"]
            for _i in _r_idx_set:
                for _pfx in ("R", "tau", "alpha"):
                    _col = f"{_pfx}{_i}"
                    if _col in df_cnls.columns:
                        plotable_columns.append(_col)
            # Standalone inductances introduced by custom topology.
            if "L_hf" in df_cnls.columns:
                plotable_columns.append("L_hf")
            for _i in sorted({int(k[1:]) for k in df_cnls.columns if re.fullmatch(r"L\d+", k)}):
                plotable_columns.append(f"L{_i}")

            # Update selectable list dynamically
            if "Line plots" in cnls_plot_modes:
                _sync_multiselect_state("cnls_line_selection", plotable_columns)
                cnls_line_selection = st.multiselect(
                    "Select parameters to plot",
                    plotable_columns,
                    default=plotable_columns,
                    key="cnls_line_selection"
                )

        # ---- Dynamic column ordering ----
        r_indices = sorted(
            {int(k[1:]) for k in df_cnls.columns if k.startswith("R") and k not in ("R_ohmic", "R_pol")}
        )

        ordered_cols = ["ASR", "R_ohmic"]

        for idx in r_indices:
            if f"R{idx}" in df_cnls.columns:
                ordered_cols.append(f"R{idx}")
            if f"tau{idx}" in df_cnls.columns:
                ordered_cols.append(f"tau{idx}")
            if f"alpha{idx}" in df_cnls.columns:
                ordered_cols.append(f"alpha{idx}")

        # Standalone inductances (HF inductance + extra inductors).
        l_indices = sorted({int(k[1:]) for k in df_cnls.columns if re.fullmatch(r"L\d+", k)})
        if "L_hf" in df_cnls.columns:
            ordered_cols.append("L_hf")
        for idx in l_indices:
            ordered_cols.append(f"L{idx}")

        df_display = df_cnls[ordered_cols]

        # ---- Rename columns with Greek letters ----
        rename_map = {"R_ohmic": "Rₒₕₘ"}

        for idx in r_indices:
            if f"tau{idx}" in df_display.columns:
                rename_map[f"tau{idx}"] = f"τ{idx}"
            if f"alpha{idx}" in df_display.columns:
                rename_map[f"alpha{idx}"] = f"α{idx}"

        df_display = df_display.rename(columns=rename_map)

        if cnls_show_params:
            df_display.index = np.arange(1, len(df_display) + 1)
            df_display.index.name = "Index"
            st.dataframe(df_display, width="stretch")


        # ---- Plot section unchanged ----
        if len(df_cnls) == 1:

            series = df_cnls.iloc[0]
            cnls_file = sibling_file(files_to_process[0], "CNLS")

            if "Bar plot" in cnls_plot_modes:
                st.plotly_chart(cnls_bar_plotly(series, ylim=None), width="stretch")

            if "Elements fitting" in cnls_plot_modes:

                cnls_file = sibling_file(files_to_process[0], "CNLS")

                # DRT elements (already done)
                fig_elem = cnls_elements_fitting_plotly(cnls_file, df_cnls.index[0])
                if fig_elem:
                    st.plotly_chart(fig_elem, width="stretch", key="cnls_single_elements_fit")

                # Nyquist fit
                fig_nyq = cnls_nyquist_fit_plotly(cnls_file, df_cnls.index[0])
                if fig_nyq:
                    st.plotly_chart(fig_nyq, width="stretch", key="cnls_single_nyquist_fit")

                # Residuals
                fig_res = cnls_residuals_plotly(cnls_file, df_cnls.index[0])
                if fig_res:
                    st.plotly_chart(fig_res, width="stretch", key="cnls_single_residuals")
        else:

            if "Heatmap" in cnls_plot_modes:
                for fig in cnls_heatmap_plotly(
                    df_cnls, st.session_state.palette_choice, cnls_heatmap_params,
                    r_limit=cnls_r_limit, tau_limit=cnls_tau_limit, alpha_limit=cnls_alpha_limit,
                ):
                    st.plotly_chart(fig, width="stretch")

            if "Line plots" in cnls_plot_modes and cnls_line_selection:
                for param in cnls_line_selection:
                    if param.startswith("tau"):
                        _ylim = cnls_tau_limit
                    elif param.startswith("alpha"):
                        _ylim = cnls_alpha_limit
                    elif param in ("ASR", "R_pol") or param == "L_hf" or re.fullmatch(r"L\d+", param):
                        _ylim = None
                    else:
                        _ylim = cnls_r_limit
                    st.plotly_chart(
                        cnls_line_plotly(df_cnls, param, ylim=_ylim),
                        width="stretch"
                    )

                # Resistance table for the resistance subset of the plotted parameters
                res_in_sel = [
                    p for p in cnls_line_selection
                    if p in ("ASR", "R_pol", "R_ohmic") or re.fullmatch(r"R\d+", p)
                ]
                render_resistance_table(df_cnls, res_in_sel, rename={"R_ohmic": "R_ohm"})

        # ---- CNLS compare ----
        if "CNLS compare" in cnls_plot_modes:
            st.subheader("CNLS compare")

            compare_candidates = [f for f in files_to_process if sibling_file(f, "CNLS").exists()]

            if not compare_candidates:
                st.info("No CNLS files found for the selected EIS files.")
                st.session_state["cnls_compare_eis_files"] = []
            else:
                compare_label_map = {display_name_map[f.name]: f for f in compare_candidates}

                if len(compare_candidates) == 1:
                    selected_labels = list(compare_label_map.keys())
                else:
                    _sync_multiselect_state("cnls_compare_files", list(compare_label_map.keys()))
                    selected_labels = st.multiselect(
                        "Select files",
                        list(compare_label_map.keys()),
                        default=list(compare_label_map.keys()),
                        key="cnls_compare_files"
                    )

                selected_eis_files = [compare_label_map[lbl] for lbl in selected_labels]
                st.session_state["cnls_compare_eis_files"] = selected_eis_files

                for compare_idx, eis_file in enumerate(selected_eis_files):
                    compare_cnls_file = sibling_file(eis_file, "CNLS")
                    compare_fname = display_name_map[eis_file.name]

                    fig_im = cnls_elements_im_bode_plotly(compare_cnls_file, compare_fname)
                    if fig_im:
                        st.plotly_chart(fig_im, width="stretch", key=f"cnls_compare_im_bode_{compare_idx}")

                    fig_nyq = cnls_nyquist_fit_plotly(compare_cnls_file, compare_fname,
                                                      xlim=cnls_cmp_xlim, ylim=cnls_cmp_ylim)
                    if fig_nyq:
                        st.plotly_chart(fig_nyq, width="stretch", key=f"cnls_compare_nyquist_fit_{compare_idx}")

                    fig_drt = cnls_elements_fitting_plotly(compare_cnls_file, compare_fname)
                    if fig_drt:
                        st.plotly_chart(fig_drt, width="stretch", key=f"cnls_compare_elements_fit_{compare_idx}")

    else:
        st.info("CNLS enabled, but no CNLS files/sheets were found for the selected EIS files.")


# ===============================
# ZIP Export (ONLY plots shown; PNGs; non-empty)
# ===============================
if save_zip:
    export_folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_path = export_folder / f"SOCEIS_figures_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Nyquist
        for p, data in nyquist_data.items():
            if not data:
                continue

            if nyquist_3d:
                if p == "DRT Fit":
                    add_nyquist_fit_3d_png(zf, data, title="DRT_Fit")
                else:
                    add_nyquist_3d_png(zf, data, p)
            else:
                if p == "DRT Fit":
                    add_nyquist_fit_png(zf, data)
                else:
                    add_nyquist_png(zf, data, p)

        if nyquist_compare_selected:
            for mode in nyquist_compare_selected:
                add_nyquist_compare_png(
                    zf,
                    mode,
                    files_to_process,
                    display_name_map
                )

        # EIS resistances (KK) across files
        if eis_res_plot and eis_res_rows:
            df_eis_res = pd.DataFrame(eis_res_rows).set_index("Label")
            for param in eis_res_plot:
                if param in df_eis_res.columns:
                    add_cnls_line_png(zf, df_eis_res, param, folder="EIS/Resistances")

        # Bode
        for p, data in bode_data.items():
            if data:
                add_bode_png(zf, data, p, real=True) # Z'
                add_bode_png(zf, data, p, real=False) # -Z"

        # DRT
        for p, data in drt_data.items():
            if data:
                if drt_3d:
                    add_drt_3d_png(zf, data, p)
                else:
                    add_drt_png(zf, data, p)

        # DRT resistances (ReIm) across files
        if drt_res_plot and drt_res_rows:
            df_drt_res = pd.DataFrame(drt_res_rows).set_index("Label")
            for param in drt_res_plot:
                if param in df_drt_res.columns:
                    add_cnls_line_png(zf, df_drt_res, param, folder="DRT/Resistances")


        # CNLS
        if analyze_cnls and df_cnls is not None and not df_cnls.empty:

            # Equivalent circuit schematic (from the first CNLS file's topology).
            _ecm_fig = cnls_circuit_figure(sibling_file(files_to_process[0], "CNLS"))
            if _ecm_fig is not None:
                for fmt in st.session_state.export_formats:
                    zf.writestr(f"CNLS/EquivalentCircuit.{fmt}", _fig_to_bytes(_ecm_fig, fmt))
                plt.close(_ecm_fig)

            if len(files_to_process) == 1:

                cnls_file = sibling_file(files_to_process[0], "CNLS")

                if "Bar plot" in cnls_plot_modes:
                    add_cnls_bar_png(zf, df_cnls.iloc[0], df_cnls.index[0], ylim=None)

                if "Elements fitting" in cnls_plot_modes:
                    add_cnls_elements_fitting_png(
                        zf,
                        cnls_file,
                        df_cnls.index[0]
                    )
                    add_cnls_nyquist_fit_png(
                            zf,
                            cnls_file,
                            df_cnls.index[0]
                    )
                    add_cnls_residuals_png(
                            zf,
                            cnls_file,
                            df_cnls.index[0]
                    )

            else:

                if "Heatmap" in cnls_plot_modes:
                    add_cnls_heatmap_png(
                        zf,
                        df_cnls,
                        st.session_state.palette_choice,
                        cnls_heatmap_params,
                        r_limit=cnls_r_limit,
                        tau_limit=cnls_tau_limit,
                        alpha_limit=cnls_alpha_limit,
                    )

                if "Line plots" in cnls_plot_modes and cnls_line_selection:
                    for param in cnls_line_selection:
                        if param.startswith("tau"):
                            _ylim = cnls_tau_limit
                        elif param.startswith("alpha"):
                            _ylim = cnls_alpha_limit
                        elif param in ("ASR", "R_pol") or param == "L_hf" or re.fullmatch(r"L\d+", param):
                            _ylim = None
                        else:
                            _ylim = cnls_r_limit
                        add_cnls_line_png(zf, df_cnls, param, ylim=_ylim)

            if "CNLS compare" in cnls_plot_modes:
                for eis_file in st.session_state.get("cnls_compare_eis_files", []):
                    compare_cnls_file = sibling_file(eis_file, "CNLS")
                    compare_fname = display_name_map[eis_file.name]
                    add_cnls_compare_png(zf, compare_cnls_file, compare_fname,
                                         xlim=cnls_cmp_xlim, ylim=cnls_cmp_ylim)


    st.success(f"ZIP saved at: {zip_path.resolve()}")
