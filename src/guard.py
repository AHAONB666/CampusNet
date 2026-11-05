# -*- coding: utf-8 -*-
# 反编译还原（decompyle3 3.8）。原文件 guard.py，PyInstaller 打包于 CampusNet.exe。
# 个别 try/except 结构由字节码还原，语义等价。
"""守护逻辑：连 WiFi -> 探网 -> 认证 -> 循环"""
import ctypes
import threading
import time

import config
import eportal
import netutil
import portal

MUTEX_NAME = 'Global\\CampusNetGuardMutex_2026'

FATAL_HINTS = ('用户不存在', '密码错误', '密码不正确', '用户名或密码', '账号已锁',
               '账户已锁定', '账号已被锁定', '欠费', '已停机', '已暂停',
               '认证失败次数', '账号状态异常')


class State(object):
    on_change = None

    def __init__(self):
        self.ssid = ''
        self.online = False
        self.was_online = False
        self.last_msg = '启动中'
        self.logs = []
        self.retry_count = 0
        self.fail_count = 0
        self.fatal = False
        self.total_relogin = 0
        self.running = False
        self.retry_at = 0.0
        self.last_error = ''

    def notify(self):
        """通知 UI 读取最新快照；调用方可位于后台线程。"""
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def set_retry(self, seconds):
        """记录真实的下一次重试时间，供界面显示倒计时。"""
        self.retry_at = time.time() + max(0, int(seconds))
        self.notify()

    def clear_retry(self):
        """重试被唤醒或完成后清除倒计时，避免展示伪造数字。"""
        if self.retry_at:
            self.retry_at = 0.0
            self.notify()

    def push(self, msg):
        self.last_msg = msg
        self.logs.append(msg)
        if len(self.logs) > 300:
            del self.logs[:100]
        config.log(msg)
        self.notify()


class Guard(threading.Thread):

    def __init__(self, cfg, state, on_change=None):
        threading.Thread.__init__(self, daemon=True)
        self.cfg = cfg
        self.state = state
        self.ip = ''
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._mutex = None
        state.on_change = on_change

    def _acquire_mutex(self):
        """全局命名互斥量，保证只有一个守护实例在跑"""
        try:
            k32 = ctypes.windll.kernel32
            h = k32.CreateMutexW(None, False, MUTEX_NAME)
            if h and k32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
                k32.CloseHandle(h)
                return False
            self._mutex = h
            return True
        except Exception:
            return True

    def stop(self):
        self.state.clear_retry()
        self._stop.set()
        self._wake.set()

    def wake(self):
        """立即结束当前等待；倒计时随唤醒同时失效。"""
        self.state.clear_retry()
        self._wake.set()

    def run(self):
        if not self._acquire_mutex():
            self.state.push('已有守护进程在运行，本实例仅显示界面')
            return
        self.state.running = True
        self.state.push('守护已启动')
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                self.state.last_error = str(e)
                self.state.push('异常: %r' % (e,))
            interval = max(5, int(self.cfg.get('check_interval') or 20))
            self._wake.wait(interval)
            self._wake.clear()
            self.state.clear_retry()
        self.state.running = False
        self.state.clear_retry()
        self.state.push('守护已停止')

    def tick(self):
        cfg = self.cfg
        ssid = (cfg.get('ssid') or '').strip()

        # 1) WiFi 没连到目标 SSID 就先连
        if ssid:
            cur = netutil.current_ssid()
            self.state.ssid = cur or '未连接'
            if not netutil.wifi_connected_to(ssid):
                self.state.push('当前 WiFi=%s，尝试连接 %s' % (cur or '无', ssid))
                ok, out = netutil.connect_wifi(ssid)
                self.state.push('连接 %s %s' % (ssid, '指令已发送' if ok else '失败: ' + out))
                for _ in range(12):
                    if self._stop.is_set():
                        return
                    time.sleep(1)
                    if netutil.wifi_connected_to(ssid):
                        break
                cur = netutil.current_ssid()
                self.state.ssid = cur or '未连接'
                if not netutil.wifi_connected_to(ssid):
                    self.state.push('仍为 %s，本轮跳过' % (cur or '未连接'))
                    return
                self.state.push('已连上 %s，等待网络就绪' % ssid)
                time.sleep(2)

        # 2) 探测是否真联网（generate_204 未被劫持）
        self.ip = netutil.wlan_ip()
        if netutil.internet_ok(bind_ip=self.ip):
            self.state.online = True
            self.state.clear_retry()
            self.state.last_error = ''
            self.state.fatal = False
            if self.state.retry_count:
                self.state.retry_count = 0
                self.state.notify()
            elif not self.state.was_online:
                self.state.push('网络正常')
            self.state.was_online = True
            try:
                eportal.maybe_keepalive()
            except Exception:
                pass
            return

        self.state.online = False
        self.state.was_online = False
        self.state.retry_count += 1
        if self.state.retry_count > 1:
            self.state.push('未联网，第 %d 次尝试认证' % self.state.retry_count)

        # 3) 认证
        ok, msg = portal.login(cfg, bind_ip=self.ip)
        if ok:
            self.state.online = True
            self.state.was_online = True
            self.state.retry_count = 0
            self.state.fail_count = 0
            self.state.fatal = False
            self.state.last_error = ''
            self.state.clear_retry()
            self.state.total_relogin += 1
            self.state.push('✅ 认证成功（本次重连 %d 次）' % self.state.total_relogin)
            return

        self.state.last_error = msg or '认证未通过'
        self.state.push('❌ ' + (msg or '认证未通过'))

        # 3a) 账号类硬错误：停手，避免连续失败锁号
        if any(h in msg for h in FATAL_HINTS):
            self.state.fatal = True
            self.state.push('⛔ 账号或密码被拒绝，已暂停自动重试（防止账号被锁）')
            self.state.push('   改好账号密码后点「立即认证」即可恢复')
            self._wake.wait()
            self._wake.clear()
            self.state.clear_retry()
            self.state.fatal = False
            self.state.fail_count = 0
            self.state.notify()
            return

        # 3b) 软失败：第 2 次失败时重新探测认证页，指数退避
        self.state.fail_count += 1
        if self.state.fail_count == 2:
            if (self.cfg.get('portal_url') or '').strip():
                fresh = netutil.detect_portal_url(bind_ip=self.ip)
                if fresh:
                    self.cfg['portal_url'] = fresh
                    self.state.push('改用实时探测到的认证页重试')
        base = max(8, int(cfg.get('retry_interval') or 8))
        backoff = min(300, base * 2 ** min(self.state.fail_count - 1, 5))
        if self.state.fail_count in (3, 6, 10):
            self.state.push('已连续失败 %d 次，重试间隔放缓到 %d 秒'
                            % (self.state.fail_count, backoff))
        self.state.set_retry(backoff)
        self._wake.wait(backoff)
        self._wake.clear()
        self.state.clear_retry()
