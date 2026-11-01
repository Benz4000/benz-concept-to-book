// V11 local reading harness. Invoked only by verify_release.py with explicit tools.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {createRequire} from 'node:module';
const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const require=createRequire(import.meta.url);
const {chromium}=require(cfg.playwright_module);
const packageInfo=require(path.join(path.dirname(cfg.playwright_module),'package.json'));
const root=path.resolve(cfg.root),output=path.resolve(cfg.output);
const mime={'.xhtml':'application/xhtml+xml','.html':'text/html','.css':'text/css','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.ttf':'font/ttf','.otf':'font/otf','.svg':'image/svg+xml'};
const allowed=new Set(cfg.resources);
const requests=[],errors=[],checks=[],screenshots=[];
const server=http.createServer((req,res)=>{
  try {
    const relative=decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1);
    if(!allowed.has(relative)){res.writeHead(404);res.end();return;}
    const file=path.resolve(root,...relative.split('/'));
    if(!file.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Content-Security-Policy':"default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self'; font-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",'Cache-Control':'no-store'});
    res.end(fs.readFileSync(file));
  }catch(e){res.writeHead(500);res.end(String(e));}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
const watchdog=setTimeout(()=>{console.error('Reader harness deadline exceeded');if(browser)browser.close().finally(()=>process.exit(2));else process.exit(2);},cfg.timeout_seconds*1000);
watchdog.unref();
try {
  browser=await chromium.launch({executablePath:cfg.browser,headless:true,timeout:30000});
  const context=await browser.newContext({acceptDownloads:false,serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const u=new URL(route.request().url());
    if(u.origin===origin&&allowed.has(decodeURIComponent(u.pathname).slice(1)))return route.continue();
    requests.push({url:route.request().url(),state:'blocked'});return route.abort();
  });
  const page=await context.newPage();page.setDefaultTimeout(10000);
  page.on('pageerror',error=>errors.push(String(error)));
  const urlFor=relative=>origin+'/'+relative.split('/').map(encodeURIComponent).join('/');
  const inspect=async()=>page.evaluate(()=>{
    const style=e=>getComputedStyle(e),rect=e=>e.getBoundingClientRect();
    const content=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,table,img')];
    return {title:document.title,text:document.body.innerText,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,
      hidden:content.filter(e=>style(e).display==='none'||style(e).visibility==='hidden').length,
      overflowing:content.filter(e=>rect(e).width>0&&(rect(e).left< -2||rect(e).right>innerWidth+2)).map(e=>({tag:e.tagName,text:(e.textContent||'').slice(0,100)})),
      images:[...document.images].map(e=>({src:e.getAttribute('src'),loaded:e.complete&&e.naturalWidth>0,alt:e.getAttribute('alt')}))};
  });
  for(let di=0;di<cfg.documents.length;di++){
    const doc=cfg.documents[di];
    for(let ci=0;ci<cfg.conditions.length;ci++){
      const condition=cfg.conditions[ci];await page.setViewportSize({width:condition.width,height:condition.height});
      await page.goto(urlFor(doc),{waitUntil:'networkidle'});
      // Font scaling is an explicit harness condition, not an emulated named reader.
      await page.evaluate(scale=>{for(const e of document.querySelectorAll('body *'))if(e.children.length===0||/^(P|H[1-6]|TH|TD|LI)$/.test(e.tagName))e.dataset.v11Size=getComputedStyle(e).fontSize;for(const e of document.querySelectorAll('[data-v11-size]'))e.style.fontSize=(parseFloat(e.dataset.v11Size)*scale)+'px';},condition.text_scale);
      await page.evaluate(()=>document.fonts.ready);
      const before=await inspect();
      const file=`document-${di+1}-condition-${ci+1}.png`;
      await page.screenshot({path:path.join(output,file),fullPage:false});screenshots.push({path:file,document:doc,condition,scope:'viewport only'});
      checks.push({kind:'reflow',document:doc,condition,passed:before.scrollWidth<=before.clientWidth+2&&before.overflowing.length===0&&before.hidden===0&&before.images.every(i=>i.loaded),observation:before});
    }
    await page.goto(urlFor(doc),{waitUntil:'networkidle'});
    const links=await page.locator('a[href]').evaluateAll(elements=>elements.map((a,index)=>({index,href:a.getAttribute('href'),label:a.textContent})));
    if(links.length>500)throw new Error('Document exceeds 500-link test bound');
    for(const link of links){
      const destination=new URL(link.href,urlFor(doc));
      if(destination.origin!==origin){checks.push({kind:'external-link',document:doc,href:link.href,state:'not-fetched'});continue;}
      await page.goto(urlFor(doc),{waitUntil:'networkidle'});
      let passed=false,observed;
      try {
        await page.locator('a[href]').nth(link.index).click({noWaitAfter:false});
        await page.waitForURL(destination.href);
        const id=decodeURIComponent(destination.hash.slice(1));
        observed=await page.evaluate(id=>{const e=id?document.getElementById(id):document.body;return {exists:!!e,text:e?.textContent?.slice(0,300),visible:!!e&&getComputedStyle(e).display!=='none'&&getComputedStyle(e).visibility!=='hidden',url:location.href};},id);
        passed=observed.exists&&observed.visible&&new URL(observed.url).href===destination.href;
      }catch(error){observed={error:String(error)};}
      checks.push({kind:'navigation',document:doc,href:link.href,label:link.label,passed,observation:observed});
    }
  }
  const report={schema_version:1,adapter:'v11-reader-probe',state:checks.every(c=>c.passed!==false)&&errors.length===0?'passed':'failed',browser_version:browser.version(),playwright_version:packageInfo.version,checks,screenshots,blocked_requests:requests,errors,
    limitations:'Local Chromium reading harness of HTML or exact extracted EPUB spine documents. Viewport captures and measured geometry/link clicks do not establish semantic link correctness, named EPUB app/device behavior, full visual inspection, assistive usability, or human reading.'};
  fs.writeFileSync(path.join(output,'reader-probe.json'),JSON.stringify(report,null,2));
}finally{clearTimeout(watchdog);if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
