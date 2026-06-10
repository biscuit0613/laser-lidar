"""数据导出模块

将处理结果导出为标准 GIS 格式，方便在 ArcGIS、QGIS 等软件中使用。

支持格式:
- GeoTIFF: 带地理坐标的 CHM 栅格文件

依赖: rasterio (可选)
"""

import numpy as np


def export_chm_to_geotiff(
    chm: np.ndarray,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
    crs_wkt: str,
    output_path: str,
):
    """将 CHM 导出为 GeoTIFF 栅格文件

    GeoTIFF 是 GIS 领域标准栅格格式，包含地理坐标和投影信息，
    可在 QGIS、ArcGIS 等软件中直接打开和分析。

    Args:
        chm: shape (ny, nx) 的 CHM 数组
        x_edges: X 方向网格边界（用于计算仿射变换参数）
        y_edges: Y 方向网格边界
        crs_wkt: 坐标参考系的 WKT 字符串
        output_path: 输出 .tif 文件路径

    Returns:
        输出文件路径

    Raises:
        ImportError: 未安装 rasterio 时抛出
    """
    try:
        import rasterio
        from rasterio.transform import from_origin
    except ImportError:
        raise ImportError(
            "导出 GeoTIFF 需要 rasterio 库。安装命令: uv pip install rasterio"
        )

    # 计算仿射变换参数：左上角坐标 + 像元尺寸
    transform = from_origin(
        x_edges[0],         # 左上角 X（东向）
        y_edges[-1],        # 左上角 Y（北向）
        x_edges[1] - x_edges[0],  # X 方向分辨率
        y_edges[1] - y_edges[0],  # Y 方向分辨率
    )

    # GeoTIFF 配置文件
    profile = {
        'driver': 'GTiff',
        'height': chm.shape[0],
        'width': chm.shape[1],
        'count': 1,             # 单波段
        'dtype': chm.dtype,
        'crs': crs_wkt,         # 坐标参考系
        'transform': transform,  # 地理配准参数
        'nodata': np.nan,       # 空值标记
        'compress': 'lzw',      # LZW 无损压缩，减小文件体积
    }

    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(chm, 1)       # 写入第一个波段

    return output_path
