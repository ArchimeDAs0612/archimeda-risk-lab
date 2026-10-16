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

## OpenSSF Best Practices：项目15545已保存63%，未获徽章

用户已创建[项目15545](https://www.bestpractices.dev/en/projects/15545)，并明确确认按CDLA-Permissive-2.0公开自评资料。用户在现有浏览器中自行提交后，后台读取[平台公开JSON](https://www.bestpractices.dev/en/projects/15545.json)，确认badge_level=in_progress、badge_percentage_0=63、tiered_percentage=63，平台保存时间为2026-10-16T15:29:55.616Z（北京时间23:29:55）。这是实际已保存进度，替代此前未保存的63%预填及最初0%记录；尚未获得Passing。

[官方自动填表草案](../.bestpractices.json)中的全部60项状态已逐项与保存记录比较一致：41项Met、1项N/A、18项未知。平台还有草案未列出的条目及更高等级条目，因此18项不代表所有剩余要求。已核实的证据覆盖文档、Git、构建、CI、测试、警告、交付和哈希。未测覆盖率、英文完整性、响应历史、安全知识、应用静态/动态安全分析等继续未知；不因希望拿徽章而全部填Met。N/A仅用于项目自身没有内存不安全语言的专项要求。

使用官方`reanalyze=1`可重新读取仓库草案并提出答案，提议本身不是已保存事实。本次资料许可已经用户确认，不改变源码MIT许可，也不代表本人已声明安全知识。遵守当前禁止操纵浏览器的约定，由用户执行网页提交，助手仅通过公开接口核验；没有提取Cookie或绕过认证。Best Practices是可公开核查的自评，不是算法竞赛奖项或独立人工技术评审。

格式依据：[官方JSON自动提议](https://github.com/ossf/best-practices-badge/blob/main/docs/bestpractices-json.md)、[认证/API说明](https://github.com/ossf/best-practices-badge/blob/main/docs/api.md)。本文件自行总结，不复制完整官方标准；官方标准及网站内容归OpenSSF Best Practices badge contributors，按其CC-BY许可提供。

## 新增验证接入：真实来源证明、完整覆盖与待办

首次公开验证基线为`d8848a2753423c266bce93764c89d4f47bd8d3a4`。[真实运行](https://github.com/ArchimeDAs0612/archimeda-risk-lab/actions/runs/38929772719)中measurement与provenance均成功；[原始覆盖/安全摘要](PUBLICATION_QUALITY.json)记录118项测试对应全包Python行覆盖86.61%、分支覆盖74.75%，包括未执行CLI。Bandit扫描全部Python应用/交付源码，HTTPS入口与降级跳转约束已修复，12项LOW subprocess提示保留并绑定源文件摘要，无MEDIUM/HIGH。它不覆盖JS/SQL，也不证明算法正确或没有漏洞。

**安装包签名已经取得并独立验证。** [来源收据](PUBLICATION_PROVENANCE.json)记录真实wheel摘要、GitHub/Sigstore证书、透明日志时间及精确源码SHA。本地另行验证仓库、源码提交、签名工作流和托管runner；从源码目录之外安装wheel并预测9577行，其中8465行可与原保存概率按事件一对一比较，最大误差0；另外1112行不在原标签合格预测表中，不冒称也有已保存对照。没有声明SLSA等级或算法获奖。原run artifacts保留7天，本地已保存原wheel及完整验签输出。

- **Codecov**：作者已完成账号接入。第一次OIDC上传因Repository not found失败，接入后原失败job重跑成功，平台commit API已返回同一源码SHA和complete。首次平台报告仅识别9/19个模块，85.17%为不完整范围，因此没有将它作为全包覆盖率挂到首页。修复XML为仓库相对路径并增加防漏检查后，提交bf545e0baf1b43f2a291a1f510cb0d339235b0ea的官方API返回complete，完整19模块、1748条语句，覆盖率81.4%，已逐文件核对且没有遗漏。首页接入真实动态徽章；[公开收据](PUBLICATION_CODECOV.json)保留首次不完整结果。Codecov将未完整执行分支的行计为partial，其81.4%不是Coverage.py纯行覆盖86.61%的同一口径。
- **SonarQube Cloud**：扫描/真实quality gate步骤已准备；作者尚待提供公开项目链接，当前仓库无SONAR_TOKEN、组织或project key，不展示未取得的徽章。可先在https://sonarcloud.io登录并创建Free公开项目；若使用自动扫描，先核验公开门槛，不能把未执行的CI扫描写成已执行。CI扫描需要仓库变量SONAR_ORGANIZATION、SONAR_PROJECT_KEY及本人直接存入GitHub secret的SONAR_TOKEN，再设SONAR_ENABLED=true；无需在聊天发送凭据。
- **Zenodo DOI**：[归档收据](PUBLICATION_ARCHIVE.json)确认公开提交d8848a2的361个白名单文件逐个匹配，源码ZIP为30813931字节。归档和签名wheel已保存在本地runs/verification-d8848a2；CITATION.cff与.zenodo.json使用真实公开作者名和MIT，不虚构单位、ORCID或DOI。作者须在https://zenodo.org/uploads/new用本人账号实际提交归档，或接入https://zenodo.org/account/settings/github/；目前未取得DOI。这个归档是明确提交的研究快照，不是新的软件版本。
- **OpenSSF Passing**：平台最后已保存仍为63%。仓库新增提议包含英文接口、实际静态分析及有明确适用理由的N/A；当前草案62项：47 Met、5 N/A、10未知，另外平台未列入草案的条目仍需审核。提议不是已保存状态，未知安全知识/响应历史等不自动改成Met。用户已确认同一CDLA资料许可，不重复索要许可；需在平台重新分析后自行核对保存。[本人安全知识练习](PUBLICATION_SECURITY_PRACTICE.md)提供真实讲解/改动/反例入口，尚未认定本人掌握。

修复后的本地验证增加了上传XML完整性反例，共119项测试；XML使用defusedxml安全解析，不通过屏蔽安全发现换绿。开发依赖与运行依赖分开；许可文本见[PUBLICATION_TOOL_LICENSES.txt](PUBLICATION_TOOL_LICENSES.txt)，英文接口见[PUBLICATION_ENGLISH_GUIDE.md](PUBLICATION_ENGLISH_GUIDE.md)。平台免费方案不自动开通付费试用，账号接入和本人声明不代填。

## 比赛/期刊：尚未报名

目前未提交比赛预测或期刊申请。竞赛按具体赛题、数据许可、个人参赛资格与截止日期报名，不能将整个Lab上传后声称参赛获奖。IEEE-CIS Fraud Detection是历史2019赛事，晚提交不冒称正式奖项；JOSS当前要求持续六个月以上公开开发，现阶段不提交不合格申请。账号、本人声明及对应平台条款须实际完成，不能用占位链接或本地结果冒充登记。

当前执行进度和后续必要动作仅维护于[CHECKPOINT](../CHECKPOINT.md)，不另建任务/调度系统。当前不以Star或徽章数量评价算法成熟度。
