const path=require('path');const {pathToFileURL}=require('url');
const {chromium}=require('playwright');
// Paths are resolved relative to this script so it runs from any working directory (macOS/Linux/Windows).
const ROOT=path.resolve(__dirname,'..');
const REPLAY=pathToFileURL(path.join(ROOT,'outputs','traffic_project','results','replay.html')).href;
(async()=>{
 const b=await chromium.launch({headless:true});const p=await b.newPage({viewport:{width:1280,height:1050}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(REPLAY);
 const result=await p.evaluate(()=>{
  let releases=0,wrongGreen=0,continuous=0,stops=0;
  for(const sc of scenarios)for(const co of controllers){
   $('scenario').value=sc;$('controller').value=co;
   if(laneCount()!==2||events().vehicles.length!==8)throw Error('Expected eight inbound lanes');
   events().vehicles.forEach((list,channel)=>{
    list.forEach(v=>{if(Number.isFinite(v.departure)){releases++;if(rows()[v.departure-1].phase!==`${channel<4?0:1}:green`)wrongGreen++;}});
    for(const v of list.filter(v=>v.freeFlow).slice(0,10)){
     const positions=[-.2,-.1,0,.1].map(dt=>statesAt(v.departure-.5+dt).find(c=>c.channel===channel&&c.id===v.id)?.s);
     if(positions.some((s,k)=>s===undefined||Math.abs(s-[-20,-10,0,10][k])>1e-6))stops++;
     continuous++;
    }
   });
  }
  $('scenario').value='balanced';$('controller').value='fixed';time=180.3;render();
  const visibleChannels=[...new Set(statesAt(time).map(c=>c.channel))];
  return {releases,wrongGreen,continuous,stops,visibleChannels};
 });
 await p.screenshot({path:path.join(ROOT,'work','two_lanes_desktop.png'),fullPage:true});
 const before=await p.locator('#clock').innerText();await p.locator('#play').click();await p.waitForTimeout(600);await p.locator('#play').click();const after=await p.locator('#clock').innerText();
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(ROOT,'work','two_lanes_mobile.png'),fullPage:true});
 const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 console.log(JSON.stringify({...result,errors,before,after,overflow}));await b.close();
 if(errors.length||result.wrongGreen||result.stops||result.visibleChannels.length!==8||overflow||before===after)process.exit(1);
})();
