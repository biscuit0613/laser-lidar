"""数字地形模型 (DTM) 生成模块

通过对地面点进行空间插值，生成规则网格的数字地形模型。
DTM 是计算作物株高的基准面，反映去除了植被后的裸地表高程。

插值方法:
- 默认使用 scipy 的线性插值 (linear)，在点云分布均匀时效果良好
- 当点数不足时回退到中位数填充

依赖: numpy, scipy.interpolate
"""

import numpy as np
from scipy.interpolate import griddata


def compute_dtm(
    ground_pts: np.ndarray,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    method: str = 'linear',
) -> np.ndarray:
    """由地面点插值生成数字地形模型（DTM）

    以地面点作为已知样本点，在规则网格上进行空间插值，
    得到每个网格中心点的地面高程估计值。

    Args:
        ground_pts: shape (M, 3) 的地面点坐标数组，列为 (x, y, z)
        x_grid: shape (ny, nx) 的网格 X 坐标矩阵（由 meshgrid 生成）
        y_grid: shape (ny, nx) 的网格 Y 坐标矩阵
        method: 插值方法，支持 'linear'(线性), 'nearest'(最近邻),
                'cubic'(三次) 三种，推荐 'linear'

    Returns:
        shape (ny, nx) 的 DTM 高程数组，单位米

    Note:
        当某点超出地面点凸包范围时使用中位数填充 (fill_value)，
        确保整张 DTM 没有空洞。
    """
    # 地面点数量过少时直接使用中位数值填充
    if len(ground_pts) < 4:
        z_val = np.median(ground_pts[:, 2]) if len(ground_pts) > 0 else 0
        return np.full_like(x_grid, z_val)

    # 使用 scipy 的 griddata 进行散点插值
    # 输入: 已知点的 (x,y) 坐标和 z 值
    # 输出: 在 (x_grid, y_grid) 处插值得到的 z 值
    dtm = griddata(
        ground_pts[:, :2],      # 已知点的 x, y 坐标
        ground_pts[:, 2],       # 已知点的 z 值（高程）
        (x_grid, y_grid),       # 目标网格坐标
        method=method,           # 插值方法
        fill_value=np.median(ground_pts[:, 2]),  # 外推区域填充地面高程中位数
    )
    return dtm
