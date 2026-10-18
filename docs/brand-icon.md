# Pictide 图标

- 完整图标：[pictide.svg](../web/public/icons/pictide.svg)，深色圆角背景与白色符号。
- 透明符号：[pictide-mark.svg](../web/public/icons/pictide-mark.svg)，使用 currentColor，内联时可跟随主题。

以用户确认的草图形态为准：外圈撑出 P，内侧浪头回卷，竖干随水势收成尖尾。精修曲线切线衔接、内勾与尾部的粗细过渡；负形形成浪洞。

主体为一条闭合填充路径。画布为 256×256；以原画布中心统一缩放至 94%，再向左 1.5、向下 2 个单位调整视觉位置，增加底框内的留白。完整图标与透明符号共享路径和变换。

无字体、图片或外部依赖，已核对前后对照及 16–64px 预览。当前为矢量设计源文件，应用已发布的 PNG 和页面品牌标记尚未替换。

## 渐细浪花拟合对照稿

以同一渐细参考轮廓生成四种拟合密度，尺寸与视觉位置一致，关键转折点共用；数量指整条轮廓的三次贝塞尔段数，尾部闭合直线共用。

- [A：8 段](../web/public/icons/studies/pictide-wave-8.svg)
- [B：12 段](../web/public/icons/studies/pictide-wave-12.svg)
- [C：18 段](../web/public/icons/studies/pictide-wave-18.svg)
- [D：24 段](../web/public/icons/studies/pictide-wave-24.svg)

中间的背景负形沿回卷方向逐渐收窄。当前为比较稿，主图继续保留已确认版本。离线拟合脚本、参考轮廓与局部放大预览保存在 data/verification/wave-curve-studies-20261018。

## 新版草图直接拟合

从用户提供的新版黑白草图提取实际边界，轻度平滑笔迹噪声，保留尾尖和内勾的转折；在同一画布比例下比较四种三次贝塞尔段数：

- [A：12 段](../web/public/icons/studies/pictide-sketch-v2-12.svg)
- [B：18 段](../web/public/icons/studies/pictide-sketch-v2-18.svg)
- [C：24 段](../web/public/icons/studies/pictide-sketch-v2-24.svg)
- [D：32 段](../web/public/icons/studies/pictide-sketch-v2-32.svg)

新版具有较厚外圈、较短尖尾和收窄的白色回卷通道。各稿为独立闭合矢量路径；仍是比较稿，未替换应用图标。边界提取、拟合脚本与渲染预览保存在 data/verification/wave-new-sketch-20261018。
