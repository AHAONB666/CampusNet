# -*- coding: utf-8 -*-
"""仿iOS校园网 —— 桌面启动器

把内置的 CampusNet-iOS.html 交给系统上的 Edge / Chrome 以「应用模式」打开，
得到一个无地址栏、无标签页的独立窗口，外观接近原生桌面程序。

选择这份实现的原因：
  * 页面本身是纯前端（零依赖），不需要 Web 服务；
  * 用系统已有的 Chromium 内核渲染，体积只有几百 KB，
    不必拖一个 Electron / CEF 运行时进来（那会多出 100MB 以上）；
  * 应用模式（--app）没有浏览器外壳，任务栏图标与窗口标题由页面决定。

若系统没有 Edge / Chrome，退化为默认浏览器打开，保证功能不丢。
"""

import os
import sys
import time
import subprocess

APP_NAME = "懒得连校园网"
HTML_NAME = "CampusNet-iOS.html"

# 手机竖屏比例：420 × 860（约 1:2.05，比 iPhone 15 的 1:2.17 略宽，
# 让状态卡的 2×2 数据块在 390–420 之间不至于太挤）。
# 页面的移动端断点是 768，这个宽度会命中最紧凑的单列 + 底部 Tab Bar 布局。
PHONE_W = 420
PHONE_H = 860


def window_geometry():
    """返回 (尺寸, 位置)：固定手机竖屏，屏幕装不下就收高，并居中放置。

    用 SPI_GETWORKAREA 取工作区（已扣掉任务栏）。本进程是 DPI 无感知的，
    拿到的坐标与 --window-size / --window-position 是同一套单位，不必再做 DPI 换算。
    """
    width, height = PHONE_W, PHONE_H
    x = y = None
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            work_w = rect.right - rect.left
            work_h = rect.bottom - rect.top
            # 留 40px 给标题栏与边距；低于 560 就没有手机感了，保底
            height = max(560, min(PHONE_H, work_h - 40))
            x = rect.left + max(0, (work_w - width) // 2)
            y = rect.top + max(0, (work_h - height) // 2)
    except Exception:
        pass

    size = "%d,%d" % (width, height)
    pos = None if x is None else "%d,%d" % (x, y)
    return size, pos


def asset_path(name):
    """PyInstaller 单文件模式下资源被解到 _MEIPASS，源码运行时取同级目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _reg_paths():
    """从注册表补几个非默认安装位置（用户版 Edge、Chrome Beta 等）。"""
    found = []
    try:
        import winreg
    except ImportError:
        return found

    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
    ]
    for root, path in keys:
        try:
            with winreg.OpenKey(root, path) as k:
                value, _ = winreg.QueryValueEx(k, "")
                if value and os.path.isfile(value):
                    found.append(value)
        except OSError:
            continue
    return found


def find_chromium():
    """按优先级找一个 Chromium 系浏览器。"""
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    candidates = [
        os.path.join(program_files_x86, r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(program_files, r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(local, r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(program_files, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(program_files_x86, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
    ]
    candidates.extend(_reg_paths())

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def profile_dir():
    """独立用户数据目录：避免和日常浏览器共用配置，也避免第二次启动附着到旧窗口。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "CampusNetIOS", "profile")
    try:
        os.makedirs(path)
    except OSError:
        pass
    return path


def find_window():
    """找本应用的窗口句柄（按标题精确匹配）。

    刻意不要求可见：收进托盘后窗口是隐藏状态，这时再次双击 exe
    应该把它叫回来，而不是又开一份。
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hits = []
        proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value == APP_NAME:
                    hits.append(hwnd)
            return True

        user32.EnumWindows(proc(_cb), 0)
        return hits[0] if hits else None
    except Exception:
        return None


def restore_window(hwnd):
    """把窗口从托盘/最小化状态叫回来，并恢复任务栏按钮。"""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        SW_RESTORE, SW_SHOW = 9, 5

        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_APPWINDOW)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def hide_to_tray(hwnd):
    """最小化时从任务栏摘掉并隐藏窗口，只留托盘图标。

    Edge 的窗口属于另一个进程，改不了它的窗口过程（WNDPROC 不能跨进程），
    所以这里用「轮询 IsIconic + 摘 WS_EX_APPWINDOW」代替钩子，
    效果一样：点最小化 → 任务栏消失 → 右下角托盘还在。
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        SW_HIDE = 0

        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_APPWINDOW)
        user32.ShowWindow(hwnd, SW_HIDE)
        return True
    except Exception:
        return False


