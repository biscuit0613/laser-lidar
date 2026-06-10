"""样方分析模块 (Quadrat Analysis)

将分析区域划分为固定大小的样方（quadrat），
统计每个样方内的作物株高分布特征，用于：
- 发现田块内部的空间变异
- 比较不同区域的作物长势
- 辅助采样方案设计

依赖: numpy
"""

import numpy as np


def quadrat_analysis(
    chm: np.ndarray,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    block_size: int = 2,
):
    """对 CHM 进行样方统计分析

    将 CHM 网格按 block_size×block_size 划分为多个样方，
    对每个样方计算株高的均值、中位数、最大值、P90 等统计量。

    Args:
        chm:       shape (ny, nx) 的冠层高度模型
        x_grid:    shape (ny, nx) 的网格 X 坐标矩阵
        y_grid:    shape (ny, nx) 的网格 Y 坐标矩阵
        block_size: 样方大小（以网格数为单位），默认 2×2

    Returns:
        样方统计列表，每个元素为字典:
            row/col:   样方在网格中的行列位置
            x/y_center: 样方中心地理坐标
            count:      样方内有效像元数
            mean/median/max/p90: 株高统计值（米）

    Example:
        若 resolution=0.25m, block_size=2，则每个样方代表 0.5×0.5m 区域。
    """
    ny, nx = chm.shape
    blocks = []

    # 按行列步进遍历网格
    for i in range(0, ny, block_size):
        for j in range(0, nx, block_size):
            # 取出当前样方覆盖的 CHM 子块
            block = chm[i:i + block_size, j:j + block_size]
            # 筛选有效像元（非空且高度 > 1cm）
            valid = block[~np.isnan(block) & (block > 0.01)]
            if len(valid) == 0:
                continue  # 跳过无作物的样方

            # 计算样方的地理中心坐标
            y_center = float(y_grid[i:i + block_size, j:j + block_size].mean())
            x_center = float(x_grid[i:i + block_size, j:j + block_size].mean())

            blocks.append({
                'row': i // block_size,        # 样方行号
                'col': j // block_size,        # 样方列号
                'x_center': round(x_center, 4), # 中心 X 坐标
                'y_center': round(y_center, 4), # 中心 Y 坐标
                'count': int(len(valid)),       # 有效像元数
                'mean': round(float(valid.mean()), 4),
                'median': round(float(np.median(valid)), 4),
                'max': round(float(valid.max()), 4),
                'p90': round(float(np.percentile(valid, 90)), 4),
            })
    return blocks
