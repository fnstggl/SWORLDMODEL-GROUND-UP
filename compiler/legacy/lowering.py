"""Lowering: execute a genesis plan into a live runtime world.

Zero LLM calls, zero inference, zero helpful completion: the plan is applied
op by op through the kernel's single mutation funnel, every schedule is
placed, the declarative terminal is compiled, and per-actor identity briefs
are rendered from each actor's OWN state only (information boundaries are
preserved -- a brief can never leak what its actor does not know).

Anything the kernel refuses (bad provenance, unknown references, illegal
ops) surfaces here as a compile error with the offending op attached --
wrong worlds stop before anyone simulates them."""
from __future__ import annotations

from sworldmodel import World, build_terminal, fmt_local, parse_iso
from sworldmodel.engine import Terminal
from sworldmodel.terminals import validate_terminal_spec


class LoweringError(RuntimeError):
    pass


def lower_world(plan: dict) -> World:
    """Plan -> World (genesis unsealed; the engine seals it at run start)."""
    w = World(parse_iso(plan["start"]))
    for op, data in plan["ops"]:
        try:
            w.apply(op, data, None)
        except Exception as e:
            raise LoweringError(f"kernel refused genesis op {op}: {e} "
                                f"(data: {data})") from e
    for s in plan["schedules"]:
        try:
            w.schedule(s["kind"], s["data"], parse_iso(s["at"]), None)
        except Exception as e:
            raise LoweringError(f"kernel refused schedule {s['kind']} at "
                                f"{s['at']}: {e}") from e
    return w


def lower_terminal_obj(plan: dict) -> Terminal:
    validate_terminal_spec(plan["terminal_spec"])
    return build_terminal(plan["terminal_spec"])


def persona_briefs(world: World, start_iso: str) -> dict:
    """Identity briefs for LLM minds, rendered from each actor's own state.
    The rest of what a mind sees (beliefs, memories, noticed information,
    time) flows through the ActorView at simulation time."""
    start = parse_iso(start_iso)
    out = {}
    for aid, st in sorted(world.actors.items()):
        lines = [f"You are {st.name} -- {st.role}.",
                 f"Local date and time now: {fmt_local(start, st.tz)}."]
        if st.plan:
            lines.append(f"What you are currently doing: {st.plan}")
        out[aid] = {"name": st.name, "persona_brief": "\n".join(lines)}
    return out


def lower(plan: dict):
    """Plan -> (world, terminal, minds_info).  Deterministic; called both by
    validation (on throwaway replicas) and by instantiate()."""
    w = lower_world(plan)
    term = lower_terminal_obj(plan)
    return w, term, persona_briefs(w, plan["start"])
