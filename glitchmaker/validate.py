"""Config validation for glitchmaker.

Collects all errors (blocking) and warnings (unknown keys, exit 0).
Invalid types/ranges -> errors; extra keys -> warnings -> stderr plain.
"""

import re

from .effects import EFFECTS

_ALLOWED_TOP = {"input", "output_dir", "fps", "gif_length", "seed", "overlap", "effects"}
_ALLOWED_ENTRY = {"effect", "params", "start", "end", "ramp"}
_ALLOWED_RAMPS = {"constant", "ascend", "descend", "peak"}
_ALLOWED_OVERLAP = {"stack", "average"}

# ponytail: explicit allowlist, add entry when new effect added
_ALLOWED_PARAMS = {
    "rgbShift": {"rgbRedX", "rgbRedY", "rgbGreenX", "rgbGreenY", "rgbBlueX", "rgbBlueY"},
    "noise": {"amount", "scale"},
    "scanLines": {"lines", "opacity"},
    "interference": {"amount", "color"},
    "hShake": {"amount"},
    "vShake": {"amount"},
    "blockDistort": {"amount", "blockSize"},
    "waveDistort": {"amount", "waveFreq"},
    "pixelSort": {"amount"},
    "dataMosaic": {"amount"},
    "contrast": {"amount"},
    "brightness": {"amount"},
    "saturation": {"amount"},
    "grayscale": {"amount"},
    "sepia": {"amount"},
    "vintage": {"amount"},
    "invert": {"invert"},
    "colorShift": {"amount"},
    "chromaticAberration": {"amount"},
    "edgeCorruption": {"amount"},
    "digitalRain": {"amount"},
    "compressionArtifacts": {"amount"},
    "channelShift": {"amount"},
    "bufferOverflow": {"amount"},
}

