"""只管理這次建立的工作程序樹；Windows Job Object關閉即釋放所有子程序。"""
import os
import signal


class ProcessScope:
    def __init__(self, process):
        self.process = process
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes as W
        class Limits(ctypes.Structure):
            _fields_ = [('ProcessTime', ctypes.c_longlong), ('JobTime', ctypes.c_longlong),
                        ('Flags', W.DWORD), ('MinWorkingSet', ctypes.c_size_t), ('MaxWorkingSet', ctypes.c_size_t),
                        ('ActiveProcessLimit', W.DWORD), ('Affinity', ctypes.c_size_t),
                        ('Priority', W.DWORD), ('Scheduling', W.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('Basic', Limits), ('Io', IO), ('ProcessMemory', ctypes.c_size_t),
                        ('JobMemory', ctypes.c_size_t), ('PeakProcessMemory', ctypes.c_size_t), ('PeakJobMemory', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in [
            ('CreateJobObjectW', [ctypes.c_void_p, W.LPCWSTR], W.HANDLE),
            ('SetInformationJobObject', [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD], W.BOOL),
            ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ('AssignProcessToJobObject', [W.HANDLE,W.HANDLE], W.BOOL),
            ('TerminateJobObject', [W.HANDLE,W.UINT], W.BOOL), ('CloseHandle',[W.HANDLE],W.BOOL)]:
            function = getattr(kernel,name)
            function.argtypes, function.restype = args, result
        self.kernel = kernel
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        owned = None
        try:
            info = Extended()
            info.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            owned = kernel.OpenProcess(0x0100 | 0x0001, False, process.pid)  # SET_QUOTA | TERMINATE
            if not owned or not kernel.AssignProcessToJobObject(job, owned):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = job
        except BaseException:
            kernel.CloseHandle(job)
            raise
        finally:
            if owned:
                kernel.CloseHandle(owned)

    def terminate(self):
        if os.name == 'nt':
            if self.handle and not self.kernel.TerminateJobObject(self.handle, 1):
                import ctypes
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        elif os.name != 'nt' and self.process.poll() is None:
            self.terminate()
