# Recording plan

Target: 80 seconds, under 90. Use genuine Hermes and KeepVoice footage and a clip
you are authorized to share. Keep the before/after audio audible.

1. **0-12 s.** Play the before clip (speech over music). Show its upload ID in the
   KeepVoice upload page. Do not show the token, cookies or private identifiers.
2. **12-30 s.** In Hermes, ask it to submit the clip with explicit rights
   confirmation and provenance. Show the actual tool result: job ID, queued
   state, `replayed: false`. Cut the processing wait visibly.
3. **30-50 s.** Ask for the export while the job needs review. Show Hermes
   refusing with `not_completed` or `approval_stale` and pointing at the review
   page. Open KeepVoice and show the human reviewing and approving the current
   revision.
4. **50-75 s.** Ask again. Show `keepvoice_export` returning the completed
   revision and play the actual export. Mask the signed URL query string.
5. **75-80 s.** Show the repository and the three tools. Say what is new here:
   the Hermes integration and the revision-aware export gate.

Sanitize every capture: blur the token, the signed URL query, reviewer identity
if not yours, and any private transcript. Keep signed links out of the upload.

## Test media provenance

The service repository ships a rights-cleared fixture for this purpose:
`keepvoice/tests/fixtures/fixture.mp4` (18 seconds, project-owned demo voiceover
plus a synthesized music bed). Its recorded provenance in the service end-to-end
script is: "Repository demo voiceover plus synthesized music bed; project-owned
rights-cleared fixture". Use that clip and that wording unless you have a better
consented source. The large camera clips in the checkout are not cleared for
public publication.
