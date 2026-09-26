# ToolRecap V4

ToolRecap V4 is a portable Windows desktop application for producing source-grounded video content in two modes:

- **Recap Mode** — factual analysis, editorial planning, VoiceStudio narration, original-source audio, subtitle tracks, and rendered recap videos.
- **Highlight Mode** — original video scenes with original source audio and remapped original-dialogue subtitles, without generated narration.

The application includes saved-project resume, AI Gateway integration, single-window Recap/Highlight/Settings navigation, fixed commentary reading speed, narration-fit processing, and NVIDIA-accelerated video rendering where supported.

## Install the portable release

1. Open the repository's **Releases** page.
2. Download `ToolRecapV4-Windows-x64-v1.0.2.zip` from the latest release.
3. Extract the entire ZIP to a writable local folder.
4. Keep the complete extracted `ToolRecapV4` folder together.
5. Run `ToolRecapV4.exe` from that folder.
6. Open **Settings** and configure the required AI Gateway models/credentials. Configure VoiceStudio when using Recap narration.
7. Choose **Recap** or **Highlight**, select source media, enter the corresponding prompt, and start the workflow.

No separate Python installation is required for normal portable use. FFmpeg, FFprobe, the Python runtime, and required application libraries are included in the one-folder package.

## Windows and hardware requirements

- 64-bit Windows 10 or Windows 11.
- Sufficient local storage for source preparation, caches, temporary render files, and published video.
- Network access to any configured AI Gateway or remote VoiceStudio service.
- NVIDIA acceleration requires a compatible NVIDIA GPU and current NVIDIA driver.
- The full CUDA Toolkit is **not** required or bundled.

ToolRecap can use CPU rendering when GPU acceleration is deliberately disabled. If NVIDIA mode is selected, NVENC initialization failures are reported explicitly.

## Portable state and privacy

The portable application folder contains only application runtime files. User settings, encrypted credentials, project checkpoints, caches, and update staging data are stored separately under:

```text
%LOCALAPPDATA%\ToolRecapV4\
```

API credentials are stored with Windows DPAPI and are not included in release packages. Copying the portable folder to another computer does not transfer user credentials or projects.

## Self-check

The frozen executable supports a zero-project runtime check:

```text
ToolRecapV4.exe --selfcheck --selfcheck-json selfcheck.json
```

Exit code `0` means all mandatory portable-runtime checks passed. Optional models, credentials, or hardware may be reported as warnings.

## Development

Source tests:

```powershell
pytest -q
python -m compileall -q toolrecap_v4
```

Build the one-folder portable package on Windows:

```powershell
python build_portable.py
```

The generated `dist/`, `build/`, and `release/` directories are intentionally excluded from Git history. Downloadable binaries are distributed through GitHub Releases.
