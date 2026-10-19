# Installation and Image API Setup

[简体中文](getting-started.zh-CN.md)

[User documentation](../README.md) · Next: [Roam](roam.md)

Connect an image generation service and start exploring, without writing prompts by hand.

## Before you start

Download and extract a portable package, then follow the startup steps for [Windows](setup/windows.md#portable-edition), [Linux](setup/linux.md#portable-edition), or [macOS](setup/macos.md#portable-edition). It includes the runtime and tag library; the recommendation dependency below downloads on first launch. Once the browser opens, connect a service under Settings → Image API.

Connect your local ComfyUI installation, or choose OpenAI Images or Gemini for cloud generation. Pictide does not include an image generation model. When using ComfyUI, start both applications separately.

Portable builds and startup checks have passed on Windows, Linux, and macOS. Live cloud image generation remains unverified.

On your first visit, choose **Show me around** for a short tour from connecting a service to exploring images. You can end it anytime and reopen it under **Settings → General → Getting started**.

## Connect ComfyUI

1. Start ComfyUI with an image generation model installed.
2. Add ComfyUI under Settings → Image API and enter its address, such as `http://127.0.0.1:8188` (use its actual port).
3. Keep “Default text-to-image,” load and select a checkpoint, test the connection, and save.

The default workflow supports complete SD/SDXL checkpoints. Open Roam, choose “Start roaming,” and wait for your first image. Likes and dislikes help future recommendations adapt to your preferences.

### Custom workflows

For other models such as Flux, or your own process, choose “Custom API workflow.” Import **API-format JSON** exported from ComfyUI, select positive and negative prompt inputs and image output nodes, then save. Regular UI workflow JSON cannot be used directly.

## Connect OpenAI Images or Gemini

1. Add an API under Settings → Image API and choose **OpenAI Images** or **Gemini**.
2. Enter an API key, an image-capable model ID, and a Base URL. Official URLs are `https://api.openai.com/v1` and `https://generativelanguage.googleapis.com/v1beta`, respectively.
3. Test the connection and save, then generate one image on Generate. The connection test does not generate images or incur generation charges; a successful image confirms that your account and model work.

Cloud connections use positive prompts; leave the negative prompt empty in your roaming preset.

Images, likes, and preferences stay local. Prompts and generation options go to your chosen service under its billing and data policies. When Roam first switches to a cloud API, automatic prefetch starts at `0`. Increasing it generates images ahead of time and incurs charges; requesting the next image still generates one with prefetch off.

Once a request starts, local cancellation cannot guarantee remote cancellation or prevent charges. If a request times out or its result is uncertain, check your provider's activity before retrying.

## Recommendation dependency preparation

First launch downloads MiniLM, a recommendation dependency (about **91 MB**). Keep the launcher window open until downloading and verification finish; the application opens afterward. If downloading fails, restore connectivity and restart to resume. Completed downloads are reused offline.

<details>
<summary>First launch offline: prepare the model manually</summary>

Download these five files on a connected machine, keep their names, and place them in `models/minilm/` under your selected data directory (normally `data/models/minilm/`). Then start Pictide. See the [model catalog](../../backend/recommand/model.json) for the version and checksums.

- [model.onnx](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/model.onnx)
- [tokenizer.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer.json)
- [config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/config.json)
- [tokenizer_config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer_config.json)
- [special_tokens_map.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/special_tokens_map.json)

</details>

## Start from source

Source startup requires Python 3.10+. On a fresh checkout, build the frontend and [add a library](prompts.md#add-and-switch-libraries). Follow the steps for [Windows](setup/windows.md#prepare-from-source), [Linux](setup/linux.md#prepare-from-source), or [macOS](setup/macos.md#prepare-from-source).
