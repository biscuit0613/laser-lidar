#!/usr/bin/env python3
"""批量分析入口脚本

扫描当前目录下所有 LAS 文件，依次执行株高分析并生成可视化结果。

用法:
    python run_analysis.py

输出:
    - 每个 LAS 文件对应的分析图 {filename}_analysis.png
    - 汇总结果 analysis_results.json
"""

import sys
import json
from pathlib import Path

# 确保能找到本项目模块
sys.path.insert(0, str(Path(__file__).parent))
from crop_height.pipeline import CropHeightAnalyzer
from crop_height.visualize import plot_crop_height_summary


def main():
    """主流程：扫描 LAS → 逐个分析 → 汇总结果"""
    # 查找当前目录下所有 .las 文件
    las_dir = Path(__file__).parent
    las_files = sorted(las_dir.glob('*.las'))

    if not las_files:
        print("未找到 .las 文件")
        return

    print(f"找到 {len(las_files)} 个 LAS 文件")

    all_results = {}
    for las_path in las_files:
        print(f"\n{'='*60}")
        print(f"正在处理: {las_path.name}")
        print(f"{'='*60}")

        # 初始化分析器，分辨率 0.25m
        analyzer = CropHeightAnalyzer(str(las_path), resolution=0.25)
        analyzer.run()

        # 输出株高统计
        stats = analyzer.stats
        print(f"  总点数: {analyzer.info.point_count:,}")
        print(f"  地面点: {len(analyzer.ground_pts):,} | 植被点: {len(analyzer.veg_pts):,}")
        print(f"  CHM 有效像元: {stats.get('count', 0)}")
        print(f"  平均株高: {stats.get('mean', 'N/A')} m")
        print(f"  中位株高: {stats.get('median', 'N/A')} m")
        print(f"  P90: {stats.get('p90', 'N/A')} m")
        print(f"  P95: {stats.get('p95', 'N/A')} m")

        # RGB 分析
        if analyzer.rgb is not None:
            rgb_stats = analyzer.rgb_analysis()
            print(f"  绿光占比: {rgb_stats['green_ratio']:.3f}")
            print(f"  植被覆盖度: {rgb_stats['vegetation_cover']['coverage']:.1f}%")

        # 样方分析（每 2 个网格一组，即 0.5×0.5m）
        quadrats = analyzer.quadrat(block_size=2)
        print(f"  样方数 (>1cm): {len(quadrats)}")
        if quadrats:
            heights = [q['mean'] for q in quadrats]
            print(f"  样方均值范围: {min(heights):.3f} ~ {max(heights):.3f} m")

        # 生成可视化
        out_path = las_dir / f"{las_path.stem}_analysis.png"
        plot_crop_height_summary(analyzer, str(out_path))
        print(f"  可视化已保存: {out_path.name}")

        all_results[las_path.name] = stats

    # 汇总输出
    print(f"\n{'='*60}")
    print("汇总对比")
    print(f"{'='*60}")
    print(f"{'文件名':<20} {'均高':>8} {'中位':>8} {'P90':>8} {'P95':>8} {'像元':>8}")
    print("-" * 60)
    for fname, s in all_results.items():
        print(
            f"{fname:<20} {s.get('mean', '-'):>8} {s.get('median', '-'):>8} "
            f"{s.get('p90', '-'):>8} {s.get('p95', '-'):>8} {s.get('count', '-'):>8}"
        )

    # 保存 JSON 结果
    with open(las_dir / 'analysis_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\n结果已保存到 analysis_results.json")


if __name__ == '__main__':
    main()
