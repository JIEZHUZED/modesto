#!/usr/bin/env bash
source activate idp
python runFullOpt.py
python runOpt.py
python testPostPr.py
