#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "docstring_parser_swig>=0.0.1",
# ]
# ///

__author__ = "mosamadeeb"
__license__ = "MIT"
__version__ = "1.0.3"

import importlib
import importlib.util
import inspect
import os
import sys
import re
from contextlib import redirect_stdout
from io import StringIO

from docstring_parser import DocstringStyle, parse

# Types that should be translated to Python types
type_map = {
    "int": "int",
    "long": "int",
    "unsignedlong": "int",
    "short": "int",
    "double": "float",
    "float": "float",
    "bool": "bool",
    "std_string": "str",
    "std_string_ref": "str",
    "std_string_const_ref": "str",
}

# Types that should only be replaced for the output (because Swig will convert them to native types)
type_map_native = dict()

# Types to add to the top of the file (set to a dummy value)
type_set = set()


def clean_type_name(type_name: str) -> str:
    cleaned = (
        type_name.replace("<", "__")
        .replace(">", "__")
        .replace(",", "__")
        .replace("const", "_const")
        .replace("*", "_ptr")
        .replace("&", "_ref")
        .replace("::", "_")
    )
    type_set.add(cleaned)

    if cleaned not in type_map and cleaned.startswith("std_vector__"):
        # example: std_vector__int__size_type
        value_type = cleaned.split("__")[1]
        type_map[f"std_vector__{value_type}___size_type"] = "int"
        type_map[f"std_vector__{value_type}___difference_type"] = "int"

        translated_type = type_map.get(value_type, value_type)
        type_map[f"std_vector__{value_type}___value_type"] = translated_type
        type_map[f"std_vector__{value_type}___value_type_ref"] = translated_type
        type_map[f"std_vector__{value_type}___value_type_const_ref"] = translated_type

        type_map[f"std_vector__{value_type}___iterator"] = "SwigPyIterator"
        type_map[f"std_vector__{value_type}___reverse_iterator"] = "SwigPyIterator"

        type_map[cleaned] = f"list[{translated_type}]"

    if cleaned not in type_map and cleaned.startswith("std_map__"):
        # example: std_map__std_string__std_string__size_type
        key_type = cleaned.split("__")[1]
        mapped_type = cleaned.split("__")[2]
        type_map[f"std_map__{key_type}__{mapped_type}___size_type"] = "int"

        translated_key_type = type_map.get(key_type, key_type)
        type_map[f"std_map__{key_type}__{mapped_type}___key_type"] = translated_key_type
        type_map[f"std_map__{key_type}__{mapped_type}___key_type_ref"] = translated_key_type
        type_map[f"std_map__{key_type}__{mapped_type}___key_type_const_ref"] = translated_key_type

        translated_mapped_type = type_map.get(mapped_type, mapped_type)
        type_map[f"std_map__{key_type}__{mapped_type}___mapped_type"] = translated_mapped_type
        type_map[f"std_map__{key_type}__{mapped_type}___mapped_type_ref"] = translated_mapped_type
        type_map[f"std_map__{key_type}__{mapped_type}___mapped_type_const_ref"] = translated_mapped_type

        type_map[f"std_map__{key_type}__{mapped_type}___iterator"] = "SwigPyIterator"
        type_map[f"std_map__{key_type}__{mapped_type}___reverse_iterator"] = "SwigPyIterator"
        type_map[f"std_map__{key_type}__{mapped_type}___mapped_type_const_ref"] = translated_mapped_type

        type_map[cleaned] = f"dict[{translated_key_type}, {translated_mapped_type}]"

    return type_map.get(cleaned, cleaned)


def clean_param_type_name(type_name: str) -> str:
    cleaned = clean_type_name(type_name)
    # Allow native types when typemaps are used
    return f'{cleaned} | {type_map_native[cleaned]}' if cleaned in type_map_native else cleaned


def clean_return_type_name(type_name: str) -> str:
    cleaned = clean_type_name(type_name)
    return type_map_native.get(cleaned, cleaned)


