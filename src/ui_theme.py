# -*- coding: utf-8 -*-
"""iOS 风格设计令牌（Design Tokens）

集中定义颜色、字体层级、圆角、间距、阴影与动效曲线，
ui_quiet.py 只消费这里的令牌，不再散落硬编码数值。

设计依据：Apple Human Interface Guidelines
- 颜色取自 iOS 系统色（systemBlue / systemGray / systemGreen 等）
- 字号取 SF 字阶（LargeTitle 34 / Title2 22 / Headline 17 / Body 15 / Caption 12）
- 间距取 4pt 栅格（4 / 8 / 12 / 16 / 20 / 24 / 32 / 40）
- 圆角：卡片 16 / 控件 10 / 胶囊取高度一半
- 动效：iOS 标准弹簧（response 0.35 / damping 0.86）
"""

# ---------------------------------------------------------------- 间距（4pt 栅格）
SPACE = {
    'xs': 4,
    'sm': 8,
    'md': 12,
    'lg': 16,
    'xl': 20,
    'xxl': 24,
    'xxxl': 32,
    'huge': 40,
}

# ---------------------------------------------------------------- 圆角
RADIUS = {
    'card': 16,      # 分组卡片
    'btn': 12,       # 按钮
    'field': 10,     # 输入框
    'chip': 8,       # 小标签
    'window': 12,    # 窗口外框（macOS 风格偏小，Windows 11 参考值）
    'pill': 999,     # 胶囊（取高度一半）
}

# ---------------------------------------------------------------- 字体层级
# (字号, 字重)；tkinter 字重只有 normal/bold
FONT = {
    'large_title': (34, 'bold'),
    'title1': (28, 'bold'),
    'title2': (22, 'bold'),
    'title3': (20, 'bold'),
    'headline': (15, 'bold'),
    'body': (14, 'normal'),
    'callout': (13, 'normal'),
    'subhead': (13, 'normal'),
    'footnote': (12, 'normal'),
    'caption1': (11, 'normal'),
    'caption2': (10, 'normal'),
    'mono_num': (34, 'normal'),   # 数字大号（Segoe UI Variable Display）
}

# ---------------------------------------------------------------- 字距
TRACKING = {
    'brand': 1.6,      # 品牌字（CAMPUSNET）大写拉宽
    'section': 0.9,    # 分组标题
    'label': 0.4,      # 数据标签
    'normal': 0.0,
}

# ---------------------------------------------------------------- 浅色
LIGHT = dict(
    name='浅色',
    # 背景层级：分组背景 → 卡片 → 浮层
    bg='#F2F2F7',          # systemGroupedBackground
    card='#FFFFFF',        # secondarySystemGroupedBackground
    bar='#F2F2F7',
    # 文字层级
    text='#000000',        # label
    text2='#6C6C70',       # secondaryLabel（3C3C43 60% 近似）
    text3='#8E8E93',       # tertiaryLabel / systemGray
    # 分隔线
    line='#E3E3E8',        # separator（C6C6C8 30% 近似）
    line2='#D1D1D6',       # opaqueSeparator
    div='#E3E3E8',
    card_line='#EFEFF4',
    line_strong='#C6C6C8',
    # 墨色（兼容旧键名）
    ink='#000000',
    # 强调色
    accent='#007AFF',      # systemBlue
    acc_soft='#E8F1FF',    # systemBlue 10%
    on_accent='#FFFFFF',
    # 语义色
    ok='#34C759',          # systemGreen
    warn='#FF9500',        # systemOrange
    err='#FF3B30',         # systemRed
    err_soft='#FFEBEA',
    # 中性填充（iOS fill）
    neu_soft='#F2F2F7',    # systemGray6
    neu_sol='#E5E5EA',     # systemGray5
    neu_gly='#8E8E93',
    divider_stat='#E3E3E8',
    chevron='#C4C4C6',     # systemGray3
    seg_bg='#EFEFF0',      # 分段控件轨道
    # 按钮
    btn='#007AFF',
    btn_fg='#FFFFFF',
    btn2='#E5E5EA',
    btn2_fg='#007AFF',
    hover='#EAEAF0',       # 列表点击高亮
    # 开关
    sw_on='#34C759',
    sw_off='#E9E9EB',
    knob='#FFFFFF',
    track='#C7C7CC',
    # 阴影
    shadow='#000000',
)

