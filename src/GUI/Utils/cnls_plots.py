import os
import numpy as np
import dearpygui.dearpygui as dpg
import src.GUI.Utils as gui_utils
import src.GUI.Utils.cnls_curvefit as cf_engine


_CF_SHADE_THEME = None


def _cf_shade_theme():
    """Cached translucent theme for the CF confidence-band shade series."""
    global _CF_SHADE_THEME
    if _CF_SHADE_THEME is not None and dpg.does_item_exist(_CF_SHADE_THEME):
        return _CF_SHADE_THEME
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvShadeSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Fill, (70, 130, 180, 60), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_Line, (70, 130, 180, 60), category=dpg.mvThemeCat_Plots)
    _CF_SHADE_THEME = theme
    return theme


def _sanitize_log_xy(x, y, keep_decades=18):
    """Return finite, positive x/y pairs for log-x plotting.

    keep_decades limits pathological span from bad points when switching
    reference methods (e.g., accidental 1e-288 lower bounds).
    """
    try:
        x_arr = np.asarray(x, dtype=np.float64).reshape(-1)
        y_arr = np.asarray(y, dtype=np.float64).reshape(-1)
    except Exception:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    n = min(len(x_arr), len(y_arr))
    if n == 0:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    x_arr = x_arr[:n]
    y_arr = y_arr[:n]
    mask = np.isfinite(x_arr) & np.isfinite(y_arr) & (x_arr > 0)
    if np.count_nonzero(mask) < 1:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    x_valid = x_arr[mask]
    y_valid = y_arr[mask]

    # Remove extreme low-end outliers that collapse log axis limits.
    if len(x_valid) >= 2:
        x_min = float(np.min(x_valid))
        x_max = float(np.max(x_valid))
        span_limit = 10.0 ** float(keep_decades)
        if x_min > 0 and x_max > 0 and (x_max / x_min) > span_limit:
            lower_bound = x_max / span_limit
            keep_mask = x_valid >= lower_bound
            if np.count_nonzero(keep_mask) >= 2:
                x_valid = x_valid[keep_mask]
                y_valid = y_valid[keep_mask]

    return np.asarray(x_valid, dtype=np.float32), np.asarray(y_valid, dtype=np.float32)


def _set_log_axis_limits(x_axis, x_values):
    if x_axis is None or x_values is None or len(x_values) < 2:
        return
    x_min = float(np.min(x_values))
    x_max = float(np.max(x_values))
    if np.isfinite(x_min) and np.isfinite(x_max) and x_min > 0 and x_max > x_min:
        dpg.set_axis_limits(x_axis, x_min, x_max)


def _is_rbf_cnls_data_type(data_type):
    return isinstance(data_type, str) and data_type.endswith('_RBF')


def _set_drt_y_limits(y_axis, y_arrays, force_zero_lower=False):
    """Set robust y-limits for DRT plots.

    For ordinary Tikhonov modes we avoid pinning the lower bound to 0,
    so negative valleys remain visible. For RBF modes we keep zero-based
    lower bound behavior to preserve existing visual style.
    """
    if y_axis is None:
        return

    merged = []
    for arr in y_arrays:
        if arr is None:
            continue
        y = np.asarray(arr, dtype=np.float64).reshape(-1)
        y = y[np.isfinite(y)]
        if len(y) > 0:
            merged.append(y)

    if len(merged) == 0:
        dpg.set_axis_limits(y_axis, 0.0, 1.0)
        return

    y_all = np.concatenate(merged)
    y_min = float(np.min(y_all))
    y_max = float(np.max(y_all))

    if force_zero_lower:
        low = 0.0
        high = y_max * 1.1 if y_max > 0 else 1.0
    else:
        span = y_max - y_min
        if not np.isfinite(span) or span <= 0:
            pad = max(abs(y_max) * 0.1, 1e-6)
        else:
            pad = span * 0.1
        low = y_min - pad
        high = y_max + pad
        if low == high:
            high = low + 1.0

    dpg.set_axis_limits(y_axis, low, high)


