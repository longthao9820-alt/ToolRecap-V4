from __future__ import annotations
import json
from pathlib import Path
import pytest
import time
from toolrecap_v4.persistence import ProjectPersistence
from toolrecap_v4.settings import AppSettings,GatewayFormValues,GatewaySettingsController,SettingsManager
from toolrecap_v4.secrets import OPTIONAL_ENTROPY

class Secrets:
    def __init__(self,value=None):self.data={} if value is None else {"gateway_api_key":value}
    def get_secret(self,k):return self.data.get(k)
    def set_secret(self,k,v):self.data[k]=v
    def delete_secret(self,k):return self.data.pop(k,None) is not None
class Gateway:
    calls=[]
    def __init__(self,**kwargs):self.kwargs=kwargs
    def validate_model_availability(self,model):self.calls.append((self.kwargs,model));return True
def form(**changes):
    values=dict(endpoint=" https://router.example.net/custom ",api_key="fake-secret-123",scanner_model="scanner-route",scanner_reasoning="medium",scanner_parallelism=4,scanner_chunk_duration_ms=120000,vision_model="vision-route",vision_reasoning="low",finalizer_model="finalizer-route",finalizer_reasoning="high");values.update(changes);return GatewayFormValues(**values)

def test_settings_secure_roundtrip_and_unified_mapping(tmp_path):
    persistence=ProjectPersistence(storage_root=tmp_path);manager=SettingsManager(persistence=persistence);secrets=Secrets();controller=GatewaySettingsController(manager,secrets,Gateway)
    saved=controller.save(AppSettings(),form(),masked_placeholder="MASKED")
    loaded=manager.load();assert loaded.gateway_endpoint=="https://router.example.net/custom" and loaded.scanner_model=="scanner-route" and loaded.vision_model=="vision-route"
    assert loaded.scanner_parallelism==4 and loaded.scanner_chunk_duration_ms==120000
    assert loaded.finalizer_model=="finalizer-route" and {loaded.planner_model,loaded.writer_model,loaded.gateway_prime_model}=={"finalizer-route"}
    assert secrets.get_secret("gateway_api_key")=="fake-secret-123"
    assert "fake-secret-123" not in (tmp_path/"settings"/"settings.json").read_text()

def test_legacy_different_finalizer_stages_preserved_until_explicit_save(tmp_path):
    legacy={"gateway_endpoint":"http://legacy:20128","gateway_sub_model":"scan-old","planner_model":"plan-a","writer_model":"write-b","gateway_prime_model":"prime-c","planner_reasoning":"high","writer_reasoning":"low","original_audio_db":-3.0,"voice_id":"echo"}
    settings=AppSettings.from_dict(legacy);assert settings.finalizer_model=="" and settings.planner_model=="plan-a" and settings.writer_model=="write-b"
    controller=GatewaySettingsController(SettingsManager(storage_root=tmp_path),Secrets(),Gateway)
    preserved=controller.save(settings,form(finalizer_model="",finalizer_reasoning=""),masked_placeholder="MASKED")
    assert preserved.planner_model=="plan-a" and preserved.writer_model=="write-b" and preserved.voice_id=="echo" and preserved.original_audio_db==-3.0
    unified=controller.save(preserved,form(finalizer_model="unified",finalizer_reasoning="medium"),masked_placeholder="MASKED")
    assert {unified.planner_model,unified.writer_model,unified.gateway_prime_model,unified.finalizer_model}=={"unified"}

def test_diagnostics_use_unsaved_values_once_and_do_not_persist(tmp_path):
    Gateway.calls.clear();manager=SettingsManager(storage_root=tmp_path);manager.save(AppSettings(gateway_endpoint="http://saved:20128",scanner_model="saved-scan"));controller=GatewaySettingsController(manager,Secrets("saved-key"),Gateway)
    result=controller.test(form(endpoint="https://unsaved.example",api_key="unsaved-key",scanner_model="unsaved-scan"),"scanner",masked_placeholder="MASKED")
    assert result["ok"] and len(Gateway.calls)==1 and Gateway.calls[0][0]["base_url"]=="https://unsaved.example" and Gateway.calls[0][1]=="unsaved-scan"
    assert manager.load().gateway_endpoint=="http://saved:20128" and not list((tmp_path/"projects").glob("*.json"))

def test_diagnostic_failure_redacts_secret():
    class Failing(Gateway):
        def validate_model_availability(self,model):raise RuntimeError(f"Authorization Bearer {self.kwargs['api_key']} failed")
    result=GatewaySettingsController(type("M",(),{})(),Secrets(),Failing).test(form(),"finalizer",masked_placeholder="MASKED")
    assert not result["ok"] and "fake-secret-123" not in result["message"] and "[REDACTED]" in result["message"]

