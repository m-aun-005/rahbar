# RAHBAR Completion and Execution Guide

This guide is written for the current repository in this folder. The repository contains a substantial implementation produced by Antigravity, but it has not yet been validated on Docker/Kubernetes, connected to GitHub, or demonstrated end to end.

## 1. What the assignment requires

The assignment is to build RAHBAR, a grounded question-answering service over a real document corpus and deploy it on Kubernetes.

A question must follow this path:

~~~text
Question -> API validation -> semantic cache -> Chroma retrieval
         -> evidence prompt -> schema-constrained LLM answer
         -> Pydantic validation -> citation check -> response
~~~

The response must use only retrieved evidence. Every citation must match a retrieved passage. If no passage clears the relevance threshold, the service must return an honest abstention.

The system is split into two paths:

~~~text
Indexer Job/CronJob -> ChromaDB (only writer)

User -> Ingress -> UI -> API replicas -> ChromaDB (reader)
                                      -> Redis cache
                                      -> LLM provider
~~~

The assignment tests whether the design survives an empty index, a stale document, a bad extraction, a prompt injection, a missing answer, a deleted pod, a restart, and horizontal scaling.

## 2. Required deliverables

The finished repository must contain:

- A real corpus of at least six public documents and 40 pages.
- Two versions of one policy and metadata for document version/superseded status.
- One scanned PDF, OCR handling, and documentation of extraction limits.
- One meaningful table and a before/after extraction example.
- A structure-aware indexer with extract, clean, chunk, embed, and store stages.
- ChromaDB storage with source, section, page, doc_version, and superseded metadata.
- An API that retrieves, filters old versions, grounds answers, validates output, checks citations, and abstains.
- A semantic cache with a measured threshold and re-index invalidation.
- A pinned embedding model shared by API and indexer, with a runtime mismatch guardrail.
- Dockerfiles for API, indexer, and UI.
- Kubernetes Namespace, Deployments, Chroma StatefulSet, Redis PVC, Job, CronJob, Services, Ingress, ConfigMap, Secret placeholder, NetworkPolicies, probes, resource limits, and HPA.
- At least 15 golden evaluation questions and a regression gate.
- At least 12 meaningful tests, including abstention and prompt-injection tests.
- CI and CD workflows with tests, lint, manifest validation, image builds, security scan, e2e evaluation, SHA-tagged images, and gated publishing/deployment.
- README, corpus notes, pipeline notes, failure analysis, engineering notes, ADRs, evidence, and AI-use disclosure.
- A GitHub repository, successful CI/CD run, Docker image links, and committed evaluation results.

## 3. Current status of this repository

The static implementation is strong.

Already present:

- Git repository on branch dev.
- 28 commits with conventional prefixes.
- API, indexer, UI, eval, corpus, k8s, docs, and workflows.
- No remaining unfinished starter markers.
- No production NotImplementedError stubs.
- Four ADRs.
- Sixteen golden questions.
- Fifteen test functions.
- Five evidence files.
- Dockerfiles and .dockerignore files.
- Kubernetes resources and overlays.
- README and required documentation.
- eval/results.json and eval/baseline.json.
- Secret placeholder only, no apparent real secret.

Local static verification already performed:

- Submission checker: 166 passed, 1 warning, 0 failures.
- API unit tests: 6 passed.
- Indexer unit tests: 6 passed.
- Python compileall: passed.
- Dev and production Kustomize rendering: passed.

The one checker warning concerns the committed secret placeholder. That is expected and safe if it contains only a placeholder.

The repository is therefore implementation-complete enough to move to runtime validation. It is not deployment-complete until Docker, minikube, GitHub Actions, and the required demonstrations succeed.

## 4. Known issues to fix before relying on CI/CD

These problems were found by inspecting the current files.

### 4.1 CI e2e image tags

CI builds and loads images tagged with the GitHub SHA, but the dev Kubernetes overlay refers to images tagged dev. The cluster therefore may not find the images.

Fix one of these approaches:

- Patch the dev overlay image names to use the current SHA in CI.
- Or build/load both SHA and dev tags during CI.
- Prefer the first approach for traceability.

### 4.2 CI e2e name prefixes

The dev overlay adds the prefix dev-. Rendered names include:

~~~text
dev-api
dev-indexer
dev-reindex
dev-api service
~~~

The current CI commands refer to unprefixed names such as job/indexer, cronjob/reindex, and svc/api.

Change the CI commands to use the rendered names, or remove the dev name prefix. The commands must consistently target the same names used by the overlay.

### 4.3 CD production image names

The production overlay adds prod- names but does not replace the base image references with the Docker Hub images tagged by GitHub SHA. The CD deployment may therefore use local dev image names or fail to pull images.

Add an image transformation in the production overlay, or pass image overrides in the CD command. Use the Docker Hub repository and github.sha tag.

### 4.4 Trivy must fail on serious vulnerabilities

The current scan has exit-code set to 0. That reports vulnerabilities without failing the workflow. The assignment requires HIGH or CRITICAL fixable findings to fail CI.

