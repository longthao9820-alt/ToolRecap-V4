from pathlib import Path
import threading

from toolrecap_v4.persistence import ProjectPersistence
from toolrecap_v4.ui.main_window import MainWindow
from toolrecap_v4.ui.settings_dialog import SettingsDialog


def _owned_toplevels(app: MainWindow) -> list[str]:
    result = []
    for child in app.tk.call("winfo", "children", "."):
        if str(app.tk.call("winfo", "class", child)).lower() == "toplevel":
            result.append(str(child))
    return result


def test_settings_is_embedded_and_navigation_keeps_one_toplevel(tmp_path: Path) -> None:
    app = MainWindow(persistence=ProjectPersistence(tmp_path))
    try:
        assert isinstance(app.settings_page, SettingsDialog)
        assert app.settings_page.winfo_toplevel() is app
        assert _owned_toplevels(app) == []
        for _ in range(20):
            for page in ("recap", "settings", "highlight", "settings", "recap"):
                app._show_page(page)
                app.update_idletasks()
                assert app.current_page == page
                assert _owned_toplevels(app) == []
        assert str(app.tk.call("grab", "current")) in {"", "()"}
    finally:
        app.destroy()


def test_page_state_and_settings_revert_are_preserved(tmp_path: Path) -> None:
    persistence = ProjectPersistence(tmp_path)
    app = MainWindow(persistence=persistence)
    try:
        app.highlight_prompt_text.delete("1.0", "end")
        app.highlight_prompt_text.insert("1.0", "find every worthwhile character moment")
        app._show_page("settings")
        app.settings_page.var_gw_endpoint.set("https://unsaved.example")
        app._show_page("highlight")
        assert app.highlight_prompt_text.get("1.0", "end-1c") == "find every worthwhile character moment"
        app._show_page("settings")
        assert app.settings_page.var_gw_endpoint.get() == "https://unsaved.example"
        app.settings_page._on_close()
        assert app.settings_page.var_gw_endpoint.get() == app.settings_manager.load().gateway_endpoint
        assert app.winfo_exists()
    finally:
        app.destroy()


def test_settings_validation_is_inline_and_async_queue_does_not_block_navigation(tmp_path: Path) -> None:
    app = MainWindow(persistence=ProjectPersistence(tmp_path))
    try:
        page = app.settings_page
        page.var_gw_endpoint.set("invalid://endpoint")
        page._on_save()
        assert page.lbl_status.cget("text").startswith("⚠")
        calls: list[str] = []
        worker = threading.Thread(target=lambda: page._post_ui(lambda: calls.append("done")))
        worker.start(); worker.join(timeout=1)
        assert calls == []
        app._show_page("highlight")
        assert app.current_page == "highlight"
        page._poll_ui_queue()
        assert calls == ["done"]
    finally:
        app.destroy()
