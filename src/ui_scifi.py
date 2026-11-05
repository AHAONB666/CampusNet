# uncompyle6 version 3.9.3
# Python bytecode version base 3.8.0 (3413)
# Decompiled from: Python 3.13.14 (main, Jun 11 2026, 04:04:46) [MSC v.1944 64 bit (AMD64)]
# Embedded file name: ui_scifi.py
"""科幻风控制面板 —— 三套主题，纯 tkinter Canvas 自绘 + 动画"""
import math, os, sys, threading, time, tkinter as tk
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
import autostart, config, guard as guard_mod, netutil, portal, win11fx

def shade(color, f):
    c = color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    r, g, b = [max(0, min(255, int(v * f))) for v in (r, g, b)]
    return "#%02x%02x%02x" % (r, g, b)


THEMES = {'hud':dict(key="hud",
   name="深空 HUD",
   bg="#03060d",
   panel="#070e19",
   line="#0d2233",
   primary="#22d3ee",
   accent="#38bdf8",
   dim="#0e5065",
   text="#dff6ff",
   text2="#6d90a6",
   ok="#2ce8b0",
   bad="#fb3b5c",
   warn="#f5a524",
   mono="Consolas",
   ui="Microsoft YaHei UI"), 
 'cyber':dict(key="cyber",
   name="赛博霓虹",
   bg="#08030f",
   panel="#120720",
   line="#2b0f45",
   primary="#e879f9",
   accent="#00e5ff",
   dim="#5b1f6e",
   text="#f7e9ff",
   text2="#a37fb8",
   ok="#00ffa3",
   bad="#ff2d6f",
   warn="#ffb020",
   mono="Consolas",
   ui="Microsoft YaHei UI"), 
 'matrix':dict(key="matrix",
   name="终端矩阵",
   bg="#000804",
   panel="#02120a",
   line="#0a3a1e",
   primary="#22c55e",
   accent="#a3e635",
   dim="#14532d",
   text="#ccf5d8",
   text2="#4d8c62",
   ok="#4ade80",
   bad="#ef4444",
   warn="#eab308",
   mono="Consolas",
   ui="Consolas")}
W, H = (760, 800)

