from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from pathlib import Path
from typing import Any
from toolrecap_v4.analysis.evidence_store import EvidenceStore
from toolrecap_v4.analysis.finalizer.catalog import SeasonEvidenceCatalog
from toolrecap_v4.analysis.finalizer.packing import pack_catalog
from toolrecap_v4.analysis.finalizer.planner import PlannerDraft
from toolrecap_v4.analysis.vision.models import VisualRunResult
from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.errors import FinalPlannerValidationError,SeasonPlanLockError
from toolrecap_v4.gateway import GatewayClient
from toolrecap_v4.persistence import atomic_write_json

FINAL_PLAN_PROTOCOL="final-season-plan-draft-v1"; SEASON_PLAN_VERSION="season-plan-v1"; FINAL_PROMPT_VERSION="final-planner-refinement-v1"
def _digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True)
class SeasonPlan:
    plan_version:str; plan_hash:str; project_id:str; recap_prompt_hash:str; catalog_hash:str; evidence_revision:str; visual_revision:str; planner_draft_hash:str; final_planner_response_hash:str; outputs:tuple[dict[str,Any],...]
    def semantic_dict(self):return {"plan_version":self.plan_version,"project_id":self.project_id,"recap_prompt_hash":self.recap_prompt_hash,"catalog_hash":self.catalog_hash,"evidence_revision":self.evidence_revision,"visual_revision":self.visual_revision,"planner_draft_hash":self.planner_draft_hash,"final_planner_response_hash":self.final_planner_response_hash,"outputs":list(self.outputs)}
    def to_dict(self):v=self.semantic_dict();v["plan_hash"]=self.plan_hash;return v
@dataclass(frozen=True)
class SeasonPlanResult: plan:SeasonPlan; path:Path; reused:bool

