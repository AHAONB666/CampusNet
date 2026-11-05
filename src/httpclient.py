# decompyle3 version 3.8.0
# Python bytecode 3.8
# Decompiled from: Python 3.8.10 (tags/v3.8.10:3d8993a, May  3 2021, 11:48:03) [MSC v.1928 64 bit (AMD64)]
# Embedded file name: httpclient.py
"""精简 HTTP 客户端：支持绑定本机网卡 IP（绕开 VPN/TUN 代理）、手动跟随重定向"""
import http.client, ssl, urllib.parse
DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

class Response(object):

    def __init__(self, status, url, text, headers):
        self.status = status
        self.url = url
        self.text = text
        self.headers = headers

    def __repr__(self):
        return '<Response %s %s>' % (self.status, self.url)


def _split(url):
    p = urllib.parse.urlsplit(url)
    scheme = (p.scheme or 'http').lower()
    host = p.hostname or ''
    port = p.port or (443 if scheme == 'https' else 80)
    path = p.path or '/'
    if p.query:
        path += '?' + p.query
    return (scheme, host, port, path)


def _decode(body, headers):
    ctype = headers.get('content-type', '') or ''
    charset = 'utf-8'
    low = ctype.lower()
    if 'charset=' in low:
        charset = ctype[low.index('charset=') + 8:].split(';')[0].strip().strip('"')
    for enc in (charset, 'utf-8', 'gbk'):
        try:
            return body.decode(enc, 'strict')
        except Exception:
            pass
    return body.decode('utf-8', 'ignore')
def request(url, method='GET', data=None, headers=None, bind_ip=None, timeout=8, max_redirect=6, verify_tls=False):
    """data 可为 dict / bytes / None；bind_ip 绑定本机该网卡 IP"""
    hdrs = {'User-Agent':DEFAULT_UA, 
     'Accept':'*/*',  'Accept-Language':'zh-CN,zh;q=0.9', 
     'Connection':'close'}
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode('utf-8')
            hdrs.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        elif isinstance(data, str):
            body = data.encode('utf-8')
        else:
            body = data
    src = (bind_ip, 0) if bind_ip else None
    cur = url
    for _ in range(max_redirect + 1):
        scheme, host, port, path = _split(cur)
        if not host:
            raise ValueError('非法URL: %s' % cur)
        if scheme == 'https':
            ctx = ssl.create_default_context()
            if not verify_tls:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx,
              source_address=src)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout, source_address=src)
        try:
            conn.request(method, path, body=body, headers=hdrs)
            r = conn.getresponse()
            raw = r.read()
            rh = dict(((k.lower(), v) for k, v in r.getheaders()))
            status = r.status
            loc = rh.get('location')
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if status in (301, 302, 303, 307, 308) and loc:
            cur = urllib.parse.urljoin(cur, loc)
            if status in (301, 302, 303):
                method, body = ('GET', None)
                hdrs.pop('Content-Type', None)
        else:
            return Response(status, cur, _decode(raw, rh), rh)
    raise RuntimeError('重定向次数过多')