Change the scan to use exit-code 1 and keep the severity filter. Then confirm the workflow still passes against the built images.

Do not submit these workflow issues as-is. Fix them before the first real pull request.

## 5. Set up Windows correctly

Use WSL 2 Ubuntu for repository commands because the Makefile expects Bash.

Install or verify:

- WSL 2 with Ubuntu.
- Docker Desktop with WSL integration enabled.
- Git.
- Python 3.12.
- GNU make.
- kubectl.
- minikube.
- kustomize, or use kubectl kustomize.
- Optional: Ollama for local generation and embeddings.

Open Ubuntu and move to the repository:

~~~bash
cd /mnt/c/Users/Decent/Desktop/SCD\ Assignment/rahbar
git status
git branch --show-current
~~~

Keep Docker Desktop running whenever you build images or start minikube.

## 6. Create and connect the GitHub repository

Do not overwrite the existing Git history. It already contains the implementation commits.

On GitHub:

1. Create a new empty repository named rahbar.
2. Do not initialize it with another README, license, or .gitignore.
3. Copy the HTTPS or SSH repository URL.
4. In WSL, run:

~~~bash
git remote -v
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin dev
~~~

If origin already exists, inspect it before changing it:

~~~bash
git remote -v
git remote set-url origin YOUR_GITHUB_REPOSITORY_URL
~~~

On GitHub, protect main:

- Require pull requests.
- Require CI checks before merging.
- Require one approval if your course requires it.
- Disable direct pushes to main.

Create main through a pull request from dev after the first CI run. Do not commit API keys, Docker passwords, kubeconfig files, or .env files.

## 7. First local validation

From the repository root:

~~~bash
make install
make test
make lint
make check
python scripts/check_submission.py
~~~

The Makefile runs API and indexer tests from their own directories. Running pytest from the repository root can produce import-path errors even when the Makefile test target is correct.

Also run:

~~~bash
kubectl kustomize k8s/overlays/dev > /tmp/rahbar-dev.yaml
kubectl kustomize k8s/overlays/prod > /tmp/rahbar-prod.yaml
git grep -nE 'API_KEY|PASSWORD|TOKEN|SECRET' || true
git log --all --oneline
~~~

Review any secret-looking result manually. The placeholder manifest is allowed; real credentials are not.

## 8. Verify the corpus and indexer locally

The assignment grades the corpus, not only the code. Inspect corpus/MANIFEST.md and docs/CORPUS.md. Confirm that the listed URLs, checksums, versions, page counts, scanned document, table document, and absent topic are real.

If the raw corpus is not present, fetch it according to the repository instructions:

~~~bash
cp corpus/sources.example.yaml corpus/sources.yaml
make fetch
python corpus/fetch.py --verify
~~~

Never commit corpus/raw unless the assignment explicitly permits your chosen documents to be committed.

Run the fixture/dummy indexer first:

~~~bash
python -m pipeline.run --dummy
~~~

For the real indexer, Chroma and the embedding endpoint must be running. Confirm that the indexer writes model metadata and the required chunk metadata. Confirm that a successful index invalidates the cache.

## 9. Start and verify Docker

Build the three images:

~~~bash
docker build -t rahbar-api:dev api
docker build -t rahbar-indexer:dev indexer
docker build -t rahbar-ui:dev ui
docker images | Select-String rahbar
~~~

On Windows PowerShell, use the same commands without the Select-String line if you are working inside WSL.

Check that:

- all builds finish successfully;
- images use pinned base versions;
- containers run as non-root;
- no credentials are in image layers;
- API and indexer images start with their declared commands;
- UI nginx can write to its allowed temporary directory.

Run the API stub locally if needed:

~~~bash
make dev
~~~

In another terminal:

~~~bash
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl -X POST http://localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What does the stub contain?"}'
~~~

## 10. Start minikube

Use Docker Desktop as the driver:

~~~bash
minikube start --driver=docker --cni=calico --memory=6144 --cpus=4
minikube addons enable metrics-server
minikube addons enable ingress
minikube status
~~~

Calico is required because the default cluster networking may ignore NetworkPolicy.

If using host Ollama, start it so the cluster can reach it:

~~~bash
export OLLAMA_HOST=0.0.0.0
ollama serve
ollama pull llama3.2:3b
ollama pull nomic-embed-text
~~~

On Windows with the Docker driver, use minikube tunnel if the Ingress IP is not reachable:

~~~bash
minikube tunnel
~~~

Keep the tunnel terminal open.

## 11. Build and load images into minikube

~~~bash
docker build -t rahbar-api:dev api
docker build -t rahbar-indexer:dev indexer
docker build -t rahbar-ui:dev ui
minikube image load rahbar-api:dev
minikube image load rahbar-indexer:dev
minikube image load rahbar-ui:dev
~~~

Use imagePullPolicy IfNotPresent for locally loaded images.

## 12. Deploy in a safe order

Use the exact names rendered by your chosen overlay. A simple development deployment is:

~~~bash
kubectl apply -k k8s/overlays/dev
kubectl get all -n rahbar
kubectl get pvc -n rahbar
kubectl get events -n rahbar --sort-by=.lastTimestamp
~~~

