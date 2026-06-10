#!/usr/bin/env python3
"""
MCP (Model Context Protocol) 服务器 — 作物株高分析服务

FarmOS 调度中枢通过 Streamable HTTP 协议对接本服务。
LLM 通过 MCP 工具调用实现点云分析与株高测量。

启动方式:
  生产部署:
    uvicorn crop_height.mcp_server:app --host 0.0.0.0 --port 8000

  本地调试 (备用):
    python -m crop_height.mcp_server --port 8000

Inspector 调试:
  npx @modelcontextprotocol/inspector
  → Transport: Streamable HTTP
  → URL: http://localhost:8000/mcp
"""

import os
import sys
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .pipeline import CropHeightAnalyzer
from .las_reader import get_las_info as get_las_file_info

# ── MCP 服务器实例 ─────────────────────────────────────────────
mcp = FastMCP(
    "laser-lidar",
    instructions=(
        "Agricultural LiDAR crop/plant height analysis service. "
        "Process LAS point cloud files to determine crop height. "
        "Files must contain ASPRS Classification: Class 2 (Ground) and Class 1 (Vegetation)."
    ),
)


# ── 健康检查 ──────────────────────────────────────────────────
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "laser-lidar mcp"})


# ── Tool: 获取 LAS 文件信息 ────────────────────────────────────
@mcp.tool(
    description=(
        "获取 LAS 点云文件的元数据信息。返回点总数、坐标范围、坐标系、"
        "各分类别点数、是否包含RGB字段等。不执行株高分析，仅预览文件结构。"
    ),
)
async def get_las_info(
    file_path: Annotated[str, "LAS 点云文件的绝对路径或相对于工作目录的路径"],
) -> dict:
    """
    获取 LAS 文件的基础元数据信息。
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"文件不存在: {file_path}"}

    try:
        info = get_las_file_info(str(path))
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
        return {"error": f"读取 LAS 文件失败: {e}"}


# ── Tool: 单文件株高分析 ──────────────────────────────────────
@mcp.tool(
    description=(
        "对单个 LAS 点云文件执行作物株高分析。自动分离地面点 (Class 2) "
        "与植被点 (Class 1)，构建冠层高度模型 (CHM)，返回株高统计指标 "
        "(均值、中位数、P90、P95)、样方空间分布以及 RGB 植被指数。"
    ),
)
async def analyze_crop_height(
    file_path: Annotated[str, "LAS 点云文件的路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，值越小精度越高但计算量越大。推荐 0.25"] = 0.25,
) -> dict:
    """
    对单个 LAS 文件执行作物株高分析。
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"文件不存在: {file_path}"}
    if resolution <= 0:
        return {"error": "分辨率必须大于 0"}

    try:
        analyzer = CropHeightAnalyzer(str(path), resolution=resolution)
        analyzer.run()
    except Exception as e:
        return {"error": f"分析失败: {e}"}

    # 组装基础结果
    result = {
        "file": str(path),
        "resolution": resolution,
        "point_count": analyzer.info.point_count,
        "classification": dict(analyzer.info.classifications),
        "chm_statistics": analyzer.stats,
    }

    # 样方分析 (0.5m × 0.5m 区块)
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
    description=(
        "批量比较多个 LAS 文件的株高统计结果。适用于对比不同地块、"
        "不同处理或不同时相的作物长势。返回每个文件的均值、中位数、P90、P95 等对比表。"
    ),
)
async def batch_compare(
    file_paths: Annotated[list[str], "需要比较的 LAS 文件路径列表，至少传入一个路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，默认 0.25"] = 0.25,
) -> dict:
    """
    批量比较多个 LAS 文件的株高统计结果。
    """
    if not file_paths:
        return {"error": "未提供文件路径"}

    results = []
    errors = []
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            errors.append({"file": fp, "error": "文件不存在"})
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
    description=(
        "将分析生成的冠层高度模型 (CHM) 导出为 GeoTIFF 栅格文件。"
        "输出文件可在 QGIS、ArcGIS 等 GIS 软件中打开。输出路径必须为绝对路径。"
    ),
)
async def export_geotiff(
    file_path: Annotated[str, "输入的 LAS 点云文件路径"],
    output_path: Annotated[str, "输出的 .tif 文件绝对路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，默认 0.25"] = 0.25,
) -> dict:
    """
    将分析生成的 CHM 导出为 GeoTIFF 栅格文件。
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"输入文件不存在: {file_path}"}

    out = Path(output_path)
    if out.is_dir():
        return {"error": f"输出路径是一个目录: {output_path}"}

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
        return {"error": f"导出失败: {e}"}


# ── CORS 中间件 ───────────────────────────────────────────────
# 开发调试阶段开启，生产环境如需限制来源请修改 allow_origins
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "mcp-protocol-version",
            "mcp-session-id",
            "Authorization",
            "Content-Type",
        ],
        expose_headers=["mcp-session-id"],
    )
]

# ── ASGI 应用 (供 uvicorn 直接加载) ───────────────────────────
app = mcp.http_app(path="/mcp", middleware=middleware)


# ── CLI 入口 (备用启动方式) ────────────────────────────────────
def main():
    """命令行启动入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="laser-lidar MCP Server — 作物株高点云分析服务"
    )
    parser.add_argument(
        "--host", default=None,
        help="监听地址 (默认 0.0.0.0，可从环境变量 HOST 读取)"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="监听端口 (默认 8000，可从环境变量 PORT 读取)"
    )
    args = parser.parse_args()

    host = args.host or os.environ.get("HOST", "0.0.0.0")
    port = args.port or int(os.environ.get("PORT", "8000"))

    import uvicorn
    uvicorn.run(
        "crop_height.mcp_server:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
