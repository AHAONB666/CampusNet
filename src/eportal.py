# -*- coding: utf-8 -*-
# 语义级还原（原 decompyle3 产物已按可用逻辑重建）。
"""城市热点 ePortal（Dr.COM）专用认证适配器
   认证服务器: <学校认证服务器IP>（各校不同，以实际认证页地址为准）
   接口: POST /eportal/InterFace.do?method=login
   返回 JSON: {"result":"success|fail","message":"...","userIndex":"...","keepaliveInterval":N}
"""
import json
import time
import urllib.parse

import httpclient
import netutil
from config import log

SESSION = {
    'user_index': '',
    'interval': 0,
    'purl': '',
    'ip': '',
    'last_beat': 0.0,
}


def _split(purl):
    return urllib.parse.urlsplit(purl)


def api_url(purl, method='login'):
    p = _split(purl)
    return '%s://%s/eportal/InterFace.do?method=%s' % (
        p.scheme, p.netloc, method)


def query_string(purl):
    if '?' in purl:
        return purl.split('?', 1)[1]
    return ''


def is_eportal(purl):
    return bool(purl) and '/eportal/' in purl.lower()


def _post(purl, method, data, ip, referer=None, timeout=15):
    body = urllib.parse.urlencode(data).encode('utf-8')
    hdrs = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    if referer:
        hdrs['Referer'] = referer
    try:
        return httpclient.request(
            api_url(purl, method), method='POST', data=body, bind_ip=ip,
            timeout=timeout, headers=hdrs)
    except Exception:
        return httpclient.request(
            api_url(purl, method), method='POST', data=body, bind_ip=None,
            timeout=timeout, headers=hdrs)


def _json(text):
    """解析 ePortal 返回的 JSON；前后有杂质时截取 {}；失败返回 {}"""
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        i = text.find('{')
        j = text.rfind('}')
        if 0 <= i < j:
            return json.loads(text[i:j + 1])
    except Exception:
        pass
    return {}


def get_services(purl, ip):
    """获取可选服务列表，返回 (默认服务名, [全部服务名])；失败返回 ('', [])"""
    qs = query_string(purl)
    try:
        r = _post(purl, 'getServices', {}, ip, referer=purl)
        info = _json(r.text)
        if info.get('isService') == 'false':
            return '', []
        raw = info.get('serviceJson') or '[]'
        items = json.loads(raw) if isinstance(raw, str) else raw
        names = [
            item.get('name') or ''
            for item in items if isinstance(item, dict)]
        return (names[0] if names else ''), names
    except Exception as e:
        try:
            log('获取服务列表失败: %r' % (e,))
        except Exception:
            pass
        return '', []


def login(cfg, bind_ip=None, purl=None):
    """返回 (ok, msg)；返回 (None, 'not-eportal') 表示不适用"""
    ip = bind_ip or netutil.wlan_ip()
    purl = purl or (cfg.get('portal_url') or '').strip() \
        or netutil.detect_portal_url(bind_ip=ip)
    if not is_eportal(purl):
        return None, 'not-eportal'
    user = (cfg.get('username') or '').strip()
    pwd = cfg.get('password') or ''
    if not (user and pwd):
        return False, '未填写账号或密码'
    qs = query_string(purl)
    if not qs:
        return False, '认证页缺少 queryString 参数'
    cookie = None
    try:
        r0 = httpclient.request(purl, bind_ip=ip, timeout=10)
        cookie = r0.headers.get('set-cookie')
    except Exception:
        pass
    service, _names = get_services(purl, ip)
    data = {
        'userId': user,
        'password': pwd,
        'service': service,
        'queryString': qs,
        'operatorPwd': '',
        'operatorUserId': '',
        'validcode': '',
        'passwordEncrypt': 'false',
    }
    hdrs = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': purl,
    }
    if cookie:
        hdrs['Cookie'] = cookie.split(';')[0]
    body = urllib.parse.urlencode(data).encode('utf-8')
    try:
        r = httpclient.request(
            api_url(purl, 'login'), method='POST', data=body, bind_ip=ip,
            timeout=15, headers=hdrs)
    except Exception as e:
        return False, '连接认证服务器失败: %r' % (e,)
    info = _json(r.text)
    result = (info.get('result') or '').lower()
    msg = info.get('message') or ''
    try:
        log('ePortal login result=%s msg=%s' % (
            result or r.status, msg[:80]))
    except Exception:
        pass
    if result == 'success':
        SESSION.update({
            'user_index': info.get('userIndex') or '',
            'interval': int(info.get('keepaliveInterval') or 0),
            'purl': purl,
            'ip': ip,
            'last_beat': time.time(),
        })
        return True, msg or '认证成功'
    if any(k in msg for k in ('已在线', '已经在线', '已登录')):
        return True, msg
    if not info:
        return False, '认证服务器返回异常: %s' % r.text[:80]
    return False, msg or '认证失败'


def maybe_keepalive():
    """按服务器返回的间隔发心跳；未登录或 interval<=0 时什么都不做"""
    s = SESSION
    if not s['user_index'] or s['interval'] <= 0 or not s['purl']:
        return
    now = time.time()
    if now - s['last_beat'] < max(30, s['interval']):
        return
    try:
        _post(s['purl'], 'keepalive', {'userIndex': s['user_index']},
              s['ip'], referer=s['purl'], timeout=8)
        s['last_beat'] = now
    except Exception as e:
        try:
            log('心跳失败: %r' % (e,))
        except Exception:
            pass


def reset_session():
    SESSION.update({'user_index': '', 'interval': 0, 'last_beat': 0.0})
