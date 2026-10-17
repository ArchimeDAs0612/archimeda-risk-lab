"""Offline views of saved research evidence; selectors never simulate training."""
import json
from pathlib import Path


def render_study(result, kind, destination):
    if kind not in ['credit', 'selection', 'fields', 'rolling', 'sensitivity']:
        raise ValueError('unknown report kind')
    payload = json.dumps(dict(kind=kind, result=result), ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Archimeda Risk Lab · 可复核研究</title><style>
body{font:16px/1.7 system-ui,sans-serif;background:#f4f8fb;color:#18324a;margin:0}main{max-width:1100px;margin:auto;padding:32px}h1,h2{color:#185c92}section{background:white;padding:22px;margin:20px 0;border:1px solid #d7e2ec}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}th{min-width:140px;width:25%}td{overflow-wrap:anywhere;white-space:pre-wrap}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}select{font:inherit;max-width:100%;padding:6px}.scroll{overflow:auto}.notice{border-left:4px solid #185c92;padding:12px}a{color:#185c92}</style>
<main><h1 id="title">Archimeda Risk Lab · 可复核研究</h1><p class="notice">所有数字来自同一份保存结果。下拉框仅选择已运行的实验，不进行在线训练或调用模型。数据、假设和失败结果均可检查。</p>
<p><a href="result.json">完整结果 JSON</a> · <a href="https://github.com/ArchimeDAs0612/archimeda-risk-lab">代码与复现命令</a></p>
<section><h2>选择已运行的比较</h2><select id="choice" aria-label="已运行的实验"></select><div id="summary" class="scroll"></div></section>
<section><h2>完整条件、失败与边界</h2><div id="details"></div></section>
<section><h2>完整证据</h2><details><summary>展开本次运行的全部聚合结果</summary><pre id="evidence"></pre></details></section></main>
<script id="source" type="application/json">PAYLOAD</script><script>
'use strict';const data=JSON.parse(document.getElementById('source').textContent),r=data.result;
const choice=document.getElementById('choice'), summary=document.getElementById('summary'), details=document.getElementById('details');
function block(target,text){const p=document.createElement('p');p.textContent=text;target.appendChild(p)}
function table(target,rows){const t=document.createElement('table');for(const [k,v] of Object.entries(rows)){const tr=document.createElement('tr'),key=document.createElement('th'),val=document.createElement('td');key.textContent=k;val.textContent=typeof v==='object'?JSON.stringify(v,null,2):String(v);tr.append(key,val);t.appendChild(tr)}target.appendChild(t)}
let options={};if(data.kind==='credit'){
document.getElementById('title').textContent='外部信用数据：模型与Pattern';options=r.models;
block(details,'最终区只评价冻结方案；不是时间外验证、支付误伤实验或因果收益。');
block(details,'冻结规则：'+r.pattern.frozen_rule.predicates.map(p=>p.transformed_feature+' '+p.operator+' '+p.threshold).join(' AND '));
table(details,r.pattern.variants);block(details,'重新发现的选择区Jaccard：'+r.pattern.rediscovery.map(x=>x.selection.jaccard.toFixed(3)).join('、'));
block(details,'删除最后条件产生新候选，支持量必须重新计算。');
table(details,{'配对AP区间':r.paired_ap_vs_lr,'原Brier':r.calibration.original.brier,'校准Brier':r.calibration.sigmoid.brier,'数据质量':r.quality});
}else if(data.kind==='selection'){
document.getElementById('title').textContent='选择性标签、成熟延迟与策略代价';
for(const [name,row] of Object.entries(r.models))options[name]=row;
for(const row of r.policy_scenarios)options['策略 '+row.name+' / 正常需求拒绝成本 '+row.assumptions.legitimate_decline_cost]=row;
block(details,'已知、正概率的随机审计×成熟机制才支持IPW；隐藏真值只供最终模拟评价。');
table(details,{'不可识别机制':r.nonidentification,'冷启动切片':r.cold_start,'模拟边界':r.limitations});
}else if(data.kind==='sensitivity'){
document.getElementById('title').textContent='IPW正则化与错误标签延迟假设';options=r.models;
block(details,'三训练臂在新的预登记种子比较。隐藏真值只供评价；真实依赖结局的观测概率不能由缺失标签自动恢复。');
table(details,{'总体真值':r.oracle_rate,'直接观测均值':r.naive_mean,'错误假设与评价器已知概率':r.delay_summary,'权重总和':r.raw_weight_sum,'归一化权重总和':r.normalized_weight_sum,'限制':r.limitations});
}else if(data.kind==='rolling'){
document.getElementById('title').textContent='滚动时间验证与漂移监控的失败边界';
for(const row of r.windows)options['时间窗 '+row.test_interval.join('—')]=row;
for(const [name,row] of Object.entries(r.monitor.summary))options['监控 '+name]=row;
block(details,'阈值只用参考主体校准；独立主体仍出现误报和漏报。监控报警不能替代模型安全判断。');
table(details,{'实际报警率':r.monitor.summary,'阈值':r.monitor.thresholds,'限制':r.limitations.concat(r.monitor.limits)});
}else{
document.getElementById('title').textContent='字段变更：增量、禁用与失败恢复';options={'变更前':r.before,'变更后':r.after};
block(details,'确定性工具实际执行；没有LLM调用，没有自动语义批准。');table(details,{'验收状态':r.status,'逐项手定期望':r.checks,'失败与恢复记录':r.changes,'限制':r.limits});
}
for(const name of Object.keys(options)){const o=document.createElement('option');o.value=name;o.textContent=name;choice.appendChild(o)}
function update(){summary.replaceChildren();table(summary,options[choice.value]);if(data.kind==='credit')table(summary,{'固定10%容量':r.fixed_capacity[choice.value]})}choice.addEventListener('change',update);update();document.getElementById('evidence').textContent=JSON.stringify(r,null,2);
</script></html>'''.replace('PAYLOAD', payload)
    Path(destination).write_text(page, encoding='utf-8')
