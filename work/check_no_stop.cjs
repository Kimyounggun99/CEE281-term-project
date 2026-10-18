const path=require('path');const {pathToFileURL}=require('url');
const {chromium}=require('playwright');
// Paths are resolved relative to this script so it runs from any working directory (macOS/Linux/Windows).
const ROOT=path.resolve(__dirname,'..');
const REPLAY=pathToFileURL(path.join(ROOT,'outputs','traffic_project','results','replay.html')).href;
(async()=>{const b=await chromium.launch({headless:true});const p=await b.newPage();await p.goto(REPLAY);
const result=await p.evaluate(()=>{let checked=0,failures=[];for(const sc of scenarios)for(const co of controllers){$('scenario').value=sc;$('controller').value=co;events().vehicles.forEach((vs,i)=>{for(const v of vs.filter(v=>v.freeFlow).slice(0,25)){const release=v.departure-.5;const positions=[-.2,-.1,0,.1].map(dt=>statesAt(release+dt).find(c=>c.approach===i&&c.id===v.id)?.s);if(positions.some((s,k)=>Math.abs(s-[-20,-10,0,10][k])>1e-6))failures.push({sc,co,id:v.id,positions});checked++;}})}return{checked,failures}});console.log(JSON.stringify(result));await b.close();if(result.failures.length)process.exit(1)})();
