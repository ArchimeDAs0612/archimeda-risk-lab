# 风险策略条件与决策回放

## 问题与设计

同一事件同时满足A、B，与订单历史中分别存在A和B不是同一规则；候选条件命中也不等于执行拒绝。研究把条件、事件集合、组合逻辑和动作分开，使用保存的完整树路径与训练预处理逐成员复算，然后在同一最终窗对比冻结基线与模拟策略。

输入为[冻结记录](../artifacts/rc1/research/normal/frozen_selection.json)、[主实验预测及事件](../artifacts/rc1/research/normal/all_predictions.csv)与结果中的策略假设。完整候选含训练中位数、缺失指示、float32比较域；不得把人工删条件的简化版冒充原路径。

## 实现与运行证据

[条件语义](../risklab/data.py) · [路径AST与动作回放](../risklab/patterns.py) · [边界反例](../tests/test_pattern_boundaries.py) · [策略测试](../tests/test_patterns.py) · [独立成员/动作复算器](../scripts/verify_v02.py)。

`raw_tree:11`完整条件见[结果](../docs/RC1_RESULTS.md)：设备年龄下界/上界、地理距离和认证强度四项AND。最终命中90次、18个风险。OR拒绝使拒绝9→99，风险零拒绝7→79；完整90个动作变更ID保存在[主结果strategies](../artifacts/rc1/research/normal/result.json)。AND拒绝为0，OR审核保持9个拒绝并产生166个审核；这些是不同动作，不能仅对比规则覆盖率。

[在线工作台](https://archimedas0612.github.io/risk-decision-lab/artifacts/rc1/research/normal/index.html)允许修改条件/组合、查看事件与导出结果。浏览器重算是已保存样本上的JavaScript操作；新训练及Python实验需要本地命令。

## 反证与局限

[结果patterns](../artifacts/rc1/research/normal/result.json)保留逐项删条件后的新增/移除成员、来源/金额分层、重发现不稳定及策略敏感性。来源×金额匹配仅覆盖84/90，不能把其结论外推未匹配成员。空用户AST不能代替真实树根叶，float32阈值边界必须逐成员核对。

假设成本9002.63→8122.62依赖拒绝阻止全部风险金额损失、审核无保护且行为不变；不是收益或可上线推荐。独立审计风险零事件亦不是已证实的真实好用户。下一步见[统一待办](../CHECKPOINT.md)：稳定选择、校准/阈值和更明确业务约束。

## 本人练习

1. 解释同事件AND、订单历史条件并集、完整路径和策略动作四个层次。
2. 在新输出目录将OR拒绝改为OR审核，逐个核对changed_event_ids和成本算术。
3. 构造跨事件A/B、阈值两侧float32和空AST，验证哪些应命中、哪些必须报错。