If the overlay uses the dev- prefix, check names with:

~~~bash
kubectl get deployments,services,jobs,cronjobs -n rahbar
~~~

Create the LLM Secret from an environment variable only:

~~~bash
export LLM_API_KEY='your-key-in-your-shell-only'
make secret
~~~

If using the stub provider, the key may be unnecessary, but never replace a real key with a committed manifest.

Run or monitor the indexer:

~~~bash
kubectl get jobs,pods -n rahbar
kubectl logs -n rahbar job/dev-indexer
~~~

Use the actual rendered Job name if your overlay prefixes it.

Wait for API readiness:

~~~bash
kubectl get pods -n rahbar -w
kubectl rollout status deployment/dev-api -n rahbar
kubectl get endpoints -n rahbar
kubectl get hpa -n rahbar
~~~

Use the actual names shown by kubectl get deployments.

## 13. Test the running service

Port-forward the rendered API Service:

~~~bash
kubectl port-forward -n rahbar svc/dev-api 8000:8000
~~~

Then test:

~~~bash
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
curl -X POST http://localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Ask a question supported by the corpus"}'
~~~

Check all of these behaviors:

- valid grounded answer;
- citations match retrieved passages;
- unsupported question abstains;
- prompt-injection content is not followed;
- repeated safe question can use the cache;
- follow-up question is not incorrectly cached;
- readiness fails when Chroma/Redis/index is unavailable;
- API remains alive while a dependency is slow.

## 14. Capture the required evidence

The assignment requires evidence, not only code. Save command output or screenshots under docs/evidence.

Capture:

1. Branch protection and pull-request settings.
2. A deliberately blocked merge caused by failing CI.
3. A successful green CI run.
4. kubectl top pods output with resource usage.
5. kubectl get endpoints showing at least three API endpoints.
6. HPA output with a known CPU request and replica range.
7. A grounded answer with citations.
8. A must-abstain answer.
9. A prompt-injection test result.
10. Pod deletion and recovery.
11. Embedding-model mismatch causing readyz to return 503 and a useful log line.
12. Rollout status, then rollout undo.
13. Successful evaluation output and committed results/baseline files.

Useful commands:

~~~bash
kubectl top pods -n rahbar
kubectl get endpoints -n rahbar
kubectl get hpa -n rahbar
kubectl delete pod POD_NAME -n rahbar
kubectl get pods -n rahbar -w
kubectl rollout status deployment/dev-api -n rahbar
kubectl rollout undo deployment/dev-api -n rahbar
~~~

## 15. Fix and run CI/CD

After fixing image tags, prefixed resource names, production image overrides, and Trivy exit code:

~~~bash
git add .
git commit -m "fix: make CI and CD deploy immutable image tags"
git push origin dev
~~~

Open a pull request from dev to main. Watch every job:

- lint;
- tests and coverage;
- manifest validation;
- image builds;
- security scan;
- kind or k3d e2e evaluation.

Do not merge until the CI e2e job reaches the API, runs the indexer fixture Job, and completes eval/run_eval.py successfully.

After merging to main, verify CD:

- tests pass;
- Docker Hub login succeeds;
- all three images are pushed with the commit SHA;
- production manifests use those SHA images;
- deployment rollout succeeds;
- smoke test succeeds.

The CD workflow must not deploy latest.

## 16. Evaluation and final checks

Run the evaluation against the running service:

~~~bash
python eval/run_eval.py --api http://YOUR_INGRESS_ADDRESS --host rahbar.local
~~~

Check that:

- recall@5 is measured and documented;
- citation validity is at least 95%;
- abstention correctness is 100%;
- baseline and results are committed;
- exact-term recall and version-sensitive behavior are discussed.

Final local commands:

~~~bash
make test
make lint
make check
python scripts/check_submission.py
git status
git log --oneline --decorate -12
~~~

## 17. Time estimate

Because most implementation work already exists, a realistic estimate is:

| Work | Typical time |
|---|---:|
| Read/review repository and fix workflow issues | 45-90 minutes |
| Create GitHub repository, push, protect main | 20-45 minutes |
| Install/configure WSL, Docker, minikube, kubectl | 45-120 minutes |
| Build images and resolve Docker issues | 30-90 minutes |
| Deploy and debug minikube | 60-150 minutes |
| Run evaluation and capture evidence | 45-90 minutes |
| CI/CD credentials, Docker Hub, and final run | 45-120 minutes |
| Final documentation review and submission | 30-60 minutes |

Expected total: about 5-9 hours if Docker and networking work normally; 8-14 hours if this is the first time using WSL/minikube or if image pulls/network policies cause problems.

The repository coding portion is mostly done. The remaining effort is operational: fixing CI/CD, installing tools, running the stack, diagnosing failures, collecting evidence, and submitting through GitHub.

## 18. What you must personally do

You must personally create/use the GitHub and Docker Hub accounts, keep API keys private, run Docker/minikube/Ollama on your computer, capture evidence, submit the links, and understand the design for the viva. AI assistance must remain disclosed in docs/AI-USAGE.md.


