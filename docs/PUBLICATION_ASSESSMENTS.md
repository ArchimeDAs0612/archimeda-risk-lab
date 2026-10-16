# 可独立申请的公开评估

当前范围：无需组队或邀请他人参与，先完成可直接使用现有GitHub授权的免费评估。这里记录申请/运行事实，不把申请准备当获奖或认证。

## OpenSSF Scorecard

已完成实际接入与公开结果核验。首次评估为**4.5/10，18项检查**，源码提交`2a577b194961c2a69235406fcc18626608dc8f64`，工具报告时间`2026-10-16T10:07:36Z`。原始Action JSON与公开API的日期、工具版本、源码、总分和全部检查逐项相等；API仅省略原始JSON的null metadata，保存文件未改写，SHA256为`f44057013602e9dbafc7dc0f8b42761a644d36f7935c91feb4951baba95fb609`。

[官方真实运行](https://github.com/ArchimeDAs0612/archimeda-risk-lab/actions/runs/38885107975) · [官方公开结果查看器](https://scorecard.dev/viewer/?uri=github.com/ArchimeDAs0612/archimeda-risk-lab) · [公开API](https://api.scorecard.dev/projects/github.com/ArchimeDAs0612/archimeda-risk-lab) · [首次原始报告](PUBLICATION_SCORECARD.json)。API/徽章显示最新扫描，保存文件是首次基线，不冒充后续提交已扫描。

官方Action固定v2.5.0提交`fa7117db83c52d787ae5a89f350999701505d78e`。运行成功与评分高低是两件事，没有人为通过阈值，不隐藏低分；不是OpenSSF人工认证或算法奖项。

[工作流](../.github/workflows/scorecard.yml)仅main推送或手动运行，无定时任务；公共Ubuntu runner，默认只读，单任务短期OIDC仅用于向OpenSSF发布已公开仓库的评估结果，无个人Token、云账号或付费服务。未启用SARIF上传，所以不授予security-events写入权限。

报告关注仓库安全与维护实践，不评估AUC、Pattern增益或社会影响。项目新、独立贡献者少、缺独立代码审核等应如实显示；不会为了分数假造审核或维护历史。[官方说明](https://github.com/ossf/scorecard-action/blob/main/README.md)。

## 首次检查结果与真实不足

| 官方检查 | 得分 | 原始理由 |
| --- | ---: | --- |
| Maintained | 0 | project was created within the last 90 days. Please review its contents carefully |
| Dangerous-Workflow | 10 | no dangerous workflow patterns detected |
| Security-Policy | 10 | security policy file detected |
| Packaging | -1 | packaging workflow not detected |
| Binary-Artifacts | 10 | no binaries found in the repo |
| Code-Review | 0 | Found 0/7 approved changesets -- score normalized to 0 |
| Token-Permissions | 10 | GitHub workflow tokens follow principle of least privilege |
| Pinned-Dependencies | 5 | dependency not pinned by hash detected -- score normalized to 5 |
| Vulnerabilities | 10 | 0 existing vulnerabilities detected |
| CII-Best-Practices | 0 | no effort to earn an OpenSSF best practices badge detected |
| SAST | 0 | SAST tool is not run on all commits -- score normalized to 0 |
| Dependency-Update-Tool | 0 | no update tool detected |
| License | 10 | license file detected |
| Signed-Releases | 0 | Project has not signed or included provenance with any releases. |
| Fuzzing | 0 | project is not fuzzed |
| Branch-Protection | 0 | branch protection not enabled on development/release branches |
| Contributors | 0 | project has 0 contributing companies or organizations -- score normalized to 0 |
| CI-Tests | 10 | 5 out of 5 merged PRs checked by a CI test -- score normalized to 10 |

`-1`是工具无法评估/未识别，不是0分或不存在实现。Packaging未识别发布工作流不否认已有wheel安装测试；Maintained为0的理由是仓库创建不足90天，不是已证明无人维护。Contributors检测组织多样性，不等于没有作者。Vulnerabilities的10分只说明未检测到该工具所查的已知问题。

这些差距保留：不刷历史、不用假账号增加贡献者、不用机器人审批冒充独立审查、不为了分数假签名或隐藏失败。可独立改进的分支保护、依赖更新、应用静态分析和发布证明须作为明确后续维护处理；需要外部独立贡献的条目不伪造。

## OpenSSF Best Practices：已保存76%，未获徽章

[项目15545](https://www.bestpractices.dev/en/projects/15545)公开JSON已核验：`badge_percentage_0=76`，`updated_at=2026-10-16T18:43:24.110Z`。此前63%是历史；本次重新分析曾提议78%，但Sonar新增安全发现尚未完成复核，因此把`static_analysis_fixed`改为未知并使用普通“Submit (and exit)”保存。公开JSON确认状态和解释均持久化，未将78%提议冒称最终进度。

用户已确认同一CDLA-Permissive-2.0资料许可，本次明确允许夜间隐藏浏览器操作；没有控制桌面、用户窗口或提取会话凭据。源码MIT许可不变。`Save (and continue) 🤖`会重新分析并带回仓库草案，人工修正使用普通提交，并同步修改[仓库草案](../.bestpractices.json)避免未来回填旧结论。

新增证据包括英文接口、真实覆盖/静态扫描及有明确理由的N/A；本人安全知识、响应历史和未完成的安全复核继续未知，不冒称Passing。自评不是算法竞赛奖项或独立人工评审。[本人练习](PUBLICATION_SECURITY_PRACTICE.md)尚未完成能力认证。

格式依据：[官方JSON自动提议](https://github.com/ossf/best-practices-badge/blob/main/docs/bestpractices-json.md)、[认证/API说明](https://github.com/ossf/best-practices-badge/blob/main/docs/api.md)。官方标准及网站内容归OpenSSF Best Practices badge contributors，按其CC-BY许可提供。

## 新增验证接入：真实来源证明、完整覆盖与待办

首次公开验证基线为`d8848a2753423c266bce93764c89d4f47bd8d3a4`。[真实运行](https://github.com/ArchimeDAs0612/archimeda-risk-lab/actions/runs/38929772719)中measurement与provenance均成功；[原始覆盖/安全摘要](PUBLICATION_QUALITY.json)记录118项测试对应全包Python行覆盖86.61%、分支覆盖74.75%，包括未执行CLI。Bandit扫描全部Python应用/交付源码，HTTPS入口与降级跳转约束已修复，12项LOW subprocess提示保留并绑定源文件摘要，无MEDIUM/HIGH。它不覆盖JS/SQL，也不证明算法正确或没有漏洞。

**安装包签名已经取得并独立验证。** [来源收据](PUBLICATION_PROVENANCE.json)记录真实wheel摘要、GitHub/Sigstore证书、透明日志时间及精确源码SHA。本地另行验证仓库、源码提交、签名工作流和托管runner；从源码目录之外安装wheel并预测9577行，其中8465行可与原保存概率按事件一对一比较，最大误差0；另外1112行不在原标签合格预测表中，不冒称也有已保存对照。没有声明SLSA等级或算法获奖。原run artifacts保留7天，本地已保存原wheel及完整验签输出。

- **Codecov**：作者已完成账号接入。第一次OIDC上传因Repository not found失败，接入后原失败job重跑成功，平台commit API已返回同一源码SHA和complete。首次平台报告仅识别9/19个模块，85.17%为不完整范围，因此没有将它作为全包覆盖率挂到首页。修复XML为仓库相对路径并增加防漏检查后，提交bf545e0baf1b43f2a291a1f510cb0d339235b0ea的官方API返回complete，完整19模块、1748条语句，覆盖率81.4%，已逐文件核对且没有遗漏。首页接入真实动态徽章；[公开收据](PUBLICATION_CODECOV.json)保留首次不完整结果。Codecov将未完整执行分支的行计为partial，其81.4%不是Coverage.py纯行覆盖86.61%的同一口径。
- **SonarQube Cloud**：已真实创建Free组织`archimedas0612`，仅导入Lab。原GitHub App所有仓库安装范围经用户精确确认收窄为单Lab，自动导入新仓库关闭。首次自动扫描绑定main `1e1c47dbb6c7b9e9f7ba9dd15c3ac672bb9ba9bb`；[公开项目](https://sonarcloud.io/project/overview?id=ArchimeDAs0612_archimeda-risk-lab)与[原始收据](PUBLICATION_SONAR.json)可核查。65项安全发现、131项维护发现、页面2项可靠性发现；旧API bugs=0与现代可靠性分类口径不同。安全评级E、质量门槛NONE/Not computed，未获得通过徽章。扫描含历史/生成产物，313780 ncloc不代表当前Python包体量；未通过排除或接受问题换绿。未导入覆盖报告，Codecov独立保留；无需新Sonar令牌，CI Sonar job仍未启用。 第二次main自动扫描绑定`cec86f6a9af2f3571c6805a5b5046d80d820d444`，默认Sonar way新增代码门槛返回OK，官方动态SVG返回passed，首页据此挂真实徽章；未改门槛、手动移动基线或接受/排除问题。整体E评级和65项发现不因新增代码门槛通过而消失，原始首次NONE与后续通过分别保留于同一收据。
- **Zenodo DOI**：登录后已保存草稿23423965，软件类型、公开作者、MIT、完整源码提交、研究边界与仓库URL均实际填写。30MB ZIP上传失败，刷新后为0字节Pending、无校验；未发布、没有DOI。原361文件逐项核验快照保留；已准备13.6MB tar.xz并逐文件验证相同内容，清理失败空条目待用户具体批准。[草稿执行收据](PUBLICATION_ZENODO.json)与[原快照收据](PUBLICATION_ARCHIVE.json)明确区分；不创建重复记录或新软件版本。
- **OpenSSF Passing**：已保存76%，新增Sonar结果使静态分析修复结论保持未知；公开记录与仓库草案均如实保留。安全知识和响应历史不得代填，未取得Passing。

修复后的本地验证增加了上传XML完整性反例，共119项测试；XML使用defusedxml安全解析，不通过屏蔽安全发现换绿。开发依赖与运行依赖分开；许可文本见[PUBLICATION_TOOL_LICENSES.txt](PUBLICATION_TOOL_LICENSES.txt)，英文接口见[PUBLICATION_ENGLISH_GUIDE.md](PUBLICATION_ENGLISH_GUIDE.md)。平台免费方案不自动开通付费试用，账号接入和本人声明不代填。

## 比赛/期刊：尚未报名

目前未提交比赛预测或期刊申请。竞赛按具体赛题、数据许可、个人参赛资格与截止日期报名，不能将整个Lab上传后声称参赛获奖。IEEE-CIS Fraud Detection是历史2019赛事，晚提交不冒称正式奖项；JOSS当前要求持续六个月以上公开开发，现阶段不提交不合格申请。账号、本人声明及对应平台条款须实际完成，不能用占位链接或本地结果冒充登记。

当前执行进度和后续必要动作仅维护于[CHECKPOINT](../CHECKPOINT.md)，不另建任务/调度系统。当前不以Star或徽章数量评价算法成熟度。
