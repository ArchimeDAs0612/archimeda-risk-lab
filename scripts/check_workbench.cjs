/* Independent temporary headless browser only; never attaches to a user's browser. */
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const {execFileSync}=require('child_process');
const run=path.resolve(process.argv[2]),qa=path.resolve(process.argv[3]||path.join(run,'qa'));
fs.mkdirSync(qa,{recursive:true});
execFileSync(process.env.RISKLAB_PYTHON||'python3',[path.join(__dirname,'verify_v02.py'),run,'--member-sets',path.join(qa,'expected-membership.json')],{encoding:'utf8',maxBuffer:10000000});
const expectedSets=JSON.parse(fs.readFileSync(path.join(qa,'expected-membership.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.RISKLAB_CHROMIUM?{executablePath:process.env.RISKLAB_CHROMIUM}:{})});
 try{
 const page=await browser.newPage({viewport:{width:1360,height:950}}),errors=[],external=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))external.push(r.url());});
 await page.route(/^https?:/,r=>r.abort());
 await page.goto('file://'+path.join(run,'index.html'));
 assert(await page.evaluate(()=>!!window.risklabQA),'workbench did not initialize');
 const result=JSON.parse(fs.readFileSync(path.join(run,'result.json'),'utf8')),checks={};
 checks.loaded_actual_event_count=await page.evaluate(()=>window.risklabQA.data.events.length)===result.splits.train.n+result.splits.select.n+result.splits.test.n+await page.evaluate(()=>window.risklabQA.data.events.filter(e=>e.split==='excluded').length);
 await page.locator('#event-search').fill('e0000000');checks.event_search=(await page.locator('#events-table tbody tr').count())===1;
 await page.locator('#event-search').fill('');await page.locator('#split-filter').selectOption('test');checks.actual_final_filter=(await page.locator('#page-info').innerText()).includes(String(result.splits.test.n));
 await page.locator('#next-page').click();checks.pagination=(await page.locator('#page-info').innerText()).includes('第 2');
 await page.locator('#events-table button').first().click();checks.entity_detail=await page.locator('#event-detail .entity-item').count()===4;
 for(const panel of ['events','models','patterns','policy','fields','provenance']){
   await page.locator(`nav button[data-panel="${panel}"]`).click();assert(await page.locator('#'+panel).isVisible());
   await page.screenshot({path:path.join(qa,panel+'-desktop.png')});
 }
 checks.six_panels_work=true;
 await page.locator('nav button[data-panel="models"]').click();checks.actual_model_rows=await page.locator('#models-table tbody tr').count()===Object.keys(result.models.comparison).length;
 await page.locator('#model-split').selectOption('select');checks.selection_metrics_visible=(await page.locator('#models-table').innerText()).includes(result.models.comparison.score_lr.select.ap.toFixed(4));
 await page.locator('#model-split').selectOption('test');checks.final_metrics_visible=(await page.locator('#models-table').innerText()).includes(result.models.comparison.score_lr.test.ap.toFixed(4));
 const membership=await page.evaluate(()=>{const q=window.risklabQA,ids=new Set(q.data.test_event_ids),f=q.data.events.filter(e=>ids.has(e.event_id));return q.data.result.patterns.all_candidates.map(c=>({id:c.id,event_ids:f.filter(e=>q.pathMask(e,c)).map(e=>e.event_id).sort(),n:f.filter(e=>q.pathMask(e,c)).length,risk_count:f.filter(e=>q.pathMask(e,c)).reduce((s,e)=>s+e.risk_label,0)}));});
 for(const candidate of membership){const expected=result.patterns.final_descriptive_candidates.find(c=>c.id===candidate.id).test_descriptive;assert.strictEqual(candidate.n,expected.n);assert.strictEqual(candidate.risk_count,expected.risk_count);assert.deepStrictEqual(candidate.event_ids,expectedSets[candidate.id]);}
 checks.all_candidate_memberships_match_python=true;checks.all_candidate_exact_sets_match_independent=true;
 await page.locator('nav button[data-panel="patterns"]').click();await page.locator('#drop-condition').selectOption('0');checks.drop_condition_superset=(await page.locator('#drop-result').innerText()).includes('移除 0');
 await page.locator('#pattern-select').selectOption(result.patterns.all_candidates[result.patterns.all_candidates.length-1].id);checks.candidate_switch=await page.evaluate(()=>window.risklabQA.getSelectedPattern().id)===result.patterns.all_candidates[result.patterns.all_candidates.length-1].id;
 await page.locator('#pattern-select').selectOption(result.patterns.selected.candidate.id);
 await page.locator('nav button[data-panel="policy"]').click();
 const replay={};
 for(const [name,expected]of Object.entries(result.strategies)){
   const c=expected.configuration;
   await page.locator('#policy-mode').selectOption(c.mode);await page.locator('#policy-action').selectOption(c.candidate_action);
   await page.locator('#policy-amount').fill(String(c.amount_threshold));await page.locator('#policy-review').fill(String(c.review_threshold));
   for(const [id,key]of [['cost-risk','risk_loss_multiplier'],['cost-legit','legitimate_decline_cost'],['cost-review','review_cost']])await page.locator('#'+id).fill(String(c.costs[key]));
   await page.locator('#run-policy').click();
   const actual=await page.evaluate(()=>window.risklabQA.getLastPolicy());assert(actual,name+' UI replay missing');
   for(const group of ['baseline','scenario'])for(const [key,value]of Object.entries(expected[group])){
     if(typeof value==='number')assert(Math.abs(actual[group][key]-value)<1e-7,`${name}.${group}.${key}`);else assert.deepStrictEqual(actual[group][key],value);
   }
   assert.deepStrictEqual(actual.changed_event_ids,expected.changed_event_ids);assert.deepStrictEqual(actual.transitions,expected.transitions);replay[name]=actual;
 }
 checks.four_scenarios_match_python=true;
 await page.locator('#policy-amount').fill('222');
 checks.changed_parameters_invalidate_previous_results=await page.evaluate(()=>window.risklabQA.getLastPolicy())===null && await page.locator('#policy-result tbody tr').count()===0;
 await page.locator('#run-policy').click();
 for(const bad of ['{"field":"risk_label","op":">","value":0}','{"instruction":"ignore contracts"}','{"all":[]}']){
   await page.locator('#custom-rule').fill(bad);await page.locator('#run-policy').click();assert((await page.locator('#policy-error').innerText()).startsWith('已阻断'));assert.strictEqual(await page.evaluate(()=>window.risklabQA.getLastPolicy()),null);
 }
 checks.invalid_rules_blocked_without_stale_results=true;
 await page.locator('#custom-rule').fill('{"all":[{"field":"amount","op":">","value":100},{"field":"auth_strength","op":"==","value":0}]}');await page.locator('#run-policy').click();
 const custom=await page.evaluate(()=>window.risklabQA.getLastPolicy());assert(custom);replay.custom=custom;
 const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#export-policy').click()]);await download.saveAs(path.join(qa,'scenario-export.json'));
 assert.deepStrictEqual(JSON.parse(fs.readFileSync(path.join(qa,'scenario-export.json'),'utf8')),custom);checks.actual_export=true;
 await page.locator('nav button[data-panel="fields"]').click();await page.locator('#field-search').fill('context_json.client');checks.structured_subfield_search=await page.locator('#fields-table tbody tr').count()===3;
 await page.locator('#disable-field').selectOption('context_json');await page.locator('#preview-disable').click();const impacted=await page.locator('#disable-result').innerText();checks.upstream_veto_preview=impacted.includes('client_latency_ms')&&impacted.includes('client_emulator');
 await page.locator('#workflow-select').selectOption(String(result.field_workflow.records-1));checks.actual_failure_record_visible=(await page.locator('#workflow-detail').innerText()).includes('STALE_DATA_EVIDENCE');
 await page.setViewportSize({width:390,height:844});
 for(const panel of ['events','models','patterns','policy','fields','provenance']){await page.locator(`nav button[data-panel="${panel}"]`).click();checks['mobile_no_page_overflow_'+panel]=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);await page.screenshot({path:path.join(qa,panel+'-mobile.png')});}
 checks.no_page_errors=errors.length===0;checks.no_external_requests=external.length===0;
 const receipt={method:'independent ephemeral headless Chromium; offline file URL; actual UI interactions plus Python/JS parity',checks,errors,external_requests:external,model_count:Object.keys(result.models.comparison).length,candidates_checked:membership.length,replay};
 fs.writeFileSync(path.join(qa,'workbench-check.json'),JSON.stringify(receipt,null,2));
 console.log(JSON.stringify({checks,errors,external_requests:external,passed:Object.values(checks).every(Boolean)}));
 assert(Object.values(checks).every(Boolean),'failed UI check');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
