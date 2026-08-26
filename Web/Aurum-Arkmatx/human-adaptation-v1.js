/* AURUM_HUMAN_ADAPTATION_V1_EXPERIMENTAL
 * Presentation-only Future Branch consumer.
 * Evidence stays in this browser. No network calls, identity inference, privilege,
 * authentication, external action, destructive action, or server mutation.
 */
(()=>{'use strict';
if(window.__aurumHumanAdaptationV1)return;
window.__aurumHumanAdaptationV1=true;
const KEY='aurum-human-adaptation-v1';
const SESSION_KEY='aurum-human-adaptation-session-v1';
const MIN_EVIDENCE=3,STALE_MS=30*24*60*60*1000,MAX_SESSIONS=16;
const ROLLBACK_AVAILABLE=true;
const marker={schema:'aurum-browser-human-adaptation-v1',storageScope:'local-browser-only',presentationOnly:true,grantsAuthority:false,serverMutationAllowed:false,externalActionAllowed:false,destructiveActionAllowed:false,identityInferenceAllowed:false,authenticationThresholdChangeAllowed:false,privilegeChangeAllowed:false,rollbackAvailable:ROLLBACK_AVAILABLE};
function now(){return Date.now()}
function sessionId(){let id=sessionStorage.getItem(SESSION_KEY);if(!id){id=`s-${now()}-${Math.random().toString(36).slice(2,10)}`;sessionStorage.setItem(SESSION_KEY,id)}return id}
function empty(){return{schema:marker.schema,updatedAt:now(),positiveSessions:[],negativeSessions:[],adapted:false}}
function read(){try{const raw=localStorage.getItem(KEY);if(!raw)return empty();const value=JSON.parse(raw);if(!value||value.schema!==marker.schema)return empty();if(now()-Number(value.updatedAt||0)>STALE_MS)return empty();value.positiveSessions=Array.isArray(value.positiveSessions)?value.positiveSessions.slice(-MAX_SESSIONS):[];value.negativeSessions=Array.isArray(value.negativeSessions)?value.negativeSessions.slice(-MAX_SESSIONS):[];value.adapted=value.adapted===true;return value}catch{return empty()}}
function write(value){value.updatedAt=now();localStorage.setItem(KEY,JSON.stringify(value))}
function uniqueAdd(list,id){return [...new Set([...list,id])].slice(-MAX_SESSIONS)}
function record(expanded){const value=read(),id=sessionId();value.positiveSessions=value.positiveSessions.filter(x=>x!==id);value.negativeSessions=value.negativeSessions.filter(x=>x!==id);if(expanded)value.positiveSessions=uniqueAdd(value.positiveSessions,id);else value.negativeSessions=uniqueAdd(value.negativeSessions,id);write(value);return value}
function decision(value=read()){const positive=value.positiveSessions.length,negative=value.negativeSessions.length,net=positive-negative;return{...marker,positiveSessions:positive,negativeSessions:negative,netEvidence:net,singleObservationCanSwitch:false,disposition:positive>=MIN_EVIDENCE&&net>=2&&ROLLBACK_AVAILABLE?'adapt-reversibly':'keep-warm',adapted:value.adapted===true}}
function reset(card){localStorage.removeItem(KEY);if(card)card.setAttribute('aria-expanded','false')}
function addReset(card){if(!card||card.querySelector('[data-human-adaptation-reset]'))return;const detail=card.querySelector('.fb-detail');if(!detail)return;const button=document.createElement('button');button.type='button';button.dataset.humanAdaptationReset='true';button.textContent='Reset learned view';button.style.cssText='margin-top:10px;border:1px solid #35465d;border-radius:9px;background:#17212d;color:inherit;padding:7px 9px;font-size:10px;cursor:pointer';button.addEventListener('click',event=>{event.stopPropagation();reset(card);button.textContent='Learned view reset'});detail.appendChild(button)}
function bind(){const card=document.querySelector('[data-id="future-branch"]');if(!card||card.dataset.humanAdaptationBound==='true')return false;card.dataset.humanAdaptationBound='true';let value=read(),d=decision(value);if(d.disposition==='adapt-reversibly'&&card.getAttribute('aria-expanded')!=='true'){card.setAttribute('aria-expanded','true');value.adapted=true;write(value)}addReset(card);card.addEventListener('click',()=>{queueMicrotask(()=>{const v=record(card.getAttribute('aria-expanded')==='true'),next=decision(v);if(next.disposition==='adapt-reversibly'&&!v.adapted){v.adapted=true;write(v)}addReset(card)})});return true}
let tries=0;const timer=setInterval(()=>{tries+=1;if(bind()||tries>30)clearInterval(timer)},250);
window.__aurumHumanAdaptationState=()=>decision(read());
})();
