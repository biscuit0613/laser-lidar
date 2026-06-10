#!/usr/bin/env python3
"""
MCP (Model Context Protocol) 服务器 — 作物株高分析服务

为 LLM (大语言模型) 提供点云分析工具，支持：
  - 单文件株高分析
  - 多文件批量对比
  - CHM 导出为 GeoTIFF
  - LAS 文件元数据查询

启动方式:
  1. stdio 模式 (调试):
     laser-lidar-mcp --transport stdio

  2. SSE 模式 (生产部署):
     laser-lidar-mcp --host 0.0.0.0 --port 8080

环境变量:
  HOST: 监听地址 (默认 0.0.0.0)
  PORT: 监听端口 (默认 8080)
"""

import argparse
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .pipeline import CropHeightAnalyzer
from .las_reader import get_las_info

# ── MCP 服务器实例 ─────────────────────────────────────────────
mcp = FastMCP(
    "laser-lidar",
    instructions=(
        "Agricultural LiDAR crop height analysis service. "
        "Process LAS point cloud files to determine crop/plant height. "
        "Requires files with ASPRS Classification: Class 2 = Ground, Class 1 = Vegetation."
    ),
)


# ── Tool: 获取 LAS 文件信息 ────────────────────────────────────
@mcp.tool(
    name="get_las_info",
    description=(
        "Get metadata and classification summary of a LAS point cloud file. "
        "Returns point count, coordinate bounds, CRS, classification distribution, "
        "and available fields. Does NOT perform full height analysis."
    ),
)
async def get_las_info_tool(file_path: str) -> dict:
    """
    获取 LAS 文件的基础元数据信息。

    Args:
        file_path: 绝对路径或相对于工作目录的 LAS 文件路径
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    try:
        info = get_las_info(str(path))
        return {
            "file": info.path,
            "point_count": info.point_count,
            "bounds": info.bounds,
            "crs": info.crs,
            "classifications": info.classifications,
            "has_rgb": info.has_rgb,
            "fields": info.fields,
        }
    except Exception as e:
        return {"error": f"Failed to read LAS file: {e}"}


# ── Tool: 单文件株高分析 ──────────────────────────────────────
@mcp.tool(
    name="analyze_crop_height",
    description=(
        "Analyze crop/plant height from a LAS point cloud file. "
        "Processes ground vs vegetation points to compute the Canopy Height Model (CHM). "
        "Returns height statistics (mean, median, P90, P95), quadrat-based spatial analysis, "
        "and RGB vegetation indices if available. "
        "Use this for detailed plot-level crop height assessment."
    ),
)
async def analyze_crop_height_tool(
    file_path: str,
    resolution: float = 0.25,
) -> dict:
    """
    对单个 LAS 文件执行作物株高分析。

    Args:
        file_path: LAS 点云文件路径
        resolution: 分析网格分辨率，单位米 (默认 0.25，即每平方米 4 格)
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    if resolution <= 0:
        return {"error": "Resolution must be positive"}

    try:
        analyzer = CropHeightAnalyzer(str(path), resolution=resolution)
        analyzer.run()
    except Exception as e:
        return {"error": f"Analysis failed: {e}"}

    # 组装结果
    result = {
        "file": str(path),
        "resolution": resolution,
        "point_count": analyzer.info.point_count,
        "classification": dict(analyzer.info.classifications),
        "chm_statistics": analyzer.stats,
    }

    # 样方分析 (0.5m × 0.5m 区块，如用户需要更详细可调参数)
    quadrats = analyzer.quadrat(block_size=2)
    if quadrats:
        result["quadrat_analysis"] = {
            "block_size_cells": 2,
            "block_size_meters": round(resolution * 2, 2),
            "blocks": quadrats,
            "summary": {
                "total_blocks": len(quadrats),
                "mean_range": {
                    "min": round(min(q["mean"] for q in quadrats), 4),
                    "max": round(max(q["mean"] for q in quadrats), 4),
                },
            },
        }

    # RGB 颜色分析
    result["rgb_analysis"] = analyzer.rgb_analysis()

    return result


