# 15: `prototype/` → `notebooks/` — research notebooks re-pointed at `santa`; `src/` and `data/` removed

**What to build:** The repo has one code package. `prototype/` is renamed to `notebooks/`; the research notebooks (prototype, gift-rec eval, wish eval, image eval, LLM benchmark) stay and import from `santa` instead of `prototype/src`; `prototype/src/` and `prototype/data/` are deleted. This is the last issue because everything the old notebooks import must already exist in `santa/`.

**Blocked by:** 12, 14

**Status:** ready-for-human

- [x] `git mv prototype notebooks`; the four workshop notebooks from issue 12 live alongside the research ones
- [x] Research notebooks import `santa.schemas`, `santa.prompts`, `santa.models`, `santa.card`; evaluation helpers that are still needed move to `santa/eval.py` (or `notebooks/_helpers.py`), the rest is deleted
- [x] `prototype/src/`, `prototype/data/`, `prototype/santa_workflow.py` removed; `.gitignore` entries updated; `research` dependency group covers what the notebooks need
- [x] `santa_demo/proto.py` and every `sys.path` insert gone; `tests/conftest.py` no longer imports `santa_demo.proto`
- [x] Research notebooks (`10_`–`14_`) execute top-to-bottom with `SANTA_EVAL_FAKE=1`; outputs stripped. Workshop `01_`–`04_` remain issue 12's live-endpoint execute.
- [x] README/AGENTS/CONTEXT updated for the new layout

## Comments

2026-09-08: `prototype/` deleted. Research notebooks live at `notebooks/10_prototype.ipynb` … `14_benchmark_llm.ipynb` (renamed to avoid colliding with workshop `01_`–`04_`). Helpers in `santa/eval.py`. `SANTA_EVAL_FAKE=1 jupyter nbconvert --execute` run for 10–14; workshop playgrounds still need live endpoints (issue 12).
