import os
import copy
import numpy as np
import pandas as pd
import src.GUI.Utils as gui_utils
import src.GUI.Utils.progress_modal as _pm
import src.Methods.CNLS.Utils as CNLS_fn
import dearpygui.dearpygui as dpg

# Callback function to handle the options
def update_child_window_size():
    """
    Update the size of the child window based on the viewport size.
    """
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()

    def safe_configure(tag, **kwargs):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, **kwargs)
    
    # Set the width and height of the child window
    safe_configure("child_window_file_list_cnls", width=int(viewport_width * 0.45), height=int(viewport_height * 0.15))
    safe_configure("child_window_parameter_cnls", width=int(viewport_width * 0.45), height=int(viewport_height * 0.35))
    safe_configure("child_window_cnls_buttons", width=int(viewport_width * 0.45), height=int(viewport_height * 0.082))
    safe_configure("child_window_cnls_data", width=int(viewport_width * 0.45), height=-1)
    safe_configure("child_window_cnls_elements", width=int(viewport_width * 0.3), height=-1)
    safe_configure("child_window_cnls_plot", width=-1, height=-1)
    safe_configure("child_window_cnls_parameters", width=-1, height=-1)
    safe_configure("Button_cnls_cnls_fit", width=int(viewport_width*0.1))
    safe_configure("Button_cnls_load_parameters", width=int(viewport_width*0.1))
    safe_configure("Button_cnls_initialize_parameters", width=int(viewport_width*0.1))
    safe_configure("Button_Save_CNLS", width=-1)

def _initialization_cnls(config, CNLS):
    """Initialize CNLS for each selected file that has processed EIS data.
    Returns a list of filenames that were skipped (no EIS data in store).
    """
    skipped = []
    for file_name in config.selected_files:
        file_name_no_ext = os.path.splitext(file_name)[0]
        if file_name_no_ext not in config.store:
            skipped.append(file_name)
        elif 'CNLS' not in config.store[file_name_no_ext]:
            config.store[file_name_no_ext]['CNLS'] = copy.deepcopy(CNLS)
            CNLS_tmp = config.store[file_name_no_ext]['CNLS']
            CNLS_tmp.file_folder = config.folder_path
            CNLS_tmp.filename = os.path.basename(file_name)
            print(f"---- CNLS data initialized from {file_name} successfully.")
    return skipped

def rs_lb_kk_callback(sender, app_data, config):
    """Handle Rs_LB_KK checkbox: when enabled, disable Rs_LB_DRT."""
    if app_data:
        dpg.set_value("check_box_cnls_rs_lb_drt", False)

def rs_lb_drt_callback(sender, app_data, config):
    """Handle Rs_LB_DRT checkbox: when enabled, disable Rs_LB_KK."""
    if app_data:
        dpg.set_value("check_box_cnls_rs_lb_kk", False)

def plot_cnls_tau_callback(sender, app_data, config):
    num_peaks = range(dpg.get_value("input_nbr_peaks"))
    for i in num_peaks:
        if dpg.get_value('check_box_cnls_tau'):
            dpg.configure_item(f"input_peak_{i}", default_value=gui_utils.cnls_functions._peak_value_set(config, num_peaks, i), format="%.3e")
        else:
            dpg.configure_item(f"input_peak_{i}", default_value=gui_utils.cnls_functions._peak_value_set(config, num_peaks, i), format="%.3f")
    dpg.configure_item(f"cnls_text_peak_{num_peaks[0]}", default_value="High f [Hz]" if not dpg.get_value('check_box_cnls_tau') else "Low tau [s]")
    dpg.configure_item(f"cnls_text_peak_{num_peaks[-1]}", default_value="Low f [Hz]" if not dpg.get_value('check_box_cnls_tau') else "High tau [s]")
    gui_utils.cnls_plots.update_single_plots(config)

