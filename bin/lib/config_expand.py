from typing import Any, MutableMapping

import jinja2

MAX_ITERS = 5

JINJA_ENV = jinja2.Environment()


def is_list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


# dear god it's late and this can't really be sensible, right?
def is_list_of_strings_or_lists(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) or is_list_of_strings_or_lists(x) for x in value)


def is_value_type(value: Any) -> bool:
    return isinstance(value, str) \
           or isinstance(value, bool) \
           or isinstance(value, float) \
           or isinstance(value, int) \
           or is_list_of_strings(value) \
           or is_list_of_strings_or_lists(value)


def needs_expansion(target):
    for value in target.values():
        if is_list_of_strings(value):
            for v in value:
                if '{' in v:
                    return True
        elif isinstance(value, str):
            if '{' in value:
                return True
    return False


def expand_one(template_string, configuration):
    jinjad = JINJA_ENV.from_string(template_string).render(**configuration)
    return jinjad.format(**configuration)


def expand_target(target: MutableMapping[str, Any], context):
    iterations = 0
    while needs_expansion(target):
        iterations += 1
        if iterations > MAX_ITERS:
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
