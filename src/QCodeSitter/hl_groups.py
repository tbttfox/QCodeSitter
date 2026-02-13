# Only "bg" and "fg" are required for
# "gutter" and "gutter_fg" are required for the line number
# "fg_dim" "bg_dim" "hl_dim" are used for code folding
# The rest are used for the FORMAT_SPECS which defines a color scheme

# Note that any hex colors with alpha values should be given
# in ARGB format (Which is how QColor reads them by default)

# fmt: off

# This colorscheme is pulled from the nvim Dracula theme
# https://github.com/Mofiqul/dracula.nvim
DARK_THEME = {
    "palette": {
        "red":             "#FF5555",
        "orange":          "#FFB86C",
        "yellow":          "#F1FA8C",
        "green":           "#50fa7b",
        "purple":          "#BD93F9",
        "cyan":            "#8BE9FD",
        "pink":            "#FF79C6",
        "bright_red":      "#FF6E6E",
        "bright_green":    "#69FF94",
        "bright_yellow":   "#FFFFA5",
        "bright_blue":     "#D6ACFF",
        "bright_magenta":  "#FF92DF",
        "bright_cyan":     "#A4FFFF",
        "bright_white":    "#FFFFFF",
        "white":           "#ABB2BF",
        "half_mid_gray":   "#B4B4B4",
        "mid_gray":        "#C8C8C8",
        "gray":            "#787878",
        "dark_gray":       "#101010",
        "black":           "#191A21",
        "cream":           "#F8F8F2",
        "xlight_slate":    "#8E9CBC",
        "light_slate":     "#6272A4",
        "mid_light_slate": "#4C4C5C",
        "slate":           "#3E4452",
        "slate2":          "#3C3C4C",
        "mid_dark_slate":  "#282A36",
        "dark_slate":      "#21222C",
    },

    "gui" : {
        "bg":               "mid_dark_slate",
        "bg_dim":           "slate2",
        "fg":               "cream",
        "fg_dim":           "mid_gray",
        "gutter":           "dark_gray",
        "gutter_fg":        "xlight_slate",
        "hl_dim":           "mid_light_slate",
        "match_hl":         "bright_yellow",
        "menu":             "dark_slate",
        "outside_bg":       "dark_slate",
        "pair_hl":          "mid_gray",
        "primary_cursor":   "bright_white",
        "secondary_cursor": "half_mid_gray",
        "selection":        "mid_light_slate",
        "selection_color":  "half_mid_gray",
        "visual":           "slate",
    },

    "syntax" : {
        "attribute":             {"color": "cyan"},
        "attribute.builtin":     {"color": "cyan"},
        "boolean":               {"color": "purple"},
        "character.special":     {"color": "green"},
        "comment":               {"color": "light_slate"},
        "constructor":           {"color": "cyan"},
        "function":              {"color": "green"},
        "function.builtin":      {"color": "cyan"},
        "function.call":         {"color": "green"},
        "function.macro":        {"color": "green"},
        "function.method":       {"color": "green"},
        "function.method.call":  {"color": "green"},
        "keyword":               {"color": "pink"},
        "keyword.conditional":   {"color": "pink"},
        "keyword.coroutine":     {"color": "pink"},
        "keyword.directive":     {"color": "pink"},
        "keyword.exception":     {"color": "purple"},
        "keyword.function":      {"color": "cyan"},
        "keyword.import":        {"color": "pink"},
        "keyword.operator":      {"color": "pink"},
        "keyword.repeat":        {"color": "pink"},
        "keyword.return":        {"color": "pink"},
        "keyword.type":          {"color": "pink"},
        "module":                {"color": "orange"},
        "module.builtin":        {"color": "orange"},
        "none":                  {"color": "purple"},
        "number":                {"color": "purple"},
        "number.float":          {"color": "green"},
        "operator":              {"color": "pink"},
        "punctuation.bracket":   {"color": "cream"},
        "punctuation.delimiter": {"color": "cream"},
        "string":                {"color": "yellow"},
        "string.documentation":  {"color": "cyan"},
        "string.escape":         {"color": "cyan"},
        "string.regexp":         {"color": "red"},
        "type":                  {"color": "bright_cyan"},
        "type.builtin":          {"color": "cyan", "italic": True},
        "type.definition":       {"color": "bright_cyan"},
        "variable":              {"color": "cream"},
        "variable.builtin":      {"color": "purple"},
        "variable.member":       {"color": "orange"},
        "variable.parameter":    {"color": "orange"},
        "constant":              {"color": "purple"},
        "constant.builtin":      {"color": "purple"},
    },
}

