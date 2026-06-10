"""地面点与植被点分离模块

根据 LAS 标准分类标签将点云分为地面点和植被点：
- Class 2 (Ground): 地面点，用于构建数字地形模型 DTM
- Class 1 (Unclassified): 未分类点，在农田场景中通常为植被/作物点

LAS 标准分类说明 (ASPRS):
  Class 0: Never classified
  Class 1: Unclassified
  Class 2: Ground
  Class 3: Low Vegetation
  Class 4: Medium Vegetation
  Class 5: High Vegetation
  Class 6: Building
  ...

依赖: laspy, numpy
"""

import numpy as np
import laspy


def filter_by_classification(
    las: laspy.LasData,
    ground_class: int = 2,
    vegetation_class: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """根据分类标签分离地面点和植被点

    从 LAS 数据中按 classification 字段筛选出地面点和植被/作物点，
    返回各自的三维坐标数组。

    Args:
        las: laspy 读取的 LAS 数据对象
        ground_class: 地面点的分类值，LAS 标准中 Class 2 = Ground
        vegetation_class: 植被点的分类值，默认为 Class 1 (Unclassified)
                         农田场景下未分类点通常是作物

    Returns:
        (ground_pts, veg_pts) 元组:
            ground_pts: shape (M, 3) 的地面点坐标
            veg_pts:    shape (N, 3) 的植被/作物点坐标
    """
    # 创建布尔掩码分别标记地面和植被
    ground_mask = las.classification == ground_class
    veg_mask = las.classification == vegetation_class

    # 提取所有点的 XYZ 坐标，shape (总点数, 3)
    xyz = np.vstack([las.x, las.y, las.z]).T

    # 根据掩码分别返回地面点和植被点
    return xyz[ground_mask], xyz[veg_mask]
