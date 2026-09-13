# Research questions

The seven questions from the project brief, with where each one actually stands.
Claims marked **measured** come from `results/report.json`; claims marked
**implemented, unmeasured** describe a mechanism whose benefit has not been
demonstrated.

---

## 1. How can multiple cognitive processes compete for attention without rigid workflows?

**Approach.** Processes propose scored intentions into a shared pool; a swappable
priority strategy ranks them; one wins per tick. Weights are modulated by internal
drives, biased by a learned per-kind term, and adjusted by support, habituation and
commitment. Identical proposals from independent processes merge and gain support
rather than competing with themselves.

**Measured.** The rigid alternative fails badly: `fixed_pipeline` — strict
precedence by intention kind — returns **0.0 across all eight seeds**, attention
entropy exactly 0, because noisy sensors generate contradictions faster than a
"resolve contradictions before pursuing goals" rule can clear them. The same
intention set chosen uniformly at random returns 4.4; under the economy, 44.9.
Competition among heterogeneous proposals is strongly supported.

**Counter-evidence about our own scoring.** The sophistication is not what helps.
Drive-modulated weights return 24.1 against 44.9 for fixed weights, and the learned
per-kind bias is actively harmful — removing it is the best architecture measured
(54.6 mean, 59.5 median against 44.9 / 17.5). What earns its place is the
competition itself, not the cleverness of the ranking function.

**Open.** Preemption margin, commitment and habituation are three knobs that all
control thrash. We have not isolated their individual contributions.

---

## 2. How can an agent generate goals dynamically from gaps in its world model?

**Approach.** Two mechanisms, both reasoning over declared capabilities: regression
over tool preconditions produces `KNOW` goals for unknowns; relaxed planning
produces `ACHIEVE` goals for blockers. A third case — an exhausted frontier behind
a barrier — turns an obstacle into a dependency.

**Measured.** 6.4 emergent goals per run under `full`, 9.6 under the
best-performing architecture, forming chains up to four levels deep. The canonical chain (thread → its location → reach the vault → hold
the gold key → find the gold key) assembles with nothing scripted.

**Limitation.** Gap analysis is sound but shallow: it recurses over `requires` and
`knowledge` declarations and would not discover a dependency the tool author did
not declare. This is the boundary between engineered capability and emergent
behaviour, and it is a real one.

---

## 3. How do you measure autonomy in agentic systems?

**Approach.** Eight metrics: self-initiated actions, emergent goals, knowledge gaps
resolved, strategy adaptations, topology changes, reflection events, uncertainty
reduction, goal progress rate.

**Finding, and a warning.** Several of these are trivially gamed. `reflection_events`
is the clearest case: `fixed_pipeline` produces **798 reflections against the full
architecture's 48** and achieves nothing — reflection there is scheduled, so the
count measures the schedule rather than the cognition. `random_attention` produces
350 for the same reason: cheap internal intentions win often when selection is
uniform. A high autonomy count is not evidence of autonomy.

See [autonomy/metrics.md](../autonomy/metrics.md) for how each metric can be
inflated. We think the honest summary is: these metrics are *diagnostics*, useful
alongside task outcome, and worthless as an objective.

---

## 4. How can a system detect stagnation and change its own strategy?

**Approach.** A performance monitor computes progress, information gain, failure
rate, attention entropy and tool mix over a rolling window; diagnoses are emitted
in the brief's own language; each diagnosis maps to decision points whose
alternatives the adaptation loop can trial. Adoption requires the *system's*
reward-plus-information per tick to improve by more than the pooled noise between
matched windows.

**Measured, and mixed.** Stagnation detection works — the monitor reliably
diagnoses `STAGNATION` and `PLANNING_INEFFECTIVE` on the seeds where the agent sits
in an energy-poverty trap. Adaptation adopts **0.8 variants per run**. Comparing
`no_attention_learning` (adaptation on, 54.6) with `static_weights` (adaptation and
learning both off, 33.5) hints that adaptation helps — but that is a two-factor
inference from a one-factor design, and `no_metacognition` at 39.1 points the other
way. Undetermined.

Two honest diagnoses of our own mechanism: the trial length (12 uses) gives too few
samples against a very noisy signal, and an earlier version that judged candidates
by per-intention reward reliably adopted *worse* strategies, because a strategy can
make its own intentions look cheap while costing the system its opportunities. The
current system-level criterion with a noise threshold is more defensible and adopts
far less.

---

## 5. How can dynamic agent architectures self-organize?

**Approach.** Complexity pressure proposes a team; the proposal competes; units add
focused proposals and command nothing; dissolution writes outcomes to memory.

**Measured.** Teams form, contribute and dissolve for legible reasons: 61.1
topology changes per run. Under the current configuration `no_organization` returns
18.4 against 44.9 — a large and consistent gap, where our earlier configuration
showed none. Suggestive, not conclusive at n=8.

Note the counter-example that keeps this honest: `no_curiosity` produces the
*highest* topology churn of any architecture (146.6) and returns 1.0. Churn is not
organization.

---

## 6. How can episodic memory influence future decisions?

**Approach.** Episodes carry reward, information gain and surprise; consolidation
folds them into statistics by signature; those statistics feed the
`historical_success_rate` feature and therefore attention. Failure records are
diagnosed by cause and become lessons that trigger adaptation requests.

**Measured, and the answer is a shrug.** The `no_memory_feedback` ablation zeroes
`historical_success_rate` while leaving memory otherwise intact — it still records,
consolidates, diagnoses failures and drives adaptation. Result: 24.1 mean / 20.0
median against 44.9 / 17.5. Lower mean, marginally higher median, far lower
variance. Past success rates shape the upper tail of the distribution rather than
the typical run.

We would not describe episodic memory as demonstrated to improve decisions here.
The path from experience to attention is closed, tested and instrumented; its value
is unproven.

---

## 7. How do you separate engineered capability from emergent behaviour?

**Approach.** The separation is enforced structurally: environments declare schema,
tools, sources and initial goals, and nothing in `core/`, `intentions/`, `goals/`
or `cognition/` is environment-aware. No cognitive process calls another. There is
no branch anywhere of the form "if X happened, do Y".

**Honest boundary.** The line is real but not absolute. Feature *functions* — how
`expected_value` is computed for an exploration intention, say — are engineered,
and they shape behaviour strongly. What is emergent is the *arbitration*: which
pressure wins, when, and what chain of goals that produces. We would describe the
result as engineered motivation with emergent behaviour, which is a weaker and more
accurate claim than the tagline.
