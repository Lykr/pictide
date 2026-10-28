# Docker deployment

[简体中文](../../zh-CN/guides/setup/docker.md)

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

Docker runs Pictide's web application and CPU recommendation service. Connect an existing ComfyUI or cloud image API in Settings; ComfyUI and image-generation models run separately.

## Start with Compose

Download `compose.yaml` from [GitHub Releases](https://github.com/Lykr/pictide/releases/latest), place it in an empty directory, and run there:

```shell
docker compose up -d
docker compose logs -f pictide
```

Open [http://localhost:8189](http://localhost:8189). On first startup, Pictide downloads and verifies the **filtered** vocabulary and MiniLM before serving the page. The container stays in `starting` health status during preparation. Later starts reuse these resources from the data volume; interrupted downloads resume.

Compose downloads the prebuilt image from `ghcr.io/lykr/pictide`; Docker selects Linux amd64 or arm64 for your machine. No source checkout or local build tools are needed. Release downloads pin the image version, for example `0.10.0`. The repository's Compose file follows the latest stable release.

Each release builds its portable packages and both image architectures from the same tagged commit. Images pass native startup, CPU inference and persistence checks before publication. The running image contains Python, application code and built frontend assets; vocabulary databases and model weights download on first use.

The default Compose configuration publishes only to this computer. Set `PICTIDE_BIND=0.0.0.0` for access from a trusted LAN. `PICTIDE_PORT` changes the host port while the container keeps port 8189.

## Data and configuration

Compose creates a named `pictide-data` volume mounted at `/data`. It holds settings, images, feedback, vocabularies, model files, resumable downloads and logs. Stopping or recreating the container retains that volume.

To configure Compose, create a local `.env` beside `compose.yaml`, for example:

```dotenv
PICTIDE_PORT=8189
PICTIDE_BIND=127.0.0.1
PICTIDE_VOCABULARY=filtered
```

Use `PICTIDE_VOCABULARY=all-ratings` to choose that edition when no valid vocabulary exists. **All-ratings may generate explicit content.** Existing valid vocabularies are reused; see [Vocabulary editions](../vocabularies.md).

The image runs as UID/GID `10001:10001`. For a bind mount, replace `pictide-data:/data` with a directory writable by that user, or set Compose's `user` to the directory owner's numeric UID/GID. Keep each running Pictide instance on its own data directory.

## Connect an image API

Set the API URL in Pictide's Settings:

| Service location | Example URL |
| --- | --- |
| Docker host | `http://host.docker.internal:8188` |
| Another machine on the LAN | `http://192.168.1.20:8188` |
| Another container on the same Docker network | `http://comfyui:8188` |

The Compose file includes the host-gateway mapping for Linux. A host-side ComfyUI on Linux must listen on an address reachable from Docker, for example by starting it with `--listen 0.0.0.0`. `localhost` inside the container refers to Pictide's container. See Docker's [networking guide](https://docs.docker.com/compose/how-tos/networking/) for connecting services across Compose projects.

## Update and stop

Download the new release's `compose.yaml` into the same directory, retaining your `.env`, then pull and recreate:

```shell
docker compose pull
docker compose up -d
```

Docker deployments update by replacing the image; the application's portable-package updater is not used. The existing data volume remains mounted. To stop:

```shell
docker compose down
```

## Without Compose

```shell
docker run -d --name pictide --init --restart unless-stopped \
  -p 127.0.0.1:8189:8189 -v pictide-data:/data \
  --add-host host.docker.internal:host-gateway ghcr.io/lykr/pictide:0.10.0
```

Arguments after the image replace its default vocabulary choice, for example `ghcr.io/lykr/pictide:0.10.0 --vocabulary all-ratings`.

## Download an image file

If the Docker host cannot reach GHCR, download `pictide-VERSION-linux-amd64-docker.tar.gz` or `pictide-VERSION-linux-arm64-docker.tar.gz` from the same release, along with `compose.yaml`. Select your host architecture, transfer both files, and run:

```shell
docker load -i pictide-0.10.0-linux-amd64-docker.tar.gz
docker compose up -d --pull never
```

The image file contains the same tested image as the registry. Initial vocabulary and MiniLM preparation still needs network access. `SHA256SUMS` verifies downloaded files. For build details, `release-diagnostics.zip` contains `release.json` with the source commit and image digests, plus build and test reports.

## Build from source

For development, clone the repository and use the build override:

```shell
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

This builds `pictide:local`. The default Compose configuration always uses a prebuilt image. See [Docker build verification](../../dev/development.md#build-and-verify-docker).
