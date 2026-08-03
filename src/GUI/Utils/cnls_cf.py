"""CNLS curve-fit options with independent settings for each parameter."""
import os

import numpy as np
import dearpygui.dearpygui as dpg

import src.GUI.Utils as gui_utils
import src.GUI.Utils.cnls_curvefit as cf_engine


WINDOW_TAG = "window_cnls_cf"
_XINDEX_TAG = "checkbox_cnls_cf_xindex"
_BATCH_CATEGORY_TAG = "combo_cnls_cf_batch_category"
_BATCH_METHOD_TAG = "combo_cnls_cf_batch_method"
_BATCH_DEGREE_TAG = "input_cnls_cf_batch_degree"
_BATCH_DEGREE_TEXT_TAG = "text_cnls_cf_batch_degree"
_BATCH_CI_TAG = "input_cnls_cf_batch_ci"
_BATCH_FORMULA_TAG = "text_cnls_cf_batch_formula"
_BATCH_APPLY_TAG = "button_cnls_cf_apply_selected"
_FIT_TAG = "button_cnls_cf_fit"
_RESET_TAG = "button_cnls_cf_reset"
_PARAMETERS_TAG = "child_cnls_cf_parameters"
_ACTIVE_ELEMENT_TAG = "combo_cnls_cf_active_element"
_OPEN_SELECTOR_TAG = "button_cnls_cf_open_parameter_selector"
_SELECTOR_WINDOW_TAG = "window_cnls_cf_parameter_selector"
_SELECTOR_LIST_TAG = "child_cnls_cf_parameter_selector_list"
_GATED_TAGS = (
    _BATCH_CATEGORY_TAG, _BATCH_METHOD_TAG, _BATCH_DEGREE_TAG,
    _BATCH_CI_TAG, _BATCH_APPLY_TAG, _FIT_TAG, _RESET_TAG,
)

_DEFAULT_METHOD = "Polynomial"
_DEFAULT_DEGREE = 1
_DEFAULT_CONFIDENCE = 0.95


def _display_cnls(config):
    """Return the displayed file's CNLS circuit, or None."""
    if not config.display_file:
        return None
    store = config.store.get(os.path.splitext(config.display_file)[0])
    return store.get("CNLS") if store else None


def _degree(value):
    try:
        return max(1, min(6, int(value)))
    except (TypeError, ValueError):
        return _DEFAULT_DEGREE


def _confidence(value):
    """Normalize a fractional CI to the supported inclusive range."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_CONFIDENCE
    if not np.isfinite(value):
        return _DEFAULT_CONFIDENCE
    return min(0.9999, max(0.50, value))


def _default_setting():
    return {
        "selected": False,
        "method": _DEFAULT_METHOD,
        "degree": _DEFAULT_DEGREE,
        "confidence_level": _DEFAULT_CONFIDENCE,
    }


def _parameter_settings(config, cnls):
    """Return normalized, index-keyed settings for the displayed circuit."""
    existing = config.store.get("cf_parameter_settings", {})
    if not isinstance(existing, dict):
        existing = {}

    settings = {}
    for para_idx, _ in enumerate(cnls.ElementsParamNames or []):
        raw = existing.get(para_idx, existing.get(str(para_idx), {}))
        raw = raw if isinstance(raw, dict) else {}
        method = raw.get("method", _DEFAULT_METHOD)
        if method not in cf_engine.METHODS:
            method = _DEFAULT_METHOD
        settings[para_idx] = {
            "selected": bool(raw.get("selected", False)),
            "method": method,
            "degree": _degree(raw.get("degree", _DEFAULT_DEGREE)),
            "confidence_level": _confidence(raw.get("confidence_level", _DEFAULT_CONFIDENCE)),
        }

    config.store["cf_parameter_settings"] = settings
    fits = config.store.get("cf_fits", {})
    if isinstance(fits, dict):
        # Ignore pre-per-parameter fit records keyed by display name and remove
        # fits for parameters that have been deselected or no longer exist.
        config.store["cf_fits"] = {
            idx: fit for idx, fit in fits.items()
            if isinstance(idx, int) and idx in settings and settings[idx]["selected"]
        }
    else:
        config.store["cf_fits"] = {}
    return settings


def _element_labels(cnls):
    """Return labels for the circuit-element switcher."""
    labels = []
    for idx, element in enumerate(cnls.Elements or []):
        labels.append(str(element.get("name") or f"Element {idx + 1}"))
    return labels


def _active_element_index(config, cnls):
    """Return a valid active element index for the displayed circuit."""
    count = len(cnls.Elements or [])
    if count == 0:
        return None
    try:
        idx = int(config.store.get("cf_active_element_index", 0))
    except (TypeError, ValueError):
        idx = 0
    idx = min(max(0, idx), count - 1)
    config.store["cf_active_element_index"] = idx
    return idx


def _gather_xy(config, para_idx):
    """Collect one parameter's x-index/value pairs across selected files."""
    xs, ys = [], []
    for file_name in config.selected_files:
        store = config.store.get(os.path.splitext(file_name)[0])
        cnls = store.get("CNLS") if store else None
        if cnls is None or cnls.ElementsParamValues is None:
            continue
        if para_idx >= len(cnls.ElementsParamValues):
            continue
        try:
            ys.append(float(cnls.ElementsParamValues[para_idx]))
            xs.append(float(config.file_values.get(os.path.basename(file_name), 0.0)))
        except (TypeError, ValueError):
            continue
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def _locate_param(cnls, para_idx):
    """Map a flat parameter index to (element index, element offset)."""
    for elem_idx, (start, end) in enumerate(zip(cnls.ElementsStartIndex, cnls.ElementsEndIndex)):
        if start <= para_idx <= end:
            return elem_idx, para_idx - start
    return None, None


