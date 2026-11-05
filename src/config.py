# -*- coding: utf-8 -*-
# 语义级还原（原 decompyle3 产物已按可用逻辑重建）。
"""配置读写：Windows DPAPI 密码加密 + 多学校 profile 切换

磁盘结构（version 2）::

    {
      "version": 2,
      "active": "campus-demo",
      "profiles": [
        {"id": "...", "name": "...", "ssid": "...", "username": "...",
         "password": "dpapi:xxxx", "portal_url": "", "user_field": "",
         "pwd_field": "", "extra_params": ""}
      ],
      "check_interval": 20,
      "retry_interval": 8,
      "auto_start": true,
      "auto_reconnect": true
    }

对外接口保持「扁平 dict」不变：``load()`` 把 active profile 的字段展开到顶层，
``save(cfg)`` 把顶层里的 profile 字段写回当前 active profile、其余写全局。
这样 guard.py / ui_scifi.py 等既有调用方无需改动。

密码存储：
* 新格式 ``dpapi:<base64>`` —— 用 crypt32 的 CryptProtectData 加密，
  只能被同一 Windows 用户在同一台机器上解密；
* 旧格式（``_pwd_enc: true`` 的 XOR+base64）仅用于读取，读到后静默迁移为 DPAPI；
* 明文 —— 直接可用（DPAPI 极少数不可用环境下的降级形态）。
"""
import base64
import ctypes
import json
import os
import sys
import threading

APP_NAME = 'CampusNet'
APP_VERSION = '2.4.0'
_KEY = b'campusnet-legacy-xor-v1'
PWD_PREFIX = 'dpapi:'
CRYPTPROTECT_UI_FORBIDDEN = 1


class _DATA_BLOB(ctypes.Structure):
    """对应 Win32 的 DATA_BLOB 结构"""
    _fields_ = [
        ('cbData', ctypes.c_uint32),
        ('pbData', ctypes.POINTER(ctypes.c_char)),
    ]


_DLL_LOCK = threading.Lock()
_crypt32 = None
_DIR_CACHE = None


def _load_dlls():
    """惰性加载 crypt32，返回 (CryptProtectData, CryptUnprotectData) 或 (None, None)"""
    global _crypt32
    if _crypt32 is None:
        with _DLL_LOCK:
            if _crypt32 is None:
                try:
                    dll = ctypes.WinDLL('crypt32', use_last_error=True)
                    protect = dll.CryptProtectData
                    unprotect = dll.CryptUnprotectData
                    protect.restype = ctypes.c_bool
                    protect.argtypes = [
                        ctypes.POINTER(_DATA_BLOB), ctypes.c_wchar_p,
                        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                        ctypes.c_uint32, ctypes.POINTER(_DATA_BLOB),
                    ]
                    unprotect.restype = ctypes.c_bool
                    unprotect.argtypes = [
                        ctypes.POINTER(_DATA_BLOB), ctypes.c_wchar_p,
                        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                        ctypes.c_uint32, ctypes.POINTER(_DATA_BLOB),
                    ]
                    _crypt32 = (protect, unprotect)
                except Exception:
                    _crypt32 = (None, None)
    return _crypt32


def _make_blob(data):
    """把 bytes 打包成 DATA_BLOB。

    Args:
        data: 原始字节。

    Returns:
        (blob, keepalive)：keepalive 是必须保留引用的缓冲区，
        否则 blob 里的指针会被 GC 回收。
    """
    raw = bytes(data or b'')
    if not raw:
        return _DATA_BLOB(0, None), None
    buf = ctypes.create_string_buffer(raw)
    blob = _DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf


def _blob_take(blob):
    """从 DATA_BLOB 取出字节串并释放其缓冲区"""
    try:
        if not blob or not blob.cbData:
            return b''
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        if blob and blob.pbData:
            try:
                ctypes.windll.kernel32.LocalFree(blob.pbData)
            except Exception:
                pass


