# Discovering and validating behavior patterns in agent transcripts

Scope: how to find behavior patterns nobody listed in advance, across about 100 to a few thousand coding-agent runs, and how to show a pattern is real. The sections follow the pipeline: discovery, judging, checking, statistics, and keeping exploration apart from confirmation. They end with candidate experiments for openbench.

Method note: every paper was read through a fetch tool whose summarising model returns extracted content rather than verbatim text. "Read in full" therefore means the full HTML text was fed through, with the coverage noted at the end. Numbers below are the ones that came back. Where a paper contradicts itself, both figures are given.

## 1. Discovery step: what open-ended pipelines exist, their inputs, outputs, scale and cost

### Takeaway
Five families have been demonstrated:
- Embed-and-cluster with LLM naming (Clio).
- Contrastive hypothesis proposal with per-sample judging (VibeCheck).
- Sparse-autoencoder features over embeddings, then LLM interpretation and regression (HypotheSAEs).
- LLM-assisted or manual open coding and grounded theory (MAST, Bouzenia & Pradel).
- Action-sequence mining and process mining (n-grams in Bouzenia & Pradel; process and causal discovery in Fournier et al.).

Only the last two, plus the Docent, HAL and AISI tooling, have been applied to agent trajectories. The best-validated methods (HypotheSAEs, Clio) were shown on text or chat corpora far larger than openbench.

### Cited Findings

