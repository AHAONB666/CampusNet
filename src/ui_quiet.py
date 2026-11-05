"""静蓝 Calm Utility —— CampusNet 界面

结构：
  · 窗口 420x644：顶部 44px 标题条 + 内容区 + 底部 64px 三标签导航
  · 三个页签：主页（状态）/ 我的（账号与学校）/ 设置（行为与外观）
  · 新手引导为独立全窗视图，不显示底部导航
  · 浅色 / 深色 / 跟随系统 三套主题
纯 tkinter Canvas 自绘，无第三方图形依赖。DPI 感知，按系统缩放绘制。
"""
import ctypes
from ctypes import wintypes
import json
import math
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import font as tkfont

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import autostart
import config
import guard as guard_mod
import netutil
import portal
import win11fx


# ---------------------------------------------------------------- 版式
# B · 编辑排版：无卡片，靠字号与头发线建立层级
W, H = 860, 580
PAD = 48
PADT = 38
PADB = 38
NAV_H = 30
LEFT, RIGHT = PAD, W - PAD
CX = W // 2
ROW_H = 44

UI = "Noto Sans SC"
NUM = "Segoe UI Variable Display"

_FONTS_READY = False


def _ensure_fonts(root=None):
    """按可用性回退字体，避免在没装 Noto Sans SC 的机器上退化成方块。"""
    global UI, NUM, _FONTS_READY
    if _FONTS_READY:
        return
    try:
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    if fams and UI not in fams:
        UI = "Microsoft YaHei UI" if "Microsoft YaHei UI" in fams else "Segoe UI"
    if fams and NUM not in fams:
        NUM = "Segoe UI"
    _FONTS_READY = True


# ---------------------------------------------------------------- 主题令牌
LIGHT = dict(
    name="浅色",
    bg="#FAFAF8", card="#FFFFFF", bar="#FAFAF8",
    text="#14140F", text2="#62625A", text3="#72726A",
    line="#E4E4DC", line2="#D8D8D0", div="#E4E4DC", card_line="#E4E4DC",
    line_strong="#14140F",
    ink="#14140F",
    accent="#14140F", acc_soft="#EDEDE8", on_accent="#FAFAF8",
    ok="#2F7D32", warn="#B26A00", err="#B3261E", err_soft="#F7E8E6",
    neu_soft="#F0F0EB", neu_sol="#D8D8D0", neu_gly="#8C8C84",
    divider_stat="#E4E4DC", chevron="#8C8C84", seg_bg="#EFEFEA",
    btn="#14140F", btn_fg="#FAFAF8",
    btn2="#F0F0EC", btn2_fg="#14140F",
    hover="#EDEDE8",
    sw_on="#14140F", sw_off="#D8D8D0", knob="#FAFAF8",
    track="#9C9C90",
)
DARK = dict(
    name="深色",
    bg="#111110", card="#1A1A18", bar="#111110",
    text="#F5F5F0", text2="#A0A099", text3="#8C8C84",
    line="#2A2A26", line2="#3A3A35", div="#2A2A26", card_line="#2A2A26",
    line_strong="#F5F5F0",
    ink="#F5F5F0",
    accent="#F5F5F0", acc_soft="#1E1E1B", on_accent="#111110",
    ok="#6BCB77", warn="#E0A458", err="#FF6B6B", err_soft="#2C1E1D",
    neu_soft="#1E1E1B", neu_sol="#3A3A35", neu_gly="#8C8C84",
    divider_stat="#2A2A26", chevron="#8A8A82", seg_bg="#1E1E1B",
    btn="#F5F5F0", btn_fg="#111110",
    btn2="#1E1E1C", btn2_fg="#F5F5F0",
    hover="#1C1C1A",
    sw_on="#F5F5F0", sw_off="#3A3A36", knob="#111110",
    track="#6E6E68",
)
PALETTES = {"light": LIGHT, "dark": DARK}


# ---------------------------------------------------------------- 新手引导文案
GUIDES = (
    ("01", "接入凭据", "先在「我的」填写账号与密码，信息只保存在本机。",
     ("我的 →「账号」可直接修改学号与密码",
      "密码用 Windows DPAPI 加密存本地",
      "拷到别的电脑要重新输密码")),
    ("02", "发起认证", "回到主页，一次点击即可提交认证。",
     ("点主页的「连接」提交认证",
      "在线后可用「重新检测」立即巡检",
      "失败会显示原因，账号问题可直接修改")),
    ("03", "自动重连", "按需要在「设置」开启连接行为。",
     ("设置 →「开机自动连接」与「断线自动重连」",
      "最小化到托盘会继续监测，关闭窗口会退出",
      "关闭自动重连不影响手动连接")),
    ("04", "多学校", "不止一所学校？添加并切换配置就行。",
     ("我的 →「学校与认证」可增删学校",
      "认证页留空 = 自动探测",
      "切换配置后主页状态即时刷新")),
)


# ---------------------------------------------------------------- DPI
def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return True
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:
        return False


def system_scale():
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, min(3.0, float(dpi) / 96.0))
    except Exception:
        return 1.0


enable_dpi_awareness()
S = system_scale()


def _f(family, px):
    return (family, -max(7, int(round(px * S))))


def _rr(c, x1, y1, x2, y2, r=8, **kw):
    return win11fx.round_rect(c, x1, y1, x2, y2, r, **kw)


# ---------------------------------------------------------------- 主题持久化
def _ui_state_path():
    try:
        return os.path.join(config.app_dir(), "ui.json")
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".campusnet-ui.json")


def load_theme_setting():
    try:
        with open(_ui_state_path(), "r", encoding="utf-8") as fh:
            val = (json.load(fh) or {}).get("theme")
        if val in ("light", "dark", "auto"):
            return val
    except Exception:
        pass
    return "light"


def save_theme_setting(val):
    try:
        path = _ui_state_path()
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh) or {}
            except Exception:
                data = {}
        data["theme"] = val
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def system_is_light():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return True


# ---------------------------------------------------------------- 流量
class Traffic(object):
    """本次运行流量：进程启动时取基线，之后差值即本次用量。"""

    def __init__(self):
        self.base = self._read()

    @staticmethod
    def _read():
        try:
            import psutil
            c = psutil.net_io_counters()
            return int(c.bytes_recv) + int(c.bytes_sent)
        except Exception:
            pass
        try:
            out = netutil.run("netstat -e")
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
                    return int(parts[0]) + int(parts[1])
        except Exception:
            pass
        return None

    def session(self):
        cur = self._read()
        if cur is None or self.base is None:
            return None
        diff = cur - self.base
        if diff < 0:
            self.base = cur
            return 0
        return diff


def human_bytes(n):
    if n is None:
        return "--"
    units = ("B", "KB", "MB", "GB", "TB")
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return ("%d %s" % (v, u)) if u == "B" else ("%.2f %s" % (v, u))
        v /= 1024.0
    return "--"


