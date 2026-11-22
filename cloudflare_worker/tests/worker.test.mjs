import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {createHmac,generateKeyPairSync,createVerify} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import worker, {parseStrictJson, transitionsFor, verifyWebhookSignature, createAppJWT, fetchInstallationInventory, reconcile, Rejected} from '../src/index.mjs';

const schema=readFileSync(resolve(fileURLToPath(new URL('../migrations/0001_inventory.sql',import.meta.url))),'utf-8');
const secret='test-only-webhook-secret-32-bytes';
const OWNER='cavoixanh638';
const OWNER_ID=285230476;
const INST=196300001;
let ctr=0;
function uuid(){ctr++;return `11111111-2222-4333-8444-${String(ctr).padStart(12,'0')}`;}
class MockD1 {
  constructor(){this.sqlite=new DatabaseSync(':memory:');this.sqlite.exec(schema);}
  prepare(sql){const st=this.sqlite.prepare(sql);const bound=(args=[])=>({
    bind(...values){return bound(values);},
    async run(){const info=st.run(...args);return {success:true,meta:{changes:info.changes}};},
    async first(){return st.get(...args)??null;},
    async all(){return {results:st.all(...args)};},
    _run(){return st.run(...args);},
  });return bound();}
  async batch(statements){this.sqlite.exec('BEGIN IMMEDIATE');try{const results=statements.map(x=>x._run());this.sqlite.exec('COMMIT');return results.map(x=>({success:true,meta:{changes:x.changes}}));}catch(error){this.sqlite.exec('ROLLBACK');throw error;}}
  get(sql,...args){return this.sqlite.prepare(sql).get(...args);}
  rows(){return this.sqlite.prepare('SELECT * FROM repositories ORDER BY repo_id').all();}
  close(){this.sqlite.close();}
}
function env(init={}) {return {DB:new MockD1(),MODE:'read_only',OWNER_LOGIN:OWNER,OWNER_ID:String(OWNER_ID),GITHUB_INSTALLATION_ID:String(INST),GITHUB_WEBHOOK_SECRET:secret,...init};}
function repo(id,name=`${OWNER}/project-${id}`,opts={}){return {id,full_name:name,private:true,archived:false,owner:{login:OWNER,id:OWNER_ID},...opts};}
const installation={id:INST,account:{login:OWNER,id:OWNER_ID,type:'User'}};
function payload(action='created',r=repo(101)){return {action,installation:structuredClone(installation),repository:r};}
function request(event,p,guid=uuid(),opts={}){
  const raw=typeof p==='string'?p:JSON.stringify(p);
  const s=opts.signature ?? 'sha256='+createHmac('sha256',secret).update(raw).digest('hex');
  return new Request('https://worker.example/webhook',{method:'POST',headers:{'content-type':opts.type??'application/json','x-hub-signature-256':s,'x-github-delivery':guid,'x-github-event':event},body:raw});
}
async function post(e,evt='repository',p=payload(),guid=uuid(),opts={}){return worker.fetch(request(evt,p,guid,opts),e);}
function count(e){return e.DB.get('SELECT COUNT(*) AS n FROM webhook_deliveries').n;}
const goodRepo=()=>[repo(101),repo(102)];