# ---------------------------------------------------------------- 深色
DARK = dict(
    name='深色',
    bg='#000000',          # systemBackground（OLED 纯黑）
    card='#1C1C1E',        # secondarySystemGroupedBackground
    bar='#000000',
    text='#FFFFFF',
    text2='#9B9BA1',       # EBEBF5 60% 近似
    text3='#8E8E93',
    line='#38383A',        # separator
    line2='#48484A',
    div='#38383A',
    card_line='#2C2C2E',
    line_strong='#48484A',
    ink='#FFFFFF',
    accent='#0A84FF',      # systemBlue (dark)
    acc_soft='#0F2B48',
    on_accent='#FFFFFF',
    ok='#30D158',
    warn='#FF9F0A',
    err='#FF453A',
    err_soft='#3A1B19',
    neu_soft='#1C1C1E',
    neu_sol='#2C2C2E',
    neu_gly='#8E8E93',
    divider_stat='#38383A',
    chevron='#5C5C5E',
    seg_bg='#1C1C1E',
    btn='#0A84FF',
    btn_fg='#FFFFFF',
    btn2='#2C2C2E',
    btn2_fg='#0A84FF',
    hover='#2C2C2E',
    sw_on='#30D158',
    sw_off='#39393D',
    knob='#FFFFFF',
    track='#5C5C5E',
    shadow='#000000',
)

PALETTES = {'light': LIGHT, 'dark': DARK}


# ---------------------------------------------------------------- 动效
# iOS 标准时长（秒）
DUR = {
    'instant': 0.10,    # 按压反馈
    'fast': 0.20,       # hover / 小元素
    'normal': 0.32,     # 页面转场
    'slow': 0.45,       # 弹层
}

# 曲线参数
CURVE = {
    'standard': 'std',      # 对称缓入缓出，用于转场
    'decelerate': 'dec',    # 减速，用于入场
    'accelerate': 'acc',    # 加速，用于退场
    'spring': 'spring',     # 轻微回弹，用于开关与按压
}


def spring_value(t, damping=0.86, response=0.35):
    """一阶阻尼弹簧的归一化位移（0→1，可轻微过冲）。

    t         : 已过时间 / 总时长
    damping   : 阻尼比，越小回弹越明显（iOS 默认约 0.86）
    response  : 响应时长，影响收敛速度
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    import math
    w = 2.0 * math.pi / max(0.05, response)
    z = max(0.05, min(0.99, damping))
    wd = w * math.sqrt(1.0 - z * z)
    e = math.exp(-z * w * t)
    return 1.0 - e * (math.cos(wd * t) + (z * w / wd) * math.sin(wd * t))


def ios_ease_standard(t):
    """iOS 标准缓动 cubic-bezier(0.4, 0.0, 0.2, 1) 的近似：先快后慢、收尾平稳。"""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 2.4


def ios_ease_decelerate(t):
    """cubic-bezier(0.0, 0.0, 0.2, 1)：入场"""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3.2


def ios_ease_accelerate(t):
    """cubic-bezier(0.4, 0.0, 1, 1)：退场"""
    t = max(0.0, min(1.0, t))
    return t ** 2.4


def lerp(a, b, t):
    return a + (b - a) * t


def mix_color(c1, c2, t):
    """两个 #rrggbb 按 t 线性插值，用于 Canvas 没有 alpha 时的渐显。"""
    t = max(0.0, min(1.0, t))
    try:
        a, b = c1.lstrip('#'), c2.lstrip('#')
        if len(a) >= 6 and len(b) >= 6:
            r1, g1, b1 = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
            r2, g2, b2 = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
            return '#%02x%02x%02x' % (
                int(round(lerp(r1, r2, t))),
                int(round(lerp(g1, g2, t))),
                int(round(lerp(b1, b2, t))),
            )
    except Exception:
        pass
    return c2


def with_alpha_over(fg, alpha, bg):
    """把 fg 以 alpha 叠在 bg 上，得到等效不透明色（Canvas 无 alpha 时的替代）。"""
    return mix_color(bg, fg, alpha)
