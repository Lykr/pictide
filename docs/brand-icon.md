# Pictide 图标

正式图标采用用户确认的浪形 P 精修稿：15 段三次贝塞尔曲线，外圈与竖干自然衔接，白色负形沿回卷逐渐收窄；只保留尾尖与内勾尖端的锐度。

- [完整图标](../web/public/icons/pictide.svg)：深色圆角背景、白色符号，用于页头和浏览器图标。
- [透明符号](../web/public/icons/pictide-mark.svg)：相同轮廓，填充使用 currentColor，可直接用矢量编辑器修改。
- 安装图标：apple-touch-icon.png（180px）、pictide-192.png、pictide-512.png；由相同曲线导出，深色不透明底，系统负责外形裁切。

画布为 256×256。完整图标及安装 PNG 将符号围绕画布中心缩放至 80%，使主体落在 maskable 图标的中央安全圆内；透明符号保留精修稿的原始画布与路径。源文件不依赖字体或外部图片。

网页页头、favicon 和 PWA 安装资源统一引用正式版本。缓存标记为 wave-v1；已添加至 iOS 主屏幕的旧图标可能需要移除后重新添加。

历史对照稿位于 [studies](../web/public/icons/studies/)，包括 [确认的精修稿](../web/public/icons/studies/pictide-wave-refined.svg)；拟合、曲线检查与预览记录位于 data/verification/，不随 Git 提交。
