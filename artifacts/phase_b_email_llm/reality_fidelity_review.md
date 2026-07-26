# Reality-fidelity review -- Phase B (one live LLM actor)

Bob is played by deepseek-chat through the exact Mind interface the scripted
actors use.  The model receives only Bob's rendered local view (his identity,
beliefs, memories, noticed messages and the authoritative time context) and
returns JSON: intentions, private-state updates about himself, optional
future wake.  Structurally it holds no reference to the world, clock, queue,
terminal or other actors; everything it returns passes kernel validation
(hostile-output tests prove forbidden updates are recorded as violations and
skipped, unknown verbs are rejected, shared state stays untouched).

Observed live behavior: Bob noticed Alice's email Monday 09:00 Pacific (the
kernel decided when he could notice it -- the model was never asked to invent
time), decided to reply, composed for a self-chosen realistic duration, and
his reply's content came from HIS OWN belief (the $4.2M he locked in March),
not from any world fact he couldn't see.  Alice -- still scripted -- noticed
the reply on her half-hour cadence and interpreted it into her belief; the
terminal resolved mechanically from that belief record.

Honest limitations:
- One live actor only (by design of this step); live-vs-live dynamics are
  untested here.
- The model is prompted for temperature-0 JSON; richer free-form deliberation
  (drafting, hesitating, multitasking) is not yet elicited.
- Replay never calls the model (exchanges are in the ledger), but a live
  RE-RUN is not bit-deterministic: the API may answer differently. Replay
  determinism and run determinism are different guarantees; only the first
  is claimed for Phase B.
