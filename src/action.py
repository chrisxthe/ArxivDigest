#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate a personalised arXiv digest and (optionally) e-mail it.

Tunable options:
    CATEGORY_FILTER_ENABLED – True  → enforce `categories` from config.yaml
                                  and look back `LOOKBACK_DAYS` instead of 1.
                               False → ignore `categories` completely.
    LOOKBACK_DAYS           – How many days of arXiv history to pull when
                               the category filter is enabled.
"""

# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL TOGGLE & SETTINGS
# ──────────────────────────────────────────────────────────────────────────────
CATEGORY_FILTER_ENABLED = True        # ← flip to False to disable the filter
LOOKBACK_DAYS           = 7           # used only when the filter is ON
# ──────────────────────────────────────────────────────────────────────────────

from datetime import date
import argparse, yaml, os, sys, time, traceback
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

import openai
from relevancy import generate_relevance_score, process_subject_fields
from download_new_papers import get_papers

# ── Sanity-check: key must be in env ──────────────────────────────────────────
print("DEBUG: env key len =", len(os.getenv("OPENAI_API_KEY", "")), file=sys.stderr)
openai.api_key = os.getenv("OPENAI_API_KEY", "")
print("DEBUG: openai.api_key len =", len(openai.api_key or ""), file=sys.stderr)

try:
    t0 = time.time()
    openai.Model.list()            # light ping
    print(f"DEBUG: ping OK ({time.time() - t0:.2f}s)", file=sys.stderr)
except Exception as e:
    print("DEBUG: ping FAILED:", e, file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)

# ── Topic → arXiv abbreviation maps (unchanged) ──────────────────────────────
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
    """Fetch papers → optional category filter → GPT scoring → HTML body."""
    # 1) Resolve arXiv abbreviation -------------------------------------------
    if topic == "Physics":
        raise RuntimeError("You must choose a physics subtopic.")
    elif topic in physics_topics:
        abbr = physics_topics[topic]
    elif topic in topics:
        abbr = topics[topic]
    else:
        raise RuntimeError(f"Invalid topic {topic}")

    # 2) Fetch recent papers ---------------------------------------------------
    lookback = LOOKBACK_DAYS if CATEGORY_FILTER_ENABLED else 1
    papers   = get_papers(abbr, days=lookback)  # get_papers must accept 'days'
    print(f"DEBUG: fetched {len(papers)} papers from last {lookback} day(s)",
          file=sys.stderr)

    # 3) Optional category filter ---------------------------------------------
    if CATEGORY_FILTER_ENABLED and categories:
        invalid = [c for c in categories if c not in category_map[topic]]
        if invalid:
            raise RuntimeError(f"{invalid} not valid for topic {topic}")

        papers = [
            p for p in papers
            if set(process_subject_fields(p["subjects"])) & set(categories)
        ]
        print("DEBUG: after category filter ->", len(papers), "papers",
              file=sys.stderr)

    # 4) Bail out early if nothing left ---------------------------------------
    if not papers:
        raise RuntimeError("No papers matched the current settings.")

    # 5) GPT relevance scoring -------------------------------------------------
    if interest:
        ranked, hallucination = generate_relevance_score(
            papers,
            query={"interest": interest},
            threshold_score=threshold,
            num_paper_in_prompt=16,
        )
    
        # `ranked` holds only {"Relevancy score", "Reasons for match"}
        # so stitch those metrics back onto the full paper objects:
        scored = []
        for full, extra in zip(papers, ranked):
            if extra.get("Relevancy score", 0) >= threshold:
                full.update(extra)          # add the two keys
                scored.append(full)
    
        papers = scored
        print("DEBUG after GPT filter →", len(papers), file=sys.stderr)

    # 6) Build HTML ------------------------------------------------------------
    body = "<br><br>".join(
        f'Title: <a href="{p["main_page"]}">{p["title"]}</a>'
        f'<br>Authors: {p["authors"]}'
        + (f'<br>Score: {p.get("Relevancy score","")}'
           f'<br>Reason: {p.get("Reasons for match","")}' if interest else "")
        for p in papers
    )
    return body


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml",
                        help="YAML config file to use")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    # Ensure key present after dotenv reload ----------------------------------
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("No OPENAI_API_KEY in environment")

    topic      = cfg["topic"]
    categories = cfg["categories"]
    threshold  = cfg["threshold"]
    interest   = cfg["interest"]

    body = generate_body(topic, categories, interest, threshold)

    # Write digest -------------------------------------------------------------
    with open("digest.html", "w") as fh:
        fh.write(body)
    print("DEBUG: wrote digest.html (%d bytes)" % os.path.getsize("digest.html"),
          file=sys.stderr)

    # Optional e-mail via SendGrid --------------------------------------------
    if os.getenv("SENDGRID_API_KEY"):
        sg          = SendGridAPIClient(api_key=os.getenv("SENDGRID_API_KEY"))
        from_email  = Email(os.getenv("FROM_EMAIL"))
        to_email    = To(os.getenv("TO_EMAIL"))
        subject     = date.today().strftime("Personalized arXiv Digest, %d %b %Y")
        content     = Content("text/html", body)
        mail_json   = Mail(from_email, to_email, subject, content).get()

        resp = sg.client.mail.send.post(request_body=mail_json)
        if 200 <= resp.status_code < 300:
            print("SendGrid email sent ✓")
        else:
            print(f"SendGrid error {resp.status_code}: {resp.text}")
    else:
        print("No SENDGRID_API_KEY – skipping e-mail")
