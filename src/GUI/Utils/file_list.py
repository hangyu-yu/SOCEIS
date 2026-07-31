import os
import re
import glob
import copy
import numpy as np
from natsort import natsorted
import dearpygui.dearpygui as dpg
import src.GUI.Utils as gui_utils
from src.Methods.CNLS.Circuit import Circuit


def _normalize_path(path_obj):
    """Handle Windows long path (260+ chars) by adding \\\\?\\ prefix."""
    path_str = str(path_obj)
    if os.name == 'nt' and os.path.isabs(path_str) and not path_str.startswith('\\\\'):
        return '\\\\?' + os.path.sep + os.path.abspath(path_str)
    return path_str


def parse_start_step(text):
    """Parse MATLAB-style 'start:step' (or 'start:step:stop', stop ignored).

    Returns (start, step) as floats, or None if the text cannot be parsed.
    """
    if not isinstance(text, str):
        return None
    parts = [p.strip() for p in text.split(":")]
    if len(parts) not in (2, 3):
        return None
    try:
        start = float(parts[0])
        step = float(parts[1])
    except ValueError:
        return None
    return start, step


def _open_import_progress(total_steps):
    """Thin wrapper: open a progress window for historical data import."""
    import src.GUI.Utils.progress_modal as _pm
    return _pm.open_progress(
        "Data Import",
        "Importing historical data...",
        total_steps,
        window_tag="window_data_import_progress",
    )


def _update_import_progress(progress_ctx, current_step, current_name=""):
    import src.GUI.Utils.progress_modal as _pm
    _pm.update_progress(progress_ctx, current_step, current_name)


def _close_import_progress(progress_ctx):
    import src.GUI.Utils.progress_modal as _pm
    _pm.close_progress(progress_ctx)

def select_files(config, tag):
    """
    Update the selected file paths in the config.
    """
    folder_path_norm = _normalize_path(config.folder_path)
    if os.path.isdir(folder_path_norm):
        # config.file_list = sorted(glob.glob(os.path.join(config.folder_path, f"*{config.file_extensions}")))
        pattern = re.compile(f".*{config.file_extensions}$", re.IGNORECASE)
        config.file_list = natsorted([
            os.path.join(config.folder_path, entry.name)
            for entry in os.scandir(folder_path_norm)
            if entry.is_file() and pattern.search(entry.name)
        ])
        if config.store.get("verbose_logs", False):
            print(f"---- File list from [{tag}]", config.file_list)
        if not config.file_list:
            config.file_list = ['[Error] No file found! Recheck the folder path or file extension, otherwise report the issue.']
    else:
        config.file_list = ['[Error] Folder path not found! Recheck the folder path or report the issue.']

def sync_file_list_checkboxes(config, tag):
    """
    Synchronize checkbox states for an existing file list widget without rebuilding it.
    """
    if not tag or not dpg.does_item_exist(tag):
        return

    selected_set = set(config.selected_files or [])
    for file in config.file_list:
        filename = os.path.basename(file)
        checkbox_tag = f"checkbox_{tag}_{filename}"
        if dpg.does_item_exist(checkbox_tag):
            target_value = filename in selected_set
            try:
                current_value = dpg.get_value(checkbox_tag)
            except Exception:
                current_value = None
            if current_value != target_value:
                dpg.set_value(checkbox_tag, target_value)

def update_selected_files(config, tag=None, force_refresh=False):
    """
    Update the list of selected files in config.selected_files.
    """
    if config.store.get("_file_selection_updating", False):
        return

    config.store["_file_selection_updating"] = True
    try:
        if not 'previous_selected' in config.store:
            config.store['previous_selected'] = []
        previous_selected = (config.store['previous_selected'] or [])
        previous_display = config.display_file
    
        config.selected_files = [
            os.path.basename(file)
            for file in config.file_list
            if dpg.get_value(f"checkbox_{tag}_{os.path.basename(file)}")
        ]

        # Keep current display file if still selected to avoid unnecessary redraw.
        if previous_display in (config.selected_files or []):
            config.display_file = previous_display
        else:
            config.display_file = config.selected_files[0] if config.selected_files else None

        if dpg.does_item_exist("combo_eis_plot_file"):
            dpg.configure_item("combo_eis_plot_file", items=config.selected_files, default_value=config.display_file)
        if dpg.does_item_exist("combo_drt_plot_file"):
            dpg.configure_item("combo_drt_plot_file", items=config.selected_files, default_value=config.display_file)

        # Keep other file-list checkboxes synced without triggering redundant set_value writes.
        sync_file_list_checkboxes(config, "child_window_file_list_eis")
        sync_file_list_checkboxes(config, "child_window_file_list_drt")
        sync_file_list_checkboxes(config, "child_window_file_list_cnls")
        sync_file_list_checkboxes(config, "child_window_file_list_soceis")

        # Nothing changed at all — skip everything unless caller requests refresh.
        selection_changed = previous_selected != list(config.selected_files or [])
        display_changed = previous_display != config.display_file

        config.store['previous_selected'] = config.selected_files

        if not selection_changed and not display_changed and not force_refresh:
            return

        # Update display combos in analysis tabs whenever selection or display changed.
        if dpg.does_item_exist("group_eis_display_file"):
            gui_utils.file_list.update_file_list_and_display(0, 0, config, "combo_eis_plot_file", "group_eis_display_file")
        if dpg.does_item_exist("group_drt_display_file"):
            gui_utils.file_list.update_file_list_and_display(0, 0, config, "combo_drt_plot_file", "group_drt_display_file")
        if dpg.does_item_exist("group_cnls_display_file"):
            gui_utils.file_list.update_file_list_and_display(0, 0, config, "combo_display_file_cnls", "group_cnls_display_file")

        # Rebuild "all" overlay plots only when the selection set itself changed.
        if selection_changed:
            try:
                if dpg.does_item_exist("tab_bar_eis_plot_all"):
                    gui_utils.eis_plots.update_all_plots(config)
                if dpg.does_item_exist("tab_bar_drt_plot_all"):
                    gui_utils.drt_plots.update_all_plots(config)
                if dpg.does_item_exist("tab_bar_cnls_plot_all"):
                    gui_utils.cnls_plots.update_all_plots(config)
            except Exception:
                pass
            # Refresh resistance tables (which list ALL selected files).
            # Only when display_file didn't change to avoid double-update
            # (display_file() already calls table_update when display changes).
            if not display_changed:
                try:
                    if dpg.does_item_exist("tab_eis"):
                        gui_utils.eis_table.table_update(config)
                    if dpg.does_item_exist("tab_drt"):
                        gui_utils.drt_table.table_update(config)
                except Exception:
                    pass

        # Refresh single-file detail panels when display changes or a forced refresh is requested.
        if display_changed or force_refresh:
            try:
                gui_utils.file_list.display_file(
                    None,
                    config.display_file,
                    config,
                    refresh_eis_tab=dpg.does_item_exist("tab_eis"),
                    refresh_drt_tab=dpg.does_item_exist("tab_drt"),
                    refresh_cnls_tab=dpg.does_item_exist("tab_cnls"),
                )
            except Exception:
                pass
    finally:
        config.store["_file_selection_updating"] = False
    
