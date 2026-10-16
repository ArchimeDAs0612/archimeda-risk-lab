# 来源与许可

本项目新写代码、方法说明和独立合成数据采用仓库 MIT 许可，随 Release Candidate 供发布审查。没有外部业务数据、图片、企业代码或报告素材。许可证不替代具体发布目标及公开授权。

运行依赖固定版本及许可证：NumPy 2.0.2（BSD-3-Clause）；pandas 2.3.3（BSD-3-Clause）；SciPy 1.13.1（BSD-3-Clause，含发行包附带组件许可）；scikit-learn 1.6.1（BSD-3-Clause）；joblib 1.5.3（BSD-3-Clause）；threadpoolctl 3.6.0（BSD-3-Clause）；python-dateutil 2.9.0.post0（Apache-2.0 / BSD-3-Clause）；pytz 2026.5（MIT）；six 1.17.0（MIT）；tzdata 2026.5（Apache-2.0，时区数据的公共领域声明详见随包许可）。Python 与 SQLite 由运行环境提供，不随交付复制运行二进制。

`third-party-licenses.txt` 从本轮实际安装包的 dist-info 许可证文件读取，保留包内组件声明。安装器/构建工具不属于核心运行依赖。没有将第三方运行包或二进制打进交付 ZIP。

官方文档仅作链接引用，未复制正文或图像。若以后引入公开数据，须单独核验原始来源、许可、可用字段、标签、时点及再分发条件；当前没有对任何外部数据集作出许可判断。

V0.2 核心没有新增 Python 运行依赖。开发验证另使用 Playwright / playwright-core 1.62.1（Apache-2.0），实际运行于已提供的开发依赖环境；package.json 固定可选验证版本。其许可证见 playwright-dev-licenses.txt。浏览器与 Node 二进制不打包，公共工作台本身不需要这些开发依赖。新机器安装开发依赖时须遵守相应发行包和可选系统组件许可。

## 公开自动评估工具

OpenSSF Scorecard Action v2.5.0（提交`fa7117db83c52d787ae5a89f350999701505d78e`）为Apache-2.0，见[官方许可](https://github.com/ossf/scorecard-action/blob/fa7117db83c52d787ae5a89f350999701505d78e/LICENSE)。仅在免费公共CI中运行官方容器，不把其代码或二进制重许可/打包到Lab。Actions upload-artifact固定官方v4提交，许可见[官方MIT](https://github.com/actions/upload-artifact/blob/ea165f8d65b6e75b540449e92b4886f43607fa02/LICENSE)。核心Python依赖没有改变。
