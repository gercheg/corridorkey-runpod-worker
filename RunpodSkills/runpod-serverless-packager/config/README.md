# Config

Store local configuration templates here, not secrets.

Recommended files for a copied local setup:

```text
dockerhub.example.env
runpod.example.env
s3.example.env
```

Do not commit real tokens, API keys, registry passwords, or S3 secrets.

Use this directory to document variable names only:

```text
RUNPOD_API_KEY=
RUNPOD_ENDPOINT_ID=
DOCKERHUB_USER=
DOCKERHUB_PAT=
BUCKET_ENDPOINT_URL=
BUCKET_NAME=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_PUBLIC_BASE_URL=
S3_PREFIX=
```