# This colorscheme is pulled from the nvim Edge theme
# https://github.com/sainnhe/edge
LIGHT_THEME = {
    "palette" : {
        'true_black':    '#000000',
        'true_white':    '#FFFFFF',
        'black':         '#DDE2E7',
        'bg_dim':        '#E8EBF0',
        'bg0':           '#FAFAFA',
        'bg1':           '#EEF1F4',
        'bg2':           '#E8EBF0',
        'bg3':           '#E8EBF0',
        'bg4':           '#DDE2E7',
        'bg_grey':       '#BCC5CF',
        'bg_red':        '#F6E4E4',
        'bg_yellow':     '#F0ECE2',
        'bg_green':      '#E5EEE4',
        'bg_blue':       '#E3EAF6',
        'bg_purple':     '#F4E9F8',
        'filled_red':    '#E17373',
        'filled_green':  '#76AF6F',
        'filled_blue':   '#6996E0',
        'filled_purple': '#BF75D6',
        'fg':            '#4B505B',
        'red':           '#D05858',
        'yellow':        '#BE7E05',
        'green':         '#608E32',
        'cyan':          '#3A8B84',
        'blue':          '#5079BE',
        'purple':        '#B05CCC',
        'grey':          '#8790A0',
        'grey_dim':      '#BAC3CB',
    },

    "gui" : {
        "bg":               "true_white",
        "bg_dim":           "bg1",
        "fg":               "fg",
        "fg_dim":           "grey",
        "gutter":           "bg2",
        "gutter_fg":        "fg",
        "hl_dim":           "filled_blue",
        "match_hl":         "filled_green",
        "menu":             "bg4",
        "outside_bg":       "bg_grey",
        "pair_hl":          "bg_yellow",
        "primary_cursor":   "true_black",
        "secondary_cursor": "true_black",
        "selection":        "filled_blue",
        "selection_color":  "blue",
        "visual":           "grey_dim",
    },

    "syntax" : {
        "attribute":             {"color": "yellow"},
        "attribute.builtin":     {"color": "blue"},
        "boolean":               {"color": "green"},
        "character.special":     {"color": "yellow"},
        "comment":               {"color": "grey"},
        "constructor":           {"color": "blue"},
        "function":              {"color": "blue"},
        "function.builtin":      {"color": "blue"},
        "function.call":         {"color": "blue"},
        "function.macro":        {"color": "blue"},
        "function.method":       {"color": "blue"},
        "function.method.call":  {"color": "blue"},
        "keyword":               {"color": "purple"},
        "keyword.conditional":   {"color": "purple"},
        "keyword.coroutine":     {"color": "purple"},
        "keyword.directive":     {"color": "purple"},
        "keyword.exception":     {"color": "purple"},
        "keyword.function":      {"color": "purple"},
        "keyword.import":        {"color": "purple"},
        "keyword.operator":      {"color": "purple"},
        "keyword.repeat":        {"color": "purple"},
        "keyword.return":        {"color": "purple"},
        "keyword.type":          {"color": "yellow"},
        "module":                {"color": "yellow"},
        "module.builtin":        {"color": "yellow"},
        "none":                  {"color": "fg"},
        "number":                {"color": "green"},
        "number.float":          {"color": "green"},
        "operator":              {"color": "purple"},
        "punctuation.bracket":   {"color": "grey"},
        "punctuation.delimiter": {"color": "grey"},
        "string":                {"color": "green"},
        "string.documentation":  {"color": "green"},
        "string.escape":         {"color": "yellow"},
        "string.regexp":         {"color": "yellow"},
        "type":                  {"color": "yellow"},
        "type.builtin":          {"color": "yellow"},
        "type.definition":       {"color": "yellow"},
        "variable":              {"color": "red", "italic": True},
        "variable.builtin":      {"color": "cyan", "italic": True},
        "variable.member":       {"color": "cyan"},
        "variable.parameter":    {"color": "red", "italic": True},
        "constant":              {"color": "red", "italic": True},
        "constant.builtin":      {"color": "red", "italic": True},
    },
}
# fmt: on


def read_theme(theme) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Read a palette/gui/syntax theme and produce a color palette and syntax palette

    Themes are structured in json with 3 keys: palette/gui/syntax

    "palette" is the optional color palette. This dictionary allows you to have one place
    to define the actual colors and give them nice names. The values of this dict must be
    hex #RRGGBB or #AARRGGBB. As long as you can pass it as a single argument to QColor.

    "gui" are the color requirements for the gui along with any Behavior specific colors
    You can define custom gui colors in the hex format, or reference a key in the palette

    "syntax" are the syntax highlighting colors and formatters. The values in this dictionary
    are dictionaries themselves with "color" "italic" and "bold" keys (TODO: and maybe others??)

    Args:
        theme: A json theme as defined above

    Returns:
        guicolors: A dictionary mapping gui color names to hex color strings. Also includes any
            palette color names
        syntaxcolors: A dictionary mapping treesitter syntax range names to format settings
    """
    pal = theme.get("palette", {})
    gui = theme["gui"]
    syn = theme["syntax"]

    gui = {k: pal.get(v, v) for k, v in gui.items()}
    gui.update(pal)

    newsyn = {}
    for k, vdata_orig in syn.items():
        vdata = vdata_orig.copy()
        col = vdata["color"]
        vdata["color"] = gui.get(col, col)
        newsyn[k] = vdata

    return gui, newsyn
