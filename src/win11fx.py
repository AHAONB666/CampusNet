# decompyle3 version 3.8.0
# Python bytecode 3.8
# Decompiled from: Python 3.8.10 (tags/v3.8.10:3d8993a, May  3 2021, 11:48:03) [MSC v.1928 64 bit (AMD64)]
# Embedded file name: win11fx.py
"""Windows 11 窗口质感 + 动画缓动工具

圆角裁剪 / 亚克力 / 深色标题栏 / 缓动曲线 / 颜色插值
全部用 ctypes 调用系统 API，无第三方依赖。
"""
import ctypes, math
from ctypes import wintypes
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

def _top_hwnd(root):
    """取真正的顶层窗口句柄（overrideredirect 窗口 winfo_id 可能是子窗口）"""
    try:
        root.update_idletasks()
        hwnd = root.winfo_id()
        parent = user32.GetParent(hwnd)
        return parent if parent else hwnd
    except Exception:
        return 0


def apply_round_corner(root, w, h, radius=22, dpi=1.0):
    """圆角裁剪：SetWindowRgn + CreateRoundRectRgn（兼容性最好）"""
    try:
        hwnd = _top_hwnd(root)
        if not hwnd:
            return False
        r = max(2, int(radius * dpi))
        rgn = gdi32.CreateRoundRectRgn(0, 0, int(w * 1) + 1, int(h) + 1, r * 2, r * 2)
        ok = user32.SetWindowRgn(hwnd, rgn, True)
        v = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(v), ctypes.sizeof(v))
        return bool(ok)
    except Exception:
        return False


def enable_acrylic(root, tint_abgr=0xCC0D0306):
    """亚克力毛玻璃（Win10 1803+ / Win11）。失败静默降级为纯色"""
    try:
        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ('AccentState', ctypes.c_int),
                ('AccentFlags', ctypes.c_int),
                ('GradientColor', ctypes.c_uint),
                ('AnimationId', ctypes.c_int),
            ]

        class WCADATA(ctypes.Structure):
            _fields_ = [
                ('Attribute', ctypes.c_int),
                ('Data', ctypes.c_void_p),
                ('SizeOfData', ctypes.c_size_t),
            ]

        accent = ACCENTPOLICY()
        accent.AccentState = 4
        accent.AccentFlags = 2
        accent.GradientColor = tint_abgr
        accent.AnimationId = 0
        data = WCADATA()
        data.Attribute = 19
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        fn = user32.SetWindowCompositionAttribute
        fn.argtypes = [wintypes.HWND, ctypes.POINTER(WCADATA)]
        return bool(fn(_top_hwnd(root), ctypes.byref(data)))
    except Exception:
        return False


def set_dwm_attr(root, attr, value):
    try:
        v = ctypes.c_int(value)
        return dwmapi.DwmSetWindowAttribute(_top_hwnd(root), attr, ctypes.byref(v),
                                            ctypes.sizeof(v)) == 0
    except Exception:
        return False


def set_dark_mode(root):
    """DWMWA_USE_IMMERSIVE_DARK_MODE = 20"""
    return set_dwm_attr(root, 20, 1)


def set_no_shadow(root, enable=True):
    """去掉系统投影（我们自己在画布上画更柔和的）"""
    try:
        return set_dwm_attr(root, 2, 0 if enable else 1)
    except Exception:
        return False
def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t):
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t ** 3
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def ease_out_quart(t):
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 4


def ease_out_back(t, overshoot=1.2):
    """带轻微回弹，用于窗口/元素入场"""
    t = max(0.0, min(1.0, t))
    c3 = overshoot + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + overshoot * (t - 1.0) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    """两个 #rrggbb 颜色按 t 插值"""
    t = max(0.0, min(1.0, t))
    a = c1.lstrip('#')
    b = c2.lstrip('#')
    r1, g1, b1 = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    r2, g2, b2 = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return '#%02x%02x%02x' % (int(lerp(r1, r2, t)), int(lerp(g1, g2, t)), int(lerp(b1, b2, t)))


def pulse(t, speed=1.0, lo=0.0, hi=1.0):
    """平滑呼吸值，t 为累计时间"""
    s = (math.sin(t * speed) + 1.0) / 2.0
    return lo + (hi - lo) * s


def draw_soft_shadow(canvas, x1, y1, x2, y2, bg, color='#000000', spread=8, layers=8, radius=0):
    """在画布上画柔和外阴影（多层半透明模拟）"""
    for i in range(layers, 0, -1):
        f = i / float(layers)
        pad = spread * f
        col = lerp_color(bg, color, 0.055 * (1.0 - f + 0.15))
        if radius:
            _round_rect(canvas, (x1 - pad), (y1 - pad), (x2 + pad), (y2 + pad), (radius + pad * 0.6),
              outline=col, width=1)
        else:
            canvas.create_rectangle((x1 - pad), (y1 - pad), (x2 + pad), (y2 + pad), outline=col,
              width=1)


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """画圆角矩形（用 polygon + smooth 近似）"""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [
     x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
     x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
     x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return (canvas.create_polygon)(pts, smooth=True, **kw)


def round_rect(canvas, x1, y1, x2, y2, r=8, **kw):
    """画圆角矩形（半径可省略，默认 8px）"""
    return _round_rect(canvas, x1, y1, x2, y2, r, **kw)
