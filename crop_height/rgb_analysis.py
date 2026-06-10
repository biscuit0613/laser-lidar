"""RGB 颜色分析模块

利用点云的 RGB 颜色信息估算植被覆盖度和绿色指数。
虽然 LAS 的 RGB 数据不像多光谱那样有近红外波段，
但仍可以通过颜色特征分析作物的绿色程度。

计算方法:
1. Green Ratio: 绿色通道占总亮度的比例
2. Vegetation Cover: 绿光占比超过阈值（默认 0.35）的点比例
3. Excess Green (ExG): 2G - R - B，经典植被指数

依赖: numpy
"""

import numpy as np


def green_ratio(rgb: np.ndarray) -> float:
    """计算点云整体的绿光占比

    Green Ratio = 平均 G / (R + G + B)
    数值越高表示整体颜色越绿，植被越健康。

    Args:
        rgb: shape (N, 3) 的 RGB 数组，值范围 0~65535 (16位)

    Returns:
        绿光占比 0.0~1.0
    """
    total = rgb.sum(axis=1)
    mask = total > 0
    if not mask.any():
        return 0.0
    # 计算每个点的 G/(R+G+B) 并取平均
    g_ratio = rgb[mask, 1].astype(float) / total[mask].astype(float)
    return float(np.mean(g_ratio))


def vegetation_cover(rgb: np.ndarray, g_threshold: float = 0.35) -> dict:
    """估算植被覆盖度

    以绿光占比超过阈值作为判断植被点的标准，
    计算植被点占总点的比例，间接反映植被覆盖度。

    阈值说明:
    0.35 是经验值，适用于一般绿色植被场景。
    可根据实际数据调整：阈值越低，覆盖度越高。

    Args:
        rgb: shape (N, 3) 的 RGB 数组
        g_threshold: 绿光占比阈值，默认 0.35

    Returns:
        包含覆盖度和分析信息的字典
    """
    total = rgb.sum(axis=1).astype(float)
    mask = total > 0
    if not mask.any():
        return {'coverage': 0.0, 'threshold': g_threshold}
    g_ratio = rgb[mask, 1].astype(float) / total[mask]
    coverage = float((g_ratio > g_threshold).mean())
    return {
        'coverage': round(coverage * 100, 2),  # 植被覆盖度百分比
        'threshold': g_threshold,
        'points_analyzed': int(mask.sum()),
    }


def excess_green(rgb: np.ndarray) -> dict:
    """计算过绿指数 (Excess Green, ExG)

    ExG = 2*G - R - B
    ExG 是经典的基于 RGB 的植被指数，正值表示绿色植被，
    值越大表示植被越茂盛。

    先将 16 位 RGB 值归一化到 0~1，再计算 ExG。

    Args:
        rgb: shape (N, 3) 的 RGB 数组，值范围 0~65535

    Returns:
        ExG 的均值和标准差
    """
    # 将 16 位整数归一化到 [0, 1] 浮点数
    norm = rgb.astype(float) / 65535.0
    r, g, b = norm[:, 0], norm[:, 1], norm[:, 2]
    total = r + g + b
    mask = total > 0
    if not mask.any():
        return {'exg_mean': 0.0}
    # ExG 公式: 2G - R - B
    exg = 2 * g[mask] - r[mask] - b[mask]
    return {
        'exg_mean': round(float(exg.mean()), 4),
        'exg_std': round(float(exg.std()), 4),
    }
