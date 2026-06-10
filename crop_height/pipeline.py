"""点云作物株高分析主流程编排模块

CropHeightAnalyzer 是本项目的核心类，编排完整的分析流程：
  1. 读取 LAS 文件 → 2. 分离地面/植被点 → 3. 构建 DTM
  → 4. 构建 DSM → 5. 计算 CHM → 6. 统计与导出

使用示例:
    from crop_height.pipeline import CropHeightAnalyzer

    analyzer = CropHeightAnalyzer("scan.las", resolution=0.25)
    analyzer.run()
    print(analyzer.stats)
    analyzer.export_geotiff("chm.tif")

依赖: numpy, scipy, laspy (由各子模块引入)
"""

import numpy as np
from pathlib import Path

from .las_reader import read_las, get_las_info, extract_points, extract_rgb
from .ground_filter import filter_by_classification
from .dtm import compute_dtm
from .dsm_chm import (
    build_grid, build_dsm, compute_chm, chm_statistics,
)
from .quadrat import quadrat_analysis
from .rgb_analysis import green_ratio, vegetation_cover, excess_green


class CropHeightAnalyzer:
    """作物株高分析器

    封装完整的点云处理流程：从 LAS 文件到株高统计结果。

    Attributes:
        las_path:      LAS 文件路径
        resolution:    分析网格分辨率（米）
        ground_pts:    地面点坐标, shape (M, 3)
        veg_pts:       植被点坐标, shape (N, 3)
        dtm:           数字地形模型, shape (ny, nx)
        dsm:           数字表面模型, shape (ny, nx)
        chm:           冠层高度模型, shape (ny, nx)
        rgb:           RGB 颜色数据, shape (N, 3) 或 None
    """

    def __init__(self, las_path: str | Path, resolution: float = 0.25):
        """初始化分析器

        Args:
            las_path:   LAS 点云文件路径
            resolution: 网格分辨率，单位米。默认 0.25m (每平方米 4 格)
                        分辨率越低分析越快，但会丢失细节。
        """
        self.las_path = str(las_path)
        self.resolution = resolution
        self.las = read_las(self.las_path)
        self.info = get_las_info(self.las_path)

        # 后续由 run() 填充的属性，初始均为 None
        self.ground_pts: np.ndarray | None = None   # 地面点 N×3
        self.veg_pts: np.ndarray | None = None      # 植被点 N×3
        self.x_edges: np.ndarray | None = None      # X 网格边界
        self.y_edges: np.ndarray | None = None      # Y 网格边界
        self.x_grid: np.ndarray | None = None       # X 网格中心
        self.y_grid: np.ndarray | None = None       # Y 网格中心
        self.dtm: np.ndarray | None = None          # 数字地形模型
        self.dsm: np.ndarray | None = None          # 数字表面模型
        self.chm: np.ndarray | None = None          # 冠层高度模型
        self.rgb: np.ndarray | None = None          # RGB 颜色数据

    def run(self):
        """执行完整的株高分析流程

        步骤:
        1. 提取所有点云的三维坐标
        2. 按分类标签分离地面点和植被点
        3. 根据坐标范围构建规则分析网格
        4. 由地面点插值生成 DTM
        5. 由植被点取最大值生成 DSM
        6. DSM - DTM 得到 CHM，负值归零
        7. 提取 RGB 颜色信息

        Returns:
            self，支持链式调用
        """
        # 步骤 1: 提取全部点坐标 (用于后续边界计算)
        xyz = extract_points(self.las)

        # 步骤 2: 按 LAS classification 分离地面和植被
        self.ground_pts, self.veg_pts = filter_by_classification(self.las)

        # 步骤 3: 构建规则网格
        self.x_edges, self.y_edges, self.x_grid, self.y_grid = build_grid(
            self.info.bounds, self.resolution
        )

        # 步骤 4: 地面点插值 → DTM
        self.dtm = compute_dtm(self.ground_pts, self.x_grid, self.y_grid)

        # 步骤 5: 植被点最大值 → DSM
        self.dsm = build_dsm(self.veg_pts, self.x_edges, self.y_edges)
        # 用 DTM 填充 DSM 中没有植被点的空洞区域
        dsm_nan = np.isnan(self.dsm)
        self.dsm[dsm_nan] = self.dtm[dsm_nan]

        # 步骤 6: DSM - DTM → CHM
        self.chm = compute_chm(self.dsm, self.dtm)

        # 步骤 7: 提取 RGB
        self.rgb = extract_rgb(self.las)

        return self

    @property
    def stats(self) -> dict:
        """获取 CHM 统计结果（属性方式访问）

        包含了点数、分辨率、坐标边界等上下文信息。

        Returns:
            统计字典，包含 mean, median, p90, p95 等株高指标
        """
        if self.chm is None:
            return {}
        s = chm_statistics(self.chm)
        s['resolution'] = self.resolution
        s['file'] = self.las_path
        s['bounds'] = self.info.bounds
        s['classifications'] = self.info.classifications
        return s

    def quadrat(self, block_size: int = 2) -> list:
        """进行样方分析

        将 CHM 划分为等大的样方，分别统计每个区域的株高。

        Args:
            block_size: 样方包含的网格数，默认 2。
                        若 resolution=0.25m，则每个样方 0.5×0.5m。

        Returns:
            样方统计列表
        """
        if self.chm is None:
            return []
        return quadrat_analysis(self.chm, self.x_grid, self.y_grid, block_size)

    def rgb_analysis(self) -> dict:
        """执行 RGB 颜色分析

        计算绿光占比、植被覆盖度、过绿指数等指标。

        Returns:
            颜色分析结果字典，无 RGB 时返回 {'has_rgb': False}
        """
        if self.rgb is None:
            return {'has_rgb': False}
        return {
            'has_rgb': True,
            'green_ratio': round(green_ratio(self.rgb), 4),
            'vegetation_cover': vegetation_cover(self.rgb),
            'excess_green': excess_green(self.rgb),
        }

    def export_geotiff(self, output_path: str) -> str:
        """将 CHM 导出为 GeoTIFF

        Args:
            output_path: 输出 .tif 文件路径

        Returns:
            输出文件路径

        Raises:
            RuntimeError: 尚未执行 run() 时抛出
        """
        if self.chm is None:
            raise RuntimeError("请先执行 run() 方法再进行导出")
        from .export import export_chm_to_geotiff
        return export_chm_to_geotiff(
            self.chm, self.x_edges, self.y_edges,
            self.las.header.parse_crs().to_wkt(),
            output_path,
        )
