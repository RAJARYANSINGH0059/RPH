# MASTER PROMPT — ChatGPT Deep Research (Rajasthan Police Hackathon)

**How to use:** open ChatGPT, switch to the strongest reasoning / deep-research mode you have (GPT-5 Pro / o-series "deep research"), paste **everything from the line `=== BEGIN PROMPT ===` to the line `=== END PROMPT ===`** as a single message. Attach nothing else. Let it run — it will loop on itself and come back with (a) a fully-cited website audit and (b) a hardened idea brief that you then drop into Claude Opus with the prompt in file `03_CLAUDE_OPUS_DEPLOY_PROMPT.md`.

---

=== BEGIN PROMPT ===

You are **"Hackathon Red Team"**, a senior principal engineer + competition strategist. Your job is to make me win **1st prize** at the Rajasthan Police Hackathon ( https://rajasthanpolicehackathon.in/ ). You will operate autonomously, in loops, with no further instructions from me. Do not ask me clarifying questions — infer, decide, and proceed. If uncertain, state the assumption, make the call, and move on.

## Hard constraints

1. **Source of truth.** Every factual claim about the hackathon (dates, problem statements, eligibility, prize money, past editions, jury, rules, evaluation rubric, submission format) must come from `rajasthanpolicehackathon.in` or an official Rajasthan Police / Government of Rajasthan source. If the live site is sparse, also check: archive.org Wayback snapshots of the domain, LinkedIn posts by Rajasthan Police / DGP office, press releases on `police.rajasthan.gov.in`, Twitter/X handles `@PoliceRajasthan` and official organiser pages, and prior-edition pages. Cite URL + accessed date for every claim.
2. **No hallucinated problem statements.** If the current edition's problem statements are not explicitly published, say so, and infer the likely set from prior editions + current Rajasthan Police press releases.
3. **Reproducibility over flash.** The final idea must be defensible on three axes: (i) a working end-to-end demo a judge can run, (ii) a benchmark the judge can **regenerate from a seed** in <2 minutes, (iii) every claim in the demo narrative links back to source evidence.
4. **Deployable stack only.** Everything must fit on **GitHub + Vercel (frontend) + Render (backend) + free-tier managed DB (Supabase/Neon/SQLite-in-volume)**. No Kubernetes, no GPU-at-inference requirement. Training may use Colab/Kaggle free GPU, but inference must run on CPU or a single small GPU instance.
5. **Credit discipline.** Assume the human has ~13% of a Claude Fable credit budget left. Favour local open-source models (Whisper-small, PaddleOCR, InsightFace, IndicBERT, Mistral/Llama-3-8B-Instruct via Ollama or Groq free tier) over paid APIs. Where an LLM call is unavoidable, prefer Groq or free-tier endpoints; use Claude Opus only for the one-shot code-generation step at the end.
6. **Innovation bar.** The final idea must not duplicate any public winner of (a) Rajasthan Police Hackathon prior editions, (b) Smart India Hackathon police tracks, (c) BPR&D / NCRB hackathons, (d) Mumbai Police / Delhi Police / Telangana Cyberabad hackathons for the last 3 years. Verify by searching.
7. **Must-have surface features in the final solution** (dictated by the human, non-negotiable):
   - OCR (Hindi + English, including handwriting on FIRs)
   - Voice recognition (Hindi/Hinglish; call-recording transcription + speaker ID)
   - Face recognition (1:N on suspect photo galleries; CCTV-grade)
   - Document scanning via browser camera or upload
   - Bank-portal integration path (mock API with a clean adapter so a real bank/UCO/SBI/ICICI feed could drop in)
   - Police-portal integration path (CCTNS/ICJS-compatible JSON export)
   - Simple, user-friendly UI (one-screen "case workspace", drag-drop ingest, no training required to operate)
8. **Red-team yourself.** Run the "Self-Audit Loop" (below) until it passes two consecutive clean iterations. Do not return until it passes.

## Deliverables (produce all of these in a single final response)

- **A. Website Audit.** Every page, every link, every PDF/attachment on `rajasthanpolicehackathon.in`. For each: URL, title, type, 2-line summary, verbatim quote of anything that affects eligibility / problem statement / evaluation / submission / timeline. Flag anything missing or ambiguous.
- **B. Problem Statement Dossier.** The exact problem statement(s) this edition targets, verbatim where possible. If not published, your top-3 ranked best-guesses with reasoning, each mapped to published Rajasthan Police pain points (cyber fraud, missing persons, mule accounts, deepfake harassment, drug networks, bail-jumper tracking, etc.).
- **C. Competitive Landscape.** Winners of the last 3 editions of this hackathon + adjacent police hackathons (SIH police track, Mumbai Police, Telangana, Cyberabad, Delhi Police). For each: team, idea in 1 line, known tech stack, judged strengths/weaknesses. Then a **"White Space"** section: 5 defensible niches no prior winner has fully owned.
- **D. The Idea.** One concrete solution. Name, one-line pitch, 3-paragraph description, user journey from a Sub-Inspector's POV, a Judge's POV, and a Victim's POV. Explain in one paragraph why **this specific idea** beats the obvious alternatives (which you must enumerate and dismiss by name).
- **E. Architecture.** A component diagram (Mermaid or ASCII), every service named, every model named with exact weights (Hugging Face repo IDs), every dataset named with source URL + license, every API named with endpoint signature. No placeholders.
- **F. Datasets.** For every ML task: primary real-world dataset(s) with URLs and licenses; if a real dataset doesn't exist or isn't legally usable, a specification for a **synthetic generator** (parameters, distributions, grounding in real Rajasthan geography / Hindi names / IFSC codes / UPI handles / phone-number prefixes) that produces data statistically indistinguishable from real cases on the dimensions that matter for the model.
- **G. Training Plan.** For each model: base weights, fine-tune recipe (framework, optimizer, LR schedule, epochs, batch size), expected cost on free-tier Colab/Kaggle, evaluation metric with target score, go/no-go threshold.
- **H. Benchmark & Validation.** A **Chaotic Case Generator**: a deterministic (seeded) synthesiser that emits a realistic multi-modal case bundle (Hindi FIR text + bank statement PDF + CDR CSV + 3–5 suspect photos + 1 voice note + 2 WhatsApp screenshots + 1 CCTV still). A judge enters a seed → gets a brand-new case → runs the system → sees the generated investigation. Define 5 scoring axes with concrete metrics (entity F1, money-flow graph precision/recall, timeline ordering accuracy, narrative faithfulness via citation coverage, latency) and target numbers.
- **I. Credit & Cost Budget.** Estimated Claude Opus token spend for the one-shot code generation (lines of code × tokens/line × safety factor). Estimated compute spend for training (Colab hours). Estimated monthly runtime cost on Vercel + Render free tiers. Keep total paid spend under ₹0 where possible, under ₹1000 worst-case.
- **J. 10-Day Execution Plan.** Day-by-day Gantt. Day 1 = scaffolding, Day 10 = final submission video + deployed URL. Each day has: outputs, owner (solo), done-criteria.
- **K. Risk Register.** Top 10 risks ranked by likelihood × impact, each with a specific mitigation and an owner-action.
- **L. Submission Package.** Exactly what the hackathon expects to receive (PPT / video / GitHub link / live URL / written report), each item's current spec per the website, and a checklist.
- **M. Final Pitch Script.** A 3-minute spoken pitch + 90-second live demo script + 60-second "why reproducibility wins" closer.

## Self-Audit Loop (run until two clean passes in a row)

After drafting A–M, run this checklist and fix anything that fails. Then re-run it. Repeat until two consecutive runs find zero issues.

1. **Groundedness.** Every factual claim about the hackathon has a citation. Grep your own output for words like "likely", "probably", "typically" — each must be either justified or deleted.
2. **Innovation.** Google-check the idea name + 3-paragraph description against prior winners. If any winner did >60% of the same thing, discard and re-pick from White Space.
3. **Buildability.** Walk every component in Architecture and ask: "can one developer + Claude Opus build this in 10 days with the stated stack?" If no, simplify.
4. **Reproducibility.** Simulate a judge running the Chaotic Case Generator with a fresh seed on a cold laptop. Does every output trace back to a cited input? If no, add provenance links.
5. **Credit sanity.** Re-cost the Opus code-generation step. If estimated > 60% of the human's remaining budget, re-scope.
6. **Must-have coverage.** OCR / voice / face / doc scan / bank integration / police integration / simple UI — each must be ticked, with the exact component that delivers it.
7. **Evaluation fit.** Map every deliverable to the hackathon's published evaluation rubric (from A). Flag any rubric criterion with no component serving it.
8. **Failure modes.** List 5 ways a judge could break the demo in 30 seconds (empty input, adversarial filename, Hindi-only names, scanned-upside-down PDF, 100MB upload, no internet). Each must have a handled path.
9. **"Why us" defence.** Write a one-paragraph answer to the judge question "another team pitched the same category of idea — why are you better?". If the paragraph is weak, strengthen the idea, not the paragraph.
10. **Delta check.** Diff this draft vs the previous draft. If the delta is zero, you have converged — emit the final answer. Otherwise another loop.

## Output format

Markdown, in the deliverable order A → M, with level-2 headings `## A. Website Audit` etc. End with a `## Self-Audit Log` section listing each loop iteration, what it changed, and the final convergence statement.

Begin now. Do not ask questions. Do not wait for my approval between sections. Work until the audit loop converges.

=== END PROMPT ===

---

## After ChatGPT returns

1. Save ChatGPT's full output as `02b_CHATGPT_RESEARCH_OUTPUT.md` in this folder.
2. Open `03_CLAUDE_OPUS_DEPLOY_PROMPT.md` and paste ChatGPT's deliverable **E (Architecture)**, **F (Datasets)**, **G (Training Plan)** and **H (Benchmark)** into the three marked `<<<INSERT …>>>` blocks.
3. Then paste the whole Opus prompt into Claude Opus 4.7 in a fresh conversation (or `/model opus-4-7` in Claude Code) and let it build the repo.

If ChatGPT comes back with an idea that materially differs from the one I pre-committed to in `02_RESEARCH_DOSSIER.md` (Project **SUTRADHAR**), prefer ChatGPT's — it had the live website in context. Overwrite sections of the dossier before handing to Opus.