def select_all_files(config, tag=None):
    """
    Select all files in the file list.
    """
    config.store["_file_selection_updating"] = True
    for file in config.file_list:
        checkbox_tag = f"checkbox_{tag}_{os.path.basename(file)}"
        if dpg.does_item_exist(checkbox_tag):
            dpg.set_value(checkbox_tag, True)
    config.store["_file_selection_updating"] = False
    update_selected_files(config, tag)

def unselect_all_files(config, tag=None):
    """
    Unselect all files in the file list.
    """
    config.store["_file_selection_updating"] = True
    for file in config.file_list:
        checkbox_tag = f"checkbox_{tag}_{os.path.basename(file)}"
        if dpg.does_item_exist(checkbox_tag):
            dpg.set_value(checkbox_tag, False)
    config.store["_file_selection_updating"] = False
    update_selected_files(config, tag)

def _sync_selected_files_with_current_list(config):
    """Keep selected files valid after refreshing current folder-based file list."""
    valid_basenames = {os.path.basename(file) for file in config.file_list if "[Error]" not in file}

    normalized_selected = []
    for item in (config.selected_files or []):
        filename = os.path.basename(str(item))
        if filename in valid_basenames and filename not in normalized_selected:
            normalized_selected.append(filename)
    config.selected_files = normalized_selected

    display_candidate = os.path.basename(str(config.display_file)) if config.display_file else None
    if display_candidate in config.selected_files:
        config.display_file = display_candidate
    else:
        config.display_file = config.selected_files[0] if config.selected_files else None

