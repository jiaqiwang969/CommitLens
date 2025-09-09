# LaTeX 编译常见问题与通用解决方案

在使用 XeLaTeX/LaTeX 编译各类文档时，常见如下问题及对应通用修复建议，供后续排查与复用。

## 1. 系统字体缺失导致字体加载报错
- 现象：如 `ctex` 等宏包默认调用操作系统字体（如 `STHeiti`、`STSong` 等），但目标环境未安装，出现类似
  - `Package fontspec Error: The font "STHeiti" cannot be found.`
- 解决方案：优先使用 TeX Live 自带、跨平台可用的字体集（如 Fandol、Noto），通过 `fontset=fandol` 等参数指定，避免依赖系统字体。若需特定字体，确保环境已安装或在受控环境中固定字体依赖。

## 2. 行内代码下划线与 Markdown 反引号导致报错
- 现象：在正文或列表中直接使用 Markdown 风格反引号（如 `` `in_circle` ``）且代码含下划线 `_`，会触发 `Missing $ inserted.` 等错误（因 `_` 在文本模式下需转义）。
- 解决方案：含下划线的行内代码建议用 `\verb|...|` 或 `\lstinline|...|`（需加载 `listings` 宏包）代替反引号。批量替换时，优先处理反引号包裹且含 `_` 的片段。

## 3. 常见非致命警告
- `Underfull \hbox ...`：排版拉伸不足，通常不影响输出，可通过调整换行、连字符或使用 `\sloppy` 缓解。
- `fontspec Warning: ... does not contain requested Script "CJK"`：字体脚本声明提示，通常可忽略。
- `hyperref Warning: Rerun to get /PageLabels`：需二次编译以完善交叉引用，属正常提示。

## 4. 被包含文件中重复声明导言区
- 现象：被 `\input` 或 `\include` 的子文件中含有 `\documentclass`、`\begin{document}` 等导言区命令，导致
  - `LaTeX Error: Can be used only in preamble.`
- 解决方案：将被包含文件改为“片段”格式（无导言区、无 `\begin{document}`/`\end{document}`），仅保留正文结构（如 `\section` 等）。如需在正文中提及控制序列名（如 `\documentclass`），用 `\verb|...|` 包裹，避免被当作命令执行。

## 5. 图像文件无效或格式错误
- 现象：插入的 PDF/图片文件实际为非图像格式（如 ASCII 文本），导致
  - `Unable to load picture or PDF file ...`
- 解决方案：临时可用 `\fbox{\parbox{...}{...}}` 占位，确保编译不中断。建议用 `file` 或 `pdfinfo` 等工具检查文件类型，确保插入的为有效图片/PDF。

## 6. 错误的下划线转义方式
- 现象：在 `\texttt{...}` 等命令中用 `\\_`（两个反斜杠）试图转义下划线，实际变为换行命令加下划线，导致 `Missing $ inserted.` 等错误。
- 解决方案：正确转义应使用 `\_`，或直接用 `\verb|...|` 表示行内代码。

## 7. 特殊字符与编码问题
- 现象：如在标题或正文中直接使用 `≤`（U+2264）等特殊符号，若所用字体缺字，出现
  - `Missing character: There is no ≤ ...`
- 解决方案：可用数学符号（如 `$\le$`）替代，或用文字描述（如“不超过 200 字”），或切换到包含该字形的字体。

## 8. 行内代码与参数环境兼容性
- 建议：行内代码优先用 `\lstinline|...|` 或 `\verb|...|`。如需在“移动参数”环境（如 `\caption{}`）中使用，考虑用 `\texttt{...}` 并正确转义下划线，或将代码移至正文。

## 9. 批量检查与规范建议
- 建议：可用正则或脚本批量查找反引号包裹且含 `_` 的片段，统一替换为 `\verb|...|` 或 `\lstinline|...|`，以提升文档可移植性和编译稳定性。

