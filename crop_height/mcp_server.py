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

# LAS 文件数据根目录。网页端传相对路径时会拼接此路径。
# 可通过环境变量 LAS_DATA_DIR 配置，默认 None（使用传入的原始路径）。
LAS_DATA_DIR = os.environ.get("LAS_DATA_DIR") or None


def _resolve_path(file_path: str) -> Path:
    """解析文件路径：如果 LAS_DATA_DIR 设置了且传入相对路径，则拼接"""
    p = Path(file_path)
    if p.is_absolute():
        return p
    if LAS_DATA_DIR:
        return Path(LAS_DATA_DIR) / p
    return p.resolve()


def _cm(val: float | None) -> float | None:
    """米转厘米，保留 2 位小数"""
    if val is None:
        return None
    return round(val * 100, 2)


def _run_analyzer(file_path: str, resolution: float):
    """解析路径并运行分析器，返回 (path, analyzer) 或 (path, error_dict)"""
    path = _resolve_path(file_path)
    if not path.exists():
        return None, {
            "error": f"文件不存在: {file_path}",
            "hint": "若配置了 LAS_DATA_DIR，文件应放在该目录下；否则请使用绝对路径。",
        }
    if resolution <= 0:
        return None, {"error": "分辨率必须大于 0"}
    try:
        from .pipeline import CropHeightAnalyzer
        analyzer = CropHeightAnalyzer(str(path), resolution=resolution)
        analyzer.run()
        return path, analyzer
    except Exception as e:
        return None, {"error": f"分析失败: {e}"}


from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

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
    file_path: Annotated[str, "LAS 点云文件路径。支持绝对路径；若配置了环境变量 LAS_DATA_DIR，也支持相对路径"],
) -> dict:
    """
    获取 LAS 文件的基础元数据信息。
    """
    path = _resolve_path(file_path)
    if not path.exists():
        hint = f"若配置了 LAS_DATA_DIR，文件应放在该目录下；否则请使用绝对路径。"
        return {"error": f"文件不存在: {file_path}", "hint": hint}

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
        "(均值、中位数、P90、P95、Min、Max、Std，单位均为厘米) 及 CHM 像元数。"
        "如需样方空间分布，请使用 analyze_quadrat 工具；"
        "如需 RGB 植被指数，请使用 analyze_rgb 工具。"
    ),
)
async def analyze_crop_height(
    file_path: Annotated[str, "LAS 点云文件路径。支持绝对路径；若配置了环境变量 LAS_DATA_DIR，也支持相对路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，值越小精度越高但计算量越大。推荐 0.25"] = 0.25,
) -> dict:
    """
    对单个 LAS 文件执行作物株高分析，返回 CHM 统计指标（单位厘米）。
    """
    path, result = _run_analyzer(file_path, resolution)
    if result is None:
        return result

    analyzer = result
    stats = analyzer.stats
    return {
        "file": str(path),
        "resolution": resolution,
        "point_count": analyzer.info.point_count,
        "classification": dict(analyzer.info.classifications),
        "chm_statistics": {
            "count": stats.get("count"),
            "min": _cm(stats.get("min")),
            "max": _cm(stats.get("max")),
            "mean": _cm(stats.get("mean")),
            "median": _cm(stats.get("median")),
            "std": _cm(stats.get("std")),
            "p25": _cm(stats.get("p25")),
            "p75": _cm(stats.get("p75")),
            "p90": _cm(stats.get("p90")),
            "p95": _cm(stats.get("p95")),
        },
    }


# ── Tool: 样方空间分布分析 ────────────────────────────────────
@mcp.tool(
    description=(
        "对 LAS 点云文件进行样方 (quadrat) 空间分布分析。将 CHM 网格划分为 "
        "等大区块，返回每个区块内的株高均值、中位数、最大值、P90（单位均为厘米），"
        "用于发现田块内部的空间变异。"
    ),
)
async def analyze_quadrat(
    file_path: Annotated[str, "LAS 点云文件路径。支持绝对路径；若配置了 LAS_DATA_DIR，也支持相对路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，推荐 0.25"] = 0.25,
    block_size: Annotated[int, "每个样方包含的网格数，默认 2（即 0.5×0.5m 区块）"] = 2,
) -> dict:
    """
    对 LAS 文件进行样方空间分布分析，返回株高值（单位厘米）。
    """
    path, result = _run_analyzer(file_path, resolution)
    if result is None:
        return result

    analyzer = result
    quadrats = analyzer.quadrat(block_size=block_size)
    if not quadrats:
        return {
            "file": str(path),
            "resolution": resolution,
            "block_size_cells": block_size,
            "block_size_meters": round(resolution * block_size, 2),
            "blocks": [],
            "summary": {"total_blocks": 0},
        }

    blocks_cm = []
    for q in quadrats:
        blocks_cm.append({
            "row": q["row"],
            "col": q["col"],
            "x_center": q["x_center"],
            "y_center": q["y_center"],
            "count": q["count"],
            "mean": _cm(q["mean"]),
            "median": _cm(q["median"]),
            "max": _cm(q["max"]),
            "p90": _cm(q["p90"]),
        })

    means = [q["mean"] for q in quadrats]
    return {
        "file": str(path),
        "resolution": resolution,
        "block_size_cells": block_size,
        "block_size_meters": round(resolution * block_size, 2),
        "blocks": blocks_cm,
        "summary": {
            "total_blocks": len(quadrats),
            "mean_range": {
                "min": _cm(min(means)),
                "max": _cm(max(means)),
            },
            "median_mean": _cm(sum(means) / len(means)),
        },
    }


