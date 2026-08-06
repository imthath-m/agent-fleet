"""Deterministic fakes for local runs, tests, and evals — the triage analogue
of `spine.reference_agent.default_responder`. No network, no model, no creds.

`classifier_responder` keys off genuine signal words in the ticket itself. It
reads only the text after the `User:` marker that
`triage.classifier.build_prompt` emits, so the enum vocabularies listed earlier
in the prompt can never match themselves. Nothing here looks at ticket ids or
any golden-set-only token: the rules are ordinary support-desk heuristics, so
the eval numbers they produce mean something.

`resolver_responder` is the same idea for the resolver stage, and
`resolution_judge_client` is the fake grader for what it produces.
"""

from __future__ import annotations

import json
import re

from spine.models import FakeModelClient

from triage.resolver import CONTEXT_MARKER, USER_MARKER, content_terms

_USER_MARKER = "User:"

# An ordered (label, pattern) table, compiled from a signal-word table below.
_Rules = tuple[tuple[str, "re.Pattern[str]"], ...]

# Each table is ordered: the first label with a signal word present wins, and
# the last entry of each group is the fallback used when nothing matches.

_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "complaint",
        (
            "unacceptable",
            "ridiculous",
            "worst",
            "complaint",
            "complain",
            "fed up",
            "disappointed",
            "appalling",
            "waste of my time",
        ),
    ),
    (
        "billing",
        (
            "invoice",
            "billing",
            "billed",
            "charge",
            "charged",
            "refund",
            "payment",
            "subscription",
            "receipt",
            "renewal",
        ),
    ),
    (
        "account",
        (
            "log in",
            "login",
            "sign in",
            "locked out",
            "my account",
            "password",
            "username",
            "credentials",
            "two-factor",
        ),
    ),
    (
        "how_to",
        (
            "how do i",
            "how can i",
            "how to",
            "is there a way",
            "what is the command",
            "which command",
            "steps to",
            "walk me through",
            "where do i",
        ),
    ),
    (
        "technical",
        (
            "error",
            "crash",
            "fails",
            "failed",
            "failing",
            "not working",
            "stopped working",
            "broken",
            "does not work",
            "doesn't work",
            "freeze",
            "frozen",
            "hangs",
            "no longer works",
            # Symptom phrasing, for tickets that describe a fault without ever
            # using the word "error".
            "will not boot",
            "won't boot",
            "not detected",
            "nothing happens",
            "rescue prompt",
            "stays black",
            "no signal",
            "drops every",
            "disconnect",
            "refuses",
            "block",
        ),
    ),
)
_INTENT_DEFAULT = "other"

_PRIORITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "urgent",
        (
            "urgent",
            "asap",
            "immediately",
            "emergency",
            "critical",
            "outage",
            "production is down",
            "server is down",
            "data loss",
            "cannot work at all",
            "completely unusable",
        ),
    ),
    (
        "high",
        (
            "blocked",
            "blocking",
            "can't work",
            "cannot work",
            "unable to work",
            "can't log in",
            "cannot log in",
            "can't sign in",
            "cannot sign in",
            "locked out",
            "deadline",
            "won't boot",
            "will not boot",
            "no internet",
            "been down",
        ),
    ),
    (
        "low",
        (
            "no rush",
            "no hurry",
            "whenever you get a chance",
            "just curious",
            "just wondering",
            "low priority",
            "minor",
            "cosmetic",
            "no longer need",
        ),
    ),
)
_PRIORITY_DEFAULT = "normal"

_PRODUCT_AREA_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "install",
        (
            "install ubuntu",
            "installer",
            "installation media",
            "bootable usb",
            "usb stick",
            "live cd",
            "live usb",
            "dual boot",
            "dual-boot",
            "grub",
            "uefi",
            "secure boot",
            "partition",
            "reinstall",
            "fresh install",
            "won't boot",
            "will not boot",
        ),
    ),
    (
        "packaging",
        (
            "apt",
            "aptitude",
            "dpkg",
            "ppa",
            "repositor",
            "snap",
            "synaptic",
            "software centre",
            "software center",
            "update manager",
            ".deb",
            "package manager",
            "packages",
            "broken package",
            "dependenc",
            "unmet",
        ),
    ),
    (
        "networking",
        (
            "wifi",
            "wi-fi",
            "wireless",
            "ethernet",
            "network",
            "dns",
            "dhcp",
            "vpn",
            "internet",
            "router",
            "firewall",
            "ufw",
            "ip address",
        ),
    ),
    (
        "users_permissions",
        (
            "sudo",
            "sudoers",
            "permission",
            "chmod",
            "chown",
            "umask",
            "root user",
            "add a user",
            "add user",
            "user group",
            "group membership",
            "password",
            "acl",
            # Sign-in problems land on the same KB pages (LostPassword, RootSudo).
            "log in",
            "login",
            "sign in",
            "locked out",
        ),
    ),
    (
        "hardware",
        (
            "printer",
            "printing",
            "scanner",
            "webcam",
            "touchpad",
            "bluetooth",
            "graphics card",
            "nvidia",
            "monitor",
            "display driver",
            "audio",
            "sound card",
            "microphone",
            "battery",
        ),
    ),
)
_PRODUCT_AREA_DEFAULT = "other"

_SENTIMENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "angry",
        (
            "unacceptable",
            "furious",
            "outrageous",
            "ridiculous",
            "disgusted",
            "livid",
            "appalling",
            "worst",
            "!!!",
            "absolutely useless",
            "fed up",
        ),
    ),
    (
        "frustrated",
        (
            "frustrat",
            "annoying",
            "annoyed",
            "still not",
            "still doesn't",
            "still broken",
            "third time",
            "second time",
            "tired of",
            "struggling",
            "wasted",
            "going in circles",
        ),
    ),
    (
        "positive",
        (
            "thank you for",
            "thanks for",
            "appreciate",
            "works great",
            "love ubuntu",
            "great product",
            "happy with",
        ),
    ),
)
_SENTIMENT_DEFAULT = "neutral"


def _compile(signals: tuple[str, ...]) -> re.Pattern[str]:
    """One alternation per label, anchored at a word start.

    The leading `\\b` is what stops "laptop" matching the "apt" signal. There is
    deliberately no trailing boundary, so prefix signals ("frustrat",
    "repositor", "dependenc") still match their inflections. Signals that do not
    begin with a word character ("!!!", ".deb") are matched literally.
    """
    parts = [rf"\b{re.escape(s)}" if s[0].isalnum() else re.escape(s) for s in signals]
    return re.compile("|".join(parts))


def _compile_rules(rules: tuple[tuple[str, tuple[str, ...]], ...]) -> _Rules:
    return tuple((label, _compile(signals)) for label, signals in rules)


_INTENT_PATTERNS = _compile_rules(_INTENT_RULES)
_PRIORITY_PATTERNS = _compile_rules(_PRIORITY_RULES)
_PRODUCT_AREA_PATTERNS = _compile_rules(_PRODUCT_AREA_RULES)
_SENTIMENT_PATTERNS = _compile_rules(_SENTIMENT_RULES)


def _pick(text: str, rules: _Rules, default: str) -> str:
    for label, pattern in rules:
        if pattern.search(text):
            return label
    return default


def ticket_text(prompt: str) -> str:
    """The ticket portion of a classifier prompt, lowercased.

    Everything before the `User:` marker is instruction text (including the
    enum vocabularies) and must never be matched against.
    """
    return prompt.partition(_USER_MARKER)[2].lower()


def classifier_responder(prompt: str) -> str:
    """Canned classification JSON, keyed off signal words in the ticket text."""
    text = ticket_text(prompt)
    return json.dumps(
        {
            "intent": _pick(text, _INTENT_PATTERNS, _INTENT_DEFAULT),
            "priority": _pick(text, _PRIORITY_PATTERNS, _PRIORITY_DEFAULT),
            "product_area": _pick(text, _PRODUCT_AREA_PATTERNS, _PRODUCT_AREA_DEFAULT),
            "sentiment": _pick(text, _SENTIMENT_PATTERNS, _SENTIMENT_DEFAULT),
        }
    )


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #

_NO_ANSWER = "I don't have enough grounded information to answer that confidently."


def resolver_responder(prompt: str) -> str:
    """A grounded answer assembled from *every* retrieved passage.

    `spine.reference_agent.default_responder` answers from the first context
    line only, because its demo corpus is one sentence per document. Here a
    passage is a ~1000-character KB chunk and `Resolution.citations` names all
    `config.RETRIEVAL_TOP_K` of them, so answering from the first alone would
    cite three documents the answer never drew on. Reading the whole context
    block is also what a real model does with it.
    """
    context = prompt.partition(CONTEXT_MARKER)[2].partition(USER_MARKER)[0].strip()
    if not context:
        return _NO_ANSWER
    # Each line is "- <doc_id>: <chunk text>"; the first ": " is the separator.
    bodies = [line.lstrip("- ").partition(": ")[2].strip() for line in context.splitlines()]
    bodies = [b for b in bodies if b]
    if not bodies:
        return _NO_ANSWER
    return "Based on our documentation: " + " ".join(bodies)


# --------------------------------------------------------------------------- #
# Resolution judge
# --------------------------------------------------------------------------- #

_JUDGE_REFERENCE_MARKER = "Reference / expected:"
_JUDGE_ANSWER_MARKER = "Agent answer:"
# `spine.eval.metrics.DEFAULT_JUDGE_TEMPLATE` puts its own closing instructions
# after the answer; they are template text, not the agent's words.
_JUDGE_INSTRUCTION_MARKER = "Reply with a JSON object"


def resolution_judge_client() -> FakeModelClient:
    """Deterministic stand-in for the real judge (a real one is Phase 8).

    Same canned-JSON contract as `spine.eval.example.demo_judge_client`, but
    graded instead of all-or-nothing: it scores the share of the reference
    answer's content words that the agent's answer actually contains. That asks
    the question the resolver is on the hook for — did retrieval put the facts a
    correct answer needs in front of the model — and a partially-right answer
    scores between an exact one and an unrelated one.
    """

    def respond(prompt: str) -> str:
        head, _, tail = prompt.partition(_JUDGE_ANSWER_MARKER)
        reference = head.partition(_JUDGE_REFERENCE_MARKER)[2]
        answer = tail.partition(_JUDGE_INSTRUCTION_MARKER)[0].lower()
        terms = content_terms(reference)
        if not terms:
            return json.dumps({"score": 0.0, "reason": "no reference answer to judge against"})
        hits = sum(1 for term in terms if term in answer)
        return json.dumps(
            {
                "score": round(hits / len(terms), 3),
                "reason": f"{hits}/{len(terms)} reference terms present in the answer",
            }
        )

    return FakeModelClient(responder=respond)
