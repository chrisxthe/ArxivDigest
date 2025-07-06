#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate a personalised arXiv digest.

The *defaults* below are over-ridden at runtime by values in ``config.yaml``:

    lookback_days            – how many recent days to pull from arXiv  
    category_filter_enabled  – True ⇒ apply ``categories`` list; False ⇒ ignore  
    threshold                – min GPT relevance score (1-10) to keep a paper
"""

# ─────────────────────────── defaults ────────────────────────────────────────
CATEGORY_FILTER_ENABLED = True      # will be replaced by YAML if present
LOOKBACK_DAYS           = 7
# ─────────────────────────────────────────────────────────────────────────────

from datetime import date
import os, sys, time, traceback, argparse, yaml
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
import openai

from relevancy import generate_relevance_score, process_subject_fields
from download_new_papers import get_papers

# ─── quick sanity-check for the key ──────────────────────────────────────────
print("DEBUG env key len =", len(os.getenv("OPENAI_API_KEY", "")), file=sys.stderr)
openai.api_key = os.getenv("OPENAI_API_KEY", "")
print("DEBUG openai.api_key len =", len(openai.api_key or ""), file=sys.stderr)
try:
    t0 = time.time(); openai.Model.list()
    print(f"DEBUG ping OK ({time.time()-t0:.2f}s)", file=sys.stderr)
except Exception as e:
    traceback.print_exc(); sys.exit(1)


# Topic → arXiv abbreviation maps (unchanged) 
topics = {  # …
    "Physics": "",
    "Mathematics": "math",
    "Computer Science": "cs",
    "Quantitative Biology": "q-bio",
    "Quantitative Finance": "q-fin",
    "Statistics": "stat",
    "Electrical Engineering and Systems Science": "eess",
    "Economics": "econ",
}

physics_topics = {
    "Astrophysics": "astro-ph",
    "Condensed Matter": "cond-mat",
    "General Relativity and Quantum Cosmology": "gr-qc",
    "High Energy Physics - Experiment": "hep-ex",
    "High Energy Physics - Lattice": "hep-lat",
    "High Energy Physics - Phenomenology": "hep-ph",
    "High Energy Physics - Theory": "hep-th",
    "Mathematical Physics": "math-ph",
    "Nonlinear Sciences": "nlin",
    "Nuclear Experiment": "nucl-ex",
    "Nuclear Theory": "nucl-th",
    "Physics": "physics",
    "Quantum Physics": "quant-ph",
}


# TODO: surely theres a better way
category_map = {
    "Astrophysics": [
        "Astrophysics of Galaxies",
        "Cosmology and Nongalactic Astrophysics",
        "Earth and Planetary Astrophysics",
        "High Energy Astrophysical Phenomena",
        "Instrumentation and Methods for Astrophysics",
        "Solar and Stellar Astrophysics",
    ],
    "Condensed Matter": [
        "Disordered Systems and Neural Networks",
        "Materials Science",
        "Mesoscale and Nanoscale Physics",
        "Other Condensed Matter",
        "Quantum Gases",
        "Soft Condensed Matter",
        "Statistical Mechanics",
        "Strongly Correlated Electrons",
        "Superconductivity",
    ],
    "General Relativity and Quantum Cosmology": ["None"],
    "High Energy Physics - Experiment": ["None"],
    "High Energy Physics - Lattice": ["None"],
    "High Energy Physics - Phenomenology": ["None"],
    "High Energy Physics - Theory": ["None"],
    "Mathematical Physics": ["None"],
    "Nonlinear Sciences": [
        "Adaptation and Self-Organizing Systems",
        "Cellular Automata and Lattice Gases",
        "Chaotic Dynamics",
        "Exactly Solvable and Integrable Systems",
        "Pattern Formation and Solitons",
    ],
    "Nuclear Experiment": ["None"],
    "Nuclear Theory": ["None"],
    "Physics": [
        "Accelerator Physics",
        "Applied Physics",
        "Atmospheric and Oceanic Physics",
        "Atomic and Molecular Clusters",
        "Atomic Physics",
        "Biological Physics",
        "Chemical Physics",
        "Classical Physics",
        "Computational Physics",
        "Data Analysis, Statistics and Probability",
        "Fluid Dynamics",
        "General Physics",
        "Geophysics",
        "History and Philosophy of Physics",
        "Instrumentation and Detectors",
        "Medical Physics",
        "Optics",
        "Physics and Society",
        "Physics Education",
        "Plasma Physics",
        "Popular Physics",
        "Space Physics",
    ],
    "Quantum Physics": ["None"],
    "Mathematics": [
        "Algebraic Geometry",
        "Algebraic Topology",
        "Analysis of PDEs",
        "Category Theory",
        "Classical Analysis and ODEs",
        "Combinatorics",
        "Commutative Algebra",
        "Complex Variables",
        "Differential Geometry",
        "Dynamical Systems",
        "Functional Analysis",
        "General Mathematics",
        "General Topology",
        "Geometric Topology",
        "Group Theory",
        "History and Overview",
        "Information Theory",
        "K-Theory and Homology",
        "Logic",
        "Mathematical Physics",
        "Metric Geometry",
        "Number Theory",
        "Numerical Analysis",
        "Operator Algebras",
        "Optimization and Control",
        "Probability",
        "Quantum Algebra",
        "Representation Theory",
        "Rings and Algebras",
        "Spectral Theory",
        "Statistics Theory",
        "Symplectic Geometry",
    ],
    "Computer Science": [
        "Artificial Intelligence",
        "Computation and Language",
        "Computational Complexity",
        "Computational Engineering, Finance, and Science",
        "Computational Geometry",
        "Computer Science and Game Theory",
        "Computer Vision and Pattern Recognition",
        "Computers and Society",
        "Cryptography and Security",
        "Data Structures and Algorithms",
        "Databases",
        "Digital Libraries",
        "Discrete Mathematics",
        "Distributed, Parallel, and Cluster Computing",
        "Emerging Technologies",
        "Formal Languages and Automata Theory",
        "General Literature",
        "Graphics",
        "Hardware Architecture",
        "Human-Computer Interaction",
        "Information Retrieval",
        "Information Theory",
        "Logic in Computer Science",
        "Machine Learning",
        "Mathematical Software",
        "Multiagent Systems",
        "Multimedia",
        "Networking and Internet Architecture",
        "Neural and Evolutionary Computing",
        "Numerical Analysis",
        "Operating Systems",
        "Other Computer Science",
        "Performance",
        "Programming Languages",
        "Robotics",
        "Social and Information Networks",
        "Software Engineering",
        "Sound",
        "Symbolic Computation",
        "Systems and Control",
    ],
    "Quantitative Biology": [
        "Biomolecules",
        "Cell Behavior",
        "Genomics",
        "Molecular Networks",
        "Neurons and Cognition",
        "Other Quantitative Biology",
        "Populations and Evolution",
        "Quantitative Methods",
        "Subcellular Processes",
        "Tissues and Organs",
    ],
    "Quantitative Finance": [
        "Computational Finance",
        "Economics",
        "General Finance",
        "Mathematical Finance",
        "Portfolio Management",
        "Pricing of Securities",
        "Risk Management",
        "Statistical Finance",
        "Trading and Market Microstructure",
    ],
    "Statistics": [
        "Applications",
        "Computation",
        "Machine Learning",
        "Methodology",
        "Other Statistics",
        "Statistics Theory",
    ],
    "Electrical Engineering and Systems Science": [
        "Audio and Speech Processing",
        "Image and Video Processing",
        "Signal Processing",
        "Systems and Control",
    ],
    "Economics": ["Econometrics", "General Economics", "Theoretical Economics"],
}

def generate_body(topic, categories, interest, threshold):
    """Fetch → dedup → (opt) filter → GPT score → HTML."""
    # 1) arXiv abbreviation ----------------------------------------------------
    if topic == "Physics":
        raise RuntimeError("You must choose a physics subtopic.")
    abbr = physics_topics.get(topic) or topics.get(topic)
    if not abbr:
        raise RuntimeError(f"Invalid topic {topic}")

    # 2) get papers + dedup ----------------------------------------------------
    lookback = LOOKBACK_DAYS if CATEGORY_FILTER_ENABLED else 1
    papers   = get_papers(abbr, days=lookback)
    uniq = {}
    for p in papers:
        uniq.setdefault(p["id"], p)        # keep first occurrence
    papers = list(uniq.values())
    print(f"DEBUG fetched {len(papers)} unique from last {lookback}d",
          file=sys.stderr)

    # 3) category filter -------------------------------------------------------
    if CATEGORY_FILTER_ENABLED and categories:
        invalid = [c for c in categories if c not in category_map[topic]]
        if invalid:
            raise RuntimeError(f"{invalid} not valid for topic {topic}")
        papers = [p for p in papers
                  if set(process_subject_fields(p["subjects"])) & set(categories)]
        print("DEBUG after category filter →", len(papers), file=sys.stderr)

    if not papers:
        raise RuntimeError("No papers matched current settings.")
    
    # 4) GPT relevance scoring -------------------------------------------------
    if interest:
        ranked, _ = generate_relevance_score(
            papers,
            query={"interest": interest},
            threshold_score=threshold,
            num_paper_in_prompt=16,
        )

        # dict[id] -> full paper
        by_id = {p["id"]: p for p in papers}

        # attach GPT metrics to matching papers
        for extra in ranked:
            pid   = extra.get("id")                     # echoed by LLM
            score = extra.get("Relevancy score", 0)
            try:
                score_num = int(score)
            except (ValueError, TypeError):
                try:
                    score_num = int(float(score))
                except Exception:
                    score_num = 0

            if pid in by_id and score_num >= threshold:
                by_id[pid].update(
                    {"Relevancy score": score_num,
                     "Reasons for match": extra.get("Reasons for match", "")}
                )

        # keep only those papers that now carry a score ≥ threshold
        papers = [p for p in by_id.values()
                  if p.get("Relevancy score", 0) >= threshold]

        print("DEBUG after GPT filter →", len(papers), "papers", file=sys.stderr)

    # 5) Build HTML ------------------------------------------------------------
    body = "<br><br>".join(
        (
            f'Title: <a href="{p["main_page"]}">{p["title"]}</a>'
            f'<br>Authors: {p["authors"]}'
            f'<br>Score: {p.get("Relevancy score","")}'
            f'<br>Reason: {p.get("Reasons for match","")}'
            f'<br>Abstract: {p["abstract"]}'
        )
        for p in papers
    )
    return body


# ─── CLI entry-point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    # override global defaults from YAML
    CATEGORY_FILTER_ENABLED = cfg.get("category_filter_enabled",
                                      CATEGORY_FILTER_ENABLED)
    LOOKBACK_DAYS           = cfg.get("lookback_days", LOOKBACK_DAYS)

    topic      = cfg["topic"]
    categories = cfg["categories"]
    threshold  = cfg["threshold"]
    interest   = cfg["interest"]

    body = generate_body(topic, categories, interest, threshold)

    with open("digest.html", "w") as fh:
        fh.write(body)
    print("DEBUG wrote digest.html (%d bytes)"
          % os.path.getsize("digest.html"), file=sys.stderr)

    # optional e-mail via SendGrid --------------------------------------------
    if os.getenv("SENDGRID_API_KEY"):
        sg   = SendGridAPIClient(api_key=os.getenv("SENDGRID_API_KEY"))
        mail = Mail(
            Email(os.getenv("FROM_EMAIL")),
            To(os.getenv("TO_EMAIL")),
            date.today().strftime("Personalized arXiv Digest, %d %b %Y"),
            Content("text/html", body),
        )
        resp = sg.client.mail.send.post(request_body=mail.get())
        print("SendGrid status", resp.status_code)
    else:
        print("No SENDGRID_API_KEY – skipping e-mail")