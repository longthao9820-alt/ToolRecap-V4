from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from pathlib import Path
from typing import Any,Sequence
from toolrecap_v4.analysis.evidence_store import EvidenceStore
from toolrecap_v4.analysis.finalizer.finalization import MAPPING_VERSION,REPAIR_PROTOCOL_VERSION,VALIDATOR_VERSION,FinalizationResult,OutputValidator,_digest,map_final_json
from toolrecap_v4.analysis.finalizer.season_plan import SeasonPlan
from toolrecap_v4.analysis.finalizer.writer import WRITER_SYSTEM_PROMPT,assemble_writer_jobs,verify_locked_plan_artifact,verify_visual_artifact
from toolrecap_v4.analysis.finalizer.writer_store import WriterStore
from toolrecap_v4.analysis.models import PreparedEpisode
from toolrecap_v4.analysis.scanner.prompts import measure_text_request_bytes
from toolrecap_v4.analysis.vision.models import VisualRunResult
from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.errors import CancelledError,FinalJsonPersistenceError,FinalJsonValidationError,PayloadContextError,WriterCapacityError,WriterRepairExhaustedError,WriterValidationError,ZeroOutputError
from toolrecap_v4.gateway import GatewayClient
from toolrecap_v4.persistence import ProjectPersistence,atomic_write_json
from toolrecap_v4.validator import validate_project

@dataclass(frozen=True)
class FinalizationConfig:
    repair_model:str;repair_reasoning:str="";repair_attempts:int=2;max_request_bytes:int|None=None;max_response_bytes:int=10*1024*1024

