# fmt: off
FORMAT_SPECS = {
    # Keywords and control flow
    "keyword": {"color": "#0000FF", "bold": True},
    "keyword.conditional": {"color": "#0000FF", "bold": True},
    "keyword.repeat": {"color": "#0000FF", "bold": True},
    "keyword.return": {"color": "#0000FF", "bold": True},
    "keyword.operator": {"color": "#0000FF", "bold": True},
    "keyword.import": {"color": "#0000FF", "bold": True},
    "keyword.exception": {"color": "#0000FF", "bold": True},

    # Functions and methods
    "function": {"color": "#795E26", "bold": True},
    "function.builtin": {"color": "#0000FF"},
    "function.method": {"color": "#008080"},
    "function.call": {"color": "#008080"},
    "method.call": {"color": "#008080"},

    # Types and classes
    "type": {"color": "#267F99", "bold": True},
    "type.builtin": {"color": "#0000FF"},
    "class": {"color": "#267F99", "bold": True},
    "constructor": {"color": "#267F99", "bold": True},

    # Variables and parameters
    "variable": {"color": "#001080"},
    "variable.builtin": {"color": "#0000FF"},
    "variable.parameter": {"color": "#001080"},
    "parameter": {"color": "#001080"},

    # Constants and literals
    "constant": {"color": "#0000FF"},
    "constant.builtin": {"color": "#0000FF"},
    "boolean": {"color": "#0000FF"},
    "number": {"color": "#098658"},
    "float": {"color": "#098658"},
    "string": {"color": "#A31515"},
    "string.escape": {"color": "#EE9900", "bold": True},
    "character": {"color": "#A31515"},

    # Comments and documentation
    "comment": {"color": "#008000", "italic": True},
    "comment.documentation": {"color": "#008000", "italic": True},

    # Operators and punctuation
    "operator": {"color": "#000000"},
    "punctuation": {"color": "#000000"},
    "punctuation.bracket": {"color": "#000000"},
    "punctuation.delimiter": {"color": "#000000"},

    # Decorators and attributes
    "decorator": {"color": "#808000"},
    "attribute": {"color": "#008080"},
    "property": {"color": "#008080"},

    # Special
    "tag": {"color": "#800000"},
    "label": {"color": "#000000", "bold": True},
    "namespace": {"color": "#267F99"},
    "module": {"color": "#267F99"},
}
# fmt: on