class QuietUI(object):

    def __init__(self, root, demo=False, fade=True):
        self.root = root
        self.demo = demo
        self.cfg = config.load() or {}
        self.state = guard_mod.State()
        self.guard = None
        self.traffic = Traffic()

        self.kind = "idle"
        self.view = "home"
        self.guide_step = 0

        self.online = False
        self.connecting = False
        self.error = ""
        self.ssid = "—"
        self.relogin = 0

        self.logs = []
        self._seen = 0
        self._online_since = None
        self._spin = 0.0
        self._last_sec = -1
        self._metrics_busy = False
        self._ip = ""
        self._signal = None
        self._bytes = None
        self._drag = (0, 0)
        self._auto_on = False
        self._rec_on = bool(self.cfg.get("auto_reconnect", True))
        self._spinner = None
        self._checking = False
        self._auth_generation = 0
        self._check_generation = 0
        self.sub_item = None
        self._editor = None
        self._editor_guard = False
        self._rows = {}
        self._focusables = []
        self._focus_tag = None
        self._keyboard_focus = False

        self.theme_setting = load_theme_setting()
        self.P = self._resolve_palette()

        _ensure_fonts(root)
        self.w, self.h = W, H
        self._maxed = False
        self._normal_size = (W, H)
        self.sw = int(round(self.w * S))
        self.sh = int(round(self.h * S))

        root.overrideredirect(True)
        root.title("CampusNet")
        root.geometry("%dx%d+%d+%d" % (self.sw, self.sh, 360, 90))
        root.configure(bg=self.P["bg"])

        self.c = tk.Canvas(root, width=self.sw, height=self.sh, bg=self.P["bg"],
                           highlightthickness=0, bd=0)
        self.c.pack(fill="both", expand=True)

        try:
            root.update_idletasks()
            win11fx.apply_round_corner(root, self.sw, self.sh, 12, 1.0)
            win11fx.set_no_shadow(root, True)
        except Exception:
            pass

        self._tray_q = []
        self.tray = None
        self._bind()
        self._sync_toggles()
        self._pick_initial_kind()
        self._render()
        self._init_tray()

        self._tick()
        if fade:
            self._fade(0.0)
        else:
            try:
                root.attributes("-alpha", 1.0)
            except Exception:
                pass

    # ------------------------------------------------------------ 主题
    def _resolve_palette(self):
        if self.theme_setting == "dark":
            return PALETTES["dark"]
        if self.theme_setting == "auto":
            return PALETTES["light"] if system_is_light() else PALETTES["dark"]
        return PALETTES["light"]

    def _dialog_theme(self):
        P = self.P
        return dict(bg=P["bg"], panel=P["card"], text=P["text"], text2=P["text2"],
                    primary=P["accent"], ok=P["ok"], warn=P["warn"], bad=P["err"],
                    mono="Consolas", ui=UI,
                    btn_bg=P["accent"], btn_fg=P["on_accent"],
                    btn2_bg=P["acc_soft"], btn2_fg=P["text"])

    def set_theme(self, val, persist=True):
        self.theme_setting = val
        if persist:
            save_theme_setting(val)
        self.P = self._resolve_palette()
        self.root.configure(bg=self.P["bg"])
        self.c.configure(bg=self.P["bg"])
        self._render()

    # ------------------------------------------------------------ 动效
    # Fluent 三曲线：所有动效共用，避免一页里出现两种节奏
    #   std  cubic-bezier(.33,0,.67,1)  250ms  通用
    #   dec  cubic-bezier(.1,.9,.2,1)   300ms  进入
    #   acc  cubic-bezier(.7,0,1,.5)    200ms  退出
    @staticmethod
    def _ease(name, t):
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        if name == "std":
            return t * t * (3.0 - 2.0 * t)
        if name == "acc":
            return t ** 2.2
        if name == "spring":
            u = t - 1.0
            return 1.0 + 2.70158 * u * u * u + 1.70158 * u * u
        return 1.0 - (1.0 - t) ** 3

    @staticmethod
    def _mix(c1, c2, p):
        try:
            a, b = c1.lstrip("#"), c2.lstrip("#")
            if len(a) >= 6 and len(b) >= 6:
                r1, g1, b1 = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
                r2, g2, b2 = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
                return "#%02x%02x%02x" % (
                    int(round(r1 + (r2 - r1) * p)),
                    int(round(g1 + (g2 - g1) * p)),
                    int(round(b1 + (b2 - b1) * p)))
        except Exception:
            pass
        return c2 if p > 0.5 else c1

    def _start_enter(self, dx=16, dur=0.30, curve="dec"):
        """整页进入：横向位移 + 由背景色渐显。Canvas 没有 alpha，用颜色插值代替。"""
        try:
            items = self.c.find_withtag("fx")
        except Exception:
            return
        self._fx = []
        for i in items:
            try:
                f = self.c.itemcget(i, "fill")
            except Exception:
                continue
            if f:
                self._fx.append((i, f))
        if not self._fx:
            return
        self._fx_t0 = time.time()
        self._fx_dur = max(0.08, dur)
        self._fx_dx = float(dx) * S
        self._fx_shift = 0.0
        self._fx_curve = curve
        self._fx_on = True
        if dx:
            try:
                self.c.move("fx", self._fx_dx, 0)
            except Exception:
                pass

    def _anim_step(self):
        if not getattr(self, "_fx_on", False):
            return
        t = (time.time() - self._fx_t0) / self._fx_dur
        p = 1.0 if t >= 1.0 else self._ease(self._fx_curve, t)
        bg = self.P["bg"]
        for i, target in self._fx:
            try:
                self.c.itemconfigure(
                    i, fill=(target if p >= 1.0 else self._mix(bg, target, p)))
            except Exception:
                pass
        if self._fx_dx:
            want = -self._fx_dx * p
            try:
                self.c.move("fx", want - self._fx_shift, 0)
            except Exception:
                pass
            self._fx_shift = want
        if t >= 1.0:
            self._fx_on = False
            self._fx = []

    def _hover(self, tag, on, color_on=None):
        """hover：底色插值到 hover 色（由 _tick 逐帧推进）。"""
        self._hv = (tag, bool(on), time.time(), color_on)

    def _hover_step(self):
        hv = getattr(self, "_hv", None)
        if not hv:
            return
        tag, on, t0, color_on = hv
        t = time.time() - t0
        if t > 0.16:
            self._hv = None
            return
        p = self._ease("std", t / 0.12) if on else 1.0 - self._ease("std", t / 0.12)
        col = self._mix(self.P["text2"], color_on or self.P["text"], max(0.0, min(1.0, p)))
        try:
            self.c.itemconfigure(tag, fill=col)
        except Exception:
            pass

    # ------------------------------------------------------------ 绘制入口
    def _render(self):
        self.R = self.w - PAD
        self.CX = self.w // 2
        self._close_editor(save=False)
        self._rows = {}
        self._focusables = []
        self.c.delete("all")
        self._fx = []
        self._fx_on = False
        self.sub_item = None
        self.v_uptime = self.v_traffic = self.v_relogin = self.v_ip = None
        self.v_retry = None
        self._focus_tag = None
        self._keyboard_focus = False
        c = self.c
        c.create_rectangle(0, 0, self.w, self.h, fill=self.P["bg"], outline="", tags=("base",))
        _rr(c, 0.5, 0.5, self.w - 0.5, self.h - 0.5, 12, fill="", outline=self.P["line"],
            width=1, tags=("base",))

        if self.view == "guide":
            self._build_guide()
        else:
            self._topbar()
            if self.view == "home":
                self._build_home()
            elif self.view == "me":
                self._build_me()
            else:
                self._build_settings()

        if S != 1.0:
            try:
                c.scale("all", 0, 0, S, S)
            except Exception:
                pass
        self._start_enter()
        self._draw_focus()

    # ---------- 文字与命中 ----------
    def _tw(self, text, px, family=None):
        cache = getattr(self, "_fcache", None)
        if cache is None:
            cache = self._fcache = {}
        key = (family or UI, int(px))
        f = cache.get(key)
        if f is None:
            try:
                f = tkfont.Font(family=key[0], size=-max(7, int(round(px))))
            except Exception:
                f = False
            cache[key] = f
        if not f:
            return len(text) * px * 0.6
        return f.measure(text)

    def _tracked(self, c, x, cy, text, px, fill, tracking, tags=()):
        """带字距的文字：Canvas 不支持 letter-spacing，逐字符画。返回总宽。"""
        n = len(text)
        if n <= 0:
            return 0
        widths = [self._tw(ch, px) for ch in text]
        total = sum(widths) + tracking * (n - 1)
        cx = x
        for ch, w in zip(text, widths):
            c.create_text(cx, cy, text=ch, anchor="w", fill=fill,
                          font=_f(UI, px), tags=tags)
            cx += w + tracking
        return total

    def _hit(self, x1, y1, x2, y2, tag, fill=None):
        """创建可靠热区；调用方需在文字与图标之前绘制，避免遮挡。"""
        return self.c.create_rectangle(x1, y1, x2, y2,
                                       fill=(fill or self.P["bg"]),
                                       outline="", tags=(tag,))

    def _focusable(self, tag, bounds):
        """登记当前页可键盘操作的自绘控件及其逻辑坐标。"""
        if tag not in [item[0] for item in self._focusables]:
            self._focusables.append((tag, tuple(bounds)))

    def _draw_focus(self):
        """在自绘控件外绘制可见焦点；坐标需随 DPI 单独缩放。"""
        self.c.delete("focus_ring")
        if not self._keyboard_focus or not self._focus_tag:
            return
        for tag, bounds in self._focusables:
            if tag != self._focus_tag:
                continue
            x1, y1, x2, y2 = bounds
            item = self.c.create_rectangle(
                x1, y1, x2, y2, fill="", outline=self.P["text"],
                width=1.2, dash=(3, 2), tags=("focus_ring",))
            if S != 1.0:
                self.c.scale(item, 0, 0, S, S)
            self.c.tag_raise(item)
            return

    def _wrap_text(self, text, max_width, px, max_lines=2):
        """按实际字宽换行，仅在超过行数时添加省略号。"""
        text = " ".join(str(text or "").split())
        if not text:
            return ""
        lines = []
        current = ""
        overflow = False
        for ch in text:
            candidate = current + ch
            if current and self._tw(candidate, px) > max_width:
                lines.append(current)
                current = ch
                if len(lines) >= max_lines:
                    overflow = True
                    break
            else:
                current = candidate
        if len(lines) < max_lines and current:
            lines.append(current)
        elif current and len(lines) >= max_lines:
            overflow = True
        lines = lines[:max_lines]
        if overflow and lines:
            last = lines[-1]
            while last and self._tw(last + "…", px) > max_width:
                last = last[:-1]
            lines[-1] = last + "…"
        return "\n".join(lines)

    def _chev(self, x, cy, color=None, tags=()):
        col = color or self.P["chevron"]
        self.c.create_line(x - 3, cy - 3.5, x + 0.5, cy, x - 3, cy + 3.5,
                           fill=col, width=1.3, capstyle="round",
                           joinstyle="round", tags=tags)

    def _switch(self, x2, cy, on, tags=()):
        c, P = self.c, self.P
        x1 = x2 - 34
        y1 = cy - 9
        if on:
            _rr(c, x1, y1, x2, y1 + 18, 9, fill=P["sw_on"], outline="",
                tags=tags)
        else:
            _rr(c, x1, y1, x2, y1 + 18, 9, fill=P["bg"], outline=P["line2"],
                width=1, tags=tags)
        kx = x2 - 9 if on else x1 + 9
        c.create_oval(kx - 7, cy - 7, kx + 7, cy + 7,
                      fill=(P["knob"] if on else P["chevron"]),
                      outline="", tags=tags)

    def _wifi(self, c, cx, cy, r, color, w=1.6, tags=()):
        for i, k in enumerate((1.0, 0.66, 0.32)):
            c.create_arc(cx - r * k, cy - r * k + 3, cx + r * k, cy + r * k + 3,
                         start=35, extent=110, style="arc", outline=color,
                         width=w, tags=tags)
        c.create_oval(cx - 1.4, cy + r * 0.42, cx + 1.4, cy + r * 0.42 + 2.8,
                      fill=color, outline="", tags=tags)

    # ---------- 顶部 ----------
    def _topbar(self):
        c, P = self.c, self.P
        y = PADT
        self._tracked(c, PAD, y + 8, "CAMPUSNET", 11, P["text"], 1.54,
                      tags=("fx",))
        # 导航右对齐，右侧给三枚窗口按钮让出 126px
        ctl_w = 126
        items = (("home", "主页"), ("me", "我的"), ("settings", "设置"))
        x = self.R - ctl_w - 18
        for key, label in reversed(items):
            w = self._tw(label, 12.5)
            x -= w
            active = (self.view == key)
            tag = "nav_" + key
            self._hit(x - 8, y - 10, x + w + 8, y + 24, tag)
            self._focusable(tag, (x - 8, y - 10, x + w + 8, y + 24))
            c.create_text(x, y + 8, text=label, anchor="w",
                          fill=(P["text"] if active else P["text2"]),
                          font=_f(UI, 12.5), tags=(tag, "fx"))
            if active:
                c.create_line(x, y + 17, x + w, y + 17, fill=P["text"],
                              width=1.5, tags=(tag, "fx"))
            x -= 26
        self._win_controls(y, ctl_w)
        c.create_line(PAD, y + NAV_H, self.R, y + NAV_H, fill=P["line_strong"],
                      width=1, tags=("fx",))

    def _win_controls(self, y, total_w):
        """右上角三枚窗口按钮：42x30 热区，hover 出底色，关闭 hover 变红。"""
        c, P = self.c, self.P
        bw = total_w / 3.0
        y1, y2 = y - 8, y + 22
        cy = (y1 + y2) / 2.0
        x = self.R
        for tag, kind in (("tb_close", "close"), ("tb_max", "max"),
                          ("tb_min", "min")):
            x -= bw
            # 热区先画（在下层），图标后画（在上层）
            c.create_rectangle(x, y1, x + bw, y2, fill=P["bg"], outline="",
                               tags=(tag, tag + "_bg"))
            self._focusable(tag, (x + 2, y1, x + bw - 2, y2))
            cx = x + bw / 2.0
            col = P["text2"]
            if kind == "min":
                c.create_line(cx - 5, cy, cx + 5, cy, fill=col, width=1.4,
                              capstyle="round", tags=(tag, tag + "_fg"))
            elif kind == "max":
                c.create_rectangle(cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5,
                                   fill="", outline=col, width=1.3,
                                   tags=(tag, tag + "_fg"))
            else:
                c.create_line(cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5, fill=col,
                              width=1.4, capstyle="round",
                              tags=(tag, tag + "_fg"))
                c.create_line(cx + 4.5, cy - 4.5, cx - 4.5, cy + 4.5, fill=col,
                              width=1.4, capstyle="round",
                              tags=(tag, tag + "_fg"))

    def _win_hover(self, tag, on):
        c = self.c
        if (not on) and getattr(self, "_win_hover_tag", None) not in (None, tag):
            return
        self._win_hover_tag = tag if on else None
        try:
            if tag == "tb_close" and on:
                c.itemconfigure(tag + "_bg", fill=self.P["err"])
                c.itemconfigure(tag + "_fg", fill="#FFFFFF")
            else:
                c.itemconfigure(tag + "_bg",
                                fill=(self.P["hover"] if on else self.P["bg"]))
                c.itemconfigure(tag + "_fg", fill=self.P["text2"])
        except Exception:
            pass

    # ---------- 主页 ----------
    def _build_home(self):
        c, P = self.c, self.P
        kind = self.kind

        if kind == "online":
            dot, title = P["ok"], "已连接"
            tag = self.ssid if self.ssid not in ("", "—") else "校园网"
            meta = "%s  ·  %s" % (self._profile_name(), self._ip or "IP 获取中")
        elif kind == "connecting":
            dot, title = P["warn"], "正在连接…"
            tag = self.ssid if self.ssid not in ("", "—") else "校园网"
            meta = "正在向认证服务器提交凭据"
        elif kind == "error":
            dot, title = P["err"], "认证失败"
            tag = self.ssid if self.ssid not in ("", "—") else "校园网"
            # 错误原因按实际字宽换行展示（最多两行），不再生硬截断
            meta = self._wrap_text(
                self.error or "认证未通过，请检查账号后重试",
                self.R - PAD, 12.5, 2)
        elif kind == "noconfig":
            dot, title = P["text3"], "未配置账号"
            tag = "尚未接入"
            meta = "先到「我的」填写学号与密码"
        else:
            dot, title = P["text3"], "未连接"
            tag = self.ssid if self.ssid not in ("", "—") else "校园网"
            meta = "%s  ·  点击下方按钮接入" % self._profile_name()

        y = PADT + NAV_H + 10 + 54

        # 状态行（右上角不再重复展示在线时长，数据区已有）
        c.create_oval(PAD, y + 2, PAD + 7, y + 9, fill=dot, outline="",
                      tags=("fx",))
        self._tracked(c, PAD + 16, y + 5.5, tag, 12, dot, 0.96, tags=("fx",))

        # 大标题
        y += 17 + 16
        self.big_item = c.create_text(PAD, y + 26, text=title, anchor="w",
                                      fill=P["text"], font=_f(UI, 46),
                                      tags=("fx",))
        # meta
        y += 52 + 14
        self.sub_item = c.create_text(PAD, y, text=meta, anchor="nw",
                                      fill=P["text2"], font=_f(UI, 12.5),
                                      tags=("fx",))
        if kind == "error":
            ay = y + 42
            if self._is_account_error():
                # 账号类错误：提供直达「我的」的修改入口
                label = "修改账号  →"
                lw = self._tw(label, 12.5)
                self._hit(PAD - 4, ay - 13, PAD + lw + 6, ay + 9, "err_fix")
                self._focusable("err_fix",
                                (PAD - 4, ay - 13, PAD + lw + 6, ay + 9))
                c.create_text(PAD, ay, text=label, anchor="w",
                              fill=P["text"], font=_f(UI, 12.5),
                              tags=("err_fix", "fx"))
            else:
                # 网络类错误：倒计时来自守护记录的真实重试时刻
                self.v_retry = c.create_text(PAD, ay, text=self._retry_text(),
                                             anchor="w", fill=P["text3"],
                                             font=_f(UI, 11.5), tags=("fx",))
            y += 30
        # 分割线
        y += 17 + 46
        c.create_line(PAD, y, self.R, y, fill=P["line"], width=1, tags=("fx",))

        # 四栏数据：窗口变高时把多余空间按比例分给数据区，避免中间出现大洞
        y += 1 + 36
        by = self.h - PADB - 44
        extra = (by - 26) - y - 86
        if extra > 60:
            y += int(extra * 0.45)
        up = self._uptime_text() if kind == "online" else u"\u2014"
        self._data_row(y, (
            ("uptime", "在线时长", up, "本次监测", 36),
            ("traffic", "本机流量", human_bytes(self._bytes), "本次运行 · 全接口", 36),
            ("relogin", "本次重连", "%d 次" % self.relogin, "本次运行累计", 36),
            ("ip", "IP 地址", self._ip or "—", "校园网分配", 25),
        ))

        # 底部操作区
        c.create_line(PAD, by - 26, self.R, by - 26, fill=P["line"], width=1,
                      tags=("fx",))
        if kind == "connecting":
            bfill, bfg, blabel = P["btn2"], P["btn2_fg"], "取消"
        else:
            bfill, bfg = P["btn"], P["btn_fg"]
            blabel = {"idle": "连接", "noconfig": "去填写",
                      "error": "重新连接", "online": "重新检测"}[kind]
        _rr(c, PAD, by, PAD + 148, by + 44, 2, fill=bfill, outline="",
            tags=("btn", "fx"))
        c.create_text(PAD + 74, by + 22, text=blabel, fill=bfg,
                      font=_f(UI, 13), tags=("btn", "fx"))
        self._focusable("btn", (PAD, by, PAD + 148, by + 44))
        log_label = "查看完整日志  →"
        log_w = self._tw(log_label, 12.5)
        self._hit(PAD + 164, by + 2, PAD + 176 + log_w + 4, by + 42, "row_log")
        self._focusable("row_log",
                        (PAD + 164, by + 2, PAD + 176 + log_w + 4, by + 42))
        c.create_text(PAD + 176, by + 22, text=log_label, anchor="w",
                      fill=P["text2"], font=_f(UI, 12.5),
                      tags=("row_log", "fx"))
        self._hit(self.R - 214, by + 2, self.R, by + 42, "tg2")
        self._focusable("tg2", (self.R - 214, by + 2, self.R, by + 42))
        self._switch(self.R, by + 22, self._rec_on, ("tg2", "fx"))
        c.create_text(self.R - 46, by + 22, text="自动重连", anchor="e",
                      fill=P["text2"], font=_f(UI, 12), tags=("tg2", "fx"))

    def _data_row(self, top, cols):
        c, P = self.c, self.P
        inner = self.w - 2 * PAD
        cw = inner / 4.0
        for i, (key, lab, val, sub, vsize) in enumerate(cols):
            x = PAD + i * cw + (0 if i == 0 else 26)
            if i:
                c.create_line(PAD + i * cw, top + 4, PAD + i * cw, top + 82,
                              fill=P["line"], width=1, tags=("fx",))
            self._tracked(c, x, top + 6, lab, 10.5, P["text3"], 1.05,
                          tags=("fx",))
            it = c.create_text(x, top + 40, text=val, anchor="w", fill=P["text"],
                               font=_f(NUM, vsize), tags=("fx",))
            if key:
                setattr(self, "v_" + key, it)
            c.create_text(x, top + 74, text=sub, anchor="w", fill=P["text3"],
                          font=_f(UI, 10.5), tags=("fx",))

    # ---------- 我的 ----------
    def _build_me(self):
        """我的 = 账号 / 学校 / 认证服务器 / 配置切换（不再放行为开关）。"""
        c, P = self.c, self.P
        y = PADT + NAV_H + 10 + 40

        name = self._account_name() or "未填写账号"
        c.create_text(PAD, y + 20, text=name, anchor="w", fill=P["text"],
                      font=_f(NUM, 34), tags=("fx",))
        y += 44
        c.create_text(PAD, y + 8, text="%s  ·  校园网账号" % self._profile_name(),
                      anchor="w", fill=P["text2"], font=_f(UI, 12.5),
                      tags=("fx",))

        y += 17 + 34
        # 账号（行内编辑，点击右侧值即可修改）
        y = self._section_label(y, "账号", rule=False)
        y = self._list_row(y, "学号", (self.cfg or {}).get("username") or "未填写",
                           "username", arrow=True)
        y = self._list_row(y, "密码", self._mask_pwd(), "password", arrow=True)
        # 学校与认证服务器
        y += 6
        y = self._section_label(y, "学校与认证")
        y = self._list_row(y, "当前学校", self._profile_name(), "row_school",
                           arrow=True)
        portal_url = ((self.cfg or {}).get("portal_url") or "").strip()
        y = self._list_row(y, "认证服务器", portal_url or "自动探测",
                           "row_portal", arrow=True)
        y = self._list_row(y, "切换 / 新增配置", None, "row_profiles", arrow=True)

    # ---------- 设置 ----------
    def _build_settings(self):
        """设置 = 开机自动连接 / 断线自动重连 / 检测间隔 / 主题 / 运行日志 / 关于。"""
        c, P = self.c, self.P
        y = PADT + NAV_H + 10 + 28

        c.create_text(PAD, y + 16, text="设置", anchor="w", fill=P["text"],
                      font=_f(UI, 30), tags=("fx",))
        y += 30 + 10
        c.create_text(PAD, y + 8, text="连接行为、外观与关于",
                      anchor="w", fill=P["text2"], font=_f(UI, 12), tags=("fx",))

        y += 17 + 22
        y = self._section_label(y, "连接", rule=False)
        y = self._list_row(y, "开机自动连接", None, "tg1", switch=True,
                           on=self._auto_on)
        y = self._list_row(y, "断线自动重连", None, "tg2", switch=True,
                           on=self._rec_on)
        y = self._list_row(y, "检测间隔",
                           "%s 秒" % ((self.cfg or {}).get("check_interval") or 20),
                           "row_interval", arrow=True)
        y += 4
        y = self._section_label(y, "外观")
        y = self._theme_row(y)
        y += 4
        y = self._section_label(y, "关于")
        y = self._list_row(y, "运行日志", None, "row_log", arrow=True)
        y = self._list_row(y, "新手引导", None, "row_guide", arrow=True)
        c.create_text(PAD, y + 12, text="CampusNet v" + config.APP_VERSION,
                      anchor="w", fill=P["text3"], font=_f(UI, 11.5),
                      tags=("fx",))

    def _section_label(self, y, text, rule=True):
        c, P = self.c, self.P
        if rule:
            c.create_line(PAD, y, self.R, y, fill=P["line"], width=1,
                          tags=("fx",))
            y += 24
        self._tracked(c, PAD, y + 5, text, 10.5, P["text3"], 1.05,
                      tags=("fx",))
        return y + 10 + 8

    def _list_row(self, y, label, value, tag, switch=False, arrow=False, on=False):
        c, P = self.c, self.P
        cy = y + ROW_H / 2.0
        # 整行热区铺在文字下层：行间任意位置均可点击，且不遮挡字形
        self._hit(PAD, y, self.R, y + ROW_H, tag)
        self._focusable(tag, (PAD, y, self.R, y + ROW_H))
        c.create_text(PAD, cy, text=label, anchor="w", fill=P["text"],
                      font=_f(UI, 13), tags=(tag, "fx"))
        if value:
            c.create_text(self.R - (22 if arrow else 0), cy, text=value,
                          anchor="e", fill=P["text2"], font=_f(UI, 12.5),
                          tags=(tag, "fx"))
        if arrow:
            self._chev(self.R - 6, cy, P["chevron"], (tag, "fx"))
        if switch:
            self._switch(self.R, cy, bool(on), (tag, "fx"))
        self._rows[tag] = (y, y + ROW_H)
        # 配置键与行 tag 不同名，登记别名供行内编辑定位
        if tag == "row_interval":
            self._rows["check_interval"] = (y, y + ROW_H)
        return y + ROW_H

    def _theme_row(self, y):
        c, P = self.c, self.P
        cy = y + 20
        c.create_text(PAD, cy, text="主题", anchor="w", fill=P["text"],
                      font=_f(UI, 13), tags=("fx",))
        x = self.R - 22
        for key, label in (("auto", "跟随系统"), ("dark", "深色"), ("light", "浅色")):
            w = self._tw(label, 12.5)
            x -= w
            active = (self.theme_setting == key)
            self._hit(x - 8, cy - 14, x + w + 8, cy + 14, "seg_" + key)
            self._focusable("seg_" + key, (x - 8, cy - 14, x + w + 8, cy + 14))
            c.create_text(x, cy, text=label, anchor="w",
                          fill=(P["text"] if active else P["text3"]),
                          font=_f(UI, 12.5), tags=("seg_" + key, "fx"))
            if active:
                c.create_line(x, cy + 10, x + w, cy + 10, fill=P["text"],
                              width=1.2, tags=("seg_" + key, "fx"))
            x -= 24
        return y + 40

    # ---------- 新手引导 ----------
    def _build_guide(self):
        c, P = self.c, self.P
        total = len(GUIDES)
        step = max(0, min(total - 1, self.guide_step))
        num, title, sub, bullets = GUIDES[step]

        y = PADT
        c.create_text(PAD, y + 8, text="新手引导", anchor="w", fill=P["text2"],
                      font=_f(UI, 12), tags=("fx",))
        skip_label = "跳过  ✕"
        skip_w = self._tw(skip_label, 12)
        self._hit(self.R - skip_w - 12, y - 8, self.R + 2, y + 22, "g_skip")
        self._focusable("g_skip",
                        (self.R - skip_w - 12, y - 8, self.R + 2, y + 22))
        c.create_text(self.R, y + 8, text=skip_label, anchor="e", fill=P["text3"],
                      font=_f(UI, 12), tags=("g_skip", "fx"))
        c.create_line(PAD, y + NAV_H, self.R, y + NAV_H, fill=P["line_strong"],
                      width=1, tags=("fx",))

        y += NAV_H + 46
        self._tracked(c, PAD, y + 5, num, 11, P["text3"], 2.2, tags=("fx",))
        y += 24
        c.create_text(PAD, y + 22, text=title, anchor="w", fill=P["text"],
                      font=_f(UI, 38), tags=("fx",))
        y += 44 + 10
        c.create_text(PAD, y + 8, text=sub, anchor="w", fill=P["text2"],
                      font=_f(UI, 13), tags=("fx",))
        y += 17 + 30
        c.create_line(PAD, y, self.R, y, fill=P["line"], width=1, tags=("fx",))
        y += 1 + 26

        for i, b in enumerate(bullets):
            c.create_text(PAD, y + 9, text="0%d" % (i + 1), anchor="w",
                          fill=P["text3"], font=_f(NUM, 10.5), tags=("fx",))
            c.create_text(PAD + 34, y + 9, text=b, anchor="w", fill=P["text"],
                          font=_f(UI, 13), tags=("fx",))
            c.create_line(PAD, y + 26, self.R, y + 26, fill=P["line"], width=1,
                          tags=("fx",))
            y += 34

        # 底栏
        by = self.h - PADB - 40
        c.create_line(PAD, by - 22, self.R, by - 22, fill=P["line"], width=1,
                      tags=("fx",))
        # 分页点
        gap = 14
        start = self.CX - ((total - 1) * gap) / 2.0
        for i in range(total):
            cx = start + i * gap
            if i == step:
                c.create_oval(cx - 3.6, by + 16.6, cx + 3.6, by + 23.4,
                              fill=P["text"], outline="", tags=("fx",))
            else:
                c.create_oval(cx - 2.8, by + 17.4, cx + 2.8, by + 22.6,
                              fill="", outline=P["text3"], width=1, tags=("fx",))
        # 主按钮
        nw = 104
        last = (step == total - 1)
        _rr(c, self.R - nw, by, self.R, by + 40, 2, fill=P["btn"], outline="",
            tags=("g_next", "fx"))
        c.create_text(self.R - nw / 2.0, by + 20,
                      text=("开始使用" if last else "下一步"), fill=P["btn_fg"],
                      font=_f(UI, 13), tags=("g_next", "fx"))
        self._focusable("g_next", (self.R - nw, by, self.R, by + 40))
        # 上一步
        if step > 0:
            prev_w = self._tw("上一步", 12.5)
            self._hit(self.R - nw - 24 - prev_w, by, self.R - nw - 8,
                      by + 40, "g_prev")
            self._focusable("g_prev",
                            (self.R - nw - 24 - prev_w, by, self.R - nw - 8,
                             by + 40))
            c.create_text(self.R - nw - 16, by + 20, text="上一步", anchor="e",
                          fill=P["text2"], font=_f(UI, 12.5),
                          tags=("g_prev", "fx"))
        # 未配账号时给直达入口（账号编辑在「我的」页）
        if not self._has_creds():
            goto_label = "还没有账号？去填写  →"
            goto_w = self._tw(goto_label, 11.5)
            self._hit(PAD - 4, by, PAD + goto_w + 6, by + 40, "g_goto")
            self._focusable("g_goto", (PAD - 4, by, PAD + goto_w + 6, by + 40))
            c.create_text(PAD, by + 20, text=goto_label, anchor="w",
                          fill=P["text2"], font=_f(UI, 11.5),
                          tags=("g_goto", "fx"))

    def _pick_initial_kind(self):
        if self.cfg.get("username") and self.cfg.get("password"):
            self.kind = "idle"
        else:
            self.kind = "noconfig"

    def _profile_name(self):
        cfg = self.cfg or {}
        return cfg.get("_profile_name") or cfg.get("ssid") or "未配置学校"

    def _account_name(self):
        return (self.cfg or {}).get("username") or "未登录"

    def _mask_pwd(self):
        return "••••••••" if (self.cfg or {}).get("password") else "未设置"

    def _has_creds(self):
        cfg = self.cfg or {}
        return bool(cfg.get("username") and cfg.get("password"))

    def _uptime_text(self):
        if not (self.online and self._online_since):
            return "--:--:--"
        s = int(time.time() - self._online_since)
        return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)

    def _signal_text(self):
        if not self.online:
            return "--"
        return "%d%%" % self._signal if self._signal is not None else "--"

    def _refresh_metrics(self):
        if self.view != "home":
            return
        try:
            self.c.itemconfigure(self.v_uptime, text=self._uptime_text())
            self.c.itemconfigure(self.v_traffic, text=human_bytes(self._bytes))
        except Exception:
            pass
        if self.online and not self._metrics_busy:
            self._metrics_busy = True

            def work():
                sig = None
                ip = ""
                total = None
                try:
                    sig = netutil.signal_percent()
                except Exception:
                    pass
                try:
                    ip = netutil.wlan_ip() or ""
                except Exception:
                    pass
                try:
                    total = self.traffic.session()
                except Exception:
                    pass
                self._post(lambda: self._apply_metrics(sig, ip, total))

            threading.Thread(target=work, daemon=True).start()

    def _apply_metrics(self, sig, ip, total):
        self._metrics_busy = False
        self._signal = sig
        self._ip = ip
        self._bytes = total
        try:
            self.c.itemconfigure(self.v_ip, text=ip or "—")
            self.c.itemconfigure(self.v_traffic, text=human_bytes(total))
            if self.sub_item is not None and self.kind == "online":
                self.c.itemconfigure(
                    self.sub_item,
                    text="%s  ·  %s" % (self._profile_name(),
                                           ip or "IP 获取中"))
        except Exception:
            pass

    def _sync_toggles(self):
        """开关以持久化偏好为准：守护的运行状态跟随偏好，而不是反过来。"""
        try:
            self._auto_on = bool(autostart.is_enabled())
        except Exception:
            self._auto_on = False
        self._rec_on = bool((self.cfg or {}).get("auto_reconnect", True))

    # ------------------------------------------------------------ 交互
    def _bind(self):
        c = self.c
        c.bind("<Button-1>", self._drag_start)
        c.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<Map>", self._on_map)
        self.root.bind("<Escape>", lambda e: self.guide_finish(mark=True)
                       if self.view == "guide" else None)

        c.tag_bind("btn", "<Button-1>", lambda e: self.do_primary())
        c.tag_bind("nav_home", "<Button-1>", lambda e: self.go("home"))
        c.tag_bind("nav_me", "<Button-1>", lambda e: self.go("me"))
        c.tag_bind("nav_settings", "<Button-1>", lambda e: self.go("settings"))
        c.tag_bind("tg1", "<Button-1>", lambda e: self.do_autostart())
        c.tag_bind("tg2", "<Button-1>", lambda e: self.do_reconnect_toggle())
        c.tag_bind("row_school", "<Button-1>", lambda e: self.open_advanced())
        c.tag_bind("row_portal", "<Button-1>", lambda e: self.open_advanced())
        c.tag_bind("row_profiles", "<Button-1>", lambda e: self.open_advanced())
        c.tag_bind("row_advanced", "<Button-1>", lambda e: self.open_advanced())
        c.tag_bind("row_log", "<Button-1>", lambda e: self.open_log())
        c.tag_bind("row_guide", "<Button-1>", lambda e: self.show_guide(0))
        c.tag_bind("err_fix", "<Button-1>", lambda e: self._fix_account())
        c.tag_bind("username", "<Button-1>",
                   lambda e: self._edit_credentials("username"))
        c.tag_bind("password", "<Button-1>",
                   lambda e: self._edit_credentials("password"))
        c.tag_bind("row_interval", "<Button-1>", lambda e: self._edit_number("check_interval"))
        for key in ("light", "dark", "auto"):
            c.tag_bind("seg_" + key, "<Button-1>",
                       lambda e, k=key: self.set_theme(k))
        c.tag_bind("tb_min", "<Button-1>", lambda e: self.do_minimize())
        c.tag_bind("tb_max", "<Button-1>", lambda e: self.do_maximize())
        c.tag_bind("tb_close", "<Button-1>", lambda e: self.on_close())
        c.tag_bind("g_prev", "<Button-1>", lambda e: self.guide_go(-1))
        c.tag_bind("g_next", "<Button-1>", lambda e: self.guide_next())
        c.tag_bind("g_skip", "<Button-1>", lambda e: self.guide_finish(mark=True))
        c.tag_bind("g_goto", "<Button-1>",
                   lambda e: self.guide_finish(to="me", mark=True))

        hot = ("btn", "nav_home", "nav_me", "nav_settings", "tg1", "tg2",
               "row_school", "row_portal", "row_profiles", "row_advanced",
               "row_log", "row_guide", "err_fix", "username", "password",
               "row_interval", "seg_light", "seg_dark", "seg_auto",
               "tb_min", "tb_max", "tb_close",
               "g_prev", "g_next", "g_skip", "g_goto")
        for tag in hot:
            c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))
        for tag in ("tb_min", "tb_max", "tb_close"):
            c.tag_bind(tag, "<Enter>",
                       lambda e, t=tag: self._win_hover(t, True))
            c.tag_bind(tag, "<Leave>",
                       lambda e, t=tag: self._win_hover(t, False))

        # 键盘导航：Tab / Shift+Tab 循环焦点，Enter / Space 激活，
        # Ctrl+1/2/3 切换页签；编辑框聚焦时全局快捷键一律让位
        self.root.bind("<Tab>", self._on_tab)
        self.root.bind("<Shift-Tab>", self._on_tab)
        try:
            self.root.bind("<ISO_Left_Tab>", self._on_tab)
        except Exception:
            pass
        self.root.bind("<Return>", self._on_activate_key)
        self.root.bind("<KP_Enter>", self._on_activate_key)
        self.root.bind("<space>", self._on_activate_key)
        self.root.bind("<Control-Key-1>", lambda e: self._ctrl_go("home"))
        self.root.bind("<Control-Key-2>", lambda e: self._ctrl_go("me"))
        self.root.bind("<Control-Key-3>", lambda e: self._ctrl_go("settings"))

    # ------------------------------------------------------------ 键盘导航
    def _editor_active(self):
        """行内编辑框存活期间，全局快捷键不得抢占输入。"""
        return self._editor is not None

    def _event_in_editor(self, e):
        return isinstance(getattr(e, "widget", None), tk.Entry)

    def _on_tab(self, e):
        if self._editor_active() or self._event_in_editor(e):
            return None
        shift = bool(getattr(e, "state", 0) & 0x0001)
        self._move_focus(-1 if shift else 1)
        return "break"

    def _move_focus(self, delta):
        """在当前页已登记的焦点项之间循环。"""
        if not self._focusables:
            return
        tags = [t for t, _b in self._focusables]
        if self._focus_tag not in tags:
            nxt = tags[0] if delta >= 0 else tags[-1]
        else:
            nxt = tags[(tags.index(self._focus_tag) + delta) % len(tags)]
        self._keyboard_focus = True
        self._focus_tag = nxt
        self._draw_focus()

    def _on_activate_key(self, e):
        if self._event_in_editor(e) or self._editor_active():
            return None
        if self._focus_tag:
            self._activate(self._focus_tag)
            return "break"
        return None

    def _ctrl_go(self, view):
        if self._event_in_editor_safe() or self._editor_active():
            return None
        if self.view == "guide":
            return None
        self.go(view)
        return "break"

    def _event_in_editor_safe(self):
        try:
            w = self.root.focus_get()
        except Exception:
            w = None
        return isinstance(w, tk.Entry)

    def _activate(self, tag):
        """焦点项激活分发：与鼠标点击保持同一套动作。"""
        if tag == "btn":
            self.do_primary()
        elif tag.startswith("nav_"):
            self.go(tag[4:])
        elif tag == "tg1":
            self.do_autostart()
        elif tag == "tg2":
            self.do_reconnect_toggle()
        elif tag in ("username", "password"):
            self._edit_credentials(tag)
        elif tag == "row_interval":
            self._edit_number("check_interval")
        elif tag in ("row_school", "row_portal", "row_profiles",
                     "row_advanced"):
            self.open_advanced()
        elif tag == "row_log":
            self.open_log()
        elif tag == "err_fix":
            self._fix_account()
        elif tag.startswith("seg_"):
            self.set_theme(tag[4:])
        elif tag == "tb_min":
            self.do_minimize()
        elif tag == "tb_max":
            self.do_maximize()
        elif tag == "tb_close":
            self.on_close()
        elif tag == "g_prev":
            self.guide_go(-1)
        elif tag == "g_next":
            self.guide_next()
        elif tag == "g_skip":
            self.guide_finish(mark=True)
        elif tag == "g_goto":
            self.guide_finish(to="me", mark=True)

    def _drag_start(self, e):
        # 鼠标一旦介入，隐藏键盘焦点框，避免两种交互态并存
        self._keyboard_focus = False
        try:
            self.c.delete("focus_ring")
        except Exception:
            pass
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        if e.y_root - self.root.winfo_y() < (PADT + NAV_H - 4) * S:
            self.root.geometry("+%d+%d" % (e.x_root - self._drag[0],
                                           e.y_root - self._drag[1]))

    def _on_map(self, _e=None):
        try:
            if self.root.state() == "normal" and not self.root.overrideredirect():
                self.root.after(15, lambda: self.root.overrideredirect(True))
        except Exception:
            pass

    def _init_tray(self):
        try:
            from tray import Tray
            tray = Tray(on_show=lambda: self._tray_q.append("show"),
                        on_quit=lambda: self._tray_q.append("quit"),
                        title="CampusNet")
            self.tray = tray if tray.hwnd else None
        except Exception:
            self.tray = None

    def _drain_tray(self):
        while self._tray_q:
            act = self._tray_q.pop(0)
            if act == "show":
                self.show_window()
            elif act == "quit":
                self.quit_app()
                return

    def show_window(self):
        try:
            self.root.deiconify()
            self.root.overrideredirect(True)
            self.root.lift()
            win11fx.apply_round_corner(self.root, self.sw, self.sh, 12, 1.0)
            self.root.attributes("-topmost", True)
            self.root.after(150, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception:
            pass

    def hide_to_tray(self):
        try:
            self.root.withdraw()
        except Exception:
            return
        self.log("已收进托盘，守护继续运行；右键托盘图标可退出")

    def quit_app(self):
        # 顺序很关键：保存编辑 → 等托盘线程干净退出 → 销毁 Tk。
        # 任何一步乱序都可能在进程退出阶段触发堆损坏。
        try:
            self._close_editor(save=True)
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.destroy()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def do_minimize(self):
        if self.tray is not None:
            self.hide_to_tray()
            return
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception:
            pass

    def do_maximize(self):
        if self._maxed:
            self.w, self.h = self._normal_size
            self._maxed = False
        else:
            self._normal_size = (self.w, self.h)
            self.w, self.h = 1180, 720
            self._maxed = True
        self._apply_size()
        self._repaint_window_state()

    def _apply_size(self):
        self.sw = int(round(self.w * S))
        self.sh = int(round(self.h * S))
        try:
            self.c.configure(width=self.sw, height=self.sh)
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = max(0, min(self.root.winfo_x(), sw - self.sw))
            y = max(0, min(self.root.winfo_y(), sh - self.sh))
            self.root.geometry("%dx%d+%d+%d" % (self.sw, self.sh, x, y))
            self.root.update_idletasks()
            win11fx.apply_round_corner(self.root, self.sw, self.sh, 12, 1.0)
        except Exception:
            pass
        self._render()

    def _repaint_window_state(self):
        """最大化按钮的图标跟随状态：已最大化时画成「还原」的双框。"""
        try:
            c = self.c
            c.delete("tb_max_fg")
            w = 126 / 3.0
            cx = self.R - w - w / 2.0
            cy = (PADT - 8 + PADT + 22) / 2.0
            col = self.P["text2"]
            if self._maxed:
                c.create_line(cx - 4.5, cy - 2.5, cx + 2.5, cy - 2.5,
                              cx + 2.5, cy + 4.5, cx - 4.5, cy + 4.5,
                              cx - 4.5, cy - 2.5, fill=col, width=1.3,
                              tags=("tb_max", "tb_max_fg"))
                c.create_line(cx - 2.5, cy - 4.5, cx + 4.5, cy - 4.5,
                              cx + 4.5, cy + 2.5, fill=col, width=1.3,
                              tags=("tb_max", "tb_max_fg"))
            else:
                c.create_rectangle(cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5,
                                   fill="", outline=col, width=1.3,
                                   tags=("tb_max", "tb_max_fg"))
            if S != 1.0:
                c.scale("tb_max_fg", 0, 0, S, S)
        except Exception:
            pass

    def on_close(self):
        if self.view == "guide":
            self.guide_finish(mark=True)
            return
        # ✕ = 直接退出；想后台常驻请点最小化
        self.quit_app()

    # ------------------------------------------------------------ 导航
    def go(self, view):
        self._close_editor(save=True)
        self.view = view
        if view == "me":
            self._sync_toggles()
        self._render()

    def open_settings(self):
        self.go("settings")

    # ------------------------------------------------------------ 引导
    def _skip_path(self):
        base = config.app_dir()
        for root in (base, os.path.dirname(base)):
            d = os.path.join(root, "launcher")
            if os.path.isdir(d):
                return os.path.join(d, "guide.skip")
        return os.path.join(base, "guide.skip")

    def should_guide(self):
        try:
            return not os.path.exists(self._skip_path())
        except Exception:
            return False

    def show_guide(self, step=0):
        self.guide_step = max(0, min(len(GUIDES) - 1, step))
        self.view = "guide"
        self._render()

    def guide_go(self, delta):
        self.guide_step = max(0, min(len(GUIDES) - 1, self.guide_step + delta))
        self._render()

    def guide_next(self):
        if self.guide_step >= len(GUIDES) - 1:
            self.guide_finish(mark=True)
        else:
            self.guide_go(1)

    def _write_skip(self):
        try:
            path = self._skip_path()
            d = os.path.dirname(path)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            with open(path, "w", encoding="ascii") as fh:
                fh.write("1")
        except Exception as exc:
            self.log("写入引导标记失败：%r" % (exc,))

    def guide_finish(self, to=None, mark=False):
        """离开引导进入主界面。

        「跳过 ✕」「开始使用」「Escape」都会真正离开引导并写入标记，
        默认落在主页；``to`` 可指定落地页（如去「我的」填写账号）。
        """
        if mark:
            self._write_skip()
        if to in ("home", "me", "settings"):
            self.go(to)
        else:
            self.go("home")

    # ------------------------------------------------------------ 行内编辑
    def _edit_credentials(self, key):
        self._close_editor(save=True)
        bounds = self._rows.get(key)
        if not bounds:
            self.open_advanced()
            return
        y1, y2 = bounds
        e = tk.Entry(self.root, bd=0, relief="flat", bg=self.P["bg"],
                     fg=self.P["text"], insertbackground=self.P["text"],
                     highlightthickness=1, highlightbackground=self.P["line2"],
                     highlightcolor=self.P["text"],
                     font=_f(UI, 12.5), justify="right")
        if key == "password":
            e.configure(show="●")
        e.insert(0, (self.cfg or {}).get(key, ""))
        e.place(x=int((PAD + 150) * S), y=int((y1 + 4) * S),
                width=int((RIGHT - PAD - 170) * S), height=int(28 * S))
        e.focus_set()
        e.select_range(0, "end")
        e.bind("<Return>", lambda ev: self._close_editor(save=True))
        e.bind("<Escape>", lambda ev: self._close_editor(save=False))
        e.bind("<FocusOut>", lambda ev: self._close_editor(save=True))
        self._editor = [e, key, None]

    def _edit_number(self, key, lo=5, hi=300):
        """行内编辑数字型配置（检测间隔），保存时夹到合理区间。"""
        self._close_editor(save=True)
        bounds = self._rows.get(key) or self._rows.get("row_" + key)
        if not bounds:
            self.open_advanced()
            return
        y1, y2 = bounds
        e = tk.Entry(self.root, bd=0, relief="flat", bg=self.P["bg"],
                     fg=self.P["text"], insertbackground=self.P["text"],
                     highlightthickness=1, highlightbackground=self.P["line2"],
                     highlightcolor=self.P["text"],
                     font=_f(NUM, 12.5), justify="right")
        e.insert(0, str((self.cfg or {}).get(key) or 20))
        e.place(x=int((RIGHT - 180) * S), y=int((y1 + 4) * S),
                width=int(160 * S), height=int(28 * S))
        e.focus_set()
        e.select_range(0, "end")
        e.bind("<Return>", lambda ev: self._close_editor(save=True))
        e.bind("<Escape>", lambda ev: self._close_editor(save=False))
        e.bind("<FocusOut>", lambda ev: self._close_editor(save=True))
        self._editor = [e, key, lambda v: max(lo, min(hi, int(float(v))))]

    def _close_editor(self, save=True):
        if not self._editor or self._editor_guard:
            return
        self._editor_guard = True
        e, key, cast = self._editor
        self._editor = None
        try:
            value = e.get()
        except Exception:
            value = None
        try:
            e.destroy()
        except Exception:
            pass
        self._editor_guard = False
        if cast is not None and value is not None:
            try:
                value = cast(value)
            except Exception:
                value = None
        if save and value is not None:
            old = (self.cfg or {}).get(key, "")
            if value != old:
                cfg = config.load() or {}
                cfg[key] = value
                try:
                    config.save(cfg)
                    self.cfg = cfg
                    label = {"username": "学号", "password": "密码"}.get(key, "设置")
                    self.log("已更新%s" % label)
                except Exception as exc:
                    self.log("保存失败：%r" % (exc,))
                if self.kind == "noconfig" and cfg.get("username") \
                        and cfg.get("password"):
                    self.kind = "idle"
                self._render()

    # ------------------------------------------------------------ 外部窗口
    def open_advanced(self):
        from settings import SettingsDialog

        def saved(cfg):
            self.cfg = dict(cfg or {})
            if self.guard and self.guard.is_alive():
                try:
                    self.guard.cfg = dict(self.cfg)
                    self.guard.wake()
                except Exception:
                    pass
            self._sync_toggles()
            self.log("设置已保存 · 学校：%s" % self._profile_name())
            if self.kind == "noconfig" and self._has_creds():
                self.kind = "idle"
            self._render()

        SettingsDialog(self.root, self._dialog_theme(), saved)

    def open_log(self):
        try:
            path = os.path.join(config.app_dir(), "campusnet.log")
            if not os.path.exists(path):
                path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "campusnet.log")
            os.startfile(os.path.abspath(path))
        except Exception as exc:
            self.log("打开日志失败：%r" % (exc,))

    # ------------------------------------------------------------ 业务
    def log(self, msg, persist=True):
        self.logs.append("%s  %s" % (time.strftime("%H:%M"), msg))
        del self.logs[:-40]
        if persist:
            try:
                config.log(msg)
            except Exception:
                pass
        if self.view == "home":
            try:
                self._build_home_events_only()
            except Exception:
                pass

    def _build_home_events_only(self):
        """主页只刷新数字，避免整页重绘打断动画。"""
        c = self.c
        try:
            if self.v_uptime is not None:
                c.itemconfigure(self.v_uptime, text=self._uptime_text())
            if self.v_traffic is not None:
                c.itemconfigure(self.v_traffic, text=human_bytes(self._bytes))
            if self.v_relogin is not None:
                c.itemconfigure(self.v_relogin, text="%d 次" % self.relogin)
            if self.v_ip is not None:
                c.itemconfigure(self.v_ip, text=self._ip or "—")
            if self.sub_item is not None and self.kind == "online":
                c.itemconfigure(
                    self.sub_item,
                    text="%s  ·  %s" % (self._profile_name(),
                                           self._ip or "IP 获取中"))
        except Exception:
            pass

    def do_primary(self):
        if self.kind == "online":
            self.do_recheck()
        elif self.kind == "connecting":
            # 取消：作废在途认证请求，迟到的结果不得再改写界面
            self._auth_generation += 1
            self.connecting = False
            self.kind = "idle"
            self._render()
            self.log("已取消本次认证")
        elif self.kind == "noconfig":
            self.go("me")
        else:
            self.do_connect()

    def do_connect(self):
        cfg = self.cfg or {}
        if not (cfg.get("username") and cfg.get("password")):
            self.kind = "noconfig"
            self._render()
            return
        self.connecting = True
        self.kind = "connecting"
        # 每次手动认证分配一个代次；取消或再次发起后，旧代次结果一律忽略
        self._auth_generation += 1
        gen = self._auth_generation
        self._render()
        self.log("正在提交认证…（请求 #%d）" % gen)

        def work():
            ip = ""
            try:
                ip = netutil.wlan_ip()
                if netutil.internet_ok(bind_ip=ip):
                    self._post(lambda: self._after_login(
                        gen, True, "WLAN 已认证，无需重复登录"))
                    return
            except Exception:
                pass
            try:
                ok, msg = portal.login(dict(cfg), bind_ip=ip)
            except Exception as exc:
                ok, msg = False, "认证异常：%r" % (exc,)
            self._post(lambda: self._after_login(gen, ok, msg))

        threading.Thread(target=work, daemon=True).start()

    def _after_login(self, gen, ok, msg):
        if gen != self._auth_generation:
            # 迟到结果：请求已被取消或被新请求取代，直接丢弃
            self.log("已忽略一次过期的认证结果（请求 #%d）" % gen, persist=False)
            return
        self.connecting = False
        self.log(("✓ " if ok else "✗ ") + (msg or ""))
        if ok:
            self.online = True
            self._online_since = time.time()
            self.traffic = Traffic()
            try:
                self.ssid = netutil.current_ssid() or self.ssid
            except Exception:
                pass
            self.kind = "online"
            self._render()
            # 尊重「断线自动重连」偏好：关闭时手动认证后也不偷跑守护
            if self._rec_on:
                self._start_guard()
            self._sync_toggles()
        else:
            self.error = msg or "认证未通过"
            self.kind = "error"
            self._render()

    # ------------------------------------------------------------ 重新检测
    def do_recheck(self):
        """在线主按钮：立即巡检一次网络并给出真实反馈。

        与「断线自动重连」开关职责不同：这里是一次性主动检测，
        不改变守护的运行策略；守护在跑时顺手唤醒它立即巡检一轮。
        """
        if self._checking:
            return
        self._checking = True
        self._check_generation += 1
        gen = self._check_generation
        self.log("正在重新检测网络状态…")
        if self.guard and self.guard.is_alive():
            try:
                self.guard.cfg = dict(self.cfg or {})
                self.guard.wake()
            except Exception:
                pass

        def work():
            ok = False
            try:
                ip = netutil.wlan_ip()
                ok = bool(netutil.internet_ok(bind_ip=ip))
            except Exception:
                ok = False
            self._post(lambda: self._after_recheck(gen, ok))

        threading.Thread(target=work, daemon=True).start()

    def _after_recheck(self, gen, ok):
        if gen != self._check_generation:
            return  # 已有更新的检测请求，丢弃本次迟到结果
        self._checking = False
        if ok:
            if not self.online:
                self.online = True
                self._online_since = time.time()
            self.kind = "online"
            self.log("✓ 检测通过，网络可用")
        else:
            if self.guard and self.guard.is_alive():
                self.log("✗ 暂未联网，自动重连会继续尝试")
            else:
                self.online = False
                self._reset_session()
                self.error = "当前无法访问互联网，请检查 WiFi 连接后重试"
                self.kind = "error"
                self.log("✗ 暂未联网")
        self._render()

    # ------------------------------------------------------------ 错误态
    def _is_account_error(self):
        """账号类硬错误（服务器明确拒绝），应引导用户去改账号。"""
        try:
            if getattr(self.state, "fatal", False):
                return True
        except Exception:
            pass
        msg = self.error or ""
        return any(h in msg for h in guard_mod.FATAL_HINTS)

    def _retry_remaining(self):
        """距离守护下一次真实重试的剩余秒数（0 表示无在途倒计时）。"""
        try:
            retry_at = float(getattr(self.state, "retry_at", 0.0) or 0.0)
        except Exception:
            return 0
        return max(0, int(round(retry_at - time.time())))

    def _retry_text(self):
        rem = self._retry_remaining()
        if rem > 0:
            return "%d 秒后自动重试" % rem
        if self.guard and self.guard.is_alive():
            return "守护正在巡检，稍后自动重试"
        return "自动重连已关闭，可点「重新连接」立即重试"

    def _fix_account(self):
        """账号类错误入口：跳到「我的」并直接打开学号编辑框。"""
        self.go("me")
        self._edit_credentials("username")

    def _reset_session(self):
        """会话结束：清掉在线时长与本次流量，避免旧数值残留。"""
        self._online_since = None
        self._bytes = None
        self._signal = None

    def do_disconnect(self):
        self._stop_guard()
        self.online = False
        self._reset_session()
        self.kind = "idle"
        self._render()
        self._sync_toggles()
        self.log("已停止自动重连；校园网会话仍在，需要下线请在认证页点「注销」")

    def do_reconnect_toggle(self):
        """断线自动重连：偏好持久化到 auto_reconnect，关闭后下次启动不再自动巡检。"""
        if self._rec_on:
            self._rec_on = False
            self._stop_guard()
            self.log("已关闭断线自动重连，下次启动不再自动监测")
        else:
            if not self._has_creds():
                self.log("请先在「我的」填写账号密码")
                self.go("me")
                return
            self._rec_on = True
            self._start_guard()
            self.log("已开启断线自动重连")
        self._persist_auto_reconnect()
        self._sync_toggles()
        self._render()

    def _persist_auto_reconnect(self):
        try:
            cfg = config.load() or {}
            cfg["auto_reconnect"] = bool(self._rec_on)
            config.save(cfg)
            self.cfg = cfg
        except Exception as exc:
            self.log("保存自动重连偏好失败：%r" % (exc,))

    def do_autostart(self):
        try:
            if autostart.is_enabled():
                autostart.disable()
                self.log("已关闭开机自动连接")
            else:
                ok, _ = autostart.enable()
                self.log("已开启开机自动连接" if ok else "设置失败")
        except Exception as exc:
            self.log("开机自启设置失败：%r" % (exc,))
        self._sync_toggles()
        self._render()

    def _start_guard(self):
        if self.guard and self.guard.is_alive():
            try:
                self.guard.cfg = dict(self.cfg or {})
                self.guard.wake()
            except Exception:
                pass
            return
        self.guard = guard_mod.Guard(dict(self.cfg or {}), self.state,
                                     on_change=self._on_state_change)
        self.guard.start()

    def _stop_guard(self):
        try:
            if self.guard:
                self.guard.stop()
        except Exception:
            pass

    def _on_state_change(self):
        self._post(self._apply_state)

    def _apply_state(self):
        st = self.state
        if st.online and not self.online:
            self._online_since = time.time()
        elif not st.online and self.online:
            self._online_since = None
        self.online = bool(st.online)
        if st.ssid and st.ssid != "—":
            self.ssid = st.ssid
        self.relogin = st.total_relogin

        if len(st.logs) < self._seen:
            self._seen = 0
        new = st.logs[self._seen:]
        if new:
            self._seen = len(st.logs)
            for m in new:
                self.log(str(m), persist=False)

        target = None
        if st.fatal:
            # 优先展示服务器返回的真实拒绝原因，其次才是守护提示语
            self.error = st.last_error or st.last_msg or "认证被暂停"
            target = "error"
        elif self.online:
            target = "online"
        elif self.kind in ("online", "connecting"):
            target = "idle"
        if target and target != self.kind:
            if target == "idle":
                self._reset_session()
            self.kind = target
            if self.view == "home":
                self._render()
        self._refresh_metrics()

    # ------------------------------------------------------------ 循环
    def _post(self, fn):
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    def _tick(self):
        try:
            self._drain_tray()
        except Exception:
            pass
        try:
            self._anim_step()
            self._hover_step()
        except Exception:
            pass
        try:
            sec = int(time.time())
            if sec != self._last_sec:
                self._last_sec = sec
                if self.view == "home":
                    if self.kind == "online":
                        self._refresh_metrics()
                    elif self.kind == "error" and self.v_retry is not None:
                        # 错误态倒计时每秒刷新，来源是守护的真实 retry_at
                        try:
                            self.c.itemconfigure(self.v_retry,
                                                 text=self._retry_text())
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            self.root.after(16, self._tick)
        except Exception:
            pass

    def _fade(self, k):
        k = min(1.0, k + 0.12)
        try:
            self.root.attributes("-alpha", win11fx.ease_out_cubic(k))
        except Exception:
            return
        if k < 1.0:
            self.root.after(16, lambda: self._fade(k))


