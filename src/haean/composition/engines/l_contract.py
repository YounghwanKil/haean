"""Explicit-input boundary shared by the LEET and verbal algorithm ports."""

from copy import deepcopy


class EngineContract:
    """Keep profile data and results independent, including concurrent profiles.

    The numerical checks are composition checks, not expert or originality review.
    The private algorithm methods retain the upstream error/warning distinction.
    """

    track: str
    supported_sizes: tuple[int, ...]
    sample_options: frozenset[str]

    def __init__(
        self, *, format_rules: dict, content_rules: dict, content_config: dict,
        rules_config: dict | None = None, labels: dict | None = None,
    ):
        supplied = {
            "format_rules": format_rules,
            "content_rules": content_rules,
            "content_config": content_config,
            "rules_config": {} if rules_config is None else rules_config,
            "labels": {} if labels is None else labels,
        }
        for name, value in supplied.items():
            if not isinstance(value, dict):
                raise ValueError(f"{self.track}: {name} must be an explicitly loaded dictionary")
            setattr(self, name, deepcopy(value))
        self.RULES = self.format_rules
        self.CR = self.content_rules
        self.CC = self.content_config
        try:
            self._init_format()
            self._init_content()
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            raise ValueError(f"{self.track}: invalid profile structure: {exc}") from exc

    def _option_errors(self, options: dict) -> list[str]:
        unknown = set(options) - self.sample_options
        return [f"{self.track}: unsupported options: {', '.join(sorted(unknown))}"] if unknown else []

    def sample(self, seed=0, **options) -> dict:
        errors = self._option_errors(options)
        if errors:
            raise ValueError('; '.join(errors))
        if "size" in options and options["size"] not in self.supported_sizes:
            raise ValueError(f"{self.track}: supported sizes are {self.supported_sizes}")
        if "variant" in options and options["variant"] not in (None, "mix"):
            raise ValueError(f"{self.track}: unsupported variant {options['variant']!r}")
        try:
            return deepcopy(self._f_sample(seed=seed, **options))
        except (KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
            raise ValueError(f"{self.track}: format rules cannot produce a design: {exc}") from exc

    def validate_report(self, design, **options) -> dict:
        """Return errors and upstream warnings without mutating the design."""
        errors = self._option_errors(options)
        if not isinstance(design, dict) or not isinstance(design.get("slots"), list):
            return {"errors": errors + ["format design must contain a slots list"], "warnings": [], "infos": []}
        slots = design["slots"]
        if len(slots) not in self.supported_sizes:
            errors.append(f"{self.track}: {len(slots)} slots; supported sizes are {self.supported_sizes}")
        if any(not isinstance(slot, dict) for slot in slots):
            errors.append("format slots must be dictionaries")
        else:
            numbers = [slot.get("slot") for slot in slots]
            if any(type(number) is not int for number in numbers) or numbers != list(range(1, len(slots) + 1)):
                errors.append("format slot numbers must be ordered 1..N, without omissions or duplicates")
            if options.get("size") is not None and options["size"] != len(slots):
                errors.append("format size does not match the requested size")
            for slot in slots:
                try:
                    expected_code = self._f_type_code(slot["area"], slot["type"], slot["principle"])
                    if slot.get("type_code") != expected_code:
                        errors.append(f"slot {slot.get('slot')}: type_code does not match area/type/principle")
                    if type(slot.get("answer")) is not int or slot["answer"] not in range(1, 6):
                        errors.append(f"slot {slot.get('slot')}: answer must be an integer from 1 to 5")
                    if self.track == "psat_verbal" and slot.get("set") is not (slot["slot"] in self.SET_OF):
                        errors.append(f"slot {slot.get('slot')}: set membership does not match the profile")
                except (KeyError, TypeError, ValueError):
                    errors.append(f"slot {slot.get('slot')}: missing or unknown area/type/principle")
        if errors:
            return {"errors": errors, "warnings": [], "infos": []}
        try:
            upstream_errors, warnings = self._f_validate(deepcopy(design))
            return {"errors": list(upstream_errors), "warnings": list(warnings), "infos": []}
        except (KeyError, TypeError, IndexError, ValueError, ZeroDivisionError) as exc:
            return {"errors": [f"{self.track}: invalid format design or rule profile: {exc}"], "warnings": [], "infos": []}

    def validate(self, design, **options) -> list[str]:
        return self.validate_report(design, **options)["errors"]

    def _validate_content_references(self):
        materials = self.CR.get("m20_materials")
        if not isinstance(materials, list) or not materials:
            raise ValueError(f"{self.track}: content_rules.m20_materials is empty or malformed")
        ids = []
        for material in materials:
            if not isinstance(material, dict) or not isinstance(material.get("id"), str) or not material["id"].strip():
                raise ValueError(f"{self.track}: content material reference ID is missing")
            ids.append(material["id"])
        known = set(ids)
        if len(ids) != len(known):
            raise ValueError(f"{self.track}: duplicate content material reference IDs")
        cells = self.CR.get("cells")
        if not isinstance(cells, dict):
            raise ValueError(f"{self.track}: content_rules.cells must be a dictionary")
        for cell, stats in cells.items():
            if not isinstance(stats, dict):
                raise ValueError(f"{self.track}: content cell {cell!r} must be a dictionary")
            refs = stats.get("reference_pool", [])
            if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in known for ref in refs):
                raise ValueError(f"{self.track}: unresolved reference_pool in content cell {cell!r}")

    def content(self, design, ledger=None, seed=0) -> dict:
        errors = self.validate(design)
        if errors:
            raise ValueError("content blocked by format validation: " + '; '.join(errors))
        if ledger is not None and not isinstance(ledger, dict):
            raise ValueError("content ledger must be a dictionary or None")
        self._validate_content_references()
        try:
            result = self._c_design_set(deepcopy(design), ledger=deepcopy(ledger), seed=seed)
        except (KeyError, TypeError, IndexError, ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{self.track}: content rules cannot produce a complete design: {exc}") from exc
        actual = result.get("슬롯")
        expected = [(slot["slot"], slot["type_code"]) for slot in design["slots"]]
        if not isinstance(actual, list) or [(slot.get("slot"), slot.get("type_code")) for slot in actual] != expected:
            raise ValueError(f"{self.track}: content slots do not match the validated format slots")
        return deepcopy(result)