def pump_once(interval=0.35):
    """等待间隔，顺便让主线程保持可响应。"""
    time.sleep(interval)


def is_window(hwnd):
    try:
        import ctypes
        return bool(ctypes.windll.user32.IsWindow(hwnd))
    except Exception:
        return False


def is_iconic(hwnd):
    try:
        import ctypes
        return bool(ctypes.windll.user32.IsIconic(hwnd))
    except Exception:
        return False


def promote_tray_icon():
    """把本程序的托盘图标从「隐藏的图标(∧)」提到任务栏常显。

    Win11 为每个托盘图标在 HKCU\\Control Panel\\NotifyIconSettings 下建一个项，
    靠 IsPromoted 决定是否常驻任务栏；首次出现默认是 0（收进 ∧）。
    这里按 ExecutablePath 找到自己那一项，把 IsPromoted 置 1。
    只写当前用户的 HKCU，不需要管理员权限，也不动系统其它设置。
    """
    try:
        import winreg
    except ImportError:
        return False

    try:
        exe = os.path.normcase(os.path.abspath(sys.executable))
    except Exception:
        return False

    root_path = r"Control Panel\NotifyIconSettings"
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, root_path, 0,
                              winreg.KEY_READ | winreg.KEY_WRITE)
    except OSError:
        return False

    changed = False
    index = 0
    while True:
        try:
            sub = winreg.EnumKey(root, index)
        except OSError:
            break
        index += 1
        try:
            key = winreg.OpenKey(root, sub, 0, winreg.KEY_READ | winreg.KEY_WRITE)
        except OSError:
            continue
        try:
            try:
                path, _ = winreg.QueryValueEx(key, "ExecutablePath")
            except OSError:
                continue
            if not path or os.path.normcase(path) != exe:
                continue
            try:
                current, _ = winreg.QueryValueEx(key, "IsPromoted")
            except OSError:
                current = None
            if current != 1:
                winreg.SetValueEx(key, "IsPromoted", 0, winreg.REG_DWORD, 1)
                changed = True
        finally:
            key.Close()

    root.Close()
    return changed


def find_tray_window():
    """找本程序已经开着的托盘宿主窗口（窗口关掉后它仍在）。"""
    try:
        import ctypes
        return ctypes.windll.user32.FindWindowW("CampusNetTrayWnd", None) or None
    except Exception:
        return None


def ask_existing_to_show(tray_hwnd):
    """让已经在跑的那份把窗口叫出来（等价于点一下托盘图标）。"""
    try:
        import ctypes

        WM_APP = 0x8000
        WM_TRAYICON = WM_APP + 1
        WM_LBUTTONUP = 0x0202
        ctypes.windll.user32.PostMessageW(tray_hwnd, WM_TRAYICON, 0, WM_LBUTTONUP)
        return True
    except Exception:
        return False


def kill_window_process(hwnd):
    """退出时按窗口 pid 结束整个 Edge 进程树（含渲染进程），不留后台残留。"""
    try:
        import ctypes
        from ctypes import wintypes

        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid.value)],
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass



def clear_stale_lock(pdir):
    """清掉上次被强杀留下的单实例锁。

    Edge 被强制结束时会残留 SingletonLock，下次启动会变成「进程活着但没有窗口」，
    表现就是双击没反应。删掉这几个锁文件即可恢复；正常退出时它们本来就会消失。
    """
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            target = os.path.join(pdir, name)
            if os.path.exists(target) or os.path.islink(target):
                os.unlink(target)
        except OSError:
            pass


