"""CNLS "CF option" sub-window: curve-fit parameter trends vs per-file x index.

Non-modal window opened from the CNLS Parameters menu. Lets the user plot each
parameter against its file x index, fit a trend (with 95% confidence band), and
push the fitted value/bounds back into each file as initial guess + Ub/Lb.
"""
import os
import numpy as np
import dearpygui.dearpygui as dpg
import src.GUI.Utils as gui_utils
import src.GUI.Utils.cnls_curvefit as cf_engine

WINDOW_TAG = "window_cnls_cf"
_XINDEX_TAG = "checkbox_cnls_cf_xindex"
_CATEGORY_TAG = "combo_cnls_cf_category"
_METHOD_TAG = "combo_cnls_cf_method"
_DEGREE_TAG = "input_cnls_cf_degree"
_DEGREE_TEXT_TAG = "text_cnls_cf_degree"
_FORMULA_TAG = "text_cnls_cf_formula"
_FIT_TAG = "button_cnls_cf_fit"
_RESET_TAG = "button_cnls_cf_reset"
_TABLE_TAG = "table_cnls_cf_results"
_GATED_TAGS = (_CATEGORY_TAG, _METHOD_TAG, _DEGREE_TAG, _FIT_TAG, _RESET_TAG)


def _display_cnls(config):
    """Return the displayed file's CNLS circuit, or None."""
    if not config.display_file:
        return None
    file_key = os.path.splitext(config.display_file)[0]
    store = config.store.get(file_key)
    if not store or 'CNLS' not in store:
        return None
    return store['CNLS']


def _gather_xy(config, para_idx):
    """Collect (x index, param value) across selected files for one parameter."""
    xs, ys = [], []
    for file_name in config.selected_files:
        file_key = os.path.splitext(file_name)[0]
        store = config.store.get(file_key)
        if not store or 'CNLS' not in store:
            continue
        cnls = store['CNLS']
        if cnls.ElementsParamValues is None or para_idx >= len(cnls.ElementsParamValues):
            continue
        ys.append(float(cnls.ElementsParamValues[para_idx]))
        xs.append(float(config.file_values.get(os.path.basename(file_name), 0.0)))
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def _locate_param(cnls, para_idx):
    """Map a flat parameter index to (element index, offset within element)."""
    for elem_idx, (start, end) in enumerate(zip(cnls.ElementsStartIndex, cnls.ElementsEndIndex)):
        if start <= para_idx <= end:
            return elem_idx, para_idx - start
    return None, None


def _build_results_table(config):
    if not dpg.does_item_exist(_TABLE_TAG):
        return
    dpg.delete_item(_TABLE_TAG, children_only=True)
    dpg.add_table_column(label="Parameter", parent=_TABLE_TAG)
    dpg.add_table_column(label="R^2", parent=_TABLE_TAG)
    dpg.add_table_column(label="Fitted equation", parent=_TABLE_TAG)
    for pname, fit in config.store.get('cf_fits', {}).items():
        with dpg.table_row(parent=_TABLE_TAG):
            dpg.add_text(pname)
            dpg.add_text(f"{fit['r2']:.4f}" if fit.get('ok') else "n/a")
            dpg.add_text(cf_engine.equation_string(fit))


def _update_formula_text():
    if not dpg.does_item_exist(_FORMULA_TAG):
        return
    method = dpg.get_value(_METHOD_TAG) if dpg.does_item_exist(_METHOD_TAG) else "Polynomial"
    dpg.set_value(_FORMULA_TAG, f"Formula:  {cf_engine.formula_of(method)}")


def _set_gated_enabled(enabled):
    for tag in _GATED_TAGS:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, enabled=enabled)


def _update_degree_visibility():
    show = dpg.does_item_exist(_METHOD_TAG) and dpg.get_value(_METHOD_TAG) == "Polynomial"
    for tag in (_DEGREE_TEXT_TAG, _DEGREE_TAG):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=show)


def _on_xindex_toggle(sender, app_data, config):
    config.store['cf_x_index'] = bool(app_data)
    _set_gated_enabled(bool(app_data))
    gui_utils.cnls_plots.update_all_plots(config)


def _on_category_change(sender, app_data, config):
    methods = cf_engine.CATEGORIES.get(app_data, ["Polynomial"])
    dpg.configure_item(_METHOD_TAG, items=methods, default_value=methods[0])
    config.store['cf_method'] = methods[0]
    _update_degree_visibility()
    _update_formula_text()


def _on_method_change(sender, app_data, config):
    config.store['cf_method'] = app_data
    _update_degree_visibility()
    _update_formula_text()


def _on_fit_data(config):
    cnls = _display_cnls(config)
    if cnls is None or not cnls.ElementsParamNames:
        import src.GUI.Utils.progress_modal as _pm
        _pm.show_warning_dialog("CF option", "No displayed file with CNLS parameters to fit.")
        return
    method = dpg.get_value(_METHOD_TAG)
    degree = int(dpg.get_value(_DEGREE_TAG))
    config.store['cf_method'] = method
    config.store['cf_degree'] = degree

    fits = {}
    for para_idx, pname in enumerate(cnls.ElementsParamNames):
        x, y = _gather_xy(config, para_idx)
        fits[pname] = cf_engine.fit_parameter(x, y, method, degree)
    config.store['cf_fits'] = fits

    _build_results_table(config)
    gui_utils.cnls_plots.update_all_plots(config)


