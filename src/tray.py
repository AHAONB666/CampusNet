"""托盘图标：Win32 Shell_NotifyIcon 的最小实现，不引入第三方依赖。

线程模型：消息循环跑在独立守护线程里，窗口与图标都在该线程创建。
回调只做「登记动作」，由 Tk 主线程轮询执行，避免跨线程调用 Tk。
"""
import ctypes
import os
import sys
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

# 显式声明签名：不声明的话 ctypes 按 c_int 传参，LRESULT 会溢出
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.restype = wintypes.HWND
user32.TrackPopupMenu.restype = ctypes.c_int

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
IMAGE_ICON = 1
LR_LOADFROMFILE, LR_DEFAULTSIZE = 0x10, 0x40
MF_STRING, MF_SEPARATOR = 0x0, 0x800

CMD_SHOW, CMD_QUIT = 1, 2
SM_CXSMICON, SM_CYSMICON = 49, 50

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT)]


def asset_path(name):
    """打包后资源在 _MEIPASS，源码运行时在上级 assets 目录。"""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


class Tray(object):

    def __init__(self, on_show=None, on_quit=None, title="CampusNet",
                 icon_name="icon.ico"):
        self.on_show = on_show or (lambda: None)
        self.on_quit = on_quit or (lambda: None)
        self.title = title
        self.icon_name = icon_name
        self.hwnd = None
        self._ready = threading.Event()
        self._wndproc = WNDPROC(self._on_message)
        self._class = "CampusNetTrayWnd"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(3.0)

    # ---------------------------------------------------------- 线程内
    def _run(self):
        try:
            hinst = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinst
            wc.hIcon = 0
            wc.hCursor = 0
            wc.hbrBackground = 0
            wc.lpszMenuName = None
            wc.lpszClassName = self._class
            user32.RegisterClassW(ctypes.byref(wc))

            HWND_MESSAGE = wintypes.HWND(-3)
            self.hwnd = user32.CreateWindowExW(0, self._class, self.title, 0,
                                               0, 0, 0, 0, HWND_MESSAGE,
                                               None, hinst, None)
            if not self.hwnd:
                self._ready.set()
                return

            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAYICON
            nid.hIcon = self._load_icon()
            nid.szTip = self.title[:120]
            self._nid = nid
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
            self._ready.set()

            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            self._ready.set()

    def _load_icon(self):
        try:
            path = asset_path(self.icon_name)
            cx = user32.GetSystemMetrics(SM_CXSMICON)
            cy = user32.GetSystemMetrics(SM_CYSMICON)
            h = user32.LoadImageW(None, path, IMAGE_ICON, cx, cy,
                                  LR_LOADFROMFILE)
            if h:
                return h
        except Exception:
            pass
        try:
            return user32.LoadIconW(None, wintypes.LPCWSTR(32512))
        except Exception:
            return 0

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            low = lparam & 0xFFFF
            if low in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.on_show()
            elif low == WM_RBUTTONUP:
                self._popup(hwnd)
            return 0
        if msg == WM_CLOSE:
            try:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            except Exception:
                pass
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _popup(self, hwnd):
        try:
            menu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, MF_STRING, CMD_SHOW, "\u663e\u793a\u4e3b\u754c\u9762")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, "\u9000\u51fa")
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, pt.x, pt.y, 0,
                                        hwnd, None)
            user32.PostMessageW(hwnd, 0, 0, 0)
            user32.DestroyMenu(menu)
            if cmd == CMD_SHOW:
                self.on_show()
            elif cmd == CMD_QUIT:
                self.on_quit()
        except Exception:
            pass

    # ---------------------------------------------------------- 主线程
    def destroy(self):
        """请求托盘线程退出，并等它真正结束。

        必须等待：托盘线程是 daemon，主线程若先走，解释器终结时
        该线程可能仍挂在 Win32 调用里，随后进程以堆损坏报错退出
        （alloc: invalid block）。
        """
        try:
            if self.hwnd:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
        try:
            if self._thread.is_alive():
                self._thread.join(2.0)
        except Exception:
            pass
