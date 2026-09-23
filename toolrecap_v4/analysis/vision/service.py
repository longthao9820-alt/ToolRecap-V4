from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from pathlib import Path
from typing import Any,Sequence
from toolrecap_v4.analysis.evidence_store import EvidenceStore
from toolrecap_v4.analysis.finalizer.catalog import catalog_detail_hash
from toolrecap_v4.analysis.finalizer.planner import PlannerDraft
from toolrecap_v4.analysis.models import PreparedEpisode
from toolrecap_v4.analysis.vision.frames import FRAME_POLICY_VERSION,FrameExtractionPolicy,FrameExtractor,build_visual_requests
from toolrecap_v4.analysis.vision.models import VisualEvidence,VisualRunResult
from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.errors import VisionRepairExhaustedError,VisionValidationError,VisualStoreError
from toolrecap_v4.gateway import GatewayClient
from toolrecap_v4.persistence import atomic_write_json

VISION_PROTOCOL_VERSION="visual-evidence-v1"; VISION_PROMPT_VERSION="factual-scene-vision-v1"; VISION_VALIDATION_VERSION="visual-validation-v1"
@dataclass(frozen=True)
class VisionConfig:
    model:str; reasoning:str=""; repair_attempts:int=1; frame_policy:FrameExtractionPolicy=FrameExtractionPolicy()

def _digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

