// Lane F only: real Tauri Android UI, native selection/confirmation and HTTPS.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { connect } = require('../mobile/cdp.cjs');
const ui = require('../mobile/adb-ui.cjs');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const expected = require('./fixture/expected.json');

async function wait(cdp, text, budget = 120000) {
  const end = Date.now() + budget;
  while (Date.now() < end) {
    if ((await cdp.bodyText()).includes(text)) return;
    await pause(300);
  }
  throw new Error(`UI_TIMEOUT:${text}`);
}
async function click(cdp, text) {
  const end = Date.now() + 15000;
  while (Date.now() < end) {
    if (await cdp.evaluate(`(() => {
      const b=[...document.querySelectorAll('button')].find(n=>n.innerText.trim()===${JSON.stringify(text)}&&!n.disabled);
      if(!b)return false;b.scrollIntoView({block:'center'});b.click();return true;
    })()`)) return;
    await pause(250);
  }
  throw new Error(`BUTTON_UNAVAILABLE:${text}`);
}
async function prepare(cdp) {
  const collection = {version:'privacytrace-policy-collector/1',results:[{state:'PROVIDED',source:{
    id:'lane-f-policy',title:'Lane F synthetic policy',source_type:'OFFICIAL_WEB_POLICY',
    text:expected.policy_quote,package_name:expected.package_name,version:'UNKNOWN',region:'',product:''
  }}]};
  await cdp.evaluate(`document.querySelector('details.policy-assist').setAttribute('open','')`);
  await cdp.evaluate(`(()=>{const e=document.querySelector('#collector-result');e.value=${JSON.stringify(JSON.stringify(collection))};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await pause(300);
  await click(cdp,'检查回填内容');
  await wait(cdp,'确认来源类型后补入当前材料');
  await click(cdp,'确认并补入材料');
  await wait(cdp,'来源和未检查候选已补入');
  await click(cdp,'自动准备政策并继续');
  await wait(cdp,'保存候选并开始分析');
  await click(cdp,'Lane F synthetic policy');
  await click(cdp,'添加候选');
  await cdp.evaluate(`(()=>{
    for(const [s,v,event] of ${JSON.stringify([
      ['#candidate-quote',expected.policy_quote,'input'],['#candidate-type',expected.data_type,'change'],
      ['#candidate-subject','APP','change'],['#candidate-action','ACCESS','change']
    ])}){const e=document.querySelector(s);if(!e)throw Error('CANDIDATE_FIELD');e.value=v;e.dispatchEvent(new Event(event,{bubbles:true}));}
  })()`);
  await pause(300);
  await click(cdp,'保存候选');
  await wait(cdp,'候选声明 1');
}
async function main() {
  const [action,config] = process.argv.slice(2);
  if(!config || !process.env.PT_ADB_SERIAL)throw Error('Explicit config and PT_ADB_SERIAL required');
  const options=JSON.parse(fs.readFileSync(config,'utf8'));
  if(options.origin!=='https://127.0.0.1:28453'||!Number.isInteger(options.cdpPort)||!options.output||!/^[A-Za-z0-9-]+$/.test(options.runId))throw Error('F_CONFIG_REQUIRED');
  if(ui.run(['emu','avd','name']).split(/\r?\n/)[0].trim()!=='privacytrace-issue134-f')throw Error('F_AVD_REQUIRED');
  fs.mkdirSync(options.output,{recursive:true});
  if(action==='upload') {
    ui.run(['shell','am','force-stop','org.privacytrace.mobile']);
    ui.run(['shell','pm','clear','org.privacytrace.mobile']);
    ui.openApp();await pause(2500);
  }
  const end=Date.now()+30000;
  while(true){try{ui.forwardDevtools(options.cdpPort);break;}catch(error){if(Date.now()>=end)throw error;await pause(300);}}
  const cdp=await connect(options.cdpPort);
  try {
    if(action==='upload') {
      await click(cdp,'选择应用并上传');ui.waitText('选择上传实例',{timeoutMs:30000});
      ui.clearAndType(options.origin);ui.tapText('检查并继续');
      ui.waitText('选择要读取的应用',{timeoutMs:60000});ui.tapText('Issue 134 controlled fixture');
      ui.waitText('确认上传所选应用',{timeoutMs:60000});ui.tapText('确认上传');
      await wait(cdp,'政策来源',180000);
    } else if(action==='prepare')await prepare(cdp);
    else if(action==='start'){await click(cdp,'保存候选并开始分析');await wait(cdp,'刷新进度');}
    else if(action==='refresh')await click(cdp,'刷新进度');
    else if(action==='report'){await wait(cdp,'查看报告',180000);await click(cdp,'查看报告');await wait(cdp,'隐私声明对照');}
    else if(action==='drill'){
      await cdp.clickText('查看 2 条证据');await pause(500);
    }
    else if(action==='delete'){
      await click(cdp,'删除远端材料');ui.waitText('删除远端材料',{timeoutMs:30000});
      ui.clearAndType(options.origin);ui.tapText('检查并继续');
      ui.waitText('确认删除远端材料',{timeoutMs:30000});ui.tapText('确认删除');
      await wait(cdp,'选择应用并上传');
    } else if(action!=='snapshot')throw Error('Unknown F action');
    await pause(600);
    const body=await cdp.bodyText();
    const prefix=path.join(options.output,`${options.runId}-${action}-${Date.now()}`);
    fs.writeFileSync(prefix+'.txt',body);await cdp.screenshot(prefix+'.png');
    const result={at_utc:new Date().toISOString(),action,status:'OBSERVED',case_passed:false,
      body_sha256:crypto.createHash('sha256').update(body).digest('hex'),
      scope_aliases:[...new Set(body.match(/\b[a-f0-9]{32}\b/g)||[])].map(id=>crypto.createHash('sha256').update(id).digest('hex')),
      report_button:body.includes('查看报告'),error_visible:!!await cdp.evaluate(`document.querySelector('[role="alert"]')?.textContent?.trim()`)};
    fs.writeFileSync(prefix+'.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  } finally { await cdp.close(); }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