class FinalizationService:
    def __init__(self,gateway:GatewayClient,root:Path|str,config:FinalizationConfig):self.gateway=gateway;self.root=Path(root);self.config=config
    def run(self,*,project_id:str,project_name:str,raw_prompt:str,language:str,plan:SeasonPlan,episodes:Sequence[PreparedEpisode],visual:VisualRunResult,cancellation_token:CancellationToken|None=None)->FinalizationResult:
        if not plan.outputs:raise ZeroOutputError("Schema 3.0 canonical validator rejects empty outputs; zero-output plan remains an explicit terminal state and no content is fabricated.")
        verify_locked_plan_artifact(self.root,plan);verify_visual_artifact(self.root,project_id,visual)
        jobs=assemble_writer_jobs(project_id=project_id,raw_prompt=raw_prompt,language=language,plan=plan,episodes=episodes,evidence_store=EvidenceStore(self.root,project_id),visual=visual,model=self.config.repair_model,reasoning=self.config.repair_reasoning)
        writer_store=WriterStore(self.root,project_id,plan.plan_hash);artifacts=[]
        for job in jobs:
            a=writer_store.load(job)
            if a is None:raise WriterValidationError("Missing/corrupt Phase 8 Writer artifact",output_id=job.output_id,issue_codes=("WRITER_ARTIFACT_MISSING",))
            artifacts.append(a)
        deps={"project_id":project_id,"plan_hash":plan.plan_hash,"writer_hashes":[a.response_hash for a in artifacts],"validator":VALIDATOR_VERSION,"mapping":MAPPING_VERSION,"schema":"3.0","repair_model":self.config.repair_model,"repair_reasoning":self.config.repair_reasoning,"repair_protocol":REPAIR_PROTOCOL_VERSION}
        dependency_digest=_digest(deps);root=self.root/"projects"/project_id/"finalization";pointer=root/f"active-{dependency_digest[:24]}.json"
        if pointer.is_file():
            try:
                active=json.loads(pointer.read_text());revision=active["revision"];base=root/revision;final_path=base/"final.json";manifest=base/"manifest.json";data=json.loads(final_path.read_text());m=json.loads(manifest.read_text());validate_project(data,{e.source_basename or e.source_path.name:e.duration_ms for e in episodes})
                if m.get("status")=="COMPLETE" and m.get("dependency_digest")==dependency_digest and m.get("artifact_hash")==_digest(data) and m.get("revision")==revision and active.get("artifact_hash")==m.get("artifact_hash"):
                    ProjectPersistence(self.root).save_final_json(project_id,data);return FinalizationResult(data,revision,m["artifact_hash"],tuple(),tuple(),True)
            except Exception:pass
        work_base=root/f"s-{dependency_digest[:12]}"
        validator=OutputValidator(project_id=project_id,plan=plan,episodes=episodes,visual=visual,evidence_store=EvidenceStore(self.root,project_id));results=[];repaired=[]
        for job,artifact in zip(jobs,artifacts):
            if cancellation_token:cancellation_token.check_cancelled()
            result=validator.validate(job,artifact.raw_response)
            if result.state!="VALID":result=self._repair(job,artifact,result,validator,work_base,cancellation_token);repaired.append(job.output_id)
            results.append(result);self._save_validated(work_base,artifact,result)
        final=map_final_json(project_id=project_id,project_name=project_name,episodes=episodes,plan=plan,validated=results)
        try:validate_project(final,{e.source_basename or e.source_path.name:e.duration_ms for e in episodes},cancellation_token)
        except Exception as exc:raise FinalJsonValidationError(f"Merged schema 3.0 Final JSON is invalid: {exc}") from exc
        if cancellation_token:cancellation_token.check_cancelled()
        final_dependencies={**deps,"ordered_validated_output_hashes":[_digest(r.normalized) for r in results]};revision=f"final-{_digest(final_dependencies)[:24]}";base=root/revision;final_path=base/"final.json";manifest=base/"manifest.json"
        base.mkdir(parents=True,exist_ok=True);atomic_write_json(manifest,{"status":"BUILDING","dependency_digest":dependency_digest});atomic_write_json(final_path,final);artifact_hash=_digest(final);atomic_write_json(manifest,{"status":"COMPLETE","dependency_digest":dependency_digest,"semantic_dependencies":final_dependencies,"artifact_hash":artifact_hash,"revision":revision,"validated_output_ids":[r.output_id for r in results]});atomic_write_json(pointer,{"status":"COMPLETE","dependency_digest":dependency_digest,"revision":revision,"artifact_hash":artifact_hash})
        ProjectPersistence(self.root).save_final_json(project_id,final)
        return FinalizationResult(final,revision,artifact_hash,tuple(results),tuple(repaired),False)
    def _repair(self,job,artifact,validation,validator,base,token):
        issue_digest=_digest(list(validation.issues));directory=base/job.output_id/f"r-{issue_digest[:8]}";directory.mkdir(parents=True,exist_ok=True)
        for attempt in range(1,self.config.repair_attempts+1):
            raw_path=directory/f"attempt-{attempt:02d}.raw.txt";raw=None
            if raw_path.is_file():raw=raw_path.read_text(encoding="utf-8")
            else:
                prompt=json.dumps({"repair_protocol":REPAIR_PROTOCOL_VERSION,"task":"Repair only this assigned output's technical validation defects. Do not add/remove/reorder outputs, change output_id, replan, or replace the story.","output_id":job.output_id,"season_plan_hash":job.context["season_plan_hash"],"raw_recap_prompt":job.context["raw_recap_prompt"],"locked_plan_entry":job.context["locked_plan_entry"],"original_writer_response":artifact.raw_response,"validation_issue_codes":list(validation.issues),"authoritative_full_evidence":job.context["authoritative_full_evidence"],"authoritative_visual_evidence":job.context["authoritative_visual_evidence"],"source_mapping":job.context["source_mapping"],"required_writer_contract":job.context["contract"]},ensure_ascii=False,sort_keys=True,separators=(",",":"))
                size=measure_text_request_bytes(model=self.config.repair_model,reasoning=self.config.repair_reasoning,user_prompt=prompt,system_prompt=WRITER_SYSTEM_PROMPT)
                if self.config.max_request_bytes is not None and size>self.config.max_request_bytes:raise WriterCapacityError("Complete repair context exceeds configured capacity")
                try:r=self.gateway.submit_text_chat(prompt=prompt,model=self.config.repair_model,system_prompt="Repair only deterministic technical defects for the assigned output. Preserve locked scope and identity.",reasoning_effort=self.config.repair_reasoning or None,expect_json=False,cancellation_token=token,phase="writer_repair")
                except PayloadContextError as exc:raise WriterCapacityError("Gateway rejected complete repair context") from exc
                raw=r.raw_response;encoded=raw.encode()
                if len(encoded)>self.config.max_response_bytes:raise WriterRepairExhaustedError("Repair response exceeds full-response storage limit")
                raw_path.write_bytes(encoded);atomic_write_json(directory/f"attempt-{attempt:02d}.manifest.json",{"status":"RECEIVED","response_hash":hashlib.sha256(encoded).hexdigest(),"attempt":attempt,"issue_digest":issue_digest,"original_response_hash":artifact.response_hash})
            repaired=validator.validate(job,raw)
            atomic_write_json(directory/f"attempt-{attempt:02d}.result.json",{"state":repaired.state,"issues":list(repaired.issues),"validated_output_hash":_digest(repaired.normalized) if repaired.normalized else None})
            if repaired.state=="VALID":return repaired
            validation=repaired
        raise WriterRepairExhaustedError(f"Repair exhausted for {job.output_id}")
    def _save_validated(self,base,artifact,result):
        d=base/"outputs"/result.output_id;d.mkdir(parents=True,exist_ok=True);atomic_write_json(d/"validated_output.json",{"status":"VALID","output_id":result.output_id,"original_response_hash":artifact.response_hash,"validated_output_hash":_digest(result.normalized),"validator_version":VALIDATOR_VERSION,"output":result.normalized})
