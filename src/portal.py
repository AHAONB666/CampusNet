# -*- coding: utf-8 -*-
# 语义级还原（原 decompyle3 产物已按可用逻辑重建）。
"""Portal 认证引擎：自动发现认证页 -> 解析表单 -> 智能填充 -> 提交 -> 校验"""
import re
import time
import urllib.parse
from html.parser import HTMLParser

import httpclient
import netutil
from config import log

USER_KEYS = [
    'username', 'userid', 'user_name', 'account', 'loginname', 'logname',
    'stu_no', 'stuno', 'studentno', 'useraccount', 'uid', 'user', 'name',
    'phone', 'mobile', 'dddddd', '0']
PWD_KEYS = ['password', 'passwd', 'pwd', 'pass', 'upass', 'userpwd', '1']
JS_REDIRECT = re.compile(
    r'(?:location(?:\.href)?\s*=\s*|window\.location(?:\.href)?\s*=\s*'
    r'|location\.replace\()\s*[\'"]([^\'"]+)[\'"]', re.I)


class FormParser(HTMLParser):
    """从 HTML 中抓取 form 及其 input/select 字段"""

    def __init__(self):
        super().__init__()
        self.forms = []
        self._cur = None
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = dict((k.lower(), v or '') for k, v in attrs)
        if tag == 'form':
            self._cur = {
                'action': a.get('action', ''),
                'method': (a.get('method') or 'get').lower(),
                'id': a.get('id', ''),
                'name': a.get('name', ''),
                'fields': [],
            }
            self.forms.append(self._cur)
        elif tag == 'input' and self._cur is not None:
            self._cur['fields'].append({
                'tag': 'input',
                'type': (a.get('type') or 'text').lower(),
                'name': a.get('name', ''),
                'value': a.get('value', ''),
                'id': a.get('id', ''),
            })
        elif tag == 'select' and self._cur is not None:
            self._select = {
                'tag': 'select',
                'type': 'select',
                'name': a.get('name', ''),
                'value': '',
                'id': a.get('id', ''),
            }
            self._cur['fields'].append(self._select)
        elif (tag == 'option' and self._select is not None
              and (a.get('selected') is not None
                   or self._select['value'] == '')):
            self._select['value'] = a.get('value', '') or ''

    def handle_endtag(self, tag):
        if tag == 'form':
            self._cur = None
        elif tag == 'select':
            self._select = None


def _score(name, keys):
    """字段名与关键词的匹配得分：完全相等 > 包含，越靠前越高"""
    n = (name or '').lower()
    for i, k in enumerate(keys):
        if n == k:
            return 100 - i
    for i, k in enumerate(keys):
        if k and k in n:
            return 50 - i
    return 0


def parse_forms(html):
    """解析 HTML 中的全部表单；解析失败返回空列表"""
    p = FormParser()
    try:
        p.feed(html)
    except Exception:
        pass
    return p.forms


def pick_form(forms):
    """优先选含密码框的表单"""
    best, best_s = None, -1
    for f in forms:
        s = 0
        for fd in f['fields']:
            nm = fd.get('name') or ''
            if _score(nm, USER_KEYS) > 0:
                s += 2
            if _score(nm, PWD_KEYS) > 0:
                s += 3
        if any(fd.get('type') == 'password' for fd in f['fields']):
            s += 5
        if s > best_s:
            best, best_s = f, s
    if best_s > 0:
        return best


def _request_with_fallback(url, method='GET', data=None, headers=None,
                           bind_ip=None, timeout=10, max_redirect=6):
    """优先绑定 WLAN 网卡请求；绑定失败退回默认路由"""
    try:
        return httpclient.request(
            url, method=method, data=data, headers=headers,
            bind_ip=bind_ip, timeout=timeout, max_redirect=max_redirect)
    except Exception:
        if bind_ip:
            return httpclient.request(
                url, method=method, data=data, headers=headers,
                bind_ip=None, timeout=timeout, max_redirect=max_redirect)
        raise


def _extract_msg(html):
    """从页面提取提示语：JS 变量 / title / alert / 纯文本"""
    if not html:
        return ''
    for pat in (
            r'msg\s*[:=]\s*[\'"]([^\'"]{2,60})[\'"]',
            r'<title>([^<]{2,60})</title>',
            r'(?:alert|confirm)\(\s*[\'"]([^\'"]{2,60})',
            r'err(?:or|msg)?\s*[:=]\s*[\'"]([^\'"]{2,60})[\'"]'):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    txt = re.sub(r'<script[\s\S]*?</script>', ' ', html, flags=re.I)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt[:80]


SRUN_HINTS = ('srun_portal', 'cgi-bin/srun', 'srun_portal_pc',
              'srun_portal_type')


def detect_type(url, html=''):
    """判定认证系统类型"""
    u = (url or '').lower()
    h = (html or '').lower()
    if '/eportal/' in u or 'interfacedo' in h.replace('.', '') \
            or 'eportal' in u:
        return 'eportal'
    if any(k in h for k in SRUN_HINTS) or 'srun' in u:
        return 'srun'
    if 'ruijie' in h or ('锐捷' in html):
        return 'ruijie'
    if '<input' in h:
        if 'type="password"' in h or "type='password'" in h:
            return 'form'
        return 'unknown'
    return 'unknown'


TYPE_NAMES = {
    'eportal': '城市热点 ePortal（Dr.COM）',
    'srun': '深澜 srun',
    'ruijie': '锐捷 / 通用门户',
    'form': '标准网页表单',
    'unknown': '未识别',
}


