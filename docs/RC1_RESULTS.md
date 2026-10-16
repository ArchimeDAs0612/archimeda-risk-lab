# RC1 真实结果与失败

所有数值从保存结果生成。新模拟器修正物理设备年龄，不能与旧V0.2直接作模型增益比较。

## 模型和种子

| seed | 选择模型 | 最终AP | Score LR AP | Pattern | 支持/风险 | 结论 |
|---|---|---:|---:|---|---|---|
| 20261016 | raw_forest | 0.2044 | 0.1298 | raw_tree:11 | 90/18 | SUPPORTED_FOR_INVESTIGATION |
| 20261017 | hybrid_forest | 0.1876 | 0.1317 | raw_tree:13 | 65/17 | SUPPORTED_FOR_INVESTIGATION |
| 20261018 | enriched_forest | 0.2611 | 0.1589 | enriched_tree:11 | 89/12 | INSUFFICIENT_SUPPORT |

第三个种子失败区间跨0，未改测试数据或改选候选。选择模型不同说明选择波动；种子是同机制敏感性，不是外部域测试。

## 主实验完整候选

```json
{
  "id": "raw_tree:11",
  "model": "raw_tree",
  "path": {
    "leaf_id": 11,
    "predicates": [
      {
        "feature_index": 2,
        "transformed_feature": "device_age_days",
        "threshold": 0.43503323197364807,
        "operator": ">"
      },
      {
        "feature_index": 2,
        "transformed_feature": "device_age_days",
        "threshold": 10.210319519042969,
        "operator": "<="
      },
      {
        "feature_index": 4,
        "transformed_feature": "geo_distance",
        "threshold": 0.13304689526557922,
        "operator": ">"
      },
      {
        "feature_index": 3,
        "transformed_feature": "auth_strength",
        "threshold": 0.5,
        "operator": ">"
      }
    ],
    "train_support": 449
  },
  "train": {
    "n": 449,
    "risk_count": 50,
    "coverage": 0.08747321254626923,
    "risk_rate": 0.111358574610245,
    "enrichment": 1.5703394600944713
  },
  "select": {
    "n": 65,
    "risk_count": 9,
    "coverage": 0.047653958944281524,
    "risk_rate": 0.13846153846153847,
    "enrichment": 1.8159763313609467
  },
  "eligible_selection_support": true,
  "preprocessing": {
    "input_columns": [
      "amount",
      "account_age_days",
      "device_age_days",
      "auth_strength",
      "geo_distance",
      "attempts_24h",
      "declines_7d"
    ],
    "output_columns": [
      "amount",
      "account_age_days",
      "device_age_days",
      "auth_strength",
      "geo_distance",
      "attempts_24h",
      "declines_7d",
      "amount__missing",
      "account_age_days__missing",
      "device_age_days__missing",
      "auth_strength__missing",
      "geo_distance__missing",
      "attempts_24h__missing",
      "declines_7d__missing"
    ],
    "train_medians": {
      "amount": 30.167623592590783,
      "account_age_days": 42.9843287037037,
      "device_age_days": 30.7084109605904,
      "auth_strength": 1.0,
      "geo_distance": 0.2139116694692763,
      "attempts_24h": 0.0,
      "declines_7d": 0.0
    },
    "missing": "replace by train median and append a missing indicator per input",
    "dtype": "float32",
    "fit_scope": "train only"
  }
}
```

最终差值区间 [0.012743958456356553, 0.1984701545062216]；来源/金额反证保留 84/90，未匹配单元不声称验证。3次训练重采样重新发现Jaccard为 [0.0, 0.0, 0.0]。固定候选支持不等于重新发现稳定。

## 策略模拟

| 场景 | 拒绝 | 风险零拒绝 | 假设成本 | 改动事件 |
|---|---:|---:|---:|---:|
| union_decline | 99 | 79 | 8122.62 | 90 |
| intersection_decline | 0 | 0 | 9489.84 | 9 |
| union_review | 9 | 7 | 9044.63 | 84 |
| raised_amount | 93 | 75 | 8620.83 | 96 |

完全审计、拒绝防止全部风险损失、审核无保护、无行为响应，不是生产业务收益。

## 标签可见性

| 机制 | 观察数 | 子集AP | 子集Recall | 全部尝试Recall可识别范围 |
|---|---:|---:|---:|---|
| full_independent_audit | 1968 | 0.2044 | 0.3210 | [0.32098765432098764, 0.32098765432098764] |
| non_declined_only | 1959 | 0.1967 | 0.3125 | [0.3048780487804878, 0.3333333333333333] |
| settled_only | 1786 | 0.1932 | 0.3285 | [0.15, 0.41025641025641024] |
| random_25pct_decline_audit | 1961 | 0.1956 | 0.3125 | [0.3048780487804878, 0.32515337423312884] |

仅随机审计机制的已知概率支持IPW比例估计；确定性零概率缺失不可用IPW识别。当前没有标签缺失纠偏训练、反事实业务收益或拒绝推断。

## 字段工具

实际 8 场景、18次工具调用、28/28验证。LLM used=false；工具执行和失败恢复不等于LLM Agent。输出见 `artifacts/rc1/field-tools/transcript.json`。
