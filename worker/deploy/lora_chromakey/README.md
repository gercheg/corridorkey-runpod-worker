# Lora Chromakey Gameplay Test

This folder records the reproducible inputs and published outputs for the
Lora green-screen gameplay generation that was processed by CorridorKey on
RunPod Serverless.

Large local binaries and full RunPod responses are intentionally ignored.
The source of truth is `MANIFEST.json` plus the CDN URLs inside it.

## Outputs

- Corrected pure-green start frame:
  <https://content.loremax.ai/Demos/CorridorKey/lora_chromakey/lora_start_frame_pure_green.png>
- Loremax / Seedance generated video:
  <https://content.loremax.ai/data/2026/04/25/0DCiSFABlxtB.mp4>
- CorridorKey composited output:
  <https://content.loremax.ai/Demos/CorridorKey/lora_chromakey/lora_corridorkey_comp.mp4>
- CorridorKey preview:
  <https://content.loremax.ai/Demos/CorridorKey/lora_chromakey/lora_corridorkey_preview.png>

## Reproduce

1. Use Loremax reference `8406` (Lora) and build a 9:16 start frame on a
   chroma background via `Loremax_Image_Scene_builder`.
2. If the generated background is not exact `#00FF00`, normalize only the
   border-connected green area before using it as a video start frame.
3. Run `Loremax_Video_Scene_builder` with:
   - `mode_name=Seedance`
   - `model_type=standard`
   - `duration=6`
   - `aspect_ratio=9:16`
   - `need_audio=false`
   - `need_multi_prompt=false`
   - `image_urls=[corrected start frame URL]`
4. Submit the generated video URL to the CorridorKey RunPod endpoint
   `a72mhm1kdwsvoh` with the settings captured in `MANIFEST.json`.

## Re-upload

If the local media files exist, run:

```powershell
worker\deploy\lora_chromakey\reupload_artifacts.ps1
```

The script uploads only to the writable `Demos/CorridorKey/lora_chromakey/`
prefix and leaves protected Loremax folders untouched.
