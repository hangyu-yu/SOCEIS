import os
import json
import shutil
import stat
from pathlib import Path
import numpy as np


def _normalize_path(path_obj):
    """Handle Windows long path (260+ chars) by adding \\\\?\\ prefix."""
    path_str = str(path_obj)
    if os.name == 'nt' and os.path.isabs(path_str) and not path_str.startswith('\\\\'):
        return '\\\\?' + os.path.sep + os.path.abspath(path_str)
    return path_str

class Config:
    def __init__(self, config_file="config.json"):
        _gui_dir  = os.path.dirname(os.path.abspath(__file__))  # …/src/GUI/
        _src_dir  = os.path.dirname(_gui_dir)                   # …/src/
        _root_dir = os.path.dirname(_src_dir)                   # project root / site-packages
        # Assets now live exclusively in <root>/soceis/assets/.
        # project_path is the parent of both src/ and soceis/.
        self.project_path = _root_dir
        self._src_dir = _src_dir  # stable path to the src/ package, used internally
        self.bootstrap_config_file = os.path.join(_src_dir, 'GUI', config_file)
        self.config_file = self.bootstrap_config_file
        self.temp_folder_name = "temp"
        self.supported_file_extensions = [".txt", ".mpt", ".csv", ".xlsx", ".dta", ".z", ".fcd"]
        self.default_data_import_function = str(Path(__file__).parent.parent / "Functions" / "01_Data_read" / "read_general_all.py")
        # Default font size
        self.font_size = 20
        # Default folder path
        self.folder_path = os.path.dirname(os.path.abspath(__file__))
        # Selected file extensions
        self.file_extensions = self.supported_file_extensions[0]
        # File list
        self.file_list = []
        # Selected file paths
        self.selected_files = []
        # Per-file numeric values (basename -> float), default 0.0
        self.file_values = {}
        # Displayed file name
        self.display_file = ""
        # Select data import functino
        self.data_import_function = self.default_data_import_function
        # Fixed all the plots for CNLS fit
        self.fix_all_plots_CNLS = False
        # Store
        self.store = {}
        self.store['element_list'] = {"Resistor": "R", "Inductor": "L", "Inductor_a": "La", "Capacitor": "C", "CPE": "Q", "RC": "RC", "RQ": "RQ", "Gerisher": "G", "fFLW": "fFLW", "FLW": "FLW", "Warburg": "W", "RandleC": "RandleC", "RandleCPE": "RandleCPE", "RandleCPEfFLW": "RandleCPEfFLW", "RandleCfFLW": "RandleCfFLW"}
        self.store["peak_fixed_frequencies"] = []
        self.store["Elements"] = [
            {'name': 'L1', 'type': 'Inductor', 'Param': [1], 'Ub': [np.inf], 'Lb': [1e-10]},
            {'name': 'R2', 'type': 'Resistor', 'Param': [1], 'Ub': [np.inf], 'Lb': [1e-10]},
        ]
        self.store["segment_constraints"] = 'segment'
        self.store['viewer_processes'] = []
        self.store["eis_freq_cut"] = False

        self._initialize_config_context()

    def _safe_read_json(self, path):
        """Read JSON safely and return dict fallback for format errors."""
        try:
            if not path or not os.path.exists(_normalize_path(path)):
                return {}
            with open(_normalize_path(path), "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _safe_write_json(self, path, data):
        """Write JSON safely, creating parent folders if needed."""
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(_normalize_path(parent), exist_ok=True)
        with open(_normalize_path(path), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _coerce_existing_dir(self, value):
        if isinstance(value, str) and value.strip():
            candidate = os.path.abspath(os.path.expanduser(value.strip()))
            if os.path.isdir(_normalize_path(candidate)):
                return candidate
        return None

    def _coerce_list_of_strings(self, value):
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if item is not None and str(item) != ""]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _coerce_file_values(self, value):
        """Coerce a raw file-values map to {basename: float}, dropping bad entries."""
        if not isinstance(value, dict):
            return {}
        result = {}
        for key, raw in value.items():
            name = os.path.basename(str(key)).strip()
            if not name:
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            if number != number or number in (float("inf"), float("-inf")):  # NaN/inf guard
                continue
            result[name] = number
        return result

    def _default_config_dict(self, folder_path=None):
        folder = folder_path or self.folder_path
        return {
            "font_size": self.font_size,
            "folder_path": folder,
            "file_list": [],
            "selected_files": [],
            "file_values": {},
            "file_extensions": self.supported_file_extensions[0],
            "display_file": "",
            "data_import_function": self.default_data_import_function,
        }

    def _sanitize_loaded_config(self, raw_data, folder_override=None):
        """Normalize mixed/legacy config formats to current schema with safe defaults."""
        data = raw_data if isinstance(raw_data, dict) else {}
        defaults = self._default_config_dict(folder_override or self.folder_path)

        def _normalize_filename(value):
            text = str(value).strip()
            return os.path.basename(text) if text else ""

        # font_size: tolerate string/float inputs
        font_size_raw = data.get("font_size", defaults["font_size"])
        try:
            font_size = int(float(font_size_raw))
            font_size = font_size if font_size > 0 else defaults["font_size"]
        except Exception:
            font_size = defaults["font_size"]

        folder_path = folder_override or self._coerce_existing_dir(data.get("folder_path")) or defaults["folder_path"]

        file_list = self._coerce_list_of_strings(data.get("file_list", defaults["file_list"]))

        selected_files_raw = self._coerce_list_of_strings(data.get("selected_files", defaults["selected_files"]))
        selected_files = []
        for item in selected_files_raw:
            filename = _normalize_filename(item)
            if filename and filename not in selected_files:
                selected_files.append(filename)

        file_ext_raw = data.get("file_extensions", defaults["file_extensions"])
        if isinstance(file_ext_raw, str) and file_ext_raw.strip():
            file_extensions = file_ext_raw.strip()
        elif isinstance(file_ext_raw, (list, tuple)) and file_ext_raw:
            file_extensions = str(file_ext_raw[0])
        elif isinstance(file_ext_raw, dict):
            file_extensions = str(file_ext_raw.get("default", defaults["file_extensions"]))
        else:
            file_extensions = defaults["file_extensions"]

        display_raw = data.get("display_file", defaults["display_file"])
        if isinstance(display_raw, str):
            display_file = _normalize_filename(display_raw)
        elif isinstance(display_raw, (list, tuple)) and display_raw:
            display_file = _normalize_filename(display_raw[0])
        else:
            display_file = ""

        data_import_raw = data.get("data_import_function", defaults["data_import_function"])
        if isinstance(data_import_raw, str) and data_import_raw.strip() and os.path.isfile(_normalize_path(data_import_raw.strip())):
            data_import_function = data_import_raw.strip()
        else:
            data_import_function = defaults["data_import_function"]

        file_values = self._coerce_file_values(data.get("file_values", defaults["file_values"]))

        return {
            "font_size": font_size,
            "folder_path": folder_path,
            "file_list": file_list,
            "selected_files": selected_files,
            "file_values": file_values,
            "file_extensions": file_extensions,
            "display_file": display_file,
            "data_import_function": data_import_function,
        }

    def _project_temp_config_path(self, folder_path):
        return os.path.join(folder_path, self.temp_folder_name, "config.json")

    def _normalize_extension(self, ext_value):
        """Normalize extension input like '.txt' / '*.txt' / 'txt' to '.txt'."""
        if not isinstance(ext_value, str):
            return ""
        ext = ext_value.strip().lower()
        if not ext:
            return ""
        if ext.startswith("*"):
            ext = ext[1:]
        if ext and not ext.startswith("."):
            ext = f".{ext}"
        return ext

    def _normalized_supported_extensions(self):
        """Normalized extension list shared with GUI for consistent behavior."""
        normalized = []
        for ext in self.supported_file_extensions:
            ext_norm = self._normalize_extension(ext)
            if ext_norm and ext_norm not in normalized:
                normalized.append(ext_norm)
        return normalized

    def _is_under_software_dirs(self, folder_path):
        """Do not create temp under software directories src/ and soceis/assets/."""
        target = os.path.abspath(folder_path)
        restricted_roots = [
            os.path.abspath(self._src_dir),
            os.path.abspath(os.path.join(os.path.dirname(self._src_dir), "soceis", "assets")),
        ]

        for root in restricted_roots:
            try:
                if os.path.commonpath([target, root]) == root:
                    return True
            except ValueError:
                # Different drives on Windows
                continue
        return False

    def _has_matching_extension_files(self, folder_path):
        """Only create temp when folder contains at least one file matching GUI extension list."""
        extensions = self._normalized_supported_extensions()
        if not extensions:
            return False

        try:
            folder_norm = _normalize_path(folder_path)
            if not os.path.isdir(folder_norm):
                return False

            for entry in os.scandir(folder_norm):
                if entry.is_file() and any(entry.name.lower().endswith(ext) for ext in extensions):
                    return True
        except Exception:
            return False

        return False

    def _ensure_project_temp_config(self, folder_path, force=False, replace_existing=False):
        """Create folder/temp/config.json when allowed by path and content rules."""
        config_path = self._project_temp_config_path(folder_path)
        config_exists = os.path.exists(_normalize_path(config_path))
        if config_exists and not replace_existing:
            return config_path

        if config_exists and replace_existing:
            try:
                os.remove(_normalize_path(config_path))
            except Exception:
                pass

        # Rule 1: never create under software directories.
        if self._is_under_software_dirs(folder_path):
            return None

        # Rule 2: only create when there are files matching current extension,
        # unless caller explicitly forces creation.
        if not force and not self._has_matching_extension_files(folder_path):
            return None

        temp_dir = os.path.dirname(config_path)
        os.makedirs(_normalize_path(temp_dir), exist_ok=True)

        copied = False
        if os.path.exists(_normalize_path(self.bootstrap_config_file)):
            try:
                shutil.copy2(_normalize_path(self.bootstrap_config_file), _normalize_path(config_path))
                copied = True
            except Exception:
                copied = False

        raw_seed = self._safe_read_json(config_path) if copied else {}
        seeded = self._sanitize_loaded_config(raw_seed, folder_override=folder_path)
        seeded["file_list"] = []
        seeded["selected_files"] = []
        seeded["file_values"] = {}
        seeded["display_file"] = ""
        self._safe_write_json(config_path, seeded)
        return config_path

    def create_temp_config_for_folder(self, folder_path=None, force=False, replace_existing=False):
        """Public helper: create temp/config for a folder when allowed.

        Args:
            folder_path: target folder (defaults to current folder_path)
            force: bypass extension-file existence guard
            replace_existing: overwrite existing temp/config.json if present
        """
        target = self._coerce_existing_dir(folder_path if folder_path is not None else self.folder_path)
        if target is None:
            return None
        return self._ensure_project_temp_config(target, force=force, replace_existing=replace_existing)

    def remove_temp_folder_for_folder(self, folder_path=None):
        """Public helper: remove folder/temp recursively if it exists."""
        target = self._coerce_existing_dir(folder_path if folder_path is not None else self.folder_path)
        if target is None:
            return False

        # Keep software directories protected.
        if self._is_under_software_dirs(target):
            return False

        temp_dir = os.path.join(target, self.temp_folder_name)

        def _on_rm_error(func, path, exc_info):
            # Retry deletion for read-only files on Windows.
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        # Try raw path first, then long-path normalized variant.
        candidate_paths = [temp_dir, _normalize_path(temp_dir)]
        removed_any = False

        for candidate in candidate_paths:
            try:
                if os.path.isdir(candidate):
                    shutil.rmtree(candidate, onerror=_on_rm_error)
                    removed_any = True
            except Exception:
                continue

        # Final existence check with both variants.
        still_exists = any(os.path.isdir(path) for path in candidate_paths)
        return removed_any and not still_exists

    def _resolve_active_config_file(self, folder_path):
        """Use folder temp/config.json, creating it only when allowed; otherwise fallback to bootstrap config."""
        temp_config_path = self._project_temp_config_path(folder_path)
        if os.path.exists(_normalize_path(temp_config_path)):
            return temp_config_path
        created_path = self._ensure_project_temp_config(folder_path, force=False)
        if created_path:
            return created_path
        return self.bootstrap_config_file

    def _save_bootstrap_pointer(self):
        """Keep only startup pointer values in bootstrap config for next launch."""
        bootstrap = self._safe_read_json(self.bootstrap_config_file)
        if not isinstance(bootstrap, dict):
            bootstrap = {}
        bootstrap["folder_path"] = self.folder_path
        bootstrap["font_size"] = self.font_size
        self._safe_write_json(self.bootstrap_config_file, bootstrap)

    def _initialize_config_context(self):
        bootstrap_data = self._safe_read_json(self.bootstrap_config_file)
        initial_folder = self._coerce_existing_dir(bootstrap_data.get("folder_path")) or self.folder_path
        self.folder_path = initial_folder
        self.config_file = self._resolve_active_config_file(self.folder_path)
        self.load_config(self.config_file)
        self._save_bootstrap_pointer()
        self.store['previous_selected'] = self.selected_files

    def use_project_folder(self, folder_path, load_existing=True):
        """Switch config context to target folder temp/config.json and optionally load it."""
        resolved = self._coerce_existing_dir(folder_path)
        if resolved is None:
            return False

        self.folder_path = resolved
        self.config_file = self._resolve_active_config_file(self.folder_path)
        if load_existing:
            self.load_config(self.config_file)
        self._save_bootstrap_pointer()
        return True

    def load_config(self, config_file_path=None):
        """Load configuration from active temp config with backward-compatible parsing."""
        self.store['viewer_processes'] = []
        if config_file_path:
            self.config_file = config_file_path

        raw = self._safe_read_json(self.config_file)
        sanitized = self._sanitize_loaded_config(raw, folder_override=self.folder_path)

        self.font_size = sanitized["font_size"]
        self.folder_path = sanitized["folder_path"]
        self.file_list = sanitized["file_list"]
        self.selected_files = sanitized["selected_files"]
        self.file_values = sanitized["file_values"]
        self.file_extensions = sanitized["file_extensions"]
        self.data_import_function = sanitized["data_import_function"]
        self.display_file = sanitized["display_file"] or (self.selected_files[0] if self.selected_files else "")

        if not self.data_import_function:
            self.data_import_function = self.default_data_import_function

    def save_config(self):
        """Save configuration to existing temp config if present; otherwise save to bootstrap config."""
        self.config_file = self._resolve_active_config_file(self.folder_path)

        data = {
            "font_size": self.font_size,
            "folder_path": self.folder_path,
            "file_list": self.file_list,
            "selected_files": self.selected_files,
            "file_values": self.file_values,
            "file_extensions": self.file_extensions,
            "display_file": self.display_file,
            "data_import_function": self.data_import_function
        }
        data = self._sanitize_loaded_config(data, folder_override=self.folder_path)
        self._safe_write_json(self.config_file, data)
        self._save_bootstrap_pointer()