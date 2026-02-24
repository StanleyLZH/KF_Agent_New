"""
Windows 控件捕获：桌面红框 overlay + 热键 Ctrl+Shift+C 捕获，无需点击目标控件。
仅 Windows 使用，需 pywinauto、pyautogui、comtypes。
优先使用 UIA RawViewWalker 获取最内层控件（千牛等 Electron 应用），备选 MSAA。
"""
import logging
import sys
import threading
import warnings
from typing import Any, Callable, Optional

# 抑制 pywinauto 在子线程中的 STA 提示（已在本线程 CoInitializeEx STA）
warnings.filterwarnings("ignore", message=".*STA COM.*", category=UserWarning)

logger = logging.getLogger(__name__)

# 捕获结果：由 overlay 线程写入，主线程读取
_capture_result: Optional[dict[str, Any]] = None
_capture_done = threading.Event()

# 边框宽度
BORDER = 3

# 面积阈值：超过此值认为是大块容器，尝试 RawViewWalker/MSAA 获取更细粒度
_LARGE_AREA_THRESHOLD = 200000


def _get_rect_from_elem(elem) -> Optional[tuple[int, int, int, int]]:
    """从元素获取 (left, top, right, bottom)，失败返回 None。"""
    try:
        w = elem.wrapper_object() if hasattr(elem, "wrapper_object") else elem
        r = w.rectangle()
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        try:
            ei = elem.element_info if hasattr(elem, "element_info") else elem
            if hasattr(ei, "rectangle"):
                r = ei.rectangle
                return (r.left, r.top, r.right, r.bottom)
            if hasattr(ei, "rect"):
                r = ei.rect
                return (r.left, r.top, r.right, r.bottom) if hasattr(r, "left") else tuple(r)[:4]
        except Exception:
            pass
    return None


def _get_smallest_element_at_point(elem, x: int, y: int, max_depth: int = 8) -> Any:
    """
    从 elem 出发，找到包含 (x,y) 的最小子元素（深度模式，类似影刀）。
    若存在更小的子控件包含该点，则返回该子控件；否则返回 elem。
    """
    if max_depth <= 0:
        return elem
    try:
        rect = _get_rect_from_elem(elem)
        if rect is None:
            return elem
        l, t, r, b = rect
        if l >= r or t >= b:
            return elem
        best_child = None
        best_area = (r - l) * (b - t)
        children = elem.children() if hasattr(elem, "children") else []
        for child in children:
            try:
                child_rect = _get_rect_from_elem(child)
                if child_rect is None:
                    continue
                cl, ct, cr, cb = child_rect
                if cl <= x <= cr and ct <= y <= cb:
                    area = (cr - cl) * (cb - ct)
                    if 0 < area < best_area:
                        best_area = area
                        best_child = child
            except Exception:
                continue
        if best_child is not None:
            return _get_smallest_element_at_point(best_child, x, y, max_depth - 1)
    except Exception:
        pass
    return elem


