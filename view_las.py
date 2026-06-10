# view_las_pyvista.py
import pyvista as pv
import laspy
import numpy as np

print("正在加载点云文件...")
las = laspy.read("las20230424_1.las")
points = np.vstack((las.x, las.y, las.z)).transpose()
print(f"加载完成，共 {len(points):,} 个点。")

# 创建 PyVista 点云对象并添加高程作为标量数据
point_cloud = pv.PolyData(points)
point_cloud["Elevation"] = points[:, 2]

print("正在启动可视化窗口...")
# 创建绘图器并设置背景色
plotter = pv.Plotter()
plotter.background_color = 'black'
# 添加点云，使用 'viridis' 颜色映射，点大小设为2
plotter.add_mesh(point_cloud, scalars="Elevation", cmap="viridis", point_size=2, render_points_as_spheres=False)
# 显示坐标系和颜色条
plotter.show_grid(color='white')
plotter.show()
