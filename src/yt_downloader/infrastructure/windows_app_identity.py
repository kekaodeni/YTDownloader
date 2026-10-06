"""Per-user Shell shortcut identity for unpackaged, portable Windows toasts.

Uses IShellLinkW + IPropertyStore as in Microsoft's DesktopToasts sample.
No installer, elevation, service, or notification COM activator is required.
"""
import ctypes
from pathlib import Path
import os
import sys
import threading
import uuid

AUMID = 'YTDownloader'
DISPLAY_NAME = 'YT Downloader'
_registration_lock = threading.Lock()


class GUID(ctypes.Structure):
    _fields_ = [('bytes', ctypes.c_ubyte * 16)]

    @classmethod
    def from_string(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [('fmtid', GUID), ('pid', ctypes.c_uint32)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [('vt', ctypes.c_ushort), ('reserved', ctypes.c_ushort * 3),
                ('pointer', ctypes.c_void_p), ('padding', ctypes.c_ubyte * (8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4))]


def _method(interface, index, *argument_types):
    table = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argument_types)(table[index])


def _check(result):
    if result < 0:
        raise OSError(f'Windows application identity HRESULT 0x{result & 0xffffffff:08x}')


def set_process_identity():
    if sys.platform == 'win32':
        _check(ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(AUMID)))


def register_shortcut(icon_path):
    # Concurrent single-task completions share one per-user shortcut.
    with _registration_lock:
        return _register_shortcut(icon_path)


def _register_shortcut(icon_path):
    """Refresh only our own shortcut so moving a portable folder stays valid."""
    if sys.platform != 'win32':
        return {}
    from yt_downloader.infrastructure.runtime import resource_path
    icon = resource_path('assets', 'app.ico')
    if not icon.is_file():
        icon = Path(icon_path)
    target = Path(sys.executable)
    arguments = ''
    if not getattr(sys, 'frozen', False):
        if target.with_name('pythonw.exe').is_file():
            target = target.with_name('pythonw.exe')
        arguments = '-m yt_downloader'
    shortcut = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs' / f'{DISPLAY_NAME}.lnk'
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    ole = ctypes.windll.ole32
    initialized = ole.CoInitializeEx(None, 2)
    _check(initialized)
    interfaces = []
    try:
        link = ctypes.c_void_p()
        clsid = GUID.from_string('00021401-0000-0000-c000-000000000046')
        iid = GUID.from_string('000214f9-0000-0000-c000-000000000046')
        _check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(link)))
        interfaces.append(link)
        for index, value in ((20, str(target)), (11, arguments), (9, str(resource_path())), (7, DISPLAY_NAME)):
            _check(_method(link, index, ctypes.c_wchar_p)(link, value))
        _check(_method(link, 17, ctypes.c_wchar_p, ctypes.c_int)(link, str(icon), 0))
        def query(iid_text):
            result = ctypes.c_void_p()
            identity = GUID.from_string(iid_text)
            _check(_method(link, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
                link, ctypes.byref(identity), ctypes.byref(result)))
            interfaces.append(result)
            return result
        store = query('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
        key = PROPERTYKEY(GUID.from_string('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'), 5)
        text = ctypes.create_unicode_buffer(AUMID)
        value = PROPVARIANT(vt=31, pointer=ctypes.cast(text, ctypes.c_void_p))  # VT_LPWSTR
        _check(_method(store, 6, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))(
            store, ctypes.byref(key), ctypes.byref(value)))
        _check(_method(store, 7)(store))
        persist = query('0000010b-0000-0000-c000-000000000046')
        _check(_method(persist, 6, ctypes.c_wchar_p, ctypes.c_int)(persist, str(shortcut), 1))
        return dict(shortcut=str(shortcut), target=str(target), aumid=AUMID, display_name=DISPLAY_NAME, icon=str(icon))
    finally:
        for interface in reversed(interfaces):
            _method(interface, 2)(interface)
        ole.CoUninitialize()
