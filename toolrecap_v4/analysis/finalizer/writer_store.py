from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import uuid
from typing import Any
from toolrecap_v4.analysis.finalizer.writer import WriterArtifact,WriterJob
from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.errors import WriterPersistenceError
from toolrecap_v4.persistence import atomic_write_json

class WriterStore:
    def __init__(self,root:Path|str,project_id:str,plan_hash:str):self.base=Path(root)/"projects"/project_id/"writers"/plan_hash
    def output_dir(self,output_id):return self.base/output_id
    def load(self,job:WriterJob)->WriterArtifact|None:
        d=self.output_dir(job.output_id);m=d/"manifest.json";r=d/"raw_response.txt"
        if not m.is_file() or not r.is_file():return None
        try:
            meta=json.loads(m.read_text());rawb=r.read_bytes()
            if meta.get("status")!="RESPONSE_COMPLETE" or meta.get("dependency_digest")!=job.dependency_digest or meta.get("full_response") is not True or hashlib.sha256(rawb).hexdigest()!=meta.get("response_hash"):return None
            parsed=None;p=d/"writer_draft.json"
            if p.is_file():parsed=json.loads(p.read_text()).get("parsed_json")
            return WriterArtifact(job.output_id,job.dependency_digest,meta["response_hash"],rawb.decode(),meta["extraction_state"],parsed,meta["request_bytes"],meta["measurement"])
        except Exception:return None
    def load_received_raw(self,job:WriterJob)->str|None:
        d=self.output_dir(job.output_id);m=d/"manifest.json";r=d/"raw_response.txt"
        if not m.is_file() or not r.is_file():return None
        try:
            meta=json.loads(m.read_text());rawb=r.read_bytes()
            if meta.get("status")!="RECEIVED" or meta.get("dependency_digest")!=job.dependency_digest or meta.get("full_response") is not True or hashlib.sha256(rawb).hexdigest()!=meta.get("response_hash"):return None
            return rawb.decode()
        except Exception:return None
    def save_received_raw(self,job:WriterJob,raw:str,request_bytes:int,measurement:dict[str,Any],max_bytes:int):
        d=self.output_dir(job.output_id);d.mkdir(parents=True,exist_ok=True);encoded=raw.encode();stored=encoded[:max_bytes]
        if len(stored)!=len(encoded):
            (d/"diagnostic_response.txt").write_bytes(stored);atomic_write_json(d/"manifest.json",{"status":"DIAGNOSTIC_RESPONSE_TRUNCATED","dependency_digest":job.dependency_digest,"response_bytes":len(encoded),"stored_bytes":len(stored),"full_response":False});raise WriterPersistenceError(f"Writer response for {job.output_id} exceeds full-response storage cap")
        tmp=d/f"raw.tmp.{uuid.uuid4().hex}";tmp.write_bytes(encoded);os.replace(tmp,d/"raw_response.txt");digest=hashlib.sha256(encoded).hexdigest();atomic_write_json(d/"manifest.json",{"status":"RECEIVED","output_id":job.output_id,"dependency_digest":job.dependency_digest,"response_hash":digest,"response_bytes":len(encoded),"full_response":True,"request_bytes":request_bytes,"measurement":measurement})
    def save(self,job:WriterJob,raw:str,extraction_state:str,parsed:dict[str,Any]|None,request_bytes:int,measurement:dict[str,Any],max_bytes:int,cancellation_token:CancellationToken|None)->WriterArtifact:
        d=self.output_dir(job.output_id);d.mkdir(parents=True,exist_ok=True);encoded=raw.encode()
        if not (d/"raw_response.txt").is_file():self.save_received_raw(job,raw,request_bytes,measurement,max_bytes)
        if cancellation_token:cancellation_token.check_cancelled()
        atomic_write_json(d/"context_manifest.json",{"output_id":job.output_id,"request_id":job.request_id,"dependency_digest":job.dependency_digest,"context_hash":hashlib.sha256(json.dumps(job.context,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()})
        atomic_write_json(d/"writer_draft.json",{"output_id":job.output_id,"extraction_state":extraction_state,"parsed_json":parsed})
        digest=hashlib.sha256(encoded).hexdigest();atomic_write_json(d/"manifest.json",{"status":"RESPONSE_COMPLETE","output_id":job.output_id,"dependency_digest":job.dependency_digest,"response_hash":digest,"response_bytes":len(encoded),"full_response":True,"extraction_state":extraction_state,"request_bytes":request_bytes,"measurement":measurement})
        return WriterArtifact(job.output_id,job.dependency_digest,digest,raw,extraction_state,parsed,request_bytes,measurement)
    def save_project_manifest(self,plan_hash:str,output_ids:list[str],artifacts:dict[str,WriterArtifact],failures:dict[str,str]):
        data={"status":"COMPLETE" if len(artifacts)==len(output_ids) and not failures else "INCOMPLETE","season_plan_hash":plan_hash,"expected_output_count":len(output_ids),"ordered_output_ids":output_ids,"completed_response_count":len(artifacts),"pending_count":len(output_ids)-len(artifacts)-len(failures),"failed_count":len(failures),"canceled_count":0,"outputs":{oid:{"dependency_digest":artifacts[oid].dependency_digest,"response_hash":artifacts[oid].response_hash,"extraction_state":artifacts[oid].extraction_state} for oid in artifacts},"failures":failures}
        atomic_write_json(self.base/"manifest.json",data);return data
