# Security policy

Archimeda Risk Lab是独立合成研究软件，不是生产支付决策或凭据托管服务。公开实验不使用真实用户数据；请勿上传企业资料、个人敏感数据或密钥。

## Supported scope

当前main和当前预发布`0.3.0rc1`接受安全问题修复。历史快照用于复现，不承诺回补；发现历史泄漏仍应私下报告，单次删除不能消除Git历史中的风险。运行不可信输入前阅读数据/字段合同，不把JSON模型当通用安全沙箱。

## Private reporting

使用GitHub的[私密漏洞报告](https://github.com/ArchimeDAs0612/archimeda-risk-lab/security/advisories/new)，提供影响、最小独立复现、受影响提交/版本和修复建议。普通研究问题使用Issues；不要公开可利用细节或附真实敏感样本。

报告由维护者按实际可用时间确认、复现、修复并协调披露，不提供付费赏金或响应时限保证。未确认影响前不宣称漏洞已修复；严重问题优先处理。没有事故记录不能证明没有漏洞。

## Controls and limits

发布采用来源/许可审查、变更历史启发式扫描、行为测试、公开CI及独立指标/规则复算。GitHub Actions依赖固定官方提交，默认只读；OpenSSF Scorecard发布任务仅额外使用短期OIDC以证明公开结果来源，无仓库写入、个人令牌或新增云账号。

Scorecard是第三方开源工具的自动检查，不是人工渗透测试、基金会认证、算法正确性或生产安全保证。Best Practices材料只是待本人审核的自评草案。安全知识、账号2FA、真实人工审核及漏洞响应实践不能通过代码文件自动证明。
