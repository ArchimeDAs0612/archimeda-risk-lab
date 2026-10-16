# GitHub-First Continuous Delivery Protocol V1.0

用户于2026-10-16确立的长期规则，适用于当前工程、未来版本、普通执行、Goal及已授权恢复任务。仓库固定为 `https://github.com/ArchimeDAs0612/risk-decision-lab`；当前已核实账号及仓库归属，不从网页地址推断认证。

## 正式交付判定

本地实现、测试或HTML成功都不是正式交付。只有真实工程/实验完成、必要验收通过、公开安全及许可合格、Git提交推送成功、公开main与交付commit一致且能从GitHub复现，才可报告 **DELIVERED / PUBLISHED**。缺一项即明确 **LOCAL COMPLETE / PUBLICATION BLOCKED**，记录具体原因与下一动作。

Lab使命持续进行，版本验收不代表职业资产建设结束。不得用文件、提交、测试或功能数量代替能力、验证深度与失败理解。

## 永久授权与边界

用户已明确授权在现有账号中创建、复用和公开此独立Lab仓库，并持续发布通过审查的Lab成果，不再逐轮请求同类公开许可。授权不涵盖企业材料、他人未获许可资产、密钥、其他仓库、个人门户或付费服务。不能确认安全的内容必须隔离或阻断，不得用改名/扰动掩饰公司资产。

## 每轮工作流

1. 读AGENTS/Checkpoint，核对认证、远程归属、分支、工作区与远程差异，保留既有成果。
2. 独立研发与实际实验；普通失败自行修复，保留有效及失败证据，避免同一路线无信息重复。
3. 运行受影响测试、集成和实验smoke；核对真实输出、适用范围、局限与复现。
4. 审查发布白名单、暂存区、所有可达历史、配置、来源和第三方许可；不输出环境秘密，不把“扫描无匹配”当保密性证明。
5. 更新README、方法、结果、CHANGELOG与准确Checkpoint；尚未实现的内容标Planned/Missing。
6. 用有意义的语义提交形成版本；推送分支/PR，CI成功后合入main。不强制推送、不盲目覆盖远程。
7. 核验公开API、main SHA和同SHA CI；干净克隆运行必要命令并检查输出。Pages还须核对实际HTTP和部署commit。
8. 报告九项收据：Repository、Commit、Version、Implemented、Experiments、Validation、Reproduction、Limitations、Next。

## 自动验证与静态Demo

`.github/workflows/check.yml`负责依赖安装、单测、代码编译、旧/新实验smoke、保存模型与回放、字段工具/选择性标签、打包/来源安全检查。PR也执行验证；部署仅允许main成功后进行。未运行或失败的CI不能展示为通过。

`scripts/build_pages.py`仅复制已公开且实际运行的静态产物，记录部署源码SHA及文件摘要；Pages展示离线工作台和浏览器规则回放，不训练模型、不运行Python后端或LLM。不改变个人门户。Actions使用公共仓库标准Linux runner、短期Pages artifact，不申请付费资源或缓存扩容。

`scripts/verify_publication.py`优先匿名API核验指定main及同提交CI；仅明确证实共享匿名额度耗尽时复用已授权GitHub CLI读取元数据，并另以无凭据HTTP核验公开访问。权限错误不作此替代，验证来源明确记录。部署启用时还核对Pages来源SHA；所有检查通过才输出正式交付状态。

## 来源与维护

代码和合成数据为独立实现并采用MIT，第三方依赖单独保留许可。完整生成器、模型/Pattern/策略/治理/测试/文档都进入仓库；缓存、私有状态、重复超大中间数据可排除，但须有代码与配置复现。真正LLM Agent仍未实现，不能创建虚假完成资产。

未来新技术遵循通用问题抽象→独立实现→实际实验→验证→GitHub提交→版本记录→展示更新。自动续跑同样遵守互斥、首次绝对截止时间和有效授权，不由本协议获得无限后台执行许可。
