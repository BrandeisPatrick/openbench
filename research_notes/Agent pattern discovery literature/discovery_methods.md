# Methods for discovering (not pre-specifying) behavioral patterns in agent traces and LLM outputs

Scope note. The two existing openbench maps (`research/background/reasoning-pattern-literature-map.md`, `literature-map-post-training-signatures.md`) already cover Hodoscope (2604.11072), MAST (2503.13657), TraceProbe (2607.06184), ProcGrep (2606.16988), AgentEcho (2604.21255), Automata from Agent Traces (2608.23670), Act·onomy (2605.13625), Behavioral Drivers (2604.02547), LOT open taxonomy (2509.24147), Agent Genome (2606.15579), RL Squeezes (2509.21128) and Base Models Know How (2510.07364, SAE reasoning taxonomies). They are cited here only for placement. Everything below is new to those maps unless marked.

Reading caveat. "Read in full" means the arXiv HTML full text was fetched and processed (not only the abstract). For four long papers the fetch covered roughly the first 100k characters (main body plus early appendices), noted per paper in the last section. Numbers below are as reported from those reads; anything not seen is in Gaps.

## 1. Which pipelines exist for open-ended discovery over transcript / trace corpora?

### Takeaway
There are four families: (a) summarise-embed-cluster-name pipelines (Clio, LLooM, Docent clustering, Hodoscope); (b) contrastive "describe the difference" pipelines that propose natural-language hypotheses and then verify them with a judge on every sample (D5, VibeCheck, Docent pairwise comparison, Explaining Datasets in Words); (c) feature-first pipelines that build interpretable features from SAEs over embeddings or reader-model activations and only then ask an LLM to name them (HypotheSAEs, interp_embed); (d) analyst-driven tooling where humans form hypotheses and LLM "scanners" count them (Inspect Scout, Docent search/rubrics). Only (b) and (c) have built-in quantitative validation; (a) relies on human inspection. None except Docent and Hodoscope has been demonstrated on coding-agent traces at scale.