def to_file_url(path):
    """转成 file:/// 形式，处理空格与非 ASCII（中文桌面路径很常见）。"""
    p = os.path.abspath(path).replace("\\", "/")
    from urllib.parse import quote
    return "file:///" + quote(p, safe="/:")


def fail(message):
    """无窗口程序里这行是唯一的可见反馈，不能省。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    except Exception:
        pass
    sys.exit(1)


def main():
    html = asset_path(HTML_NAME)
    if not os.path.isfile(html):
        fail("找不到页面文件：%s" % html)

    url = to_file_url(html)
    browser = find_chromium()

    if not browser:
        # 没有 Chromium 内核就交给默认浏览器，功能仍然可用，只是多了浏览器外壳
        try:
            os.startfile(html)
        except OSError:
            fail("未找到可用的浏览器，无法打开页面。\n路径：%s" % html)
        return

    # 已经开着就置前，不再开第二份（也避免两个进程抢同一个配置目录）
    hwnd = find_window()
    if hwnd:
        restore_window(hwnd)
        return

    # 窗口关了但托盘还活着：让那一份把窗口重新叫出来，同样不再开第二份
    tray_hwnd = find_tray_window()
    if tray_hwnd:
        ask_existing_to_show(tray_hwnd)
        return

    pdir = profile_dir()
    clear_stale_lock(pdir)

    size, pos = window_geometry()

    args = [
        browser,
        "--app=" + url,
        "--window-size=" + size,
        "--user-data-dir=" + pdir,
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",                    # 不弹「同步浏览数据」推广框
        "--disable-background-networking",
        "--disable-features=msEdgeSidebarV2,msEdgeCollections,msEdgeSyncPromo,"
        "EdgeSyncPromo,SigninPromo,msImplicitSignin",
    ]
    if pos:
        args.append("--window-position=" + pos)

    creation = 0
    if os.name == "nt":
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    state = {"hwnd": None, "hidden": False, "quit": False}

    def spawn():
        """拉起窗口并等它出现；返回句柄（失败返回 None）。"""
        clear_stale_lock(pdir)
        try:
            subprocess.Popen(args, creationflags=creation)
        except OSError:
            return None
        deadline = time.time() + 25
        while time.time() < deadline and not state["quit"]:
            h = find_window()
            if h:
                state["hwnd"] = h
                state["hidden"] = False
                return h
            time.sleep(0.3)
        return None

    def on_show():
        h = state["hwnd"]
        if h and is_window(h):
            state["hidden"] = False
            restore_window(h)
        else:
            # 窗口已经被关掉：重新拉起一个，托盘图标始终不断
            spawn()

    def on_quit():
        state["quit"] = True
        h = state["hwnd"]
        if h:
            kill_window_process(h)

    if not spawn():
        fail("窗口没能启动。\n请手动打开：%s" % html)
        return

    tray_icon = None
    try:
        import tray as tray_mod

        tray_icon = tray_mod.Tray(on_show=on_show, on_quit=on_quit,
                                  title=APP_NAME)
        # 把图标从「隐藏的图标」提升到任务栏常显，再刷新一次让资源管理器读到
        if promote_tray_icon():
            tray_icon.refresh()
    except Exception:
        tray_icon = None

    try:
        while not state["quit"]:
            h = state["hwnd"]
            if h and not is_window(h):
                # 用户点了 ✕：窗口没了，但托盘继续留着，等他点图标重开
                state["hwnd"] = None
                h = None
            if h and not state["hidden"] and is_iconic(h):
                # 点最小化：收进托盘，任务栏不再占位
                hide_to_tray(h)
                state["hidden"] = True
            time.sleep(0.35)
    finally:
        if tray_icon:
            tray_icon.destroy()
        if state["hwnd"]:
            kill_window_process(state["hwnd"])



if __name__ == "__main__":
    main()