def _fit_text(fit):
    if not fit:
        return "Fit result: not fitted"
    if not fit.get("ok"):
        return f"Fit result: {fit.get('message', 'fit failed')}"
    return f"Fit result: R² = {fit['r2']:.4f}; {cf_engine.equation_string(fit)}"


def _invalidate_fit(config, para_idx):
    fits = config.store.get("cf_fits", {})
    if isinstance(fits, dict):
        fits.pop(para_idx, None)


def _set_gated_enabled(enabled):
    for tag in _GATED_TAGS:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, enabled=enabled)


def _update_batch_degree_visibility():
    show = dpg.does_item_exist(_BATCH_METHOD_TAG) and dpg.get_value(_BATCH_METHOD_TAG) == "Polynomial"
    for tag in (_BATCH_DEGREE_TEXT_TAG, _BATCH_DEGREE_TAG):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=show)


def _update_batch_formula(method=None):
    if not dpg.does_item_exist(_BATCH_FORMULA_TAG):
        return
    if method is None:
        method = dpg.get_value(_BATCH_METHOD_TAG) if dpg.does_item_exist(_BATCH_METHOD_TAG) else _DEFAULT_METHOD
    dpg.set_value(_BATCH_FORMULA_TAG, f"Formula:  {cf_engine.formula_of(method)}")


def _refresh_cards_and_plots(config):
    _build_parameter_cards(config)
    gui_utils.cnls_plots.update_all_plots(config)


def _on_xindex_toggle(sender, app_data, config):
    config.store["cf_x_index"] = bool(app_data)
    _set_gated_enabled(bool(app_data))
    _refresh_cards_and_plots(config)


def _on_batch_category(sender, app_data, config):
    methods = cf_engine.CATEGORIES.get(app_data, [_DEFAULT_METHOD])
    dpg.configure_item(_BATCH_METHOD_TAG, items=methods)
    dpg.set_value(_BATCH_METHOD_TAG, methods[0])
    config.store["cf_batch_method"] = methods[0]
    _update_batch_degree_visibility()
    _update_batch_formula(methods[0])


def _on_batch_method(sender, app_data, config):
    config.store["cf_batch_method"] = app_data
    _update_batch_degree_visibility()
    _update_batch_formula(app_data)


