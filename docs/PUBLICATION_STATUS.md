> 现名：[阿基米达风险决策实验室 / Archimeda Risk Lab](https://github.com/ArchimeDAs0612/archimeda-risk-lab) · [当前Demo](https://archimedas0612.github.io/archimeda-risk-lab/)。以下为原名下的历史首发记录；旧Pages路径不作为当前入口。

# GitHub-First 正式公开交付

**DELIVERED / PUBLISHED — Risk Decision Lab 0.3.0rc1 / GitHub-First V1.0**。Lab长期职业使命仍为ONGOING。本文件记录历史首次公开验收；当前进度与研究待办统一见[CHECKPOINT](../CHECKPOINT.md)，日常增量不另建发布版本。主分支最新状态以真实CI徽章和精确提交核验为准，文档不自证尚未完成的CI。

| 项目 | 实际结果 |
| --- | --- |
| Repository | [ArchimeDAs0612/risk-decision-lab](https://github.com/ArchimeDAs0612/risk-decision-lab)，PUBLIC |
| Accepted source commit | `376aa58b1bcff5f47266524a307a2a358ab463b4`；后续补交付证据和限流核验修复也须通过同等CI |
| Version | 风险工程0.3.0rc1；交付协议V1.0，不为上传人为增加算法版本 |
| CI | [真实成功运行](https://github.com/ArchimeDAs0612/risk-decision-lab/actions/runs/38868113597)：Linux Python3.9/3.11完整验证，Pages构建/部署成功 |
| Demo | [真实在线静态工作台](https://archimedas0612.github.io/risk-decision-lab/)；已实际HTTP及浏览器交互验证 |
| Reproduction | 匿名公开克隆、新输出目录12步成功，六类核心输出相等；详见PUBLICATION_REPRODUCTION.json |
| Safety | 发布白名单、文件/许可、完整可达历史均复查；无未审二进制或检测到的敏感内容，不把扫描当保密性证明 |

## 本轮实际实现

持久化AGENTS/长期规则；PR与main自动验证；精确main SHA、同SHA CI和Pages来源核验；静态发布白名单/摘要；公开复现与实际交互证据。没有修改风险算法定义、训练数据或旧失败结果，没有修改个人门户或其他仓库。

公开核验曾遇到共享匿名API额度耗尽（403且剩余0）。现仅在已明确确认额度原因时复用已有授权CLI读取元数据，另用无凭据HTTP/公开克隆证明公开可访问；权限错误继续失败。验证来源在PUBLICATION_VERIFICATION.json中如实记录。

Pages启用最初被自动审批拒绝。补充用户附件第九节的静态Pages授权、限定此Lab路径和65个输入与公开Git blob逐项一致的证据后，审批通过，真实部署完成。没有通过其他平台或间接工作流绕过拒绝。

## 实验与解释边界

复用真实模型/Pattern/字段实验：主森林最终AP0.2044，Score LR0.1298；冻结候选覆盖90次/18个风险，仅支持调查；重新发现不稳定，失败种子保留。字段工具为确定性工作流，未接入LLM。选择性标签实验显示仅观察成功支付时总体Recall只能识别在[0.15,0.4103]。模拟动作/成本不等于生产因果收益。

Pages只展示保存结果和浏览器规则回放，不训练模型、不执行Python服务或动态Agent。真实数据、稳定迁移、因果收益、实际LLM和本人独立掌握仍未建立。

## 历史交付后的维护

最新规则见[AGENTS](../AGENTS.md)与[交付操作](GITHUB_FIRST.md)；研究待办只维护于[CHECKPOINT](../CHECKPOINT.md)。首次全历史审查与干净克隆证据继续有效，日常按改动增量审查和验证，不重训有效实验或自动升版。

最新commit可用 `git rev-parse origin/main` 查看；部署来源为在线 `site-provenance.json`。运行 `python scripts/verify_publication.py --expected-commit <完整SHA> --pages-url https://archimedas0612.github.io/archimeda-risk-lab/` 核验指定交付。首次接受收据是历史事实，最新HEAD必须重新核验，不能拿旧绿色CI冒充新提交。
