# decompyle3 version 3.8.0
# Python bytecode 3.8
# Decompiled from: Python 3.8.10 (tags/v3.8.10:3d8993a, May  3 2021, 11:48:03) [MSC v.1928 64 bit (AMD64)]
# Embedded file name: netutil.py
"""网络检测 + WiFi 连接控制（Windows netsh）"""
import re, socket, subprocess, httpclient
PROBES = [
 'http://connect.rom.miui.com/generate_204',
 'http://www.gstatic.com/generate_204',
 'http://204.ustc.edu.cn']

def _decode(raw):
    """netsh 输出编码随系统设置变化：优先 UTF-8，失败退回 GBK"""
    for enc in ('utf-8', 'gbk'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', 'ignore')


def run(cmd, timeout=20):
    """执行命令，返回 (code, stdout)"""
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout,
                           creationflags=134217728)
        return (p.returncode, _decode(p.stdout) + _decode(p.stderr))
    except subprocess.TimeoutExpired:
        return (-1, 'timeout')
    except Exception as e:
        return (-1, str(e))
def wlan_ip():
    """物理无线网卡 IP（绕开 TUN / VPN 虚拟网卡）"""
    code, out = run('netsh interface ip show addresses "WLAN"')
    if code == 0:
        m = re.search('IP\\s*(?:地址|Address)[^\\d]*(\\d+\\.\\d+\\.\\d+\\.\\d+)', out)
        if m:
            return m.group(1)
        for cand in re.findall('(\\d+\\.\\d+\\.\\d+\\.\\d+)', out):
            if not cand.startswith('255.'):
                return cand

        return local_ip()


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('223.5.5.5', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ''
def current_ssid():
    code, out = run('netsh wlan show interfaces')
    if code != 0:
        return
    m = re.search('^\\s*SSID\\s*[:：]\\s*(.+?)\\s*$', out, re.M)
    if m:
        return m.group(1).strip()


def wifi_connected_to(ssid):
    return (current_ssid() or '').strip().lower() == (ssid or '').strip().lower()


def signal_percent():
    """当前无线信号强度百分比"""
    code, out = run('netsh wlan show interfaces')
    if code != 0:
        return
    m = re.search('(?:信号|Signal)\\s*[:：]\\s*(\\d+)\\s*%', out)
    if m:
        return int(m.group(1))


def ping_ms(src_ip=None, host='223.5.5.5', timeout=4):
    """实测延迟（毫秒）；指定 src_ip 时从该网卡发出"""
    cmd = 'ping -n 1 -w 1200 '
    if src_ip:
        cmd += '-S %s ' % src_ip
    cmd += host
    code, out = run(cmd, timeout=timeout)
    m = re.search('(?:时间|time)\\s*[=<]\\s*(\\d+)\\s*ms', out, re.I)
    if m:
        return int(m.group(1))


def list_profiles():
    code, out = run('netsh wlan show profiles')
    return [x.strip() for x in re.findall('[:：]\\s*(.+?)\\s*$', out, re.M) if x.strip()]


def connect_wifi(ssid, timeout=25):
    if not ssid:
        return (False, '未配置 SSID')
    esc = ssid.replace('"', '')
    code, out = run(('netsh wlan connect name="%s" ssid="%s"' % (esc, esc)), timeout=timeout)
    low = out.lower()
    ok = (code == 0) and (any((k in out for k in ('已成功', '完成', '成功')))) or ('success' in low)
    return (
     ok, out.strip().replace('\r\n', ' ')[:160])


def _req(url, bind_ip=None, timeout=5, max_redirect=0):
    try:
        return httpclient.request(url, bind_ip=bind_ip, timeout=timeout, max_redirect=max_redirect)
    except Exception:
        if bind_ip:
            return httpclient.request(url, bind_ip=None, timeout=timeout, max_redirect=max_redirect)
        raise


def probe_once(url, bind_ip=None, timeout=5):
    """返回 (状态码, Location, 正文)"""
    try:
        r = _req(url, bind_ip=bind_ip, timeout=timeout)
        return (r.status, r.headers.get('location'), r.text)
    except Exception as e:
        return (None, None, str(e))


def internet_ok(bind_ip=None, timeout=5):
    """真联网 = 探测点返回 204 或预期空响应（未被劫持）"""
    for u in PROBES:
        code, loc, body = probe_once(u, bind_ip=bind_ip, timeout=timeout)
        if code == 204:
            return True
        if code == 200 and body is not None:
            if len(body.strip()) <= 8 or 'generate_204' in body.lower():
                return True
    return False


def detect_portal_url(bind_ip=None, timeout=5):
    for u in PROBES:
        code, loc, body = probe_once(u, bind_ip=bind_ip, timeout=timeout)
        if loc:
            if loc.startswith('http'):
                return loc
        if code == 200:
            if body:
                m = re.search('https?://[^\\s\\"\'<>]+', body)
                if m:
                    if 'generate_204' not in m.group(0):
                        return m.group(0)
    return None