def _on_apply_to_selected(config):
    cnls = _display_cnls(config)
    if cnls is None:
        return
    settings = _parameter_settings(config, cnls)
    method = dpg.get_value(_BATCH_METHOD_TAG)
    degree = _degree(dpg.get_value(_BATCH_DEGREE_TAG))
    confidence = _confidence(float(dpg.get_value(_BATCH_CI_TAG)) / 100.0)
    changed = False
    for para_idx, setting in settings.items():
        if not setting["selected"]:
            continue
        setting.update(method=method, degree=degree, confidence_level=confidence)
        _invalidate_fit(config, para_idx)
        changed = True
    if changed:
        _refresh_cards_and_plots(config)


def _on_active_element(sender, app_data, user_data):
    config, label_to_index = user_data
    config.store["cf_active_element_index"] = label_to_index.get(app_data, 0)
    _build_parameter_cards(config)


def _on_set_all_parameters(config, selected):
    """Select or unselect every parameter and invalidate the affected fits."""
    cnls = _display_cnls(config)
    if cnls is None:
        return
    settings = _parameter_settings(config, cnls)
    for setting in settings.values():
        setting["selected"] = selected
    config.store["cf_fits"] = {}
    _refresh_cards_and_plots(config)
    _build_parameter_selector(config)


def _open_parameter_selector(config):
    cnls = _display_cnls(config)
    if cnls is None:
        return
    if dpg.does_item_exist(_SELECTOR_WINDOW_TAG):
        dpg.delete_item(_SELECTOR_WINDOW_TAG)
    with dpg.window(label="Select parameters", tag=_SELECTOR_WINDOW_TAG, modal=False,
                    no_collapse=True, width=360, height=520, pos=(170, 170)):
        with dpg.group(horizontal=True):
            dpg.add_button(label="Select all", callback=lambda: _on_set_all_parameters(config, True))
            dpg.add_button(label="Unselect all", callback=lambda: _on_set_all_parameters(config, False))
            dpg.add_button(label="Close", callback=lambda: dpg.delete_item(_SELECTOR_WINDOW_TAG))
        dpg.add_separator()
        with dpg.child_window(tag=_SELECTOR_LIST_TAG, width=-1, height=-1):
            pass
    _build_parameter_selector(config)


def _build_parameter_selector(config):
    if not dpg.does_item_exist(_SELECTOR_LIST_TAG):
        return
    dpg.delete_item(_SELECTOR_LIST_TAG, children_only=True)
    cnls = _display_cnls(config)
    if cnls is None:
        return
    settings = _parameter_settings(config, cnls)
    for para_idx, pname in enumerate(cnls.ElementsParamNames or []):
        dpg.add_checkbox(
            label=pname, parent=_SELECTOR_LIST_TAG, default_value=settings[para_idx]["selected"],
            callback=_on_parameter_selected, user_data=(config, para_idx),
        )


def _on_parameter_selected(sender, app_data, user_data):
    config, para_idx = user_data
    cnls = _display_cnls(config)
    if cnls is None:
        return
    settings = _parameter_settings(config, cnls)
    settings[para_idx]["selected"] = bool(app_data)
    _invalidate_fit(config, para_idx)
    _refresh_cards_and_plots(config)


def _on_parameter_category(sender, app_data, user_data):
    config, para_idx = user_data
    cnls = _display_cnls(config)
    if cnls is None:
        return
    methods = cf_engine.CATEGORIES.get(app_data, [_DEFAULT_METHOD])
    settings = _parameter_settings(config, cnls)
    settings[para_idx]["method"] = methods[0]
    _invalidate_fit(config, para_idx)
    _refresh_cards_and_plots(config)


def _on_parameter_method(sender, app_data, user_data):
    config, para_idx = user_data
    cnls = _display_cnls(config)
    if cnls is None:
        return
    settings = _parameter_settings(config, cnls)
    settings[para_idx]["method"] = app_data if app_data in cf_engine.METHODS else _DEFAULT_METHOD
    _invalidate_fit(config, para_idx)
    _refresh_cards_and_plots(config)


def _on_parameter_degree(sender, app_data, user_data):
    config, para_idx = user_data
    cnls = _display_cnls(config)
    if cnls is None:
        return
    settings = _parameter_settings(config, cnls)
    settings[para_idx]["degree"] = _degree(app_data)
    _invalidate_fit(config, para_idx)
    _refresh_cards_and_plots(config)


