const path=require('path');const {pathToFileURL}=require('url');
const {chromium}=require('playwright');
// Paths are resolved relative to this script so it runs from any working directory (macOS/Linux/Windows).
const ROOT=path.resolve(__dirname,'..');
const REPLAY=pathToFileURL(path.join(ROOT,'outputs','traffic_project','results','replay.html')).href;
(async()=>{
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
let errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(REPLAY);
await page.setViewportSize({width:1280,height:1000});
await page.locator('#time').fill('240');await page.locator('#time').dispatchEvent('input');
await page.screenshot({path:path.join(ROOT,'work','replay_desktop.png'),fullPage:true});
const initial=await page.locator('#clock').innerText();
await page.locator('#play').click();await page.waitForTimeout(500);await page.locator('#play').click();
const moved=await page.locator('#clock').innerText();
if(initial===moved)throw Error('Replay did not advance');
await page.locator('#scenario').selectOption('heavy');await page.locator('#controller').selectOption('mpc_transformer');
await page.locator('#time').fill('899');await page.locator('#time').dispatchEvent('input');
const pixels=await page.locator('canvas').evaluate(c=>{const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;return new Set(Array.from({length:1000},(_,i)=>a.slice(i*1000,i*1000+3).join(','))).size});
if(pixels<3)throw Error('Blank canvas');
await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(ROOT,'work','replay_mobile.png'),fullPage:true});
const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
if(overflow)throw Error('Mobile overflow');
console.log(JSON.stringify({errors,initial,moved,pixels,overflow,scenario:await page.locator('#scenario').inputValue()}));
await browser.close();if(errors.length)process.exit(1);
})();
