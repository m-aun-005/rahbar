# AI Usage Disclosure

In compliance with the assignment rules and course policy, this document provides honest attribution of all AI tools utilized during the architecture, coding, and debugging of RAHBAR.

| Tool | What It Wrote or Shaped | What We Changed Afterwards, and Why |
| :--- | :--- | :--- |
| **Claude / Anthropic** | Drafted initial regex patterns for PDF header and footer stripping in `indexer/pipeline/clean.py`. | Modified regex patterns to explicitly exempt clause and section numbers (e.g. `Clause 1.21` and `Section 5.4`). The raw generated regex stripped leading numbers, which destroyed exact-term retrieval. |
| **GitHub Copilot** | Suggested boilerplate FastAPI route definitions for `/healthz` and `/metrics`. | Completely rewrote `/readyz` probe logic to enforce Chroma collection non-emptiness checks, Redis reachability, and the embedding-pin guardrail (`embed_model` matching), ensuring false readiness states cannot be reported. |
| **Gemini / DeepMind** | Provided initial templates for Kubernetes NetworkPolicy manifests and Kustomize overlays. | Added Calico-compliant CIDR egress rules to permit communication with the host machine's Ollama daemon (`port 11434`) and cluster DNS (`port 53` in `kube-system`). The initial policy blocked all egress, causing DNS lookup failures. |
| **ChatGPT (GPT-4o)** | Suggested structure for the golden question set (`eval/golden.yaml`). | Customized questions to specifically target the FAST-NUCES 2023 vs 2026 academic regulations, exact fee numbers, and deliberate hostel omissions to test 100% honest abstention. |