def _get_control_and_rect_via_uia_raw(x: int, y: int) -> tuple[Optional[dict[str, Any]], Optional[tuple[int, int, int, int]]]:
    """
    使用 UIA RawViewWalker 直接遍历完整树，获取包含 (x,y) 的最内层控件。
    RawView 比 ControlView 包含更多元素，对千牛等 Electron 应用可能暴露更细粒度控件。
    """
    try:
        import comtypes.client
        from ctypes.wintypes import tagPOINT

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import IUIAutomation

        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=IUIAutomation,
        )
        pt = tagPOINT(x, y)
        elem = uia.ElementFromPoint(pt)
        if elem is None:
            return None, None

        walker = uia.RawViewWalker
        if walker is None:
            return None, None

        def _rect_from_element(el) -> Optional[tuple[int, int, int, int]]:
            try:
                r = el.CurrentBoundingRectangle
                return (r.left, r.top, r.right, r.bottom)
            except Exception:
                return None

        def _smallest_at_point(parent, px: int, py: int, depth: int = 12) -> Any:
            if depth <= 0:
                return parent
            try:
                child = walker.GetFirstChildElement(parent)
                best = None
                best_area = 999999999
                while child is not None:
                    try:
                        rc = _rect_from_element(child)
                        if rc:
                            cl, ct, cr, cb = rc
                            if cl <= px <= cr and ct <= py <= cb:
                                area = (cr - cl) * (cb - ct)
                                if 0 < area < best_area:
                                    best_area = area
                                    best = child
                    except Exception:
                        pass
                    try:
                        next_child = walker.GetNextSiblingElement(child)
                        child = next_child
                    except Exception:
                        break
                if best is not None:
                    return _smallest_at_point(best, px, py, depth - 1)
            except Exception:
                pass
            return parent

        elem = _smallest_at_point(elem, x, y)
        rect = _rect_from_element(elem)
        if rect is None:
            return None, None

        automation_id: Optional[str] = None
        control_type: Optional[str] = None
        name: Optional[str] = None
        try:
            automation_id = elem.CurrentAutomationId or None
        except Exception:
            pass
        try:
            # CurrentLocalizedControlType 为可读字符串（如 "按钮"），优先于 ControlType 枚举值
            control_type = elem.CurrentLocalizedControlType or None
        except Exception:
            pass
        if control_type is None:
            try:
                ct = elem.CurrentControlType
                control_type = str(ct) if ct else None
            except Exception:
                pass
        try:
            name = elem.CurrentName or None
        except Exception:
            pass

        window_title: Optional[str] = None
        window_class: Optional[str] = None
        try:
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            top = desktop.top_from_point(x, y)
            if top is not None:
                tw = top.wrapper_object()
                window_title = tw.window_text() or None
                window_class = tw.class_name() or None
        except Exception:
            pass

        control = {
            "window_title": window_title,
            "window_class": window_class,
            "control_id": None,
            "automation_id": automation_id,
            "control_type": control_type,
            "name": name,
        }
        return control, rect
    except Exception as e:
        logger.debug("_get_control_and_rect_via_uia_raw: %s", e)
        return None, None


def _get_control_and_rect_at(x: int, y: int) -> tuple[Optional[dict[str, Any]], Optional[tuple[int, int, int, int]]]:
    """
    返回 (控件属性字典, (left, top, right, bottom)) 或 (None, None)。
    优先使用 UIA RawViewWalker 获取最内层控件（千牛等 Electron 应用），否则回退到 pywinauto。
    """
    if sys.platform != "win32":
        return None, None

    # 1. 优先尝试 UIA RawViewWalker（完整树遍历，可识别 ControlView 中不可见的子元素）
    control, rect = _get_control_and_rect_via_uia_raw(x, y)
    if control is not None and rect is not None:
        return control, rect

    # 2. 回退到 pywinauto（ControlView + 深度模式 + win32 备选）
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        elem = desktop.from_point(x, y)
        if elem is None:
            return None, None
        elem = _get_smallest_element_at_point(elem, x, y)
        rect = _get_rect_from_elem(elem)
        if rect:
            area = (rect[2] - rect[0]) * (rect[3] - rect[1])
            if area > _LARGE_AREA_THRESHOLD:
                try:
                    desktop_win32 = Desktop(backend="win32")
                    elem_win32 = desktop_win32.from_point(x, y)
                    if elem_win32:
                        rect_win32 = _get_rect_from_elem(elem_win32)
                        if rect_win32:
                            a2 = (rect_win32[2] - rect_win32[0]) * (rect_win32[3] - rect_win32[1])
                            if 0 < a2 < area:
                                elem, rect = elem_win32, rect_win32
                except Exception:
                    pass
        window_title: Optional[str] = None
        window_class: Optional[str] = None
        control_id: Optional[int] = None
        automation_id: Optional[str] = None
        control_type: Optional[str] = None
        name: Optional[str] = None
        try:
            top = desktop.top_from_point(x, y)
            if top is not None:
                tw = top.wrapper_object()
                window_title = tw.window_text() or None
                window_class = tw.class_name() or None
        except Exception:
            pass
        try:
            w = elem.wrapper_object()
            name = w.window_text() or None
            if window_class is None:
                window_class = w.class_name() or None
        except Exception:
            pass
        try:
            ei = elem.element_info
            if hasattr(ei, "control_id"):
                control_id = getattr(ei, "control_id", None)
            if hasattr(ei, "automation_id"):
                automation_id = getattr(ei, "automation_id", None)
            elif hasattr(ei, "auto_id"):
                automation_id = getattr(ei, "auto_id", None)
            if hasattr(ei, "control_type"):
                ct = getattr(ei, "control_type", None)
                control_type = str(ct) if ct else None
            if name is None and hasattr(ei, "name"):
                name = getattr(ei, "name", None)
        except Exception:
            pass
        control = {
            "window_title": window_title,
            "window_class": window_class,
            "control_id": control_id,
            "automation_id": automation_id,
            "control_type": control_type,
            "name": name,
        }
        return control, rect
    except Exception as e:
        logger.warning("get_control_and_rect_at: %s", e)
        return None, None


