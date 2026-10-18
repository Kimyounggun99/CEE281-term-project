const path=require('path');const {pathToFileURL}=require('url');
const {chromium}=require('playwright');
// Paths are resolved relative to this script so it runs from any working directory (macOS/Linux/Windows).
const ROOT=path.resolve(__dirname,'..');
const REPLAY=pathToFileURL(path.join(ROOT,'outputs','traffic_project','results','replay.html')).href;
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(REPLAY);
 await page.waitForFunction(()=>window.replay,null,{timeout:120000});
 const result=await page.evaluate(()=>{
  const r=window.replay;let maxLength=0,maxInventory=0;
  for(const rows of Object.values(r.data))for(const row of rows){
   maxLength=Math.max(maxLength,...row.lane_queue_length_m.flat());
   maxInventory=Math.max(maxInventory,...row.lane_inventory.flat());
  }
  r.select('heavy','fixed');r.seek(800);
  const ctx=document.querySelector('canvas').getContext('2d'),pixels=ctx.getImageData(0,0,960,960).data;
  const unique=new Set();for(let i=0;i<pixels.length;i+=4)unique.add(`${pixels[i]},${pixels[i+1]},${pixels[i+2]}`);
  return {maxLength,maxInventory,pixelColors:unique.size,spacing:r.motion.heavy_fixed.parameters.approach_length_m};
 });
 await page.screenshot({path:path.join(ROOT,'work','storage_overview.png'),fullPage:true});
 await page.getByRole('slider',{name:'Map zoom'}).fill('3');
 await page.screenshot({path:path.join(ROOT,'work','storage_zoom.png'),fullPage:true});
 await page.getByRole('slider',{name:'Map zoom'}).fill('1');
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:path.join(ROOT,'work','storage_mobile.png'),fullPage:true});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await browser.close();console.log(JSON.stringify({...result,errors,overflow}));
 if(errors.length||overflow||result.maxLength>200.0001||result.maxInventory>30||result.spacing!==200||result.pixelColors<20)process.exit(1);
})();