_MUTEX = None


def _already_running():
    """命名互斥量判断是否已有实例；句柄必须留在模块级，否则会被回收。"""
    global _MUTEX
    try:
        _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False,
                                                     "Local\\CampusNet_UI")
        return ctypes.windll.kernel32.GetLastError() == 183
    except Exception:
        return False


def _activate_existing():
    """把已有实例的窗口叫到前台，失败则返回 False。"""
    try:
        u = ctypes.windll.user32
        found = []

        def cb(hwnd, lp):
            if not u.IsWindowVisible(hwnd):
                return True
            n = u.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value != "CampusNet":
                return True
            r = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 200 and r.bottom - r.top > 300:
                found.append(hwnd)
            return True

        proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND,
                                  wintypes.LPARAM)(cb)
        u.EnumWindows(proc, 0)
        if found:
            u.ShowWindow(found[0], 9)
            u.SetForegroundWindow(found[0])
            return True
    except Exception:
        pass
    return False


def main():
    if _already_running():
        _activate_existing()
        return
    root = tk.Tk()
    app = QuietUI(root)
    app.log("界面已就绪 · " + app._profile_name())
    cfg = app.cfg or {}
    # 尊重持久化偏好：关闭「断线自动重连」后，下次启动不再自动启动守护
    if cfg.get("username") and cfg.get("password") \
            and cfg.get("auto_reconnect", True):
        app._start_guard()
        app._sync_toggles()
        app._render()

    theme = os.environ.get("CAMPUSNET_UI_THEME")
    if theme in ("light", "dark", "auto"):
        app.set_theme(theme, persist=False)
    view = os.environ.get("CAMPUSNET_UI_VIEW")
    if view in ("home", "me", "settings"):
        app.go(view)
    elif view == "guide":
        app.show_guide(int(os.environ.get("CAMPUSNET_UI_STEP") or 0))
    elif app.should_guide():
        app.show_guide()
    root.mainloop()
    # 退出前的清理（保存编辑、删托盘图标、销毁 Tk）都已在 quit_app 完成。
    # 这里直接终止进程、跳过解释器终结：守护/认证等 daemon 线程可能仍
    # 挂在网络调用里，终结阶段冻结它们曾导致退出时报堆损坏
    # （alloc: invalid block, exit code 3）。
    os._exit(0)


if __name__ == "__main__":
    main()
