// Theme (lagoon): loaded synchronously in <head>, external file (CSP-safe), runs before first paint.
// Default: no data-theme attribute -> daisyUI applies "lagoon" or, via prefers-color-scheme: dark, "lagoon-dark".
// Compatibility: the existing localStorage key "lic-theme" ("light" | "dark", absent = system) is still honoured on
// desktop (>=600px) and set by the desktop-only theme radios (input[name=theme]) in the header settings menu
// (selectors v2, variant B «Одно меню»); on mobile (<=599px) the system theme always applies and the stored desktop
// choice is kept untouched. Never sent anywhere. No cookies.
// Also wires the header <details class="settings"> menu: aria-expanded, Esc closes + returns focus, click outside
// and tabbing out close it, button theme icon (.is-light/.is-dark on summary) and aria-label follow the choice.
(function(){
  'use strict';
  var KEY='lic-theme',root=document.documentElement,
      mob=window.matchMedia?window.matchMedia('(max-width: 599px)'):null;
  function get(){try{var v=window.localStorage.getItem(KEY);return v==='light'||v==='dark'?v:'system';}catch(e){return 'system';}}
  function set(v){try{if(v==='system')window.localStorage.removeItem(KEY);else window.localStorage.setItem(KEY,v);}catch(e){}}
  var choice=get(),sum=null;
  function apply(){var c=(mob&&mob.matches)?'system':choice;
    if(c==='system')root.removeAttribute('data-theme');else root.setAttribute('data-theme',c==='dark'?'lagoon-dark':'lagoon');}
  function label(){if(!sum)return;
    sum.classList.toggle('is-light',choice==='light');sum.classList.toggle('is-dark',choice==='dark');
    var l=sum.getAttribute('data-l-'+((mob&&mob.matches)?'mobile':choice));if(l)sum.setAttribute('aria-label',l);}
  function onMq(){apply();label();}
  apply();
  if(mob){if(mob.addEventListener)mob.addEventListener('change',onMq);else if(mob.addListener)mob.addListener(onMq);}
  document.addEventListener('DOMContentLoaded',function(){
    var dd=document.querySelector('details.settings');
    sum=dd?dd.querySelector('summary'):null;
    var radios=document.querySelectorAll('input[name="theme"]');
    for(var i=0;i<radios.length;i++){
      radios[i].checked=radios[i].value===choice;
      radios[i].addEventListener('change',function(ev){var v=ev.target.value;
        choice=v==='light'||v==='dark'?v:'system';set(choice);apply();label();});
    }
    label();
    if(!dd||!sum)return;
    function close(focus){if(dd.open){dd.open=false;if(focus)sum.focus();}}
    dd.addEventListener('toggle',function(){sum.setAttribute('aria-expanded',dd.open?'true':'false');});
    // .kbd: keyboard focus marker so the radio ring also shows where a browser (WebKit) does not match :focus-visible after arrow keys
    dd.addEventListener('keydown',function(ev){dd.classList.add('kbd');if((ev.key==='Escape'||ev.key==='Esc')&&dd.open){ev.preventDefault();close(true);}});
    dd.addEventListener('pointerdown',function(){dd.classList.remove('kbd');});
    dd.addEventListener('focusout',function(ev){var t=ev.relatedTarget;if(t&&!dd.contains(t))close(false);});
    document.addEventListener('click',function(ev){if(dd.open&&!dd.contains(ev.target))close(false);});
  });
})();
