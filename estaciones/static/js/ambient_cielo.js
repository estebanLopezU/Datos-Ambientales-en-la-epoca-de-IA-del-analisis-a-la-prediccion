/* Cielo vivo Ambient — canvas 2D vanilla, sin dependencias.
   Escenas: lluvia|porllover|frio|calor|nublado|despejado|standby
   Momento: dia|noche (hora America/Bogota). */
(function(){
'use strict';
var cv=null,ctx=null,W=0,H=0,raf=null;
var estado={escena:'standby',momento:'dia',intensidad:0.5};
var gotas=[],nubes=[],estrellas=[],copos=[],ondas=[];
function bogotaHora(){try{var f=new Intl.DateTimeFormat('es-CO',{timeZone:'America/Bogota',hour:'numeric',hour12:false});return parseInt(f.format(new Date()),10);}catch(e){return new Date().getHours();}}
function esNoche(d){var h=bogotaHora();if(h<6||h>=18) return true;if(d&&d.radiacion_solar!=null&&d.radiacion_solar<10&&(h<6||h>=17)) return true;return false;}
function estadoClima(d){
  if(!d) return {escena:'standby',momento:(bogotaHora()<6||bogotaHora()>=18?'noche':'dia'),intensidad:0};
  var noche=esNoche(d); var mom=noche?'noche':'dia';
  var s=(d.sensacion!=null?d.sensacion:d.temperatura);
  var hr=d.humedad_relativa, rad=d.radiacion_solar;
  var tasa=d.lluvia_tasa||0, hora=d.lluvia_hora||0;
  if(tasa>0) return {escena:'lluvia',momento:mom,intensidad:Math.min(0.3+tasa*0.4,1)};
  if(hora>0||(hr!=null&&hr>=88)) return {escena:'porllover',momento:mom,intensidad:0.6};
  if(s!=null&&s<=10) return {escena:'frio',momento:mom,intensidad:Math.min((10-s)/10+0.3,1)};
  if(s!=null&&s>=27) return {escena:'calor',momento:mom,intensidad:Math.min((s-27)/8+0.3,1)};
  if(!noche&&rad!=null){
    if(rad<150) return {escena:'nublado',momento:mom,intensidad:0.7};
    if(rad<350||(hr!=null&&hr>70)) return {escena:'nublado',momento:mom,intensidad:0.45};
    return {escena:'despejado',momento:mom,intensidad:0.5};
  }
  if(hr!=null&&hr>80&&!noche) return {escena:'nublado',momento:mom,intensidad:0.5};
  return {escena:'despejado',momento:mom,intensidad:0.5};
}
var NOMBRES={lluvia:['Lloviendo'],porllover:['Por llover'],frio:['Frio'],calor:['Calor'],nublado:['Nublado'],despejado:['Despejado'],standby:['Sin datos']};
var ICONOS={lluvia:'&#127783;&#65039;',porllover:'&#9729;&#65039;',frio:'&#129398;',calor:'&#129397;',nublado:'&#9729;&#65039;',despejado:'&#9728;&#65039;',standby:'&#128164;',luna:'&#127769;'};
function aplicar(e){
  estado=e;
  document.body.setAttribute('data-escena',e.escena);
  document.body.setAttribute('data-momento',e.momento);
  var chip=document.getElementById('chip-clima');
  if(chip){
    var n=NOMBRES[e.escena]||NOMBRES.standby;
    var ico=ICONOS[e.escena]||ICONOS.standby;
    if(e.escena==='despejado'&&e.momento==='noche') ico=ICONOS.luna;
    chip.innerHTML='<span class="dot"></span><span>'+ico+' '+n[0]+(e.momento==='noche'?' - noche':' - dia')+'</span>';
  }
  sembrar();
}
function rnd(a,b){return a+Math.random()*(b-a);}
function sembrar(){
  var n=Math.round(W*H/18000);
  gotas=[];nubes=[];estrellas=[];copos=[];ondas=[];
  var i,k=Math.max(40,Math.min(160,n));
  if(estado.escena==='lluvia'||estado.escena==='porllover'){
    var g=estado.escena==='lluvia'?Math.round(k*estado.intensidad)+30:24;
    for(i=0;i<g;i++) gotas.push({x:rnd(0,W),y:rnd(0,H),l:rnd(12,26),v:rnd(9,20)});
  }
  if(estado.escena==='frio'){
    for(i=0;i<70;i++) copos.push({x:rnd(0,W),y:rnd(0,H),r:rnd(1,3.2),v:rnd(.4,1.6),f:rnd(0,6.28)});
  }
  if(estado.escena==='calor'){
    for(i=0;i<26;i++) ondas.push({x:rnd(0,W),y:rnd(H*.35,H),r:rnd(8,30),v:rnd(.5,1.5),a:rnd(.08,.22)});
  }
  var noc=estado.momento==='noche';
  var nc=estado.escena==='despejado'?4:((estado.escena==='nublado'||estado.escena==='porllover')?9:6);
  for(i=0;i<nc;i++) nubes.push({x:rnd(0,W),y:rnd(H*.02,H*.42),w:rnd(90,240),v:rnd(.15,.6),a:noc?.16:(estado.escena==='nublado'?.5:.3)});
  if(noc){for(i=0;i<110;i++) estrellas.push({x:rnd(0,W),y:rnd(0,H*.7),r:rnd(.4,1.6),p:rnd(0,6.28)});}
}
function dibujar(t){
  ctx.clearRect(0,0,W,H);
  var noche=estado.momento==='noche';
  var i,e;
  if(estrellas.length){for(i=0;i<estrellas.length;i++){e=estrellas[i];var tw=.35+.65*Math.abs(Math.sin(t/900+e.p));ctx.globalAlpha=tw;ctx.fillStyle='#e2e8f0';ctx.beginPath();ctx.arc(e.x,e.y,e.r,0,6.283);ctx.fill();}ctx.globalAlpha=1;}
  if(estado.escena==='despejado'||estrellas.length){
    var ax=W*.86,ay=H*.16;
    if(!noche){var g=ctx.createRadialGradient(ax,ay,4,ax,ay,90);g.addColorStop(0,'rgba(253,224,71,.95)');g.addColorStop(.25,'rgba(251,191,36,.55)');g.addColorStop(1,'rgba(251,191,36,0)');ctx.fillStyle=g;ctx.beginPath();ctx.arc(ax,ay,90,0,6.283);ctx.fill();ctx.fillStyle='#fde047';ctx.beginPath();ctx.arc(ax,ay,22,0,6.283);ctx.fill();}
    else{ctx.fillStyle='rgba(226,232,240,.9)';ctx.beginPath();ctx.arc(ax,ay,20,0,6.283);ctx.fill();ctx.fillStyle='#050a16';ctx.beginPath();ctx.arc(ax-8,ay-5,17,0,6.283);ctx.fill();}
  }
  for(i=0;i<nubes.length;i++){e=nubes[i];e.x+=e.v;if(e.x-e.w>W)e.x=-e.w;
    ctx.globalAlpha=e.a;ctx.fillStyle=noche?'#1e293b':'#94a3b8';
    ctx.beginPath();ctx.ellipse(e.x,e.y,e.w,e.w*.32,0,0,6.283);ctx.ellipse(e.x-e.w*.35,e.y+8,e.w*.5,e.w*.2,0,0,6.283);ctx.ellipse(e.x+e.w*.35,e.y+8,e.w*.5,e.w*.2,0,0,6.283);ctx.fill();ctx.globalAlpha=1;}
  if(estado.escena==='calor'){for(i=0;i<ondas.length;i++){e=ondas[i];e.y-=e.v;if(e.y<H*.1){e.y=H*.95;e.x=rnd(0,W);}ctx.globalAlpha=e.a;ctx.strokeStyle='#fb923c';ctx.lineWidth=2;ctx.beginPath();ctx.arc(e.x,e.y,e.r+6*Math.sin(t/400+e.x),0,6.283);ctx.stroke();}ctx.globalAlpha=1;}
  if(estado.escena==='frio'){ctx.fillStyle='rgba(165,243,252,.85)';for(i=0;i<copos.length;i++){e=copos[i];e.y+=e.v;e.x+=Math.sin(t/800+e.f)*.4;if(e.y>H){e.y=-4;e.x=rnd(0,W);}ctx.beginPath();ctx.arc(e.x,e.y,e.r,0,6.283);ctx.fill();}}
  if(gotas.length){ctx.strokeStyle=estado.escena==='lluvia'?'rgba(96,165,250,.75)':'rgba(148,163,184,.5)';ctx.lineWidth=2;ctx.beginPath();for(i=0;i<gotas.length;i++){e=gotas[i];e.y+=e.v;e.x-=e.v*.18;if(e.y>H){e.y=-20;e.x=rnd(0,W);}ctx.moveTo(e.x,e.y);ctx.lineTo(e.x+e.l*.18,e.y-e.l);}ctx.stroke();}
}
function loop(t){dibujar(t||0);raf=requestAnimationFrame(loop);}
function ajustar(){if(!cv)return;var d=Math.min(window.devicePixelRatio||1,2);ctx.setTransform(1,0,0,1,0,0);W=cv.width=Math.floor(innerWidth);H=cv.height=Math.floor(innerHeight);cv.style.width=innerWidth+'px';cv.style.height=innerHeight+'px';void d;sembrar();}
function demoForzado(){try{var q=new URLSearchParams(location.search);var x=(q.get('demo')||'').toLowerCase();if(NOMBRES[x]){var n=(bogotaHora()<6||bogotaHora()>=18)?'noche':'dia';aplicar({escena:x,momento:n,intensidad:.7});return true;}}catch(e){}return false;}
function init(){
  cv=document.getElementById('cielo');if(!cv)return;ctx=cv.getContext('2d');
  if(!document.body.getAttribute('data-escena'))document.body.setAttribute('data-escena','standby');
  if(!document.body.getAttribute('data-momento'))document.body.setAttribute('data-momento','dia');
  ajustar();addEventListener('resize',ajustar);
  var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(!demoForzado())aplicar({escena:document.body.getAttribute('data-escena'),momento:document.body.getAttribute('data-momento'),intensidad:.5});
  if(!reduce){if(raf)cancelAnimationFrame(raf);raf=requestAnimationFrame(loop);}else dibujar(0);
  document.addEventListener('visibilitychange',function(){if(reduce)return;if(document.hidden){cancelAnimationFrame(raf);raf=null;}else if(!raf)raf=requestAnimationFrame(loop);});
}
window.AmbientCielo={init:init,actualizar:function(d){if(demoForzado())return estado;var s2=null;try{s2=estadoClima(d);}catch(e){s2={escena:'standby',momento:estado.momento,intensidad:0};}aplicar(s2);return s2;},estado:function(){return estado;}};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();

