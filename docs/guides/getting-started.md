# Installation and Image API Setup

[简体中文](../zh-CN/guides/getting-started.md)

[User documentation](../README.md) · Next: [Roam](roam.md)

Connect an image generation service and start exploring, without writing prompts by hand.

## Before you start

Download and extract a portable package, then follow the startup steps for [Windows](setup/windows.md#portable-edition), [Linux](setup/linux.md#portable-edition), or [macOS](setup/macos.md#portable-edition). It includes the runtime and tag library; the recommendation dependency below downloads on first launch.

Windows preparation can download ComfyUI and the recommended Anima model, then connect its default workflow automatically; see the [Windows guide](setup/windows.md#portable-edition). Packages keep image generation models as optional downloads.

For an existing local ComfyUI installation or an OpenAI Images or Gemini cloud service, connect it under Settings → Image API. To let Pictide start and stop an existing local ComfyUI installation, enable [local startup](settings.md#start-and-stop-local-comfyui) in General settings. Pictide-installed Windows environments retain their automatic startup.

Previous portable packages passed native builds and startup checks on Windows, Linux, and macOS. The new desktop packaging is described in the platform guides; Mac desktop behavior still needs verification. Live cloud image generation remains unverified.

On your first visit, choose **Show me around**. With local generation already prepared, the tour starts at **Start roaming**; otherwise it helps you connect a service first. You can end it anytime and reopen it under **Settings → General → Getting started**.

## Connect ComfyUI

1. Start ComfyUI with an image generation model installed.
2. Add ComfyUI under Settings → Image API and enter its address, such as `http://127.0.0.1:8188` (use its actual port).
3. Keep “Default text-to-image,” load and select a checkpoint, test the connection, and save.

The default workflow supports complete SD/SDXL checkpoints. Open Roam, choose “Start roaming,” and wait for your first image. Likes and dislikes help future recommendations adapt to your preferences.

### Custom workflows

When manually connecting models such as Anima or Flux, or your own process, choose “Custom API workflow.” Import **API-format JSON** exported from ComfyUI, select positive and negative prompt inputs and image output nodes, then save. Regular UI workflow JSON cannot be used directly. Models prepared through Pictide already include their default workflow and bindings.

### Recommended image generation model

For anime and illustrations, we recommend [Anima Turbo v1.1](https://huggingface.co/circlestone-labs/Anima). It supports Danbooru tags and uses ComfyUI's built-in nodes. Windows local preparation handles the following files and workflow for you. For manual setup, download these three files, about **5.63 GB** in total, into the matching folders under your ComfyUI models directory:

| Folder | File |
| --- | --- |
| `diffusion_models/` | [anima-turbo-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-turbo-v1.1.safetensors) |
| `text_encoders/` | [qwen_3_06b_base.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/text_encoders/qwen_3_06b_base.safetensors) |
| `vae/` | [qwen_image_vae.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/vae/qwen_image_vae.safetensors) |

Import the [Anima Turbo API workflow](../assets/workflows/anima-turbo-v1.1.api.json) through “Custom API workflow.” Bind positive text to `11 → text`, negative text to `12 → text`, and the seed to `19 → seed`; select `1 · Save Image` as the image output. The workflow uses **832×1248 (2:3 portrait), 10 steps, CFG 1, Euler / simple**. Negative prompts have no effect at CFG 1.

The model has a [non-commercial license](https://huggingface.co/circlestone-labs/Anima#license); generated images may be used commercially.

## Connect OpenAI Images or Gemini

1. Add an API under Settings → Image API and choose **OpenAI Images** or **Gemini**.
2. Enter an API key, an image-capable model ID, and a Base URL. Official URLs are `https://api.openai.com/v1` and `https://generativelanguage.googleapis.com/v1beta`, respectively.
3. Test the connection and save, then generate one image on Generate. The connection test does not generate images or incur generation charges; a successful image confirms that your account and model work.

In Danbooru mode, cloud connections use positive prompts; leave the negative prompt empty in your roaming preset. Natural-language mode can include avoidance instructions in the positive description.

Images, likes, and preferences stay local. Prompts and generation options go to your chosen service under its billing and data policies. When Roam first switches to a cloud API, automatic prefetch starts at `0`. Increasing it generates images ahead of time and incurs charges; requesting the next image still generates one with prefetch off.

Once a request starts, local cancellation cannot guarantee remote cancellation or prevent charges. If a request times out or its result is uncertain, check your provider's activity before retrying.

## Natural-language prompts

For models that work better with descriptions, add a connection under **Settings → LLM API**. Use an OpenAI-compatible text API with its Base URL, model ID, and key, or choose **ChatGPT** and continue through browser authorization. For an API key connection, the URL includes the API version, for example `https://api.openai.com/v1`; the service must support Chat Completions with JSON output.

Then select **Natural language** in your **Image API** settings, choose the saved **LLM API**, and save. Several image APIs can share one LLM connection.

For ChatGPT, sign in from the computer running Pictide using its localhost address, then load and save an available model. Eligible requests use your account's authorized plan allowance; image generation still uses the image API. Use **Manage usage** to review limits. If access or allowance is unavailable, Pictide stops conversion; it never silently switches to paid API usage. After setup, your other devices can use the saved connection.

Continue choosing tags, presets, and anchors as usual. Pictide turns the chosen combination into a description before generating an image. Under **Prompts → Preview**, select that image API to see both tags and the final text. The text is read-only and can be copied.

This sends the selected concepts to the text service and may incur additional charges. Drift composes fresh text, Flow asks for minimal wording changes, and Anchor reuses prepared text. If preparation fails, no image is submitted; check the service and retry. Model quality determines how faithfully the text and image follow your tags.

Keep **Danbooru** to use tags directly without an LLM.

## Network proxy

Internet downloads and image services automatically follow your system's HTTP(S) proxy settings or proxy environment variables. Localhost, private IP addresses, and local hostnames connect directly. To bypass a proxy for a custom internal domain, add it to your proxy exceptions or `NO_PROXY`. With no proxy configured, connections are direct. Pictide does not change your system settings. On macOS, HTTPS connections use the system certificate trust settings.

## Recommendation dependency preparation

First launch downloads MiniLM, a recommendation dependency (about **91 MB**). Keep the launcher window open until downloading and verification finish; the application opens afterward. If downloading fails, restore connectivity and restart to resume. Completed downloads are reused offline.

<details>
<summary>First launch offline: prepare the model manually</summary>

Download these five files on a connected machine, keep their names, and place them in `models/minilm/` under your selected [data directory](backup.md#data-location). Then start Pictide. See the [model catalog](../../backend/recommendation/model.json) for the version and checksums.

- [model.onnx](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/model.onnx)
- [tokenizer.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer.json)
- [config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/config.json)
- [tokenizer_config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer_config.json)
- [special_tokens_map.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/special_tokens_map.json)

</details>

## Start from source

Source startup requires Python 3.10+. On a fresh checkout, build the frontend and [add a library](prompts.md#add-and-switch-libraries). Follow the steps for [Windows](setup/windows.md#prepare-from-source), [Linux](setup/linux.md#prepare-from-source), or [macOS](setup/macos.md#prepare-from-source).
