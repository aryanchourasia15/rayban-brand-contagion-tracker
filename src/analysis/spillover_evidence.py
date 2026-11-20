"""Opt-in evidence rule for direct, qualified core-brand distrust; not a classifier."""
import re

VERSION = 'context-evidence-2.0'


def explicit_core_support(quotes):
    """Require core scope, negative trust/avoidance and a controversy link together.

    Supports 'privacy concerns keep me from wanting regular eyewear' and qualified
    distrust, without inferring damage from product criticism or core-brand praise.
    Exact quote membership/type checks remain the caller's responsibility.
    """
    for original in quotes:
        text = original.lower().replace('\u2019', "'").replace('\u2011', '-')
        text = re.sub(r'ray[ -]?ban\s+(?:meta|stories)', '<product>', text)
        units = re.split(r'[.!?;\n]|\b(?:but|however|although|yet)\b', text)
        for unit in units:
            controversy = re.search(r'privacy|recording|surveillance|smart[ -]glasses|camera|\bmeta\b|<product>', unit)
            cause = re.search(r'because|due to|after|since|makes? me|made me|keep(?:s)? me from|spill(?:s)? over', unit)
            if not controversy or not cause:
                continue
            if re.search(r"(?:don't|do not|not|never)\s+(?:distrust|avoid|boycott|stop buying)", unit):
                continue
            core = r'(?:traditional|ordinary|regular|classic)\s+(?:ray[ -]?ban(?:s)?|frames|sunglasses|eyewear)|(?:whole|entire|wider) brand|all (?:their|ray[ -]?ban) products'
            if not re.search(core, unit):
                continue
            # Anchor the adverse predicate to core eyewear, not a nearby product name.
            doubts = re.search(r"(?:not sure|wonder if|wonder whether|doubt).{0,85}\btrust\b.{0,65}(?:" + core + r')', unit)
            avoidance = re.search(r"(?:don't trust|do not trust|distrust|won't buy|will not buy|avoid|boycott|not wanting|from wanting to wear).{0,55}(?:" + core + r')', unit)
            if doubts or avoidance:
                match = doubts or avoidance
                if '<product>' not in match.group():
                    return True
    return False
