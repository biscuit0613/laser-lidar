# crop_height — 农业点云作物株高分析工具包
#
# 对农田激光雷达扫描得到的 LAS 点云文件进行处理，
# 通过构建 DTM/DSM/CHM 确定作物株高，并支持可视化与导出。
#
# 主要模块:
#   pipeline      — 主流程编排 (CropHeightAnalyzer)
#   las_reader    — LAS 文件读取与元数据提取
#   ground_filter — 地面点/植被点分离
#   dtm           — 数字地形模型插值
#   dsm_chm       — 数字表面模型与冠层高度模型
#   quadrat       — 样方统计分析
#   rgb_analysis  — RGB 颜色与植被覆盖度分析
#   export        — GeoTIFF 导出
#   visualize     — 结果可视化
