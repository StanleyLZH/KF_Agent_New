"""Windows 红框高亮（闪烁）工具。"""
import ctypes
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _blink_overlay_thread(
    rect: tuple[int, int, int, int],
    duration_seconds: float,
    interval_seconds: float,
    border_px: int,
) -> None:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32

    user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
    user32.RegisterClassExW.restype = ctypes.c_ushort
    user32.CreateWindowExW.argtypes = [
        ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = ctypes.c_void_p

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("style", ctypes.c_uint),
            ("lpfnWndProc", ctypes.c_void_p),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.c_void_p),
            ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", ctypes.c_void_p),
            ("lpszClassName", ctypes.c_void_p),
            ("hIconSm", ctypes.c_void_p),
        ]

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hdc", ctypes.c_void_p),
            ("fErase", ctypes.c_long),
            ("rcPaint", RECT),
            ("fRestore", ctypes.c_long),
            ("fIncUpdate", ctypes.c_long),
            ("rgbReserved", ctypes.c_byte * 32),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MSG(ctypes.Structure):
        _pack_ = 8
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("time", ctypes.c_ulong),
            ("pt", POINT),
            ("lPrivate", ctypes.c_ulong),
        ]

    WM_PAINT = 0x000F
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WM_QUIT = 0x0012
    PM_REMOVE = 0x0001
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000
    WS_POPUP = 0x80000000
    RGN_DIFF = 4
    SW_HIDE = 0
    SW_SHOW = 5
    HWND_TOPMOST = ctypes.c_void_p(-1)
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001

    left, top, right, bottom = rect
    width = max(1, right - left + border_px * 2)
    height = max(1, bottom - top + border_px * 2)
    x = left - border_px
    y = top - border_px

    WNDPROC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)

    def wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            if hdc:
                red = gdi32.CreateSolidBrush(0x0000FF)
                r = RECT()
                user32.GetClientRect(hwnd, ctypes.byref(r))
                user32.FillRect(hdc, ctypes.byref(r), red)
                gdi32.DeleteObject(red)
                user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wnd_proc_cb = WNDPROC(wnd_proc)
    _keep = [wnd_proc_cb]

    class_name = "KFRectBlink_%s" % threading.get_ident()
    class_name_buf = ctypes.c_wchar_p(class_name)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = ctypes.cast(wnd_proc_cb, ctypes.c_void_p)
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = ctypes.cast(class_name_buf, ctypes.c_void_p)

    if not user32.RegisterClassExW(ctypes.byref(wc)):
        logger.warning("RegisterClassExW failed")
        return

    hwnd = user32.CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE,
        class_name,
        None,
        WS_POPUP,
        x,
        y,
        width,
        height,
        0,
        0,
        wc.hInstance,
        None,
    )
    if not hwnd:
        logger.warning("CreateWindowExW failed")
        return

    try:
        rgn_outer = gdi32.CreateRectRgn(0, 0, width, height)
        rgn_inner = gdi32.CreateRectRgn(border_px, border_px, width - border_px, height - border_px)
        rgn_frame = gdi32.CreateRectRgn(0, 0, 0, 0)
        gdi32.CombineRgn(rgn_frame, rgn_outer, rgn_inner, RGN_DIFF)
        user32.SetWindowRgn(hwnd, rgn_frame, 1)
        gdi32.DeleteObject(rgn_outer)
        gdi32.DeleteObject(rgn_inner)

        user32.ShowWindow(hwnd, SW_HIDE)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

        deadline = time.monotonic() + max(0.2, duration_seconds)
        visible = False
        msg = MSG()
        while time.monotonic() < deadline:
            visible = not visible
            user32.ShowWindow(hwnd, SW_SHOW if visible else SW_HIDE)
            user32.InvalidateRect(hwnd, None, 1)
            end_tick = time.monotonic() + max(0.05, interval_seconds)
            while time.monotonic() < end_tick:
                while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    if msg.message == WM_QUIT:
                        return
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.01)
    finally:
        try:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            msg = MSG()
            for _ in range(20):
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    if msg.message == WM_QUIT:
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.01)
        except Exception:
            pass


def blink_rect(
    rect: tuple[int, int, int, int],
    duration_seconds: float = 2.0,
    interval_seconds: float = 0.2,
    border_px: int = 3,
) -> bool:
    """在 Windows 上对指定矩形做红框闪烁提示。"""
    try:
        import sys

        if sys.platform != "win32":
            return False
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            return False
        t = threading.Thread(
            target=_blink_overlay_thread,
            args=(rect, duration_seconds, interval_seconds, border_px),
            daemon=True,
        )
        t.start()
        return True
    except Exception as e:
        logger.warning("blink_rect failed: %s", e)
        return False