def RC_initialization_callback(sender, app_data, config):
    # Check if there are Randle elements
    has_randle = any('Randle' in element.get('type', '') for element in config.store.get('Elements', []))
    
    if has_randle:
        # Disable RC initialization if Randle elements exist
        dpg.configure_item("check_box_cnls_rc_initialization", value=False)
        print("[Warning] RC initialization is disabled because Randle elements are present in the circuit.")
        config.store['RC_fit_switch'] = False
    else:
        # Allow RC initialization only without Randle elements
        if dpg.get_value("check_box_cnls_rc_initialization"):
            config.store['RC_fit_switch'] = True
        else:
            config.store['RC_fit_switch'] = False


def fix_all_plots_callback(sender, app_data, config):
    """Update fixed-plot mode and refresh CNLS plots immediately."""
    config.fix_all_plots_CNLS = app_data
    try:
        gui_utils.cnls_plots.update_all_plots(config)
    except Exception as e:
        print(f"[Warning] CNLS plot refresh failed after toggling Fix all plots: {e}")

# Main tab function for EIS
def gui_tab_cnls(config, EIS, CNLS):
    config.save_config()

    # Fast path: if CNLS tab already exists, just switch to it and avoid expensive rebuild.
    if dpg.does_item_exist("tab_cnls"):
        # Run init to pick up any newly-selected files and warn about those without data.
        _skipped = _initialization_cnls(config, CNLS)
        if _skipped:
            _pm.show_warning_dialog(
                "CNLS — Missing Data",
                "The following selected files have no EIS/DRT processed data "
                "and will be skipped in CNLS fitting:\n\n"
                + "\n".join(f"  • {f}" for f in _skipped)
            )
        if dpg.does_item_exist("tab_bar_main"):
            dpg.set_value("tab_bar_main", "tab_cnls")
        try:
            gui_utils.file_list.display_file(
                None,
                config.display_file,
                config,
                refresh_eis_tab=False,
                refresh_drt_tab=False,
                refresh_cnls_tab=True,
            )
        except Exception:
            pass
        update_child_window_size()
        return

    if dpg.does_item_exist("tab_cnls"):
        dpg.delete_item("tab_cnls", children_only=False)  # Clear the tab content if it exists
    # Initialize the configuration
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()

    _skipped = _initialization_cnls(config, CNLS)
    if _skipped:
        _pm.show_warning_dialog(
            "CNLS — Missing Data",
            "The following selected files have no EIS/DRT processed data "
            "and will be skipped in CNLS fitting:\n\n"
            + "\n".join(f"  \u2022 {f}" for f in _skipped)
        )

    # Ensure display_file points to a file with valid CNLS data before building the tab body.
    # If no valid file exists, show an error and abort tab creation.
    _valid_display = next(
        (_f for _f in config.selected_files
         if os.path.splitext(_f)[0] in config.store and 'CNLS' in config.store[os.path.splitext(_f)[0]]),
        None
    )
    if _valid_display is None:
        _pm.show_error_dialog(
            "CNLS — No Data",
            "None of the selected files have processed EIS/DRT data.\n"
            "Please import and process the data first before opening CNLS."
        )
        return
    config.display_file = _valid_display

    # Set the theme for different widgets
    with dpg.theme() as blue_button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (15, 86, 135, 255))  # Background color (blue)
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255, 255))  # Text color (white)

    with dpg.tab(label="CNLS", tag="tab_cnls", parent="tab_bar_main"):
        with dpg.group(horizontal=True):
            with dpg.group():
                # Window for file list
                with dpg.child_window(width=int(viewport_width * 0.45), height=int(viewport_height*0.15), horizontal_scrollbar=True, menubar=True, tag="child_window_file_list_cnls"):
                    gui_utils.file_list.update_file_list(
                        config,
                        "child_window_file_list_cnls",
                        EIS,
                        CNLS,
                        import_history=False,
                        show_progress=False,
                        run_alignment=False,
                    )

                # Window for the parameters
                with dpg.child_window(width=int(viewport_width * 0.45), height=int(viewport_height * 0.35), horizontal_scrollbar=True, menubar=True, tag="child_window_parameter_cnls"):
                    with dpg.menu_bar(parent="child_window_parameter_cnls", tag="menu_cnls_parameters"):
                        with dpg.menu(label="Parameters"):
                            dpg.add_checkbox(
                                label="Fix all plots",
                                callback=lambda s, a: fix_all_plots_callback(s, a, config),
                            )
                            dpg.add_checkbox(
                                tag="check_box_cnls_tau",
                                label="x-tau",
                                default_value = False,
                                callback=lambda sender, app_data: plot_cnls_tau_callback(sender, app_data, config),
                            )
                            dpg.add_checkbox(
                                tag="check_box_cnls_rc_initialization",
                                label="RC initilization",
                                default_value = config.store[os.path.splitext(config.display_file)[0]]['CNLS'].RC_fit_switch if gui_utils.cnls_functions._file_existence_check(config) and config.store[os.path.splitext(config.display_file)[0]]['CNLS'].RC_fit_switch is not None else False,
                                callback=lambda sender, app_data: RC_initialization_callback(sender, app_data, config),
                            )
                            dpg.add_checkbox(
                                tag="check_box_cnls_rs_lb_kk",
                                label="Rs_LB_KK",
                                default_value = bool(getattr(config.store[os.path.splitext(config.display_file)[0]]['CNLS'], 'Rs_LB_KK', False)) if gui_utils.cnls_functions._file_existence_check(config) else False,
                                callback=lambda sender, app_data: rs_lb_kk_callback(sender, app_data, config),
                            )
                            dpg.add_checkbox(
                                tag="check_box_cnls_rs_lb_drt",
                                label="Rs_LB_DRT",
                                default_value = bool(getattr(config.store[os.path.splitext(config.display_file)[0]]['CNLS'], 'Rs_LB_DRT', False)) if gui_utils.cnls_functions._file_existence_check(config) else False,
                                callback=lambda sender, app_data: rs_lb_drt_callback(sender, app_data, config),
                            )
                            dpg.add_menu_item(
                                label="CF option",
                                callback=lambda s, a: gui_utils.cnls_cf.open_cf_window(config),
                            )
                        with dpg.menu(label="Add elements"):
                            dpg.add_menu_item(
                                label="Selector",
                                callback=lambda s, a: gui_utils.cnls_functions.open_selector_window(s, a, config)
                            )
                            dpg.add_separator()
                            for header, element in config.store['element_list'].items():
                                dpg.add_menu_item(
                                    label=f"Add {header}",
                                    callback=lambda s, a: gui_utils.cnls_elements.add_element(s, a, config)
                                )
                        gui_utils.cnls_elements.menu_remove_elements(config)
                    
                    # CNLS elements and parameter tables
                    with dpg.group(horizontal=True):
                        with dpg.child_window(width=int(viewport_width*0.3), height=-1, horizontal_scrollbar=True, menubar=False, no_scrollbar= False, tag="child_window_cnls_elements", border=False):
                            gui_utils.cnls_elements.update_elements(config)

                        # Window for the CNLS parameters
                        with dpg.child_window(width=-1, height=-1, border=False, horizontal_scrollbar=True, menubar=False, tag="child_window_cnls_parameters"):
                            dpg.add_checkbox(
                                tag="checkbox_cnls_segement_constraints",
                                label="Segment constraints",
                                default_value = True if config.store['segment_constraints'] == 'segment' else False,
                                callback=lambda s, a: gui_utils.cnls_functions.segment_constraints(s, a, config)
                            )

                            with dpg.table(
                                tag = "Table_cnls_parameters",
                                header_row=False,
                                borders_innerH=False,
                                row_background=False,
                                borders_outerH=False,
                                policy=dpg.mvTable_SizingStretchSame
                            ):
                                # Two columns for the sample name and the sample type
                                dpg.add_table_column(tag="cnls_parameter_column1", width_stretch=True)
                                dpg.add_table_column(tag="cnls_parameter_column2", width_stretch=True)

                                # Table contents
                                with dpg.table_row():
                                    dpg.add_checkbox(
                                    tag="checkbox_cnls_R_percentage",
                                    label="R Cons %",
                                    default_value = False if config.store[os.path.splitext(config.display_file)[0]]['CNLS'].R_cons is None else True
                                    )
                                    dpg.add_input_float(
                                        tag=f"input_constraints_R_percentage",
                                        format="%.1f",
                                        enabled=True if config.store['segment_constraints'] == 'segment' else False,
                                        default_value=10 if config.store[os.path.splitext(config.display_file)[0]]['CNLS'].R_cons is None else config.store[os.path.splitext(config.display_file)[0]]['CNLS'].R_cons,
                                        width=-1,
                                        step=0,
                                        step_fast=0,
                                        min_value=1e-100,
                                        max_value=1e100,
                                    )
                                with dpg.table_row():
                                    dpg.add_checkbox(
                                    tag="checkbox_cnls_Tau_percentage",
                                    label="Tau Cons %",
                                    default_value = False if config.store[os.path.splitext(config.display_file)[0]]['CNLS'].Tau_cons is None else True
                                    )
                                    dpg.add_input_float(
                                        tag=f"input_constraints_Tau_percentage",
                                        format="%.1f",
                                        enabled=True if config.store['segment_constraints'] == 'segment' else False,
                                        default_value=10 if config.store[os.path.splitext(config.display_file)[0]]['CNLS'].Tau_cons is None else config.store[os.path.splitext(config.display_file)[0]]['CNLS'].Tau_cons,
                                        width=-1,
                                        step=0,
                                        step_fast=0,
                                        min_value=1e-100,
                                        max_value=1e100,
                                    )
                                with dpg.table_row():
                                    dpg.add_text("Data_type:")
                                    cnls_data_type_items = CNLS_fn.get_cnls_data_type_items()
                                    cnls_data_type_default = CNLS_fn.normalize_cnls_data_type(CNLS.data_type)[0]
                                    if cnls_data_type_default not in cnls_data_type_items:
                                        cnls_data_type_default = "truncated"
                                    dpg.add_combo(
                                        tag="combo_cnls_data_type",
                                        default_value = cnls_data_type_default,
                                        width = -1,
                                        items = cnls_data_type_items,
                                        callback=lambda s, a: gui_utils.cnls_functions.update_data_type(s, a, config)
                                    )
                                with dpg.table_row():
                                    dpg.add_text("Peaks")
                                    dpg.add_button(
                                        tag="button_select_peaks",
                                        label="Select from DRT",
                                        width=-1,
                                        callback=lambda s, a: gui_utils.cnls_functions.open_peak_select_window(config)
                                    )
                                with dpg.table_row():
                                    dpg.add_text("Nbr iters:")
                                    dpg.add_input_int(
                                        tag="input_nbr_iters",
                                        default_value = config.store[os.path.splitext(config.display_file)[0]]['CNLS'].iteration if gui_utils.cnls_functions._file_existence_check(config) and config.store[os.path.splitext(config.display_file)[0]]['CNLS'].iteration is not None else 5,
                                        width = -1,
                                        min_value = 1,
                                        max_value = 10,
                                        callback=lambda s, a: gui_utils.cnls_functions.nbr_iteration(s, a, config)
                                    )
                                with dpg.table_row():
                                    dpg.add_text("Nbr peaks:")
                                    dpg.add_input_int(
                                        tag="input_nbr_peaks",
                                        default_value = len(config.store[os.path.splitext(config.display_file)[0]]['CNLS'].f_fixed) if gui_utils.cnls_functions._file_existence_check(config) and config.store[os.path.splitext(config.display_file)[0]]['CNLS'].f_fixed is not None else 5,
                                        width = -1,
                                        min_value = 1,
                                        max_value = 10000,
                                        callback=lambda s, a: gui_utils.cnls_functions.dynamic_peak_ids(s, a, config)
                                    )
                                gui_utils.cnls_functions.dynamic_peak_ids(0, 0, config)

                # Window for the buttons
                with dpg.child_window(width=int(viewport_width * 0.45), height=int(viewport_height*0.082), horizontal_scrollbar=True, menubar=False, tag="child_window_cnls_buttons"):
                    with dpg.group(horizontal=True):
                        dpg.add_button(tag="Button_cnls_initialize_parameters", label="Initialize param.", width=int(viewport_width*0.1), callback=lambda s, a: gui_utils.cnls_functions.initialize_parameters(s, a, config))
                        dpg.bind_item_theme("Button_cnls_initialize_parameters", blue_button_theme)

                        dpg.add_button(tag="Button_cnls_load_parameters", label="Load parameters", width=int(viewport_width*0.1), callback=lambda s, a: gui_utils.cnls_functions.load_parameters(s, a, config))
                        dpg.bind_item_theme("Button_cnls_load_parameters", blue_button_theme)

                        dpg.add_button(tag="Button_cnls_cnls_fit", label="CNLS fit", width=int(viewport_width*0.1), callback=lambda s, a: gui_utils.cnls_functions.cnls_fit(s, a, config))
                        dpg.bind_item_theme("Button_cnls_cnls_fit", blue_button_theme)

                        dpg.add_button(tag="Button_Save_CNLS", label="Save CNLS", width=-1, callback=lambda s, a: gui_utils.cnls_functions.save_cnls(s, a, config, CNLS))
                        dpg.bind_item_theme("Button_Save_CNLS", blue_button_theme)

                    with dpg.group(horizontal=True, tag="group_cnls_display_file"):
                        dpg.add_text("Displayed file:")
                        dpg.add_button(arrow=True, direction=dpg.mvDir_Left, tag="button_prev_display_file_cnls",
                                       callback=lambda: gui_utils.file_list.step_display_file(config, -1))
                        dpg.add_button(arrow=True, direction=dpg.mvDir_Right, tag="button_next_display_file_cnls",
                                       callback=lambda: gui_utils.file_list.step_display_file(config, +1))
                        gui_utils.file_list.update_file_list_and_display(0, 0, config, "combo_display_file_cnls", "group_cnls_display_file")
                
                # Window for the data display
                with dpg.child_window(width=int(viewport_width * 0.45), height=-1, horizontal_scrollbar=True, menubar=False, border=False, tag="child_window_cnls_data"):
                    with dpg.tab_bar(tag="tab_bar_cnls_data"):
                        gui_utils.cnls_table.table_update(config)

            # Window for the plot display
            with dpg.group():
                with dpg.child_window(width=-1, height=-1, horizontal_scrollbar=True, menubar=False, border=True, tag="child_window_cnls_plot"):
                    pass
                    with dpg.tab_bar(tag="tab_bar_cnls_plot"):
                        with dpg.tab(label="Single", tag="tab_cnls_plot_single"):
                            with dpg.tab_bar(tag="tab_bar_cnls_plot_single"):
                                gui_utils.cnls_plots.update_single_plots(config)
                        with dpg.tab(label="All", tag="tab_cnls_plot_all"):
                            with dpg.tab_bar(tag="tab_bar_cnls_plot_all"):
                                gui_utils.cnls_plots.update_all_plots(config)
                            
    # Update the child window size when the viewport is resized
    gui_utils.file_list.display_file(
        None,
        config.display_file,
        config,
        refresh_eis_tab=False,
        refresh_drt_tab=False,
        refresh_cnls_tab=True,
    )
    dpg.set_value("tab_bar_main", 'tab_cnls')
    update_child_window_size()
                            