def _on_parameter_ci(sender, app_data, user_data):
    """Validate and commit one parameter's CI after editing has finished."""
    config, para_idx = user_data
    cnls = _display_cnls(config)
    if cnls is None:
        return
    settings = _parameter_settings(config, cnls)
    settings[para_idx]["confidence_level"] = _confidence(float(app_data) / 100.0)
    _invalidate_fit(config, para_idx)
    _refresh_cards_and_plots(config)


def _on_parameter_ci_deactivated(sender, app_data, user_data):
    """Commit the CI when its input loses focus after an edit."""
    config, para_idx, input_tag = user_data
    if dpg.does_item_exist(input_tag):
        _on_parameter_ci(input_tag, dpg.get_value(input_tag), (config, para_idx))


def _build_parameter_cards(config):
    if not dpg.does_item_exist(_PARAMETERS_TAG):
        return
    dpg.delete_item(_PARAMETERS_TAG, children_only=True)
    cnls = _display_cnls(config)
    if cnls is None or not cnls.ElementsParamNames:
        dpg.add_text("No displayed file with CNLS parameters.", parent=_PARAMETERS_TAG)
        return

    settings = _parameter_settings(config, cnls)
    fits = config.store.get("cf_fits", {})
    enabled = bool(config.store.get("cf_x_index", False))
    active_element_idx = _active_element_index(config, cnls)
    if active_element_idx is None:
        return
    if (active_element_idx >= len(cnls.ElementsStartIndex)
            or active_element_idx >= len(cnls.ElementsEndIndex)):
        return
    start_idx = max(0, cnls.ElementsStartIndex[active_element_idx])
    end_idx = min(cnls.ElementsEndIndex[active_element_idx], len(cnls.ElementsParamNames) - 1)
    # Show every parameter that belongs to the selected circuit element: RC
    # yields R/tau, RQ yields its three values, and larger elements show all of
    # their associated parameters in the scrollable workspace.
    for para_idx in range(start_idx, end_idx + 1):
        pname = cnls.ElementsParamNames[para_idx]
        setting = settings[para_idx]
        category = cf_engine.category_of(setting["method"])
        with dpg.child_window(parent=_PARAMETERS_TAG, height=149, border=True):
            with dpg.group(horizontal=True):
                # Top-aligned left column: selection and identity only.
                with dpg.child_window(width=155, height=130, border=False):
                    with dpg.group(horizontal=True):
                        dpg.add_checkbox(default_value=setting["selected"],
                                         callback=_on_parameter_selected, user_data=(config, para_idx))
                        dpg.add_text(pname, wrap=118)

                # Right column: four compact rows of independent configuration.
                with dpg.child_window(width=-1, height=130, border=False):
                    with dpg.group(horizontal=True):
                        dpg.add_text("Method")
                        dpg.add_combo(
                            items=list(cf_engine.CATEGORIES), default_value=category,
                            width=120, enabled=enabled, callback=_on_parameter_category,
                            user_data=(config, para_idx),
                        )
                        dpg.add_combo(
                            items=cf_engine.CATEGORIES[category], default_value=setting["method"],
                            width=135, enabled=enabled, callback=_on_parameter_method,
                            user_data=(config, para_idx),
                        )
                    with dpg.group(horizontal=True):
                        dpg.add_text("Degree")
                        dpg.add_input_int(
                            default_value=setting["degree"], width=100, min_value=1, max_value=6,
                            min_clamped=True, max_clamped=True,
                            enabled=enabled and setting["method"] == "Polynomial",
                            callback=_on_parameter_degree, user_data=(config, para_idx),
                        )
                        if setting["method"] != "Polynomial":
                            dpg.add_text("(Polynomial only)")
                    with dpg.group(horizontal=True):
                        dpg.add_text("CI (%)")
                        ci_tag = f"input_cnls_cf_parameter_ci_{para_idx}"
                        ci_handler_tag = f"handler_cnls_cf_parameter_ci_{para_idx}"
                        if dpg.does_item_exist(ci_handler_tag):
                            dpg.delete_item(ci_handler_tag)
                        dpg.add_input_float(
                            tag=ci_tag, default_value=setting["confidence_level"] * 100.0,
                            width=100, format="%.2f", enabled=enabled,
                        )
                        with dpg.item_handler_registry(tag=ci_handler_tag):
                            dpg.add_item_deactivated_after_edit_handler(
                                callback=_on_parameter_ci_deactivated,
                                user_data=(config, para_idx, ci_tag),
                            )
                        dpg.bind_item_handler_registry(ci_tag, ci_handler_tag)
                    dpg.add_text(_fit_text(fits.get(para_idx)), wrap=500)


