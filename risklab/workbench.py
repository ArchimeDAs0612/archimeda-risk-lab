"""Offline interactive research workbench, backed only by this actual run's artifacts."""
import json
from html import escape
from pathlib import Path
import pandas as pd
from .report import shell


def clean_records(frame):
    return json.loads(frame.to_json(orient='records',double_precision=15))


def build_workbench(result,sample,parts,test,field,geometry,out):
    split_by_id={event:split for split,frame in parts.items() for event in frame.event_id}
    view=sample.copy();view['split']=[split_by_id.get(e,'excluded') for e in view.event_id]
    view['cluster']=geometry.assign(view)
    data={'result':result,'events':clean_records(view),'field':field,
      'schema_version':'2.0','similarity':geometry.metadata(),
      'training_event_ids':parts['train'].event_id.tolist(),'test_event_ids':test.event_id.tolist(),
      'scope':'fully independent synthetic data; local research only; no production authority'}
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    directory=Path(__file__).with_name('web');css=(directory/'workbench.css').read_text();js=(directory/'workbench.js').read_text()
    body='''<p class="notice">RUN_VERSION / 真实合成实验 · 冻结后评价 · 本地研究 · 生产授权未授予</p>
    <nav aria-label="研究模块"><button data-panel="events" class="active">交易与案例</button><button data-panel="models">模型实验</button><button data-panel="patterns">Pattern 研究</button><button data-panel="policy">策略回放</button><button data-panel="fields">字段工作流</button><button data-panel="provenance">来源与边界</button></nav>
    <section id="events" class="panel"><h2>从一次尝试出发，检查关联与历史</h2><div id="overview" class="cards"></div>
    <div class="controls"><label>事件 / 用户 / 订单检索<input id="event-search" placeholder="输入模拟标识"></label><label>时间窗口<select id="split-filter"><option value="all">所有事件</option><option value="train">训练</option><option value="select">选择</option><option value="test">最终评价</option><option value="excluded">未入评价窗</option></select></label><label>原策略动作<select id="action-filter"><option value="all">全部</option><option>approve</option><option>review</option><option>decline</option></select></label></div>
    <div id="events-table"></div><div class="pager"><button id="prev-page">上一页</button><span id="page-info"></span><button id="next-page">下一页</button></div>
    <div id="event-detail"></div><h3>Rej→Pass 窗口敏感性</h3><div id="pair-windows"></div><label>实际案例<select id="case-select"></select></label><div id="case-detail"></div><h3>可解释聚类（训练特征拟合，标签仅用于描述）</h3><div id="clusters"></div></section>
    <section id="models" class="panel" hidden><h2>可比输入实验与隔离评价</h2><p id="model-conclusion"></p><label>评价窗口<select id="model-split"><option value="select">选择窗</option><option value="test" selected>最终窗</option><option value="train">训练窗</option></select></label><div id="models-table"></div><div id="model-chart"></div><h3>特征族消融：完整 LR − 移除族 LR</h3><div id="ablations"></div><h3>时间外与来源迁移诊断</h3><div id="temporal"></div><div id="source-transfer"></div><details><summary>分布变化与指标定义</summary><pre id="model-diagnostics"></pre></details></section>
    <section id="patterns" class="panel" hidden><h2>完整路径、独立验证和反证</h2><p id="pattern-conclusion"></p><label>候选完整路径<select id="pattern-select"></select></label><div id="pattern-conditions"></div><div id="pattern-counts"></div><label>诊断性简化<select id="drop-condition"><option value="none">保留全部条件</option></select></label><div id="drop-result"></div><p class="muted">查看其他叶和简化条件是说明性研究；本轮仅冻结候选获得后续独立评价，不能用最终窗重新选最佳规则。</p><h3>金额／来源反证与稳定性</h3><div id="pattern-countercheck"></div><details><summary>阈值、特征敏感性及重新发现</summary><pre id="pattern-diagnostics"></pre></details></section>
    <section id="policy" class="panel" hidden><h2>在最终窗上改规则，检查动作与覆盖</h2><p>每次点击从实际最终窗事件重新计算。完全审计标签只用于事后算术；拒绝阻止所有风险金额损失、审核无保护、无行为响应，均为模拟假设。</p>
    <div class="controls"><label>组合逻辑<select id="policy-mode"><option value="or">原拒绝条件 OR 候选</option><option value="and">原拒绝条件 AND 候选</option><option value="candidate_only">仅候选条件</option></select></label><label>候选动作<select id="policy-action"><option value="decline">拒绝</option><option value="review">审核</option></select></label><label>金额条件 &gt;<input id="policy-amount" type="number" min="0" value="210"></label><label>审核评分 &gt;<input id="policy-review" type="number" min="0" max="1" step="0.01" value="0.58"></label><label>风险损失倍数<input id="cost-risk" type="number" min="0" step="0.1" value="1"></label><label>正常拒绝成本<input id="cost-legit" type="number" min="0" step="0.1" value="4"></label><label>审核成本<input id="cost-review" type="number" min="0" step="0.1" value="0.5"></label></div>
    <label>可选安全规则 JSON（留空采用 Pattern 页当前完整候选）<textarea id="custom-rule" rows="4" placeholder='{"all":[{"field":"amount","op":">","value":100},{"field":"auth_strength","op":"==","value":0}]}'></textarea></label>
    <p class="muted">支持 all / any / not 与五种数值比较；禁止标签、结果、来源和标识，最多 64 节点、8 层。缺失和 float32 映射使用训练预处理。</p><button id="run-policy">运行本地回放</button><button id="export-policy">导出当前回放 JSON</button><p id="policy-error" role="alert"></p><div id="policy-result" aria-live="polite"></div><div id="policy-transitions"></div><details><summary>改变动作的实际事件</summary><pre id="policy-changed"></pre></details></section>
    <section id="fields" class="panel" hidden><h2>Field Intelligence：确定性工具与审核边界</h2><p id="field-conclusion"></p><label>字段检索<input id="field-search" placeholder="字段名、类型或业务域"></label><div id="fields-table"></div><h3>实际执行的字段变更</h3><label>工作流记录<select id="workflow-select"></select></label><pre id="workflow-detail"></pre><h3>禁用传播预演</h3><label>字段或来源<select id="disable-field"></select></label><button id="preview-disable">预演禁用及下游限制</button><div id="disable-result"></div><p class="muted">此按钮在浏览器本地预演真实依赖图；不会保存合同或批准字段。持久化变更使用 README 中的 field-change 命令，候选语义等待人工审核。</p><details><summary>工具生成的训练假设（尚未验证）</summary><pre id="field-hypotheses"></pre></details></section>
    <section id="provenance" class="panel" hidden><h2>证据来源、版本与局限</h2><p>数据、模型、路径和工作流来自本次真实运行。图表与表格从内嵌运行产物计算，无外部请求。修改 Python 后须在新输出目录重新运行，不能只改页面数值。</p><p>聚类不是风险标签；Rej→Pass 不是误伤证据；关联和模拟动作不代表真实业务后果或因果收益。没有实际 LLM 调用。本人技术理解与练习待本人验证。远程 CI、其他环境及外部真实数据未在此页冒称通过。</p><details open><summary>配置及代码／数据／界面指纹</summary><pre id="provenance-detail"></pre></details><a href="result.json">查看本次 result.json</a> · <a href="frozen_selection.json">冻结记录</a> · <a href="field/workflow.json">实际字段工具记录</a></section>
    <p class="rail">Risk Decision Lab · 独立合成研究 / 无生产授权 / AI 协助开发，本人掌握待验证</p>'''
    body=body.replace('RUN_VERSION',escape(result['provenance']['version']))
    document=shell('Risk Decision Intelligence · 研究工作台',body)
    document=document.replace('</style>','\n'+css+'</style>').replace('</body>','<script id="research-data" type="application/json">'+payload+'</script><script>'+js+'</script></body>')
    (Path(out)/'index.html').write_text(document,encoding='utf-8')