@pytest.mark.parametrize("changes",[{"scanner_parallelism":0},{"scanner_parallelism":33},{"scanner_chunk_duration_ms":999},{"scanner_chunk_duration_ms":3600001},{"endpoint":"ftp://bad"},{"scanner_reasoning":"provider-magic"}])
def test_validation_rejects_unsafe_values_without_mutation(tmp_path,changes):
    manager=SettingsManager(storage_root=tmp_path);original=AppSettings(gateway_endpoint="http://saved:20128");manager.save(original);controller=GatewaySettingsController(manager,Secrets("old"),Gateway)
    with pytest.raises(ValueError):controller.save(original,form(**changes),masked_placeholder="MASKED")
    assert manager.load().gateway_endpoint=="http://saved:20128" and controller.secret_store.get_secret("gateway_api_key")=="old"

def test_unknown_unrelated_settings_are_preserved(tmp_path):
    p=ProjectPersistence(storage_root=tmp_path);p.save_settings({"gateway_endpoint":"http://old:1","future_unrelated_field":{"x":1}});manager=SettingsManager(persistence=p);manager.save(AppSettings(gateway_endpoint="http://new:2"));raw=p.load_settings();assert raw["future_unrelated_field"]=={"x":1}

def test_dpapi_compatibility_constants_and_description_unchanged():
    import inspect,toolrecap_v4.secrets as module
    assert OPTIONAL_ENTROPY==b"ToolRecapV3_DPAPI_SecretStorage_v1" and '"ToolRecapV3_Secret"' in inspect.getsource(module.dpapi_encrypt)

def test_failed_settings_persistence_rolls_back_secret():
    class BadManager:
        def save(self,settings):raise OSError("disk full")
    secrets=Secrets("old-key");controller=GatewaySettingsController(BadManager(),secrets,Gateway)
    with pytest.raises(OSError):controller.save(AppSettings(),form(api_key="new-key"),masked_placeholder="MASKED")
    assert secrets.get_secret("gateway_api_key")=="old-key"

def test_dialog_cancel_and_background_unsaved_test_values(tmp_path):
    from toolrecap_v4.ui.main_window import MainWindow
    from toolrecap_v4.ui.settings_dialog import SettingsDialog
    persistence=ProjectPersistence(storage_root=tmp_path);SettingsManager(persistence=persistence).save(AppSettings(gateway_endpoint="http://saved:20128",scanner_model="saved-model"));app=MainWindow(persistence=persistence)
    try:
        dialog=SettingsDialog(app,persistence=persistence,initial_tab="tab_gw");dialog.update_idletasks()
        assert hasattr(dialog,"scanner_parallelism_spin") and hasattr(dialog,"scanner_chunk_spin") and hasattr(dialog,"vision_model_entry")
        captured=[]
        class Controller:
            def test(self,form_value,role,**kwargs):captured.append((form_value,role));time.sleep(.05);return {"ok":True,"message":"Connection successful"}
        dialog.gateway_controller=Controller();dialog.var_gw_endpoint.set("https://unsaved.example");dialog.var_gw_sub_model.set("unsaved-model")
        started=time.monotonic();dialog._test_sub_connection();assert time.monotonic()-started<.2 and str(dialog.btn_test_sub.cget("state"))=="disabled"
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and dialog._gateway_test_running["scanner"]:app.update();time.sleep(.01)
        assert captured[0][0].endpoint=="https://unsaved.example" and captured[0][0].scanner_model=="unsaved-model"
        dialog.destroy();loaded=SettingsManager(persistence=persistence).load();assert loaded.gateway_endpoint=="http://saved:20128" and loaded.scanner_model=="saved-model"
    finally:app.destroy()

def test_dialog_save_error_redacts_form_secret(tmp_path):
    from unittest.mock import patch
    from toolrecap_v4.ui.main_window import MainWindow
    from toolrecap_v4.ui.settings_dialog import SettingsDialog
    persistence=ProjectPersistence(storage_root=tmp_path);app=MainWindow(persistence=persistence)
    try:
        dialog=SettingsDialog(app,persistence=persistence);dialog.var_gw_key.set("save-secret-xyz");dialog.var_gw_sub_model.set("scan");dialog.var_gw_prime_model.set("final")
        dialog.gateway_controller.save=lambda *a,**k:(_ for _ in ()).throw(RuntimeError("failed with save-secret-xyz"))
        with patch("toolrecap_v4.ui.settings_dialog.messagebox.showerror") as shown:dialog._on_save()
        assert shown.called and "save-secret-xyz" not in shown.call_args.args[1] and "[REDACTED]" in shown.call_args.args[1]
        dialog.destroy()
    finally:app.destroy()