class VisualEvidenceService:
    def __init__(self,gateway:GatewayClient,root:Path|str,config:VisionConfig,extractor:FrameExtractor|None=None):
        self.gateway=gateway; self.root=Path(root); self.config=config; self.extractor=extractor or FrameExtractor(root,config.frame_policy)
    def run(self,*,project_id:str,draft:PlannerDraft,planner_draft_hash:str,episodes:Sequence[PreparedEpisode],evidence_revision:str,cancellation_token:CancellationToken|None=None)->VisualRunResult:
        requests=build_visual_requests(project_id,draft,episodes)
        deps={"project_id":project_id,"planner_draft_hash":planner_draft_hash,"requests":[r.to_dict() for r in requests],"policy":FRAME_POLICY_VERSION,"vision_model":self.config.model,"vision_reasoning":self.config.reasoning,"prompt":VISION_PROMPT_VERSION,"schema":VISION_PROTOCOL_VERSION,"validation":VISION_VALIDATION_VERSION,"evidence_revision":evidence_revision}
        revision=f"vis-{_digest(deps)[:24]}"; base=self.root/"projects"/project_id/"visual"/revision; manifest=base/"manifest.json"
        if manifest.is_file():
            try:
                m=json.loads(manifest.read_text()); data=json.loads((base/"visual_evidence.json").read_text())
                if m.get("status")=="COMPLETE" and m.get("dependency_digest")==_digest(deps) and _digest(data)==m.get("data_hash"):
                    ev=tuple(self._from_dict(x) for x in data["evidence"]); return VisualRunResult(revision,requests,ev,data["completeness"],len(requests),0)
            except Exception:pass
        base.mkdir(parents=True,exist_ok=True)
        if not requests:
            data={"visual_revision":revision,"requests":[],"evidence":[],"completeness":{"expected":0,"completed":0,"failed":0,"canceled":0,"selected_frame_count":0,"visual_evidence_count":0,"complete":True}}
            atomic_write_json(base/"visual_evidence.json",data); atomic_write_json(manifest,{"status":"COMPLETE","dependency_digest":_digest(deps),"data_hash":_digest(data)})
            return VisualRunResult(revision,(),(),data["completeness"],0,0)
        store=EvidenceStore(self.root,project_id); all_ev=[]; offsets={}; req_counts={}
        for r in requests:req_counts[r.episode_id]=req_counts.get(r.episode_id,0)+1
        for req_index,req in enumerate(requests,1):
            if cancellation_token:cancellation_token.check_cancelled()
            per=max(1,min(self.config.frame_policy.frames_per_range,self.config.frame_policy.frames_per_episode//req_counts[req.episode_id]))
            offset=offsets.get(req.episode_id,0); frames=self.extractor.extract(req,offset,per,cancellation_token); offsets[req.episode_id]=offset+len(frames)
            nearby=store.query_range(req.episode_id,req.start_ms,req.end_ms,evidence_revision).items
            context=[{"evidence_id":e.evidence_id,"observation":e.observation,"detail_hash":catalog_detail_hash(e)} for e in nearby]
            prompt=json.dumps({"protocol_version":VISION_PROTOCOL_VERSION,"task":"Report only factual visible observations from these selected still frames.","visual_request":req.to_dict(),"frames":[{"frame_id":f.frame_id,"timestamp_ms":f.timestamp_ms} for f in frames],"nearby_factual_evidence":context,"identity_rule":"Name a person only when nearby factual evidence grounds identity; otherwise preserve ambiguity.","purpose_question":req.purpose},ensure_ascii=False,separators=(",",":"))
            raw=""; parsed=None; errors=[]; valid=False
            raw_path=base/f"{req.visual_request_id}.raw.txt"
            if raw_path.is_file():
                try: raw=raw_path.read_text(encoding="utf-8");parsed=json.loads(raw);self._validate(parsed,req,frames);valid=True
                except Exception: parsed=None
            for attempt in range(self.config.repair_attempts+1) if not valid else ():
                result=self.gateway.submit_image_chat(prompt=prompt,images=[f.path for f in frames],model=self.config.model,system_prompt="Extract factual visual observations only. No ranking, narration, motives, or off-screen invention.",reasoning_effort=self.config.reasoning or None,expect_json=False,cancellation_token=cancellation_token,phase="visual_evidence")
                raw=result.raw_response; raw_path.write_text(raw[:2*1024*1024],encoding="utf-8")
                try: parsed=json.loads(raw); self._validate(parsed,req,frames); valid=True; break
                except Exception as exc: errors.append(str(exc)); prompt=json.dumps({"task":"Correct only technical JSON defects.","errors":errors,"original_request":json.loads(prompt),"invalid_response":raw[:65536]},ensure_ascii=False)
            if not valid: raise VisionRepairExhaustedError(f"Vision repair exhausted for {req.visual_request_id}")
            all_ev.append(VisualEvidence(f"{req.episode_id}-VIS-{sum(1 for e in all_ev if e.episode_id==req.episode_id)+1:03d}",project_id,req.episode_id,req.source_id,req.visual_request_id,req.start_ms,req.end_ms,tuple(f.frame_id for f in frames),tuple(f.timestamp_ms for f in frames),parsed["range_observation"],tuple(parsed.get("entities",[])),tuple(parsed.get("objects",[])),tuple(parsed.get("on_screen_text",[])),tuple(parsed.get("uncertainty",[])),req.related_evidence_ids,{"vision_model":self.config.model,"protocol":VISION_PROTOCOL_VERSION,"frame_hashes":[f.content_hash for f in frames],"response_hash":hashlib.sha256(raw.encode()).hexdigest()}))
        comp={"expected":len(requests),"completed":len(all_ev),"failed":0,"canceled":0,"selected_frame_count":sum(len(e.frame_ids) for e in all_ev),"visual_evidence_count":len(all_ev),"request_ids":[r.visual_request_id for r in requests],"visual_evidence_ids":[e.visual_evidence_id for e in all_ev],"complete":True}
        data={"visual_revision":revision,"requests":[r.to_dict() for r in requests],"evidence":[e.to_dict() for e in all_ev],"completeness":comp}; atomic_write_json(base/"visual_evidence.json",data); atomic_write_json(manifest,{"status":"COMPLETE","dependency_digest":_digest(deps),"data_hash":_digest(data)})
        return VisualRunResult(revision,requests,tuple(all_ev),comp,0,len(requests))
    def _validate(self,d,req,frames):
        if not isinstance(d,dict) or d.get("protocol_version")!=VISION_PROTOCOL_VERSION or d.get("visual_request_id")!=req.visual_request_id:raise VisionValidationError("Vision identity/protocol mismatch")
        known={f.frame_id:f.timestamp_ms for f in frames}; rows=d.get("frames")
        if not isinstance(rows,list) or not isinstance(d.get("range_observation"),str) or not d["range_observation"].strip():raise VisionValidationError("Malformed Vision response")
        for row in rows:
            if not isinstance(row,dict) or row.get("frame_id") not in known or type(row.get("timestamp_ms")) is not int or row["timestamp_ms"]!=known[row["frame_id"]]:raise VisionValidationError("Unknown frame or timestamp")
        for key in ("entities","objects","on_screen_text","uncertainty"):
            if not isinstance(d.get(key,[]),list) or not all(isinstance(x,str) for x in d.get(key,[])):raise VisionValidationError("Invalid Vision arrays")
    def _from_dict(self,d):return VisualEvidence(d["visual_evidence_id"],d["project_id"],d["episode_id"],d["source_id"],d["visual_request_id"],d["start_ms"],d["end_ms"],tuple(d["frame_ids"]),tuple(d["frame_timestamps_ms"]),d["observation"],tuple(d["entities"]),tuple(d["objects"]),tuple(d["on_screen_text"]),tuple(d["uncertainty"]),tuple(d["related_evidence_ids"]),d["provenance"])
