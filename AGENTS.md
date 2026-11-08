# KeepVoice for Hermes

- The existing KeepVoice API owns media processing and approval. Hermes adds three registered tools and an export gate. Keep the backend and Agento workflow intact.
- Follow the official Hermes plugin guide and catalog rules. Use public extension surfaces. Keep dependencies small and bounded. Avoid self-updating code, bundled executables and background workers in the plugin.
- Use Hermes profile-scoped secrets. Keep token values, reviewer credentials, raw API responses, private transcripts and signed URLs out of logs, fixtures, screenshots and Git. Never inspect credential files directly. Use sanitized fixtures.
- Make external effects clear. Submission requires explicit source authorization. Human review occurs in KeepVoice. Use bounded requests. Return stable error codes and concrete recovery actions.
- Record checkpoints after implementation, validation, live proof and submission preparation. Include commit, actual commands/results, blockers and the next action. Do not invent passed checks or live results.
- Keep README and demo copy direct. No decorative footer or generated attribution. Document necessary licenses and disclosures.