// All tests use generated fixture identities. No production webhook or access token.
test('dry-run is inert even when valid payload is posted',async()=>{const e=env({MODE:'dry_run'});const r=await post(e);assert.equal(r.status,503);assert.equal(count(e),0);});
test('health is generic and does not expose private inventory',async()=>{const e=env();const r=await worker.fetch(new Request('https://worker.example/healthz'),e);assert.equal(r.status,200);const s=await r.text();assert.ok(!s.includes('GITHUB_INSTALLATION_ID'));assert.ok(!s.includes('project-'));assert.match(s,/repository_writes/);});
test('unknown paths and methods are disabled',async()=>{const e=env();for(const u of ['/admin','/repos','/onboard','/dispatch','/webhook']){const r=await worker.fetch(new Request('https://worker.example'+u),e);assert.equal(r.status,404);}});
test('signed repository created stores private inventory and receipt',async()=>{const e=env();const r=await post(e);assert.equal(r.status,202);assert.equal(e.DB.rows().length,1);assert.equal(e.DB.rows()[0].visibility,'private');assert.equal(count(e),1);});
test('duplicate delivery same payload has no second write',async()=>{const e=env();const g=uuid();const p=payload();assert.equal((await post(e,'repository',p,g)).status,202);const old=e.DB.rows()[0].updated_at_ms;assert.equal((await post(e,'repository',p,g)).status,200);assert.equal(e.DB.rows()[0].updated_at_ms,old);assert.equal(count(e),1);});
test('duplicate GUID with a different signed payload is rejected',async()=>{const e=env(),g=uuid();await post(e,'repository',payload('created',repo(101)),g);const r=await post(e,'repository',payload('created',repo(102)),g);assert.equal(r.status,409);assert.equal(e.DB.rows().length,1);});
test('invalid signature is rejected before state changes',async()=>{const e=env();const r=await post(e,'repository',payload(),uuid(),{signature:'sha256='+'0'.repeat(64)});assert.equal(r.status,401);assert.equal(count(e),0);});
test('missing signature is rejected',async()=>{await assert.rejects(()=>verifyWebhookSignature(secret,new Uint8Array(0),null),Rejected);});
test('unsupported content type is rejected',async()=>{const e=env();assert.equal((await post(e,'repository',payload(),uuid(),{type:'text/plain'})).status,415);});
test('missing or wrong owner blocks acceptance',async()=>{const e=env();const p=payload();p.installation.account.login='another';assert.equal((await post(e,'repository',p)).status,401);assert.equal(count(e),0);});
test('wrong owner account ID blocks acceptance',async()=>{const e=env();const p=payload();p.installation.account.id=2;assert.equal((await post(e,'repository',p)).status,401);});
test('wrong installation ID blocks acceptance',async()=>{const e=env();const p=payload();p.installation.id=88;assert.equal((await post(e,'repository',p)).status,401);});
test('wrong repository owner blocks acceptance',async()=>{const e=env();const p=payload('created',repo(101,'other/name'));assert.equal((await post(e,'repository',p)).status,401);});
test('unsupported webhook event is rejected',async()=>{const e=env();assert.equal((await post(e,'workflow_run',payload())).status,401);});
test('JSON duplicate object keys are rejected',async()=>{const e=env();const p=`{"action":"created","action":"deleted","installation":${JSON.stringify(installation)},"repository":${JSON.stringify(repo(101))}}`;assert.equal((await post(e,'repository',p)).status,401);assert.equal(count(e),0);});
test('Unicode escape duplicate key is rejected',()=>{assert.throws(()=>parseStrictJson(new TextEncoder().encode('{"a":1,"\\u0061":2}')),Rejected);});
test('trailing payload is rejected',()=>{assert.throws(()=>parseStrictJson(new TextEncoder().encode('{"a":1} 1')),Rejected);});
test('oversized request is 413 without writing state',async()=>{const e=env();const p='{"note":"'+ 'x'.repeat(524288)+'"}';assert.equal((await post(e,'repository',p)).status,413);assert.equal(count(e),0);});
test('installation added repositories records all by ID',async()=>{const e=env();const p={action:'added',installation,repositories_added:goodRepo(),repositories_removed:[]};assert.equal((await post(e,'installation_repositories',p)).status,202);assert.equal(e.DB.rows().length,2);});
test('installation removed repository becomes inaccessible',async()=>{const e=env();await post(e,'installation_repositories',{action:'added',installation,repositories_added:goodRepo(),repositories_removed:[]});await post(e,'installation_repositories',{action:'removed',installation,repositories_added:[],repositories_removed:[repo(101)]});assert.equal(e.DB.get('SELECT state FROM repositories WHERE repo_id=?',101).state,'inaccessible');});
test('repository rename updates same ID rather than duplicating',async()=>{const e=env();await post(e);await post(e,'repository',payload('renamed',repo(101,`${OWNER}/renamed`)));assert.equal(e.DB.rows().length,1);assert.equal(e.DB.rows()[0].full_name,`${OWNER}/renamed`);});
test('archived and unarchived update lifecycle',async()=>{const e=env();await post(e,'repository',payload('archived',repo(101,undefined,{archived:true})));assert.equal(e.DB.rows()[0].state,'archived');await post(e,'repository',payload('unarchived',repo(101)));assert.equal(e.DB.rows()[0].state,'active');});
test('installation deletion revokes access for every known repository',async()=>{const e=env();await post(e,'installation_repositories',{action:'added',installation,repositories_added:goodRepo(),repositories_removed:[]});await post(e,'installation',{action:'deleted',installation});assert.deepEqual(e.DB.rows().map(x=>x.state),['inaccessible','inaccessible']);});
test('installation created requests reconciliation',async()=>{const e=env();await post(e,'installation',{action:'created',installation,repositories:goodRepo()});assert.equal(e.DB.get("SELECT value FROM app_state WHERE key='needs_reconcile'").value,'1');});
test('malformed event never inserts receipt',async()=>{const e=env();assert.equal((await post(e,'repository',{action:'created'})).status,401);assert.equal(count(e),0);});
test('invalid configuration is fail-closed',async()=>{const e=env({GITHUB_INSTALLATION_ID:''});assert.equal((await post(e)).status,401);assert.equal(count(e),0);});
test('invalid D1 results in 503 and no unverified success',async()=>{const e=env();e.DB.batch=async()=>{throw Error('d1 down');};assert.equal((await post(e)).status,503);});
test('ping is authenticated and does not create inventory entries',async()=>{const e=env();assert.equal((await post(e,'ping',{zen:'Keep it logically awesome'})).status,202);assert.equal(e.DB.rows().length,0);});