# ── Tool: RGB 植被指数分析 ────────────────────────────────────
@mcp.tool(
    description=(
        "对 LAS 点云文件进行 RGB 颜色分析，估算植被覆盖度和绿色指数。"
        "返回绿光占比 (Green Ratio)、基于绿光阈值的植被覆盖度、"
        "以及过绿指数 (ExG) 的均值和标准差。"
        "仅对包含 RGB 颜色信息的点云文件有效。"
    ),
)
async def analyze_rgb(
    file_path: Annotated[str, "LAS 点云文件路径。支持绝对路径；若配置了 LAS_DATA_DIR，也支持相对路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，推荐 0.25"] = 0.25,
    green_threshold: Annotated[float, "绿光占比阈值，用于判定植被点，默认 0.35"] = 0.35,
) -> dict:
    """
    对 LAS 文件进行 RGB 植被指数分析。
    """
    path, result = _run_analyzer(file_path, resolution)
    if result is None:
        return result

    analyzer = result
    if analyzer.rgb is None:
        return {
            "file": str(path),
            "has_rgb": False,
            "message": "该 LAS 文件不包含 RGB 颜色信息，无法进行颜色分析。",
        }

    base = analyzer.rgb_analysis()

    from .rgb_analysis import vegetation_cover, excess_green
    veg_custom = vegetation_cover(analyzer.rgb, g_threshold=green_threshold)
    exg = excess_green(analyzer.rgb)

    return {
        "file": str(path),
        "has_rgb": True,
        "green_ratio": base["green_ratio"],
        "vegetation_cover": veg_custom,
        "excess_green": exg,
    }


# ── Tool: 多文件批量比较 ──────────────────────────────────────
@mcp.tool(
    description=(
        "批量比较多个 LAS 文件的株高统计结果。适用于对比不同地块、"
        "不同处理或不同时相的作物长势。返回每个文件的均值、中位数、P90、P95"
        "等指标，单位均为厘米。"
    ),
)
async def batch_compare(
    file_paths: Annotated[list[str], "需要比较的 LAS 文件路径列表，至少传入一个路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，默认 0.25"] = 0.25,
) -> dict:
    """
    批量比较多个 LAS 文件的株高统计结果（单位厘米）。
    """
    if not file_paths:
        return {"error": "未提供文件路径"}

    results = []
    errors = []
    for fp in file_paths:
        path, analyzer_or_error = _run_analyzer(fp, resolution)
        if path is None:
            errors.append({"file": fp, "error": analyzer_or_error.get("error", "未知错误")})
            continue

        analyzer = analyzer_or_error
        stats = analyzer.stats
        results.append({
            "file": str(path),
            "point_count": analyzer.info.point_count,
            "ground_points": len(analyzer.ground_pts),
            "vegetation_points": len(analyzer.veg_pts),
            "chm_cells": stats.get("count", 0),
            "mean_height": _cm(stats.get("mean")),
            "median_height": _cm(stats.get("median")),
            "p90_height": _cm(stats.get("p90")),
            "p95_height": _cm(stats.get("p95")),
            "min_height": _cm(stats.get("min")),
            "max_height": _cm(stats.get("max")),
            "std_height": _cm(stats.get("std")),
        })

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
    file_path: Annotated[str, "输入的 LAS 点云文件路径。支持绝对路径；若配置了 LAS_DATA_DIR，也支持相对路径"],
    output_path: Annotated[str, "输出的 .tif 文件绝对路径"],
    resolution: Annotated[float, "分析网格分辨率，单位米，默认 0.25"] = 0.25,
) -> dict:
    """
    将分析生成的 CHM 导出为 GeoTIFF 栅格文件。
    """
    path = _resolve_path(file_path)
    if not path.exists():
        hint = f"若配置了 LAS_DATA_DIR，文件应放在该目录下；否则请使用绝对路径。"
        return {"error": f"输入文件不存在: {file_path}", "hint": hint}

    out = Path(output_path)
    if out.is_dir():
        return {"error": f"输出路径是一个目录: {output_path}"}

    try:
        from .pipeline import CropHeightAnalyzer
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
