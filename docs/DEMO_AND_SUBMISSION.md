# Demo and submission

## 80-second demo

1. **0–12 s.** Play a short before clip you have permission to share. Show the upload ID and explain the job. Blur private identifiers if needed.
2. **12–30 s.** Submit in Hermes and show the actual registered tool result. Cut the processing wait visibly.
3. **30–50 s.** Show the review state and ask for an export. Hermes explains why it cannot return one yet. Open the preview in KeepVoice and show the human approving the current revision.
4. **50–75 s.** Ask again after finalization. Show the completed revision and play the actual export. Mask the signed URL.
5. **75–80 s.** Show the repo and what was built for Hermes. Keep the video under 90 seconds.

Use genuine Hermes and KeepVoice footage. Keep the before/after audio audible. If using VideoWright for editing, use it to assemble real captures. Narration is optional. For a README diagram, diagram-design can produce an SVG, export a PNG, and embed the PNG next to the setup steps. Neither tool is a plugin dependency.

## Catalog PR

Validate locally before pinning. Create a public source repo and record the full 40-character commit SHA. Use the current [catalog entry schema](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md) to prepare exactly one new entry at `plugin-catalog/keepvoice-hermes.yaml`. Check the name, quote version, match runtime requirements to the plugin manifest and pin the reviewed source. Open the PR against [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

Describe what it does, public Hermes extension points, reuse versus new work, real validation results, and all catalog rule 13 disclosures. Attach screenshots if the plugin has a UI. Ensure reviewers have a documented way to evaluate it, such as a safe fixture mode for automated checks and a consented live demo with their own credentials where available.

## X post draft

I built KeepVoice for Hermes for the @NousResearch Hermes Agent Plugin Hackathon. It starts a voice cleanup job, shows what needs creator review, and hands back the export after the creator approves the current cut.

Demo below. Catalog PR: [insert PR URL]

## Submit

1. Open the catalog PR.
2. Post the public demo video on X tagging @NousResearch. Copy the post permalink.
3. Submit the PR and X post links through [the official form](https://form.typeform.com/to/FwJLvOln) and save the receipt. You can submit once the PR is open. Follow up on catalog review separately.

Deadline: **Nov 11, 2026, 5 p.m. EST / Nov 12, 2026, 3:30 a.m. IST**. [Official announcement](https://x.com/NousResearch/status/2118094256438936062)
