#!/bin/sh
# Live acceptance: compile the three arbitrary questions in both evidence
# modes.  Each run writes a full WorldBundle + trace under artifacts/compiled/.
set -x
ASOF=2026-07-27

WORLDC_VERBOSE=1 python3 compile_question.py \
  "Should Coca-Cola launch the 'Share Your Real Thing' user-generated-content campaign described in the brief?" \
  --asof $ASOF --docs evidence/beverage_ugc.json \
  --out artifacts/compiled/beverage_ugc__evidence_docs

WORLDC_VERBOSE=1 python3 compile_question.py \
  "Is this cold email likely to get a response from Mark Cuban within two weeks?" \
  --asof $ASOF --docs evidence/cold_email.json \
  --out artifacts/compiled/cold_outreach__evidence_docs

WORLDC_VERBOSE=1 python3 compile_question.py \
  "Is the Senate going to pass the education funding bill before the August recess?" \
  --asof $ASOF --docs evidence/education_bill.json \
  --out artifacts/compiled/education_bill__evidence_docs

WORLDC_VERBOSE=1 python3 compile_question.py \
  "Should Coca-Cola launch a six-week TikTok user-generated-content contest campaign (branded hashtag, weekly creator prizes, roughly a two-million-dollar budget) in September 2026?" \
  --asof $ASOF --out artifacts/compiled/beverage_ugc__model_memory

WORLDC_VERBOSE=1 python3 compile_question.py \
  "Is the U.S. Senate going to pass a major K-12 education funding bill before the August 2026 recess?" \
  --asof $ASOF --out artifacts/compiled/education_bill__model_memory
