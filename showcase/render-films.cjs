/* Deterministic 1080p renderer for the two authored films.
 * node showcase/render-films.cjs 90s|review check|stills|render [workers=4]
 * Uses the repository's Playwright and ffmpeg/ffprobe from PATH.
 * All intermediates go under ignored tmp/film-render/. No server is needed.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const { spawn, execFileSync } = require('node:child_process');
const { once } = require('node:events');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..');
const films = {
  '90s': {html:'showcase/privacytrace-90s/film-showcase.html', audio:'showcase/privacytrace-90s/assets/soundtrack-polished.m4a', out:'showcase/privacytrace-90s/delivery/PrivacyTrace-作品展示-90s.mp4', dur:90, times:[5,15,20,20.5,21,21.35,21.6,22.5,25,31,39,43,50,58,66,70,79,87], boundaries:[9,21,45,60,72,84]},
  review: {html:'showcase/privacytrace-review/delivery/film-review.html', audio:'showcase/privacytrace-review/delivery/assets/soundtrack-polished.m4a', out:'showcase/privacytrace-review/delivery/PrivacyTrace-Review-1080p.mp4',dur:120,times:[4,8.5,16,26,35,43,47,50,54,58,62,70,77,85,93,97,104,116],boundaries:[9.375,21.875,40.625,65,90,108.75]}
};
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function assetInputs(){
  const base=path.join(path.dirname(path.join(ROOT,f.html)),'assets');
  const files=[];
  function walk(folder){
    for(const entry of fs.readdirSync(folder,{withFileTypes:true})){
      const p=path.join(folder,entry.name);
      if(entry.isDirectory())walk(p);else files.push(p);
    }
  }
  walk(base);
  const bindings=files.map(p=>path.relative(base,p).replaceAll('\\','/')+'\0'+hash(fs.readFileSync(p))).sort();
  return {path:path.relative(ROOT,base).replaceAll('\\','/'),files:files.length,sha256:hash(Buffer.from(bindings.join('\n')))};
}
const [name,mode='check',workerArg='4']=process.argv.slice(2);
const f=films[name];
if(!f || !['check','stills','render'].includes(mode)) throw new Error('Usage: node showcase/render-films.cjs 90s|review check|stills|render [workers=4]');
const dir=path.join(ROOT,'tmp','film-render',name);
fs.mkdirSync(dir,{recursive:true});
async function pageFor(browser){
  const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(pathToFileURL(path.join(ROOT,f.html)).href);
  await page.waitForFunction(()=>window.__ready===true);
  const missing=await page.evaluate(()=>Array.from(document.images).filter(i=>!i.complete||!i.naturalWidth).map(i=>i.getAttribute('src')));
  if(missing.length)throw new Error('Missing images: '+missing);
  return {page,errors};
}
async function shot(page,t){
  await page.evaluate(t=>window.__seek(t),t);
  return page.screenshot({type:'png',animations:'disabled'});
}
async function checks(){
  const sourceSha256=hash(fs.readFileSync(path.join(ROOT,f.html))), inputAssets=assetInputs();
  const browser=await chromium.launch();
  try{
    const {page,errors}=await pageFor(browser);
    const times=[...new Set([...f.times,...f.boundaries.flatMap(t=>[t-.1,t,t+.1])])];
    const reference=new Map();
    for(const t of times){reference.set(t,hash(await shot(page,t)));}
    // A reverse pass exercises cross-scene seeks and the async frame bank.
    for(const t of [...times].reverse()){
      if(hash(await shot(page,t))!==reference.get(t))throw new Error('History-dependent frame at '+t);
      if(hash(await shot(page,t))!==reference.get(t))throw new Error('Unstable repeated seek at '+t);
    }
    if(name==='90s'){
      const frames=[];
      for(const t of [22.5,25,31,39,43]){
        await page.evaluate(t=>window.__seek(t),t);
        frames.push(hash(await page.locator('#shot').screenshot({type:'png'})));
      }
      if(new Set(frames).size!==5)throw new Error('Operation footage has repeated/frozen states');
    }
    if(errors.length)throw new Error(errors.join('\n'));
    if(hash(fs.readFileSync(path.join(ROOT,f.html)))!==sourceSha256 || JSON.stringify(assetInputs())!==JSON.stringify(inputAssets))throw new Error('Inputs changed while checking');
    const result={film:name,deterministic:true,exactPixels:true,missingAssets:[],pageErrors:[],times,sourceSha256,inputAssets};
    fs.writeFileSync(path.join(dir,'seek-check.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result));
  }finally{await browser.close();}
}
async function stills(){
  const browser=await chromium.launch();
  try{
    const {page,errors}=await pageFor(browser);
    for(const t of f.times)fs.writeFileSync(path.join(dir,`still-${t}.png`),await shot(page,t));
    if(errors.length)throw new Error(errors.join('\n'));
    console.log('stills',dir);
  }finally{await browser.close();}
}
async function render(){
  const sourceSha256=hash(fs.readFileSync(path.join(ROOT,f.html))), audioSha256=hash(fs.readFileSync(path.join(ROOT,f.audio))), inputAssets=assetInputs();
  const workers=Math.max(1,Math.min(4,Number(workerArg)||4));
  const count=f.dur*30;
  const chunks=[];
  await Promise.all(Array.from({length:workers},async(_,k)=>{
    const start=Math.floor(count*k/workers), end=Math.floor(count*(k+1)/workers);
    const target=path.join(dir,`chunk-${k}.mp4`);chunks[k]=target;
    const browser=await chromium.launch();
    try{
      const {page,errors}=await pageFor(browser);
      const ff=spawn('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','image2pipe','-framerate','30','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-threads','2','-pix_fmt','yuv420p',target],{stdio:['pipe','ignore','pipe'],windowsHide:true});
      let log='';ff.stderr.on('data',b=>{log+=b;});
      const done=once(ff,'close');
      for(let frame=start;frame<end;frame++){
        const buffer=await shot(page,frame/30);
        if(!ff.stdin.write(buffer))await once(ff.stdin,'drain');
        if((frame-start)%300===0)console.log(`${name} worker ${k}: ${frame-start}/${end-start}`);
      }
      ff.stdin.end();const [code]=await done;
      if(code!==0)throw new Error(log);
      if(errors.length)throw new Error(errors.join('\n'));
    }finally{await browser.close();}
  }));
  const list=path.join(dir,'concat.txt');
  fs.writeFileSync(list,chunks.map(p=>`file '${p.replaceAll('\\','/')}'`).join('\n'));
  execFileSync('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',list,'-i',path.join(ROOT,f.audio),'-map','0:v:0','-map','1:a:0','-c','copy','-t',String(f.dur),'-movflags','+faststart',path.join(ROOT,f.out)]);
  // Complete decode, including audio, rather than trusting container metadata.
  execFileSync('ffmpeg',['-v','error','-xerror','-i',path.join(ROOT,f.out),'-f','null','-']);
  if(hash(fs.readFileSync(path.join(ROOT,f.html)))!==sourceSha256 || JSON.stringify(assetInputs())!==JSON.stringify(inputAssets))throw new Error('Inputs changed while rendering');
  const proof={film:name,renderer:'showcase/render-films.cjs',width:1920,height:1080,fps:30,frames:count,workers,shutter:0,sourceSha256,audioSha256,inputAssets,sha256:hash(fs.readFileSync(path.join(ROOT,f.out))),decode:'passed'};
  fs.writeFileSync(path.join(dir,'render.json'),JSON.stringify(proof,null,2)+'\n');
  console.log(JSON.stringify(proof));
}
(mode==='check'?checks():mode==='stills'?stills():render()).catch(e=>{console.error(e);process.exitCode=1;});