class SeasonPlanService:
    def __init__(self,gateway:GatewayClient,root:Path|str,model:str,reasoning:str=""):self.gateway=gateway;self.root=Path(root);self.model=model;self.reasoning=reasoning
    def run(self,*,project_id:str,raw_recap_prompt:str,catalog:SeasonEvidenceCatalog,draft:PlannerDraft,visual:VisualRunResult,cancellation_token:CancellationToken|None=None)->SeasonPlanResult:
        if not visual.completeness.get("complete") or visual.completeness.get("failed") or visual.completeness.get("canceled"):raise SeasonPlanLockError("Visual requests are not technically complete.")
        draft_hash=_digest(draft.to_dict()); deps={"project_id":project_id,"prompt_hash":hashlib.sha256(raw_recap_prompt.encode()).hexdigest(),"catalog_hash":catalog.catalog_hash,"evidence_revision":catalog.evidence_revision,"visual_revision":visual.visual_revision,"planner_draft_hash":draft_hash,"model":self.model,"reasoning":self.reasoning,"protocol":FINAL_PLAN_PROTOCOL,"prompt":FINAL_PROMPT_VERSION}
        revision=f"plan-{_digest(deps)[:24]}"; base=self.root/"projects"/project_id/"plans"/revision; plan_path=base/"season_plan.json"; manifest=base/"manifest.json"
        if plan_path.is_file() and manifest.is_file():
            try:
                p=json.loads(plan_path.read_text());m=json.loads(manifest.read_text())
                if m.get("status")=="LOCKED" and m.get("dependency_digest")==_digest(deps) and _digest(p)==m.get("artifact_hash"):return SeasonPlanResult(self._from_dict(p),plan_path,True)
            except Exception:pass
        store=EvidenceStore(self.root,project_id); full=[]
        ids=[]
        for out in draft.proposed_outputs:
            ids.extend((*out.evidence_ids,*out.supporting_evidence_ids))
        for eid in dict.fromkeys(ids):
            e=store.get(eid,catalog.evidence_revision)
            if e is None:raise FinalPlannerValidationError(f"Unknown Evidence ID {eid}")
            full.append(e.to_dict())
        payload={"protocol_version":FINAL_PLAN_PROTOCOL,"project_id":project_id,"raw_recap_prompt":raw_recap_prompt,"catalog":pack_catalog(catalog),"catalog_hash":catalog.catalog_hash,"evidence_revision":catalog.evidence_revision,"planner_draft":draft.to_dict(),"authoritative_full_evidence":full,"visual_revision":visual.visual_revision,"visual_evidence":[e.to_dict() for e in visual.evidence],"visual_completeness":visual.completeness,"instruction":"Return ordered final output concepts only. Do not assign out_### IDs, narration, clips, or Final JSON."}
        result=self.gateway.submit_text_chat(prompt=json.dumps(payload,ensure_ascii=False,separators=(",",":")),model=self.model,system_prompt="Refine the season plan using complete season context and validated visual evidence. Preserve AI output order.",reasoning_effort=self.reasoning or None,expect_json=False,cancellation_token=cancellation_token,phase="final_planner_refinement")
        try: raw=json.loads(result.raw_response)
        except Exception as exc:raise FinalPlannerValidationError("Malformed final Planner JSON") from exc
        outputs=self._validate(raw,project_id,catalog,visual)
        canonical=[]
        for i,o in enumerate(outputs,1):canonical.append({"output_id":f"out_{i:03d}",**o})
        response_hash=hashlib.sha256(result.raw_response.encode()).hexdigest(); unhashed=SeasonPlan(SEASON_PLAN_VERSION,"pending",project_id,deps["prompt_hash"],catalog.catalog_hash,catalog.evidence_revision,visual.visual_revision,draft_hash,response_hash,tuple(canonical)); plan=SeasonPlan(**{**unhashed.__dict__,"plan_hash":_digest(unhashed.semantic_dict())})
        if cancellation_token:cancellation_token.check_cancelled()
        base.mkdir(parents=True,exist_ok=True);atomic_write_json(manifest,{"status":"BUILDING","dependency_digest":_digest(deps)});atomic_write_json(plan_path,plan.to_dict());atomic_write_json(manifest,{"status":"LOCKED","dependency_digest":_digest(deps),"artifact_hash":_digest(plan.to_dict()),"plan_hash":plan.plan_hash});return SeasonPlanResult(plan,plan_path,False)
    def _validate(self,d,project_id,catalog,visual):
        required={"protocol_version","action","project_id","catalog_hash","evidence_revision","visual_revision","outputs"}
        if not isinstance(d,dict) or set(d)!=required or d.get("protocol_version")!=FINAL_PLAN_PROTOCOL or d.get("action")!="FINAL_SEASON_PLAN_DRAFT" or d.get("project_id")!=project_id or d.get("catalog_hash")!=catalog.catalog_hash or d.get("evidence_revision")!=catalog.evidence_revision or d.get("visual_revision")!=visual.visual_revision or not isinstance(d.get("outputs"),list):raise FinalPlannerValidationError("Final Planner identity/schema mismatch")
        valid_e={i.evidence_id for i in catalog.items};valid_v={i.visual_evidence_id for i in visual.evidence};eps={e.episode_id:e for e in catalog.ordered_episodes};refs=set();out=[];fields={"planner_ref","title_concept","editorial_thesis","story_arc","episode_ids","evidence_ids","visual_evidence_ids","source_ranges","uncertainty","writer_brief"}
        for item in d["outputs"]:
            if not isinstance(item,dict) or set(item)!=fields or "output_id" in item:raise FinalPlannerValidationError("Invalid final output schema")
            if item["planner_ref"] in refs:raise FinalPlannerValidationError("Duplicate planner_ref")
            refs.add(item["planner_ref"])
            if not all(isinstance(item.get(k),list) for k in ("episode_ids","evidence_ids","visual_evidence_ids","source_ranges","uncertainty")) or not isinstance(item.get("writer_brief"),dict):raise FinalPlannerValidationError("Invalid output collections")
            if any(x not in eps for x in item["episode_ids"]) or any(x not in valid_e for x in item["evidence_ids"]) or any(x not in valid_v for x in item["visual_evidence_ids"]):raise FinalPlannerValidationError("Unknown final plan reference")
            for r in item["source_ranges"]:
                ep=eps.get(r.get("episode_id")) if isinstance(r,dict) else None
                if ep is None or type(r.get("start_ms")) is not int or type(r.get("end_ms")) is not int or r["start_ms"]<0 or r["end_ms"]<=r["start_ms"] or r["end_ms"]>ep.duration_ms:raise FinalPlannerValidationError("Invalid final source range")
            out.append(item)
        return out
    def _from_dict(self,d):return SeasonPlan(d["plan_version"],d["plan_hash"],d["project_id"],d["recap_prompt_hash"],d["catalog_hash"],d["evidence_revision"],d["visual_revision"],d["planner_draft_hash"],d["final_planner_response_hash"],tuple(d["outputs"]))