def _open_large_file_select_window(config, tag, EIS=None, CNLS=None):
    """Open a dedicated, larger window for selecting from current available file list."""
    window_tag = f"window_large_file_selector_{tag}"
    list_child_tag = f"child_large_selector_list_{tag}"
    index_input_tag = f"input_large_selector_index_{tag}"
    autofill_input_tag = f"input_large_selector_autofill_{tag}"

    if dpg.does_item_exist(window_tag):
        dpg.delete_item(window_tag)

    # Ensure the list reflects current folder + extension.
    select_files(config, tag)
    current_file_names = [os.path.basename(path) for path in config.file_list if "[Error]" not in path]

    def _compress_one_based_indices(indices):
        ordered = sorted(set(indices))
        if not ordered:
            return ""

        ranges = []
        start = ordered[0]
        prev = ordered[0]
        for idx in ordered[1:]:
            if idx == prev + 1:
                prev = idx
            else:
                ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
                start = idx
                prev = idx
        ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
        return ",".join(ranges)

    def _selected_index_text_from_names(selected_names):
        index_map = {name: i for i, name in enumerate(current_file_names, start=1)}
        selected_indices = [index_map[name] for name in selected_names if name in index_map]
        return _compress_one_based_indices(selected_indices)

    def _update_temp_selected_from_window():
        selected_names = []
        for filename in current_file_names:
            cb_tag = f"checkbox_large_selector_{tag}_{filename}"
            if dpg.does_item_exist(cb_tag) and dpg.get_value(cb_tag):
                selected_names.append(filename)
        dpg.set_item_user_data(window_tag, selected_names)
        if dpg.does_item_exist(index_input_tag):
            dpg.set_value(index_input_tag, _selected_index_text_from_names(selected_names))

    def _on_confirm_add_files():
        _update_temp_selected_from_window()
        selected_names = dpg.get_item_user_data(window_tag) or []

        # Refresh by current folder + extension then apply selected filenames.
        select_files(config, tag)
        current_names = {os.path.basename(path) for path in config.file_list if "[Error]" not in path}
        config.store['previous_selected'] = config.selected_files
        config.selected_files = [name for name in selected_names if name in current_names]
        _sync_selected_files_with_current_list(config)

        # Respect explicit empty confirmation from the large selector.
        if not config.selected_files:
            config.store["_skip_autoselect_first_once"] = True

        # Capture per-file numeric values (all rows) and persist to folder config.
        _persist_file_values()
        config.save_config()

        update_file_list(config, tag, EIS, CNLS)
        # Reuse standard selection callback to update display file and redraw all related plots.
        update_selected_files(config, tag, force_refresh=True)
        dpg.delete_item(window_tag)

    def _apply_index_selection():
        raw_text = dpg.get_value(index_input_tag) if dpg.does_item_exist(index_input_tag) else ""
        if not raw_text:
            for filename in current_file_names:
                cb_tag = f"checkbox_large_selector_{tag}_{filename}"
                if dpg.does_item_exist(cb_tag):
                    dpg.set_value(cb_tag, False)
            _update_temp_selected_from_window()
            return

        chosen_indices = set()
        for token in str(raw_text).split(","):
            part = token.strip()
            if not part:
                continue
            if "-" in part:
                pieces = part.split("-", 1)
                try:
                    start = int(pieces[0].strip())
                    end = int(pieces[1].strip())
                except ValueError:
                    continue
                if start > end:
                    start, end = end, start
                for idx in range(start, end + 1):
                    chosen_indices.add(idx)
            else:
                try:
                    chosen_indices.add(int(part))
                except ValueError:
                    continue

        for one_based_idx, filename in enumerate(current_file_names, start=1):
            cb_tag = f"checkbox_large_selector_{tag}_{filename}"
            if dpg.does_item_exist(cb_tag):
                dpg.set_value(cb_tag, one_based_idx in chosen_indices)

        _update_temp_selected_from_window()

    def _set_all_large_selector(checked, clear_index=False):
        for filename in current_file_names:
            cb_tag = f"checkbox_large_selector_{tag}_{filename}"
            if dpg.does_item_exist(cb_tag):
                dpg.set_value(cb_tag, checked)
        if clear_index and dpg.does_item_exist(index_input_tag):
            dpg.set_value(index_input_tag, "")
        _update_temp_selected_from_window()

    def _apply_auto_fill():
        """Assign start + i*step to checked files in list order (i resets from 0)."""
        raw_text = dpg.get_value(autofill_input_tag) if dpg.does_item_exist(autofill_input_tag) else ""
        spec = parse_start_step(raw_text)
        if spec is None:
            return
        start, step = spec
        i = 0
        for filename in current_file_names:
            cb_tag = f"checkbox_large_selector_{tag}_{filename}"
            val_tag = f"input_large_selector_value_{tag}_{filename}"
            if dpg.does_item_exist(cb_tag) and dpg.get_value(cb_tag):
                if dpg.does_item_exist(val_tag):
                    dpg.set_value(val_tag, start + i * step)
                i += 1

    def _persist_file_values():
        """Read every row's value input into config.file_values (all rows)."""
        for filename in current_file_names:
            val_tag = f"input_large_selector_value_{tag}_{filename}"
            if dpg.does_item_exist(val_tag):
                try:
                    config.file_values[filename] = float(dpg.get_value(val_tag))
                except (TypeError, ValueError):
                    continue

    vp_w = dpg.get_viewport_client_width() if hasattr(dpg, "get_viewport_client_width") else dpg.get_viewport_width()
    vp_h = dpg.get_viewport_client_height() if hasattr(dpg, "get_viewport_client_height") else dpg.get_viewport_height()
    win_width  = max(480, int(vp_w * 0.9))
    win_height = max(360, int(vp_h * 0.9))
    # Bottom panel holds: spacer + index row + value row + select-all row + spacer + separator + confirm row + inner padding
    _bottom_h = 158

    with dpg.window(
        label="Large File Selector",
        tag=window_tag,
        modal=True,
        width=win_width,
        height=win_height,
        no_resize=False,
        no_collapse=True,
        pos=(max(0, (vp_w - win_width) // 2), max(0, (vp_h - win_height) // 2)),
    ):
        dpg.add_text("Select files from current available list, then confirm to apply.")
        dpg.add_separator()
        # ── Column header (fixed, above the scrollable list) ──────────
        with dpg.group(horizontal=True):
            dpg.add_text("x index")
            dpg.add_spacer(width=48)
            dpg.add_text("File")
        dpg.add_separator()
        # ── Scrollable file list ──────────────────────────────────────
        with dpg.child_window(tag=list_child_tag, width=-1, height=-_bottom_h, horizontal_scrollbar=True):
            for filename in current_file_names:
                default_checked = filename in (config.selected_files or [])
                with dpg.group(horizontal=True):
                    dpg.add_input_float(
                        tag=f"input_large_selector_value_{tag}_{filename}",
                        default_value=float(config.file_values.get(filename, 0.0)),
                        width=90,
                        step=0,
                        step_fast=0,
                        format="%.6g",
                    )
                    dpg.add_checkbox(
                        label=filename,
                        tag=f"checkbox_large_selector_{tag}_{filename}",
                        default_value=default_checked,
                        callback=lambda s, a: _update_temp_selected_from_window()
                    )
        # ── Fixed bottom controls panel ───────────────────────────────
        with dpg.child_window(width=-1, height=_bottom_h, no_scrollbar=True, border=True):
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_text("Index")
                dpg.add_input_text(
                    tag=index_input_tag,
                    hint="e.g. 1,3,5-8",
                    width=220,
                    on_enter=True,
                    callback=lambda s, a: _apply_index_selection(),
                )
                dpg.add_button(label="Apply Index", callback=lambda: _apply_index_selection())
            _update_temp_selected_from_window()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Select all", callback=lambda: _set_all_large_selector(True))
                dpg.add_button(label="Unselect all", callback=lambda: _set_all_large_selector(False, clear_index=True))
            with dpg.group(horizontal=True):
                dpg.add_text("Value")
                dpg.add_input_text(
                    tag=autofill_input_tag,
                    hint="e.g. 0:0.2",
                    width=140,
                    on_enter=True,
                    callback=lambda s, a: _apply_auto_fill(),
                )
                dpg.add_button(label="Auto fill", callback=lambda: _apply_auto_fill())
                dpg.add_text("(checked files, start:step)")
            dpg.add_spacer(height=6)
            dpg.add_separator()
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="  Confirm  ", callback=_on_confirm_add_files)
                dpg.add_spacer(width=8)
                dpg.add_button(label="  Cancel  ", callback=lambda: dpg.delete_item(window_tag))


def refresh_open_file_lists_on_extension_change(config, EIS=None, CNLS=None):
    """Refresh file lists in all opened tabs when extension selector changes."""
    source_tag = "child_window_file_list_soceis"
    import_history = EIS is not None and CNLS is not None

    if dpg.does_item_exist(source_tag):
        update_file_list(
            config,
            source_tag,
            EIS,
            CNLS,
            import_history=import_history,
            show_progress=import_history,
            run_alignment=False,
        )

    for tag in [
        "child_window_file_list_eis",
        "child_window_file_list_drt",
        "child_window_file_list_cnls",
    ]:
        if dpg.does_item_exist(tag):
            update_file_list(
                config,
                tag,
                EIS,
                CNLS,
                import_history=False,
                show_progress=False,
                run_alignment=False,
            )

    if dpg.does_item_exist(source_tag):
        try:
            update_selected_files(config, source_tag)
        except Exception:
            pass

def update_file_list(config, tag = None, EIS = None, CNLS = None, import_history=True, show_progress=False, run_alignment=True):
    """
    Update the file list based on the selected extension and default folder path.
    """
    config.file_extensions = dpg.get_value("file_extension_selector")
    select_files(config, tag)
    _sync_selected_files_with_current_list(config)

    # If nothing is selected but valid files exist, auto-select the first file.
    # One-shot opt-out is used when user explicitly confirms an empty selection.
    skip_autoselect_first = bool(config.store.pop("_skip_autoselect_first_once", False))
    valid_files_pre = [f for f in config.file_list if "[Error]" not in f]
    if not config.selected_files and valid_files_pre and not skip_autoselect_first:
        first_name = os.path.basename(valid_files_pre[0])
        config.selected_files = [first_name]
        config.display_file = first_name

    dpg.delete_item(tag, children_only=True)
    first_selected_file = os.path.basename(config.selected_files[0]) if config.selected_files else None

    with dpg.menu_bar(parent=tag):
        with dpg.menu(label="File list"):
            dpg.add_menu_item(label="Select all", callback=lambda: select_all_files(config, tag))
            dpg.add_menu_item(label="Unselect all", callback=lambda: unselect_all_files(config, tag))
            dpg.add_menu_item(label="Open large selector", callback=lambda: _open_large_file_select_window(config, tag, EIS, CNLS))

    for file in config.file_list:
        filename = os.path.basename(file)
        checkbox_tag = f"checkbox_{tag}_{filename}"
        
        # Determine if this file should be checked
        should_check = any(
            os.path.basename(selected_file) == filename 
            for selected_file in config.selected_files
        )
        
        # Add checkbox with proper callback
        with dpg.group(parent=tag, horizontal=True):
            dpg.add_checkbox(
                label=gui_utils.small_functions.string_abbreviation(filename, 38, 38) if tag == "child_window_file_list_soceis" else gui_utils.small_functions.string_abbreviation(filename, 22, 22),
                tag=checkbox_tag,
                default_value=should_check,
                callback=lambda s, a, f=filename: update_selected_files(config, tag)
            )

    if not import_history or EIS is None or CNLS is None:
        if run_alignment:
            file_alignment(config)
        return

    valid_files = valid_files_pre
    progress_ctx = _open_import_progress(len(valid_files)) if show_progress else None

    eis_dir_exists = os.path.isdir(_normalize_path(os.path.join(config.folder_path, "EIS")))
    drt_dir_exists = os.path.isdir(_normalize_path(os.path.join(config.folder_path, "DRT")))
    cnls_dir_exists = os.path.isdir(_normalize_path(os.path.join(config.folder_path, "CNLS")))

    try:
        # Import historical data once per refresh (not once per checkbox row).
        for idx, file in enumerate(valid_files):
            file_name_no_ext = os.path.splitext(os.path.basename(file))[0]
            is_first_selected_file = first_selected_file is not None and os.path.basename(file) == first_selected_file
            _update_import_progress(progress_ctx, idx + 1, os.path.basename(file))

            eis_xlsx = _normalize_path(os.path.join(config.folder_path, "EIS", file_name_no_ext + ".xlsx"))
            drt_xlsx = _normalize_path(os.path.join(config.folder_path, "DRT", file_name_no_ext + ".xlsx"))
            cnls_xlsx = _normalize_path(os.path.join(config.folder_path, "CNLS", file_name_no_ext + ".xlsx"))

            if eis_dir_exists and os.path.exists(eis_xlsx):
                _already_attempted = config.store.get(file_name_no_ext, {}).get('_eis_import_attempted', False)
                _needs_import = (
                    file_name_no_ext not in config.store.keys()
                    or "EIS" not in config.store[file_name_no_ext].keys()
                    or (config.store[file_name_no_ext]['EIS'].raw['Re'] is None and not _already_attempted)
                )
                if _needs_import:
                    config.store[file_name_no_ext] = {}
                    config.store[file_name_no_ext]['EIS'] = copy.deepcopy(EIS)
                    EIS_tmp = config.store[file_name_no_ext]['EIS']
                    EIS_tmp.file_folder = config.folder_path
                    EIS_tmp.filename = os.path.basename(file)
                    EIS_tmp.import_data_EIS()
                    # Mark as attempted so parameter-only files aren't re-imported on every refresh.
                    config.store[file_name_no_ext]['_eis_import_attempted'] = True

                    if is_first_selected_file or ((not config.selected_files) and idx == 0):
                        EIS.filename = os.path.basename(file)
                        EIS.import_data_EIS()
                        print(f"---- EIS data imported from {file} successfully.")

            if drt_dir_exists and os.path.exists(drt_xlsx):
                if file_name_no_ext not in config.store.keys() or "EIS" not in config.store[file_name_no_ext].keys():
                    config.store[file_name_no_ext] = {}
                    config.store[file_name_no_ext]['EIS'] = copy.deepcopy(EIS)
                EIS_tmp = config.store[file_name_no_ext]['EIS']
                EIS_tmp.file_folder = config.folder_path
                EIS_tmp.filename = os.path.basename(file)

                need_drt_import = (
                    config.store.get('beacon_DRT_import', False)
                    or not config.store[file_name_no_ext].get('_drt_loaded', False)
                )
                if need_drt_import:
                    EIS_tmp.import_data_DRT()
                    config.store[file_name_no_ext]['_drt_loaded'] = True

                if is_first_selected_file or ((not config.selected_files) and idx == 0):
                    EIS.file_folder = config.folder_path
                    EIS.filename = os.path.basename(file)
                    EIS.import_data_DRT()
                    print(f"---- DRT data imported from {file} successfully.")
            if cnls_dir_exists and os.path.exists(cnls_xlsx):
                if file_name_no_ext not in config.store.keys():
                    config.store[file_name_no_ext] = {}

                file_data = config.store.get(file_name_no_ext, {})
                try:
                    if "EIS" not in file_data:
                        config.store[file_name_no_ext]['EIS'] = copy.deepcopy(EIS)
                        eis_for_cnls = config.store[file_name_no_ext]['EIS']
                        eis_for_cnls.file_folder = config.folder_path
                        eis_for_cnls.filename = os.path.basename(file)
                        if os.path.exists(drt_xlsx):
                            eis_for_cnls.import_data_DRT()
                        else:
                            eis_for_cnls.import_data_EIS()

                    eis_for_cnls = config.store[file_name_no_ext]['EIS']
                    if eis_for_cnls.tknv_truncated is None and os.path.exists(drt_xlsx):
                        eis_for_cnls.file_folder = config.folder_path
                        eis_for_cnls.filename = os.path.basename(file)
                        eis_for_cnls.import_data_DRT()

                    can_import_cnls = (
                        eis_for_cnls.tknv_truncated is not None
                        and isinstance(eis_for_cnls.tknv_truncated, dict)
                        and "ReIm" in eis_for_cnls.tknv_truncated.keys()
                    )

                    if can_import_cnls and ("CNLS" not in file_data or config.store.get('beacon_DRT_import', False)):
                        config.store[file_name_no_ext]['CNLS'] = copy.deepcopy(
                            Circuit(
                                file_folder=config.folder_path,
                                filename=os.path.basename(file),
                                Elements=None,
                                EIS=eis_for_cnls,
                                data_type='truncated',
                            )
                        )
                        CNLS_tmp = config.store[file_name_no_ext]['CNLS']
                        CNLS_tmp.ImportCircuit()

                        if is_first_selected_file or ((not config.selected_files) and idx == 0):
                            CNLS.file_folder = config.folder_path
                            CNLS.filename = os.path.basename(file)
                            CNLS.ImportCircuit()
                            config.store["Elements"] = CNLS.Elements if CNLS.Elements is not None else {}
                            config.store["segment_constraints"] = CNLS.constraint_type
                            print(f"---- CNLS data imported from {file} successfully.")
                except Exception as e:
                    print(f"[Warning] CNLS data import failed for {file}. Please check the CNLS and EIS data folder in the file. Error details: {e}")

        config.store['beacon_DRT_import'] = False
    finally:
        _close_import_progress(progress_ctx)

    if show_progress:
        import src.GUI.Utils.progress_modal as _pm
        def _raw_is_empty(fname):
            fk = os.path.splitext(fname)[0]
            if fk not in config.store or "EIS" not in config.store[fk]:
                return True
            _f = config.store[fk]["EIS"].raw["f"]
            return _f is None or (hasattr(_f, "__len__") and len(_f) == 0)
        _no_data_files = [f for f in config.selected_files if _raw_is_empty(f)]
        _is_default_dir = os.path.exists(os.path.join(config.folder_path, "requirements.txt"))
        _has_processed_data = os.path.isdir(os.path.join(config.folder_path, "EIS"))
        if _no_data_files and not _is_default_dir and _has_processed_data:
            _pm.show_warning_dialog(
                "Import — Missing Saved Data",
                "The following selected files have no saved EIS/DRT data "
                "and cannot be used until they are processed:\n\n"
                + "\n".join(f"  \u2022 {f}" for f in _no_data_files)
            )

    if run_alignment:
        file_alignment(config)

def display_file(sender, app_data, config, refresh_eis_tab=True, refresh_drt_tab=True, refresh_cnls_tab=True):
    """
    Callback function to display the selected file in the combo box.
    """
    # Update the displayed file name in the GUI
    if sender is not None:
        config.display_file = dpg.get_value(sender)
    else:
        config.display_file = app_data if app_data is not None else None

    # Sync all display-file combo widgets so every tab reflects the new selection
    for _combo_tag in ("combo_eis_plot_file", "combo_drt_plot_file", "combo_display_file_cnls"):
        if dpg.does_item_exist(_combo_tag):
            dpg.configure_item(_combo_tag, default_value=config.display_file)

    EIS_tmp = config.store[os.path.splitext(config.display_file)[0]]['EIS'] if config.display_file and os.path.splitext(config.display_file)[0] in config.store.keys() and 'EIS' in config.store[os.path.splitext(config.display_file)[0]].keys() else None
    
    CNLS_tmp = config.store[os.path.splitext(config.display_file)[0]]['CNLS'] if config.display_file and os.path.splitext(config.display_file)[0] in config.store.keys() and 'CNLS' in config.store[os.path.splitext(config.display_file)[0]].keys() else None

    def _safe_set_value(tag, value):
        if not dpg.does_item_exist(tag):
            return
        try:
            dpg.set_value(tag, value)
        except Exception as e:
            if config.store.get("verbose_logs", False):
                print(f"[Warning] set_value failed for '{tag}': {e}")

    def _safe_configure(tag, **kwargs):
        if not dpg.does_item_exist(tag):
            return
        try:
            dpg.configure_item(tag, **kwargs)
        except Exception as e:
            if config.store.get("verbose_logs", False):
                print(f"[Warning] configure_item failed for '{tag}': {e}")

    # Update EIS data
    try:
        if EIS_tmp is not None:
            # General parameters
            _safe_set_value("CellArea", f"{float(EIS_tmp.parameter['Sample']['CellArea']):.2f}")
            _safe_set_value("n_cell", f"{float(EIS_tmp.parameter['Sample']['n_cell']):.0f}")
            _safe_set_value("instrument_type", EIS_tmp.parameter['Sample']['instrument_type'])
            _safe_set_value("check_box_eis_freq_cut", EIS_tmp.parameter['Preprocessing']['freq_cut'])
            if EIS_tmp.parameter['Preprocessing']['freq_cut']:
                _safe_set_value("text_num_cut_upper", "Upper cut [Hz]:")
                _safe_set_value("text_num_cut_lower", "Lower cut [Hz]:")
                _safe_set_value("num_cut_upper", f"{float(EIS_tmp.parameter['Preprocessing']['num_cut_upper']):.2f}")
                _safe_set_value("num_cut_lower", f"{float(EIS_tmp.parameter['Preprocessing']['num_cut_lower']):.2f}")
            else:
                _safe_set_value("text_num_cut_upper", "Upper cut:")
                _safe_set_value("text_num_cut_lower", "Lower cut:")
                _safe_set_value("num_cut_upper", f"{int(EIS_tmp.parameter['Preprocessing']['num_cut_upper'])}")
                _safe_set_value("num_cut_lower", f"{int(EIS_tmp.parameter['Preprocessing']['num_cut_lower'])}")
            _safe_set_value("sig_threshold", f"{float(EIS_tmp.parameter['RM_significance']['sig_threshold']):.3f}")
            _safe_set_value("kk_threshold", f"{float(EIS_tmp.parameter['KK']['kk_threshold']):.1f}")
            _safe_set_value("rm_significance", EIS_tmp.parameter["RM_significance"]["rm_significance"])
            _safe_set_value("rm_outliers", EIS_tmp.parameter["Rmoutliers"]["Rmoutliers"])
            _safe_set_value("RmNonKK", EIS_tmp.parameter["KK"]["RmNonKK"])

            # KK parameters
            _safe_set_value("nRCmax", f"{float(EIS_tmp.parameter['KK']['nRCmax']):.0f}")
            _safe_set_value("nRC", f"{float(EIS_tmp.parameter['KK']['nRC']):.0f}")
            _safe_set_value("mu_threshold", f"{float(EIS_tmp.parameter['KK']['mu_threshold']):.2f}")
            _safe_set_value("KK_test", EIS_tmp.parameter["KK"]["KK_test"])
            _safe_set_value("KK_type", True if EIS_tmp.parameter["KK"]["KK_type"] == "Mu_criterion" else False)

            # Manual removal parameters
            _safe_set_value("checkbox_manual_remove_batch_points", EIS_tmp.parameter["ManualRemoval"]["enable"])
            _safe_set_value("input_manual_remove_batch_indices", gui_utils.eis_batch_manual.compress_indices([i + 1 for i in EIS_tmp.parameter["ManualRemoval"]["indices"]]))

            # EIS parameters
            _safe_set_value("Smooth_PointsPerDecade", f"{float(EIS_tmp.parameter['Smoothing']['PointsPerDecade']):.0f}")
            _safe_set_value("extrapolation_fmin", f"{float(EIS_tmp.parameter['Extrapolation']['fmin']):.0e}")
            _safe_set_value("extrapolation_fmax", f"{float(EIS_tmp.parameter['Extrapolation']['fmax']):.0e}")
            _safe_set_value("Extrapolation_PointsPerDecade", f"{float(EIS_tmp.parameter['Extrapolation']['PointsPerDecade']):.0f}")
            _safe_set_value("zhit_enable", EIS_tmp.parameter["ZHIT"]["enable"])
            _safe_set_value("zhit_poly_order", f"{float(EIS_tmp.parameter['ZHIT']['poly_order']):.0f}")
            _safe_set_value("zhit_window_frac", f"{float(EIS_tmp.parameter['ZHIT']['window_frac']):.3f}")

            # Enable state
            manual_enable = bool(EIS_tmp.parameter['ManualRemoval']['enable'])
            _safe_configure("num_cut_upper", enabled=not manual_enable)
            _safe_configure("num_cut_lower", enabled=not manual_enable)
            _safe_configure("sig_threshold", enabled=not manual_enable)
            _safe_configure("kk_threshold", enabled=not manual_enable)
            _safe_configure("rm_significance", enabled=not manual_enable)
            _safe_configure("rm_outliers", enabled=not manual_enable)
            _safe_configure("RmNonKK", enabled=not manual_enable)
            _safe_configure("button_manual_cut_single", enabled=not manual_enable)

            _safe_configure("input_manual_remove_batch_indices", enabled=manual_enable)
            _safe_configure("button_manual_cut_batch", enabled=manual_enable)
            _safe_configure("button_manual_cut_batch_reset", enabled=manual_enable)

    except Exception as e:
        print(f"[Warning] setting EIS parameters: {e} for displayed file.")

    # Update DRT parameters
    try:
        if EIS_tmp is not None:
            _safe_set_value('check_box_tknv_pos', EIS_tmp.parameter["DRT"]["tknv_pos"])
            _safe_set_value('input_text_lambda', EIS_tmp.parameter["DRT"]["lambda"])
            _safe_set_value('input_text_min_lambda', EIS_tmp.parameter["LambdaOpt"]["lambda_min"])
            _safe_set_value('input_text_max_lambda', EIS_tmp.parameter["LambdaOpt"]["lambda_max"])
            _safe_set_value('input_text_lambda_points', EIS_tmp.parameter["LambdaOpt"]["n"])
            if dpg.does_item_exist('combo_lambda_target'):
                lambda_target_items = gui_utils.drt_functions.get_lambda_target_items(EIS_tmp)
                _safe_configure('combo_lambda_target', items=lambda_target_items)
                lambda_target = gui_utils.drt_functions.normalize_lambda_target(
                    EIS_tmp.parameter["LambdaOpt"].get("target", "truncated"),
                    EIS_tmp,
                )
                EIS_tmp.parameter["LambdaOpt"]["target"] = lambda_target
                _safe_set_value('combo_lambda_target', lambda_target)
            lambda_mode_optimal = EIS_tmp.parameter["DRT"].get("Lambda_selection", "Manual") == "Optimal"
            _safe_set_value('check_box_lambda_mode', lambda_mode_optimal)
            if dpg.does_item_exist("input_text_lambda"):
                _safe_configure("input_text_lambda", enabled=not lambda_mode_optimal)
                _safe_set_value("input_text_lambda", "Optimal" if lambda_mode_optimal else EIS_tmp.parameter["DRT"]["lambda"])
            if dpg.does_item_exist("text_optimal_lambda") and config.store[os.path.splitext(config.display_file)[0]]['EIS'].lambda_opt:
                _safe_set_value("text_optimal_lambda", f"{float(config.store[os.path.splitext(config.display_file)[0]]['EIS'].lambda_opt):.4e}")
            elif dpg.does_item_exist("text_optimal_lambda"):
                _safe_set_value("text_optimal_lambda", "Non-calculated")
            # RBF-DRT parameters
            rbf_params = EIS_tmp.parameter.get("DRT_RBF", {})
            _safe_set_value('input_text_rbf_lambda', rbf_params.get("lambda", 1e-3))
            _safe_set_value('combo_rbf_type', rbf_params.get("rbf_type", "Gaussian"))
            _safe_set_value('input_text_rbf_coeff', rbf_params.get("coeff", 0.5))
            _safe_set_value('combo_rbf_shape_control', rbf_params.get("shape_control", "FWHM Coefficient"))
            _safe_set_value('combo_rbf_der_used', rbf_params.get("der_used", "1st order"))
            _safe_set_value('combo_rbf_method', rbf_params.get("method", "ridge"))
            _safe_set_value('check_box_rbf_fit_inductance', bool(rbf_params.get("fit_inductance", False)))
    except:
        if dpg.does_item_exist("text_optimal_lambda"):
            dpg.set_value("text_optimal_lambda", "Non-calculated")
    
    # Update the EIS table and plots
    try:
        if refresh_eis_tab and dpg.does_item_exist("tab_eis"):
            gui_utils.eis_table.table_update(config)
            gui_utils.eis_plots.update_single_plots(config)
    except:
        print("------ EIS plots update failed. Please check the EIS data.")
        pass
    
    # Udpate the DRT table and plots
    try:
        if refresh_drt_tab and dpg.does_item_exist("tab_drt"):
            gui_utils.drt_table.table_update(config)
            gui_utils.drt_plots.update_single_plots(config)
    except:
        print("------ DRT plots update failed. Please check the DRT data.")
        pass

    # Update the CNLS table and plots
    try:
        if refresh_cnls_tab and dpg.does_item_exist("tab_cnls"):
            _file_key = os.path.splitext(config.display_file)[0] if config.display_file else None
            _has_cnls = _file_key is not None and _file_key in config.store and 'CNLS' in config.store[_file_key]
            if _has_cnls:
                cnls_data_type = gui_utils.cnls_functions.normalize_cnls_data_type(
                    config.store[_file_key]['CNLS'].data_type
                )
                dpg.configure_item("combo_cnls_data_type", default_value=cnls_data_type)
                config.store[_file_key]['CNLS'].data_type = cnls_data_type
                dpg.configure_item("input_nbr_iters", default_value=config.store[_file_key]['CNLS'].iteration)
                dpg.configure_item("input_nbr_peaks", default_value=len(config.store[_file_key]['CNLS'].f_fixed)) if config.store[_file_key]['CNLS'].f_fixed is not None else 6
                gui_utils.cnls_functions.dynamic_peak_ids(0, 0, config)
                _cnls = config.store[_file_key]['CNLS']
                if dpg.does_item_exist("check_box_cnls_rc_initialization"):
                    dpg.configure_item("check_box_cnls_rc_initialization", default_value=bool(getattr(_cnls, 'RC_fit_switch', False)))
                if dpg.does_item_exist("check_box_cnls_rs_lb_kk"):
                    dpg.configure_item("check_box_cnls_rs_lb_kk", default_value=bool(getattr(_cnls, 'Rs_LB_KK', False)))
                if dpg.does_item_exist("check_box_cnls_rs_lb_drt"):
                    dpg.configure_item("check_box_cnls_rs_lb_drt", default_value=bool(getattr(_cnls, 'Rs_LB_DRT', False)))
                dpg.configure_item("checkbox_cnls_R_percentage",  default_value=_cnls.R_cons is not None)
                dpg.configure_item("checkbox_cnls_Tau_percentage", default_value=_cnls.Tau_cons is not None)
                if dpg.does_item_exist("input_constraints_R_percentage"):
                    dpg.configure_item("input_constraints_R_percentage",  default_value=_cnls.R_cons   if _cnls.R_cons   is not None else 10.0)
                if dpg.does_item_exist("input_constraints_Tau_percentage"):
                    dpg.configure_item("input_constraints_Tau_percentage", default_value=_cnls.Tau_cons if _cnls.Tau_cons is not None else 10.0)

                if config.store["Elements"] is None or config.store["Elements"] == []:
                    config.store["Elements"] = [
                        {'name': 'L1', 'type': 'Inductor', 'Param': [1], 'Ub': [np.inf], 'Lb': [1e-10]},
                        {'name': 'R2', 'type': 'Resistor', 'Param': [1], 'Ub': [np.inf], 'Lb': [1e-10]},
                    ]
                if config.store[_file_key]['CNLS'].Elements is not None:
                    config.store["Elements"] = config.store[_file_key]['CNLS'].Elements

                # Adopt the displayed file's saved topology as the current GUI
                # topology, so a reloaded custom circuit is retained (the selector
                # and fit/load paths read config.store["topology"]).
                config.store["topology"] = getattr(config.store[_file_key]['CNLS'], 'topology', None)
                config.store["_topology_custom"] = bool(config.store["topology"])

                gui_utils.cnls_elements.update_elements(config)
            # Always refresh table + plots so they clear when file has no CNLS data
            gui_utils.cnls_table.table_update(config)
            gui_utils.cnls_plots.update_single_plots(config)
    except:
        print("------ CNLS plots update failed. Please check the CNLS data.")
    # Print the selected file for debugging
    if config.store.get("verbose_logs", False):
        print(f"---- File to plot: {config.display_file}")

def update_file_list_and_display(sender, app_data, config, tag_name, parent_tag):
    if config.display_file is None or config.display_file == "":
        config.display_file = config.selected_files[0] if config.selected_files else None
    dpg.delete_item(tag_name)
    dpg.add_combo(
        parent=parent_tag,
        tag=tag_name,
        default_value = gui_utils.small_functions.string_abbreviation(config.display_file, 17, 17) if config.display_file is not None else None,
        width = -1,
        items=config.selected_files,
        callback=lambda s, a: gui_utils.file_list.display_file(s, a, config)
    )

def step_display_file(config, direction):
    """
    Switch the displayed file to the previous (direction=-1) or next (direction=+1)
    entry in config.selected_files. Clamps at the ends (no wrap). Reuses display_file()
    so every tab's combo, table and plots refresh exactly as if the combo was changed.
    """
    files = list(config.selected_files or [])
    if not files:
        return

    current = config.display_file
    idx = files.index(current) if current in files else 0
    new_idx = idx + direction
    if new_idx < 0 or new_idx >= len(files):
        return

    new_file = files[new_idx]
    if new_file == current:
        return

    display_file(
        None,
        new_file,
        config,
        refresh_eis_tab=dpg.does_item_exist("tab_eis"),
        refresh_drt_tab=dpg.does_item_exist("tab_drt"),
        refresh_cnls_tab=dpg.does_item_exist("tab_cnls"),
    )

def file_alignment(config):
    """
    Align the file list and display file in the GUI.
    """
    # Iterate through the file list and check for alignment
    if '[Error]' not in config.file_list[0]:
        file_list_base_names = [os.path.basename(file) for file in config.file_list]
        file_list_no_ext = {os.path.splitext(n)[0] for n in file_list_base_names}
        verbose = config.store.get("verbose_logs", False)

        if verbose:
            print("-- File alignment check:")

        # Check files in EIS/DRT/CNLS folders for alignment with config.file_list
        for sub in ("EIS", "DRT", "CNLS"):
            sub_folder = os.path.join(config.folder_path, sub)
            if os.path.isdir(sub_folder):
                for existing_file in glob.glob(os.path.join(sub_folder, "*.xlsx")):
                    file_name_no_ext = os.path.splitext(os.path.basename(existing_file))[0]
                    if file_name_no_ext not in file_list_no_ext:
                        if verbose:
                            print(f"[Warning] unaligned file in {sub}: {existing_file}")

        # Ensure all files in config.selected_files exist in the current file list
        aligned_selected_files = []
        for file_name in config.selected_files:
            if file_name in file_list_base_names:
                aligned_selected_files.append(file_name)
            elif verbose:
                print(f"[Warning] unaligned file in selected_files: {file_name}")

        # Update config.selected_files with the aligned list
        config.selected_files = aligned_selected_files

        if verbose:
            print("---- File alignment finished.")