### Cited Findings
**Clio (Anthropic), arXiv 2412.13678 — read in full (first half).**
- Steps: per-conversation "facets" (some computed directly, e.g., number of turns; others extracted by a model, e.g., language, or summarised, e.g., topic, with the summary prompt told to omit private information) → embed a natural-language facet (paper cites Sentence-BERT / all-mpnet-base-v2) → k-means → a model writes a title and summary per cluster from sample members → recursive hierarchy via k-means plus prompting. — [Clio](https://arxiv.org/abs/2412.13678)
- Scale: ~1 million Claude.ai Free and Pro conversations; a 100,000-conversation run cost $48.81. — [Clio](https://arxiv.org/abs/2412.13678)
- Validation: on 19,476 synthetic transcripts with known generating categories, Clio reconstructs the ground-truth distribution "with 94% accuracy, compared to 5% for random guessing"; per-cluster concern score vs classifier flag rate Pearson r = 0.71; privacy audit of 5,000 conversations found no clusters with private data. — [Clio](https://arxiv.org/abs/2412.13678)
- Stated failure modes: hallucination, misreading slang/sarcasm, missed implicit information, suboptimal groupings for outliers, overly broad labels, imperfect hierarchy placement; fundamentally poor at detecting rare but consequential behaviour; outputs treated as preliminary and no automated action is taken on clusters alone. — [Clio](https://arxiv.org/abs/2412.13678)
- Agent/coding relevance: coding is the most common category ("web and mobile application development" >10% of conversations); Clio was also run on computer-use conversations after the October 2024 Claude 3.5 Sonnet launch, but no volumes or findings are given in the part read. — [Clio](https://arxiv.org/abs/2412.13678)

**LLooM concept induction (Lam et al., CHI '24), arXiv 2404.12259 — read in full (first half).**
- Operators: Distill-filter (quote extraction, gpt-3.5-turbo, T=0) → Distill-summarize (2–4 bullets of 5–8 words) → Cluster (ada-002 embeddings, HDBSCAN, bullets pooled across documents) → Synthesize (gpt-4, 2–4-word concept names plus a one-sentence inclusion criterion) → Score (gpt-3.5-turbo or PaLM, five-point multiple-choice mapped to 0–1 and thresholded) → Loop on uncovered examples or examples covered only by "generic" concepts (matching ≥50% of examples). Optional user "seed" term steers Distill or Synthesize. — [LLooM](https://arxiv.org/abs/2404.12259)
- Scale and cost: samples up to 200 items per run, at most 20 concepts; average run $1.44, 848,323 tokens, 13.7 min; scoring is 79.9% of cost. — [LLooM](https://arxiv.org/abs/2404.12259)
- Evaluation: coverage of ground-truth topics, Bills (28 topics, n=213): LLooM 0.74 vs GPT-4 Turbo 0.56 vs BERTopic 0.29; Wiki (15 topics, n=205): LLooM 0.81, GPT-4 0.83, GPT-4 Turbo 0.82, BERTopic 0.63 (only BERTopic vs GPT-4 significant); 10 trials each; GPT-3.5 automatic coverage matching checked against manual matching on 16 trials (MAE 0.07). Uncategorised share vs BERTopic in scenarios: 9.5% vs 44.4%, 2.5% vs 26.2%, 6.7% vs 18.6%. — [LLooM](https://arxiv.org/abs/2404.12259)
- Stated limitations: defaults not robustly tested across datasets; no verification that quotes are exact or that scores are accurate; run-to-run variation hurts replicability; ~200-item samples may not generalise to full datasets. — [LLooM](https://arxiv.org/abs/2404.12259)

**VibeCheck (Dunlap et al.), arXiv 2410.12851 — read in full.**
- Steps: GPT-4o reads batches of 5 prompt–output pairs from d=20 prompts (40 for HC3) and proposes differences → proposals clustered (agglomerative, instructor-xl) and reduced to K=10 "vibes" (axes like formal→friendly) → two judges (GPT-4o-mini and Llama-3-70b) score every pair on every vibe, each run twice with output order swapped; order-dependent verdicts become 0 → vibes dropped if Cohen's κ < 0.2 or separability < 0.05 → logistic regression on vibe scores for model-matching (MM) and preference prediction (PP) → misclassified pairs seed the next discovery round (3 iterations typical; gains flatten after 3–5). — [VibeCheck](https://arxiv.org/abs/2410.12851)
- Scale: train/test splits of a few hundred each (e.g., Chatbot Arena 839/839, MATH 218/218, HC3 250/250). — [VibeCheck](https://arxiv.org/abs/2410.12851)
- Results: Chatbot Arena Llama-3-70b vs GPT-4/Claude-3-Opus, MM 80.34 (3 iterations) vs 72.10 with predefined vibes, but PP 59.34 vs 61.11 for predefined vibes (so discovered vibes beat predefined ones at telling models apart, not at predicting preference); MATH GPT-4o vs Llama-3-405b MM 97.09; captioning MM 99.13. Recovered most human-found HC3 differences but missed "GPT fabricates facts" and literal-interpretation. — [VibeCheck](https://arxiv.org/abs/2410.12851)
- Stated limits: confounding (a vibe may track accuracy rather than cause preference); discovery misses differences when accuracy differs widely; cheap judge often wrong on math; judges biased toward own outputs; repeated runs yield different vibes; STEM kept only 7 vibes above threshold. — [VibeCheck](https://arxiv.org/abs/2410.12851)

**D5 (Zhong et al.), arXiv 2302.14233 — abstract/summary only.** Takes a goal plus two corpora and outputs a natural-language predicate on which they differ, judged on validity and relevance; built SynD5 (synthetic, known differences) and OpenD5 benchmarks; goal-conditioning correct 12% more often on SynD5 and relevant 31% more often on OpenD5. Code github.com/ruiqi-zhong/D5. — [D5](https://arxiv.org/abs/2302.14233)

**Explaining Datasets in Words (Zhong et al.), arXiv 2409.08466 — read in full (first ~75%).**
- Treats natural-language predicates as model parameters for clustering, time-series, and classification models; optimises by relaxing predicates to embedding-space vectors, gradient descent, then LLM discretisation (candidates re-ranked by correlation with relaxed scores) and iterative replace-the-weakest-predicate refinement. — [Explaining Datasets](https://arxiv.org/abs/2409.08466)
- Clustering F1/surface on five 2,048-sample datasets: method 0.64/0.57 vs prompting 0.27/0.45 vs specialised GoalEx 0.62/0.57; K-means F1 0.65 is on par (Table 4). — [Explaining Datasets](https://arxiv.org/abs/2409.08466)
- Applied to model outputs: classifier on Chatbot Arena found Llama-3-70B better than Claude-3-Opus on queries that "ask an open-ended or thought-provoking question" and worse on technical questions or ones containing code. Application results are judged qualitatively only. Cost: ~100K API calls for ~100 predicates over 1,024 samples. — [Explaining Datasets](https://arxiv.org/abs/2409.08466)

**HypotheSAEs (Movva et al.), arXiv 2502.04382 — read in full (main body).**
- Steps: text-embedding-3-small embeddings → TopK sparse autoencoder over embeddings (size tuned per dataset, e.g., M=4096, k=32 for Congress) → Lasso picks exactly H neurons predictive of a target label → GPT-4o names each neuron from 10 high- and 10 low-activating texts (3 candidates, keep best fidelity) → GPT-4o-mini annotates the named concept on held-out text → multivariate regression with Bonferroni correction (p < 2.5e-3). — [HypotheSAEs](https://arxiv.org/abs/2502.04382)
- Results: significant hypotheses 45/60 vs NLParam 24, BERTopic 23, HypoGeniC 20; Congress 18.1 min, $1.29 vs HypoGeniC 575.4 min, $11.02 and NLParam 904.9 min, $69.92. Ablation: SAE features give 45 significant hypotheses with fidelity 0.836 vs raw embedding dimensions 30 / 0.545 and PCA 23 / 0.547 — the sparse basis is what makes neurons nameable. — [HypotheSAEs](https://arxiv.org/abs/2502.04382)
- Requires a target variable (it is supervised discovery: "what predicts Y"), training sets of ~9K–200K texts in its experiments. — [HypotheSAEs](https://arxiv.org/abs/2502.04382)

**Interpretable embeddings with SAEs / data diffing (Jiang, Sun, Dunlap, Smith, Nanda), arXiv 2512.10092 — read in full (first ~55%).**
- Steps: pass each document through a reader model (Llama 3.3 70B, Goodfire SAE at layer 50, 65,536 latents, ≤2,048-token texts) → max-pool each latent over tokens → binarise → diff latent frequencies between corpora → relabel top 200 latents with an LLM → LLM writes ≤10 hypotheses → an LLM judge checks each hypothesis on every response to compute verified frequency differences. Also NPMI co-occurrence of latents, spectral clustering on Jaccard similarity, and latent-based retrieval. — [interp_embed](https://arxiv.org/abs/2512.10092)
- Results: 2–8× fewer tokens than LLM-only diffing (e.g., 3.5M vs 25.3M/27.5M); SAE correlations recovered injected correlations consistently while the LLM baseline did so inconsistently over ten reshuffles even at T=0. Case studies: OpenAI GPT-3.5→GPT-5 responses on 1K prompts show rising trade-off explanations and personalised follow-ups from GPT-4.1 on; Tulu-3 SFT data shows "I hope it is correct" attached to math prompts, missed by the LLM baseline. No agent traces analysed; 2,048-token context limit is a hard constraint for agent traces. Code: github.com/nickjiang2378/interp_embed. — [interp_embed](https://arxiv.org/abs/2512.10092)

**Docent (Transluce) — blog posts read in full; no paper found.**
- Features: per-transcript summaries; LLM search for a user-described pattern; clustering of search hits (a large LLM proposes centroids, a smaller LLM assigns, heuristic pushes toward mutually exclusive, exhaustive clusters); counterfactual "intervention" by resuming cached VM snapshots with changed inputs. Built on UK AISI Inspect. — [Introducing Docent](https://transluce.org/introducing-docent)
- Terminal-Bench 2.0 case (89 tasks, 3 rollouts per task per model, GPT-5 Codex vs GPT-5.1 Codex, 256M+ tokens): gpt-5-mini wrote a cause-of-failure explanation for 100+ (failed run of one model, successful run of the other) pairs per task → second prompt synthesised model-level failure modes → hypothesis tested with structured queries over run metadata. — [Docent Terminal-Bench](https://transluce.org/docent/blog/terminal-bench)
- Stated limitations: summaries "often contain false positives"; no precision/recall figures; each LLM analysis is stochastic. — [Introducing Docent](https://transluce.org/introducing-docent); [Docent Terminal-Bench](https://transluce.org/docent/blog/terminal-bench)

**Inspect Scout (UK AISI + Meridian Labs) — docs/blog summary only, plus AISI pipeline blog read in full.** Scanners are functions over a transcript (LLM-based or grep-style without model calls), run live or post hoc, results to a dataframe, with support to validate scanners against human-labelled examples; Transect (October 2026) builds on it for long runs. — [Inspect Scout docs](https://meridianlabs-ai.github.io/inspect_scout); [AISI scanners](https://inspect.aisi.org.uk/scanners.html). AISI's seven-step pipeline: define purpose → organise transcripts → manually inspect "at least a few samples" → refine question into concrete signals → design scanner (choose content level: user messages, reasoning, tool calls) → validate scanner on a subset against ground truth (one annotator for objective criteria, several for subjective) → use results. — [AISI pipeline blog](https://www.aisi.gov.uk/blog/a-pipeline-for-transcript-analysis-using-inspect-scout); paper on TechRxiv, not read: [Seven simple steps](https://www.techrxiv.org/users/1032063/articles/1391870-seven-simple-steps-for-log-analysis-in-ai-systems)

**LLM-assisted inductive / thematic coding — search snippets only (abstract/summary only).** Reported human–GPT-4 agreement on inductive coding κ = 0.57 (Zhang et al., AHFE 2025); human–LLM ARI 0.61 for codes and 0.54 for themes, close to human–human agreement (survey-text study; GPT-5 follow-up at arXiv 2608.22417); a Findings of ACL 2026 paper argues standard inter-coder reliability fits open-ended inductive coding poorly. — [AHFE 2025](https://openaccess.cms-conferences.org/publications/book/978-1-964867-71-7/article/978-1-964867-71-7_14); [arXiv 2608.22417](https://arxiv.org/abs/2608.22417); [ACL Findings 2026](https://aclanthology.org/2026.findings-acl.2073.pdf)

Other 2026 trace-mining papers surfaced (abstract/summary only, unverified): FileGram (2604.04901) embeds LLM episode summaries and clusters them agglomeratively; TraceCompiler (2608.02680) mines intent clusters from agent traces into workflows; SKILL.md generation (2606.20363) segments GUI trajectories and clusters segments into candidate skills. — [FileGram](https://arxiv.org/abs/2604.04901); [TraceCompiler](https://arxiv.org/abs/2608.02680); [SKILL.md](https://arxiv.org/abs/2606.20363)

### Inferences
- For openbench the natural split is: family (b) contrastive with per-sample verification when the question is "how does generation N differ from N−1" (VibeCheck-style loop over paired runs on the same PR), and family (a) open clustering when the question is "what happens at all". Docent's Terminal-Bench workflow is the only published example of (b) on coding-agent traces and it is cheap (one judge call per failed/successful pair).
- SAE-based methods (c) are the most statistically disciplined (Bonferroni, held-out annotation, ablations) but need either a target label (HypotheSAEs) or short texts (interp_embed, ≤2,048 tokens). For agent traces this means applying them to per-step or per-command summaries, not whole runs.
- Every family ends with an LLM writing a name; the only check that the name means what the cluster contains is a second, independent LLM (or human) re-applying the name to samples. Pipelines that skip this step (LLooM's scoring is unvalidated; Clio's cluster names are checked only on synthetic data; Docent's summaries) have documented false positives.

### Gaps
- Docent has no paper with precision/recall; its clustering algorithm details beyond the blog are unknown to me.
- HypoGeniC (2404.04326) and TnT-LLM were not read; HypoGeniC appears only as a HypotheSAEs baseline. The Clio appendix (k values, multilingual accuracy table) and LLooM's expert case studies fell in unread portions.
- No CHI/CSCW paper on LLM-assisted grounded theory applied to AI agent traces was found.

## 2. Sequence-level methods for the ACTION channel

### Takeaway
Applied action-channel methods to agents are: n-gram / sequential pattern mining (Bouzenia & Pradel on SWE-bench agents), BPE-style procedure induction (ProcGrep, already covered), directly-follows automata (Automata from Agent Traces, covered) and Markov-chain learning with Alergia over an LLM-induced alphabet (ATLAS). The critical shared step is abstracting raw commands into an alphabet; ATLAS lets an LLM invent and normalise the alphabet, which is the most "discovery-like" variant. No change-point/phase-detection paper on coding-agent traces was found in this pass.

### Cited Findings
**ATLAS (Lopez-Miguel, Happe, Cito, Bartocci, Könighofer, Tappler; MODELS 2026), arXiv 2608.14352 — read in full.**
- Inputs: HackingBuddyGPT penetration-testing agent on DeepSeek V4 Flash, 12 vulnerable Linux VMs, 20 runs per VM, 20-turn limit (240 runs). — [ATLAS](https://arxiv.org/abs/2608.14352)
- Steps: (1) the LLM categorises actions and observations into labels (e.g., DISCOVERY_SUID, EXPLOITABLE_FILE); (2) normalisation merges semantically similar labels into a compact vocabulary; (3) per-trace assignment maps each step to an (action, output) pair, with retries on malformed output; (4) Alergia (AALpy) learns a labelled Markov chain per scenario; models are then pruned, strongly connected components collapsed, and rendered as DAGs. — [ATLAS](https://arxiv.org/abs/2608.14352)
- Outputs: e.g., 57-state and 41-state chains, with mappings back to frequent concrete commands. Finding example: on sudo-NOPASSWD, after reaching EXPLOITABLE_SUDO the agent succeeds immediately in 30% of cases and runs an inefficient `sudo id` in 70%; reading bash history is the crucial step in another scenario. — [ATLAS](https://arxiv.org/abs/2608.14352)
- Validation: no held-out fitness, human evaluation, stability analysis or abstraction-quality metric; only downstream transfer (strategy hints raised ministral-14b from 1/60 to 23/60). Stated failure modes: SCC collapsing hides important steps; reconnaissance-heavy behaviour obscures task-relevant paths; category discovery needs a strong LLM. The paper is internally inconsistent on trace count ("2020" vs 20). Replication package: doi.org/10.6084/m9.figshare.32841767. — [ATLAS](https://arxiv.org/abs/2608.14352)

**Bouzenia & Pradel, "Understanding Software Engineering Agents: A Study of Thought-Action-Result Trajectories" (ASE 2025), arXiv 2506.18824 — read in full.**
- Data: RepairAgent (Defects4J), AutoCodeRover and OpenHands (SWE-bench Lite); 40 trajectories per agent, 120 total, 2,822 iterations. — [Bouzenia & Pradel](https://arxiv.org/abs/2506.18824)
- Action channel: 8 categories (Explore, Locate, Search, Reproduce, Generate fix, Run tests, Refactor, Explain); known tools mapped automatically, the rest labelled by one author with joint resolution; 8.3% of actions uncategorisable. Pattern mining = fixed-length n-grams (tried n ∈ {4,5,6}, used n=4), no support threshold reported, top patterns shown only in figures. — [Bouzenia & Pradel](https://arxiv.org/abs/2506.18824)
- Inductive coding: ~14K pairs of trajectory components open-coded into 18 relationship labels (e.g., thought–action Misalignment; result–thought Misinterpretation; result–action No influence). Selected numbers: result–action "No influence" 1.2% (success) vs 6.2% (failure) for RepairAgent and 4.9% vs 14.6% for AutoCodeRover; thought–action misalignment 0% vs 4.8% (AutoCodeRover). Anti-patterns named: repeated identical actions without follow-up, repeated fix generation without testing, premature termination without validation. — [Bouzenia & Pradel](https://arxiv.org/abs/2506.18824)
- Data/code: github.com/sola-st/llm-agents-study. — [Bouzenia & Pradel](https://arxiv.org/abs/2506.18824)

Already covered in the openbench maps (cite only): ProcGrep BPE procedure vocabulary; Automata from Agent Traces directly-follows FSM, replay fitness, cycle rate; Agent Genome sequence analysis; Hodoscope action-summary embedding + density difference. — see `research/background/reasoning-pattern-literature-map.md`.

Process-mining-for-prompts (COMPASS, CEUR-WS Vol-3996) and ProcBench (2605.20251) surfaced in search — abstract/summary only. — [COMPASS](https://ceur-ws.org/Vol-3996/paper-5.pdf); [ProcBench](https://arxiv.org/abs/2605.20251)

### Inferences
- An LLM-induced alphabet (ATLAS steps 1–3) plus a fixed regex alphabet (Behavioral Drivers, Automata) gives a cheap robustness check: a pattern that appears under both abstractions is less likely to be an artefact of either.
- Bouzenia & Pradel show that cross-channel relations (does the result change the next action? does the action match the stated thought?) produce patterns that pure action mining misses; openbench records reasoning, command and output, so this pairing is available.

### Gaps
- No paper found applying change-point or phase segmentation to coding-agent trajectories in this pass; not proven absent.
- Bouzenia & Pradel give no support thresholds or agreement numbers, so their mined patterns cannot be checked for stability.

## 3. Separating real patterns from noise and judge artefacts

### Takeaway
The validation tools in use are: (i) re-applying each discovered pattern with an independent judge on every sample and testing the difference (VibeCheck, interp_embed, HypotheSAEs, Docent's metadata query); (ii) judge-agreement filters (VibeCheck κ ≥ 0.2, two judges, order swapping); (iii) held-out prediction plus Bonferroni (HypotheSAEs); (iv) synthetic corpora with planted ground truth (Clio, D5 SynD5, LLooM Wiki/Bills, Explaining Datasets, interp_embed); (v) counterfactual intervention on the environment (Docent); (vi) human validation of scanners on a labelled subset (Inspect Scout / AISI). Stability under resampling is acknowledged as a problem (VibeCheck, LLooM, Docent all say runs vary) but no paper read reports a resampling stability statistic for discovered patterns.

### Cited Findings
- VibeCheck: two judges averaged, order-swap with ties to 0, drop vibes with κ < 0.2 or separability < 0.05; notes judges favour their own outputs and repeated runs give different vibes. — [VibeCheck](https://arxiv.org/abs/2410.12851)
- HypotheSAEs: Bonferroni correction on held-out multivariate regression; novelty tested by controlling for previously published features (Congress: 28 of 33 hypotheses remain significant after controlling for n-grams; Headlines: all 15 remain significant after controlling for prior hypotheses). — [HypotheSAEs](https://arxiv.org/abs/2502.04382)
- interp_embed: LLM baseline recovered planted correlations inconsistently across ten reshuffles even at temperature 0, i.e., LLM-only discovery is order-sensitive; SAE hypotheses verified by a judge on every response. Warns latent labels can be poor and that one must look at the data directly. — [interp_embed](https://arxiv.org/abs/2512.10092)
- Clio: 94% reconstruction on 19,476 synthetic transcripts; acknowledges rare behaviours are poorly detected. — [Clio](https://arxiv.org/abs/2412.13678)
- Docent: hypotheses confirmed by intervention (Cybench flag found in a Dockerfile; after removal the agent failed 10 further attempts; finding confirmed with the benchmark authors) and by metadata query (timeouts); summaries otherwise "often contain false positives". — [Introducing Docent](https://transluce.org/introducing-docent); [Docent Terminal-Bench](https://transluce.org/docent/blog/terminal-bench)
- LLooM: automatic coverage scoring checked against manual matching (MAE 0.07), but concept scores themselves not validated. — [LLooM](https://arxiv.org/abs/2404.12259)
- Inter-rater reliability on inductive coding: κ ≈ 0.57 human–GPT-4 (abstract only); a 2026 ACL Findings paper argues IRR is a poor fit for open-ended inductive coding. — [AHFE 2025](https://openaccess.cms-conferences.org/publications/book/978-1-964867-71-7/article/978-1-964867-71-7_14); [ACL Findings 2026](https://aclanthology.org/2026.findings-acl.2073.pdf)

### Inferences
- A defensible openbench protocol: discover on one split of runs (e.g., half the PRs), freeze pattern definitions, then have a different-family judge (not the discovering model, not a model under test) label every run in the held-out split; test generation differences with a paired test across PRs and correct for the number of candidate patterns; hand-label a stratified subset to report judge precision/recall per pattern. This combines VibeCheck's filters, HypotheSAEs' held-out Bonferroni, and AISI's scanner validation.
- Because openbench's models under test overlap with likely judges, VibeCheck's warning about self-preference applies directly; judges should be from a lab outside each compared lineage.
- Run discovery several times with shuffled order and keep patterns that recur (motivated by interp_embed's reshuffle finding and VibeCheck/LLooM run variance); no paper read gives a threshold.

### Gaps
- No paper read reports a quantitative stability-under-resampling measure (e.g., cluster Jaccard across bootstrap runs) for LLM-discovered patterns.
- False-discovery-rate control (vs Bonferroni) for many candidate patterns was not found in any read paper.

## 4. How small can the corpus be?

### Takeaway
No paper read gives a measured minimum. Demonstrated scales on the discovery side are small: VibeCheck discovers from 20–40 prompts and validates on ~200–800 pairs; LLooM works on ≤200 sampled items; ATLAS uses 20 runs per environment; Bouzenia & Pradel use 40 trajectories per agent; Docent's Terminal-Bench study used 3 rollouts × 89 tasks per model. Statistically validated methods (HypotheSAEs) used thousands to hundreds of thousands of texts.

### Cited Findings
- VibeCheck: discovery batches from d = 20 prompts (40 for HC3), test splits 218–839; no explicit minimum stated. — [VibeCheck](https://arxiv.org/abs/2410.12851)
- LLooM: ≤200 items, and notes results may not hold on full datasets. — [LLooM](https://arxiv.org/abs/2404.12259)
- ATLAS: 20 runs per VM, no minimum stated. — [ATLAS](https://arxiv.org/abs/2608.14352)
- Bouzenia & Pradel: 40 per agent; random sampling "may miss rare patterns". — [Bouzenia & Pradel](https://arxiv.org/abs/2506.18824)
- Docent Terminal-Bench: 3 rollouts per task per model; macro-averaging used because rollout counts were uneven. — [Docent Terminal-Bench](https://transluce.org/docent/blog/terminal-bench)
- HypotheSAEs: 8.8K–200K training texts. — [HypotheSAEs](https://arxiv.org/abs/2502.04382)
- AISI: manually inspect "at least a few samples" before designing scanners; no numeric guidance. — [AISI pipeline blog](https://www.aisi.gov.uk/blog/a-pipeline-for-transcript-analysis-using-inspect-scout)

### Inferences
- For a few hundred to a few thousand runs, LLM-proposal methods (VibeCheck/Docent/LLooM style) fit the volume; SAE-on-embedding methods are near the low end of where they have been tested and would need step-level units (many per run) to have enough samples.
- Since rare behaviours are the documented weak spot (Clio, Bouzenia & Pradel), and a few hundred runs cannot support per-model rates for patterns under a few percent, openbench should report per-pattern counts with intervals and treat sub-1% patterns as anecdotes.

### Gaps
- No evidence found on minimum runs per model or per task for stable discovered patterns; this is an open question.

## 5. Genuinely new coding-agent patterns and how they were confirmed

### Takeaway
Few discovery-pipeline outputs on coding agents have been confirmed beyond LLM spot-checks. The best-confirmed new findings are environment/eval artefacts and time-management behaviour from Docent, confirmed by intervention or metadata counts, rather than new reasoning patterns.

### Cited Findings
- GPT-5.1 Codex vs GPT-5 Codex on Terminal-Bench 2.0: GPT-5.1 failures cluster on poor time management (installing GPU instead of CPU packages; aborting training jobs instead of waiting); confirmed by counts: timeouts 49.4% vs 29.1% of runs, 24 tasks time out only for GPT-5.1 vs 3 only for GPT-5; macro reward 0.27 vs 0.39 overall, but GPT-5.1 leads by ~7 pp on timeout-free tasks. Caveat by authors: illustrative, re-run gap (11.4 pp) differs from the leaderboard's 6.5 pp, and the timeout-free filter may favour easier tasks. — [Docent Terminal-Bench](https://transluce.org/docent/blog/terminal-bench)
- Docent on InterCode CTF (79 tasks × 5 runs, GPT-4o): missing packages/network found via transcripts; fixing them raised pass rate 68.6% → 78%; of 11 tasks at 0% pass@5, 4 were broken; 10 transcripts where GPT-4o degenerated into incoherent text after repeated failure. Cybench: flag exposed in a Dockerfile, confirmed by rerun and with benchmark authors. — [Introducing Docent](https://transluce.org/introducing-docent)
- Bouzenia & Pradel: result–action "No influence" (agent ignores a tool result) is more frequent in failing trajectories; confirmed only by the authors' own annotation with partial agreement checks, on 40 trajectories per agent. — [Bouzenia & Pradel](https://arxiv.org/abs/2506.18824)
- Already in the openbench maps: Hodoscope surfaced git-history exploitation and related unanticipated behaviours (see map; not re-researched).

### Inferences
- The confirmation standard to copy is Docent's: after discovery, convert the pattern into a cheap, checkable quantity (a metadata count, a regex on commands, or an environment counterfactual) and test it on the whole corpus.
- For openbench specifically, git-history access and test-file edits (Hodoscope-style) and time-budget behaviour (Docent) are the patterns with prior confirmation on coding agents; anything else the bench discovers would need its own confirmation.

### Gaps
- Could not find a coding-agent paper that showed a discovered pattern was absent from all prior taxonomies via a formal check (e.g., HypotheSAEs-style "significant after controlling for prior features"). That would be the novel contribution for openbench.

## Papers read in full

(Full text processed via fetch of arXiv HTML or the original blog page. "First half" means roughly the first 100k characters, covering the main body and early appendices.)

1. **ATLAS**, https://arxiv.org/html/2608.14352 — full text added the actual scale (240 runs, single agent, pentest only), the complete absence of abstraction-quality or held-out validation, and the internal trace-count inconsistency.
2. **Bouzenia & Pradel, Thought-Action-Result Trajectories**, https://arxiv.org/html/2506.18824v2 — added the n=4 n-gram method without support thresholds, the 18-label open-coding scheme with success/failure rates, and that there are no agreement statistics (only "partial" checks).
3. **VibeCheck**, https://arxiv.org/html/2410.12851 — added the judge-artefact controls (two judges, order swap, κ and separability filters), the discovery budget (20 prompts), and that discovered vibes lose to predefined ones on preference prediction (59.34 vs 61.11) despite abstract-level claims.
4. **HypotheSAEs**, https://arxiv.org/html/2502.04382 (main body) — added the Bonferroni held-out test, the ablation showing the SAE basis drives nameability (fidelity 0.836 vs 0.545), cost numbers vs HypoGeniC, and the novelty-after-controlling test.
5. **Clio**, https://arxiv.org/html/2412.13678 (first half) — added the synthetic-reconstruction validation (94% on 19,476 transcripts), the cost per 100K conversations, and the explicit list of operational and fundamental failure modes including poor rare-behaviour detection.
6. **LLooM**, https://arxiv.org/html/2404.12259 (first half) — added operator-level models and parameters, the ≤200-item / ≤20-concept budget, coverage numbers vs BERTopic and GPT-4, and that concept scores are not validated.
7. **Interpretable Embeddings with SAEs (data diffing)**, https://arxiv.org/html/2512.10092v1 (first ~55%) — added the reader model/SAE and 2,048-token limit, the per-response judge verification of hypotheses, and the finding that LLM-only discovery is unstable across reshuffles at T=0.
8. **Explaining Datasets in Words**, https://arxiv.org/html/2409.08466 (first ~75%) — added that application results on model outputs are qualitative only, that K-means matches the method on clustering F1, and the ~100K API-call cost.

Blog/primary pages read in full (not papers): Introducing Docent, https://transluce.org/introducing-docent; Docent Terminal-Bench, https://transluce.org/docent/blog/terminal-bench; AISI transcript-analysis pipeline, https://www.aisi.gov.uk/blog/a-pipeline-for-transcript-analysis-using-inspect-scout.

Abstract/summary only: D5 (2302.14233); Inspect Scout docs; FileGram (2604.04901); TraceCompiler (2608.02680); SKILL.md generation (2606.20363); DataCOPE / Unsupervised Skill Discovery (2606.06416); COMPASS (CEUR-WS 3996); ProcBench (2605.20251); AHFE 2025 inductive-coding study; arXiv 2608.22417; ACL Findings 2026 inductive-coding evaluation paper. HypoGeniC (2404.04326) and TnT-LLM were not read at all.
