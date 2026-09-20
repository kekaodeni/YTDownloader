"""Pinned Windows process identity for interruption recovery, without PID-only kills."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import os


def _kernel():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    return kernel


def _open(kernel,pid,terminate=False):
    handle=kernel.OpenProcess(0x1000|0x100000|(1 if terminate else 0),False,pid)
    if not handle and ctypes.get_last_error()!=87:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _identity(kernel,handle,pid):
    buffer=ctypes.create_unicode_buffer(32768)
    size=wintypes.DWORD(len(buffer))
    if not kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    created,exited,kernel_time,user_time=(wintypes.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel_time),ctypes.byref(user_time)):
        raise ctypes.WinError(ctypes.get_last_error())
    return dict(pid=pid,executable=str(Path(buffer.value).resolve()),
                created=(created.dwHighDateTime<<32)|created.dwLowDateTime)


def process_identity(pid):
    if os.name!='nt' or type(pid) is not int or pid<=0:
        return {}
    kernel=_kernel();handle=_open(kernel,pid)
    if not handle:return {}
    try:return _identity(kernel,handle,pid)
    finally:kernel.CloseHandle(handle)


def stop_recorded_process(record,expected_executable):
    if not record:return False
    if (set(record)!={'pid','executable','created'} or type(record['pid']) is not int
            or record['pid']<=0 or type(record['created']) is not int
            or Path(record['executable']).resolve()!=Path(expected_executable).resolve()):
        raise ValueError('Candidate process identity does not belong to this installation')
    if os.name!='nt':raise RuntimeError('Recorded Windows process cannot be recovered on this platform')
    kernel=_kernel();handle=_open(kernel,record['pid'],True)
    if not handle:return False
    try:
        if kernel.WaitForSingleObject(handle,0)==0:return False
        if _identity(kernel,handle,record['pid'])!=record:return False
        if not kernel.TerminateProcess(handle,1):raise ctypes.WinError(ctypes.get_last_error())
        if kernel.WaitForSingleObject(handle,5000)!=0:raise TimeoutError('Candidate process did not release its files')
        return True
    finally:kernel.CloseHandle(handle)