class ScifiUI(object):

    def __init__(self, root, theme='hud', demo=False):
        self.root = root
        self.T = THEMES[theme]
        self.cfg = config.load()
        self.demo = demo
        self.t = 0.0
        self.logs = []
        self.online = False
        self.running = False
        self.relogin = 0
        self.ssid = "—"
        self.last_msg = "待机中"
        self._drag = (0, 0)
        self._btn_items = {}
        self.metrics = {}
        self.log_items = []
        self.state = guard_mod.State()
        self.guard = None
        self._last_n = 0
        self._seen = 0
        self._online_since = None
        self._sig_cache = (0, None)
        self._ip_cache = (0, '')
        self._lat_cache = (0, None)
        self._last_frame = time.perf_counter()
        self._active = False
        self._state_k = 0.0
        self._intro = 0.0
        self._btn_hover = {}
        self._dpi = 1.0
        try:
            self._dpi = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except Exception:
            pass
        else:
            root.overrideredirect(True)
            root.title("CampusNet 控制台 - " + self.T["name"])
            root.geometry("%dx%d+%d+%d" % (W, H, 320, 60))
            root.configure(bg=(self.T["bg"]))
        try:
            root.attributes("-alpha", 1.0)
        except Exception:
            pass
        else:
            self.c = tk.Canvas(root, width=W, height=H, bg=(self.T["bg"]), highlightthickness=0,
              bd=0)
            self.c.pack(fill="both", expand=True)
            try:
                root.update_idletasks()
                win11fx.set_dark_mode(root)
                win11fx.apply_round_corner(root, W, H, 26, self._dpi)
            except Exception:
                pass
            else:
                self._build()
                self._bind()
                for i, k in enumerate(('hud', 'cyber', 'matrix'), start=1):
                    root.bind(str(i), lambda e, kk=k: self.switch_theme(kk))
                else:
                    self._animate()
                    self._fade_in()

    def _fade_in(self, k=0.0):
        """窗口淡入：0.25 秒 ease-out，结束时 alpha=1.0 保证不透底"""
        k = min(1.0, k + 0.09)
        try:
            self.root.attributes("-alpha", win11fx.ease_out_cubic(k))
        except Exception:
            return
        else:
            if k < 1.0:
                self.root.after(16, lambda: self._fade_in(k))

    def switch_theme(self, key):
        """热切换主题：保留输入内容，重建全部绘制"""
        if key == self.T["key"]:
            return
        u = self.e_user.get() if getattr(self, "e_user", None) else ""
        p = self.e_pwd.get() if getattr(self, "e_pwd", None) else ""
        for e in (getattr(self, "e_user", None), getattr(self, "e_pwd", None)):
            if e:
                e.destroy()
            self.T = THEMES[key]
            self.root.configure(bg=(self.T["bg"]))
            self.c.configure(bg=(self.T["bg"]))
            self.c.delete("all")
            self.metrics = {}
            self.log_items = []
            self._btn_items = {}
            self._build()
            self.e_user.insert(0, u)
            self.e_pwd.insert(0, p)
            self._render_logs()
            self._refresh_metrics()

    def _glow_line(self, coords, color, width=1, layers=3):
        for i in range(layers, 0, -1):
            (self.c.create_line)(*coords, fill=shade(color, 0.18 * (layers - i + 1) / layers), width=width + i * 2, 
             capstyle="round")
        else:
            (self.c.create_line)(*coords, fill=color, width=width, capstyle="round")

    def _glow_rect(self, x1, y1, x2, y2, color, width=1, layers=3, fill=''):
        for i in range(layers, 0, -1):
            self.c.create_rectangle((x1 - i), (y1 - i), (x2 + i), (y2 + i), outline=(shade(color, 0.12 * (layers - i + 1) / layers)),
              width=(width + i * 2))
        else:
            return self.c.create_rectangle(x1, y1, x2, y2, outline=color, width=width, fill=fill)

    def _glow_text(self, x, y, text, color, font, anchor='w', glow=True):
        if glow:
            for dx, dy, f in ((-1, 0, 0.25), (1, 0, 0.25), (0, -1, 0.25), (0, 1, 0.25)):
                self.c.create_text((x + dx), (y + dy), text=text, fill=(shade(color, f)), font=font,
                  anchor=anchor)

        return self.c.create_text(x, y, text=text, fill=color, font=font, anchor=anchor)

    def _grid(self):
        T = self.T
        for x in range(0, W, 38):
            self.c.create_line(x, 0, x, H, fill=(shade(T["line"], 0.55)), width=1)
        else:
            for y in range(0, H, 38):
                self.c.create_line(0, y, W, y, fill=(shade(T["line"], 0.55)), width=1)

    def _corner_marks(self, pad=14, ln=26):
        T = self.T
        p = T["primary"]
        for x, y, dx, dy in ((pad, pad, 1, 1), (W - pad, pad, -1, 1),
         (
          pad, H - pad, 1, -1), (W - pad, H - pad, -1, -1)):
            self._glow_line((x, y, x + dx * ln, y), p, 2, 2)
            self._glow_line((x, y, x, y + dy * ln), p, 2, 2)

    def _button(self, x, y, w, h, label, cmd, kind='primary'):
        T = self.T
        color = T["primary"] if kind == "primary" else T["text2"]
        tag = "btn_%d" % len(self._btn_items)
        r = win11fx.round_rect((self.c), x, y, (x + w), (y + h), 8, fill=(shade(color, 0.13)),
          outline=(shade(color, 0.5)),
          width=1)
        t = self.c.create_text((x + w / 2), (y + h / 2 - 1), text=label, fill=color, font=(
         T["ui"], 10, "bold"))
        self._btn_items[tag] = {'rect': r, 'text': t, 'color': color, 'k': 0.0, 'target': 0.0}
        for it in (r, t):
            self.c.tag_bind(it, "<Button-1>", lambda e, f=cmd: f())
            self.c.tag_bind(it, "<Enter>", lambda e, tg=tag: self._btn_hover_to(tg, 1.0))
            self.c.tag_bind(it, "<Leave>", lambda e, tg=tag: self._btn_hover_to(tg, 0.0))
        else:
            return tag

    def _btn_hover_to(self, tag, v):
        d = self._btn_items.get(tag)
        if d:
            d["target"] = v

    def _entry(self, x, y, w, h, show=''):
        T = self.T
        bgfill = shade(T["panel"], 1.8)
        win11fx.round_rect((self.c), x, y, (x + w), (y + h), 8, fill=bgfill,
          outline=(shade(T["primary"], 0.25)),
          width=1)
        e = tk.Entry((self.root), bd=0, relief="flat", bg=bgfill, fg=(T["text"]),
          insertbackground=(T["primary"]),
          font=(
         T["mono"], 10),
          highlightthickness=0,
          show=show)
        self.c.create_window((x + 9), (y + 1), window=e, anchor="nw", width=(w - 18),
          height=(h - 2))
        return e

    def _pwd_toggle(self, x, y):
        """密码框旁边的 显示/隐藏 切换"""
        T = self.T
        t = self.c.create_text(x, y, text="显示", fill=(shade(T["primary"], 0.7)), font=(
         T["ui"], 9), anchor="w")
        def toggle(_e):
            cur = self.e_pwd.cget("show")
            self.e_pwd.config(show="" if cur else "●")
            self.c.itemconfigure(t, text=("隐藏" if cur else "显示"))
        self.c.tag_bind(t, "<Button-1>", toggle)
        self.c.tag_bind(t, "<Enter>", lambda e: self.c.itemconfigure(t, fill=(T["primary"])))
        self.c.tag_bind(t, "<Leave>", lambda e: self.c.itemconfigure(t, fill=(shade(T["primary"], 0.7))))

    def _log_copy(self, x, y):
        """日志区右上角的复制按钮"""
        T = self.T
        t = self.c.create_text(x, y, text="⧉ 复制日志", fill=(shade(T["primary"], 0.7)), font=(
         T["ui"], 9), anchor="e")
        def copy_logs(_e):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append("\n".join(self.logs))
                self.c.itemconfigure(t, text="✓ 已复制")
                self.root.after(1200, lambda: self.c.itemconfigure(t, text="⧉ 复制日志"))
            except Exception:
                pass
        self.c.tag_bind(t, "<Button-1>", copy_logs)
        self.c.tag_bind(t, "<Enter>", lambda e: self.c.itemconfigure(t, fill=(T["primary"])))
        self.c.tag_bind(t, "<Leave>", lambda e: self.c.itemconfigure(t, fill=(shade(T["primary"], 0.7))))

    def _refresh_autostart(self):
        """根据注册表实际状态刷新自启按钮的文案与颜色"""
        tag = getattr(self, "_btn_auto", None)
        d = self._btn_items.get(tag) if tag else None
        if not d:
            return
        on = autostart.is_enabled()
        k = self.T["key"]
        if k == "hud":
            label = "◈ 自启 · 已开" if on else "◈ 自启 · 已关"
        elif k == "cyber":
            label = "◈ AUTO ON" if on else "◈ AUTO OFF"
        else:
            label = "[ AUTO:ON ]" if on else "[ AUTO:OFF ]"
        d["color"] = self.T["ok"] if on else self.T["text2"]
        hv = d.get("k", 0.0)
        self.c.itemconfigure(d["rect"], fill=(shade(d["color"], 0.13 + 0.32 * hv)),
          outline=(shade(d["color"], 0.5 + 0.5 * hv)))
        self.c.itemconfigure(d["text"], text=label, fill=d["color"])

    def _build(self):
        k = self.T["key"]
        self.title_school = None
        self.title_cyber = None
        self.title_matrix = None
        if k == "hud":
            self._layout_hud()
        else:
            if k == "cyber":
                self._layout_cyber()
            else:
                self._layout_matrix()
        self._corner_marks()
        self._titlebar()
        self._refresh_autostart()

    def _profile_name(self):
        """当前学校显示名（无配置时退回 SSID）"""
        cfg = self.cfg or {}
        return cfg.get("_profile_name") or cfg.get("ssid") or "未配置学校"

    def _school_title(self):
        """HUD 标题栏文本：学校名 · SSID（二者相同时只显示一个）"""
        ssid = (self.cfg or {}).get("ssid") or ""
        name = self._profile_name()
        if ssid:
            if name != ssid:
                return "%s · %s" % (name, ssid)
        return name or ssid or "未配置学校"

    def _school_cyber_text(self):
        """赛博主题副标题：SSID 逐字分隔 + 学校名"""
        cfg = self.cfg or {}
        ssid = (cfg.get("ssid") or "").upper()
        name = cfg.get("_profile_name") or ""
        parts = []
        if ssid:
            parts.append(" ".join(ssid))
        if name:
            if name.upper() != ssid:
                parts.append(name)
        return "   ·   ".join(parts) or "W I R E L E S S   A U T H"

    def _school_matrix_text(self):
        """矩阵主题右上角标识：[ SSID // 学校名 ]"""
        cfg = self.cfg or {}
        ssid = (cfg.get("ssid") or "").upper() or "NO-SSID"
        name = self._profile_name()
        if name.upper() == ssid:
            return "[ %s ]" % ssid
        return "[ %s // %s ]" % (ssid, name)

    def _refresh_title(self):
        """学校切换后重建三套主题里的学校文字（不重建整块画布）"""
        try:
            if getattr(self, "title_school", None):
                self.c.itemconfigure((self.title_school), text=(self._school_title()))
            if getattr(self, "title_cyber", None):
                self.c.itemconfigure((self.title_cyber), text=(self._school_cyber_text()))
            if getattr(self, "title_matrix", None):
                self.c.itemconfigure((self.title_matrix), text=(self._school_matrix_text()))
        except Exception:
            pass

    def _titlebar(self):
        T = self.T
        self.c.create_rectangle(0, 0, W, 44, fill=(shade(T["bg"], 1.6)), outline="")
        self._glow_line((0, 44, W, 44), T["primary"], 1, 1)
        self._glow_text(22, 22, "◤ CAMPUS NET", (T["primary"]), (
         T["mono"], 13, "bold"),
          anchor="w")
        self.title_school = self.c.create_text(200, 23, text=(self._school_title()), fill=(T["text2"]),
          font=(T["ui"], 9),
          anchor="w")
        self.c.create_text((W - 150), 23, text=("◈ %s" % T["name"]), fill=(shade(T["primary"], 0.65)),
          font=(T["ui"], 8),
          anchor="e")
        gear = self.c.create_text((W - 96), 22, text="⚙ 设置", fill=(shade(T["primary"], 0.9)), font=(
         T["ui"], 11),
          anchor="e")
        self.c.tag_bind(gear, "<Button-1>", lambda e: self.open_settings())
        self.c.tag_bind(gear, "<Enter>", lambda e: self.c.itemconfigure(gear, fill=(T["primary"])))
        self.c.tag_bind(gear, "<Leave>", lambda e: self.c.itemconfigure(gear, fill=(shade(T["primary"], 0.9))))
        cx = W - 30
        close_id = self.c.create_text(cx, 22, text="✕", fill=(T["text2"]), font=(
         T["ui"], 12, "bold"))
        self.c.tag_bind(close_id, "<Button-1>", lambda e: self.on_close())
        min_id = self.c.create_text((cx - 34), 22, text="—", fill=(T["text2"]), font=(
         T["ui"], 12, "bold"))
        self.c.tag_bind(min_id, "<Button-1>", lambda e: self.do_minimize())

    def _layout_hud(self):
        T = self.T
        self._grid()
        self.cx, self.cy, self.r = (205, 235, 108)
        for i, f in enumerate((1.3, 1.18, 1.06)):
            self.c.create_oval((self.cx - self.r * f), (self.cy - self.r * f), (self.cx + self.r * f),
              (self.cy + self.r * f), outline=(shade(T["primary"], 0.18 - i * 0.04)),
              width=1)
        else:
            for k in range(60):
                a = math.radians(k * 6 - 90)
                inner = self.r * 1.11
                outer = self.r * (1.24 if k % 5 == 0 else 1.16)
                self.c.create_line((self.cx + math.cos(a) * inner), (self.cy + math.sin(a) * inner), (self.cx + math.cos(a) * outer),
                  (self.cy + math.sin(a) * outer), fill=(shade(T["primary"], 0.55 if k % 5 == 0 else 0.22)),
                  width=1)
            else:
                self.ring_bg = self.c.create_oval((self.cx - self.r), (self.cy - self.r), (self.cx + self.r),
                  (self.cy + self.r), outline=(shade(T["dim"], 0.8)),
                  width=8)
                self.ring = self.c.create_arc((self.cx - self.r), (self.cy - self.r), (self.cx + self.r),
                  (self.cy + self.r), start=90,
                  extent=(-270),
                  style="arc",
                  outline=(shade(T["primary"], 0.35)),
                  width=8)
                self.ring_rot = self.c.create_arc((self.cx - self.r - 12), (self.cy - self.r - 12), (self.cx + self.r + 12),
                  (self.cy + self.r + 12), start=0,
                  extent=52,
                  style="arc",
                  outline=(T["accent"]),
                  width=2)
                self.state_txt = self.c.create_text((self.cx), (self.cy - 10), text="OFFLINE", fill=(T["bad"]),
                  font=(T["mono"], 20, "bold"))
                self.c.create_text((self.cx), (self.cy + 20), text="— 连接状态 —", fill=(T["text2"]),
                  font=(T["ui"], 8))
                self.sub_txt = self.c.create_text((self.cx), (self.cy + 46), text="等待启动", fill=(T["text2"]),
                  font=(T["mono"], 9))
                dx = 380
                self.c.create_text(dx, 150, text="▍ 实时数据", fill=(T["primary"]), font=(
                 T["ui"], 10, "bold"),
                  anchor="w")
                self._glow_line((dx, 166, W - 40, 166), shade(T["primary"], 0.4), 1, 1)
                self.metrics = {}
                rows = [('SSID', '网 络'), ('SIGNAL', '信 号'), ('IP', '内网地址'), 
                 ('RELOGIN', '重连次数'),  ('UPTIME', '在线时长')]
                for i, (k, label) in enumerate(rows):
                    y = 194 + i * 34
                    self.c.create_text(dx, y, text=k, fill=(T["text2"]), font=(T["mono"], 9), anchor="w")
                    self.metrics[k] = self.c.create_text((W - 40), y, text="--", fill=(T["text"]), font=(
                     T["mono"], 10, "bold"),
                      anchor="e")
                else:
                    iy = 400
                    self.c.create_text(40, iy, text="▍ 接入凭据", fill=(T["primary"]), font=(
                     T["ui"], 10, "bold"),
                      anchor="w")
                    self._glow_line((40, iy + 14, W - 40, iy + 14), shade(T["primary"], 0.4), 1, 1)
                    self.c.create_text(42, (iy + 44), text="账号", fill=(T["text2"]), font=(T["ui"], 9), anchor="w")
                    self.e_user = self._entry(100, iy + 32, 300, 26)
                    self.c.create_text(42, (iy + 84), text="密码", fill=(T["text2"]), font=(T["ui"], 9), anchor="w")
                    self.e_pwd = self._entry(100, (iy + 72), 300, 26, show="●")
                    self._pwd_toggle(410, iy + 85)
                    self.c.create_text(430, (iy + 44), text="账号为手机号", fill=(T["text2"]), font=(
                     T["ui"], 8),
                      anchor="w")
                    by = iy + 116
                    self._button(40, by, 132, 34, "⚡ 立即认证", self.do_login)
                    self._button(184, by, 112, 34, "⟳ 重新检测", self.do_check, "ghost")
                    self._btn_auto = self._button(308, by, 112, 34, "◈ 开机自启", self.do_autostart, "ghost")
                    self._button(432, by, 100, 34, "✕ 退出", self.root.destroy, "ghost")
                    ly = by + 56
                    self.c.create_text(40, ly, text="▍ 系统日志", fill=(T["primary"]), font=(
                     T["ui"], 10, "bold"),
                      anchor="w")
                    self._log_copy(W - 40, ly + 2)
                    self._glow_line((40, ly + 14, W - 40, ly + 14), shade(T["primary"], 0.4), 1, 1)
                    self.log_box = (40, ly + 26, W - 40, H - 30)
                    self.log_rect = (win11fx.round_rect)(self.c, *(self.log_box), **{'outline':shade(T["primary"], 0.28), 
                     'fill':shade(T["panel"], 1.2)})
                    self.log_items = []
                    self.scan = self.c.create_line(40, (ly + 26), (W - 40), (ly + 26), fill=(shade(T["primary"], 0.35)),
                      width=2)

    def _layout_cyber(self):
        T = self.T
        for x in range(20, W, 26):
            for y in range(60, H, 26):
                self.c.create_oval((x - 1), (y - 1), (x + 1), (y + 1), fill=(shade(T["line"], 0.9)), outline="")

        for dx, dy, col in (
         (
          -3, 0, T["accent"]), (3, 0, T["bad"]), (0, 0, T["text"])):
            self.c.create_text((W / 2 + dx), (96 + dy), text="CAMPUS  LINK", fill=col,
              font=(T["mono"], 34, "bold"))
        else:
            self._glow_line((W / 2 - 200, 128, W / 2 + 200, 128), T["primary"], 2, 3)
            self.title_cyber = self.c.create_text((W / 2), 148, text=(self._school_cyber_text()), fill=(T["text2"]),
              font=(T["mono"], 8))
            self.pill = self.c.create_rectangle((W / 2 - 130), 178, (W / 2 + 130), 222, outline=(T["bad"]),
              width=2,
              fill=(shade(T["bad"], 0.12)))
            self.state_txt = self.c.create_text((W / 2), 200, text="● OFFLINE", fill=(T["bad"]),
              font=(T["mono"], 13, "bold"))
            self.sub_txt = self.c.create_text((W / 2), 244, text="等待启动", fill=(T["text2"]),
              font=(T["mono"], 9))
            self.ring_rot = self.c.create_line(0, 0, 1, 1, fill=(T["bg"]))
            cw, ch2 = (330, 92)
            for i, (title, items) in enumerate((
             (
              "NETWORK", [('SSID', '网 络'), ('IP', '内网地址')]),
             (
              "SESSION", [('RELOGIN', '重连'), ('UPTIME', '在线')]))):
                x0 = 40 + i * (cw + 20)
                y0 = 276

            for gi in range(3, 0, -1):
                self.c.create_rectangle((x0 - gi), (y0 - gi), (x0 + cw + gi), (y0 + ch2 + gi), outline=(shade(T["primary"], 0.1 * gi / 3)),
                  width=1)
            else:
                self.c.create_rectangle(x0, y0, (x0 + cw), (y0 + ch2), outline=(shade(T["primary"], 0.55)), width=1,
                  fill=(shade(T["panel"], 1.4)))
                self.c.create_text((x0 + 14), (y0 + 20), text=title, fill=(T["primary"]), font=(
                 T["mono"], 10, "bold"),
                  anchor="w")
                self._glow_line((x0 + 14, y0 + 34, x0 + cw - 14, y0 + 34), shade(T["primary"], 0.35), 1, 1)
                for j, (k, label) in enumerate(items):
                    yy = y0 + 54 + j * 24
                    self.c.create_text((x0 + 14), yy, text=label, fill=(T["text2"]), font=(
                     T["ui"], 9),
                      anchor="w")
                    self.metrics[k] = self.c.create_text((x0 + cw - 14), yy, text="--", fill=(T["text"]),
                      font=(T["mono"], 10, "bold"),
                      anchor="e")
                else:
                    iy = 396
                    self.c.create_text(40, iy, text="CREDENTIAL", fill=(T["primary"]), font=(
                     T["mono"], 10, "bold"),
                      anchor="w")
                    self._glow_line((40, iy + 14, W - 40, iy + 14), shade(T["primary"], 0.4), 1, 1)
                    self.e_user = self._entry(40, iy + 30, 330, 30)
                    self.e_pwd = self._entry(390, (iy + 30), 330, 30, show="●")
                    self._pwd_toggle(660, iy + 73)
                    self.c.create_text(40, (iy + 72), text="账号（手机号）", fill=(T["text2"]), font=(
                     T["ui"], 8),
                      anchor="w")
                    self.c.create_text(390, (iy + 72), text="密码", fill=(T["text2"]), font=(
                     T["ui"], 8),
                      anchor="w")
                    by = iy + 96
                    self._button(40, by, 200, 38, "⚡ CONNECT", self.do_login)
                    self._button(252, by, 150, 38, "⟳ RESCAN", self.do_check, "ghost")
                    self._btn_auto = self._button(414, by, 150, 38, "◈ AUTORUN", self.do_autostart, "ghost")
                    self._button(576, by, 144, 38, "✕ EXIT", self.root.destroy, "ghost")
                    ly = by + 56
                    self.c.create_text(40, ly, text="TELEMETRY", fill=(T["primary"]), font=(
                     T["mono"], 10, "bold"),
                      anchor="w")
                    self._log_copy(W - 40, ly + 2)
                    self.wave_y = ly + 34
                    self.wave = (self.c.create_line)(*[40, self.wave_y] * 60, fill=T["primary"], width=2, smooth=True)
                    self.log_box = (40, ly + 64, W - 40, H - 28)
                    self.log_rect = (win11fx.round_rect)(self.c, *(self.log_box), **{'outline':shade(T["primary"], 0.28), 
                     'fill':shade(T["panel"], 1.1)})
                    self.log_items = []
                    self.scan = self.c.create_line(40, (ly + 66), (W - 40), (ly + 66), fill=(shade(T["primary"], 0.3)),
                      width=2)

    def _layout_matrix(self):
        T = self.T
        self._grid()
        self._glow_text(40, 96, "CAMPUS NET", (T["primary"]), (
         T["mono"], 26, "bold"),
          anchor="w")
        self.c.create_text(42, 128, text="==============================================================", fill=(shade(T["primary"], 0.45)), font=(
         T["mono"], 9),
          anchor="w")
        self.title_matrix = self.c.create_text((W - 40), 108, text=(self._school_matrix_text()), fill=(T["text2"]),
          font=(T["mono"], 9),
          anchor="e")
        self._glow_line((40, 156, W - 40, 156), T["primary"], 1, 2)
        self.c.create_text(40, 182, text="> SYSTEM STATUS", fill=(T["text2"]), font=(
         T["mono"], 9),
          anchor="w")
        self.state_txt = self.c.create_text(200, 182, text="[ OFFLINE ]", fill=(T["bad"]), font=(
         T["mono"], 11, "bold"),
          anchor="w")
        self.sub_txt = self.c.create_text(40, 204, text="> 等待启动", fill=(T["text2"]), font=(
         T["mono"], 9),
          anchor="w")
        self.ring_rot = self.c.create_line(0, 0, 1, 1, fill=(T["bg"]))
        self.metrics = {}
        rows = [
         ('SSID', 'NETWORK'), ('SIGNAL', 'SIGNAL '), ('IP', 'LAN IP '), 
         ('RELOGIN', 'RELOGIN'),  ('UPTIME', 'UPTIME ')]
        for i, (k, label) in enumerate(rows):
            y = 240 + i * 26
            self.c.create_text(48, y, text=("├─ " + label), fill=(T["text2"]), font=(
             T["mono"], 9),
              anchor="w")
            self.metrics[k] = self.c.create_text(300, y, text="--", fill=(T["text"]), font=(
             T["mono"], 9, "bold"),
              anchor="w")
        else:
            self.c.create_text(40, 400, text="> AUTH INPUT", fill=(T["primary"]), font=(
             T["mono"], 10, "bold"),
              anchor="w")
            self.c.create_text(40, 428, text="user  :", fill=(T["text2"]), font=(T["mono"], 10), anchor="w")
            self.e_user = self._entry(110, 416, 280, 26)
            self.c.create_text(40, 464, text="pass  :", fill=(T["text2"]), font=(T["mono"], 10), anchor="w")
            self.e_pwd = self._entry(110, 452, 280, 26, show="●")
            self._pwd_toggle(410, 464)
            self.c.create_text(410, 428, text="> 手机号登录", fill=(T["text2"]), font=(
             T["mono"], 8),
              anchor="w")
            by = 494
            self._button(40, by, 150, 32, "[ CONNECT ]", self.do_login)
            self._button(202, by, 130, 32, "[ RESCAN ]", self.do_check, "ghost")
            self._btn_auto = self._button(344, by, 130, 32, "[ AUTORUN ]", self.do_autostart, "ghost")
            self._button(490, by, 110, 32, "[ EXIT ]", self.root.destroy, "ghost")
            ly = by + 54
            self.c.create_text(40, ly, text="> LOG STREAM", fill=(T["primary"]), font=(
             T["mono"], 10, "bold"),
              anchor="w")
            self._log_copy(W - 40, ly + 2)
            self._glow_line((40, ly + 14, W - 40, ly + 14), shade(T["primary"], 0.4), 1, 1)
            self.log_box = (40, ly + 24, W - 40, H - 26)
            self.log_rect = (win11fx.round_rect)(self.c, *(self.log_box), **{'outline':shade(T["primary"], 0.28), 
             'fill':"#000000"})
            self.log_items = []
            self.scan = self.c.create_line(40, (ly + 24), (W - 40), (ly + 24), fill=(shade(T["primary"], 0.4)),
              width=2)

    def _bind(self):
        self.c.bind("<Button-1>", self._drag_start)
        self.c.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<Escape>", lambda e: self.on_close())
        self.root.bind("<Map>", self._on_map)
        self.root.bind("<Enter>", lambda e: self._set_active(True))
        self.root.bind("<Leave>", lambda e: self._set_active(False))

    def _set_active(self, on):
        self._active = on

    def on_close(self):
        if self.state.running:
            try:
                from tkinter import messagebox
                if not messagebox.askokcancel("退出确认", "关闭窗口会停止自动重连。\n\n若已开启「开机自启」，下次开机仍会在后台自动运行。\n\n确定退出？"):
                    return
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def do_minimize(self):
        """无边框窗口系统不允许直接最小化，先临时去掉 overrideredirect"""
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception:
            pass

    def _on_map(self, _e=None):
        """从任务栏恢复后重新变回无边框"""
        try:
            if self.root.state() == "normal":
                if not self.root.overrideredirect():
                    self.root.after(15, lambda: self.root.overrideredirect(True))
        except Exception:
            pass

    def _drag_start(self, e):
        self._drag = (
         e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        if e.y_root - self.root.winfo_y() < 44:
            self.root.geometry("+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1]))

    def log(self, msg):
        self.logs.append("%s  %s" % (time.strftime("%H:%M:%S"), msg))
        del self.logs[:-9]
        self.last_msg = msg
        self._render_logs()
        try:
            config.log(msg)
        except Exception:
            pass

    def _start_guard(self):
        if self.guard:
            if self.guard.is_alive():
                self.guard.wake()
                return
        self.guard = guard_mod.Guard((self.cfg), (self.state), on_change=(self._on_state_change))
        self.guard.start()
        self.root.after(700, self._check_guard)

    def _check_guard(self):
        if self.state.running:
            self.log("守护已生效，掉线会自动重连")
        else:
            self.log("已有后台实例在运行，本窗口仅做手动认证")

    def _on_state_change(self):
        try:
            self.root.after(0, self._apply_state)
        except Exception:
            pass

    def _apply_state(self):
        st = self.state
        if st.online and not self.online:
            self._online_since = time.time()
        elif not st.online:
            self._online_since = None
        self.online = st.online
        if st.ssid and st.ssid != "—":
            self.ssid = st.ssid
        self.relogin = st.total_relogin
        new = st.logs[self._seen:]
        if new:
            self._seen = len(st.logs)
            for m in new:
                self.logs.append("%s  %s" % (time.strftime("%H:%M:%S"), m))
            del self.logs[:-9]
            self._render_logs()

        self._refresh_metrics()

    def _render_logs(self):
        T = self.T
        for it in self.log_items:
            self.c.delete(it)
        else:
            self.log_items = []
            x1, y1, x2, y2 = self.log_box
            lines = self.logs[-7:]
            bottom = y2 - 20
            for i, line in enumerate(reversed(lines)):
                it = self.c.create_text((x1 + 14), (bottom - i * 19), text=("› " + line[:110]), fill=(T["text"]),
                  font=(T["mono"], 9),
                  anchor="w")
                self.log_items.append(it)

    def open_settings(self):
        """打开高级设置；保存后同步学校标题、守护配置与凭据输入框"""
        from settings import SettingsDialog

        def saved(cfg):
            fresh = dict(cfg)
            self.cfg = fresh
            if self.guard:
                if self.guard.is_alive():
                    try:
                        self.guard.cfg = fresh
                        self.guard.wake()
                    except Exception:
                        pass

            self._sync_credentials()
            self._refresh_title()
            self.log("设置已保存 · 学校：%s · 认证页：%s" % (
             cfg.get("_profile_name") or cfg.get("ssid") or "-",
             cfg.get("portal_url") or "自动探测"))

        SettingsDialog(self.root, self.T, saved)

    def _sync_credentials(self):
        """把配置里的账号/密码回填到主界面输入框"""
        try:
            self.e_user.delete(0, "end")
            self.e_user.insert(0, (self.cfg or {}).get("username", ""))
            self.e_pwd.delete(0, "end")
            self.e_pwd.insert(0, (self.cfg or {}).get("password", ""))
        except Exception:
            pass

    def do_login(self):
        user = self.e_user.get().strip()
        pwd = self.e_pwd.get()
        if not (user and pwd):
            self.log("请先填写账号和密码")
            return
        self.log("正在提交认证…")

        def work():
            ip = netutil.wlan_ip()
            if netutil.internet_ok(bind_ip=ip):
                self.root.after(0, lambda: self.log("WLAN 已认证，无需重复登录"))
                return
            cfg = dict(self.cfg)
            cfg["username"] = user
            cfg["password"] = pwd
            ok, msg = portal.login(cfg, bind_ip=ip)
            self.root.after(0, lambda: self._after_login(ok, msg))

        threading.Thread(target=work, daemon=True).start()

    def _after_login(self, ok, msg):
        self.log(("✓ " if ok else "✗ ") + msg)
        if ok:
            self.online = True
            cfg = config.load()
            cfg["username"] = self.e_user.get().strip()
            cfg["password"] = self.e_pwd.get()
            config.save(cfg)
            self.cfg = cfg
            self.log("配置已保存")
            self._start_guard()
            if self.guard:
                self.guard.wake()

    def do_check(self):
        self.log("重新检测网络…")

        def work():
            ip = netutil.wlan_ip()
            ok = netutil.internet_ok(bind_ip=ip)
            self.root.after(0, lambda: self.log("检测完成：%s" % ("已联网" if ok else "需要认证")))

        threading.Thread(target=work, daemon=True).start()

    def do_autostart(self):
        if autostart.is_enabled():
            autostart.disable()
            self.log("已关闭开机自启")
        else:
            ok, _ = autostart.enable()
            self.log("已开启开机自启" if ok else "设置失败")
        self._refresh_autostart()

    def _animate(self):
        try:
            if not self.root.winfo_viewable():
                self.root.after(400, self._animate)
                return
        except Exception:
            pass

        now = time.perf_counter()
        dt = now - self._last_frame
        if dt > 0.25:
            dt = 0.016
        self._last_frame = now
        self.t += dt

        if self._intro < 1.0:
            self._intro = min(1.0, self._intro + dt / 0.55)

        T = self.T
        try:
            target_k = 1.0 if self.online else 0.0
            self._state_k += (target_k - self._state_k) * min(1.0, dt * 7.0)
            if self.state.fatal:
                col = T["warn"]
            else:
                col = win11fx.lerp_color(T["bad"], T["ok"], self._state_k)
            breath = 0.7 + 0.3 * win11fx.pulse(self.t * 3.3)

            if self.T["key"] == "cyber":
                pts = []
                for i in range(60):
                    x = 40 + i * (W - 80) / 59.0
                    y = self.wave_y + math.sin(i * 0.35 + self.t * 2.4) * 12 * math.sin(self.t * 0.6 + i * 0.08)
                    pts += [x, y]
                self.c.coords(self.wave, *pts)
            elif self.c.type(self.ring_rot) == "arc":
                ang = self.t * 63 % 360
                self.c.itemconfigure(self.ring_rot, start=ang)

            lx1, ly1, lx2, ly2 = self.log_box
            ph = self.t * 0.45 % 2.0
            tri = ph if ph < 1.0 else 2.0 - ph
            sy = ly1 + 12 + win11fx.ease_in_out_cubic(tri) * (ly2 - ly1 - 24)
            self.c.coords(self.scan, lx1, sy, lx2, sy)
            self.c.itemconfigure(self.scan, fill=shade(T["primary"], 0.16 + 0.26 * (1 - abs(0.5 - tri) * 2)))

            self._frame_i = getattr(self, "_frame_i", 0) + 1
            label = "PAUSED" if self.state.fatal else ("ONLINE" if self.online else "OFFLINE")
            state_changed = label != getattr(self, "_last_label", None)
            if state_changed or self._frame_i % 5 == 0:
                self._last_label = label
                text_col = shade(col, breath)
                if self.T["key"] == "hud":
                    self.c.itemconfigure(self.state_txt, fill=text_col, text=label)
                elif self.T["key"] == "cyber":
                    self.c.itemconfigure(self.state_txt, fill=text_col, text="● " + label)
                    self.c.itemconfigure(self.pill, outline=col, width=2)
                    self.c.itemconfigure(self.pill, fill=shade(col, 0.1))
                else:
                    self.c.itemconfigure(self.state_txt, fill=text_col, text="[ %s ]" % label)
                self.c.itemconfigure(self.sub_txt, fill=shade(T["text2"], 0.75 + 0.25 * breath))
                up = self.metrics.get("UPTIME")
                if up:
                    self.c.itemconfigure(up, text=self._uptime_text())

            for d in self._btn_items.values():
                if abs(d["target"] - d["k"]) > 0.004:
                    d["k"] += (d["target"] - d["k"]) * min(1.0, dt * 14.0)
                    c0 = d["color"]
                    self.c.itemconfigure(d["rect"], fill=shade(c0, 0.13 + 0.32 * d["k"]),
                      outline=shade(c0, 0.5 + 0.5 * d["k"]))
                    self.c.itemconfigure(d["text"], fill=win11fx.lerp_color(c0, "#ffffff", d["k"] * 0.9))
        except Exception:
            pass

        self.root.after(10 if self._active else 45, self._animate)

    def set_status(self, online=None, ssid=None, relogin=None):
        if online is not None:
            self.online = online
        if ssid is not None:
            self.ssid = ssid
        if relogin is not None:
            self.relogin = relogin
        self._refresh_metrics()

    def _read_ip(self):
        now = time.time()
        if now - self._ip_cache[0] < 10:
            return self._ip_cache[1]
        val = netutil.wlan_ip()
        self._ip_cache = (now, val)
        return val

    def _read_latency(self):
        now = time.time()
        if now - self._lat_cache[0] < 6:
            return self._lat_cache[1]
        val = netutil.ping_ms(src_ip=(self._read_ip() or None))
        self._lat_cache = (now, val)
        return val

    def _read_signal(self):
        """信号强度，5 秒缓存（netsh 调用较慢，不能每帧跑）"""
        now = time.time()
        if now - self._sig_cache[0] < 5:
            return self._sig_cache[1]
        val = netutil.signal_percent()
        self._sig_cache = (now, val)
        return val

    def _uptime_text(self):
        if not (self.online and self._online_since):
            return "--:--:--"
        s = int(time.time() - self._online_since)
        return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)

    def _refresh_metrics(self):
        T = self.T
        sig = self._read_signal() if self.online else None
        vals = {'SSID':self.ssid[:18],
         'SIGNAL':"%d%%" % sig if (sig is not None) else "--", 
         'IP':self._read_ip() or "--" if (self.online) else "--", 
         'RELOGIN':str(self.relogin), 
         'UPTIME':(self._uptime_text)()}
        for k, item in getattr(self, "metrics", {}).items():
            self.c.itemconfigure(item, text=(vals.get(k, "--")))
        else:
            if getattr(self, "sub_txt", None):
                if not self.online:
                    msg = getattr(self.state, "last_msg", "") or "等待接入"
                    if getattr(self.state, "fatal", False):
                        msg = "已暂停 · " + msg
                    text = msg[:30]
                else:
                    lat = self._read_latency()
                    text = "链路稳定 · %d ms" % lat if lat is not None else "链路已连接"
                self.c.itemconfigure((self.sub_txt), text=text)


def _cfg_signature(cfg):
    """用于判断配置是否变化（学校/凭据/认证页/字段映射）"""
    return (
     cfg.get("_active"), cfg.get("ssid"), cfg.get("username"),
     cfg.get("password"), cfg.get("portal_url"),
     cfg.get("user_field"), cfg.get("pwd_field"), cfg.get("extra_params"))


def run_silent():
    cfg = config.load()
    if not (cfg.get("username") and cfg.get("password")):
        config.log("未配置账号密码，后台守护不启动")
        return
    st = guard_mod.State()
    g = guard_mod.Guard(cfg, st)
    g.start()
    config.log("静默守护已启动 pid=%s" % os.getpid())

    last_sig = _cfg_signature(cfg)
    try:
        while True:
            time.sleep(20)
            try:
                fresh = config.load(strict=True)
            except Exception as e:
                config.log("配置读取失败，继续使用旧配置（守护不受影响）：%r" % (e,))
                continue
            sig = _cfg_signature(fresh)
            if sig == last_sig:
                continue
            if not (fresh.get("username") and fresh.get("password")):
                config.log("检测到配置变更，但新配置缺少账号或密码，后台守护已停止（「%s」）" % (fresh.get("_profile_name") or "未命名"))
                g.stop()
                return
            g.cfg = fresh
            last_sig = sig
            g.wake()
            config.log("检测到配置变更，后台守护已切换为「%s」" % (fresh.get("_profile_name") or "未命名"))
    except KeyboardInterrupt:
        g.stop()


def main():
    args = [a.lower() for a in sys.argv[1:]]
    if "--silent" in args:
        run_silent()
        return
    # 默认使用「静蓝」新界面；--classic 回退到原科幻风三主题
    if "--classic" not in args:
        import ui_quiet
        ui_quiet.main()
        return
    theme = "hud"
    for a in args:
        if a in THEMES:
            theme = a
    else:
        root = tk.Tk()
        app = ScifiUI(root, theme)
        cfg = config.load()
        app.e_user.insert(0, cfg.get("username", ""))
        app.e_pwd.insert(0, cfg.get("password", ""))
        app.log("界面已就绪 · 学校：" + (cfg.get("_profile_name") or "未配置"))
        if cfg.get("username") and cfg.get("password"):
            app._start_guard()
        else:
            app.log("请填写账号密码，然后点击认证")
            app.log("其他学校请点右上角菜单填写认证页地址")
        root.mainloop()


if __name__ == "__main__":
    main()