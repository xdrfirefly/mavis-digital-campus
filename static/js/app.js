// v0.9.5 — Weather-Aware Phenology.
import { worldConfig } from './world-config.js?v=093';
import { assets, forestPlacements, worldProps } from './world-assets.js?v=093';
import { createCamera } from './camera.js';

const els = {
  buildings: document.querySelector('#buildings'), agents: document.querySelector('#agents'), routeLayer: document.querySelector('#route-layer'),
  forest: document.querySelector('#forest-decor'), props: document.querySelector('#prop-layer'),
  hudTaskList: document.querySelector('#hud-task-list'), hudTaskCount: document.querySelector('#hud-task-count'),
  approvalBanner: document.querySelector('#approval-banner'), approvalCount: document.querySelector('#approval-count'),
  projectSummary: document.querySelector('#project-summary'), projectBadge: document.querySelector('#project-badge'), taskList: document.querySelector('#task-list'),
  activityList: document.querySelector('#activity-list'), campusAskForm: document.querySelector('#campus-ask-form'), campusQuestion: document.querySelector('#campus-question'),
  campusAgent: document.querySelector('#campus-agent'), campusAskBtn: document.querySelector('#campus-ask-btn'), campusAskResponse: document.querySelector('#campus-ask-response'), resetBtn: document.querySelector('#reset-btn'),
  connection: document.querySelector('.connection'), wsText: document.querySelector('#ws-text'), toast: document.querySelector('#toast'),
  buildingPanel: document.querySelector('#building-panel'), viewport: document.querySelector('#world-viewport'), stage: document.querySelector('#world-stage'),
  zoomIn: document.querySelector('#zoom-in'), zoomOut: document.querySelector('#zoom-out'), home: document.querySelector('#camera-home'), zoomLabel: document.querySelector('#zoom-label'),
  drawer: document.querySelector('#hud-drawer'), drawerKicker: document.querySelector('#drawer-kicker'), drawerTitle: document.querySelector('#drawer-title'), drawerBody: document.querySelector('#drawer-body'), drawerClose: document.querySelector('#drawer-close'),
  navButtons: [...document.querySelectorAll('.bottom-nav [data-panel]')], clock: document.querySelector('#campus-clock'),
  needsMeBtn: document.querySelector('#needs-me-btn'), needsMeCount: document.querySelector('#needs-me-count'), briefingBtn: document.querySelector('#briefing-btn'), briefingCount: document.querySelector('#briefing-count'),
  repositoryBtn: document.querySelector('#repository-btn'), memoryBtn: document.querySelector('#memory-btn'), playbooksBtn: document.querySelector('#playbooks-btn'), focusWorkspaceBtn: document.querySelector('#focus-workspace-btn'),
  conceptModal: document.querySelector('#concept-modal'), conceptModalTitle: document.querySelector('#concept-modal-title'),
  conceptModalImage: document.querySelector('#concept-modal-image'), conceptModalClose: document.querySelector('#concept-modal-close'),
  deliverableModal: document.querySelector('#deliverable-modal'), deliverableModalTitle: document.querySelector('#deliverable-modal-title'),
  deliverableModalMeta: document.querySelector('#deliverable-modal-meta'), deliverableModalBody: document.querySelector('#deliverable-modal-body'),
  deliverableModalClose: document.querySelector('#deliverable-modal-close'), deliverableCopy: document.querySelector('#deliverable-copy'), deliverableRemember: document.querySelector('#deliverable-remember'),
  deliverableDownloadMd: document.querySelector('#deliverable-download-md'), deliverableDownloadTxt: document.querySelector('#deliverable-download-txt'),
  deliverablePrint: document.querySelector('#deliverable-print'),
  aiAuthorityText: document.querySelector('#ai-authority-text'), aiCallCount: document.querySelector('#ai-call-count'),
  aiTokenCount: document.querySelector('#ai-token-count'), aiCostToday: document.querySelector('#ai-cost-today'),
  aiControlBadge: document.querySelector('#ai-control-badge'), aiStopBtn: document.querySelector('#ai-stop-btn'),
  aiBudgetInput: document.querySelector('#ai-budget-input'), aiBudgetSave: document.querySelector('#ai-budget-save'),
  geminiStatusDot: document.querySelector('#gemini-status-dot'), geminiConnectionText: document.querySelector('#gemini-connection-text'),
  geminiModel: document.querySelector('#gemini-model'), geminiTestBtn: document.querySelector('#gemini-test-btn'),
  geminiTestResult: document.querySelector('#gemini-test-result'),
  openaiStatusDot: document.querySelector('#openai-status-dot'), openaiConnectionText: document.querySelector('#openai-connection-text'),
  openaiModel: document.querySelector('#openai-model'), openaiTestBtn: document.querySelector('#openai-test-btn'),
  openaiTestResult: document.querySelector('#openai-test-result'),
  routeChief: document.querySelector('#route-chief'), routeResearch: document.querySelector('#route-research'),
  routePrograms: document.querySelector('#route-programs'), routeCaretaker: document.querySelector('#route-caretaker'),
  pondWeatherWidget: document.querySelector('#pond-weather-widget')
};

let state = null;
let activeView = { panel: 'map', id: null, parent: null };
let activeDeliverableId = null;
const projectTabById = new Map();
let repositoryQuery = '';
let repositoryKind = 'all';
let memoryQuery = '';
let memoryType = 'all';
let memoryStatus = 'Active';
let memoryReview = 'all';
let memoryEditingId = null;
let memorySupersedeId = null;
let playbookStatus = 'all';
let playbookEditingId = null;
let libraryQuery = '';
let libraryType = 'all';
let libraryStatus = 'Active';
let libraryEditingId = null;
let grantEditingId = null;
let calendarEditingId = null;
let grantDiscoveryResult = null;
let grantDiscoveryLoading = false;
let grantImportingKey = null;
let vernadetteCommandResult = null;
let vernadetteCommandSubmitting = false;
let librarianQuery = '';
let librarianResult = null;
let workReport = null;
let workReportLoading = false;
let poeCommandResult = null;
let poeCommandSubmitting = false;
let stellaDailyResult = null;
let stellaDailySubmitting = false;
let workReportFilters = {person_id:'',activity_category_id:'',project_id:'',participation_type:'',start_date:'',end_date:''};
let chiefPlanSubmitting = false;
let campusAskSubmitting = false;
let campusAskLastResult = null;
let campusAskHistory = [];
const CAMPUS_ASK_SESSION_KEY='mavis-campus-ask-thread-v093';
let worldBuilt = false;
const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
const { routeNodes, routeEdges, buildingNode } = worldConfig;
const agentNudge = { chief:{x:-3.2,y:0}, operations:{x:4.6,y:3.2}, grants:{x:3.5,y:-1.2}, programs:{x:-4.2,y:0.9}, research:{x:1.5,y:0}, caretaker:{x:2.1,y:-1.2} };
const agentRuntime = new Map();
let ambientCycleTimer = null;
let ambientStarted = false;
const ambientDestinationChoices = {
  chief:['barn','library','forest','pond'],
  programs:['library','manor','forest','pond'],
  research:['barn','manor','forest','pond'],
  caretaker:['pond','barn','library','manor'],
  grants:['library','barn','forest','pond'],
  operations:['manor','library','forest','pond']
};
const CAMPUS_ASK_HISTORY_LIMIT = 20;

createCamera(els.viewport, els.stage, { zoomIn:els.zoomIn, zoomOut:els.zoomOut, home:els.home, zoomLabel:els.zoomLabel });

function esc(v=''){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));}
function toast(msg){els.toast.textContent=msg;els.toast.classList.add('show');setTimeout(()=>els.toast.classList.remove('show'),2600);}
function titleCase(s=''){return s.replace(/\b\w/g,m=>m.toUpperCase());}
function displayWorkflowText(v=''){
  return String(v||'')
    .replaceAll('Chief of Staff','Stella · Chief of Staff')
    .replaceAll("Chief's","Stella's")
    .replaceAll('Chief final review','Stella final review')
    .replaceAll('The Chief','Stella')
    .replaceAll('the Chief','Stella')
    .replaceAll('Chief plan','Stella plan')
    .replaceAll('Chief review','Stella review');
}
function fmtNumber(value=0){return Number(value||0).toLocaleString();}
function fmtBytes(value=0){const n=Number(value||0);if(n<1024)return `${n} B`;if(n<1048576)return `${(n/1024).toFixed(1)} KB`;if(n<1073741824)return `${(n/1048576).toFixed(1)} MB`;return `${(n/1073741824).toFixed(1)} GB`;}
function fmtMoney(value=0,digits=4){return `$${Number(value||0).toFixed(digits)}`;}
function operationLabel(value=''){
  return ({
    chief_plan:'Stella planning',
    research_task:'Research',
    programs_task:'Programs',
    chief_final_review:'Stella final review',
    chief_revision_plan:'Stella revision planning',
    connection_test:'Connection test'
  })[value]||titleCase(String(value).replaceAll('_',' '));
}
function deliverablesForProject(id){
  return (state?.deliverables||[]).filter(d=>Number(d.project_id)===Number(id));
}
function deliverableById(id){
  return (state?.deliverables||[]).find(d=>Number(d.id)===Number(id));
}
function repositoryFilesForProject(id){
  return (state?.project_files||[]).filter(f=>Number(f.project_id)===Number(id));
}
function repositoryFileKindLabel(kind='other'){
  return ({pdf:'PDF',slides:'Slides',document:'Document',spreadsheet:'Spreadsheet',image:'Image',text:'Text',archive:'Archive',other:'Other'})[kind]||titleCase(kind);
}
function repositoryFileIcon(kind='other'){
  return ({pdf:'▧',slides:'▤',document:'▥',spreadsheet:'▦',image:'▣',text:'≡',archive:'▰',other:'◆'})[kind]||'◆';
}
function repositoryFileCard(file,{showProject=false}={}){
  const canView=['pdf','image','text'].includes(file.file_kind)&&file.exists!==false;
  return `<article class="repository-file-card kind-${esc(file.file_kind)}">
    <div class="repository-file-icon">${repositoryFileIcon(file.file_kind)}</div>
    <div class="repository-file-copy">
      <span class="repository-file-kind">${esc(repositoryFileKindLabel(file.file_kind))}${showProject?` · ${esc(file.project_title||'Project')}`:''}</span>
      <strong>${esc(file.display_name||file.filename)}</strong>
      <small>${esc(file.filename)} · v${esc(file.version||1)} · ${esc(file.status||'Current')} · ${esc(file.created_by||'Campus')}</small>
      ${file.exists===false?'<em>File is registered but missing from disk.</em>':''}
    </div>
    <div class="repository-file-actions">
      ${canView?`<a href="/api/repository/files/${file.id}/view" target="_blank" rel="noopener">Open</a>`:''}
      ${file.exists!==false?`<a href="/api/repository/files/${file.id}/download">Download</a>`:''}
      ${showProject?`<button type="button" data-open-project="${file.project_id}">Project</button>`:''}
    </div>
  </article>`;
}