# ── Tool: 多文件批量比较 ──────────────────────────────────────
@mcp.tool(
    name="batch_compare",
    description=(
        "Compare crop height statistics across multiple LAS files. "
        "Useful for comparing different field plots, treatments, or time points. "
        "Returns a summary table of mean, median, P90, and P95 heights per file."
    ),
)
async def batch_compare_tool(
    file_paths: list[str],
    resolution: float = 0.25,
) -> dict:
    """
    批量比较多个 LAS 文件的株高统计结果。

    Args:
        file_paths: LAS 文件路径列表
        resolution: 分析网格分辨率，单位米 (默认 0.25)
    """
    if not file_paths:
        return {"error": "No file paths provided"}

    results = []
    errors = []
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            errors.append({"file": fp, "error": "File not found"})
            continue

        try:
            analyzer = CropHeightAnalyzer(str(path), resolution=resolution)
            analyzer.run()
            stats = analyzer.stats
            results.append({
                "file": str(path),
                "point_count": analyzer.info.point_count,
                "ground_points": len(analyzer.ground_pts),
                "vegetation_points": len(analyzer.veg_pts),
                "chm_cells": stats.get("count", 0),
                "mean_height": stats.get("mean"),
                "median_height": stats.get("median"),
                "p90_height": stats.get("p90"),
                "p95_height": stats.get("p95"),
                "min_height": stats.get("min"),
                "max_height": stats.get("max"),
                "std_height": stats.get("std"),
            })
        except Exception as e:
            errors.append({"file": fp, "error": str(e)})

    return {
        "files_analyzed": len(results),
        "files_failed": len(errors),
        "resolution": resolution,
        "results": results,
        "errors": errors if errors else None,
    }


# ── Tool: 导出 CHM 为 GeoTIFF ─────────────────────────────────
@mcp.tool(
    name="export_geotiff",
    description=(
        "Export the Canopy Height Model (CHM) as a GeoTIFF raster file. "
        "The output file can be opened in GIS software such as QGIS or ArcGIS. "
        "Requires an absolute output_path."
    ),
)
async def export_geotiff_tool(
    file_path: str,
    output_path: str,
    resolution: float = 0.25,
) -> dict:
    """
    将分析生成的 CHM 导出为 GeoTIFF 栅格文件。

    Args:
        file_path: 输入的 LAS 点云文件路径
        output_path: 输出的 .tif 文件路径（必须为绝对路径）
        resolution: 分析网格分辨率，单位米 (默认 0.25)
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"Input file not found: {file_path}"}

    out = Path(output_path)
    if out.is_dir():
        return {"error": f"Output path is a directory: {output_path}"}

    try:
        analyzer = CropHeightAnalyzer(str(path), resolution=resolution)
        analyzer.run()
        result = analyzer.export_geotiff(str(out))
        return {
            "success": True,
            "output": result,
            "file_size_bytes": out.stat().st_size,
        }
    except ImportError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Export failed: {e}"}


# ── 服务器入口 ─────────────────────────────────────────────────
def main():
    """解析命令行参数并启动 MCP 服务器"""
    parser = argparse.ArgumentParser(
        description="laser-lidar MCP Server — 作物株高点云分析服务"
    )
    parser.add_argument(
        "--host", default=None,
        help="监听地址 (默认: 0.0.0.0, 可从环境变量 HOST 读取)"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="监听端口 (默认: 8080, 可从环境变量 PORT 读取)"
    )
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="sse",
        help="传输方式: stdio (本地CLI) 或 sse (HTTP远程) [默认: sse]"
    )
    args = parser.parse_args()

    # 从环境变量或命令行参数读取配置
    host = args.host or os.environ.get("HOST", "0.0.0.0")
    port = args.port or int(os.environ.get("PORT", "8080"))

    if args.transport == "stdio":
        print("Starting MCP server in stdio mode...", file=sys.stderr)
        mcp.run(transport="stdio")
    else:
        print(f"Starting MCP server in SSE mode on {host}:{port}...", file=sys.stderr)
        print(f"  SSE endpoint: http://{host}:{port}/sse", file=sys.stderr)
        print(f"  Messages:      POST http://{host}:{port}/messages", file=sys.stderr)
        print(f"  Health:        GET  http://{host}:{port}/health", file=sys.stderr)

        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse

        async def health(request):
            return JSONResponse({"status": "ok", "service": "laser-lidar mcp"})

        app = mcp.sse_app()
        app.router.routes.append(Route("/health", endpoint=health))

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )


if __name__ == "__main__":
    main()
