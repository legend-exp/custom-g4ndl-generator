import importlib.metadata

project = "custom-g4ndl-generator"
author = "LEGEND Collaboration"
release = importlib.metadata.version("custom-g4ndl-generator")

extensions = ["myst_parser"]
html_theme = "furo"
html_title = project
myst_heading_anchors = 3
