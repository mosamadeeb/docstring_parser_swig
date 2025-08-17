"""Swig autodoc docstring parsing."""

import inspect
import re
import typing as T

from .common import (
    Docstring,
    DocstringExample,
    DocstringParam,
    DocstringReturns,
    DocstringStyle,
)


SWIG_FUNC_SIG_RE = re.compile(r"^(?P<func_name>\w+)\((?P<params>.*?)\)\s*(?:->\s*(?P<return_type>.+))?$")
SWIG_FUNC_PARAM_RE = re.compile(r"\s*(?P<type>.+?)\s+(?P<name>\w+)(?:\s*=\s*(?P<default>.+))?\s*$")

class SwigParser:
    """Parser for Swig autodoc docstrings."""

    def __init__(
        self
    ):
        pass

    def parse(self, text: T.Optional[str]) -> Docstring:
        """Parse the Swig autodoc docstring into its components.

        :returns: parsed docstring
        """
        ret = Docstring(style=DocstringStyle.SWIG)
        if not text:
            return ret

        # Clean according to PEP-0257
        text = inspect.cleandoc(text)

        # Split into lines. Each line is an overload
        overloads = text.splitlines()
        for i, overload in enumerate(overloads):
            overload = overload.strip()
            if not overload:
                continue

            match = SWIG_FUNC_SIG_RE.match(overload)
            if match:
                func_name, params, return_type = match.groups()

                if return_type:
                    # Add return value
                    ret.meta.append(DocstringReturns(
                        args=[func_name, i],
                        description=None,
                        type_name=return_type.strip().replace(' ', ''),
                        is_generator=False,
                    ))

                def split_params(param_str):
                    params = []
                    current = []
                    depth = 0
                    for c in param_str:
                        if c == '<':
                            depth += 1
                        elif c == '>':
                            depth -= 1
                        elif c == ',' and depth == 0:
                            params.append(''.join(current))
                            current = []
                            continue
                        current.append(c)
                    if current:
                        params.append(''.join(current))
                    return params

                for param in split_params(params):
                    param = param.strip()
                    if not param:
                        continue
                    param_match = SWIG_FUNC_PARAM_RE.match(param)
                    if not param_match:
                        continue
                    param_type = param_match.group("type").strip().replace(' ', '')
                    param_name = param_match.group("name").strip()
                    param_default = param_match.group("default")

                    has_default = bool(param_default)

                    # Add param
                    ret.meta.append(DocstringParam(
                        args=[func_name, i, param_name],
                        description=None,
                        arg_name=param_name,
                        type_name=param_type,
                        is_optional=has_default,
                        default=param_default.strip() if has_default else None,
                    ))

                # Add example
                ret.meta.append(DocstringExample(
                    args=[func_name, i],
                    snippet=overload,
                    description=None,
                ))

        # No descriptions in this format
        ret.short_description = None
        ret.long_description = None
        ret.blank_after_short_description = False
        ret.blank_after_long_description = False

        return ret


def parse(text: T.Optional[str]) -> Docstring:
    """Parse the Swig autodoc docstring into its components.

    :returns: parsed docstring
    """
    return SwigParser().parse(text)
