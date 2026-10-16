"""Self-contained offline report; every metric comes from actual run artifacts."""
import html
import json
from pathlib import Path


def fmt(value):
    if value is None:
        return "—"
    return f"{value:.4f}" if isinstance(value,float) else html.escape(str(value))


def table(rows, columns):
    return '<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{html.escape(label)}</th>' for _,label in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{fmt(row.get(key))}</td>' for key,_ in columns)+'</tr>' for row in rows)+'</tbody></table></div>'


def pretty(value):
    return '<pre>'+html.escape(json.dumps(value,ensure_ascii=False,indent=2))+'</pre>'


def shell(title, body):
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+html.escape(title)+'''</title><style>
:root{--ink:#18324a;--blue:#185c92;--muted:#60758b;--line:#d7e2ec;--bg:#f4f8fb}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 system-ui,-apple-system,"PingFang SC",sans-serif}main{max-width:1120px;margin:40px auto;padding:40px;background:#fff;border-top:6px solid var(--blue)}h1{font-size:32px;line-height:1.3;margin:12px 0 22px}h2{font-size:23px;margin:42px 0 12px;color:var(--blue)}h3{font-size:18px}p{max-width:88ch}small,.muted{color:var(--muted)}.tag{color:#185c92;letter-spacing:.08em;font-size:13px}.notice{padding:18px 22px;background:#eef5fb;border-left:4px solid #185c92}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}td,th{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{background:#f0f5fa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:20px;font:13px/1.6 ui-monospace,monospace}details{margin:16px 0;border-bottom:1px solid var(--line)}summary{cursor:pointer;padding:10px 0;color:var(--blue)}a{color:var(--blue)}.bars{margin:20px 0}.barrow{display:grid;grid-template-columns:165px 1fr 70px;align-items:center;gap:12px;margin:12px 0;font-size:14px}.track{background:#eaf0f6;height:19px}.fill{background:#2c78ae;height:19px}.rail{border-top:1px solid var(--line);margin-top:40px;padding-top:18px;font-size:13px}@media(max-width:720px){main{margin:0;padding:24px 16px}h1{font-size:26px}.barrow{grid-template-columns:125px 1fr 55px;font-size:12px}}@media print{main{padding:0;margin:0;max-width:none}pre{font-size:10px}.table-wrap{overflow:visible}}
</style></head><body><main><div class="tag">RISK DECISION LAB / SYNTHETIC EXPERIMENT</div><h1>'''+html.escape(title)+'</h1>'+body+'</main></body></html>'


