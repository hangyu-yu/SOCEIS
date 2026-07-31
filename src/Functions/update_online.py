import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote

import requests


def _normalize_path(path_obj):
    """Handle Windows long path (260+ chars) by adding \\\\?\\ prefix."""
    path_str = str(path_obj)
    if sys.platform == 'win32' and os.path.isabs(path_str) and not path_str.startswith('\\\\'):
        return '\\\\?' + os.path.sep + os.path.abspath(path_str)
    return path_str


def _get_default_branch(repo_owner, repo_name):
    """Return repository default branch, fallback to main if API is unavailable."""
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        payload = response.json()
        return payload.get("default_branch", "main")
    except requests.RequestException:
        return "main"


def _decode_windows_zip_path(path_obj):
    """Decode URL-encoded names from zip entries on Windows when present."""
    path_str = str(path_obj)
    if sys.platform == 'win32' and '%' in path_str:
        return Path(unquote(path_str))
    return Path(path_str)


def _iter_relative_files(root_dir):
    for path in root_dir.rglob("*"):
        if path.is_file():
            yield path.relative_to(root_dir)


def _iter_relative_dirs(root_dir):
    for path in root_dir.rglob("*"):
        if path.is_dir():
            yield path.relative_to(root_dir)


def _is_under(rel_path, prefix):
    try:
        rel_path.relative_to(prefix)
        return True
    except ValueError:
        return False


def _is_projects_tree(rel_path):
    return bool(rel_path.parts) and rel_path.parts[0].lower() == "projects"


def _should_keep_local(rel_path, keep_paths):
    # Keep exact paths and everything under kept directories.
    return _is_projects_tree(rel_path) or any(_is_under(rel_path, keep_path) for keep_path in keep_paths)


def _is_internal_keep(rel_path):
    """Keep local VCS metadata to avoid breaking repository state."""
    if not rel_path.parts:
        return False
    return rel_path.parts[0] == ".git"


def _sync_tree(source_root, target_root, keep_paths):
    """Mirror source tree into target tree, preserving configured local files."""
    source_files = set(_iter_relative_files(source_root))
    source_dirs = set(_iter_relative_dirs(source_root))

    for rel_path in source_files:
        if _should_keep_local(rel_path, keep_paths):
            continue
        source_file = source_root / rel_path
        target_file = target_root / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_normalize_path(source_file), _normalize_path(target_file))

    target_files = [p for p in target_root.rglob("*") if p.is_file()]
    for target_file in target_files:
        rel_path = target_file.relative_to(target_root)
        if _is_internal_keep(rel_path) or _should_keep_local(rel_path, keep_paths):
            continue
        if rel_path not in source_files:
            try:
                Path(_normalize_path(target_file)).unlink(missing_ok=True)
            except Exception:
                pass

    target_dirs = sorted((p for p in target_root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
    for target_dir in target_dirs:
        rel_path = target_dir.relative_to(target_root)
        if _is_internal_keep(rel_path):
            continue
        # Skip kept directories themselves and all their descendants.
        if _should_keep_local(rel_path, keep_paths):
            continue
        # Also skip ancestors of kept paths (e.g., `src` for `src/GUI/config.json`).
        if any(_is_under(keep_path, rel_path) for keep_path in keep_paths):
            continue
        if rel_path not in source_dirs:
            shutil.rmtree(target_dir, ignore_errors=True)


def run_online_update(app_root, repo_owner="hangyu-yu", repo_name="EISAP", keep_paths=None):
    """
    Download latest default-branch source and mirror into app_root.

    Returns:
        tuple[bool, str]: success flag and status message.
    """
    app_root = Path(app_root).resolve()
    if keep_paths is None:
        keep_paths = [Path("src/GUI/config.json"), Path("Projects")]
    keep_paths = [Path(p) for p in keep_paths]

    temp_root = Path(tempfile.mkdtemp(prefix="soceis_update_"))
    try:
        branch = _get_default_branch(repo_owner, repo_name)
        zip_url = f"https://github.com/{repo_owner}/{repo_name}/archive/refs/heads/{branch}.zip"
        zip_path = temp_root / "source.zip"

        response = requests.get(zip_url, stream=True, timeout=60)
        response.raise_for_status()

        with open(_normalize_path(zip_path), "wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_handle.write(chunk)

        extract_dir = temp_root / "extracted"
        Path(_normalize_path(extract_dir)).mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(_normalize_path(zip_path), "r") as archive:
            archive.extractall(_normalize_path(extract_dir))

        extracted_roots = [path for path in extract_dir.iterdir() if path.is_dir()]
        if len(extracted_roots) != 1:
            return False, "Update package structure is invalid."

        source_root = _decode_windows_zip_path(extracted_roots[0])
        if not Path(_normalize_path(source_root / "EISAP.py")).exists() or not Path(_normalize_path(source_root / "src")).exists():
            return False, "Downloaded package does not look like EISAP project."

        _sync_tree(source_root=source_root, target_root=app_root, keep_paths=keep_paths)
        return True, f"Update completed from branch '{branch}'."
    except requests.Timeout:
        return False, "Update failed: GitHub request timed out."
    except requests.ConnectionError:
        return False, "Update failed: cannot connect to GitHub."
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        return False, f"Update failed: GitHub returned HTTP {status_code}."
    except zipfile.BadZipFile:
        return False, "Update failed: downloaded package is not a valid zip file."
    except PermissionError:
        return False, "Update failed: no write permission in project folder."
    except Exception as exc:
        return False, f"Update failed: {exc}"
    finally:
        try:
            shutil.rmtree(_normalize_path(temp_root), ignore_errors=True)
        except Exception:
            pass