def _resolve_drt_plot_xy(drt_result, use_tau=False, fallback_f=None):
    """Resolve DRT x/y from a DRT result dict, supporting RBF fine-grid keys."""
    if not isinstance(drt_result, dict):
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    reim = drt_result.get('ReIm', {})
    if not isinstance(reim, dict):
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    y = reim.get('g', None)
    if y is None:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)
    y_arr = np.asarray(y, dtype=np.float64).reshape(-1)

    x_candidates = []
    for key in ('f', 'f_gamma'):
        x_raw = reim.get(key, None)
        if x_raw is None:
            continue
        x_candidates.append(np.asarray(x_raw, dtype=np.float64).reshape(-1))

    tau_gamma = reim.get('tau_gamma', None)
    if tau_gamma is not None:
        tau_arr = np.asarray(tau_gamma, dtype=np.float64).reshape(-1)
        with np.errstate(divide='ignore', invalid='ignore'):
            x_candidates.append(1.0 / (2.0 * np.pi * tau_arr))

    # Compatibility fallback for imported CNLS files where DRT dict may only keep gamma.
    if fallback_f is not None:
        x_candidates.append(np.asarray(fallback_f, dtype=np.float64).reshape(-1))

    for x_arr in x_candidates:
        if len(x_arr) == len(y_arr) and np.all(np.isfinite(x_arr) & (x_arr > 0)):
            x_use = x_arr
            if use_tau:
                with np.errstate(divide='ignore', invalid='ignore'):
                    x_use = 1.0 / (2.0 * np.pi * x_use)
            x_clean, y_clean = _sanitize_log_xy(x_use, y_arr)
            if len(x_clean) > 0:
                return x_clean, y_clean

    return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

