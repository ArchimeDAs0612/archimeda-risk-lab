# 阿基米达风险决策实验室 · 当前检查点与唯一主要待办

长期使命：持续进行。当前授权范围：用户要求取得已筛选的公开验证标识；推进Codecov覆盖率、Sonar质量门槛、GitHub构建来源证明、OpenSSF Passing补证和Zenodo存档。保留同一工程，不新增算法研究、付费服务或调度。

## 当前状态与有效基线

- 上次正式交付：main `bf545e0baf1b43f2a291a1f510cb0d339235b0ea`，[同提交CI成功](https://github.com/ArchimeDAs0612/archimeda-risk-lab/actions/runs/38933893272)，[公开仓库](https://github.com/ArchimeDAs0612/archimeda-risk-lab)与[静态Demo](https://archimedas0612.github.io/archimeda-risk-lab/)可访问。原公开收据保留为历史，不把旧绿色CI当本提交验收。
- 当前交付：官方OpenSSF Scorecard首次真实评估4.5/10、18项检查，官方运行和公开API均验证；[原始证据与逐项不足](docs/PUBLICATION_ASSESSMENTS.md)及README官方动态徽章已接入。私密漏洞报告已启用，贡献/安全说明及Best Practices草案已公开。核心研究资产不变。
- 本提交的正式接受条件：相关测试、安全/许可、远程内容、同SHA CI和Pages来源一致。最新验收事实以[GitHub main检查](https://github.com/ArchimeDAs0612/archimeda-risk-lab/actions/workflows/check.yml?query=branch%3Amain)及在线`site-provenance.json`为准；本文件不预先宣称未来CI成功。
- 核心有效产物及验证：[结果](docs/RC1_RESULTS.md)、[方法](docs/RC1_METHODS.md)、[研究验证](docs/RC1_VERIFICATION.json)、[干净环境复现](docs/RC1_REPRODUCTION.json)、[公开克隆复现](docs/PUBLICATION_REPRODUCTION.json)。本次不改训练、配置、模型、预测、标签或失败结果，不重新训练。
- 历史V0.2和私有阶段记录保留，不再作为当前状态副本。自动续跑任务仍暂停，自动写入式续跑未启用；本次不新建Goal或绝对截止时间，不重置旧任务时间。

## 验证与当前下一动作

此前实际通过：114项行为测试、保存证据33项核验及475项独立复算。此次对应检查为公开候选/链接/品牌识别、行为测试、增量安全审查和更名后仓库身份/Pages来源一致；实际同提交CI为最终验收来源。研究产物及核心算法相对有效基线无变化，未重训有效实验；依赖未变，原许可与干净环境复现继续有效。

Best Practices项目15545的已核实草稿已保存。用户确认CDLA-Permissive-2.0资料许可后自行点击提交；后台读取https://www.bestpractices.dev/en/projects/15545.json确认badge_level=in_progress、badge_percentage_0=63、tiered_percentage=63，平台updated_at=2026-10-16T15:29:55.616Z（北京时间23:29:55）。仓库草案60项状态与保存记录全部一致：41项Met、1项N/A、18项未知；草案未列出的平台条目另计。此前0%公开记录和未保存63%仅是历史。

公开新增基线d8848a2753423c266bce93764c89d4f47bd8d3a4已通过原研究两环境验收。Quality evidence的measurement/provenance实际成功；签名wheel在本地独立验证源码SHA、身份和runner，安装后9577行预测、8465行保存对照误差0，证据见PUBLICATION_PROVENANCE.json。Codecov首次因未接入失败；用户确认启用后重跑上传成功，但平台仅识别9/19模块，已定位XML路径问题并本地修复，已经在bf545e0baf1b43f2a291a1f510cb0d339235b0ea的官方API核验complete、19模块/1748语句全量匹配，平台81.4%；与纯行86.61%统计口径不同。新增防漏测试后共119项通过，全包行覆盖86.61%、分支74.75%。12项LOW subprocess提示保留，新增/漂移/中高发现阻断。原始d8848a2报告作为历史基线，不冒充未来提交结果。

当前下一动作：同步已取得的Codecov完整报告徽章与收据，并核验同SHA CI/Pages。Sonar仍在创建组织引导阶段，用户发来的链接含Team/Advanced Security选项，已指导改选Free；未将临时登录参数写入工程或转发请求，仍待真正公开项目链接/结果。Zenodo本人提交所需30MB归档和元数据已交付，361文件逐项绑定d8848a2。OpenSSF已保存仍为63%，仓库新草案62项（47 Met、5 N/A、10未知）尚未在平台保存，安全知识不能代填。没有DOI、Sonar门槛或Passing时不展示取得。自动续跑仍暂停，不新增调度、算法研究或版本。

## 尚未授权启动的研究待办

| 优先级 | 待研究问题 | 当前证据缺口与验收方向 |
| --- | --- | --- |
| 高 | 自动评估发现的工程安全缺口 | Scorecard已保存真实低分；后续可独立补分支保护、应用静态分析、依赖更新和发布证明，不伪造独立审核/贡献或定时扩项 |
| 高 | 选择性标签下训练与模型选择 | 已有识别边界，没有纠偏训练；预登记缺失机制、基线、误差和独立评价，零概率缺失保留不可识别结论 |
| 高 | 滚动时间验证与获准外部数据 | 当前后续窗与同机制种子不是外部域泛化；先核实许可，再盲测、记录漂移和失效 |
| 高 | 稳定Pattern选择 | 当前训练重发现Jaccard为0；改进训练内稳定选择，冻结后独立评价，不重挑已看过最终窗 |
| 中 | 校准、阈值与业务约束 | 当前有排序指标及假设策略成本，没有真实业务效用或完整校准研究；新增独立校准/阈值评价 |
| 中 | 真正LLM工具调用及评估 | 当前确定性工具已运行；缺少获授权模型环境，需实际调用、错误/注入评估与费用边界，不能借规则脚本宣称LLM |
| 中 | 治理审核身份与真实监控 | 已有版本/禁用/失效传播；没有认证审核身份和生产监控，需新接口授权与可测试威胁模型 |

上述是研究方向，不是已交付功能或运行中的任务。平台表单已由用户保存并完成公开核验，当前没有保存阻塞；未来LLM/外部数据须先具备合法输入和明确授权。

## 本人掌握

[专题练习](studies/README.md)与[五分钟路线](docs/INTERVIEW_GUIDE.md)提供独立解释、修改和反例验证。本人完成记录尚未提供，不能标记已掌握。工程验收与本人能力验收分开。
