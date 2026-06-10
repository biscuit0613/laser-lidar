from fastmcp import FastMCP
from typing import Annotated

# --- 跨域配置相关 ---
# 在使用 MCP Inspector 等前端调试工具进行跨域连接时需要
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# --- 业务逻辑依赖，根据实际需求添加和删除 ---
from datetime import datetime
import asyncio

# 1. 初始化 MCP 服务实例
# 替换成一个具有实际含义的名称
mcp = FastMCP("demo-server")


# 2. 定义工具 (Tools)
# MCP 工具会自动暴露给 LLM，使其具备调用外部函数的能力。
# 注释和参数类型提示（Type Hints）对于 LLM 正确理解并调用工具至关重要。


@mcp.tool(description="对两个整数进行加法计算（同步示例）")
def add_numbers(
    a: Annotated[int, "第一个加数"],
    b: Annotated[int, "第二个加数"],
) -> int:
    return a + b


@mcp.tool(description="查询指定城市的当前服务器时间（异步/IO密集型示例）")
async def get_server_time(
    city: Annotated[str, "要查询的城市名称"],
) -> dict:
    await asyncio.sleep(0.5)  # 模拟网络延迟
    return {"city": city, "time": datetime.now().isoformat(), "timezone": "UTC+8"}


@mcp.tool(description="对长文本进行截断摘要")
def summarize_text(
    text: Annotated[str, "待摘要的原始文本"],
    max_length: Annotated[int, "摘要最大长度，单位为字符"] = 100,
) -> str:
    return text[:max_length] + ("..." if len(text) > max_length else "")


@mcp.tool(description="根据任务 ID 跟踪后台任务执行进度")
def query_task_status(
    task_id: Annotated[str, "需要查询的任务 ID"],
) -> dict:
    return {
        "task_id": task_id,
        "status": "running",
        "progress": 65,
        "last_update": datetime.now().strftime("%H:%M:%S"),
    }


@mcp.tool(description="生成任务进展 Markdown 报告（返回 Markdown 文本示例）")
def generate_task_report_markdown(
    task_id: Annotated[str, "任务 ID"],
    operator: Annotated[str, "当前执行人名称"],
    progress: Annotated[int, "任务进度百分比，范围 0-100"] = 65,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""# 任务进展报告\n\n- 任务 ID: {task_id}\n- 执行人: {operator}\n- 当前进度: {progress}%\n- 更新时间: {now}\n\n## 建议\n\n1. 若进度低于 80%，请优先排查阻塞环节。\n2. 如需联动调度中枢，请补充任务上下文。\n"""


# ---------------------------------------------------------
# 3. 运行配置：HTTP 传输模式
# ---------------------------------------------------------

# 配置跨域中间件 (CORS)
# 注意：仅在开发调试阶段（如配合 MCP Inspector 使用）开启。
# 生产环境下，将CORS中间件移除
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 调试用，允许所有来源
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

# 创建ASGI实例，供服务器运行使用
# 不需要加入中间件时，可直接使用: app = mcp.http_app()
app = mcp.http_app(middleware=middleware)

# ---------------------------------------------------------
# 4. 启动说明
# ---------------------------------------------------------
# 在当前目录下启动服务：
# 1. 确保已安装 uvicorn：pip install uvicorn
# 2. 确保终端当前路径在包含 demo.py 的目录下
# 3. 运行命令：uvicorn demo:app --host 0.0.0.0 --port 8000
# 4. 一些机器上的环境配置问题可能导致uvicorn的CLI找不到，可以使用以下命令：
#    python -m uvicorn demo:app --host 0.0.0.0 --port 8000
# (注意：将 demo 替换为你想要运行的文件名)
# ---------------------------------------------------------