function memoriesForProject(id,{includeInstitution=true}={}){
  return (state?.institutional_memory||[]).filter(m=>{
    const own=Number(m.project_id)===Number(id);
    return own||(includeInstitution&&m.project_id==null);
  });
}
function memoryTypeIcon(type='Context'){
  return ({Decision:'✓',Fact:'◆',Policy:'§',Lesson:'↺',Preference:'★',Context:'◈'})[type]||'◈';
}
function memoryReviewLabel(m){
  if(Number(m.review_interval_days||0)===0)return 'Review: not scheduled';
  if(m.review_due)return `Review due${Number(m.review_overdue_days||0)>0?` · ${m.review_overdue_days}d overdue`:''}`;
  return m.review_due_at?`Review by ${fmtTime(m.review_due_at,true)}`:'Review schedule pending';
}
function memoryCard(m,{showProject=true}={}){
  const archived=m.status==='Archived';
  const scope=m.project_id==null?'Institution-wide':(m.project_title||`Project #${m.project_id}`);
  return `<article class="memory-card ${archived?'archived':''} importance-${String(m.importance||'Normal').toLowerCase()}">
    <div class="memory-icon">${memoryTypeIcon(m.memory_type)}</div>
    <div class="memory-copy">
      <span class="memory-meta">${esc(m.memory_type)} · ${esc(scope)} · ${esc(m.importance||'Normal')}</span>
      <strong>${esc(m.title)}</strong>
      <p>${esc(m.body)}</p>
      ${m.tags?`<small>Tags: ${esc(m.tags)}</small>`:''}
      <small>Source: ${esc(m.source_kind||'manual')}${m.source_id!=null?` #${esc(m.source_id)}`:''} · ${esc(m.created_by||'Human')} · ${fmtTime(m.updated_at,true)}</small>
      <small class="memory-review-state ${m.review_due?'due':'fresh'}">${esc(memoryReviewLabel(m))}${m.supersedes_id?` · replaces #${esc(m.supersedes_id)}`:''}${m.superseded_by_id?` · replaced by #${esc(m.superseded_by_id)}`:''}</small>
    </div>
    <div class="memory-actions">
      ${showProject&&m.project_id!=null?`<button type="button" data-open-project="${m.project_id}">Project</button>`:''}
      <button type="button" data-memory-review="${m.id}">Mark Reviewed</button>
      ${!m.superseded_by_id?`<button type="button" data-memory-supersede="${m.id}">Supersede</button>`:''}
      <button type="button" data-memory-edit="${m.id}">Edit</button>
      <button type="button" data-memory-status="${m.id}" data-memory-status-value="${archived?'Active':'Archived'}">${archived?'Restore':'Archive'}</button>
    </div>
  </article>`;
}
function memoryForm({projectId=null,memory=null,mode="edit"}={}){
  const editing=Boolean(memory);
  const superseding=editing&&mode==="supersede";
  const selectedProject=editing?memory.project_id:projectId;
  const scopeField=projectId!=null
    ? `<input type="hidden" name="project_id" value="${projectId}"><small class="memory-scope-note">This memory is scoped to ${esc(projectById(projectId)?.title||`Project #${projectId}`)}.</small>`
    : `<label>Scope<select name="project_id"><option value=""${selectedProject==null?' selected':''}>Institution-wide</option>${(state.projects||[]).map(p=>`<option value="${p.id}"${Number(selectedProject)===Number(p.id)?' selected':''}>${esc(p.title)}</option>`).join('')}</select></label>`;
  const selectedType=memory?.memory_type||'Context';
  const selectedImportance=memory?.importance||'Normal';
  const selectedReview=Number(memory?.review_interval_days??180);
  return `<form class="memory-form" data-memory-form${editing?` data-memory-edit-id="${memory.id}"`:''}${superseding?` data-memory-supersede-id="${memory.id}"`:''}${projectId!=null?` data-memory-project="${projectId}"`:''}>
    <div class="memory-form-grid">
      <label>Type<select name="memory_type">${['Decision','Fact','Policy','Lesson','Preference','Context'].map(t=>`<option value="${t}"${selectedType===t?' selected':''}>${t}</option>`).join('')}</select></label>
      <label>Importance<select name="importance"><option value="Normal"${selectedImportance==='Normal'?' selected':''}>Normal</option><option value="Core"${selectedImportance==='Core'?' selected':''}>Core</option></select></label>
      ${scopeField}
      <label>Review<select name="review_interval_days"><option value="90"${selectedReview===90?' selected':''}>Every 90 days</option><option value="180"${selectedReview===180?' selected':''}>Every 180 days</option><option value="365"${selectedReview===365?' selected':''}>Every year</option><option value="0"${selectedReview===0?' selected':''}>No scheduled review</option></select></label>
    </div>
    <label>Title<input name="title" maxlength="180" required value="${esc(memory?.title||'')}" placeholder="What should the institution remember?"></label>
    <label>Memory<textarea name="body" rows="4" maxlength="5000" required placeholder="Record the durable decision, fact, policy, lesson, preference, or context...">${esc(memory?.body||'')}</textarea></label>
    <label>Tags<input name="tags" maxlength="500" value="${esc(memory?.tags||'')}" placeholder="Optional comma-separated tags"></label>
    <div class="memory-form-actions"><button type="submit">${superseding?'Create Replacement Memory':editing?'Save Memory Changes':'Save to Institutional Memory'}</button>${editing?'<button type="button" class="button-quiet" data-memory-edit-cancel>Cancel</button>':''}</div>
    ${editing&&memory?.source_kind!=='manual'?`<small class="memory-scope-note">Provenance stays attached: ${esc(memory.source_kind)} #${esc(memory.source_id)}.</small>`:''}
  </form>`;
}

function expectedDeliverables(plan){
  if(!plan)return[];
  try{
    const value=JSON.parse(plan.expected_deliverables_json||'[]');
    return Array.isArray(value)?value:[];
  }catch{return[];}
}
function verificationItems(d){
  try{
    const value=JSON.parse(d.verification_json||'[]');
    return Array.isArray(value)?value:[];
  }catch{return[];}
}
function deliverableStatusClass(status=''){
  return String(status).toLowerCase().replaceAll(' ','-').replaceAll('_','-');
}
function markdownInline(value=''){
  return esc(value).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
}
function renderSimpleMarkdown(markdown=''){
  const lines=String(markdown||'').replace(/\r/g,'').split('\n');
  let html='',listOpen=false;
  const closeList=()=>{if(listOpen){html+='</ul>';listOpen=false;}};
  for(const raw of lines){
    const line=raw.trimEnd();
    if(!line.trim()){closeList();continue;}
    if(/^---+$/.test(line.trim())){closeList();html+='<hr>';continue;}
    const heading=line.match(/^(#{1,4})\s+(.*)$/);
    if(heading){
      closeList();
      const level=Math.min(4,heading[1].length+1);
      html+=`<h${level}>${markdownInline(heading[2])}</h${level}>`;
      continue;
    }
    const bullet=line.match(/^\s*[-•]\s+(.*)$/);
    if(bullet){
      if(!listOpen){html+='<ul>';listOpen=true;}
      html+=`<li>${markdownInline(bullet[1])}</li>`;
      continue;
    }
    closeList();
    html+=`<p>${markdownInline(line)}</p>`;
  }
  closeList();
  return html||'<p>No content.</p>';
}
function plainTextFromMarkdown(markdown=''){
  return String(markdown||'')
    .replace(/^#{1,6}\s+/gm,'')
    .replace(/^\s*[-•]\s+/gm,'• ')
    .replace(/\*\*/g,'')
    .replace(/^---+$/gm,'');
}
function safeFilename(value='deliverable'){
  return String(value||'deliverable')
    .replace(/[<>:"/\\|?*\x00-\x1F]/g,'')
    .replace(/\s+/g,' ')
    .trim()
    .slice(0,100)||'deliverable';
}
function downloadText(filename,content,type='text/plain'){
  const blob=new Blob([content],{type:`${type};charset=utf-8`});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),500);
}
function openDeliverable(id){
  const d=deliverableById(id);if(!d||!els.deliverableModal)return;
  activeDeliverableId=Number(d.id);
  els.deliverableModalTitle.textContent=d.title;
  const verify=verificationItems(d);
  const source=[d.created_by,d.provider,d.model].filter(Boolean).join(' · ');
  els.deliverableModalMeta.textContent=`${d.status} · v${d.version}${source?` · ${source}`:''}${verify.length?` · ${verify.length} verification flag${verify.length===1?'':'s'}`:''}`;
  els.deliverableModalBody.innerHTML=renderSimpleMarkdown(d.content_md);
  els.deliverableModal.hidden=false;
  els.deliverableModal.setAttribute('aria-hidden','false');
  requestAnimationFrame(()=>{els.deliverableModalBody.scrollTop=0;els.deliverableModalBody.focus({preventScroll:true});});
}
function closeDeliverable(){
  if(!els.deliverableModal)return;
  els.deliverableModal.hidden=true;
  els.deliverableModal.setAttribute('aria-hidden','true');
  activeDeliverableId=null;
}
async function copyActiveDeliverable(){
  const d=deliverableById(activeDeliverableId);if(!d)return;
  try{
    await navigator.clipboard.writeText(d.content_md||'');
    toast('Project output copied.');
  }catch{
    toast('Copy failed. Your browser may require clipboard permission.');
  }
}
function downloadActiveDeliverable(ext){
  const d=deliverableById(activeDeliverableId);if(!d)return;
  const base=safeFilename(d.title);
  if(ext==='md')downloadText(`${base}.md`,d.content_md||'','text/markdown');
  else downloadText(`${base}.txt`,plainTextFromMarkdown(d.content_md||''),'text/plain');
}
function printActiveDeliverable(){
  const d=deliverableById(activeDeliverableId);if(!d)return;
  document.body.classList.add('printing-deliverable');
  document.title=d.title;
  window.print();
  setTimeout(()=>{document.body.classList.remove('printing-deliverable');document.title='Mavis Digital Campus';},200);
}

function recommendationLabel(value=''){
  return ({
    approve_internal:'Approve internal',
    revise:'Revision recommended',
    hold:'Hold recommended',
    review:'Review needed'
  })[value]||'';
}
function approvalMeta(a){
  const project=projectById(a.project_id);
  const revisionPlan=a.stage==='revision_plan'||String(a.title||'').startsWith('Approve revision plan:');
  if(revisionPlan){
    return {
      stage:'revision_plan',
      recommendation:null,
      className:'revision-plan',
      kicker:'Selective revision plan',
      railTitle:'Revision Plan Approval',
      railSubtitle:'Stella selected what should reopen',
      approveLabel:'Approve selective revision',
      changesLabel:'Change revision plan',
      helper:'Approval reopens only the tasks and outputs selected by Stella. Preserved outputs keep their current versions. No external action is authorized.'
    };
  }

  const finalReview=a.stage==='final_review'||String(a.title||'').startsWith('Chief final review:');
  if(!finalReview){
    return {
      stage:'plan',
      recommendation:null,
      className:'plan',
      kicker:'Plan approval',
      railTitle:'Plan Approval',
      railSubtitle:'Stella plan · human gate',
      approveLabel:'Approve plan',
      changesLabel:'Request plan changes',
      helper:'Approve to start the internal campus workflow. No external action is authorized.'
    };
  }

  const rec=a.chief_recommendation||'review';
  if(rec==='approve_internal'){
    return {
      stage:'final_review',recommendation:rec,className:'approve',
      kicker:'Stella recommends approval',
      railTitle:'Approval Ready',
      railSubtitle:'Stella recommends accept',
      approveLabel:'Approve internal package',
      changesLabel:'Request changes',
      helper:'Stella recommends accepting the internal package. Public or external action still requires a separate future decision.'
    };
  }
  if(rec==='revise'){
    return {
      stage:'final_review',recommendation:rec,className:'revise',
      kicker:'Stella recommends revision',
      railTitle:'Revision Recommended',
      railSubtitle:'Human decision needed',
      approveLabel:'Approve anyway',
      changesLabel:'Request revisions',
      helper:'Stella recommends revision. Request revisions to move the project into Needs Revision, or approve anyway if you accept the internal package as-is.'
    };
  }
  if(rec==='hold'){
    return {
      stage:'final_review',recommendation:rec,className:'hold',
      kicker:'Stella recommends hold',
      railTitle:'Decision Needed',
      railSubtitle:'Stella recommends hold',
      approveLabel:'Approve anyway',
      changesLabel:'Request changes',
      helper:'Stella recommends holding this package. Close the panel to leave it pending, or request changes to move it into Needs Revision.'
    };
  }
  return {
    stage:'final_review',recommendation:rec,className:'review',
    kicker:'Stella final review',
    railTitle:'Decision Needed',
    railSubtitle:'Human gate',
    approveLabel:'Approve internal package',
    changesLabel:'Request changes',
    helper:'Review Stella’s package and choose whether to accept it or request changes.'
  };
}
function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms));}
function buildingById(id){return state?.buildings.find(b=>b.id===id);}
function agentById(id){return state?.agents.find(a=>a.id===id);}
function projectById(id){return state?.projects.find(p=>p.id===Number(id));}
function taskById(id){return state?.tasks.find(t=>t.id===Number(id));}
function ownerName(id){return agentById(id)?.name || id || 'Unassigned';}
function fmtTime(iso, includeDate=false){if(!iso)return '';const d=new Date(iso);return includeDate?d.toLocaleString():d.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});}
function notesForProject(projectId){return (state?.notes||[]).filter(n=>n.project_id===Number(projectId)&&n.task_id==null);}
function notesForTask(taskId){return (state?.notes||[]).filter(n=>n.task_id===Number(taskId));}
function projectTasks(projectId){return (state?.tasks||[]).filter(t=>t.project_id===Number(projectId)).sort((a,b)=>a.sequence-b.sequence);}
function currentProject(){return state?.projects?.[0] || null;}
function statusClass(status=''){return status.toLowerCase().replaceAll(' ','-');}
function statusIcon(status=''){
  const s=status.toLowerCase();
  if(s.includes('blocked')) return '!';
  if(s.includes('research')) return '⌕';
  if(s.includes('walking')||s.includes('returning')||s.includes('carrying')) return '➜';
  if(s.includes('review')) return '▤';
  if(s.includes('waiting')) return '◷';
  if(s.includes('building')||s.includes('draft')||s.includes('outline')) return '✎';
  if(s.includes('delegat')||s.includes('brief')) return '↗';
  if(s.includes('deliver')||s.includes('completed')) return '✓';
  return '•';
}

function agentPortrait(a){
  const portraits={
    chief:'/static/assets/agents/chief-of-staff/portrait.jpg',
    programs:'/static/assets/agents/programs/portrait.jpg',
    research:'/static/assets/agents/research/portrait.jpg',
    caretaker:'/static/assets/agents/caretaker/portrait.jpg',
    operations:'/static/assets/ui/crest.svg',
    grants:'/static/assets/ui/crest.svg'
  };
  return portraits[a?.id] || assets.agents[a?.id];
}
function openConcept(kind){
  const concepts={
    chief:{title:'Stella — Chief of Staff — Character Sheet',src:'/static/assets/agents/chief-of-staff/master-sheet.png',alt:'Stella character concept sheet'},
    programs:{title:'Percy — Programs & Education — Character Sheet',src:'/static/assets/agents/programs/master-sheet.png',alt:'Percy character concept sheet'},
    research:{title:'Rose — Research & Archives — Character Sheet',src:'/static/assets/agents/research/master-sheet.png',alt:'Rose character concept sheet'},
    caretaker:{title:'Stewart — Land Steward — Character Sheet',src:'/static/assets/agents/caretaker/master-sheet.png',alt:'Stewart character concept sheet'},
    barn:{title:'Coopenheimer Barn — Concept Sheet',src:'/static/assets/buildings/coopenheimer-barn/master-sheet.png',alt:'Coopenheimer Barn concept art sheet'},
    manor:{title:'Mavis Manor — Concept Sheet',src:'/static/assets/buildings/mavis-manor/master-sheet.png',alt:'Mavis Manor concept art sheet'},
    library:{title:'Library of Mavis — Concept Sheet',src:'/static/assets/buildings/library-of-mavis/master-sheet.png',alt:'Library of Mavis concept art sheet'}
  };
  const c=concepts[kind]; if(!c||!els.conceptModal)return;
  els.conceptModalTitle.textContent=c.title;els.conceptModalImage.src=c.src;els.conceptModalImage.alt=c.alt;
  els.conceptModal.hidden=false;els.conceptModal.setAttribute('aria-hidden','false');document.body.classList.add('modal-open');
}
function agentConceptMeta(id){
  const meta={
    chief:{title:'Stella · Chief of Staff',copy:'Executive coordination · delegation, prioritization, and human approval.'},
    programs:{title:'Percy · Director of Programs & Education',copy:'Useful, grounded education · curriculum, workshops, teaching, and program development.'},
    research:{title:'Rose · Director of Research & Archives',copy:'Research, verification, archives, provenance, and institutional memory.'},
    caretaker:{title:'Stewart · Land Steward',copy:'Grounds, infrastructure, living systems, weather, seasons, and practical land stewardship.'}
  };
  return meta[id]||null;
}

function closeConcept(){
  if(!els.conceptModal)return;els.conceptModal.hidden=true;els.conceptModal.setAttribute('aria-hidden','true');document.body.classList.remove('modal-open');
}

function buildWorldDecor(){
  if(worldBuilt) return;
  worldBuilt = true;
  els.forest.innerHTML = forestPlacements.map(([kind,x,y,s])=>`<img class="forest-tree" src="${assets.vegetation[kind]}" style="left:${x}%;top:${y}%;--s:${s}" alt="" />`).join('') +
    `<img class="forest-understory" src="${assets.vegetation.shrub}" style="left:10%;top:63%" alt=""><img class="forest-understory" src="${assets.vegetation.shrub}" style="left:57%;top:61%" alt=""><img class="forest-understory" src="${assets.vegetation.shrub}" style="left:75%;top:79%" alt=""><img class="forest-flowers" src="${assets.vegetation.flowers}" style="left:31%;top:84%" alt=""><img class="forest-flowers" src="${assets.vegetation.flowers}" style="left:67%;top:33%" alt="">`;
  els.props.innerHTML = worldProps.map(p=>{
    const src = p.type==='flowers'?assets.vegetation.flowers:p.type==='shrub'?assets.vegetation.shrub:assets.props[p.type];
    return `<img class="world-prop ${p.type}" src="${src}" style="left:${p.x}%;top:${p.y}%;--r:${p.rotate||0}deg" alt="">`;
  }).join('');
}

function artForBuilding(id){
  if(id==='fruit_forest') return `<span class="zone-hit-area" aria-hidden="true"></span>`;
  const src=assets.buildings[id];
  return `<img class="building-sprite" src="${src}" alt="" aria-hidden="true">`;
}
function renderBuildings(){
  if(els.buildings.children.length) return;
  els.buildings.innerHTML = state.buildings.map(b=>`<button type="button" class="building-hit ${b.kind||'building'} ${b.id}" data-building="${esc(b.id)}" style="left:${b.x}%;top:${b.y}%" aria-label="Open ${esc(b.name)}">${artForBuilding(b.id)}<span class="map-label">${esc(b.name)}</span></button>`).join('');
  els.buildings.querySelectorAll('[data-building]').forEach(btn=>btn.addEventListener('click',()=>showBuilding(btn.dataset.building)));
}
function showBuilding(id){
  const b=buildingById(id); if(!b)return;
  const present=state.agents.filter(a=>a.building_id===id);
  const team=state.agents.filter(a=>a.home_building_id===id);
  const teamIds=new Set(team.map(a=>a.id));
  const tasks=state.tasks.filter(t=>teamIds.has(t.owner_agent_id)&&t.status!=='Completed');
  els.buildingPanel.innerHTML=`<div class="building-panel-kicker">${b.kind==='zone'?'Campus Zone':'Department'}</div><h3>${esc(b.name)}</h3><p>${esc(b.purpose)}</p><dl><div><dt>Home team</dt><dd>${team.length?team.map(a=>esc(a.name)).join(', '):'No assigned department yet'}</dd></div><div><dt>Staff here now</dt><dd>${present.length?present.map(a=>esc(a.name)).join(', '):'None'}</dd></div><div><dt>Open work</dt><dd>${tasks.length?tasks.map(t=>esc(t.title)).join('<br>'):'No open assigned tasks'}</dd></div></dl><button type="button" class="panel-open-btn" id="open-location-view">Open ${b.kind==='zone'?'location':'department'}</button>`;
  els.buildingPanel.classList.add('open');
  els.buildingPanel.querySelector('#open-location-view')?.addEventListener('click',()=>openDrawer('department',id));
}

function findNodeRoute(start,goal){
  if(!start || !goal || start===goal) return goal?[goal]:[];
  const queue=[[start]], visited=new Set([start]);
  while(queue.length){
    const path=queue.shift(), here=path[path.length-1];
    for(const next of routeEdges[here]||[]){
      if(visited.has(next)) continue;
      const candidate=[...path,next];
      if(next===goal) return candidate;
      visited.add(next); queue.push(candidate);
    }
  }
  return [start,goal];
}
function findRoute(fromBuilding,toBuilding){
  return findNodeRoute(buildingNode[fromBuilding],buildingNode[toBuilding]);
}
function getAgentNode(agent){
  let node=document.querySelector(`.agent-token[data-agent-id="${agent.id}"]`);
  if(node) return node;
  node=document.createElement('button'); node.type='button'; node.className=`agent-token ${agent.id}`; node.dataset.agentId=agent.id; node.setAttribute('aria-label',`Open ${agent.name}`);
  const sprite=assets.agents[agent.id];node.innerHTML=`<div class="agent-status-icon"></div><div class="agent-sprite${sprite?'':' provisional-sprite'}"${sprite?` style="background-image:url('${sprite}')"`:''}></div><div class="agent-label"><strong></strong><span></span></div>`;
  node.addEventListener('click',()=>openDrawer('agent',agent.id,'people'));
  els.agents.appendChild(node); return node;
}
function positionNode(node,point,agentId,withNudge=true){const n=withNudge?(agentNudge[agentId]||{x:0,y:0}):{x:0,y:0};node.style.left=`${point.x+n.x}%`;node.style.top=`${point.y+n.y}%`;}
function setAgentLabel(node,agent){
  const runtime=agentRuntime.get(agent.id);
  node.querySelector('.agent-label strong').textContent=agent.name;
  node.querySelector('.agent-label span').textContent=runtime?.ambientLabel||agent.status;
  node.querySelector('.agent-status-icon').textContent=statusIcon(agent.status);
}
function setFacing(node,from,to){const dx=to.x-from.x;node.classList.toggle('facing-left',dx<0);node.classList.toggle('facing-right',dx>=0);}
function drawRoute(agentId, route){
  if(!els.routeLayer||route.length<2)return null;
  els.routeLayer.querySelector(`[data-route-agent="${agentId}"]`)?.remove();
  const poly=document.createElementNS('http://www.w3.org/2000/svg','polyline');poly.dataset.routeAgent=agentId;
  poly.setAttribute('points',route.map(id=>`${routeNodes[id].x},${routeNodes[id].y}`).join(' '));poly.setAttribute('class',`active-route route-${agentId}`);els.routeLayer.appendChild(poly);return poly;
}
async function animateRoute(agent,fromBuilding,toBuilding){
  const runtime=agentRuntime.get(agent.id); if(!runtime)return;
  runtime.moving=true;runtime.targetBuilding=toBuilding;
  const node=getAgentNode(agent);node.classList.add('walking');const route=findRoute(fromBuilding,toBuilding);const line=drawRoute(agent.id,route);
  if(prefersReducedMotion||route.length<2){const last=routeNodes[buildingNode[toBuilding]];if(last)positionNode(node,last,agent.id,true);}else{
    for(let i=1;i<route.length;i++){
      const prev=routeNodes[route[i-1]], next=routeNodes[route[i]], isLast=i===route.length-1;
      setFacing(node,prev,next);positionNode(node,next,agent.id,isLast);await sleep(500);
    }
  }
  runtime.currentBuilding=toBuilding;runtime.moving=false;runtime.targetBuilding=null;node.classList.remove('walking');
  if(line){line.classList.add('route-complete');setTimeout(()=>line.remove(),900);}
  if(runtime.queuedBuilding&&runtime.queuedBuilding!==runtime.currentBuilding){const queued=runtime.queuedBuilding;runtime.queuedBuilding=null;animateRoute(agent,runtime.currentBuilding,queued);}
}
function agentCanAmbientWander(agent){
  return Boolean(agent && String(agent.status||'').trim().toLowerCase()==='available' && !agent.task_id);
}
function ambientPlaceLabel(nodeId){
  return ({pond:'Walking by the pond',forest:'In the Fruit Forest',barn:'Visiting the barn',library:'At the Library',manor:'At Mavis Manor'})[nodeId]||'Taking a campus walk';
}
function cancelAmbientMovement(agentId,{snap=true}={}){
  const runtime=agentRuntime.get(agentId);
  if(runtime){runtime.ambientToken=(runtime.ambientToken||0)+1;runtime.ambient=false;runtime.ambientLabel='';runtime.ambientDestination=null;}
  const node=document.querySelector(`.agent-token[data-agent-id="${agentId}"]`);
  if(node){
    node.classList.remove('ambient-walking','ambient-idle','ambient-social');
    if(!runtime?.moving)node.classList.remove('walking');
    if(snap&&runtime?.currentBuilding){const base=routeNodes[buildingNode[runtime.currentBuilding]];if(base)positionNode(node,base,agentId,true);}
    const live=(state?.agents||[]).find(a=>a.id===agentId);if(live)setAgentLabel(node,live);
  }
}
async function walkAmbientRoute(agent,route,token,{stepMs=560}={}){
  const runtime=agentRuntime.get(agent.id),node=getAgentNode(agent);if(!runtime||route.length<1)return false;
  node.classList.add('walking','ambient-walking');node.classList.remove('ambient-idle');
  for(let i=1;i<route.length;i++){
    if(!runtime.ambient||runtime.ambientToken!==token||runtime.moving)return false;
    const prev=routeNodes[route[i-1]],next=routeNodes[route[i]];if(!prev||!next)continue;
    setFacing(node,prev,next);positionNode(node,next,agent.id,true);await sleep(stepMs);
  }
  node.classList.remove('walking','ambient-walking');node.classList.add('ambient-idle');
  return runtime.ambient&&runtime.ambientToken===token&&!runtime.moving;
}
async function ambientTravelAgent(agent,destinationNode,{companionName='',lingerMs=null}={}){
  if(prefersReducedMotion||document.hidden||!agentCanAmbientWander(agent))return;
  const runtime=agentRuntime.get(agent.id);if(!runtime||runtime.moving||runtime.ambient)return;
  const startNode=buildingNode[runtime.currentBuilding];if(!startNode||!routeNodes[destinationNode]||destinationNode===startNode)return;
  runtime.ambient=true;runtime.ambientDestination=destinationNode;runtime.ambientToken=(runtime.ambientToken||0)+1;
  const token=runtime.ambientToken,node=getAgentNode(agent);
  runtime.ambientLabel=companionName?`Walking with ${companionName}`:ambientPlaceLabel(destinationNode);setAgentLabel(node,agent);
  if(companionName)node.classList.add('ambient-social');
  const outRoute=findNodeRoute(startNode,destinationNode);
  if(!await walkAmbientRoute(agent,outRoute,token))return;
  runtime.ambientLabel=companionName?`Visiting with ${companionName}`:ambientPlaceLabel(destinationNode);setAgentLabel(node,agent);
  const pause=lingerMs??(8000+Math.floor(Math.random()*10000));await sleep(pause);
  if(!runtime.ambient||runtime.ambientToken!==token||runtime.moving)return;
  runtime.ambientLabel=companionName?`Walking with ${companionName}`:'Heading home';setAgentLabel(node,agent);
  const backRoute=findNodeRoute(destinationNode,startNode);
  if(!await walkAmbientRoute(agent,backRoute,token))return;
  if(runtime.ambientToken!==token)return;
  runtime.ambient=false;runtime.ambientLabel='';runtime.ambientDestination=null;
  node.classList.remove('walking','ambient-walking','ambient-idle','ambient-social');
  const base=routeNodes[startNode];if(base)positionNode(node,base,agent.id,true);setAgentLabel(node,agent);
}
function chooseAmbientDestination(agent){
  const runtime=agentRuntime.get(agent.id),start=buildingNode[runtime?.currentBuilding];
  const choices=(ambientDestinationChoices[agent.id]||['pond','forest','barn','library','manor']).filter(x=>x!==start&&routeNodes[x]);
  return choices.length?choices[Math.floor(Math.random()*choices.length)]:null;
}
function startAmbientMovement(){
  if(ambientStarted||prefersReducedMotion)return;ambientStarted=true;
  const schedule=()=>{
    const delay=5200+Math.floor(Math.random()*5200);
    ambientCycleTimer=setTimeout(()=>{
      if(state&&!document.hidden){
        const active=[...agentRuntime.values()].filter(r=>r.ambient||r.moving).length;
        const eligible=(state.agents||[]).filter(a=>agentCanAmbientWander(a)&&!agentRuntime.get(a.id)?.moving&&!agentRuntime.get(a.id)?.ambient);
        if(active<2&&eligible.length){
          // Agents sharing a home sometimes head out together — especially Percy/Poe and Stella/Vernadette.
          const byHome=new Map();eligible.forEach(a=>{const home=agentRuntime.get(a.id)?.currentBuilding||a.building_id;if(!byHome.has(home))byHome.set(home,[]);byHome.get(home).push(a);});
          const pairs=[...byHome.values()].filter(group=>group.length>=2);
          if(pairs.length&&Math.random()<0.42&&active===0){
            const group=pairs[Math.floor(Math.random()*pairs.length)].slice(0,2);
            const destination=chooseAmbientDestination(group[0]);
            if(destination){
              const linger=9000+Math.floor(Math.random()*9000);
              ambientTravelAgent(group[0],destination,{companionName:group[1].name,lingerMs:linger});
              ambientTravelAgent(group[1],destination,{companionName:group[0].name,lingerMs:linger});
            }
          }else{
            const agent=eligible[Math.floor(Math.random()*eligible.length)],destination=chooseAmbientDestination(agent);
            if(destination)ambientTravelAgent(agent,destination);
          }
        }
      }
      schedule();
    },delay);
  };
  schedule();
}
function renderAgents(){
  const liveIds=new Set();
  state.agents.forEach(agent=>{
    liveIds.add(agent.id);const node=getAgentNode(agent);setAgentLabel(node,agent);let runtime=agentRuntime.get(agent.id);
    if(!runtime){runtime={currentBuilding:agent.building_id,moving:false,targetBuilding:null,queuedBuilding:null,ambient:false,ambientToken:0,ambientLabel:'',ambientDestination:null};agentRuntime.set(agent.id,runtime);const start=routeNodes[buildingNode[agent.building_id]];if(start)positionNode(node,start,agent.id,true);}
    if(agent.building_id!==runtime.currentBuilding){cancelAmbientMovement(agent.id,{snap:true});if(runtime.moving){if(agent.building_id!==runtime.targetBuilding)runtime.queuedBuilding=agent.building_id;}else animateRoute(agent,runtime.currentBuilding,agent.building_id);}
    else if(!agentCanAmbientWander(agent)&&runtime.ambient){cancelAmbientMovement(agent.id,{snap:true});}
  });
  document.querySelectorAll('.agent-token[data-agent-id]').forEach(node=>{if(!liveIds.has(node.dataset.agentId)){cancelAmbientMovement(node.dataset.agentId,{snap:false});agentRuntime.delete(node.dataset.agentId);node.remove();}});
}

function renderHudTasks(){
  const project=currentProject();const tasks=project?projectTasks(project.id):[];
  els.hudTaskCount.textContent=tasks.filter(t=>t.status!=='Completed').length;
  if(!tasks.length){els.hudTaskList.innerHTML='<p class="hud-empty">No active project.</p>';return;}
  els.hudTaskList.innerHTML=tasks.slice(0,4).map(t=>`<button type="button" class="hud-task" data-hud-task="${t.id}"><span>${statusIcon(t.status==='Waiting'?'waiting':t.status)}</span><div><span class="owner">${esc(ownerName(t.owner_agent_id))}</span><span class="task-name">${esc(displayWorkflowText(t.title))}</span></div><span class="mini-status">${esc(t.status)}</span></button>`).join('');
  els.hudTaskList.querySelectorAll('[data-hud-task]').forEach(btn=>btn.addEventListener('click',()=>openDrawer('task',btn.dataset.hudTask,'projects')));
}
function renderProject(){
  const p=currentProject();
  if(!p){els.projectSummary.className='project-summary empty-state';els.projectSummary.textContent='No active project.';els.projectBadge.textContent='Idle';els.taskList.innerHTML='';return;}
  els.projectBadge.textContent=p.status;
  els.projectSummary.className='project-summary';els.projectSummary.innerHTML=`<strong>${esc(p.title)}</strong><span>Status: ${esc(p.status)}</span><button type="button" class="inline-link" id="open-current-project">Open project</button>`;
  els.projectSummary.querySelector('#open-current-project')?.addEventListener('click',()=>openDrawer('project',p.id,'projects'));
  els.taskList.innerHTML=projectTasks(p.id).map(t=>`<button type="button" class="task-row" data-main-task="${t.id}"><div class="task-seq">${t.sequence}</div><div><div class="task-title">${esc(displayWorkflowText(t.title))}</div><div class="task-meta">Owner: ${esc(ownerName(t.owner_agent_id))}</div></div><div class="task-status ${statusClass(t.status)}">${esc(t.status)}</div>${t.result?`<div class="task-result">${esc(t.result)}</div>`:''}</button>`).join('');
  els.taskList.querySelectorAll('[data-main-task]').forEach(btn=>btn.addEventListener('click',()=>openDrawer('task',btn.dataset.mainTask,'projects')));
}
function renderApprovalBanner(){
  const pending=state.approvals.filter(a=>a.status==='Pending');els.approvalCount.textContent=pending.length;
  if(!pending.length){els.approvalBanner.hidden=true;els.approvalBanner.innerHTML='';return;}
  const a=pending[0];els.approvalBanner.hidden=false;els.approvalBanner.innerHTML=`<div class="approval-kicker">✓ Approval Ready</div><h3>${esc(displayWorkflowText(a.title))}</h3><p>${esc(displayWorkflowText(a.summary))}</p><button class="button-primary" id="review-approval" type="button">Review now</button>`;
  els.approvalBanner.querySelector('#review-approval').addEventListener('click',()=>openDrawer('approvals'));
}
function renderActivity(){
  if(!state.activity.length){els.activityList.innerHTML='<div class="empty-state">No activity yet.</div>';return;}
  els.activityList.innerHTML=state.activity.slice(0,30).map(a=>`<div class="activity-item"><strong>${esc(displayWorkflowText(a.actor))}</strong> — ${esc(displayWorkflowText(a.message))}<span class="activity-time">${fmtTime(a.created_at)} · ${esc(titleCase(a.event_type))}</span></div>`).join('');
}
function renderExecutiveBadge(){
  const e=state.executive||{};
  const count=Number.isFinite(Number(e.attention_count))
    ? Number(e.attention_count)
    : (e.pending_approvals||0)+(e.needs_revision||0)+(e.blocked_tasks||0);
  els.needsMeCount.textContent=count;
  els.needsMeBtn.classList.toggle('has-attention',count>0);
  const briefCount=Number(state.executive_briefing?.priority_count||0);
  if(els.briefingCount)els.briefingCount.textContent=briefCount;
  els.briefingBtn?.classList.toggle('has-attention',briefCount>0);
}

function renderDashboardRails(){
  const e=state.executive||{};
  const openTasks=state.tasks.filter(t=>t.status!=='Completed');
  const pending=state.approvals.filter(a=>a.status==='Pending');
  const setText=(id,value)=>{const n=document.querySelector(id);if(n)n.textContent=value;};

  setText('#top-project-count',state.projects.length);
  setText('#top-repository-count',(state.project_files||[]).filter(f=>f.status!=='Previous').length);
  setText('#top-memory-count',(state.institutional_memory||[]).filter(m=>m.status==='Active').length);
  setText('#top-playbook-count',(state.playbooks||[]).filter(p=>p.status==='Active').length);
  setText('#top-approval-count',pending.length);
  setText('#top-people-count',state.agents.length);
  setText('#rail-needs-count',e.attention_count??((e.pending_approvals||0)+(e.needs_revision||0)+(e.blocked_tasks||0)));
  setText('#rail-ready-count',e.ready_to_approve||0);
  setText('#rail-chief-revisions-count',e.revision_recommended||0);
  setText('#rail-hold-count',e.hold_recommended||0);
  setText('#rail-plan-count',e.plan_approvals||0);
  setText('#rail-revision-plan-count',e.revision_plan_approvals||0);
  setText('#rail-revisions-count',e.needs_revision||0);
  setText('#rail-blocked-count',e.blocked_tasks||0);
  setText('#overview-projects',e.active_projects||0);
  setText('#overview-tasks',openTasks.length);
  setText('#overview-approvals',pending.length);
  setText('#overview-outputs',(state.deliverables||[]).filter(d=>d.status!=='Superseded').length);
  setText('#overview-repository',(state.project_files||[]).filter(f=>f.status!=='Previous').length);
  setText('#overview-people',(state.people||[]).length);
  const health=state.system_health||{};
  const healthNode=document.querySelector('#system-health');
  if(healthNode){
    healthNode.textContent=health.ok
      ? (Number(health.interrupted_projects||0)>0?`${health.interrupted_projects} recovery`:`Schema ${health.schema_version||'OK'}`)
      : 'Needs attention';
    healthNode.classList.toggle('warning',!health.ok||Number(health.interrupted_projects||0)>0);
  }
  const compactStaffStatus=status=>{
    const x=String(status||'').toLowerCase();
    if(x.includes('blocked')||x.includes('failed'))return 'Needs help';
    if(x.includes('waiting'))return 'Waiting';
    if(x.includes('available'))return 'Available';
    if(x.includes('planning')||x.includes('working')||x.includes('review')||x.includes('research')||x.includes('prepar')||x.includes('synth')||x.includes('deliver')||x.includes('progress'))return 'Working';
    return status?'Active':'Available';
  };
  for(const [id,nodeId] of Object.entries({chief:'chief-team-status',programs:'programs-team-status',research:'research-team-status',caretaker:'caretaker-team-status',operations:'operations-team-status',grants:'grants-team-status'})){
    const a=agentById(id),node=document.querySelector(`#${nodeId}`);
    if(node&&a){node.textContent=compactStaffStatus(a.status);node.title=a.status||'';node.dataset.state=compactStaffStatus(a.status).toLowerCase().replaceAll(' ','-');}
  }

  const approvalNode=document.querySelector('#right-approval-card');
  const approvalTitle=document.querySelector('#approval-rail-title');
  const approvalSubtitle=document.querySelector('#approval-rail-subtitle');

  if(approvalNode){
    if(!pending.length){
      approvalNode.className='right-approval-card';
      approvalNode.innerHTML='<div class="right-empty">No decisions waiting.</div>';
      if(approvalTitle)approvalTitle.textContent='Approval Ready';
      if(approvalSubtitle)approvalSubtitle.textContent='Human gate';
    }else{
      const a=pending[0], meta=approvalMeta(a);
      approvalNode.className=`right-approval-card recommendation-${meta.className}`;
      if(approvalTitle)approvalTitle.textContent=meta.railTitle;
      if(approvalSubtitle)approvalSubtitle.textContent=meta.railSubtitle;

      const flags=[];
      if(Number(a.verification_count||0)>0)flags.push(`${a.verification_count} verification flag${Number(a.verification_count)===1?'':'s'}`);
      if(Number(a.gap_count||0)>0)flags.push(`${a.gap_count} gap${Number(a.gap_count)===1?'':'s'}`);

      approvalNode.innerHTML=`
        <div class="approval-kicker recommendation-${meta.className}">✓ ${esc(meta.kicker)}</div>
        <h3>${esc(displayWorkflowText(a.title))}</h3>
        <p>${esc(displayWorkflowText(a.chief_review_summary||a.summary))}</p>
        ${flags.length?`<div class="approval-mini-flags">${flags.map(x=>`<span>${esc(x)}</span>`).join('')}</div>`:''}
        <button type="button" data-open-panel="approvals">Review decision</button>`;
    }
  }
}

function backButton(panel,id=null){return `<button type="button" class="drawer-back" data-open-panel="${esc(panel)}"${id!=null?` data-open-id="${esc(id)}"`:''}>← Back</button>`;}
function workMinutesLabel(minutes){
  const m=Math.max(0,Number(minutes||0));
  if(m<60)return `${Math.round(m)} min`;
  const h=Math.floor(m/60),rem=Math.round(m%60);
  return rem?`${h} hr ${rem} min`:`${h} hr`;
}
function workReportParams(filters=workReportFilters){
  const params=new URLSearchParams();
  Object.entries(filters||{}).forEach(([key,value])=>{if(value!==''&&value!==null&&value!==undefined)params.set(key,String(value));});
  return params.toString();
}
function workReportBreakdown(title,items){
  return `<section class="drawer-section work-report-breakdown"><div class="section-row"><h4>${esc(title)}</h4><span>${items.length}</span></div>${items.length?`<div class="work-report-bars">${items.map(item=>`<div class="work-report-row"><span><strong>${esc(item.label)}</strong><small>${item.session_count} session${Number(item.session_count)===1?'':'s'}</small></span><b>${workMinutesLabel(item.minutes)}</b></div>`).join('')}</div>`:'<p>No matching hours.</p>'}</section>`;
}
function drawerWorkReport(){
  const people=state.people||[], categories=state.activity_categories||[], projects=state.projects||[];
  const f=workReportFilters||{};
  const select=(value,target)=>String(value??'')===String(target??'')?' selected':'';
  const report=workReport;
  const query=workReportParams(f);
  const filters=`<section class="drawer-section work-report-filter-card"><div class="section-row"><div><span class="profile-kicker">Poe · Work Hours</span><h4>Work Hours Report</h4></div><span>${report?.timezone_name?esc(report.timezone_name):'Campus time'}</span></div><p>Filter the same trusted work ledger for monthly reporting, grants, program records, or other documentation. Open clock sessions are not counted until they are clocked out.</p><form class="memory-form" data-work-report-form><div class="memory-form-grid"><label>From<input type="date" name="start_date" value="${esc(f.start_date||'')}"></label><label>Through<input type="date" name="end_date" value="${esc(f.end_date||'')}"></label><label>Person<select name="person_id"><option value="">All people</option>${people.map(x=>`<option value="${x.id}"${select(f.person_id,x.id)}>${esc(x.display_name)}</option>`).join('')}</select></label><label>Participation<select name="participation_type"><option value="">All participation</option>${['Volunteer','Learning','Paid'].map(x=>`<option${select(f.participation_type,x)}>${x}</option>`).join('')}</select></label><label>Activity<select name="activity_category_id"><option value="">All activities</option>${categories.map(x=>`<option value="${x.id}"${select(f.activity_category_id,x.id)}>${esc(x.name)}</option>`).join('')}</select></label><label>Project / Program<select name="project_id"><option value="">All projects</option>${projects.map(x=>`<option value="${x.id}"${select(f.project_id,x.id)}>${esc(x.title)}</option>`).join('')}</select></label></div><div class="memory-form-actions"><button class="button-primary" type="submit">Run Report</button><button type="button" class="button-quiet" data-work-report-reset>Clear Filters</button><a class="button-quiet work-report-export" href="/api/work-report.csv${query?`?${esc(query)}`:''}" download>Export CSV</a></div></form></section>`;
  if(workReportLoading&&!report)return `${backButton('people')}${filters}<section class="drawer-section"><p>Building Poe’s report…</p></section>`;
  if(!report)return `${backButton('people')}${filters}<section class="drawer-section"><p>Open the report to load recorded hours.</p></section>`;
  const sum=report.summary||{};
  const headline=`<section class="drawer-section"><div class="work-report-summary"><span><strong>${Number(sum.hours||0).toFixed(2)}</strong><small>hours</small></span><span><strong>${sum.session_count||0}</strong><small>sessions</small></span><span><strong>${sum.people_count||0}</strong><small>people</small></span></div></section>`;
  const monthly=workReportBreakdown('Monthly Totals',report.monthly||[]);
  const breakdowns=`<div class="work-report-two-col">${workReportBreakdown('By Person',report.by_person||[])}${workReportBreakdown('By Activity',report.by_activity||[])}</div><div class="work-report-two-col">${workReportBreakdown('By Participation',report.by_participation||[])}${workReportBreakdown('By Project / Program',report.by_project||[])}</div>`;
  const sessions=(report.sessions||[]);
  const sessionList=`<section class="drawer-section"><div class="section-row"><h4>Matching Work Sessions</h4><span>${sessions.length}</span></div>${sessions.length?`<div class="work-report-sessions">${sessions.slice(0,150).map(x=>`<div class="work-session-card"><div><strong>${esc(x.person_name)} · ${workMinutesLabel(x.duration_minutes)}</strong><small>${esc(x.local_date)} · ${esc(x.participation_type)} · ${esc(x.activity_name||'Uncategorized')}${x.project_title?` · ${esc(x.project_title)}`:''}</small>${x.notes?`<p>${esc(x.notes)}</p>`:''}</div><button type="button" class="button-quiet" data-work-edit="${x.id}">Correct</button></div>`).join('')}</div>${sessions.length>150?`<p class="work-report-note">Showing the newest 150 matching sessions here. CSV export includes all ${sessions.length} matching sessions.</p>`:''}`:'<p>No completed work sessions match these filters.</p>'}</section>`;
  return `${backButton('people')}${filters}${headline}${monthly}${breakdowns}${sessionList}`;
}

function poeConversationCard(){
  const result=poeCommandResult;
  const response=result?`<div class="poe-command-response ${esc(result.status||'ok')}"><strong>${result.status==='clarification'?'Poe needs one detail':'Poe'}</strong><p>${esc(result.message||'')}</p>${result.report_filters?'<button type="button" class="button-quiet" data-poe-open-report>Open These Hours</button>':''}</div>`:'';
  return `<section class="drawer-section poe-command-card"><div class="section-row"><div><span class="profile-kicker">Talk to Poe</span><h4>Natural Work Commands</h4></div><span>local · no AI call</span></div><p>Tell Poe what happened in ordinary language. He only changes the People & Work ledger when the command is clear enough to do safely.</p><form class="poe-command-form" data-poe-command-form><label>What should Poe do?<textarea name="text" rows="3" maxlength="1000" placeholder="Poe, clock me in for farm work on the Monastic Garden."></textarea></label><div class="poe-command-examples"><span>Try:</span><button type="button" data-poe-example="Poe, clock me in for farm work.">Clock me in</button><button type="button" data-poe-example="Poe, show me our education hours this month.">Show hours</button><button type="button" data-poe-example="Poe, add 2 hours yesterday for Sam doing maintenance.">Remember past work</button></div><div class="memory-form-actions"><button class="button-primary" type="submit" ${poeCommandSubmitting?'disabled':''}>${poeCommandSubmitting?'Poe is checking…':'Ask Poe'}</button></div></form>${response}</section>`;
}

