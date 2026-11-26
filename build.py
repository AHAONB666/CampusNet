# -*- coding: utf-8 -*-
"""CampusNet 一键构建脚本

用法:
    D:/开发环境/Python/3.8/python.exe build.py

输出:
    dist/CampusNet.exe  （单文件、无控制台窗口）
    构建完成后打印版本号、文件大小、SHA256

设计要点:
    - 全部路径由 __file__ 推导，不含任何绝对路径，换机器/换目录可直接复用
    - 入口固定为 src/ui_scifi.py（它负责分发: 默认加载 ui_quiet，--silent 走守护）
    - ui_quiet / psutil / tray 必须显式声明为 hidden-import，否则动态导入会被漏掉
    - 构建前清空 dist/ 与中间目录，避免拿到上一轮的陈旧产物
"""
import os
import re
import sys
import shutil
import hashlib
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'src')
ASSETS = os.path.join(ROOT, 'assets')
ENTRY = os.path.join(SRC, 'ui_scifi.py')
ICON = os.path.join(ASSETS, 'icon.ico')
DIST = os.path.join(ROOT, 'dist')
WORK = os.path.join(ROOT, '_build', 'work')

HIDDEN_IMPORTS = ['ui_quiet', 'psutil', 'tray']


def read_version():
    """从 src/config.py 读取 APP_VERSION，避免版本号两处维护"""
    cfg = os.path.join(SRC, 'config.py')
    with open(cfg, encoding='utf-8') as f:
        m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", f.read())
    if not m:
        raise SystemExit('无法从 src/config.py 读取 APP_VERSION')
    return m.group(1)


def check_env():
    """构建前置检查：入口、图标、PyInstaller 是否就位"""
    problems = []
    if not os.path.isfile(ENTRY):
        problems.append('缺少入口文件: %s' % ENTRY)
    if not os.path.isfile(ICON):
        problems.append('缺少图标文件: %s' % ICON)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        problems.append('当前解释器未安装 PyInstaller: %s' % sys.executable)
    if problems:
        for p in problems:
            print('[错误] ' + p)
        raise SystemExit(1)
    print('[环境] Python   : %s' % sys.version.split()[0])
    print('[环境] 解释器   : %s' % sys.executable)
    import PyInstaller
    print('[环境] PyInstaller: %s' % PyInstaller.__version__)


def clean():
    for d in (DIST, WORK):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    print('[清理] 已移除 dist/ 与 _build/work/')


def build():
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--onefile',
        '--windowed',
        '--name', 'CampusNet',
        '--icon', ICON,
        '--add-data', '%s%sassets' % (ICON, os.pathsep),
        '--distpath', DIST,
        '--workpath', WORK,
        '--specpath', WORK,
    ]
    for mod in HIDDEN_IMPORTS:
        cmd += ['--hidden-import', mod]
    cmd.append(ENTRY)

    print('[构建] 开始打包 ...')
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit('[失败] PyInstaller 返回码 %d' % proc.returncode)


def report(version):
    exe = os.path.join(DIST, 'CampusNet.exe')
    if not os.path.isfile(exe):
        raise SystemExit('[失败] 未生成 %s' % exe)
    size = os.path.getsize(exe)
    with open(exe, 'rb') as f:
        sha = hashlib.sha256(f.read()).hexdigest().upper()
    print('')
    print('=' * 56)
    print('  构建完成')
    print('=' * 56)
    print('  版本   : v%s' % version)
    print('  路径   : %s' % exe)
    print('  大小   : %d 字节 (%.2f MB)' % (size, size / 1048576.0))
    print('  SHA256 : %s' % sha)
    print('=' * 56)
    return sha


def deploy():
    """把构建产物同步到项目根目录。

    程序把 config.json 存在 exe 同目录，因此根目录必须保有一份可运行的 exe，
    否则 launcher 与日常双击会失去配置。dist/ 作为发布归档保留。
    """
    src = os.path.join(DIST, 'CampusNet.exe')
    dst = os.path.join(ROOT, 'CampusNet.exe')
    try:
        shutil.copy2(src, dst)
        print('[部署] 已同步到根目录: %s' % dst)
    except PermissionError:
        print('[提示] 根目录 CampusNet.exe 正在运行，已跳过覆盖')
        print('       退出程序后重新执行 build.py 即可完成同步')


def main():
    version = read_version()
    print('=' * 56)
    print('  CampusNet 构建 v%s' % version)
    print('=' * 56)
    check_env()
    clean()
    build()
    report(version)
    deploy()
    print('')
    print('  发布 : 上传 dist/CampusNet.exe 到 GitHub Release')
    print('  运行 : 双击根目录 CampusNet.exe，或 launcher/启动CampusNet.vbs')


if __name__ == '__main__':
    main()
