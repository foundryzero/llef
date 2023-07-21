# Foundry Zero Open Source Python Style Guide

The LLEF project comes with a .vscode workspace settings file which should enforce some of these style guidelines for you. However for completeness, the guidelines against which pull requests will be reviewed are included below.

## Code formatting

`black` should be used for code formatting. `black` is best described by the project themselves:

> Black is the uncompromising Python code formatter. By using it, you agree to cede control over minutiae of hand-formatting. In return, Black gives you speed, determinism, and freedom from `pycodestyle` nagging about formatting. You will save time and mental energy for more important matters.

Python repositories should specify a `requirements.txt` file in the root of the project directory containing all the external pip dependies.

## Documentation
All public functions and classes should be documented in the standard Python docstring style, detailing the intention of the function, the arguments, any exceptions it may raise, and the return value.

Private functions should ideally be documented too, for ease of maintainability. 

When using type hints, it is not necessary to include the argument types in the documentation.

The `sphinx-notypes` style is recommended.

```
def function(arg1: int, arg2: str) -> str:
"""
This is a function
:param arg1: An argument
:param arg2: Another argument
:raises KeyError: description of error condition
:return: The return string
"""
```

## Linting
Set up VS Code (or your IDE of choice) to make use of pylint to check your project for easily catchable issues.

## Type hints
When writing complex Python code, consider using type hints and mypy to statically check them.

Remember: Type hints are not enforced by the Python interpreter, so only static analysis tools like mypy will inform you of errors in your code caught by type hinting.

# Import ordering
Imports should be ordered in alphabetical order, grouped from most widely applicable (e.g. language built ins) to most specific (e.g. project specified)

```
import json
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms.formsets import formset_factory
from django.forms.models import inlineformset_factory
from django.views.decorators.http import require_POST

from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

from .forms import KeywordForm, SynonymForm
```

A tool such as `isort` should be used to do this automatically for you and to ensure consistency.

