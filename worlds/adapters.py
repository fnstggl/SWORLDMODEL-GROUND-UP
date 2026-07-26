"""Shared scenario action definitions -- pure data, no code.

These are the kind of definitions a world compiler would emit.  Scenario
meaning ("send a message", "read a message") is expressed entirely as
declarative authority conditions, preconditions and effects composed from
the kernel's universal operations.  The same definitions serve the email
world and the committee world unchanged; there is no per-scenario engine
path anywhere.
"""

SEND_MESSAGE = {
    "verb": "send_message",
    "description": ("Compose and send a message. params: to (actor id), "
                    "channel, content, data (optional dict). Composing takes "
                    "time; delivery latency comes from the channel."),
    "conditions": [
        {"require": "actor_exists", "id": "{params.to}"},
        {"require": "channel_exists", "name": "{params.channel}"},
        {"require": "param_nonempty", "param": "content"},
    ],
    "effects": [
        ["info.send_new", {"author": "{actor}", "to": ["{params.to}"],
                           "channel": "{params.channel}",
                           "content": "{params.content}",
                           "data": "{params.data}"}],
        ["actor.memory", {"actor": "{actor}", "kind": "note",
                          "content": "Sent message to {params.to} on "
                                     "{params.channel}: {params.content}",
                          "source": "{action_id}"}],
    ],
}

READ_MESSAGE = {
    "verb": "read_message",
    "description": ("Read a message you have noticed. params: info (message "
                    "id), content (the text, for your own record). Reading "
                    "takes time."),
    "conditions": [
        {"require": "noticed_info", "info": "{params.info}"},
    ],
    "effects": [
        ["actor.memory", {"actor": "{actor}", "kind": "note",
                          "content": "Read message {params.info} in full.",
                          "source": "{params.info}"}],
    ],
}
