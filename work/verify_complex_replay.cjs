// Exercise the embedded replay without browser dependencies; canvas rasterization is not checked.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const file=process.argv[2]||path.join(__dirname,'../outputs/traffic_project/results_complex/replay.html');

(async()=>{
 const elements=new Map(),errors=[];
 const context=new Proxy({},{get:(target,key)=>target[key]||(()=>{}),set:(target,key,value)=>(target[key]=value,true)});
 function element(id){
  if(!elements.has(id))elements.set(id,{
   options:[],_value:'',textContent:'',
   get value(){return this._value||this.options[0]?.value||''},set value(value){this._value=String(value)},
   set innerHTML(value){this.options=[]},add(option){this.options.push(option)},getContext:()=>context
  });
  return elements.get(id);
 }
 element('zoom').value='1.6';element('speed').value='1';
 const window={};let frame;
 const script=fs.readFileSync(file,'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
 await vm.runInNewContext(script,{window,document:{getElementById:element},
  Option:function(text,value){this.text=text;this.value=value},Uint8Array,atob,Blob,Response,DecompressionStream,
  requestAnimationFrame:callback=>{frame=callback},console:{error:error=>errors.push(String(error))}});
 assert.deepEqual(errors,[]);assert.ok(window.replay,'Replay payload failed to load');
 const replay=window.replay,headings={N:[-1,0],S:[1,0],E:[0,-1],W:[0,1]};
 const modes=['protected_permissive','protected','permissive'],controllers=['mpc_transformer','responsive','fixed'];
 let selections=0,rights=0;
 for(const [key,motion] of Object.entries(replay.motion)){
  const mode=modes.find(m=>key.startsWith(m+'_')),controller=controllers.find(c=>key.endsWith('_'+c));
  const scenario=key.slice(mode.length+1,-controller.length-1);
  replay.select(mode,scenario,controller);selections++;
  assert.ok(element('sub').textContent.includes('TR'));
  for(const time of [0,1,60,180,replay.data[key].length])replay.seek(time);
  const last=replay.data[key].at(-1);
  assert.equal(element('throughput').textContent,`${last.throughput.reduce((a,b)=>a+b,0)} (${last.left_throughput.reduce((a,b)=>a+b,0)} / ${last.right_throughput.reduce((a,b)=>a+b,0)})`);
  for(const [id,channel,start,xs,,,movement] of motion.tracks){
   if(movement!==2)continue;
   const i=xs.findIndex(x=>x>motion.layout.right_path_m+motion.parameters.vehicle_length_m/2+1);
   if(i<0)continue;
   // Stay inside the sampled interval despite rounding at its final timestamp.
   const time=start+i*motion.dt_s-1e-8,car=replay.statesAt(time).find(c=>c.id===id);
   assert.ok(car,`${key}: vehicle ${id}, sample ${i}/${xs.length-1}`);
   const approach=motion.layout.channels[channel][0],[dx,dy]=headings[approach];
   assert.ok(Math.abs(Math.cos(car.ang)-dx)<1e-6&&Math.abs(Math.sin(car.ang)-dy)<1e-6,`${key}: ${approach} right took the wrong exit`);
   assert.ok(Number.isFinite(car.x)&&Number.isFinite(car.y));rights++;
  }
 }
 assert.ok(rights>0,'No completed right-turn paths checked');
 replay.seek(10);element('play').onclick();frame(100);frame(200);
 assert.ok(Number.parseFloat(element('clock').textContent)>10,'Playback clock did not advance');
 element('play').onclick();element('reset').onclick();assert.equal(element('clock').textContent,'0.0 s');
 console.log(JSON.stringify({status:'passed',selections,rightTurnPaths:rights,rasterization:'not checked'}));
})().catch(error=>{console.error(error);process.exitCode=1});