function eventById(id){return (state.events||[]).find(x=>Number(x.id)===Number(id));}
function calendarTimeLabel(x){
  if(Number(x?.all_day||0))return 'All day';
  const start=x?.start_time||'',end=x?.end_time||'';
  return start&&end?`${start}–${end}`:(start||'Time not set');
}
function calendarEventCard(x){
  return `<article class="calendar-event-card level-${esc(String(x.commitment_level||'Normal').toLowerCase())} ${x.status==='Cancelled'?'is-cancelled':''}"><div><span class="profile-kicker">${esc(x.event_type||'Event')} · ${esc(x.commitment_level||'Normal')}</span><strong>${esc(x.title||'Untitled event')}</strong><small>${esc(x.event_date||'')} · ${esc(calendarTimeLabel(x))}${x.location?` · ${esc(x.location)}`:''}${x.project_title?` · ${esc(x.project_title)}`:''}</small>${x.notes?`<p>${esc(x.notes)}</p>`:''}</div><div class="calendar-event-actions"><span>${esc(x.status||'Scheduled')}</span><button type="button" class="button-quiet" data-calendar-edit="${x.id}">Edit</button></div></article>`;
}
function drawerCalendar(){
  const events=state.events||[], summary=state.calendar_summary||{};
  const edit=calendarEditingId?eventById(calendarEditingId):null;
  const projectOptions=(state.projects||[]).map(p=>`<option value="${p.id}"${edit&&Number(edit.project_id)===Number(p.id)?' selected':''}>${esc(p.title)}</option>`).join('');
  const typeOptions=['Personal','Institute','Class / Program','Farm','Deadline','Meeting','Other'].map(x=>`<option${(edit?.event_type||'Institute')===x?' selected':''}>${x}</option>`).join('');
  const levelOptions=['Light','Normal','Major'].map(x=>`<option${(edit?.commitment_level||'Normal')===x?' selected':''}>${x}</option>`).join('');
  const statusOptions=['Scheduled','Cancelled'].map(x=>`<option${(edit?.status||'Scheduled')===x?' selected':''}>${x}</option>`).join('');
  const form=`<section class="drawer-section calendar-editor"><div class="section-row"><div><span class="profile-kicker">Campus Calendar</span><h4>${edit?'Edit event':'Add event'}</h4></div><span>internal · local</span></div><p>This Calendar is stored inside Mavis Digital Campus. It gives Stella real commitments to plan around; it does not sync with Google yet.</p><form class="memory-form" data-calendar-event-form data-event-id="${edit?.id||''}"><label>Title<input name="title" maxlength="220" required value="${esc(edit?.title||'')}" placeholder="Library class, board meeting, farm workday…"></label><div class="memory-form-grid"><label>Date<input type="date" name="event_date" required value="${esc(edit?.event_date||summary.today_date||'')}"></label><label>Type<select name="event_type">${typeOptions}</select></label><label>Starts<input type="time" name="start_time" value="${esc(edit?.start_time||'')}"></label><label>Ends<input type="time" name="end_time" value="${esc(edit?.end_time||'')}"></label><label>Commitment<select name="commitment_level">${levelOptions}</select></label><label>Project / Program<select name="project_id"><option value="">None</option>${projectOptions}</select></label><label>Location<input name="location" maxlength="300" value="${esc(edit?.location||'')}" placeholder="Craft Memorial Library"></label><label>Status<select name="status">${statusOptions}</select></label></div><label class="calendar-all-day"><input type="checkbox" name="all_day" value="1"${Number(edit?.all_day||0)?' checked':''}> All-day event</label><label>Notes<textarea name="notes" rows="3" maxlength="4000" placeholder="Preparation, travel, what matters…">${esc(edit?.notes||'')}</textarea></label><div class="memory-form-actions"><button class="button-primary" type="submit">${edit?'Save Event':'Add Event'}</button>${edit?'<button type="button" class="button-quiet" data-calendar-edit-cancel>Cancel Edit</button>':''}</div></form></section>`;
  const today=summary.today||[], tomorrow=summary.tomorrow||[], week=(summary.this_week||[]).filter(x=>x.event_date!==summary.today_date&&x.event_date!==summary.tomorrow_date);
  const future=events.filter(x=>x.status==='Scheduled'&&String(x.event_date||'')>String(summary.week_end_date||''));
  const cancelled=events.filter(x=>x.status==='Cancelled').slice(-10).reverse();
  const section=(title,rows,empty)=>`<section class="drawer-section"><div class="section-row"><h4>${title}</h4><span>${rows.length}</span></div>${rows.length?`<div class="calendar-event-list">${rows.map(calendarEventCard).join('')}</div>`:`<p>${empty}</p>`}</section>`;
  const overview=`<section class="drawer-section calendar-summary"><div class="calendar-summary-grid"><span><strong>${summary.today_count||0}</strong><small>Today</small></span><span><strong>${summary.tomorrow_count||0}</strong><small>Tomorrow</small></span><span><strong>${summary.week_count||0}</strong><small>7 days</small></span></div><p><strong>Stella planning:</strong> Major or multiple same-day commitments automatically reduce the number of extra focus items she recommends.</p><small>Google Calendar: ${esc(summary.external_connected?'Connected':summary.external_status||'Not connected')}</small></section>`;
  return `${overview}${form}${section('Today',today,'Nothing scheduled today.')}${section('Tomorrow',tomorrow,'Nothing scheduled tomorrow.')}${section('Later this week',week,'No additional events in the next seven days.')}${future.length?section('Later',future.slice(0,30),''):''}${cancelled.length?section('Cancelled / history',cancelled,''):''}`;
}

