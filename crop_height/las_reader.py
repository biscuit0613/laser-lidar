"""LAS 点云文件读取与基本信息提取模块

本模块负责：
- 读取 LAS 格式的点云文件
- 提取文件元数据（坐标范围、分类信息、CRS 等）
- 提取三维坐标点和 RGB 颜色数据

依赖: laspy, numpy
"""

from pathlib import Path
import laspy
import numpy as np
from dataclasses import dataclass


@dataclass
class LasInfo:
    """LAS 文件的元数据结构体

    包含文件路径、点数、坐标边界、坐标系、各类别点数、是否有RGB、字段列表等信息。
    """
    path: str            # 文件路径
    point_count: int     # 点云总数
    bounds: dict         # 坐标范围: {'x': (min,max), 'y': (min,max), 'z': (min,max)}
    crs: str             # 坐标参考系 WKT 字符串
    classifications: dict  # 各类别点数字典, e.g. {1: 101106, 2: 16913}
    has_rgb: bool        # 是否包含 RGB 颜色信息
    fields: list         # 点云所有维度字段名列表


def _get_crs_wkt(las: laspy.LasData) -> str:
    """安全地解析 LAS 文件的坐标参考系

    尝试从 LAS header 中解析 CRS (Coordinate Reference System)，
    如果解析失败则返回空字符串，避免中断处理流程。

    Args:
        las: laspy 读取的 LAS 数据对象

    Returns:
        CRS 的 WKT 字符串，解析失败返回 ''
    """
    try:
        crs = las.header.parse_crs()
        return str(crs) if crs else ''
    except Exception:
        return ''


def read_las(path: str | Path) -> laspy.LasData:
    """读取 LAS 文件并返回 laspy 数据对象

    封装 laspy.read()，作为整个项目的统一入口。

    Args:
        path: LAS 文件路径

    Returns:
        laspy.LasData 对象，包含所有点云数据
    """
    return laspy.read(path)


def get_las_info(path: str | Path) -> LasInfo:
    """提取 LAS 文件的完整元数据信息

    读取 LAS 并解析出点数、坐标边界、分类分布、坐标系等关键元数据。

    Args:
        path: LAS 文件路径

    Returns:
        LasInfo 结构体，包含文件元数据
    """
    las = read_las(path)
    # 统计每个分类类别的点数
    classes, counts = np.unique(las.classification, return_counts=True)
    # 检查是否包含 RGB 三个通道
    has_rgb = all(hasattr(las, c) for c in ('red', 'green', 'blue'))
    return LasInfo(
        path=str(path),
        point_count=len(las.points),
        bounds={
            'x': (float(las.x.min()), float(las.x.max())),
            'y': (float(las.y.min()), float(las.y.max())),
            'z': (float(las.z.min()), float(las.z.max())),
        },
        crs=_get_crs_wkt(las),
        classifications={int(c): int(cnt) for c, cnt in zip(classes, counts)},
        has_rgb=has_rgb,
        fields=list(las.point_format.dimension_names),
    )


def extract_points(las: laspy.LasData) -> np.ndarray:
    """从 LAS 数据中提取所有三维点坐标

    将 X, Y, Z 三列堆叠为 N×3 的 numpy 数组。

    Args:
        las: laspy 数据对象

    Returns:
        shape (N, 3) 的数组，每行为 (x, y, z) 坐标
    """
    return np.vstack([las.x, las.y, las.z]).T


def extract_rgb(las: laspy.LasData) -> np.ndarray | None:
    """从 LAS 数据中提取 RGB 颜色信息

    如果 LAS 包含 RGB 数据，返回 N×3 的数组（值范围通常 0~65535）；
    否则返回 None。

    Args:
        las: laspy 数据对象

    Returns:
        shape (N, 3) 的 RGB 数组，或 None
    """
    if not all(hasattr(las, c) for c in ('red', 'green', 'blue')):
        return None
    rgb = np.vstack([np.array(las.red), np.array(las.green), np.array(las.blue)]).T
    return rgb