test('generate JWT with RS256 signature and bounded lifetime',async()=>{
 const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
 const pem=privateKey.export({type:'pkcs8',format:'pem'});
 const jwt=await createAppJWT(1234,pem,1000000);const [h,p,s]=jwt.split('.');
 const verify=createVerify('RSA-SHA256');verify.update(`${h}.${p}`);verify.end();assert.ok(verify.verify(publicKey,Buffer.from(s.replace(/-/g,'+').replace(/_/g,'/'),'base64')));
 const claims=JSON.parse(Buffer.from(p,'base64url'));assert.equal(claims.exp-claims.iat,600);assert.equal(claims.iss,'1234');
});
test('PKCS1 PEM rejected; conversion must be local owner action',async()=>{
 const {privateKey}=generateKeyPairSync('rsa',{modulusLength:2048});await assert.rejects(()=>createAppJWT(1,privateKey.export({type:'pkcs1',format:'pem'})),Rejected);
});
function fakeGitHub(repositories,options={}){
 let calls=0;const seen=[];const fetcher=async(u,opts)=>{
   calls++;seen.push({url:u,method:opts.method,body:opts.body});
   if(options.failAt===calls)return new Response('oops',{status:403,headers:{'content-type':'application/json'}});
   if(u.endsWith('/access_tokens'))return Response.json({token:'test-installation-token'});
   if(!u.startsWith('https://api.github.com/installation/repositories?'))return new Response('',{status:404});
   const p=Number(new URL(u).searchParams.get('page'));
   let all=repositories;
   if(options.changeCountOnPage===p)all=repositories.slice(0,repositories.length-1);
   return Response.json({total_count:all.length,repositories:all.slice((p-1)*100,p*100)});
 };return {fetcher,seen,callCount:()=>calls};
}
function addTestKey(e){const {privateKey}=generateKeyPairSync('rsa',{modulusLength:2048});e.GITHUB_PRIVATE_KEY=privateKey.export({type:'pkcs8',format:'pem'});e.GITHUB_APP_ID='1234';}
test('read-only sync lists and stores repositories without API mutations',async()=>{const e=env();addTestKey(e);const h=fakeGitHub(goodRepo());const s=await reconcile(e,h.fetcher);assert.equal(s.count,2);assert.equal(e.DB.rows().length,2);assert.equal(h.seen.length,2);assert.equal(h.seen[1].method,'GET');assert.equal(h.seen[0].method,'POST');assert.deepEqual(JSON.parse(h.seen[0].body),{permissions:{metadata:'read'}});});
test('read-only sync detects repo removal only after complete snapshot',async()=>{const e=env();addTestKey(e);await reconcile(e,fakeGitHub(goodRepo()).fetcher);await reconcile(e,fakeGitHub([repo(102)]).fetcher);assert.equal(e.DB.get('SELECT state FROM repositories WHERE repo_id=?',101).state,'inaccessible');});
test('empty snapshot cannot erase previous active inventory',async()=>{const e=env();addTestKey(e);await reconcile(e,fakeGitHub(goodRepo()).fetcher);await assert.rejects(()=>reconcile(e,fakeGitHub([]).fetcher),Rejected);assert.equal(e.DB.rows()[0].state,'active');});
test('API 403 cannot mutate existing inventory',async()=>{const e=env();addTestKey(e);await reconcile(e,fakeGitHub(goodRepo()).fetcher);await assert.rejects(()=>reconcile(e,fakeGitHub([], {failAt:1}).fetcher),Rejected);assert.equal(e.DB.rows().length,2);});
test('partial pagination cannot mutate existing inventory',async()=>{const e=env();addTestKey(e);await reconcile(e,fakeGitHub(goodRepo()).fetcher);const many=Array.from({length:102},(_,i)=>repo(i+200));await assert.rejects(()=>reconcile(e,fakeGitHub(many,{changeCountOnPage:2}).fetcher),Rejected);assert.equal(e.DB.rows().length,2);});
test('pagination over 100 entries is complete',async()=>{const e=env();addTestKey(e);const many=Array.from({length:105},(_,i)=>repo(i+200));assert.equal((await reconcile(e,fakeGitHub(many).fetcher)).count,105);assert.equal(e.DB.rows().length,105);});
test('wrong owner from GitHub API cannot mutate existing inventory',async()=>{const e=env();addTestKey(e);await reconcile(e,fakeGitHub(goodRepo()).fetcher);await assert.rejects(()=>reconcile(e,fakeGitHub([repo(200,'other/name')]).fetcher),Rejected);assert.equal(e.DB.rows().length,2);});
test('disabled reconciler makes no requests and no D1 writes',async()=>{const e=env({MODE:'dry_run'});addTestKey(e);let called=false;await assert.rejects(()=>reconcile(e,async()=>{called=true;return null;}),Rejected);assert.equal(called,false);});
test('scheduled handler disabled in dry_run',async()=>{const e=env({MODE:'dry_run'});let called=false;await worker.scheduled({},e,{waitUntil(){called=true;}});assert.equal(called,false);});
test('test doubles do not leak production repo inventory',()=>{assert.equal(String(repo(101).full_name).includes('project-'),true);});