def render_report(result, path):
    gate = result["admission"]
    body = f'<p class="notice">工程执行：{fmt(result["execution"])} · 证据准入：{fmt(gate["evidence_admission"])} · 候选结论：{fmt(result["candidate_verdict"])} · 生产授权：未授予</p>'
    if not gate["allow_model"]:
        body += '<h2>输入触发预定义限制</h2><p>检查流程执行成功，模型比较和候选评估已停止。此页没有可解释为模型有效性的指标。修复输入后须重跑完整链路。</p>'
        body += table(gate["findings"],[("code","风险检查"),("severity","状态"),("message","限制原因")])
        body += '<details><summary>输入、配置与实现指纹</summary>'+pretty(result["provenance"] )+'</details>'
        Path(path).write_text(shell("坏输入被阻断，证据不准入",body),encoding="utf-8")
        return
    winner = result["frozen_selection"]["selected_model_by_selection_ap"]
    gain, final = result["ap_gain"], result["candidate"]["test"]
    body += '<h2>本次实验支持什么</h2>'
    body += f'<p>在选择窗口按 AP 选定 {fmt(winner)}。最终窗口相对 score_lr 的 AP 差为 {fmt(gain["estimate"])}，用户簇重采样区间为 {fmt(gain["ci95"])}。这衡量此合成场景的排序增益，不代表真实支付收益。</p>'
    body += f'<p>完整路径候选在最终窗口覆盖 {final["n"]} 次尝试，其中风险标签 {final["risk_count"]} 次，风险率 {fmt(final["risk_rate"])}；结论为 {fmt(result["candidate_verdict"])}。支持标准预设为选择/测试最小覆盖、测试至少 5 个风险标签，且固定候选对其余样本风险率差的用户簇区间下界大于零。</p>'
    body += '<p>候选用途仅限调查。拒绝后通过不是误伤标签；来源诊断、标签置乱和分层反证不能证明无泄漏或无混淆。重新发现只做 3 次，不能声称稳定规律。本人理解与修改练习尚待本人完成。</p>'
    body += '<h2>问题与数据合同</h2><p>分析单位是一次支付尝试。唯一目标是决策时预测 risk_label；支付结果、后续通过关系、调查候选是不同概念。审计在 2–7 天后完全观察所有尝试，是理想化条件。主体隐藏倾向和随机真值生成量不写入特征，拒绝交易不会被当作正常。</p>'
    body += '<p>原始事件包含用户、订单、设备和 UTC 决策时间。SQL 用 [t−24h,t) 构建用户尝试量，用 [t−7d,t) 与已可见动作构建拒绝量；同时间事件不互相使用。预处理只在训练窗拟合，当前字段采集时间不得晚于决策时间。</p>'
    body += table([dict(window=k,**v) for k,v in result["splits"].items()],[("window","窗口"),("n","样本数"),("positives","风险标签数"),("base_rate","风险率"),("new_subjects","相对训练的新主体事件"),("new_subject_count","新主体数")])
    cfg = result["provenance"]["config"]
    body += f'<p>按相对起始日：训练 [0,{cfg["train_end_day"]})，冻结第 {cfg["train_asof_day"]} 天；选择 [{cfg["select_start_day"]},{cfg["select_end_day"]})，冻结第 {cfg["select_asof_day"]} 天；最终 [{cfg["test_start_day"]},{cfg["days"]})，审计截止第 {cfg["evaluation_asof_day"]} 天。窗口外或未成熟排除 {result["excluded_from_windows"]} 行。已有主体跨窗允许，另列新主体结果。</p>'
    body += '<h2>LR、树模型与信号对照</h2><p>固定浅层 CART 树便于逐条保留路径；LR 使用训练中位数、缺失指示和训练标准化。没有过采样，按自然不平衡基准率评价。AP 是 average precision；另报 ROC-AUC、Brier 和选择窗分位阈值。树叶分数并列可使覆盖超过名义 10%，实际覆盖如下。</p>'
    rows = [dict(model=name,window=window,**v) for name,values in result["model_comparison"].items() for window,v in values.items() if window!="train"]
    body += table(rows,[("model","模型"),("window","窗口"),("ap","AP"),("auc","ROC-AUC"),("brier","Brier"),("flagged_fraction","实际标记比例"),("precision","Precision"),("recall","Recall")])
    body += '<h3>最终窗口 AP（横轴 0–1，静态实测值）</h3><div class="bars" role="img" aria-label="最终窗口各模型 AP 对比">'
    for name, values in result["model_comparison"].items():
        v = values["test"]["ap"]
        body += f'<div class="barrow"><span>{fmt(name)}</span><div class="track"><div class="fill" style="width:{100*v:.5f}%"></div></div><span>{fmt(v)}</span></div>'
    body += '</div><details><summary>新主体 / 已有主体泛化与概率分箱</summary>'+pretty({"subgroups":result["subgroup_metrics"],"calibration":result["calibration"]})+'</details>'
    body += '<h2>完整候选、缺失处理与成员核验</h2><p>以下路径从根节点到叶节点全部保留。谓词作用于训练中位数填补后、附加缺失标记的 float32 输入。每个窗口的全部叶节点回放集合均与模型 apply 成员逐行比较。保存完整精度阈值，不截断路径。</p>'
    body += pretty(result["frozen_selection"])
    body += table([dict(window=k,**v) for k,v in result["candidate"].items()],[("window","窗口"),("n","覆盖"),("risk_count","风险数"),("risk_rate","风险率"),("complement_risk_rate","其余样本风险率"),("difference_cluster_ci95","固定候选差值 95% 区间")])
    body += '<details><summary>完整路径成员一致性与删上游条件差集</summary>'+pretty({"membership":result["membership"],"simplification":result["simplification"]})+'</details>'
    body += '<p>删掉首个条件得到新候选，其差集和指标已重新计算。这是测试后的说明性诊断，没有新留出窗口前不得升级该新候选。选择窗搜叶后区间只作描述；最终窗的区间针对已冻结候选，仍依赖用户簇可代表当前样本的假设。</p>'
    body += '<h2>反证与稳定性边界</h2><p>分层反证在来源 × 预先定义金额带内比较候选与非候选。仅保留两侧至少 5 行的单元，按候选量加权并披露保留量；这不构成因果匹配。训练标签置乱使用选择窗评价；固定候选重采样与重新训练再发现的 Jaccard 分开记录。</p>'
    body += '<details><summary>分层反证、标签置乱、重新发现及漂移明细</summary>'+pretty({"stratified":result["countercheck"],"permutation":result["permutation_controls"],"rediscovery":result["rediscovery"],"drift":result["drift"]})+'</details>'
    body += '<h2>模拟规则与拒绝后通过案例</h2><p>基线规则为同一次事件 amount &gt; 210 且 auth_strength = 0 时拒绝；否则 prior_score &gt; 0.58 时审核，再否则通过。规则条件和动作优先级分开。用户级配对选择窗口内最早的后续支付成功事件，可多对一，也可不同订单。这里只描述关系和窗口敏感度。</p>'
    body += table([dict(hours=k,**v) for k,v in result["case_pairing"].items()],[("hours","小时窗口"),("pairs","配对数"),("same_order","同订单"),("different_order","不同订单"),("unique_later_events","不同后续成功事件数")])
    body += '<details><summary>单事件联合条件与跨事件并集</summary>'+pretty(result["condition_semantics"] )+'</details>'
    body += '<h2>策略回放只是一项假设实验</h2><p>候选拒绝优先于原审核动作。下列成本假设把风险通过视为全额损失、拒绝视为完全避损、审核视为无保护，且无行为响应。标签完全可见才允许这个模拟；数值不是生产收益，也没有上线授权。</p>'
    body += pretty(result["policy_scenario"])
    body += '<h2>可追溯性与复现入口</h2><p>同目录 result.json 是本页指标的来源；predictions.csv 是逐行评价输入；samples.csv、pairs_*h.csv、all_tree_paths.json 和 frozen_selection.json 保留可复算证据。根目录 README 与 docs/learning.md 给出命令、能力映射和三项本人练习。</p>'
    body += f'<p>本次核心链路耗时 {fmt(result["elapsed_seconds"])} 秒（不含环境安装、测试及 HTML 写入）。生产外部有效性、真实标签缺失识别、行为响应和本人独立掌握未验证。</p>'
    body += '<details><summary>配置、数据、代码、依赖指纹</summary>'+pretty(result["provenance"] )+'</details>'
    body += '<p class="rail">Independent implementation · synthetic evidence only · deterministic field workflow, not an LLM Agent</p>'
    Path(path).write_text(shell("从合成支付事件到可核验的调查候选",body),encoding="utf-8")


def render_demo(summary, path):
    body = '<p>正常输入运行完整比较、候选回放与独立后续评价。四类坏输入执行预设检查并阻断结论；修复后重新运行完整链路，核对确定性结果。</p>'
    rows = [{"branch":name,"admission":run["admission"],"verdict":run["candidate_verdict"],"codes":", ".join(run["codes"])} for name,run in summary["branches"].items()]
    body += table(rows,[("branch","分支"),("admission","证据准入"),("verdict","候选结论"),("codes","触发检查")])
    body += '<ul>'+''.join(f'<li><a href="{name}/report.html">{html.escape(name)} 实际运行报告</a></li>' for name in summary["branches"] )+'</ul>'
    body += '<h2>修复重跑一致性</h2>'+pretty(summary["repair_comparison"])
    body += '<p>每个报告自含且可离线打开。汇总页相邻目录链接用于导航；结果来自本次执行，没有在线部署。</p>'
    Path(path).write_text(shell("正常评价、异常限制与修复重跑",body),encoding="utf-8")