def dpapi_encrypt(plain):
    """明文字符串 -> dpapi:<base64>；失败返回 ''"""
    protect, _unprotect = _load_dlls()
    if not protect or not plain:
        return ''
    try:
        src, keep = _make_blob(plain.encode('utf-8'))
        out = _DATA_BLOB()
        ok = protect(
            ctypes.byref(src), None, None, 0, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
        if not ok:
            return ''
        token = base64.b64encode(_blob_take(out)).decode('ascii')
        return PWD_PREFIX + token
    except Exception:
        return ''


def dpapi_decrypt(token):
    """dpapi:<base64> -> 明文字符串；失败返回 None"""
    _protect, unprotect = _load_dlls()
    if not unprotect or not token:
        return None
    try:
        raw = base64.b64decode(token[len(PWD_PREFIX):])
        src, keep = _make_blob(raw)
        out = _DATA_BLOB()
        ok = unprotect(
            ctypes.byref(src), None, None, 0, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
        if not ok:
            return None
        return _blob_take(out).decode('utf-8')
    except Exception:
        return None


def _writable(path):
    """目录是否可写（用临时文件试探，失败即认为不可写）"""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.campusnet_write_test')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('ok')
        os.remove(probe)
        return True
    except Exception:
        return False


def app_dir():
    """优先用程序所在目录（便携）；不可写则退回 %APPDATA%\\CampusNet"""
    global _DIR_CACHE
    if _DIR_CACHE:
        return _DIR_CACHE
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    if _writable(base):
        _DIR_CACHE = base
        return base
    fallback = os.path.join(
        os.environ.get('APPDATA') or os.path.expanduser('~'), APP_NAME)
    try:
        os.makedirs(fallback, exist_ok=True)
    except Exception:
        pass
    _DIR_CACHE = fallback
    return fallback


CONFIG_PATH = os.path.join(app_dir(), 'config.json')
LOG_PATH = os.path.join(app_dir(), 'campusnet.log')
PROFILE_KEYS = ('ssid', 'username', 'password', 'portal_url', 'user_field',
                'pwd_field', 'extra_params')
GLOBAL_KEYS = ('check_interval', 'retry_interval', 'auto_start',
               'auto_reconnect', 'minimize_to_tray', 'auth_type')
_DEFAULT_GLOBAL = {
    'check_interval': 20,
    'retry_interval': 8,
    'auto_start': True,
    'auto_reconnect': True,
    'minimize_to_tray': True,
    'auth_type': 'auto',
}
_DEFAULT_PROFILE = {
    'id': 'campus-demo',
    'name': '',
    'ssid': 'CAMPUS-DEMO',
    'username': '',
    'password': '',
    'portal_url': '',
    'user_field': '',
    'pwd_field': '',
    'extra_params': '',
}
DEFAULT = {
    'ssid': 'CAMPUS-DEMO',
    'username': '',
    'password': '',
    'portal_url': '',
    'auth_type': 'auto',
    'user_field': '',
    'pwd_field': '',
    'extra_params': '',
    'check_interval': 20,
    'retry_interval': 8,
    'auto_start': True,
    'auto_reconnect': True,
    'minimize_to_tray': True,
    '_pwd_enc': False,
}


def _xor(data):
    """对字节串做固定 key 的 XOR 混淆"""
    return bytes(
        b ^ _KEY[(i % len(_KEY))] for i, b in enumerate(data))


def enc(text):
    """旧格式加密（仅为兼容保留，新代码不要再用）"""
    return base64.b64encode(_xor(text.encode('utf-8'))).decode('ascii')


def dec(token):
    """旧格式解密；解不开返回空串"""
    try:
        raw = base64.b64decode(token or '')
        return _xor(raw).decode('utf-8')
    except Exception:
        return ''


def _read_raw(strict=False):
    """读原始 JSON。strict=True 时配置损坏抛异常，否则返回 {}"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        if strict:
            raise
        return {}


def _slug(text, fallback='school'):
    """把 SSID / 名称转成只含 ASCII 的安全 id"""
    out = ''
    for ch in (text or '').strip().lower():
        if 'a' <= ch <= 'z' or '0' <= ch <= '9':
            out += ch
        elif ch in '-_.':
            out += '_'
    out = out.strip('_')
    return out or fallback


def _unique_id(base, profiles):
    """在已有 profile 中生成不重复的 id"""
    used = set(p.get('id') or '' for p in profiles)
    if base not in used:
        return base
    i = 2
    while '%s_%d' % (base, i) in used:
        i += 1
    return '%s_%d' % (base, i)


def _decode_pwd(value):
    """把磁盘上的密码字段解成明文（支持 dpapi / 明文；解不开返回 ""）"""
    if not value:
        return ''
    if value.startswith(PWD_PREFIX):
        plain = dpapi_decrypt(value)
        if plain is None:
            log('已保存的密码无法解密，该学校需要重新填写密码')
            return ''
        return plain
    return value


def _encode_pwd(plain):
    """把明文密码加密成可落盘的字符串（DPAPI 失败时降级明文并写日志）"""
    if not plain:
        return ''
    token = dpapi_encrypt(plain)
    if token:
        return token
    log('⚠ DPAPI 加密不可用，密码将以明文保存在 config.json 中')
    return plain


def _fill_profile(src, index):
    """把磁盘上的单个 profile 补齐成内存态（密码为明文）

    Note:
        ``name`` 保持原值：为空就留空（显示层统一兜底成「未配置学校」），
        不要在这里用 ssid/id 顶替，否则用户保存后会看到伪造的校名。
    """
    prof = {
        'id': str(src.get('id') or '').strip() or 'school%d' % (index + 1),
        'name': str(src.get('name') or '').strip(),
        'ssid': str(src.get('ssid') or '').strip(),
        'username': str(src.get('username') or '').strip(),
        'password': _decode_pwd(str(src.get('password') or '')),
        'portal_url': str(src.get('portal_url') or '').strip(),
        'user_field': str(src.get('user_field') or '').strip(),
        'pwd_field': str(src.get('pwd_field') or '').strip(),
        'extra_params': str(src.get('extra_params') or '').strip(),
    }
    return prof


def _empty_store():
    """构造只有默认学校的空配置（内存态）"""
    prof = dict(_DEFAULT_PROFILE)
    store = {
        'version': 2,
        'active': prof['id'],
        'profiles': [prof],
    }
    for key in GLOBAL_KEYS:
        store[key] = _DEFAULT_GLOBAL[key]
    return store


def _normalize(raw):
    """把任意版本的原始配置整理成 v2 内存态。

    Args:
        raw: ``_read_raw()`` 读到的 dict。

    Returns:
        (store, changed)：changed 为 True 表示磁盘内容需要静默回写
        （格式升级 / 密码迁移 / active 非法）。
    """
    if not raw:
        return _empty_store(), False
    legacy_xor = bool(raw.get('_pwd_enc'))
    profiles_raw = raw.get('profiles')

    if isinstance(profiles_raw, list) and profiles_raw:
        profiles = []
        for idx, item in enumerate(profiles_raw):
            if not isinstance(item, dict):
                continue
            src = dict(item)
            pwd = str(src.get('password') or '')
            if legacy_xor and pwd and not pwd.startswith(PWD_PREFIX):
                src['password'] = dec(pwd)
            profiles.append(_fill_profile(src, len(profiles)))
        if profiles:
            store = {'version': 2, 'profiles': profiles}
            active = str(raw.get('active') or '').strip()
            ids = [p['id'] for p in profiles]
            if active not in ids:
                active = ids[0]
            store['active'] = active
            for key in GLOBAL_KEYS:
                store[key] = raw.get(key, _DEFAULT_GLOBAL[key])
            changed = (
                raw.get('version') != 2 or legacy_xor
                or str(raw.get('active') or '') != active)
            return store, changed

    # 旧版单学校配置
    prof = dict(_DEFAULT_PROFILE)
    ssid = str(raw.get('ssid') or '').strip()
    prof['ssid'] = ssid or _DEFAULT_PROFILE['ssid']
    prof['name'] = ssid or _DEFAULT_PROFILE['name']
    prof['id'] = _slug(ssid, _DEFAULT_PROFILE['id'])
    for key in ('username', 'portal_url', 'user_field', 'pwd_field',
                'extra_params'):
        prof[key] = str(raw.get(key) or '').strip()
    pwd = str(raw.get('password') or '')
    if legacy_xor and pwd:
        pwd = dec(pwd)
    prof['password'] = _decode_pwd(pwd)
    store = {
        'version': 2,
        'active': prof['id'],
        'profiles': [prof],
    }
    for key in GLOBAL_KEYS:
        store[key] = raw.get(key, _DEFAULT_GLOBAL[key])
    return store, True


def _write(store):
    """把内存态配置落盘（密码 DPAPI 加密 + 原子替换）

    Note:
        ``name`` 为空就写空串，不用 id/ssid 顶替——否则「未配置学校」
        保存一次就会被写成 WiFi 名（显示层负责兜底文案）。
    """
    profiles = store.get('profiles') or []
    out_profiles = []
    for prof in profiles:
        out_profiles.append({
            'id': prof.get('id') or 'school',
            'name': prof.get('name') or '',
            'ssid': prof.get('ssid') or '',
            'username': prof.get('username') or '',
            'password': _encode_pwd(prof.get('password') or ''),
            'portal_url': prof.get('portal_url') or '',
            'user_field': prof.get('user_field') or '',
            'pwd_field': prof.get('pwd_field') or '',
            'extra_params': prof.get('extra_params') or '',
        })
    if not out_profiles:
        out_profiles = [dict(_DEFAULT_PROFILE)]
    active = store.get('active') or out_profiles[0]['id']
    ids = [p['id'] for p in out_profiles]
    if active not in ids:
        active = ids[0]
    out = {
        'version': 2,
        'active': active,
        'profiles': out_profiles,
    }
    for key in GLOBAL_KEYS:
        out[key] = store.get(key, _DEFAULT_GLOBAL[key])

    tmp = CONFIG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def _active_profile(store):
    """取当前 active 的 profile（内存态），没有则返回第一个"""
    profiles = store.get('profiles') or []
    if not profiles:
        return None
    active = store.get('active')
    for prof in profiles:
        if prof.get('id') == active:
            return prof
    return profiles[0]


def _public_profile(prof):
    """对外的学校摘要（不含密码）

    ``name`` 保持原值（未命名的占位 profile 返回空串），
    由调用方自行兜底显示文案（UI 统一显示「未配置学校」）。
    """
    return {
        'id': prof.get('id') or '',
        'name': prof.get('name') or '',
        'ssid': prof.get('ssid') or '',
        'username': prof.get('username') or '',
    }


def _flatten(store):
    """把 active profile 展开成扁平 dict（老调用方看到的形态）"""
    cfg = dict(_DEFAULT_GLOBAL)
    prof = _active_profile(store) or dict(_DEFAULT_PROFILE)
    for key in PROFILE_KEYS:
        cfg[key] = prof.get(key, '')
    for key in GLOBAL_KEYS:
        cfg[key] = store.get(key, _DEFAULT_GLOBAL[key])
    cfg['_profiles'] = [
        _public_profile(p) for p in store.get('profiles') or []]
    cfg['_active'] = prof.get('id') or ''
    cfg['_profile_name'] = prof.get('name') or '未配置学校'
    cfg['_pwd_enc'] = False
    return cfg


def _load_store(strict=False):
    """读盘 + 迁移，必要时静默回写；返回内存态 store

    Args:
        strict: 透传给 :func:`_read_raw`，True 时配置损坏会抛异常。
    """
    store, changed = _normalize(_read_raw(strict))
    if changed:
        try:
            _write(store)
            log('配置已自动升级到 version 2（密码改用 DPAPI 加密）')
        except Exception as exc:
            try:
                log('配置自动升级回写失败：%r' % (exc,))
            except Exception:
                pass
    return store


def load(strict=False):
    """读取配置。

    Args:
        strict: 默认 False，保持旧行为——配置文件损坏时吞掉异常、返回默认
            配置（guard.py / UI 等现有调用方依赖此行为）。
            传 True 时读取/解析失败会抛异常，供 ``--silent`` 后台守护区分
            「配置文件损坏」（应继续用旧配置、不退出）与「用户主动清空凭据」
            （应停机）。

    Returns:
        扁平 dict：active profile 的 ssid / username / password /
        portal_url / user_field / pwd_field / extra_params 位于顶层，
        再合并 check_interval 等全局字段，另外附带 ``_profiles`` /
        ``_active`` / ``_profile_name`` 供 UI 使用。

    Raises:
        Exception: 仅当 ``strict=True`` 且配置文件无法读取/解析时。
    """
    return _flatten(_load_store(strict))


def save(cfg):
    """保存配置（接受扁平 dict）。

    Args:
        cfg: 扁平 dict。``ssid`` / ``username`` / ``password`` 等字段写回
            当前 active profile（可用 ``cfg["_active"]`` 指定目标 profile），
            ``check_interval`` 等写回全局。

    Note:
        本函数只写数据，**不会切换 active 学校**（切换请用
        :func:`switch_profile`）。只有当配置里没有 active、或 active 指向
        一个不存在的学校时才做兜底修正。

    Warning:
        ``PROFILE_KEYS`` 里的 7 个字段是**整条覆盖**写入的，因此 ``cfg``
        必须是「被写目标学校自身的完整快照」。标准用法是
        ``cfg = load()``（此时 ``cfg`` 就是 active 学校的快照）→ 只改需要
        改的键 → ``save(cfg)``；跨学校写入则必须显式指定
        ``cfg["_active"] = 目标 id`` **并且** 让 7 个字段都来自那一所学校，
        否则会整条覆盖目标学校（例如拿 A 的快照去写 B，B 就会被 A 覆盖）。
    """
    store = _load_store()
    profiles = store.get('profiles') or []
    target_id = str(cfg.get('_active') or store.get('active') or '')
    prof = None
    for item in profiles:
        if item.get('id') == target_id:
            prof = item
            break
    if prof is None:
        prof = _active_profile(store)
    if prof is None:
        prof = dict(_DEFAULT_PROFILE)
        store['profiles'] = [prof]
    for key in PROFILE_KEYS:
        if key in cfg:
            val = cfg.get(key)
            prof[key] = '' if val is None else str(val)
    for key in GLOBAL_KEYS:
        if key in cfg:
            store[key] = cfg.get(key)
    active = store.get('active')
    if not active or active not in [
            p.get('id') for p in store.get('profiles') or []]:
        store['active'] = prof.get('id')
    _write(store)


def list_profiles():
    """列出所有学校配置。

    Returns:
        [{"id", "name", "ssid", "username"}, ...]，不含密码。
    """
    store = _load_store()
    return [_public_profile(p) for p in store.get('profiles') or []]


def get_active():
    """返回当前生效的学校配置 id（无配置时返回 ""）"""
    store = _load_store()
    prof = _active_profile(store)
    if prof:
        return prof.get('id')
    return ''


def switch_profile(pid):
    """切换当前学校。成功返回 True；pid 不存在返回 False"""
    store = _load_store()
    profiles = store.get('profiles') or []
    for prof in profiles:
        if prof.get('id') == pid:
            if store.get('active') != pid:
                store['active'] = pid
                _write(store)
                log('已切换学校：%s' % (prof.get('name') or pid))
            return True
    return False


def add_profile(name, ssid, username, password, portal_url=''):
    """新增一个学校配置并自动切为当前。

    Args:
        name: 显示名称（如「某某大学」）。
        ssid: 校园 WiFi 名称。
        username: 账号。
        password: 明文密码（落盘时自动 DPAPI 加密）。
        portal_url: 认证页地址，留空表示自动探测。

    Returns:
        新学校配置的 id。
    """
    existed = os.path.exists(CONFIG_PATH)
    store = _load_store()
    profiles = store.get('profiles') or []
    # 首次使用或仍是一个完全空白的默认学校时，直接替换它
    if not existed or (len(profiles) == 1
                       and not profiles[0].get('username')
                       and not profiles[0].get('password')):
        profiles = []
    pid = _unique_id(_slug(ssid or name, 'school'), profiles)
    prof = {
        'id': pid,
        'name': (name or ssid or pid).strip(),
        'ssid': (ssid or '').strip(),
        'username': (username or '').strip(),
        'password': password or '',
        'portal_url': (portal_url or '').strip(),
        'user_field': '',
        'pwd_field': '',
        'extra_params': '',
    }
    profiles.append(prof)
    store['profiles'] = profiles
    store['active'] = pid
    _write(store)
    log('已新增学校配置：%s（%s）' % (prof['name'], pid))
    return pid


def delete_profile(pid):
    """删除指定学校。至少保留一所学校，成功返回 True"""
    store = _load_store()
    profiles = store.get('profiles') or []
    if len(profiles) <= 1:
        return False
    kept = [p for p in profiles if p.get('id') != pid]
    if len(kept) == len(profiles):
        return False
    store['profiles'] = kept
    if store.get('active') == pid:
        store['active'] = kept[0].get('id')
    _write(store)
    return True


def profile_id_for(ssid):
    """按 SSID 查找学校配置 id。

    Args:
        ssid: 校园 WiFi 名称。

    Returns:
        匹配的 profile id；找不到返回 None。
    """
    key = (ssid or '').strip().lower()
    if not key:
        return None
    store = _load_store()
    for prof in store.get('profiles') or []:
        if (prof.get('ssid') or '').strip().lower() == key:
            return prof.get('id')
    return None


_LOG_LOCK = threading.Lock()
_LOG_MUTEX_NAME = 'Local\\CampusNetLogMutex_2026'
_LOG_MUTEX = None


def _log_mutex():
    """惰性创建跨进程日志互斥量。

    Returns:
        (kernel32, handle)；非 Windows 或创建失败时返回 None，
        此时降级为仅进程内串行（日志仍可写，只是跨进程不再互斥）。
    """
    global _LOG_MUTEX
    if _LOG_MUTEX is None:
        try:
            k32 = ctypes.WinDLL('kernel32', use_last_error=True)
            k32.CreateMutexW.argtypes = [
                ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.WaitForSingleObject.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32]
            k32.WaitForSingleObject.restype = ctypes.c_uint32
            k32.ReleaseMutex.argtypes = [ctypes.c_void_p]
            k32.ReleaseMutex.restype = ctypes.c_bool
            handle = k32.CreateMutexW(None, False, _LOG_MUTEX_NAME)
            _LOG_MUTEX = (k32, handle) if handle else False
        except Exception:
            _LOG_MUTEX = False
    return _LOG_MUTEX or None


def log(msg):
    """追加一行日志到 campusnet.log（超过 512KB 自动轮转）

    Note:
        ``--silent`` 后台守护与界面会**同时**往同一个日志追加内容。实测 Windows 上
        并发 ``open(..., "a")`` / ``os.open(O_APPEND)`` 都会丢行或把两行写串
        （四线程写 200 行只剩 50 行、四进程写 200 行只剩 128 行且出现空行），
        因此这里做了两层串行：进程内 :data:`_LOG_LOCK`，跨进程命名互斥量。
        取不到互斥量时降级为仅进程内加锁，绝不因日志问题抛异常。
    """
    import datetime
    line = '[%s] %s\n' % (
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg)
    data = line.encode('utf-8', 'replace')
    with _LOG_LOCK:
        mutex = _log_mutex()
        owned = False
        k32 = None
        handle = None
        if mutex is not None:
            k32, handle = mutex
            try:
                owned = k32.WaitForSingleObject(handle, 2000) in (0, 128)
            except Exception:
                owned = False
        fd = None
        try:
            try:
                if os.path.exists(LOG_PATH) and \
                        os.path.getsize(LOG_PATH) > 524288:
                    os.replace(LOG_PATH, LOG_PATH + '.old')
            except Exception:
                pass
            fd = os.open(
                LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 420)
            os.write(fd, data)
        except Exception:
            pass
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            if owned and k32 is not None:
                try:
                    k32.ReleaseMutex(handle)
                except Exception:
                    pass
