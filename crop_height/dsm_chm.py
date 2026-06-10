"""数字表面模型 (DSM) 与冠层高度模型 (CHM) 生成模块

核心算法流程：
1. DSM: 在每个网格单元内取植被点的最大 Z 值，得到冠层顶面高程
2. CHM: DSM 减去 DTM，得到每个网格的作物绝对高度
3. 统计: 计算 CHM 的均值/中位数/百分位数等分布特征

依赖: numpy
"""

import numpy as np


def build_dsm(
    veg_pts: np.ndarray,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
) -> np.ndarray:
    """由植被点生成数字表面模型（DSM）

    对每个网格单元，取该单元内所有植被点的最大 Z 值作为冠层顶面高程。
    这种方法称为"最大像元法"，能有效捕捉冠层顶部信号。

    Args:
        veg_pts: shape (N, 3) 的植被点坐标，列为 (x, y, z)
        x_edges: 网格 X 方向边界线，长度 = nx + 1
        y_edges: 网格 Y 方向边界线，长度 = ny + 1

    Returns:
        shape (ny, nx) 的 DSM 高程数组，无植被点的单元为 NaN

    Note:
        使用 searchsorted 实现 O(N log nx + N log ny) 的高效网格映射，
        优于逐点遍历的双重循环。
    """
    nx = len(x_edges) - 1   # X 方向网格数
    ny = len(y_edges) - 1   # Y 方向网格数
    dsm = np.full((ny, nx), np.nan)  # 初始化为 NaN

    # 将每个点映射到其所属的网格索引
    x_vals, y_vals, z_vals = veg_pts[:, 0], veg_pts[:, 1], veg_pts[:, 2]
    # searchsorted 返回点在边界数组中的插入位置，减1得到网格列索引
    xi = np.clip(np.searchsorted(x_edges, x_vals) - 1, 0, nx - 1)
    yi = np.clip(np.searchsorted(y_edges, y_vals) - 1, 0, ny - 1)

    # 遍历所有植被点，更新每个网格的最大 Z 值
    # 使用 numpy 索引比纯 Python 循环更高效
    for idx in range(len(veg_pts)):
        ix, iy = xi[idx], yi[idx]
        z = z_vals[idx]
        # 如果当前网格还没有值，或当前 Z 更大，则更新
        if np.isnan(dsm[iy, ix]) or z > dsm[iy, ix]:
            dsm[iy, ix] = z

    return dsm


def compute_chm(dsm: np.ndarray, dtm: np.ndarray) -> np.ndarray:
    """计算冠层高度模型（CHM）= DSM - DTM

    CHM 的每个网格值代表该位置作物的绝对高度：
      Crop Height = Canopy Surface Elevation - Ground Elevation

    将负值（由于插值误差导致 DSM < DTM）截断为 0。

    Args:
        dsm: shape (ny, nx) 的数字表面模型
        dtm: shape (ny, nx) 的数字地形模型

    Returns:
        shape (ny, nx) 的 CHM 作物高度数组，单位米
    """
    chm = dsm - dtm
    chm[chm < 0] = 0   # 负值归零，避免物理上不合理的高度
    return chm


def chm_statistics(chm: np.ndarray) -> dict:
    """计算 CHM 的统计特征

    排除 NaN 和低于 1cm 的网格，因为这些通常是无作物区域或噪声。
    返回株高的均值、中位数、分位数、标准差等。

    Args:
        chm: shape (ny, nx) 的冠层高度模型

    Returns:
        统计字典，包含 count, min, max, mean, median, std,
        p25(25分位), p75(75分位), p90(90分位), p95(95分位)
    """
    # 筛选有效像元：非空且高度 > 1cm
    valid = chm[~np.isnan(chm) & (chm > 0.01)]
    if len(valid) == 0:
        return {}
    return {
        'count': int(len(valid)),           # 有效像元数
        'min': round(float(valid.min()), 4),
        'max': round(float(valid.max()), 4),
        'mean': round(float(valid.mean()), 4),
        'median': round(float(np.median(valid)), 4),
        'std': round(float(valid.std()), 4),
        'p25': round(float(np.percentile(valid, 25)), 4),   # 下四分位
        'p75': round(float(np.percentile(valid, 75)), 4),   # 上四分位
        'p90': round(float(np.percentile(valid, 90)), 4),   # 90% 分位，常用作物指标
        'p95': round(float(np.percentile(valid, 95)), 4),   # 95% 分位，反映最高作物
    }


def build_grid(bounds: dict, resolution: float = 0.25):
    """构建规则分析网格

    根据点云坐标范围和指定分辨率，生成网格边界线和网格中心点坐标矩阵。

    Args:
        bounds: 坐标范围字典，格式 {'x': (min, max), 'y': (min, max), 'z': ...}
        resolution: 网格分辨率，单位米，默认 0.25m (即每平方米 4 个网格)

    Returns:
        (x_edges, y_edges, x_grid, y_grid) 元组:
            x_edges:  X 方向网格边界，长度 nx+1
            y_edges:  Y 方向网格边界，长度 ny+1
            x_grid:   shape (ny, nx) 网格中心 X 坐标矩阵
            y_grid:   shape (ny, nx) 网格中心 Y 坐标矩阵
    """
    x_min, x_max = bounds['x']
    y_min, y_max = bounds['y']

    # 计算网格数量（向上取整确保覆盖整个区域）
    nx = int(np.ceil((x_max - x_min) / resolution))
    ny = int(np.ceil((y_max - y_min) / resolution))

    # 生成网格边界线（等间距）
    x_edges = np.linspace(x_min, x_min + nx * resolution, nx + 1)
    y_edges = np.linspace(y_min, y_min + ny * resolution, ny + 1)

    # 计算网格中心点坐标
    x_centers = (x_edges[:-1] + x_edges[1:]) / 2
    y_centers = (y_edges[:-1] + y_edges[1:]) / 2
    x_grid, y_grid = np.meshgrid(x_centers, y_centers)

    return x_edges, y_edges, x_grid, y_grid