def extract_cpp_type(class_name, cpp_type):
    cpp_type = cpp_type.replace(' ', '')
    cleaned = clean_type_name(cpp_type)

    # Update the output type map so that we show the correct return type
    # This is needed because Swig will return the python native object
    # https://www.swig.org/Doc4.2/Library.html#Library_std_vector
    if cleaned.startswith('list') or cleaned.startswith('dict'):
        type_map_native[class_name] = cleaned


def gen_function(func, is_method=False):
    doc = parse(func.__doc__)
    indent = "    " if is_method else ""

    if func.__doc__ == "" or len(doc.meta) == 0:
        # No docs found, use inspect to get signature and type hints
        try:
            sig = inspect.signature(func)

            param_strs = []
            for name, param in sig.parameters.items():
                if param.annotation is not inspect.Parameter.empty:
                    type_name = (
                        param.annotation.__name__ if hasattr(param.annotation, "__name__") else str(param.annotation)
                    )
                else:
                    type_name = "Any"
                param_strs.append(name if name == "self" else f"{name}: {type_name}")
            if sig.return_annotation is not inspect.Signature.empty:
                ret_type = (
                    sig.return_annotation.__name__
                    if hasattr(sig.return_annotation, "__name__")
                    else str(sig.return_annotation)
                )
            else:
                ret_type = "Any"

            param_str = ", ".join(param_strs)
            print(f"{indent}def {func.__name__}({param_str}) -> {ret_type}:")
            print(f"{indent}    ...")
            print()
            return
        except ValueError:
            # Should log something here, but printing something will add it to the output file
            pass

    # Remove self from params
    params = doc.params
    if is_method:
        params = [p for p in params if p.arg_name != "self"]

    if doc.style == DocstringStyle.SWIG:
        # Collect overloads: map overload_index -> {'params': [...], 'return': ...}
        overloads = {}
        for example in doc.examples:
            overload_index = example.args[1]
            overload_params = [param for param in params if param.args[1] == overload_index]
            overload_return = doc.returns if (doc.returns and doc.returns.args[1] == overload_index) else None
            overloads[overload_index] = {"params": overload_params, "return": overload_return}

        # Now, we want to check each overloads params, and if it has the same name and type, then merge the duplicates (keep 1 only)
        # Otherwise, we will add the new types as optional by adding a bar (|) between the type names when printing
        if overloads:
            # Assume all overloads have the same number of params, align by position
            param_lists = [v["params"] for v in overloads.values()]
            num_params = max(len(params) for params in param_lists)
            merged_params = []
            for i in range(num_params):
                names = set()
                types = set()
                for params in param_lists:
                    if i < len(params):
                        names.add(params[i].arg_name)
                        types.add(clean_param_type_name(params[i].type_name))
                if len(names) == 1 and len(types) == 1:
                    merged_params.append({"arg_name": list(names)[0], "type_name": list(types)[0]})
                else:
                    merged_params.append(
                        {
                            "arg_name": list(names)[0] if len(names) == 1 else f"param{i}",
                            "type_name": " | ".join(sorted(types)),
                        }
                    )

            # Merge return types
            return_types = set()
            for v in overloads.values():
                if v["return"]:
                    return_types.add(clean_return_type_name(v["return"].type_name))

            param_str = ", ".join((['self'] if is_method else []) + [f"{arg['arg_name']}: {arg['type_name']}" for arg in merged_params])
            ret_str = " | ".join(sorted(return_types)) if return_types else "None"

            print(f"{indent}def {func.__name__}({param_str}) -> {ret_str}:")
            if func.__doc__ and func.__doc__.strip():
                print(f'{indent}    r"""{func.__doc__}"""')
            print(f"{indent}    ...")
        else:
            # No overloads
            param_str = ", ".join((['self'] if is_method else []) + [f"{arg.arg_name}: {clean_param_type_name(arg.type_name)}" for arg in params])
            ret_str = clean_return_type_name(doc.returns.type_name) if doc.returns else "None"

            print(f"{indent}def {func.__name__}({param_str}) -> {ret_str}:")
            if func.__doc__ and func.__doc__.strip():
                print(f'{indent}    r"""{func.__doc__}"""')
            print(f"{indent}    ...")
    else:
        # This is Doxygen converted to PyDoc
        # TODO: support merged doxygen (pydoc)
        print(
            f"{indent}def {func.__name__}({', '.join((['self'] if is_method else []) + [f'{arg.arg_name}: {clean_param_type_name(arg.type_name)}' for arg in params])}) -> {clean_return_type_name(doc.returns.type_name) if doc.returns else 'None'}:"
        )
        if func.__doc__ and func.__doc__.strip():
            print(f'{indent}    r"""{func.__doc__}"""')
        print(f"{indent}    ...")

    print()


