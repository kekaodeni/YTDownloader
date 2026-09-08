"""Opt-in per-user MKV thumbnail integration. Does not change file open commands."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
import winreg
import zipfile

VERSION = "3.3.6"
URL = "https://github.com/Xanashi/Icaros/releases/download/v3.3.6/Icaros_v3.3.6.zip"
SHA256 = "18854b445420e7167b5f54696009c9ffbc0e7917da9d9a686eac71ea3c81d47a"
CLSID = "{c5aec3ec-e812-4677-a9a7-4fee1f9aa000}"
THUMBNAIL = "{e357fccd-a995-4576-b01f-234630154e96}"
ROOT = Path(os.environ["LOCALAPPDATA"]) / "YTDownloader" / "shell"
# Keep the previous tool-view backup separate from the actual Windows user.
BACKUP = ROOT / "icaros-desktop-registration.json"


def read_value(key, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            value, kind = winreg.QueryValueEx(handle, name)
            return {"value": value, "type": kind}
    except FileNotFoundError:
        return None


def assignments(directory):
    # The COM server is registered by the separately approved administrator step.
    return [
        (rf"Software\Classes\.mkv\ShellEx\{THUMBNAIL}", "", CLSID),
        (rf"Software\Classes\.mkv\ShellEx\{{BB2E617C-0920-11d1-9A0B-00C04FC2D6C1}}", "", CLSID),
        (r"Software\Icaros", "UseCoverArt", 1),
    ]


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def notify():
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def disable():
    if not BACKUP.exists():
        return {"status": "not_enabled"}
    saved = json.loads(BACKUP.read_text(encoding="utf-8"))
    retained = []
    for item in reversed(saved["values"]):
        current = read_value(item["key"], item["name"])
        expected = {"value": item["installed"], "type": winreg.REG_DWORD if isinstance(item["installed"], int) else winreg.REG_SZ}
        if current != expected:
            # A later user or installer change takes precedence over this backup.
            if current != item["before"]:
                retained.append(item["key"])
            continue
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, item["key"], 0, winreg.KEY_SET_VALUE) as handle:
            before = item["before"]
            if before is None:
                winreg.DeleteValue(handle, item["name"])
            else:
                winreg.SetValueEx(handle, item["name"], 0, before["type"], before["value"])
    for key in sorted({item["key"] for item in saved["values"]}, key=len, reverse=True):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                children, values, _ = winreg.QueryInfoKey(handle)
            if not children and not values:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            pass
    save_json(ROOT / "icaros-desktop-last-restore.json", {"retained_later_changes": retained})
    BACKUP.unlink()
    notify()
    return {"status": "restored", "retained_later_changes": retained, "component_directory": saved["directory"]}


def enable(package=None):
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"Software\Classes\CLSID\{CLSID}\InprocServer32", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as server:
        registered, _ = winreg.QueryValueEx(server, "")
    if not Path(registered).is_file():
        raise RuntimeError("Register the standard COM server first with administrator approval.")
    if BACKUP.exists():
        saved = json.loads(BACKUP.read_text(encoding="utf-8"))
        if all(read_value(x["key"], x["name"]) == {"value": x["installed"], "type": winreg.REG_DWORD if isinstance(x["installed"], int) else winreg.REG_SZ} for x in saved["values"]):
            return {"status": "already_enabled", "directory": saved["directory"]}
        raise RuntimeError("Existing integration changed; restore before enabling again.")
    ROOT.mkdir(parents=True, exist_ok=True)
    directory = Path(registered).parent.parent
    values = [{"key": key, "name": name, "installed": value, "before": read_value(key, name)} for key, name, value in assignments(directory)]
    save_json(BACKUP, {"version": VERSION, "package_sha256": SHA256, "directory": str(directory), "intended_scope": "current Windows user", "values": values})
    try:
        for item in values:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, item["key"], 0, winreg.KEY_SET_VALUE) as handle:
                value = item["installed"]
                winreg.SetValueEx(handle, item["name"], 0, winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ, value)
    except Exception:
        disable()
        raise
    notify()
    return {"status": "enabled", "extension": ".mkv", "directory": str(directory), "backup": str(BACKUP)}


def register_server(package):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Standard COM registration requires administrator approval.")
    if package is None:
        raise ValueError("Supply the verified official portable ZIP with --package.")
    content = Path(package).read_bytes()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise RuntimeError("Official Icaros package SHA256 mismatch")
    import io
    directory = Path(os.environ["ProgramFiles"]) / "YTDownloader Shell" / ("Icaros-" + VERSION)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for entry in archive.infolist():
            target = (directory / entry.filename).resolve()
            if not target.is_relative_to(directory.resolve()):
                raise ValueError("Unsafe archive member")
            if target.exists() and not entry.is_dir() and target.read_bytes() != archive.read(entry):
                raise RuntimeError("Existing component file differs from the official archive")
        archive.extractall(directory)
    server_values = [
        (rf"Software\Classes\CLSID\{CLSID}", "", "Icaros Thumbnail Provider"),
        (rf"Software\Classes\CLSID\{CLSID}\InprocServer32", "", str(directory / "64-bit" / "IcarosThumbnailProvider.dll")),
        (rf"Software\Classes\CLSID\{CLSID}\InprocServer32", "ThreadingModel", "Apartment"),
        (r"Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved", CLSID, "Icaros Thumbnail Provider"),
    ]
    backup = directory.parent / "machine-registration.json"
    values = []
    if backup.exists():
        saved = json.loads(backup.read_text(encoding="utf-8"))
        if saved["directory"] != str(directory):
            raise RuntimeError("Existing server registration differs; restore it first.")
    else:
        for key, name, installed in server_values:
            before = None
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as handle:
                    value, kind = winreg.QueryValueEx(handle, name)
                    before = {"value": value, "type": kind}
            except FileNotFoundError:
                pass
            values.append({"key": key, "name": name, "installed": installed, "before": before})
        save_json(backup, {"directory": str(directory), "values": values, "package_sha256": SHA256})
    try:
        for key, name, value in server_values:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as handle:
                winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)
    except Exception:
        unregister_server()
        raise
    notify()
    return {"status": "server_registered", "directory": str(directory), "backup": str(backup), "process_isolation": "enabled"}


def unregister_server():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Administrator approval required.")
    backup = Path(os.environ["ProgramFiles"]) / "YTDownloader Shell" / "machine-registration.json"
    if not backup.exists():
        return {"status": "not_registered"}
    data = json.loads(backup.read_text(encoding="utf-8"))
    retained = []
    for item in reversed(data["values"]):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, item["key"], 0, winreg.KEY_READ | winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as handle:
                current, kind = winreg.QueryValueEx(handle, item["name"])
                if current != item["installed"] or kind != winreg.REG_SZ:
                    retained.append(item["key"]); continue
                if item["before"] is None:
                    winreg.DeleteValue(handle, item["name"])
                else:
                    before = item["before"]
                    winreg.SetValueEx(handle, item["name"], 0, before["type"], before["value"])
        except FileNotFoundError:
            pass
    backup.replace(backup.with_name("machine-last-restore.json"))
    notify()
    return {"status": "server_restored", "retained_later_changes": retained}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--enable", action="store_true")
    actions.add_argument("--disable", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--register-server", action="store_true")
    actions.add_argument("--unregister-server", action="store_true")
    parser.add_argument("--package", type=Path)
    args = parser.parse_args()
    result = register_server(args.package) if args.register_server else unregister_server() if args.unregister_server else enable(args.package) if args.enable else disable() if args.disable else {"setup_process_elevated": bool(ctypes.windll.shell32.IsUserAnAdmin()), "registered": read_value(rf"Software\Classes\.mkv\ShellEx\{THUMBNAIL}", ""), "backup_exists": BACKUP.exists()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
