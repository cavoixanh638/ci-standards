/**
 * Cloudflare Workers Free + D1: owner-scoped GitHub App inventory detector.
 * READ ONLY for GitHub: no Contents, PR, Actions, Billing, merge or deploy APIs.
 * In dry_run it does not ingest webhooks or call GitHub at all.
 */
const MAX_WEBHOOK_BYTES = 524288;
const MAX_PAGE_COUNT = 40; // Reserve free-plan HTTP subrequests for token issuance and retries.
const GITHUB_API = 'https://api.github.com';
const REPO_NAME = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const EVENTS = {
  ping: [null],
  repository: ['created', 'renamed', 'deleted', 'transferred', 'archived', 'unarchived', 'privatized', 'publicized'],
  installation: ['created', 'deleted', 'suspend', 'unsuspend'],
  installation_repositories: ['added', 'removed'],
};
const encoder = new TextEncoder();

export class Rejected extends Error {}
function fail(reason) { throw new Rejected(reason); }
function numberId(value) {
  return Number.isSafeInteger(value) && value > 0 ? value : fail('invalid positive id');
}
function mode(env) { return env?.MODE === 'read_only' ? 'read_only' : 'dry_run'; }
function config(env) {
  if (!env || env.OWNER_LOGIN !== 'cavoixanh638' || String(env.OWNER_ID) !== '285230476') fail('unexpected owner config');
  if (!env.DB || typeof env.DB.prepare !== 'function' || typeof env.DB.batch !== 'function') fail('missing private D1 database');
  if (!env.GITHUB_INSTALLATION_ID || !/^\d+$/.test(String(env.GITHUB_INSTALLATION_ID))) fail('missing installation ID');
  numberId(Number(env.GITHUB_INSTALLATION_ID));
  return { owner: env.OWNER_LOGIN, ownerId: 285230476, installationId: Number(env.GITHUB_INSTALLATION_ID) };
}
function headers(responseStatus, body) {
  return new Response(JSON.stringify(body), {
    status: responseStatus,
    headers: {'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer'},
  });
}
function b64url(bytes) {
  const value = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s=''; for (const n of value) s+=String.fromCharCode(n);
  return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');
}
function fromHex(hex) {
  if (!/^[0-9a-f]{64}$/i.test(hex)) fail('invalid sha256 hex');
  return Uint8Array.from(hex.match(/.{2}/g),n=>parseInt(n,16));
}
async function hexSha256(bytes) {
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return Array.from(d,n=>n.toString(16).padStart(2,'0')).join('');
}
export async function verifyWebhookSignature(secret, raw, header) {
  if (typeof secret!=='string' || secret.length < 16) fail('webhook secret unavailable');
  if (typeof header!=='string' || !/^sha256=[0-9a-f]{64}$/i.test(header)) fail('invalid signature header');
  const key=await crypto.subtle.importKey('raw',encoder.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['verify']);
  const ok=await crypto.subtle.verify('HMAC',key,fromHex(header.slice(7)),raw);
  if (!ok) fail('invalid webhook signature');
}
async function limitedBody(request) {
  const stated=request.headers.get('content-length');
  if (stated !== null && (!/^\d+$/.test(stated) || Number(stated)>MAX_WEBHOOK_BYTES)) fail('payload too large');
  if (!request.body) fail('body required');
  const reader=request.body.getReader(); const chunks=[]; let length=0;
  try {
    for (;;) {
      const {done,value}=await reader.read(); if(done)break;
      length+=value.byteLength;
      if(length>MAX_WEBHOOK_BYTES) fail('payload too large');
      chunks.push(value);
    }
  } finally { if (length>MAX_WEBHOOK_BYTES) await reader.cancel().catch(()=>{}); }
  const out=new Uint8Array(length);let offset=0;
  for(const chunk of chunks){out.set(chunk,offset);offset+=chunk.byteLength;}
  return out;
}
// Scan the JSON lexical structure first so duplicate object keys are rejected.
// JSON.parse alone silently chooses the last duplicate key.
export function parseStrictJson(raw) {
  let src;
  try{src=new TextDecoder('utf-8',{fatal:true}).decode(raw);}catch{fail('non-UTF8 payload');}
  let i=0;
  const ws=()=>{while(i<src.length && /\s/.test(src[i]))i++;};
  const str=()=>{
    if(src[i]!=='"')fail('expected JSON string');
    const start=i++;let escaped=false;
    for(;i<src.length;i++){
      const c=src[i];
      if(escaped){escaped=false;continue;}
      if(c==='\\'){escaped=true;continue;}
      if(c==='"'){i++;try{return JSON.parse(src.slice(start,i));}catch{fail('invalid JSON string');}}
    }
    fail('unterminated JSON string');
  };
  const scan=(depth)=>{
    if(depth>64)fail('JSON nesting too deep');ws();
    if(src[i]==='{'){
      i++;ws();const keys=new Set();if(src[i]==='}'){i++;return;}
      for(;;){ws();const key=str();if(keys.has(key))fail('duplicate JSON object key');keys.add(key);ws();
        if(src[i++]!==':')fail('missing colon');scan(depth+1);ws();
        if(src[i]==='}'){i++;break;}if(src[i++]!==',')fail('missing comma');
      }
    }else if(src[i]==='['){
      i++;ws();if(src[i]===']'){i++;return;}
      for(;;){scan(depth+1);ws();if(src[i]===']'){i++;break;}if(src[i++]!==',')fail('missing comma');}
    }else if(src[i]==='"'){str();}
    else{const start=i;while(i<src.length && !/[\s,\]}]/.test(src[i]))i++;if(i===start)fail('invalid JSON token');}
  };
  scan(0);ws();if(i!==src.length)fail('trailing JSON');
  let payload;try{payload=JSON.parse(src);}catch{fail('invalid JSON');}
  if(payload===null || Array.isArray(payload) || typeof payload!=='object')fail('object payload required');
  return payload;
}
function repoTransition(value,cfg,requestedState=null){
  if(!value || typeof value!=='object' || Array.isArray(value))fail('invalid repository object');
  const id=numberId(value.id),name=value.full_name;
  if(typeof name!=='string' || !REPO_NAME.test(name) || name.split('/')[0].toLowerCase()!==cfg.owner.toLowerCase())fail('repository owner/name mismatch');
  if(value.owner && (value.owner.login?.toLowerCase()!==cfg.owner.toLowerCase() || (value.owner.id && value.owner.id!==cfg.ownerId)))fail('repository owner identity mismatch');
  if(value.private!==undefined && typeof value.private!=='boolean')fail('invalid private flag');
  if(value.archived!==undefined && typeof value.archived!=='boolean')fail('invalid archived flag');
  return {id,name,state:requestedState ?? (value.archived===true?'archived':'active'),visibility:value.private===true?'private':value.private===false?'public':'unknown'};
}
export function transitionsFor(event,payload,cfg){
  const action=payload.action??null;
  if(!Object.hasOwn(EVENTS,event) || !EVENTS[event].includes(action))fail('unsupported webhook event');
  if(event==='ping')return {changes:[],action,event};
  const install=payload.installation;
  if(!install || typeof install!=='object' || install.id!==cfg.installationId)fail('installation ID mismatch');
  const account=install.account;
  if(!account || account.login?.toLowerCase()!==cfg.owner.toLowerCase() || account.id!==cfg.ownerId || account.type!=='User')fail('installation account mismatch');
  let changes=[];
  if(event==='repository'){
    changes=[repoTransition(payload.repository,cfg,['deleted','transferred'].includes(action)?'inaccessible':null)];
  }else if(event==='installation_repositories'){
    if(!Array.isArray(payload.repositories_added) || !Array.isArray(payload.repositories_removed))fail('missing repository arrays');
    changes=[...payload.repositories_added.map(x=>repoTransition(x,cfg)),...payload.repositories_removed.map(x=>repoTransition(x,cfg,'inaccessible'))];
    if(changes.length===0)fail('empty repository change');
  }else if(event==='installation' && action==='created'){
    if(!Array.isArray(payload.repositories))fail('missing initial repositories');
    changes=payload.repositories.map(x=>repoTransition(x,cfg));
  }
  const ids=new Set();for(const x of changes){if(ids.has(x.id))fail('duplicate repository id');ids.add(x.id);}
  if(changes.length>300)fail('repository batch too large');
  return {changes,action,event};
}
const ADMIT_SQL=`INSERT INTO webhook_deliveries(delivery_id,payload_hash,nonce,received_at_ms)
VALUES(?,?,?,?) ON CONFLICT(delivery_id) DO NOTHING`;
const APPLY_EVENT_SQL=`INSERT INTO repositories(repo_id,full_name,state,visibility,source,updated_at_ms)
SELECT CAST(json_extract(j.value,'$.id') AS INTEGER),json_extract(j.value,'$.name'),
       json_extract(j.value,'$.state'),json_extract(j.value,'$.visibility'),'webhook',?
FROM json_each(?) AS j
WHERE EXISTS(SELECT 1 FROM webhook_deliveries WHERE delivery_id=? AND nonce=? AND payload_hash=?)
AND NOT EXISTS(SELECT 1 FROM app_state WHERE key='installation_enabled' AND value='0')
ON CONFLICT(repo_id) DO UPDATE SET full_name=excluded.full_name,state=excluded.state,
visibility=CASE WHEN excluded.visibility='unknown' THEN repositories.visibility ELSE excluded.visibility END,
source=excluded.source,updated_at_ms=excluded.updated_at_ms`;
const INSTALL_SUSPEND_SQL=`UPDATE repositories SET state='inaccessible',source='installation',updated_at_ms=?
WHERE EXISTS(SELECT 1 FROM webhook_deliveries WHERE delivery_id=? AND nonce=? AND payload_hash=?)`;
const INSTALL_STATE_SQL=`INSERT INTO app_state(key,value) SELECT 'installation_enabled',?
WHERE EXISTS(SELECT 1 FROM webhook_deliveries WHERE delivery_id=? AND nonce=? AND payload_hash=?)
ON CONFLICT(key) DO UPDATE SET value=excluded.value`;
const RECONCILE_EVENT_SQL=`INSERT INTO app_state(key,value) SELECT 'needs_reconcile','1'
WHERE EXISTS(SELECT 1 FROM webhook_deliveries WHERE delivery_id=? AND nonce=? AND payload_hash=?)
ON CONFLICT(key) DO UPDATE SET value=excluded.value`;