def _on_fit_data(config):
    import src.GUI.Utils.progress_modal as progress_modal

    cnls = _display_cnls(config)
    if cnls is None or not cnls.ElementsParamNames:
        progress_modal.show_warning_dialog("CF option", "No displayed file with CNLS parameters to fit.")
        return
    settings = _parameter_settings(config, cnls)
    selected = [idx for idx, setting in settings.items() if setting["selected"]]
    if not selected:
        progress_modal.show_warning_dialog("CF option", "Select at least one parameter before fitting.")
        return

    fits = {}
    for para_idx in selected:
        setting = settings[para_idx]
        x, y = _gather_xy(config, para_idx)
        fits[para_idx] = cf_engine.fit_parameter(
            x, y, setting["method"], setting["degree"], setting["confidence_level"],
        )
    config.store["cf_fits"] = fits
    _refresh_cards_and_plots(config)


def _on_reset_parameters(config):
    import src.GUI.Utils.progress_modal as progress_modal

    cnls_display = _display_cnls(config)
    if cnls_display is None:
        progress_modal.show_warning_dialog("CF option", "No displayed file with CNLS parameters to reset.")
        return
    settings = _parameter_settings(config, cnls_display)
    fits = config.store.get("cf_fits", {})
    selected_fits = [idx for idx, setting in settings.items()
                     if setting["selected"] and fits.get(idx, {}).get("ok")]
    if not selected_fits:
        progress_modal.show_warning_dialog("CF option", "Fit at least one selected parameter before resetting.")
        return

    for file_name in config.selected_files:
        file_key = os.path.splitext(file_name)[0]
        store = config.store.get(file_key)
        cnls = store.get("CNLS") if store else None
        if cnls is None:
            continue
        x0 = float(config.file_values.get(os.path.basename(file_name), 0.0))

        for elem in cnls.Elements:
            elem["Param"] = list(elem["Param"])
            ub, lb = list(elem.get("Ub") or []), list(elem.get("Lb") or [])
            while len(ub) < len(elem["Param"]):
                ub.append(np.inf)
            while len(lb) < len(elem["Param"]):
                lb.append(1e-10)
            elem["Ub"], elem["Lb"] = ub, lb

        for para_idx in selected_fits:
            yhat, ylo, yhi = cf_engine.predict_at(fits[para_idx], x0)
            if not np.isfinite(yhat):
                continue
            lb, ub = ylo, yhi
            if not (np.isfinite(lb) and np.isfinite(ub) and ub > lb):
                eps = max(abs(yhat) * 1e-6, 1e-12)
                lb, ub = yhat - eps, yhat + eps
            elem_idx, offset = _locate_param(cnls, para_idx)
            if elem_idx is None:
                continue
            cnls.Elements[elem_idx]["Param"][offset] = float(yhat)
            cnls.Elements[elem_idx]["Ub"][offset] = float(ub)
            cnls.Elements[elem_idx]["Lb"][offset] = float(lb)

        # Do not call initialize_elements here.  That method rebuilds
        # ElementsParamValues from Elements['Param']; the all-tab plots use
        # ElementsParamValues as the last completed CNLS fit, so rebuilding it
        # would incorrectly move the plotted points before a new CNLS fit.
        # initialize_parameters() invokes initialize_elements immediately before
        # the next CNLS run, at which point these seeds and bounds take effect.

    display = _display_cnls(config)
    if display is not None and display.Elements and dpg.does_item_exist("child_window_cnls_elements"):
        config.store["Elements"] = display.Elements
        try:
            gui_utils.cnls_elements.update_elements(config)
        except Exception as exc:
            print(f"[Warning] CF reset: element table refresh failed: {exc}")
    # Refresh editable seeds, but keep all-tab points at the last CNLS fit.
    _refresh_cards_and_plots(config)


