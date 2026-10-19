# Installation and Backend Setup

[简体中文](getting-started.zh-CN.md)

[Documentation](../README.md) · Next: [Prompts](prompts.md) / [Roam](roam.md)

This page covers startup preparation and generation backend setup for the portable and source editions. Prepare ComfyUI and a working text-to-image model before starting Pictide.

## Before you start

The portable edition includes the application, frontend, a compact tag library, and offline MiniLM. Extract it and run the startup entry point for your operating system: [Windows](setup/windows.md#portable-edition) · [Linux](setup/linux.md#portable-edition) · [macOS](setup/macos.md#portable-edition).

The source edition requires Python 3.10+. A fresh checkout also requires a frontend build; see [development prerequisites (Chinese)](../dev/development.md#首次准备检出目录) for Node.js and pnpm versions. Once the frontend is built, daily use does not require a Node.js service.

The launcher automatically prepares the Python environment, dependencies, and caches inside the selected data directory. It does not download image generation models, tag libraries, or recommendation models. Create a separate runtime environment on each operating system rather than reusing another system's venv. The Linux and macOS script flows have passed Bash smoke checks; installation on their native environments remains unverified.

## Install and start on your operating system

Choose your system and follow its page for startup, source preparation, custom parameters, and LAN configuration:

- [Windows](setup/windows.md)
- [Linux](setup/linux.md)
- [macOS](setup/macos.md)

After startup, continue with the ComfyUI setup below. The application and ComfyUI start and stop independently; there is no automatic startup or persistent service.

## Connect ComfyUI

1. Start ComfyUI, open Settings → Backend in Pictide, and enter a backend name and its actual address, such as `http://127.0.0.1:8188`. The Desktop edition may use another port.
2. Keep “Default text-to-image,” load and select an installed checkpoint. Leave it empty to use the first model in the list automatically. No workflow import or input binding is required.
3. Test the connection and save. After preparing the tag library and recommendation model, open Roam and click “Start roaming” to view the first image, express a preference, and move to the next image. You can also submit a prompt on Generate to verify manual text-to-image generation.

The built-in workflow uses ComfyUI's standard nodes and supports complete SD/SDXL-compatible checkpoints. Defaults are 832×1216, 16 steps, CFG 2.5, DPM++ 2M / Karras, and denoise 1. Models are not downloaded. Use an appropriate custom workflow for other model architectures such as Flux.

### Custom workflows

For a custom process, switch to “Custom API workflow,” import **API-format** JSON, and select the positive and negative text inputs, optional seed, and image output nodes. Normal UI workflows containing a `nodes` array are not supported. Clearing the custom workflow returns to default text-to-image; an existing nonempty workflow remains custom.

The Workflow control in Settings combines a name input with a dropdown: choose default text-to-image, a saved workflow, or a custom API workflow, or type a name to filter existing entries. Editing the name after selecting an existing entry renames it while preserving its ID. Selecting the custom entry fills in an editable default name that avoids existing names. “Save backend” saves the template to `data/workflows` and applies it to the backend together, without a separate save-as or apply step. Saving checks the revision that was read; conflicts with external edits preserve the draft and prevent overwriting. When creating a custom workflow, the same name and content reuse an existing template, while the same name with different content is rejected. Versions before template updates are stored in `data/workflows/.backups`.

Workflow updates apply to the backend being saved. Other backends keep their own saved workflow snapshots; select the workflow again and save to apply the latest version. Existing tasks always use the backend configuration from submission time, unaffected by later edits.

Deleting a workflow removes it from the selection list, keeps a file backup, and clears the current backend's reference to the template. The backend retains its applied node, binding, and output snapshots and can continue generating. Deleting a backend only removes its currently selectable configuration; configuration revisions, historical tasks, images, and ratings are retained. Submitted tasks continue with the original configuration. These deletions do not clean up images or ComfyUI data; see [data recovery](backup.md).

The default text-to-image Node parameters can be expanded into a custom draft. Ordinary inputs such as model, dimensions, batch count, sampling steps, CFG, sampler, scheduler, and denoise can be edited while connections stay unchanged. API workflow JSON is collapsed by default; expand it to edit or import API JSON. Parameter editing and JSON editing share the same draft.

### Prompts and image records

Before import, replace random prompt generation nodes in the workflow with fixed text inputs. Pictide injects the final text into the bound inputs. The workflow should send that text directly to the text encoder and use the same text source for output prompt records. Do not randomize or rewrite text downstream, as the record would no longer accurately represent the encoder's actual input.

ComfyUI only executes the generation API; prompt generation, preview, and prompt-saving nodes are no longer installed. Workflows use native image outputs such as PreviewImage / SaveImage, while Pictide saves the images and corresponding positive/negative prompt JSON. If an old workflow contains removed RulePrompt nodes, replace them with native text inputs and image outputs before importing.

### Task execution and checks

Multiple backends can be saved separately. After editing a backend address or workflow, old tasks continue using the backend configuration from submission time so that tasks and images reference the correct service. New tasks subscribe to ComfyUI completion events before submitting generation. At most two tasks are in flight across the application, usually one generating and one queued in ComfyUI. On notification, Pictide verifies completion over HTTP, submits the next item, then saves images. If notifications are unavailable, it automatically falls back to polling; see [task event notifications (Chinese)](../dev/issues/task-events.md) and the [submission window (Chinese)](../dev/issues/task-window.md). After generation, Pictide copies images into `data/images` and saves a same-named JSON containing only the positive and negative prompts actually submitted; no configuration or additional TXT is saved. Saved images remain browsable after ComfyUI closes. Images from before the upgrade are copied on first access, which requires them to remain readable from the corresponding backend. ComfyUI manages its own output/temp files.

Connection testing performs a read-only preflight that detects common missing models, missing input images, connection problems, and invalid enumerated values. It does not submit generation or replace formal validation by ComfyUI custom nodes. HTTP 400 errors show identifiable node and input causes.

## Start from source

A fresh checkout contains no dependencies, tag library, recommendation model, or frontend build output. Install and build using the [development workflow (Chinese)](../dev/development.md#首次准备检出目录); see the [prompts guide](prompts.md#data-preparation) for library import and the [recommendation module](../dev/architecture/recommendation.md#model-preparation) for model preparation. See [data backup](backup.md) for paths and backups.
