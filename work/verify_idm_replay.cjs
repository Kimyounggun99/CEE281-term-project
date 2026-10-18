const path=require('path');const {pathToFileURL}=require('url');
const {chromium}=require('playwright');
// Paths are resolved relative to this script so it runs from any working directory (macOS/Linux/Windows).
const ROOT=path.resolve(__dirname,'..');
const REPLAY=pathToFileURL(path.join(ROOT,'outputs','traffic_project','results','replay.html')).href;
(async()=>{const b=await chromium.launch({headless:true});const p=await b.newPage({viewport:{width:1280,height:1050}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
await p.goto(REPLAY);await p.waitForFunction(()=>window.replay,null,{timeout:120000});
const result=await p.evaluate(()=>{const r=window.replay;let tracks=0,maximum=0,acceleratingCrossings=0,unchangedCrossings=0;for(const m of Object.values(r.motion))for(const tr of m.tracks){tracks++;const x=tr[3],v=tr[4];maximum=Math.max(maximum,...v);const j=x.findIndex(q=>q>=0);if(j>1&&j+2<v.length){if(v[j+2]>v[j-2]+.1)acceleratingCrossings++;if(Math.abs(v[j+2]-v[j-2])<.01)unchangedCrossings++;}}r.select('balanced','fixed');r.seek(80.3);const a=r.statesAt(80.3),z=r.statesAt(80.4);const moved=a.filter(v=>{const w=z.find(c=>c.id===v.id);return w&&Math.abs(v.s-w.s)>.01}).length;return{tracks,maximum,acceleratingCrossings,unchangedCrossings,moved,outgoing:a.filter(v=>v.outgoing).length}});
await p.screenshot({path:path.join(ROOT,'work','idm_desktop.png'),fullPage:true});await p.locator('#play').click();await p.waitForTimeout(1200);await p.locator('#play').click();const clock=await p.locator('#clock').innerText();
await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(ROOT,'work','idm_mobile.png'),fullPage:true});const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
console.log(JSON.stringify({...result,clock,errors,overflow}));await b.close();if(errors.length||overflow||result.maximum>10.001||!result.moved||!result.unchangedCrossings||!result.acceleratingCrossings)process.exit(1)})();
