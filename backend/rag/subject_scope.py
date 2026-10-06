"""Distinguish conditional subjects supplied by the user from identity claims."""

import re


def conditional_subjects(text):
    # Only an explicitly hypothetical/prepositional subject. Mentioning a name
    # anywhere in a question does not establish its identity or configuration.
    return set(
        re.findall(r"\b(?i:for|given|on|with)\s+(?:(?i:a|an|the)\s+)?([A-Z][A-Za-z0-9_]*)\b", text)
    )


def contextual_subjects(sentence, question):
    supplied = conditional_subjects(question)
    return {
        name
        for name in conditional_subjects(sentence)
        if name in supplied or (name.endswith("s") and name[:-1] in supplied)
    }