def gen_pyi(module_name, target_module, output_path=None):
    function_count = 0

    # Do an early pass over classes to populate the native typemap
    for name, obj in [(n, getattr(target_module, n)) for n in dir(target_module) if not n.startswith("_")]:
        if isinstance(obj, type):
            if obj.__doc__:
                # Check the class doc and extract the type name
                # example: "Proxy of C++ std::map< std::string,std::string > class."
                match = re.search(r"Proxy of C\+\+ (.+?) class\.", obj.__doc__)
                if match:
                    cpp_type = match.group(1)
                    extract_cpp_type(name, cpp_type)

    # Class types to NOT add as dummy values
    class_set = set()

    out = StringIO()
    with redirect_stdout(out):
        for name, obj in [(n, getattr(target_module, n)) for n in dir(target_module) if not n.startswith("_")]:
            if isinstance(obj, type):
                class_set.add(name)
                bases = ", ".join([base.__name__ for base in obj.__bases__])
                print(f"class {name}({bases}):")
                if obj.__doc__:
                    print(f'    r"""{obj.__doc__}"""')
                print('    ...\n')

                for method in obj.__dict__.values():
                    if callable(method):
                        if method.__name__ in ["_swig_repr", f"delete_{name}"]:
                            continue

                        gen_function(method, is_method=True)
                        function_count += 1
                print()
            else:
                if callable(obj):
                    gen_function(obj)
                    function_count += 1

    if output_path is None:
        output_path = f"{module_name}.pyi"

    with open(output_path, "w") as f:
        f.write("from typing import Any\n\n")
        for type_name in sorted(type_set.difference(class_set).difference(type_map.keys())):
            f.write(f"{type_name} = ...\n")
        f.write("\n")
        f.write(out.getvalue())

    return len(class_set), function_count

def main():
    help_text = f"""
Usage: {sys.argv[0]} <module_name_or_path>

Generate a .pyi stub file for a Python module using docstring for type hints. Supports type hints for Swig generated bindings.

You can provide either a module name (e.g. mymodule) or a path to a .py file (e.g. /path/to/mymodule.py).
If a file path is given, the output .pyi file will be created in the same directory as the input file.
If a module name is given, the output will be created in the current directory.
"""
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(help_text)
        sys.exit(0 if len(sys.argv) > 1 else 1)

    arg = sys.argv[1]
    output_path = None
    if arg.endswith(".py") or os.path.sep in arg:
        module_path = os.path.abspath(arg)
        module_name = os.path.splitext(os.path.basename(module_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, module_path)

        if spec is None or spec.loader is None:
            print(f"Could not load module from {module_path}")
            sys.exit(1)

        target_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = target_module
        module_dir = os.path.dirname(module_path)

        sys.path.insert(0, module_dir)
        try:
            spec.loader.exec_module(target_module)
        finally:
            sys.path.pop(0)
        output_path = os.path.join(module_dir, f"{module_name}.pyi")
    else:
        module_name = arg
        target_module = importlib.import_module(module_name)

    class_count, function_count = gen_pyi(module_name, target_module, output_path)
    print(f"Generated type hints for {class_count} classes and {function_count} functions")


if __name__ == "__main__":
    main()
