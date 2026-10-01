# The JOSS paper: where it stands

**Parked 1 Oct 2026, to revisit in January 2027.** Nothing has been
submitted to JOSS.

## The files

| File | What it is |
|---|---|
| `paper.md` | The paper, corrected claim by claim against the code. |
| `paper.bib` | Its references. |
| `factcheck.md` | The fact-check of the first draft: every claim run, with evidence, and Roberto's rulings recorded. Read its *Status* section first. |

The first draft, as it arrived from another session, is
`C:\Users\perez\Downloads\paper.md` (and `paper.bib`), kept untouched.

## Done (1 Oct 2026, items #470 and #471)

- Every factual claim checked by running code; the Formulation paragraph
  rewritten (the engine is *equation generation*, not sparse tableau: node
  voltages plus element currents, no element voltages).
- The repository made ready for review: CI on Python 3.9 to 3.14,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, the README's tests
  and stale sentences fixed.
- Out of beta: `Development Status :: 5 - Production/Stable`, released as
  **0.6.18** on PyPI; GitHub Releases `v0.6.17` and `v0.6.18`.
- Roberto's ORCID, `0000-0002-2495-6993`, in the paper and `CITATION.cff`.
- Research impact written from the archive (the 2000 IEEE Region 9 award,
  the 2001 thesis, the 2001 *BURAN* article) and from the users' comments
  Roberto publishes (83 comments, 74 people, more than 30 universities,
  20 countries):
  <https://roberto.perez-franco.com/en/symbulator/comments-received-in-english/>,
  <https://roberto.perez-franco.com/es/symbulator/comentarios-recibidos-en-espanol/>.

## Settled, so not to be reopened

- **Polar phasors stay floating point.** Roberto's ruling of 25 Aug 2026,
  confirmed 1 Oct 2026: *"No point in making polars exact. It's not
  practical."* The paper explains it.
- **Out of beta**, versions 9 and 8, at Roberto's word (1 Oct 2026), over the
  fact-check's advice to stay at Beta for submission.
- **No instructor is known to have adopted Symbulator for a class**
  (Roberto, 1 Oct 2026). The paper claims student and professional use only;
  do not ask for teaching adoption again.
- **PyPI downloads and GitHub stars are left out** of the paper: 60 releases
  in seven weeks inflate the downloads (8,042 from 13 Aug to 30 Sep 2026),
  and the repository had no stars.

## Open, for January

1. **Dates for the users' comments**, or any evidence of use after the TI-89
   era (versions 6, 7, 8 or 9). All 83 comments concern Symbulator 3, Q and 4
   and the 2000 award, so as they stand they support "1999 to the early
   2000s", not "over decades".
2. **Acknowledgements** (the TODO in the paper).
3. **The Nilsson & Riedel 12e year and place** from the book's title page
   (`paper.bib`, entry `nilsson2023`, marked TODO).
4. **State of the field**: Roberto to sharpen what Lcapy or SLiCAP cannot do
   (TODO in the paper). Reviewers will read it closely.
5. **The AI disclosure**: Roberto to confirm it matches how he worked, and
   name any other tools (TODO in the paper).
6. **Before submitting**, re-run the checks rather than trusting this file:
   - `python -m pytest symbulator/tests -q` and the CI badge on GitHub;
   - the code claims in the paper (the scripts are in `factcheck.md`);
   - the word count: JOSS allows about 1,750 words; on 1 Oct 2026 the prose
     was 1,736;
   - `date:` in the front matter, set to the submission day;
   - the version the paper and `CITATION.cff` name, against PyPI's latest;
   - a Zenodo archive of the release being submitted (JOSS asks for its DOI
     at acceptance).
7. **Worth knowing before review:** the public history began on 21 Aug
   2026, which reviewers may find short; every commit is authored as
   `Symbulator`, with the AI models named in the trailers.
