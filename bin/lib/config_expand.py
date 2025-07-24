import logging
from typing import Any, Mapping, MutableMapping

import jinja2

_MAX_ITERS = 5
_LOGGER = logging.getLogger(__name__)
_JINJA_ENV = jinja2.Environment()


def is_list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


# dear god it's late and this can't really be sensible, right?
def is_list_of_strings_or_lists(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) or is_list_of_strings_or_lists(x) for x in value)


def is_value_type(value: Any) -> bool:
    return (
        isinstance(value, str)
        or isinstance(value, bool)
        or isinstance(value, float)
        or isinstance(value, int)
        or is_list_of_strings(value)
        or is_list_of_strings_or_lists(value)
    )


def string_needs_expansion(value: str) -> bool:
    return "{%" in value or "{{" in value or "{#" in value


def needs_expansion(target: MutableMapping[str, Any]) -> bool:
    for value in target.values():
        if is_list_of_strings(value):
            if any(string_needs_expansion(v) for v in value):
                return True
        elif isinstance(value, str):
            if string_needs_expansion(value):
                return True
    return False


def expand_one(template_string: str, configuration: Mapping[str, Any]) -> str:
    try:
        return _JINJA_ENV.from_string(template_string).render(**configuration)
    except jinja2.exceptions.TemplateError:
        # in python 3.11 we would...
        # e.add_note(f"Template '{template_string}'")
        _LOGGER.warning("Failed to expand '%s'", template_string)
        raise


def expand_target(target: MutableMapping[str, Any], context: list[str]) -> MutableMapping[str, str]:
    iterations = 0
    while needs_expansion(target):
        iterations += 1
        if iterations > _MAX_ITERS:
            raise RuntimeError(f"Too many mutual references (in {'/'.join(context)})")
        for key, value in target.items():
            try:
                if is_list_of_strings(value):
                    target[key] = [expand_one(x, target) for x in value]
                elif isinstance(value, str):
                    target[key] = expand_one(value, target)
                elif isinstance(value, float):
                    target[key] = str(value)
            except KeyError as ke:
                raise RuntimeError(f"Unable to find key {ke} in {target[key]} (in {'/'.join(context)})") from ke
    return target
