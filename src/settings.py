# decompyle3 version 3.8.0
# Python bytecode 3.8
# Decompiled from: Python 3.8.10 (tags/v3.8.10:3d8993a, May  3 2021, 11:48:03) [MSC v.1928 64 bit (AMD64)]
# Embedded file name: settings.py
"""高级设置：多学校配置切换 + 认证页地址 + 字段映射"""
import ctypes, threading, tkinter as tk
from tkinter import messagebox, simpledialog
import config, netutil, portal

def _shade(color, f):
    c = color.lstrip('#')
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    r, g, b = [max(0, min(255, int(v * f))) for v in (r, g, b)]
    return '#%02x%02x%02x' % (r, g, b)


def _dpi_scale():
    """与主界面同一套 DPI 比例；未开启 DPI 感知时自然退化为 1.0。"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, min(3.0, float(dpi) / 96.0))
    except Exception:
        return 1.0


S = _dpi_scale()


def px(v):
    """逻辑像素 -> 物理像素。"""
    return int(round(float(v) * S))


def _font(family, pt, bold=False):
    """磅值 -> 像素字号（负值），避免 tk scaling 把字放大而坐标没跟上。"""
    size = -max(7, int(round(float(pt) * 1.3333 * S)))
    return (family, size, 'bold') if bold else (family, size)


class SettingsDialog(object):
    __doc__ = '高级设置窗口（非模态阻塞式 Toplevel）'

    def __init__(self, master, theme, on_saved=None):
        self.T = theme
        self.on_saved = on_saved
        self.cfg = config.load()
        self.profiles = config.list_profiles()
        self._label2id = {}
        self._form_pid = ''
        w, h = (620, 700)
        self.top = tk.Toplevel(master)
        self.top.title('高级设置 · 学校与认证服务器')
        self.top.configure(bg=(theme['bg']))
        self.top.geometry('%dx%d+%d+%d' % (
         px(w), px(h), max(0, master.winfo_rootx() + px(60)),
         max(0, master.winfo_rooty() + px(16))))
        self.top.transient(master)
        self.top.grab_set()
        self.top.resizable(False, False)
        self._build(w, h)

    def _label(self, x, y, text, color=None, size=9, bold=False):
        T = self.T
        lb = tk.Label((self.top), text=text, bg=(T['bg']), fg=(color or T['text2']),
          font=_font(T['ui'], size, bold),
          anchor='w',
          justify='left')
        lb.place(x=px(x), y=px(y))
        return lb

    def _entry(self, x, y, w, val='', show=''):
        T = self.T
        e = tk.Entry((self.top), bg=(_shade(T['panel'], 1.8)), fg=(T['text']), insertbackground=(T['primary']),
          relief='flat',
          highlightthickness=1,
          highlightbackground=(_shade(T['primary'], 0.5)),
          highlightcolor=(T['primary']),
          font=_font(T['mono'], 10),
          show=show)
        e.insert(0, val or '')
        e.place(x=px(x), y=px(y), width=px(w), height=px(28))
        return e

    def _button(self, x, y, w, text, cmd, primary=True):
        T = self.T
        color = T['primary'] if primary else T['text2']
        bgc = T.get('btn_bg' if primary else 'btn2_bg') or _shade(color, 0.16 if primary else 0.1)
        fgc = T.get('btn_fg' if primary else 'btn2_fg') or color
        b = tk.Button((self.top), text=text, command=cmd, font=_font(T['ui'], 9, True), bg=bgc,
          fg=fgc,
          activebackground=(_shade(bgc, 0.9)),
          activeforeground=fgc,
          disabledforeground=(_shade(fgc, 0.62)),
          relief='flat',
          bd=0,
          cursor='hand2')
        b.place(x=px(x), y=px(y), width=px(w), height=px(32))
        return b

    def _school_option_menu(self, x, y, w, h):
        """构建学校下拉选择控件"""
        T = self.T
        self.var_profile = tk.StringVar(value='')
        names = list(self._label2id.keys())
        if not names:
            names = [
             '（无）']
        self.om = (tk.OptionMenu)(self.top, self.var_profile, *names)
        self.om.configure(bg=(_shade(T['panel'], 1.8)), fg=(T['text']), activebackground=(_shade(T['primary'], 0.25)),
          activeforeground='#ffffff',
          relief='flat',
          bd=0,
          highlightthickness=1,
          highlightbackground=(_shade(T['primary'], 0.5)),
          highlightcolor=(T['primary']),
          font=_font(T['ui'], 9),
          anchor='w',
          cursor='hand2')
        try:
            self.om['menu'].configure(bg=(_shade(T['panel'], 1.5)), fg=(T['text']), activebackground=(_shade(T['primary'], 0.35)),
              activeforeground='#ffffff',
              font=_font(T['ui'], 9),
              bd=0)
        except Exception:
            pass
        else:
            self.om.place(x=px(x), y=px(y), width=px(w), height=px(h))
            return self.om

    def _build_label_map(self):
        """构造「下拉显示文本 -> profile id」映射，重名自动加后缀"""
        mapping = {}
        for prof in self.profiles:
            label = '%s · %s' % (prof.get('name') or '未配置学校',
             prof.get('ssid') or '未设 SSID')
            while label in mapping:
                label += ' •'
            mapping[label] = prof.get('id')
        self._label2id = mapping
        return mapping

    def _label_of(self, pid):
        """反查指定 profile id 对应的下拉显示文本"""
        for label, ident in self._label2id.items():
            if ident == pid:
                return label
        else:
            return ''

    def _build(self, w, h):
        T = self.T
        self._build_label_map()
        self._label(24, 12, '◤ 学校配置', T['primary'], 11, True)
        self._label(24, 32, '下拉选择学校 →「切换」后下方所有字段自动刷新', T['text2'], 8)
        self._school_option_menu(24, 50, 300, 30)
        self.b_switch = self._button(340, 48, 74, '切换', self.do_switch)
        self.b_new = self._button(422, 48, 74, '新建', (self.do_new), primary=False)
        self.b_del = self._button(504, 48, 88, '删除', (self.do_delete), primary=False)
        self.lb_school = self._label(24, 88, '', T['text2'], 8)
        self._label(24, 110, '◤ 接入凭据', T['primary'], 11, True)
        self._label(24, 136, '校园 WiFi', T['text2'], 9)
        self.e_ssid = self._entry(110, 130, 220, '')
        self._label(342, 136, '路由器的 SSID，区分大小写', T['text2'], 8)
        self._label(24, 168, '账号', T['text2'], 9)
        self.e_user = self._entry(110, 162, 220, '')
        self._label(342, 168, '手机号 / 学号', T['text2'], 8)
        self._label(24, 200, '密码', T['text2'], 9)
        self.e_pwd = self._entry(110, 194, 220, '', show='●')
        self._label(342, 200, 'DPAPI 加密保存，仅本机本账号可解', T['text2'], 8)
        self._label(24, 228, '◤ 认证服务器', T['primary'], 11, True)
        self._label(24, 248, '留空则自动探测；其他学校填写其登录页完整地址', T['text2'], 8)
        self.e_url = self._entry(24, 268, w - 48, '')
        self.b_test = self._button(24, 300, 110, '识别此地址', self.do_analyze)
        self.lb_result = self._label(146, 308, '点击「识别此地址」探测系统类型', T['text2'], 8)
        self._label(24, 336, '◤ 字段映射', T['primary'], 11, True)
        self._label(24, 356, '自动识别不准时手动填写表单里的 input name，留空则自动', T['text2'], 8)
        self._label(24, 386, '账号字段', T['text2'], 9)
        self.e_user_field = self._entry(96, 380, 170, '')
        self._label(288, 386, '密码字段', T['text2'], 9)
        self.e_pwd_field = self._entry(360, 380, 170, '')
        self._label(24, 422, '额外参数', T['text2'], 9)
        self.e_extra = self._entry(96, 416, 434, '')
        self._label(24, 448, '形如 a=1&b=2，会一并提交给认证接口', T['text2'], 8)
        self._label(24, 474, '◤ 运行参数', T['primary'], 11, True)
        self._label(24, 500, '检测间隔', T['text2'], 9)
        self.e_int = self._entry(96, 494, 70, '')
        self._label(176, 500, '秒（建议 15~30）', T['text2'], 8)
        self._button(24, 528, 130, '导出诊断包', (self.do_diag), primary=False)
        self.lb_diag = self._label(166, 536, '认证不通时点这里，把生成的文件夹发给开发者', T['text2'], 8)
        tk.Label((self.top), text='支持：城市热点 ePortal（Dr.COM）、标准网页表单', bg=(T['bg']),
          fg=(_shade(T['text2'], 0.85)),
          font=_font(T['ui'], 8),
          justify='left',
          anchor='w').place(x=px(24), y=px(566))
        tk.Frame((self.top), bg=(_shade(T['primary'], 0.35)), height=px(1)).place(x=px(24),
          y=px(h - 96),
          width=px(w - 48))
        self._button(24, h - 74, 120, '保存', self.do_save)
        self._button(154, (h - 74), 90, '取消', (self.top.destroy), primary=False)
        self._button((w - 154), (h - 74), 130, '打开配置目录', (lambda: __import__('os').startfile(config.app_dir())),
          primary=False)
        self.lb_footer = self._label(24, h - 36, '配置路径：' + config.CONFIG_PATH, _shade(T['text2'], 0.7), 7)
        self._refresh_form(config.get_active())

    def _collect_fields(self):
        """收集表单里的所有字段（返回扁平 dict）"""
        url = self.e_url.get().strip()
        if url:
            if not url.lower().startswith('http'):
                url = 'http://' + url
        try:
            interval = int(self.e_int.get().strip() or 20)
        except ValueError:
            interval = 20
        return {'ssid': self.e_ssid.get().strip(),
                'username': self.e_user.get().strip(),
                'password': self.e_pwd.get(),
                'portal_url': url,
                'user_field': self.e_user_field.get().strip(),
                'pwd_field': self.e_pwd_field.get().strip(),
                'extra_params': self.e_extra.get().strip(),
                'check_interval': max(5, min(300, interval))}

    def _flush_form(self, pid=None):
        """把当前表单内容写回指定学校配置（不改变当前 active 学校）。

        Args:
            pid: 目标学校 id；缺省时写回表单当前显示的学校（``self._form_pid``）。

        Note:
            ``config.load()`` 返回的是 active 学校的字段快照，这里用
            ``cfg["_active"] = pid`` 把写入目标定向到 pid，``config.save()``
            只覆盖 pid 这条 profile，不会动其他学校、也不会改 active。
        """
        pid = pid or self._form_pid
        if not pid:
            return
        cfg = config.load()
        cfg['_active'] = pid
        cfg.update(self._collect_fields())
        config.save(cfg)

    def _refresh_form(self, pid):
        """把指定学校配置回填到表单控件（必要时先切换 active）"""
        if pid:
            if pid != config.get_active():
                config.switch_profile(pid)
        cfg = config.load()
        self.cfg = cfg
        active = cfg.get('_active') or ''
        self.e_ssid.delete(0, 'end')
        self.e_ssid.insert(0, cfg.get('ssid', ''))
        self.e_user.delete(0, 'end')
        self.e_user.insert(0, cfg.get('username', ''))
        self.e_pwd.delete(0, 'end')
        self.e_pwd.insert(0, cfg.get('password', ''))
        self.e_url.delete(0, 'end')
        self.e_url.insert(0, cfg.get('portal_url', ''))
        self.e_user_field.delete(0, 'end')
        self.e_user_field.insert(0, cfg.get('user_field', ''))
        self.e_pwd_field.delete(0, 'end')
        self.e_pwd_field.insert(0, cfg.get('pwd_field', ''))
        self.e_extra.delete(0, 'end')
        self.e_extra.insert(0, cfg.get('extra_params', ''))
        self.e_int.delete(0, 'end')
        self.e_int.insert(0, str(cfg.get('check_interval', 20)))
        self._form_pid = active
        self.lb_result.configure(text='点击「识别此地址」探测系统类型', fg=(self.T['text2']))
        self._reload_profiles(select=active)

    def _reload_profiles(self, select=None):
        """重新读取学校列表并刷新下拉控件与按钮状态"""
        self.profiles = config.list_profiles()
        self._build_label_map()
        menu = self.om['menu']
        menu.delete(0, 'end')
        for label in self._label2id:
            menu.add_command(label=label, command=(lambda v=label: self.var_profile.set(v)))
        else:
            pid = select or config.get_active()
            label = self._label_of(pid) or (list(self._label2id.keys()) or ['（无）'])[0]
            self.var_profile.set(label)
            total = len(self.profiles)
            try:
                if total <= 1:
                    self.b_del.configure(state='disabled')
                else:
                    self.b_del.configure(state='normal')
            except Exception:
                pass
            else:
                name = self._profile_name_of(pid)
                ssid = next((p.get('ssid') for p in self.profiles if p['id'] == pid), '')
                self.lb_school.configure(text=('当前：%s ｜ SSID：%s ｜ 共 %d 所学校%s' % (
                 name or '—', ssid or '—', total,
                 '（至少保留一所，删除已禁用）' if total <= 1 else '')),
                  fg=(self.T['primary'] if total > 1 else self.T['warn']))

    def _current_pid(self):
        """当前下拉选中的学校配置 id（注意：可能尚未「切换」）"""
        return self._label2id.get(self.var_profile.get())

    def _profile_name_of(self, pid):
        """按 id 取学校显示名（无名时显示「未配置学校」，找不到退回 id）"""
        for prof in self.profiles:
            if prof.get('id') == pid:
                return prof.get('name') or '未配置学校'
        else:
            return pid or '—'

    def _pending_selection(self):
        """下拉选中但尚未切换的学校 id；没有这种不一致时返回 "" """
        selected = self._current_pid()
        if selected:
            if self._form_pid:
                if selected != self._form_pid:
                    return selected
        return ''

    def do_switch(self):
        """切换到下拉选中的学校并刷新表单"""
        pid = self._current_pid()
        if not pid:
            self.lb_school.configure(text='请先在下拉框里选择一所学校', fg=(self.T['bad']))
            return
        if pid == self._form_pid:
            if pid == config.get_active():
                self._refresh_form(pid)
                self.lb_school.configure(text='当前已是该学校，字段已刷新', fg=(self.T['text2']))
                return
        try:
            self._flush_form(self._form_pid)
        except Exception:
            pass
        else:
            if not config.switch_profile(pid):
                self.lb_school.configure(text='切换失败，详见日志', fg=(self.T['bad']))
                return
            self._refresh_form(pid)
            self.lb_school.configure(text=('已切换到「%s」，字段已同步' % self._profile_name_of(pid)), fg=(self.T['ok']))

    def do_new(self):
        """新建学校配置：询问名称后创建并自动切换过去"""
        name = simpledialog.askstring('新建学校',
          '给这所学校起个名字（如：某某大学）\n\n其余字段（SSID / 账号 / 密码）创建后在表单里填写。', parent=(self.top))
        if not (name and name.strip()):
            return
        name = name.strip()
        try:
            self._flush_form(self._form_pid)
        except Exception:
            pass
        else:
            pid = config.add_profile(name, '', '', '', '')
            self._refresh_form(pid)
            self.lb_school.configure(text=('已新建「%s」，请填写 SSID / 账号 / 密码后保存' % name), fg=(self.T['ok']))

    def do_delete(self):
        """删除下拉选中的学校配置（至少保留一所）"""
        pid = self._current_pid()
        if len(self.profiles) <= 1:
            self.lb_school.configure(text='至少需要保留一所学校，无法删除',
              fg=(self.T['warn']))
            messagebox.showinfo('无法删除', '至少需要保留一所学校配置。', parent=(self.top))
            return
        if not pid:
            self.lb_school.configure(text='请先选择要删除的学校', fg=(self.T['bad']))
            return
        name = self._profile_name_of(pid)
        if not messagebox.askyesno('删除确认',
          ('确定删除学校配置「%s」？\n\n该学校的 SSID / 账号 / 密码会一并删除，且不可恢复。' % name),
          parent=(self.top)):
            return
        if not self._form_pid or self._form_pid != pid:
            try:
                self._flush_form(self._form_pid)
            except Exception:
                pass
            else:
                if not config.delete_profile(pid):
                    self.lb_school.configure(text='删除失败（至少需要保留一所学校）',
                      fg=(self.T['bad']))
                    return
        self._refresh_form(config.get_active())
        self.lb_school.configure(text=('已删除「%s」' % name), fg=(self.T['ok']))

    def do_analyze(self):
        """探测认证页类型并回填字段名"""
        url = self.e_url.get().strip()
        if not url:
            self.lb_result.configure(text='请先填写认证页地址', fg=(self.T['warn']))
            return
        if not url.lower().startswith('http'):
            url = 'http://' + url
        self.lb_result.configure(text='正在探测…', fg=(self.T['text2']))

        def work():
            ip = netutil.wlan_ip()
            info = portal.analyze(url, bind_ip=ip)
            self.top.after(0, lambda: self._show_result(info, url))

        threading.Thread(target=work, daemon=True).start()

    def _show_result(self, info, url):
        T = self.T
        if not info['ok']:
            self.lb_result.configure(text=('✗ ' + info['hint']), fg=(T['bad']))
            return
        self.e_url.delete(0, 'end')
        self.e_url.insert(0, url)
        text = '✓ %s｜%s' % (info['type_name'], info['hint'])
        self.lb_result.configure(text=(text[:72]), fg=(T['ok']))
        if info['user_field']:
            self.e_user_field.delete(0, 'end')
            self.e_user_field.insert(0, info['user_field'])
        if info['pwd_field']:
            self.e_pwd_field.delete(0, 'end')
            self.e_pwd_field.insert(0, info['pwd_field'])

    def do_diag(self):
        """导出诊断包（使用当前表单里的认证页地址）"""
        self.lb_diag.configure(text='正在抓取认证页生成诊断包…', fg=(self.T['text2']))

        def work():
            import diag
            cfg = dict(self.cfg)
            fields = self._collect_fields()
            cfg.update(fields)
            try:
                path, _ = diag.run(cfg)
                self.top.after(0, lambda: self._diag_done(path))
            except Exception as e:
                try:
                    self.top.after(0, lambda: self.lb_diag.configure(text=('诊断失败：%s' % e),
                      fg=(self.T['bad'])))
                finally:
                    e = None
                    del e

        threading.Thread(target=work, daemon=True).start()

    def _diag_done(self, path):
        import os
        self.lb_diag.configure(text='✓ 已导出，可把该文件夹发给开发者', fg=(self.T['ok']))
        try:
            os.startfile(os.path.dirname(path))
        except Exception:
            pass

    def do_save(self):
        """保存：只写回表单当前显示的那所学校（``self._form_pid``）。

        若下拉框选中的学校与表单显示的不一致（用户只选了但没点「切换」），
        直接拒绝保存并提示，避免把表单内容整体覆盖到另一所学校。
        """
        pending = self._pending_selection()
        if pending:
            self.lb_school.configure(text='下拉选中项尚未「切换」，已取消保存（避免覆盖另一所学校）',
              fg=(self.T['warn']))
            messagebox.showwarning('尚未切换学校',
              ('下拉框里选中的是「%s」，但表单里显示的仍是「%s」。\n\n直接保存会把当前表单内容写入「%s」。\n请先点「切换」，或把下拉框改回「%s」再保存。' % (
             self._profile_name_of(pending),
             self._profile_name_of(self._form_pid),
             self._profile_name_of(self._form_pid),
             self._profile_name_of(self._form_pid))),
              parent=(self.top))
            return
        pid = self._form_pid or config.get_active()
        self._flush_form(pid)
        cfg = config.load()
        self.cfg = cfg
        if self.on_saved:
            try:
                self.on_saved(cfg)
            except Exception:
                pass

        self.top.destroy()