test('invalid database schema rolls back the entire webhook transaction',async()=>{
 const e=env();e.DB.sqlite.exec('DROP TABLE repositories');
 assert.equal((await post(e)).status,503);
 assert.equal(count(e),0);
});
test('later signed event wins over an in-flight stale API snapshot',async()=>{
 const e=env();addTestKey(e);
 await reconcile(e,fakeGitHub([repo(101,`${OWNER}/original`)]).fetcher);
 let changed=false;
 const slowFetcher=async (u,o)=>{
   if(u.endsWith('/access_tokens'))return Response.json({token:'fixture-token'});
   if(!changed){
     await new Promise(resolve=>setTimeout(resolve,8));
     assert.equal((await post(e,'repository',payload('renamed',repo(101,`${OWNER}/new-name`)))).status,202);
     changed=true;
   }
   return Response.json({total_count:1,repositories:[repo(101,`${OWNER}/original`)]});
 };
 await reconcile(e,slowFetcher);
 assert.equal(e.DB.rows()[0].full_name,`${OWNER}/new-name`);
});
test('unknown mode never enables live processing',async()=>{
 const e=env({MODE:'enabled'});addTestKey(e);
 assert.equal((await post(e)).status,503);
 let called=false;await worker.scheduled({},e,{waitUntil(){called=true;}});assert.equal(called,false);
});
test('escaped duplicate key in nested webhook object is rejected',async()=>{
 const e=env();const raw=`{"action":"created","installation":{"id":${INST},"account":{"login":"${OWNER}","id":${OWNER_ID},"type":"User","type":"Organization"}},"repository":${JSON.stringify(repo(101))}}`;
 assert.equal((await post(e,'repository',raw)).status,401);
 assert.equal(count(e),0);
});
test('suspended app ignores new repositories until owner re-enables access',async()=>{
 const e=env();await post(e,'repository',payload());await post(e,'installation',{action:'suspend',installation});
 assert.equal(e.DB.rows()[0].state,'inaccessible');
});
test('suspended installation cannot reactivate through a new repository event',async()=>{
 const e=env();await post(e,'repository',payload());
 await post(e,'installation',{action:'suspend',installation});
 assert.equal((await post(e,'repository',payload('created',repo(102)))).status,202);
 assert.equal(e.DB.rows().length,1);
 assert.equal(e.DB.rows()[0].state,'inaccessible');
});
test('unsuspend permits repository changes, schedules reconciliation',async()=>{
 const e=env();await post(e,'repository',payload());await post(e,'installation',{action:'suspend',installation});
 await post(e,'installation',{action:'unsuspend',installation});
 assert.equal((await post(e,'repository',payload('created',repo(102)))).status,202);
 assert.equal(e.DB.rows().length,2);
 assert.equal(e.DB.get("SELECT value FROM app_state WHERE key='needs_reconcile'").value,'1');
});
test('scheduled reconciliation stops while App is suspended',async()=>{
 const e=env();addTestKey(e);await post(e,'installation',{action:'suspend',installation});
 let invoked=false;await assert.rejects(()=>reconcile(e,async()=>{invoked=true;return null;}),Rejected);
 assert.equal(invoked,false);
});
