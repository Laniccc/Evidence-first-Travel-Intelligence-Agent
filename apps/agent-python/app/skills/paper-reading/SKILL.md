---
name: paper-reading
description: Read and analyze papers, PDFs, and technical documents to extract method, evidence, and key findings.
triggers: pdf,paper,论文,文献,document,article,read paper,academic,学术
---

# Paper Reading Skill

Use this skill when the task involves reading academic papers, technical documents, or PDF files.

## Workflow

1. **Identify metadata**: title, authors, venue/year if available, source path or URL, document type.
2. **Read in order**: abstract/summary → introduction/background → core content → results/findings → limitations/caveats.
3. **Extract structured information**:
   - Problem setting and motivation
   - Core contribution or main argument
   - Method, approach, or pipeline
   - Data sources, metrics, baselines (if applicable)
   - Main results and evidence quality
   - Limitations and risks acknowledged by the authors
4. **Separate author claims from your own inference**. Mark each extracted point as "author stated" or "inferred".
5. **When the document is incomplete or noisy**, say so explicitly and avoid overclaiming.
6. **Cite specific sections or page references** when quoting from the document.

## Output Preference

- **Metadata block**: title, authors, source, date
- **Core argument** (1-3 sentences)
- **Method / approach breakdown**
- **Key findings / evidence** (with section references)
- **Limitations** (author-stated + your observed)
- **Relevance assessment**: how this connects to the user's research question

## Quality Rules

- Do not invent findings that aren't in the document.
- Flag sections that were unreadable or missing.
- For technical papers, prefer quantitative claims over qualitative summaries.
- If the document is not academic (blog post, tutorial, documentation), adapt the extraction: focus on factual claims and instructions rather than "method" and "experiments".
