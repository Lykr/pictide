# Docker deployment

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

Docker runs Pictide's web application and CPU recommendation service. Connect an existing ComfyUI or cloud image API in Settings; ComfyUI and image-generation models run separately.

## Start with Compose

Clone the repository, open its directory, and run:

```shell
docker compose up -d --build
docker compose logs -f pictide
```

Open [http://localhost:8189](http://localhost:8189). On first startup, Pictide downloads and verifies the **filtered** vocabulary and MiniLM before serving the page. The container stays in `starting` health status during preparation. Later starts reuse these resources from the data volume; interrupted downloads resume.

The image builds the frontend in a separate Node.js stage. The running image contains Python, application code and built assets; it includes neither vocabulary databases nor MiniLM or generation model weights. Linux amd64 and arm64 are checked by the Docker validation workflow.

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

Update your source checkout, then rebuild and recreate:

```shell
git pull --ff-only
docker compose up -d --build
```

Docker deployments update by replacing the image; the application's portable-package updater is not used. The existing data volume remains mounted. To stop:

```shell
docker compose down
```

## Without Compose

```shell
docker build -t pictide:local .
docker run -d --name pictide --init --restart unless-stopped \
  -p 127.0.0.1:8189:8189 -v pictide-data:/data \
  --add-host host.docker.internal:host-gateway pictide:local
```

Arguments after the image replace its default vocabulary choice, for example `pictide:local --vocabulary all-ratings`.
