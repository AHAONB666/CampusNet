# decompyle3 version 3.8.0
# Python bytecode 3.8
# Decompiled from: Python 3.8.10 (tags/v3.8.10:3d8993a, May  3 2021, 11:48:03) [MSC v.1928 64 bit (AMD64)]
# Embedded file name: autostart.py
"""开机自启：直接调用 Windows 注册表 API（不依赖 reg.exe）"""
import os, sys
try:
    import winreg
except ImportError:
    winreg = None
RUN_SUBKEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
VALUE_NAME = 'CampusNetAutoLogin'


def _cmd():
    if getattr(sys, 'frozen', False):
        return '"%s" --silent' % sys.executable
    here = os.path.dirname(os.path.abspath(__file__))
    py = sys.executable
    pyw = py.replace('python.exe', 'pythonw.exe')
    if not os.path.exists(pyw):
        pyw = py
    return '"%s" "%s" --silent' % (pyw, os.path.join(here, 'main.py'))


def is_enabled():
    if not winreg:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_SUBKEY, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return bool(val)
    except Exception:
        return False


def enable():
    if not winreg:
        return False, 'winreg 不可用'
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_SUBKEY, 0,
                                winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, _cmd())
        return True, _cmd()
    except Exception as e:
        return False, repr(e)


def disable():
    if not winreg:
        return False, 'winreg 不可用'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_SUBKEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE_NAME)
        return True, 'ok'
    except FileNotFoundError:
        return True, '未设置'
    except Exception as e:
        return False, repr(e)
