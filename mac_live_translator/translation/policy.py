"""Meeting translation policies: glossary, filler detection, and boundary safety."""

from __future__ import annotations

from mac_live_translator.asr.stability import key

IT_GLOSSARY = (
    "Keep IT/business terms exact: GTM, PMM, Slack, GitLab, GitOps, CI/CD, KubeCon, "
    "re:Invent, Google Next, campaign manager, sync, issue, deployment, rollback."
)

UNSAFE_ENDINGS = {
    # Articles, prepositions, conjunctions
    "a", "an", "the", "and", "or", "but", "nor", "at", "by", "for", "from",
    "in", "into", "of", "on", "to", "with", "without", "than", "as", "if",
    "that", "which", "who", "whom", "whose", "while", "because", "so",
    # Negation and contractions
    "not", "no", "never", "don't", "didn't", "doesn't", "won't", "can't",
    "couldn't", "shouldn't", "wouldn't", "isn't", "aren't", "wasn't", "weren't",
    # Phrasal verb heads
    "roll", "cut", "sign", "shut", "scale", "spin", "set", "log", "fall",
    "carry", "bring", "point", "pick", "check", "break", "turn", "give", "take",
}

PHRASAL_HEADS = {
    "roll", "cut", "sign", "shut", "scale", "spin", "set", "log", "fall",
    "carry", "bring", "point", "pick", "check", "break", "turn", "give", "take",
}

PHRASAL_PARTICLES = {
    "back", "over", "off", "down", "up", "in", "out", "on", "away", "through", "about"
}

NEGATIONS = {
    "not", "no", "never", "cannot", "hardly", "barely", "don't", "didn't",
    "doesn't", "won't", "can't", "couldn't", "shouldn't", "wouldn't",
    "isn't", "aren't", "wasn't", "weren't"
}

SUBORDINATING = {
    "because", "although", "since", "unless", "if", "whether", "while",
    "whereas", "until", "before", "after", "as"
}

FILLER_WORDS = {
    "um", "uh", "uh-huh", "mhm", "ah", "er", "like", "you know",
    "yeah", "yep", "yes", "okay", "right", "so", "well",
}


def is_filler(words: list[str]) -> bool:
    """Identify short conversational speech consisting only of fillers."""
    if not words or len(words) > 3:
        return False
    return all(key(w) in FILLER_WORDS for w in words)


def is_risky_boundary(left_words: list[str], right_words: list[str]) -> bool:
    """Detect genuine syntactic boundaries prone to distorted Vietnamese translations."""
    if not left_words or not right_words:
        return False
    left_last = left_words[-1]
    right_first = right_words[0]
    if left_last.endswith((".", "?", "!")):
        return False
    if left_last.endswith((";", ":")):
        return False
    left_k = key(left_last)
    right_k = key(right_first)
    if left_k in UNSAFE_ENDINGS:
        return True
    if left_k in PHRASAL_HEADS and right_k in PHRASAL_PARTICLES:
        return True
    if left_k in NEGATIONS or right_k in NEGATIONS:
        return True
    if right_k in SUBORDINATING:
        return True
    if left_k.isdigit() or right_k.isdigit() or left_last.endswith("%") or right_first.startswith("$"):
        return True
    return False

