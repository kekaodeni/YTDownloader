"""Stdlib Win32 pipe client; no Qt, settings, browser or Cookie imports."""
import ctypes
from ctypes import wintypes
import hashlib
import os
import struct
import time
from .protocol import MAX_MESSAGE_BYTES, ProtocolError, decode_message, frame

def current_user_sid():
    if os.name != 'nt': return str(os.getuid())
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    handle, size = wintypes.HANDLE(), wintypes.DWORD()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(handle)): raise OSError()
    try:
        adv.GetTokenInformation(handle, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(handle, 1, buffer, size, ctypes.byref(size)): raise OSError()
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        text = wintypes.LPWSTR()
        if not adv.ConvertSidToStringSidW(sid, ctypes.byref(text)): raise OSError()
        try: return text.value
        finally: kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
    finally: kernel.CloseHandle(handle)

def endpoint_name():
    from yt_downloader.infrastructure.paths import AppPaths
    identity = current_user_sid() + '|' + str(AppPaths.discover().data.resolve()).casefold()
    return 'YTDownloader-' + hashlib.sha256(identity.encode()).hexdigest()[:24]

def send_local(message, *, timeout=5, name=None):
    if os.name != 'nt': raise OSError('Windows named pipe unavailable')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.ReadFile.argtypes = [wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
    kernel.WriteFile.argtypes = kernel.ReadFile.argtypes
    kernel.PeekNamedPipe.argtypes = [wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
    path = '\\\\.\\pipe\\' + (name or endpoint_name())
    deadline = time.monotonic() + timeout
    # Overlapped writes have a deadline too: a hung desktop must never leave
    # the browser's Native Messaging process blocked in synchronous WriteFile.
    class OVERLAPPED(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
    kernel.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
    handle = kernel.CreateFileW(path, 0xC0000000, 0, None, 3, 0x40000000, None)
    if handle == ctypes.c_void_p(-1).value: raise OSError('host_unavailable')
    def transfer(operation, buffer, size):
        event = kernel.CreateEventW(None, True, False, None)
        if not event: raise OSError('host_unavailable')
        overlapped = OVERLAPPED(hEvent=event)
        count = wintypes.DWORD()
        try:
            if not operation(handle, buffer, size, ctypes.byref(count), ctypes.byref(overlapped)):
                if ctypes.get_last_error() != 997: raise OSError('host_unavailable')
                remaining = max(0, int((deadline - time.monotonic()) * 1000))
                if kernel.WaitForSingleObject(event, remaining) != 0:
                    kernel.CancelIoEx(handle, ctypes.byref(overlapped))
                    # The buffers must remain alive until cancellation completes.
                    kernel.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(count), True)
                    raise TimeoutError('bridge_timeout')
                if not kernel.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(count), False):
                    raise OSError('host_unavailable')
            return count.value
        finally: kernel.CloseHandle(event)
    try:
        data = frame(message)
        if transfer(kernel.WriteFile, data, len(data)) != len(data): raise OSError('host_unavailable')
        received = bytearray()
        needed = 4
        while len(received) < needed:
            if time.monotonic() >= deadline: raise TimeoutError('bridge_timeout')
            count = wintypes.DWORD()
            if not kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(count), None): raise OSError('host_unavailable')
            if not count.value:
                time.sleep(.01); continue
            buffer = ctypes.create_string_buffer(min(count.value, needed - len(received)))
            read = transfer(kernel.ReadFile, buffer, len(buffer))
            if not read: raise OSError('host_unavailable')
            received.extend(buffer.raw[:read])
            if len(received) == 4:
                length = struct.unpack('<I', received)[0]
                if not 0 < length <= MAX_MESSAGE_BYTES: raise ProtocolError()
                needed = length + 4
        return decode_message(bytes(received[4:]))
    finally: kernel.CloseHandle(handle)
