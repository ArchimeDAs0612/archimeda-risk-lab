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

## OpenSSF Best Practices：申请草案，未登记/未获徽章

已查询[项目登记API](https://www.bestpractices.dev/en/projects.json?url=https%3A%2F%2Fgithub.com%2FArchimeDAs0612%2Farchimeda-risk-lab)，当前没有该项目记录。本站POST/修改需要独立登录会话，现有GitHub CLI授权不是Best Practices登录；未代建账号、未获取浏览器Cookie、未填写本人知识或2FA等未知声明。

已准备[官方自动填表格式草案](../.bestpractices.json)、[贡献说明](../CONTRIBUTING.md)、[安全报告流程](../SECURITY.md)。草案只提议有对应URL的基础事实；安全知识、静态/动态分析保持未知，不宣称Passing或100%。

本人下一动作：自行用GitHub登录[Best Practices新建项目](https://www.bestpractices.dev/en/projects/new)，仓库填`https://github.com/ArchimeDAs0612/archimeda-risk-lab`，名称填Archimeda Risk Lab，主页填`https://archimedas0612.github.io/archimeda-risk-lab/`。首次编辑Passing时官方工具可读取根目录`.bestpractices.json`提出答案，逐项检查再保存；创建后的数字项目链接可继续用于核验。无需邀请别人参加。

格式依据：[官方JSON自动提议](https://github.com/ossf/best-practices-badge/blob/main/docs/bestpractices-json.md)、[认证/API说明](https://github.com/ossf/best-practices-badge/blob/main/docs/api.md)。本文件自行总结，不复制完整官方标准；官方标准及网站内容归OpenSSF Best Practices badge contributors，按其CC-BY许可提供。

## 比赛/期刊：尚未报名

目前未提交比赛预测或期刊申请。竞赛按具体赛题、数据许可、个人参赛资格与截止日期报名，不能将整个Lab上传后声称参赛获奖。IEEE-CIS Fraud Detection是历史2019赛事，晚提交不冒称正式奖项；JOSS当前要求持续六个月以上公开开发，现阶段不提交不合格申请。账号、本人声明及对应平台条款须实际完成，不能用占位链接或本地结果冒充登记。

当前执行进度和后续必要动作仅维护于[CHECKPOINT](../CHECKPOINT.md)，不另建任务/调度系统。当前不以Star或徽章数量评价算法成熟度。
