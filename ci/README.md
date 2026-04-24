# CI templates

`docker-publish.yml.template` is the GitHub Actions workflow that builds
`worker/Dockerfile` and publishes the resulting image to
`ghcr.io/${owner}/corridorkey-runpod-worker`.

It's shipped here (instead of `.github/workflows/`) because the
`gh` OAuth token used to create this repo did not carry the
`workflow` scope and GitHub refuses to accept workflow-file pushes
without it. Activating the workflow is a one-minute, one-click
operation:

## One-time activation

1. Open <https://github.com/gercheg/corridorkey-runpod-worker/actions/new>
   and click **set up a workflow yourself**.
2. Name the file `docker-publish.yml`.
3. Paste the contents of [`docker-publish.yml.template`](./docker-publish.yml.template)
   (same directory) into the editor.
4. Commit directly to `master`. GitHub creates the file at
   `.github/workflows/docker-publish.yml` with your browser session's
   scopes (those include `workflow` automatically).
5. The workflow triggers on the same commit and starts building.

## Alternative: `gh auth refresh`

If you'd rather drive it from the CLI, run:

```powershell
gh auth refresh --hostname github.com --scopes "workflow,write:packages"
git mv ci/docker-publish.yml.template .github/workflows/docker-publish.yml
git commit -m "ci: activate docker publish workflow"
git push
```

## What the workflow does

- `workflow_dispatch` inputs:
  - `skip_model_prefetch` (default `1`) — skip baking weights into the
    image. Start with `1`; flip to `0` once you've confirmed GHA
    runners can fit the ~15 GB model layer (needs the
    `jlumbroso/free-disk-space` trim + possibly a larger runner).
  - `corridorkey_ref` (default `main`) — upstream CorridorKey git ref
    to build against.
- Logs into `ghcr.io` with the workflow-scoped `GITHUB_TOKEN`
  (`packages: write` permission is declared at the job level).
- Builds `worker/Dockerfile` with GHA cache (`type=gha,mode=max`).
- Tags: `sha-XXXXXXX`, branch name, and `latest` (only on default
  branch).

## Expected output

After the first successful run you'll have:

- `ghcr.io/gercheg/corridorkey-runpod-worker:latest`
- `ghcr.io/gercheg/corridorkey-runpod-worker:master`
- `ghcr.io/gercheg/corridorkey-runpod-worker:sha-XXXXXXX`

These tags are what `worker/deploy/runpodctl_deploy.ps1` expects.
