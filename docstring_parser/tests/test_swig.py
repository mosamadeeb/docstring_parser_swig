"""Tests for Swig autodoc docstring routines."""

from docstring_parser.common import (
    DocstringParam, DocstringReturns, DocstringExample
)
from docstring_parser.swig import (
    SwigParser,
)


def test_simple_function():
    parser = SwigParser()
    docstring = parser.parse("average(IntVector v) -> double")
    assert len(docstring.meta) == 3  # return, param, example
    ret = docstring.meta[0]
    assert isinstance(ret, DocstringReturns)
    assert ret.type_name == "double"
    param = docstring.meta[1]
    assert isinstance(param, DocstringParam)
    assert param.arg_name == "v"
    assert param.type_name.replace(' ', '') == "IntVector"
    assert param.default is None
    ex = docstring.meta[2]
    assert isinstance(ex, DocstringExample)
    assert ex.snippet == "average(IntVector v) -> double"


def test_function_with_defaults():
    parser = SwigParser()
    docstring = parser.parse("function_name(int x, int y, Foo foo=None, Bar bar=None) -> bool")
    params = [m for m in docstring.meta if isinstance(m, DocstringParam)]
    assert len(params) == 4
    assert params[2].arg_name == "foo"
    assert params[2].type_name.replace(' ', '') == "Foo"
    assert params[2].default == "None"
    assert params[2].is_optional
    assert params[3].arg_name == "bar"
    assert params[3].type_name.replace(' ', '') == "Bar"
    assert params[3].default == "None"
    assert params[3].is_optional
    ret = [m for m in docstring.meta if isinstance(m, DocstringReturns)][0]
    assert ret.type_name == "bool"


def test_cpp_types():
    parser = SwigParser()
    docstring = parser.parse("insert(DoubleVector self, std::vector< double >::iterator pos, std::vector< double >::value_type const & x) -> std::vector< double >::iterator")
    params = [m for m in docstring.meta if isinstance(m, DocstringParam)]
    assert params[0].arg_name == "self"
    assert params[0].type_name.replace(' ', '') == "DoubleVector"
    assert params[1].arg_name == "pos"
    assert params[1].type_name.replace(' ', '') == "std::vector<double>::iterator"
    assert params[2].arg_name == "x"
    assert params[2].type_name.replace(' ', '') == "std::vector<double>::value_typeconst&"
    ret = [m for m in docstring.meta if isinstance(m, DocstringReturns)][0]
    assert ret.type_name == "std::vector<double>::iterator"


def test_overloads():
    parser = SwigParser()
    docstring = parser.parse("""__init__(DoubleVector self) -> DoubleVector\n__init__(DoubleVector self, DoubleVector other) -> DoubleVector\n__init__(DoubleVector self, std::vector< double >::size_type size) -> DoubleVector\n__init__(DoubleVector self, std::vector< double >::size_type size, std::vector< double >::value_type const & value) -> DoubleVector""")
    # There should be 4 overloads, each with their own params/returns/example
    assert sum(1 for m in docstring.meta if isinstance(m, DocstringExample)) == 4
    assert sum(1 for m in docstring.meta if isinstance(m, DocstringReturns)) == 4
    # Check the last overload's last param
    params = [m for m in docstring.meta if isinstance(m, DocstringParam)]
    assert params[-1].arg_name == "value"
    assert params[-1].type_name.replace(' ', '') == "std::vector<double>::value_typeconst&"
    assert params[-1].default is None


def test_no_params():
    parser = SwigParser()
    docstring = parser.parse("func()")
    assert docstring.short_description is None
    assert docstring.long_description is None
    assert len(docstring.meta) == 1  # Only example
    assert isinstance(docstring.meta[0], DocstringExample)
    assert docstring.meta[0].snippet == "func()"


def test_template_type_with_commas():
    parser = SwigParser()
    docstring = parser.parse("__setitem__(StringStringMap self, std::map< std::string,std::string >::key_type const & key, std::map< std::string,std::string >::mapped_type const & x)")
    params = [m for m in docstring.meta if isinstance(m, DocstringParam)]
    assert len(params) == 3
    assert params[0].arg_name == "self"
    assert params[0].type_name.replace(' ', '') == "StringStringMap"
    assert params[1].arg_name == "key"
    assert params[1].type_name.replace(' ', '') == "std::map<std::string,std::string>::key_typeconst&"
    assert params[2].arg_name == "x"
    assert params[2].type_name.replace(' ', '') == "std::map<std::string,std::string>::mapped_typeconst&"