def open_cf_window(config):
    """Open (or rebuild) the non-modal per-parameter CF option window."""
    if dpg.does_item_exist(WINDOW_TAG):
        dpg.delete_item(WINDOW_TAG)

    cf_x = bool(config.store.get("cf_x_index", False))
    method = config.store.get("cf_batch_method", config.store.get("cf_method", _DEFAULT_METHOD))
    if method not in cf_engine.METHODS:
        method = _DEFAULT_METHOD
    degree = _degree(config.store.get("cf_batch_degree", config.store.get("cf_degree", _DEFAULT_DEGREE)))
    confidence = _confidence(config.store.get("cf_batch_confidence_level", _DEFAULT_CONFIDENCE))
    category = cf_engine.category_of(method)
    cnls = _display_cnls(config)
    labels = _element_labels(cnls) if cnls is not None else []
    label_to_index = {label: idx for idx, label in enumerate(labels)}
    active_idx = _active_element_index(config, cnls) if cnls is not None else None
    active_label = labels[active_idx] if active_idx is not None else ""

    with dpg.window(label="CF option", tag=WINDOW_TAG, modal=False, no_collapse=True,
                    width=738, height=710, pos=(120, 120)):
        dpg.add_checkbox(
            label="x index", tag=_XINDEX_TAG, default_value=cf_x,
            callback=lambda s, a: _on_xindex_toggle(s, a, config),
        )
        dpg.add_text("Enable x index to configure and fit parameter trends.")
        dpg.add_separator()
        dpg.add_text("Batch settings (apply only to checked parameters)")
        with dpg.group(horizontal=True):
            dpg.add_combo(
                items=list(cf_engine.CATEGORIES), tag=_BATCH_CATEGORY_TAG,
                default_value=category, width=125,
                callback=lambda s, a: _on_batch_category(s, a, config),
            )
            dpg.add_combo(
                items=cf_engine.CATEGORIES[category], tag=_BATCH_METHOD_TAG,
                default_value=method, width=135,
                callback=lambda s, a: _on_batch_method(s, a, config),
            )
            dpg.add_text("Degree", tag=_BATCH_DEGREE_TEXT_TAG)
            dpg.add_input_int(
                tag=_BATCH_DEGREE_TAG, default_value=degree, width=70,
                min_value=1, max_value=6, min_clamped=True, max_clamped=True,
            )
            dpg.add_text("CI (%)")
            dpg.add_input_float(
                tag=_BATCH_CI_TAG, default_value=confidence * 100.0, width=120,
                min_value=50.0, max_value=99.99, min_clamped=True, max_clamped=True,
                format="%.2f",
            )
            dpg.add_button(label="Apply to selected", tag=_BATCH_APPLY_TAG,
                           callback=lambda: _on_apply_to_selected(config))
        dpg.add_text("", tag=_BATCH_FORMULA_TAG, wrap=680)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Fit data", tag=_FIT_TAG, callback=lambda: _on_fit_data(config))
            dpg.add_button(label="reset parameters", tag=_RESET_TAG,
                           callback=lambda: _on_reset_parameters(config))
        dpg.add_separator()
        dpg.add_text("Current element")
        with dpg.group(horizontal=True):
            dpg.add_combo(
                items=labels, tag=_ACTIVE_ELEMENT_TAG, default_value=active_label,
                width=260, callback=_on_active_element, user_data=(config, label_to_index),
            )
            dpg.add_button(label="Select parameters...", tag=_OPEN_SELECTOR_TAG,
                           callback=lambda: _open_parameter_selector(config))
        with dpg.child_window(tag=_PARAMETERS_TAG, width=-1, height=-1,
                              horizontal_scrollbar=False):
            pass

    _update_batch_degree_visibility()
    _update_batch_formula()
    _set_gated_enabled(cf_x)
    _build_parameter_cards(config)
