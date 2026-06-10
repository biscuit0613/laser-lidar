"""可视化模块

生成包含 6 个子图的综合分析图，直观展示点云分类、DTM、DSM、CHM 分布：
  A. 点云俯视图（按分类着色）
  B. 数字地形模型 DTM
  C. 数字表面模型 DSM
  D. 冠层高度模型 CHM 热力图
  E. CHM 株高直方图
  F. 统计信息面板

依赖: matplotlib, numpy
"""

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from mpl_toolkits.axes_grid1 import make_axes_locatable

from .pipeline import CropHeightAnalyzer


def plot_crop_height_summary(
    analyzer: CropHeightAnalyzer,
    output_path: str = 'crop_height_analysis.png',
    dpi: int = 150,
):
    """绘制作物株高分析综合图

    生成 2×3 的六宫格图，全面展示分析结果。

    Args:
        analyzer: 已执行 run() 的 CropHeightAnalyzer 实例
        output_path: 输出图片路径，默认 crop_height_analysis.png
        dpi: 输出图片 DPI，默认 150

    Returns:
        输出图片路径
    """
    fig, axes = plt.subplots(2, 3, figsize=(18, 20))

    # 从分析器获取数据
    ground = analyzer.ground_pts
    veg = analyzer.veg_pts
    chm = analyzer.chm
    dtm = analyzer.dtm
    dsm = analyzer.dsm
    x_grid = analyzer.x_grid
    y_grid = analyzer.y_grid
    stats = analyzer.stats

    # 统一的颜色和标题样式
    font_color = '#2c3e50'
    title_font = {'fontsize': 13, 'fontweight': 'bold', 'color': font_color}

    # ==== 子图 A: 点云俯视图（按分类着色） ====
    ax = axes[0, 0]
    if ground is not None and veg is not None:
        ax.scatter(
            ground[:, 0], ground[:, 1],
            c='#8B4513', s=8, alpha=0.7,
            label=f'ground points ({len(ground):,})', edgecolors='none'
        )
        ax.scatter(
            veg[:, 0], veg[:, 1],
            c='#2ECC71', s=8, alpha=0.7,
            label=f'vegetation points ({len(veg):,})', edgecolors='none'
        )
    ax.set_xlabel('Easting (m)', fontsize=10)
    ax.set_ylabel('Northing (m)', fontsize=10)
    ax.set_title('A. Point Cloud Classification(bird eye view)', **title_font)
    ax.legend(fontsize=8, markerscale=0.8, loc='upper left')
    ax.set_aspect('equal')

    # 计算统一的坐标范围供后续子图使用
    extent = [x_grid[0, 0], x_grid[0, -1], y_grid[-1, 0], y_grid[0, 0]]

    # ==== 子图 B: DTM 地形模型 ====
    ax = axes[0, 1]
    if dtm is not None:
        im = ax.imshow(dtm, extent=extent, origin='upper', cmap='terrain', aspect='auto')
        divider = make_axes_locatable(ax)
        cax = divider.append_axes('right', size='5%', pad=0.05)
        plt.colorbar(im, cax=cax, label='Elevation (m)')
    ax.set_xlabel('Easting (m)', fontsize=10)
    ax.set_ylabel('Northing (m)', fontsize=10)
    ax.set_title('B. Digital Terrain Model (DTM)', **title_font)

    # ==== 子图 C: DSM 表面模型 ====
    ax = axes[0, 2]
    if dsm is not None:
        im = ax.imshow(dsm, extent=extent, origin='upper', cmap='viridis', aspect='auto')
        divider = make_axes_locatable(ax)
        cax = divider.append_axes('right', size='5%', pad=0.05)
        plt.colorbar(im, cax=cax, label='Elevation (m)')
    ax.set_xlabel('Easting (m)', fontsize=10)
    ax.set_ylabel('Northing (m)', fontsize=10)
    ax.set_title('C. Digital Surface Model (DSM)', **title_font)

    # ==== 子图 D: CHM 株高热力图 ====
    ax = axes[1, 0]
    if chm is not None:
        vmin, vmax = 0, max(0.3, np.nanmax(chm))
        im = ax.imshow(
            chm, extent=extent, origin='upper', cmap='YlGn',
            norm=Normalize(vmin=vmin, vmax=vmax), aspect='auto'
        )
        divider = make_axes_locatable(ax)
        cax = divider.append_axes('right', size='5%', pad=0.05)
        plt.colorbar(im, cax=cax, label='Crop Height (m)')
    ax.set_xlabel('Easting (m)', fontsize=10)
    ax.set_ylabel('Northing (m)', fontsize=10)
    ax.set_title('D. Canopy Height Model (CHM)', **title_font)

    # ==== 子图 E: CHM 株高分布直方图 ====
    ax = axes[1, 1]
    if chm is not None:
        valid = chm[~np.isnan(chm) & (chm > 0.01)]
        if len(valid) > 0:
            ax.hist(valid, bins=30, color='#2ECC71', edgecolor='white', alpha=0.85)
            # 标记中位线和均值线
            ax.axvline(
                np.median(valid), color='#E74C3C',
                linestyle='--', linewidth=2,
                label=f"Median: {np.median(valid):.3f}m"
            )
            ax.axvline(
                np.mean(valid), color='#3498DB',
                linestyle=':', linewidth=2,
                label=f"Mean: {np.mean(valid):.3f}m"
            )
            ax.legend(fontsize=8)
            ax.set_xlabel('Crop Height (m)', fontsize=10)
            ax.set_ylabel('Number of Pixels (bins)', fontsize=10)
    ax.set_title('E. Height Distribution Histogram', **title_font)

    # ==== 子图 F: 统计信息面板 ====
    ax = axes[1, 2]
    ax.axis('off')  # 隐藏坐标轴，纯文本面板

    # 构建信息行
    info_lines = [
        f"file path: {Path(analyzer.las_path).name}",
        f"total points: {analyzer.info.point_count:,}",
        f"grid: {analyzer.chm.shape[1]}×{analyzer.chm.shape[0]} (@{analyzer.resolution}m)",
        "",
        "--- Height Statistics (CHM) ---",
        f"mean: {stats.get('mean', 'N/A'):} m",
        f"median: {stats.get('median', 'N/A'):} m",
        f"P90: {stats.get('p90', 'N/A'):} m",
        f"P95: {stats.get('p95', 'N/A'):} m",
        f"min: {stats.get('min', 'N/A'):} m",
        f"max: {stats.get('max', 'N/A'):} m",
        f"std: {stats.get('std', 'N/A'):} m",
        "",
        "--- Point Cloud Classification ---",
        f"ground points: {len(ground) if ground is not None else 0:,}",
        f"vegetation points: {len(veg) if veg is not None else 0:,}",
    ]

    # 如果有 RGB 数据，追加颜色分析结果
    if analyzer.rgb is not None:
        rgban = analyzer.rgb_analysis()
        if rgban.get('has_rgb'):
            info_lines += [
                "",
                "--- RGB Color Analysis ---",
                f"Green Band Ratio: {rgban['green_ratio']:.3f}",
                f"Vegetation Cover Percentage: {rgban['vegetation_cover']['coverage']:.1f}%",
            ]

    # 逐行渲染文本面板
    y_pos = 0.95
    for line in info_lines:
        if line.startswith('---'):
            # 标题行加粗
            ax.text(0.05, y_pos, line, fontsize=10, fontweight='bold',
                    color=font_color, transform=ax.transAxes)
        else:
            ax.text(0.05, y_pos, line, fontsize=10, color=font_color,
                    transform=ax.transAxes, fontfamily='monospace')
        y_pos -= 0.045

    # 总标题
    plt.suptitle(
        f'Crop Height Lidar Analysis — {Path(analyzer.las_path).name}',
        fontsize=16, fontweight='bold', color=font_color, y=0.98
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close()
    return output_path
