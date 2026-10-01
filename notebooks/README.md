# Notebooks

Executed Jupyter notebooks for the `symbulator` package. Each is
committed with its outputs, so GitHub shows the answers, and each
opens in Google Colab with `pip install symbulator matplotlib` as its
first cell.

| Notebook | What it is |
|---|---|
| `quickstart.ipynb` | The package in a notebook, end to end: a circuit as a string, typeset results, the tutorial's `ir1`/`v2` spellings, `polar()`, Thevenin, two-ports, transients, a Bode plot, the `%%dc` cell magics, Expert Mode. |
| `books/` | Every built-in example book of the Symbulator app as its own notebook, 24 in all: the eighteen lesson books of the tutorial (`Lesson_01` to `Lesson_13`), the samplers *Problems from Alexander & Sadiku 7ed* and *Problems from Nilsson & Riedel 12ed*, the Manual's worked circuits, the Showcase, *A Baker's Dozen* and the monograph's exemplars. Built by `build_books.py` from the app's own `.cir` files. `check_books.py` runs each entry through the app's own `/api/solve` and compares every answer the two have in common; it needs the app's repository beside this one, so it is a maintainer's check rather than part of the test suite. |
| `the_monograph.ipynb` | The exemplar circuits of *The Internal Logic of Symbulator*, run as the eight entries the app lists under *The Monograph*. Built by `build_monograph.py`, which reads the circuits from the app's own `The_Monograph.cir` so the notebook, the app's menu and the monograph's Appendix B cannot drift apart. Also served at https://learn.symbulator.com/monograph.ipynb, linked from the landing page beside the PDF. |

To rebuild after a change, from the repository root with an
interpreter that has `nbclient` and `matplotlib`:

```
python notebooks/build_monograph.py
python notebooks/build_books.py --all
```

The script needs the project's layout, `repos/solver` beside
`repos/server`, and says so if it cannot find the circuits.

The reference for using the package in a notebook is the README's
*In a notebook* section, one level up.