function drawerPeople(){
  const people=state.people||[], categories=state.activity_categories||[], sessions=state.work_sessions||[], summary=state.work_summary||{};
  const active=sessions.filter(x=>!x.ended_at), recent=sessions.filter(x=>x.ended_at).slice(0,20);
  const projectOptions=(state.projects||[]).map(p=>`<option value="${p.id}">${esc(p.title)}</option>`).join('');
  const personOptions=people.filter(p=>p.status==='Active').map(p=>`<option value="${p.id}">${esc(p.display_name)} · ${esc(p.person_type)}</option>`).join('');
  const categoryOptions=categories.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');
  const staff=`<section class="drawer-section"><div class="section-row"><h4>Campus Staff</h4><span>${state.agents.length}</span></div><div class="drawer-grid">${state.agents.map(a=>`<button type="button" class="drawer-card drawer-card-button staff-card staff-${esc(a.id)}" data-open-agent="${a.id}">
    <img class="staff-card-avatar portrait" src="${agentPortrait(a)}" alt="">
    <strong>${esc(a.name)}</strong><small>${esc(a.role)}</small><small>${esc(buildingById(a.building_id)?.name||'')} · ${esc(a.status)}</small>
  </button>`).join('')}</div></section>`;
  const poe=`<section class="drawer-section poe-operations-callout"><div><span class="profile-kicker">Poe · Operations & Volunteer Coordinator</span><h4>People & Work Ledger</h4><p>Record the facts once. Poe keeps volunteer, learning, and occasional paid hours organized so the same work can later support project, grant, and reporting views.</p><button type="button" class="button-quiet poe-report-button" data-open-panel="work_report">Open Work Hours Report</button></div><div class="work-summary-strip"><span><strong>${people.length}</strong> people</span><span><strong>${summary.active_count||0}</strong> clocked in</span><span><strong>${workMinutesLabel(summary.completed_minutes||0)}</strong> recorded</span></div></section>`;
  const addPerson=`<section class="drawer-section"><h4>Add a person</h4><form class="memory-form" data-person-form><div class="memory-form-grid"><label>Name<input name="display_name" maxlength="180" required placeholder="Volunteer or worker name"></label><label>Type<select name="person_type"><option>Volunteer</option><option>Staff</option><option>Board</option><option>Contractor</option><option>Collaborator</option><option>Other</option></select></label></div><label class="poe-primary-check"><input type="checkbox" name="is_primary_user" value="1"> This is me — use this record when I say “me / I / my” to Poe.</label><label>Operational notes<textarea name="notes" rows="2" maxlength="4000" placeholder="Optional skills, interests, orientation note, or useful context"></textarea></label><div class="memory-form-actions"><button class="button-primary" type="submit">Add Person</button></div></form></section>`;
  const peopleList=`<section class="drawer-section"><div class="section-row"><h4>People Ledger</h4><span>${people.length}</span></div>${people.length?`<div class="people-ledger-list">${people.map(p=>{const open=active.find(x=>Number(x.person_id)===Number(p.id));return `<div class="person-ledger-card"><span><strong>${esc(p.display_name)}${p.is_primary_user?'<b class="poe-me-badge">ME</b>':''}</strong><small>${esc(p.person_type)} · ${esc(p.status)}</small></span><span class="person-ledger-actions">${open?`<em class="work-live">CLOCKED IN · ${esc(open.activity_name||'Uncategorized')}</em>`:'<em>Ready</em>'}${!p.is_primary_user?`<button type="button" class="button-quiet" data-person-primary="${p.id}">This is me</button>`:''}</span></div>`}).join('')}</div>`:'<p>No volunteers or workers have been added yet.</p>'}</section>`;
  const clockIn=people.length?`<section class="drawer-section"><h4>Clock work in</h4><form class="memory-form" data-clock-in-form><div class="memory-form-grid"><label>Person<select name="person_id" required><option value="">Choose person…</option>${personOptions}</select></label><label>Participation<select name="participation_type"><option>Volunteer</option><option>Learning</option><option>Paid</option></select></label><label>Activity<select name="activity_category_id" required><option value="">Choose activity…</option>${categoryOptions}</select></label><label>Project / Program<select name="project_id"><option value="">No project</option>${projectOptions}</select></label></div><label>What are they doing?<textarea name="notes" rows="2" maxlength="4000" placeholder="Optional short work note"></textarea></label><div class="memory-form-actions"><button class="button-primary" type="submit">Poe · Clock In</button></div></form></section>`:'';
  const activeList=`<section class="drawer-section"><div class="section-row"><h4>Currently Clocked In</h4><span>${active.length}</span></div>${active.length?active.map(x=>`<div class="work-session-card active"><div><strong>${esc(x.person_name)}</strong><small>${esc(x.participation_type)} · ${esc(x.activity_name||'Uncategorized')}${x.project_title?` · ${esc(x.project_title)}`:''}</small><small>Started ${fmtTime(x.started_at,true)}</small>${x.notes?`<p>${esc(x.notes)}</p>`:''}</div><button type="button" data-work-clock-out="${x.id}">Clock Out</button></div>`).join(''):'<p>Nobody is clocked in right now.</p>'}</section>`;
  const recentList=`<section class="drawer-section"><div class="section-row"><h4>Recent Work</h4><span>${recent.length}</span></div>${recent.length?recent.map(x=>`<div class="work-session-card"><div><strong>${esc(x.person_name)} · ${workMinutesLabel(x.duration_minutes)}</strong><small>${esc(x.participation_type)} · ${esc(x.activity_name||'Uncategorized')}${x.project_title?` · ${esc(x.project_title)}`:''}</small><small>${x.entry_mode==='manual_duration'?`Remembered duration · ${esc(x.work_date||'date recorded')}`:`${fmtTime(x.started_at,true)} → ${fmtTime(x.ended_at,true)}`}</small>${x.notes?`<p>${esc(x.notes)}</p>`:''}</div><button type="button" class="button-quiet" data-work-edit="${x.id}">Correct</button></div>`).join(''):'<p>No completed work sessions yet.</p>'}</section>`;
  return `${poe}${poeConversationCard()}${activeList}${clockIn}${addPerson}${peopleList}${recentList}${staff}`;
}
function grantAmountLabel(g){
  const min=g.amount_min==null?null:Number(g.amount_min), max=g.amount_max==null?null:Number(g.amount_max);
  const money=n=>Number(n).toLocaleString(undefined,{style:'currency',currency:'USD',maximumFractionDigits:0});
  if(min!=null&&max!=null)return min===max?money(min):`${money(min)}–${money(max)}`;
  if(min!=null)return `${money(min)}+`;
  if(max!=null)return `Up to ${money(max)}`;
  return g.amount_notes||'Amount not recorded';
}
function grantDeadlineLabel(deadline){
  if(!deadline)return 'No deadline recorded';
  const d=new Date(`${deadline}T12:00:00`), now=new Date();
  const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  const days=Math.round((d-today)/86400000);
  const when=days===0?'today':days===1?'tomorrow':days>1?`in ${days} days`:`${Math.abs(days)} days ago`;
  return `${d.toLocaleDateString([], {year:'numeric',month:'short',day:'numeric'})} · ${when}`;
}
function grantScoreOptions(value){return [1,2,3,4,5].map(n=>`<option value="${n}"${Number(value)===n?' selected':''}>${n} / 5</option>`).join('');}
function vernadetteResultGrants(grants=[]){
  if(!grants.length)return '';
  return `<div class="vernadette-result-list">${grants.slice(0,8).map(g=>`<div class="vernadette-result-grant"><span><strong>${esc(g.title||'Grant')}</strong><small>${esc(g.funder||'')}${g.deadline?` · due ${esc(g.deadline)}`:''}</small></span><em>${esc(g.status||'')} · ${esc(g.recommendation||'')}</em></div>`).join('')}</div>`;
}
function grantDiscoveryResults(results=[]){
  if(!results.length)return '';
  return `<div class="grant-discovery-list">${results.slice(0,20).map(g=>`<article class="grant-discovery-card${g.already_in_desk?' already-imported':''}"><div class="grant-discovery-head"><div><span>${esc((g.source_status||'federal').toUpperCase())}${g.opportunity_number?` · ${esc(g.opportunity_number)}`:''}</span><strong>${esc(g.title||'Federal opportunity')}</strong><small>${esc(g.funder||'U.S. Federal Agency')}</small></div>${g.already_in_desk?`<em>In Desk · ${esc(g.desk_status||'')}</em>`:`<button type="button" class="button-primary" data-grant-import-source="${esc(g.source_key||'')}" ${grantImportingKey===String(g.source_key)?'disabled':''}>${grantImportingKey===String(g.source_key)?'Adding…':'Add to Desk'}</button>`}</div><div class="grant-discovery-meta"><span><b>${g.deadline?esc(grantDeadlineLabel(g.deadline)):'No close date listed'}</b><small>Federal deadline</small></span><span><b>${g.open_date?esc(g.open_date):'Not listed'}</b><small>Posted / open</small></span></div><div class="grant-discovery-actions"><a href="${esc(g.source_url||'#')}" target="_blank" rel="noopener">Open Grants.gov source ↗</a></div></article>`).join('')}</div>`;
}
function grantDiscoveryPanel(){
  const result=grantDiscoveryResult;
  const status=result?`<div class="grant-discovery-response"><strong>Federal discovery</strong><p>${esc(result.message||`${result.hit_count||0} Grants.gov result(s).`)}</p>${grantDiscoveryResults(result.results||[])}</div>`:'';
  return `<section class="drawer-section grant-discovery-panel"><div class="section-row"><div><span class="profile-kicker">Vernadette · Federal Discovery</span><h4>Search Grants.gov</h4></div><span>live web · no AI call</span></div><p>Search currently posted and forecasted U.S. federal opportunities. Results stay outside the Grant Desk until you choose <b>Add to Desk</b>. This is one funding source, not a complete search of foundations, state, local, or corporate grants.</p><form class="grant-discovery-form" data-grant-discovery-form><label>What kind of funding are we looking for?<input name="keyword" maxlength="180" required placeholder="rural community education"></label><div class="vernadette-command-examples"><span>Try:</span><button type="button" data-grant-discovery-example="agriculture education">Agriculture education</button><button type="button" data-grant-discovery-example="rural community development">Rural community</button><button type="button" data-grant-discovery-example="conservation water">Conservation & water</button><button type="button" data-grant-discovery-example="historic preservation">Historic preservation</button></div><div class="memory-form-actions"><button class="button-primary" type="submit" ${grantDiscoveryLoading?'disabled':''}>${grantDiscoveryLoading?'Searching Grants.gov…':'Search Federal Grants'}</button></div></form>${status}</section>`;
}
function vernadetteConversationCard(){
  const result=vernadetteCommandResult;
  const response=result?`<div class="vernadette-command-response ${esc(result.status||'ok')}"><strong>${result.status==='clarification'?'Vernadette needs one detail':'Vernadette'}</strong><p>${esc(result.message||'')}</p>${vernadetteResultGrants(result.grants||[])}${grantDiscoveryResults(result.discovery_results||[])}${result.open_grant_desk&&activeView.panel!=='grants'?'<button type="button" class="button-quiet" data-open-panel="grants">Open Grant Desk</button>':''}</div>`:'';
  return `<section class="drawer-section vernadette-command-card"><div class="section-row"><div><span class="profile-kicker">Talk to Vernadette</span><h4>Natural Grant Commands</h4></div><span>local + federal search · no AI call</span></div><p>Ask about the Grant Desk, add or update known opportunities, or ask Vernadette to search Grants.gov when you name a funding topic.</p><form class="vernadette-command-form" data-vernadette-command-form><label>What should Vernadette do?<textarea name="text" rows="3" maxlength="1400" placeholder="Vernadette, find grants for rural community education."></textarea></label><div class="vernadette-command-examples"><span>Try:</span><button type="button" data-vernadette-example="Vernadette, find grants for rural community education.">Find federal grants</button><button type="button" data-vernadette-example="Vernadette, what grants are due this month?">Due this month</button><button type="button" data-vernadette-example="Vernadette, what should we pursue?">What should we pursue?</button></div><div class="memory-form-actions"><button class="button-primary" type="submit" ${vernadetteCommandSubmitting?'disabled':''}>${vernadetteCommandSubmitting?'Vernadette is checking…':'Ask Vernadette'}</button></div></form>${response}</section>`;
}
function grantForm(g=null){
  const editing=Boolean(g), projects=state.projects||[];
  const statuses=['Discovered','Reviewing','Pursue','Preparing','Submitted','Awarded','Declined','Passed'];
  const recommendations=['Pursue','Review','Pass'];
  const val=(k,f='')=>g?.[k]??f;
  return `<section class="drawer-section grant-form-card"><div class="section-row"><div><span class="profile-kicker">Vernadette · Grants & Development Officer</span><h4>${editing?'Edit Grant Opportunity':'Add Grant Opportunity'}</h4></div><span>${editing?`#${g.id}`:'manual intake'}</span></div>
  <form class="memory-form" data-grant-form${editing?` data-grant-id="${g.id}"`:''}>
    <div class="memory-form-grid">
      <label>Funder<input name="funder" maxlength="220" required value="${esc(val('funder'))}" placeholder="Foundation, agency, company..."></label>
      <label>Grant / Opportunity<input name="title" maxlength="260" required value="${esc(val('title'))}" placeholder="Opportunity name"></label>
      <label>Deadline<input type="date" name="deadline" value="${esc(val('deadline'))}"></label>
      <label>Status<select name="status">${statuses.map(x=>`<option${String(val('status','Discovered'))===x?' selected':''}>${x}</option>`).join('')}</select></label>
      <label>Minimum amount<input type="number" name="amount_min" min="0" step="1" value="${val('amount_min')==null?'':esc(val('amount_min'))}" placeholder="Optional"></label>
      <label>Maximum amount<input type="number" name="amount_max" min="0" step="1" value="${val('amount_max')==null?'':esc(val('amount_max'))}" placeholder="Optional"></label>
      <label>Project / Program<select name="project_id"><option value="">Not linked yet</option>${projects.map(x=>`<option value="${x.id}"${Number(val('project_id'))===Number(x.id)?' selected':''}>${esc(x.title)}</option>`).join('')}</select></label>
      <label>Recommendation<select name="recommendation">${recommendations.map(x=>`<option${String(val('recommendation','Review'))===x?' selected':''}>${x}</option>`).join('')}</select></label>
    </div>
    <label>Amount / match notes<input name="amount_notes" maxlength="500" value="${esc(val('amount_notes'))}" placeholder="Example: $10k–$25k; 20% match required"></label>
    <label>Source / link<input type="url" name="source_url" maxlength="1200" value="${esc(val('source_url'))}" placeholder="https://..."></label>
    <div class="grant-score-grid">
      <label>Mission fit<select name="mission_fit">${grantScoreOptions(val('mission_fit',3))}</select><small>5 = excellent Mavis fit</small></label>
      <label>Workload<select name="workload">${grantScoreOptions(val('workload',3))}</select><small>5 = heavy application/reporting load</small></label>
      <label>Restrictions<select name="restrictions">${grantScoreOptions(val('restrictions',3))}</select><small>5 = highly restrictive funds</small></label>
      <label>Strategic value<select name="strategic_value">${grantScoreOptions(val('strategic_value',3))}</select><small>5 = strongly advances priorities</small></label>
    </div>
    <label>Vernadette assessment<textarea name="assessment_notes" rows="3" maxlength="5000" placeholder="Why is this worth pursuing, reviewing, or passing?">${esc(val('assessment_notes'))}</textarea></label>
    <label>Internal notes<textarea name="notes" rows="3" maxlength="5000" placeholder="Requirements, contacts, missing documents, match details...">${esc(val('notes'))}</textarea></label>
    <div class="memory-form-actions"><button class="button-primary" type="submit">${editing?'Save Grant Changes':'Add to Grant Desk'}</button>${editing?'<button type="button" class="button-quiet" data-grant-edit-cancel>Cancel</button>':''}</div>
  </form></section>`;
}
function drawerGrants(){
  const grants=state.grants||[], sum=state.grant_summary||{}, editing=grants.find(x=>Number(x.id)===Number(grantEditingId));
  const pipeline=`<section class="drawer-section vernadette-callout"><div><span class="profile-kicker">Vernadette · Grants & Development Officer</span><h4>Grant Desk</h4><p>Track opportunities first. Vernadette helps judge mission fit, workload, restrictions, and strategic value before Mavis commits time or makes promises.</p></div><div class="grant-summary-strip"><span><strong>${sum.active_pipeline||0}</strong><small>active pipeline</small></span><span><strong>${sum.upcoming_30_days||0}</strong><small>due in 30 days</small></span><span><strong>${sum.total||0}</strong><small>all records</small></span></div></section>`;
  const cards=grants.length?`<section class="drawer-section"><div class="section-row"><h4>Funding Pipeline</h4><span>${grants.length}</span></div><div class="grant-list">${grants.map(g=>`<article class="grant-card recommendation-${String(g.recommendation||'review').toLowerCase()}"><div class="grant-card-head"><div><span>${esc(g.status)} · ${esc(g.recommendation)}</span><strong>${esc(g.title)}</strong><small>${esc(g.funder)}${g.project_title?` · ${esc(g.project_title)}`:''}</small></div><button type="button" class="button-quiet" data-grant-edit="${g.id}">Edit</button></div><div class="grant-card-meta"><span><b>${esc(grantAmountLabel(g))}</b><small>Amount</small></span><span><b>${esc(grantDeadlineLabel(g.deadline))}</b><small>Deadline</small></span></div><div class="grant-score-row"><span>Mission <b>${g.mission_fit}/5</b></span><span>Workload <b>${g.workload}/5</b></span><span>Restrictions <b>${g.restrictions}/5</b></span><span>Strategic <b>${g.strategic_value}/5</b></span></div>${g.assessment_notes?`<p>${esc(g.assessment_notes)}</p>`:''}${g.amount_notes?`<small class="grant-note">${esc(g.amount_notes)}</small>`:''}${g.opportunity_number?`<small class="grant-note">Federal opportunity: ${esc(g.opportunity_number)}${g.source_status?` · ${esc(g.source_status)}`:''}</small>`:''}${g.source_url?`<a class="grant-source" href="${esc(g.source_url)}" target="_blank" rel="noopener">Open source ↗</a>`:''}</article>`).join('')}</div></section>`:'<section class="drawer-section"><p>No funding opportunities are in Vernadette’s desk yet. Add one manually when something looks worth evaluating.</p></section>';
  return `${pipeline}${grantDiscoveryPanel()}${vernadetteConversationCard()}${grantForm(editing||null)}${cards}`;
}

function drawerAgent(id){
  const a=agentById(id);if(!a)return '<p>Agent not found.</p>';
  const currentTask=taskById(a.task_id);const assigned=state.tasks.filter(t=>t.owner_agent_id===a.id).sort((x,y)=>y.id-x.id);
  const recent=state.activity.filter(x=>x.actor===a.name).slice(0,8);
  const meta=agentConceptMeta(a.id);
  const concept=meta?`<section class="concept-hero">
    <img src="${agentPortrait(a)}" alt="${esc(a.name)} concept portrait">
    <div class="concept-hero-copy"><strong>${esc(meta.title)}</strong><small>${esc(meta.copy)}</small>
    <button type="button" class="concept-action" data-concept="${a.id}">View full character sheet</button></div>
  </section>`:'';
  return `${backButton('people')}${concept}<div class="profile-card agent-${esc(a.id)}"><div class="profile-avatar concept-portrait" style="background-image:url('${agentPortrait(a)}')"></div><div><span class="profile-kicker">${esc(a.role)}</span><h4>${esc(a.name)}</h4><p>${esc(a.status)}</p></div></div><div class="management-grid"><div class="management-stat"><span>Home</span><strong>${esc(buildingById(a.home_building_id)?.name||'')}</strong></div><div class="management-stat"><span>Current location</span><strong>${esc(buildingById(a.building_id)?.name||'')}</strong></div></div>${a.id==='operations'?poeConversationCard():''}${a.id==='grants'?`${vernadetteConversationCard()}<section class="drawer-section vernadette-callout"><span class="profile-kicker">Grant Desk</span><h4>Funding Pipeline</h4><p>Vernadette can talk naturally about her Grant Desk and search live posted/forecasted federal opportunities through Grants.gov. Imported discoveries still require human review.</p><button type="button" class="button-quiet" data-open-panel="grants">Open Grant Desk</button></section>`:''}${currentTask?`<section class="drawer-section"><h4>Current task</h4><button class="drawer-task detail-button" data-open-task="${currentTask.id}"><span><strong>${esc(displayWorkflowText(currentTask.title))}</strong><small>${esc(currentTask.status)}</small></span><span>›</span></button></section>`:''}<section class="drawer-section"><h4>Assigned work</h4>${assigned.length?assigned.map(t=>`<button class="drawer-task detail-button" data-open-task="${t.id}"><span><strong>${esc(displayWorkflowText(t.title))}</strong><small>${esc(projectById(t.project_id)?.title||'')}</small></span><span class="drawer-status">${esc(t.status)}</span></button>`).join(''):'<p>No project work assigned yet.</p>'}</section><section class="drawer-section"><h4>Recent activity</h4>${recent.length?recent.map(x=>`<div class="mini-history"><span>${esc(displayWorkflowText(x.message))}</span><small>${fmtTime(x.created_at,true)}</small></div>`).join(''):'<p>No recent activity.</p>'}</section>`;
}
function drawerRepository(){
  const all=(state.project_files||[]).filter(f=>f.status!=='Previous');
  const kinds=['all','pdf','slides','document','spreadsheet','image','text','archive','other'];
  const q=repositoryQuery.trim().toLowerCase();
  const filtered=all.filter(file=>{
    const kindOk=repositoryKind==='all'||file.file_kind===repositoryKind;
    const hay=`${file.display_name||''} ${file.filename||''} ${file.project_title||''} ${file.created_by||''}`.toLowerCase();
    return kindOk&&(!q||hay.includes(q));
  });
  const projectCount=new Set(all.map(f=>Number(f.project_id))).size;
  return `<section class="drawer-section repository-intro">
    <div class="section-row"><h4>Project Repository</h4><span>${all.length} current file${all.length===1?'':'s'}</span></div>
    <p>This is the Campus filing cabinet for finished project files. Current project outputs are filed here as Markdown now; future PDFs, slide decks, Word files, spreadsheets, images, ZIPs, and other generated artifacts can register in the same repository.</p>
    <div class="repository-summary"><strong>${projectCount}</strong><span>project${projectCount===1?'':'s'} with files</span></div>
    <button type="button" class="repository-rescan-button" data-rescan-repository>Refresh Repository</button>
  </section>
  <section class="drawer-section repository-tools">
    <label>Find a file<input type="search" data-repository-search value="${esc(repositoryQuery)}" placeholder="Search file or project name..."></label>
    <label>File type<select data-repository-kind>${kinds.map(kind=>`<option value="${kind}"${repositoryKind===kind?' selected':''}>${kind==='all'?'All file types':repositoryFileKindLabel(kind)}</option>`).join('')}</select></label>
  </section>
  <section class="drawer-section">
    <div class="section-row"><h4>Files</h4><span>${filtered.length} shown</span></div>
    ${filtered.length?`<div class="repository-file-list">${filtered.map(file=>repositoryFileCard(file,{showProject:true})).join('')}</div>`:'<div class="output-empty"><strong>No matching files.</strong><span>Try another search or file type. If an agent just created a file on disk, use Refresh Repository.</span></div>'}
  </section>`;
}

function libraryForm(item=null){
  const types=['Class','Program','Series','Research','Policy','Reference','Archive','Other'];
  return `<form class="memory-form library-form" data-library-form${item?` data-library-id="${item.id}"`:''}>
    <label>Title<input name="title" maxlength="220" required value="${esc(item?.title||'')}" placeholder="Example: Tinctures 101"></label>
    <div class="memory-form-grid">
      <label>Type<select name="collection_type">${types.map(v=>`<option value="${v}"${(item?.collection_type||'Program')===v?' selected':''}>${v}</option>`).join('')}</select></label>
      <label>Subject<input name="subject" maxlength="220" value="${esc(item?.subject||'')}" placeholder="Herbalism, Permaculture, Technology..."></label>
      <label>Status<select name="status">${['Active','Archived'].map(v=>`<option value="${v}"${(item?.status||'Active')===v?' selected':''}>${v}</option>`).join('')}</select></label>
    </div>
    <label>Description<textarea name="description" rows="4" maxlength="2400" placeholder="What this class, program, policy, research collection, or archive contains...">${esc(item?.description||'')}</textarea></label>
    <div class="memory-form-actions"><button class="button-primary" type="submit">${item?'Save Catalog Record':'Add to Catalog'}</button>${item?'<button type="button" class="button-quiet" data-library-edit-cancel>Cancel</button>':''}</div>
  </form>`;
}
function libraryCard(item){
  const archived=item.status==='Archived';
  return `<article class="memory-card library-card ${archived?'archived':''}">
    <div class="memory-icon">▦</div>
    <div class="memory-copy">
      <span class="memory-meta">${esc(item.collection_type)} · ${esc(item.status)}${item.subject?` · ${esc(item.subject)}`:''}</span>
      <strong>${esc(item.title)}</strong>
      <p>${esc(item.description||'No description yet.')}</p>
      <small>${Number(item.material_count||0)} attached material${Number(item.material_count||0)===1?'':'s'} · Cataloged ${fmtTime(item.created_at,true)} · Updated ${fmtTime(item.updated_at,true)}</small>
    </div>
    <div class="memory-actions">
      <button type="button" data-library-edit="${item.id}">Edit</button>
      ${archived?`<button type="button" data-library-status="${item.id}" data-library-status-value="Active">Restore</button>`:`<button type="button" data-library-status="${item.id}" data-library-status-value="Archived">Archive</button>`}
    </div>
  </article>`;
}
function libraryCatalogingForm(item){
  const collections=(state.library_collections||[]).filter(x=>x.status==='Active');
  const materialTypes=['Lesson Plan','Instructor Notes','Worksheet','Slideshow','Handout','Supply List','Photo','Video','Audio','Document','Spreadsheet','Archive','Reference','Other'];
  const stem=String(item.original_filename||'').replace(/\.[^.]+$/,'').replace(/[_-]+/g,' ').trim();
  if(!collections.length)return `<div class="output-empty"><strong>Create an active Catalog record first.</strong><span>Then this file can be assigned to that class, program, series, research collection, or archive.</span></div>`;
  return `<form class="memory-form library-cataloging-form" data-library-catalog-form data-inbox-id="${item.id}">
    <div class="memory-form-grid">
      <label>Library collection<select name="collection_id" required>${collections.map(c=>`<option value="${c.id}">${esc(c.title)} · ${esc(c.collection_type)}</option>`).join('')}</select></label>
      <label>Material type<select name="material_type">${materialTypes.map(v=>`<option value="${v}"${v==='Document'?' selected':''}>${v}</option>`).join('')}</select></label>
    </div>
    <label>Material title<input name="title" maxlength="240" required value="${esc(stem||item.original_filename||'Untitled material')}"></label>
    <div class="memory-form-grid">
      <label>Edition / version<input name="edition_label" maxlength="160" placeholder="Example: Aug 2026"></label>
      <label>Edition date<input name="edition_date" type="date"></label>
    </div>
    <label>Catalog notes<textarea name="notes" rows="2" maxlength="2400" placeholder="Optional context about this file or class edition..."></textarea></label>
    <div class="memory-form-actions"><button class="button-primary" type="submit">Approve into Trusted Library</button></div>
  </form>`;
}
function libraryInboxCard(item){
  return `<article class="memory-card library-inbox-card">
    <div class="memory-icon">⇩</div>
    <div class="memory-copy">
      <span class="memory-meta">${esc(item.status||'Incoming')} · ${esc(item.mime_type||'file')}</span>
      <strong>${esc(item.original_filename)}</strong>
      <p>Quarantined incoming material. Review the original file, classify it, then use the Cataloging Desk below to approve it into the trusted Library.</p>
      <small>${fmtBytes(item.size_bytes)} · Received ${fmtTime(item.received_at,true)} · SHA-256 ${esc(String(item.sha256||'').slice(0,12))}…</small>
      <div class="memory-actions"><a class="button-quiet" href="/api/library/inbox/${item.id}/file" target="_blank" rel="noopener">Open File</a></div>
      ${libraryCatalogingForm(item)}
    </div>
  </article>`;
}
function libraryMaterialCard(item){
  return `<article class="memory-card library-material-card">
    <div class="memory-icon">▣</div>
    <div class="memory-copy">
      <span class="memory-meta">${esc(item.material_type||'Material')} · ${esc(item.collection_title||'Unassigned')}${item.edition_label?` · ${esc(item.edition_label)}`:''}</span>
      <strong>${esc(item.title)}</strong>
      <p>${esc(item.notes||item.original_filename||'Trusted Library material.')}</p>
      <small>${item.original_filename?`${esc(item.original_filename)} · `:''}${item.size_bytes?`${fmtBytes(item.size_bytes)} · `:''}Cataloged ${fmtTime(item.created_at,true)} · ${item.index_status==='indexed'?`Indexed ${Number(item.index_char_count||0).toLocaleString()} chars`:item.index_status==='needs_ocr'?'Needs OCR':`Index: ${esc(item.index_status||'pending')}`}</small>
    </div>
    <div class="memory-actions">${item.relative_path?`<a class="button-quiet" href="/api/library/materials/${item.id}/file" target="_blank" rel="noopener">Open File</a>`:''}</div>
  </article>`;
}

function librarianMaterialResult(item){
  return `<article class="memory-card library-material-card">
    <div class="memory-icon">⌕</div>
    <div class="memory-copy">
      <span class="memory-meta">${esc(item.material_type||'Material')} · ${esc(item.collection_title||'Library')} · score ${Number(item.librarian_score||0)}</span>
      <strong>${esc(item.title||'Untitled material')}</strong>
      <p>${esc(item.content_match_excerpt||item.notes||item.original_filename||'Trusted Library material.')}</p>
      <small>${item.edition_label?`${esc(item.edition_label)} · `:''}${item.edition_date?`${esc(item.edition_date)} · `:''}${item.content_indexed?'Matched trusted document text · ':''}Trusted Library only</small>
    </div>
    <div class="memory-actions">${item.relative_path?`<a class="button-quiet" href="/api/library/materials/${item.id}/file" target="_blank" rel="noopener">Open File</a>`:''}</div>
  </article>`;
}
function librarianCollectionResult(item){
  return `<article class="memory-card library-card">
    <div class="memory-icon">⌕</div>
    <div class="memory-copy">
      <span class="memory-meta">${esc(item.collection_type||'Collection')} · ${esc(item.subject||'General')} · score ${Number(item.librarian_score||0)}</span>
      <strong>${esc(item.title||'Untitled collection')}</strong>
      <p>${esc(item.description||'No description yet.')}</p>
      <small>${Number(item.material_count||0)} trusted material${Number(item.material_count||0)===1?'':'s'} · Active Library record</small>
    </div>
  </article>`;
}
function librarianPanel(){
  const r=librarianResult;
  return `<section class="drawer-section library-librarian">
    <div class="section-row"><h4>Librarian</h4><span>local only · no web</span></div>
    <p>The Librarian searches only <strong>human-approved trusted Library holdings</strong>. Incoming Materials are excluded. If Mavis does not already have enough, the Librarian recommends handing the question to Research instead of browsing.</p>
    <form class="memory-form" data-librarian-form>
      <label>Ask the Library<input name="query" maxlength="300" required value="${esc(librarianQuery)}" placeholder="What do we already have about tinctures?"></label>
      <div class="memory-form-actions"><button class="button-primary" type="submit">Ask Librarian</button></div>
    </form>
    ${r?`<div class="librarian-response">
      <div class="section-row"><strong>${esc(r.message||'')}</strong><span>confidence · ${esc(r.confidence||'none')}</span></div>
      ${r.external_research_recommended?'<p><strong>External Research recommended.</strong> The Librarian will not search the web.</p>':''}
      ${r.collections?.length?`<div class="section-row"><h4>Matching collections</h4><span>${r.collections.length}</span></div><div class="memory-list">${r.collections.map(librarianCollectionResult).join('')}</div>`:''}
      ${r.materials?.length?`<div class="section-row"><h4>Matching trusted materials</h4><span>${r.materials.length}</span></div><div class="memory-list">${r.materials.map(librarianMaterialResult).join('')}</div>`:''}
      ${!r.collections?.length&&!r.materials?.length?'<div class="output-empty"><strong>Nothing useful found in the trusted Library.</strong><span>Catalog more Mavis material or ask Rose to research it beyond the trusted Library.</span></div>':''}
      <small>Source boundary: trusted Library only · Incoming excluded · web access disabled · ${Number(r.additional_ai_calls||0)} AI calls</small>
    </div>`:''}
  </section>`;
}

function libraryUploadForm(){
  return `<form class="memory-form library-upload-form" data-library-upload-form>
    <label class="library-dropbox">Library Drop Box
      <input type="file" name="files" multiple required>
      <span>Select past classes, slides, worksheets, notes, PDFs, images, ZIPs, or other institutional files. Up to 100 files per batch; 100 MB per file.</span>
    </label>
    <div class="memory-form-actions"><button class="button-primary" type="submit">Add to Incoming Materials</button></div>
  </form>`;
}
function drawerLibrary(){
  const all=state.library_collections||[];
  const inbox=state.library_inbox||[];
  const materials=state.library_materials||[];
  const q=libraryQuery.trim().toLowerCase();
  const filtered=all.filter(item=>{
    const typeOk=libraryType==='all'||item.collection_type===libraryType;
    const statusOk=libraryStatus==='all'||item.status===libraryStatus;
    const hay=`${item.title||''} ${item.collection_type||''} ${item.subject||''} ${item.description||''}`.toLowerCase();
    return typeOk&&statusOk&&(!q||hay.includes(q));
  });
  const active=all.filter(x=>x.status==='Active').length;
  const archived=all.filter(x=>x.status==='Archived').length;
  const editing=libraryEditingId?all.find(x=>Number(x.id)===Number(libraryEditingId)):null;
  const types=['Class','Program','Series','Research','Policy','Reference','Archive','Other'];
  return `<section class="drawer-section memory-intro library-intro">
    <div class="section-row"><h4>Library of Mavis</h4><span>${inbox.length} incoming</span></div>
    <p><strong>Incoming files are quarantined</strong> until human approval. The local Librarian searches only human-approved trusted Library holdings, never Incoming Materials or the greater web. <strong>v0.8.6.7 adds Local Document Indexing:</strong> The Librarian can now search text extracted locally from approved PDFs, DOCX, PPTX, XLSX, and text files; Programs can use that trusted text when revising an existing class.</p>
    <div class="memory-summary"><span><strong>${all.length}</strong> catalog records</span><span><strong>${active}</strong> active</span><span><strong>${inbox.length}</strong> incoming</span><span><strong>${materials.length}</strong> trusted materials</span><span><strong>${Number(state.library_foundation?.indexed_materials||0)}</strong> text indexed</span></div>
  </section>
  ${librarianPanel()}
  <section class="drawer-section memory-create library-intake"><div class="section-row"><h4>Incoming Materials</h4><span>Drop Box</span></div>${libraryUploadForm()}
    ${inbox.length?`<div class="memory-list library-inbox-list">${inbox.map(libraryInboxCard).join('')}</div>`:'<div class="output-empty"><strong>The Cataloging Desk is clear.</strong><span>Upload past class material here; new files stay quarantined until you approve them.</span></div>'}
  </section>
  <section class="drawer-section memory-tools library-tools">
    <div class="section-row"><h4>Card Catalog</h4><span>trusted index</span></div>
    <label>Search catalog<input type="search" data-library-search value="${esc(libraryQuery)}" placeholder="Search title, subject, description..."></label>
    <label>Type<select data-library-type><option value="all"${libraryType==='all'?' selected':''}>All types</option>${types.map(v=>`<option value="${v}"${libraryType===v?' selected':''}>${v}</option>`).join('')}</select></label>
    <label>Status<select data-library-status-filter><option value="Active"${libraryStatus==='Active'?' selected':''}>Active</option><option value="Archived"${libraryStatus==='Archived'?' selected':''}>Archived</option><option value="all"${libraryStatus==='all'?' selected':''}>All</option></select></label>
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Catalog records</h4><span>${filtered.length} shown</span></div>${filtered.length?`<div class="memory-list">${filtered.map(libraryCard).join('')}</div>`:'<div class="output-empty"><strong>No matching Library records.</strong><span>Add the first class or program below, or change the search filters.</span></div>'}</section>
  <section class="drawer-section"><div class="section-row"><h4>Trusted Materials</h4><span>${materials.length} approved</span></div>${materials.length?`<div class="memory-list">${materials.map(libraryMaterialCard).join('')}</div>`:'<div class="output-empty"><strong>No trusted files cataloged yet.</strong><span>Approve an Incoming Material through the Cataloging Desk to create the first one.</span></div>'}</section>
  <section class="drawer-section memory-create"><h4>${editing?'Edit Catalog Record':'Add Catalog Record'}</h4>${libraryForm(editing)}</section>`;
}


let phenologyHistory=null;
function drawerEnvironment(){
  const env=state.environment||{};
  const windows=env.seasonal_windows||[];
  const phenology=env.phenology_observations||[];
  const watchlist=env.phenology_watchlist||[];
  const checks=env.phenology_checks||[];
  const active=env.active_seasonal_windows||[];
  const days=env.forecast_days||[];
  const current=env.current_conditions||null;
  const today=env.local_date||new Date().toISOString().slice(0,10);
  const currentSource=current?.source||'No live reading yet';
  const pwsStatus=env.pws_connection_status||'Not checked';
  const forecastStatus=env.forecast_connection_status||'Not checked';
  const temp=current?.temperature_f==null?'—':Number(current.temperature_f).toFixed(1);
  const humidity=current?.humidity_pct==null?'—':Math.round(Number(current.humidity_pct));
  const wind=current?.wind_mph==null?'—':Number(current.wind_mph).toFixed(1);
  const rain=current?.precip_total_in==null?'—':Number(current.precip_total_in).toFixed(2);
  return `<section class="drawer-section memory-intro">
    <div class="section-row"><h4>Weather & Seasons</h4><span>${esc(env.season||'Season not set')} · ${esc(env.pws_station_id||'KWFLATT11')}</span></div>
    <p><strong>KWFLATT11 is the primary observed-weather station.</strong> Weather Underground PWS readings use its official API when a key is configured. Open-Meteo supplies the seven-day forecast and safely provides current fallback conditions when the PWS API is unavailable. Weather networking is isolated from the Librarian and makes <strong>0 AI calls</strong>.</p>
    <div class="memory-summary"><span><strong>${esc(env.location_label||'Flat Top, West Virginia')}</strong> location</span><span><strong>${esc(env.season||'—')}</strong> season</span><span><strong>${esc(pwsStatus)}</strong> PWS</span><span><strong>${esc(forecastStatus)}</strong> forecast</span><span><strong>${days.length}</strong> forecast days</span><span><strong>0</strong> AI calls</span></div>
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Current Conditions</h4><span>${esc(currentSource)}</span></div>
    ${current?`<div class="memory-list"><article class="memory-card"><div class="memory-icon">☁</div><div class="memory-copy"><span class="memory-meta">${esc(current.observed_at||'time unavailable')} · ${esc(current.station_id||env.pws_station_id||'model')}</span><strong>${temp}°F · ${esc(current.summary||'Current conditions')}</strong><p>Humidity ${humidity}% · Wind ${wind} mph · Station precipitation ${rain} in</p><small>${current.source_kind==='personal_weather_station'?'Measured at your personal weather station':'Regional/model fallback — not a KWFLATT11 measurement'}</small></div></article></div>`:'<div class="output-empty"><strong>No live weather stored yet.</strong><span>Refresh Weather to populate current conditions and the seven-day forecast.</span></div>'}
    <div class="memory-form-actions"><button class="button-primary" type="button" data-weather-refresh>Refresh Weather</button></div>
    <p><small>Last refresh: ${esc(env.last_refresh_at||'never')} · ${esc(env.last_refresh_status||'Never')}${env.last_refresh_error?` · ${esc(env.last_refresh_error)}`:''}</small></p>
    ${env.pws_status_detail?`<p><small><strong>PWS status:</strong> ${esc(env.pws_status_detail)}</small></p>`:''}
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Moon Cycle</h4><span>local calculation · 0 network calls</span></div>
    <div class="memory-list"><article class="memory-card"><div class="memory-icon">${esc(env.moon?.icon||'🌙')}</div><div class="memory-copy"><span class="memory-meta">${env.moon?.illumination_pct==null?'—':`${Number(env.moon.illumination_pct).toFixed(1)}% illuminated`} · moon age ${env.moon?.age_days==null?'—':`${Number(env.moon.age_days).toFixed(1)} days`}</span><strong>${esc(env.moon?.phase||'Moon cycle unavailable')}</strong><p>Next full moon: ${esc(env.moon?.next_full_moon||'—')} · Next new moon: ${esc(env.moon?.next_new_moon||'—')}</p><small>Approximate planning display calculated locally from the mean lunar cycle; not an astronomical ephemeris.</small></div></article></div>
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Forecast</h4><span>${esc(env.forecast_source||'Open-Meteo')}</span></div>
    ${days.length?`<div class="memory-list">${days.map(d=>`<article class="memory-card"><div class="memory-icon">☁</div><div class="memory-copy"><span class="memory-meta">${esc(d.forecast_date)} · ${d.precip_chance==null?'—':`${esc(d.precip_chance)}% precip`}</span><strong>${d.high_f==null?'—':Number(d.high_f).toFixed(0)}° / ${d.low_f==null?'—':Number(d.low_f).toFixed(0)}°F · ${esc(d.summary||'')}</strong><p>${d.precip_total_in==null?'':`${Number(d.precip_total_in).toFixed(2)} in precip · `}${d.wind_gust_max_mph==null?'':`gusts to ${Number(d.wind_gust_max_mph).toFixed(0)} mph`}</p><small>${esc(d.source||'forecast')}</small></div></article>`).join('')}</div>`:'<div class="output-empty"><strong>No forecast stored.</strong><span>Refresh Weather or add a manual forecast day.</span></div>'}
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Station & Location</h4><span>durable settings</span></div><form class="memory-form" data-environment-settings-form>
    <label>Location<input name="location_label" value="${esc(env.location_label||'Flat Top, West Virginia')}" required></label>
    <div class="memory-form-grid"><label>Weather Underground PWS ID<input name="pws_station_id" value="${esc(env.pws_station_id||'KWFLATT11')}" required></label><label>Timezone<input name="timezone_name" value="${esc(env.timezone_name||'America/New_York')}" required></label></div>
    <div class="memory-form-grid"><label>Seasonal region<input name="seasonal_region" value="${esc(env.seasonal_region||'Southern Appalachia')}"></label><label>Live weather<select name="live_weather_enabled"><option value="1"${env.live_weather_enabled!==false?' selected':''}>Enabled</option><option value="0"${env.live_weather_enabled===false?' selected':''}>Disabled</option></select></label></div>
    <div class="memory-form-grid"><label>Latitude<input name="latitude" type="number" step="any" value="${env.latitude??37.59}"></label><label>Longitude<input name="longitude" type="number" step="any" value="${env.longitude??-81.11}"></label></div>
    <p><small>PWS API key: ${env.pws_api_key_configured?'configured':'not configured — add WEATHER_UNDERGROUND_API_KEY to .env to read KWFLATT11 directly'}</small></p>
    <div class="memory-form-actions"><button type="submit">Save Weather Settings</button></div></form></section>
  <section class="drawer-section"><div class="section-row"><h4>Manual Forecast Override</h4><span>optional</span></div>
    <form class="memory-form" data-weather-day-form><div class="memory-form-grid"><label>Date<input type="date" name="forecast_date" value="${esc(today)}" required></label><label>Summary<input name="summary" placeholder="Dry morning, showers late"></label></div><div class="memory-form-grid"><label>High °F<input type="number" step="0.1" name="high_f"></label><label>Low °F<input type="number" step="0.1" name="low_f"></label><label>Precip %<input type="number" min="0" max="100" name="precip_chance"></label></div><div class="memory-form-actions"><button type="submit">Save Manual Day</button></div></form>
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Active Seasonal Windows</h4><span>${active.length}</span></div>
    ${active.length?`<div class="memory-list">${active.map(w=>`<article class="memory-card"><div class="memory-icon">◐</div><div class="memory-copy"><span class="memory-meta">${esc(w.category)} · ${esc(w.start_md)} → ${esc(w.end_md)} · ${esc(w.priority)}</span><strong>${esc(w.name)}</strong><p>${esc(w.notes||'Active seasonal window.')}</p></div></article>`).join('')}</div>`:'<div class="output-empty"><strong>No active seasonal windows.</strong></div>'}
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Seasonal Windows</h4><span>customizable</span></div>
    <form class="memory-form" data-seasonal-window-form><div class="memory-form-grid"><label>Name<input name="name" required placeholder="Garlic planting window"></label><label>Category<input name="category" value="Farm Window"></label><label>Priority<select name="priority"><option>Normal</option><option>High</option><option>Low</option></select></label></div><div class="memory-form-grid"><label>Start MM-DD<input name="start_md" placeholder="10-01" required></label><label>End MM-DD<input name="end_md" placeholder="11-15" required></label></div><label>Notes<textarea name="notes" rows="2" placeholder="What changes during this window?"></textarea></label><div class="memory-form-actions"><button type="submit">Add Seasonal Window</button></div></form>
    <div class="memory-list">${windows.map(w=>`<article class="memory-card ${w.status==='Archived'?'archived':''}"><div class="memory-icon">◐</div><div class="memory-copy"><span class="memory-meta">${esc(w.category)} · ${esc(w.start_md)} → ${esc(w.end_md)}</span><strong>${esc(w.name)}</strong><p>${esc(w.notes||'')}</p><small>${esc(w.status)} · ${esc(w.priority)}</small></div><div class="memory-actions"><button type="button" data-seasonal-status="${w.id}" data-seasonal-status-value="${w.status==='Archived'?'Active':'Archived'}">${w.status==='Archived'?'Restore':'Archive'}</button></div></article>`).join('')}</div>
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Phenology</h4><span>Rose review</span></div><p>Record what was actually observed. Suggestions remain unconfirmed until a person reviews them.</p>
    <form class="memory-form" data-phenology-form><div class="memory-form-grid"><label>Subject / indicator<input name="subject" required placeholder="Apple tree or spring peepers"></label><label>Stage / event<select name="stage"><option>bud break</option><option>first leaf</option><option>first bloom</option><option>full bloom</option><option>fruit set</option><option>ripening</option><option>harvest</option><option>leaf color</option><option>leaf fall</option><option>first seen</option><option>first heard</option><option>emergence</option><option>nesting</option><option>migration / arrival</option><option>first frost</option><option>first hard freeze</option><option>first snow</option><option>soil workable</option><option>spring peepers</option><option>fireflies</option><option>peak fall color</option></select></label></div><div class="memory-form-grid"><label>Date<input type="date" name="observation_date" value="${esc(today)}" required></label><label>Location / area<input name="location_area" required placeholder="Fruit Forest"></label></div><label>Notes<textarea name="notes" rows="2" placeholder="What did you actually see or hear?"></textarea></label><div class="memory-form-actions"><button type="submit">Add Observation</button></div></form>
    ${phenology.length?`<div class="memory-list">${phenology.map(p=>`<article class="memory-card"><div class="memory-icon">◉</div><div class="memory-copy"><span class="memory-meta">${esc(p.observation_date)} · ${esc(p.location_area)} · ${esc(p.source)}</span><strong>${esc(p.subject)} — ${esc(p.stage)}</strong><p>${esc(p.notes||'')}</p><small>${esc(p.status)} · Rose review</small></div>${p.status==='suggested'?`<div class="memory-actions"><button type="button" data-phenology-review="${p.id}" data-phenology-status="confirmed">Confirm</button><button type="button" data-phenology-review="${p.id}" data-phenology-status="rejected">Reject</button></div>`:''}</article>`).join('')}</div>`:'<div class="output-empty"><strong>No phenology observations yet.</strong><span>Begin with a direct observation from the land.</span></div>'}
    <div class="section-row"><h4>History / Compare Years</h4><span>Rose archive</span></div><form class="memory-form" data-phenology-history-form><div class="memory-form-grid"><label>Subject<input name="subject" required></label><label>Stage<input name="stage" required></label><label>Location (optional)<input name="location_area"></label></div><button type="submit">Compare Records</button></form>${phenologyHistory?`<div class="memory-card"><strong>Rose found ${phenologyHistory.records.length} trusted record${phenologyHistory.records.length===1?'':'s'} for ${esc(phenologyHistory.subject)} — ${esc(phenologyHistory.stage)}.</strong>${phenologyHistory.records.length<2?'<p>More years are needed for comparison.</p>':`<p>${esc(phenologyHistory.statistics.years_recorded)} years recorded · Average ${esc(phenologyHistory.statistics.average_date)} · Earliest ${esc(phenologyHistory.statistics.earliest_date)} · Latest ${esc(phenologyHistory.statistics.latest_date)}</p>`}<p>${phenologyHistory.records.map(r=>`${esc(r.year)} — ${esc(r.observation_date)} — ${esc(r.location_area)}`).join('<br>')}</p></div>`:''}
    <div class="section-row"><h4>Rose’s Seasonal Checks</h4><button type="button" data-generate-phenology-checks>Refresh</button></div>${checks.length?checks.map(c=>`<article class="memory-card"><strong>${esc(c.subject)} — ${esc(c.stage)}</strong><p>${esc(c.location_area)} · ${esc(c.reason)}</p><div class="memory-actions"><button type="button" data-check-dismiss="${c.id}">Not Yet / Dismiss</button></div></article>`).join(''):'<p>No pending checks. Rose will only ask when you refresh the queue.</p>'}
    <div class="section-row"><h4>Watchlist</h4><span>${watchlist.filter(item=>item.status==='Active').length} active</span></div><p>Worth watching only—use Ask Rose to create one review question, never a fact.</p>${watchlist.map(w=>`<article class="memory-card"><div class="memory-copy"><span class="memory-meta">${esc(w.category)} · ${esc(w.location_area)} · ${esc(w.status)}</span><strong>${esc(w.subject)}</strong><p>${esc((w.stages||[]).join(' · '))}</p></div><div class="memory-actions">${w.status==='Active'?`<button type="button" data-watch-suggest="${w.id}">Ask Rose</button>`:''}<button type="button" data-watch-status="${w.id}" data-watch-status-value="${w.status==='Active'?'Inactive':'Active'}">${w.status==='Active'?'Pause':'Activate'}</button></div></article>`).join('')}
    <form class="memory-form" data-watchlist-form><div class="memory-form-grid"><label>Subject<input name="subject" required></label><label>Category<input name="category" value="Custom indicator" required></label></div><div class="memory-form-grid"><label>Location<input name="location_area" required></label><label>Stages (comma-separated)<input name="stages" required></label></div><button type="submit">Add Watchlist Item</button></form>
  </section>`;
}

function drawerMemory(){
  const all=state.institutional_memory||[];
  const q=memoryQuery.trim().toLowerCase();
  const filtered=all.filter(m=>{
    const statusOk=memoryStatus==='all'||m.status===memoryStatus;
    const typeOk=memoryType==='all'||m.memory_type===memoryType;
    const reviewOk=memoryReview==='all'||(memoryReview==='due'?Boolean(m.review_due):!m.review_due);
    const hay=`${m.title||''} ${m.body||''} ${m.tags||''} ${m.project_title||''} ${m.memory_type||''}`.toLowerCase();
    return statusOk&&typeOk&&reviewOk&&(!q||hay.includes(q));
  });
  const governance=state.memory_governance||{};
  const active=governance.active??all.filter(m=>m.status==='Active').length;
  const core=all.filter(m=>m.status==='Active'&&m.importance==='Core').length;
  const due=governance.due??all.filter(m=>m.status==='Active'&&m.review_due).length;
  return `<section class="drawer-section memory-intro">
    <div class="section-row"><h4>Institutional Memory</h4><span>${active} active</span></div>
    <p>This is the durable, human-curated knowledge layer for the Campus. Active memories can be supplied to AI roles as bounded context; archived memories stay readable but are not sent to agents.</p>
    <div class="memory-summary"><span><strong>${active}</strong> active</span><span><strong>${core}</strong> core</span><span class="${due?'memory-due-count':''}"><strong>${due}</strong> review due</span><span><strong>${all.length-active}</strong> archived</span></div>
  </section>
  <section class="drawer-section memory-tools">
    <label>Find memory<input type="search" data-memory-search value="${esc(memoryQuery)}" placeholder="Search title, text, tags, or project..."></label>
    <label>Type<select data-memory-type><option value="all">All types</option>${['Decision','Fact','Policy','Lesson','Preference','Context'].map(t=>`<option value="${t}"${memoryType===t?' selected':''}>${t}</option>`).join('')}</select></label>
    <label>Status<select data-memory-status-filter><option value="Active"${memoryStatus==='Active'?' selected':''}>Active</option><option value="Archived"${memoryStatus==='Archived'?' selected':''}>Archived</option><option value="all"${memoryStatus==='all'?' selected':''}>All</option></select></label>
    <label>Review<select data-memory-review-filter><option value="all"${memoryReview==='all'?' selected':''}>All</option><option value="due"${memoryReview==='due'?' selected':''}>Due</option><option value="fresh"${memoryReview==='fresh'?' selected':''}>Fresh</option></select></label>
  </section>
  <section class="drawer-section"><div class="section-row"><h4>Memory cards</h4><span>${filtered.length} shown</span></div>${filtered.length?`<div class="memory-list">${filtered.map(m=>memoryCard(m)).join('')}</div>`:'<div class="output-empty"><strong>No matching memory.</strong><span>Create the first durable memory below or change the filters.</span></div>'}</section>
  <section class="drawer-section memory-create"><h4>${memorySupersedeId?'Supersede memory':memoryEditingId?'Edit memory':'Add memory'}</h4>${memoryForm({memory:(memorySupersedeId||memoryEditingId)?all.find(m=>Number(m.id)===Number(memorySupersedeId||memoryEditingId)):null,mode:memorySupersedeId?'supersede':'edit'})}</section>`;
}

function playbookSteps(pb){try{return JSON.parse(pb?.steps_json||'[]')}catch{return[]}}
function playbookForm(pb=null){
  const projects=(state.projects||[]);
  const owner=pb?.owner_agent_id||'';
  const steps=pb?playbookSteps(pb).join('\n'):'';
  return `<form class="memory-form playbook-form" data-playbook-form${pb?` data-playbook-id="${pb.id}"`:''}>
    <label>Scope<select name="project_id"><option value="">Institution-wide</option>${projects.map(p=>`<option value="${p.id}"${Number(pb?.project_id)===Number(p.id)?' selected':''}>Project · ${esc(p.title)}</option>`).join('')}</select></label>
    <label>Owner<select name="owner_agent_id"><option value=""${!owner?' selected':''}>Institution / any role</option>${['chief','research','programs','caretaker'].map(id=>`<option value="${id}"${owner===id?' selected':''}>${esc(agentById(id)?.name||titleCase(id))}</option>`).join('')}</select></label>
    <label>Title<input name="title" maxlength="180" required value="${esc(pb?.title||'')}"></label>
    <label>Purpose<textarea name="purpose" rows="3" required>${esc(pb?.purpose||'')}</textarea></label>
    <label>When to use<textarea name="trigger_text" rows="2" placeholder="Trigger, situation, or decision point...">${esc(pb?.trigger_text||'')}</textarea></label>
    <label>Steps <small>one step per line</small><textarea name="steps" rows="7" required placeholder="Confirm scope\nGather source material\nDraft the work\nRun human review">${esc(steps)}</textarea></label>
    <label>Tags<input name="tags" value="${esc(pb?.tags||'')}" placeholder="education, approvals, publishing"></label>
    <label>Status<select name="status">${['Draft','Active','Archived'].map(v=>`<option value="${v}"${(pb?.status||'Draft')===v?' selected':''}>${v}</option>`).join('')}</select></label>
    <div class="memory-form-actions"><button class="button-primary" type="submit">${pb?'Save Playbook':'Create Playbook'}</button>${pb?'<button type="button" class="button-quiet" data-playbook-edit-cancel>Cancel</button>':''}</div>
  </form>`;
}
function playbookCard(pb){
  const steps=playbookSteps(pb);
  return `<article class="memory-card ${pb.status==='Archived'?'archived':''}">
    <div class="memory-card-head"><div><span class="memory-type">${esc(pb.status)}</span><span class="memory-scope">${esc(pb.project_title||'Institution-wide')}</span></div><strong>${esc(pb.title)}</strong></div>
    <p>${esc(pb.purpose)}</p>
    ${pb.trigger_text?`<div class="playbook-trigger"><strong>Use when</strong><span>${esc(pb.trigger_text)}</span></div>`:''}
    <ol class="playbook-steps">${steps.map(x=>`<li>${esc(x)}</li>`).join('')}</ol>
    <div class="memory-meta"><span>Owner · ${esc(pb.owner_name||pb.owner_agent_id||'Institution')}</span>${pb.tags?`<span>${esc(pb.tags)}</span>`:''}</div>
    <div class="memory-actions"><button type="button" data-playbook-edit="${pb.id}">Edit</button>${pb.status!=='Active'?`<button type="button" data-playbook-status="${pb.id}" data-playbook-status-value="Active">Activate</button>`:''}${pb.status!=='Archived'?`<button type="button" data-playbook-status="${pb.id}" data-playbook-status-value="Archived">Archive</button>`:''}${pb.status!=='Draft'?`<button type="button" data-playbook-status="${pb.id}" data-playbook-status-value="Draft">Draft</button>`:''}</div>
  </article>`;
}
function drawerPlaybooks(){
  const all=state.playbooks||[];
  const filtered=all.filter(pb=>playbookStatus==='all'||pb.status===playbookStatus);
  const active=all.filter(pb=>pb.status==='Active').length,draft=all.filter(pb=>pb.status==='Draft').length;
  const editing=playbookEditingId?all.find(pb=>Number(pb.id)===Number(playbookEditingId)):null;
  return `<section class="drawer-section memory-intro"><div class="section-row"><h4>Institutional Playbooks</h4><span>${active} active</span></div>
    <p>Playbooks are human-authored procedures for repeatable work. Active playbooks can guide Stella during planning, revision, and final review; they never authorize outside action.</p>
    <div class="memory-summary"><span><strong>${active}</strong> active</span><span><strong>${draft}</strong> draft</span><span><strong>${all.filter(x=>x.status==='Archived').length}</strong> archived</span></div></section>
    <section class="drawer-section memory-tools"><label>Status<select data-playbook-status-filter><option value="all"${playbookStatus==='all'?' selected':''}>All</option>${['Active','Draft','Archived'].map(v=>`<option value="${v}"${playbookStatus===v?' selected':''}>${v}</option>`).join('')}</select></label></section>
    <section class="drawer-section"><div class="section-row"><h4>Procedures</h4><span>${filtered.length} shown</span></div>${filtered.length?`<div class="memory-list">${filtered.map(playbookCard).join('')}</div>`:'<div class="output-empty"><strong>No playbooks yet.</strong><span>Start with one procedure you repeat often rather than documenting everything at once.</span></div>'}</section>
    <section class="drawer-section memory-create"><h4>${editing?'Edit Playbook':'Create Playbook'}</h4>${playbookForm(editing)}</section>`;
}

function drawerProjects(){
  if(!state.projects.length)return '<p>No projects yet. Ask the Campus for help, and create a project only when the work truly needs one.</p>';
  return `<div class="drawer-stack">${state.projects.map(p=>{const tasks=projectTasks(p.id);const done=tasks.filter(t=>t.status==='Completed').length;return `<button type="button" class="project-card-button" data-open-project="${p.id}"><div><strong>${esc(p.title)}</strong><small>${esc(p.status)} · ${done}/${tasks.length} tasks complete</small></div><span>›</span></button>`;}).join('')}</div>`;
}
function drawerProject(id){
  const p=projectById(id);if(!p)return '<p>Project not found.</p>';
  const tasks=projectTasks(p.id), notes=notesForProject(p.id), approvals=state.approvals.filter(a=>Number(a.project_id)===Number(p.id));
  const projectMemories=memoriesForProject(p.id).filter(m=>m.status==='Active');
  const plan=(state.chief_plans||[]).find(x=>Number(x.project_id)===Number(p.id));
  const run=(state.workflow_runs||[]).find(x=>Number(x.project_id)===Number(p.id));
  const allOutputs=deliverablesForProject(p.id);
  const projectFiles=repositoryFilesForProject(p.id);
  const currentFiles=projectFiles.filter(f=>f.status!=='Previous');
  const previousFiles=projectFiles.filter(f=>f.status==='Previous');
  const outputs=allOutputs.filter(d=>d.status!=='Superseded');
  const previousOutputs=allOutputs.filter(d=>d.status==='Superseded').sort((a,b)=>Number(b.version)-Number(a.version));
  const revisionRequests=(state.revision_requests||[]).filter(x=>Number(x.project_id)===Number(p.id)).sort((a,b)=>Number(b.id)-Number(a.id));
  const revisionPlans=(state.revision_plans||[]).filter(x=>Number(x.project_id)===Number(p.id)).sort((a,b)=>Number(b.revision_number)-Number(a.revision_number));
  const revisionRequest=revisionRequests[0]||null;
  const revisionPlan=revisionPlans[0]||null;
  const expected=expectedDeliverables(plan);
  const producedTypes=new Set(outputs.map(d=>d.deliverable_type));
  const missingExpected=expected.filter(item=>!producedTypes.has(item.type));
  const parseList=value=>{try{return JSON.parse(value||'[]')}catch{return[]}};
  const criteria=plan?parseList(plan.success_criteria_json):[], questions=plan?parseList(plan.questions_json):[], risks=plan?parseList(plan.risk_notes_json):[];

  let tab=projectTabById.get(Number(p.id));
  if(!tab){
    tab=(outputs.length&&['Awaiting Execution Review','Completed','Needs Revision','Awaiting Revision Approval'].includes(p.status))?'outputs':'overview';
  }

  const tabs=[
    ['overview','Overview'],
    ['outputs',`Outputs${outputs.length?` · ${outputs.length}`:''}`],
    ['files',`Files${currentFiles.length?` · ${currentFiles.length}`:''}`],
    ['tasks',`Tasks · ${tasks.length}`],
    ['notes',`Notes · ${notes.length}`],
    ['memory',`Memory · ${projectMemories.length}`],
    ['history','History']
  ];
  const tabBar=`<nav class="project-tabs" aria-label="Project sections">${tabs.map(([key,label])=>`<button type="button" data-project-tab="${key}" data-project-id="${p.id}" class="${tab===key?'active':''}">${esc(label)}</button>`).join('')}</nav>`;

  const revisionTaskItems=revisionPlan?parseList(revisionPlan.task_revisions_json):[];
  const revisionOutputItems=revisionPlan?parseList(revisionPlan.deliverable_revisions_json):[];
  const revisionPreserved=revisionPlan?parseList(revisionPlan.preserve_keys_json):[];

  const revisionPlanHtml=revisionPlan?`<section class="drawer-section revision-plan-card">
    <div class="section-row"><h4>Revision ${esc(revisionPlan.revision_number)} plan</h4><span>${esc(revisionPlan.status)}</span></div>
    <p>${esc(revisionPlan.summary)}</p>
    ${revisionTaskItems.length?`<h5>Reopen only</h5>${revisionTaskItems.map(item=>{
      const task=taskById(item.task_id);
      return `<div class="revision-plan-item"><strong>${esc(task?.title||`Task #${item.task_id}`)}</strong><small>${esc(item.reason||'')}</small><em>${esc(item.revision_brief||'')}</em></div>`;
    }).join('')}`:''}
    ${revisionOutputItems.length?`<h5>New output versions</h5>${revisionOutputItems.map(item=>{
      const out=allOutputs.find(d=>d.deliverable_key===item.deliverable_key&&d.status!=='Superseded')||allOutputs.find(d=>d.deliverable_key===item.deliverable_key);
      return `<div class="revision-plan-item"><strong>${esc(out?.title||item.deliverable_key)}</strong><small>${esc(item.reason||'')}</small></div>`;
    }).join('')}`:''}
    <small>${revisionPreserved.length} current output key${revisionPreserved.length===1?'':'s'} preserved unchanged.</small>
  </section>`:'';

  let executionNote='';
  if(p.status==='Active'){
    const isRevision=revisionPlan?.status==='Executing'||run?.state==='Revision Running'||run?.state==='Revision Queued';
    executionNote=isRevision
      ? `<div class="execution-state revision-running"><strong>Selective revision is executing</strong><span>Only the approved tasks are reopening. Preserved output versions remain untouched.</span></div>`
      : `<div class="execution-state running"><strong>Approved plan is executing</strong><span>v0.8.4 is building durable project outputs as specialist artifacts complete.</span></div>`;
  }else if(p.status==='Execution Interrupted'){
    const blocked=tasks.filter(t=>t.status==='Blocked');
    const completed=tasks.filter(t=>t.status==='Completed').length;
    executionNote=`<div class="execution-state interrupted">
      <strong>Workflow interrupted — recovery available</strong>
      <span>${esc(run?.last_error||'The previous workflow stopped before every selected task was completed.')}</span>
      <small>${completed}/${tasks.length} tasks currently completed${run?.retry_count?` · ${run.retry_count} prior retry attempt${Number(run.retry_count)===1?'':'s'}`:''}.</small>
      ${blocked.length?`<small>Blocked at: ${esc(blocked[0].title)}</small>`:''}
      <button type="button" class="recovery-button" data-retry-project="${p.id}">Retry / Resume Workflow</button>
      <small class="helper-text">Completed tasks and all saved output versions remain preserved.</small>
    </div>`;
  }else if(p.status==='Awaiting Execution Review'){
    executionNote='<div class="execution-state review"><strong>Finished package — your review required</strong><span>Stella reviewed the current project outputs and returned the package to you.</span></div>';
  }else if(p.status==='Awaiting Revision Approval'){
    executionNote=`<div class="execution-state revision-approval"><strong>Selective revision plan waiting for you</strong><span>Stella has chosen which tasks should reopen and which outputs should receive a new version. Review the pending approval before any revision work starts.</span></div>`;
  }else if(p.status==='Completed'){
    executionNote='<div class="execution-state complete"><strong>Project package approved</strong><span>The current internal output versions were accepted by the human executive.</span></div>';
  }else if(p.status==='Needs Revision'){
    const canPlan=revisionRequest&&['Requested','Planning Failed','Changes Requested'].includes(revisionRequest.status);
    executionNote=`<div class="execution-state revision">
      <strong>Revision requested</strong>
      <span>${esc(revisionRequest?.request_text||'The package is waiting for additional executive direction.')}</span>
      ${canPlan?`<button type="button" class="revision-plan-button" data-plan-revision="${p.id}">${revisionRequest.status==='Planning Failed'?'Retry Stella Revision Plan':'Ask Stella to Plan Revision'}</button>`:''}
      <small class="helper-text">Stella will make one planning call, select the smallest useful set of existing work, and return that revision plan for your approval before anything reruns.</small>
    </div>`;
  }

  const expectedSummary=expected.length
    ? `<section class="drawer-section expected-output-summary"><div class="section-row"><h4>Expected outputs</h4><span>${expected.length-missingExpected.length}/${expected.length} covered</span></div><div class="expected-output-chips">${expected.map(item=>`<span class="${producedTypes.has(item.type)?'covered':'missing'}">${producedTypes.has(item.type)?'✓':'○'} ${esc(item.title)}</span>`).join('')}</div></section>`
    : '';

  const planHtml=plan?`<section class="drawer-section chief-plan-section"><div class="section-row"><h4>Original Stella plan</h4><span>${esc(plan.provider||'AI')} · ${esc(plan.model)}</span></div><p>${esc(plan.summary)}</p>${criteria.length?`<h5>Success looks like</h5><ul>${criteria.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${questions.length?`<div class="chief-plan-questions"><strong>Questions for you</strong>${questions.map(x=>`<p>${esc(x)}</p>`).join('')}</div>`:''}${risks.length?`<h5>Watch items</h5><ul>${risks.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}</section>`:'';

  const runHtml=run?`<section class="drawer-section workflow-journal"><div class="section-row"><h4>Workflow journal</h4><span>${esc(run.state)}</span></div><p>${run.current_task_id?`Current/recovery task #${esc(run.current_task_id)}. `:''}${run.last_error?esc(run.last_error):'No unresolved workflow error.'}</p><small>Retries: ${esc(run.retry_count||0)} · updated ${fmtTime(run.updated_at,true)}</small></section>`:'';

  const outputCard=d=>{
    const verify=verificationItems(d);
    return `<button type="button" class="deliverable-card status-${deliverableStatusClass(d.status)}" data-open-deliverable="${d.id}">
      <div class="deliverable-card-main">
        <span class="deliverable-type">${esc(String(d.deliverable_type||'output').replaceAll('_',' '))}</span>
        <strong>${esc(d.title)}</strong>
        <small>${esc(d.purpose||'Project output')}</small>
        <div class="deliverable-card-meta">
          <span>${esc(d.status)}</span>
          <span>v${esc(d.version)}</span>
          <span>${esc(d.created_by)}</span>
          ${verify.length?`<span class="verify">${verify.length} verify</span>`:''}
        </div>
        ${d.chief_review_note?`<em>${esc(d.chief_review_note)}</em>`:''}
      </div>
      <span class="deliverable-open">Open ›</span>
    </button>`;
  };

  let content='';
  if(tab==='overview'){
    content=`${executionNote}${revisionPlanHtml}${expectedSummary}${planHtml}${runHtml}`;
  }else if(tab==='outputs'){
    content=`${executionNote}<section class="drawer-section outputs-intro">
      <div class="section-row"><h4>Current Project Outputs</h4><span>${outputs.length} current</span></div>
      <p>Current outputs are the versions Stella will evaluate. A revision creates a new version only for selected outputs.</p>
      ${expected.length?`<div class="output-coverage"><strong>${expected.length-missingExpected.length}/${expected.length}</strong><span>expected output types covered</span></div>`:''}
    </section>
    ${outputs.length?`<div class="deliverable-list">${outputs.map(outputCard).join('')}</div>`:`<div class="output-empty"><strong>No outputs yet.</strong><span>Expected outputs will appear here as the agents finish their work.</span></div>`}
    ${previousOutputs.length?`<section class="drawer-section output-version-history"><div class="section-row"><h4>Previous Versions</h4><span>${previousOutputs.length}</span></div><p>Superseded versions remain readable and are never overwritten.</p><div class="deliverable-list previous">${previousOutputs.map(outputCard).join('')}</div></section>`:''}
    ${missingExpected.length?`<section class="drawer-section missing-outputs"><h4>Still expected</h4>${missingExpected.map(item=>`<div class="expected-output-missing"><strong>${esc(item.title)}</strong><small>${esc(item.purpose||'Expected by the approved Stella plan.')}</small></div>`).join('')}</section>`:''}`;
  }else if(tab==='files'){
    content=`<section class="drawer-section repository-intro project-files-intro">
      <div class="section-row"><h4>Project Files</h4><span>${currentFiles.length} current</span></div>
      <p>These are the actual files filed for this project. Outputs explain the work; Files are the paperwork and artifacts you can open or download.</p>
      <button type="button" class="repository-rescan-button" data-rescan-repository>Refresh Files</button>
    </section>
    ${currentFiles.length?`<div class="repository-file-list">${currentFiles.map(file=>repositoryFileCard(file)).join('')}</div>`:`<div class="output-empty"><strong>No project files yet.</strong><span>Current text outputs will be filed automatically. PDFs, slide decks, documents, spreadsheets, images, and other artifacts will appear here when the Campus creates or registers them.</span></div>`}
    ${previousFiles.length?`<section class="drawer-section output-version-history"><div class="section-row"><h4>Previous Files</h4><span>${previousFiles.length}</span></div><div class="repository-file-list previous">${previousFiles.map(file=>repositoryFileCard(file)).join('')}</div></section>`:''}`;
  }else if(tab==='tasks'){
    content=`${revisionPlanHtml}<section class="drawer-section"><h4>Approved tasks</h4>${tasks.length?tasks.map(t=>`<button class="drawer-task detail-button" data-open-task="${t.id}"><span><strong>${esc(t.title)}</strong><small>${esc(ownerName(t.owner_agent_id))}${t.brief?` · ${esc(t.brief)}`:''}</small></span><span class="drawer-status ${statusClass(t.status)}">${esc(t.status)}</span></button>`).join(''):'<p>No tasks.</p>'}</section>`;
  }else if(tab==='notes'){
    content=`<section class="drawer-section"><div class="section-row"><h4>Executive notes</h4><span>${notes.length}</span></div>${notes.length?notes.map(n=>`<div class="note-card"><strong>${esc(n.author)}</strong><p>${esc(n.body)}</p><div class="note-card-footer"><small>${fmtTime(n.created_at,true)}</small><button type="button" data-memory-capture-kind="note" data-memory-capture-id="${n.id}">Remember</button></div></div>`).join(''):'<p>No notes yet.</p>'}<form class="note-form" data-note-project="${p.id}"><label>Add project note<textarea name="body" rows="3" maxlength="1200" placeholder="Record a decision, reminder, concern, or next step..."></textarea></label><button type="submit">Save note</button></form></section>`;
  }else if(tab==='memory'){
    const projectOnly=projectMemories.filter(m=>Number(m.project_id)===Number(p.id));
    const institutionWide=projectMemories.filter(m=>m.project_id==null);
    content=`<section class="drawer-section memory-intro project-memory-intro"><div class="section-row"><h4>Memory available to this project</h4><span>${projectMemories.length} active</span></div><p>Project-scoped memory is preferred for this project. Institution-wide memory is also available to Stella, Rose, Percy, and Stella’s final review when they work on it.</p></section>
    ${projectOnly.length?`<section class="drawer-section"><div class="section-row"><h4>Project memory</h4><span>${projectOnly.length}</span></div><div class="memory-list">${projectOnly.map(m=>memoryCard(m,{showProject:false})).join('')}</div></section>`:'<div class="output-empty"><strong>No project-specific memory yet.</strong><span>Add durable context below when a decision or lesson should survive beyond ordinary notes.</span></div>'}
    ${institutionWide.length?`<section class="drawer-section"><div class="section-row"><h4>Institution-wide memory</h4><span>${institutionWide.length}</span></div><div class="memory-list compact">${institutionWide.map(m=>memoryCard(m,{showProject:false})).join('')}</div></section>`:''}
    <section class="drawer-section memory-create"><h4>Add project memory</h4>${memoryForm({projectId:p.id})}</section>`;
  }else if(tab==='history'){
    const revisionHistory=revisionPlans.length?`<section class="drawer-section"><h4>Revision history</h4>${revisionPlans.map(r=>`<div class="mini-history revision-history-item"><span><strong>Revision ${esc(r.revision_number)}</strong> — ${esc(r.status)}</span><small>${esc(r.summary)}</small><small>${fmtTime(r.updated_at,true)} · ${esc(r.provider)} / ${esc(r.model)}</small></div>`).join('')}</section>`:'';
    content=`${revisionHistory}<section class="drawer-section"><h4>Approval history</h4>${approvals.length?approvals.map(a=>`<div class="mini-history"><span><strong>${esc(a.status)}</strong> — ${esc(displayWorkflowText(a.title))}</span>${a.decision_note?`<small>Note: ${esc(a.decision_note)}</small>`:''}<small>${fmtTime(a.updated_at,true)}</small></div>`).join(''):'<p>No approvals yet.</p>'}</section>${runHtml}`;
  }

  return `${backButton('projects')}
    <div class="drawer-card project-detail-head">
      <span class="profile-kicker">Project #${p.id}</span>
      <strong>${esc(p.title)}</strong>
      <small>${esc(p.status)} · ${outputs.length} current output${outputs.length===1?'':'s'} · ${currentFiles.length} file${currentFiles.length===1?'':'s'}${previousOutputs.length?` · ${previousOutputs.length} previous output version${previousOutputs.length===1?'':'s'}`:''} · updated ${fmtTime(p.updated_at,true)}</small>
    </div>
    ${tabBar}
    <div class="project-tab-content">${content}</div>`;
}
function programsLibraryFirstCard(task){
  if(String(task?.owner_agent_id||'')!=='programs')return '';
  const pf=(state?.programs_library_preflights||[]).find(x=>Number(x.task_id)===Number(task.id));
  if(!pf)return '';
  const result=pf.result||{};
  const resultCollections=Array.isArray(result.collections)?result.collections:[];
  const resultMaterials=Array.isArray(result.materials)?result.materials:[];
  const ids=[];
  [...resultCollections.map(x=>x.id),...resultMaterials.map(x=>x.collection_id)].forEach(value=>{
    const id=Number(value||0);if(id&&!ids.includes(id))ids.push(id);
  });
  const options=ids.map(id=>(state.library_collections||[]).find(c=>Number(c.id)===id)||resultCollections.find(c=>Number(c.id)===id)).filter(Boolean);
  const selected=(state.library_collections||[]).find(c=>Number(c.id)===Number(pf.selected_collection_id));
  const decisionLabel={reuse:'Reuse Existing',revise:'Revise Existing',create_new:'Create New'}[pf.decision]||pf.decision||'';
  if(pf.status==='No Match'){
    return `<section class="drawer-section library-first-card resolved"><div class="section-row"><h4>Programs Library First</h4><span>✓ Checked</span></div><p>The Librarian found no useful trusted Mavis holding for <strong>${esc(pf.query||'this topic')}</strong>, so Programs was allowed to continue with new work.</p><small>Local trusted Library only · Incoming Materials excluded · 0 Librarian AI/web calls</small></section>`;
  }
  if(pf.status!=='Pending'){
    return `<section class="drawer-section library-first-card resolved"><div class="section-row"><h4>Programs Library First</h4><span>✓ ${esc(decisionLabel||'Decided')}</span></div><p>${selected?`Selected Library collection: <strong>${esc(selected.title)}</strong>.`:'The human reviewed the trusted Library matches.'} ${pf.human_note?`Note: ${esc(pf.human_note)}`:''}</p><small>Library First decision is recorded before Programs generation.</small></section>`;
  }
  const cards=options.length?options.map(c=>{
    const matched=resultMaterials.filter(m=>Number(m.collection_id)===Number(c.id));
    const holdings=(state.library_materials||[]).filter(m=>Number(m.collection_id)===Number(c.id));
    const preview=(matched.length?matched:holdings).slice(0,5);
    return `<article class="library-first-option"><div><span class="library-card-type">${esc(c.collection_type||'Library')}</span><strong>${esc(c.title||'Untitled')}</strong><small>${esc(c.subject||'No subject')}${Number(c.material_count||holdings.length)?` · ${Number(c.material_count||holdings.length)} trusted material${Number(c.material_count||holdings.length)===1?'':'s'}`:''}</small>${c.description?`<p>${esc(c.description)}</p>`:''}${preview.length?`<div class="library-first-holdings">${preview.map(m=>`<span>▧ ${esc(m.title||m.original_filename||'Material')}</span>`).join('')}</div>`:''}</div><div class="library-first-actions"><button type="button" data-programs-library-choice="reuse" data-task-id="${task.id}" data-collection-id="${c.id}">Reuse this</button><button type="button" data-programs-library-choice="revise" data-task-id="${task.id}" data-collection-id="${c.id}">Revise from this</button></div></article>`;
  }).join(''):'<p>Trusted materials matched, but their parent collection could not be displayed. You can still choose Create New.</p>';
  return `<section class="drawer-section library-first-card pending"><div class="section-row"><h4>Programs Library First</h4><span>Decision needed</span></div><p><strong>The Librarian found existing Mavis Institute material before Programs generated anything.</strong> Choose whether to reuse an existing collection, create a new revision from one, or deliberately make something new.</p><div class="library-first-results">${cards}</div><label class="approval-note-label">Library First note (optional)<textarea rows="2" maxlength="1200" data-library-first-note="${task.id}" placeholder="What should Programs preserve, change, or avoid?"></textarea></label><div class="library-first-create"><button type="button" data-programs-library-choice="create_new" data-task-id="${task.id}">Create New Anyway</button></div><small>Reuse makes no Programs AI call and copies trusted Library files into the project Repository. Revise can now use trusted text extracted locally from approved Library files when that text is available. Scanned PDFs without embedded text remain marked Needs OCR.</small></section>`;
}

function drawerTask(id){
  const t=taskById(id);if(!t)return '<p>Task not found.</p>';
  const p=projectById(t.project_id), notes=notesForTask(t.id), owner=agentById(t.owner_agent_id);
  const researchArtifact=(state.research_artifacts||[]).find(x=>Number(x.task_id)===Number(t.id));
  const programsArtifact=(state.programs_artifacts||[]).find(x=>Number(x.task_id)===Number(t.id));
  const chiefReviewArtifact=(state.chief_review_artifacts||[]).find(x=>Number(x.task_id)===Number(t.id));
  let sourceBadge='';
  if(researchArtifact){
    sourceBadge=`<span class="result-source ai">AI-generated · Rose · Research · ${esc(researchArtifact.provider)} / ${esc(researchArtifact.model)}</span>`;
  }else if(programsArtifact){
    sourceBadge=`<span class="result-source ai programs">AI-generated · Percy · Programs · ${esc(programsArtifact.provider)} / ${esc(programsArtifact.model)}</span>`;
  }else if(chiefReviewArtifact){
    sourceBadge=`<span class="result-source ai chief-review">AI-generated · Stella · Final Review · ${esc(chiefReviewArtifact.provider)} / ${esc(chiefReviewArtifact.model)}</span>`;
  }else if(t.result){
    sourceBadge='<span class="result-source simulated">Simulated workflow result</span>';
  }
  const statuses=['Waiting','In Progress','Blocked','Completed'];
  return `${backButton('project',t.project_id)}<div class="drawer-card task-detail-head"><span class="profile-kicker">Task ${t.sequence}</span><strong>${esc(displayWorkflowText(t.title))}</strong><small>${esc(p?.title||'Project')}</small></div>${t.brief?`<section class="drawer-section"><h4>Stella’s brief</h4><p>${esc(t.brief)}</p></section>`:''}<div class="management-grid"><div class="management-stat"><span>Owner</span><strong>${esc(owner?.name||'Unassigned')}</strong></div><div class="management-stat"><span>Status</span><strong>${esc(t.status)}</strong></div></div>${programsLibraryFirstCard(t)}${t.result?`<section class="drawer-section"><div class="section-row"><h4>Result</h4>${sourceBadge}</div><div class="result-panel">${esc(t.result)}</div></section>`:''}${t.status==='Blocked'&&p?.status==='Execution Interrupted'?`<section class="drawer-section task-recovery"><h4>Recovery</h4><p>This task stopped the automated workflow. Retry the project to continue from unfinished work without repeating completed tasks.</p><button type="button" class="recovery-button" data-retry-project="${p.id}">Retry / Resume Workflow</button></section>`:''}<section class="drawer-section"><h4>Manual status</h4><div class="status-actions">${statuses.map(s=>`<button type="button" data-task-status="${t.id}" data-status-value="${esc(s)}" class="${s===t.status?'selected':''}">${esc(s)}</button>`).join('')}</div><small class="helper-text">Manual status changes are blocked while the automated campus workflow is actively running.</small></section><section class="drawer-section"><div class="section-row"><h4>Task notes</h4><span>${notes.length}</span></div>${notes.length?notes.map(n=>`<div class="note-card"><strong>${esc(n.author)}</strong><p>${esc(n.body)}</p><div class="note-card-footer"><small>${fmtTime(n.created_at,true)}</small><button type="button" data-memory-capture-kind="note" data-memory-capture-id="${n.id}">Remember</button></div></div>`).join(''):'<p>No task notes yet.</p>'}<form class="note-form" data-note-task="${t.id}"><label>Add task note<textarea name="body" rows="3" maxlength="1200" placeholder="Add context or instructions for this task..."></textarea></label><button type="submit">Save note</button></form></section>`;
}
function drawerDepartment(buildingId){
  const b=buildingById(buildingId);if(!b)return '<p>Location not found.</p>';
  const team=state.agents.filter(a=>a.home_building_id===buildingId), present=state.agents.filter(a=>a.building_id===buildingId), ids=new Set(team.map(a=>a.id));
  const tasks=state.tasks.filter(t=>ids.has(t.owner_agent_id)).sort((x,y)=>y.id-x.id);
  const buildingConcepts={
    barn:{img:'/static/assets/buildings/coopenheimer-barn/hero.jpg',title:'Education Through Experience',copy:'Programs & Education · weathered Victorian/Appalachian learning barn.',button:'View full barn concept'},
    manor:{img:'/static/assets/buildings/mavis-manor/hero.jpg',title:'Executive Home of the Campus',copy:'Executive leadership, welcome, stewardship, and home at the heart of Mavis Digital Campus.',button:'View full manor concept'},
    library:{img:'/static/assets/buildings/library-of-mavis/hero.jpg',title:'Research · Knowledge · Preservation',copy:'A warm Victorian research library blending solarpunk and steampunk details for study, archives, and community learning.',button:'View full library concept'}
  };
  const conceptMeta=buildingConcepts[buildingId];
  const concept=conceptMeta?`<section class="concept-hero">
    <img src="${conceptMeta.img}" alt="${esc(b.name)} concept art">
    <div class="concept-hero-copy"><strong>${esc(conceptMeta.title)}</strong><small>${esc(conceptMeta.copy)}</small>
    <button type="button" class="concept-action" data-concept="${buildingId}">${esc(conceptMeta.button)}</button></div>
  </section>`:'';
  return `${concept}<div class="drawer-card project-detail-head"><span class="profile-kicker">${b.kind==='zone'?'Campus Location':'Department'}</span><strong>${esc(b.name)}</strong><small>${esc(b.purpose)}</small></div><section class="drawer-section"><h4>Team</h4>${team.length?team.map(a=>`<button class="drawer-task detail-button" data-open-agent="${a.id}"><span><strong>${esc(a.name)}</strong><small>${esc(a.status)}</small></span><span>${a.building_id===buildingId?'Here':'Away'}</span></button>`).join(''):'<p>No permanent staff assigned yet.</p>'}</section><section class="drawer-section"><h4>On site now</h4><p>${present.length?present.map(a=>`${esc(a.name)} — ${esc(a.status)}`).join('<br>'):'No staff currently here.'}</p></section><section class="drawer-section"><h4>Department work</h4>${tasks.length?tasks.map(t=>`<button class="drawer-task detail-button" data-open-task="${t.id}"><span><strong>${esc(displayWorkflowText(t.title))}</strong><small>${esc(projectById(t.project_id)?.title||'')}</small></span><span class="drawer-status">${esc(t.status)}</span></button>`).join(''):'<p>No department tasks yet.</p>'}</section>`;
}
function approvalCard(a){
  const project=projectById(a.project_id), meta=approvalMeta(a);
  const pending=a.status==='Pending';
  const flags=[];
  if(Number(a.verification_count||0)>0)flags.push(`${a.verification_count} verification flag${Number(a.verification_count)===1?'':'s'}`);
  if(Number(a.gap_count||0)>0)flags.push(`${a.gap_count} gap${Number(a.gap_count)===1?'':'s'}`);

  let actions='';
  if(pending){
    const approveButton=`<button class="${meta.recommendation&&meta.recommendation!=='approve_internal'?'decision-override':''}" data-approval="${a.id}" data-decision="approve">${esc(meta.approveLabel)}</button>`;
    const changesButton=`<button class="${meta.recommendation==='revise'||meta.recommendation==='hold'?'decision-recommended':''}" data-approval="${a.id}" data-decision="changes">${esc(meta.changesLabel)}</button>`;
    const ordered=meta.recommendation==='revise'||meta.recommendation==='hold'
      ? `${changesButton}${approveButton}`
      : `${approveButton}${changesButton}`;

    actions=`
      <label class="approval-note-label">Decision note (optional)
        <textarea class="approval-note" data-approval-note="${a.id}" rows="3" maxlength="1200" placeholder="Why are you approving this, or what should change?"></textarea>
      </label>
      <p class="decision-helper">${esc(meta.helper)}</p>
      <div class="drawer-actions">${ordered}</div>`;
  }else{
    actions=`<strong>${esc(a.status)}</strong>${a.decision_note?`<div class="decision-note">${esc(a.decision_note)}</div>`:''}`;
  }

  return `<div class="drawer-approval recommendation-${meta.className}">
    <span class="profile-kicker">${esc(project?.title||'Project')}</span>
    <div class="recommendation-banner recommendation-${meta.className}">
      <strong>${esc(meta.kicker)}</strong>
      ${meta.recommendation?`<small>${esc(recommendationLabel(meta.recommendation))}</small>`:''}
    </div>
    <h3>${esc(displayWorkflowText(a.title))}</h3>
    <p>${esc(displayWorkflowText(a.chief_review_summary||a.summary))}</p>
    ${flags.length?`<div class="approval-mini-flags">${flags.map(x=>`<span>${esc(x)}</span>`).join('')}</div>`:''}
    ${actions}
  </div>`;
}

function drawerApprovals(){
  if(!state.approvals.length)return '<p>No approvals have been created yet.</p>';
  const pending=state.approvals.filter(a=>a.status==='Pending'), decided=state.approvals.filter(a=>a.status!=='Pending');
  return `${pending.length?`<section class="drawer-section"><h4>Waiting for you</h4>${pending.map(approvalCard).join('')}</section>`:'<p>No decisions are waiting for you.</p>'}${decided.length?`<section class="drawer-section"><h4>Decision history</h4>${decided.map(approvalCard).join('')}</section>`:''}`;
}
function snapshotBrief(snapshot){try{return JSON.parse(snapshot?.brief_json||'{}')}catch{return{}}}
function dailyFocusTarget(item){
  if(item.approval_id)return 'data-open-panel="approvals"';
  if(item.grant_id)return 'data-open-panel="grants"';
  if(item.task_id)return `data-open-task="${item.task_id}"`;
  if(item.project_id)return `data-open-project="${item.project_id}"`;
  if(item.work_session_id)return 'data-open-panel="people"';
  if(item.event_id)return 'data-open-panel="calendar"';
  return 'data-open-panel="briefing"';
}
function dailyFocusCards(daily){
  const focus=daily?.focus||[];
  if(!focus.length)return '<div class="all-clear"><strong>No daily focus yet.</strong><span>Stella has not found a recorded Campus priority.</span></div>';
  return `<div class="daily-focus-list">${focus.map((item,i)=>`<button class="daily-focus-card focus-${i+1}" ${dailyFocusTarget(item)}><span class="daily-focus-slot">${esc(item.slot||`Priority ${i+1}`)} · ${esc(item.agent||'Stella')}</span><strong>${esc(displayWorkflowText(item.title||''))}</strong><small>${esc(displayWorkflowText(item.why||''))}</small><em><b>First move:</b> ${esc(item.first_action||'')}</em></button>`).join('')}</div>`;
}
function drawerBriefing(){
  const b=state.executive_briefing||{};
  const daily=stellaDailyResult?.daily_steward||b.daily_steward||{};
  const priorities=b.priorities||[], projects=b.projects||[], due=b.memory_due||[], playbooks=b.active_playbooks||[], completed=b.recent_completed_tasks||[], outputs=b.recent_outputs||[];
  const targetFor=item=>item.approval_id?'data-open-panel="approvals"':item.grant_id?'data-open-panel="grants"':item.task_id?`data-open-task="${item.task_id}"`:item.project_id?`data-open-project="${item.project_id}"`:item.memory_id?'data-open-panel="memory"':'data-open-panel="ai_activity"';
  const watch=daily.watch||[];
  const staff=daily.staff_inputs||[];
  const response=stellaDailyResult?`<div class="stella-daily-response ${esc(stellaDailyResult.status||'ok')}"><strong>Stella</strong><p>${esc(stellaDailyResult.message||'')}</p></div>`:'';
  return `<section class="drawer-section daily-steward-hero"><div class="section-row"><div><span class="profile-kicker">Stella · Chief of Staff</span><h4>Daily Steward</h4></div><span>${esc(daily.local_date||'Today')} · ${esc(daily.season||'')}</span></div>
    <p>Stella coordinates the Campus lanes and the internal Calendar into a deliberately small daily plan. <strong>This remains deterministic and makes zero AI calls.</strong></p>
    <div class="daily-context-strip"><span><strong>Stewart</strong><small>${esc(daily.weather_summary||'No stored weather detail')}</small></span><button type="button" data-open-panel="calendar"><strong>Calendar</strong><small>${esc(daily.calendar?.status||'No events today')}</small></button><span><strong>Attention rule</strong><small>Maximum ${daily.focus_cap||3} focus item${Number(daily.focus_cap||3)===1?'':'s'} today</small></span></div>
    <form class="stella-daily-form" data-stella-daily-form><label>Ask Stella<textarea name="text" rows="2" maxlength="500" placeholder="Stella, what should I focus on today?">What should I focus on today?</textarea></label><div class="memory-form-actions"><button class="button-primary" type="submit" ${stellaDailySubmitting?'disabled':''}>${stellaDailySubmitting?'Stella is checking…':'Ask Stella'}</button><button type="button" class="button-quiet" data-save-briefing>Save Today’s Snapshot</button></div></form>${response}</section>
    <section class="drawer-section daily-focus-section"><div class="section-row"><h4>What to focus on today</h4><span>${(daily.focus||[]).length} / ${daily.focus_cap||3}</span></div>${dailyFocusCards(daily)}${daily.protect_attention?`<div class="protect-attention"><strong>Protect your attention</strong><span>${esc(daily.protect_attention)}</span></div>`:''}</section>
    ${(daily.calendar?.today||[]).length?`<section class="drawer-section"><div class="section-row"><h4>Today’s commitments</h4><span>${daily.calendar.today.length}</span></div><div class="calendar-event-list">${daily.calendar.today.map(calendarEventCard).join('')}</div><button type="button" class="button-quiet" data-open-panel="calendar">Open Calendar</button></section>`:''}
    ${watch.length?`<section class="drawer-section"><div class="section-row"><h4>Watch, don’t chase</h4><span>${watch.length}</span></div><div class="daily-watch-list">${watch.map(x=>`<div><strong>${esc(x.source||'Campus')} · ${esc(x.title||'Watch')}</strong><span>${esc(x.detail||'')}</span></div>`).join('')}</div></section>`:''}
    <section class="drawer-section"><div class="section-row"><h4>Staff lanes checked</h4><span>${staff.length}</span></div><div class="daily-staff-grid">${staff.map(x=>`<div><strong>${esc(x.agent||'')}</strong><small>${esc(x.lane||'')}</small><span>${esc(x.status||'')}</span></div>`).join('')}</div><small class="daily-limit-note">${esc((daily.limitations||[]).join(' · '))}</small></section>
    <section class="drawer-section"><div class="section-row"><h4>Campus priority queue</h4><span>${priorities.length}</span></div>${priorities.length?priorities.map(item=>`<button class="attention-card ${esc(item.priority||'medium')} kind-${esc(item.kind||'item')}" ${targetFor(item)}><span class="attention-kind">${esc(item.label||'Attention')}</span><strong>${esc(displayWorkflowText(item.title||''))}</strong><small>${esc(displayWorkflowText(item.summary||''))}</small></button>`).join(''):'<div class="all-clear"><strong>No priority items.</strong><span>Nothing currently needs intervention or scheduled memory review.</span></div>'}</section>
    <section class="drawer-section"><div class="section-row"><h4>Project Pulse</h4><span>${projects.length}</span></div>${projects.length?projects.map(p=>`<button class="drawer-task detail-button" data-open-project="${p.id}"><span><strong>${esc(p.title)}</strong><small>${esc(p.status)} · ${p.completed_tasks||0}/${p.task_count||0} tasks</small></span><span>${p.progress_percent||0}%</span></button>`).join(''):'<p>No tracked projects.</p>'}</section>
    ${due.length?`<section class="drawer-section"><div class="section-row"><h4>Institutional Memory Due</h4><span>${due.length}</span></div>${due.map(m=>`<button class="drawer-task detail-button" data-open-panel="memory"><span><strong>${esc(m.title)}</strong><small>${esc(m.importance)} · ${esc(m.memory_type)}${m.project_title?` · ${esc(m.project_title)}`:''}</small></span><span>Review</span></button>`).join('')}</section>`:''}
    <section class="drawer-section"><div class="section-row"><h4>Recent Movement</h4><span>${completed.length+outputs.length}</span></div>${completed.slice(0,5).map(t=>`<button class="drawer-task detail-button" data-open-task="${t.id}"><span><strong>Completed · ${esc(t.title)}</strong><small>${esc(t.project_title)}</small></span><span>${fmtTime(t.updated_at,true)}</span></button>`).join('')}${outputs.slice(0,4).map(o=>`<button class="drawer-task detail-button" data-open-project="${o.project_id}"><span><strong>Output · ${esc(o.title)}</strong><small>${esc(o.project_title)} · v${o.version}</small></span><span>›</span></button>`).join('')}${!completed.length&&!outputs.length?'<p>No completed tasks or outputs yet.</p>':''}</section>
    <section class="drawer-section"><div class="section-row"><h4>Saved Daily Briefings</h4><span>${(state.briefing_snapshots||[]).length}</span></div>${(state.briefing_snapshots||[]).length?(state.briefing_snapshots||[]).slice(0,6).map(s=>{const x=snapshotBrief(s);return `<div class="mini-history"><span><strong>${fmtTime(s.captured_at,true)}</strong> · ${(x.daily_steward?.focus||[]).length||0} focus item${Number((x.daily_steward?.focus||[]).length||0)===1?'':'s'}</span><small>${x.counts?.pending_approvals||0} approvals · ${x.counts?.memory_review_due||0} memory reviews · ${x.counts?.active_playbooks||0} active playbooks</small></div>`}).join(''):'<p>No saved Daily Steward snapshots yet.</p>'}</section>`;
}

function drawerExecutive(){
  const e=state.executive||{}, attention=e.attention||[];
  const metric=(value,label,cls='')=>`<div class="${cls}"><strong>${value||0}</strong><span>${label}</span></div>`;

  return `<div class="executive-metrics executive-decision-metrics">
    ${metric(e.ready_to_approve,'Ready','decision-ready')}
    ${metric(e.revision_recommended,'Revise','decision-revise')}
    ${metric(e.hold_recommended,'Hold','decision-hold')}
    ${metric(e.plan_approvals,'Plans')}
    ${metric(e.revision_plan_approvals,'Revision Plans','decision-revision-plan')}
    ${metric(e.blocked_tasks,'Blocked')}
  </div>
  <section class="drawer-section">
    <h4>What needs your attention</h4>
    ${attention.length?attention.map(item=>{
      const label=item.label||titleCase(String(item.kind||'').replaceAll('_',' '));
      const target=item.approval_id
        ? 'data-open-panel="approvals"'
        : item.task_id
          ? `data-open-task="${item.task_id}"`
          : `data-open-project="${item.project_id}"`;
      const detail=[];
      if(Number(item.verification_count||0)>0)detail.push(`${item.verification_count} verification flag${Number(item.verification_count)===1?'':'s'}`);
      if(Number(item.gap_count||0)>0)detail.push(`${item.gap_count} gap${Number(item.gap_count)===1?'':'s'}`);
      return `<button class="attention-card ${esc(item.priority)} kind-${esc(item.kind)}" ${target}>
        <span class="attention-kind">${esc(label)}</span>
        <strong>${esc(item.title)}</strong>
        <small>${esc(item.summary||'')}</small>
        ${detail.length?`<em>${esc(detail.join(' · '))}</em>`:''}
      </button>`;
    }).join(''):'<div class="all-clear"><strong>Nothing is waiting on you.</strong><span>The campus can continue without an executive decision right now.</span></div>'}
  </section>
  <section class="drawer-section">
    <h4>Current staff</h4>
    ${state.agents.map(a=>`<button class="drawer-task detail-button" data-open-agent="${a.id}">
      <span><strong>${esc(a.name)}</strong><small>${esc(a.status)}</small></span>
      <span>${esc(buildingById(a.building_id)?.name||'')}</span>
    </button>`).join('')}
  </section>`;
}

function openDrawer(panel,id=null,parent=null){
  const sameView=activeView.panel===panel && String(activeView.id??'')===String(id??'') && String(activeView.parent??'')===String(parent??'');
  const priorScroll=sameView?els.drawerBody.scrollTop:0;
  activeView={panel,id,parent};

  els.navButtons.forEach(b=>b.classList.toggle(
    'active',
    b.dataset.panel===panel
      || (['agent'].includes(panel)&&b.dataset.panel==='people')
      || (panel==='grants'&&b.dataset.panel==='grants')
      || (['project','task'].includes(panel)&&b.dataset.panel==='projects')
  ));

  if(panel==='map'){
    els.drawer.hidden=true;
    els.viewport.classList.remove('drawer-open');
    return;
  }

  let kicker='Campus',title='Panel',html='';
  if(panel==='executive'){kicker='Executive';title='What Needs Me';html=drawerExecutive();}
  if(panel==='briefing'){kicker='Stella · Chief of Staff';title='Daily Steward';html=drawerBriefing();}
  if(panel==='calendar'){kicker='Planning';title='Campus Calendar';html=drawerCalendar();}
  if(panel==='people'){kicker='Staff';title='People';html=drawerPeople();}
  if(panel==='grants'){kicker='Development';title='Vernadette · Grant Desk';html=drawerGrants();}
  if(panel==='work_report'){kicker='Operations';title='Work Hours Report';html=drawerWorkReport();}
  if(panel==='agent'){const a=agentById(id);kicker='Staff';title=a?.name||'Agent';html=drawerAgent(id);}
  if(panel==='projects'){kicker='Work';title='Projects';html=drawerProjects();}
  if(panel==='repository'){kicker='Files';title='Project Repository';html=drawerRepository();}
  if(panel==='library'){kicker='Library of Mavis';title='Card Catalog';html=drawerLibrary();}
  if(panel==='environment'){kicker='Living Systems';title='Weather & Seasons';html=drawerEnvironment();}
  if(panel==='memory'){kicker='Library of Mavis';title='Institutional Memory';html=drawerMemory();}
  if(panel==='playbooks'){kicker='Library of Mavis';title='Institutional Playbooks';html=drawerPlaybooks();}
  if(panel==='project'){kicker='Project';title=projectById(id)?.title||'Project';html=drawerProject(id);}
  if(panel==='task'){kicker='Task';title=taskById(id)?.title||'Task';html=drawerTask(id);}
  if(panel==='programs'){kicker='Department';title='Programs';html=drawerDepartment('barn');}
  if(panel==='research'){kicker='Department';title='Research';html=drawerDepartment('library');}
  if(panel==='department'){const b=buildingById(id);kicker=b?.kind==='zone'?'Location':'Department';title=b?.name||'Location';html=drawerDepartment(id);}
  if(panel==='approvals'){kicker='Human Gate';title='Approvals & Decisions';html=drawerApprovals();}
  if(panel==='ai_activity'){kicker='AI Operations';title='AI Activity & Cost';html=drawerAiActivity();}

  els.drawerKicker.textContent=kicker;
  els.drawerTitle.textContent=title;
  els.drawerBody.innerHTML=html;
  els.drawer.hidden=false;
  els.viewport.classList.add('drawer-open');

  requestAnimationFrame(()=>{
    els.drawerBody.scrollTop=sameView?priorScroll:0;
    if(!sameView){
      try{els.drawerBody.focus({preventScroll:true});}catch{}
    }
  });
}
function refreshDrawer(){const editing=els.drawer.contains(document.activeElement)&&['TEXTAREA','INPUT','SELECT'].includes(document.activeElement?.tagName);if(activeView.panel!=='map'&&!els.drawer.hidden&&!editing)openDrawer(activeView.panel,activeView.id,activeView.parent);}

function renderAiControls(){
  const control=state.ai_control||{};
  const today=state.ai_usage?.today||{};
  const enabled=Boolean(control.enabled);
  const budgetBlocked=Boolean(control.budget_blocked);
  const effective=Boolean(control.effective_enabled);

  if(els.aiCallCount)els.aiCallCount.textContent=fmtNumber(today.calls||0);
  if(els.aiTokenCount){
    els.aiTokenCount.textContent=fmtNumber(
      Number(today.estimated_input_tokens||0)+Number(today.estimated_output_tokens||0)
    );
  }
  if(els.aiCostToday)els.aiCostToday.textContent=fmtMoney(today.estimated_openai_list_cost_usd||0,4);

  if(els.aiControlBadge){
    els.aiControlBadge.classList.remove('enabled','stopped','guardrail');
    if(!enabled){
      els.aiControlBadge.textContent='Stopped';
      els.aiControlBadge.classList.add('stopped');
    }else if(budgetBlocked){
      els.aiControlBadge.textContent='OpenAI guardrail';
      els.aiControlBadge.classList.add('guardrail');
    }else{
      els.aiControlBadge.textContent='Enabled';
      els.aiControlBadge.classList.add('enabled');
    }
  }

  if(els.aiStopBtn){
    els.aiStopBtn.textContent=enabled?'Emergency Stop AI':'Resume AI';
    els.aiStopBtn.classList.toggle('resume',!enabled);
    els.aiStopBtn.setAttribute('aria-pressed',String(!enabled));
  }

  if(els.aiBudgetInput && document.activeElement!==els.aiBudgetInput){
    els.aiBudgetInput.value=Number(control.daily_estimated_cost_limit_usd??1).toFixed(2);
  }


}

function drawerAiActivity(){
  const usage=state.ai_usage||{}, today=usage.today||{}, control=state.ai_control||{};
  const projects=usage.projects||[], calls=usage.calls||[];
  const status=!control.enabled
    ? 'Emergency Stop AI is active.'
    : control.budget_blocked
      ? 'The estimated-cost guardrail is blocking new OpenAI calls.'
      : 'AI calls are enabled.';

  const projectRows=projects.length
    ? projects.map(p=>`<button type="button" class="drawer-task detail-button ai-project-usage" data-open-project="${p.project_id}">
        <span>
          <strong>${esc(p.project_title)}</strong>
          <small>${fmtNumber(p.calls)} call${Number(p.calls)===1?'':'s'} · ~${fmtNumber(Number(p.estimated_input_tokens||0)+Number(p.estimated_output_tokens||0))} tokens</small>
        </span>
        <span>${fmtMoney(p.estimated_list_cost_usd||0,4)}</span>
      </button>`).join('')
    : '<p>No project-attributed AI activity yet.</p>';

  const callRows=calls.length
    ? calls.map(call=>{
        const tokenTotal=Number(call.estimated_input_tokens||0)+Number(call.estimated_output_tokens||0);
        const cost=call.estimated_list_cost_usd;
        const costText=cost===null||cost===undefined?'Not locally priced':fmtMoney(cost,5);
        const project=call.project_id?projectById(call.project_id):null;
        return `<div class="ai-call-card ${esc(String(call.status||'').toLowerCase())}">
          <div class="section-row">
            <strong>${esc(operationLabel(call.operation))}</strong>
            <span>${esc(call.status||'')}</span>
          </div>
          <small>${esc(call.provider)} · ${esc(call.model)}</small>
          ${project?`<small>Project: ${esc(project.title)}</small>`:''}
          <div class="ai-call-metrics">
            <span>~${fmtNumber(tokenTotal)} tokens</span>
            <span>${costText}</span>
            <span>${fmtNumber(call.latency_ms||0)} ms</span>
          </div>
          ${call.message?`<p>${esc(call.message)}</p>`:''}
          <small>${fmtTime(call.created_at,true)}</small>
        </div>`;
      }).join('')
    : '<p>No AI calls have been logged yet.</p>';

  return `<div class="ai-usage-hero">
      <div><span>Today · UTC</span><strong>${fmtNumber(today.calls||0)}</strong><small>AI calls</small></div>
      <div><span>Estimated tokens</span><strong>${fmtNumber(Number(today.estimated_input_tokens||0)+Number(today.estimated_output_tokens||0))}</strong><small>chars ÷ 4</small></div>
      <div><span>OpenAI list price</span><strong>${fmtMoney(today.estimated_openai_list_cost_usd||0,4)}</strong><small>estimate</small></div>
      <div><span>Daily guardrail</span><strong>${Number(control.daily_estimated_cost_limit_usd||0)===0?'Off':fmtMoney(control.daily_estimated_cost_limit_usd||0,2)}</strong><small>${esc(status)}</small></div>
    </div>

    <section class="drawer-section ai-cost-warning">
      <h4>What this estimate means</h4>
      <p>${esc(usage.method?.billing_warning||'This is an estimate, not an invoice.')}</p>
      <small>Token estimate: ${esc(usage.method?.token_estimate||'characters divided by 4')}. Pricing basis: ${esc(usage.method?.pricing_basis||'configured list price')}.</small>
    </section>

    <section class="drawer-section">
      <h4>Project AI usage</h4>
      ${projectRows}
    </section>

    <section class="drawer-section">
      <h4>Recent AI calls</h4>
      <div class="ai-call-list">${callRows}</div>
    </section>`;
}

function weatherKind(summary=''){
  const text=String(summary||'').toLowerCase();
  if(text.includes('thunder'))return 'storm';
  if(text.includes('snow')||text.includes('sleet'))return 'snow';
  if(text.includes('rain')||text.includes('shower')||text.includes('drizzle'))return 'rain';
  if(text.includes('fog')||text.includes('mist'))return 'fog';
  if(text.includes('clear')||text.includes('sun'))return 'clear';
  if(text.includes('cloud')||text.includes('overcast'))return 'cloud';
  return 'cloud';
}
function weatherGlyph(summary=''){
  return ({storm:'⛈',snow:'❄',rain:'🌧',fog:'🌫',clear:'☀',cloud:'☁'})[weatherKind(summary)]||'☁';
}
function weatherScene(kind){
  if(kind==='clear')return '<span class="weather-sun"></span><span class="weather-ray ray-a"></span><span class="weather-ray ray-b"></span>';
  if(kind==='rain')return '<span class="weather-cloud cloud-a"></span><span class="rain-drop drop-a"></span><span class="rain-drop drop-b"></span><span class="rain-drop drop-c"></span>';
  if(kind==='snow')return '<span class="weather-cloud cloud-a"></span><span class="snow-flake flake-a">✦</span><span class="snow-flake flake-b">✦</span><span class="snow-flake flake-c">✦</span>';
  if(kind==='storm')return '<span class="weather-cloud cloud-a"></span><span class="storm-bolt">ϟ</span><span class="rain-drop drop-a"></span><span class="rain-drop drop-c"></span>';
  if(kind==='fog')return '<span class="fog-line fog-a"></span><span class="fog-line fog-b"></span><span class="fog-line fog-c"></span>';
  return '<span class="weather-cloud cloud-a"></span><span class="weather-cloud cloud-b"></span>';
}
function renderPondWeatherWidget(){
  const widget=els.pondWeatherWidget;if(!widget)return;
  const env=state?.environment||{};
  const current=env.current_conditions||null;
  const moon=env.moon||{};
  const days=env.forecast_days||[];
  const today=days.find(d=>d.forecast_date===env.local_date)||days[0]||null;
  const temp=current?.temperature_f==null?'—':`${Math.round(Number(current.temperature_f))}°`;
  const summary=current?.summary||today?.summary||'Weather unavailable';
  const shortSummary=summary.length>22?`${summary.slice(0,21)}…`:summary;
  const kind=weatherKind(summary);
  const source=current?.source_kind==='personal_weather_station'?(current.station_id||env.pws_station_id||'KWFLATT11'):(current?.source||env.forecast_source||'Weather');
  const moonName=moon.phase||'Moon cycle';
  const moonLight=moon.illumination_pct==null?'—':`${Number(moon.illumination_pct).toFixed(0)}%`;
  const pwsStatus=String(env.pws_connection_status||'');
  const weatherWarning=pwsStatus && pwsStatus!=='Connected' ? `<span class="living-status-warning" aria-hidden="true">!</span>` : '';
  const weatherLabel=`Weather: ${summary}, ${temp}. Source: ${source}. ${pwsStatus?`PWS ${pwsStatus}. `:''}Open Weather & Seasons.`;
  const moonLabel=`Moon: ${moonName}, ${moonLight} illuminated. Open Moon Cycle details.`;
  widget.innerHTML=`<button class="living-weather-card kind-${kind}" type="button" aria-label="${esc(weatherLabel)}" title="${esc(weatherLabel)}"><span class="weather-scene" aria-hidden="true">${weatherScene(kind)}</span><span class="weather-card-copy"><strong>${esc(temp)}</strong><small>${esc(shortSummary)}</small></span>${weatherWarning}</button><button class="living-moon-chip" type="button" aria-label="${esc(moonLabel)}" title="${esc(moonLabel)}"><span class="moon-glyph" aria-hidden="true">${esc(moon.icon||'🌙')}</span><span><strong>${esc(moonName)}</strong><small>${esc(moonLight)}</small></span></button>`;
  widget.hidden=false;
}

function render(){
  if(!state)return;
  buildWorldDecor();renderBuildings();renderAgents();renderPondWeatherWidget();renderHudTasks();renderProject();renderApprovalBanner();renderActivity();renderExecutiveBadge();renderDashboardRails();renderAiControls();refreshDrawer();
}

async function getJson(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok){let d={};try{d=await r.json();}catch{}throw new Error(d.detail||`Request failed (${r.status})`);}return r.json();}
function providerEls(providerId){
  if(providerId==='gemini'){
    return {dot:els.geminiStatusDot,text:els.geminiConnectionText,model:els.geminiModel,button:els.geminiTestBtn,result:els.geminiTestResult};
  }
  return {dot:els.openaiStatusDot,text:els.openaiConnectionText,model:els.openaiModel,button:els.openaiTestBtn,result:els.openaiTestResult};
}

function providerLabel(providerId){
  return providerId==='openai'?'OpenAI':'Gemini';
}

function renderProviderStatus(providerId,info){
  const ui=providerEls(providerId);
  if(!ui.dot)return;

  ui.dot.classList.remove('configured','connected','error');
  ui.model.textContent=info?.model||'—';

  if(info?.last_verified){
    ui.dot.classList.add('connected');
    ui.text.textContent='Connected · verified';
  }else if(info?.configured){
    ui.dot.classList.add('configured');
    ui.text.textContent='Key configured · ready';
  }else{
    ui.text.textContent=`${providerLabel(providerId)} key not configured`;
  }
}

function renderAiStatus(info){
  renderProviderStatus('gemini',info.providers?.gemini||{});
  renderProviderStatus('openai',info.providers?.openai||{});

  if(els.aiAuthorityText)els.aiAuthorityText.textContent=info.authority||'Multi-provider routing · no automatic fallback.';

  const routes=info.roles||{};
  if(els.routeChief)els.routeChief.textContent=providerLabel(routes.chief);
  if(els.routeResearch)els.routeResearch.textContent=providerLabel(routes.research);
  if(els.routePrograms)els.routePrograms.textContent=providerLabel(routes.programs);
  if(els.routeCaretaker)els.routeCaretaker.textContent=providerLabel(routes.caretaker);
}

async function refreshAiStatus(){
  try{
    renderAiStatus(await getJson('/api/ai/status'));
  }catch(err){
    for(const providerId of ['gemini','openai']){
      const ui=providerEls(providerId);
      if(ui.text)ui.text.textContent='AI status unavailable';
      if(ui.dot)ui.dot.classList.add('error');
    }
  }
}

async function toggleAiStop(){
  if(!state?.ai_control)return;
  const stopping=Boolean(state.ai_control.enabled);
  const endpoint=stopping?'/api/ai/stop':'/api/ai/resume';
  const question=stopping
    ? 'Stop all NEW AI calls? A request already in flight may still finish.'
    : null;

  if(question&&!confirm(question))return;

  const old=els.aiStopBtn?.textContent;
  if(els.aiStopBtn){
    els.aiStopBtn.disabled=true;
    els.aiStopBtn.textContent=stopping?'Stopping…':'Resuming…';
  }

  try{
    const result=await post(endpoint);
    toast(stopping
      ? 'Emergency Stop AI is active. New AI calls are blocked.'
      : (result.control?.budget_blocked
          ? 'AI resumed manually, but the cost guardrail is still blocking new calls.'
          : 'AI calls are enabled.'));
  }catch(err){
    toast(err.message);
  }finally{
    if(els.aiStopBtn){
      els.aiStopBtn.disabled=false;
      if(old)els.aiStopBtn.textContent=old;
    }
  }
}

async function saveAiBudget(){
  if(!els.aiBudgetInput)return;
  const value=Number(els.aiBudgetInput.value);
  if(!Number.isFinite(value)||value<0||value>1000){
    toast('Enter a daily estimate limit between $0 and $1,000.');
    return;
  }

  const old=els.aiBudgetSave?.textContent;
  if(els.aiBudgetSave){
    els.aiBudgetSave.disabled=true;
    els.aiBudgetSave.textContent='Saving…';
  }

  try{
    const result=await post('/api/ai/budget',{daily_estimated_cost_limit_usd:value});
    toast(value===0
      ? 'Estimated-cost guardrail disabled.'
      : `Daily estimated-cost guardrail set to ${fmtMoney(value,2)}.`);
    if(result.control?.budget_blocked){
      toast('The new limit is already below today’s estimate, so new AI calls remain blocked.');
    }
  }catch(err){
    toast(err.message);
  }finally{
    if(els.aiBudgetSave){
      els.aiBudgetSave.disabled=false;
      els.aiBudgetSave.textContent=old||'Save';
    }
  }
}

async function testProviderConnection(providerId){
  const ui=providerEls(providerId);
  if(!ui.button)return;

  const label=providerLabel(providerId);
  const old=ui.button.textContent;

  ui.button.disabled=true;
  ui.button.textContent=`Testing ${label}…`;
  ui.result.textContent='Sending one harmless verification prompt…';
  ui.dot.classList.remove('configured','connected','error');

  try{
    const result=await post(`/api/ai/test/${providerId}`);
    ui.dot.classList.add('connected');
    ui.text.textContent=result.verified?'Connected · verified':'Connected · responded';
    ui.model.textContent=result.model||'—';
    ui.result.textContent=`${result.message} · ${result.latency_ms} ms`;
    toast(`${label} connection is working.`);
  }catch(err){
    ui.dot.classList.add('error');
    ui.text.textContent='Connection test failed';
    ui.result.textContent=err.message;
    toast(err.message);
  }finally{
    ui.button.disabled=false;
    ui.button.textContent=old;
    refreshAiStatus();
  }
}

async function post(url,body){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  if(!r.ok){let d={};try{d=await r.json();}catch{}throw new Error(d.detail||`Request failed (${r.status})`);}return r.json();
}
async function loadWorkReport(filters=null){
  if(filters)workReportFilters={...workReportFilters,...filters};
  workReportLoading=true;
  if(activeView.panel==='work_report')openDrawer('work_report');
  try{
    const query=workReportParams(workReportFilters);
    const r=await fetch(`/api/work-report${query?`?${query}`:''}`,{cache:'no-store'});
    if(!r.ok){let d={};try{d=await r.json();}catch{}throw new Error(d.detail||`Report failed (${r.status})`);}
    workReport=await r.json();
  }catch(err){toast(err.message);}
  finally{
    workReportLoading=false;
    if(activeView.panel==='work_report')openDrawer('work_report');
  }
}
function readWorkReportFilters(form){
  const fd=new FormData(form), result={};
  ['person_id','activity_category_id','project_id','participation_type','start_date','end_date'].forEach(key=>result[key]=String(fd.get(key)||''));
  return result;
}

async function savePerson(form){
  const fd=new FormData(form);
  const body={display_name:String(fd.get('display_name')||'').trim(),person_type:String(fd.get('person_type')||'Volunteer'),notes:String(fd.get('notes')||''),is_primary_user:fd.get('is_primary_user')==='1'};
  if(!body.display_name){toast('Add a name first.');return;}
  try{await post('/api/people',body);form.reset();toast(`${body.display_name} added to Poe’s people ledger.`);}catch(err){toast(err.message);}
}
async function saveCalendarEvent(form){
  const f=new FormData(form), id=Number(form.dataset.eventId||0)||null;
  const body={
    title:(f.get('title')||'').trim(), event_date:f.get('event_date')||'', start_time:f.get('start_time')||null,
    end_time:f.get('end_time')||null, all_day:f.get('all_day')==='1', location:(f.get('location')||'').trim(),
    event_type:f.get('event_type')||'Institute', commitment_level:f.get('commitment_level')||'Normal',
    project_id:f.get('project_id')?Number(f.get('project_id')):null, notes:(f.get('notes')||'').trim(), status:f.get('status')||'Scheduled'
  };
  try{await post(id?`/api/events/${id}`:'/api/events',body);calendarEditingId=null;toast(id?'Calendar event updated.':'Calendar event added.');openDrawer('calendar');}
  catch(err){toast(err.message);}
}

async function saveGrant(form){
  const fd=new FormData(form), num=name=>String(fd.get(name)||'').trim()===''?null:Number(fd.get(name));
  const projectRaw=String(fd.get('project_id')||'');
  const body={
    funder:String(fd.get('funder')||'').trim(),title:String(fd.get('title')||'').trim(),deadline:String(fd.get('deadline')||'')||null,
    amount_min:num('amount_min'),amount_max:num('amount_max'),amount_notes:String(fd.get('amount_notes')||''),source_url:String(fd.get('source_url')||'').trim(),
    status:String(fd.get('status')||'Discovered'),project_id:projectRaw?Number(projectRaw):null,notes:String(fd.get('notes')||''),
    mission_fit:Number(fd.get('mission_fit')||3),workload:Number(fd.get('workload')||3),restrictions:Number(fd.get('restrictions')||3),strategic_value:Number(fd.get('strategic_value')||3),
    recommendation:String(fd.get('recommendation')||'Review'),assessment_notes:String(fd.get('assessment_notes')||'')
  };
  if(!body.funder||!body.title){toast('Add the funder and grant name first.');return;}
  const id=form.dataset.grantId;
  try{await post(id?`/api/grants/${id}`:'/api/grants',body);grantEditingId=null;toast(id?'Vernadette updated the grant record.':'Vernadette added the opportunity to the Grant Desk.');openDrawer('grants');}catch(err){toast(err.message);}
}

async function searchGrantDiscovery(form){
  if(grantDiscoveryLoading)return;
  const keyword=String(new FormData(form).get('keyword')||'').trim();
  if(!keyword){toast('Tell Vernadette what kind of funding to search for.');return;}
  grantDiscoveryLoading=true;grantDiscoveryResult=null;openDrawer('grants');
  try{
    const result=await post('/api/grants/discover',{keyword,rows:20});
    grantDiscoveryResult={...result,message:`Grants.gov reports ${result.hit_count||0} matching federal opportunity record(s); showing ${result.returned||0}. Review before adding anything to the Grant Desk.`};
    toast(`Vernadette found ${result.returned||0} federal result(s) to review.`);
  }catch(err){grantDiscoveryResult={message:err.message,results:[]};toast(err.message);}
  finally{grantDiscoveryLoading=false;openDrawer('grants');}
}
function currentDiscoveryItem(sourceKey){
  const key=String(sourceKey||'');
  const pools=[grantDiscoveryResult?.results||[],vernadetteCommandResult?.discovery_results||[]];
  for(const pool of pools){const found=pool.find(x=>String(x.source_key||'')===key);if(found)return found;}
  return null;
}
async function importGrantDiscovery(sourceKey){
  const item=currentDiscoveryItem(sourceKey);
  if(!item){toast('That discovery result is no longer loaded. Search again.');return;}
  if(item.already_in_desk){toast('That opportunity is already in the Grant Desk.');return;}
  grantImportingKey=String(sourceKey);openDrawer(activeView.panel,activeView.id,activeView.parent);
  try{
    const result=await post('/api/grants/import-discovery',{source_key:item.source_key,opportunity_number:item.opportunity_number||'',title:item.title,funder:item.funder,deadline:item.deadline||null,source_status:item.source_status||''});
    item.already_in_desk=true;item.grant_id=result.grant_id;item.desk_status=result.desk_status||'Discovered';
    toast(result.status==='already_exists'?'That opportunity was already in the Grant Desk.':'Vernadette added the federal opportunity to the Grant Desk for review.');
  }catch(err){toast(err.message);}
  finally{grantImportingKey=null;openDrawer(activeView.panel,activeView.id,activeView.parent);}
}

async function sendVernadetteCommand(form){
  if(vernadetteCommandSubmitting)return;
  const text=String(new FormData(form).get('text')||'').trim();
  if(!text){toast('Tell Vernadette what you want her to do.');return;}
  vernadetteCommandSubmitting=true;vernadetteCommandResult=null;openDrawer(activeView.panel,activeView.id,activeView.parent);
  try{
    vernadetteCommandResult=await post('/api/vernadette/command',{text});
    if(vernadetteCommandResult.status==='ok')toast(vernadetteCommandResult.message||'Vernadette handled it.');
  }catch(err){vernadetteCommandResult={status:'clarification',message:err.message};toast(err.message);}
  finally{vernadetteCommandSubmitting=false;openDrawer(activeView.panel,activeView.id,activeView.parent);}
}

async function setPrimaryPerson(id){
  try{await post(`/api/people/${id}/primary`,{});toast('Poe will now understand “me” as that person.');}catch(err){toast(err.message);}
}
async function sendPoeCommand(form){
  if(poeCommandSubmitting)return;
  const text=String(new FormData(form).get('text')||'').trim();
  if(!text){toast('Tell Poe what you want him to do.');return;}
  poeCommandSubmitting=true;poeCommandResult=null;openDrawer(activeView.panel,activeView.id,activeView.parent);
  try{
    poeCommandResult=await post('/api/poe/command',{text});
    if(poeCommandResult.status==='ok')toast(poeCommandResult.message||'Poe handled it.');
  }catch(err){poeCommandResult={status:'clarification',message:err.message};toast(err.message);}
  finally{poeCommandSubmitting=false;openDrawer(activeView.panel,activeView.id,activeView.parent);}
}
function openPoeReportResult(){
  if(!poeCommandResult?.report_filters)return;
  const f=poeCommandResult.report_filters;
  workReportFilters={
    person_id:f.person_id==null?'':String(f.person_id),activity_category_id:f.activity_category_id==null?'':String(f.activity_category_id),project_id:f.project_id==null?'':String(f.project_id),participation_type:f.participation_type||'',start_date:f.start_date||'',end_date:f.end_date||''
  };
  workReport=null;openDrawer('work_report');loadWorkReport();
}

async function clockInWork(form){
  const fd=new FormData(form);
  const personId=Number(fd.get('person_id')||0),categoryId=Number(fd.get('activity_category_id')||0),projectRaw=String(fd.get('project_id')||'');
  if(!personId||!categoryId){toast('Choose a person and activity.');return;}
  const body={person_id:personId,activity_category_id:categoryId,participation_type:String(fd.get('participation_type')||'Volunteer'),project_id:projectRaw?Number(projectRaw):null,notes:String(fd.get('notes')||'')};
  try{await post('/api/work-sessions/clock-in',body);form.reset();toast('Poe clocked the work session in.');}catch(err){toast(err.message);}
}
async function clockOutWork(id){
  try{const result=await post(`/api/work-sessions/${id}/clock-out`,{});toast(`Poe clocked the session out · ${workMinutesLabel(result.duration_minutes)}.`);}catch(err){toast(err.message);}
}
async function correctWorkSession(id){
  const item=(state.work_sessions||[]).find(x=>Number(x.id)===Number(id));if(!item)return;
  if(item.entry_mode==='manual_duration'){
    const workDate=prompt('Correct work date (YYYY-MM-DD):',item.work_date||'');if(workDate===null)return;
    const duration=prompt('Correct duration in minutes:',String(item.duration_minutes||''));if(duration===null)return;
    const minutes=Number(duration);if(!Number.isFinite(minutes)||minutes<=0){toast('Duration must be greater than zero.');return;}
    const notes=prompt('Correct work note:',item.notes||'');if(notes===null)return;
    try{await post(`/api/work-sessions/${id}`,{work_date:workDate.trim(),duration_minutes:Math.round(minutes),notes});toast('Remembered work entry corrected. Poe preserved the audit trail.');}catch(err){toast(err.message);}
    return;
  }
  const started=prompt('Correct start time (ISO date/time):',item.started_at||'');if(started===null)return;
  const ended=prompt('Correct end time (ISO date/time):',item.ended_at||'');if(ended===null)return;
  const notes=prompt('Correct work note:',item.notes||'');if(notes===null)return;
  try{await post(`/api/work-sessions/${id}`,{started_at:started.trim(),ended_at:ended.trim(),notes});toast('Work session corrected. Poe preserved the audit trail.');}catch(err){toast(err.message);}
}

async function decideApproval(id,decision){
  try{
    const note=els.drawerBody.querySelector(`[data-approval-note="${id}"]`)?.value||'';
    const result=await post(`/api/approvals/${id}/decide`,{decision,note});
    if(decision==='changes'){
      toast('Changes requested. The current output versions are preserved.');
      if(result.project_id)openDrawer('project',result.project_id,'projects');
      return;
    }
    if(result.revision_execution_started){
      toast('Selective revision approved. Only the chosen work is reopening.');
      if(result.project_id)openDrawer('project',result.project_id,'projects');
    }else if(result.execution_started){
      toast('Plan approved. The campus is starting the approved workflow now.');
      if(result.project_id)openDrawer('project',result.project_id,'projects');
    }else if(result.project_completed){
      toast('Project outputs approved. This internal package is complete.');
      if(result.project_id)openDrawer('project',result.project_id,'projects');
    }else{
      toast('Approval recorded.');
    }
  }catch(err){toast(err.message);}
}
async function decideProgramsLibraryFirst(taskId,decision,collectionId=null){
  const task=taskById(taskId);
  const buttons=[...els.drawerBody.querySelectorAll('[data-programs-library-choice]')];
  buttons.forEach(b=>b.disabled=true);
  const note=els.drawerBody.querySelector(`[data-library-first-note="${taskId}"]`)?.value||'';
  try{
    const payload={decision,note};
    if(collectionId)payload.collection_id=Number(collectionId);
    const result=await post(`/api/programs/library-first/${taskId}/decide`,payload);
    const label={reuse:'Reuse Existing',revise:'Revise Existing',create_new:'Create New'}[decision]||decision;
    toast(`${label} recorded. Programs workflow is resuming.`);
    if(result.project_id)openDrawer('project',result.project_id,'projects');
    else if(task)openDrawer('task',task.id,'projects');
  }catch(err){
    toast(err.message);
    buttons.forEach(b=>b.disabled=false);
  }
}

async function saveNote(kind,id,body){
  try{await post(kind==='project'?`/api/projects/${id}/notes`:`/api/tasks/${id}/notes`,{body,author:'Human'});toast('Note saved.');}
  catch(err){toast(err.message);}
}
async function saveMemory(form){
  const data=new FormData(form);
  const editId=form.dataset.memoryEditId?Number(form.dataset.memoryEditId):null;
  const payload={
    project_id:data.get('project_id')?Number(data.get('project_id')):null,
    memory_type:data.get('memory_type')||'Context',
    importance:data.get('importance')||'Normal',
    title:String(data.get('title')||'').trim(),
    body:String(data.get('body')||'').trim(),
    tags:String(data.get('tags')||'').trim(),
    review_interval_days:Number(data.get('review_interval_days')||180)
  };
  if(!payload.title||!payload.body){toast('Memory needs a title and body.');return;}
  try{
    const supersedeId=form.dataset.memorySupersedeId?Number(form.dataset.memorySupersedeId):null;
    if(supersedeId){
      const result=await post(`/api/memory/${supersedeId}/supersede`,payload);
      memorySupersedeId=null;memoryEditingId=Number(result.memory_id);
      toast('Replacement memory created; the prior memory was archived.');
    }else if(editId){
      await post(`/api/memory/${editId}`,payload);
      memoryEditingId=null;
      toast('Institutional Memory updated.');
    }else{
      await post('/api/memory',{...payload,created_by:'Human',source_kind:'manual'});
      toast('Saved to Institutional Memory.');
      form.reset();
    }
  }catch(err){toast(err.message);}
}
async function captureMemory(kind,id){
  try{
    const result=await post('/api/memory/capture',{source_kind:kind,source_id:Number(id),memory_type:'Context',importance:'Normal',review_interval_days:180});
    if(result.already_exists){
      memoryEditingId=Number(result.memory_id);
      toast('That source is already in Institutional Memory. Opening it for review.');
      openDrawer('memory');
    }else{
      memoryEditingId=Number(result.memory_id);
      toast('Captured into Institutional Memory. Review or refine it now.');
      openDrawer('memory');
    }
  }catch(err){toast(err.message);}
}
async function rememberActiveDeliverable(){
  if(!activeDeliverableId)return;
  const id=activeDeliverableId;
  closeDeliverable();
  await captureMemory('deliverable',id);
}
async function reviewMemory(id){
  try{await post(`/api/memory/${id}/review`);toast('Memory review recorded and the next review date was scheduled.');}
  catch(err){toast(err.message);}
}
async function setMemoryStatus(id,status){
  try{
    await post(`/api/memory/${id}/status`,{status});
    toast(status==='Archived'?'Memory archived. It will no longer be sent to agents.':'Memory restored to active use.');
  }catch(err){toast(err.message);}
}

async function updateTaskStatus(id,status){
  try{await post(`/api/tasks/${id}/status`,{status});toast(`Task marked ${status}.`);}
  catch(err){toast(err.message);}
}

async function planRevision(projectId){
  const project=projectById(projectId);
  const title=project?.title||`Project ${projectId}`;
  if(!confirm(`Ask Stella to plan the smallest useful revision for "${title}"? This makes one Stella planning call, but no revision work will run until you approve the plan.`))return;

  try{
    toast('Stella is planning the selective revision…');
    const result=await post(`/api/projects/${projectId}/revision/plan`);
    toast(`Revision ${result.revision_number} is ready for your approval.`);
    openDrawer('project',result.project_id,'projects');
    refreshAiStatus();

  }catch(err){
    toast(err.message);
  }
}

async function sendStellaDaily(form){
  if(stellaDailySubmitting)return;
  const text=String(new FormData(form).get('text')||'').trim();
  if(!text){toast('Ask Stella what you need help prioritizing.');return;}
  stellaDailySubmitting=true;stellaDailyResult=null;openDrawer('briefing');
  try{
    stellaDailyResult=await post('/api/stella/daily',{text});
    if(stellaDailyResult.status==='ok')toast('Stella checked today’s Campus priorities.');
  }catch(err){stellaDailyResult={status:'clarification',message:err.message};toast(err.message);}
  finally{stellaDailySubmitting=false;openDrawer('briefing');}
}

async function saveBriefingSnapshot(){
  try{const result=await post('/api/briefing/snapshot');toast(`Briefing snapshot saved · ${result.additional_ai_calls} extra AI calls.`);openDrawer('briefing');}catch(err){toast(err.message);}
}

async function savePlaybook(form){
  const fd=new FormData(form);
  const payload={
    project_id:fd.get('project_id')?Number(fd.get('project_id')):null,
    owner_agent_id:fd.get('owner_agent_id')||null,
    title:String(fd.get('title')||'').trim(),purpose:String(fd.get('purpose')||'').trim(),trigger_text:String(fd.get('trigger_text')||'').trim(),
    steps:String(fd.get('steps')||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean),tags:String(fd.get('tags')||'').trim(),status:String(fd.get('status')||'Draft')
  };
  if(!payload.title||!payload.purpose||!payload.steps.length){toast('Playbooks need a title, purpose, and at least one step.');return;}
  try{
    const id=form.dataset.playbookId;
    await post(id?`/api/playbooks/${id}`:'/api/playbooks',payload);
    playbookEditingId=null;toast(id?'Playbook updated.':'Playbook created.');openDrawer('playbooks');
  }catch(err){toast(err.message);}
}
async function setPlaybookStatus(id,status){
  try{await post(`/api/playbooks/${id}/status`,{status});toast(`Playbook set to ${status}.`);if(playbookEditingId===Number(id))playbookEditingId=null;openDrawer('playbooks');}catch(err){toast(err.message);}
}

async function askLibrarian(form){
  const fd=new FormData(form);
  const query=String(fd.get('query')||'').trim();
  if(!query){toast('Ask the Librarian a question first.');return;}
  librarianQuery=query;
  const button=form.querySelector('button[type="submit"]');
  if(button){button.disabled=true;button.textContent='Searching Library…';}
  try{
    const response=await fetch(`/api/library/librarian?q=${encodeURIComponent(query)}`);
    let result={};try{result=await response.json();}catch{}
    if(!response.ok)throw new Error(result.detail||'Librarian search failed.');
    librarianResult=result;
    toast(result.status==='found'?'Librarian found trusted Library material.':'Nothing useful found in the trusted Library.');
    openDrawer('library');
  }catch(err){toast(err.message||'Librarian search failed.');}
  finally{if(button){button.disabled=false;button.textContent='Ask Librarian';}}
}

async function uploadLibraryInbox(form){
  const input=form.querySelector('input[type="file"]');
  const selected=Array.from(input?.files||[]);
  if(!selected.length){toast('Choose at least one file for the Library Drop Box.');return;}
  if(selected.length>100){toast('Please upload no more than 100 files in one batch.');return;}
  const button=form.querySelector('button[type="submit"]');
  if(button){button.disabled=true;button.textContent='Uploading…';}
  let received=0,duplicates=0;
  try{
    for(const file of selected){
      if(file.size>100*1024*1024)throw new Error(`${file.name} is larger than the 100 MB per-file limit.`);
      const response=await fetch(`/api/library/inbox/upload?filename=${encodeURIComponent(file.name)}`,{
        method:'POST',
        headers:{'Content-Type':file.type||'application/octet-stream','X-Filename':file.name},
        body:file
      });
      let result={};try{result=await response.json();}catch{}
      if(!response.ok)throw new Error(result.detail||`Upload failed for ${file.name}.`);
      if(result.status==='duplicate')duplicates++;else received++;
    }
    toast(`Library Drop Box: ${received} received${duplicates?` · ${duplicates} duplicate${duplicates===1?'':'s'} skipped`:''}.`);
    openDrawer('library');
  }catch(err){toast(err.message||'Library upload failed.');openDrawer('library');}
  finally{if(button){button.disabled=false;button.textContent='Add to Incoming Materials';}}
}

async function catalogLibraryInbox(form){
  const fd=new FormData(form);
  const inboxId=Number(form.dataset.inboxId);
  const payload={
    collection_id:Number(fd.get('collection_id')),
    title:String(fd.get('title')||'').trim(),
    material_type:String(fd.get('material_type')||'Document'),
    edition_label:String(fd.get('edition_label')||'').trim(),
    edition_date:String(fd.get('edition_date')||'').trim()||null,
    notes:String(fd.get('notes')||'').trim()
  };
  if(!inboxId||!payload.collection_id||!payload.title){toast('Choose a collection and material title first.');return;}
  const button=form.querySelector('button[type="submit"]');
  if(button){button.disabled=true;button.textContent='Cataloging…';}
  try{
    await post(`/api/library/inbox/${inboxId}/catalog`,payload);
    toast('Approved into the trusted Library.');
    openDrawer('library');
  }catch(err){toast(err.message||'Cataloging failed.');openDrawer('library');}
  finally{if(button){button.disabled=false;button.textContent='Approve into Trusted Library';}}
}

async function saveLibraryCollection(form){
  const fd=new FormData(form);
  const payload={
    title:String(fd.get('title')||'').trim(),
    collection_type:String(fd.get('collection_type')||'Program'),
    subject:String(fd.get('subject')||'').trim(),
    description:String(fd.get('description')||'').trim(),
    status:String(fd.get('status')||'Active')
  };
  if(!payload.title){toast('Library records need a title.');return;}
  try{
    const id=form.dataset.libraryId;
    await post(id?`/api/library/collections/${id}`:'/api/library/collections',payload);
    libraryEditingId=null;
    toast(id?'Library catalog record updated.':'Added to the Library catalog.');
    openDrawer('library');
  }catch(err){toast(err.message);}
}
async function setLibraryStatus(id,status){
  try{
    await post(`/api/library/collections/${id}/status`,{status});
    if(libraryEditingId===Number(id))libraryEditingId=null;
    toast(status==='Archived'?'Library record archived.':'Library record restored.');
    openDrawer('library');
  }catch(err){toast(err.message);}
}

async function saveEnvironmentSettings(form){
  const fd=new FormData(form); const num=n=>fd.get(n)===''?null:Number(fd.get(n));
  try{await post('/api/environment/settings',{location_label:fd.get('location_label'),timezone_name:fd.get('timezone_name'),seasonal_region:fd.get('seasonal_region'),latitude:num('latitude'),longitude:num('longitude'),pws_station_id:fd.get('pws_station_id'),live_weather_enabled:fd.get('live_weather_enabled')!=='0'});toast('Weather settings saved.');openDrawer('environment');}catch(err){toast(err.message);}
}
async function refreshWeather(){
  const btn=els.drawerBody.querySelector('[data-weather-refresh]'); const old=btn?.textContent;
  try{if(btn){btn.disabled=true;btn.textContent='Refreshing…';}await post('/api/environment/refresh',{});toast('Weather refreshed.');openDrawer('environment');}catch(err){toast(err.message||'Weather refresh failed.');openDrawer('environment');}finally{if(btn){btn.disabled=false;btn.textContent=old||'Refresh Weather';}}
}
async function saveWeatherDay(form){
  const fd=new FormData(form); const num=n=>fd.get(n)===''?null:Number(fd.get(n));
  try{await post('/api/environment/weather/day',{forecast_date:fd.get('forecast_date'),high_f:num('high_f'),low_f:num('low_f'),precip_chance:num('precip_chance'),summary:fd.get('summary')});toast('Manual forecast day saved.');openDrawer('environment');}catch(err){toast(err.message);}
}
async function saveSeasonalWindow(form){
  const fd=new FormData(form);
  try{await post('/api/environment/seasonal-windows',{name:fd.get('name'),category:fd.get('category'),start_md:fd.get('start_md'),end_md:fd.get('end_md'),priority:fd.get('priority'),notes:fd.get('notes'),status:'Active'});toast('Seasonal window added.');openDrawer('environment');}catch(err){toast(err.message);}
}
async function setSeasonalStatus(id,status){try{await post(`/api/environment/seasonal-windows/${id}/status`,{status});toast(`Seasonal window ${String(status).toLowerCase()}.`);openDrawer('environment');}catch(err){toast(err.message);}}
async function savePhenology(form){const fd=new FormData(form);try{await post('/api/environment/phenology',{subject:fd.get('subject'),stage:fd.get('stage'),observation_date:fd.get('observation_date'),location_area:fd.get('location_area'),source:'human observation',status:'observed',notes:fd.get('notes')});toast('Phenology observation recorded.');openDrawer('environment');}catch(err){toast(err.message);}}
async function reviewPhenology(id,status){try{await post(`/api/environment/phenology/${id}/review`,{status});toast(`Phenology suggestion ${status}.`);openDrawer('environment');}catch(err){toast(err.message);}}
async function loadPhenologyHistory(form){const f=new FormData(form),q=new URLSearchParams({subject:f.get('subject'),stage:f.get('stage'),location_area:f.get('location_area')||''});try{phenologyHistory=await getJson(`/api/environment/phenology/history?${q}`);openDrawer('environment');}catch(err){toast(err.message);}}
async function saveWatchlist(form){const f=new FormData(form);try{await post('/api/environment/phenology/watchlist',{subject:f.get('subject'),category:f.get('category'),location_area:f.get('location_area'),stages:String(f.get('stages')).split(','),notes:''});openDrawer('environment');}catch(err){toast(err.message);}}


function setFocusWorkspace(enabled){
  document.body.classList.toggle('focus-workspace',Boolean(enabled));
  if(els.focusWorkspaceBtn){
    els.focusWorkspaceBtn.textContent=enabled?'Show Side Panels':'Focus Workspace';
    els.focusWorkspaceBtn.setAttribute('aria-pressed',enabled?'true':'false');
  }
  try{localStorage.setItem('mavis-focus-workspace',enabled?'1':'0');}catch{}
}
function toggleFocusWorkspace(){
  setFocusWorkspace(!document.body.classList.contains('focus-workspace'));
}
async function rescanRepository(){
  try{
    const result=await post('/api/repository/rescan');
    toast(`Repository refreshed · ${result.file_count} file${Number(result.file_count)===1?'':'s'}.`);
  }catch(err){toast(err.message);}
}

async function retryProject(projectId){
  const project=projectById(projectId);
  const title=project?.title||`Project ${projectId}`;
  if(!confirm(`Retry / Resume "${title}" from unfinished work? Completed tasks and saved artifacts will be preserved.`))return;

  try{
    const result=await post(`/api/projects/${projectId}/resume`);
    toast('Recovery started. Completed work will not be repeated.');
    openDrawer('project',result.project_id,'projects');
  }catch(err){
    toast(err.message);
  }
}


function campusAskRouteLabel(result){
  return result?.handled_by||result?.agent_name||'Campus';
}
function campusAskTimeLabel(){
  try{return new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});}catch{return 'Now';}
}
function campusAskEntryHtml(result,question){
  const route=campusAskRouteLabel(result);
  const source=result.mode==='deterministic'?'local · no AI call':result.mode==='ai_advice'?`advisory AI · ${esc(result.model||'configured provider')}`:'Campus routing';
  const routeSource=result.route_source==='selected'?'You chose this person':result.route_source==='followup'?'Follow-up continuity':result.route_source==='project_guard'?'Project safeguard':'Auto-routed';
  let body='';
  if(result.message)body+=`<p>${esc(result.message)}</p>`;
  if(result.daily_steward){
    const daily=result.daily_steward,focus=daily.focus||[];
    body+=`<div class="campus-ask-focus">${focus.map((x,i)=>`<div><b>${i+1}</b><span><strong>${esc(displayWorkflowText(x.title||''))}</strong><small>${esc(displayWorkflowText(x.why||''))}</small></span></div>`).join('')||'<p>No focus items are currently competing for today.</p>'}</div>${daily.protect_attention?`<p class="campus-ask-protect"><strong>Protect your attention:</strong> ${esc(daily.protect_attention)}</p>`:''}`;
  }
  const actions=[];
  if(result.open_panel)actions.push(`<button type="button" class="button-quiet" data-open-panel="${esc(result.open_panel)}">Open ${esc(result.open_label||titleCase(result.open_panel))}</button>`);
  if(result.suggest_project)actions.push(`<button type="button" class="button-primary" data-campus-create-project="${esc(result.original_text||question||'')}">Create Project Plan</button>`);
  const badge=result.project_created?'Project created':result.suggest_project?'Project not created':'Read-only';
  const routeNote=result.route_reason?`<div class="campus-route-note"><b>${esc(routeSource)}</b><span>${esc(result.route_reason)}</span></div>`:'';
  return `<article class="campus-ask-exchange"><div class="campus-ask-question"><small>You · ${esc(campusAskTimeLabel())}</small><p>${esc(question||'')}</p></div><div class="campus-ask-answer"><div class="campus-ask-response-head"><div><span>${esc(route)}</span><small>${source}</small></div><b>${esc(badge)}</b></div>${routeNote}${body}${actions.length?`<div class="campus-ask-response-actions">${actions.join('')}</div>`:''}</div></article>`;
}
function campusAskThreadHtml(){
  const hint=campusAskHistory.length>1?`<div class="campus-ask-history-hint">Newest response first · scroll down for older exchanges</div>`:'';
  return `${hint}<div class="campus-ask-thread">${campusAskHistory.join('')}</div>`;
}
function saveCampusAskThread(){try{sessionStorage.setItem(CAMPUS_ASK_SESSION_KEY,JSON.stringify(campusAskHistory.slice(0,CAMPUS_ASK_HISTORY_LIMIT)));}catch{}}
function restoreCampusAskThread(){
  const node=els.campusAskResponse;if(!node)return;
  try{const saved=JSON.parse(sessionStorage.getItem(CAMPUS_ASK_SESSION_KEY)||'[]');campusAskHistory=Array.isArray(saved)?saved.slice(0,CAMPUS_ASK_HISTORY_LIMIT):[];}catch{campusAskHistory=[];}
  if(campusAskHistory.length){node.innerHTML=campusAskThreadHtml();node.hidden=false;node.scrollTop=0;}
}
function clearCampusAskThread(){campusAskHistory=[];campusAskLastResult=null;try{sessionStorage.removeItem(CAMPUS_ASK_SESSION_KEY);}catch{};const node=els.campusAskResponse;if(node){node.innerHTML='';node.hidden=true;}toast('Ask the Campus conversation cleared.');}
function renderCampusAskResponse(result,question=''){
  const node=els.campusAskResponse;if(!node)return;
  campusAskLastResult=result||null;
  if(!result){clearCampusAskThread();return;}
  campusAskHistory.unshift(campusAskEntryHtml(result,question||els.campusQuestion?.value||''));
  campusAskHistory=campusAskHistory.slice(0,CAMPUS_ASK_HISTORY_LIMIT);
  saveCampusAskThread();
  node.innerHTML=campusAskThreadHtml();
  node.hidden=false;node.scrollTop=0;
  requestAnimationFrame(()=>node.scrollIntoView({behavior:prefersReducedMotion?'auto':'smooth',block:'nearest'}));
}
async function askCampus(){
  if(campusAskSubmitting){toast('The Campus is already handling that question.');return;}
  const text=els.campusQuestion?.value?.trim()||'';
  if(!text){toast('Write a question or request first.');return;}
  const agent=els.campusAgent?.value||'auto';
  const old=els.campusAskBtn?.textContent||'Ask';
  try{
    campusAskSubmitting=true;if(els.campusAskBtn){els.campusAskBtn.disabled=true;els.campusAskBtn.textContent='Checking…';}
    const previousAgent=agent==='auto'?(campusAskLastResult?.agent||''):'';
    const result=await post('/api/campus/ask',{text,agent,previous_agent:previousAgent});
    renderCampusAskResponse(result,text);
    if(result.vernadette_result){vernadetteCommandResult=result.vernadette_result;if(result.vernadette_result.discovery_results)grantDiscoveryResult={provider:result.vernadette_result.provider,query:result.vernadette_result.query,hit_count:result.vernadette_result.hit_count,results:result.vernadette_result.discovery_results};}
    if(result.poe_result)poeCommandResult=result.poe_result;
    if(result.daily_steward){stellaDailyResult={status:'ok',message:result.message||'',daily_steward:result.daily_steward};}
    refreshAiStatus();
  }catch(err){renderCampusAskResponse({handled_by:'Campus',mode:'routing',message:err.message||String(err),project_created:false},text);}
  finally{campusAskSubmitting=false;if(els.campusAskBtn){els.campusAskBtn.disabled=false;els.campusAskBtn.textContent=old;}}
}

function newChiefRequestId(){return globalThis.crypto?.randomUUID?.()||`chief-${Date.now()}-${Math.random().toString(16).slice(2)}`;}
async function submitChiefPlan(request,{forceNew=false}={}){
  const result=await post('/api/chief/plan',{title:request,request_id:newChiefRequestId(),force_new:forceNew});
  if(result.duplicate_prevented){
    openDrawer('project',result.project_id,'projects');
    if(result.project_status==='Awaiting Approval'){
      toast('Duplicate request prevented · review the existing Stella plan first.');
      return result;
    }
    toast('Duplicate request prevented · opened the existing project.');
    if(confirm('This same request was just planned. Click OK only if you intentionally want Stella to create a separate new plan.')){
      return await submitChiefPlan(request,{forceNew:true});
    }
    return result;
  }
  toast(`Stella prepared ${result.task_count} proposed tasks. Review the plan before approving it.`);
  openDrawer('project',result.project_id,'projects');
  refreshAiStatus();
  return result;
}
els.campusAskForm?.addEventListener('submit',async e=>{e.preventDefault();await askCampus();});
els.campusQuestion?.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();els.campusAskForm?.requestSubmit();}});
document.querySelector('#campus-ask-clear')?.addEventListener('click',clearCampusAskThread);
restoreCampusAskThread();
els.campusAskForm?.addEventListener('click',async e=>{
  const example=e.target.closest('[data-campus-example]');
  if(example){els.campusQuestion.value=example.dataset.campusExample||'';els.campusQuestion.focus();return;}
  const panel=e.target.closest('[data-open-panel]');
  if(panel){openDrawer(panel.dataset.openPanel);return;}
  const create=e.target.closest('[data-campus-create-project]');
  if(create){
    const request=create.dataset.campusCreateProject||els.campusQuestion?.value?.trim()||'';
    if(!request)return;
    const old=create.textContent;
    try{create.disabled=true;create.textContent='Stella is planning…';await submitChiefPlan(request);}
    catch(err){toast(err.message);}
    finally{create.disabled=false;create.textContent=old;}
  }
});
els.resetBtn.addEventListener('click',async()=>{if(!confirm('Reset campus projects, Stella plans, notes, approvals, activity, and project files? Institutional Memory is preserved. This cannot be undone.'))return;try{await post('/api/reset');toast('Campus work reset. Staff returned home.');openDrawer('map');}catch(err){toast(err.message);}});
els.navButtons.forEach(btn=>btn.addEventListener('click',()=>openDrawer(btn.dataset.panel)));
els.drawerClose.addEventListener('click',()=>openDrawer('map'));
els.needsMeBtn.addEventListener('click',()=>openDrawer('executive'));
els.briefingBtn?.addEventListener('click',()=>openDrawer('briefing'));
els.repositoryBtn?.addEventListener('click',()=>openDrawer('repository'));
els.memoryBtn?.addEventListener('click',()=>openDrawer('memory'));
els.playbooksBtn?.addEventListener('click',()=>openDrawer('playbooks'));
els.pondWeatherWidget?.addEventListener('click',()=>openDrawer('environment'));
els.focusWorkspaceBtn?.addEventListener('click',toggleFocusWorkspace);
els.geminiTestBtn?.addEventListener('click',()=>testProviderConnection('gemini'));
els.openaiTestBtn?.addEventListener('click',()=>testProviderConnection('openai'));
els.aiStopBtn?.addEventListener('click',toggleAiStop);
els.aiBudgetSave?.addEventListener('click',saveAiBudget);
els.aiBudgetInput?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();saveAiBudget();}});

document.querySelectorAll('.dashboard-rail').forEach(rail=>rail.addEventListener('click',e=>{
  const btn=e.target.closest('button');if(!btn)return;
  if(btn.dataset.concept)openConcept(btn.dataset.concept);
  else if(btn.dataset.openAgent)openDrawer('agent',btn.dataset.openAgent,'people');
  else if(btn.dataset.openPanel){openDrawer(btn.dataset.openPanel,btn.dataset.openId||null);if(btn.dataset.openPanel==='work_report')loadWorkReport();}
}));
els.conceptModalClose?.addEventListener('click',closeConcept);
els.conceptModal?.querySelector('[data-close-concept]')?.addEventListener('click',closeConcept);
els.deliverableModalClose?.addEventListener('click',closeDeliverable);
els.deliverableModal?.querySelector('[data-close-deliverable]')?.addEventListener('click',closeDeliverable);
els.deliverableCopy?.addEventListener('click',copyActiveDeliverable);
els.deliverableRemember?.addEventListener('click',rememberActiveDeliverable);
els.deliverableDownloadMd?.addEventListener('click',()=>downloadActiveDeliverable('md'));
els.deliverableDownloadTxt?.addEventListener('click',()=>downloadActiveDeliverable('txt'));
els.deliverablePrint?.addEventListener('click',printActiveDeliverable);
document.addEventListener('keydown',e=>{
  if(e.key!=='Escape')return;
  if(!els.deliverableModal?.hidden){closeDeliverable();return;}
  if(!els.conceptModal?.hidden){closeConcept();return;}
  if(!els.drawer.hidden){openDrawer('map');}
});

els.drawerBody.addEventListener('click',e=>{
  const btn=e.target.closest('button');if(!btn)return;
  if(btn.dataset.concept)openConcept(btn.dataset.concept);
  else if(btn.dataset.projectTab){
    projectTabById.set(Number(btn.dataset.projectId),btn.dataset.projectTab);
    openDrawer('project',btn.dataset.projectId,'projects');
    requestAnimationFrame(()=>{els.drawerBody.scrollTop=0;});
  }
  else if(btn.dataset.openDeliverable)openDeliverable(btn.dataset.openDeliverable);
  else if(btn.dataset.openAgent)openDrawer('agent',btn.dataset.openAgent,'people');
  else if(btn.dataset.openProject)openDrawer('project',btn.dataset.openProject,'projects');
  else if(btn.dataset.openTask)openDrawer('task',btn.dataset.openTask,'projects');
  else if(btn.dataset.openPanel){openDrawer(btn.dataset.openPanel,btn.dataset.openId||null);if(btn.dataset.openPanel==='work_report')loadWorkReport();}
  else if(btn.dataset.approval)decideApproval(btn.dataset.approval,btn.dataset.decision);
  else if(btn.dataset.programsLibraryChoice)decideProgramsLibraryFirst(btn.dataset.taskId,btn.dataset.programsLibraryChoice,btn.dataset.collectionId||null);
  else if(btn.dataset.taskStatus)updateTaskStatus(btn.dataset.taskStatus,btn.dataset.statusValue);
  else if(btn.dataset.planRevision)planRevision(btn.dataset.planRevision);
  else if(btn.hasAttribute('data-rescan-repository'))rescanRepository();
  else if(btn.dataset.memoryReview)reviewMemory(btn.dataset.memoryReview);
  else if(btn.dataset.memorySupersede){memorySupersedeId=Number(btn.dataset.memorySupersede);memoryEditingId=null;openDrawer('memory');}
  else if(btn.dataset.memoryEdit){memoryEditingId=Number(btn.dataset.memoryEdit);memorySupersedeId=null;openDrawer('memory');}
  else if(btn.hasAttribute('data-memory-edit-cancel')){memoryEditingId=null;memorySupersedeId=null;openDrawer('memory');}
  else if(btn.dataset.memoryCaptureKind)captureMemory(btn.dataset.memoryCaptureKind,btn.dataset.memoryCaptureId);
  else if(btn.dataset.memoryStatus)setMemoryStatus(btn.dataset.memoryStatus,btn.dataset.memoryStatusValue);
  else if(btn.dataset.playbookEdit){playbookEditingId=Number(btn.dataset.playbookEdit);openDrawer('playbooks');}
  else if(btn.hasAttribute('data-playbook-edit-cancel')){playbookEditingId=null;openDrawer('playbooks');}
  else if(btn.dataset.playbookStatus)setPlaybookStatus(btn.dataset.playbookStatus,btn.dataset.playbookStatusValue);
  else if(btn.dataset.libraryEdit){libraryEditingId=Number(btn.dataset.libraryEdit);openDrawer('library');}
  else if(btn.hasAttribute('data-library-edit-cancel')){libraryEditingId=null;openDrawer('library');}
  else if(btn.dataset.libraryStatus)setLibraryStatus(btn.dataset.libraryStatus,btn.dataset.libraryStatusValue);
  else if(btn.hasAttribute('data-weather-refresh'))refreshWeather();
  else if(btn.dataset.seasonalStatus)setSeasonalStatus(btn.dataset.seasonalStatus,btn.dataset.seasonalStatusValue);
  else if(btn.dataset.phenologyReview)reviewPhenology(btn.dataset.phenologyReview,btn.dataset.phenologyStatus);
  else if(btn.dataset.watchSuggest)post(`/api/environment/phenology/watchlist/${btn.dataset.watchSuggest}/suggest`,{}).then(()=>openDrawer('environment')).catch(err=>toast(err.message));
  else if(btn.dataset.watchStatus)post(`/api/environment/phenology/watchlist/${btn.dataset.watchStatus}/status`,{status:btn.dataset.watchStatusValue}).then(()=>openDrawer('environment')).catch(err=>toast(err.message));
  else if(btn.hasAttribute('data-generate-phenology-checks'))post('/api/environment/phenology/checks/generate',{}).then(()=>openDrawer('environment')).catch(err=>toast(err.message));
  else if(btn.dataset.checkDismiss)post(`/api/environment/phenology/checks/${btn.dataset.checkDismiss}/status`,{status:'dismissed'}).then(()=>openDrawer('environment')).catch(err=>toast(err.message));
  else if(btn.hasAttribute('data-save-briefing'))saveBriefingSnapshot();
  else if(btn.hasAttribute('data-work-report-reset')){workReportFilters={person_id:'',activity_category_id:'',project_id:'',participation_type:'',start_date:'',end_date:''};workReport=null;loadWorkReport();}
  else if(btn.dataset.grantImportSource)importGrantDiscovery(btn.dataset.grantImportSource);
  else if(btn.dataset.grantDiscoveryExample){const input=els.drawerBody.querySelector('[data-grant-discovery-form] input[name="keyword"]');if(input){input.value=btn.dataset.grantDiscoveryExample;input.focus();}}
  else if(btn.dataset.calendarEdit){calendarEditingId=Number(btn.dataset.calendarEdit);openDrawer('calendar');}
  else if(btn.hasAttribute('data-calendar-edit-cancel')){calendarEditingId=null;openDrawer('calendar');}
  else if(btn.dataset.grantEdit){grantEditingId=Number(btn.dataset.grantEdit);openDrawer('grants');}
  else if(btn.hasAttribute('data-grant-edit-cancel')){grantEditingId=null;openDrawer('grants');}
  else if(btn.dataset.personPrimary)setPrimaryPerson(btn.dataset.personPrimary);
  else if(btn.hasAttribute('data-poe-open-report'))openPoeReportResult();
  else if(btn.dataset.poeExample){const ta=els.drawerBody.querySelector('[data-poe-command-form] textarea[name="text"]');if(ta){ta.value=btn.dataset.poeExample;ta.focus();}}
  else if(btn.dataset.vernadetteExample){const ta=els.drawerBody.querySelector('[data-vernadette-command-form] textarea[name="text"]');if(ta){ta.value=btn.dataset.vernadetteExample;ta.focus();}}
  else if(btn.dataset.workClockOut)clockOutWork(btn.dataset.workClockOut);
  else if(btn.dataset.workEdit)correctWorkSession(btn.dataset.workEdit);
  else if(btn.dataset.retryProject)retryProject(btn.dataset.retryProject);
});
els.drawerBody.addEventListener('input',e=>{
  if(e.target.matches('[data-repository-search]')){
    repositoryQuery=e.target.value;
    const caret=e.target.selectionStart;
    openDrawer('repository');
    requestAnimationFrame(()=>{
      const input=els.drawerBody.querySelector('[data-repository-search]');
      if(input){input.focus({preventScroll:true});try{input.setSelectionRange(caret,caret);}catch{}}
    });
  }
  if(e.target.matches('[data-memory-search]')){
    memoryQuery=e.target.value;
    const caret=e.target.selectionStart;
    openDrawer('memory');
    requestAnimationFrame(()=>{
      const input=els.drawerBody.querySelector('[data-memory-search]');
      if(input){input.focus({preventScroll:true});try{input.setSelectionRange(caret,caret);}catch{}}
    });
  }
  if(e.target.matches('[data-library-search]')){
    libraryQuery=e.target.value;
    const caret=e.target.selectionStart;
    openDrawer('library');
    requestAnimationFrame(()=>{
      const input=els.drawerBody.querySelector('[data-library-search]');
      if(input){input.focus({preventScroll:true});try{input.setSelectionRange(caret,caret);}catch{}}
    });
  }
});
els.drawerBody.addEventListener('change',e=>{
  if(e.target.matches('[data-repository-kind]')){
    repositoryKind=e.target.value||'all';
    openDrawer('repository');
  }
  if(e.target.matches('[data-memory-type]')){memoryType=e.target.value||'all';openDrawer('memory');}
  if(e.target.matches('[data-memory-status-filter]')){memoryStatus=e.target.value||'Active';openDrawer('memory');}
  if(e.target.matches('[data-memory-review-filter]')){memoryReview=e.target.value||'all';openDrawer('memory');}
  if(e.target.matches('[data-playbook-status-filter]')){playbookStatus=e.target.value||'all';openDrawer('playbooks');}
  if(e.target.matches('[data-library-type]')){libraryType=e.target.value||'all';openDrawer('library');}
  if(e.target.matches('[data-library-status-filter]')){libraryStatus=e.target.value||'Active';openDrawer('library');}
});

els.drawerBody.addEventListener('submit',e=>{
  const form=e.target.closest('form');if(!form)return;e.preventDefault();
  if(form.hasAttribute('data-stella-daily-form')){sendStellaDaily(form);return;}
  if(form.hasAttribute('data-librarian-form')){askLibrarian(form);return;}
  if(form.hasAttribute('data-library-upload-form')){uploadLibraryInbox(form);return;}
  if(form.hasAttribute('data-library-catalog-form')){catalogLibraryInbox(form);return;}
  if(form.hasAttribute('data-memory-form')){saveMemory(form);return;}
  if(form.hasAttribute('data-playbook-form')){savePlaybook(form);return;}
  if(form.hasAttribute('data-library-form')){saveLibraryCollection(form);return;}
  if(form.hasAttribute('data-environment-settings-form')){saveEnvironmentSettings(form);return;}
  if(form.hasAttribute('data-weather-day-form')){saveWeatherDay(form);return;}
  if(form.hasAttribute('data-seasonal-window-form')){saveSeasonalWindow(form);return;}
  if(form.hasAttribute('data-phenology-form')){savePhenology(form);return;}
  if(form.hasAttribute('data-phenology-history-form')){loadPhenologyHistory(form);return;}
  if(form.hasAttribute('data-watchlist-form')){saveWatchlist(form);return;}
  if(form.hasAttribute('data-work-report-form')){loadWorkReport(readWorkReportFilters(form));return;}
  if(form.hasAttribute('data-poe-command-form')){sendPoeCommand(form);return;}
  if(form.hasAttribute('data-vernadette-command-form')){sendVernadetteCommand(form);return;}
  if(form.hasAttribute('data-grant-discovery-form')){searchGrantDiscovery(form);return;}
  if(form.hasAttribute('data-calendar-event-form')){saveCalendarEvent(form);return;}
  if(form.hasAttribute('data-grant-form')){saveGrant(form);return;}
  if(form.hasAttribute('data-person-form')){savePerson(form);return;}
  if(form.hasAttribute('data-clock-in-form')){clockInWork(form);return;}
  const body=form.elements.body?.value?.trim();if(!body){toast('Write a note first.');return;}
  if(form.dataset.noteProject)saveNote('project',form.dataset.noteProject,body);
  if(form.dataset.noteTask)saveNote('task',form.dataset.noteTask,body);
  form.reset();
});

try{setFocusWorkspace(localStorage.getItem('mavis-focus-workspace')==='1');}catch{setFocusWorkspace(false);}

function updateClock(){els.clock.textContent=new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});}updateClock();setInterval(updateClock,30000);
function connect(){
  const proto=location.protocol==='https:'?'wss':'ws';const ws=new WebSocket(`${proto}://${location.host}/ws`);
  ws.addEventListener('open',()=>{els.connection.classList.add('online');els.wsText.textContent='Live';ws.send('hello');});
  ws.addEventListener('message',e=>{const msg=JSON.parse(e.data);if(msg.type==='state'){state=msg.data;render();}});
  ws.addEventListener('close',()=>{els.connection.classList.remove('online');els.wsText.textContent='Reconnecting…';setTimeout(connect,1200);});
}
fetch('/api/state').then(r=>r.json()).then(s=>{state=s;render();startAmbientMovement();}).catch(()=>{startAmbientMovement();});refreshAiStatus();connect();
