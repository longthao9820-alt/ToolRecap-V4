from __future__ import annotations
from concurrent.futures import FIRST_COMPLETED,ThreadPoolExecutor,wait
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any,Sequence
from toolrecap_v4.analysis.evidence_store import EvidenceStore
from toolrecap_v4.analysis.finalizer.season_plan import SeasonPlan
from toolrecap_v4.analysis.finalizer.writer import WRITER_SYSTEM_PROMPT,WriterArtifact,WriterRunResult,assemble_writer_jobs,best_effort_extract,build_writer_prompt,verify_locked_plan_artifact,verify_visual_artifact
from toolrecap_v4.analysis.finalizer.writer_store import WriterStore
from toolrecap_v4.analysis.models import PreparedEpisode
from toolrecap_v4.analysis.scanner.prompts import measure_text_request_bytes
from toolrecap_v4.analysis.vision.models import VisualRunResult
from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.errors import CancelledError,GatewayError,PayloadContextError,WriterCapacityError,WriterTransportError
from toolrecap_v4.gateway import GatewayClient

@dataclass(frozen=True)
class WriterConfig:
    model:str;reasoning:str="";parallelism:int=3;max_request_bytes:int|None=None;max_response_bytes:int=10*1024*1024

class WriterService:
    def __init__(self,gateway:GatewayClient,root:Path|str,config:WriterConfig):self.gateway=gateway;self.root=Path(root);self.config=config
    def _run_one(self,job,store,token):
        cached=store.load(job)
        if cached:return cached,True
        recovered=store.load_received_raw(job)
        if recovered is not None:
            state,parsed=best_effort_extract(recovered);meta=json.loads((store.output_dir(job.output_id)/"manifest.json").read_text());return store.save(job,recovered,state,parsed,meta["request_bytes"],meta["measurement"],self.config.max_response_bytes,token),True
        if token:token.check_cancelled()
        prompt=build_writer_prompt(job);measured=measure_text_request_bytes(model=self.config.model,reasoning=self.config.reasoning,user_prompt=prompt,system_prompt=WRITER_SYSTEM_PROMPT)
        if self.config.max_request_bytes is not None and measured>self.config.max_request_bytes:raise WriterCapacityError(f"Complete Writer context for {job.output_id} exceeds configured capacity")
        try:r=self.gateway.submit_text_chat(prompt=prompt,model=self.config.model,system_prompt=WRITER_SYSTEM_PROMPT,reasoning_effort=self.config.reasoning or None,expect_json=False,cancellation_token=token,phase="output_writer")
        except PayloadContextError as exc:raise WriterCapacityError(f"Gateway rejected complete Writer context for {job.output_id}") from exc
        except CancelledError:raise
        except GatewayError as exc:raise WriterTransportError(f"Writer transport failed for {job.output_id}: {exc}") from exc
        measurement={"phase":"output_writer","output_id":job.output_id,"model":self.config.model,"reasoning":self.config.reasoning,"request_bytes":r.bytes_sent,"preflight_bytes":measured,"capacity_status":"UNKNOWN" if self.config.max_request_bytes is None else "FIT","evidence_count":len(job.context["authoritative_full_evidence"]),"visual_evidence_count":len(job.context["authoritative_visual_evidence"]),"episode_count":len(job.context["source_mapping"]),"attempt":0,"http_status":(r.metadata or {}).get("status_code"),"duration_ms":(r.metadata or {}).get("duration_ms")}
        store.save_received_raw(job,r.raw_response,r.bytes_sent,measurement,self.config.max_response_bytes)
        state,parsed=best_effort_extract(r.raw_response)
        return store.save(job,r.raw_response,state,parsed,r.bytes_sent,measurement,self.config.max_response_bytes,token),False
    def run(self,*,project_id:str,raw_prompt:str,language:str,plan:SeasonPlan,episodes:Sequence[PreparedEpisode],visual:VisualRunResult,cancellation_token:CancellationToken|None=None)->WriterRunResult:
        verify_locked_plan_artifact(self.root,plan);verify_visual_artifact(self.root,project_id,visual)
        jobs=assemble_writer_jobs(project_id=project_id,raw_prompt=raw_prompt,language=language,plan=plan,episodes=episodes,evidence_store=EvidenceStore(self.root,project_id),visual=visual,model=self.config.model,reasoning=self.config.reasoning);store=WriterStore(self.root,project_id,plan.plan_hash);artifacts={};failures={};reused=requested=0
        if not jobs:return WriterRunResult(plan.plan_hash,(),store.save_project_manifest(plan.plan_hash,[],{},{}),0,0)
        iterator=iter(jobs)
        with ThreadPoolExecutor(max_workers=self.config.parallelism,thread_name_prefix="writer") as pool:
            active={}
            for _ in range(min(self.config.parallelism,len(jobs))):j=next(iterator);active[pool.submit(self._run_one,j,store,cancellation_token)]=j
            while active:
                if cancellation_token:cancellation_token.check_cancelled()
                done,_=wait(active,return_when=FIRST_COMPLETED,timeout=.1)
                for f in done:
                    j=active.pop(f)
                    try:a,was_reused=f.result();artifacts[j.output_id]=a;reused+=int(was_reused);requested+=int(not was_reused)
                    except CancelledError:raise
                    except Exception as exc:failures[j.output_id]=str(exc)
                    try:n=next(iterator);active[pool.submit(self._run_one,n,store,cancellation_token)]=n
                    except StopIteration:pass
        manifest=store.save_project_manifest(plan.plan_hash,[j.output_id for j in jobs],artifacts,failures)
        if failures:raise WriterTransportError(f"Writer stage incomplete: {failures}")
        return WriterRunResult(plan.plan_hash,tuple(artifacts[j.output_id] for j in jobs),manifest,reused,requested)
