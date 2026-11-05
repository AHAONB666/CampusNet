# decompyle3 version 3.8.0
# Python bytecode 3.8
# Decompiled from: Python 3.8.10 (tags/v3.8.10:3d8993a, May  3 2021, 11:48:03) [MSC v.1928 64 bit (AMD64)]
# Embedded file name: diag.py
"""诊断：抓取真实认证页并导出，用于适配学校 Portal 协议"""
import os, socket, time, config, httpclient, netutil, portal

def wlan_ip():
    return netutil.wlan_ip()


def run(cfg=None, save_dir=None):
    cfg = cfg or config.load()
    save_dir = save_dir or os.path.join(config.app_dir(), 'debug')
    try:
        os.makedirs(save_dir, exist_ok=True)
    except Exception:
        pass
    else:
        stamp = time.strftime('%Y%m%d_%H%M%S')
        lines = []
        add = lines.append
        add('============================================================')
        add('校园网认证诊断  %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
        add('============================================================')
        ssid = netutil.current_ssid()
        ip = wlan_ip()
        add('SSID        : %s' % (ssid or '未连接'))
        add('本机IP      : %s' % ip)
        code, out = netutil.run('ipconfig')
        for ln in out.splitlines():
            if any((k in ln for k in ('默认网关', 'Default Gateway', 'DNS 服务器', 'DNS Servers'))):
                add('   ' + ln.strip())
        else:
            online = netutil.internet_ok(bind_ip=ip)
            add('是否已认证  : %s' % ('是（已可上网）' if online else '否（需要认证）'))
            portal_url = (cfg.get('portal_url') or '').strip() or netutil.detect_portal_url(bind_ip=ip)
            add('认证页地址  : %s' % (portal_url or '未探测到'))
            html_path = os.path.join(save_dir, 'portal_%s.html' % stamp)
            if portal_url:
                try:
                    r = httpclient.request(portal_url, bind_ip=ip, timeout=10)
                    add('抓取结果    : HTTP %s  最终地址=%s  长度=%d' % (r.status, r.url, len(r.text)))
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write('<!-- FETCHED FROM: %s -->\n<!-- FINAL URL: %s -->\n' % (portal_url, r.url))
                        f.write(r.text)
                    add('认证页已保存: %s' % html_path)
                    forms = portal.parse_forms(r.text)
                    add('发现表单数  : %d' % len(forms))
                    for i, f in enumerate(forms):
                        add('  表单%d action=%s method=%s' % (i + 1, f['action'] or '(当前页)', f['method']))
                        for fd in f['fields']:
                            add('     - %-6s name=%-16s value=%s' % (
                             fd.get('type', 'select'), fd.get('name', ''), (fd.get('value') or '')[:40]))

                    else:
                        best = portal.pick_form(forms)
                        if best:
                            uk = pk = ''
                            for fd in best['fields']:
                                nm = fd.get('name') or ''
                                if portal._score(nm, portal.PWD_KEYS) > 0 and not pk:
                                    pk = nm
                                else:
                                    if portal._score(nm, portal.USER_KEYS) > 0:
                                        if not uk:
                                            uk = nm
                            else:
                                add('自动识别    : 账号字段=%s  密码字段=%s' % (uk or '未识别', pk or '未识别'))

                except Exception as e:
                    try:
                        add('抓取失败    : %r' % (e,))
                    finally:
                        e = None
                        del e

            else:
                add('提示        : 当前已联网或网络未就绪，无法取得认证页。')
                add('              请断开 WiFi 后重新连接（不要登录），再运行本诊断。')
            txt_path = os.path.join(save_dir, 'diag_%s.txt' % stamp)
            text = '\n'.join(lines)
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
            return (txt_path, text)