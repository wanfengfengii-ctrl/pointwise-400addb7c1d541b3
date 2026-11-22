REPAIR_CHOICES = ('none', 'A', 'B', 'AB')


def rule_applies(rule: dict, enabled_devices: frozenset[str], choice: str) -> bool:
    return choice in rule['choices'] and enabled_devices.issuperset(rule['requires'])
