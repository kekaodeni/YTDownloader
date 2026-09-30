"""Task-scoped Windows Job Object used to contain helper subprocess trees."""

from __future__ import annotations

import logging
import os


logger = logging.getLogger(__name__)


class ProcessJob:
    """Own one child process tree and terminate only that tree when requested."""

    def __init__(self) -> None:
        self._handle: int | None = None
        self._assigned = False
        self._suspended = {}
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            info = EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
            kernel32.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            if not kernel32.SetInformationJobObject(
                handle, 9, ctypes.byref(info), ctypes.sizeof(info)
            ):
                error = ctypes.WinError(ctypes.get_last_error())
                kernel32.CloseHandle(handle)
                raise error
            self._handle = int(handle)
        except Exception:
            logger.exception("Unable to create Windows Job Object")

    def assign(self, process_id: int) -> bool:
        if os.name != "nt" or self._handle is None:
            return False
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
            process = kernel32.OpenProcess(0x0100 | 0x0001, False, process_id)
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not kernel32.AssignProcessToJobObject(self._handle, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel32.CloseHandle(process)
            self._assigned = True
            return True
        except Exception:
            logger.exception("Unable to assign metadata helper pid=%s to Job Object", process_id)
            return False

    def terminate(self, exit_code: int = 1) -> bool:
        if os.name != "nt" or self._handle is None or not self._assigned:
            return False
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel32.TerminateJobObject.restype = wintypes.BOOL
            if not kernel32.TerminateJobObject(self._handle, exit_code):
                raise ctypes.WinError(ctypes.get_last_error())
            return True
        except Exception:
            logger.exception("Unable to terminate metadata helper Job Object")
            return False

    @staticmethod
    def terminate_process(process_id: int, exit_code: int = 1) -> bool:
        """Terminate one known helper PID when nested jobs are unavailable."""
        if os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel32.TerminateProcess.restype = wintypes.BOOL
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            handle = kernel32.OpenProcess(0x0001 | 0x00100000, False, process_id)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not kernel32.TerminateProcess(handle, exit_code):
                    raise ctypes.WinError(ctypes.get_last_error())
                kernel32.WaitForSingleObject(handle, 500)
            finally:
                kernel32.CloseHandle(handle)
            return True
        except Exception:
            logger.exception("Unable to terminate metadata helper pid=%s", process_id)
            return False

    def close(self) -> None:
        if self._suspended:
            try:
                self.resume()
            except OSError:
                self.terminate()
                logger.exception("Unable to resume closing helper Job Object")
        if os.name == "nt" and self._handle is not None:
            import ctypes

            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle(self._handle)
            self._handle = None
            self._assigned = False

    def members(self) -> tuple[int, ...]:
        """Query only the process tree owned by this job."""
        if os.name != 'nt' or self._handle is None or not self._assigned:
            return ()
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                       ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        capacity = 32
        while True:
            class ProcessList(ctypes.Structure):
                _fields_ = [('assigned', wintypes.DWORD), ('count', wintypes.DWORD),
                            ('ids', ctypes.c_size_t * capacity)]
            data = ProcessList()
            if kernel32.QueryInformationJobObject(self._handle, 3, ctypes.byref(data), ctypes.sizeof(data), None):
                return tuple(data.ids[:data.count])
            if ctypes.get_last_error() != 234:
                raise ctypes.WinError(ctypes.get_last_error())
            capacity *= 2

    @staticmethod
    def _suspension_api():
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        ntdll = ctypes.WinDLL('ntdll')
        for name in ('NtSuspendProcess', 'NtResumeProcess'):
            function = getattr(ntdll, name)
            function.argtypes = [wintypes.HANDLE]
            function.restype = ctypes.c_long
        return kernel32, ntdll

    def suspend(self):
        """Suspend every job member, retaining handles to prevent PID reuse."""
        import ctypes
        kernel32, ntdll = self._suspension_api()
        try:
            # A stopped parent cannot create more children. Repeat until the
            # membership is stable, including children created during the call.
            while True:
                new = [pid for pid in self.members() if pid not in self._suspended]
                if not new:
                    break
                for pid in new:
                    handle = kernel32.OpenProcess(0x0800 | 0x1000, False, pid)
                    if not handle:
                        if pid not in self.members():
                            continue
                        raise ctypes.WinError(ctypes.get_last_error())
                    status = ntdll.NtSuspendProcess(handle)
                    if status < 0:
                        kernel32.CloseHandle(handle)
                        raise OSError(f'NtSuspendProcess failed: {status:#x}')
                    self._suspended[pid] = handle
        except Exception:
            self.resume()
            raise
        if not self._suspended:
            raise OSError('The section process exited before suspension')

    def resume(self):
        import ctypes
        from ctypes import wintypes
        kernel32, ntdll = self._suspension_api()
        failure = None
        for pid, handle in reversed(tuple(self._suspended.items())):
            try:
                code = wintypes.DWORD()
                alive = kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259
                if alive:
                    status = ntdll.NtResumeProcess(handle)
                    if status < 0:
                        raise OSError(f'NtResumeProcess failed: {status:#x}')
            except Exception as error:
                failure = error
            finally:
                kernel32.CloseHandle(handle)
                del self._suspended[pid]
        if failure is not None:
            raise failure