def update_single_plots(config):
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    """Update single-file DRT plots."""
    print("-- Updating DRT single plots...")
    try:
        _no_data = (
            config.display_file is None
            or os.path.splitext(config.display_file)[0] not in config.store
            or 'CNLS' not in config.store[os.path.splitext(config.display_file)[0]]
        )
        if _no_data:
            for _tag in [
                "tab_cnls_drt_plot_single",
                "tab_cnls_residual_plot_single",
                "tab_cnls_fit_plot_single",
                "tab_cnls_element_plot_single",
            ]:
                if dpg.does_item_exist(_tag):
                    dpg.delete_item(_tag, children_only=True)
            print("---- Continue. The specified file does not exist or not processed.")
            return
    except:
        print("---- Skipped: No valid file selected.")
        return

    file_key = os.path.splitext(config.display_file)[0]
    EIS_tmp = config.store[file_key]['EIS']
    CNLS_tmp = config.store[file_key]['CNLS']
    try:
        reference = gui_utils.cnls_functions.apply_cnls_reference_data(CNLS_tmp, EIS_tmp)
    except Exception as e:
        print(f"---- Skipped: CNLS reference data unavailable ({e}).")
        return

    if dpg.does_item_exist("combo_cnls_data_type"):
        dpg.set_value("combo_cnls_data_type", CNLS_tmp.data_type)

    if not dpg.does_item_exist("tab_bar_cnls_plot_single"):
        print("---- Skipped: tab_bar_cnls_plot_single not found.")
        return

    data = CNLS_tmp
    f_fit = data.f
    f_drt = data.f_drt if hasattr(data, "f_drt") and data.f_drt is not None else data.f
    force_zero_drt_lower = _is_rbf_cnls_data_type(getattr(data, "data_type", None))

    # Plot the DRT to identify the peaks
    try:
        if dpg.does_item_exist("tab_cnls_drt_plot_single"):
            dpg.delete_item("tab_cnls_drt_plot_single", children_only=True)
        else:
            with dpg.tab(label="DRT", tag="tab_cnls_drt_plot_single", parent="tab_bar_cnls_plot_single"):
                pass

        with dpg.plot(tag="plot_cnls_drt_single", width=-1, height=-1, no_menus=False, crosshairs=True, parent="tab_cnls_drt_plot_single"):
            x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
            y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="gamma [ohm·s·cm2]")
            file_name_no_ext = os.path.splitext(config.display_file)[0]
            drt_freq = reference.get('drt_f', reference['f'])
            frequency_DRT_show = drt_freq if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*drt_freq)
            DRT_DRT_show = reference['drt_mes']
            x_drt, y_drt = _sanitize_log_xy(frequency_DRT_show, DRT_DRT_show)
            if len(x_drt) > 0:
                dpg.add_line_series(x_drt, y_drt, parent=y_axis)
                _set_log_axis_limits(x_axis, x_drt)
                _set_drt_y_limits(y_axis, [y_drt], force_zero_lower=force_zero_drt_lower)
                dpg.add_plot_legend()

        # Plot the residual
        if dpg.does_item_exist("tab_cnls_residual_plot_single"):
            dpg.delete_item("tab_cnls_residual_plot_single", children_only=True)
        else:
            with dpg.tab(label="Residual", tag="tab_cnls_residual_plot_single", parent="tab_bar_cnls_plot_single"):
                pass

        with dpg.group(parent="tab_cnls_residual_plot_single"):
            with dpg.plot(tag="plot_cnls_residual_single", width=-1, height=int(0.4*viewport_height), no_menus=False):
                dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Residual [%]")
                if data.ResidualsReal is not None and data.ResidualsImag is not None and f_fit is not None:
                    dpg.add_scatter_series(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), 100 * data.ResidualsReal, parent=y_axis, label="Re")
                    dpg.add_scatter_series(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), 100 * data.ResidualsImag, parent=y_axis, label="Im")
                    dpg.add_plot_legend()
            with dpg.table(
                tag=f"table_cnls_plot_residuals",
                reorderable=False, # Allow column reordering via drag-and-drop
                header_row=False,  # Hide the header row
                scrollX=True,      # Enable horizontal scrolling
                scrollY=True,      # Enable vertical scrolling
                policy=dpg.mvTable_SizingFixedFit,  # Automatically adjust column width
            ):
                dpg.add_table_column(width_stretch=True)
                dpg.add_table_column(width_stretch=True)
                with dpg.table_row():
                    with dpg.plot(tag="plot_module_single", width=-1, height=-1, no_menus=False):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="|Z| [ohm·cm2]")
                        if f_fit is not None:
                            dpg.add_scatter_series(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), np.abs(data.Zmes), parent=y_axis, label="Measure")
                            dpg.add_line_series(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), np.abs(data.Ztot), parent=y_axis, label="Fit")
                            dpg.add_plot_legend()
                    with dpg.plot(tag="plot_phase_single", width=-1, height=-1, no_menus=False):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Phase [deg]")
                        if f_fit is not None:
                            dpg.add_scatter_series(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), -np.angle(data.Zmes, deg=True), parent=y_axis, label="Measure")
                            dpg.add_line_series(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), -np.angle(data.Ztot, deg=True), parent=y_axis, label="Fit")
                            dpg.add_plot_legend()
        
        if dpg.does_item_exist("tab_cnls_fit_plot_single"):
            dpg.delete_item("tab_cnls_fit_plot_single", children_only=True)
        else:
            with dpg.tab(label="Fit", tag="tab_cnls_fit_plot_single", parent="tab_bar_cnls_plot_single"):
                pass

        with dpg.table(
            tag=f"table_cnls_plot_fit",
            parent="tab_cnls_fit_plot_single",
            reorderable=False, # Allow column reordering via drag-and-drop
            header_row=False,  # Hide the header row
            scrollX=True,      # Enable horizontal scrolling
            scrollY=True,      # Enable vertical scrolling
            policy=dpg.mvTable_SizingFixedFit,  # Automatically adjust column width
        ):
            dpg.add_table_column(width_stretch=True)
            dpg.add_table_column(width_stretch=True)
            if f_fit is not None:
                with dpg.table_row():
                    with dpg.plot(tag="plot_Re_single", width=-1, height=int(0.4*viewport_height), no_menus=False):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Z' [ohm·cm2]")
                        dpg.add_scatter_series(np.asarray(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), dtype=np.float32), np.asarray(data.Zmes.real, dtype=np.float32), parent=y_axis, label="Measure")
                        dpg.add_line_series(np.asarray(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), dtype=np.float32), np.asarray(data.Ztot.real, dtype=np.float32), parent=y_axis, label="Fit")
                        dpg.add_plot_legend()
                    with dpg.plot(tag="plot_Im_single", width=-1, height=int(0.4*viewport_height), no_menus=False):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="-Z'' [ohm·cm2]")
                        dpg.add_scatter_series(np.asarray(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), dtype=np.float32), -np.asarray(data.Zmes.imag, dtype=np.float32), parent=y_axis, label="Measure")
                        dpg.add_line_series(np.asarray(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), dtype=np.float32), -np.asarray(data.Ztot.imag, dtype=np.float32), parent=y_axis, label="Fit")
                        dpg.add_plot_legend()
                with dpg.table_row():
                    with dpg.plot(tag="plot_ReIm_single", width=-1, height=-1, no_menus=False, equal_aspects = True):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Z' [ohm·cm2]", log_scale=False)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="-Z'' [ohm·cm2]")
                        dpg.add_scatter_series(np.asarray(data.Zmes.real, dtype=np.float32), -np.asarray(data.Zmes.imag, dtype=np.float32), parent=y_axis, label="Measure")
                        dpg.add_line_series(np.asarray(data.Ztot.real, dtype=np.float32), -np.asarray(data.Ztot.imag, dtype=np.float32), parent=y_axis, label="Fit")
                        dpg.add_plot_legend()
                    with dpg.plot(tag="plot_DRT_single", width=-1, height=-1, no_menus=False):
                        x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="gamma [ohm·s·cm2]")
                        x_series_all = []
                        if f_drt is not None and data.DRTmes is not None:
                            x_meas, y_meas = _sanitize_log_xy(
                                np.asarray(f_drt if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_drt), dtype=np.float64),
                                np.asarray(data.DRTmes, dtype=np.float64),
                            )
                            if len(x_meas) > 0:
                                dpg.add_scatter_series(x_meas, y_meas, parent=y_axis, label="Measure")
                                x_series_all.append(x_meas)

                        x_fit_drt, y_fit_drt = _resolve_drt_plot_xy(
                            data.DRT,
                            use_tau=dpg.get_value("check_box_cnls_tau"),
                            fallback_f=f_fit,
                        )
                        if len(x_fit_drt) > 0:
                            dpg.add_line_series(x_fit_drt, y_fit_drt, parent=y_axis, label="Fit")
                            x_series_all.append(x_fit_drt)

                        _set_drt_y_limits(
                            y_axis,
                            [y_meas if 'y_meas' in locals() else None, y_fit_drt],
                            force_zero_lower=force_zero_drt_lower,
                        )

                        if len(x_series_all) > 0:
                            _set_log_axis_limits(x_axis, np.concatenate(x_series_all))
                        dpg.add_plot_legend()

        # Element breakdown
        if dpg.does_item_exist("tab_cnls_element_plot_single"):
            dpg.delete_item("tab_cnls_element_plot_single", children_only=True)
        else:
            with dpg.tab(label="Elements", tag="tab_cnls_element_plot_single", parent="tab_bar_cnls_plot_single"):
                pass

        with dpg.group(parent="tab_cnls_element_plot_single"):
            with dpg.plot(tag="plot_elements_nyquist_single", width=-1, height=int(viewport_height*0.4), no_menus=False, equal_aspects = True):
                dpg.add_plot_axis(dpg.mvXAxis, label="Z' [ohm·cm2]", log_scale=False)
                y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="-Z'' [ohm·cm2]")
                if data.Zmes is not None and data.w is not None:
                    dpg.add_scatter_series(np.asarray(data.Zmes.real, dtype=np.float32), -np.asarray(data.Zmes.imag, dtype=np.float32), parent=y_axis, label="Measure")
                    _, Z = data.EvaluateCircuit()
                    element_type_map = {elem['name']: elem['type'] for elem in data.Elements}
                    for idx, element in enumerate(Z.columns):
                        cumulative_real = sum(np.real(Z[element].iloc[-1]) for element in Z.columns[:idx])
                        if element_type_map.get(element) == 'Inductor':
                            cumulative_real = sum(
                                np.real(Z[col][0]) for col in Z.columns
                                if element_type_map.get(col) in ['Resistor', 'Gerisher', 'fFLW', 'FLW']
                            )
                        dpg.add_line_series(np.asarray(np.real(Z[element])+cumulative_real, dtype=np.float32), -np.asarray(np.imag(Z[element]), dtype=np.float32), parent=y_axis, label=f"{element}")
                    dpg.add_plot_legend()

            with dpg.table(
                tag=f"table_cnls_plot_elements",
                reorderable=False, # Allow column reordering via drag-and-drop
                header_row=False,  # Hide the header row
                scrollX=True,      # Enable horizontal scrolling
                scrollY=True,      # Enable vertical scrolling
                policy=dpg.mvTable_SizingFixedFit,  # Automatically adjust column width
            ):
                dpg.add_table_column(width_stretch=True)
                dpg.add_table_column(width_stretch=True)
                with dpg.table_row():
                    with dpg.plot(tag="plot_cnls_elements_Im_single", width=-1, height=-1, no_menus=False):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="-Z'' [ohm·cm2]")
                        if f_fit is not None and data.Zmes is not None and data.w is not None:
                            dpg.add_scatter_series(np.asarray(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), dtype=np.float32), -np.asarray(np.imag(data.Zmes), dtype=np.float32), parent=y_axis, label="Measure")
                            for element in Z.columns:
                                dpg.add_line_series(np.asarray(f_fit if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_fit), dtype=np.float32), -np.asarray(np.imag(Z[element]), dtype=np.float32), parent=y_axis, label=f"{element}")
                            dpg.add_plot_legend()

                    with dpg.plot(tag="plot_cnls_elements_DRT_single", width=-1, height=-1, no_menus=False):
                        x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Frequency [Hz]" if not dpg.get_value("check_box_cnls_tau") else "tau [s]", log_scale=True)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="gamma [ohm·s·cm2]")
                        if f_fit is not None and data.Zmes is not None and data.w is not None:
                            x_series_all = []
                            y_series = []
                            if f_drt is not None and data.DRTmes is not None:
                                x_meas, y_meas = _sanitize_log_xy(
                                    np.asarray(f_drt if not dpg.get_value("check_box_cnls_tau") else 1/(2*np.pi*f_drt), dtype=np.float64),
                                    np.asarray(data.DRTmes, dtype=np.float64),
                                )
                                if len(x_meas) > 0:
                                    dpg.add_scatter_series(x_meas, y_meas, parent=y_axis, label="Measure")
                                    x_series_all.append(x_meas)
                                    y_series.append(y_meas)
                            for element in data.ElementDRTs:
                                if element == 'mes':
                                    continue
                                if (element.startswith('L') and 'Randle' not in element) or (element.startswith('R') and not any(excluded in element for excluded in ['RQ', 'RC', 'Randle'])):
                                    continue
                                x_elem, y_elem = _resolve_drt_plot_xy(
                                    data.ElementDRTs[element],
                                    use_tau=dpg.get_value("check_box_cnls_tau"),
                                    fallback_f=f_fit,
                                )
                                if len(x_elem) == 0:
                                    continue
                                dpg.add_line_series(x_elem, y_elem, parent=y_axis, label=f"{element}")
                                x_series_all.append(x_elem)
                                y_series.append(y_elem)
                            _set_drt_y_limits(y_axis, y_series, force_zero_lower=force_zero_drt_lower)
                            if len(x_series_all) > 0:
                                _set_log_axis_limits(x_axis, np.concatenate(x_series_all))
                            dpg.add_plot_legend()

        print("---- CNLS single plots updated successfully.")
    except:
        print("[Warning] CNLS data not updated for the selected file, which could be due to the unconsistent elements used in different files, or check cnls_plots.py_update_single_plots function.")

