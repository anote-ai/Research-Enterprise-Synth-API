#!/usr/bin/env python3
"""Regenerates paper/main_aaai.tex from paper/main.tex: reflows the plain-article draft into
the official AAAI-26 anonymous-submission two-column format (aaai2026.sty/.bst, from the real
AAAI author kit at https://aaai.org/authorkit26-1/). main.tex is the source of truth for edits;
main_aaai.tex is a build output of this script, not hand-maintained separately.

Run from anywhere; paths are resolved relative to the repo root.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "paper" / "main.tex"
DST = ROOT / "paper" / "main_aaai.tex"

text = SRC.read_text()

# --- 1. Split off the old preamble / author block, keep everything from \begin{abstract} on ---
start = text.index(r"\begin{abstract}")
body = text[start:]

# Strip the trailing bibliographystyle line (aaai2026.sty sets it automatically)
body = body.replace(
    "\\bibliographystyle{plain}\n\\bibliography{references}",
    "\\bibliography{references}",
)

# --- 2. Fix subsubsection-level (N.M.P) cross-references. AAAI cannot number a third
# heading level, so every "Section~N.M.P" becomes "Section~N.M". Two of these were already
# pointing at the wrong top-level section before this conversion (a pre-existing bug: the
# Haiku ablation and the 3-API generalization result are physically inside Section 5's
# Experiment 4/5 subsections, not Section 6) -- fixed here rather than carried forward.
body = body.replace("Section~6.5.1", "Section~5.6")   # Haiku ablation: lives in 5.6, not 6.5
body = body.replace("Section~6.6.1", "Section~5.7")   # 3-API generalization: lives in 5.7, not 6.6
body = re.sub(r"Section~(\d+\.\d+)\.\d+", r"Section~\1", body)      # remaining N.M.P -> N.M
body = re.sub(r"Section~(\d+\.\d+)--\d+\.\d+", r"Section~\1", body)  # N.M.P--N.M.Q range -> N.M

# --- 3. Wrap bare `\begin{center} ... \begin{tabular} ... \end{tabular} ... \end{center}`
# blocks into proper AAAI table floats with real captions. Non-tabular center blocks
# (the two pipeline-flow text diagrams) are left untouched.
captions = [
    ("lll", "GitHub REST API & APIs.guru", "Training APIs and their verified endpoint counts."),
    ("lccc", "Valid $\\rightarrow$ plausible", "Claude Haiku 4.5 semantic-plausibility check results by API."),
    ("lcc", "Base (zero-shot, untuned) & 12.5", "Downstream tool-selection accuracy and parameter validity on the held-out Zoom set (single run)."),
    ("lccc", "Zoom & 12.5\\% & 25.0\\%", "Tool-selection accuracy across three held-out APIs (single run per model)."),
    ("lccc", "Zoom & 12.5 $\\pm$", "Tool-selection accuracy across three held-out APIs, mean $\\pm$ std over 5 training seeds."),
    ("lcc", "Public (Zoom/DigitalOcean/Spotify", "Tool-selection accuracy on public vs.\\ never-published private held-out API sets."),
    ("lcc", "Twilio & 50.0", "Tool-selection accuracy on six additional real, public held-out APIs."),
    ("lll", "Wrong HTTP method", "Corrupted-trajectory detection rate by planted error type."),
    ("lll", "Base LLM (zero-shot)", "Downstream tool success and argument correctness on the held-out Zoom set."),
    ("lccccc", "Uses OpenAPI specs", "Capability comparison with ToolBench, API-Bank, and AgentInstruct."),
    ("lll", "GitHub & 100.0\\% & 93.3", "Ablation A1: parameter validity and instruction diversity without intent generation."),
    ("ll", "Without verification", "Ablation A2: planted-error survival with and without the verification engine."),
    ("llll", "Full pipeline & 100\\%", "Summary of all four ablation results."),
    ("p{1.6cm}p{2cm}p{6.5cm}p{2.2cm}", "GitHub & Developer", "Summary of the three case-study trajectories and their verification outcomes."),
    ("lc", "Intent Match & 2.81", "LLM-judge mean scores (1--5 scale) across four evaluation dimensions."),
    ("lcc", "Wrong tool selected", "Distribution of LLM-judge-identified primary error types."),
    ("lc", "Binary Tool Selection Accuracy", "Binary tool-selection accuracy vs.\\ LLM-judge full-correctness rate."),
]

label_counter = [0]

def wrap_table(m):
    colspec = m.group("colspec")
    inner = m.group(0)
    label_counter[0] += 1
    idx = label_counter[0]
    # find the matching caption by colspec + a distinctive content snippet
    cap = None
    for cs, snippet, caption_text in captions:
        if cs == colspec and snippet.replace("\\\\", "") in inner:
            cap = caption_text
            break
    if cap is None:
        cap = "Results."  # should not happen; fallback keeps compilation working
    # The 5-column capability-comparison table needs both columns' width; everything
    # else fits one column once set in footnotesize with tighter column padding
    # (\tabcolsep is explicitly permitted by the AAAI style guide as the one \setlength
    # exception, specifically for compressing overwide tables).
    star = "*" if (colspec.startswith("p{1.6cm}") or colspec == "lccccc") else ""
    return (
        f"\\begin{{table{star}}}[t]\n\\centering\n\\footnotesize\n"
        f"\\setlength{{\\tabcolsep}}{{2pt}}\n"
        f"\\begin{{tabular}}{{{colspec}}}{m.group('rows')}\\end{{tabular}}\n"
        f"\\caption{{{cap}}}\n\\label{{tab:auto{idx}}}\n\\end{{table{star}}}\n"
    )

pattern = re.compile(
    r"\\begin\{center\}\n(?P<small>\\small\n|\\footnotesize\n)?"
    r"\\begin\{tabular\}\{(?P<colspec>(?:[^{}]|\{[^{}]*\})+)\}(?P<rows>.*?)\\end\{tabular\}\n"
    r"\\end\{center\}",
    re.DOTALL,
)

def wrap_table_guarded(m):
    # The pipeline-flow text diagram (single "c" column, arrows, no real data) is not a
    # table -- leave it as a plain centered text block, not a numbered/captioned float.
    if m.group("colspec") == "c":
        return m.group(0)
    return wrap_table(m)

body, n = pattern.subn(wrap_table_guarded, body)
print(f"Wrapped {n} tabular blocks total (one 'c'-column flow diagram intentionally skipped)")

# --- 3b. Long inline \texttt{} API paths overflow the narrower AAAI column; add
# \allowbreak at slashes so LaTeX can wrap them instead of running into the margin.
body = body.replace(
    r"\texttt{PUT /orgs/\{org\}/actions/secrets/\{secret\_name\}/repositories}",
    r"\texttt{PUT /orgs/\allowbreak\{org\}/\allowbreak actions/\allowbreak secrets/\allowbreak\{secret\_name\}/\allowbreak repositories}",
)

# --- 3c. Shorten table cell/header text that's still too wide for the narrower AAAI
# column even at footnotesize+tabcolsep=3pt (per AAAI's own guidance: shortened column
# titles / reduced precision are the sanctioned way to compress an overwide table,
# rather than \resizebox, which is forbidden). No numbers change, only labels.
shortenings = [
    ("551 paths / 845 path-method operations", "551 / 845 methods"),
    ("299 paths / 446 path-method operations", "299 / 446 methods"),
    ("174 paths / 174 path-method operations", "174 / 174 methods"),
    ("Base (zero-shot, untuned)", "Base (untuned)"),
    ("+ LoRA on Self-Instruct data", "+ Self-Instruct"),
    ("+ LoRA on EnterpriseSynth data", "+ EnterpriseSynth"),
    (r"Public (Zoom/DigitalOcean/Spotify, $n$=48)", r"Public ($n$=48)"),
    (r"Private (never-published, $n$=30)", r"Private ($n$=30)"),
    ("Base LLM (zero-shot)", "Base LLM"),
    ("Self-Instruct-fine-tuned", "Self-Instruct-tuned"),
    ("EnterpriseSynth-fine-tuned", "EnterpriseSynth-tuned"),
    (r"\textbf{Argument Correctness}", r"\textbf{Arg.\ Correctness}"),
]
for old, new in shortenings:
    # Match across source line-wraps: a space in `old` matches any run of whitespace in
    # `body`, since LaTeX (unlike this string search) treats a wrapped line break as a space.
    pat = re.compile(r"\s+".join(re.escape(part) for part in old.split(" ")))
    if not pat.search(body):
        raise SystemExit(f"shortening target not found, source text may have changed: {old!r}")
    body = pat.sub(new.replace("\\", "\\\\"), body, count=1)

# --- 4. Assemble the full AAAI-26 anonymous-submission preamble, exactly per the
# template the user supplied (anonymous-submission-latex-2026.tex). ---
preamble = r"""\documentclass[letterpaper]{article} % DO NOT CHANGE THIS
\usepackage[submission]{aaai2026}  % DO NOT CHANGE THIS
\usepackage{times}  % DO NOT CHANGE THIS
\usepackage{helvet}  % DO NOT CHANGE THIS
\usepackage{courier}  % DO NOT CHANGE THIS
\usepackage[hyphens]{url}  % DO NOT CHANGE THIS
\usepackage{graphicx} % DO NOT CHANGE THIS
\urlstyle{rm} % DO NOT CHANGE THIS
\def\UrlFont{\rm}  % DO NOT CHANGE THIS
\usepackage{natbib}  % DO NOT CHANGE THIS AND DO NOT ADD ANY OPTIONS TO IT
\usepackage{caption} % DO NOT CHANGE THIS AND DO NOT ADD ANY OPTIONS TO IT
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{booktabs}
\frenchspacing  % DO NOT CHANGE THIS
\setlength{\pdfpagewidth}{8.5in} % DO NOT CHANGE THIS
\setlength{\pdfpageheight}{11in} % DO NOT CHANGE THIS
\pdfinfo{
/TemplateVersion (2026.1)
}

\setcounter{secnumdepth}{2}

\title{EnterpriseSynth: Zero-Execution SFT and Eval Data from OpenAPI Specs}
\author{
    Anonymous Submission
}
\affiliations{
}

\begin{document}

\maketitle

"""

DST.write_text(preamble + body)
print(f"Wrote {DST} ({len(preamble + body)} bytes)")
