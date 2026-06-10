# laser-lidar

农业激光雷达点云处理 — 作物株高自动分析

根据农田 LiDAR 扫描的 LAS 点云，通过构建 DTM/DSM/CHM 确定作物株高。

## 环境准备

```bash
uv sync
source .venv/bin/activate
```

## 测试程序（快速验证处理效果）

### 方法一：独立脚本（推荐）

```bash
source .venv/bin/activate
python run_analysis.py
```

自动扫描当前目录下所有 `.las` 文件，依次输出株高统计并生成可视化图 `<文件名>_analysis.png`。

### 方法二：Python API

```python
source .venv/bin/activate
```

```python
from crop_height.pipeline import CropHeightAnalyzer

a = CropHeightAnalyzer("las20230424_1.las", resolution=0.25).run()
print(a.stats)
```

## 启动 MCP 服务器

### SSE 模式（远程部署，给其他大模型用）

```bash
source .venv/bin/activate

# 默认端口 8080
laser-lidar-mcp

# 指定地址和端口
laser-lidar-mcp --host 0.0.0.0 --port 8080
```

端点 | 说明
---|---
`GET  /sse` | MCP SSE 连接端点
`POST /messages` | MCP 消息端点
`GET  /health` | 健康检查

### stdio 模式（本地调试）

```bash
laser-lidar-mcp --transport stdio
```

## 项目结构

```
crop_height/         # 核心处理包
  pipeline.py        # 主流程编排 (CropHeightAnalyzer)
  las_reader.py      # LAS 文件读取与元数据
  ground_filter.py   # 地面/植被点分离
  dtm.py             # 数字地形模型插值
  dsm_chm.py         # 数字表面模型与冠层高度模型
  quadrat.py         # 样方分析
  rgb_analysis.py    # RGB 颜色与植被覆盖度
  export.py          # GeoTIFF 导出
  visualize.py       # 结果可视化
  mcp_server.py      # MCP 服务器
```