_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _is_number(v):
    """Check if v is int/float but not bool."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(config):
    """Validate config dict. Returns (errors, warnings) each list of {field, message}."""
    errors = []
    warnings = []

    if not isinstance(config, dict):
        errors.append({"field": "$", "message": f"config must be an object, got {type(config).__name__}"})
        return errors, warnings

    # unknown top-level keys -> warn
    for k in config:
        if k not in _ALLOWED_TOP:
            warnings.append({"field": k, "message": f"unknown field '{k}'"})

    # required top-level
    for field in ("input", "output_dir", "fps", "gif_length", "seed", "overlap", "effects"):
        if field not in config:
            errors.append({"field": field, "message": f"missing required field '{field}'"})

    # input
    if "input" in config:
        if not isinstance(config["input"], str) or not config["input"].strip():
            errors.append({"field": "input", "message": f"expected non-empty string, got {config['input']!r}"})

    # output_dir
    if "output_dir" in config and not isinstance(config["output_dir"], str):
        errors.append({"field": "output_dir", "message": f"expected string, got {type(config['output_dir']).__name__}"})

    # fps
    if "fps" in config:
        v = config["fps"]
        if not isinstance(v, int) or isinstance(v, bool):
            errors.append({"field": "fps", "message": f"expected integer, got {v!r}"})
        elif v <= 0:
            errors.append({"field": "fps", "message": f"expected positive integer, got {v!r}"})

    # gif_length
    if "gif_length" in config:
        v = config["gif_length"]
        if not _is_number(v):
            errors.append({"field": "gif_length", "message": f"expected number, got {v!r}"})
        elif v <= 0:
            errors.append({"field": "gif_length", "message": f"expected positive number, got {v!r}"})

    # seed - required, int, not null
    if "seed" in config:
        v = config["seed"]
        if not isinstance(v, int) or isinstance(v, bool):
            errors.append({"field": "seed", "message": f"expected integer, got {v!r}"})

    # overlap
    if "overlap" in config:
        v = config["overlap"]
        if not isinstance(v, str) or v not in _ALLOWED_OVERLAP:
            errors.append({"field": "overlap", "message": f"must be 'stack' or 'average', got {v!r}"})


    # effects
    if "effects" in config:
        v = config["effects"]
        if not isinstance(v, list):
            errors.append({"field": "effects", "message": f"expected array, got {type(v).__name__}"})
        else:
            for i, entry in enumerate(v):
                base = f"effects[{i}]"
                if not isinstance(entry, dict):
                    errors.append({"field": base, "message": f"expected object, got {type(entry).__name__}"})
                    continue
                # unknown entry keys -> warn
                for k in entry:
                    if k not in _ALLOWED_ENTRY:
                        warnings.append({"field": f"{base}.{k}", "message": f"unknown field '{k}'"})
                # effect
                if "effect" not in entry:
                    errors.append({"field": f"{base}.effect", "message": "missing required field 'effect'"})
                else:
                    ev = entry["effect"]
                    if not isinstance(ev, str):
                        errors.append({"field": f"{base}.effect", "message": f"expected string, got {ev!r}"})
                    elif ev not in EFFECTS:
                        warnings.append({"field": f"{base}.effect", "message": f"unknown effect '{ev}', expected one of {', '.join(sorted(EFFECTS))}"})
                # params - required per entry if effect present, and all allowed params required
                eff_name = entry.get("effect") if isinstance(entry.get("effect"), str) and entry.get("effect") in EFFECTS else None
                if "params" not in entry:
                    if eff_name is not None:
                        errors.append({"field": f"{base}.params", "message": "missing required field 'params'"})
                else:
                    pv = entry["params"]
                    if not isinstance(pv, dict):
                        errors.append({"field": f"{base}.params", "message": f"expected object, got {type(pv).__name__}"})
                    else:
                        allowed = _ALLOWED_PARAMS.get(eff_name) if eff_name else None
                        if allowed is not None:
                            for req in sorted(allowed):
                                if req not in pv:
                                    errors.append({"field": f"{base}.params.{req}", "message": f"missing required field '{req}' for effect '{eff_name}'"})
                        for pk, pv_val in pv.items():
                            if allowed is not None and pk not in allowed:
                                errors.append({"field": f"{base}.params.{pk}", "message": f"unknown param '{pk}' for effect '{eff_name}'"})
                            # type checks
                            if pk == "color":
                                if not isinstance(pv_val, str) or not _HEX_RE.match(pv_val):
                                    errors.append({"field": f"{base}.params.{pk}", "message": f"expected hex color like '#ff00ff', got {pv_val!r}"})
                            elif pk == "invert":
                                if not isinstance(pv_val, bool):
                                    errors.append({"field": f"{base}.params.{pk}", "message": f"expected boolean, got {pv_val!r}"})
                            else:
                                if not _is_number(pv_val):
                                    errors.append({"field": f"{base}.params.{pk}", "message": f"expected number, got {pv_val!r}"})
                # start - required
                if "start" not in entry:
                    errors.append({"field": f"{base}.start", "message": "missing required field 'start'"})
                else:
                    sv = entry["start"]
                    if not _is_number(sv):
                        errors.append({"field": f"{base}.start", "message": f"expected number, got {sv!r}"})
                    elif sv < 0:
                        errors.append({"field": f"{base}.start", "message": f"expected >= 0, got {sv!r}"})
                # end - required
                if "end" not in entry:
                    errors.append({"field": f"{base}.end", "message": "missing required field 'end'"})
                else:
                    ev = entry["end"]
                    if not _is_number(ev):
                        errors.append({"field": f"{base}.end", "message": f"expected number, got {ev!r}"})
                    elif ev < 0:
                        errors.append({"field": f"{base}.end", "message": f"expected >= 0, got {ev!r}"})
                # start < end if both numbers
                if "start" in entry and "end" in entry and _is_number(entry["start"]) and _is_number(entry["end"]):
                    if entry["start"] >= entry["end"]:
                        errors.append({"field": base, "message": f"'start' ({entry['start']}) must be < 'end' ({entry['end']})"})
                # ramp - required, only 4 string values
                if "ramp" not in entry:
                    errors.append({"field": f"{base}.ramp", "message": "missing required field 'ramp'"})
                else:
                    rv = entry["ramp"]
                    if not isinstance(rv, str) or rv not in _ALLOWED_RAMPS:
                        errors.append({"field": f"{base}.ramp", "message": f"must be one of 'constant', 'ascend', 'descend', 'peak', got {rv!r}"})

    return errors, warnings
