"""
Windows 区域截图：全屏半透明遮罩，按住 Ctrl 并拖动鼠标框选区域，松开后截取该区域。
仅 Windows 使用，需 PIL (ImageGrab)。
"""
import logging
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_region_result: Optional[tuple[int, int, int, int]] = None  # (left, top, right, bottom)
_region_done = threading.Event()


def _overlay_thread(
    templates_dir: Path,
    on_done: Callable[[Optional[Path]], None],
) -> None:
    """全屏半透明遮罩，Ctrl+左键拖动框选，松开后截取区域并保存，回调文件路径或 None。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    SM_CXSCREEN = 0
    SM_CYSCREEN = 1
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_MOUSEMOVE = 0x0200
    WM_PAINT = 0x000F
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WM_KEYDOWN = 0x0100
    VK_CONTROL = 0x11
    VK_ESCAPE = 0x1B
    WS_EX_LAYERED = 0x00080000
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TRANSPARENT = 0x00000020
    WS_POPUP = 0x80000000
    LWA_ALPHA = 0x2
    RGN_DIFF = 4
    BORDER = 4  # 选区框边框宽度（独立窗口，非分层，保证可见）

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("style", ctypes.c_ulong),
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

    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.LoadCursorW.restype = ctypes.c_void_p
    user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    IDC_CROSS = 32515  # 十字光标，便于框选

    wnd_proc_cb = None
    selecting = False
    start_x, start_y = 0, 0
    end_x, end_y = 0, 0
    hwnd_frame = [None]  # 独立选区框窗口（非分层），保证虚框可见

    def update_frame_window(rect: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            if hwnd_frame[0]:
                user32.MoveWindow(hwnd_frame[0], -1000, -1000, 1, 1, 1)
            return
        x = left - BORDER
        y = top - BORDER
        ww = (right - left) + 2 * BORDER
        hh = (bottom - top) + 2 * BORDER
        if hwnd_frame[0] is None:
            hwnd_frame[0] = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TRANSPARENT, frame_class_name, None, WS_POPUP,
                -1000, -1000, 1, 1, 0, 0, kernel32.GetModuleHandleW(None), None,
            )
            if hwnd_frame[0]:
                user32.ShowWindow(hwnd_frame[0], 5)
        if not hwnd_frame[0]:
            return
        user32.MoveWindow(hwnd_frame[0], x, y, ww, hh, 1)
        rgn_outer = gdi32.CreateRectRgn(0, 0, ww, hh)
        rgn_inner = gdi32.CreateRectRgn(BORDER, BORDER, ww - BORDER, hh - BORDER)
        rgn_frame = gdi32.CreateRectRgn(0, 0, 0, 0)
        gdi32.CombineRgn(rgn_frame, rgn_outer, rgn_inner, RGN_DIFF)
        user32.SetWindowRgn(hwnd_frame[0], rgn_frame, 1)
        gdi32.DeleteObject(rgn_outer)
        gdi32.DeleteObject(rgn_inner)

    def get_rect() -> tuple[int, int, int, int]:
        left = min(start_x, end_x)
        right = max(start_x, end_x)
        top = min(start_y, end_y)
        bottom = max(start_y, end_y)
        if right - left < 2 or bottom - top < 2:
            return (0, 0, 0, 0)
        return (left, top, right, bottom)

    WNDPROC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)

    def wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        nonlocal selecting, start_x, start_y, end_x, end_y
        if msg == WM_LBUTTONDOWN:
            if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
                selecting = True
                start_x = lparam & 0xFFFF
                start_y = (lparam >> 16) & 0xFFFF
                end_x, end_y = start_x, start_y
                update_frame_window(get_rect())
                user32.InvalidateRect(hwnd, None, 1)
            return 0
        if msg == WM_MOUSEMOVE:
            if selecting:
                end_x = lparam & 0xFFFF
                end_y = (lparam >> 16) & 0xFFFF
                update_frame_window(get_rect())
                user32.InvalidateRect(hwnd, None, 1)
            return 0
        if msg == WM_LBUTTONUP:
            if selecting:
                selecting = False
                if hwnd_frame[0]:
                    user32.DestroyWindow(hwnd_frame[0])
                    hwnd_frame[0] = None
                left, top, right, bottom = get_rect()
                user32.InvalidateRect(hwnd, None, 1)
                if right > left and bottom > top:
                    try:
                        from PIL import ImageGrab
                        import time
                        templates_dir.mkdir(parents=True, exist_ok=True)
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        path = templates_dir / f"capture_{ts}.png"
                        img = ImageGrab.grab(bbox=(left, top, right, bottom))
                        img.save(str(path))
                        on_done(path)
                    except Exception as e:
                        logger.warning("region capture save: %s", e)
                        on_done(None)
                else:
                    on_done(None)
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return 0
        if msg == WM_KEYDOWN and wparam == VK_ESCAPE:
            selecting = False
            if hwnd_frame[0]:
                user32.DestroyWindow(hwnd_frame[0])
                hwnd_frame[0] = None
            on_done(None)
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return 0
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            if hdc:
                r = RECT()
                user32.GetClientRect(hwnd, ctypes.byref(r))
                gray = gdi32.CreateSolidBrush(0x808080)
                gdi32.FillRect(hdc, ctypes.byref(r), gray)
                gdi32.DeleteObject(gray)
                user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == WM_CLOSE:
            if hwnd_frame[0]:
                user32.DestroyWindow(hwnd_frame[0])
                hwnd_frame[0] = None
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wnd_proc_cb = WNDPROC(wnd_proc)

    user32.CreateWindowExW.argtypes = [
        ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    user32.DefWindowProcW.restype = ctypes.c_void_p

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_ulong),
            ("wParam", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("time", ctypes.c_ulong),
            ("pt", ctypes.c_long * 2),
        ]

    def frame_wnd_proc(fhwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(fhwnd, ctypes.byref(ps))
            if hdc:
                r = RECT()
                user32.GetClientRect(fhwnd, ctypes.byref(r))
                red = gdi32.CreateSolidBrush(0x0000FF)
                gdi32.FillRect(hdc, ctypes.byref(r), red)
                gdi32.DeleteObject(red)
                user32.EndPaint(fhwnd, ctypes.byref(ps))
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(fhwnd, msg, wparam, lparam)

    frame_wnd_proc_cb = WNDPROC(frame_wnd_proc)
    _keep_frame_proc = [frame_wnd_proc_cb]
    frame_class_name = "KFRegionFrame_%s" % threading.get_ident()
    _frame_class_buf = ctypes.c_wchar_p(frame_class_name)
    wc_frame = WNDCLASSEXW()
    wc_frame.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc_frame.lpfnWndProc = ctypes.cast(frame_wnd_proc_cb, ctypes.c_void_p)
    wc_frame.hInstance = kernel32.GetModuleHandleW(None)
    wc_frame.lpszClassName = ctypes.cast(_frame_class_buf, ctypes.c_void_p)
    if not user32.RegisterClassExW(ctypes.byref(wc_frame)):
        logger.warning("RegisterClassExW failed (region frame)")
    # 若框窗口类注册失败，update_frame_window 中 CreateWindow 会失败，不影响主流程

    try:
        class_name = "KFRegionCapture_%s" % threading.get_ident()
        _class_name_buf = ctypes.c_wchar_p(class_name)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(wnd_proc_cb, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_CROSS))
        wc.lpszClassName = ctypes.cast(_class_name_buf, ctypes.c_void_p)
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            logger.warning("RegisterClassExW failed (region capture)")
            on_done(None)
            return

        cx = user32.GetSystemMetrics(SM_CXSCREEN)
        cy = user32.GetSystemMetrics(SM_CYSCREEN)
        hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST,
            class_name,
            "RegionCapture",
            WS_POPUP,
            0, 0, cx, cy,
            0, 0, kernel32.GetModuleHandleW(None), None,
        )
        if not hwnd:
            logger.warning("CreateWindowExW region overlay failed")
            on_done(None)
            return

        if not user32.SetLayeredWindowAttributes(hwnd, 0, 180, LWA_ALPHA):
            logger.warning("SetLayeredWindowAttributes failed")
        user32.ShowWindow(hwnd, 5)

        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.DestroyWindow(hwnd)
    except Exception as e:
        logger.exception("region capture overlay: %s", e)
        on_done(None)


# 阶段一：等待用户按热键（切换好目标窗口后再按）
_HOTKEY_MOD = 0x0002 | 0x0004   # MOD_CONTROL | MOD_SHIFT
_HOTKEY_VK = 0x52                # 'R'
_HOTKEY_ID = 2


def _hotkey_listener_thread(hwnd_out: list, hotkey_fired: threading.Event) -> None:
    """仅注册全局热键 Ctrl+Shift+R，收到后设置 hotkey_fired 并退出。不阻塞用户切换窗口。"""
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    WM_HOTKEY = 0x0312
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WS_POPUP = 0x80000000

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("style", ctypes.c_ulong),
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

    WNDPROC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)

    def wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_HOTKEY:
            hotkey_fired.set()
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    user32.DefWindowProcW.restype = ctypes.c_void_p

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_ulong),
            ("wParam", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("time", ctypes.c_ulong),
            ("pt", ctypes.c_long * 2),
        ]

    try:
        wnd_proc_cb = WNDPROC(wnd_proc)
        class_name = "KFRegionHotkey_%s" % threading.get_ident()
        _class_name_buf = ctypes.c_wchar_p(class_name)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(wnd_proc_cb, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = ctypes.cast(_class_name_buf, ctypes.c_void_p)
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            return
        user32.CreateWindowExW.argtypes = [
            ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        user32.CreateWindowExW.restype = ctypes.c_void_p
        hwnd = user32.CreateWindowExW(
            0, class_name, None, WS_POPUP,
            -1000, -1000, 1, 1, 0, 0, kernel32.GetModuleHandleW(None), None,
        )
        if not hwnd:
            return
        hwnd_out.append(hwnd)
        if not user32.RegisterHotKey(hwnd, _HOTKEY_ID, _HOTKEY_MOD, _HOTKEY_VK):
            logger.warning("RegisterHotKey Ctrl+Shift+R failed")
            user32.DestroyWindow(hwnd)
            return
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        try:
            user32.UnregisterHotKey(hwnd, _HOTKEY_ID)
        except Exception:
            pass
        user32.DestroyWindow(hwnd)
    except Exception as e:
        logger.debug("hotkey listener: %s", e)


def run_capture_region_session(templates_dir: Path, timeout: float = 120.0) -> Optional[Path]:
    """
    启动区域截图（两阶段）：
    1) 先等待用户按 Ctrl+Shift+R（可先切换到目标窗口再按）；
    2) 出现全屏半透明遮罩后，按住 Ctrl 并拖动鼠标框选区域，松开即截取并保存。
    返回保存的文件路径，超时或取消返回 None。仅 Windows 有效。
    """
    global _region_result, _region_done
    if sys.platform != "win32":
        return None

    # 阶段一：等待全局热键 Ctrl+Shift+R（此时可自由切换窗口）
    hotkey_hwnd: list = []
    hotkey_fired = threading.Event()
    hotkey_thread = threading.Thread(
        target=_hotkey_listener_thread,
        args=(hotkey_hwnd, hotkey_fired),
        daemon=True,
    )
    hotkey_thread.start()
    # 等热键线程把 hwnd 写进去
    for _ in range(50):
        if hotkey_hwnd:
            break
        threading.Event().wait(0.05)
    ok = hotkey_fired.wait(timeout=timeout)
    if not ok and hotkey_hwnd:
        try:
            user32 = __import__("ctypes").windll.user32
            user32.PostMessageW(hotkey_hwnd[0], 0x0010, 0, 0)  # WM_CLOSE
        except Exception:
            pass
    hotkey_thread.join(timeout=2.0)
    if not hotkey_fired.is_set():
        return None

    # 阶段二：显示遮罩，Ctrl+拖动框选
    _region_result = None
    _region_done.clear()

    def on_done(path: Optional[Path]) -> None:
        global _region_result
        _region_result = path
        _region_done.set()

    t = threading.Thread(target=_overlay_thread, args=(templates_dir, on_done), daemon=True)
    t.start()
    _region_done.wait(timeout=60.0)
    return _region_result
