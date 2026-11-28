// Find elements causing horizontal overflow and list broken images.
import { spawn } from "node:child_process";
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = "https://keel-desktop.vercel.app";
const ROUTES = process.argv.slice(2);
const PORT = 9334;
const chrome = spawn(CHROME, ["--headless=new","--disable-gpu","--hide-scrollbars","--no-first-run","--no-default-browser-check",`--remote-debugging-port=${PORT}`,`--user-data-dir=C:/Users/Admin/AppData/Local/Temp/opencode/keel-audit-profile2`,`--window-size=1440,1000`,"about:blank"], {windowsHide:true, stdio:"ignore"});
const sleep = ms => new Promise(r=>setTimeout(r,ms));
let ws;
for (let i=0;i<40;i++){ try { const l=await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p=l.find(t=>t.type==="page"); if(p){ ws=new WebSocket(p.webSocketDebuggerUrl); break; } } catch{} await sleep(250); }
await new Promise(ok=>ws.onopen=ok);
let n=0; const pend=new Map(); ws.onmessage=e=>{const m=JSON.parse(e.data); if(m.id&&pend.has(m.id)){pend.get(m.id)(m.result);pend.delete(m.id);}};
const send=(method,params={})=>new Promise(ok=>{const id=++n;pend.set(id,ok);ws.send(JSON.stringify({id,method,params}));});
for (const r of ROUTES) {
  await send("Page.navigate",{url:BASE+r}); await sleep(1200);
  const expr=`(() => {
    const w = document.documentElement.clientWidth;
    const bad=[...document.querySelectorAll('body *')].filter(e=>{
      const b=e.getBoundingClientRect();
      return b.width>0 && (b.right > w+2 || b.left < -2) && getComputedStyle(e).position!=='fixed';
    }).map(e=>({
      tag:e.tagName.toLowerCase(),
      cls:(e.className && typeof e.className==='string'?e.className:'').slice(0,80),
      id:e.id||'',
      left:Math.round(e.getBoundingClientRect().left),
      right:Math.round(e.getBoundingClientRect().right),
      width:Math.round(e.getBoundingClientRect().width)
    })).slice(0,12);
    const broken=[...document.images].filter(i=>!i.complete||i.naturalWidth===0).map(i=>i.getAttribute('src'));
    return JSON.stringify({w,bad,broken});
  })()`;
  const res=await send("Runtime.evaluate",{expression:expr,returnByValue:true});
  console.log("\n=== "+r+" ===");
  console.log(JSON.stringify(JSON.parse(res.result.value),null,1));
}
ws.close(); chrome.kill();