def _overlay_thread(
    get_cursor: Callable[[], tuple[int, int]],
    on_done: Callable[[Optional[dict[str, Any]]], None],
) -> None:
    """红框 overlay + 热键 Ctrl+Shift+C 捕获（无需鼠标钩子，避免 ERROR_MOD_NOT_FOUND/1429）。"""
    import ctypes

    # 兼容 Python 3.13：不依赖 wintypes，全部用 ctypes 原生类型
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

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32
    ole32 = ctypes.windll.ole32
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    user32.CreateWindowExW.argtypes = [
        ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    user32.DefWindowProcW.restype = ctypes.c_void_p
    user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong]
    user32.RegisterHotKey.restype = ctypes.c_long
    user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.UnregisterHotKey.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_ulong,
    ]
    user32.SetWindowPos.restype = ctypes.c_long
    user32.PeekMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_uint]
    user32.PeekMessageW.restype = ctypes.c_long
    user32.TranslateMessage.argtypes = [ctypes.c_void_p]
    user32.TranslateMessage.restype = ctypes.c_long
    user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
    user32.DispatchMessageW.restype = ctypes.c_void_p
    user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    user32.PostMessageW.restype = ctypes.c_long

    try:
        ole32.CoInitializeEx(0, 0x2)
    except Exception:
        pass

    WM_TIMER = 0x0113
    WM_PAINT = 0x000F
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WM_HOTKEY = 0x0312
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    VK_C = 0x43
    HOTKEY_ID = 1
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000
    WS_POPUP = 0x80000000
    ID_TIMER = 1
    TIMER_MS = 50
    RGN_DIFF = 4
    HWND_TOPMOST = ctypes.c_void_p(-1)
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001

    current_rect: Optional[tuple[int, int, int, int]] = None
    hwnd_overlay = None

    def get_control_at_cursor() -> tuple[Optional[dict[str, Any]], Optional[tuple[int, int, int, int]]]:
        x, y = get_cursor()
        return _get_control_and_rect_at(x, y)

    # 无控件时显示在光标处的小红框（空心框，与控件框一致）
    FALLBACK_SIZE = 60
    FALLBACK_BORDER = 3

    def update_frame_window(hwnd: int, rect: Optional[tuple[int, int, int, int]]) -> None:
        if rect is None:
            try:
                cx, cy = get_cursor()
                x = cx - FALLBACK_SIZE // 2
                y = cy - FALLBACK_SIZE // 2
                user32.MoveWindow(hwnd, x, y, FALLBACK_SIZE, FALLBACK_SIZE, 1)
                rgn_outer = gdi32.CreateRectRgn(0, 0, FALLBACK_SIZE, FALLBACK_SIZE)
                rgn_inner = gdi32.CreateRectRgn(
                    FALLBACK_BORDER, FALLBACK_BORDER,
                    FALLBACK_SIZE - FALLBACK_BORDER, FALLBACK_SIZE - FALLBACK_BORDER,
                )
                rgn_frame = gdi32.CreateRectRgn(0, 0, 0, 0)
                gdi32.CombineRgn(rgn_frame, rgn_outer, rgn_inner, RGN_DIFF)
                user32.SetWindowRgn(hwnd, rgn_frame, 1)
                gdi32.DeleteObject(rgn_outer)
                gdi32.DeleteObject(rgn_inner)
                user32.InvalidateRect(hwnd, None, 1)
            except Exception:
                pass
            return
        left, top, right, bottom = rect
        w, h = right - left, bottom - top
        if w <= 0 or h <= 0:
            return
        x, y = left - BORDER, top - BORDER
        ww, hh = w + BORDER * 2, h + BORDER * 2
        user32.MoveWindow(hwnd, x, y, ww, hh, 1)
        rgn_outer = gdi32.CreateRectRgn(0, 0, ww, hh)
        rgn_inner = gdi32.CreateRectRgn(BORDER, BORDER, ww - BORDER, hh - BORDER)
        rgn_frame = gdi32.CreateRectRgn(0, 0, 0, 0)
        gdi32.CombineRgn(rgn_frame, rgn_outer, rgn_inner, RGN_DIFF)
        user32.SetWindowRgn(hwnd, rgn_frame, 1)
        gdi32.DeleteObject(rgn_outer)
        gdi32.DeleteObject(rgn_inner)
        user32.InvalidateRect(hwnd, None, 1)

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

    WNDPROC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)

    def wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        nonlocal current_rect
        if msg == WM_HOTKEY:
            try:
                x, y = get_cursor()
                control, _ = _get_control_and_rect_at(x, y)
                on_done(control)
            except Exception as e:
                logger.debug("WM_HOTKEY get_control: %s", e)
                on_done(None)
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return 0
        if msg == WM_TIMER:
            try:
                _, rect = get_control_at_cursor()
                if rect != current_rect:
                    current_rect = rect
                    update_frame_window(hwnd, rect)
            except Exception as e:
                logger.debug("WM_TIMER: %s", e)
            return 0
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

    def _last_error() -> int:
        return kernel32.GetLastError()

    # 64 位下 MSG 需与 Win32 一致，含 lPrivate 字段
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

    WM_QUIT = 0x0012
    PM_REMOVE = 0x0001

    try:
        class_name = "KFControlPicker_%s" % threading.get_ident()
        _class_name_buf = ctypes.c_wchar_p(class_name)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(wnd_proc_cb, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = ctypes.cast(_class_name_buf, ctypes.c_void_p)
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            logger.warning("RegisterClassExW failed, GetLastError=%s", _last_error())
            on_done(None)
            return

        hwnd_overlay = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE,
            class_name,
            None,
            WS_POPUP,
            -1000, -1000, 1, 1,
            0, 0, wc.hInstance, None,
        )
        if not hwnd_overlay:
            logger.warning("CreateWindowExW overlay failed, GetLastError=%s", _last_error())
            on_done(None)
            return

        user32.ShowWindow(hwnd_overlay, 5)
        # 再次置顶，避免被其他窗口挡住
        user32.SetWindowPos(hwnd_overlay, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        if not user32.RegisterHotKey(hwnd_overlay, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_C):
            logger.warning("RegisterHotKey failed, GetLastError=%s", _last_error())
            user32.DestroyWindow(hwnd_overlay)
            on_done(None)
            return

        # 用 PeekMessage 循环 + 手动更新红框，不依赖 WM_TIMER（避免消息未派发导致红框不更新、热键无反应）
        import time
        try:
            _, rect = get_control_at_cursor()
            update_frame_window(hwnd_overlay, rect)
        except Exception:
            update_frame_window(hwnd_overlay, None)
        msg = MSG()
        while True:
            if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                try:
                    _, rect = get_control_at_cursor()
                    if rect is None:
                        # 无控件时红框跟随光标，必须每次更新
                        current_rect = None
                        update_frame_window(hwnd_overlay, None)
                    elif rect != current_rect:
                        # 有控件时红框套住该控件，随控件不同大小变化
                        current_rect = rect
                        update_frame_window(hwnd_overlay, rect)
                except Exception:
                    pass
                time.sleep(0.05)
        user32.UnregisterHotKey(hwnd_overlay, HOTKEY_ID)
        user32.DestroyWindow(hwnd_overlay)
    except Exception as e:
        logger.exception("overlay_thread: %s", e)
        on_done(None)


def run_pick_control_session(timeout: float = 120.0) -> Optional[dict[str, Any]]:
    """
    启动控件捕获：红框 overlay，按 Ctrl+Shift+C 捕获当前光标下控件（不点击目标）。
    仅 Windows 有效。
    """
    global _capture_result, _capture_done
    if sys.platform != "win32":
        return None
    try:
        import pyautogui
    except ImportError:
        logger.warning("pyautogui not available for control picker")
        return None

    _capture_result = None
    _capture_done.clear()

    def get_cursor() -> tuple[int, int]:
        return pyautogui.position()

    def on_done(control: Optional[dict[str, Any]]) -> None:
        global _capture_result
        _capture_result = control
        _capture_done.set()

    t = threading.Thread(target=_overlay_thread, args=(get_cursor, on_done), daemon=True)
    t.start()
    _capture_done.wait(timeout=timeout)
    return _capture_result