def _on_reset_parameters(config):
    import src.GUI.Utils.progress_modal as _pm
    fits = config.store.get('cf_fits', {})
    if not fits:
        _pm.show_warning_dialog("CF option", "Run 'Fit data' before resetting parameters.")
        return

    for file_name in config.selected_files:
        file_key = os.path.splitext(file_name)[0]
        store = config.store.get(file_key)
        if not store or 'CNLS' not in store:
            continue
        cnls = store['CNLS']
        x0 = float(config.file_values.get(os.path.basename(file_name), 0.0))

        # Normalize each element's Param/Ub/Lb to mutable, length-matched lists.
        for elem in cnls.Elements:
            elem['Param'] = list(elem['Param'])
            ub = list(elem.get('Ub') or [])
            lb = list(elem.get('Lb') or [])
            while len(ub) < len(elem['Param']):
                ub.append(np.inf)
            while len(lb) < len(elem['Param']):
                lb.append(1e-10)
            elem['Ub'], elem['Lb'] = ub, lb

        for para_idx, pname in enumerate(cnls.ElementsParamNames):
            fit = fits.get(pname)
            if not fit or not fit.get('ok'):
                continue
            yhat, ylo, yhi = cf_engine.predict_at(fit, x0)
            if not np.isfinite(yhat):
                continue
            lb, ub = ylo, yhi
            if not (np.isfinite(lb) and np.isfinite(ub) and ub > lb):
                eps = max(abs(yhat) * 1e-6, 1e-12)
                lb, ub = yhat - eps, yhat + eps
            elem_idx, offset = _locate_param(cnls, para_idx)
            if elem_idx is None:
                continue
            cnls.Elements[elem_idx]['Param'][offset] = float(yhat)
            cnls.Elements[elem_idx]['Ub'][offset] = float(ub)
            cnls.Elements[elem_idx]['Lb'][offset] = float(lb)

        try:
            cnls.initialize_elements(change_UBLB=False)
        except Exception as exc:
            print(f"[Warning] CF reset: initialize_elements failed for {file_key}: {exc}")

    # Refresh the editable elements/parameters table. It renders from
    # config.store['Elements']; re-point that at the displayed file's updated
    # circuit (mirrors display_file) and rebuild the input widgets.
    disp = _display_cnls(config)
    if disp is not None and disp.Elements and dpg.does_item_exist("child_window_cnls_elements"):
        config.store['Elements'] = disp.Elements
        try:
            gui_utils.cnls_elements.update_elements(config)
        except Exception as exc:
            print(f"[Warning] CF reset: element table refresh failed: {exc}")

    # Points now sit on the fitted curve; refresh the all-tab plots.
    # The bottom-left data table is intentionally left untouched on reset.
    gui_utils.cnls_plots.update_all_plots(config)


def open_cf_window(config):
    """Open (or re-open) the non-modal CF option window."""
    if dpg.does_item_exist(WINDOW_TAG):
        dpg.delete_item(WINDOW_TAG)

    cf_x = bool(config.store.get('cf_x_index', False))
    method = config.store.get('cf_method', "Polynomial")
    if method not in cf_engine.METHODS:
        method = "Polynomial"
    degree = int(config.store.get('cf_degree', 1))
    category = cf_engine.category_of(method)
    categories = list(cf_engine.CATEGORIES)

    with dpg.window(label="CF option", tag=WINDOW_TAG, modal=False, no_collapse=True,
                    width=616, height=520, pos=(120, 120)):
        dpg.add_checkbox(
            label="x index",
            tag=_XINDEX_TAG,
            default_value=cf_x,
            callback=lambda s, a: _on_xindex_toggle(s, a, config),
        )
        dpg.add_text("All-tab parameter plots use each file's x index (points only) when checked.")
        dpg.add_separator()

        with dpg.group(horizontal=True):
            dpg.add_text("Category")
            dpg.add_combo(
                items=categories,
                tag=_CATEGORY_TAG,
                default_value=category,
                width=130,
                callback=lambda s, a: _on_category_change(s, a, config),
            )
            dpg.add_text("Method")
            dpg.add_combo(
                items=cf_engine.CATEGORIES[category],
                tag=_METHOD_TAG,
                default_value=method,
                width=170,
                callback=lambda s, a: _on_method_change(s, a, config),
            )
            dpg.add_text("Degree", tag=_DEGREE_TEXT_TAG)
            dpg.add_input_int(
                tag=_DEGREE_TAG, default_value=degree, width=90,
                min_value=1, max_value=6, min_clamped=True, max_clamped=True,
            )

        dpg.add_text("", tag=_FORMULA_TAG, wrap=520)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Fit data", tag=_FIT_TAG, callback=lambda: _on_fit_data(config))
            dpg.add_button(label="reset parameters", tag=_RESET_TAG, callback=lambda: _on_reset_parameters(config))

        dpg.add_separator()
        dpg.add_text("Fit results")
        with dpg.child_window(width=-1, height=-1, horizontal_scrollbar=True):
            with dpg.table(tag=_TABLE_TAG, header_row=True, resizable=True,
                           borders_innerH=True, borders_outerH=True,
                           borders_innerV=True, borders_outerV=True,
                           scrollY=True, policy=dpg.mvTable_SizingStretchProp):
                pass

    _update_degree_visibility()
    _update_formula_text()
    _set_gated_enabled(cf_x)
    _build_results_table(config)