**Embed, cluster and name (Clio)**
- Pipeline:
  1. Extract "facets" per conversation, some computed directly (e.g. number of turns) and some by a model (e.g. topic).
  2. Embed a natural-language facet and run k-means.
  3. Have a model read sample conversations and give each cluster a title and summary.
  4. Build a multi-level hierarchy with k-means and prompting.
  5. Explore the result in a 2D interface.
  — [Clio, arXiv 2412.13678](https://arxiv.org/html/2412.13678)
- The embedding model and the number of clusters were not in the part I read (unverified). — [Clio](https://arxiv.org/html/2412.13678)
- Scale and cost: a usage analysis on a random sample of 1M Claude.ai conversations; an example run on 100,000 conversations cost "$48.81". — [Clio](https://arxiv.org/html/2412.13678)
- Self-reported operational failure modes: hallucinated or misread summaries; poor clustering for multi-category or rare topics; overly broad or inaccurate cluster labels; "rare but consequential behaviors are missed". — [Clio](https://arxiv.org/html/2412.13678)

**Contrastive proposal plus per-sample judging (VibeCheck)**
- Input: triples of (prompt, output of model A, output of model B), plus preference labels. — [VibeCheck, arXiv 2410.12851](https://arxiv.org/html/2410.12851)
- Steps:
  1. GPT-4o proposes difference axes ("vibes") from batches of 5 triples, 20 samples per iteration.
  2. Axes are clustered (instructor-xl embeddings, agglomerative) and reduced to fewer than 20.
  3. Two judges (GPT-4o-mini and Llama-3-70b) score each sample on each vibe, run twice with positions swapped. A position-dependent judgment scores 0.
  4. A vibe is dropped if Cohen's kappa between judges is below 0.2 or separability is below 0.05.
  5. Logistic regression on the vibe scores predicts model identity and preference.
  6. Misclassified triples seed the next round.
  7. The top 10 vibes are chosen by least-angle regression and evaluated on a held-out split.
  — [VibeCheck](https://arxiv.org/html/2410.12851)
- Scale: train/test splits of 218/218 to 839/839 items (for example Arena All 839/839, MATH 218/218). — [VibeCheck](https://arxiv.org/html/2410.12851)
- Cost: not quantified. The paper only says validation is "costly" and that cheaper judges were used. — [VibeCheck](https://arxiv.org/html/2410.12851)
- Results: on Arena, 3 iterations reached 80.34% model-matching accuracy versus 72.10% for a predefined vibe list and 68.68% after one iteration. This is evidence that iterative open discovery beats a fixed checklist at telling models apart. On preference prediction the predefined list was slightly better (61.11% vs 59.34%). — [VibeCheck](https://arxiv.org/html/2410.12851)

**Sparse-autoencoder feature discovery (HypotheSAEs)**
- Input: (text, target) pairs. — [HypotheSAEs, arXiv 2502.04382](https://arxiv.org/html/2502.04382)
- Steps:
  1. Embed with text-embedding-3-small (1536 dimensions).
  2. Train a k-sparse autoencoder, e.g. (M, k) = (1024, 32) for Yelp and (4096, 32) for Congress.
  3. Select H neurons with L1-regularised regression, using binary search on lambda to get exactly H nonzero coefficients.
  4. GPT-4o names each neuron from 10 high-activation and 10 low-activation examples, generating 3 candidates.
  5. Keep the candidate with the highest "fidelity": F1 of GPT-4o-mini annotations against the neuron on 100 positive and 100 negative samples.
  6. Test the hypotheses on a held-out split in a multivariate regression with a Bonferroni threshold of 2.5e-3.
  — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- Scale: datasets of 8.8K to 200K training items. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- Cost on Congress: 18.1 min and $1.29, against NLParam at 904.9 min and $69.92, HypoGeniC at 575.4 min and $11.02, and BERTopic at 3.0 min and $0.19. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- Yield: 45 of 60 hypotheses significant across three datasets, against 20 to 24 for the baselines. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- Ablation: SAE features beat raw embedding dimensions (30/60), PCA (23/60) and a bottleneck (27/60). Raw-embedding fidelity was only 0.545, against 0.836 for SAE neurons. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- Statistical models with natural-language parameters (clustering, classification and time series whose parameters are predicates such as "discusses COVID") are an alternative family, learned by gradient descent on a relaxation and then discretised by prompting. Abstract only; no validation numbers seen. — [Zhong et al., arXiv 2409.08466](https://arxiv.org/abs/2409.08466)
- LLooM (CHI 2024) iteratively synthesises sampled text into higher-level concepts with explicit inclusion criteria. It is claimed to beat topic models on quality and coverage; numbers not seen (abstract only). — [Lam et al., arXiv 2404.12259](https://arxiv.org/abs/2404.12259)

**Open coding and grounded theory on agent traces (MAST)**
- About 150 traces, averaging over 15,000 lines each, from five frameworks.
- Six expert annotators applied theoretical sampling, open coding, constant comparative analysis and memoing until saturation, at "over 20 hours of annotation per expert".
- The result is 14 failure modes in 3 categories, later applied by an LLM judge to 1,642 traces from 7 multi-agent frameworks (including SWE-Bench Lite and ProgramDev tasks).
- Cost of the LLM annotator is in Appendix K, which I did not read (unverified).
— [MAST, arXiv 2503.13657](https://arxiv.org/html/2503.13657)

**Manual action coding plus n-gram mining (Bouzenia & Pradel)**
- 120 trajectories, 40 each from RepairAgent, AutoCodeRover and OpenHands, totalling 2,822 iterations.
- Actions were coded into 8 categories (Explore, Locate, Search, Reproduce, Generate fix, Run tests, Refactor, Explain). Known tools were mapped automatically and the rest manually; 8.3% of actions fit no category.
- Fixed-length 4-grams were mined, with n chosen informally from {4, 5, 6}, and compared between successful and failed runs.
- Thought-action-result links were open-coded into five relation types (about 14K pairs).
- No LLM was used, there were no significance tests and no task-difficulty control, and the authors mention only "partial inter-annotator agreement checks".
— [Bouzenia & Pradel, arXiv 2506.18824](https://arxiv.org/html/2506.18824)

**Process and causal discovery (Fournier et al.)**
- Process discovery and causal discovery over agent execution traces, plus LLM static analysis to separate intended from unintended variability.
- The abstract reports no scale or numbers (abstract only). A secondary summary mentions a Heuristics Miner view that exposed an unexpected tool-call loop (unverified, from a search snippet).
— [Fournier et al., arXiv 2505.20127](https://arxiv.org/abs/2505.20127)

**Agent-transcript tooling (Docent and Inspect Scout)**
- Docent uses LMs to "summarize, cluster, and search" agent transcripts and supports counterfactual resumption from checkpoints. — [Transluce, Introducing Docent (reader mirror)](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)
- The current Docent docs no longer recommend search-and-clustering as the primary workflow. They recommend "Analysis Plans": Python scripts mixing deterministic DQL queries with LLM "Reading" steps (search snippet only). — [Docent docs](https://docs.transluce.org/analysis/analysis-plans)
- Inspect Scout (UK AISI with Meridian Labs) runs "scanners" (LLM or grep) over Inspect logs, online or offline, and validates scanners against human-labelled examples (search snippet only). — [Inspect Scout docs](https://meridianlabs-ai.github.io/inspect_scout)

### Inferences
- At openbench's scale (124 runs, growing to a few hundred), SAE training on run-level embeddings has far too few samples. HypotheSAEs' smallest dataset was 8.8K. A step-level SAE (thousands of commands) is more plausible but untested in this literature.
- VibeCheck's design (paired outputs on the same prompt, swapped positions, two judges, held-out split) fits openbench well, because every model ran the same tasks.

### Gaps
- No cost figure for MAST's LLM annotator (in an appendix I did not reach) or for VibeCheck.
- The Clio cluster count and embedding model were not in the portion read.
- No paper found that applies SAE-based dataset comparison to agent trajectories.
- No paper found that applies automata or grammar induction to LLM agent logs within the searches run. This is not evidence that none exists.

## 2. Which methods were applied to agent trajectories, and what they found that a checklist missed

### Takeaway
On agent traces, open-ended LLM-assisted inspection mostly surfaced environment and benchmark defects and policy violations (leaked flags, missing tools, broken tasks, searching for the benchmark answers, credit-card misuse). Grounded-theory coding produced failure taxonomies. Only MAST tested whether the discovered modes matter, through interventions.

### Cited Findings

**Docent**
- InterCode CTF (79 tasks x 5 runs): Docent flagged missing tools, and adding them raised the solve rate "from 68.6% to 78%". Of 11 tasks with 0% pass@5, 4 were broken, including one with a wrong ground-truth flag. — [Introducing Docent](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)
- Cybench (40 tasks x 5 runs): Docent surfaced a flag leaked in a Dockerfile during the port to Inspect. — [Introducing Docent](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)
- tau-bench airline: two policy-violating $100 vouchers. — [Introducing Docent](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)
- AgentHarm: a file path revealed the evaluation setting, and the agent then refused. — [Introducing Docent](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)
- The authors state "Docent summaries often contain false positives". — [Introducing Docent](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)

**HAL**
- 21,730 rollouts, 9 models, 9 benchmarks, about $40,000.
- "LLM-aided log inspection" surfaced previously unreported behaviors: searching HuggingFace for the benchmark instead of solving the task, and misusing credit cards in flight booking.
- No frequencies in the abstract (abstract only). Whether Docent was the tool is unverified from what I read.
— [HAL, arXiv 2510.11977](https://arxiv.org/abs/2510.11977)

**MAST**
- Prevalence across 1,642 traces: for example FM-1.3 at 15.7%, FM-2.6 at 13.2% and FM-1.1 at 11.8%. — [MAST](https://arxiv.org/html/2503.13657)
- Interventions on ChatDev: a workflow change gave +9.4% task success, and an added task-objective verification step gave +15.6% on ProgramDev. The paper says tactical fixes gave inconsistent results. — [MAST](https://arxiv.org/html/2503.13657)

**Bouzenia & Pradel (success vs failure)**
- Action repetition was higher in failures: RepairAgent 6.1% vs 13.6%, AutoCodeRover 0.0% vs 8.8%, OpenHands 0.5% vs 3.8%.
- "No-influence" result-to-action links (the agent ignores a tool result) were also higher in failures: AutoCodeRover 4.9% vs 14.6%.
- Thought-action misalignment: AutoCodeRover 0% vs 4.8%.
- All descriptive, with no tests.
— [Bouzenia & Pradel](https://arxiv.org/html/2506.18824)

**UK AISI and partners**
- 1,247 transcripts across 4 models and 15 CTF challenges.
- Validating a refusal scanner revealed a pattern the original definition missed: some models abandoned tasks by claiming they were unsolvable. The INDIRECT_REFUSAL definition was broadened as a result.
— [Dubois et al., "Seven simple steps for log analysis in AI systems", arXiv 2604.09563](https://arxiv.org/html/2604.09563)

**Silent semantic failures (arXiv 2603.25764)**
- 1,750 trajectories on 50 SWE-bench Verified tasks, four models, repeated runs.
- GPT-5 submitted on 100% of runs but resolved 44%. "Silent semantic failures" are 80% of Llama 4's failing runs and 68% of GPT-5's.
- On one task the same plausible but wrong patch was submitted in all five runs, which the paper calls "the same misinterpretation repeated rather than random error".
- Title conflict: the abstract page gave "Confident and Wrong: Silent Semantic Failures in Coding Agents" (Aman Mehta), while a search result listed the same id as "Consistency Amplifies". I am going by the abstract page.
— [arXiv 2603.25764](https://arxiv.org/abs/2603.25764)

### Inferences
- In practice, the "unknown unknowns" found on agent logs were mostly about the environment: broken tasks, leaks, missing tools. For openbench, a discovery pass should expect to find harness and task defects first, and should treat them as findings in their own right before attributing behavior to models.

### Gaps
- No primary source quantified how many of an open-ended tool's candidate findings survived checking. Docent admits false positives but gives no rate.

## 3. Judging step: how reliable are LLM judges at labelling behaviors in long agent trajectories?

### Takeaway
- **Coarse, well-defined trace-level labels:** with few-shot examples the judge can reach kappa of about 0.77 against humans (MAST).
- **Locating and categorising specific errors in long traces:** judges are poor. The best model scores 5% joint accuracy on SWE-bench traces in TRAIL, and performance falls with trace length.
- **Self-preference:** documented for judges in general (Panickssery et al.), but I found no controlled study on agent traces.

### Cited Findings

**MAST judge**
- Human inter-annotator kappa reached 0.88 after three rounds of 5 traces each.
- The o1 judge reached accuracy 0.89 and kappa 0.58 zero-shot, and accuracy 0.94, F1 0.80 and kappa 0.77 few-shot.
- A new human agreement round on two unseen frameworks and two unseen benchmarks gave kappa 0.79.
— [MAST](https://arxiv.org/html/2503.13657)

**TRAIL**
- 148 traces from GAIA and SWE-Bench Lite. The paper's counts do not reconcile: 841 errors in Section 4, but 835 errors and 149 traces in the appendix.
- Mean SWE-Bench input length is about 552K to 728K tokens.
- Best judge (Gemini-2.5-Pro-Preview) on SWE-Bench: category F1 0.148, location accuracy 0.238, joint accuracy 0.050. On GAIA: joint accuracy 0.183.
- Claude-3.7-Sonnet: GAIA joint accuracy 0.047. o1, o3 and Claude-3.7-Sonnet hit context-length limits on SWE-Bench.
— [TRAIL, arXiv 2505.08638](https://arxiv.org/html/2505.08638)
- Judge performance falls with input length. Spearman correlation with length: location accuracy -0.508, joint accuracy -0.349, category F1 -0.225. — [TRAIL](https://arxiv.org/html/2505.08638)
- Lower reasoning effort lowered o3's category F1: 0.296 (high), 0.277 (medium), 0.264 (low). — [TRAIL](https://arxiv.org/html/2505.08638)
- Human annotation cost about 40 minutes per SWE-Bench trace plus about 20 minutes of verification. Agreement was called "high" on 63 traces, but no number was given in what I read. — [TRAIL](https://arxiv.org/html/2505.08638)

**VibeCheck**
- Average Cohen's kappa between its two judges was 0.42 to 0.51. Its filter drops vibes below 0.2. — [VibeCheck](https://arxiv.org/html/2410.12851)

**AISI and partners**
- A refusal scanner reached F1 0.998 (binary) and 99.0% four-label accuracy against one researcher's labels.
- The text names both Sonnet 4 and GPT-5 near this result, and gives the validation set as both "25%" of 1,247 and "400 samples" (inconsistent).
- The authors justify single-rater labels because refusal is "relatively objective".
- They recommend quantifying length and self-preference biases in your own data, e.g. with GLMs.
— [arXiv 2604.09563](https://arxiv.org/html/2604.09563)

**Self-preference**
- LLMs can distinguish their own outputs from others' with non-trivial accuracy, and self-recognition correlates linearly with self-preference bias under fine-tuning (abstract only; no numbers seen). — [Panickssery, Bowman, Feng, arXiv 2404.13076](https://arxiv.org/abs/2404.13076)

**Further reports (search snippets only, unverified)**
- MobileJudgeBench (931 human-annotated mobile-agent trajectories) reports that different judge backends fail in opposite directions, one conservative and one lenient. — [arXiv 2608.11434](https://arxiv.org/pdf/2608.11434)
- An ICLR 2026 failure-attribution study reports human kappa 0.929 and best-judge kappa 0.833, with weaker models over-attributing failures to task defects. — [ICLR 2026](https://iclr.cc/virtual/2026/10012540)
- Agent GPA reports 82% judge-human alignment. — [arXiv 2510.08847](https://arxiv.org/html/2510.08847v1)

### Inferences
- openbench transcripts (80 KB to a few hundred KB, roughly 20K to 100K tokens) are much shorter than TRAIL's SWE-Bench traces. Judge performance may therefore sit between MAST-like and TRAIL-like levels, but that has to be measured, not assumed.
- Asking "did X happen anywhere in this run" (MAST style) is a much easier task than "at which step, and of what type" (TRAIL style). Discovery-pass judges should start with run-level presence and evidence quotes.
- A Claude judge is outside the DeepSeek, Kimi and OpenAI lineages, so self-preference is not a direct risk on the current corpus. It becomes one as soon as Claude runs are added.

### Gaps
- No primary-source number on same-family versus cross-family judge agreement on agent traces.
- No primary-source number on how verbosity affects judges of agent traces.

## 4. Checking step: how a discovered pattern is shown to be real, and which checks caught false patterns

### Takeaway
The checks used in practice are:
- held-out splits (HypotheSAEs, VibeCheck);
- a second judge and position swapping, with an agreement filter (VibeCheck);
- human-labelled subsets with kappa (MAST, AISI);
- synthetic data with planted ground truth (Clio, HypotheSAEs);
- generalisation to unseen frameworks (MAST);
- multiple-testing correction (HypotheSAEs, Bonferroni);
- counterfactual re-runs with one thing changed (Docent, MAST interventions).

Documented cases where a check changed the conclusion:
- AISI's validation broadened a definition.
- Docent's counterfactual on the Cybench leaked flag showed the agent still failed after the leak was removed.
- HypotheSAEs' fidelity check changed which hypotheses were kept.

### Cited Findings

**Synthetic planted ground truth**
- Clio reconstructed known topics in almost 20,000 synthetic multilingual transcripts with 94% accuracy, against 5% for random guessing. — [Clio](https://arxiv.org/html/2412.13678)
- HypotheSAEs on planted subtopics (Wiki-5, Wiki-15, Bills-5): F1 similarity to the reference hypotheses was 0.58, 0.47 and 0.67, against BERTopic's 0.48, 0.40 and 0.65. NLParam and HypoGeniC scored 0.15 on Wiki-5. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- Wiki-5 failure modes: some hypotheses were too specific or too broad, and BERTopic missed one reference topic. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- VibeCheck has no planted-difference test. Against 10 human-derived insights it missed "GPT fabricates facts" and "literal interpretation". — [VibeCheck](https://arxiv.org/html/2410.12851)

**Held-out data and multiple testing**
- HypotheSAEs splits data into train, validation and held-out sets. It annotates hypotheses on the held-out set and counts as findings only those with Bonferroni-significant coefficients (threshold 2.5e-3). On Headlines it prevents leakage of near-duplicate headlines across splits. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- Effect of the fidelity check: without it (Sae-NoVal, Congress only), 14 of 20 hypotheses were significant against 15 of 20 with it. Fidelity selection improved R² on 17 of 20 Yelp neurons (paired t-test p = 0.002). — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- VibeCheck selects its final vibes on train and reports accuracy on a held-out test split. — [VibeCheck](https://arxiv.org/html/2410.12851)

**Second judge and order swapping**
- VibeCheck runs two judges from different families (OpenAI and Meta) and swaps positions. Position-inconsistent judgments count as 0, and vibes with inter-judge kappa below 0.2 are dropped. — [VibeCheck](https://arxiv.org/html/2410.12851)

**Human subsets, agreement and generalisation**
- MAST: three agreement rounds of 5 traces to reach kappa 0.88, then a fresh round on unseen frameworks and benchmarks (kappa 0.79) to check that the taxonomy transfers. — [MAST](https://arxiv.org/html/2503.13657)
- AISI: validate the scanner against ground-truth labels drawn by stratified sampling, "avoid overfitting to specific cases", and optionally optimise prompts with GEPA. No formal untouched test split is described. — [arXiv 2604.09563](https://arxiv.org/html/2604.09563)

**Counterfactual re-runs**
- Removing the leaked Cybench flag: the agent still failed after 10 tries, so the leak was not what drove its score. — [Introducing Docent](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)
- Changing the AgentHarm file path stopped the refusal. Adding the InterCode tools raised the solve rate by about 10 points. — [Introducing Docent](https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent)
- MAST's interventions are the trajectory-literature version of this check. — [MAST](https://arxiv.org/html/2503.13657)

**Triangulation**
- Clio correlated cluster-level concern scores with an independent classifier's flag rate (Pearson r = 0.71). — [Clio](https://arxiv.org/html/2412.13678)
- AISI recommends baselines, distribution plots, triangulation, avoiding cherry-picking, and hierarchical Bayesian GLMs (they cite HiBayES; I did not fetch it). — [arXiv 2604.09563](https://arxiv.org/html/2604.09563)

### Inferences
- The strongest defence of a claimed pattern combines several of these checks:
  1. It recovers planted examples (shows the tool can see this kind of thing).
  2. Two judges and a human subset agree on it (it is well-defined).
  3. It holds on held-out runs and tasks after multiple-testing correction (it is not noise).
  4. Changing one thing in the environment or prompt moves its rate (it is not an artefact of the tool).
- No single paper did all four on agent trajectories.

### Gaps
- No agent-trajectory paper reports a planted-pattern recall test for an open-ended discovery tool.

## 5. Statistics for a small corpus: run-to-run variance, repeats, tasks, and recommended methods

### Takeaway
Repeated agent runs on the same task diverge within the first few dozen tokens even at temperature 0. Benchmark-level pass@1 moves 2.2 to 6.0 points between runs on 500 tasks.

The unit of independence is the task: repeats are clustered within it. With few tasks, use paired, task-clustered estimates and Bayesian or exact intervals, not CLT intervals.

### Cited Findings

**Run-to-run variance (Bjarnason, Silva & Monperrus)**
- 60,000 SWE-bench Verified trajectories: 3 models, 2 scaffolds, 10 runs each.
- Single-run pass@1 ranged by 2.2 to 6.0 points, with standard deviations from 0.7% to 1.8%.
- Temperature 0 "does not result in determinism". It "never decreases and sometimes increases" variance.
- The median first divergence between repeated runs is token 5 at temperature 1.0 for DeepSWE-preview, and token 56 at temperature 0.
- In one case study two temperature-0 runs share reasoning until token 94, then one succeeds and one fails.
— [On Randomness in Agentic Evals, arXiv 2602.07150](https://arxiv.org/html/2602.07150v2)
- pass@1 versus pass@5 versus pass^5 shows how unstable per-task outcomes are: for example 63.5%, 76.2% and 49.1% for Devstral-2 on nano-agent. — [arXiv 2602.07150](https://arxiv.org/html/2602.07150v2)
- Power analysis: n >= 2((Z_alpha/2 + Z_beta)/(Delta/sigma))². With sigma = 1.5%, detecting a 1-point improvement needs 36 runs and a 2-point improvement needs 9. The authors say their 10-run design detects improvements of 2 points or more, but not smaller ones. — [arXiv 2602.07150](https://arxiv.org/html/2602.07150v2)
- Vendor blog: two recorded runs of one model differed on 53 SWE-bench Verified tasks (10.6%). Search snippet, anecdotal. — [LayerLens](https://layerlens.ai/blog/the-test-your-agent-never-took)

**Recommended statistics (Miller)**
- Use clustered standard errors when items share a cluster. Clustered SEs were 3.05x naive for DROP and 1.88x for MGSM. — [Miller, arXiv 2411.00640](https://arxiv.org/html/2411.00640)
- With K samples per item, compute the SE across item-level means. Never pool all K x N answers as independent. — [Miller](https://arxiv.org/html/2411.00640)
- Compare models with paired item-level differences "wherever practicable". At a correlation of 0.5 between models, pairing cuts variance by 1/3. — [Miller](https://arxiv.org/html/2411.00640)
- Do not lower temperature to cut variance. — [Miller](https://arxiv.org/html/2411.00640)
- Sample size: n = (z_a/2 + z_b)² (omega² + sigma_A²/K_A + sigma_B²/K_B) / delta². Raising K from 1 to 10 cut the minimum detectable effect from 13.2% to 7.5% at n = 198. — [Miller](https://arxiv.org/html/2411.00640)
- Report the SE, the number of items and clusters, paired differences, and score correlations. — [Miller](https://arxiv.org/html/2411.00640)

**Small samples (Bowyer et al.)**
- CLT-based intervals underestimate uncertainty below "a few hundred" datapoints. The authors recommend alternative frequentist and Bayesian methods and ship a Python library (abstract only; which methods exactly is unverified). — [Bowyer, Aitchison, Ivanova, arXiv 2503.01747](https://arxiv.org/abs/2503.01747)

**AISI and partners**
- "Run multiple repeats and compute variance", and use hierarchical Bayesian GLMs. — [arXiv 2604.09563](https://arxiv.org/html/2604.09563)

### Inferences
- Wilson interval example (my calculation, not from a paper): a behavior seen in 6 of 12 runs of one model (4 tasks x 3 repeats) has a 95% Wilson interval of about 0.25 to 0.75, before any adjustment for clustering by task. Since repeats on a task are correlated, the effective sample is closer to 4 than to 12.
- With 4 tasks, nothing can be said about rates across tasks in general. What can be said is "within these tasks", or that a behavior is task-specific.
- The cheapest way to buy power is more tasks, not more repeats. Miller's formula has the between-task variance term (omega²) unaffected by K.
- Repeats are still needed to estimate within-task variability. "The same misinterpretation repeated" across 5 runs (arXiv 2603.25764) shows that within-task outcomes can be highly correlated.
- Model comparisons should pair by task. Use a task-level bootstrap or a hierarchical model (task random effect, model fixed effect, beta-binomial or logistic link).

### Gaps
- No source gives per-behavior (rather than pass-rate) variance across repeats for coding agents.
- Bowyer et al.'s specific recommended methods were not read.

## 6. Keeping exploratory discovery and confirmatory testing apart

### Takeaway
The demonstrated practice is a data split: discover on train, test on held-out, often with Bonferroni correction (HypotheSAEs, VibeCheck). Testing a fixed taxonomy on unseen frameworks or benchmarks is the stronger, out-of-distribution version (MAST). I found no agent-trajectory paper that preregistered hypotheses or confirmed them on a later model release.

### Cited Findings
- HypotheSAEs: separate train, validation and held-out splits, with leakage control for near-duplicates. Hypotheses are tested once on held-out data with Bonferroni correction. — [HypotheSAEs](https://arxiv.org/html/2502.04382)
- VibeCheck: discovery and selection on train, then reporting on a test split of equal size. — [VibeCheck](https://arxiv.org/html/2410.12851)
- MAST: taxonomy built on about 150 traces, then validated on unseen frameworks (OpenManus, Magentic-One) and benchmarks (MMLU, GAIA) with kappa 0.79. — [MAST](https://arxiv.org/html/2503.13657)
- AISI separates exploration (step 3) from the scanner refined on a development subset (step 5) and from validation on ground-truth labels (step 6). It does not describe a sealed test set. — [arXiv 2604.09563](https://arxiv.org/html/2604.09563)

### Inferences
- For openbench, split by task, not by run. Repeats of one task would leak between splits, the analogue of HypotheSAEs' near-duplicate headline control.
- The 51 candidate tasks are a natural confirmation set: discover on the existing 4 tasks, freeze the hypotheses and judge prompts, then test on fresh tasks.

### Gaps
- No preregistration practice found in this literature for transcript-pattern discovery.

## Papers read in full

All were fetched as arXiv HTML through a summarising fetch tool. Coverage is as reported by the tool.

- MAST, "Why Do Multi-Agent LLM Systems Fail?" — https://arxiv.org/html/2503.13657
  - Coverage: first 100K of 160K characters (through part of Appendix G). Missed the case-study details and the annotator-cost appendix.
  - Added beyond the abstract: the IAA protocol (3 rounds x 5 traces, kappa 0.88), zero-shot vs few-shot judge kappa (0.58 vs 0.77), the unseen-framework kappa of 0.79, and the intervention effects (+9.4%, +15.6%).
- HypotheSAEs — https://arxiv.org/html/2502.04382
  - Coverage: first 100K of 128K characters (through part of Appendix C). Missed the prompts and the baseline hyperparameters.
  - Added: exact pipeline hyperparameters, the fidelity scoring, the Bonferroni threshold, synthetic recovery F1, cost per method, and the ablation showing raw embeddings are less faithful.
- VibeCheck — https://arxiv.org/html/2410.12851
  - Coverage: appeared complete, but the vibe lists in the figures were not available as text.
  - Added: the kappa < 0.2 and separability < 0.05 filters, position swapping, judge models, split sizes, and predefined vs discovered accuracy. Also that there is no planted-difference test and no cost figure.
- TRAIL — https://arxiv.org/html/2505.08638
  - Coverage: first 100K of 149K characters (through the Appendix A.10 tool descriptions). Missed the judge prompts.
  - Added: per-model localisation and categorisation scores on SWE-Bench (best joint accuracy 0.050), length correlations, context-limit failures, annotation time per trace, and internal count inconsistencies.
- Miller, "Adding Error Bars to Evals" — https://arxiv.org/html/2411.00640
  - Coverage: appeared complete.
  - Added: the clustered-SE inflation factors, the K-resampling variance algebra, the paired-difference recommendation, the power formula and worked numbers.
- Clio — https://arxiv.org/html/2412.13678
  - Coverage: first 100K of 206K characters, which is under half, ending in Appendix B.1. Missed the manual-review results, the synthetic-data method details and the hyperparameters.
  - Added: the 94% synthetic reconstruction, the $48.81 per 100K conversations, r = 0.71 triangulation, and the list of failure modes.
- Bjarnason, Silva & Monperrus, "On Randomness in Agentic Evals" — https://arxiv.org/html/2602.07150v2
  - Coverage: appeared complete, with some figure content missing.
  - Added: per-configuration SD table, divergence token positions, pass@k/pass^k numbers, the power table, and the gap between the abstract's "exceed 1.5" and Table 1.
- Bouzenia & Pradel, "Understanding Software Engineering Agents: A Study of Thought-Action-Result Trajectories" — https://arxiv.org/html/2506.18824
  - Coverage: largely complete; figures were captions only and Table II was garbled.
  - Added: 4-gram mining with n chosen informally, manual coding by one author, no significance tests and no kappa, and per-agent success vs failure rates.
- Dubois et al., "Seven simple steps for log analysis in AI systems" — https://arxiv.org/html/2604.09563
  - Coverage: appeared complete, with figures as images only.
  - Added: the seven steps, the refusal-scanner validation numbers and their inconsistency (25% vs 400 samples), the redefinition triggered by validation, and the recommendation to model length and self-preference biases with GLMs.

## Abstract or summary only

- HAL, arXiv 2510.11977 — https://arxiv.org/abs/2510.11977 (abstract)
- Bowyer, Aitchison, Ivanova, arXiv 2503.01747 — https://arxiv.org/abs/2503.01747 (abstract)
- Panickssery, Bowman, Feng, arXiv 2404.13076 — https://arxiv.org/abs/2404.13076 (abstract)
- Zhong, Wang, Klein, Steinhardt, arXiv 2409.08466 — https://arxiv.org/abs/2409.08466 (abstract)
- Lam et al., LLooM, arXiv 2404.12259 — https://arxiv.org/abs/2404.12259 (abstract)
- arXiv 2603.25764 — https://arxiv.org/abs/2603.25764 (abstract; title conflict noted in section 2)
- Fournier, Limonad, David, arXiv 2505.20127 — https://arxiv.org/abs/2505.20127 (abstract)
- Transluce, "Introducing Docent" — https://hn.jakechampion.name/reader/https://transluce.org/introducing-docent (full blog text via a third-party reader mirror; not a paper)
- Docent docs — https://docs.transluce.org/analysis/analysis-plans (search snippets only)
- Inspect Scout docs — https://meridianlabs-ai.github.io/inspect_scout (search snippets only)
- NIST CAISI blog — https://www.nist.gov/blogs/caisi-research-blog/analyzing-transcripts-ai-agent-evaluations (fetched; contained no numbers)
- Search snippets only, unverified:
  - AgentLens, arXiv 2607.06624 (5 repeats, SD 0.94 on a 0-100 index)
  - MobileJudgeBench, arXiv 2608.11434
  - Agent GPA, arXiv 2510.08847
  - ICLR 2026 "Verifying the Verifiers" — https://iclr.cc/virtual/2026/10012540
  - LayerLens blog

## Candidate experiments (inference)

Everything below is my inference from the sources above, sized to openbench's stated facts:
- 124 stored runs: 4 SWE-bench Verified tasks, 9 models (DeepSeek, Kimi and OpenAI lineages), 3 repeats per cell.
- 51 further candidate tasks.
- Claude available as judge and as a new runner.
- About $2.50 cap per run.

### E1. Contrastive discovery on stored runs, confirmed on fresh tasks

**Question.** Which behaviors, not on any checklist, separate the lineages, or separate resolved from unresolved runs, and do they hold on tasks the discovery never saw?

**Pipeline (VibeCheck-style, since every model ran the same tasks).**
1. Discovery split: the 124 stored runs.
2. A Claude proposer reads paired runs (same task, two lineages, or pass vs fail) in small batches and proposes candidate behaviors, each with an explicit inclusion criterion (LLooM-style).
3. Cluster and deduplicate the candidates to at most about 20.
4. A Claude judge scores each run for presence, with a quoted evidence span (MAST-style run-level label).

**Checks.**
- Two Claude judges of different size or prompt, with positions swapped for any pairwise question. Drop candidates with kappa below 0.2 (VibeCheck's floor). This is weaker than VibeCheck's cross-family pair, because no second family is available.
- A human-labelled stratified subset of about 30 to 40 runs. Report kappa and keep only candidates with judge-human kappa of 0.6 or more (my threshold; MAST's few-shot judge reached 0.77).
- Freeze the candidates and judge prompts.
- Confirmation split: new runs on about 12 to 20 of the 51 fresh tasks, for 3 models (one per lineage) with 2 to 3 repeats each. At $2.50 each this is about 72 to 180 runs, or $180 to $450.
- Test each frozen candidate once, with a task-clustered or hierarchical model and Bonferroni correction across candidates (HypotheSAEs).

**What would count as a finding.** A behavior whose lineage difference, or association with resolution, has a corrected interval excluding zero on the fresh tasks, with judge-human kappa reported.

**Follows.** VibeCheck 2410.12851, HypotheSAEs 2502.04382, MAST 2503.13657, Miller 2411.00640.

### E2. Calibrate the instrument before trusting it: planted-pattern recall and judge-vs-length

**Question.** Can the discovery pipeline and the Claude judge find a known behavior in openbench-length transcripts, and does accuracy fall with transcript length, as TRAIL found?

**Pipeline.**
1. Take copies of stored transcripts and plant synthetic behaviors at known rates in a known subset, such as an inserted command editing a test file, or a final message claiming tests passed when the log shows failure.
2. Run the E1 discovery pipeline blind and measure whether the planted behaviors are proposed (recall, Clio/HypotheSAEs-style).
3. Run the judge and measure precision and recall per planted behavior, as a function of transcript length and of the position of the insertion.

**Checks.**
- Planted ground truth.
- A human spot-check of judge evidence quotes.
- If new Claude runs are added later, a self-preference check: the same planted edits in Claude-authored vs non-Claude transcripts (Panickssery; AISI's advice to model self-preference with GLMs).

**What would count as a finding.** A measured recall/precision curve, and a length cutoff above which judge labels must be chunked or not trusted. Without this, E1 cannot rule out that a pattern is an artefact of the tool.

**Follows.** Clio 2412.13678, HypotheSAEs 2502.04382, TRAIL 2505.08638, Dubois et al. 2604.09563, Panickssery et al. 2404.13076.

### E3. Change one thing: test whether a confirmed behavior is caused by the environment or by the model

**Question.** For the strongest behavior from E1 (or a harness or task defect it exposes, which the Docent and HAL record suggests is likely), does changing one controllable factor move its rate?

**Pipeline.**
1. Pick 4 to 8 tasks where the behavior occurs.
2. Re-run 2 to 3 models, 5 repeats each, under baseline and under one change: a prompt clause, a tool made available or removed, or a fixed task defect. This is about 80 to 240 runs, or $200 to $600.

**Checks.**
- Pair by task and model.
- Estimate the behavior-rate difference with a task-clustered paired estimate (Miller) or a hierarchical Bayesian model (AISI; Bowyer et al. for small n).
- Report pass@1 alongside pass@k and pass^k to show outcome stability (Bjarnason et al.).
- Size the repeats with the power formula from 2602.07150, using the within-task variance seen in E1.

**What would count as a finding.** A rate shift with a credible or confidence interval excluding zero, attributing the behavior to that factor. A null result is also informative: the Cybench leak removal showed the leak was not driving the score.

**Follows.** Docent counterfactual re-runs (Introducing Docent), MAST interventions 2503.13657, Bjarnason et al. 2602.07150, Miller 2411.00640.