class PortalAuth(object):
    """通用网页表单认证器"""

    def __init__(self, cfg, bind_ip=None):
        self.cfg = cfg
        self.user = (cfg.get('username') or '').strip()
        self.pwd = cfg.get('password') or ''
        self.portal_url = (cfg.get('portal_url') or '').strip()
        self.bind_ip = bind_ip or netutil.wlan_ip()

    def _get(self, url, method='GET', data=None, headers=None, timeout=10,
             max_redirect=6):
        """用当前绑定网卡请求页面，失败自动退回默认路由"""
        return _request_with_fallback(
            url, method=method, data=data, headers=headers,
            bind_ip=self.bind_ip, timeout=timeout,
            max_redirect=max_redirect)

    def _fill_form(self, form):
        """把账号密码填进表单字段，返回 (data, 是否完整)"""
        data = {}
        user_field = (self.cfg.get('user_field') or '').strip()
        pwd_field = (self.cfg.get('pwd_field') or '').strip()
        user_done = pwd_done = False
        for fd in form.get('fields') or []:
            name = fd.get('name') or ''
            if not name or fd.get('tag') == 'select':
                continue
            ftype = fd.get('type') or 'text'
            if ftype in ('submit', 'button', 'reset', 'file', 'image'):
                continue
            if ftype in ('checkbox', 'radio'):
                if fd.get('value'):
                    data[name] = fd['value']
                continue
            if user_field and name == user_field:
                data[name] = self.user
                user_done = True
                continue
            if pwd_field and name == pwd_field:
                data[name] = self.pwd
                pwd_done = True
                continue
            if ftype == 'password':
                data[name] = self.pwd
                pwd_done = True
                continue
            if _score(name, USER_KEYS) > 0 and not user_done:
                data[name] = self.user
                user_done = True
                continue
            if _score(name, PWD_KEYS) > 0 and not pwd_done:
                data[name] = self.pwd
                pwd_done = True
                continue
            if fd.get('value') is not None:
                data[name] = fd.get('value', '')
        return data, user_done and pwd_done

    def login(self):
        """提交表单并依据联网状态判断结果，返回 (ok, msg)"""
        if not self.portal_url:
            return False, '未配置认证页地址'
        try:
            r = self._get(self.portal_url)
        except Exception as e:
            return False, '访问认证页失败: %r' % (e,)
        html = r.text or ''
        forms = parse_forms(html)
        form = pick_form(forms) or (
            forms[0] if forms and forms[0].get('fields') else None)
        if not form:
            return False, '认证页未找到登录表单'
        data, complete = self._fill_form(form)
        if not complete:
            return False, '认证页表单字段无法识别，请在设置里手动映射'
        action = (form.get('action') or self.portal_url).strip()
        submit_url = urllib.parse.urljoin(self.portal_url, action)
        method = 'POST' if form.get('method') != 'get' else 'GET'
        try:
            r2 = self._get(submit_url, method=method, data=data,
                           timeout=15)
        except Exception as e:
            return False, '提交认证失败: %r' % (e,)
        if netutil.internet_ok(bind_ip=self.bind_ip, timeout=6):
            return True, '认证成功'
        msg = _extract_msg(r2.text or '')
        if not msg:
            msg = '认证未生效（服务器状态 %s）' % r2.status
        return False, msg


def analyze(url, bind_ip=None):
    """探测认证页类型与表单字段，供设置页回填。

    Returns:
        {"ok": bool, "type": str, "type_name": str, "hint": str,
         "user_field": str, "pwd_field": str}
    """
    info = {
        'ok': False,
        'type': 'unknown',
        'type_name': TYPE_NAMES['unknown'],
        'hint': '',
        'user_field': '',
        'pwd_field': '',
    }
    if not url:
        info['hint'] = '请先填写认证页地址'
        return info
    if not url.lower().startswith('http'):
        url = 'http://' + url
    try:
        r = _request_with_fallback(url, bind_ip=bind_ip, timeout=10)
    except Exception as e:
        info['hint'] = '访问失败: %r' % (e,)
        return info
    html = r.text or ''
    t = detect_type(url, html)
    info['type'] = t
    info['type_name'] = TYPE_NAMES.get(t, TYPE_NAMES['unknown'])
    if t == 'eportal':
        info['ok'] = True
        info['hint'] = '已识别，可直接自动认证'
        return info
    forms = parse_forms(html)
    form = pick_form(forms)
    if form:
        for fd in form.get('fields') or []:
            nm = fd.get('name') or ''
            if not info['user_field'] and _score(nm, USER_KEYS) > 0:
                info['user_field'] = nm
            if not info['pwd_field'] and _score(nm, PWD_KEYS) > 0:
                info['pwd_field'] = nm
    if info['user_field'] or info['pwd_field']:
        info['ok'] = True
        info['hint'] = '字段已识别'
    else:
        info['hint'] = '未识别到登录表单，请检查地址或手动映射字段'
    return info


def login(cfg, bind_ip=None):
    """Portal 登录入口：优先 ePortal 专用适配器，其余走通用表单认证"""
    ip = bind_ip or netutil.wlan_ip()
    purl = (cfg.get('portal_url') or '').strip()
    if not purl:
        purl = netutil.detect_portal_url(bind_ip=ip) or ''
    if not purl:
        return False, '未探测到认证页（请在设置里填写认证页地址）'
    auth_type = (cfg.get('auth_type') or 'auto').lower()
    if auth_type == 'eportal' or '/eportal/' in purl.lower():
        try:
            import eportal
            ok, msg = eportal.login(cfg, bind_ip=ip, purl=purl)
            if ok is not None:
                return ok, msg
        except Exception as e:
            try:
                log('ePortal 适配异常: %r' % (e,))
            except Exception:
                pass
    auth = PortalAuth(cfg, ip)
    auth.portal_url = purl
    return auth.login()