export async function receiveWebhook(env,{event,guid,raw,signature}){
  const cfg=config(env);
  if(!UUID.test(guid||''))fail('invalid delivery id');
  await verifyWebhookSignature(env.GITHUB_WEBHOOK_SECRET,raw,signature);
  const payload=parseStrictJson(raw);
  const {changes,action}=transitionsFor(event,payload,cfg);
  const hash=await hexSha256(raw);
  const nonce=crypto.randomUUID(); const now=Date.now();
  const batch=[env.DB.prepare(ADMIT_SQL).bind(guid.toLowerCase(),hash,nonce,now)];
  if(event==='installation' && ['created','unsuspend'].includes(action))
    batch.push(env.DB.prepare(INSTALL_STATE_SQL).bind('1',guid.toLowerCase(),nonce,hash));
  batch.push(env.DB.prepare(APPLY_EVENT_SQL).bind(now,JSON.stringify(changes),guid.toLowerCase(),nonce,hash));
  if(event==='installation' && ['deleted','suspend'].includes(action)){
    batch.push(env.DB.prepare(INSTALL_STATE_SQL).bind('0',guid.toLowerCase(),nonce,hash));
    batch.push(env.DB.prepare(INSTALL_SUSPEND_SQL).bind(now,guid.toLowerCase(),nonce,hash));
  }
  if(event==='installation' && ['created','unsuspend'].includes(action))
    batch.push(env.DB.prepare(RECONCILE_EVENT_SQL).bind(guid.toLowerCase(),nonce,hash));
  await env.DB.batch(batch);
  const receipt=await env.DB.prepare('SELECT payload_hash,nonce FROM webhook_deliveries WHERE delivery_id=?').bind(guid.toLowerCase()).first();
  if(!receipt || receipt.payload_hash!==hash)fail('conflicting delivery ID');
  return receipt.nonce===nonce?'accepted':'duplicate';
}
function pemBytes(pem){
  if(typeof pem!=='string' || !pem.includes('-----BEGIN PRIVATE KEY-----'))fail('PKCS8 key required');
  const b64=pem.replace(/-----BEGIN PRIVATE KEY-----/g,'').replace(/-----END PRIVATE KEY-----/g,'').replace(/\s/g,'');
  if(!/^[A-Za-z0-9+/]+={0,2}$/.test(b64))fail('invalid PEM');
  return Uint8Array.from(atob(b64),x=>x.charCodeAt(0));
}
export async function createAppJWT(appId,pem,now=Math.floor(Date.now()/1000)){
  if(!/^\d+$/.test(String(appId)) || !Number.isSafeInteger(Number(appId)) || Number(appId)<=0)fail('invalid app id');
  const key=await crypto.subtle.importKey('pkcs8',pemBytes(pem),{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']);
  const h=b64url(encoder.encode(JSON.stringify({alg:'RS256',typ:'JWT'})));
  const p=b64url(encoder.encode(JSON.stringify({iat:now-60,exp:now+540,iss:String(appId)})));
  const sig=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',key,encoder.encode(`${h}.${p}`));
  return `${h}.${p}.${b64url(sig)}`;
}
async function ghFetch(url,options,fetcher){
  const result=await fetcher(url,{...options,redirect:'error'});
  if(!result.ok)fail('GitHub request unavailable');
  if(result.headers.get('content-type')?.includes('text/html'))fail('unexpected GitHub response');
  return result.json();
}
export async function fetchInstallationInventory(env,cfg,fetcher=fetch){
  const jwt=await createAppJWT(env.GITHUB_APP_ID,env.GITHUB_PRIVATE_KEY);
  const jsonHeaders={'accept':'application/vnd.github+json','x-github-api-version':'2026-03-10','user-agent':'ci-standards-readonly-detector'};
  const tokenReply=await ghFetch(`${GITHUB_API}/app/installations/${cfg.installationId}/access_tokens`,{
    method:'POST',headers:{...jsonHeaders,authorization:`Bearer ${jwt}`,'content-type':'application/json'},body:JSON.stringify({permissions:{metadata:'read'}}),
  },fetcher);
  if(typeof tokenReply.token!=='string' || !tokenReply.token)fail('installation token unavailable');
  const headersWithToken={...jsonHeaders,authorization:`Bearer ${tokenReply.token}`};
  const seen=new Set(),all=[];let expected=null;
  for(let page=1;page<=MAX_PAGE_COUNT;page++){
    const response=await ghFetch(`${GITHUB_API}/installation/repositories?per_page=100&page=${page}`,{method:'GET',headers:headersWithToken},fetcher);
    if(!Number.isSafeInteger(response.total_count)||response.total_count<0||!Array.isArray(response.repositories)||response.repositories.length>100)fail('invalid GitHub repository page');
    if(expected!==null && response.total_count!==expected)fail('GitHub pagination changed');
    expected=response.total_count;
    for(const item of response.repositories){const obj=repoTransition(item,cfg);if(seen.has(obj.id))fail('duplicate GitHub repository ID');seen.add(obj.id);all.push(obj);}
    if(all.length>expected)fail('GitHub page total mismatch');
    if(all.length===expected)return all;
    if(response.repositories.length!==100)fail('partial GitHub pagination');
  }
  fail('GitHub pagination limit exceeded');
}
const RECONCILE_UPSERT_SQL=`INSERT INTO repositories(repo_id,full_name,state,visibility,source,updated_at_ms)
SELECT CAST(json_extract(j.value,'$.id') AS INTEGER),json_extract(j.value,'$.name'),
       json_extract(j.value,'$.state'),json_extract(j.value,'$.visibility'),'reconciliation',?
FROM json_each(?) AS j WHERE 1
ON CONFLICT(repo_id) DO UPDATE SET full_name=excluded.full_name,state=excluded.state,
visibility=excluded.visibility,source=excluded.source,updated_at_ms=excluded.updated_at_ms
WHERE repositories.updated_at_ms < ?`;
const RECONCILE_DEACTIVATE_SQL=`UPDATE repositories SET state='inaccessible',source='reconciliation',updated_at_ms=?
WHERE repo_id NOT IN (SELECT CAST(json_extract(j.value,'$.id') AS INTEGER) FROM json_each(?) AS j)
AND updated_at_ms<?`;
export async function reconcile(env,fetcher=fetch){
  const cfg=config(env);
  if(mode(env)!=='read_only')fail('read-only reconciliation disabled');
  const state=await env.DB.prepare("SELECT value FROM app_state WHERE key='installation_enabled'").first();
  if(state?.value==='0')fail('installation revoked or suspended');
  const start=Date.now();
  const incoming=await fetchInstallationInventory(env,cfg,fetcher);
  // Unexpected empty snapshots are held for owner review rather than wiping previous results.
  if(incoming.length===0){
    const count=await env.DB.prepare('SELECT COUNT(*) AS n FROM repositories WHERE state!=?').bind('inaccessible').first();
    if(Number(count?.n)>0)fail('empty snapshot requires manual review');
  }
  const json=JSON.stringify(incoming);
  const jobs=[env.DB.prepare(RECONCILE_UPSERT_SQL).bind(start,json,start),
    env.DB.prepare(RECONCILE_DEACTIVATE_SQL).bind(start,json,start),
    env.DB.prepare("INSERT INTO app_state(key,value) VALUES('last_reconciliation_ms',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(String(Date.now())),
    env.DB.prepare("INSERT INTO app_state(key,value) VALUES('needs_reconcile','0') ON CONFLICT(key) DO UPDATE SET value=excluded.value")];
  await env.DB.batch(jobs);
  return {count:incoming.length};
}
export default {
  async fetch(request,env){
    const url=new URL(request.url);
    if(request.method==='GET' && url.pathname==='/healthz')return headers(200,{service:'ci-standards-detector',mode:mode(env),github_actions:false,repository_writes:false});
    if(url.pathname!=='/webhook' || request.method!=='POST')return headers(404,{error:'not found'});
    if(mode(env)!=='read_only')return headers(503,{error:'detector disabled'});
    if(!/^application\/json(?:\s*;|\s*$)/i.test(request.headers.get('content-type')||''))return headers(415,{error:'unsupported content type'});
    try{
      const raw=await limitedBody(request);
      const state=await receiveWebhook(env,{event:request.headers.get('x-github-event'),guid:request.headers.get('x-github-delivery'),raw,signature:request.headers.get('x-hub-signature-256')});
      return headers(state==='accepted'?202:200,{result:state});
    }catch(e){
      // Never log raw payload, repository identifiers, headers, installation tokens or secrets.
      if(e instanceof Rejected){
        if(e.message==='payload too large')return headers(413,{error:'payload rejected'});
        if(e.message==='conflicting delivery ID')return headers(409,{error:'delivery conflict'});
        return headers(401,{error:'webhook rejected'});
      }
      return headers(503,{error:'temporarily unavailable'});
    }
  },
  async scheduled(event,env,ctx){
    if(mode(env)!=='read_only')return;
    ctx.waitUntil(reconcile(env).catch(()=>console.warn('READ_ONLY_RECONCILE_UNAVAILABLE')));
  },
};
