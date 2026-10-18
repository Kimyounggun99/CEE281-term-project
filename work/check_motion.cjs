const path=require('path');const {pathToFileURL}=require('url');
const {chromium}=require('playwright');
// Paths are resolved relative to this script so it runs from any working directory (macOS/Linux/Windows).
const ROOT=path.resolve(__dirname,'..');
const REPLAY=pathToFileURL(path.join(ROOT,'outputs','traffic_project','results','replay.html')).href;
(async()=>{
 const b=await chromium.launch({headless:true});const p=await b.newPage({viewport:{width:1280,height:1000}});
 await p.goto(REPLAY);
 const result=await p.evaluate(()=>{
  let releases=0,wrongGreen=0,moving=0;
  for(const scenario of scenarios)for(const controller of controllers){
   $('scenario').value=scenario;$('controller').value=controller;
   events().vehicles.forEach((list,i)=>list.forEach(v=>{if(Number.isFinite(v.departure)){releases++;if(rows()[Math.floor(v.departure-.5)].phase!==`${i<2?0:1}:green`)wrongGreen++;}}));
  }
  $('scenario').value='balanced';$('controller').value='fixed';
  const a=statesAt(80.1),z=statesAt(80.3);
  for(const v of a){const w=z.find(k=>k.id===v.id&&k.approach===v.approach);if(w&&Math.abs(w.s-v.s)>.1)moving++;}
  time=80.3;render();return {releases,wrongGreen,moving,outbound:statesAt(time).filter(v=>v.outgoing).length};
 });
 await p.screenshot({path:path.join(ROOT,'work','motion_desktop.png'),fullPage:true});
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(ROOT,'work','motion_mobile.png'),fullPage:true});
 console.log(result);if(result.wrongGreen||!result.moving||!result.outbound)throw Error('Motion validation failed');await b.close();
})();