def update_all_plots(config):
    """Update all CNLS plots."""
    print("-- CNLS data all plots updating...")
    if not dpg.does_item_exist("tab_bar_cnls_plot_all"):
        print("---- Skipped: tab_bar_cnls_plot_all not found.")
        return

    if not config.selected_files or not config.display_file:
        dpg.delete_item("tab_bar_cnls_plot_all", children_only=True)
        print("---- Cleared: No files selected/displayed.")
        return

    try:
        file_key = os.path.splitext(config.display_file)[0]
        if file_key not in config.store or 'CNLS' not in config.store[file_key]:
            dpg.delete_item("tab_bar_cnls_plot_all", children_only=True)
            print("---- Cleared: Display file has no CNLS data.")
            return

        CNLS_tmp = config.store[file_key]['CNLS']
        if CNLS_tmp.Elements is None:
            dpg.delete_item("tab_bar_cnls_plot_all", children_only=True)
            print("---- CNLS all plots skipped: no elements found.")
            return

        name_list = [element['name'] for element in CNLS_tmp.Elements]
        valid_element_tabs = set()
        cf_x = bool(config.store.get('cf_x_index', False))

        if config.fix_all_plots_CNLS:
            source_files = [os.path.basename(file_name) for file_name in config.file_list]
        else:
            source_files = list(config.selected_files)

        for idx, param_name in enumerate(name_list):
            element_tab = f"tab_cnls_all_{param_name}"
            valid_element_tabs.add(element_tab)

            if not dpg.does_item_exist(element_tab):
                with dpg.tab(label=param_name, tag=element_tab, parent="tab_bar_cnls_plot_all"):
                    pass

            param_tab_bar = f"tab_bar_cnls_all_{param_name}"
            if not dpg.does_item_exist(param_tab_bar):
                with dpg.tab_bar(tag=param_tab_bar, parent=element_tab):
                    pass

            start_idx = CNLS_tmp.ElementsStartIndex[idx]
            end_idx = CNLS_tmp.ElementsEndIndex[idx]
            valid_param_tabs = set()

            for para_idx in range(start_idx, end_idx + 1):
                file_name_list = []
                data_list = []
                y_min_value = 0.00
                y_max_value = 0.00
                param = CNLS_tmp.ElementsParamNames[para_idx]

                if 'tau' in param.split('_')[1]:
                    y_label = "tau [s]"
                elif 'R' in param.split('_')[1]:
                    y_label = "Resistance [ohm·cm2]"
                elif 'alpha' in param.split('_')[1]:
                    y_label = "Dispersion factor"
                elif 'L' in param.split('_')[1]:
                    y_label = "Inductance [H·cm2]"
                else:
                    y_label = "Unit"

                param_tab = f"tab_cnls_all_{param}"
                valid_param_tabs.add(param_tab)
                if not dpg.does_item_exist(param_tab):
                    with dpg.tab(label=param, tag=param_tab, parent=param_tab_bar):
                        pass

                dpg.delete_item(param_tab, children_only=True)
                with dpg.group(parent=param_tab):
                    with dpg.plot(tag=f"plot_cnls_all_{param}", width=-1, height=-1, no_menus=False):
                        x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="x index" if cf_x else "Measurements", log_scale=False)
                        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label=y_label)

                        x_index_list = []
                        for file_name in source_files:
                            file_key = os.path.splitext(file_name)[0]
                            if file_key not in config.store or 'CNLS' not in config.store[file_key]:
                                print(f"[Warning] File {file_key} not found or has no CNLS data. Skipping...")
                                continue
                            cnls_file = config.store[file_key]['CNLS']
                            if (cnls_file.ElementsParamValues is None
                                    or para_idx >= len(cnls_file.ElementsParamValues)):
                                print(f"[Warning] File {file_key} missing param index {para_idx}. Skipping...")
                                continue
                            value = cnls_file.ElementsParamValues[para_idx]
                            file_name_list.append(gui_utils.small_functions.string_abbreviation(file_key, 3, 5))
                            data_list.append(value)
                            x_index_list.append(float(config.file_values.get(os.path.basename(file_name), 0.0)))
                            y_min_value = np.min([y_min_value, value])
                            y_max_value = np.max([y_max_value, value])

                        if cf_x:
                            # Points only (no connecting line); x-axis = per-file x index.
                            dpg.add_scatter_series(x_index_list, data_list, parent=y_axis)
                            fit = config.store.get('cf_fits', {}).get(param)
                            if fit and fit.get('ok') and len(x_index_list) >= 2:
                                x_lo, x_hi = min(x_index_list), max(x_index_list)
                                if x_hi > x_lo:
                                    xs = np.linspace(x_lo, x_hi, 100)
                                    yhat, ylo, yhi = cf_engine.evaluate(fit, xs)
                                    line_mask = np.isfinite(yhat)
                                    band_mask = line_mask & np.isfinite(ylo) & np.isfinite(yhi)
                                    # Shade the CI band only where it is defined (a
                                    # degenerate covariance yields a NaN band).
                                    if np.any(band_mask):
                                        xb = xs[band_mask]
                                        shade = dpg.add_shade_series(xb.tolist(), yhi[band_mask].tolist(), y2=ylo[band_mask].tolist(), parent=y_axis, label="95% CI")
                                        dpg.bind_item_theme(shade, _cf_shade_theme())
                                        y_min_value = np.min([y_min_value, float(np.min(ylo[band_mask]))])
                                        y_max_value = np.max([y_max_value, float(np.max(yhi[band_mask]))])
                                    # Always draw the fit curve itself where finite.
                                    if np.any(line_mask):
                                        xl = xs[line_mask]
                                        dpg.add_line_series(xl.tolist(), yhat[line_mask].tolist(), parent=y_axis, label=fit.get('method', 'Fit'))
                                        dpg.add_plot_legend()
                                        y_min_value = np.min([y_min_value, float(np.min(yhat[line_mask]))])
                                        y_max_value = np.max([y_max_value, float(np.max(yhat[line_mask]))])
                            if x_index_list:
                                x_span = (max(x_index_list) - min(x_index_list)) or 1.0
                                dpg.set_axis_limits(x_axis, min(x_index_list) - 0.05 * x_span, max(x_index_list) + 0.05 * x_span)
                        else:
                            x_data = list(range(1, len(file_name_list) + 1))
                            label_pairs = tuple(zip(file_name_list, x_data))
                            dpg.add_line_series(x_data, data_list, parent=y_axis)
                            dpg.add_scatter_series(x_data, data_list, parent=y_axis)
                            dpg.set_axis_limits(x_axis, 0, len(file_name_list) + 1)
                            dpg.set_axis_ticks(x_axis, label_pairs)

                        # Pad additively so negative values (e.g. negative resistance)
                        # are enclosed; multiplicative padding on a negative minimum
                        # would raise the lower bound toward zero and clip the curve.
                        span = y_max_value - y_min_value
                        pad = span * 0.1 if span > 0 else max(abs(y_min_value), abs(y_max_value), 1e-6) * 0.1
                        y_low = y_min_value - pad if y_min_value < 0 else 0.0
                        y_high = y_max_value + pad if y_max_value > 0 else pad
                        dpg.set_axis_limits(y_axis, y_low, y_high)

            # Remove stale parameter tabs if definitions changed.
            tab_children = dpg.get_item_children(param_tab_bar)
            for child in tab_children[1]:
                child_alias = dpg.get_item_alias(child)
                if child_alias and child_alias.startswith("tab_cnls_all_") and child_alias not in valid_param_tabs:
                    dpg.delete_item(child)

        # Remove element tabs that are no longer needed.
        if dpg.does_item_exist("tab_bar_cnls_plot_all"):
            children = dpg.get_item_children("tab_bar_cnls_plot_all")
            for child in children[1]:
                child_alias = dpg.get_item_alias(child)
                if child_alias and child_alias.startswith("tab_cnls_all_") and child_alias not in valid_element_tabs:
                    dpg.delete_item(child)

        print("---- CNLS all plots updated successfully.")
    except:
        print("[Warning] CNLS data not updated for all the files, which could be due to the unconsistent elements used in different files, or check cnls_plots.py_update_all_plots function.")
