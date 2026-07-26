# SWORLDMODEL — complete run trace

All artifacts from every run, merged into one canonical, time-ordered document.

The **event ledger is the single source of truth**: `{seq, t, op, data, cause}`. Every other artifact (wakes, views, intentions, action/information/state/process lifecycles) is a *projection* of that ledger, so the merged stream below tags each record with the streams it belongs to rather than repeating it. Replaying the ledger with zero actor/LLM calls reproduces the final state hash and terminal result exactly.

Runs, in execution order:

- **email** — Two-person message interaction (NY <-> LA, weekend + DST gap) (times shown in America/New_York)
- **committee** — Small group decision (data release -> briefing -> motion -> votes) (times shown in America/Mexico_City)
- **factory** — Operational process with quantities (shifts, threshold, transit) (times shown in America/Chicago)
- **phase_b_email_llm** — Phase B: same world, Bob played by a live Deepseek-backed mind (times shown in America/New_York)


# WORLD: email

*Two-person message interaction (NY <-> LA, weekend + DST gap)*

**Question:** Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?

**Answer:** `"yes"` (resolved) — Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.

**Verification:** replay final hash `579b76c828cf1fa3…` == original `579b76c828cf1fa3…` → **True**; terminal match **True**; deterministic repeat run: **True**

**Metrics:** {"decisions": 7, "deferred_wakes": 0, "events_processed": 13, "intentions": 4, "ledger_records": 97, "llm_calls": 0, "pending_events_at_end": 1, "rejections": 0, "wall_ms": 5.6}


## email — initial_world.json (state at genesis seal)

```json
{
  "action_defs": {
    "read_message": {
      "conditions": [
        {
          "info": "{params.info}",
          "require": "noticed_info"
        }
      ],
      "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.",
      "effects": [
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Read message {params.info} in full.",
            "kind": "note",
            "source": "{params.info}"
          }
        ]
      ],
      "verb": "read_message"
    },
    "send_message": {
      "conditions": [
        {
          "id": "{params.to}",
          "require": "actor_exists"
        },
        {
          "name": "{params.channel}",
          "require": "channel_exists"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "{params.channel}",
            "content": "{params.content}",
            "data": "{params.data}",
            "to": [
              "{params.to}"
            ]
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent message to {params.to} on {params.channel}: {params.content}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "send_message"
    }
  },
  "actions": {},
  "actors": {
    "alice": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/New_York",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {
        "c1": {
          "at": "2026-03-07T02:10:00+00:00",
          "id": "c1",
          "resolved": false,
          "what": "email Bob about the Q2 numbers before the weekend"
        }
      },
      "deferred_wakes": [],
      "emotional_state": "mildly pressed by the Monday deadline",
      "goals": [
        "finalize the Monday Q2 summary with confirmed numbers"
      ],
      "id": "alice",
      "last_decision_at": null,
      "memories": [],
      "name": "Alice Ramos",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "working a long Friday",
      "plan": "Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.",
      "reconsider": [],
      "relationships": {
        "bob": "trusted colleague; owns the Q2 pipeline numbers"
      },
      "role": "program manager, East Coast office",
      "tz": "America/New_York",
      "unprocessed_info": [],
      "values": [
        "thorough",
        "dislikes sending unverified figures"
      ]
    },
    "bob": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Los_Angeles",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {
        "q2_numbers": {
          "basis": "verified: he closed the books himself on March 3",
          "statement": "The final Q2 pipeline total is $4.2M, locked on March 3.",
          "updated_at": "2026-03-06T13:00:00+00:00"
        }
      },
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "unwinding into the weekend",
      "goals": [
        "keep the quarter-close numbers accurate"
      ],
      "id": "bob",
      "last_decision_at": null,
      "memories": [],
      "name": "Bob Okafor",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "rested",
      "plan": "Off for the weekend; back Monday morning.",
      "reconsider": [],
      "relationships": {
        "alice": "trusted colleague preparing the Q2 summary"
      },
      "role": "finance lead, West Coast office",
      "tz": "America/Los_Angeles",
      "unprocessed_info": [],
      "values": [
        "precise",
        "answers colleagues promptly once he sees a request"
      ]
    }
  },
  "channels": {
    "email": {
      "latency": {
        "basis": "verified",
        "note": "typical SMTP relay delivery time",
        "seconds": 30.0
      },
      "name": "email"
    }
  },
  "entities": {},
  "facts": {},
  "history": [],
  "infos": {},
  "now": "2026-03-06T13:00:00+00:00",
  "processes": {},
  "relationships": {},
  "resources": {},
  "scheduled_events": [
    {
      "data": {
        "actor": "alice",
        "detail": "c1: email Bob about the Q2 numbers before the weekend",
        "reason": "scheduled_commitment"
      },
      "kind": "wake.actor",
      "seq": 9,
      "t": "2026-03-07T02:10:00+00:00"
    }
  ],
  "start": "2026-03-06T13:00:00+00:00",
  "terminal": null,
  "version": 10,
  "watches": {}
}
```

## email — canonical time-ordered stream (97 records)

Every ledger record in causal order. `seq` = ledger position and event id; `cause` = the record that produced it; `streams` = which artifact projections contain it.


### ⏱ 2026-03-06 08:00:00 America/New_York  ·  `2026-03-06T13:00:00+00:00`

- **`  1`** `world.genesis` ← cause `—` · _ledger-only_  
  start=2026-03-06T13:00:00+00:00 schema=1

  ```json
  {
    "cause": null,
    "data": {
      "schema": 1,
      "start": "2026-03-06T13:00:00+00:00"
    },
    "op": "world.genesis",
    "seq": 1,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  2`** `channel.add` ← cause `—` · _ledger-only_  
  email: latency 30s (verified: typical SMTP relay delivery time)

  ```json
  {
    "cause": null,
    "data": {
      "latency": {
        "basis": "verified",
        "note": "typical SMTP relay delivery time",
        "seconds": 30
      },
      "name": "email"
    },
    "op": "channel.add",
    "seq": 2,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  3`** `action.define` ← cause `—` · _actions_  
  send_message -- 3 conditions, 2 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "id": "{params.to}",
          "require": "actor_exists"
        },
        {
          "name": "{params.channel}",
          "require": "channel_exists"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "{params.channel}",
            "content": "{params.content}",
            "data": "{params.data}",
            "to": [
              "{params.to}"
            ]
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent message to {params.to} on {params.channel}: {params.content}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "send_message"
    },
    "op": "action.define",
    "seq": 3,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  4`** `action.define` ← cause `—` · _actions_  
  read_message -- 1 conditions, 1 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "info": "{params.info}",
          "require": "noticed_info"
        }
      ],
      "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.",
      "effects": [
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Read message {params.info} in full.",
            "kind": "note",
            "source": "{params.info}"
          }
        ]
      ],
      "verb": "read_message"
    },
    "op": "action.define",
    "seq": 4,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  5`** `actor.add` ← cause `—` · _state_  
  alice (Alice Ramos, program manager, East Coast office, America/New_York)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/New_York",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "mildly pressed by the Monday deadline",
      "goals": [
        "finalize the Monday Q2 summary with confirmed numbers"
      ],
      "id": "alice",
      "last_decision_at": null,
      "memories": [],
      "name": "Alice Ramos",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "working a long Friday",
      "plan": "Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.",
      "reconsider": [],
      "relationships": {
        "bob": "trusted colleague; owns the Q2 pipeline numbers"
      },
      "role": "program manager, East Coast office",
      "tz": "America/New_York",
      "unprocessed_info": [],
      "values": [
        "thorough",
        "dislikes sending unverified figures"
      ]
    },
    "op": "actor.add",
    "seq": 5,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  6`** `actor.add` ← cause `—` · _state_  
  bob (Bob Okafor, finance lead, West Coast office, America/Los_Angeles)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Los_Angeles",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "unwinding into the weekend",
      "goals": [
        "keep the quarter-close numbers accurate"
      ],
      "id": "bob",
      "last_decision_at": null,
      "memories": [],
      "name": "Bob Okafor",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "rested",
      "plan": "Off for the weekend; back Monday morning.",
      "reconsider": [],
      "relationships": {
        "alice": "trusted colleague preparing the Q2 summary"
      },
      "role": "finance lead, West Coast office",
      "tz": "America/Los_Angeles",
      "unprocessed_info": [],
      "values": [
        "precise",
        "answers colleagues promptly once he sees a request"
      ]
    },
    "op": "actor.add",
    "seq": 6,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  7`** `actor.belief` ← cause `—` · _state_  
  bob[q2_numbers] = 'The final Q2 pipeline total is $4.2M, locked on March 3.' (basis: verified: he closed the books himself on March 3)

  ```json
  {
    "cause": null,
    "data": {
      "actor": "bob",
      "basis": "verified: he closed the books himself on March 3",
      "statement": "The final Q2 pipeline total is $4.2M, locked on March 3.",
      "topic": "q2_numbers"
    },
    "op": "actor.belief",
    "seq": 7,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  8`** `actor.commit` ← cause `—` · _state_  
  alice commits c1: 'email Bob about the Q2 numbers before the weekend' at=2026-03-07T02:10:00+00:00

  ```json
  {
    "cause": null,
    "data": {
      "actor": "alice",
      "at": "2026-03-07T02:10:00+00:00",
      "id": "c1",
      "what": "email Bob about the Q2 numbers before the weekend"
    },
    "op": "actor.commit",
    "seq": 8,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  9`** `event.scheduled` ← cause `—` · _ledger-only_  
  [wake.actor] at 2026-03-07T02:10:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "actor": "alice",
        "detail": "c1: email Bob about the Q2 numbers before the weekend",
        "reason": "scheduled_commitment"
      },
      "depth": 0,
      "kind": "wake.actor",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 9,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **` 10`** `genesis.sealed` ← cause `—` · _ledger-only_  
  world construction complete; every later record needs a cause

  ```json
  {
    "cause": null,
    "data": {},
    "op": "genesis.sealed",
    "seq": 10,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **` 11`** `event.scheduled` ← cause `10` · _ledger-only_  
  [terminal.cutoff] at 2026-03-10T16:00:00+00:00 depth=0

  ```json
  {
    "cause": 10,
    "data": {
      "data": {
        "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?"
      },
      "depth": 0,
      "kind": "terminal.cutoff",
      "t": "2026-03-10T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 11,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```

### ⏱ 2026-03-06 21:10:00 America/New_York  ·  `2026-03-07T02:10:00+00:00`

- **` 12`** `event.fired` ← cause `9` · _ledger-only_  
  [wake.actor]

  ```json
  {
    "cause": 9,
    "data": {
      "data": {
        "actor": "alice",
        "detail": "c1: email Bob about the Q2 numbers before the weekend",
        "reason": "scheduled_commitment"
      },
      "event": 9,
      "kind": "wake.actor",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.fired",
    "seq": 12,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 13`** `actor.view` ← cause `12` · _views_  
  alice shown world v12, reasons=['scheduled_commitment']

  ```json
  {
    "cause": 12,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": null,
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ],
      "rendered": "Current time:\n2026-03-06 21:10:00 America/New_York\n\nUpcoming commitments:\n- email Bob about the Q2 numbers before the weekend in 0 minutes (at 2026-03-06 21:10:00 America/New_York)\n\nWhy you are being consulted now:\n- scheduled_commitment: c1: email Bob about the Q2 numbers before the weekend\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 12
    },
    "op": "actor.view",
    "seq": 13,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 14`** `actor.decision` ← cause `13` · _wakes_  
  alice because ['scheduled_commitment'] -> intentions=['send_message'] | 'Friday evening: sending Bob the Q2 question before logging off'

  ```json
  {
    "cause": 13,
    "data": {
      "actor": "alice",
      "based_on_version": 12,
      "intentions": [
        "send_message"
      ],
      "note": "Friday evening: sending Bob the Q2 question before logging off",
      "reasons": [
        {
          "channel": null,
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ]
    },
    "op": "actor.decision",
    "seq": 14,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 15`** `actor.commitment_resolved` ← cause `14` · _state_  
  alice resolved c1

  ```json
  {
    "cause": 14,
    "data": {
      "actor": "alice",
      "id": "c1"
    },
    "op": "actor.commitment_resolved",
    "seq": 15,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 16`** `actor.memory` ← cause `14` · _state_  
  alice <- (note) 'Decided to email Bob about the Q2 numbers tonight.'

  ```json
  {
    "cause": 14,
    "data": {
      "actor": "alice",
      "content": "Decided to email Bob about the Q2 numbers tonight.",
      "kind": "note",
      "source": "decision"
    },
    "op": "actor.memory",
    "seq": 16,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 17`** `action.propose` ← cause `14` · _intentions+actions_  
  a17 alice:send_message {'channel': 'email', 'content': "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", 'data': {'thread': 'q2', 'type': 'question'}, 'to': 'bob'} dur=480.0s (actor_chosen) based_on_v12

  ```json
  {
    "cause": 14,
    "data": {
      "actor": "alice",
      "based_on_version": 12,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "time she takes to compose a short email",
        "seconds": 480.0
      },
      "id": "a17",
      "interruptible": false,
      "interruption_note": "",
      "note": "fulfilling her Friday commitment",
      "params": {
        "channel": "email",
        "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
        "data": {
          "thread": "q2",
          "type": "question"
        },
        "to": "bob"
      },
      "verb": "send_message"
    },
    "op": "action.propose",
    "seq": 17,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 18`** `event.scheduled` ← cause `17` · _ledger-only_  
  [action.start] at 2026-03-07T02:10:00+00:00 depth=1

  ```json
  {
    "cause": 17,
    "data": {
      "data": {
        "action": "a17"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 18,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 19`** `action.state` ← cause `17` · _actions_  
  a17 -> scheduled

  ```json
  {
    "cause": 17,
    "data": {
      "id": "a17",
      "start_event": 18,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 19,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 20`** `event.fired` ← cause `18` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 18,
    "data": {
      "data": {
        "action": "a17"
      },
      "event": 18,
      "kind": "action.start",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.fired",
    "seq": 20,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 21`** `event.scheduled` ← cause `20` · _ledger-only_  
  [action.complete] at 2026-03-07T02:18:00+00:00 depth=0

  ```json
  {
    "cause": 20,
    "data": {
      "data": {
        "action": "a17"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-03-07T02:18:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 21,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 22`** `action.state` ← cause `20` · _actions_  
  a17 -> started completes_at=2026-03-07T02:18:00+00:00

  ```json
  {
    "cause": 20,
    "data": {
      "complete_event": 21,
      "completes_at": "2026-03-07T02:18:00+00:00",
      "id": "a17",
      "state": "started"
    },
    "op": "action.state",
    "seq": 22,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 23`** `actor.ongoing` ← cause `20` · _state_  
  alice ongoing -> a17

  ```json
  {
    "cause": 20,
    "data": {
      "action": "a17",
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 23,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```

### ⏱ 2026-03-06 21:18:00 America/New_York  ·  `2026-03-07T02:18:00+00:00`

- **` 24`** `event.fired` ← cause `21` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 21,
    "data": {
      "data": {
        "action": "a17"
      },
      "event": 21,
      "kind": "action.complete",
      "t": "2026-03-07T02:18:00+00:00"
    },
    "op": "event.fired",
    "seq": 24,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 25`** `action.state` ← cause `24` · _actions_  
  a17 -> completed

  ```json
  {
    "cause": 24,
    "data": {
      "id": "a17",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 25,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 26`** `actor.ongoing` ← cause `24` · _state_  
  alice ongoing -> None

  ```json
  {
    "cause": 24,
    "data": {
      "action": null,
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 26,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 27`** `info.create` ← cause `24` · _info_  
  i27 by alice: "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary." data={'thread': 'q2', 'type': 'question'}

  ```json
  {
    "cause": 24,
    "data": {
      "author": "alice",
      "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
      "data": {
        "thread": "q2",
        "type": "question"
      },
      "id": "i27"
    },
    "op": "info.create",
    "seq": 27,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 28`** `info.send` ← cause `27` · _info_  
  i27 -> bob via email

  ```json
  {
    "cause": 27,
    "data": {
      "channel": "email",
      "id": "i27",
      "to": "bob"
    },
    "op": "info.send",
    "seq": 28,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 29`** `event.scheduled` ← cause `28` · _ledger-only_  
  [info.deliver] at 2026-03-07T02:18:30+00:00 depth=0

  ```json
  {
    "cause": 28,
    "data": {
      "data": {
        "channel": "email",
        "info": "i27",
        "to": "bob"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-03-07T02:18:30+00:00"
    },
    "op": "event.scheduled",
    "seq": 29,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 30`** `actor.memory` ← cause `24` · _state_  
  alice <- (note) "Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary."

  ```json
  {
    "cause": 24,
    "data": {
      "actor": "alice",
      "content": "Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
      "kind": "note",
      "source": "a17"
    },
    "op": "actor.memory",
    "seq": 30,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 31`** `actor.view` ← cause `24` · _views_  
  alice shown world v30, reasons=['action_completed']

  ```json
  {
    "cause": 24,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a17"
        }
      ],
      "rendered": "Current time:\n2026-03-06 21:18:00 America/New_York\n\nTime since your previous relevant decision:\n8 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'bob', 'channel': 'email', 'content': \"Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\", 'data': {'type': 'question', 'thread': 'q2'}}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 30
    },
    "op": "actor.view",
    "seq": 31,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 32`** `actor.decision` ← cause `31` · _wakes_  
  alice because ['action_completed'] -> intentions=[] | 'Email sent; waiting on Bob'

  ```json
  {
    "cause": 31,
    "data": {
      "actor": "alice",
      "based_on_version": 30,
      "intentions": [],
      "note": "Email sent; waiting on Bob",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a17"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 32,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 33`** `actor.plan` ← cause `32` · _state_  
  alice: "Wait for Bob's reply before finalizing the summary."

  ```json
  {
    "cause": 32,
    "data": {
      "actor": "alice",
      "plan": "Wait for Bob's reply before finalizing the summary."
    },
    "op": "actor.plan",
    "seq": 33,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```

### ⏱ 2026-03-06 21:18:30 America/New_York  ·  `2026-03-07T02:18:30+00:00`

- **` 34`** `event.fired` ← cause `29` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 29,
    "data": {
      "data": {
        "channel": "email",
        "info": "i27",
        "to": "bob"
      },
      "event": 29,
      "kind": "info.deliver",
      "t": "2026-03-07T02:18:30+00:00"
    },
    "op": "event.fired",
    "seq": 34,
    "t": "2026-03-07T02:18:30+00:00"
  }
  ```
- **` 35`** `info.deliver` ← cause `34` · _info_  
  i27 DELIVERED to bob via email

  ```json
  {
    "cause": 34,
    "data": {
      "channel": "email",
      "id": "i27",
      "to": "bob"
    },
    "op": "info.deliver",
    "seq": 35,
    "t": "2026-03-07T02:18:30+00:00"
  }
  ```
- **` 36`** `event.scheduled` ← cause `34` · _ledger-only_  
  [info.notice] at 2026-03-09T16:00:00+00:00 depth=0

  ```json
  {
    "cause": 34,
    "data": {
      "data": {
        "actor": "bob",
        "basis": "inferred",
        "channel": "email",
        "info": "i27",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 36,
    "t": "2026-03-07T02:18:30+00:00"
  }
  ```

### ⏱ 2026-03-09 12:00:00 America/New_York  ·  `2026-03-09T16:00:00+00:00`

- **` 37`** `event.fired` ← cause `36` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 36,
    "data": {
      "data": {
        "actor": "bob",
        "basis": "inferred",
        "channel": "email",
        "info": "i27",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "event": 36,
      "kind": "info.notice",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 37,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 38`** `info.notice` ← cause `37` · _info_  
  i27 NOTICED by bob

  ```json
  {
    "cause": 37,
    "data": {
      "actor": "bob",
      "id": "i27"
    },
    "op": "info.notice",
    "seq": 38,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 39`** `actor.memory` ← cause `38` · _state_  
  bob <- (observation) "Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary."

  ```json
  {
    "cause": 38,
    "data": {
      "actor": "bob",
      "content": "Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
      "kind": "observation",
      "source": "i27"
    },
    "op": "actor.memory",
    "seq": 39,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 40`** `actor.view` ← cause `38` · _views_  
  bob shown world v39, reasons=['info_noticed']

  ```json
  {
    "cause": 38,
    "data": {
      "actor": "bob",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from alice on email",
          "kind": "info_noticed",
          "ref": "i27"
        }
      ],
      "rendered": "Current time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 39
    },
    "op": "actor.view",
    "seq": 40,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 41`** `actor.decision` ← cause `40` · _wakes_  
  bob because ['info_noticed'] -> intentions=['read_message'] | "Back at his desk Monday; Alice's email is at the top"

  ```json
  {
    "cause": 40,
    "data": {
      "actor": "bob",
      "based_on_version": 39,
      "intentions": [
        "read_message"
      ],
      "note": "Back at his desk Monday; Alice's email is at the top",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from alice on email",
          "kind": "info_noticed",
          "ref": "i27"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 41,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 42`** `actor.emotion` ← cause `41` · _state_  
  bob: 'Monday-morning inbox triage; slightly rushed'

  ```json
  {
    "cause": 41,
    "data": {
      "actor": "bob",
      "statement": "Monday-morning inbox triage; slightly rushed"
    },
    "op": "actor.emotion",
    "seq": 42,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 43`** `action.propose` ← cause `41` · _intentions+actions_  
  a43 bob:read_message {'content': "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", 'info': 'i27'} dur=360.0s (inferred) based_on_v39

  ```json
  {
    "cause": 41,
    "data": {
      "actor": "bob",
      "based_on_version": 39,
      "completes_when": null,
      "duration": {
        "basis": "inferred",
        "note": "reading and re-checking the request",
        "seconds": 360.0
      },
      "id": "a43",
      "interruptible": false,
      "interruption_note": "",
      "note": "new email from Alice; reading it",
      "params": {
        "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
        "info": "i27"
      },
      "verb": "read_message"
    },
    "op": "action.propose",
    "seq": 43,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 44`** `event.scheduled` ← cause `43` · _ledger-only_  
  [action.start] at 2026-03-09T16:00:00+00:00 depth=1

  ```json
  {
    "cause": 43,
    "data": {
      "data": {
        "action": "a43"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 44,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 45`** `action.state` ← cause `43` · _actions_  
  a43 -> scheduled

  ```json
  {
    "cause": 43,
    "data": {
      "id": "a43",
      "start_event": 44,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 45,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 46`** `event.fired` ← cause `44` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 44,
    "data": {
      "data": {
        "action": "a43"
      },
      "event": 44,
      "kind": "action.start",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 46,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 47`** `event.scheduled` ← cause `46` · _ledger-only_  
  [action.complete] at 2026-03-09T16:06:00+00:00 depth=0

  ```json
  {
    "cause": 46,
    "data": {
      "data": {
        "action": "a43"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-03-09T16:06:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 47,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 48`** `action.state` ← cause `46` · _actions_  
  a43 -> started completes_at=2026-03-09T16:06:00+00:00

  ```json
  {
    "cause": 46,
    "data": {
      "complete_event": 47,
      "completes_at": "2026-03-09T16:06:00+00:00",
      "id": "a43",
      "state": "started"
    },
    "op": "action.state",
    "seq": 48,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 49`** `actor.ongoing` ← cause `46` · _state_  
  bob ongoing -> a43

  ```json
  {
    "cause": 46,
    "data": {
      "action": "a43",
      "actor": "bob"
    },
    "op": "actor.ongoing",
    "seq": 49,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```

### ⏱ 2026-03-09 12:06:00 America/New_York  ·  `2026-03-09T16:06:00+00:00`

- **` 50`** `event.fired` ← cause `47` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 47,
    "data": {
      "data": {
        "action": "a43"
      },
      "event": 47,
      "kind": "action.complete",
      "t": "2026-03-09T16:06:00+00:00"
    },
    "op": "event.fired",
    "seq": 50,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 51`** `action.state` ← cause `50` · _actions_  
  a43 -> completed

  ```json
  {
    "cause": 50,
    "data": {
      "id": "a43",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 51,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 52`** `actor.ongoing` ← cause `50` · _state_  
  bob ongoing -> None

  ```json
  {
    "cause": 50,
    "data": {
      "action": null,
      "actor": "bob"
    },
    "op": "actor.ongoing",
    "seq": 52,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 53`** `actor.memory` ← cause `50` · _state_  
  bob <- (note) 'Read message i27 in full.'

  ```json
  {
    "cause": 50,
    "data": {
      "actor": "bob",
      "content": "Read message i27 in full.",
      "kind": "note",
      "source": "i27"
    },
    "op": "actor.memory",
    "seq": 53,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 54`** `actor.view` ← cause `50` · _views_  
  bob shown world v53, reasons=['action_completed']

  ```json
  {
    "cause": 50,
    "data": {
      "actor": "bob",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a43"
        }
      ],
      "rendered": "Current time:\n2026-03-09 09:06:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n6 minutes\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i27', 'content': \"Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\"}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: Monday-morning inbox triage; slightly rushed\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:06:00 America/Los_Angeles] (note) Read message i27 in full.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 53
    },
    "op": "actor.view",
    "seq": 54,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 55`** `actor.decision` ← cause `54` · _wakes_  
  bob because ['action_completed'] -> intentions=['send_message'] | 'Replying with the confirmed Q2 total'

  ```json
  {
    "cause": 54,
    "data": {
      "actor": "bob",
      "based_on_version": 53,
      "intentions": [
        "send_message"
      ],
      "note": "Replying with the confirmed Q2 total",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a43"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 55,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 56`** `actor.belief` ← cause `55` · _state_  
  bob[alice_request] = 'Alice needs the final Q2 numbers confirmed for her Monday summary.' (basis: her email (i27), read in full)

  ```json
  {
    "cause": 55,
    "data": {
      "actor": "bob",
      "basis": "her email (i27), read in full",
      "statement": "Alice needs the final Q2 numbers confirmed for her Monday summary.",
      "topic": "alice_request"
    },
    "op": "actor.belief",
    "seq": 56,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 57`** `action.propose` ← cause `55` · _intentions+actions_  
  a57 bob:send_message {'channel': 'email', 'content': 'Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.', 'data': {'in_reply_to': 'i27', 'thread': 'q2', 'type': 'reply'}, 'to': 'alice'} dur=720.0s (actor_chosen) based_on_v53

  ```json
  {
    "cause": 55,
    "data": {
      "actor": "bob",
      "based_on_version": 53,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "double-checks the ledger figure while composing",
        "seconds": 720.0
      },
      "id": "a57",
      "interruptible": false,
      "interruption_note": "",
      "note": "answering Alice's confirmation request",
      "params": {
        "channel": "email",
        "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
        "data": {
          "in_reply_to": "i27",
          "thread": "q2",
          "type": "reply"
        },
        "to": "alice"
      },
      "verb": "send_message"
    },
    "op": "action.propose",
    "seq": 57,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 58`** `event.scheduled` ← cause `57` · _ledger-only_  
  [action.start] at 2026-03-09T16:06:00+00:00 depth=1

  ```json
  {
    "cause": 57,
    "data": {
      "data": {
        "action": "a57"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-03-09T16:06:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 58,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 59`** `action.state` ← cause `57` · _actions_  
  a57 -> scheduled

  ```json
  {
    "cause": 57,
    "data": {
      "id": "a57",
      "start_event": 58,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 59,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 60`** `event.fired` ← cause `58` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 58,
    "data": {
      "data": {
        "action": "a57"
      },
      "event": 58,
      "kind": "action.start",
      "t": "2026-03-09T16:06:00+00:00"
    },
    "op": "event.fired",
    "seq": 60,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 61`** `event.scheduled` ← cause `60` · _ledger-only_  
  [action.complete] at 2026-03-09T16:18:00+00:00 depth=0

  ```json
  {
    "cause": 60,
    "data": {
      "data": {
        "action": "a57"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-03-09T16:18:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 61,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 62`** `action.state` ← cause `60` · _actions_  
  a57 -> started completes_at=2026-03-09T16:18:00+00:00

  ```json
  {
    "cause": 60,
    "data": {
      "complete_event": 61,
      "completes_at": "2026-03-09T16:18:00+00:00",
      "id": "a57",
      "state": "started"
    },
    "op": "action.state",
    "seq": 62,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```
- **` 63`** `actor.ongoing` ← cause `60` · _state_  
  bob ongoing -> a57

  ```json
  {
    "cause": 60,
    "data": {
      "action": "a57",
      "actor": "bob"
    },
    "op": "actor.ongoing",
    "seq": 63,
    "t": "2026-03-09T16:06:00+00:00"
  }
  ```

### ⏱ 2026-03-09 12:18:00 America/New_York  ·  `2026-03-09T16:18:00+00:00`

- **` 64`** `event.fired` ← cause `61` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 61,
    "data": {
      "data": {
        "action": "a57"
      },
      "event": 61,
      "kind": "action.complete",
      "t": "2026-03-09T16:18:00+00:00"
    },
    "op": "event.fired",
    "seq": 64,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 65`** `action.state` ← cause `64` · _actions_  
  a57 -> completed

  ```json
  {
    "cause": 64,
    "data": {
      "id": "a57",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 65,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 66`** `actor.ongoing` ← cause `64` · _state_  
  bob ongoing -> None

  ```json
  {
    "cause": 64,
    "data": {
      "action": null,
      "actor": "bob"
    },
    "op": "actor.ongoing",
    "seq": 66,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 67`** `info.create` ← cause `64` · _info_  
  i67 by bob: 'Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.' data={'in_reply_to': 'i27', 'thread': 'q2', 'type': 'reply'}

  ```json
  {
    "cause": 64,
    "data": {
      "author": "bob",
      "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
      "data": {
        "in_reply_to": "i27",
        "thread": "q2",
        "type": "reply"
      },
      "id": "i67"
    },
    "op": "info.create",
    "seq": 67,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 68`** `info.send` ← cause `67` · _info_  
  i67 -> alice via email

  ```json
  {
    "cause": 67,
    "data": {
      "channel": "email",
      "id": "i67",
      "to": "alice"
    },
    "op": "info.send",
    "seq": 68,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 69`** `event.scheduled` ← cause `68` · _ledger-only_  
  [info.deliver] at 2026-03-09T16:18:30+00:00 depth=0

  ```json
  {
    "cause": 68,
    "data": {
      "data": {
        "channel": "email",
        "info": "i67",
        "to": "alice"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-03-09T16:18:30+00:00"
    },
    "op": "event.scheduled",
    "seq": 69,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 70`** `actor.memory` ← cause `64` · _state_  
  bob <- (note) 'Sent message to alice on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.'

  ```json
  {
    "cause": 64,
    "data": {
      "actor": "bob",
      "content": "Sent message to alice on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
      "kind": "note",
      "source": "a57"
    },
    "op": "actor.memory",
    "seq": 70,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 71`** `actor.view` ← cause `64` · _views_  
  bob shown world v70, reasons=['action_completed']

  ```json
  {
    "cause": 64,
    "data": {
      "actor": "bob",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a57"
        }
      ],
      "rendered": "Current time:\n2026-03-09 09:18:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n12 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'alice', 'channel': 'email', 'content': 'Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.', 'data': {'type': 'reply', 'thread': 'q2', 'in_reply_to': 'i27'}}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [alice_request] Alice needs the final Q2 numbers confirmed for her Monday summary. (basis: her email (i27), read in full)\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: Monday-morning inbox triage; slightly rushed\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:06:00 America/Los_Angeles] (note) Read message i27 in full.\n- [2026-03-09 09:18:00 America/Los_Angeles] (note) Sent message to alice on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 70
    },
    "op": "actor.view",
    "seq": 71,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 72`** `actor.decision` ← cause `71` · _wakes_  
  bob because ['action_completed'] -> intentions=[] | 'Reply sent'

  ```json
  {
    "cause": 71,
    "data": {
      "actor": "bob",
      "based_on_version": 70,
      "intentions": [],
      "note": "Reply sent",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a57"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 72,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```
- **` 73`** `actor.plan` ← cause `72` · _state_  
  bob: 'Back to quarter-close work.'

  ```json
  {
    "cause": 72,
    "data": {
      "actor": "bob",
      "plan": "Back to quarter-close work."
    },
    "op": "actor.plan",
    "seq": 73,
    "t": "2026-03-09T16:18:00+00:00"
  }
  ```

### ⏱ 2026-03-09 12:18:30 America/New_York  ·  `2026-03-09T16:18:30+00:00`

- **` 74`** `event.fired` ← cause `69` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 69,
    "data": {
      "data": {
        "channel": "email",
        "info": "i67",
        "to": "alice"
      },
      "event": 69,
      "kind": "info.deliver",
      "t": "2026-03-09T16:18:30+00:00"
    },
    "op": "event.fired",
    "seq": 74,
    "t": "2026-03-09T16:18:30+00:00"
  }
  ```
- **` 75`** `info.deliver` ← cause `74` · _info_  
  i67 DELIVERED to alice via email

  ```json
  {
    "cause": 74,
    "data": {
      "channel": "email",
      "id": "i67",
      "to": "alice"
    },
    "op": "info.deliver",
    "seq": 75,
    "t": "2026-03-09T16:18:30+00:00"
  }
  ```
- **` 76`** `event.scheduled` ← cause `74` · _ledger-only_  
  [info.notice] at 2026-03-09T16:30:00+00:00 depth=0

  ```json
  {
    "cause": 74,
    "data": {
      "data": {
        "actor": "alice",
        "basis": "inferred",
        "channel": "email",
        "info": "i67",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 76,
    "t": "2026-03-09T16:18:30+00:00"
  }
  ```

### ⏱ 2026-03-09 12:30:00 America/New_York  ·  `2026-03-09T16:30:00+00:00`

- **` 77`** `event.fired` ← cause `76` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 76,
    "data": {
      "data": {
        "actor": "alice",
        "basis": "inferred",
        "channel": "email",
        "info": "i67",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "event": 76,
      "kind": "info.notice",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 77,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 78`** `info.notice` ← cause `77` · _info_  
  i67 NOTICED by alice

  ```json
  {
    "cause": 77,
    "data": {
      "actor": "alice",
      "id": "i67"
    },
    "op": "info.notice",
    "seq": 78,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 79`** `actor.memory` ← cause `78` · _state_  
  alice <- (observation) 'Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.'

  ```json
  {
    "cause": 78,
    "data": {
      "actor": "alice",
      "content": "Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
      "kind": "observation",
      "source": "i67"
    },
    "op": "actor.memory",
    "seq": 79,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 80`** `actor.view` ← cause `78` · _views_  
  alice shown world v79, reasons=['info_noticed']

  ```json
  {
    "cause": 78,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from bob on email",
          "kind": "info_noticed",
          "ref": "i67"
        }
      ],
      "rendered": "Current time:\n2026-03-09 12:30:00 America/New_York\n\nTime since your previous relevant decision:\n2 days, 14 hours, 12 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from bob on email\n\nNew information you have just noticed:\n- [email] message i67 from bob: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 79
    },
    "op": "actor.view",
    "seq": 80,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 81`** `actor.decision` ← cause `80` · _wakes_  
  alice because ['info_noticed'] -> intentions=['read_message'] | "Bob's reply arrived; reading it now"

  ```json
  {
    "cause": 80,
    "data": {
      "actor": "alice",
      "based_on_version": 79,
      "intentions": [
        "read_message"
      ],
      "note": "Bob's reply arrived; reading it now",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from bob on email",
          "kind": "info_noticed",
          "ref": "i67"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 81,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 82`** `action.propose` ← cause `81` · _intentions+actions_  
  a82 alice:read_message {'content': 'Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.', 'info': 'i67'} dur=240.0s (inferred) based_on_v79

  ```json
  {
    "cause": 81,
    "data": {
      "actor": "alice",
      "based_on_version": 79,
      "completes_when": null,
      "duration": {
        "basis": "inferred",
        "note": "short reply, quick read",
        "seconds": 240.0
      },
      "id": "a82",
      "interruptible": false,
      "interruption_note": "",
      "note": "Bob replied; reading it",
      "params": {
        "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
        "info": "i67"
      },
      "verb": "read_message"
    },
    "op": "action.propose",
    "seq": 82,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 83`** `event.scheduled` ← cause `82` · _ledger-only_  
  [action.start] at 2026-03-09T16:30:00+00:00 depth=1

  ```json
  {
    "cause": 82,
    "data": {
      "data": {
        "action": "a82"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 83,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 84`** `action.state` ← cause `82` · _actions_  
  a82 -> scheduled

  ```json
  {
    "cause": 82,
    "data": {
      "id": "a82",
      "start_event": 83,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 84,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 85`** `event.fired` ← cause `83` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 83,
    "data": {
      "data": {
        "action": "a82"
      },
      "event": 83,
      "kind": "action.start",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 85,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 86`** `event.scheduled` ← cause `85` · _ledger-only_  
  [action.complete] at 2026-03-09T16:34:00+00:00 depth=0

  ```json
  {
    "cause": 85,
    "data": {
      "data": {
        "action": "a82"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-03-09T16:34:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 86,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 87`** `action.state` ← cause `85` · _actions_  
  a82 -> started completes_at=2026-03-09T16:34:00+00:00

  ```json
  {
    "cause": 85,
    "data": {
      "complete_event": 86,
      "completes_at": "2026-03-09T16:34:00+00:00",
      "id": "a82",
      "state": "started"
    },
    "op": "action.state",
    "seq": 87,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 88`** `actor.ongoing` ← cause `85` · _state_  
  alice ongoing -> a82

  ```json
  {
    "cause": 85,
    "data": {
      "action": "a82",
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 88,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```

### ⏱ 2026-03-09 12:34:00 America/New_York  ·  `2026-03-09T16:34:00+00:00`

- **` 89`** `event.fired` ← cause `86` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 86,
    "data": {
      "data": {
        "action": "a82"
      },
      "event": 86,
      "kind": "action.complete",
      "t": "2026-03-09T16:34:00+00:00"
    },
    "op": "event.fired",
    "seq": 89,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 90`** `action.state` ← cause `89` · _actions_  
  a82 -> completed

  ```json
  {
    "cause": 89,
    "data": {
      "id": "a82",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 90,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 91`** `actor.ongoing` ← cause `89` · _state_  
  alice ongoing -> None

  ```json
  {
    "cause": 89,
    "data": {
      "action": null,
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 91,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 92`** `actor.memory` ← cause `89` · _state_  
  alice <- (note) 'Read message i67 in full.'

  ```json
  {
    "cause": 89,
    "data": {
      "actor": "alice",
      "content": "Read message i67 in full.",
      "kind": "note",
      "source": "i67"
    },
    "op": "actor.memory",
    "seq": 92,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 93`** `actor.view` ← cause `89` · _views_  
  alice shown world v92, reasons=['action_completed']

  ```json
  {
    "cause": 89,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a82"
        }
      ],
      "rendered": "Current time:\n2026-03-09 12:34:00 America/New_York\n\nTime since your previous relevant decision:\n4 minutes\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i67', 'content': 'Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.'}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\n- [2026-03-09 12:34:00 America/New_York] (note) Read message i67 in full.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 92
    },
    "op": "actor.view",
    "seq": 93,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 94`** `actor.decision` ← cause `93` · _wakes_  
  alice because ['action_completed'] -> intentions=[] | "Interpreting Bob's reply: the numbers are confirmed"

  ```json
  {
    "cause": 93,
    "data": {
      "actor": "alice",
      "based_on_version": 92,
      "intentions": [],
      "note": "Interpreting Bob's reply: the numbers are confirmed",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a82"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 94,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 95`** `actor.belief` ← cause `94` · _state_  
  alice[q2_confirmed] = 'Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.' (basis: his email (i67), read in full)

  ```json
  {
    "cause": 94,
    "data": {
      "actor": "alice",
      "basis": "his email (i67), read in full",
      "statement": "Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
      "topic": "q2_confirmed"
    },
    "op": "actor.belief",
    "seq": 95,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 96`** `actor.plan` ← cause `94` · _state_  
  alice: 'Fold the confirmed numbers into the Monday summary.'

  ```json
  {
    "cause": 94,
    "data": {
      "actor": "alice",
      "plan": "Fold the confirmed numbers into the Monday summary."
    },
    "op": "actor.plan",
    "seq": 96,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 97`** `terminal` ← cause `89` · _ledger-only_  
  [resolved] 'yes' -- Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.

  ```json
  {
    "cause": 89,
    "data": {
      "answer": {
        "answer": "yes",
        "computed_from": [
          "record:95"
        ],
        "detail": "Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3."
      },
      "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?",
      "status": "resolved"
    },
    "op": "terminal",
    "seq": 97,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```

## email — checkpoints.jsonl (1 checkpoints)

- ledger seq `76` at `2026-03-09T16:18:30+00:00` — state hash `2035c884d22e3761…`

Each checkpoint was resumed into a fresh engine with fresh minds; the resulting ledger was byte-identical to the uninterrupted run.

## email — terminal_result.json (with full producer lineage)

```json
{
  "answer": {
    "answer": "yes",
    "computed_from": [
      "record:95"
    ],
    "detail": "Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3."
  },
  "at": "2026-03-09T16:34:00+00:00",
  "producer_lineage": [
    {
      "data": {
        "answer": {
          "answer": "yes",
          "computed_from": [
            "record:95"
          ],
          "detail": "Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3."
        },
        "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?",
        "status": "resolved"
      },
      "op": "terminal",
      "seq": 97,
      "t": "2026-03-09T16:34:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a82"
        },
        "event": 86,
        "kind": "action.complete",
        "t": "2026-03-09T16:34:00+00:00"
      },
      "op": "event.fired",
      "seq": 89,
      "t": "2026-03-09T16:34:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a82"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-03-09T16:34:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 86,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a82"
        },
        "event": 83,
        "kind": "action.start",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.fired",
      "seq": 85,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a82"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 83,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 79,
        "completes_when": null,
        "duration": {
          "basis": "inferred",
          "note": "short reply, quick read",
          "seconds": 240.0
        },
        "id": "a82",
        "interruptible": false,
        "interruption_note": "",
        "note": "Bob replied; reading it",
        "params": {
          "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
          "info": "i67"
        },
        "verb": "read_message"
      },
      "op": "action.propose",
      "seq": 82,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 79,
        "intentions": [
          "read_message"
        ],
        "note": "Bob's reply arrived; reading it now",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from bob on email",
            "kind": "info_noticed",
            "ref": "i67"
          }
        ]
      },
      "op": "actor.decision",
      "seq": 81,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from bob on email",
            "kind": "info_noticed",
            "ref": "i67"
          }
        ],
        "rendered": "Current time:\n2026-03-09 12:30:00 America/New_York\n\nTime since your previous relevant decision:\n2 days, 14 hours, 12 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from bob on email\n\nNew information you have just noticed:\n- [email] message i67 from bob: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 79
      },
      "op": "actor.view",
      "seq": 80,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "id": "i67"
      },
      "op": "info.notice",
      "seq": 78,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "basis": "inferred",
          "channel": "email",
          "info": "i67",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "event": 76,
        "kind": "info.notice",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.fired",
      "seq": 77,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "basis": "inferred",
          "channel": "email",
          "info": "i67",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "depth": 0,
        "kind": "info.notice",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 76,
      "t": "2026-03-09T16:18:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i67",
          "to": "alice"
        },
        "event": 69,
        "kind": "info.deliver",
        "t": "2026-03-09T16:18:30+00:00"
      },
      "op": "event.fired",
      "seq": 74,
      "t": "2026-03-09T16:18:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i67",
          "to": "alice"
        },
        "depth": 0,
        "kind": "info.deliver",
        "t": "2026-03-09T16:18:30+00:00"
      },
      "op": "event.scheduled",
      "seq": 69,
      "t": "2026-03-09T16:18:00+00:00"
    },
    {
      "data": {
        "channel": "email",
        "id": "i67",
        "to": "alice"
      },
      "op": "info.send",
      "seq": 68,
      "t": "2026-03-09T16:18:00+00:00"
    },
    {
      "data": {
        "author": "bob",
        "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
        "data": {
          "in_reply_to": "i27",
          "thread": "q2",
          "type": "reply"
        },
        "id": "i67"
      },
      "op": "info.create",
      "seq": 67,
      "t": "2026-03-09T16:18:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a57"
        },
        "event": 61,
        "kind": "action.complete",
        "t": "2026-03-09T16:18:00+00:00"
      },
      "op": "event.fired",
      "seq": 64,
      "t": "2026-03-09T16:18:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a57"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-03-09T16:18:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 61,
      "t": "2026-03-09T16:06:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a57"
        },
        "event": 58,
        "kind": "action.start",
        "t": "2026-03-09T16:06:00+00:00"
      },
      "op": "event.fired",
      "seq": 60,
      "t": "2026-03-09T16:06:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a57"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-03-09T16:06:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 58,
      "t": "2026-03-09T16:06:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "based_on_version": 53,
        "completes_when": null,
        "duration": {
          "basis": "actor_chosen",
          "note": "double-checks the ledger figure while composing",
          "seconds": 720.0
        },
        "id": "a57",
        "interruptible": false,
        "interruption_note": "",
        "note": "answering Alice's confirmation request",
        "params": {
          "channel": "email",
          "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.",
          "data": {
            "in_reply_to": "i27",
            "thread": "q2",
            "type": "reply"
          },
          "to": "alice"
        },
        "verb": "send_message"
      },
      "op": "action.propose",
      "seq": 57,
      "t": "2026-03-09T16:06:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "based_on_version": 53,
        "intentions": [
          "send_message"
        ],
        "note": "Replying with the confirmed Q2 total",
        "reasons": [
          {
            "channel": null,
            "detail": "read_message",
            "kind": "action_completed",
            "ref": "a43"
          }
        ]
      },
      "op": "actor.decision",
      "seq": 55,
      "t": "2026-03-09T16:06:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "reasons": [
          {
            "channel": null,
            "detail": "read_message",
            "kind": "action_completed",
            "ref": "a43"
          }
        ],
        "rendered": "Current time:\n2026-03-09 09:06:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n6 minutes\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i27', 'content': \"Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\"}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: Monday-morning inbox triage; slightly rushed\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:06:00 America/Los_Angeles] (note) Read message i27 in full.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 53
      },
      "op": "actor.view",
      "seq": 54,
      "t": "2026-03-09T16:06:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a43"
        },
        "event": 47,
        "kind": "action.complete",
        "t": "2026-03-09T16:06:00+00:00"
      },
      "op": "event.fired",
      "seq": 50,
      "t": "2026-03-09T16:06:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a43"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-03-09T16:06:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 47,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a43"
        },
        "event": 44,
        "kind": "action.start",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.fired",
      "seq": 46,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a43"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 44,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "based_on_version": 39,
        "completes_when": null,
        "duration": {
          "basis": "inferred",
          "note": "reading and re-checking the request",
          "seconds": 360.0
        },
        "id": "a43",
        "interruptible": false,
        "interruption_note": "",
        "note": "new email from Alice; reading it",
        "params": {
          "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
          "info": "i27"
        },
        "verb": "read_message"
      },
      "op": "action.propose",
      "seq": 43,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "based_on_version": 39,
        "intentions": [
          "read_message"
        ],
        "note": "Back at his desk Monday; Alice's email is at the top",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from alice on email",
            "kind": "info_noticed",
            "ref": "i27"
          }
        ]
      },
      "op": "actor.decision",
      "seq": 41,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from alice on email",
            "kind": "info_noticed",
            "ref": "i27"
          }
        ],
        "rendered": "Current time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 39
      },
      "op": "actor.view",
      "seq": 40,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "id": "i27"
      },
      "op": "info.notice",
      "seq": 38,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "bob",
          "basis": "inferred",
          "channel": "email",
          "info": "i27",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "event": 36,
        "kind": "info.notice",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.fired",
      "seq": 37,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "bob",
          "basis": "inferred",
          "channel": "email",
          "info": "i27",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "depth": 0,
        "kind": "info.notice",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 36,
      "t": "2026-03-07T02:18:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i27",
          "to": "bob"
        },
        "event": 29,
        "kind": "info.deliver",
        "t": "2026-03-07T02:18:30+00:00"
      },
      "op": "event.fired",
      "seq": 34,
      "t": "2026-03-07T02:18:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i27",
          "to": "bob"
        },
        "depth": 0,
        "kind": "info.deliver",
        "t": "2026-03-07T02:18:30+00:00"
      },
      "op": "event.scheduled",
      "seq": 29,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "channel": "email",
        "id": "i27",
        "to": "bob"
      },
      "op": "info.send",
      "seq": 28,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "author": "alice",
        "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
        "data": {
          "thread": "q2",
          "type": "question"
        },
        "id": "i27"
      },
      "op": "info.create",
      "seq": 27,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "event": 21,
        "kind": "action.complete",
        "t": "2026-03-07T02:18:00+00:00"
      },
      "op": "event.fired",
      "seq": 24,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-03-07T02:18:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 21,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "event": 18,
        "kind": "action.start",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.fired",
      "seq": 20,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 18,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 12,
        "completes_when": null,
        "duration": {
          "basis": "actor_chosen",
          "note": "time she takes to compose a short email",
          "seconds": 480.0
        },
        "id": "a17",
        "interruptible": false,
        "interruption_note": "",
        "note": "fulfilling her Friday commitment",
        "params": {
          "channel": "email",
          "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
          "data": {
            "thread": "q2",
            "type": "question"
          },
          "to": "bob"
        },
        "verb": "send_message"
      },
      "op": "action.propose",
      "seq": 17,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 12,
        "intentions": [
          "send_message"
        ],
        "note": "Friday evening: sending Bob the Q2 question before logging off",
        "reasons": [
          {
            "channel": null,
            "detail": "c1: email Bob about the Q2 numbers before the weekend",
            "kind": "scheduled_commitment",
            "ref": null
          }
        ]
      },
      "op": "actor.decision",
      "seq": 14,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "reasons": [
          {
            "channel": null,
            "detail": "c1: email Bob about the Q2 numbers before the weekend",
            "kind": "scheduled_commitment",
            "ref": null
          }
        ],
        "rendered": "Current time:\n2026-03-06 21:10:00 America/New_York\n\nUpcoming commitments:\n- email Bob about the Q2 numbers before the weekend in 0 minutes (at 2026-03-06 21:10:00 America/New_York)\n\nWhy you are being consulted now:\n- scheduled_commitment: c1: email Bob about the Q2 numbers before the weekend\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 12
      },
      "op": "actor.view",
      "seq": 13,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "reason": "scheduled_commitment"
        },
        "event": 9,
        "kind": "wake.actor",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.fired",
      "seq": 12,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "reason": "scheduled_commitment"
        },
        "depth": 0,
        "kind": "wake.actor",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 9,
      "t": "2026-03-06T13:00:00+00:00"
    }
  ],
  "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?",
  "status": "resolved"
}
```

## email — replay_verification.json

```json
{
  "deterministic_repeat_run": true,
  "final_hash_match": true,
  "initial_state_hash": "ba87ca493adfb0f2c2dc5f8a8e5bf57ce735b640d8506dd3a92f5c4a10c69dac",
  "ledger_records": 97,
  "original_final_hash": "579b76c828cf1fa360d1239c27f7de5c7ab30d1c46e471c11bf75a1dc30ea217",
  "replayed_final_hash": "579b76c828cf1fa360d1239c27f7de5c7ab30d1c46e471c11bf75a1dc30ea217",
  "terminal_match": true
}
```

## email — runtime_metrics.json

```json
{
  "decisions": 7,
  "deferred_wakes": 0,
  "events_processed": 13,
  "intentions": 4,
  "ledger_records": 97,
  "llm_calls": 0,
  "pending_events_at_end": 1,
  "rejections": 0,
  "wall_ms": 5.6
}
```

## email — actor_wakes.jsonl (7 records, verbatim)

```json
{"cause": 13, "data": {"actor": "alice", "based_on_version": 12, "intentions": ["send_message"], "note": "Friday evening: sending Bob the Q2 question before logging off", "reasons": [{"channel": null, "detail": "c1: email Bob about the Q2 numbers before the weekend", "kind": "scheduled_commitment", "ref": null}]}, "op": "actor.decision", "seq": 14, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 31, "data": {"actor": "alice", "based_on_version": 30, "intentions": [], "note": "Email sent; waiting on Bob", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a17"}]}, "op": "actor.decision", "seq": 32, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 40, "data": {"actor": "bob", "based_on_version": 39, "intentions": ["read_message"], "note": "Back at his desk Monday; Alice's email is at the top", "reasons": [{"channel": "email", "detail": "message from alice on email", "kind": "info_noticed", "ref": "i27"}]}, "op": "actor.decision", "seq": 41, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 54, "data": {"actor": "bob", "based_on_version": 53, "intentions": ["send_message"], "note": "Replying with the confirmed Q2 total", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a43"}]}, "op": "actor.decision", "seq": 55, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 71, "data": {"actor": "bob", "based_on_version": 70, "intentions": [], "note": "Reply sent", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a57"}]}, "op": "actor.decision", "seq": 72, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 80, "data": {"actor": "alice", "based_on_version": 79, "intentions": ["read_message"], "note": "Bob's reply arrived; reading it now", "reasons": [{"channel": "email", "detail": "message from bob on email", "kind": "info_noticed", "ref": "i67"}]}, "op": "actor.decision", "seq": 81, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 93, "data": {"actor": "alice", "based_on_version": 92, "intentions": [], "note": "Interpreting Bob's reply: the numbers are confirmed", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a82"}]}, "op": "actor.decision", "seq": 94, "t": "2026-03-09T16:34:00+00:00"}
```

## email — actor_views.jsonl (7 records, verbatim)

```json
{"cause": 12, "data": {"actor": "alice", "reasons": [{"channel": null, "detail": "c1: email Bob about the Q2 numbers before the weekend", "kind": "scheduled_commitment", "ref": null}], "rendered": "Current time:\n2026-03-06 21:10:00 America/New_York\n\nUpcoming commitments:\n- email Bob about the Q2 numbers before the weekend in 0 minutes (at 2026-03-06 21:10:00 America/New_York)\n\nWhy you are being consulted now:\n- scheduled_commitment: c1: email Bob about the Q2 numbers before the weekend\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 12}, "op": "actor.view", "seq": 13, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 24, "data": {"actor": "alice", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a17"}], "rendered": "Current time:\n2026-03-06 21:18:00 America/New_York\n\nTime since your previous relevant decision:\n8 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'bob', 'channel': 'email', 'content': \"Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\", 'data': {'type': 'question', 'thread': 'q2'}}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 30}, "op": "actor.view", "seq": 31, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 38, "data": {"actor": "bob", "reasons": [{"channel": "email", "detail": "message from alice on email", "kind": "info_noticed", "ref": "i27"}], "rendered": "Current time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 39}, "op": "actor.view", "seq": 40, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 50, "data": {"actor": "bob", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a43"}], "rendered": "Current time:\n2026-03-09 09:06:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n6 minutes\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i27', 'content': \"Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\"}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: Monday-morning inbox triage; slightly rushed\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:06:00 America/Los_Angeles] (note) Read message i27 in full.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 53}, "op": "actor.view", "seq": 54, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 64, "data": {"actor": "bob", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a57"}], "rendered": "Current time:\n2026-03-09 09:18:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n12 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'alice', 'channel': 'email', 'content': 'Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.', 'data': {'type': 'reply', 'thread': 'q2', 'in_reply_to': 'i27'}}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [alice_request] Alice needs the final Q2 numbers confirmed for her Monday summary. (basis: her email (i27), read in full)\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: Monday-morning inbox triage; slightly rushed\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:06:00 America/Los_Angeles] (note) Read message i27 in full.\n- [2026-03-09 09:18:00 America/Los_Angeles] (note) Sent message to alice on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 70}, "op": "actor.view", "seq": 71, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 78, "data": {"actor": "alice", "reasons": [{"channel": "email", "detail": "message from bob on email", "kind": "info_noticed", "ref": "i67"}], "rendered": "Current time:\n2026-03-09 12:30:00 America/New_York\n\nTime since your previous relevant decision:\n2 days, 14 hours, 12 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from bob on email\n\nNew information you have just noticed:\n- [email] message i67 from bob: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 79}, "op": "actor.view", "seq": 80, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 89, "data": {"actor": "alice", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a82"}], "rendered": "Current time:\n2026-03-09 12:34:00 America/New_York\n\nTime since your previous relevant decision:\n4 minutes\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i67', 'content': 'Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.'}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.\n- [2026-03-09 12:34:00 America/New_York] (note) Read message i67 in full.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 92}, "op": "actor.view", "seq": 93, "t": "2026-03-09T16:34:00+00:00"}
```

## email — intentions.jsonl (4 records, verbatim)

```json
{"cause": 14, "data": {"actor": "alice", "based_on_version": 12, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "time she takes to compose a short email", "seconds": 480.0}, "id": "a17", "interruptible": false, "interruption_note": "", "note": "fulfilling her Friday commitment", "params": {"channel": "email", "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "data": {"thread": "q2", "type": "question"}, "to": "bob"}, "verb": "send_message"}, "op": "action.propose", "seq": 17, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 41, "data": {"actor": "bob", "based_on_version": 39, "completes_when": null, "duration": {"basis": "inferred", "note": "reading and re-checking the request", "seconds": 360.0}, "id": "a43", "interruptible": false, "interruption_note": "", "note": "new email from Alice; reading it", "params": {"content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "info": "i27"}, "verb": "read_message"}, "op": "action.propose", "seq": 43, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 55, "data": {"actor": "bob", "based_on_version": 53, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "double-checks the ledger figure while composing", "seconds": 720.0}, "id": "a57", "interruptible": false, "interruption_note": "", "note": "answering Alice's confirmation request", "params": {"channel": "email", "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "data": {"in_reply_to": "i27", "thread": "q2", "type": "reply"}, "to": "alice"}, "verb": "send_message"}, "op": "action.propose", "seq": 57, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 81, "data": {"actor": "alice", "based_on_version": 79, "completes_when": null, "duration": {"basis": "inferred", "note": "short reply, quick read", "seconds": 240.0}, "id": "a82", "interruptible": false, "interruption_note": "", "note": "Bob replied; reading it", "params": {"content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "info": "i67"}, "verb": "read_message"}, "op": "action.propose", "seq": 82, "t": "2026-03-09T16:30:00+00:00"}
```

## email — intention_rejections.jsonl (0 records, verbatim)

*(empty — nothing of this kind occurred in this run)*

## email — action_lifecycle.jsonl (18 records, verbatim)

```json
{"cause": null, "data": {"conditions": [{"id": "{params.to}", "require": "actor_exists"}, {"name": "{params.channel}", "require": "channel_exists"}, {"param": "content", "require": "param_nonempty"}], "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "effects": [["info.send_new", {"author": "{actor}", "channel": "{params.channel}", "content": "{params.content}", "data": "{params.data}", "to": ["{params.to}"]}], ["actor.memory", {"actor": "{actor}", "content": "Sent message to {params.to} on {params.channel}: {params.content}", "kind": "note", "source": "{action_id}"}]], "verb": "send_message"}, "op": "action.define", "seq": 3, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"conditions": [{"info": "{params.info}", "require": "noticed_info"}], "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.", "effects": [["actor.memory", {"actor": "{actor}", "content": "Read message {params.info} in full.", "kind": "note", "source": "{params.info}"}]], "verb": "read_message"}, "op": "action.define", "seq": 4, "t": "2026-03-06T13:00:00+00:00"}
{"cause": 14, "data": {"actor": "alice", "based_on_version": 12, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "time she takes to compose a short email", "seconds": 480.0}, "id": "a17", "interruptible": false, "interruption_note": "", "note": "fulfilling her Friday commitment", "params": {"channel": "email", "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "data": {"thread": "q2", "type": "question"}, "to": "bob"}, "verb": "send_message"}, "op": "action.propose", "seq": 17, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 17, "data": {"id": "a17", "start_event": 18, "state": "scheduled"}, "op": "action.state", "seq": 19, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 20, "data": {"complete_event": 21, "completes_at": "2026-03-07T02:18:00+00:00", "id": "a17", "state": "started"}, "op": "action.state", "seq": 22, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 24, "data": {"id": "a17", "state": "completed"}, "op": "action.state", "seq": 25, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 41, "data": {"actor": "bob", "based_on_version": 39, "completes_when": null, "duration": {"basis": "inferred", "note": "reading and re-checking the request", "seconds": 360.0}, "id": "a43", "interruptible": false, "interruption_note": "", "note": "new email from Alice; reading it", "params": {"content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "info": "i27"}, "verb": "read_message"}, "op": "action.propose", "seq": 43, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 43, "data": {"id": "a43", "start_event": 44, "state": "scheduled"}, "op": "action.state", "seq": 45, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 46, "data": {"complete_event": 47, "completes_at": "2026-03-09T16:06:00+00:00", "id": "a43", "state": "started"}, "op": "action.state", "seq": 48, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 50, "data": {"id": "a43", "state": "completed"}, "op": "action.state", "seq": 51, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 55, "data": {"actor": "bob", "based_on_version": 53, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "double-checks the ledger figure while composing", "seconds": 720.0}, "id": "a57", "interruptible": false, "interruption_note": "", "note": "answering Alice's confirmation request", "params": {"channel": "email", "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "data": {"in_reply_to": "i27", "thread": "q2", "type": "reply"}, "to": "alice"}, "verb": "send_message"}, "op": "action.propose", "seq": 57, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 57, "data": {"id": "a57", "start_event": 58, "state": "scheduled"}, "op": "action.state", "seq": 59, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 60, "data": {"complete_event": 61, "completes_at": "2026-03-09T16:18:00+00:00", "id": "a57", "state": "started"}, "op": "action.state", "seq": 62, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 64, "data": {"id": "a57", "state": "completed"}, "op": "action.state", "seq": 65, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 81, "data": {"actor": "alice", "based_on_version": 79, "completes_when": null, "duration": {"basis": "inferred", "note": "short reply, quick read", "seconds": 240.0}, "id": "a82", "interruptible": false, "interruption_note": "", "note": "Bob replied; reading it", "params": {"content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "info": "i67"}, "verb": "read_message"}, "op": "action.propose", "seq": 82, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 82, "data": {"id": "a82", "start_event": 83, "state": "scheduled"}, "op": "action.state", "seq": 84, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 85, "data": {"complete_event": 86, "completes_at": "2026-03-09T16:34:00+00:00", "id": "a82", "state": "started"}, "op": "action.state", "seq": 87, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 89, "data": {"id": "a82", "state": "completed"}, "op": "action.state", "seq": 90, "t": "2026-03-09T16:34:00+00:00"}
```

## email — information_lifecycle.jsonl (8 records, verbatim)

```json
{"cause": 24, "data": {"author": "alice", "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "data": {"thread": "q2", "type": "question"}, "id": "i27"}, "op": "info.create", "seq": 27, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 27, "data": {"channel": "email", "id": "i27", "to": "bob"}, "op": "info.send", "seq": 28, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 34, "data": {"channel": "email", "id": "i27", "to": "bob"}, "op": "info.deliver", "seq": 35, "t": "2026-03-07T02:18:30+00:00"}
{"cause": 37, "data": {"actor": "bob", "id": "i27"}, "op": "info.notice", "seq": 38, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 64, "data": {"author": "bob", "content": "Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "data": {"in_reply_to": "i27", "thread": "q2", "type": "reply"}, "id": "i67"}, "op": "info.create", "seq": 67, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 67, "data": {"channel": "email", "id": "i67", "to": "alice"}, "op": "info.send", "seq": 68, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 74, "data": {"channel": "email", "id": "i67", "to": "alice"}, "op": "info.deliver", "seq": 75, "t": "2026-03-09T16:18:30+00:00"}
{"cause": 77, "data": {"actor": "alice", "id": "i67"}, "op": "info.notice", "seq": 78, "t": "2026-03-09T16:30:00+00:00"}
```

## email — state_transitions.jsonl (26 records, verbatim)

```json
{"cause": null, "data": {"attention": {"email": {"basis": "inferred", "calendar": {"close": "17:00", "holidays": [], "open": "09:00", "tz": "America/New_York", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 1800.0, "note": "office worker; checks email roughly every half hour during work hours"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "mildly pressed by the Monday deadline", "goals": ["finalize the Monday Q2 summary with confirmed numbers"], "id": "alice", "last_decision_at": null, "memories": [], "name": "Alice Ramos", "noticed_info": [], "ongoing_action": null, "physical_state": "working a long Friday", "plan": "Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.", "reconsider": [], "relationships": {"bob": "trusted colleague; owns the Q2 pipeline numbers"}, "role": "program manager, East Coast office", "tz": "America/New_York", "unprocessed_info": [], "values": ["thorough", "dislikes sending unverified figures"]}, "op": "actor.add", "seq": 5, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"attention": {"email": {"basis": "inferred", "calendar": {"close": "17:00", "holidays": [], "open": "09:00", "tz": "America/Los_Angeles", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 1800.0, "note": "office worker; checks email roughly every half hour during work hours"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "unwinding into the weekend", "goals": ["keep the quarter-close numbers accurate"], "id": "bob", "last_decision_at": null, "memories": [], "name": "Bob Okafor", "noticed_info": [], "ongoing_action": null, "physical_state": "rested", "plan": "Off for the weekend; back Monday morning.", "reconsider": [], "relationships": {"alice": "trusted colleague preparing the Q2 summary"}, "role": "finance lead, West Coast office", "tz": "America/Los_Angeles", "unprocessed_info": [], "values": ["precise", "answers colleagues promptly once he sees a request"]}, "op": "actor.add", "seq": 6, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"actor": "bob", "basis": "verified: he closed the books himself on March 3", "statement": "The final Q2 pipeline total is $4.2M, locked on March 3.", "topic": "q2_numbers"}, "op": "actor.belief", "seq": 7, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"actor": "alice", "at": "2026-03-07T02:10:00+00:00", "id": "c1", "what": "email Bob about the Q2 numbers before the weekend"}, "op": "actor.commit", "seq": 8, "t": "2026-03-06T13:00:00+00:00"}
{"cause": 14, "data": {"actor": "alice", "id": "c1"}, "op": "actor.commitment_resolved", "seq": 15, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 14, "data": {"actor": "alice", "content": "Decided to email Bob about the Q2 numbers tonight.", "kind": "note", "source": "decision"}, "op": "actor.memory", "seq": 16, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 20, "data": {"action": "a17", "actor": "alice"}, "op": "actor.ongoing", "seq": 23, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 24, "data": {"action": null, "actor": "alice"}, "op": "actor.ongoing", "seq": 26, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 24, "data": {"actor": "alice", "content": "Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "kind": "note", "source": "a17"}, "op": "actor.memory", "seq": 30, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 32, "data": {"actor": "alice", "plan": "Wait for Bob's reply before finalizing the summary."}, "op": "actor.plan", "seq": 33, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 38, "data": {"actor": "bob", "content": "Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "kind": "observation", "source": "i27"}, "op": "actor.memory", "seq": 39, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 41, "data": {"actor": "bob", "statement": "Monday-morning inbox triage; slightly rushed"}, "op": "actor.emotion", "seq": 42, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 46, "data": {"action": "a43", "actor": "bob"}, "op": "actor.ongoing", "seq": 49, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 50, "data": {"action": null, "actor": "bob"}, "op": "actor.ongoing", "seq": 52, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 50, "data": {"actor": "bob", "content": "Read message i27 in full.", "kind": "note", "source": "i27"}, "op": "actor.memory", "seq": 53, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 55, "data": {"actor": "bob", "basis": "her email (i27), read in full", "statement": "Alice needs the final Q2 numbers confirmed for her Monday summary.", "topic": "alice_request"}, "op": "actor.belief", "seq": 56, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 60, "data": {"action": "a57", "actor": "bob"}, "op": "actor.ongoing", "seq": 63, "t": "2026-03-09T16:06:00+00:00"}
{"cause": 64, "data": {"action": null, "actor": "bob"}, "op": "actor.ongoing", "seq": 66, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 64, "data": {"actor": "bob", "content": "Sent message to alice on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "kind": "note", "source": "a57"}, "op": "actor.memory", "seq": 70, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 72, "data": {"actor": "bob", "plan": "Back to quarter-close work."}, "op": "actor.plan", "seq": 73, "t": "2026-03-09T16:18:00+00:00"}
{"cause": 78, "data": {"actor": "alice", "content": "Noticed message from bob on email: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "kind": "observation", "source": "i67"}, "op": "actor.memory", "seq": 79, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 85, "data": {"action": "a82", "actor": "alice"}, "op": "actor.ongoing", "seq": 88, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 89, "data": {"action": null, "actor": "alice"}, "op": "actor.ongoing", "seq": 91, "t": "2026-03-09T16:34:00+00:00"}
{"cause": 89, "data": {"actor": "alice", "content": "Read message i67 in full.", "kind": "note", "source": "i67"}, "op": "actor.memory", "seq": 92, "t": "2026-03-09T16:34:00+00:00"}
{"cause": 94, "data": {"actor": "alice", "basis": "his email (i67), read in full", "statement": "Bob confirmed the Q2 numbers: Hi Alice -- confirmed: The final Q2 pipeline total is $4.2M, locked on March 3.", "topic": "q2_confirmed"}, "op": "actor.belief", "seq": 95, "t": "2026-03-09T16:34:00+00:00"}
{"cause": 94, "data": {"actor": "alice", "plan": "Fold the confirmed numbers into the Monday summary."}, "op": "actor.plan", "seq": 96, "t": "2026-03-09T16:34:00+00:00"}
```

## email — continuous_process_transitions.jsonl (0 records, verbatim)

*(empty — nothing of this kind occurred in this run)*

## email — reality_fidelity_review.md

# Reality-fidelity review -- email world

## What is real-world faithful here
- **Time is real.** Alice's email leaves at 21:18:30 ET Friday (composing took
  8 minutes after her 21:10 decision, delivery 30s). Bob does not see it for
  the whole weekend; his notice fires Monday 09:00 Pacific. The elapsed gap is
  61h41m30s, not 62h41m30s, because 2026-03-08 (spring forward) removed an
  hour -- the kernel derived that from the tz database, not from a modeler.
- **Information is local.** Bob's reply exists only because a noticed,
  delivered message carried Alice's question; his answer quotes his own prior
  belief (the $4.2M figure he locked on March 3), not world state he cannot
  see.
- **Nothing is instant.** notice -> read (6 min) -> interpret -> compose
  (12 min) -> deliver (30s) -> Alice notices on her half-hour cadence.

## Honest limitations (labeled, not hidden)
- The 30-minute inbox cadence is an *inferred* attention model ("office
  worker") and is marked as such in the rule's provenance. Real noticing is
  burstier: phones buzz, people peek at 22:00. A phone-notification channel
  with its own rule would be the faithful extension.
- Bob starts reading the instant he notices. Realistically there is a
  seconds-to-minutes gap (finishing coffee, other emails first). The kernel
  supports it (the mind could schedule the read later); the scripted mind
  keeps it simple.
- Weekend attention is modeled as *zero*, which overstates disconnection --
  many people glance at email on Saturday. The correction would again be an
  explicit, provenance-labeled weekend rule, not a kernel change.



# WORLD: committee

*Small group decision (data release -> briefing -> motion -> votes)*

**Question:** What does the committee decide on the policy rate at the 2026-06-25 meeting (hold or cut), counted from cast votes?

**Answer:** `"hold"` (resolved) — votes: {'dana': 'hold', 'eli': 'cut', 'fran': 'hold'} -> hold 2-1

**Verification:** replay final hash `6b2311cec07e901f…` == original `6b2311cec07e901f…` → **True**; terminal match **True**; deterministic repeat run: **True**

**Metrics:** {"decisions": 15, "deferred_wakes": 0, "events_processed": 30, "intentions": 7, "ledger_records": 199, "llm_calls": 0, "pending_events_at_end": 2, "rejections": 0, "wall_ms": 17.1}


## committee — initial_world.json (state at genesis seal)

```json
{
  "action_defs": {
    "cast_vote": {
      "conditions": [
        {
          "key": "meeting_open",
          "require": "fact_equals",
          "value": true
        },
        {
          "require": "role_in",
          "roles": [
            "chair",
            "member"
          ]
        },
        {
          "key": "motion",
          "require": "fact_equals",
          "value": "{params.motion}"
        },
        {
          "key": "vote:{actor}",
          "require": "fact_absent"
        },
        {
          "param": "choice",
          "require": "param_in",
          "values": [
            "hold",
            "cut"
          ]
        }
      ],
      "description": "Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).",
      "effects": [
        [
          "fact.set",
          {
            "key": "vote:{actor}",
            "value": "{params.choice}"
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Voted {params.choice} on: {params.motion}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "cast_vote"
    },
    "prepare_briefing": {
      "conditions": [
        {
          "require": "role_in",
          "roles": [
            "staff analyst"
          ]
        },
        {
          "info": "{params.based_on_info}",
          "require": "noticed_info"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Prepare a staff briefing from a noticed release and email it to the committee. params: based_on_info, content.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "email",
            "content": "{params.content}",
            "data": {
              "based_on": "{params.based_on_info}",
              "type": "briefing"
            },
            "to": {
              "role_in": [
                "chair",
                "member"
              ]
            }
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent the inflation briefing to the committee.",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "prepare_briefing"
    },
    "propose_motion": {
      "conditions": [
        {
          "key": "meeting_open",
          "require": "fact_equals",
          "value": true
        },
        {
          "require": "role_in",
          "roles": [
            "chair"
          ]
        },
        {
          "key": "motion",
          "require": "fact_absent"
        },
        {
          "param": "motion",
          "require": "param_nonempty"
        }
      ],
      "description": "Put a motion on the floor (chair only, meeting in session). params: motion.",
      "effects": [
        [
          "fact.set",
          {
            "key": "motion",
            "value": "{params.motion}"
          }
        ],
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "meeting_floor",
            "content": "Motion on the floor: {params.motion}. Please vote.",
            "data": {
              "motion": "{params.motion}",
              "type": "motion"
            },
            "to": {
              "exclude": [
                "{actor}"
              ],
              "role_in": [
                "chair",
                "member"
              ]
            }
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Put the motion on the floor: {params.motion}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "propose_motion"
    },
    "read_message": {
      "conditions": [
        {
          "info": "{params.info}",
          "require": "noticed_info"
        }
      ],
      "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.",
      "effects": [
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Read message {params.info} in full.",
            "kind": "note",
            "source": "{params.info}"
          }
        ]
      ],
      "verb": "read_message"
    },
    "send_message": {
      "conditions": [
        {
          "id": "{params.to}",
          "require": "actor_exists"
        },
        {
          "name": "{params.channel}",
          "require": "channel_exists"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "{params.channel}",
            "content": "{params.content}",
            "data": "{params.data}",
            "to": [
              "{params.to}"
            ]
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent message to {params.to} on {params.channel}: {params.content}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "send_message"
    }
  },
  "actions": {},
  "actors": {
    "dana": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "18:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 3600.0,
          "note": "senior official; assistant batches email roughly hourly"
        },
        "meeting_floor": {
          "basis": "verified",
          "calendar": null,
          "check_every_seconds": null,
          "note": "present in the meeting room; speech is heard at once"
        }
      },
      "available_info": [],
      "beliefs": {
        "inflation": {
          "basis": "May CPI report",
          "statement": "Inflation has been running near 4 percent, above target.",
          "updated_at": "2026-06-23T14:00:00+00:00"
        }
      },
      "commitments": {
        "m1": {
          "at": "2026-06-25T16:00:00+00:00",
          "id": "m1",
          "resolved": false,
          "what": "attend the policy meeting"
        }
      },
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "decide the policy rate responsibly"
      ],
      "id": "dana",
      "last_decision_at": null,
      "memories": [],
      "name": "Dana Ortiz",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Review incoming analysis before Thursday's meeting.",
      "reconsider": [],
      "relationships": {
        "eli": "committee colleague",
        "fran": "committee colleague"
      },
      "role": "chair",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "institutionally cautious; discounts single data points"
      ]
    },
    "eli": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "18:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "checks email frequently between engagements"
        },
        "meeting_floor": {
          "basis": "verified",
          "calendar": null,
          "check_every_seconds": null,
          "note": "present in the meeting room; speech is heard at once"
        }
      },
      "available_info": [],
      "beliefs": {
        "inflation": {
          "basis": "May CPI report",
          "statement": "Inflation has been running near 4 percent, above target.",
          "updated_at": "2026-06-23T14:00:00+00:00"
        }
      },
      "commitments": {
        "m1": {
          "at": "2026-06-25T16:00:00+00:00",
          "id": "m1",
          "resolved": false,
          "what": "attend the policy meeting"
        }
      },
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "decide the policy rate responsibly"
      ],
      "id": "eli",
      "last_decision_at": null,
      "memories": [],
      "name": "Elias Roth",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Review incoming analysis before Thursday's meeting.",
      "reconsider": [],
      "relationships": {
        "dana": "committee colleague",
        "fran": "committee colleague"
      },
      "role": "member",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "data-driven; responds to new evidence"
      ]
    },
    "fran": {
      "attention": {
        "email": {
          "basis": "verified",
          "calendar": {
            "close": "18:00",
            "holidays": [
              "2026-06-24",
              "2026-06-25"
            ],
            "open": "09:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "travel schedule: offline Wednesday-Thursday, resumes Friday"
        },
        "meeting_floor": {
          "basis": "verified",
          "calendar": null,
          "check_every_seconds": null,
          "note": "present in the meeting room; speech is heard at once"
        }
      },
      "available_info": [],
      "beliefs": {
        "inflation": {
          "basis": "May CPI report",
          "statement": "Inflation has been running near 4 percent, above target.",
          "updated_at": "2026-06-23T14:00:00+00:00"
        }
      },
      "commitments": {
        "m1": {
          "at": "2026-06-25T16:00:00+00:00",
          "id": "m1",
          "resolved": false,
          "what": "attend the policy meeting"
        }
      },
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "decide the policy rate responsibly"
      ],
      "id": "fran",
      "last_decision_at": null,
      "memories": [],
      "name": "Francisca Duarte",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Review incoming analysis before Thursday's meeting.",
      "reconsider": [],
      "relationships": {
        "dana": "committee colleague",
        "eli": "committee colleague"
      },
      "role": "member",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "data-driven; responds to new evidence"
      ]
    },
    "gus": {
      "attention": {
        "data_wire": {
          "basis": "verified",
          "calendar": {
            "close": "18:00",
            "holidays": [],
            "open": "08:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": null,
          "note": "watching the release calendar is his job; the release time is scheduled"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "brief the committee accurately and fast on new data"
      ],
      "id": "gus",
      "last_decision_at": null,
      "memories": [],
      "name": "Gustavo Pena",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Watch Wednesday's inflation release and brief the committee.",
      "reconsider": [],
      "relationships": {},
      "role": "staff analyst",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "rigorous",
        "neutral"
      ]
    }
  },
  "channels": {
    "data_wire": {
      "latency": {
        "basis": "verified",
        "note": "electronic wire push at release time",
        "seconds": 5.0
      },
      "name": "data_wire"
    },
    "email": {
      "latency": {
        "basis": "verified",
        "note": "typical email delivery time",
        "seconds": 30.0
      },
      "name": "email"
    },
    "meeting_floor": {
      "latency": {
        "basis": "verified",
        "note": "spoken aloud in the meeting room",
        "seconds": 0.0
      },
      "name": "meeting_floor"
    }
  },
  "entities": {},
  "facts": {},
  "history": [],
  "infos": {},
  "now": "2026-06-23T14:00:00+00:00",
  "processes": {},
  "relationships": {},
  "resources": {},
  "scheduled_events": [
    {
      "data": {
        "note": "scheduled statistical release (verified: official calendar)",
        "ops": [
          [
            "fact.set",
            {
              "key": "inflation_release",
              "value": "3.1% y/y (below expectations)"
            }
          ],
          [
            "info.send_new",
            {
              "author": "statistics_wire",
              "channel": "data_wire",
              "content": "June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.",
              "data": {
                "series": "inflation",
                "type": "data_release"
              },
              "to": [
                "gus"
              ]
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 20,
      "t": "2026-06-24T14:00:00+00:00"
    },
    {
      "data": {
        "note": "the policy meeting is called to order (verified: official meeting calendar)",
        "ops": [
          [
            "fact.set",
            {
              "key": "meeting_open",
              "value": true
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 21,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "dana",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "kind": "wake.actor",
      "seq": 22,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "eli",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "kind": "wake.actor",
      "seq": 23,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "fran",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "kind": "wake.actor",
      "seq": 24,
      "t": "2026-06-25T16:00:00+00:00"
    }
  ],
  "start": "2026-06-23T14:00:00+00:00",
  "terminal": null,
  "version": 25,
  "watches": {}
}
```

## committee — canonical time-ordered stream (199 records)

Every ledger record in causal order. `seq` = ledger position and event id; `cause` = the record that produced it; `streams` = which artifact projections contain it.


### ⏱ 2026-06-23 08:00:00 America/Mexico_City  ·  `2026-06-23T14:00:00+00:00`

- **`  1`** `world.genesis` ← cause `—` · _ledger-only_  
  start=2026-06-23T14:00:00+00:00 schema=1

  ```json
  {
    "cause": null,
    "data": {
      "schema": 1,
      "start": "2026-06-23T14:00:00+00:00"
    },
    "op": "world.genesis",
    "seq": 1,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  2`** `channel.add` ← cause `—` · _ledger-only_  
  data_wire: latency 5s (verified: electronic wire push at release time)

  ```json
  {
    "cause": null,
    "data": {
      "latency": {
        "basis": "verified",
        "note": "electronic wire push at release time",
        "seconds": 5
      },
      "name": "data_wire"
    },
    "op": "channel.add",
    "seq": 2,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  3`** `channel.add` ← cause `—` · _ledger-only_  
  email: latency 30s (verified: typical email delivery time)

  ```json
  {
    "cause": null,
    "data": {
      "latency": {
        "basis": "verified",
        "note": "typical email delivery time",
        "seconds": 30
      },
      "name": "email"
    },
    "op": "channel.add",
    "seq": 3,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  4`** `channel.add` ← cause `—` · _ledger-only_  
  meeting_floor: latency 0s (verified: spoken aloud in the meeting room)

  ```json
  {
    "cause": null,
    "data": {
      "latency": {
        "basis": "verified",
        "note": "spoken aloud in the meeting room",
        "seconds": 0
      },
      "name": "meeting_floor"
    },
    "op": "channel.add",
    "seq": 4,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  5`** `action.define` ← cause `—` · _actions_  
  send_message -- 3 conditions, 2 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "id": "{params.to}",
          "require": "actor_exists"
        },
        {
          "name": "{params.channel}",
          "require": "channel_exists"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "{params.channel}",
            "content": "{params.content}",
            "data": "{params.data}",
            "to": [
              "{params.to}"
            ]
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent message to {params.to} on {params.channel}: {params.content}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "send_message"
    },
    "op": "action.define",
    "seq": 5,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  6`** `action.define` ← cause `—` · _actions_  
  read_message -- 1 conditions, 1 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "info": "{params.info}",
          "require": "noticed_info"
        }
      ],
      "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.",
      "effects": [
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Read message {params.info} in full.",
            "kind": "note",
            "source": "{params.info}"
          }
        ]
      ],
      "verb": "read_message"
    },
    "op": "action.define",
    "seq": 6,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  7`** `action.define` ← cause `—` · _actions_  
  propose_motion -- 4 conditions, 3 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "key": "meeting_open",
          "require": "fact_equals",
          "value": true
        },
        {
          "require": "role_in",
          "roles": [
            "chair"
          ]
        },
        {
          "key": "motion",
          "require": "fact_absent"
        },
        {
          "param": "motion",
          "require": "param_nonempty"
        }
      ],
      "description": "Put a motion on the floor (chair only, meeting in session). params: motion.",
      "effects": [
        [
          "fact.set",
          {
            "key": "motion",
            "value": "{params.motion}"
          }
        ],
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "meeting_floor",
            "content": "Motion on the floor: {params.motion}. Please vote.",
            "data": {
              "motion": "{params.motion}",
              "type": "motion"
            },
            "to": {
              "exclude": [
                "{actor}"
              ],
              "role_in": [
                "chair",
                "member"
              ]
            }
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Put the motion on the floor: {params.motion}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "propose_motion"
    },
    "op": "action.define",
    "seq": 7,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  8`** `action.define` ← cause `—` · _actions_  
  cast_vote -- 5 conditions, 2 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "key": "meeting_open",
          "require": "fact_equals",
          "value": true
        },
        {
          "require": "role_in",
          "roles": [
            "chair",
            "member"
          ]
        },
        {
          "key": "motion",
          "require": "fact_equals",
          "value": "{params.motion}"
        },
        {
          "key": "vote:{actor}",
          "require": "fact_absent"
        },
        {
          "param": "choice",
          "require": "param_in",
          "values": [
            "hold",
            "cut"
          ]
        }
      ],
      "description": "Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).",
      "effects": [
        [
          "fact.set",
          {
            "key": "vote:{actor}",
            "value": "{params.choice}"
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Voted {params.choice} on: {params.motion}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "cast_vote"
    },
    "op": "action.define",
    "seq": 8,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **`  9`** `action.define` ← cause `—` · _actions_  
  prepare_briefing -- 3 conditions, 2 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "require": "role_in",
          "roles": [
            "staff analyst"
          ]
        },
        {
          "info": "{params.based_on_info}",
          "require": "noticed_info"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Prepare a staff briefing from a noticed release and email it to the committee. params: based_on_info, content.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "email",
            "content": "{params.content}",
            "data": {
              "based_on": "{params.based_on_info}",
              "type": "briefing"
            },
            "to": {
              "role_in": [
                "chair",
                "member"
              ]
            }
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent the inflation briefing to the committee.",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "prepare_briefing"
    },
    "op": "action.define",
    "seq": 9,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 10`** `actor.add` ← cause `—` · _state_  
  gus (Gustavo Pena, staff analyst, America/Mexico_City)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "data_wire": {
          "basis": "verified",
          "calendar": {
            "close": "18:00",
            "holidays": [],
            "open": "08:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": null,
          "note": "watching the release calendar is his job; the release time is scheduled"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "brief the committee accurately and fast on new data"
      ],
      "id": "gus",
      "last_decision_at": null,
      "memories": [],
      "name": "Gustavo Pena",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Watch Wednesday's inflation release and brief the committee.",
      "reconsider": [],
      "relationships": {},
      "role": "staff analyst",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "rigorous",
        "neutral"
      ]
    },
    "op": "actor.add",
    "seq": 10,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 11`** `actor.add` ← cause `—` · _state_  
  dana (Dana Ortiz, chair, America/Mexico_City)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "18:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 3600.0,
          "note": "senior official; assistant batches email roughly hourly"
        },
        "meeting_floor": {
          "basis": "verified",
          "calendar": null,
          "check_every_seconds": null,
          "note": "present in the meeting room; speech is heard at once"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "decide the policy rate responsibly"
      ],
      "id": "dana",
      "last_decision_at": null,
      "memories": [],
      "name": "Dana Ortiz",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Review incoming analysis before Thursday's meeting.",
      "reconsider": [],
      "relationships": {
        "eli": "committee colleague",
        "fran": "committee colleague"
      },
      "role": "chair",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "institutionally cautious; discounts single data points"
      ]
    },
    "op": "actor.add",
    "seq": 11,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 12`** `actor.belief` ← cause `—` · _state_  
  dana[inflation] = 'Inflation has been running near 4 percent, above target.' (basis: May CPI report)

  ```json
  {
    "cause": null,
    "data": {
      "actor": "dana",
      "basis": "May CPI report",
      "statement": "Inflation has been running near 4 percent, above target.",
      "topic": "inflation"
    },
    "op": "actor.belief",
    "seq": 12,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 13`** `actor.commit` ← cause `—` · _state_  
  dana commits m1: 'attend the policy meeting' at=2026-06-25T16:00:00+00:00

  ```json
  {
    "cause": null,
    "data": {
      "actor": "dana",
      "at": "2026-06-25T16:00:00+00:00",
      "id": "m1",
      "what": "attend the policy meeting"
    },
    "op": "actor.commit",
    "seq": 13,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 14`** `actor.add` ← cause `—` · _state_  
  eli (Elias Roth, member, America/Mexico_City)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "18:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "checks email frequently between engagements"
        },
        "meeting_floor": {
          "basis": "verified",
          "calendar": null,
          "check_every_seconds": null,
          "note": "present in the meeting room; speech is heard at once"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "decide the policy rate responsibly"
      ],
      "id": "eli",
      "last_decision_at": null,
      "memories": [],
      "name": "Elias Roth",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Review incoming analysis before Thursday's meeting.",
      "reconsider": [],
      "relationships": {
        "dana": "committee colleague",
        "fran": "committee colleague"
      },
      "role": "member",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "data-driven; responds to new evidence"
      ]
    },
    "op": "actor.add",
    "seq": 14,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 15`** `actor.belief` ← cause `—` · _state_  
  eli[inflation] = 'Inflation has been running near 4 percent, above target.' (basis: May CPI report)

  ```json
  {
    "cause": null,
    "data": {
      "actor": "eli",
      "basis": "May CPI report",
      "statement": "Inflation has been running near 4 percent, above target.",
      "topic": "inflation"
    },
    "op": "actor.belief",
    "seq": 15,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 16`** `actor.commit` ← cause `—` · _state_  
  eli commits m1: 'attend the policy meeting' at=2026-06-25T16:00:00+00:00

  ```json
  {
    "cause": null,
    "data": {
      "actor": "eli",
      "at": "2026-06-25T16:00:00+00:00",
      "id": "m1",
      "what": "attend the policy meeting"
    },
    "op": "actor.commit",
    "seq": 16,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 17`** `actor.add` ← cause `—` · _state_  
  fran (Francisca Duarte, member, America/Mexico_City)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "email": {
          "basis": "verified",
          "calendar": {
            "close": "18:00",
            "holidays": [
              "2026-06-24",
              "2026-06-25"
            ],
            "open": "09:00",
            "tz": "America/Mexico_City",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "travel schedule: offline Wednesday-Thursday, resumes Friday"
        },
        "meeting_floor": {
          "basis": "verified",
          "calendar": null,
          "check_every_seconds": null,
          "note": "present in the meeting room; speech is heard at once"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "decide the policy rate responsibly"
      ],
      "id": "fran",
      "last_decision_at": null,
      "memories": [],
      "name": "Francisca Duarte",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Review incoming analysis before Thursday's meeting.",
      "reconsider": [],
      "relationships": {
        "dana": "committee colleague",
        "eli": "committee colleague"
      },
      "role": "member",
      "tz": "America/Mexico_City",
      "unprocessed_info": [],
      "values": [
        "data-driven; responds to new evidence"
      ]
    },
    "op": "actor.add",
    "seq": 17,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 18`** `actor.belief` ← cause `—` · _state_  
  fran[inflation] = 'Inflation has been running near 4 percent, above target.' (basis: May CPI report)

  ```json
  {
    "cause": null,
    "data": {
      "actor": "fran",
      "basis": "May CPI report",
      "statement": "Inflation has been running near 4 percent, above target.",
      "topic": "inflation"
    },
    "op": "actor.belief",
    "seq": 18,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 19`** `actor.commit` ← cause `—` · _state_  
  fran commits m1: 'attend the policy meeting' at=2026-06-25T16:00:00+00:00

  ```json
  {
    "cause": null,
    "data": {
      "actor": "fran",
      "at": "2026-06-25T16:00:00+00:00",
      "id": "m1",
      "what": "attend the policy meeting"
    },
    "op": "actor.commit",
    "seq": 19,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 20`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-06-24T14:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "scheduled statistical release (verified: official calendar)",
        "ops": [
          [
            "fact.set",
            {
              "key": "inflation_release",
              "value": "3.1% y/y (below expectations)"
            }
          ],
          [
            "info.send_new",
            {
              "author": "statistics_wire",
              "channel": "data_wire",
              "content": "June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.",
              "data": {
                "series": "inflation",
                "type": "data_release"
              },
              "to": [
                "gus"
              ]
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-06-24T14:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 20,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 21`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-06-25T16:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "the policy meeting is called to order (verified: official meeting calendar)",
        "ops": [
          [
            "fact.set",
            {
              "key": "meeting_open",
              "value": true
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 21,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 22`** `event.scheduled` ← cause `—` · _ledger-only_  
  [wake.actor] at 2026-06-25T16:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "actor": "dana",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "depth": 0,
      "kind": "wake.actor",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 22,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 23`** `event.scheduled` ← cause `—` · _ledger-only_  
  [wake.actor] at 2026-06-25T16:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "actor": "eli",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "depth": 0,
      "kind": "wake.actor",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 23,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 24`** `event.scheduled` ← cause `—` · _ledger-only_  
  [wake.actor] at 2026-06-25T16:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "actor": "fran",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "depth": 0,
      "kind": "wake.actor",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 24,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 25`** `genesis.sealed` ← cause `—` · _ledger-only_  
  world construction complete; every later record needs a cause

  ```json
  {
    "cause": null,
    "data": {},
    "op": "genesis.sealed",
    "seq": 25,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```
- **` 26`** `event.scheduled` ← cause `25` · _ledger-only_  
  [terminal.cutoff] at 2026-06-25T18:00:00+00:00 depth=0

  ```json
  {
    "cause": 25,
    "data": {
      "data": {
        "question": "What does the committee decide on the policy rate at the 2026-06-25 meeting (hold or cut), counted from cast votes?"
      },
      "depth": 0,
      "kind": "terminal.cutoff",
      "t": "2026-06-25T18:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 26,
    "t": "2026-06-23T14:00:00+00:00"
  }
  ```

### ⏱ 2026-06-24 08:00:00 America/Mexico_City  ·  `2026-06-24T14:00:00+00:00`

- **` 27`** `event.fired` ← cause `20` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 20,
    "data": {
      "data": {
        "note": "scheduled statistical release (verified: official calendar)",
        "ops": [
          [
            "fact.set",
            {
              "key": "inflation_release",
              "value": "3.1% y/y (below expectations)"
            }
          ],
          [
            "info.send_new",
            {
              "author": "statistics_wire",
              "channel": "data_wire",
              "content": "June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.",
              "data": {
                "series": "inflation",
                "type": "data_release"
              },
              "to": [
                "gus"
              ]
            }
          ]
        ]
      },
      "event": 20,
      "kind": "world.ops",
      "t": "2026-06-24T14:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 27,
    "t": "2026-06-24T14:00:00+00:00"
  }
  ```
- **` 28`** `fact.set` ← cause `27` · _state_  
  inflation_release = '3.1% y/y (below expectations)'

  ```json
  {
    "cause": 27,
    "data": {
      "key": "inflation_release",
      "value": "3.1% y/y (below expectations)"
    },
    "op": "fact.set",
    "seq": 28,
    "t": "2026-06-24T14:00:00+00:00"
  }
  ```
- **` 29`** `info.create` ← cause `27` · _info_  
  i29 by statistics_wire: 'June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.' data={'series': 'inflation', 'type': 'data_release'}

  ```json
  {
    "cause": 27,
    "data": {
      "author": "statistics_wire",
      "content": "June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.",
      "data": {
        "series": "inflation",
        "type": "data_release"
      },
      "id": "i29"
    },
    "op": "info.create",
    "seq": 29,
    "t": "2026-06-24T14:00:00+00:00"
  }
  ```
- **` 30`** `info.send` ← cause `29` · _info_  
  i29 -> gus via data_wire

  ```json
  {
    "cause": 29,
    "data": {
      "channel": "data_wire",
      "id": "i29",
      "to": "gus"
    },
    "op": "info.send",
    "seq": 30,
    "t": "2026-06-24T14:00:00+00:00"
  }
  ```
- **` 31`** `event.scheduled` ← cause `30` · _ledger-only_  
  [info.deliver] at 2026-06-24T14:00:05+00:00 depth=0

  ```json
  {
    "cause": 30,
    "data": {
      "data": {
        "channel": "data_wire",
        "info": "i29",
        "to": "gus"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-06-24T14:00:05+00:00"
    },
    "op": "event.scheduled",
    "seq": 31,
    "t": "2026-06-24T14:00:00+00:00"
  }
  ```

### ⏱ 2026-06-24 08:00:05 America/Mexico_City  ·  `2026-06-24T14:00:05+00:00`

- **` 32`** `event.fired` ← cause `31` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 31,
    "data": {
      "data": {
        "channel": "data_wire",
        "info": "i29",
        "to": "gus"
      },
      "event": 31,
      "kind": "info.deliver",
      "t": "2026-06-24T14:00:05+00:00"
    },
    "op": "event.fired",
    "seq": 32,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 33`** `info.deliver` ← cause `32` · _info_  
  i29 DELIVERED to gus via data_wire

  ```json
  {
    "cause": 32,
    "data": {
      "channel": "data_wire",
      "id": "i29",
      "to": "gus"
    },
    "op": "info.deliver",
    "seq": 33,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 34`** `event.scheduled` ← cause `32` · _ledger-only_  
  [info.notice] at 2026-06-24T14:00:05+00:00 depth=1

  ```json
  {
    "cause": 32,
    "data": {
      "data": {
        "actor": "gus",
        "basis": "verified",
        "channel": "data_wire",
        "info": "i29",
        "note": "watching the release calendar is his job; the release time is scheduled"
      },
      "depth": 1,
      "kind": "info.notice",
      "t": "2026-06-24T14:00:05+00:00"
    },
    "op": "event.scheduled",
    "seq": 34,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 35`** `event.fired` ← cause `34` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 34,
    "data": {
      "data": {
        "actor": "gus",
        "basis": "verified",
        "channel": "data_wire",
        "info": "i29",
        "note": "watching the release calendar is his job; the release time is scheduled"
      },
      "event": 34,
      "kind": "info.notice",
      "t": "2026-06-24T14:00:05+00:00"
    },
    "op": "event.fired",
    "seq": 35,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 36`** `info.notice` ← cause `35` · _info_  
  i29 NOTICED by gus

  ```json
  {
    "cause": 35,
    "data": {
      "actor": "gus",
      "id": "i29"
    },
    "op": "info.notice",
    "seq": 36,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 37`** `actor.memory` ← cause `36` · _state_  
  gus <- (observation) 'Noticed message from statistics_wire on data_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.'

  ```json
  {
    "cause": 36,
    "data": {
      "actor": "gus",
      "content": "Noticed message from statistics_wire on data_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.",
      "kind": "observation",
      "source": "i29"
    },
    "op": "actor.memory",
    "seq": 37,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 38`** `actor.view` ← cause `36` · _views_  
  gus shown world v37, reasons=['info_noticed']

  ```json
  {
    "cause": 36,
    "data": {
      "actor": "gus",
      "reasons": [
        {
          "channel": "data_wire",
          "detail": "message from statistics_wire on data_wire",
          "kind": "info_noticed",
          "ref": "i29"
        }
      ],
      "rendered": "Current time:\n2026-06-24 08:00:05 America/Mexico_City\n\nWhy you are being consulted now:\n- info_noticed: message from statistics_wire on data_wire\n\nNew information you have just noticed:\n- [data_wire] message i29 from statistics_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.\n\nYour role: staff analyst\nYour goals:\n- brief the committee accurately and fast on new data\nYour dispositions:\n- rigorous\n- neutral\nYour current plan: Watch Wednesday's inflation release and brief the committee.\nYour memories (oldest first):\n- [2026-06-24 08:00:05 America/Mexico_City] (observation) Noticed message from statistics_wire on data_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.\nActions available to you:\n- prepare_briefing: Prepare a staff briefing from a noticed release and email it to the committee. params: based_on_info, content.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 37
    },
    "op": "actor.view",
    "seq": 38,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 39`** `actor.decision` ← cause `38` · _wakes_  
  gus because ['info_noticed'] -> intentions=['prepare_briefing'] | 'Release is out; preparing the briefing'

  ```json
  {
    "cause": 38,
    "data": {
      "actor": "gus",
      "based_on_version": 37,
      "intentions": [
        "prepare_briefing"
      ],
      "note": "Release is out; preparing the briefing",
      "reasons": [
        {
          "channel": "data_wire",
          "detail": "message from statistics_wire on data_wire",
          "kind": "info_noticed",
          "ref": "i29"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 39,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 40`** `actor.belief` ← cause `39` · _state_  
  gus[inflation] = 'June inflation was 3.1% y/y, below expectations.' (basis: wire release i29)

  ```json
  {
    "cause": 39,
    "data": {
      "actor": "gus",
      "basis": "wire release i29",
      "statement": "June inflation was 3.1% y/y, below expectations.",
      "topic": "inflation"
    },
    "op": "actor.belief",
    "seq": 40,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 41`** `action.propose` ← cause `39` · _intentions+actions_  
  a41 gus:prepare_briefing {'based_on_info': 'i29', 'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'} dur=14400.0s (inferred) based_on_v37

  ```json
  {
    "cause": 39,
    "data": {
      "actor": "gus",
      "based_on_version": 37,
      "completes_when": null,
      "duration": {
        "basis": "inferred",
        "note": "comparable staff analyses take about half a working day",
        "seconds": 14400.0
      },
      "id": "a41",
      "interruptible": false,
      "interruption_note": "",
      "note": "turn the release into a committee briefing",
      "params": {
        "based_on_info": "i29",
        "content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target."
      },
      "verb": "prepare_briefing"
    },
    "op": "action.propose",
    "seq": 41,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 42`** `event.scheduled` ← cause `41` · _ledger-only_  
  [action.start] at 2026-06-24T14:00:05+00:00 depth=2

  ```json
  {
    "cause": 41,
    "data": {
      "data": {
        "action": "a41"
      },
      "depth": 2,
      "kind": "action.start",
      "t": "2026-06-24T14:00:05+00:00"
    },
    "op": "event.scheduled",
    "seq": 42,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 43`** `action.state` ← cause `41` · _actions_  
  a41 -> scheduled

  ```json
  {
    "cause": 41,
    "data": {
      "id": "a41",
      "start_event": 42,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 43,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 44`** `event.fired` ← cause `42` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 42,
    "data": {
      "data": {
        "action": "a41"
      },
      "event": 42,
      "kind": "action.start",
      "t": "2026-06-24T14:00:05+00:00"
    },
    "op": "event.fired",
    "seq": 44,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 45`** `event.scheduled` ← cause `44` · _ledger-only_  
  [action.complete] at 2026-06-24T18:00:05+00:00 depth=0

  ```json
  {
    "cause": 44,
    "data": {
      "data": {
        "action": "a41"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-06-24T18:00:05+00:00"
    },
    "op": "event.scheduled",
    "seq": 45,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 46`** `action.state` ← cause `44` · _actions_  
  a41 -> started completes_at=2026-06-24T18:00:05+00:00

  ```json
  {
    "cause": 44,
    "data": {
      "complete_event": 45,
      "completes_at": "2026-06-24T18:00:05+00:00",
      "id": "a41",
      "state": "started"
    },
    "op": "action.state",
    "seq": 46,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```
- **` 47`** `actor.ongoing` ← cause `44` · _state_  
  gus ongoing -> a41

  ```json
  {
    "cause": 44,
    "data": {
      "action": "a41",
      "actor": "gus"
    },
    "op": "actor.ongoing",
    "seq": 47,
    "t": "2026-06-24T14:00:05+00:00"
  }
  ```

### ⏱ 2026-06-24 12:00:05 America/Mexico_City  ·  `2026-06-24T18:00:05+00:00`

- **` 48`** `event.fired` ← cause `45` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 45,
    "data": {
      "data": {
        "action": "a41"
      },
      "event": 45,
      "kind": "action.complete",
      "t": "2026-06-24T18:00:05+00:00"
    },
    "op": "event.fired",
    "seq": 48,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 49`** `action.state` ← cause `48` · _actions_  
  a41 -> completed

  ```json
  {
    "cause": 48,
    "data": {
      "id": "a41",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 49,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 50`** `actor.ongoing` ← cause `48` · _state_  
  gus ongoing -> None

  ```json
  {
    "cause": 48,
    "data": {
      "action": null,
      "actor": "gus"
    },
    "op": "actor.ongoing",
    "seq": 50,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 51`** `info.create` ← cause `48` · _info_  
  i51 by gus: 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.' data={'based_on': 'i29', 'type': 'briefing'}

  ```json
  {
    "cause": 48,
    "data": {
      "author": "gus",
      "content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.",
      "data": {
        "based_on": "i29",
        "type": "briefing"
      },
      "id": "i51"
    },
    "op": "info.create",
    "seq": 51,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 52`** `info.send` ← cause `51` · _info_  
  i51 -> dana via email

  ```json
  {
    "cause": 51,
    "data": {
      "channel": "email",
      "id": "i51",
      "to": "dana"
    },
    "op": "info.send",
    "seq": 52,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 53`** `event.scheduled` ← cause `52` · _ledger-only_  
  [info.deliver] at 2026-06-24T18:00:35+00:00 depth=0

  ```json
  {
    "cause": 52,
    "data": {
      "data": {
        "channel": "email",
        "info": "i51",
        "to": "dana"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-06-24T18:00:35+00:00"
    },
    "op": "event.scheduled",
    "seq": 53,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 54`** `info.send` ← cause `51` · _info_  
  i51 -> eli via email

  ```json
  {
    "cause": 51,
    "data": {
      "channel": "email",
      "id": "i51",
      "to": "eli"
    },
    "op": "info.send",
    "seq": 54,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 55`** `event.scheduled` ← cause `54` · _ledger-only_  
  [info.deliver] at 2026-06-24T18:00:35+00:00 depth=0

  ```json
  {
    "cause": 54,
    "data": {
      "data": {
        "channel": "email",
        "info": "i51",
        "to": "eli"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-06-24T18:00:35+00:00"
    },
    "op": "event.scheduled",
    "seq": 55,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 56`** `info.send` ← cause `51` · _info_  
  i51 -> fran via email

  ```json
  {
    "cause": 51,
    "data": {
      "channel": "email",
      "id": "i51",
      "to": "fran"
    },
    "op": "info.send",
    "seq": 56,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 57`** `event.scheduled` ← cause `56` · _ledger-only_  
  [info.deliver] at 2026-06-24T18:00:35+00:00 depth=0

  ```json
  {
    "cause": 56,
    "data": {
      "data": {
        "channel": "email",
        "info": "i51",
        "to": "fran"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-06-24T18:00:35+00:00"
    },
    "op": "event.scheduled",
    "seq": 57,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 58`** `actor.memory` ← cause `48` · _state_  
  gus <- (note) 'Sent the inflation briefing to the committee.'

  ```json
  {
    "cause": 48,
    "data": {
      "actor": "gus",
      "content": "Sent the inflation briefing to the committee.",
      "kind": "note",
      "source": "a41"
    },
    "op": "actor.memory",
    "seq": 58,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 59`** `actor.view` ← cause `48` · _views_  
  gus shown world v58, reasons=['action_completed']

  ```json
  {
    "cause": 48,
    "data": {
      "actor": "gus",
      "reasons": [
        {
          "channel": null,
          "detail": "prepare_briefing",
          "kind": "action_completed",
          "ref": "a41"
        }
      ],
      "rendered": "Current time:\n2026-06-24 12:00:05 America/Mexico_City\n\nTime since your previous relevant decision:\n4 hours\n\nWhy you are being consulted now:\n- action_completed: prepare_briefing\n\nYou just finished: prepare_briefing {'based_on_info': 'i29', 'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'}\n\nYour role: staff analyst\nYour goals:\n- brief the committee accurately and fast on new data\nYour dispositions:\n- rigorous\n- neutral\nYour current beliefs:\n- [inflation] June inflation was 3.1% y/y, below expectations. (basis: wire release i29)\nYour current plan: Watch Wednesday's inflation release and brief the committee.\nYour memories (oldest first):\n- [2026-06-24 08:00:05 America/Mexico_City] (observation) Noticed message from statistics_wire on data_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.\n- [2026-06-24 12:00:05 America/Mexico_City] (note) Sent the inflation briefing to the committee.\nActions available to you:\n- prepare_briefing: Prepare a staff briefing from a noticed release and email it to the committee. params: based_on_info, content.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 58
    },
    "op": "actor.view",
    "seq": 59,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```
- **` 60`** `actor.decision` ← cause `59` · _wakes_  
  gus because ['action_completed'] -> intentions=[] | 'Briefing out to the committee'

  ```json
  {
    "cause": 59,
    "data": {
      "actor": "gus",
      "based_on_version": 58,
      "intentions": [],
      "note": "Briefing out to the committee",
      "reasons": [
        {
          "channel": null,
          "detail": "prepare_briefing",
          "kind": "action_completed",
          "ref": "a41"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 60,
    "t": "2026-06-24T18:00:05+00:00"
  }
  ```

### ⏱ 2026-06-24 12:00:35 America/Mexico_City  ·  `2026-06-24T18:00:35+00:00`

- **` 61`** `event.fired` ← cause `53` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 53,
    "data": {
      "data": {
        "channel": "email",
        "info": "i51",
        "to": "dana"
      },
      "event": 53,
      "kind": "info.deliver",
      "t": "2026-06-24T18:00:35+00:00"
    },
    "op": "event.fired",
    "seq": 61,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 62`** `info.deliver` ← cause `61` · _info_  
  i51 DELIVERED to dana via email

  ```json
  {
    "cause": 61,
    "data": {
      "channel": "email",
      "id": "i51",
      "to": "dana"
    },
    "op": "info.deliver",
    "seq": 62,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 63`** `event.scheduled` ← cause `61` · _ledger-only_  
  [info.notice] at 2026-06-24T19:00:00+00:00 depth=0

  ```json
  {
    "cause": 61,
    "data": {
      "data": {
        "actor": "dana",
        "basis": "inferred",
        "channel": "email",
        "info": "i51",
        "note": "senior official; assistant batches email roughly hourly"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-06-24T19:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 63,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 64`** `event.fired` ← cause `55` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 55,
    "data": {
      "data": {
        "channel": "email",
        "info": "i51",
        "to": "eli"
      },
      "event": 55,
      "kind": "info.deliver",
      "t": "2026-06-24T18:00:35+00:00"
    },
    "op": "event.fired",
    "seq": 64,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 65`** `info.deliver` ← cause `64` · _info_  
  i51 DELIVERED to eli via email

  ```json
  {
    "cause": 64,
    "data": {
      "channel": "email",
      "id": "i51",
      "to": "eli"
    },
    "op": "info.deliver",
    "seq": 65,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 66`** `event.scheduled` ← cause `64` · _ledger-only_  
  [info.notice] at 2026-06-24T18:30:00+00:00 depth=0

  ```json
  {
    "cause": 64,
    "data": {
      "data": {
        "actor": "eli",
        "basis": "inferred",
        "channel": "email",
        "info": "i51",
        "note": "checks email frequently between engagements"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-06-24T18:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 66,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 67`** `event.fired` ← cause `57` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 57,
    "data": {
      "data": {
        "channel": "email",
        "info": "i51",
        "to": "fran"
      },
      "event": 57,
      "kind": "info.deliver",
      "t": "2026-06-24T18:00:35+00:00"
    },
    "op": "event.fired",
    "seq": 67,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 68`** `info.deliver` ← cause `67` · _info_  
  i51 DELIVERED to fran via email

  ```json
  {
    "cause": 67,
    "data": {
      "channel": "email",
      "id": "i51",
      "to": "fran"
    },
    "op": "info.deliver",
    "seq": 68,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```
- **` 69`** `event.scheduled` ← cause `67` · _ledger-only_  
  [info.notice] at 2026-06-26T15:00:00+00:00 depth=0

  ```json
  {
    "cause": 67,
    "data": {
      "data": {
        "actor": "fran",
        "basis": "verified",
        "channel": "email",
        "info": "i51",
        "note": "travel schedule: offline Wednesday-Thursday, resumes Friday"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-06-26T15:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 69,
    "t": "2026-06-24T18:00:35+00:00"
  }
  ```

### ⏱ 2026-06-24 12:30:00 America/Mexico_City  ·  `2026-06-24T18:30:00+00:00`

- **` 70`** `event.fired` ← cause `66` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 66,
    "data": {
      "data": {
        "actor": "eli",
        "basis": "inferred",
        "channel": "email",
        "info": "i51",
        "note": "checks email frequently between engagements"
      },
      "event": 66,
      "kind": "info.notice",
      "t": "2026-06-24T18:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 70,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 71`** `info.notice` ← cause `70` · _info_  
  i51 NOTICED by eli

  ```json
  {
    "cause": 70,
    "data": {
      "actor": "eli",
      "id": "i51"
    },
    "op": "info.notice",
    "seq": 71,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 72`** `actor.memory` ← cause `71` · _state_  
  eli <- (observation) 'Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'

  ```json
  {
    "cause": 71,
    "data": {
      "actor": "eli",
      "content": "Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.",
      "kind": "observation",
      "source": "i51"
    },
    "op": "actor.memory",
    "seq": 72,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 73`** `actor.view` ← cause `71` · _views_  
  eli shown world v72, reasons=['info_noticed']

  ```json
  {
    "cause": 71,
    "data": {
      "actor": "eli",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from gus on email",
          "kind": "info_noticed",
          "ref": "i51"
        }
      ],
      "rendered": "Current time:\n2026-06-24 12:30:00 America/Mexico_City\n\nUpcoming commitments:\n- attend the policy meeting in 21 hours, 30 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- info_noticed: message from gus on email\n\nNew information you have just noticed:\n- [email] message i51 from gus: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 72
    },
    "op": "actor.view",
    "seq": 73,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 74`** `actor.decision` ← cause `73` · _wakes_  
  eli because ['info_noticed'] -> intentions=['read_message'] | 'Staff briefing arrived; reading it'

  ```json
  {
    "cause": 73,
    "data": {
      "actor": "eli",
      "based_on_version": 72,
      "intentions": [
        "read_message"
      ],
      "note": "Staff briefing arrived; reading it",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from gus on email",
          "kind": "info_noticed",
          "ref": "i51"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 74,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 75`** `action.propose` ← cause `74` · _intentions+actions_  
  a75 eli:read_message {'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.', 'info': 'i51'} dur=1200.0s (inferred) based_on_v72

  ```json
  {
    "cause": 74,
    "data": {
      "actor": "eli",
      "based_on_version": 72,
      "completes_when": null,
      "duration": {
        "basis": "inferred",
        "note": "a data briefing takes a focused read",
        "seconds": 1200.0
      },
      "id": "a75",
      "interruptible": false,
      "interruption_note": "",
      "note": "reading the staff briefing",
      "params": {
        "content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.",
        "info": "i51"
      },
      "verb": "read_message"
    },
    "op": "action.propose",
    "seq": 75,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 76`** `event.scheduled` ← cause `75` · _ledger-only_  
  [action.start] at 2026-06-24T18:30:00+00:00 depth=1

  ```json
  {
    "cause": 75,
    "data": {
      "data": {
        "action": "a75"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-06-24T18:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 76,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 77`** `action.state` ← cause `75` · _actions_  
  a75 -> scheduled

  ```json
  {
    "cause": 75,
    "data": {
      "id": "a75",
      "start_event": 76,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 77,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 78`** `event.fired` ← cause `76` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 76,
    "data": {
      "data": {
        "action": "a75"
      },
      "event": 76,
      "kind": "action.start",
      "t": "2026-06-24T18:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 78,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 79`** `event.scheduled` ← cause `78` · _ledger-only_  
  [action.complete] at 2026-06-24T18:50:00+00:00 depth=0

  ```json
  {
    "cause": 78,
    "data": {
      "data": {
        "action": "a75"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-06-24T18:50:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 79,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 80`** `action.state` ← cause `78` · _actions_  
  a75 -> started completes_at=2026-06-24T18:50:00+00:00

  ```json
  {
    "cause": 78,
    "data": {
      "complete_event": 79,
      "completes_at": "2026-06-24T18:50:00+00:00",
      "id": "a75",
      "state": "started"
    },
    "op": "action.state",
    "seq": 80,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```
- **` 81`** `actor.ongoing` ← cause `78` · _state_  
  eli ongoing -> a75

  ```json
  {
    "cause": 78,
    "data": {
      "action": "a75",
      "actor": "eli"
    },
    "op": "actor.ongoing",
    "seq": 81,
    "t": "2026-06-24T18:30:00+00:00"
  }
  ```

### ⏱ 2026-06-24 12:50:00 America/Mexico_City  ·  `2026-06-24T18:50:00+00:00`

- **` 82`** `event.fired` ← cause `79` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 79,
    "data": {
      "data": {
        "action": "a75"
      },
      "event": 79,
      "kind": "action.complete",
      "t": "2026-06-24T18:50:00+00:00"
    },
    "op": "event.fired",
    "seq": 82,
    "t": "2026-06-24T18:50:00+00:00"
  }
  ```
- **` 83`** `action.state` ← cause `82` · _actions_  
  a75 -> completed

  ```json
  {
    "cause": 82,
    "data": {
      "id": "a75",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 83,
    "t": "2026-06-24T18:50:00+00:00"
  }
  ```
- **` 84`** `actor.ongoing` ← cause `82` · _state_  
  eli ongoing -> None

  ```json
  {
    "cause": 82,
    "data": {
      "action": null,
      "actor": "eli"
    },
    "op": "actor.ongoing",
    "seq": 84,
    "t": "2026-06-24T18:50:00+00:00"
  }
  ```
- **` 85`** `actor.memory` ← cause `82` · _state_  
  eli <- (note) 'Read message i51 in full.'

  ```json
  {
    "cause": 82,
    "data": {
      "actor": "eli",
      "content": "Read message i51 in full.",
      "kind": "note",
      "source": "i51"
    },
    "op": "actor.memory",
    "seq": 85,
    "t": "2026-06-24T18:50:00+00:00"
  }
  ```
- **` 86`** `actor.view` ← cause `82` · _views_  
  eli shown world v85, reasons=['action_completed']

  ```json
  {
    "cause": 82,
    "data": {
      "actor": "eli",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a75"
        }
      ],
      "rendered": "Current time:\n2026-06-24 12:50:00 America/Mexico_City\n\nTime since your previous relevant decision:\n20 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 21 hours, 10 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i51', 'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'}\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 85
    },
    "op": "actor.view",
    "seq": 86,
    "t": "2026-06-24T18:50:00+00:00"
  }
  ```
- **` 87`** `actor.decision` ← cause `86` · _wakes_  
  eli because ['action_completed'] -> intentions=[] | 'Updating on the staff briefing'

  ```json
  {
    "cause": 86,
    "data": {
      "actor": "eli",
      "based_on_version": 85,
      "intentions": [],
      "note": "Updating on the staff briefing",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a75"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 87,
    "t": "2026-06-24T18:50:00+00:00"
  }
  ```
- **` 88`** `actor.belief` ← cause `87` · _state_  
  eli[inflation] = 'Staff analysis: inflation printed below expectations and is approaching target.' (basis: staff briefing i51, read in full)

  ```json
  {
    "cause": 87,
    "data": {
      "actor": "eli",
      "basis": "staff briefing i51, read in full",
      "statement": "Staff analysis: inflation printed below expectations and is approaching target.",
      "topic": "inflation"
    },
    "op": "actor.belief",
    "seq": 88,
    "t": "2026-06-24T18:50:00+00:00"
  }
  ```

### ⏱ 2026-06-24 13:00:00 America/Mexico_City  ·  `2026-06-24T19:00:00+00:00`

- **` 89`** `event.fired` ← cause `63` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 63,
    "data": {
      "data": {
        "actor": "dana",
        "basis": "inferred",
        "channel": "email",
        "info": "i51",
        "note": "senior official; assistant batches email roughly hourly"
      },
      "event": 63,
      "kind": "info.notice",
      "t": "2026-06-24T19:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 89,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 90`** `info.notice` ← cause `89` · _info_  
  i51 NOTICED by dana

  ```json
  {
    "cause": 89,
    "data": {
      "actor": "dana",
      "id": "i51"
    },
    "op": "info.notice",
    "seq": 90,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 91`** `actor.memory` ← cause `90` · _state_  
  dana <- (observation) 'Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'

  ```json
  {
    "cause": 90,
    "data": {
      "actor": "dana",
      "content": "Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.",
      "kind": "observation",
      "source": "i51"
    },
    "op": "actor.memory",
    "seq": 91,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 92`** `actor.view` ← cause `90` · _views_  
  dana shown world v91, reasons=['info_noticed']

  ```json
  {
    "cause": 90,
    "data": {
      "actor": "dana",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from gus on email",
          "kind": "info_noticed",
          "ref": "i51"
        }
      ],
      "rendered": "Current time:\n2026-06-24 13:00:00 America/Mexico_City\n\nUpcoming commitments:\n- attend the policy meeting in 21 hours (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- info_noticed: message from gus on email\n\nNew information you have just noticed:\n- [email] message i51 from gus: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 91
    },
    "op": "actor.view",
    "seq": 92,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 93`** `actor.decision` ← cause `92` · _wakes_  
  dana because ['info_noticed'] -> intentions=['read_message'] | 'Staff briefing arrived; reading it'

  ```json
  {
    "cause": 92,
    "data": {
      "actor": "dana",
      "based_on_version": 91,
      "intentions": [
        "read_message"
      ],
      "note": "Staff briefing arrived; reading it",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from gus on email",
          "kind": "info_noticed",
          "ref": "i51"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 93,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 94`** `action.propose` ← cause `93` · _intentions+actions_  
  a94 dana:read_message {'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.', 'info': 'i51'} dur=1200.0s (inferred) based_on_v91

  ```json
  {
    "cause": 93,
    "data": {
      "actor": "dana",
      "based_on_version": 91,
      "completes_when": null,
      "duration": {
        "basis": "inferred",
        "note": "a data briefing takes a focused read",
        "seconds": 1200.0
      },
      "id": "a94",
      "interruptible": false,
      "interruption_note": "",
      "note": "reading the staff briefing",
      "params": {
        "content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.",
        "info": "i51"
      },
      "verb": "read_message"
    },
    "op": "action.propose",
    "seq": 94,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 95`** `event.scheduled` ← cause `94` · _ledger-only_  
  [action.start] at 2026-06-24T19:00:00+00:00 depth=1

  ```json
  {
    "cause": 94,
    "data": {
      "data": {
        "action": "a94"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-06-24T19:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 95,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 96`** `action.state` ← cause `94` · _actions_  
  a94 -> scheduled

  ```json
  {
    "cause": 94,
    "data": {
      "id": "a94",
      "start_event": 95,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 96,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 97`** `event.fired` ← cause `95` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 95,
    "data": {
      "data": {
        "action": "a94"
      },
      "event": 95,
      "kind": "action.start",
      "t": "2026-06-24T19:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 97,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 98`** `event.scheduled` ← cause `97` · _ledger-only_  
  [action.complete] at 2026-06-24T19:20:00+00:00 depth=0

  ```json
  {
    "cause": 97,
    "data": {
      "data": {
        "action": "a94"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-06-24T19:20:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 98,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **` 99`** `action.state` ← cause `97` · _actions_  
  a94 -> started completes_at=2026-06-24T19:20:00+00:00

  ```json
  {
    "cause": 97,
    "data": {
      "complete_event": 98,
      "completes_at": "2026-06-24T19:20:00+00:00",
      "id": "a94",
      "state": "started"
    },
    "op": "action.state",
    "seq": 99,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```
- **`100`** `actor.ongoing` ← cause `97` · _state_  
  dana ongoing -> a94

  ```json
  {
    "cause": 97,
    "data": {
      "action": "a94",
      "actor": "dana"
    },
    "op": "actor.ongoing",
    "seq": 100,
    "t": "2026-06-24T19:00:00+00:00"
  }
  ```

### ⏱ 2026-06-24 13:20:00 America/Mexico_City  ·  `2026-06-24T19:20:00+00:00`

- **`101`** `event.fired` ← cause `98` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 98,
    "data": {
      "data": {
        "action": "a94"
      },
      "event": 98,
      "kind": "action.complete",
      "t": "2026-06-24T19:20:00+00:00"
    },
    "op": "event.fired",
    "seq": 101,
    "t": "2026-06-24T19:20:00+00:00"
  }
  ```
- **`102`** `action.state` ← cause `101` · _actions_  
  a94 -> completed

  ```json
  {
    "cause": 101,
    "data": {
      "id": "a94",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 102,
    "t": "2026-06-24T19:20:00+00:00"
  }
  ```
- **`103`** `actor.ongoing` ← cause `101` · _state_  
  dana ongoing -> None

  ```json
  {
    "cause": 101,
    "data": {
      "action": null,
      "actor": "dana"
    },
    "op": "actor.ongoing",
    "seq": 103,
    "t": "2026-06-24T19:20:00+00:00"
  }
  ```
- **`104`** `actor.memory` ← cause `101` · _state_  
  dana <- (note) 'Read message i51 in full.'

  ```json
  {
    "cause": 101,
    "data": {
      "actor": "dana",
      "content": "Read message i51 in full.",
      "kind": "note",
      "source": "i51"
    },
    "op": "actor.memory",
    "seq": 104,
    "t": "2026-06-24T19:20:00+00:00"
  }
  ```
- **`105`** `actor.view` ← cause `101` · _views_  
  dana shown world v104, reasons=['action_completed']

  ```json
  {
    "cause": 101,
    "data": {
      "actor": "dana",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a94"
        }
      ],
      "rendered": "Current time:\n2026-06-24 13:20:00 America/Mexico_City\n\nTime since your previous relevant decision:\n20 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 20 hours, 40 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i51', 'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'}\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 104
    },
    "op": "actor.view",
    "seq": 105,
    "t": "2026-06-24T19:20:00+00:00"
  }
  ```
- **`106`** `actor.decision` ← cause `105` · _wakes_  
  dana because ['action_completed'] -> intentions=[] | 'Updating on the staff briefing'

  ```json
  {
    "cause": 105,
    "data": {
      "actor": "dana",
      "based_on_version": 104,
      "intentions": [],
      "note": "Updating on the staff briefing",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a94"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 106,
    "t": "2026-06-24T19:20:00+00:00"
  }
  ```
- **`107`** `actor.belief` ← cause `106` · _state_  
  dana[inflation] = 'Staff analysis: inflation printed below expectations and is approaching target.' (basis: staff briefing i51, read in full)

  ```json
  {
    "cause": 106,
    "data": {
      "actor": "dana",
      "basis": "staff briefing i51, read in full",
      "statement": "Staff analysis: inflation printed below expectations and is approaching target.",
      "topic": "inflation"
    },
    "op": "actor.belief",
    "seq": 107,
    "t": "2026-06-24T19:20:00+00:00"
  }
  ```

### ⏱ 2026-06-25 10:00:00 America/Mexico_City  ·  `2026-06-25T16:00:00+00:00`

- **`108`** `event.fired` ← cause `21` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 21,
    "data": {
      "data": {
        "note": "the policy meeting is called to order (verified: official meeting calendar)",
        "ops": [
          [
            "fact.set",
            {
              "key": "meeting_open",
              "value": true
            }
          ]
        ]
      },
      "event": 21,
      "kind": "world.ops",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 108,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`109`** `fact.set` ← cause `108` · _state_  
  meeting_open = True

  ```json
  {
    "cause": 108,
    "data": {
      "key": "meeting_open",
      "value": true
    },
    "op": "fact.set",
    "seq": 109,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`110`** `event.fired` ← cause `22` · _ledger-only_  
  [wake.actor]

  ```json
  {
    "cause": 22,
    "data": {
      "data": {
        "actor": "dana",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "event": 22,
      "kind": "wake.actor",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 110,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`111`** `event.fired` ← cause `23` · _ledger-only_  
  [wake.actor]

  ```json
  {
    "cause": 23,
    "data": {
      "data": {
        "actor": "eli",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "event": 23,
      "kind": "wake.actor",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 111,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`112`** `event.fired` ← cause `24` · _ledger-only_  
  [wake.actor]

  ```json
  {
    "cause": 24,
    "data": {
      "data": {
        "actor": "fran",
        "detail": "m1: the policy meeting begins",
        "reason": "scheduled_commitment"
      },
      "event": 24,
      "kind": "wake.actor",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 112,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`113`** `actor.view` ← cause `110` · _views_  
  dana shown world v112, reasons=['scheduled_commitment']

  ```json
  {
    "cause": 110,
    "data": {
      "actor": "dana",
      "reasons": [
        {
          "channel": null,
          "detail": "m1: the policy meeting begins",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:00:00 America/Mexico_City\n\nTime since your previous relevant decision:\n20 hours, 40 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 0 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- scheduled_commitment: m1: the policy meeting begins\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 112
    },
    "op": "actor.view",
    "seq": 113,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`114`** `actor.decision` ← cause `113` · _wakes_  
  dana because ['scheduled_commitment'] -> intentions=['propose_motion'] | 'Meeting open; putting the hold motion on the floor'

  ```json
  {
    "cause": 113,
    "data": {
      "actor": "dana",
      "based_on_version": 112,
      "intentions": [
        "propose_motion"
      ],
      "note": "Meeting open; putting the hold motion on the floor",
      "reasons": [
        {
          "channel": null,
          "detail": "m1: the policy meeting begins",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ]
    },
    "op": "actor.decision",
    "seq": 114,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`115`** `actor.emotion` ← cause `114` · _state_  
  dana: 'focused; running the meeting'

  ```json
  {
    "cause": 114,
    "data": {
      "actor": "dana",
      "statement": "focused; running the meeting"
    },
    "op": "actor.emotion",
    "seq": 115,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`116`** `action.propose` ← cause `114` · _intentions+actions_  
  a116 dana:propose_motion {'motion': 'hold the policy rate'} dur=300.0s (actor_chosen) based_on_v112

  ```json
  {
    "cause": 114,
    "data": {
      "actor": "dana",
      "based_on_version": 112,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "opening remarks and stating the motion",
        "seconds": 300.0
      },
      "id": "a116",
      "interruptible": false,
      "interruption_note": "",
      "note": "chairing: putting the motion to a vote",
      "params": {
        "motion": "hold the policy rate"
      },
      "verb": "propose_motion"
    },
    "op": "action.propose",
    "seq": 116,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`117`** `event.scheduled` ← cause `116` · _ledger-only_  
  [action.start] at 2026-06-25T16:00:00+00:00 depth=1

  ```json
  {
    "cause": 116,
    "data": {
      "data": {
        "action": "a116"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 117,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`118`** `action.state` ← cause `116` · _actions_  
  a116 -> scheduled

  ```json
  {
    "cause": 116,
    "data": {
      "id": "a116",
      "start_event": 117,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 118,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`119`** `actor.view` ← cause `111` · _views_  
  eli shown world v118, reasons=['scheduled_commitment']

  ```json
  {
    "cause": 111,
    "data": {
      "actor": "eli",
      "reasons": [
        {
          "channel": null,
          "detail": "m1: the policy meeting begins",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:00:00 America/Mexico_City\n\nTime since your previous relevant decision:\n21 hours, 10 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 0 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- scheduled_commitment: m1: the policy meeting begins\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 118
    },
    "op": "actor.view",
    "seq": 119,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`120`** `actor.decision` ← cause `119` · _wakes_  
  eli because ['scheduled_commitment'] -> intentions=[] | 'In the meeting; waiting for the chair'

  ```json
  {
    "cause": 119,
    "data": {
      "actor": "eli",
      "based_on_version": 118,
      "intentions": [],
      "note": "In the meeting; waiting for the chair",
      "reasons": [
        {
          "channel": null,
          "detail": "m1: the policy meeting begins",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ]
    },
    "op": "actor.decision",
    "seq": 120,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`121`** `actor.emotion` ← cause `120` · _state_  
  eli: 'attentive; in the meeting'

  ```json
  {
    "cause": 120,
    "data": {
      "actor": "eli",
      "statement": "attentive; in the meeting"
    },
    "op": "actor.emotion",
    "seq": 121,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`122`** `actor.view` ← cause `112` · _views_  
  fran shown world v121, reasons=['scheduled_commitment']

  ```json
  {
    "cause": 112,
    "data": {
      "actor": "fran",
      "reasons": [
        {
          "channel": null,
          "detail": "m1: the policy meeting begins",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:00:00 America/Mexico_City\n\nUpcoming commitments:\n- attend the policy meeting in 0 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- scheduled_commitment: m1: the policy meeting begins\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- eli: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 121
    },
    "op": "actor.view",
    "seq": 122,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`123`** `actor.decision` ← cause `122` · _wakes_  
  fran because ['scheduled_commitment'] -> intentions=[] | 'In the meeting; waiting for the chair'

  ```json
  {
    "cause": 122,
    "data": {
      "actor": "fran",
      "based_on_version": 121,
      "intentions": [],
      "note": "In the meeting; waiting for the chair",
      "reasons": [
        {
          "channel": null,
          "detail": "m1: the policy meeting begins",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ]
    },
    "op": "actor.decision",
    "seq": 123,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`124`** `actor.emotion` ← cause `123` · _state_  
  fran: 'attentive; in the meeting'

  ```json
  {
    "cause": 123,
    "data": {
      "actor": "fran",
      "statement": "attentive; in the meeting"
    },
    "op": "actor.emotion",
    "seq": 124,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`125`** `event.fired` ← cause `117` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 117,
    "data": {
      "data": {
        "action": "a116"
      },
      "event": 117,
      "kind": "action.start",
      "t": "2026-06-25T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 125,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`126`** `event.scheduled` ← cause `125` · _ledger-only_  
  [action.complete] at 2026-06-25T16:05:00+00:00 depth=0

  ```json
  {
    "cause": 125,
    "data": {
      "data": {
        "action": "a116"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 126,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`127`** `action.state` ← cause `125` · _actions_  
  a116 -> started completes_at=2026-06-25T16:05:00+00:00

  ```json
  {
    "cause": 125,
    "data": {
      "complete_event": 126,
      "completes_at": "2026-06-25T16:05:00+00:00",
      "id": "a116",
      "state": "started"
    },
    "op": "action.state",
    "seq": 127,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```
- **`128`** `actor.ongoing` ← cause `125` · _state_  
  dana ongoing -> a116

  ```json
  {
    "cause": 125,
    "data": {
      "action": "a116",
      "actor": "dana"
    },
    "op": "actor.ongoing",
    "seq": 128,
    "t": "2026-06-25T16:00:00+00:00"
  }
  ```

### ⏱ 2026-06-25 10:05:00 America/Mexico_City  ·  `2026-06-25T16:05:00+00:00`

- **`129`** `event.fired` ← cause `126` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 126,
    "data": {
      "data": {
        "action": "a116"
      },
      "event": 126,
      "kind": "action.complete",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 129,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`130`** `action.state` ← cause `129` · _actions_  
  a116 -> completed

  ```json
  {
    "cause": 129,
    "data": {
      "id": "a116",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 130,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`131`** `actor.ongoing` ← cause `129` · _state_  
  dana ongoing -> None

  ```json
  {
    "cause": 129,
    "data": {
      "action": null,
      "actor": "dana"
    },
    "op": "actor.ongoing",
    "seq": 131,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`132`** `fact.set` ← cause `129` · _state_  
  motion = 'hold the policy rate'

  ```json
  {
    "cause": 129,
    "data": {
      "key": "motion",
      "value": "hold the policy rate"
    },
    "op": "fact.set",
    "seq": 132,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`133`** `info.create` ← cause `129` · _info_  
  i133 by dana: 'Motion on the floor: hold the policy rate. Please vote.' data={'motion': 'hold the policy rate', 'type': 'motion'}

  ```json
  {
    "cause": 129,
    "data": {
      "author": "dana",
      "content": "Motion on the floor: hold the policy rate. Please vote.",
      "data": {
        "motion": "hold the policy rate",
        "type": "motion"
      },
      "id": "i133"
    },
    "op": "info.create",
    "seq": 133,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`134`** `info.send` ← cause `133` · _info_  
  i133 -> eli via meeting_floor

  ```json
  {
    "cause": 133,
    "data": {
      "channel": "meeting_floor",
      "id": "i133",
      "to": "eli"
    },
    "op": "info.send",
    "seq": 134,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`135`** `event.scheduled` ← cause `134` · _ledger-only_  
  [info.deliver] at 2026-06-25T16:05:00+00:00 depth=1

  ```json
  {
    "cause": 134,
    "data": {
      "data": {
        "channel": "meeting_floor",
        "info": "i133",
        "to": "eli"
      },
      "depth": 1,
      "kind": "info.deliver",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 135,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`136`** `info.send` ← cause `133` · _info_  
  i133 -> fran via meeting_floor

  ```json
  {
    "cause": 133,
    "data": {
      "channel": "meeting_floor",
      "id": "i133",
      "to": "fran"
    },
    "op": "info.send",
    "seq": 136,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`137`** `event.scheduled` ← cause `136` · _ledger-only_  
  [info.deliver] at 2026-06-25T16:05:00+00:00 depth=1

  ```json
  {
    "cause": 136,
    "data": {
      "data": {
        "channel": "meeting_floor",
        "info": "i133",
        "to": "fran"
      },
      "depth": 1,
      "kind": "info.deliver",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 137,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`138`** `actor.memory` ← cause `129` · _state_  
  dana <- (note) 'Put the motion on the floor: hold the policy rate'

  ```json
  {
    "cause": 129,
    "data": {
      "actor": "dana",
      "content": "Put the motion on the floor: hold the policy rate",
      "kind": "note",
      "source": "a116"
    },
    "op": "actor.memory",
    "seq": 138,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`139`** `event.fired` ← cause `135` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 135,
    "data": {
      "data": {
        "channel": "meeting_floor",
        "info": "i133",
        "to": "eli"
      },
      "event": 135,
      "kind": "info.deliver",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 139,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`140`** `info.deliver` ← cause `139` · _info_  
  i133 DELIVERED to eli via meeting_floor

  ```json
  {
    "cause": 139,
    "data": {
      "channel": "meeting_floor",
      "id": "i133",
      "to": "eli"
    },
    "op": "info.deliver",
    "seq": 140,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`141`** `event.scheduled` ← cause `139` · _ledger-only_  
  [info.notice] at 2026-06-25T16:05:00+00:00 depth=2

  ```json
  {
    "cause": 139,
    "data": {
      "data": {
        "actor": "eli",
        "basis": "verified",
        "channel": "meeting_floor",
        "info": "i133",
        "note": "present in the meeting room; speech is heard at once"
      },
      "depth": 2,
      "kind": "info.notice",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 141,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`142`** `event.fired` ← cause `137` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 137,
    "data": {
      "data": {
        "channel": "meeting_floor",
        "info": "i133",
        "to": "fran"
      },
      "event": 137,
      "kind": "info.deliver",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 142,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`143`** `info.deliver` ← cause `142` · _info_  
  i133 DELIVERED to fran via meeting_floor

  ```json
  {
    "cause": 142,
    "data": {
      "channel": "meeting_floor",
      "id": "i133",
      "to": "fran"
    },
    "op": "info.deliver",
    "seq": 143,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`144`** `event.scheduled` ← cause `142` · _ledger-only_  
  [info.notice] at 2026-06-25T16:05:00+00:00 depth=2

  ```json
  {
    "cause": 142,
    "data": {
      "data": {
        "actor": "fran",
        "basis": "verified",
        "channel": "meeting_floor",
        "info": "i133",
        "note": "present in the meeting room; speech is heard at once"
      },
      "depth": 2,
      "kind": "info.notice",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 144,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`145`** `event.fired` ← cause `141` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 141,
    "data": {
      "data": {
        "actor": "eli",
        "basis": "verified",
        "channel": "meeting_floor",
        "info": "i133",
        "note": "present in the meeting room; speech is heard at once"
      },
      "event": 141,
      "kind": "info.notice",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 145,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`146`** `info.notice` ← cause `145` · _info_  
  i133 NOTICED by eli

  ```json
  {
    "cause": 145,
    "data": {
      "actor": "eli",
      "id": "i133"
    },
    "op": "info.notice",
    "seq": 146,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`147`** `actor.memory` ← cause `146` · _state_  
  eli <- (observation) 'Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.'

  ```json
  {
    "cause": 146,
    "data": {
      "actor": "eli",
      "content": "Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.",
      "kind": "observation",
      "source": "i133"
    },
    "op": "actor.memory",
    "seq": 147,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`148`** `event.fired` ← cause `144` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 144,
    "data": {
      "data": {
        "actor": "fran",
        "basis": "verified",
        "channel": "meeting_floor",
        "info": "i133",
        "note": "present in the meeting room; speech is heard at once"
      },
      "event": 144,
      "kind": "info.notice",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 148,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`149`** `info.notice` ← cause `148` · _info_  
  i133 NOTICED by fran

  ```json
  {
    "cause": 148,
    "data": {
      "actor": "fran",
      "id": "i133"
    },
    "op": "info.notice",
    "seq": 149,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`150`** `actor.memory` ← cause `149` · _state_  
  fran <- (observation) 'Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.'

  ```json
  {
    "cause": 149,
    "data": {
      "actor": "fran",
      "content": "Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.",
      "kind": "observation",
      "source": "i133"
    },
    "op": "actor.memory",
    "seq": 150,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`151`** `actor.view` ← cause `129` · _views_  
  dana shown world v150, reasons=['action_completed']

  ```json
  {
    "cause": 129,
    "data": {
      "actor": "dana",
      "reasons": [
        {
          "channel": null,
          "detail": "propose_motion",
          "kind": "action_completed",
          "ref": "a116"
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:05:00 America/Mexico_City\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- action_completed: propose_motion\n\nYou just finished: propose_motion {'motion': 'hold the policy rate'}\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour emotional state: focused; running the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (note) Put the motion on the floor: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 150
    },
    "op": "actor.view",
    "seq": 151,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`152`** `actor.decision` ← cause `151` · _wakes_  
  dana because ['action_completed'] -> intentions=['cast_vote'] | "Motion is on the floor; casting the chair's vote"

  ```json
  {
    "cause": 151,
    "data": {
      "actor": "dana",
      "based_on_version": 150,
      "intentions": [
        "cast_vote"
      ],
      "note": "Motion is on the floor; casting the chair's vote",
      "reasons": [
        {
          "channel": null,
          "detail": "propose_motion",
          "kind": "action_completed",
          "ref": "a116"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 152,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`153`** `action.propose` ← cause `152` · _intentions+actions_  
  a153 dana:cast_vote {'choice': 'hold', 'motion': 'hold the policy rate'} dur=120.0s (actor_chosen) based_on_v150

  ```json
  {
    "cause": 152,
    "data": {
      "actor": "dana",
      "based_on_version": 150,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "stating a vote in the room",
        "seconds": 120.0
      },
      "id": "a153",
      "interruptible": false,
      "interruption_note": "",
      "note": "chair votes after opening the motion",
      "params": {
        "choice": "hold",
        "motion": "hold the policy rate"
      },
      "verb": "cast_vote"
    },
    "op": "action.propose",
    "seq": 153,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`154`** `event.scheduled` ← cause `153` · _ledger-only_  
  [action.start] at 2026-06-25T16:05:00+00:00 depth=3

  ```json
  {
    "cause": 153,
    "data": {
      "data": {
        "action": "a153"
      },
      "depth": 3,
      "kind": "action.start",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 154,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`155`** `action.state` ← cause `153` · _actions_  
  a153 -> scheduled

  ```json
  {
    "cause": 153,
    "data": {
      "id": "a153",
      "start_event": 154,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 155,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`156`** `actor.view` ← cause `146` · _views_  
  eli shown world v155, reasons=['info_noticed']

  ```json
  {
    "cause": 146,
    "data": {
      "actor": "eli",
      "reasons": [
        {
          "channel": "meeting_floor",
          "detail": "message from dana on meeting_floor",
          "kind": "info_noticed",
          "ref": "i133"
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:05:00 America/Mexico_City\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from dana on meeting_floor\n\nNew information you have just noticed:\n- [meeting_floor] message i133 from dana: Motion on the floor: hold the policy rate. Please vote.\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 155
    },
    "op": "actor.view",
    "seq": 156,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`157`** `actor.decision` ← cause `156` · _wakes_  
  eli because ['info_noticed'] -> intentions=['cast_vote'] | 'Voting cut based on current beliefs'

  ```json
  {
    "cause": 156,
    "data": {
      "actor": "eli",
      "based_on_version": 155,
      "intentions": [
        "cast_vote"
      ],
      "note": "Voting cut based on current beliefs",
      "reasons": [
        {
          "channel": "meeting_floor",
          "detail": "message from dana on meeting_floor",
          "kind": "info_noticed",
          "ref": "i133"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 157,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`158`** `action.propose` ← cause `157` · _intentions+actions_  
  a158 eli:cast_vote {'choice': 'cut', 'motion': 'hold the policy rate'} dur=120.0s (actor_chosen) based_on_v155

  ```json
  {
    "cause": 157,
    "data": {
      "actor": "eli",
      "based_on_version": 155,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "stating a vote in the room",
        "seconds": 120.0
      },
      "id": "a158",
      "interruptible": false,
      "interruption_note": "",
      "note": "voting on the motion",
      "params": {
        "choice": "cut",
        "motion": "hold the policy rate"
      },
      "verb": "cast_vote"
    },
    "op": "action.propose",
    "seq": 158,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`159`** `event.scheduled` ← cause `158` · _ledger-only_  
  [action.start] at 2026-06-25T16:05:00+00:00 depth=3

  ```json
  {
    "cause": 158,
    "data": {
      "data": {
        "action": "a158"
      },
      "depth": 3,
      "kind": "action.start",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 159,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`160`** `action.state` ← cause `158` · _actions_  
  a158 -> scheduled

  ```json
  {
    "cause": 158,
    "data": {
      "id": "a158",
      "start_event": 159,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 160,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`161`** `actor.view` ← cause `149` · _views_  
  fran shown world v160, reasons=['info_noticed']

  ```json
  {
    "cause": 149,
    "data": {
      "actor": "fran",
      "reasons": [
        {
          "channel": "meeting_floor",
          "detail": "message from dana on meeting_floor",
          "kind": "info_noticed",
          "ref": "i133"
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:05:00 America/Mexico_City\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from dana on meeting_floor\n\nNew information you have just noticed:\n- [meeting_floor] message i133 from dana: Motion on the floor: hold the policy rate. Please vote.\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- eli: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 160
    },
    "op": "actor.view",
    "seq": 161,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`162`** `actor.decision` ← cause `161` · _wakes_  
  fran because ['info_noticed'] -> intentions=['cast_vote'] | 'Voting hold based on current beliefs'

  ```json
  {
    "cause": 161,
    "data": {
      "actor": "fran",
      "based_on_version": 160,
      "intentions": [
        "cast_vote"
      ],
      "note": "Voting hold based on current beliefs",
      "reasons": [
        {
          "channel": "meeting_floor",
          "detail": "message from dana on meeting_floor",
          "kind": "info_noticed",
          "ref": "i133"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 162,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`163`** `action.propose` ← cause `162` · _intentions+actions_  
  a163 fran:cast_vote {'choice': 'hold', 'motion': 'hold the policy rate'} dur=120.0s (actor_chosen) based_on_v160

  ```json
  {
    "cause": 162,
    "data": {
      "actor": "fran",
      "based_on_version": 160,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "stating a vote in the room",
        "seconds": 120.0
      },
      "id": "a163",
      "interruptible": false,
      "interruption_note": "",
      "note": "voting on the motion",
      "params": {
        "choice": "hold",
        "motion": "hold the policy rate"
      },
      "verb": "cast_vote"
    },
    "op": "action.propose",
    "seq": 163,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`164`** `event.scheduled` ← cause `163` · _ledger-only_  
  [action.start] at 2026-06-25T16:05:00+00:00 depth=3

  ```json
  {
    "cause": 163,
    "data": {
      "data": {
        "action": "a163"
      },
      "depth": 3,
      "kind": "action.start",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 164,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`165`** `action.state` ← cause `163` · _actions_  
  a163 -> scheduled

  ```json
  {
    "cause": 163,
    "data": {
      "id": "a163",
      "start_event": 164,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 165,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`166`** `event.fired` ← cause `154` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 154,
    "data": {
      "data": {
        "action": "a153"
      },
      "event": 154,
      "kind": "action.start",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 166,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`167`** `event.scheduled` ← cause `166` · _ledger-only_  
  [action.complete] at 2026-06-25T16:07:00+00:00 depth=0

  ```json
  {
    "cause": 166,
    "data": {
      "data": {
        "action": "a153"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-06-25T16:07:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 167,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`168`** `action.state` ← cause `166` · _actions_  
  a153 -> started completes_at=2026-06-25T16:07:00+00:00

  ```json
  {
    "cause": 166,
    "data": {
      "complete_event": 167,
      "completes_at": "2026-06-25T16:07:00+00:00",
      "id": "a153",
      "state": "started"
    },
    "op": "action.state",
    "seq": 168,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`169`** `actor.ongoing` ← cause `166` · _state_  
  dana ongoing -> a153

  ```json
  {
    "cause": 166,
    "data": {
      "action": "a153",
      "actor": "dana"
    },
    "op": "actor.ongoing",
    "seq": 169,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`170`** `event.fired` ← cause `159` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 159,
    "data": {
      "data": {
        "action": "a158"
      },
      "event": 159,
      "kind": "action.start",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 170,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`171`** `event.scheduled` ← cause `170` · _ledger-only_  
  [action.complete] at 2026-06-25T16:07:00+00:00 depth=0

  ```json
  {
    "cause": 170,
    "data": {
      "data": {
        "action": "a158"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-06-25T16:07:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 171,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`172`** `action.state` ← cause `170` · _actions_  
  a158 -> started completes_at=2026-06-25T16:07:00+00:00

  ```json
  {
    "cause": 170,
    "data": {
      "complete_event": 171,
      "completes_at": "2026-06-25T16:07:00+00:00",
      "id": "a158",
      "state": "started"
    },
    "op": "action.state",
    "seq": 172,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`173`** `actor.ongoing` ← cause `170` · _state_  
  eli ongoing -> a158

  ```json
  {
    "cause": 170,
    "data": {
      "action": "a158",
      "actor": "eli"
    },
    "op": "actor.ongoing",
    "seq": 173,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`174`** `event.fired` ← cause `164` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 164,
    "data": {
      "data": {
        "action": "a163"
      },
      "event": 164,
      "kind": "action.start",
      "t": "2026-06-25T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 174,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`175`** `event.scheduled` ← cause `174` · _ledger-only_  
  [action.complete] at 2026-06-25T16:07:00+00:00 depth=0

  ```json
  {
    "cause": 174,
    "data": {
      "data": {
        "action": "a163"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-06-25T16:07:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 175,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`176`** `action.state` ← cause `174` · _actions_  
  a163 -> started completes_at=2026-06-25T16:07:00+00:00

  ```json
  {
    "cause": 174,
    "data": {
      "complete_event": 175,
      "completes_at": "2026-06-25T16:07:00+00:00",
      "id": "a163",
      "state": "started"
    },
    "op": "action.state",
    "seq": 176,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```
- **`177`** `actor.ongoing` ← cause `174` · _state_  
  fran ongoing -> a163

  ```json
  {
    "cause": 174,
    "data": {
      "action": "a163",
      "actor": "fran"
    },
    "op": "actor.ongoing",
    "seq": 177,
    "t": "2026-06-25T16:05:00+00:00"
  }
  ```

### ⏱ 2026-06-25 10:07:00 America/Mexico_City  ·  `2026-06-25T16:07:00+00:00`

- **`178`** `event.fired` ← cause `167` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 167,
    "data": {
      "data": {
        "action": "a153"
      },
      "event": 167,
      "kind": "action.complete",
      "t": "2026-06-25T16:07:00+00:00"
    },
    "op": "event.fired",
    "seq": 178,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`179`** `action.state` ← cause `178` · _actions_  
  a153 -> completed

  ```json
  {
    "cause": 178,
    "data": {
      "id": "a153",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 179,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`180`** `actor.ongoing` ← cause `178` · _state_  
  dana ongoing -> None

  ```json
  {
    "cause": 178,
    "data": {
      "action": null,
      "actor": "dana"
    },
    "op": "actor.ongoing",
    "seq": 180,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`181`** `fact.set` ← cause `178` · _state_  
  vote:dana = 'hold'

  ```json
  {
    "cause": 178,
    "data": {
      "key": "vote:dana",
      "value": "hold"
    },
    "op": "fact.set",
    "seq": 181,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`182`** `actor.memory` ← cause `178` · _state_  
  dana <- (note) 'Voted hold on: hold the policy rate'

  ```json
  {
    "cause": 178,
    "data": {
      "actor": "dana",
      "content": "Voted hold on: hold the policy rate",
      "kind": "note",
      "source": "a153"
    },
    "op": "actor.memory",
    "seq": 182,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`183`** `event.fired` ← cause `171` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 171,
    "data": {
      "data": {
        "action": "a158"
      },
      "event": 171,
      "kind": "action.complete",
      "t": "2026-06-25T16:07:00+00:00"
    },
    "op": "event.fired",
    "seq": 183,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`184`** `action.state` ← cause `183` · _actions_  
  a158 -> completed

  ```json
  {
    "cause": 183,
    "data": {
      "id": "a158",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 184,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`185`** `actor.ongoing` ← cause `183` · _state_  
  eli ongoing -> None

  ```json
  {
    "cause": 183,
    "data": {
      "action": null,
      "actor": "eli"
    },
    "op": "actor.ongoing",
    "seq": 185,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`186`** `fact.set` ← cause `183` · _state_  
  vote:eli = 'cut'

  ```json
  {
    "cause": 183,
    "data": {
      "key": "vote:eli",
      "value": "cut"
    },
    "op": "fact.set",
    "seq": 186,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`187`** `actor.memory` ← cause `183` · _state_  
  eli <- (note) 'Voted cut on: hold the policy rate'

  ```json
  {
    "cause": 183,
    "data": {
      "actor": "eli",
      "content": "Voted cut on: hold the policy rate",
      "kind": "note",
      "source": "a158"
    },
    "op": "actor.memory",
    "seq": 187,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`188`** `event.fired` ← cause `175` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 175,
    "data": {
      "data": {
        "action": "a163"
      },
      "event": 175,
      "kind": "action.complete",
      "t": "2026-06-25T16:07:00+00:00"
    },
    "op": "event.fired",
    "seq": 188,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`189`** `action.state` ← cause `188` · _actions_  
  a163 -> completed

  ```json
  {
    "cause": 188,
    "data": {
      "id": "a163",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 189,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`190`** `actor.ongoing` ← cause `188` · _state_  
  fran ongoing -> None

  ```json
  {
    "cause": 188,
    "data": {
      "action": null,
      "actor": "fran"
    },
    "op": "actor.ongoing",
    "seq": 190,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`191`** `fact.set` ← cause `188` · _state_  
  vote:fran = 'hold'

  ```json
  {
    "cause": 188,
    "data": {
      "key": "vote:fran",
      "value": "hold"
    },
    "op": "fact.set",
    "seq": 191,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`192`** `actor.memory` ← cause `188` · _state_  
  fran <- (note) 'Voted hold on: hold the policy rate'

  ```json
  {
    "cause": 188,
    "data": {
      "actor": "fran",
      "content": "Voted hold on: hold the policy rate",
      "kind": "note",
      "source": "a163"
    },
    "op": "actor.memory",
    "seq": 192,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`193`** `actor.view` ← cause `178` · _views_  
  dana shown world v192, reasons=['action_completed']

  ```json
  {
    "cause": 178,
    "data": {
      "actor": "dana",
      "reasons": [
        {
          "channel": null,
          "detail": "cast_vote",
          "kind": "action_completed",
          "ref": "a153"
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:07:00 America/Mexico_City\n\nTime since your previous relevant decision:\n2 minutes\n\nWhy you are being consulted now:\n- action_completed: cast_vote\n\nYou just finished: cast_vote {'motion': 'hold the policy rate', 'choice': 'hold'}\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour emotional state: focused; running the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (note) Put the motion on the floor: hold the policy rate\n- [2026-06-25 10:07:00 America/Mexico_City] (note) Voted hold on: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 192
    },
    "op": "actor.view",
    "seq": 193,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`194`** `actor.decision` ← cause `193` · _wakes_  
  dana because ['action_completed'] -> intentions=[] | 'nothing to do'

  ```json
  {
    "cause": 193,
    "data": {
      "actor": "dana",
      "based_on_version": 192,
      "intentions": [],
      "note": "nothing to do",
      "reasons": [
        {
          "channel": null,
          "detail": "cast_vote",
          "kind": "action_completed",
          "ref": "a153"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 194,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`195`** `actor.view` ← cause `183` · _views_  
  eli shown world v194, reasons=['action_completed']

  ```json
  {
    "cause": 183,
    "data": {
      "actor": "eli",
      "reasons": [
        {
          "channel": null,
          "detail": "cast_vote",
          "kind": "action_completed",
          "ref": "a158"
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:07:00 America/Mexico_City\n\nTime since your previous relevant decision:\n2 minutes\n\nWhy you are being consulted now:\n- action_completed: cast_vote\n\nYou just finished: cast_vote {'motion': 'hold the policy rate', 'choice': 'cut'}\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\n- [2026-06-25 10:07:00 America/Mexico_City] (note) Voted cut on: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 194
    },
    "op": "actor.view",
    "seq": 195,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`196`** `actor.decision` ← cause `195` · _wakes_  
  eli because ['action_completed'] -> intentions=[] | 'nothing to do'

  ```json
  {
    "cause": 195,
    "data": {
      "actor": "eli",
      "based_on_version": 194,
      "intentions": [],
      "note": "nothing to do",
      "reasons": [
        {
          "channel": null,
          "detail": "cast_vote",
          "kind": "action_completed",
          "ref": "a158"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 196,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`197`** `actor.view` ← cause `188` · _views_  
  fran shown world v196, reasons=['action_completed']

  ```json
  {
    "cause": 188,
    "data": {
      "actor": "fran",
      "reasons": [
        {
          "channel": null,
          "detail": "cast_vote",
          "kind": "action_completed",
          "ref": "a163"
        }
      ],
      "rendered": "Current time:\n2026-06-25 10:07:00 America/Mexico_City\n\nTime since your previous relevant decision:\n2 minutes\n\nWhy you are being consulted now:\n- action_completed: cast_vote\n\nYou just finished: cast_vote {'motion': 'hold the policy rate', 'choice': 'hold'}\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- eli: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\n- [2026-06-25 10:07:00 America/Mexico_City] (note) Voted hold on: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 196
    },
    "op": "actor.view",
    "seq": 197,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`198`** `actor.decision` ← cause `197` · _wakes_  
  fran because ['action_completed'] -> intentions=[] | 'nothing to do'

  ```json
  {
    "cause": 197,
    "data": {
      "actor": "fran",
      "based_on_version": 196,
      "intentions": [],
      "note": "nothing to do",
      "reasons": [
        {
          "channel": null,
          "detail": "cast_vote",
          "kind": "action_completed",
          "ref": "a163"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 198,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```
- **`199`** `terminal` ← cause `188` · _ledger-only_  
  [resolved] 'hold' -- votes: {'dana': 'hold', 'eli': 'cut', 'fran': 'hold'} -> hold 2-1

  ```json
  {
    "cause": 188,
    "data": {
      "answer": {
        "answer": "hold",
        "computed_from": [
          "record:181",
          "record:186",
          "record:191"
        ],
        "detail": "votes: {'dana': 'hold', 'eli': 'cut', 'fran': 'hold'} -> hold 2-1"
      },
      "question": "What does the committee decide on the policy rate at the 2026-06-25 meeting (hold or cut), counted from cast votes?",
      "status": "resolved"
    },
    "op": "terminal",
    "seq": 199,
    "t": "2026-06-25T16:07:00+00:00"
  }
  ```

## committee — checkpoints.jsonl (2 checkpoints)

- ledger seq `81` at `2026-06-24T18:30:00+00:00` — state hash `504b038e093de422…`
- ledger seq `177` at `2026-06-25T16:05:00+00:00` — state hash `382894d8aebb0f55…`

Each checkpoint was resumed into a fresh engine with fresh minds; the resulting ledger was byte-identical to the uninterrupted run.

## committee — terminal_result.json (with full producer lineage)

```json
{
  "answer": {
    "answer": "hold",
    "computed_from": [
      "record:181",
      "record:186",
      "record:191"
    ],
    "detail": "votes: {'dana': 'hold', 'eli': 'cut', 'fran': 'hold'} -> hold 2-1"
  },
  "at": "2026-06-25T16:07:00+00:00",
  "producer_lineage": [
    {
      "data": {
        "answer": {
          "answer": "hold",
          "computed_from": [
            "record:181",
            "record:186",
            "record:191"
          ],
          "detail": "votes: {'dana': 'hold', 'eli': 'cut', 'fran': 'hold'} -> hold 2-1"
        },
        "question": "What does the committee decide on the policy rate at the 2026-06-25 meeting (hold or cut), counted from cast votes?",
        "status": "resolved"
      },
      "op": "terminal",
      "seq": 199,
      "t": "2026-06-25T16:07:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a163"
        },
        "event": 175,
        "kind": "action.complete",
        "t": "2026-06-25T16:07:00+00:00"
      },
      "op": "event.fired",
      "seq": 188,
      "t": "2026-06-25T16:07:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a163"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-06-25T16:07:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 175,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a163"
        },
        "event": 164,
        "kind": "action.start",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.fired",
      "seq": 174,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a163"
        },
        "depth": 3,
        "kind": "action.start",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 164,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "actor": "fran",
        "based_on_version": 160,
        "completes_when": null,
        "duration": {
          "basis": "actor_chosen",
          "note": "stating a vote in the room",
          "seconds": 120.0
        },
        "id": "a163",
        "interruptible": false,
        "interruption_note": "",
        "note": "voting on the motion",
        "params": {
          "choice": "hold",
          "motion": "hold the policy rate"
        },
        "verb": "cast_vote"
      },
      "op": "action.propose",
      "seq": 163,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "actor": "fran",
        "based_on_version": 160,
        "intentions": [
          "cast_vote"
        ],
        "note": "Voting hold based on current beliefs",
        "reasons": [
          {
            "channel": "meeting_floor",
            "detail": "message from dana on meeting_floor",
            "kind": "info_noticed",
            "ref": "i133"
          }
        ]
      },
      "op": "actor.decision",
      "seq": 162,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "actor": "fran",
        "reasons": [
          {
            "channel": "meeting_floor",
            "detail": "message from dana on meeting_floor",
            "kind": "info_noticed",
            "ref": "i133"
          }
        ],
        "rendered": "Current time:\n2026-06-25 10:05:00 America/Mexico_City\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from dana on meeting_floor\n\nNew information you have just noticed:\n- [meeting_floor] message i133 from dana: Motion on the floor: hold the policy rate. Please vote.\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- eli: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 160
      },
      "op": "actor.view",
      "seq": 161,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "actor": "fran",
        "id": "i133"
      },
      "op": "info.notice",
      "seq": 149,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "fran",
          "basis": "verified",
          "channel": "meeting_floor",
          "info": "i133",
          "note": "present in the meeting room; speech is heard at once"
        },
        "event": 144,
        "kind": "info.notice",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.fired",
      "seq": 148,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "fran",
          "basis": "verified",
          "channel": "meeting_floor",
          "info": "i133",
          "note": "present in the meeting room; speech is heard at once"
        },
        "depth": 2,
        "kind": "info.notice",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 144,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "meeting_floor",
          "info": "i133",
          "to": "fran"
        },
        "event": 137,
        "kind": "info.deliver",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.fired",
      "seq": 142,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "meeting_floor",
          "info": "i133",
          "to": "fran"
        },
        "depth": 1,
        "kind": "info.deliver",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 137,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "channel": "meeting_floor",
        "id": "i133",
        "to": "fran"
      },
      "op": "info.send",
      "seq": 136,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "author": "dana",
        "content": "Motion on the floor: hold the policy rate. Please vote.",
        "data": {
          "motion": "hold the policy rate",
          "type": "motion"
        },
        "id": "i133"
      },
      "op": "info.create",
      "seq": 133,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a116"
        },
        "event": 126,
        "kind": "action.complete",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.fired",
      "seq": 129,
      "t": "2026-06-25T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a116"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-06-25T16:05:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 126,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a116"
        },
        "event": 117,
        "kind": "action.start",
        "t": "2026-06-25T16:00:00+00:00"
      },
      "op": "event.fired",
      "seq": 125,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a116"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-06-25T16:00:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 117,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "dana",
        "based_on_version": 112,
        "completes_when": null,
        "duration": {
          "basis": "actor_chosen",
          "note": "opening remarks and stating the motion",
          "seconds": 300.0
        },
        "id": "a116",
        "interruptible": false,
        "interruption_note": "",
        "note": "chairing: putting the motion to a vote",
        "params": {
          "motion": "hold the policy rate"
        },
        "verb": "propose_motion"
      },
      "op": "action.propose",
      "seq": 116,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "dana",
        "based_on_version": 112,
        "intentions": [
          "propose_motion"
        ],
        "note": "Meeting open; putting the hold motion on the floor",
        "reasons": [
          {
            "channel": null,
            "detail": "m1: the policy meeting begins",
            "kind": "scheduled_commitment",
            "ref": null
          }
        ]
      },
      "op": "actor.decision",
      "seq": 114,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "dana",
        "reasons": [
          {
            "channel": null,
            "detail": "m1: the policy meeting begins",
            "kind": "scheduled_commitment",
            "ref": null
          }
        ],
        "rendered": "Current time:\n2026-06-25 10:00:00 America/Mexico_City\n\nTime since your previous relevant decision:\n20 hours, 40 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 0 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- scheduled_commitment: m1: the policy meeting begins\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 112
      },
      "op": "actor.view",
      "seq": 113,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "dana",
          "detail": "m1: the policy meeting begins",
          "reason": "scheduled_commitment"
        },
        "event": 22,
        "kind": "wake.actor",
        "t": "2026-06-25T16:00:00+00:00"
      },
      "op": "event.fired",
      "seq": 110,
      "t": "2026-06-25T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "dana",
          "detail": "m1: the policy meeting begins",
          "reason": "scheduled_commitment"
        },
        "depth": 0,
        "kind": "wake.actor",
        "t": "2026-06-25T16:00:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 22,
      "t": "2026-06-23T14:00:00+00:00"
    }
  ],
  "question": "What does the committee decide on the policy rate at the 2026-06-25 meeting (hold or cut), counted from cast votes?",
  "status": "resolved"
}
```

## committee — replay_verification.json

```json
{
  "deterministic_repeat_run": true,
  "final_hash_match": true,
  "initial_state_hash": "7c30131f531784f7c0725d8ec0786b2ca21c07562d0e699b472556131f87e4cc",
  "ledger_records": 199,
  "original_final_hash": "6b2311cec07e901fe52b7ebfb9f9877a01fdd594743c57bf086a1dc9cd7b6b74",
  "replayed_final_hash": "6b2311cec07e901fe52b7ebfb9f9877a01fdd594743c57bf086a1dc9cd7b6b74",
  "terminal_match": true
}
```

## committee — runtime_metrics.json

```json
{
  "decisions": 15,
  "deferred_wakes": 0,
  "events_processed": 30,
  "intentions": 7,
  "ledger_records": 199,
  "llm_calls": 0,
  "pending_events_at_end": 2,
  "rejections": 0,
  "wall_ms": 17.1
}
```

## committee — actor_wakes.jsonl (15 records, verbatim)

```json
{"cause": 38, "data": {"actor": "gus", "based_on_version": 37, "intentions": ["prepare_briefing"], "note": "Release is out; preparing the briefing", "reasons": [{"channel": "data_wire", "detail": "message from statistics_wire on data_wire", "kind": "info_noticed", "ref": "i29"}]}, "op": "actor.decision", "seq": 39, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 59, "data": {"actor": "gus", "based_on_version": 58, "intentions": [], "note": "Briefing out to the committee", "reasons": [{"channel": null, "detail": "prepare_briefing", "kind": "action_completed", "ref": "a41"}]}, "op": "actor.decision", "seq": 60, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 73, "data": {"actor": "eli", "based_on_version": 72, "intentions": ["read_message"], "note": "Staff briefing arrived; reading it", "reasons": [{"channel": "email", "detail": "message from gus on email", "kind": "info_noticed", "ref": "i51"}]}, "op": "actor.decision", "seq": 74, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 86, "data": {"actor": "eli", "based_on_version": 85, "intentions": [], "note": "Updating on the staff briefing", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a75"}]}, "op": "actor.decision", "seq": 87, "t": "2026-06-24T18:50:00+00:00"}
{"cause": 92, "data": {"actor": "dana", "based_on_version": 91, "intentions": ["read_message"], "note": "Staff briefing arrived; reading it", "reasons": [{"channel": "email", "detail": "message from gus on email", "kind": "info_noticed", "ref": "i51"}]}, "op": "actor.decision", "seq": 93, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 105, "data": {"actor": "dana", "based_on_version": 104, "intentions": [], "note": "Updating on the staff briefing", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a94"}]}, "op": "actor.decision", "seq": 106, "t": "2026-06-24T19:20:00+00:00"}
{"cause": 113, "data": {"actor": "dana", "based_on_version": 112, "intentions": ["propose_motion"], "note": "Meeting open; putting the hold motion on the floor", "reasons": [{"channel": null, "detail": "m1: the policy meeting begins", "kind": "scheduled_commitment", "ref": null}]}, "op": "actor.decision", "seq": 114, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 119, "data": {"actor": "eli", "based_on_version": 118, "intentions": [], "note": "In the meeting; waiting for the chair", "reasons": [{"channel": null, "detail": "m1: the policy meeting begins", "kind": "scheduled_commitment", "ref": null}]}, "op": "actor.decision", "seq": 120, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 122, "data": {"actor": "fran", "based_on_version": 121, "intentions": [], "note": "In the meeting; waiting for the chair", "reasons": [{"channel": null, "detail": "m1: the policy meeting begins", "kind": "scheduled_commitment", "ref": null}]}, "op": "actor.decision", "seq": 123, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 151, "data": {"actor": "dana", "based_on_version": 150, "intentions": ["cast_vote"], "note": "Motion is on the floor; casting the chair's vote", "reasons": [{"channel": null, "detail": "propose_motion", "kind": "action_completed", "ref": "a116"}]}, "op": "actor.decision", "seq": 152, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 156, "data": {"actor": "eli", "based_on_version": 155, "intentions": ["cast_vote"], "note": "Voting cut based on current beliefs", "reasons": [{"channel": "meeting_floor", "detail": "message from dana on meeting_floor", "kind": "info_noticed", "ref": "i133"}]}, "op": "actor.decision", "seq": 157, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 161, "data": {"actor": "fran", "based_on_version": 160, "intentions": ["cast_vote"], "note": "Voting hold based on current beliefs", "reasons": [{"channel": "meeting_floor", "detail": "message from dana on meeting_floor", "kind": "info_noticed", "ref": "i133"}]}, "op": "actor.decision", "seq": 162, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 193, "data": {"actor": "dana", "based_on_version": 192, "intentions": [], "note": "nothing to do", "reasons": [{"channel": null, "detail": "cast_vote", "kind": "action_completed", "ref": "a153"}]}, "op": "actor.decision", "seq": 194, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 195, "data": {"actor": "eli", "based_on_version": 194, "intentions": [], "note": "nothing to do", "reasons": [{"channel": null, "detail": "cast_vote", "kind": "action_completed", "ref": "a158"}]}, "op": "actor.decision", "seq": 196, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 197, "data": {"actor": "fran", "based_on_version": 196, "intentions": [], "note": "nothing to do", "reasons": [{"channel": null, "detail": "cast_vote", "kind": "action_completed", "ref": "a163"}]}, "op": "actor.decision", "seq": 198, "t": "2026-06-25T16:07:00+00:00"}
```

## committee — actor_views.jsonl (15 records, verbatim)

```json
{"cause": 36, "data": {"actor": "gus", "reasons": [{"channel": "data_wire", "detail": "message from statistics_wire on data_wire", "kind": "info_noticed", "ref": "i29"}], "rendered": "Current time:\n2026-06-24 08:00:05 America/Mexico_City\n\nWhy you are being consulted now:\n- info_noticed: message from statistics_wire on data_wire\n\nNew information you have just noticed:\n- [data_wire] message i29 from statistics_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.\n\nYour role: staff analyst\nYour goals:\n- brief the committee accurately and fast on new data\nYour dispositions:\n- rigorous\n- neutral\nYour current plan: Watch Wednesday's inflation release and brief the committee.\nYour memories (oldest first):\n- [2026-06-24 08:00:05 America/Mexico_City] (observation) Noticed message from statistics_wire on data_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.\nActions available to you:\n- prepare_briefing: Prepare a staff briefing from a noticed release and email it to the committee. params: based_on_info, content.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 37}, "op": "actor.view", "seq": 38, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 48, "data": {"actor": "gus", "reasons": [{"channel": null, "detail": "prepare_briefing", "kind": "action_completed", "ref": "a41"}], "rendered": "Current time:\n2026-06-24 12:00:05 America/Mexico_City\n\nTime since your previous relevant decision:\n4 hours\n\nWhy you are being consulted now:\n- action_completed: prepare_briefing\n\nYou just finished: prepare_briefing {'based_on_info': 'i29', 'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'}\n\nYour role: staff analyst\nYour goals:\n- brief the committee accurately and fast on new data\nYour dispositions:\n- rigorous\n- neutral\nYour current beliefs:\n- [inflation] June inflation was 3.1% y/y, below expectations. (basis: wire release i29)\nYour current plan: Watch Wednesday's inflation release and brief the committee.\nYour memories (oldest first):\n- [2026-06-24 08:00:05 America/Mexico_City] (observation) Noticed message from statistics_wire on data_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.\n- [2026-06-24 12:00:05 America/Mexico_City] (note) Sent the inflation briefing to the committee.\nActions available to you:\n- prepare_briefing: Prepare a staff briefing from a noticed release and email it to the committee. params: based_on_info, content.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 58}, "op": "actor.view", "seq": 59, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 71, "data": {"actor": "eli", "reasons": [{"channel": "email", "detail": "message from gus on email", "kind": "info_noticed", "ref": "i51"}], "rendered": "Current time:\n2026-06-24 12:30:00 America/Mexico_City\n\nUpcoming commitments:\n- attend the policy meeting in 21 hours, 30 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- info_noticed: message from gus on email\n\nNew information you have just noticed:\n- [email] message i51 from gus: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 72}, "op": "actor.view", "seq": 73, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 82, "data": {"actor": "eli", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a75"}], "rendered": "Current time:\n2026-06-24 12:50:00 America/Mexico_City\n\nTime since your previous relevant decision:\n20 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 21 hours, 10 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i51', 'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'}\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 85}, "op": "actor.view", "seq": 86, "t": "2026-06-24T18:50:00+00:00"}
{"cause": 90, "data": {"actor": "dana", "reasons": [{"channel": "email", "detail": "message from gus on email", "kind": "info_noticed", "ref": "i51"}], "rendered": "Current time:\n2026-06-24 13:00:00 America/Mexico_City\n\nUpcoming commitments:\n- attend the policy meeting in 21 hours (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- info_noticed: message from gus on email\n\nNew information you have just noticed:\n- [email] message i51 from gus: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 91}, "op": "actor.view", "seq": 92, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 101, "data": {"actor": "dana", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a94"}], "rendered": "Current time:\n2026-06-24 13:20:00 America/Mexico_City\n\nTime since your previous relevant decision:\n20 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 20 hours, 40 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i51', 'content': 'Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.'}\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 104}, "op": "actor.view", "seq": 105, "t": "2026-06-24T19:20:00+00:00"}
{"cause": 110, "data": {"actor": "dana", "reasons": [{"channel": null, "detail": "m1: the policy meeting begins", "kind": "scheduled_commitment", "ref": null}], "rendered": "Current time:\n2026-06-25 10:00:00 America/Mexico_City\n\nTime since your previous relevant decision:\n20 hours, 40 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 0 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- scheduled_commitment: m1: the policy meeting begins\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 112}, "op": "actor.view", "seq": 113, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 111, "data": {"actor": "eli", "reasons": [{"channel": null, "detail": "m1: the policy meeting begins", "kind": "scheduled_commitment", "ref": null}], "rendered": "Current time:\n2026-06-25 10:00:00 America/Mexico_City\n\nTime since your previous relevant decision:\n21 hours, 10 minutes\n\nUpcoming commitments:\n- attend the policy meeting in 0 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- scheduled_commitment: m1: the policy meeting begins\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 118}, "op": "actor.view", "seq": 119, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 112, "data": {"actor": "fran", "reasons": [{"channel": null, "detail": "m1: the policy meeting begins", "kind": "scheduled_commitment", "ref": null}], "rendered": "Current time:\n2026-06-25 10:00:00 America/Mexico_City\n\nUpcoming commitments:\n- attend the policy meeting in 0 minutes (at 2026-06-25 10:00:00 America/Mexico_City)\n\nWhy you are being consulted now:\n- scheduled_commitment: m1: the policy meeting begins\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- eli: committee colleague\nYour current plan: Review incoming analysis before Thursday's meeting.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 121}, "op": "actor.view", "seq": 122, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 129, "data": {"actor": "dana", "reasons": [{"channel": null, "detail": "propose_motion", "kind": "action_completed", "ref": "a116"}], "rendered": "Current time:\n2026-06-25 10:05:00 America/Mexico_City\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- action_completed: propose_motion\n\nYou just finished: propose_motion {'motion': 'hold the policy rate'}\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour emotional state: focused; running the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (note) Put the motion on the floor: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 150}, "op": "actor.view", "seq": 151, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 146, "data": {"actor": "eli", "reasons": [{"channel": "meeting_floor", "detail": "message from dana on meeting_floor", "kind": "info_noticed", "ref": "i133"}], "rendered": "Current time:\n2026-06-25 10:05:00 America/Mexico_City\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from dana on meeting_floor\n\nNew information you have just noticed:\n- [meeting_floor] message i133 from dana: Motion on the floor: hold the policy rate. Please vote.\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 155}, "op": "actor.view", "seq": 156, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 149, "data": {"actor": "fran", "reasons": [{"channel": "meeting_floor", "detail": "message from dana on meeting_floor", "kind": "info_noticed", "ref": "i133"}], "rendered": "Current time:\n2026-06-25 10:05:00 America/Mexico_City\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from dana on meeting_floor\n\nNew information you have just noticed:\n- [meeting_floor] message i133 from dana: Motion on the floor: hold the policy rate. Please vote.\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- eli: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 160}, "op": "actor.view", "seq": 161, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 178, "data": {"actor": "dana", "reasons": [{"channel": null, "detail": "cast_vote", "kind": "action_completed", "ref": "a153"}], "rendered": "Current time:\n2026-06-25 10:07:00 America/Mexico_City\n\nTime since your previous relevant decision:\n2 minutes\n\nWhy you are being consulted now:\n- action_completed: cast_vote\n\nYou just finished: cast_vote {'motion': 'hold the policy rate', 'choice': 'hold'}\n\nYour role: chair\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- institutionally cautious; discounts single data points\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- eli: committee colleague\n- fran: committee colleague\nYour emotional state: focused; running the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 13:00:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 13:20:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (note) Put the motion on the floor: hold the policy rate\n- [2026-06-25 10:07:00 America/Mexico_City] (note) Voted hold on: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- propose_motion: Put a motion on the floor (chair only, meeting in session). params: motion.\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 192}, "op": "actor.view", "seq": 193, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 183, "data": {"actor": "eli", "reasons": [{"channel": null, "detail": "cast_vote", "kind": "action_completed", "ref": "a158"}], "rendered": "Current time:\n2026-06-25 10:07:00 America/Mexico_City\n\nTime since your previous relevant decision:\n2 minutes\n\nWhy you are being consulted now:\n- action_completed: cast_vote\n\nYou just finished: cast_vote {'motion': 'hold the policy rate', 'choice': 'cut'}\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Staff analysis: inflation printed below expectations and is approaching target. (basis: staff briefing i51, read in full)\nYour relationships:\n- dana: committee colleague\n- fran: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-24 12:30:00 America/Mexico_City] (observation) Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.\n- [2026-06-24 12:50:00 America/Mexico_City] (note) Read message i51 in full.\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\n- [2026-06-25 10:07:00 America/Mexico_City] (note) Voted cut on: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 194}, "op": "actor.view", "seq": 195, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 188, "data": {"actor": "fran", "reasons": [{"channel": null, "detail": "cast_vote", "kind": "action_completed", "ref": "a163"}], "rendered": "Current time:\n2026-06-25 10:07:00 America/Mexico_City\n\nTime since your previous relevant decision:\n2 minutes\n\nWhy you are being consulted now:\n- action_completed: cast_vote\n\nYou just finished: cast_vote {'motion': 'hold the policy rate', 'choice': 'hold'}\n\nYour role: member\nYour goals:\n- decide the policy rate responsibly\nYour dispositions:\n- data-driven; responds to new evidence\nYour current beliefs:\n- [inflation] Inflation has been running near 4 percent, above target. (basis: May CPI report)\nYour relationships:\n- dana: committee colleague\n- eli: committee colleague\nYour emotional state: attentive; in the meeting\nYour current plan: Review incoming analysis before Thursday's meeting.\nYour memories (oldest first):\n- [2026-06-25 10:05:00 America/Mexico_City] (observation) Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.\n- [2026-06-25 10:07:00 America/Mexico_City] (note) Voted hold on: hold the policy rate\nActions available to you:\n- cast_vote: Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 196}, "op": "actor.view", "seq": 197, "t": "2026-06-25T16:07:00+00:00"}
```

## committee — intentions.jsonl (7 records, verbatim)

```json
{"cause": 39, "data": {"actor": "gus", "based_on_version": 37, "completes_when": null, "duration": {"basis": "inferred", "note": "comparable staff analyses take about half a working day", "seconds": 14400.0}, "id": "a41", "interruptible": false, "interruption_note": "", "note": "turn the release into a committee briefing", "params": {"based_on_info": "i29", "content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target."}, "verb": "prepare_briefing"}, "op": "action.propose", "seq": 41, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 74, "data": {"actor": "eli", "based_on_version": 72, "completes_when": null, "duration": {"basis": "inferred", "note": "a data briefing takes a focused read", "seconds": 1200.0}, "id": "a75", "interruptible": false, "interruption_note": "", "note": "reading the staff briefing", "params": {"content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.", "info": "i51"}, "verb": "read_message"}, "op": "action.propose", "seq": 75, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 93, "data": {"actor": "dana", "based_on_version": 91, "completes_when": null, "duration": {"basis": "inferred", "note": "a data briefing takes a focused read", "seconds": 1200.0}, "id": "a94", "interruptible": false, "interruption_note": "", "note": "reading the staff briefing", "params": {"content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.", "info": "i51"}, "verb": "read_message"}, "op": "action.propose", "seq": 94, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 114, "data": {"actor": "dana", "based_on_version": 112, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "opening remarks and stating the motion", "seconds": 300.0}, "id": "a116", "interruptible": false, "interruption_note": "", "note": "chairing: putting the motion to a vote", "params": {"motion": "hold the policy rate"}, "verb": "propose_motion"}, "op": "action.propose", "seq": 116, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 152, "data": {"actor": "dana", "based_on_version": 150, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "stating a vote in the room", "seconds": 120.0}, "id": "a153", "interruptible": false, "interruption_note": "", "note": "chair votes after opening the motion", "params": {"choice": "hold", "motion": "hold the policy rate"}, "verb": "cast_vote"}, "op": "action.propose", "seq": 153, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 157, "data": {"actor": "eli", "based_on_version": 155, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "stating a vote in the room", "seconds": 120.0}, "id": "a158", "interruptible": false, "interruption_note": "", "note": "voting on the motion", "params": {"choice": "cut", "motion": "hold the policy rate"}, "verb": "cast_vote"}, "op": "action.propose", "seq": 158, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 162, "data": {"actor": "fran", "based_on_version": 160, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "stating a vote in the room", "seconds": 120.0}, "id": "a163", "interruptible": false, "interruption_note": "", "note": "voting on the motion", "params": {"choice": "hold", "motion": "hold the policy rate"}, "verb": "cast_vote"}, "op": "action.propose", "seq": 163, "t": "2026-06-25T16:05:00+00:00"}
```

## committee — intention_rejections.jsonl (0 records, verbatim)

*(empty — nothing of this kind occurred in this run)*

## committee — action_lifecycle.jsonl (33 records, verbatim)

```json
{"cause": null, "data": {"conditions": [{"id": "{params.to}", "require": "actor_exists"}, {"name": "{params.channel}", "require": "channel_exists"}, {"param": "content", "require": "param_nonempty"}], "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "effects": [["info.send_new", {"author": "{actor}", "channel": "{params.channel}", "content": "{params.content}", "data": "{params.data}", "to": ["{params.to}"]}], ["actor.memory", {"actor": "{actor}", "content": "Sent message to {params.to} on {params.channel}: {params.content}", "kind": "note", "source": "{action_id}"}]], "verb": "send_message"}, "op": "action.define", "seq": 5, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"conditions": [{"info": "{params.info}", "require": "noticed_info"}], "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.", "effects": [["actor.memory", {"actor": "{actor}", "content": "Read message {params.info} in full.", "kind": "note", "source": "{params.info}"}]], "verb": "read_message"}, "op": "action.define", "seq": 6, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"conditions": [{"key": "meeting_open", "require": "fact_equals", "value": true}, {"require": "role_in", "roles": ["chair"]}, {"key": "motion", "require": "fact_absent"}, {"param": "motion", "require": "param_nonempty"}], "description": "Put a motion on the floor (chair only, meeting in session). params: motion.", "effects": [["fact.set", {"key": "motion", "value": "{params.motion}"}], ["info.send_new", {"author": "{actor}", "channel": "meeting_floor", "content": "Motion on the floor: {params.motion}. Please vote.", "data": {"motion": "{params.motion}", "type": "motion"}, "to": {"exclude": ["{actor}"], "role_in": ["chair", "member"]}}], ["actor.memory", {"actor": "{actor}", "content": "Put the motion on the floor: {params.motion}", "kind": "note", "source": "{action_id}"}]], "verb": "propose_motion"}, "op": "action.define", "seq": 7, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"conditions": [{"key": "meeting_open", "require": "fact_equals", "value": true}, {"require": "role_in", "roles": ["chair", "member"]}, {"key": "motion", "require": "fact_equals", "value": "{params.motion}"}, {"key": "vote:{actor}", "require": "fact_absent"}, {"param": "choice", "require": "param_in", "values": ["hold", "cut"]}], "description": "Cast your vote on the motion on the floor (members only, meeting in session, one vote each). params: motion, choice (hold|cut).", "effects": [["fact.set", {"key": "vote:{actor}", "value": "{params.choice}"}], ["actor.memory", {"actor": "{actor}", "content": "Voted {params.choice} on: {params.motion}", "kind": "note", "source": "{action_id}"}]], "verb": "cast_vote"}, "op": "action.define", "seq": 8, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"conditions": [{"require": "role_in", "roles": ["staff analyst"]}, {"info": "{params.based_on_info}", "require": "noticed_info"}, {"param": "content", "require": "param_nonempty"}], "description": "Prepare a staff briefing from a noticed release and email it to the committee. params: based_on_info, content.", "effects": [["info.send_new", {"author": "{actor}", "channel": "email", "content": "{params.content}", "data": {"based_on": "{params.based_on_info}", "type": "briefing"}, "to": {"role_in": ["chair", "member"]}}], ["actor.memory", {"actor": "{actor}", "content": "Sent the inflation briefing to the committee.", "kind": "note", "source": "{action_id}"}]], "verb": "prepare_briefing"}, "op": "action.define", "seq": 9, "t": "2026-06-23T14:00:00+00:00"}
{"cause": 39, "data": {"actor": "gus", "based_on_version": 37, "completes_when": null, "duration": {"basis": "inferred", "note": "comparable staff analyses take about half a working day", "seconds": 14400.0}, "id": "a41", "interruptible": false, "interruption_note": "", "note": "turn the release into a committee briefing", "params": {"based_on_info": "i29", "content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target."}, "verb": "prepare_briefing"}, "op": "action.propose", "seq": 41, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 41, "data": {"id": "a41", "start_event": 42, "state": "scheduled"}, "op": "action.state", "seq": 43, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 44, "data": {"complete_event": 45, "completes_at": "2026-06-24T18:00:05+00:00", "id": "a41", "state": "started"}, "op": "action.state", "seq": 46, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 48, "data": {"id": "a41", "state": "completed"}, "op": "action.state", "seq": 49, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 74, "data": {"actor": "eli", "based_on_version": 72, "completes_when": null, "duration": {"basis": "inferred", "note": "a data briefing takes a focused read", "seconds": 1200.0}, "id": "a75", "interruptible": false, "interruption_note": "", "note": "reading the staff briefing", "params": {"content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.", "info": "i51"}, "verb": "read_message"}, "op": "action.propose", "seq": 75, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 75, "data": {"id": "a75", "start_event": 76, "state": "scheduled"}, "op": "action.state", "seq": 77, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 78, "data": {"complete_event": 79, "completes_at": "2026-06-24T18:50:00+00:00", "id": "a75", "state": "started"}, "op": "action.state", "seq": 80, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 82, "data": {"id": "a75", "state": "completed"}, "op": "action.state", "seq": 83, "t": "2026-06-24T18:50:00+00:00"}
{"cause": 93, "data": {"actor": "dana", "based_on_version": 91, "completes_when": null, "duration": {"basis": "inferred", "note": "a data briefing takes a focused read", "seconds": 1200.0}, "id": "a94", "interruptible": false, "interruption_note": "", "note": "reading the staff briefing", "params": {"content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.", "info": "i51"}, "verb": "read_message"}, "op": "action.propose", "seq": 94, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 94, "data": {"id": "a94", "start_event": 95, "state": "scheduled"}, "op": "action.state", "seq": 96, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 97, "data": {"complete_event": 98, "completes_at": "2026-06-24T19:20:00+00:00", "id": "a94", "state": "started"}, "op": "action.state", "seq": 99, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 101, "data": {"id": "a94", "state": "completed"}, "op": "action.state", "seq": 102, "t": "2026-06-24T19:20:00+00:00"}
{"cause": 114, "data": {"actor": "dana", "based_on_version": 112, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "opening remarks and stating the motion", "seconds": 300.0}, "id": "a116", "interruptible": false, "interruption_note": "", "note": "chairing: putting the motion to a vote", "params": {"motion": "hold the policy rate"}, "verb": "propose_motion"}, "op": "action.propose", "seq": 116, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 116, "data": {"id": "a116", "start_event": 117, "state": "scheduled"}, "op": "action.state", "seq": 118, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 125, "data": {"complete_event": 126, "completes_at": "2026-06-25T16:05:00+00:00", "id": "a116", "state": "started"}, "op": "action.state", "seq": 127, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 129, "data": {"id": "a116", "state": "completed"}, "op": "action.state", "seq": 130, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 152, "data": {"actor": "dana", "based_on_version": 150, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "stating a vote in the room", "seconds": 120.0}, "id": "a153", "interruptible": false, "interruption_note": "", "note": "chair votes after opening the motion", "params": {"choice": "hold", "motion": "hold the policy rate"}, "verb": "cast_vote"}, "op": "action.propose", "seq": 153, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 153, "data": {"id": "a153", "start_event": 154, "state": "scheduled"}, "op": "action.state", "seq": 155, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 157, "data": {"actor": "eli", "based_on_version": 155, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "stating a vote in the room", "seconds": 120.0}, "id": "a158", "interruptible": false, "interruption_note": "", "note": "voting on the motion", "params": {"choice": "cut", "motion": "hold the policy rate"}, "verb": "cast_vote"}, "op": "action.propose", "seq": 158, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 158, "data": {"id": "a158", "start_event": 159, "state": "scheduled"}, "op": "action.state", "seq": 160, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 162, "data": {"actor": "fran", "based_on_version": 160, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "stating a vote in the room", "seconds": 120.0}, "id": "a163", "interruptible": false, "interruption_note": "", "note": "voting on the motion", "params": {"choice": "hold", "motion": "hold the policy rate"}, "verb": "cast_vote"}, "op": "action.propose", "seq": 163, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 163, "data": {"id": "a163", "start_event": 164, "state": "scheduled"}, "op": "action.state", "seq": 165, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 166, "data": {"complete_event": 167, "completes_at": "2026-06-25T16:07:00+00:00", "id": "a153", "state": "started"}, "op": "action.state", "seq": 168, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 170, "data": {"complete_event": 171, "completes_at": "2026-06-25T16:07:00+00:00", "id": "a158", "state": "started"}, "op": "action.state", "seq": 172, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 174, "data": {"complete_event": 175, "completes_at": "2026-06-25T16:07:00+00:00", "id": "a163", "state": "started"}, "op": "action.state", "seq": 176, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 178, "data": {"id": "a153", "state": "completed"}, "op": "action.state", "seq": 179, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 183, "data": {"id": "a158", "state": "completed"}, "op": "action.state", "seq": 184, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 188, "data": {"id": "a163", "state": "completed"}, "op": "action.state", "seq": 189, "t": "2026-06-25T16:07:00+00:00"}
```

## committee — information_lifecycle.jsonl (20 records, verbatim)

```json
{"cause": 27, "data": {"author": "statistics_wire", "content": "June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.", "data": {"series": "inflation", "type": "data_release"}, "id": "i29"}, "op": "info.create", "seq": 29, "t": "2026-06-24T14:00:00+00:00"}
{"cause": 29, "data": {"channel": "data_wire", "id": "i29", "to": "gus"}, "op": "info.send", "seq": 30, "t": "2026-06-24T14:00:00+00:00"}
{"cause": 32, "data": {"channel": "data_wire", "id": "i29", "to": "gus"}, "op": "info.deliver", "seq": 33, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 35, "data": {"actor": "gus", "id": "i29"}, "op": "info.notice", "seq": 36, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 48, "data": {"author": "gus", "content": "Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.", "data": {"based_on": "i29", "type": "briefing"}, "id": "i51"}, "op": "info.create", "seq": 51, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 51, "data": {"channel": "email", "id": "i51", "to": "dana"}, "op": "info.send", "seq": 52, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 51, "data": {"channel": "email", "id": "i51", "to": "eli"}, "op": "info.send", "seq": 54, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 51, "data": {"channel": "email", "id": "i51", "to": "fran"}, "op": "info.send", "seq": 56, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 61, "data": {"channel": "email", "id": "i51", "to": "dana"}, "op": "info.deliver", "seq": 62, "t": "2026-06-24T18:00:35+00:00"}
{"cause": 64, "data": {"channel": "email", "id": "i51", "to": "eli"}, "op": "info.deliver", "seq": 65, "t": "2026-06-24T18:00:35+00:00"}
{"cause": 67, "data": {"channel": "email", "id": "i51", "to": "fran"}, "op": "info.deliver", "seq": 68, "t": "2026-06-24T18:00:35+00:00"}
{"cause": 70, "data": {"actor": "eli", "id": "i51"}, "op": "info.notice", "seq": 71, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 89, "data": {"actor": "dana", "id": "i51"}, "op": "info.notice", "seq": 90, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 129, "data": {"author": "dana", "content": "Motion on the floor: hold the policy rate. Please vote.", "data": {"motion": "hold the policy rate", "type": "motion"}, "id": "i133"}, "op": "info.create", "seq": 133, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 133, "data": {"channel": "meeting_floor", "id": "i133", "to": "eli"}, "op": "info.send", "seq": 134, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 133, "data": {"channel": "meeting_floor", "id": "i133", "to": "fran"}, "op": "info.send", "seq": 136, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 139, "data": {"channel": "meeting_floor", "id": "i133", "to": "eli"}, "op": "info.deliver", "seq": 140, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 142, "data": {"channel": "meeting_floor", "id": "i133", "to": "fran"}, "op": "info.deliver", "seq": 143, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 145, "data": {"actor": "eli", "id": "i133"}, "op": "info.notice", "seq": 146, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 148, "data": {"actor": "fran", "id": "i133"}, "op": "info.notice", "seq": 149, "t": "2026-06-25T16:05:00+00:00"}
```

## committee — state_transitions.jsonl (48 records, verbatim)

```json
{"cause": null, "data": {"attention": {"data_wire": {"basis": "verified", "calendar": {"close": "18:00", "holidays": [], "open": "08:00", "tz": "America/Mexico_City", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": null, "note": "watching the release calendar is his job; the release time is scheduled"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "", "goals": ["brief the committee accurately and fast on new data"], "id": "gus", "last_decision_at": null, "memories": [], "name": "Gustavo Pena", "noticed_info": [], "ongoing_action": null, "physical_state": "", "plan": "Watch Wednesday's inflation release and brief the committee.", "reconsider": [], "relationships": {}, "role": "staff analyst", "tz": "America/Mexico_City", "unprocessed_info": [], "values": ["rigorous", "neutral"]}, "op": "actor.add", "seq": 10, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"attention": {"email": {"basis": "inferred", "calendar": {"close": "18:00", "holidays": [], "open": "09:00", "tz": "America/Mexico_City", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 3600.0, "note": "senior official; assistant batches email roughly hourly"}, "meeting_floor": {"basis": "verified", "calendar": null, "check_every_seconds": null, "note": "present in the meeting room; speech is heard at once"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "", "goals": ["decide the policy rate responsibly"], "id": "dana", "last_decision_at": null, "memories": [], "name": "Dana Ortiz", "noticed_info": [], "ongoing_action": null, "physical_state": "", "plan": "Review incoming analysis before Thursday's meeting.", "reconsider": [], "relationships": {"eli": "committee colleague", "fran": "committee colleague"}, "role": "chair", "tz": "America/Mexico_City", "unprocessed_info": [], "values": ["institutionally cautious; discounts single data points"]}, "op": "actor.add", "seq": 11, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"actor": "dana", "basis": "May CPI report", "statement": "Inflation has been running near 4 percent, above target.", "topic": "inflation"}, "op": "actor.belief", "seq": 12, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"actor": "dana", "at": "2026-06-25T16:00:00+00:00", "id": "m1", "what": "attend the policy meeting"}, "op": "actor.commit", "seq": 13, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"attention": {"email": {"basis": "inferred", "calendar": {"close": "18:00", "holidays": [], "open": "09:00", "tz": "America/Mexico_City", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 1800.0, "note": "checks email frequently between engagements"}, "meeting_floor": {"basis": "verified", "calendar": null, "check_every_seconds": null, "note": "present in the meeting room; speech is heard at once"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "", "goals": ["decide the policy rate responsibly"], "id": "eli", "last_decision_at": null, "memories": [], "name": "Elias Roth", "noticed_info": [], "ongoing_action": null, "physical_state": "", "plan": "Review incoming analysis before Thursday's meeting.", "reconsider": [], "relationships": {"dana": "committee colleague", "fran": "committee colleague"}, "role": "member", "tz": "America/Mexico_City", "unprocessed_info": [], "values": ["data-driven; responds to new evidence"]}, "op": "actor.add", "seq": 14, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"actor": "eli", "basis": "May CPI report", "statement": "Inflation has been running near 4 percent, above target.", "topic": "inflation"}, "op": "actor.belief", "seq": 15, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"actor": "eli", "at": "2026-06-25T16:00:00+00:00", "id": "m1", "what": "attend the policy meeting"}, "op": "actor.commit", "seq": 16, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"attention": {"email": {"basis": "verified", "calendar": {"close": "18:00", "holidays": ["2026-06-24", "2026-06-25"], "open": "09:00", "tz": "America/Mexico_City", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 1800.0, "note": "travel schedule: offline Wednesday-Thursday, resumes Friday"}, "meeting_floor": {"basis": "verified", "calendar": null, "check_every_seconds": null, "note": "present in the meeting room; speech is heard at once"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "", "goals": ["decide the policy rate responsibly"], "id": "fran", "last_decision_at": null, "memories": [], "name": "Francisca Duarte", "noticed_info": [], "ongoing_action": null, "physical_state": "", "plan": "Review incoming analysis before Thursday's meeting.", "reconsider": [], "relationships": {"dana": "committee colleague", "eli": "committee colleague"}, "role": "member", "tz": "America/Mexico_City", "unprocessed_info": [], "values": ["data-driven; responds to new evidence"]}, "op": "actor.add", "seq": 17, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"actor": "fran", "basis": "May CPI report", "statement": "Inflation has been running near 4 percent, above target.", "topic": "inflation"}, "op": "actor.belief", "seq": 18, "t": "2026-06-23T14:00:00+00:00"}
{"cause": null, "data": {"actor": "fran", "at": "2026-06-25T16:00:00+00:00", "id": "m1", "what": "attend the policy meeting"}, "op": "actor.commit", "seq": 19, "t": "2026-06-23T14:00:00+00:00"}
{"cause": 27, "data": {"key": "inflation_release", "value": "3.1% y/y (below expectations)"}, "op": "fact.set", "seq": 28, "t": "2026-06-24T14:00:00+00:00"}
{"cause": 36, "data": {"actor": "gus", "content": "Noticed message from statistics_wire on data_wire: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target.", "kind": "observation", "source": "i29"}, "op": "actor.memory", "seq": 37, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 39, "data": {"actor": "gus", "basis": "wire release i29", "statement": "June inflation was 3.1% y/y, below expectations.", "topic": "inflation"}, "op": "actor.belief", "seq": 40, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 44, "data": {"action": "a41", "actor": "gus"}, "op": "actor.ongoing", "seq": 47, "t": "2026-06-24T14:00:05+00:00"}
{"cause": 48, "data": {"action": null, "actor": "gus"}, "op": "actor.ongoing", "seq": 50, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 48, "data": {"actor": "gus", "content": "Sent the inflation briefing to the committee.", "kind": "note", "source": "a41"}, "op": "actor.memory", "seq": 58, "t": "2026-06-24T18:00:05+00:00"}
{"cause": 71, "data": {"actor": "eli", "content": "Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.", "kind": "observation", "source": "i51"}, "op": "actor.memory", "seq": 72, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 78, "data": {"action": "a75", "actor": "eli"}, "op": "actor.ongoing", "seq": 81, "t": "2026-06-24T18:30:00+00:00"}
{"cause": 82, "data": {"action": null, "actor": "eli"}, "op": "actor.ongoing", "seq": 84, "t": "2026-06-24T18:50:00+00:00"}
{"cause": 82, "data": {"actor": "eli", "content": "Read message i51 in full.", "kind": "note", "source": "i51"}, "op": "actor.memory", "seq": 85, "t": "2026-06-24T18:50:00+00:00"}
{"cause": 87, "data": {"actor": "eli", "basis": "staff briefing i51, read in full", "statement": "Staff analysis: inflation printed below expectations and is approaching target.", "topic": "inflation"}, "op": "actor.belief", "seq": 88, "t": "2026-06-24T18:50:00+00:00"}
{"cause": 90, "data": {"actor": "dana", "content": "Noticed message from gus on email: Staff briefing on the June release: June inflation printed 3.1% y/y, below the 3.6% consensus and moving toward target. Staff assessment: inflation is below expectations and approaching target.", "kind": "observation", "source": "i51"}, "op": "actor.memory", "seq": 91, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 97, "data": {"action": "a94", "actor": "dana"}, "op": "actor.ongoing", "seq": 100, "t": "2026-06-24T19:00:00+00:00"}
{"cause": 101, "data": {"action": null, "actor": "dana"}, "op": "actor.ongoing", "seq": 103, "t": "2026-06-24T19:20:00+00:00"}
{"cause": 101, "data": {"actor": "dana", "content": "Read message i51 in full.", "kind": "note", "source": "i51"}, "op": "actor.memory", "seq": 104, "t": "2026-06-24T19:20:00+00:00"}
{"cause": 106, "data": {"actor": "dana", "basis": "staff briefing i51, read in full", "statement": "Staff analysis: inflation printed below expectations and is approaching target.", "topic": "inflation"}, "op": "actor.belief", "seq": 107, "t": "2026-06-24T19:20:00+00:00"}
{"cause": 108, "data": {"key": "meeting_open", "value": true}, "op": "fact.set", "seq": 109, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 114, "data": {"actor": "dana", "statement": "focused; running the meeting"}, "op": "actor.emotion", "seq": 115, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 120, "data": {"actor": "eli", "statement": "attentive; in the meeting"}, "op": "actor.emotion", "seq": 121, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 123, "data": {"actor": "fran", "statement": "attentive; in the meeting"}, "op": "actor.emotion", "seq": 124, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 125, "data": {"action": "a116", "actor": "dana"}, "op": "actor.ongoing", "seq": 128, "t": "2026-06-25T16:00:00+00:00"}
{"cause": 129, "data": {"action": null, "actor": "dana"}, "op": "actor.ongoing", "seq": 131, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 129, "data": {"key": "motion", "value": "hold the policy rate"}, "op": "fact.set", "seq": 132, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 129, "data": {"actor": "dana", "content": "Put the motion on the floor: hold the policy rate", "kind": "note", "source": "a116"}, "op": "actor.memory", "seq": 138, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 146, "data": {"actor": "eli", "content": "Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.", "kind": "observation", "source": "i133"}, "op": "actor.memory", "seq": 147, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 149, "data": {"actor": "fran", "content": "Noticed message from dana on meeting_floor: Motion on the floor: hold the policy rate. Please vote.", "kind": "observation", "source": "i133"}, "op": "actor.memory", "seq": 150, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 166, "data": {"action": "a153", "actor": "dana"}, "op": "actor.ongoing", "seq": 169, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 170, "data": {"action": "a158", "actor": "eli"}, "op": "actor.ongoing", "seq": 173, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 174, "data": {"action": "a163", "actor": "fran"}, "op": "actor.ongoing", "seq": 177, "t": "2026-06-25T16:05:00+00:00"}
{"cause": 178, "data": {"action": null, "actor": "dana"}, "op": "actor.ongoing", "seq": 180, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 178, "data": {"key": "vote:dana", "value": "hold"}, "op": "fact.set", "seq": 181, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 178, "data": {"actor": "dana", "content": "Voted hold on: hold the policy rate", "kind": "note", "source": "a153"}, "op": "actor.memory", "seq": 182, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 183, "data": {"action": null, "actor": "eli"}, "op": "actor.ongoing", "seq": 185, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 183, "data": {"key": "vote:eli", "value": "cut"}, "op": "fact.set", "seq": 186, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 183, "data": {"actor": "eli", "content": "Voted cut on: hold the policy rate", "kind": "note", "source": "a158"}, "op": "actor.memory", "seq": 187, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 188, "data": {"action": null, "actor": "fran"}, "op": "actor.ongoing", "seq": 190, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 188, "data": {"key": "vote:fran", "value": "hold"}, "op": "fact.set", "seq": 191, "t": "2026-06-25T16:07:00+00:00"}
{"cause": 188, "data": {"actor": "fran", "content": "Voted hold on: hold the policy rate", "kind": "note", "source": "a163"}, "op": "actor.memory", "seq": 192, "t": "2026-06-25T16:07:00+00:00"}
```

## committee — continuous_process_transitions.jsonl (0 records, verbatim)

*(empty — nothing of this kind occurred in this run)*

## committee — reality_fidelity_review.md

# Reality-fidelity review -- committee world

## What is real-world faithful here
- **Scheduled reality drives the timeline.** The release (Wed 08:00) and the
  meeting (Thu 10:00) are calendar facts, not simulation rounds. Nobody is
  polled between them.
- **Analysis takes time.** The staff briefing consumes four labeled hours; it
  reaches members just after noon, and each notices it on their own attention
  pattern (hourly batching for the chair, half-hourly for Eli, not at all for
  traveling Fran). Information locality does real work: Fran votes hold on a
  stale belief because she genuinely never saw the briefing.
- **Authority is enforced by the world.** Only the chair can put a motion on
  the floor; double votes are rejected; the tally is computed only from cast
  vote records -- there is no path from anyone's belief straight to the
  outcome.

## Honest limitations (labeled, not hidden)
- **No real discussion.** A real meeting has argument, persuasion and
  amendment; here the chair states one motion and members vote their current
  beliefs. The kernel supports message exchange on the floor channel; richer
  deliberation needs richer minds (Phase B direction), not new engine parts.
- **Attention cadences are inferred** ("assistant batches email hourly") and
  labeled as such; real senior officials' attention is far less regular.
- **Beliefs move in one step.** Members flip from "near 4%" to "below
  expectations" after one briefing; real belief revision is noisier and
  socially mediated.
- Dana's caution is a disposition sentence driving a scripted rule --
  transparent but shallow; an LLM mind would trade transparency for richness.



# WORLD: factory

*Operational process with quantities (shifts, threshold, transit)*

**Question:** How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?

**Answer:** `500.0` (cutoff) — Acme's received widgets at the cutoff: 500

**Verification:** replay final hash `1915c79b3cc53a5e…` == original `1915c79b3cc53a5e…` → **True**; terminal match **True**; deterministic repeat run: **True**

**Metrics:** {"decisions": 3, "deferred_wakes": 0, "events_processed": 18, "intentions": 1, "ledger_records": 107, "llm_calls": 0, "pending_events_at_end": 3, "rejections": 0, "wall_ms": 5.2}


## factory — initial_world.json (state at genesis seal)

```json
{
  "action_defs": {
    "fulfill_order": {
      "conditions": [
        {
          "require": "role_in",
          "roles": [
            "ops manager"
          ]
        },
        {
          "key": "order:{params.order_id}:status",
          "require": "fact_equals",
          "value": "received"
        }
      ],
      "description": "Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.",
      "effects": [
        [
          "fact.set",
          {
            "key": "order:{params.order_id}:status",
            "value": "shipped"
          }
        ],
        [
          "resource.transfer",
          {
            "amount": "{params.qty}",
            "from_holder": "factory",
            "name": "widgets",
            "to_holder": "carrier"
          }
        ],
        [
          "event.schedule_in",
          {
            "basis": "inferred",
            "data": {
              "note": "carrier delivers PO {params.order_id}",
              "ops": [
                [
                  "resource.transfer",
                  {
                    "amount": "{params.qty}",
                    "from_holder": "carrier",
                    "name": "widgets",
                    "to_holder": "acme"
                  }
                ],
                [
                  "fact.set",
                  {
                    "key": "order:{params.order_id}:status",
                    "value": "delivered"
                  }
                ],
                [
                  "info.send_new",
                  {
                    "author": "carrier",
                    "channel": "order_system",
                    "content": "Delivery confirmation: PO {params.order_id} ({params.qty} widgets) delivered.",
                    "data": {
                      "id": "{params.order_id}",
                      "type": "delivery"
                    },
                    "to": [
                      "mo",
                      "acme_contact"
                    ]
                  }
                ]
              ]
            },
            "delay_hours": 18,
            "kind": "world.ops",
            "note": "regional freight transit time, comparable lanes"
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Shipped PO {params.order_id}: {params.qty} widgets handed to the carrier.",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "fulfill_order"
    }
  },
  "actions": {},
  "actors": {
    "acme_contact": {
      "attention": {},
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [],
      "id": "acme_contact",
      "last_decision_at": null,
      "memories": [],
      "name": "Acme receiving desk",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "",
      "reconsider": [],
      "relationships": {},
      "role": "customer contact",
      "tz": "America/Chicago",
      "unprocessed_info": [],
      "values": []
    },
    "mo": {
      "attention": {
        "order_system": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "08:00",
            "tz": "America/Chicago",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 900.0,
          "note": "order desk checks the order system frequently during shift"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "ship every order as soon as stock allows"
      ],
      "id": "mo",
      "last_decision_at": null,
      "memories": [],
      "name": "Mo Jackson",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Run the week's production; fulfill orders as they arrive.",
      "reconsider": [],
      "relationships": {},
      "role": "ops manager",
      "tz": "America/Chicago",
      "unprocessed_info": [],
      "values": [
        "reliable",
        "hates late shipments"
      ]
    }
  },
  "channels": {
    "order_system": {
      "latency": {
        "basis": "verified",
        "note": "order portal / EDI processing time",
        "seconds": 60.0
      },
      "name": "order_system"
    }
  },
  "entities": {
    "acme": {
      "id": "acme",
      "kind": "customer",
      "properties": {
        "name": "Acme Corp"
      }
    },
    "factory": {
      "id": "factory",
      "kind": "plant",
      "properties": {
        "line": "widget line 1"
      }
    }
  },
  "facts": {},
  "history": [],
  "infos": {},
  "now": "2026-04-06T11:00:00+00:00",
  "processes": {
    "p_line1": {
      "active": false,
      "basis": "verified",
      "capacity": null,
      "holder": "factory",
      "id": "p_line1",
      "last_applied": "2026-04-06T11:00:00+00:00",
      "note": "rated line speed from the plant spec (scenario-given)",
      "rate_per_hour": 40.0,
      "resource": "widgets"
    }
  },
  "relationships": {},
  "resources": {
    "acme:widgets": 0.0,
    "factory:widgets": 0.0
  },
  "scheduled_events": [
    {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 11,
      "t": "2026-04-06T13:00:00+00:00"
    },
    {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 12,
      "t": "2026-04-07T13:00:00+00:00"
    },
    {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 13,
      "t": "2026-04-08T13:00:00+00:00"
    },
    {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 14,
      "t": "2026-04-09T13:00:00+00:00"
    },
    {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 15,
      "t": "2026-04-10T13:00:00+00:00"
    },
    {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 16,
      "t": "2026-04-06T21:00:00+00:00"
    },
    {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 17,
      "t": "2026-04-07T21:00:00+00:00"
    },
    {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 18,
      "t": "2026-04-08T21:00:00+00:00"
    },
    {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 19,
      "t": "2026-04-09T21:00:00+00:00"
    },
    {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 20,
      "t": "2026-04-10T21:00:00+00:00"
    },
    {
      "data": {
        "note": "customer purchase order arrives",
        "ops": [
          [
            "fact.set",
            {
              "key": "order:o1:status",
              "value": "received"
            }
          ],
          [
            "fact.set",
            {
              "key": "order:o1:qty",
              "value": 500
            }
          ],
          [
            "info.send_new",
            {
              "author": "acme",
              "channel": "order_system",
              "content": "PO o1: 500 widgets, ship as soon as available.",
              "data": {
                "id": "o1",
                "qty": 500,
                "type": "order"
              },
              "to": [
                "mo"
              ]
            }
          ]
        ]
      },
      "kind": "world.ops",
      "seq": 21,
      "t": "2026-04-06T14:30:00+00:00"
    }
  ],
  "start": "2026-04-06T11:00:00+00:00",
  "terminal": null,
  "version": 22,
  "watches": {}
}
```

## factory — canonical time-ordered stream (107 records)

Every ledger record in causal order. `seq` = ledger position and event id; `cause` = the record that produced it; `streams` = which artifact projections contain it.


### ⏱ 2026-04-06 06:00:00 America/Chicago  ·  `2026-04-06T11:00:00+00:00`

- **`  1`** `world.genesis` ← cause `—` · _ledger-only_  
  start=2026-04-06T11:00:00+00:00 schema=1

  ```json
  {
    "cause": null,
    "data": {
      "schema": 1,
      "start": "2026-04-06T11:00:00+00:00"
    },
    "op": "world.genesis",
    "seq": 1,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  2`** `channel.add` ← cause `—` · _ledger-only_  
  order_system: latency 60s (verified: order portal / EDI processing time)

  ```json
  {
    "cause": null,
    "data": {
      "latency": {
        "basis": "verified",
        "note": "order portal / EDI processing time",
        "seconds": 60
      },
      "name": "order_system"
    },
    "op": "channel.add",
    "seq": 2,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  3`** `action.define` ← cause `—` · _actions_  
  fulfill_order -- 2 conditions, 4 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "require": "role_in",
          "roles": [
            "ops manager"
          ]
        },
        {
          "key": "order:{params.order_id}:status",
          "require": "fact_equals",
          "value": "received"
        }
      ],
      "description": "Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.",
      "effects": [
        [
          "fact.set",
          {
            "key": "order:{params.order_id}:status",
            "value": "shipped"
          }
        ],
        [
          "resource.transfer",
          {
            "amount": "{params.qty}",
            "from_holder": "factory",
            "name": "widgets",
            "to_holder": "carrier"
          }
        ],
        [
          "event.schedule_in",
          {
            "basis": "inferred",
            "data": {
              "note": "carrier delivers PO {params.order_id}",
              "ops": [
                [
                  "resource.transfer",
                  {
                    "amount": "{params.qty}",
                    "from_holder": "carrier",
                    "name": "widgets",
                    "to_holder": "acme"
                  }
                ],
                [
                  "fact.set",
                  {
                    "key": "order:{params.order_id}:status",
                    "value": "delivered"
                  }
                ],
                [
                  "info.send_new",
                  {
                    "author": "carrier",
                    "channel": "order_system",
                    "content": "Delivery confirmation: PO {params.order_id} ({params.qty} widgets) delivered.",
                    "data": {
                      "id": "{params.order_id}",
                      "type": "delivery"
                    },
                    "to": [
                      "mo",
                      "acme_contact"
                    ]
                  }
                ]
              ]
            },
            "delay_hours": 18,
            "kind": "world.ops",
            "note": "regional freight transit time, comparable lanes"
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Shipped PO {params.order_id}: {params.qty} widgets handed to the carrier.",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "fulfill_order"
    },
    "op": "action.define",
    "seq": 3,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  4`** `entity.add` ← cause `—` · _state_  
  factory (plant) {'line': 'widget line 1'}

  ```json
  {
    "cause": null,
    "data": {
      "id": "factory",
      "kind": "plant",
      "properties": {
        "line": "widget line 1"
      }
    },
    "op": "entity.add",
    "seq": 4,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  5`** `entity.add` ← cause `—` · _state_  
  acme (customer) {'name': 'Acme Corp'}

  ```json
  {
    "cause": null,
    "data": {
      "id": "acme",
      "kind": "customer",
      "properties": {
        "name": "Acme Corp"
      }
    },
    "op": "entity.add",
    "seq": 5,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  6`** `resource.set` ← cause `—` · _state_  
  factory:widgets = 0

  ```json
  {
    "cause": null,
    "data": {
      "amount": 0,
      "holder": "factory",
      "name": "widgets"
    },
    "op": "resource.set",
    "seq": 6,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  7`** `resource.set` ← cause `—` · _state_  
  acme:widgets = 0

  ```json
  {
    "cause": null,
    "data": {
      "amount": 0,
      "holder": "acme",
      "name": "widgets"
    },
    "op": "resource.set",
    "seq": 7,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  8`** `process.add` ← cause `—` · _process_  
  p_line1: factory:widgets @ 40.0/h active=False (verified: rated line speed from the plant spec (scenario-given))

  ```json
  {
    "cause": null,
    "data": {
      "active": false,
      "basis": "verified",
      "holder": "factory",
      "id": "p_line1",
      "note": "rated line speed from the plant spec (scenario-given)",
      "rate_per_hour": 40.0,
      "resource": "widgets"
    },
    "op": "process.add",
    "seq": 8,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **`  9`** `actor.add` ← cause `—` · _state_  
  mo (Mo Jackson, ops manager, America/Chicago)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "order_system": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "08:00",
            "tz": "America/Chicago",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 900.0,
          "note": "order desk checks the order system frequently during shift"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [
        "ship every order as soon as stock allows"
      ],
      "id": "mo",
      "last_decision_at": null,
      "memories": [],
      "name": "Mo Jackson",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "Run the week's production; fulfill orders as they arrive.",
      "reconsider": [],
      "relationships": {},
      "role": "ops manager",
      "tz": "America/Chicago",
      "unprocessed_info": [],
      "values": [
        "reliable",
        "hates late shipments"
      ]
    },
    "op": "actor.add",
    "seq": 9,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 10`** `actor.add` ← cause `—` · _state_  
  acme_contact (Acme receiving desk, customer contact, America/Chicago)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {},
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "",
      "goals": [],
      "id": "acme_contact",
      "last_decision_at": null,
      "memories": [],
      "name": "Acme receiving desk",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "",
      "plan": "",
      "reconsider": [],
      "relationships": {},
      "role": "customer contact",
      "tz": "America/Chicago",
      "unprocessed_info": [],
      "values": []
    },
    "op": "actor.add",
    "seq": 10,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 11`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-06T13:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-06T13:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 11,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 12`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-07T13:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-07T13:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 12,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 13`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-08T13:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-08T13:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 13,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 14`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-09T13:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-09T13:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 14,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 15`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-10T13:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-10T13:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 15,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 16`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-06T21:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-06T21:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 16,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 17`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-07T21:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-07T21:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 17,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 18`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-08T21:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-08T21:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 18,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 19`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-09T21:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-09T21:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 19,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 20`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-10T21:00:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-10T21:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 20,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 21`** `event.scheduled` ← cause `—` · _ledger-only_  
  [world.ops] at 2026-04-06T14:30:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "note": "customer purchase order arrives",
        "ops": [
          [
            "fact.set",
            {
              "key": "order:o1:status",
              "value": "received"
            }
          ],
          [
            "fact.set",
            {
              "key": "order:o1:qty",
              "value": 500
            }
          ],
          [
            "info.send_new",
            {
              "author": "acme",
              "channel": "order_system",
              "content": "PO o1: 500 widgets, ship as soon as available.",
              "data": {
                "id": "o1",
                "qty": 500,
                "type": "order"
              },
              "to": [
                "mo"
              ]
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-06T14:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 21,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 22`** `genesis.sealed` ← cause `—` · _ledger-only_  
  world construction complete; every later record needs a cause

  ```json
  {
    "cause": null,
    "data": {},
    "op": "genesis.sealed",
    "seq": 22,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```
- **` 23`** `event.scheduled` ← cause `22` · _ledger-only_  
  [terminal.cutoff] at 2026-04-09T17:00:00+00:00 depth=0

  ```json
  {
    "cause": 22,
    "data": {
      "data": {
        "question": "How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?"
      },
      "depth": 0,
      "kind": "terminal.cutoff",
      "t": "2026-04-09T17:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 23,
    "t": "2026-04-06T11:00:00+00:00"
  }
  ```

### ⏱ 2026-04-06 08:00:00 America/Chicago  ·  `2026-04-06T13:00:00+00:00`

- **` 24`** `event.fired` ← cause `11` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 11,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "event": 11,
      "kind": "world.ops",
      "t": "2026-04-06T13:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 24,
    "t": "2026-04-06T13:00:00+00:00"
  }
  ```
- **` 25`** `process.active` ← cause `24` · _process_  
  p_line1 active=True

  ```json
  {
    "cause": 24,
    "data": {
      "active": true,
      "id": "p_line1"
    },
    "op": "process.active",
    "seq": 25,
    "t": "2026-04-06T13:00:00+00:00"
  }
  ```

### ⏱ 2026-04-06 09:30:00 America/Chicago  ·  `2026-04-06T14:30:00+00:00`

- **` 26`** `event.fired` ← cause `21` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 21,
    "data": {
      "data": {
        "note": "customer purchase order arrives",
        "ops": [
          [
            "fact.set",
            {
              "key": "order:o1:status",
              "value": "received"
            }
          ],
          [
            "fact.set",
            {
              "key": "order:o1:qty",
              "value": 500
            }
          ],
          [
            "info.send_new",
            {
              "author": "acme",
              "channel": "order_system",
              "content": "PO o1: 500 widgets, ship as soon as available.",
              "data": {
                "id": "o1",
                "qty": 500,
                "type": "order"
              },
              "to": [
                "mo"
              ]
            }
          ]
        ]
      },
      "event": 21,
      "kind": "world.ops",
      "t": "2026-04-06T14:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 26,
    "t": "2026-04-06T14:30:00+00:00"
  }
  ```
- **` 27`** `process.accrue` ← cause `26` · _process_  
  p_line1 +60 over 2026-04-06T13:00:00+00:00 -> 2026-04-06T14:30:00+00:00

  ```json
  {
    "cause": 26,
    "data": {
      "amount": 60.0,
      "clamped": false,
      "from": "2026-04-06T13:00:00+00:00",
      "id": "p_line1",
      "to": "2026-04-06T14:30:00+00:00"
    },
    "op": "process.accrue",
    "seq": 27,
    "t": "2026-04-06T14:30:00+00:00"
  }
  ```
- **` 28`** `fact.set` ← cause `26` · _state_  
  order:o1:status = 'received'

  ```json
  {
    "cause": 26,
    "data": {
      "key": "order:o1:status",
      "value": "received"
    },
    "op": "fact.set",
    "seq": 28,
    "t": "2026-04-06T14:30:00+00:00"
  }
  ```
- **` 29`** `fact.set` ← cause `26` · _state_  
  order:o1:qty = 500

  ```json
  {
    "cause": 26,
    "data": {
      "key": "order:o1:qty",
      "value": 500
    },
    "op": "fact.set",
    "seq": 29,
    "t": "2026-04-06T14:30:00+00:00"
  }
  ```
- **` 30`** `info.create` ← cause `26` · _info_  
  i30 by acme: 'PO o1: 500 widgets, ship as soon as available.' data={'id': 'o1', 'qty': 500, 'type': 'order'}

  ```json
  {
    "cause": 26,
    "data": {
      "author": "acme",
      "content": "PO o1: 500 widgets, ship as soon as available.",
      "data": {
        "id": "o1",
        "qty": 500,
        "type": "order"
      },
      "id": "i30"
    },
    "op": "info.create",
    "seq": 30,
    "t": "2026-04-06T14:30:00+00:00"
  }
  ```
- **` 31`** `info.send` ← cause `30` · _info_  
  i30 -> mo via order_system

  ```json
  {
    "cause": 30,
    "data": {
      "channel": "order_system",
      "id": "i30",
      "to": "mo"
    },
    "op": "info.send",
    "seq": 31,
    "t": "2026-04-06T14:30:00+00:00"
  }
  ```
- **` 32`** `event.scheduled` ← cause `31` · _ledger-only_  
  [info.deliver] at 2026-04-06T14:31:00+00:00 depth=0

  ```json
  {
    "cause": 31,
    "data": {
      "data": {
        "channel": "order_system",
        "info": "i30",
        "to": "mo"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-04-06T14:31:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 32,
    "t": "2026-04-06T14:30:00+00:00"
  }
  ```

### ⏱ 2026-04-06 09:31:00 America/Chicago  ·  `2026-04-06T14:31:00+00:00`

- **` 33`** `event.fired` ← cause `32` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 32,
    "data": {
      "data": {
        "channel": "order_system",
        "info": "i30",
        "to": "mo"
      },
      "event": 32,
      "kind": "info.deliver",
      "t": "2026-04-06T14:31:00+00:00"
    },
    "op": "event.fired",
    "seq": 33,
    "t": "2026-04-06T14:31:00+00:00"
  }
  ```
- **` 34`** `process.accrue` ← cause `33` · _process_  
  p_line1 +0.666667 over 2026-04-06T14:30:00+00:00 -> 2026-04-06T14:31:00+00:00

  ```json
  {
    "cause": 33,
    "data": {
      "amount": 0.6666666666666666,
      "clamped": false,
      "from": "2026-04-06T14:30:00+00:00",
      "id": "p_line1",
      "to": "2026-04-06T14:31:00+00:00"
    },
    "op": "process.accrue",
    "seq": 34,
    "t": "2026-04-06T14:31:00+00:00"
  }
  ```
- **` 35`** `info.deliver` ← cause `33` · _info_  
  i30 DELIVERED to mo via order_system

  ```json
  {
    "cause": 33,
    "data": {
      "channel": "order_system",
      "id": "i30",
      "to": "mo"
    },
    "op": "info.deliver",
    "seq": 35,
    "t": "2026-04-06T14:31:00+00:00"
  }
  ```
- **` 36`** `event.scheduled` ← cause `33` · _ledger-only_  
  [info.notice] at 2026-04-06T14:45:00+00:00 depth=0

  ```json
  {
    "cause": 33,
    "data": {
      "data": {
        "actor": "mo",
        "basis": "inferred",
        "channel": "order_system",
        "info": "i30",
        "note": "order desk checks the order system frequently during shift"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-04-06T14:45:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 36,
    "t": "2026-04-06T14:31:00+00:00"
  }
  ```

### ⏱ 2026-04-06 09:45:00 America/Chicago  ·  `2026-04-06T14:45:00+00:00`

- **` 37`** `event.fired` ← cause `36` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 36,
    "data": {
      "data": {
        "actor": "mo",
        "basis": "inferred",
        "channel": "order_system",
        "info": "i30",
        "note": "order desk checks the order system frequently during shift"
      },
      "event": 36,
      "kind": "info.notice",
      "t": "2026-04-06T14:45:00+00:00"
    },
    "op": "event.fired",
    "seq": 37,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 38`** `process.accrue` ← cause `37` · _process_  
  p_line1 +9.33333 over 2026-04-06T14:31:00+00:00 -> 2026-04-06T14:45:00+00:00

  ```json
  {
    "cause": 37,
    "data": {
      "amount": 9.333333333333334,
      "clamped": false,
      "from": "2026-04-06T14:31:00+00:00",
      "id": "p_line1",
      "to": "2026-04-06T14:45:00+00:00"
    },
    "op": "process.accrue",
    "seq": 38,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 39`** `info.notice` ← cause `37` · _info_  
  i30 NOTICED by mo

  ```json
  {
    "cause": 37,
    "data": {
      "actor": "mo",
      "id": "i30"
    },
    "op": "info.notice",
    "seq": 39,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 40`** `actor.memory` ← cause `39` · _state_  
  mo <- (observation) 'Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.'

  ```json
  {
    "cause": 39,
    "data": {
      "actor": "mo",
      "content": "Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.",
      "kind": "observation",
      "source": "i30"
    },
    "op": "actor.memory",
    "seq": 40,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 41`** `actor.view` ← cause `39` · _views_  
  mo shown world v40, reasons=['info_noticed']

  ```json
  {
    "cause": 39,
    "data": {
      "actor": "mo",
      "reasons": [
        {
          "channel": "order_system",
          "detail": "message from acme on order_system",
          "kind": "info_noticed",
          "ref": "i30"
        }
      ],
      "rendered": "Current time:\n2026-04-06 09:45:00 America/Chicago\n\nWhy you are being consulted now:\n- info_noticed: message from acme on order_system\n\nNew information you have just noticed:\n- [order_system] message i30 from acme: PO o1: 500 widgets, ship as soon as available.\n\nYour role: ops manager\nYour goals:\n- ship every order as soon as stock allows\nYour dispositions:\n- reliable\n- hates late shipments\nYour current plan: Run the week's production; fulfill orders as they arrive.\nYour memories (oldest first):\n- [2026-04-06 09:45:00 America/Chicago] (observation) Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.\nActions available to you:\n- fulfill_order: Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.",
      "world_version": 40
    },
    "op": "actor.view",
    "seq": 41,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 42`** `actor.decision` ← cause `41` · _wakes_  
  mo because ['info_noticed'] -> intentions=['fulfill_order'] | 'Order o1 in; committing to fulfill it'

  ```json
  {
    "cause": 41,
    "data": {
      "actor": "mo",
      "based_on_version": 40,
      "intentions": [
        "fulfill_order"
      ],
      "note": "Order o1 in; committing to fulfill it",
      "reasons": [
        {
          "channel": "order_system",
          "detail": "message from acme on order_system",
          "kind": "info_noticed",
          "ref": "i30"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 42,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 43`** `actor.commit` ← cause `42` · _state_  
  mo commits c_o1: 'fulfill PO o1 (500 widgets)' at=None

  ```json
  {
    "cause": 42,
    "data": {
      "actor": "mo",
      "at": null,
      "id": "c_o1",
      "what": "fulfill PO o1 (500 widgets)"
    },
    "op": "actor.commit",
    "seq": 43,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 44`** `actor.memory` ← cause `42` · _state_  
  mo <- (note) 'New order o1 for 500 widgets; will ship as soon as stock covers it.'

  ```json
  {
    "cause": 42,
    "data": {
      "actor": "mo",
      "content": "New order o1 for 500 widgets; will ship as soon as stock covers it.",
      "kind": "note",
      "source": "i30"
    },
    "op": "actor.memory",
    "seq": 44,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 45`** `action.propose` ← cause `42` · _intentions+actions_  
  a45 mo:fulfill_order {'order_id': 'o1', 'qty': 500} dur=completes_when {'resource_at_least': ['factory', 'widgets', 500]} based_on_v40

  ```json
  {
    "cause": 42,
    "data": {
      "actor": "mo",
      "based_on_version": 40,
      "completes_when": {
        "resource_at_least": [
          "factory",
          "widgets",
          500
        ]
      },
      "duration": null,
      "id": "a45",
      "interruptible": false,
      "interruption_note": "",
      "note": "stage and ship when inventory reaches the order quantity",
      "params": {
        "order_id": "o1",
        "qty": 500
      },
      "verb": "fulfill_order"
    },
    "op": "action.propose",
    "seq": 45,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 46`** `event.scheduled` ← cause `45` · _ledger-only_  
  [action.start] at 2026-04-06T14:45:00+00:00 depth=1

  ```json
  {
    "cause": 45,
    "data": {
      "data": {
        "action": "a45"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-04-06T14:45:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 46,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 47`** `action.state` ← cause `45` · _actions_  
  a45 -> scheduled

  ```json
  {
    "cause": 45,
    "data": {
      "id": "a45",
      "start_event": 46,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 47,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 48`** `event.fired` ← cause `46` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 46,
    "data": {
      "data": {
        "action": "a45"
      },
      "event": 46,
      "kind": "action.start",
      "t": "2026-04-06T14:45:00+00:00"
    },
    "op": "event.fired",
    "seq": 48,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 49`** `watch.add` ← cause `48` · _process_  
  w49: factory:widgets >= 500 -> {'complete_action': 'a45'} (process_derived)

  ```json
  {
    "cause": 48,
    "data": {
      "basis": "process_derived",
      "holder": "factory",
      "id": "w49",
      "level": 500,
      "note": "completion condition of action a45",
      "on_reach": {
        "complete_action": "a45"
      },
      "resource": "widgets"
    },
    "op": "watch.add",
    "seq": 49,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 50`** `action.state` ← cause `48` · _actions_  
  a45 -> started watch=w49

  ```json
  {
    "cause": 48,
    "data": {
      "id": "a45",
      "state": "started",
      "watch": "w49"
    },
    "op": "action.state",
    "seq": 50,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 51`** `actor.ongoing` ← cause `48` · _state_  
  mo ongoing -> a45

  ```json
  {
    "cause": 48,
    "data": {
      "action": "a45",
      "actor": "mo"
    },
    "op": "actor.ongoing",
    "seq": 51,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```
- **` 52`** `event.scheduled` ← cause `48` · _ledger-only_  
  [watch.reached] at 2026-04-07T01:30:00+00:00 depth=0

  ```json
  {
    "cause": 48,
    "data": {
      "data": {
        "watch": "w49"
      },
      "depth": 0,
      "kind": "watch.reached",
      "t": "2026-04-07T01:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 52,
    "t": "2026-04-06T14:45:00+00:00"
  }
  ```

### ⏱ 2026-04-06 16:00:00 America/Chicago  ·  `2026-04-06T21:00:00+00:00`

- **` 53`** `event.fired` ← cause `16` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 16,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "event": 16,
      "kind": "world.ops",
      "t": "2026-04-06T21:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 53,
    "t": "2026-04-06T21:00:00+00:00"
  }
  ```
- **` 54`** `process.accrue` ← cause `53` · _process_  
  p_line1 +250 over 2026-04-06T14:45:00+00:00 -> 2026-04-06T21:00:00+00:00

  ```json
  {
    "cause": 53,
    "data": {
      "amount": 250.0,
      "clamped": false,
      "from": "2026-04-06T14:45:00+00:00",
      "id": "p_line1",
      "to": "2026-04-06T21:00:00+00:00"
    },
    "op": "process.accrue",
    "seq": 54,
    "t": "2026-04-06T21:00:00+00:00"
  }
  ```
- **` 55`** `process.active` ← cause `53` · _process_  
  p_line1 active=False

  ```json
  {
    "cause": 53,
    "data": {
      "active": false,
      "id": "p_line1"
    },
    "op": "process.active",
    "seq": 55,
    "t": "2026-04-06T21:00:00+00:00"
  }
  ```
- **` 56`** `event.cancelled` ← cause `53` · _ledger-only_  
  event 52: watch w49: no active process moves factory:widgets toward 500.0

  ```json
  {
    "cause": 53,
    "data": {
      "event": 52,
      "reason": "watch w49: no active process moves factory:widgets toward 500.0"
    },
    "op": "event.cancelled",
    "seq": 56,
    "t": "2026-04-06T21:00:00+00:00"
  }
  ```

### ⏱ 2026-04-07 08:00:00 America/Chicago  ·  `2026-04-07T13:00:00+00:00`

- **` 57`** `event.fired` ← cause `12` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 12,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "event": 12,
      "kind": "world.ops",
      "t": "2026-04-07T13:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 57,
    "t": "2026-04-07T13:00:00+00:00"
  }
  ```
- **` 58`** `process.active` ← cause `57` · _process_  
  p_line1 active=True

  ```json
  {
    "cause": 57,
    "data": {
      "active": true,
      "id": "p_line1"
    },
    "op": "process.active",
    "seq": 58,
    "t": "2026-04-07T13:00:00+00:00"
  }
  ```
- **` 59`** `event.scheduled` ← cause `57` · _ledger-only_  
  [watch.reached] at 2026-04-07T17:30:00+00:00 depth=0

  ```json
  {
    "cause": 57,
    "data": {
      "data": {
        "watch": "w49"
      },
      "depth": 0,
      "kind": "watch.reached",
      "t": "2026-04-07T17:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 59,
    "t": "2026-04-07T13:00:00+00:00"
  }
  ```

### ⏱ 2026-04-07 12:30:00 America/Chicago  ·  `2026-04-07T17:30:00+00:00`

- **` 60`** `event.fired` ← cause `59` · _ledger-only_  
  [watch.reached]

  ```json
  {
    "cause": 59,
    "data": {
      "data": {
        "watch": "w49"
      },
      "event": 59,
      "kind": "watch.reached",
      "t": "2026-04-07T17:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 60,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 61`** `process.accrue` ← cause `60` · _process_  
  p_line1 +180 over 2026-04-07T13:00:00+00:00 -> 2026-04-07T17:30:00+00:00

  ```json
  {
    "cause": 60,
    "data": {
      "amount": 180.0,
      "clamped": false,
      "from": "2026-04-07T13:00:00+00:00",
      "id": "p_line1",
      "to": "2026-04-07T17:30:00+00:00"
    },
    "op": "process.accrue",
    "seq": 61,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 62`** `watch.fired` ← cause `60` · _process_  
  w49 threshold reached

  ```json
  {
    "cause": 60,
    "data": {
      "id": "w49"
    },
    "op": "watch.fired",
    "seq": 62,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 63`** `event.scheduled` ← cause `60` · _ledger-only_  
  [action.complete] at 2026-04-07T17:30:00+00:00 depth=1

  ```json
  {
    "cause": 60,
    "data": {
      "data": {
        "action": "a45",
        "via_watch": "w49"
      },
      "depth": 1,
      "kind": "action.complete",
      "t": "2026-04-07T17:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 63,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 64`** `event.fired` ← cause `63` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 63,
    "data": {
      "data": {
        "action": "a45",
        "via_watch": "w49"
      },
      "event": 63,
      "kind": "action.complete",
      "t": "2026-04-07T17:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 64,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 65`** `action.state` ← cause `64` · _actions_  
  a45 -> completed

  ```json
  {
    "cause": 64,
    "data": {
      "id": "a45",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 65,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 66`** `actor.ongoing` ← cause `64` · _state_  
  mo ongoing -> None

  ```json
  {
    "cause": 64,
    "data": {
      "action": null,
      "actor": "mo"
    },
    "op": "actor.ongoing",
    "seq": 66,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 67`** `fact.set` ← cause `64` · _state_  
  order:o1:status = 'shipped'

  ```json
  {
    "cause": 64,
    "data": {
      "key": "order:o1:status",
      "value": "shipped"
    },
    "op": "fact.set",
    "seq": 67,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 68`** `resource.transfer` ← cause `64` · _state_  
  500 widgets: factory -> carrier

  ```json
  {
    "cause": 64,
    "data": {
      "amount": 500,
      "from_holder": "factory",
      "name": "widgets",
      "to_holder": "carrier"
    },
    "op": "resource.transfer",
    "seq": 68,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 69`** `event.scheduled` ← cause `64` · _ledger-only_  
  [world.ops] at 2026-04-08T11:30:00+00:00 depth=0

  ```json
  {
    "cause": 64,
    "data": {
      "data": {
        "delay_basis": "inferred",
        "note": "carrier delivers PO o1",
        "ops": [
          [
            "resource.transfer",
            {
              "amount": 500,
              "from_holder": "carrier",
              "name": "widgets",
              "to_holder": "acme"
            }
          ],
          [
            "fact.set",
            {
              "key": "order:o1:status",
              "value": "delivered"
            }
          ],
          [
            "info.send_new",
            {
              "author": "carrier",
              "channel": "order_system",
              "content": "Delivery confirmation: PO o1 (500 widgets) delivered.",
              "data": {
                "id": "o1",
                "type": "delivery"
              },
              "to": [
                "mo",
                "acme_contact"
              ]
            }
          ]
        ]
      },
      "depth": 0,
      "kind": "world.ops",
      "t": "2026-04-08T11:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 69,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 70`** `actor.memory` ← cause `64` · _state_  
  mo <- (note) 'Shipped PO o1: 500 widgets handed to the carrier.'

  ```json
  {
    "cause": 64,
    "data": {
      "actor": "mo",
      "content": "Shipped PO o1: 500 widgets handed to the carrier.",
      "kind": "note",
      "source": "a45"
    },
    "op": "actor.memory",
    "seq": 70,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 71`** `actor.view` ← cause `64` · _views_  
  mo shown world v70, reasons=['action_completed']

  ```json
  {
    "cause": 64,
    "data": {
      "actor": "mo",
      "reasons": [
        {
          "channel": null,
          "detail": "fulfill_order",
          "kind": "action_completed",
          "ref": "a45"
        }
      ],
      "rendered": "Current time:\n2026-04-07 12:30:00 America/Chicago\n\nTime since your previous relevant decision:\n1 day, 2 hours, 45 minutes\n\nWhy you are being consulted now:\n- action_completed: fulfill_order\n\nYou just finished: fulfill_order {'order_id': 'o1', 'qty': 500}\n\nYour role: ops manager\nYour goals:\n- ship every order as soon as stock allows\nYour dispositions:\n- reliable\n- hates late shipments\nYour current plan: Run the week's production; fulfill orders as they arrive.\nYour memories (oldest first):\n- [2026-04-06 09:45:00 America/Chicago] (observation) Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.\n- [2026-04-06 09:45:00 America/Chicago] (note) New order o1 for 500 widgets; will ship as soon as stock covers it.\n- [2026-04-07 12:30:00 America/Chicago] (note) Shipped PO o1: 500 widgets handed to the carrier.\nActions available to you:\n- fulfill_order: Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.",
      "world_version": 70
    },
    "op": "actor.view",
    "seq": 71,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 72`** `actor.decision` ← cause `71` · _wakes_  
  mo because ['action_completed'] -> intentions=[] | 'Shipment handed to the carrier'

  ```json
  {
    "cause": 71,
    "data": {
      "actor": "mo",
      "based_on_version": 70,
      "intentions": [],
      "note": "Shipment handed to the carrier",
      "reasons": [
        {
          "channel": null,
          "detail": "fulfill_order",
          "kind": "action_completed",
          "ref": "a45"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 72,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```
- **` 73`** `actor.plan` ← cause `72` · _state_  
  mo: 'Order shipped; watch for the delivery confirmation.'

  ```json
  {
    "cause": 72,
    "data": {
      "actor": "mo",
      "plan": "Order shipped; watch for the delivery confirmation."
    },
    "op": "actor.plan",
    "seq": 73,
    "t": "2026-04-07T17:30:00+00:00"
  }
  ```

### ⏱ 2026-04-07 16:00:00 America/Chicago  ·  `2026-04-07T21:00:00+00:00`

- **` 74`** `event.fired` ← cause `17` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 17,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "event": 17,
      "kind": "world.ops",
      "t": "2026-04-07T21:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 74,
    "t": "2026-04-07T21:00:00+00:00"
  }
  ```
- **` 75`** `process.accrue` ← cause `74` · _process_  
  p_line1 +140 over 2026-04-07T17:30:00+00:00 -> 2026-04-07T21:00:00+00:00

  ```json
  {
    "cause": 74,
    "data": {
      "amount": 140.0,
      "clamped": false,
      "from": "2026-04-07T17:30:00+00:00",
      "id": "p_line1",
      "to": "2026-04-07T21:00:00+00:00"
    },
    "op": "process.accrue",
    "seq": 75,
    "t": "2026-04-07T21:00:00+00:00"
  }
  ```
- **` 76`** `process.active` ← cause `74` · _process_  
  p_line1 active=False

  ```json
  {
    "cause": 74,
    "data": {
      "active": false,
      "id": "p_line1"
    },
    "op": "process.active",
    "seq": 76,
    "t": "2026-04-07T21:00:00+00:00"
  }
  ```

### ⏱ 2026-04-08 06:30:00 America/Chicago  ·  `2026-04-08T11:30:00+00:00`

- **` 77`** `event.fired` ← cause `69` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 69,
    "data": {
      "data": {
        "delay_basis": "inferred",
        "note": "carrier delivers PO o1",
        "ops": [
          [
            "resource.transfer",
            {
              "amount": 500,
              "from_holder": "carrier",
              "name": "widgets",
              "to_holder": "acme"
            }
          ],
          [
            "fact.set",
            {
              "key": "order:o1:status",
              "value": "delivered"
            }
          ],
          [
            "info.send_new",
            {
              "author": "carrier",
              "channel": "order_system",
              "content": "Delivery confirmation: PO o1 (500 widgets) delivered.",
              "data": {
                "id": "o1",
                "type": "delivery"
              },
              "to": [
                "mo",
                "acme_contact"
              ]
            }
          ]
        ]
      },
      "event": 69,
      "kind": "world.ops",
      "t": "2026-04-08T11:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 77,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```
- **` 78`** `resource.transfer` ← cause `77` · _state_  
  500 widgets: carrier -> acme

  ```json
  {
    "cause": 77,
    "data": {
      "amount": 500,
      "from_holder": "carrier",
      "name": "widgets",
      "to_holder": "acme"
    },
    "op": "resource.transfer",
    "seq": 78,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```
- **` 79`** `fact.set` ← cause `77` · _state_  
  order:o1:status = 'delivered'

  ```json
  {
    "cause": 77,
    "data": {
      "key": "order:o1:status",
      "value": "delivered"
    },
    "op": "fact.set",
    "seq": 79,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```
- **` 80`** `info.create` ← cause `77` · _info_  
  i80 by carrier: 'Delivery confirmation: PO o1 (500 widgets) delivered.' data={'id': 'o1', 'type': 'delivery'}

  ```json
  {
    "cause": 77,
    "data": {
      "author": "carrier",
      "content": "Delivery confirmation: PO o1 (500 widgets) delivered.",
      "data": {
        "id": "o1",
        "type": "delivery"
      },
      "id": "i80"
    },
    "op": "info.create",
    "seq": 80,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```
- **` 81`** `info.send` ← cause `80` · _info_  
  i80 -> mo via order_system

  ```json
  {
    "cause": 80,
    "data": {
      "channel": "order_system",
      "id": "i80",
      "to": "mo"
    },
    "op": "info.send",
    "seq": 81,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```
- **` 82`** `event.scheduled` ← cause `81` · _ledger-only_  
  [info.deliver] at 2026-04-08T11:31:00+00:00 depth=0

  ```json
  {
    "cause": 81,
    "data": {
      "data": {
        "channel": "order_system",
        "info": "i80",
        "to": "mo"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-04-08T11:31:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 82,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```
- **` 83`** `info.send` ← cause `80` · _info_  
  i80 -> acme_contact via order_system

  ```json
  {
    "cause": 80,
    "data": {
      "channel": "order_system",
      "id": "i80",
      "to": "acme_contact"
    },
    "op": "info.send",
    "seq": 83,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```
- **` 84`** `event.scheduled` ← cause `83` · _ledger-only_  
  [info.deliver] at 2026-04-08T11:31:00+00:00 depth=0

  ```json
  {
    "cause": 83,
    "data": {
      "data": {
        "channel": "order_system",
        "info": "i80",
        "to": "acme_contact"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-04-08T11:31:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 84,
    "t": "2026-04-08T11:30:00+00:00"
  }
  ```

### ⏱ 2026-04-08 06:31:00 America/Chicago  ·  `2026-04-08T11:31:00+00:00`

- **` 85`** `event.fired` ← cause `82` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 82,
    "data": {
      "data": {
        "channel": "order_system",
        "info": "i80",
        "to": "mo"
      },
      "event": 82,
      "kind": "info.deliver",
      "t": "2026-04-08T11:31:00+00:00"
    },
    "op": "event.fired",
    "seq": 85,
    "t": "2026-04-08T11:31:00+00:00"
  }
  ```
- **` 86`** `info.deliver` ← cause `85` · _info_  
  i80 DELIVERED to mo via order_system

  ```json
  {
    "cause": 85,
    "data": {
      "channel": "order_system",
      "id": "i80",
      "to": "mo"
    },
    "op": "info.deliver",
    "seq": 86,
    "t": "2026-04-08T11:31:00+00:00"
  }
  ```
- **` 87`** `event.scheduled` ← cause `85` · _ledger-only_  
  [info.notice] at 2026-04-08T13:00:00+00:00 depth=0

  ```json
  {
    "cause": 85,
    "data": {
      "data": {
        "actor": "mo",
        "basis": "inferred",
        "channel": "order_system",
        "info": "i80",
        "note": "order desk checks the order system frequently during shift"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-04-08T13:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 87,
    "t": "2026-04-08T11:31:00+00:00"
  }
  ```
- **` 88`** `event.fired` ← cause `84` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 84,
    "data": {
      "data": {
        "channel": "order_system",
        "info": "i80",
        "to": "acme_contact"
      },
      "event": 84,
      "kind": "info.deliver",
      "t": "2026-04-08T11:31:00+00:00"
    },
    "op": "event.fired",
    "seq": 88,
    "t": "2026-04-08T11:31:00+00:00"
  }
  ```
- **` 89`** `info.deliver` ← cause `88` · _info_  
  i80 DELIVERED to acme_contact via order_system

  ```json
  {
    "cause": 88,
    "data": {
      "channel": "order_system",
      "id": "i80",
      "to": "acme_contact"
    },
    "op": "info.deliver",
    "seq": 89,
    "t": "2026-04-08T11:31:00+00:00"
  }
  ```
- **` 90`** `info.noticing_unsupported` ← cause `88` · _info_  
  i80 for acme_contact: no attention rule for channel 'order_system'; delivered but noticing behavior is unsupported

  ```json
  {
    "cause": 88,
    "data": {
      "actor": "acme_contact",
      "id": "i80",
      "note": "no attention rule for channel 'order_system'; delivered but noticing behavior is unsupported"
    },
    "op": "info.noticing_unsupported",
    "seq": 90,
    "t": "2026-04-08T11:31:00+00:00"
  }
  ```

### ⏱ 2026-04-08 08:00:00 America/Chicago  ·  `2026-04-08T13:00:00+00:00`

- **` 91`** `event.fired` ← cause `13` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 13,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "event": 13,
      "kind": "world.ops",
      "t": "2026-04-08T13:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 91,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 92`** `process.active` ← cause `91` · _process_  
  p_line1 active=True

  ```json
  {
    "cause": 91,
    "data": {
      "active": true,
      "id": "p_line1"
    },
    "op": "process.active",
    "seq": 92,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 93`** `event.fired` ← cause `87` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 87,
    "data": {
      "data": {
        "actor": "mo",
        "basis": "inferred",
        "channel": "order_system",
        "info": "i80",
        "note": "order desk checks the order system frequently during shift"
      },
      "event": 87,
      "kind": "info.notice",
      "t": "2026-04-08T13:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 93,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 94`** `info.notice` ← cause `93` · _info_  
  i80 NOTICED by mo

  ```json
  {
    "cause": 93,
    "data": {
      "actor": "mo",
      "id": "i80"
    },
    "op": "info.notice",
    "seq": 94,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 95`** `actor.memory` ← cause `94` · _state_  
  mo <- (observation) 'Noticed message from carrier on order_system: Delivery confirmation: PO o1 (500 widgets) delivered.'

  ```json
  {
    "cause": 94,
    "data": {
      "actor": "mo",
      "content": "Noticed message from carrier on order_system: Delivery confirmation: PO o1 (500 widgets) delivered.",
      "kind": "observation",
      "source": "i80"
    },
    "op": "actor.memory",
    "seq": 95,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 96`** `actor.view` ← cause `94` · _views_  
  mo shown world v95, reasons=['info_noticed']

  ```json
  {
    "cause": 94,
    "data": {
      "actor": "mo",
      "reasons": [
        {
          "channel": "order_system",
          "detail": "message from carrier on order_system",
          "kind": "info_noticed",
          "ref": "i80"
        }
      ],
      "rendered": "Current time:\n2026-04-08 08:00:00 America/Chicago\n\nTime since your previous relevant decision:\n19 hours, 30 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from carrier on order_system\n\nNew information you have just noticed:\n- [order_system] message i80 from carrier: Delivery confirmation: PO o1 (500 widgets) delivered.\n\nYour role: ops manager\nYour goals:\n- ship every order as soon as stock allows\nYour dispositions:\n- reliable\n- hates late shipments\nYour current plan: Order shipped; watch for the delivery confirmation.\nYour memories (oldest first):\n- [2026-04-06 09:45:00 America/Chicago] (observation) Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.\n- [2026-04-06 09:45:00 America/Chicago] (note) New order o1 for 500 widgets; will ship as soon as stock covers it.\n- [2026-04-07 12:30:00 America/Chicago] (note) Shipped PO o1: 500 widgets handed to the carrier.\n- [2026-04-08 08:00:00 America/Chicago] (observation) Noticed message from carrier on order_system: Delivery confirmation: PO o1 (500 widgets) delivered.\nActions available to you:\n- fulfill_order: Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.",
      "world_version": 95
    },
    "op": "actor.view",
    "seq": 96,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 97`** `actor.decision` ← cause `96` · _wakes_  
  mo because ['info_noticed'] -> intentions=[] | 'Delivery of o1 confirmed; closing it out'

  ```json
  {
    "cause": 96,
    "data": {
      "actor": "mo",
      "based_on_version": 95,
      "intentions": [],
      "note": "Delivery of o1 confirmed; closing it out",
      "reasons": [
        {
          "channel": "order_system",
          "detail": "message from carrier on order_system",
          "kind": "info_noticed",
          "ref": "i80"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 97,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 98`** `actor.commitment_resolved` ← cause `97` · _state_  
  mo resolved c_o1

  ```json
  {
    "cause": 97,
    "data": {
      "actor": "mo",
      "id": "c_o1"
    },
    "op": "actor.commitment_resolved",
    "seq": 98,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```
- **` 99`** `actor.belief` ← cause `97` · _state_  
  mo[order:o1] = 'PO o1 was delivered to the customer.' (basis: carrier confirmation (i80))

  ```json
  {
    "cause": 97,
    "data": {
      "actor": "mo",
      "basis": "carrier confirmation (i80)",
      "statement": "PO o1 was delivered to the customer.",
      "topic": "order:o1"
    },
    "op": "actor.belief",
    "seq": 99,
    "t": "2026-04-08T13:00:00+00:00"
  }
  ```

### ⏱ 2026-04-08 16:00:00 America/Chicago  ·  `2026-04-08T21:00:00+00:00`

- **`100`** `event.fired` ← cause `18` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 18,
    "data": {
      "data": {
        "note": "shift end (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": false,
              "id": "p_line1"
            }
          ]
        ]
      },
      "event": 18,
      "kind": "world.ops",
      "t": "2026-04-08T21:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 100,
    "t": "2026-04-08T21:00:00+00:00"
  }
  ```
- **`101`** `process.accrue` ← cause `100` · _process_  
  p_line1 +320 over 2026-04-08T13:00:00+00:00 -> 2026-04-08T21:00:00+00:00

  ```json
  {
    "cause": 100,
    "data": {
      "amount": 320.0,
      "clamped": false,
      "from": "2026-04-08T13:00:00+00:00",
      "id": "p_line1",
      "to": "2026-04-08T21:00:00+00:00"
    },
    "op": "process.accrue",
    "seq": 101,
    "t": "2026-04-08T21:00:00+00:00"
  }
  ```
- **`102`** `process.active` ← cause `100` · _process_  
  p_line1 active=False

  ```json
  {
    "cause": 100,
    "data": {
      "active": false,
      "id": "p_line1"
    },
    "op": "process.active",
    "seq": 102,
    "t": "2026-04-08T21:00:00+00:00"
  }
  ```

### ⏱ 2026-04-09 08:00:00 America/Chicago  ·  `2026-04-09T13:00:00+00:00`

- **`103`** `event.fired` ← cause `14` · _ledger-only_  
  [world.ops]

  ```json
  {
    "cause": 14,
    "data": {
      "data": {
        "note": "shift start (verified: plant operating calendar)",
        "ops": [
          [
            "process.active",
            {
              "active": true,
              "id": "p_line1"
            }
          ]
        ]
      },
      "event": 14,
      "kind": "world.ops",
      "t": "2026-04-09T13:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 103,
    "t": "2026-04-09T13:00:00+00:00"
  }
  ```
- **`104`** `process.active` ← cause `103` · _process_  
  p_line1 active=True

  ```json
  {
    "cause": 103,
    "data": {
      "active": true,
      "id": "p_line1"
    },
    "op": "process.active",
    "seq": 104,
    "t": "2026-04-09T13:00:00+00:00"
  }
  ```

### ⏱ 2026-04-09 12:00:00 America/Chicago  ·  `2026-04-09T17:00:00+00:00`

- **`105`** `event.fired` ← cause `23` · _ledger-only_  
  [terminal.cutoff]

  ```json
  {
    "cause": 23,
    "data": {
      "data": {
        "question": "How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?"
      },
      "event": 23,
      "kind": "terminal.cutoff",
      "t": "2026-04-09T17:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 105,
    "t": "2026-04-09T17:00:00+00:00"
  }
  ```
- **`106`** `process.accrue` ← cause `105` · _process_  
  p_line1 +160 over 2026-04-09T13:00:00+00:00 -> 2026-04-09T17:00:00+00:00

  ```json
  {
    "cause": 105,
    "data": {
      "amount": 160.0,
      "clamped": false,
      "from": "2026-04-09T13:00:00+00:00",
      "id": "p_line1",
      "to": "2026-04-09T17:00:00+00:00"
    },
    "op": "process.accrue",
    "seq": 106,
    "t": "2026-04-09T17:00:00+00:00"
  }
  ```
- **`107`** `terminal` ← cause `105` · _ledger-only_  
  [cutoff] 500.0 -- Acme's received widgets at the cutoff: 500

  ```json
  {
    "cause": 105,
    "data": {
      "answer": {
        "answer": 500.0,
        "computed_from": [
          "record:78"
        ],
        "detail": "Acme's received widgets at the cutoff: 500",
        "lineage": [
          {
            "op": "resource.transfer",
            "seq": 78
          },
          {
            "op": "event.fired",
            "seq": 77
          },
          {
            "op": "event.scheduled",
            "seq": 69
          },
          {
            "op": "event.fired",
            "seq": 64
          },
          {
            "op": "event.scheduled",
            "seq": 63
          },
          {
            "op": "event.fired",
            "seq": 60
          },
          {
            "op": "event.scheduled",
            "seq": 59
          },
          {
            "op": "event.fired",
            "seq": 57
          },
          {
            "op": "event.scheduled",
            "seq": 12
          }
        ]
      },
      "question": "How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?",
      "status": "cutoff"
    },
    "op": "terminal",
    "seq": 107,
    "t": "2026-04-09T17:00:00+00:00"
  }
  ```

## factory — checkpoints.jsonl (1 checkpoints)

- ledger seq `76` at `2026-04-07T21:00:00+00:00` — state hash `ff7542480925dd26…`

Each checkpoint was resumed into a fresh engine with fresh minds; the resulting ledger was byte-identical to the uninterrupted run.

## factory — terminal_result.json (with full producer lineage)

```json
{
  "answer": {
    "answer": 500.0,
    "computed_from": [
      "record:78"
    ],
    "detail": "Acme's received widgets at the cutoff: 500",
    "lineage": [
      {
        "op": "resource.transfer",
        "seq": 78
      },
      {
        "op": "event.fired",
        "seq": 77
      },
      {
        "op": "event.scheduled",
        "seq": 69
      },
      {
        "op": "event.fired",
        "seq": 64
      },
      {
        "op": "event.scheduled",
        "seq": 63
      },
      {
        "op": "event.fired",
        "seq": 60
      },
      {
        "op": "event.scheduled",
        "seq": 59
      },
      {
        "op": "event.fired",
        "seq": 57
      },
      {
        "op": "event.scheduled",
        "seq": 12
      }
    ]
  },
  "at": "2026-04-09T17:00:00+00:00",
  "producer_lineage": [
    {
      "data": {
        "answer": {
          "answer": 500.0,
          "computed_from": [
            "record:78"
          ],
          "detail": "Acme's received widgets at the cutoff: 500",
          "lineage": [
            {
              "op": "resource.transfer",
              "seq": 78
            },
            {
              "op": "event.fired",
              "seq": 77
            },
            {
              "op": "event.scheduled",
              "seq": 69
            },
            {
              "op": "event.fired",
              "seq": 64
            },
            {
              "op": "event.scheduled",
              "seq": 63
            },
            {
              "op": "event.fired",
              "seq": 60
            },
            {
              "op": "event.scheduled",
              "seq": 59
            },
            {
              "op": "event.fired",
              "seq": 57
            },
            {
              "op": "event.scheduled",
              "seq": 12
            }
          ]
        },
        "question": "How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?",
        "status": "cutoff"
      },
      "op": "terminal",
      "seq": 107,
      "t": "2026-04-09T17:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "question": "How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?"
        },
        "event": 23,
        "kind": "terminal.cutoff",
        "t": "2026-04-09T17:00:00+00:00"
      },
      "op": "event.fired",
      "seq": 105,
      "t": "2026-04-09T17:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "question": "How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?"
        },
        "depth": 0,
        "kind": "terminal.cutoff",
        "t": "2026-04-09T17:00:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 23,
      "t": "2026-04-06T11:00:00+00:00"
    },
    {
      "data": {},
      "op": "genesis.sealed",
      "seq": 22,
      "t": "2026-04-06T11:00:00+00:00"
    }
  ],
  "question": "How many widgets has Acme received by Thursday 2026-04-09 12:00 America/Chicago?",
  "status": "cutoff"
}
```

## factory — replay_verification.json

```json
{
  "deterministic_repeat_run": true,
  "final_hash_match": true,
  "initial_state_hash": "92149612b300602ae9fe462aec2bdc396273b3c7b79c69c57ee87af6bdf24536",
  "ledger_records": 107,
  "original_final_hash": "1915c79b3cc53a5e2ac163a1e7eb2722609f26c7c39b9ee3110a7bb1a3fffd1e",
  "replayed_final_hash": "1915c79b3cc53a5e2ac163a1e7eb2722609f26c7c39b9ee3110a7bb1a3fffd1e",
  "terminal_match": true
}
```

## factory — runtime_metrics.json

```json
{
  "decisions": 3,
  "deferred_wakes": 0,
  "events_processed": 18,
  "intentions": 1,
  "ledger_records": 107,
  "llm_calls": 0,
  "pending_events_at_end": 3,
  "rejections": 0,
  "wall_ms": 5.2
}
```

## factory — actor_wakes.jsonl (3 records, verbatim)

```json
{"cause": 41, "data": {"actor": "mo", "based_on_version": 40, "intentions": ["fulfill_order"], "note": "Order o1 in; committing to fulfill it", "reasons": [{"channel": "order_system", "detail": "message from acme on order_system", "kind": "info_noticed", "ref": "i30"}]}, "op": "actor.decision", "seq": 42, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 71, "data": {"actor": "mo", "based_on_version": 70, "intentions": [], "note": "Shipment handed to the carrier", "reasons": [{"channel": null, "detail": "fulfill_order", "kind": "action_completed", "ref": "a45"}]}, "op": "actor.decision", "seq": 72, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 96, "data": {"actor": "mo", "based_on_version": 95, "intentions": [], "note": "Delivery of o1 confirmed; closing it out", "reasons": [{"channel": "order_system", "detail": "message from carrier on order_system", "kind": "info_noticed", "ref": "i80"}]}, "op": "actor.decision", "seq": 97, "t": "2026-04-08T13:00:00+00:00"}
```

## factory — actor_views.jsonl (3 records, verbatim)

```json
{"cause": 39, "data": {"actor": "mo", "reasons": [{"channel": "order_system", "detail": "message from acme on order_system", "kind": "info_noticed", "ref": "i30"}], "rendered": "Current time:\n2026-04-06 09:45:00 America/Chicago\n\nWhy you are being consulted now:\n- info_noticed: message from acme on order_system\n\nNew information you have just noticed:\n- [order_system] message i30 from acme: PO o1: 500 widgets, ship as soon as available.\n\nYour role: ops manager\nYour goals:\n- ship every order as soon as stock allows\nYour dispositions:\n- reliable\n- hates late shipments\nYour current plan: Run the week's production; fulfill orders as they arrive.\nYour memories (oldest first):\n- [2026-04-06 09:45:00 America/Chicago] (observation) Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.\nActions available to you:\n- fulfill_order: Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.", "world_version": 40}, "op": "actor.view", "seq": 41, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 64, "data": {"actor": "mo", "reasons": [{"channel": null, "detail": "fulfill_order", "kind": "action_completed", "ref": "a45"}], "rendered": "Current time:\n2026-04-07 12:30:00 America/Chicago\n\nTime since your previous relevant decision:\n1 day, 2 hours, 45 minutes\n\nWhy you are being consulted now:\n- action_completed: fulfill_order\n\nYou just finished: fulfill_order {'order_id': 'o1', 'qty': 500}\n\nYour role: ops manager\nYour goals:\n- ship every order as soon as stock allows\nYour dispositions:\n- reliable\n- hates late shipments\nYour current plan: Run the week's production; fulfill orders as they arrive.\nYour memories (oldest first):\n- [2026-04-06 09:45:00 America/Chicago] (observation) Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.\n- [2026-04-06 09:45:00 America/Chicago] (note) New order o1 for 500 widgets; will ship as soon as stock covers it.\n- [2026-04-07 12:30:00 America/Chicago] (note) Shipped PO o1: 500 widgets handed to the carrier.\nActions available to you:\n- fulfill_order: Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.", "world_version": 70}, "op": "actor.view", "seq": 71, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 94, "data": {"actor": "mo", "reasons": [{"channel": "order_system", "detail": "message from carrier on order_system", "kind": "info_noticed", "ref": "i80"}], "rendered": "Current time:\n2026-04-08 08:00:00 America/Chicago\n\nTime since your previous relevant decision:\n19 hours, 30 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from carrier on order_system\n\nNew information you have just noticed:\n- [order_system] message i80 from carrier: Delivery confirmation: PO o1 (500 widgets) delivered.\n\nYour role: ops manager\nYour goals:\n- ship every order as soon as stock allows\nYour dispositions:\n- reliable\n- hates late shipments\nYour current plan: Order shipped; watch for the delivery confirmation.\nYour memories (oldest first):\n- [2026-04-06 09:45:00 America/Chicago] (observation) Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.\n- [2026-04-06 09:45:00 America/Chicago] (note) New order o1 for 500 widgets; will ship as soon as stock covers it.\n- [2026-04-07 12:30:00 America/Chicago] (note) Shipped PO o1: 500 widgets handed to the carrier.\n- [2026-04-08 08:00:00 America/Chicago] (observation) Noticed message from carrier on order_system: Delivery confirmation: PO o1 (500 widgets) delivered.\nActions available to you:\n- fulfill_order: Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.", "world_version": 95}, "op": "actor.view", "seq": 96, "t": "2026-04-08T13:00:00+00:00"}
```

## factory — intentions.jsonl (1 records, verbatim)

```json
{"cause": 42, "data": {"actor": "mo", "based_on_version": 40, "completes_when": {"resource_at_least": ["factory", "widgets", 500]}, "duration": null, "id": "a45", "interruptible": false, "interruption_note": "", "note": "stage and ship when inventory reaches the order quantity", "params": {"order_id": "o1", "qty": 500}, "verb": "fulfill_order"}, "op": "action.propose", "seq": 45, "t": "2026-04-06T14:45:00+00:00"}
```

## factory — intention_rejections.jsonl (0 records, verbatim)

*(empty — nothing of this kind occurred in this run)*

## factory — action_lifecycle.jsonl (5 records, verbatim)

```json
{"cause": null, "data": {"conditions": [{"require": "role_in", "roles": ["ops manager"]}, {"key": "order:{params.order_id}:status", "require": "fact_equals", "value": "received"}], "description": "Commit to fulfill an open order: stage stock and ship as soon as inventory covers it. params: order_id, qty. Completes when factory inventory reaches qty.", "effects": [["fact.set", {"key": "order:{params.order_id}:status", "value": "shipped"}], ["resource.transfer", {"amount": "{params.qty}", "from_holder": "factory", "name": "widgets", "to_holder": "carrier"}], ["event.schedule_in", {"basis": "inferred", "data": {"note": "carrier delivers PO {params.order_id}", "ops": [["resource.transfer", {"amount": "{params.qty}", "from_holder": "carrier", "name": "widgets", "to_holder": "acme"}], ["fact.set", {"key": "order:{params.order_id}:status", "value": "delivered"}], ["info.send_new", {"author": "carrier", "channel": "order_system", "content": "Delivery confirmation: PO {params.order_id} ({params.qty} widgets) delivered.", "data": {"id": "{params.order_id}", "type": "delivery"}, "to": ["mo", "acme_contact"]}]]}, "delay_hours": 18, "kind": "world.ops", "note": "regional freight transit time, comparable lanes"}], ["actor.memory", {"actor": "{actor}", "content": "Shipped PO {params.order_id}: {params.qty} widgets handed to the carrier.", "kind": "note", "source": "{action_id}"}]], "verb": "fulfill_order"}, "op": "action.define", "seq": 3, "t": "2026-04-06T11:00:00+00:00"}
{"cause": 42, "data": {"actor": "mo", "based_on_version": 40, "completes_when": {"resource_at_least": ["factory", "widgets", 500]}, "duration": null, "id": "a45", "interruptible": false, "interruption_note": "", "note": "stage and ship when inventory reaches the order quantity", "params": {"order_id": "o1", "qty": 500}, "verb": "fulfill_order"}, "op": "action.propose", "seq": 45, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 45, "data": {"id": "a45", "start_event": 46, "state": "scheduled"}, "op": "action.state", "seq": 47, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 48, "data": {"id": "a45", "state": "started", "watch": "w49"}, "op": "action.state", "seq": 50, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 64, "data": {"id": "a45", "state": "completed"}, "op": "action.state", "seq": 65, "t": "2026-04-07T17:30:00+00:00"}
```

## factory — information_lifecycle.jsonl (11 records, verbatim)

```json
{"cause": 26, "data": {"author": "acme", "content": "PO o1: 500 widgets, ship as soon as available.", "data": {"id": "o1", "qty": 500, "type": "order"}, "id": "i30"}, "op": "info.create", "seq": 30, "t": "2026-04-06T14:30:00+00:00"}
{"cause": 30, "data": {"channel": "order_system", "id": "i30", "to": "mo"}, "op": "info.send", "seq": 31, "t": "2026-04-06T14:30:00+00:00"}
{"cause": 33, "data": {"channel": "order_system", "id": "i30", "to": "mo"}, "op": "info.deliver", "seq": 35, "t": "2026-04-06T14:31:00+00:00"}
{"cause": 37, "data": {"actor": "mo", "id": "i30"}, "op": "info.notice", "seq": 39, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 77, "data": {"author": "carrier", "content": "Delivery confirmation: PO o1 (500 widgets) delivered.", "data": {"id": "o1", "type": "delivery"}, "id": "i80"}, "op": "info.create", "seq": 80, "t": "2026-04-08T11:30:00+00:00"}
{"cause": 80, "data": {"channel": "order_system", "id": "i80", "to": "mo"}, "op": "info.send", "seq": 81, "t": "2026-04-08T11:30:00+00:00"}
{"cause": 80, "data": {"channel": "order_system", "id": "i80", "to": "acme_contact"}, "op": "info.send", "seq": 83, "t": "2026-04-08T11:30:00+00:00"}
{"cause": 85, "data": {"channel": "order_system", "id": "i80", "to": "mo"}, "op": "info.deliver", "seq": 86, "t": "2026-04-08T11:31:00+00:00"}
{"cause": 88, "data": {"channel": "order_system", "id": "i80", "to": "acme_contact"}, "op": "info.deliver", "seq": 89, "t": "2026-04-08T11:31:00+00:00"}
{"cause": 88, "data": {"actor": "acme_contact", "id": "i80", "note": "no attention rule for channel 'order_system'; delivered but noticing behavior is unsupported"}, "op": "info.noticing_unsupported", "seq": 90, "t": "2026-04-08T11:31:00+00:00"}
{"cause": 93, "data": {"actor": "mo", "id": "i80"}, "op": "info.notice", "seq": 94, "t": "2026-04-08T13:00:00+00:00"}
```

## factory — state_transitions.jsonl (22 records, verbatim)

```json
{"cause": null, "data": {"id": "factory", "kind": "plant", "properties": {"line": "widget line 1"}}, "op": "entity.add", "seq": 4, "t": "2026-04-06T11:00:00+00:00"}
{"cause": null, "data": {"id": "acme", "kind": "customer", "properties": {"name": "Acme Corp"}}, "op": "entity.add", "seq": 5, "t": "2026-04-06T11:00:00+00:00"}
{"cause": null, "data": {"amount": 0, "holder": "factory", "name": "widgets"}, "op": "resource.set", "seq": 6, "t": "2026-04-06T11:00:00+00:00"}
{"cause": null, "data": {"amount": 0, "holder": "acme", "name": "widgets"}, "op": "resource.set", "seq": 7, "t": "2026-04-06T11:00:00+00:00"}
{"cause": null, "data": {"attention": {"order_system": {"basis": "inferred", "calendar": {"close": "17:00", "holidays": [], "open": "08:00", "tz": "America/Chicago", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 900.0, "note": "order desk checks the order system frequently during shift"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "", "goals": ["ship every order as soon as stock allows"], "id": "mo", "last_decision_at": null, "memories": [], "name": "Mo Jackson", "noticed_info": [], "ongoing_action": null, "physical_state": "", "plan": "Run the week's production; fulfill orders as they arrive.", "reconsider": [], "relationships": {}, "role": "ops manager", "tz": "America/Chicago", "unprocessed_info": [], "values": ["reliable", "hates late shipments"]}, "op": "actor.add", "seq": 9, "t": "2026-04-06T11:00:00+00:00"}
{"cause": null, "data": {"attention": {}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "", "goals": [], "id": "acme_contact", "last_decision_at": null, "memories": [], "name": "Acme receiving desk", "noticed_info": [], "ongoing_action": null, "physical_state": "", "plan": "", "reconsider": [], "relationships": {}, "role": "customer contact", "tz": "America/Chicago", "unprocessed_info": [], "values": []}, "op": "actor.add", "seq": 10, "t": "2026-04-06T11:00:00+00:00"}
{"cause": 26, "data": {"key": "order:o1:status", "value": "received"}, "op": "fact.set", "seq": 28, "t": "2026-04-06T14:30:00+00:00"}
{"cause": 26, "data": {"key": "order:o1:qty", "value": 500}, "op": "fact.set", "seq": 29, "t": "2026-04-06T14:30:00+00:00"}
{"cause": 39, "data": {"actor": "mo", "content": "Noticed message from acme on order_system: PO o1: 500 widgets, ship as soon as available.", "kind": "observation", "source": "i30"}, "op": "actor.memory", "seq": 40, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 42, "data": {"actor": "mo", "at": null, "id": "c_o1", "what": "fulfill PO o1 (500 widgets)"}, "op": "actor.commit", "seq": 43, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 42, "data": {"actor": "mo", "content": "New order o1 for 500 widgets; will ship as soon as stock covers it.", "kind": "note", "source": "i30"}, "op": "actor.memory", "seq": 44, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 48, "data": {"action": "a45", "actor": "mo"}, "op": "actor.ongoing", "seq": 51, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 64, "data": {"action": null, "actor": "mo"}, "op": "actor.ongoing", "seq": 66, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 64, "data": {"key": "order:o1:status", "value": "shipped"}, "op": "fact.set", "seq": 67, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 64, "data": {"amount": 500, "from_holder": "factory", "name": "widgets", "to_holder": "carrier"}, "op": "resource.transfer", "seq": 68, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 64, "data": {"actor": "mo", "content": "Shipped PO o1: 500 widgets handed to the carrier.", "kind": "note", "source": "a45"}, "op": "actor.memory", "seq": 70, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 72, "data": {"actor": "mo", "plan": "Order shipped; watch for the delivery confirmation."}, "op": "actor.plan", "seq": 73, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 77, "data": {"amount": 500, "from_holder": "carrier", "name": "widgets", "to_holder": "acme"}, "op": "resource.transfer", "seq": 78, "t": "2026-04-08T11:30:00+00:00"}
{"cause": 77, "data": {"key": "order:o1:status", "value": "delivered"}, "op": "fact.set", "seq": 79, "t": "2026-04-08T11:30:00+00:00"}
{"cause": 94, "data": {"actor": "mo", "content": "Noticed message from carrier on order_system: Delivery confirmation: PO o1 (500 widgets) delivered.", "kind": "observation", "source": "i80"}, "op": "actor.memory", "seq": 95, "t": "2026-04-08T13:00:00+00:00"}
{"cause": 97, "data": {"actor": "mo", "id": "c_o1"}, "op": "actor.commitment_resolved", "seq": 98, "t": "2026-04-08T13:00:00+00:00"}
{"cause": 97, "data": {"actor": "mo", "basis": "carrier confirmation (i80)", "statement": "PO o1 was delivered to the customer.", "topic": "order:o1"}, "op": "actor.belief", "seq": 99, "t": "2026-04-08T13:00:00+00:00"}
```

## factory — continuous_process_transitions.jsonl (18 records, verbatim)

```json
{"cause": null, "data": {"active": false, "basis": "verified", "holder": "factory", "id": "p_line1", "note": "rated line speed from the plant spec (scenario-given)", "rate_per_hour": 40.0, "resource": "widgets"}, "op": "process.add", "seq": 8, "t": "2026-04-06T11:00:00+00:00"}
{"cause": 24, "data": {"active": true, "id": "p_line1"}, "op": "process.active", "seq": 25, "t": "2026-04-06T13:00:00+00:00"}
{"cause": 26, "data": {"amount": 60.0, "clamped": false, "from": "2026-04-06T13:00:00+00:00", "id": "p_line1", "to": "2026-04-06T14:30:00+00:00"}, "op": "process.accrue", "seq": 27, "t": "2026-04-06T14:30:00+00:00"}
{"cause": 33, "data": {"amount": 0.6666666666666666, "clamped": false, "from": "2026-04-06T14:30:00+00:00", "id": "p_line1", "to": "2026-04-06T14:31:00+00:00"}, "op": "process.accrue", "seq": 34, "t": "2026-04-06T14:31:00+00:00"}
{"cause": 37, "data": {"amount": 9.333333333333334, "clamped": false, "from": "2026-04-06T14:31:00+00:00", "id": "p_line1", "to": "2026-04-06T14:45:00+00:00"}, "op": "process.accrue", "seq": 38, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 48, "data": {"basis": "process_derived", "holder": "factory", "id": "w49", "level": 500, "note": "completion condition of action a45", "on_reach": {"complete_action": "a45"}, "resource": "widgets"}, "op": "watch.add", "seq": 49, "t": "2026-04-06T14:45:00+00:00"}
{"cause": 53, "data": {"amount": 250.0, "clamped": false, "from": "2026-04-06T14:45:00+00:00", "id": "p_line1", "to": "2026-04-06T21:00:00+00:00"}, "op": "process.accrue", "seq": 54, "t": "2026-04-06T21:00:00+00:00"}
{"cause": 53, "data": {"active": false, "id": "p_line1"}, "op": "process.active", "seq": 55, "t": "2026-04-06T21:00:00+00:00"}
{"cause": 57, "data": {"active": true, "id": "p_line1"}, "op": "process.active", "seq": 58, "t": "2026-04-07T13:00:00+00:00"}
{"cause": 60, "data": {"amount": 180.0, "clamped": false, "from": "2026-04-07T13:00:00+00:00", "id": "p_line1", "to": "2026-04-07T17:30:00+00:00"}, "op": "process.accrue", "seq": 61, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 60, "data": {"id": "w49"}, "op": "watch.fired", "seq": 62, "t": "2026-04-07T17:30:00+00:00"}
{"cause": 74, "data": {"amount": 140.0, "clamped": false, "from": "2026-04-07T17:30:00+00:00", "id": "p_line1", "to": "2026-04-07T21:00:00+00:00"}, "op": "process.accrue", "seq": 75, "t": "2026-04-07T21:00:00+00:00"}
{"cause": 74, "data": {"active": false, "id": "p_line1"}, "op": "process.active", "seq": 76, "t": "2026-04-07T21:00:00+00:00"}
{"cause": 91, "data": {"active": true, "id": "p_line1"}, "op": "process.active", "seq": 92, "t": "2026-04-08T13:00:00+00:00"}
{"cause": 100, "data": {"amount": 320.0, "clamped": false, "from": "2026-04-08T13:00:00+00:00", "id": "p_line1", "to": "2026-04-08T21:00:00+00:00"}, "op": "process.accrue", "seq": 101, "t": "2026-04-08T21:00:00+00:00"}
{"cause": 100, "data": {"active": false, "id": "p_line1"}, "op": "process.active", "seq": 102, "t": "2026-04-08T21:00:00+00:00"}
{"cause": 103, "data": {"active": true, "id": "p_line1"}, "op": "process.active", "seq": 104, "t": "2026-04-09T13:00:00+00:00"}
{"cause": 105, "data": {"amount": 160.0, "clamped": false, "from": "2026-04-09T13:00:00+00:00", "id": "p_line1", "to": "2026-04-09T17:00:00+00:00"}, "op": "process.accrue", "seq": 106, "t": "2026-04-09T17:00:00+00:00"}
```

## factory — reality_fidelity_review.md

# Reality-fidelity review -- factory world

## What is real-world faithful here
- **Continuous change is exact, not stepped.** Inventory is integrated from
  the labeled 40/hour rate over precisely the elapsed intervals the shift
  calendar allows: 70 units by Mo's 09:45 wake (1.75h x 40); 320 by Monday
  close; 500 exactly at Tuesday 12:30.
  The threshold event was first projected for Monday 20:30, then *cancelled*
  when the shift ended (rate fell to zero) and re-projected from Tuesday's
  restart -- the schedule follows the physics, not the other way round.
- **Nothing teleports.** Stock moves factory -> carrier -> customer; the
  18-hour transit is a labeled inference; the confirmation is a message on a
  channel with latency, noticed on the manager's desk pattern the next
  morning (delivered 06:31, noticed 08:00).
- **The answer is a measurement.** "How many widgets has Acme received" is
  read from `acme:widgets` with the full producer lineage: transfer <-
  delivery event <- shipping action <- threshold <- recorded accruals.

## Honest limitations (labeled, not hidden)
- Production has no scrap rate, no changeover downtime, no variance; the
  rated speed is taken at face value (and labeled as scenario-given).
- Shipping ignores loading time and carrier pickup windows; the 18h transit
  is a point estimate where reality is a distribution.
- The customer is passive: no chasing emails, no partial-delivery
  negotiation. Their receiving desk deliberately has no attention model, so
  its copy of the confirmation stays unnoticed rather than being invented.



# WORLD: phase_b_email_llm

*Phase B: same world, Bob played by a live Deepseek-backed mind*

**Question:** Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?

**Answer:** `"yes"` (resolved) — Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob

**Verification:** replay final hash `76dd9b93f2639ea0…` == original `76dd9b93f2639ea0…` → **True**; terminal match **True**; deterministic repeat run: **None**

**Metrics:** {"decisions": 6, "deferred_wakes": 0, "events_processed": 11, "intentions": 3, "ledger_records": 84, "llm_calls": 2, "pending_events_at_end": 1, "rejections": 0, "wall_ms": 4718.5}


## phase_b_email_llm — initial_world.json (state at genesis seal)

```json
{
  "action_defs": {
    "read_message": {
      "conditions": [
        {
          "info": "{params.info}",
          "require": "noticed_info"
        }
      ],
      "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.",
      "effects": [
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Read message {params.info} in full.",
            "kind": "note",
            "source": "{params.info}"
          }
        ]
      ],
      "verb": "read_message"
    },
    "send_message": {
      "conditions": [
        {
          "id": "{params.to}",
          "require": "actor_exists"
        },
        {
          "name": "{params.channel}",
          "require": "channel_exists"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "{params.channel}",
            "content": "{params.content}",
            "data": "{params.data}",
            "to": [
              "{params.to}"
            ]
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent message to {params.to} on {params.channel}: {params.content}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "send_message"
    }
  },
  "actions": {},
  "actors": {
    "alice": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/New_York",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {
        "c1": {
          "at": "2026-03-07T02:10:00+00:00",
          "id": "c1",
          "resolved": false,
          "what": "email Bob about the Q2 numbers before the weekend"
        }
      },
      "deferred_wakes": [],
      "emotional_state": "mildly pressed by the Monday deadline",
      "goals": [
        "finalize the Monday Q2 summary with confirmed numbers"
      ],
      "id": "alice",
      "last_decision_at": null,
      "memories": [],
      "name": "Alice Ramos",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "working a long Friday",
      "plan": "Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.",
      "reconsider": [],
      "relationships": {
        "bob": "trusted colleague; owns the Q2 pipeline numbers"
      },
      "role": "program manager, East Coast office",
      "tz": "America/New_York",
      "unprocessed_info": [],
      "values": [
        "thorough",
        "dislikes sending unverified figures"
      ]
    },
    "bob": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Los_Angeles",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {
        "q2_numbers": {
          "basis": "verified: he closed the books himself on March 3",
          "statement": "The final Q2 pipeline total is $4.2M, locked on March 3.",
          "updated_at": "2026-03-06T13:00:00+00:00"
        }
      },
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "unwinding into the weekend",
      "goals": [
        "keep the quarter-close numbers accurate"
      ],
      "id": "bob",
      "last_decision_at": null,
      "memories": [],
      "name": "Bob Okafor",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "rested",
      "plan": "Off for the weekend; back Monday morning.",
      "reconsider": [],
      "relationships": {
        "alice": "trusted colleague preparing the Q2 summary"
      },
      "role": "finance lead, West Coast office",
      "tz": "America/Los_Angeles",
      "unprocessed_info": [],
      "values": [
        "precise",
        "answers colleagues promptly once he sees a request"
      ]
    }
  },
  "channels": {
    "email": {
      "latency": {
        "basis": "verified",
        "note": "typical SMTP relay delivery time",
        "seconds": 30.0
      },
      "name": "email"
    }
  },
  "entities": {},
  "facts": {},
  "history": [],
  "infos": {},
  "now": "2026-03-06T13:00:00+00:00",
  "processes": {},
  "relationships": {},
  "resources": {},
  "scheduled_events": [
    {
      "data": {
        "actor": "alice",
        "detail": "c1: email Bob about the Q2 numbers before the weekend",
        "reason": "scheduled_commitment"
      },
      "kind": "wake.actor",
      "seq": 9,
      "t": "2026-03-07T02:10:00+00:00"
    }
  ],
  "start": "2026-03-06T13:00:00+00:00",
  "terminal": null,
  "version": 10,
  "watches": {}
}
```

## phase_b_email_llm — canonical time-ordered stream (84 records)

Every ledger record in causal order. `seq` = ledger position and event id; `cause` = the record that produced it; `streams` = which artifact projections contain it.


### ⏱ 2026-03-06 08:00:00 America/New_York  ·  `2026-03-06T13:00:00+00:00`

- **`  1`** `world.genesis` ← cause `—` · _ledger-only_  
  start=2026-03-06T13:00:00+00:00 schema=1

  ```json
  {
    "cause": null,
    "data": {
      "schema": 1,
      "start": "2026-03-06T13:00:00+00:00"
    },
    "op": "world.genesis",
    "seq": 1,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  2`** `channel.add` ← cause `—` · _ledger-only_  
  email: latency 30s (verified: typical SMTP relay delivery time)

  ```json
  {
    "cause": null,
    "data": {
      "latency": {
        "basis": "verified",
        "note": "typical SMTP relay delivery time",
        "seconds": 30
      },
      "name": "email"
    },
    "op": "channel.add",
    "seq": 2,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  3`** `action.define` ← cause `—` · _actions_  
  send_message -- 3 conditions, 2 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "id": "{params.to}",
          "require": "actor_exists"
        },
        {
          "name": "{params.channel}",
          "require": "channel_exists"
        },
        {
          "param": "content",
          "require": "param_nonempty"
        }
      ],
      "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "effects": [
        [
          "info.send_new",
          {
            "author": "{actor}",
            "channel": "{params.channel}",
            "content": "{params.content}",
            "data": "{params.data}",
            "to": [
              "{params.to}"
            ]
          }
        ],
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Sent message to {params.to} on {params.channel}: {params.content}",
            "kind": "note",
            "source": "{action_id}"
          }
        ]
      ],
      "verb": "send_message"
    },
    "op": "action.define",
    "seq": 3,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  4`** `action.define` ← cause `—` · _actions_  
  read_message -- 1 conditions, 1 effects

  ```json
  {
    "cause": null,
    "data": {
      "conditions": [
        {
          "info": "{params.info}",
          "require": "noticed_info"
        }
      ],
      "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.",
      "effects": [
        [
          "actor.memory",
          {
            "actor": "{actor}",
            "content": "Read message {params.info} in full.",
            "kind": "note",
            "source": "{params.info}"
          }
        ]
      ],
      "verb": "read_message"
    },
    "op": "action.define",
    "seq": 4,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  5`** `actor.add` ← cause `—` · _state_  
  alice (Alice Ramos, program manager, East Coast office, America/New_York)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/New_York",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "mildly pressed by the Monday deadline",
      "goals": [
        "finalize the Monday Q2 summary with confirmed numbers"
      ],
      "id": "alice",
      "last_decision_at": null,
      "memories": [],
      "name": "Alice Ramos",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "working a long Friday",
      "plan": "Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.",
      "reconsider": [],
      "relationships": {
        "bob": "trusted colleague; owns the Q2 pipeline numbers"
      },
      "role": "program manager, East Coast office",
      "tz": "America/New_York",
      "unprocessed_info": [],
      "values": [
        "thorough",
        "dislikes sending unverified figures"
      ]
    },
    "op": "actor.add",
    "seq": 5,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  6`** `actor.add` ← cause `—` · _state_  
  bob (Bob Okafor, finance lead, West Coast office, America/Los_Angeles)

  ```json
  {
    "cause": null,
    "data": {
      "attention": {
        "email": {
          "basis": "inferred",
          "calendar": {
            "close": "17:00",
            "holidays": [],
            "open": "09:00",
            "tz": "America/Los_Angeles",
            "workdays": [
              0,
              1,
              2,
              3,
              4
            ]
          },
          "check_every_seconds": 1800.0,
          "note": "office worker; checks email roughly every half hour during work hours"
        }
      },
      "available_info": [],
      "beliefs": {},
      "commitments": {},
      "deferred_wakes": [],
      "emotional_state": "unwinding into the weekend",
      "goals": [
        "keep the quarter-close numbers accurate"
      ],
      "id": "bob",
      "last_decision_at": null,
      "memories": [],
      "name": "Bob Okafor",
      "noticed_info": [],
      "ongoing_action": null,
      "physical_state": "rested",
      "plan": "Off for the weekend; back Monday morning.",
      "reconsider": [],
      "relationships": {
        "alice": "trusted colleague preparing the Q2 summary"
      },
      "role": "finance lead, West Coast office",
      "tz": "America/Los_Angeles",
      "unprocessed_info": [],
      "values": [
        "precise",
        "answers colleagues promptly once he sees a request"
      ]
    },
    "op": "actor.add",
    "seq": 6,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  7`** `actor.belief` ← cause `—` · _state_  
  bob[q2_numbers] = 'The final Q2 pipeline total is $4.2M, locked on March 3.' (basis: verified: he closed the books himself on March 3)

  ```json
  {
    "cause": null,
    "data": {
      "actor": "bob",
      "basis": "verified: he closed the books himself on March 3",
      "statement": "The final Q2 pipeline total is $4.2M, locked on March 3.",
      "topic": "q2_numbers"
    },
    "op": "actor.belief",
    "seq": 7,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  8`** `actor.commit` ← cause `—` · _state_  
  alice commits c1: 'email Bob about the Q2 numbers before the weekend' at=2026-03-07T02:10:00+00:00

  ```json
  {
    "cause": null,
    "data": {
      "actor": "alice",
      "at": "2026-03-07T02:10:00+00:00",
      "id": "c1",
      "what": "email Bob about the Q2 numbers before the weekend"
    },
    "op": "actor.commit",
    "seq": 8,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **`  9`** `event.scheduled` ← cause `—` · _ledger-only_  
  [wake.actor] at 2026-03-07T02:10:00+00:00 depth=0

  ```json
  {
    "cause": null,
    "data": {
      "data": {
        "actor": "alice",
        "detail": "c1: email Bob about the Q2 numbers before the weekend",
        "reason": "scheduled_commitment"
      },
      "depth": 0,
      "kind": "wake.actor",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 9,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **` 10`** `genesis.sealed` ← cause `—` · _ledger-only_  
  world construction complete; every later record needs a cause

  ```json
  {
    "cause": null,
    "data": {},
    "op": "genesis.sealed",
    "seq": 10,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```
- **` 11`** `event.scheduled` ← cause `10` · _ledger-only_  
  [terminal.cutoff] at 2026-03-10T16:00:00+00:00 depth=0

  ```json
  {
    "cause": 10,
    "data": {
      "data": {
        "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?"
      },
      "depth": 0,
      "kind": "terminal.cutoff",
      "t": "2026-03-10T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 11,
    "t": "2026-03-06T13:00:00+00:00"
  }
  ```

### ⏱ 2026-03-06 21:10:00 America/New_York  ·  `2026-03-07T02:10:00+00:00`

- **` 12`** `event.fired` ← cause `9` · _ledger-only_  
  [wake.actor]

  ```json
  {
    "cause": 9,
    "data": {
      "data": {
        "actor": "alice",
        "detail": "c1: email Bob about the Q2 numbers before the weekend",
        "reason": "scheduled_commitment"
      },
      "event": 9,
      "kind": "wake.actor",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.fired",
    "seq": 12,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 13`** `actor.view` ← cause `12` · _views_  
  alice shown world v12, reasons=['scheduled_commitment']

  ```json
  {
    "cause": 12,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": null,
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ],
      "rendered": "Current time:\n2026-03-06 21:10:00 America/New_York\n\nUpcoming commitments:\n- email Bob about the Q2 numbers before the weekend in 0 minutes (at 2026-03-06 21:10:00 America/New_York)\n\nWhy you are being consulted now:\n- scheduled_commitment: c1: email Bob about the Q2 numbers before the weekend\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 12
    },
    "op": "actor.view",
    "seq": 13,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 14`** `actor.decision` ← cause `13` · _wakes_  
  alice because ['scheduled_commitment'] -> intentions=['send_message'] | 'Friday evening: sending Bob the Q2 question before logging off'

  ```json
  {
    "cause": 13,
    "data": {
      "actor": "alice",
      "based_on_version": 12,
      "intentions": [
        "send_message"
      ],
      "note": "Friday evening: sending Bob the Q2 question before logging off",
      "reasons": [
        {
          "channel": null,
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "kind": "scheduled_commitment",
          "ref": null
        }
      ]
    },
    "op": "actor.decision",
    "seq": 14,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 15`** `actor.commitment_resolved` ← cause `14` · _state_  
  alice resolved c1

  ```json
  {
    "cause": 14,
    "data": {
      "actor": "alice",
      "id": "c1"
    },
    "op": "actor.commitment_resolved",
    "seq": 15,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 16`** `actor.memory` ← cause `14` · _state_  
  alice <- (note) 'Decided to email Bob about the Q2 numbers tonight.'

  ```json
  {
    "cause": 14,
    "data": {
      "actor": "alice",
      "content": "Decided to email Bob about the Q2 numbers tonight.",
      "kind": "note",
      "source": "decision"
    },
    "op": "actor.memory",
    "seq": 16,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 17`** `action.propose` ← cause `14` · _intentions+actions_  
  a17 alice:send_message {'channel': 'email', 'content': "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", 'data': {'thread': 'q2', 'type': 'question'}, 'to': 'bob'} dur=480.0s (actor_chosen) based_on_v12

  ```json
  {
    "cause": 14,
    "data": {
      "actor": "alice",
      "based_on_version": 12,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "time she takes to compose a short email",
        "seconds": 480.0
      },
      "id": "a17",
      "interruptible": false,
      "interruption_note": "",
      "note": "fulfilling her Friday commitment",
      "params": {
        "channel": "email",
        "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
        "data": {
          "thread": "q2",
          "type": "question"
        },
        "to": "bob"
      },
      "verb": "send_message"
    },
    "op": "action.propose",
    "seq": 17,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 18`** `event.scheduled` ← cause `17` · _ledger-only_  
  [action.start] at 2026-03-07T02:10:00+00:00 depth=1

  ```json
  {
    "cause": 17,
    "data": {
      "data": {
        "action": "a17"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 18,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 19`** `action.state` ← cause `17` · _actions_  
  a17 -> scheduled

  ```json
  {
    "cause": 17,
    "data": {
      "id": "a17",
      "start_event": 18,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 19,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 20`** `event.fired` ← cause `18` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 18,
    "data": {
      "data": {
        "action": "a17"
      },
      "event": 18,
      "kind": "action.start",
      "t": "2026-03-07T02:10:00+00:00"
    },
    "op": "event.fired",
    "seq": 20,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 21`** `event.scheduled` ← cause `20` · _ledger-only_  
  [action.complete] at 2026-03-07T02:18:00+00:00 depth=0

  ```json
  {
    "cause": 20,
    "data": {
      "data": {
        "action": "a17"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-03-07T02:18:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 21,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 22`** `action.state` ← cause `20` · _actions_  
  a17 -> started completes_at=2026-03-07T02:18:00+00:00

  ```json
  {
    "cause": 20,
    "data": {
      "complete_event": 21,
      "completes_at": "2026-03-07T02:18:00+00:00",
      "id": "a17",
      "state": "started"
    },
    "op": "action.state",
    "seq": 22,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```
- **` 23`** `actor.ongoing` ← cause `20` · _state_  
  alice ongoing -> a17

  ```json
  {
    "cause": 20,
    "data": {
      "action": "a17",
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 23,
    "t": "2026-03-07T02:10:00+00:00"
  }
  ```

### ⏱ 2026-03-06 21:18:00 America/New_York  ·  `2026-03-07T02:18:00+00:00`

- **` 24`** `event.fired` ← cause `21` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 21,
    "data": {
      "data": {
        "action": "a17"
      },
      "event": 21,
      "kind": "action.complete",
      "t": "2026-03-07T02:18:00+00:00"
    },
    "op": "event.fired",
    "seq": 24,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 25`** `action.state` ← cause `24` · _actions_  
  a17 -> completed

  ```json
  {
    "cause": 24,
    "data": {
      "id": "a17",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 25,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 26`** `actor.ongoing` ← cause `24` · _state_  
  alice ongoing -> None

  ```json
  {
    "cause": 24,
    "data": {
      "action": null,
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 26,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 27`** `info.create` ← cause `24` · _info_  
  i27 by alice: "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary." data={'thread': 'q2', 'type': 'question'}

  ```json
  {
    "cause": 24,
    "data": {
      "author": "alice",
      "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
      "data": {
        "thread": "q2",
        "type": "question"
      },
      "id": "i27"
    },
    "op": "info.create",
    "seq": 27,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 28`** `info.send` ← cause `27` · _info_  
  i27 -> bob via email

  ```json
  {
    "cause": 27,
    "data": {
      "channel": "email",
      "id": "i27",
      "to": "bob"
    },
    "op": "info.send",
    "seq": 28,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 29`** `event.scheduled` ← cause `28` · _ledger-only_  
  [info.deliver] at 2026-03-07T02:18:30+00:00 depth=0

  ```json
  {
    "cause": 28,
    "data": {
      "data": {
        "channel": "email",
        "info": "i27",
        "to": "bob"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-03-07T02:18:30+00:00"
    },
    "op": "event.scheduled",
    "seq": 29,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 30`** `actor.memory` ← cause `24` · _state_  
  alice <- (note) "Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary."

  ```json
  {
    "cause": 24,
    "data": {
      "actor": "alice",
      "content": "Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
      "kind": "note",
      "source": "a17"
    },
    "op": "actor.memory",
    "seq": 30,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 31`** `actor.view` ← cause `24` · _views_  
  alice shown world v30, reasons=['action_completed']

  ```json
  {
    "cause": 24,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a17"
        }
      ],
      "rendered": "Current time:\n2026-03-06 21:18:00 America/New_York\n\nTime since your previous relevant decision:\n8 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'bob', 'channel': 'email', 'content': \"Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\", 'data': {'type': 'question', 'thread': 'q2'}}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 30
    },
    "op": "actor.view",
    "seq": 31,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 32`** `actor.decision` ← cause `31` · _wakes_  
  alice because ['action_completed'] -> intentions=[] | 'Email sent; waiting on Bob'

  ```json
  {
    "cause": 31,
    "data": {
      "actor": "alice",
      "based_on_version": 30,
      "intentions": [],
      "note": "Email sent; waiting on Bob",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a17"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 32,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```
- **` 33`** `actor.plan` ← cause `32` · _state_  
  alice: "Wait for Bob's reply before finalizing the summary."

  ```json
  {
    "cause": 32,
    "data": {
      "actor": "alice",
      "plan": "Wait for Bob's reply before finalizing the summary."
    },
    "op": "actor.plan",
    "seq": 33,
    "t": "2026-03-07T02:18:00+00:00"
  }
  ```

### ⏱ 2026-03-06 21:18:30 America/New_York  ·  `2026-03-07T02:18:30+00:00`

- **` 34`** `event.fired` ← cause `29` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 29,
    "data": {
      "data": {
        "channel": "email",
        "info": "i27",
        "to": "bob"
      },
      "event": 29,
      "kind": "info.deliver",
      "t": "2026-03-07T02:18:30+00:00"
    },
    "op": "event.fired",
    "seq": 34,
    "t": "2026-03-07T02:18:30+00:00"
  }
  ```
- **` 35`** `info.deliver` ← cause `34` · _info_  
  i27 DELIVERED to bob via email

  ```json
  {
    "cause": 34,
    "data": {
      "channel": "email",
      "id": "i27",
      "to": "bob"
    },
    "op": "info.deliver",
    "seq": 35,
    "t": "2026-03-07T02:18:30+00:00"
  }
  ```
- **` 36`** `event.scheduled` ← cause `34` · _ledger-only_  
  [info.notice] at 2026-03-09T16:00:00+00:00 depth=0

  ```json
  {
    "cause": 34,
    "data": {
      "data": {
        "actor": "bob",
        "basis": "inferred",
        "channel": "email",
        "info": "i27",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 36,
    "t": "2026-03-07T02:18:30+00:00"
  }
  ```

### ⏱ 2026-03-09 12:00:00 America/New_York  ·  `2026-03-09T16:00:00+00:00`

- **` 37`** `event.fired` ← cause `36` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 36,
    "data": {
      "data": {
        "actor": "bob",
        "basis": "inferred",
        "channel": "email",
        "info": "i27",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "event": 36,
      "kind": "info.notice",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 37,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 38`** `info.notice` ← cause `37` · _info_  
  i27 NOTICED by bob

  ```json
  {
    "cause": 37,
    "data": {
      "actor": "bob",
      "id": "i27"
    },
    "op": "info.notice",
    "seq": 38,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 39`** `actor.memory` ← cause `38` · _state_  
  bob <- (observation) "Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary."

  ```json
  {
    "cause": 38,
    "data": {
      "actor": "bob",
      "content": "Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
      "kind": "observation",
      "source": "i27"
    },
    "op": "actor.memory",
    "seq": 39,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 40`** `actor.view` ← cause `38` · _views_  
  bob shown world v39, reasons=['info_noticed']

  ```json
  {
    "cause": 38,
    "data": {
      "actor": "bob",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from alice on email",
          "kind": "info_noticed",
          "ref": "i27"
        }
      ],
      "rendered": "Current time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 39
    },
    "op": "actor.view",
    "seq": 40,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 41`** `mind.exchange` ← cause `40` · _views_  
  bob LLM exchange parsed=True attempt=0

  ```json
  {
    "cause": 40,
    "data": {
      "actor": "bob",
      "attempt": 0,
      "parsed": true,
      "request": "You are Bob Okafor, finance lead on the West Coast. You personally locked the final Q2 pipeline total of $4.2M on March 3. Alice is a trusted colleague; you answer colleagues promptly once you see their request.\n\n=== YOUR CURRENT SITUATION ===\nCurrent time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "response": "{\n  \"note\": \"Alice needs the Q2 numbers for Monday's summary; I'll reply now with the confirmed $4.2M total.\",\n  \"updates\": [\n    {\n      \"op\": \"actor.memory\",\n      \"data\": {\n        \"actor\": \"bob\",\n        \"kind\": \"note\",\n        \"content\": \"Alice asked for Q2 pipeline confirmation; I replied with $4.2M.\",\n        \"source\": \"decision\"\n      }\n    }\n  ],\n  \"intentions\": [\n    {\n      \"verb\": \"send_message\",\n      \"params\": {\n        \"to\": \"alice\",\n        \"channel\": \"email\",\n        \"content\": \"Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\"\n      },\n      \"duration_minutes\": 5,\n      \"duration_basis\": \"actor_chosen\",\n      \"duration_note\": \"Quick reply to a straightforward request.\",\n      \"note\": \"Confirming the numbers promptly as Alice needs them for Monday.\"\n    }\n  ],\n  \"wake_me_in_minutes\": null\n}",
      "system": "You are Bob Okafor, a real person, living through the situation described.\nYou are not an assistant and you are not narrating a story: you are this person,\nmaking your own decisions inside your own day. You only know what appears in the\nbriefing below. You cannot see other people's thoughts, you cannot control\noutcomes, and your actions take real time. You propose what you do next; the\nworld decides what actually happens.\n\nRespond with ONLY a JSON object, no markdown fences, with this shape:\n{\n  \"note\": \"one sentence: what you are thinking/deciding and why\",\n  \"updates\": [\n    {\"op\": \"actor.belief\", \"data\": {\"actor\": \"bob\", \"topic\": \"...\",\n       \"statement\": \"...\", \"basis\": \"where this belief comes from\"}},\n    {\"op\": \"actor.memory\", \"data\": {\"actor\": \"bob\", \"kind\": \"note\",\n       \"content\": \"...\", \"source\": \"decision\"}}\n  ],\n  \"intentions\": [\n    {\"verb\": \"<one of the available actions>\", \"params\": {...},\n       \"duration_minutes\": <realistic number>,\n       \"duration_basis\": \"actor_chosen\",\n       \"duration_note\": \"why this long\",\n       \"note\": \"why you are doing this\"}\n  ],\n  \"wake_me_in_minutes\": null\n}\n\nRules:\n- updates may only use ops actor.belief / actor.memory / actor.plan /\n  actor.emotion (data.actor must be \"bob\").\n- intentions[].verb must be one of the actions listed as available to you.\n- durations must be realistic for a human doing that task.\n- if nothing needs doing right now, return empty lists.\n- \"wake_me_in_minutes\": set a number only if you genuinely want to revisit\n  the situation later without any new trigger."
    },
    "op": "mind.exchange",
    "seq": 41,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 42`** `actor.decision` ← cause `40` · _wakes_  
  bob because ['info_noticed'] -> intentions=['send_message'] | "Alice needs the Q2 numbers for Monday's summary; I'll reply now with the confirmed $4.2M total."

  ```json
  {
    "cause": 40,
    "data": {
      "actor": "bob",
      "based_on_version": 39,
      "intentions": [
        "send_message"
      ],
      "note": "Alice needs the Q2 numbers for Monday's summary; I'll reply now with the confirmed $4.2M total.",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from alice on email",
          "kind": "info_noticed",
          "ref": "i27"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 42,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 43`** `actor.memory` ← cause `42` · _state_  
  bob <- (note) 'Alice asked for Q2 pipeline confirmation; I replied with $4.2M.'

  ```json
  {
    "cause": 42,
    "data": {
      "actor": "bob",
      "content": "Alice asked for Q2 pipeline confirmation; I replied with $4.2M.",
      "kind": "note",
      "source": "decision"
    },
    "op": "actor.memory",
    "seq": 43,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 44`** `action.propose` ← cause `42` · _intentions+actions_  
  a44 bob:send_message {'channel': 'email', 'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob', 'to': 'alice'} dur=300.0s (actor_chosen) based_on_v39

  ```json
  {
    "cause": 42,
    "data": {
      "actor": "bob",
      "based_on_version": 39,
      "completes_when": null,
      "duration": {
        "basis": "actor_chosen",
        "note": "Quick reply to a straightforward request.",
        "seconds": 300.0
      },
      "id": "a44",
      "interruptible": false,
      "interruption_note": "",
      "note": "Confirming the numbers promptly as Alice needs them for Monday.",
      "params": {
        "channel": "email",
        "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
        "to": "alice"
      },
      "verb": "send_message"
    },
    "op": "action.propose",
    "seq": 44,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 45`** `event.scheduled` ← cause `44` · _ledger-only_  
  [action.start] at 2026-03-09T16:00:00+00:00 depth=1

  ```json
  {
    "cause": 44,
    "data": {
      "data": {
        "action": "a44"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 45,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 46`** `action.state` ← cause `44` · _actions_  
  a44 -> scheduled

  ```json
  {
    "cause": 44,
    "data": {
      "id": "a44",
      "start_event": 45,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 46,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 47`** `event.fired` ← cause `45` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 45,
    "data": {
      "data": {
        "action": "a44"
      },
      "event": 45,
      "kind": "action.start",
      "t": "2026-03-09T16:00:00+00:00"
    },
    "op": "event.fired",
    "seq": 47,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 48`** `event.scheduled` ← cause `47` · _ledger-only_  
  [action.complete] at 2026-03-09T16:05:00+00:00 depth=0

  ```json
  {
    "cause": 47,
    "data": {
      "data": {
        "action": "a44"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-03-09T16:05:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 48,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 49`** `action.state` ← cause `47` · _actions_  
  a44 -> started completes_at=2026-03-09T16:05:00+00:00

  ```json
  {
    "cause": 47,
    "data": {
      "complete_event": 48,
      "completes_at": "2026-03-09T16:05:00+00:00",
      "id": "a44",
      "state": "started"
    },
    "op": "action.state",
    "seq": 49,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```
- **` 50`** `actor.ongoing` ← cause `47` · _state_  
  bob ongoing -> a44

  ```json
  {
    "cause": 47,
    "data": {
      "action": "a44",
      "actor": "bob"
    },
    "op": "actor.ongoing",
    "seq": 50,
    "t": "2026-03-09T16:00:00+00:00"
  }
  ```

### ⏱ 2026-03-09 12:05:00 America/New_York  ·  `2026-03-09T16:05:00+00:00`

- **` 51`** `event.fired` ← cause `48` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 48,
    "data": {
      "data": {
        "action": "a44"
      },
      "event": 48,
      "kind": "action.complete",
      "t": "2026-03-09T16:05:00+00:00"
    },
    "op": "event.fired",
    "seq": 51,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 52`** `action.state` ← cause `51` · _actions_  
  a44 -> completed

  ```json
  {
    "cause": 51,
    "data": {
      "id": "a44",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 52,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 53`** `actor.ongoing` ← cause `51` · _state_  
  bob ongoing -> None

  ```json
  {
    "cause": 51,
    "data": {
      "action": null,
      "actor": "bob"
    },
    "op": "actor.ongoing",
    "seq": 53,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 54`** `info.create` ← cause `51` · _info_  
  i54 by bob: 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob' data={}

  ```json
  {
    "cause": 51,
    "data": {
      "author": "bob",
      "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
      "data": {},
      "id": "i54"
    },
    "op": "info.create",
    "seq": 54,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 55`** `info.send` ← cause `54` · _info_  
  i54 -> alice via email

  ```json
  {
    "cause": 54,
    "data": {
      "channel": "email",
      "id": "i54",
      "to": "alice"
    },
    "op": "info.send",
    "seq": 55,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 56`** `event.scheduled` ← cause `55` · _ledger-only_  
  [info.deliver] at 2026-03-09T16:05:30+00:00 depth=0

  ```json
  {
    "cause": 55,
    "data": {
      "data": {
        "channel": "email",
        "info": "i54",
        "to": "alice"
      },
      "depth": 0,
      "kind": "info.deliver",
      "t": "2026-03-09T16:05:30+00:00"
    },
    "op": "event.scheduled",
    "seq": 56,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 57`** `actor.memory` ← cause `51` · _state_  
  bob <- (note) 'Sent message to alice on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'

  ```json
  {
    "cause": 51,
    "data": {
      "actor": "bob",
      "content": "Sent message to alice on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
      "kind": "note",
      "source": "a44"
    },
    "op": "actor.memory",
    "seq": 57,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 58`** `actor.view` ← cause `51` · _views_  
  bob shown world v57, reasons=['action_completed']

  ```json
  {
    "cause": 51,
    "data": {
      "actor": "bob",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a44"
        }
      ],
      "rendered": "Current time:\n2026-03-09 09:05:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'alice', 'channel': 'email', 'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:00:00 America/Los_Angeles] (note) Alice asked for Q2 pipeline confirmation; I replied with $4.2M.\n- [2026-03-09 09:05:00 America/Los_Angeles] (note) Sent message to alice on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 57
    },
    "op": "actor.view",
    "seq": 58,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 59`** `mind.exchange` ← cause `58` · _views_  
  bob LLM exchange parsed=True attempt=0

  ```json
  {
    "cause": 58,
    "data": {
      "actor": "bob",
      "attempt": 0,
      "parsed": true,
      "request": "You are Bob Okafor, finance lead on the West Coast. You personally locked the final Q2 pipeline total of $4.2M on March 3. Alice is a trusted colleague; you answer colleagues promptly once you see their request.\n\n=== YOUR CURRENT SITUATION ===\nCurrent time:\n2026-03-09 09:05:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'alice', 'channel': 'email', 'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:00:00 America/Los_Angeles] (note) Alice asked for Q2 pipeline confirmation; I replied with $4.2M.\n- [2026-03-09 09:05:00 America/Los_Angeles] (note) Sent message to alice on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "response": "{\n  \"note\": \"I've replied to Alice with the confirmed number; nothing else needs my attention right now.\",\n  \"updates\": [],\n  \"intentions\": [],\n  \"wake_me_in_minutes\": null\n}",
      "system": "You are Bob Okafor, a real person, living through the situation described.\nYou are not an assistant and you are not narrating a story: you are this person,\nmaking your own decisions inside your own day. You only know what appears in the\nbriefing below. You cannot see other people's thoughts, you cannot control\noutcomes, and your actions take real time. You propose what you do next; the\nworld decides what actually happens.\n\nRespond with ONLY a JSON object, no markdown fences, with this shape:\n{\n  \"note\": \"one sentence: what you are thinking/deciding and why\",\n  \"updates\": [\n    {\"op\": \"actor.belief\", \"data\": {\"actor\": \"bob\", \"topic\": \"...\",\n       \"statement\": \"...\", \"basis\": \"where this belief comes from\"}},\n    {\"op\": \"actor.memory\", \"data\": {\"actor\": \"bob\", \"kind\": \"note\",\n       \"content\": \"...\", \"source\": \"decision\"}}\n  ],\n  \"intentions\": [\n    {\"verb\": \"<one of the available actions>\", \"params\": {...},\n       \"duration_minutes\": <realistic number>,\n       \"duration_basis\": \"actor_chosen\",\n       \"duration_note\": \"why this long\",\n       \"note\": \"why you are doing this\"}\n  ],\n  \"wake_me_in_minutes\": null\n}\n\nRules:\n- updates may only use ops actor.belief / actor.memory / actor.plan /\n  actor.emotion (data.actor must be \"bob\").\n- intentions[].verb must be one of the actions listed as available to you.\n- durations must be realistic for a human doing that task.\n- if nothing needs doing right now, return empty lists.\n- \"wake_me_in_minutes\": set a number only if you genuinely want to revisit\n  the situation later without any new trigger."
    },
    "op": "mind.exchange",
    "seq": 59,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```
- **` 60`** `actor.decision` ← cause `58` · _wakes_  
  bob because ['action_completed'] -> intentions=[] | "I've replied to Alice with the confirmed number; nothing else needs my attention right now."

  ```json
  {
    "cause": 58,
    "data": {
      "actor": "bob",
      "based_on_version": 57,
      "intentions": [],
      "note": "I've replied to Alice with the confirmed number; nothing else needs my attention right now.",
      "reasons": [
        {
          "channel": null,
          "detail": "send_message",
          "kind": "action_completed",
          "ref": "a44"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 60,
    "t": "2026-03-09T16:05:00+00:00"
  }
  ```

### ⏱ 2026-03-09 12:05:30 America/New_York  ·  `2026-03-09T16:05:30+00:00`

- **` 61`** `event.fired` ← cause `56` · _ledger-only_  
  [info.deliver]

  ```json
  {
    "cause": 56,
    "data": {
      "data": {
        "channel": "email",
        "info": "i54",
        "to": "alice"
      },
      "event": 56,
      "kind": "info.deliver",
      "t": "2026-03-09T16:05:30+00:00"
    },
    "op": "event.fired",
    "seq": 61,
    "t": "2026-03-09T16:05:30+00:00"
  }
  ```
- **` 62`** `info.deliver` ← cause `61` · _info_  
  i54 DELIVERED to alice via email

  ```json
  {
    "cause": 61,
    "data": {
      "channel": "email",
      "id": "i54",
      "to": "alice"
    },
    "op": "info.deliver",
    "seq": 62,
    "t": "2026-03-09T16:05:30+00:00"
  }
  ```
- **` 63`** `event.scheduled` ← cause `61` · _ledger-only_  
  [info.notice] at 2026-03-09T16:30:00+00:00 depth=0

  ```json
  {
    "cause": 61,
    "data": {
      "data": {
        "actor": "alice",
        "basis": "inferred",
        "channel": "email",
        "info": "i54",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "depth": 0,
      "kind": "info.notice",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 63,
    "t": "2026-03-09T16:05:30+00:00"
  }
  ```

### ⏱ 2026-03-09 12:30:00 America/New_York  ·  `2026-03-09T16:30:00+00:00`

- **` 64`** `event.fired` ← cause `63` · _ledger-only_  
  [info.notice]

  ```json
  {
    "cause": 63,
    "data": {
      "data": {
        "actor": "alice",
        "basis": "inferred",
        "channel": "email",
        "info": "i54",
        "note": "office worker; checks email roughly every half hour during work hours"
      },
      "event": 63,
      "kind": "info.notice",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 64,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 65`** `info.notice` ← cause `64` · _info_  
  i54 NOTICED by alice

  ```json
  {
    "cause": 64,
    "data": {
      "actor": "alice",
      "id": "i54"
    },
    "op": "info.notice",
    "seq": 65,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 66`** `actor.memory` ← cause `65` · _state_  
  alice <- (observation) 'Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'

  ```json
  {
    "cause": 65,
    "data": {
      "actor": "alice",
      "content": "Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
      "kind": "observation",
      "source": "i54"
    },
    "op": "actor.memory",
    "seq": 66,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 67`** `actor.view` ← cause `65` · _views_  
  alice shown world v66, reasons=['info_noticed']

  ```json
  {
    "cause": 65,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from bob on email",
          "kind": "info_noticed",
          "ref": "i54"
        }
      ],
      "rendered": "Current time:\n2026-03-09 12:30:00 America/New_York\n\nTime since your previous relevant decision:\n2 days, 14 hours, 12 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from bob on email\n\nNew information you have just noticed:\n- [email] message i54 from bob: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 66
    },
    "op": "actor.view",
    "seq": 67,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 68`** `actor.decision` ← cause `67` · _wakes_  
  alice because ['info_noticed'] -> intentions=['read_message'] | "Bob's reply arrived; reading it now"

  ```json
  {
    "cause": 67,
    "data": {
      "actor": "alice",
      "based_on_version": 66,
      "intentions": [
        "read_message"
      ],
      "note": "Bob's reply arrived; reading it now",
      "reasons": [
        {
          "channel": "email",
          "detail": "message from bob on email",
          "kind": "info_noticed",
          "ref": "i54"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 68,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 69`** `action.propose` ← cause `68` · _intentions+actions_  
  a69 alice:read_message {'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob', 'info': 'i54'} dur=240.0s (inferred) based_on_v66

  ```json
  {
    "cause": 68,
    "data": {
      "actor": "alice",
      "based_on_version": 66,
      "completes_when": null,
      "duration": {
        "basis": "inferred",
        "note": "short reply, quick read",
        "seconds": 240.0
      },
      "id": "a69",
      "interruptible": false,
      "interruption_note": "",
      "note": "Bob replied; reading it",
      "params": {
        "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
        "info": "i54"
      },
      "verb": "read_message"
    },
    "op": "action.propose",
    "seq": 69,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 70`** `event.scheduled` ← cause `69` · _ledger-only_  
  [action.start] at 2026-03-09T16:30:00+00:00 depth=1

  ```json
  {
    "cause": 69,
    "data": {
      "data": {
        "action": "a69"
      },
      "depth": 1,
      "kind": "action.start",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 70,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 71`** `action.state` ← cause `69` · _actions_  
  a69 -> scheduled

  ```json
  {
    "cause": 69,
    "data": {
      "id": "a69",
      "start_event": 70,
      "state": "scheduled"
    },
    "op": "action.state",
    "seq": 71,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 72`** `event.fired` ← cause `70` · _ledger-only_  
  [action.start]

  ```json
  {
    "cause": 70,
    "data": {
      "data": {
        "action": "a69"
      },
      "event": 70,
      "kind": "action.start",
      "t": "2026-03-09T16:30:00+00:00"
    },
    "op": "event.fired",
    "seq": 72,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 73`** `event.scheduled` ← cause `72` · _ledger-only_  
  [action.complete] at 2026-03-09T16:34:00+00:00 depth=0

  ```json
  {
    "cause": 72,
    "data": {
      "data": {
        "action": "a69"
      },
      "depth": 0,
      "kind": "action.complete",
      "t": "2026-03-09T16:34:00+00:00"
    },
    "op": "event.scheduled",
    "seq": 73,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 74`** `action.state` ← cause `72` · _actions_  
  a69 -> started completes_at=2026-03-09T16:34:00+00:00

  ```json
  {
    "cause": 72,
    "data": {
      "complete_event": 73,
      "completes_at": "2026-03-09T16:34:00+00:00",
      "id": "a69",
      "state": "started"
    },
    "op": "action.state",
    "seq": 74,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```
- **` 75`** `actor.ongoing` ← cause `72` · _state_  
  alice ongoing -> a69

  ```json
  {
    "cause": 72,
    "data": {
      "action": "a69",
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 75,
    "t": "2026-03-09T16:30:00+00:00"
  }
  ```

### ⏱ 2026-03-09 12:34:00 America/New_York  ·  `2026-03-09T16:34:00+00:00`

- **` 76`** `event.fired` ← cause `73` · _ledger-only_  
  [action.complete]

  ```json
  {
    "cause": 73,
    "data": {
      "data": {
        "action": "a69"
      },
      "event": 73,
      "kind": "action.complete",
      "t": "2026-03-09T16:34:00+00:00"
    },
    "op": "event.fired",
    "seq": 76,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 77`** `action.state` ← cause `76` · _actions_  
  a69 -> completed

  ```json
  {
    "cause": 76,
    "data": {
      "id": "a69",
      "state": "completed"
    },
    "op": "action.state",
    "seq": 77,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 78`** `actor.ongoing` ← cause `76` · _state_  
  alice ongoing -> None

  ```json
  {
    "cause": 76,
    "data": {
      "action": null,
      "actor": "alice"
    },
    "op": "actor.ongoing",
    "seq": 78,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 79`** `actor.memory` ← cause `76` · _state_  
  alice <- (note) 'Read message i54 in full.'

  ```json
  {
    "cause": 76,
    "data": {
      "actor": "alice",
      "content": "Read message i54 in full.",
      "kind": "note",
      "source": "i54"
    },
    "op": "actor.memory",
    "seq": 79,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 80`** `actor.view` ← cause `76` · _views_  
  alice shown world v79, reasons=['action_completed']

  ```json
  {
    "cause": 76,
    "data": {
      "actor": "alice",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a69"
        }
      ],
      "rendered": "Current time:\n2026-03-09 12:34:00 America/New_York\n\nTime since your previous relevant decision:\n4 minutes\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i54', 'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\n- [2026-03-09 12:34:00 America/New_York] (note) Read message i54 in full.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
      "world_version": 79
    },
    "op": "actor.view",
    "seq": 80,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 81`** `actor.decision` ← cause `80` · _wakes_  
  alice because ['action_completed'] -> intentions=[] | "Interpreting Bob's reply: the numbers are confirmed"

  ```json
  {
    "cause": 80,
    "data": {
      "actor": "alice",
      "based_on_version": 79,
      "intentions": [],
      "note": "Interpreting Bob's reply: the numbers are confirmed",
      "reasons": [
        {
          "channel": null,
          "detail": "read_message",
          "kind": "action_completed",
          "ref": "a69"
        }
      ]
    },
    "op": "actor.decision",
    "seq": 81,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 82`** `actor.belief` ← cause `81` · _state_  
  alice[q2_confirmed] = 'Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob' (basis: his email (i54), read in full)

  ```json
  {
    "cause": 81,
    "data": {
      "actor": "alice",
      "basis": "his email (i54), read in full",
      "statement": "Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
      "topic": "q2_confirmed"
    },
    "op": "actor.belief",
    "seq": 82,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 83`** `actor.plan` ← cause `81` · _state_  
  alice: 'Fold the confirmed numbers into the Monday summary.'

  ```json
  {
    "cause": 81,
    "data": {
      "actor": "alice",
      "plan": "Fold the confirmed numbers into the Monday summary."
    },
    "op": "actor.plan",
    "seq": 83,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```
- **` 84`** `terminal` ← cause `76` · _ledger-only_  
  [resolved] 'yes' -- Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob

  ```json
  {
    "cause": 76,
    "data": {
      "answer": {
        "answer": "yes",
        "computed_from": [
          "record:82"
        ],
        "detail": "Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob"
      },
      "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?",
      "status": "resolved"
    },
    "op": "terminal",
    "seq": 84,
    "t": "2026-03-09T16:34:00+00:00"
  }
  ```

## phase_b_email_llm — checkpoints.jsonl (0 checkpoints)

*(no checkpoints: the live-LLM run is not replayed through checkpoint/resume, since a re-run may legitimately differ)*

## phase_b_email_llm — terminal_result.json (with full producer lineage)

```json
{
  "answer": {
    "answer": "yes",
    "computed_from": [
      "record:82"
    ],
    "detail": "Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob"
  },
  "at": "2026-03-09T16:34:00+00:00",
  "producer_lineage": [
    {
      "data": {
        "answer": {
          "answer": "yes",
          "computed_from": [
            "record:82"
          ],
          "detail": "Alice held Bob's confirmation by 2026-03-09T16:34:00+00:00: Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob"
        },
        "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?",
        "status": "resolved"
      },
      "op": "terminal",
      "seq": 84,
      "t": "2026-03-09T16:34:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a69"
        },
        "event": 73,
        "kind": "action.complete",
        "t": "2026-03-09T16:34:00+00:00"
      },
      "op": "event.fired",
      "seq": 76,
      "t": "2026-03-09T16:34:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a69"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-03-09T16:34:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 73,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a69"
        },
        "event": 70,
        "kind": "action.start",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.fired",
      "seq": 72,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a69"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 70,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 66,
        "completes_when": null,
        "duration": {
          "basis": "inferred",
          "note": "short reply, quick read",
          "seconds": 240.0
        },
        "id": "a69",
        "interruptible": false,
        "interruption_note": "",
        "note": "Bob replied; reading it",
        "params": {
          "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
          "info": "i54"
        },
        "verb": "read_message"
      },
      "op": "action.propose",
      "seq": 69,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 66,
        "intentions": [
          "read_message"
        ],
        "note": "Bob's reply arrived; reading it now",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from bob on email",
            "kind": "info_noticed",
            "ref": "i54"
          }
        ]
      },
      "op": "actor.decision",
      "seq": 68,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from bob on email",
            "kind": "info_noticed",
            "ref": "i54"
          }
        ],
        "rendered": "Current time:\n2026-03-09 12:30:00 America/New_York\n\nTime since your previous relevant decision:\n2 days, 14 hours, 12 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from bob on email\n\nNew information you have just noticed:\n- [email] message i54 from bob: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 66
      },
      "op": "actor.view",
      "seq": 67,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "id": "i54"
      },
      "op": "info.notice",
      "seq": 65,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "basis": "inferred",
          "channel": "email",
          "info": "i54",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "event": 63,
        "kind": "info.notice",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.fired",
      "seq": 64,
      "t": "2026-03-09T16:30:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "basis": "inferred",
          "channel": "email",
          "info": "i54",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "depth": 0,
        "kind": "info.notice",
        "t": "2026-03-09T16:30:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 63,
      "t": "2026-03-09T16:05:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i54",
          "to": "alice"
        },
        "event": 56,
        "kind": "info.deliver",
        "t": "2026-03-09T16:05:30+00:00"
      },
      "op": "event.fired",
      "seq": 61,
      "t": "2026-03-09T16:05:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i54",
          "to": "alice"
        },
        "depth": 0,
        "kind": "info.deliver",
        "t": "2026-03-09T16:05:30+00:00"
      },
      "op": "event.scheduled",
      "seq": 56,
      "t": "2026-03-09T16:05:00+00:00"
    },
    {
      "data": {
        "channel": "email",
        "id": "i54",
        "to": "alice"
      },
      "op": "info.send",
      "seq": 55,
      "t": "2026-03-09T16:05:00+00:00"
    },
    {
      "data": {
        "author": "bob",
        "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
        "data": {},
        "id": "i54"
      },
      "op": "info.create",
      "seq": 54,
      "t": "2026-03-09T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a44"
        },
        "event": 48,
        "kind": "action.complete",
        "t": "2026-03-09T16:05:00+00:00"
      },
      "op": "event.fired",
      "seq": 51,
      "t": "2026-03-09T16:05:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a44"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-03-09T16:05:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 48,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a44"
        },
        "event": 45,
        "kind": "action.start",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.fired",
      "seq": 47,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a44"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 45,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "based_on_version": 39,
        "completes_when": null,
        "duration": {
          "basis": "actor_chosen",
          "note": "Quick reply to a straightforward request.",
          "seconds": 300.0
        },
        "id": "a44",
        "interruptible": false,
        "interruption_note": "",
        "note": "Confirming the numbers promptly as Alice needs them for Monday.",
        "params": {
          "channel": "email",
          "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob",
          "to": "alice"
        },
        "verb": "send_message"
      },
      "op": "action.propose",
      "seq": 44,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "based_on_version": 39,
        "intentions": [
          "send_message"
        ],
        "note": "Alice needs the Q2 numbers for Monday's summary; I'll reply now with the confirmed $4.2M total.",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from alice on email",
            "kind": "info_noticed",
            "ref": "i27"
          }
        ]
      },
      "op": "actor.decision",
      "seq": 42,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "reasons": [
          {
            "channel": "email",
            "detail": "message from alice on email",
            "kind": "info_noticed",
            "ref": "i27"
          }
        ],
        "rendered": "Current time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 39
      },
      "op": "actor.view",
      "seq": 40,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "actor": "bob",
        "id": "i27"
      },
      "op": "info.notice",
      "seq": 38,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "bob",
          "basis": "inferred",
          "channel": "email",
          "info": "i27",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "event": 36,
        "kind": "info.notice",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.fired",
      "seq": 37,
      "t": "2026-03-09T16:00:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "bob",
          "basis": "inferred",
          "channel": "email",
          "info": "i27",
          "note": "office worker; checks email roughly every half hour during work hours"
        },
        "depth": 0,
        "kind": "info.notice",
        "t": "2026-03-09T16:00:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 36,
      "t": "2026-03-07T02:18:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i27",
          "to": "bob"
        },
        "event": 29,
        "kind": "info.deliver",
        "t": "2026-03-07T02:18:30+00:00"
      },
      "op": "event.fired",
      "seq": 34,
      "t": "2026-03-07T02:18:30+00:00"
    },
    {
      "data": {
        "data": {
          "channel": "email",
          "info": "i27",
          "to": "bob"
        },
        "depth": 0,
        "kind": "info.deliver",
        "t": "2026-03-07T02:18:30+00:00"
      },
      "op": "event.scheduled",
      "seq": 29,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "channel": "email",
        "id": "i27",
        "to": "bob"
      },
      "op": "info.send",
      "seq": 28,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "author": "alice",
        "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
        "data": {
          "thread": "q2",
          "type": "question"
        },
        "id": "i27"
      },
      "op": "info.create",
      "seq": 27,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "event": 21,
        "kind": "action.complete",
        "t": "2026-03-07T02:18:00+00:00"
      },
      "op": "event.fired",
      "seq": 24,
      "t": "2026-03-07T02:18:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "depth": 0,
        "kind": "action.complete",
        "t": "2026-03-07T02:18:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 21,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "event": 18,
        "kind": "action.start",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.fired",
      "seq": 20,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "action": "a17"
        },
        "depth": 1,
        "kind": "action.start",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 18,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 12,
        "completes_when": null,
        "duration": {
          "basis": "actor_chosen",
          "note": "time she takes to compose a short email",
          "seconds": 480.0
        },
        "id": "a17",
        "interruptible": false,
        "interruption_note": "",
        "note": "fulfilling her Friday commitment",
        "params": {
          "channel": "email",
          "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.",
          "data": {
            "thread": "q2",
            "type": "question"
          },
          "to": "bob"
        },
        "verb": "send_message"
      },
      "op": "action.propose",
      "seq": 17,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "based_on_version": 12,
        "intentions": [
          "send_message"
        ],
        "note": "Friday evening: sending Bob the Q2 question before logging off",
        "reasons": [
          {
            "channel": null,
            "detail": "c1: email Bob about the Q2 numbers before the weekend",
            "kind": "scheduled_commitment",
            "ref": null
          }
        ]
      },
      "op": "actor.decision",
      "seq": 14,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "actor": "alice",
        "reasons": [
          {
            "channel": null,
            "detail": "c1: email Bob about the Q2 numbers before the weekend",
            "kind": "scheduled_commitment",
            "ref": null
          }
        ],
        "rendered": "Current time:\n2026-03-06 21:10:00 America/New_York\n\nUpcoming commitments:\n- email Bob about the Q2 numbers before the weekend in 0 minutes (at 2026-03-06 21:10:00 America/New_York)\n\nWhy you are being consulted now:\n- scheduled_commitment: c1: email Bob about the Q2 numbers before the weekend\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.",
        "world_version": 12
      },
      "op": "actor.view",
      "seq": 13,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "reason": "scheduled_commitment"
        },
        "event": 9,
        "kind": "wake.actor",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.fired",
      "seq": 12,
      "t": "2026-03-07T02:10:00+00:00"
    },
    {
      "data": {
        "data": {
          "actor": "alice",
          "detail": "c1: email Bob about the Q2 numbers before the weekend",
          "reason": "scheduled_commitment"
        },
        "depth": 0,
        "kind": "wake.actor",
        "t": "2026-03-07T02:10:00+00:00"
      },
      "op": "event.scheduled",
      "seq": 9,
      "t": "2026-03-06T13:00:00+00:00"
    }
  ],
  "question": "Does Alice have Bob's confirmation of the final Q2 numbers before Tuesday 2026-03-10 12:00 America/New_York?",
  "status": "resolved"
}
```

## phase_b_email_llm — replay_verification.json

```json
{
  "deterministic_repeat_run": null,
  "final_hash_match": true,
  "initial_state_hash": "ba87ca493adfb0f2c2dc5f8a8e5bf57ce735b640d8506dd3a92f5c4a10c69dac",
  "ledger_records": 84,
  "original_final_hash": "76dd9b93f2639ea02e2f99e861577ff20238f02a849f125546ca93411313677a",
  "replayed_final_hash": "76dd9b93f2639ea02e2f99e861577ff20238f02a849f125546ca93411313677a",
  "terminal_match": true
}
```

## phase_b_email_llm — runtime_metrics.json

```json
{
  "decisions": 6,
  "deferred_wakes": 0,
  "events_processed": 11,
  "intentions": 3,
  "ledger_records": 84,
  "llm_calls": 2,
  "pending_events_at_end": 1,
  "rejections": 0,
  "wall_ms": 4718.5
}
```

## phase_b_email_llm — actor_wakes.jsonl (6 records, verbatim)

```json
{"cause": 13, "data": {"actor": "alice", "based_on_version": 12, "intentions": ["send_message"], "note": "Friday evening: sending Bob the Q2 question before logging off", "reasons": [{"channel": null, "detail": "c1: email Bob about the Q2 numbers before the weekend", "kind": "scheduled_commitment", "ref": null}]}, "op": "actor.decision", "seq": 14, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 31, "data": {"actor": "alice", "based_on_version": 30, "intentions": [], "note": "Email sent; waiting on Bob", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a17"}]}, "op": "actor.decision", "seq": 32, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 40, "data": {"actor": "bob", "based_on_version": 39, "intentions": ["send_message"], "note": "Alice needs the Q2 numbers for Monday's summary; I'll reply now with the confirmed $4.2M total.", "reasons": [{"channel": "email", "detail": "message from alice on email", "kind": "info_noticed", "ref": "i27"}]}, "op": "actor.decision", "seq": 42, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 58, "data": {"actor": "bob", "based_on_version": 57, "intentions": [], "note": "I've replied to Alice with the confirmed number; nothing else needs my attention right now.", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a44"}]}, "op": "actor.decision", "seq": 60, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 67, "data": {"actor": "alice", "based_on_version": 66, "intentions": ["read_message"], "note": "Bob's reply arrived; reading it now", "reasons": [{"channel": "email", "detail": "message from bob on email", "kind": "info_noticed", "ref": "i54"}]}, "op": "actor.decision", "seq": 68, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 80, "data": {"actor": "alice", "based_on_version": 79, "intentions": [], "note": "Interpreting Bob's reply: the numbers are confirmed", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a69"}]}, "op": "actor.decision", "seq": 81, "t": "2026-03-09T16:34:00+00:00"}
```

## phase_b_email_llm — actor_views.jsonl (8 records, verbatim)

```json
{"cause": 12, "data": {"actor": "alice", "reasons": [{"channel": null, "detail": "c1: email Bob about the Q2 numbers before the weekend", "kind": "scheduled_commitment", "ref": null}], "rendered": "Current time:\n2026-03-06 21:10:00 America/New_York\n\nUpcoming commitments:\n- email Bob about the Q2 numbers before the weekend in 0 minutes (at 2026-03-06 21:10:00 America/New_York)\n\nWhy you are being consulted now:\n- scheduled_commitment: c1: email Bob about the Q2 numbers before the weekend\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 12}, "op": "actor.view", "seq": 13, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 24, "data": {"actor": "alice", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a17"}], "rendered": "Current time:\n2026-03-06 21:18:00 America/New_York\n\nTime since your previous relevant decision:\n8 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'bob', 'channel': 'email', 'content': \"Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\", 'data': {'type': 'question', 'thread': 'q2'}}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 30}, "op": "actor.view", "seq": 31, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 38, "data": {"actor": "bob", "reasons": [{"channel": "email", "detail": "message from alice on email", "kind": "info_noticed", "ref": "i27"}], "rendered": "Current time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 39}, "op": "actor.view", "seq": 40, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 40, "data": {"actor": "bob", "attempt": 0, "parsed": true, "request": "You are Bob Okafor, finance lead on the West Coast. You personally locked the final Q2 pipeline total of $4.2M on March 3. Alice is a trusted colleague; you answer colleagues promptly once you see their request.\n\n=== YOUR CURRENT SITUATION ===\nCurrent time:\n2026-03-09 09:00:00 America/Los_Angeles\n\nWhy you are being consulted now:\n- info_noticed: message from alice on email\n\nNew information you have just noticed:\n- [email] message i27 from alice: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "response": "{\n  \"note\": \"Alice needs the Q2 numbers for Monday's summary; I'll reply now with the confirmed $4.2M total.\",\n  \"updates\": [\n    {\n      \"op\": \"actor.memory\",\n      \"data\": {\n        \"actor\": \"bob\",\n        \"kind\": \"note\",\n        \"content\": \"Alice asked for Q2 pipeline confirmation; I replied with $4.2M.\",\n        \"source\": \"decision\"\n      }\n    }\n  ],\n  \"intentions\": [\n    {\n      \"verb\": \"send_message\",\n      \"params\": {\n        \"to\": \"alice\",\n        \"channel\": \"email\",\n        \"content\": \"Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\"\n      },\n      \"duration_minutes\": 5,\n      \"duration_basis\": \"actor_chosen\",\n      \"duration_note\": \"Quick reply to a straightforward request.\",\n      \"note\": \"Confirming the numbers promptly as Alice needs them for Monday.\"\n    }\n  ],\n  \"wake_me_in_minutes\": null\n}", "system": "You are Bob Okafor, a real person, living through the situation described.\nYou are not an assistant and you are not narrating a story: you are this person,\nmaking your own decisions inside your own day. You only know what appears in the\nbriefing below. You cannot see other people's thoughts, you cannot control\noutcomes, and your actions take real time. You propose what you do next; the\nworld decides what actually happens.\n\nRespond with ONLY a JSON object, no markdown fences, with this shape:\n{\n  \"note\": \"one sentence: what you are thinking/deciding and why\",\n  \"updates\": [\n    {\"op\": \"actor.belief\", \"data\": {\"actor\": \"bob\", \"topic\": \"...\",\n       \"statement\": \"...\", \"basis\": \"where this belief comes from\"}},\n    {\"op\": \"actor.memory\", \"data\": {\"actor\": \"bob\", \"kind\": \"note\",\n       \"content\": \"...\", \"source\": \"decision\"}}\n  ],\n  \"intentions\": [\n    {\"verb\": \"<one of the available actions>\", \"params\": {...},\n       \"duration_minutes\": <realistic number>,\n       \"duration_basis\": \"actor_chosen\",\n       \"duration_note\": \"why this long\",\n       \"note\": \"why you are doing this\"}\n  ],\n  \"wake_me_in_minutes\": null\n}\n\nRules:\n- updates may only use ops actor.belief / actor.memory / actor.plan /\n  actor.emotion (data.actor must be \"bob\").\n- intentions[].verb must be one of the actions listed as available to you.\n- durations must be realistic for a human doing that task.\n- if nothing needs doing right now, return empty lists.\n- \"wake_me_in_minutes\": set a number only if you genuinely want to revisit\n  the situation later without any new trigger."}, "op": "mind.exchange", "seq": 41, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 51, "data": {"actor": "bob", "reasons": [{"channel": null, "detail": "send_message", "kind": "action_completed", "ref": "a44"}], "rendered": "Current time:\n2026-03-09 09:05:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'alice', 'channel': 'email', 'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:00:00 America/Los_Angeles] (note) Alice asked for Q2 pipeline confirmation; I replied with $4.2M.\n- [2026-03-09 09:05:00 America/Los_Angeles] (note) Sent message to alice on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 57}, "op": "actor.view", "seq": 58, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 58, "data": {"actor": "bob", "attempt": 0, "parsed": true, "request": "You are Bob Okafor, finance lead on the West Coast. You personally locked the final Q2 pipeline total of $4.2M on March 3. Alice is a trusted colleague; you answer colleagues promptly once you see their request.\n\n=== YOUR CURRENT SITUATION ===\nCurrent time:\n2026-03-09 09:05:00 America/Los_Angeles\n\nTime since your previous relevant decision:\n5 minutes\n\nWhy you are being consulted now:\n- action_completed: send_message\n\nYou just finished: send_message {'to': 'alice', 'channel': 'email', 'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'}\n\nYour role: finance lead, West Coast office\nYour goals:\n- keep the quarter-close numbers accurate\nYour dispositions:\n- precise\n- answers colleagues promptly once he sees a request\nYour current beliefs:\n- [q2_numbers] The final Q2 pipeline total is $4.2M, locked on March 3. (basis: verified: he closed the books himself on March 3)\nYour relationships:\n- alice: trusted colleague preparing the Q2 summary\nYour emotional state: unwinding into the weekend\nYour physical state: rested\nYour current plan: Off for the weekend; back Monday morning.\nYour memories (oldest first):\n- [2026-03-09 09:00:00 America/Los_Angeles] (observation) Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 09:00:00 America/Los_Angeles] (note) Alice asked for Q2 pipeline confirmation; I replied with $4.2M.\n- [2026-03-09 09:05:00 America/Los_Angeles] (note) Sent message to alice on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "response": "{\n  \"note\": \"I've replied to Alice with the confirmed number; nothing else needs my attention right now.\",\n  \"updates\": [],\n  \"intentions\": [],\n  \"wake_me_in_minutes\": null\n}", "system": "You are Bob Okafor, a real person, living through the situation described.\nYou are not an assistant and you are not narrating a story: you are this person,\nmaking your own decisions inside your own day. You only know what appears in the\nbriefing below. You cannot see other people's thoughts, you cannot control\noutcomes, and your actions take real time. You propose what you do next; the\nworld decides what actually happens.\n\nRespond with ONLY a JSON object, no markdown fences, with this shape:\n{\n  \"note\": \"one sentence: what you are thinking/deciding and why\",\n  \"updates\": [\n    {\"op\": \"actor.belief\", \"data\": {\"actor\": \"bob\", \"topic\": \"...\",\n       \"statement\": \"...\", \"basis\": \"where this belief comes from\"}},\n    {\"op\": \"actor.memory\", \"data\": {\"actor\": \"bob\", \"kind\": \"note\",\n       \"content\": \"...\", \"source\": \"decision\"}}\n  ],\n  \"intentions\": [\n    {\"verb\": \"<one of the available actions>\", \"params\": {...},\n       \"duration_minutes\": <realistic number>,\n       \"duration_basis\": \"actor_chosen\",\n       \"duration_note\": \"why this long\",\n       \"note\": \"why you are doing this\"}\n  ],\n  \"wake_me_in_minutes\": null\n}\n\nRules:\n- updates may only use ops actor.belief / actor.memory / actor.plan /\n  actor.emotion (data.actor must be \"bob\").\n- intentions[].verb must be one of the actions listed as available to you.\n- durations must be realistic for a human doing that task.\n- if nothing needs doing right now, return empty lists.\n- \"wake_me_in_minutes\": set a number only if you genuinely want to revisit\n  the situation later without any new trigger."}, "op": "mind.exchange", "seq": 59, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 65, "data": {"actor": "alice", "reasons": [{"channel": "email", "detail": "message from bob on email", "kind": "info_noticed", "ref": "i54"}], "rendered": "Current time:\n2026-03-09 12:30:00 America/New_York\n\nTime since your previous relevant decision:\n2 days, 14 hours, 12 minutes\n\nWhy you are being consulted now:\n- info_noticed: message from bob on email\n\nNew information you have just noticed:\n- [email] message i54 from bob: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 66}, "op": "actor.view", "seq": 67, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 76, "data": {"actor": "alice", "reasons": [{"channel": null, "detail": "read_message", "kind": "action_completed", "ref": "a69"}], "rendered": "Current time:\n2026-03-09 12:34:00 America/New_York\n\nTime since your previous relevant decision:\n4 minutes\n\nWhy you are being consulted now:\n- action_completed: read_message\n\nYou just finished: read_message {'info': 'i54', 'content': 'Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob'}\n\nYour role: program manager, East Coast office\nYour goals:\n- finalize the Monday Q2 summary with confirmed numbers\nYour dispositions:\n- thorough\n- dislikes sending unverified figures\nYour relationships:\n- bob: trusted colleague; owns the Q2 pipeline numbers\nYour emotional state: mildly pressed by the Monday deadline\nYour physical state: working a long Friday\nYour current plan: Wait for Bob's reply before finalizing the summary.\nYour memories (oldest first):\n- [2026-03-06 21:10:00 America/New_York] (note) Decided to email Bob about the Q2 numbers tonight.\n- [2026-03-06 21:18:00 America/New_York] (note) Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.\n- [2026-03-09 12:30:00 America/New_York] (observation) Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob\n- [2026-03-09 12:34:00 America/New_York] (note) Read message i54 in full.\nActions available to you:\n- read_message: Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.\n- send_message: Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "world_version": 79}, "op": "actor.view", "seq": 80, "t": "2026-03-09T16:34:00+00:00"}
```

## phase_b_email_llm — intentions.jsonl (3 records, verbatim)

```json
{"cause": 14, "data": {"actor": "alice", "based_on_version": 12, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "time she takes to compose a short email", "seconds": 480.0}, "id": "a17", "interruptible": false, "interruption_note": "", "note": "fulfilling her Friday commitment", "params": {"channel": "email", "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "data": {"thread": "q2", "type": "question"}, "to": "bob"}, "verb": "send_message"}, "op": "action.propose", "seq": 17, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 42, "data": {"actor": "bob", "based_on_version": 39, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "Quick reply to a straightforward request.", "seconds": 300.0}, "id": "a44", "interruptible": false, "interruption_note": "", "note": "Confirming the numbers promptly as Alice needs them for Monday.", "params": {"channel": "email", "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "to": "alice"}, "verb": "send_message"}, "op": "action.propose", "seq": 44, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 68, "data": {"actor": "alice", "based_on_version": 66, "completes_when": null, "duration": {"basis": "inferred", "note": "short reply, quick read", "seconds": 240.0}, "id": "a69", "interruptible": false, "interruption_note": "", "note": "Bob replied; reading it", "params": {"content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "info": "i54"}, "verb": "read_message"}, "op": "action.propose", "seq": 69, "t": "2026-03-09T16:30:00+00:00"}
```

## phase_b_email_llm — intention_rejections.jsonl (0 records, verbatim)

*(empty — nothing of this kind occurred in this run)*

## phase_b_email_llm — action_lifecycle.jsonl (14 records, verbatim)

```json
{"cause": null, "data": {"conditions": [{"id": "{params.to}", "require": "actor_exists"}, {"name": "{params.channel}", "require": "channel_exists"}, {"param": "content", "require": "param_nonempty"}], "description": "Compose and send a message. params: to (actor id), channel, content, data (optional dict). Composing takes time; delivery latency comes from the channel.", "effects": [["info.send_new", {"author": "{actor}", "channel": "{params.channel}", "content": "{params.content}", "data": "{params.data}", "to": ["{params.to}"]}], ["actor.memory", {"actor": "{actor}", "content": "Sent message to {params.to} on {params.channel}: {params.content}", "kind": "note", "source": "{action_id}"}]], "verb": "send_message"}, "op": "action.define", "seq": 3, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"conditions": [{"info": "{params.info}", "require": "noticed_info"}], "description": "Read a message you have noticed. params: info (message id), content (the text, for your own record). Reading takes time.", "effects": [["actor.memory", {"actor": "{actor}", "content": "Read message {params.info} in full.", "kind": "note", "source": "{params.info}"}]], "verb": "read_message"}, "op": "action.define", "seq": 4, "t": "2026-03-06T13:00:00+00:00"}
{"cause": 14, "data": {"actor": "alice", "based_on_version": 12, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "time she takes to compose a short email", "seconds": 480.0}, "id": "a17", "interruptible": false, "interruption_note": "", "note": "fulfilling her Friday commitment", "params": {"channel": "email", "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "data": {"thread": "q2", "type": "question"}, "to": "bob"}, "verb": "send_message"}, "op": "action.propose", "seq": 17, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 17, "data": {"id": "a17", "start_event": 18, "state": "scheduled"}, "op": "action.state", "seq": 19, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 20, "data": {"complete_event": 21, "completes_at": "2026-03-07T02:18:00+00:00", "id": "a17", "state": "started"}, "op": "action.state", "seq": 22, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 24, "data": {"id": "a17", "state": "completed"}, "op": "action.state", "seq": 25, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 42, "data": {"actor": "bob", "based_on_version": 39, "completes_when": null, "duration": {"basis": "actor_chosen", "note": "Quick reply to a straightforward request.", "seconds": 300.0}, "id": "a44", "interruptible": false, "interruption_note": "", "note": "Confirming the numbers promptly as Alice needs them for Monday.", "params": {"channel": "email", "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "to": "alice"}, "verb": "send_message"}, "op": "action.propose", "seq": 44, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 44, "data": {"id": "a44", "start_event": 45, "state": "scheduled"}, "op": "action.state", "seq": 46, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 47, "data": {"complete_event": 48, "completes_at": "2026-03-09T16:05:00+00:00", "id": "a44", "state": "started"}, "op": "action.state", "seq": 49, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 51, "data": {"id": "a44", "state": "completed"}, "op": "action.state", "seq": 52, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 68, "data": {"actor": "alice", "based_on_version": 66, "completes_when": null, "duration": {"basis": "inferred", "note": "short reply, quick read", "seconds": 240.0}, "id": "a69", "interruptible": false, "interruption_note": "", "note": "Bob replied; reading it", "params": {"content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "info": "i54"}, "verb": "read_message"}, "op": "action.propose", "seq": 69, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 69, "data": {"id": "a69", "start_event": 70, "state": "scheduled"}, "op": "action.state", "seq": 71, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 72, "data": {"complete_event": 73, "completes_at": "2026-03-09T16:34:00+00:00", "id": "a69", "state": "started"}, "op": "action.state", "seq": 74, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 76, "data": {"id": "a69", "state": "completed"}, "op": "action.state", "seq": 77, "t": "2026-03-09T16:34:00+00:00"}
```

## phase_b_email_llm — information_lifecycle.jsonl (8 records, verbatim)

```json
{"cause": 24, "data": {"author": "alice", "content": "Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "data": {"thread": "q2", "type": "question"}, "id": "i27"}, "op": "info.create", "seq": 27, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 27, "data": {"channel": "email", "id": "i27", "to": "bob"}, "op": "info.send", "seq": 28, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 34, "data": {"channel": "email", "id": "i27", "to": "bob"}, "op": "info.deliver", "seq": 35, "t": "2026-03-07T02:18:30+00:00"}
{"cause": 37, "data": {"actor": "bob", "id": "i27"}, "op": "info.notice", "seq": 38, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 51, "data": {"author": "bob", "content": "Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "data": {}, "id": "i54"}, "op": "info.create", "seq": 54, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 54, "data": {"channel": "email", "id": "i54", "to": "alice"}, "op": "info.send", "seq": 55, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 61, "data": {"channel": "email", "id": "i54", "to": "alice"}, "op": "info.deliver", "seq": 62, "t": "2026-03-09T16:05:30+00:00"}
{"cause": 64, "data": {"actor": "alice", "id": "i54"}, "op": "info.notice", "seq": 65, "t": "2026-03-09T16:30:00+00:00"}
```

## phase_b_email_llm — state_transitions.jsonl (21 records, verbatim)

```json
{"cause": null, "data": {"attention": {"email": {"basis": "inferred", "calendar": {"close": "17:00", "holidays": [], "open": "09:00", "tz": "America/New_York", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 1800.0, "note": "office worker; checks email roughly every half hour during work hours"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "mildly pressed by the Monday deadline", "goals": ["finalize the Monday Q2 summary with confirmed numbers"], "id": "alice", "last_decision_at": null, "memories": [], "name": "Alice Ramos", "noticed_info": [], "ongoing_action": null, "physical_state": "working a long Friday", "plan": "Finish the weekly review tonight, then get Bob's confirmation before the Monday summary.", "reconsider": [], "relationships": {"bob": "trusted colleague; owns the Q2 pipeline numbers"}, "role": "program manager, East Coast office", "tz": "America/New_York", "unprocessed_info": [], "values": ["thorough", "dislikes sending unverified figures"]}, "op": "actor.add", "seq": 5, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"attention": {"email": {"basis": "inferred", "calendar": {"close": "17:00", "holidays": [], "open": "09:00", "tz": "America/Los_Angeles", "workdays": [0, 1, 2, 3, 4]}, "check_every_seconds": 1800.0, "note": "office worker; checks email roughly every half hour during work hours"}}, "available_info": [], "beliefs": {}, "commitments": {}, "deferred_wakes": [], "emotional_state": "unwinding into the weekend", "goals": ["keep the quarter-close numbers accurate"], "id": "bob", "last_decision_at": null, "memories": [], "name": "Bob Okafor", "noticed_info": [], "ongoing_action": null, "physical_state": "rested", "plan": "Off for the weekend; back Monday morning.", "reconsider": [], "relationships": {"alice": "trusted colleague preparing the Q2 summary"}, "role": "finance lead, West Coast office", "tz": "America/Los_Angeles", "unprocessed_info": [], "values": ["precise", "answers colleagues promptly once he sees a request"]}, "op": "actor.add", "seq": 6, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"actor": "bob", "basis": "verified: he closed the books himself on March 3", "statement": "The final Q2 pipeline total is $4.2M, locked on March 3.", "topic": "q2_numbers"}, "op": "actor.belief", "seq": 7, "t": "2026-03-06T13:00:00+00:00"}
{"cause": null, "data": {"actor": "alice", "at": "2026-03-07T02:10:00+00:00", "id": "c1", "what": "email Bob about the Q2 numbers before the weekend"}, "op": "actor.commit", "seq": 8, "t": "2026-03-06T13:00:00+00:00"}
{"cause": 14, "data": {"actor": "alice", "id": "c1"}, "op": "actor.commitment_resolved", "seq": 15, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 14, "data": {"actor": "alice", "content": "Decided to email Bob about the Q2 numbers tonight.", "kind": "note", "source": "decision"}, "op": "actor.memory", "seq": 16, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 20, "data": {"action": "a17", "actor": "alice"}, "op": "actor.ongoing", "seq": 23, "t": "2026-03-07T02:10:00+00:00"}
{"cause": 24, "data": {"action": null, "actor": "alice"}, "op": "actor.ongoing", "seq": 26, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 24, "data": {"actor": "alice", "content": "Sent message to bob on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "kind": "note", "source": "a17"}, "op": "actor.memory", "seq": 30, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 32, "data": {"actor": "alice", "plan": "Wait for Bob's reply before finalizing the summary."}, "op": "actor.plan", "seq": 33, "t": "2026-03-07T02:18:00+00:00"}
{"cause": 38, "data": {"actor": "bob", "content": "Noticed message from alice on email: Hi Bob -- could you confirm the final Q2 pipeline numbers when you get a chance? I need them for Monday's summary.", "kind": "observation", "source": "i27"}, "op": "actor.memory", "seq": 39, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 42, "data": {"actor": "bob", "content": "Alice asked for Q2 pipeline confirmation; I replied with $4.2M.", "kind": "note", "source": "decision"}, "op": "actor.memory", "seq": 43, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 47, "data": {"action": "a44", "actor": "bob"}, "op": "actor.ongoing", "seq": 50, "t": "2026-03-09T16:00:00+00:00"}
{"cause": 51, "data": {"action": null, "actor": "bob"}, "op": "actor.ongoing", "seq": 53, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 51, "data": {"actor": "bob", "content": "Sent message to alice on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "kind": "note", "source": "a44"}, "op": "actor.memory", "seq": 57, "t": "2026-03-09T16:05:00+00:00"}
{"cause": 65, "data": {"actor": "alice", "content": "Noticed message from bob on email: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "kind": "observation", "source": "i54"}, "op": "actor.memory", "seq": 66, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 72, "data": {"action": "a69", "actor": "alice"}, "op": "actor.ongoing", "seq": 75, "t": "2026-03-09T16:30:00+00:00"}
{"cause": 76, "data": {"action": null, "actor": "alice"}, "op": "actor.ongoing", "seq": 78, "t": "2026-03-09T16:34:00+00:00"}
{"cause": 76, "data": {"actor": "alice", "content": "Read message i54 in full.", "kind": "note", "source": "i54"}, "op": "actor.memory", "seq": 79, "t": "2026-03-09T16:34:00+00:00"}
{"cause": 81, "data": {"actor": "alice", "basis": "his email (i54), read in full", "statement": "Bob confirmed the Q2 numbers: Hi Alice, the final Q2 pipeline total is $4.2M, locked on March 3. Let me know if you need anything else. Best, Bob", "topic": "q2_confirmed"}, "op": "actor.belief", "seq": 82, "t": "2026-03-09T16:34:00+00:00"}
{"cause": 81, "data": {"actor": "alice", "plan": "Fold the confirmed numbers into the Monday summary."}, "op": "actor.plan", "seq": 83, "t": "2026-03-09T16:34:00+00:00"}
```

## phase_b_email_llm — continuous_process_transitions.jsonl (0 records, verbatim)

*(empty — nothing of this kind occurred in this run)*

## phase_b_email_llm — reality_fidelity_review.md

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
