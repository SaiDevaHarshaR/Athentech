/* Sahasra Admin — premium layer: 3D backdrop, hero globe, tilt, spotlight, count-up. Off: ?premium=off */
(function(){
  if(/[?&]premium=off/.test(location.search)){try{localStorage.setItem('pxOff','1')}catch(e){}}
  if(/[?&]premium=on/.test(location.search)){try{localStorage.removeItem('pxOff')}catch(e){}}
  try{if(localStorage.getItem('pxOff'))return}catch(e){}
  var de=document.documentElement; de.classList.add('px');
  var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $=function(s,r){return (r||document).querySelector(s)}, $$=function(s,r){return [].slice.call((r||document).querySelectorAll(s))};
  var dark=function(){return de.getAttribute('data-theme')!=='light'};
  var mouse={x:.5,y:.5};
  addEventListener('pointermove',function(e){mouse.x=e.clientX/innerWidth;mouse.y=e.clientY/innerHeight},{passive:true});

  /* tiny 3D engine: rotate points, perspective project */
  function rot(p,ax,ay){var c=Math.cos(ay),s=Math.sin(ay),x=p[0]*c+p[2]*s,z=-p[0]*s+p[2]*c,c2=Math.cos(ax),s2=Math.sin(ax),y=p[1]*c2-z*s2;z=p[1]*s2+z*c2;return [x,y,z]}
  function sphere(n){var pts=[],g=Math.PI*(3-Math.sqrt(5));for(var i=0;i<n;i++){var y=1-2*i/(n-1),r=Math.sqrt(1-y*y),t=g*i;pts.push([Math.cos(t)*r,y,Math.sin(t)*r])}return pts}
  function fit(cv){var d=Math.min(devicePixelRatio||1,2);cv.width=cv.clientWidth*d;cv.height=cv.clientHeight*d;return d}

  /* page backdrop: drifting particles + connecting lines */
  function backdrop(){
    var cv=document.createElement('canvas');cv.id='pxBg';document.body.insertBefore(cv,document.body.firstChild);
    var x=cv.getContext('2d'),d=fit(cv),P=[],N=innerWidth<700?30:64;
    for(var i=0;i<N;i++)P.push({x:Math.random(),y:Math.random(),z:Math.random(),vx:(Math.random()-.5)*2e-4,vy:(Math.random()-.5)*2e-4});
    addEventListener('resize',function(){d=fit(cv)});
    (function f(){
      if(document.hidden){return requestAnimationFrame(f)}
      var w=cv.width,h=cv.height;x.clearRect(0,0,w,h);var col=dark()?'160,150,255':'106,92,246';
      for(var i=0;i<N;i++){var p=P[i];p.x+=p.vx+(mouse.x-.5)*2e-5*p.z;p.y+=p.vy;if(p.x<0)p.x=1;if(p.x>1)p.x=0;if(p.y<0)p.y=1;if(p.y>1)p.y=0;
        x.fillStyle='rgba('+col+','+(.25+.4*p.z)+')';x.beginPath();x.arc(p.x*w,p.y*h,(1+p.z*1.6)*d,0,6.3);x.fill();
        for(var j=i+1;j<N;j++){var q=P[j],dx=(p.x-q.x)*w,dy=(p.y-q.y)*h,dd=dx*dx+dy*dy,m=(150*d)*(150*d);if(dd<m){x.strokeStyle='rgba('+col+','+(.16*(1-dd/m))+')';x.lineWidth=d*.8;x.beginPath();x.moveTo(p.x*w,p.y*h);x.lineTo(q.x*w,q.y*h);x.stroke()}}}
      requestAnimationFrame(f)})();
  }

  /* login hero: big wireframe globe with orbit rings */
  function hero(){
    var ov=$('#adminLoginOverlay'),hh=ov&&$('.login-hero',ov);if(!ov||!hh||$('#pxHero'))return;
    var cv=document.createElement('canvas');cv.id='pxHero';hh.insertBefore(cv,hh.firstChild);
    var x=cv.getContext('2d'),d=fit(cv),S=sphere(260),t=0;
    addEventListener('resize',function(){d=fit(cv)});
    (function f(){
      if(!document.body.contains(ov)||ov.classList.contains('hidden')||document.hidden){if(!document.body.contains(ov))return;return requestAnimationFrame(f)}
      var w=cv.width,h=cv.height,R=Math.min(w,h)*.2,cx=w*.8,cy=h*.8;t+=.0045;
      x.clearRect(0,0,w,h);var ax=.35+(mouse.y-.5)*.5,ay=t+(mouse.x-.5)*.8;
      var pr=S.map(function(p){var r=rot(p,ax,ay),k=1/(1.9-r[2]*.55);return [cx+r[0]*R*k*1.5,cy+r[1]*R*k*1.5,r[2],k]});
      x.lineWidth=d*.6;
      for(var i=0;i<pr.length;i+=1){var a=pr[i];for(var j=i+1;j<Math.min(i+7,pr.length);j++){var b=pr[j],dx=a[0]-b[0],dy=a[1]-b[1];if(dx*dx+dy*dy<(R*.2)*(R*.2)){x.strokeStyle='rgba(124,108,255,'+(.10+.25*((a[2]+1)/2))+')';x.beginPath();x.moveTo(a[0],a[1]);x.lineTo(b[0],b[1]);x.stroke()}}}
      pr.forEach(function(p){x.fillStyle='rgba(34,211,238,'+(.25+.7*((p[2]+1)/2))+')';x.beginPath();x.arc(p[0],p[1],(1+p[3]*1.4)*d,0,6.3);x.fill()});
      for(var k=0;k<3;k++){x.strokeStyle='rgba(244,114,182,'+(.28-k*.07)+')';x.lineWidth=d*1.1;x.beginPath();
        for(var a2=0;a2<=64;a2++){var an=a2/64*6.283,q=rot([Math.cos(an)*1.35,0,Math.sin(an)*1.35],ax+k*.9+.4,ay*(1+k*.3)+k),kk=1/(1.9-q[2]*.55);x[a2?'lineTo':'moveTo'](cx+q[0]*R*kk*1.5,cy+q[1]*R*kk*1.5)}x.stroke()}
      requestAnimationFrame(f)})();
  }

  /* 3D tilt + cursor spotlight */
  function fx(){
    document.addEventListener('pointermove',function(e){
      var c=e.target.closest&&e.target.closest('.metric-card,.panel,.table-panel');if(!c)return;
      var r=c.getBoundingClientRect(),px=(e.clientX-r.left)/r.width,py=(e.clientY-r.top)/r.height;
      c.style.setProperty('--mx',px*100+'%');c.style.setProperty('--my',py*100+'%');
      if(!reduce&&c.classList.contains('metric-card')||c.classList.contains('panel')&&!reduce&&r.height<420)
        c.style.transform='perspective(900px) rotateX('+((.5-py)*7)+'deg) rotateY('+((px-.5)*9)+'deg) translateZ(0)';
    },{passive:true});
    document.addEventListener('pointerout',function(e){var c=e.target.closest&&e.target.closest('.metric-card,.panel');if(c&&!c.contains(e.relatedTarget))c.style.transform=''},true);
  }

  /* count-up for numeric KPIs, re-runs when the text changes */
  function counters(){
    if(reduce)return;
    var busy=new WeakSet();
    function go(el){var raw=el.textContent.trim();if(!/^\d[\d,]*$/.test(raw)||busy.has(el))return;
      var to=+raw.replace(/,/g,'');if(to<2||to>1e9)return;busy.add(el);var t0=performance.now(),dur=900;
      (function s(n){var k=Math.min(1,(n-t0)/dur),v=Math.round(to*(1-Math.pow(1-k,3)));el.textContent=v.toLocaleString('en-IN');
        if(k<1)requestAnimationFrame(s);else{el.textContent=raw;setTimeout(function(){busy.delete(el)},50)}})(t0)}
    var mo=new MutationObserver(function(ms){ms.forEach(function(m){var t=m.target.nodeType===3?m.target.parentNode:m.target;if(t&&t.matches&&t.matches('.metric-card>strong'))go(t)})});
    $$('.metric-card>strong').forEach(function(e){mo.observe(e,{childList:true,characterData:true,subtree:true});go(e)});
  }

  /* upgrade the ⌘K hint & keep shortcut intact; add "/" focus-search */
  function keys(){
    var kb=$('.global-search kbd');if(kb)kb.textContent=/Mac/.test(navigator.platform)?'⌘ K':'Ctrl K';
    document.addEventListener('keydown',function(e){
      if(e.key==='/'&&!/INPUT|TEXTAREA|SELECT/.test((e.target||{}).tagName||'')&&!e.ctrlKey&&!e.metaKey){e.preventDefault();var i=$('#globalSearch');if(i)i.focus()}
    });
  }

  function boot(){backdrop();hero();fx();counters();keys()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
