<div align="center">

# ReceiptLedger

**Turning physical receipt photos into structured, categorized spending intelligence.**

[![Course](https://img.shields.io/badge/Course-SPM--458-4F46E5?style=flat-square)](docs/course-materials/assignments/)
[![Institution](https://img.shields.io/badge/Institution-University%20of%20Karachi-0D9488?style=flat-square)](https://uok.edu.pk/)
[![Semester](https://img.shields.io/badge/Semester-4th%20Semester-0284C7?style=flat-square)](docs/course-materials/lectures/)
[![Lifecycle](https://img.shields.io/badge/Lifecycle-3--Week%20Sprints-F59E0B?style=flat-square)](docs/specifications/07_SPRINT_PLAN_3WEEKS.md)
[![Tooling](https://img.shields.io/badge/Tooling-Jira%20%7C%20Slack-6366F1?style=flat-square&logo=jira&logoColor=white)](docs/project-management/ReceiptLedger_SoW_v3.pdf)

<p align="center">
  <img src="https://img.shields.io/badge/Flutter-02569B?style=flat-square&logo=flutter&logoColor=white" alt="Flutter" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white" alt="OpenCV" />
  <img src="https://img.shields.io/badge/Google%20Cloud-4285F4?style=flat-square&logo=googlecloud&logoColor=white" alt="Google Cloud" />
  <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white" alt="Supabase" />
  <img src="https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB" alt="React" />
  <img src="https://img.shields.io/badge/Google%20Stitch-EA4335?style=flat-square&logo=google&logoColor=white" alt="Google Stitch" />
  <img src="https://img.shields.io/badge/Jira-0052CC?style=flat-square&logo=jira&logoColor=white" alt="Jira" />
  <img src="https://img.shields.io/badge/Slack-4A154B?style=flat-square&logo=slack&logoColor=white" alt="Slack" />
</p>

</div>

---

## Overview

Tracking cash expenditures across households and small businesses is hindered by loose, mixed receipts—ranging from printed supermarket invoices to informal handwritten corner-store (*kiryana*) slips. Manual ledger entry is friction-heavy and consistently abandoned.

**ReceiptLedger** provides an automated ingestion and analytics pipeline: photograph any physical receipt on mobile, extract line items and costs via specialized OCR paths, normalize merchant naming, classify items into local spending categories, and visualize monthly trends on an interactive dashboard.

---

## End-to-End Workflow

```mermaid
flowchart LR
    A["Paper Receipt<br/>(Printed / Handwritten)"] --> B["Mobile Capture &<br/>Edge Correction"]
    B --> C{"OCR Router"}
    C -->|"Printed Slip"| D1["Cloud Vision API /<br/>Tesseract"]
    C -->|"Handwritten Note"| D2["EasyOCR Engine &<br/>Binarization"]
    D1 --> E["Item Normalization &<br/>Fuzzy Matcher"]
    D2 --> E
    E --> F["Deduplication &<br/>Rule Categorizer"]
    F --> G[("PostgreSQL Ledger<br/>(Supabase)")]
    G --> H["Analytics Dashboard &<br/>Review Queue"]

    style A fill:#1E293B,stroke:#475569,stroke-width:1px,color:#F8FAFC
    style B fill:#0F766E,stroke:#14B8A6,stroke-width:1px,color:#F0FDFA
    style C fill:#1D4ED8,stroke:#3B82F6,stroke-width:1px,color:#EFF6FF
    style D1 fill:#4338CA,stroke:#6366F1,stroke-width:1px,color:#EEF2FF
    style D2 fill:#6D28D9,stroke:#8B5CF6,stroke-width:1px,color:#F5F3FF
    style E fill:#B45309,stroke:#F59E0B,stroke-width:1px,color:#FFFBEB
    style F fill:#047857,stroke:#10B981,stroke-width:1px,color:#ECFDF5
    style G fill:#334155,stroke:#64748B,stroke-width:1px,color:#F8FAFC
    style H fill:#0369A1,stroke:#0284C7,stroke-width:1px,color:#F0F9FF
```

---

## Core Capabilities

| Subsystem | Stack / Tool | Scope |
|:---|:---:|:---|
| ![Mobile](https://img.shields.io/badge/Mobile-Capture%20Client-0284C7?style=flat-square&logo=flutter&logoColor=white) | Flutter | Single and batch receipt photo capture with edge preview and perspective deskewing. |
| ![Design](https://img.shields.io/badge/Design-UI%20Mockups-EA4335?style=flat-square&logo=google&logoColor=white) | Google Stitch | Interface wireframing, component mockups, and mobile UX design system. |
| ![Printed OCR](https://img.shields.io/badge/OCR-Printed%20Path-4F46E5?style=flat-square&logo=googlecloud&logoColor=white) | Cloud Vision API / Tesseract | High-accuracy text and pricing extraction from structured retail register receipts. |
| ![Handwritten OCR](https://img.shields.io/badge/OCR-Handwritten%20Path-7C3AED?style=flat-square&logo=python&logoColor=white) | EasyOCR + OpenCV | Character and numeric extraction tailored for informal small-shop receipts. |
| ![Normalization](https://img.shields.io/badge/NLP-Normalization-D97706?style=flat-square) | Levenshtein Matcher | Mapping colloquial names and local units into canonical retail items. |
| ![Deduplication](https://img.shields.io/badge/Security-Deduplication-E11D48?style=flat-square) | 64-bit pHash + SHA-256 | Preventing double-counting via visual hashing and metadata comparison. |
| ![Categorization](https://img.shields.io/badge/Rules-Categorization-059669?style=flat-square) | Priority Rule Engine | Auto-sorting purchases into household spending categories (groceries, utilities, etc.). |
| ![Dashboard](https://img.shields.io/badge/Web-Analytics%20Dashboard-0891B2?style=flat-square&logo=react&logoColor=white) | React + Chart.js | Visualizing monthly spend, category distribution, and human-in-the-loop review queue. |

---

## Project Boundaries

### ![In Scope](https://img.shields.io/badge/Scope-In--Scope-10B981?style=flat-square)
* **Mobile Ingestion:** Guided camera capture for single or multiple receipts.
* **Dual Text Extraction:** Separate processing pipelines for printed retail receipts and handwritten slips.
* **Item Standardization:** Canonical dictionary mapping for local product names and pack units.
* **Automated Categorization:** Rule-based tagging across common household expense categories.
* **Duplicate Detection:** Visual and textual validation against re-uploaded slips.
* **Spending Dashboard:**
  * Month-over-month expenditure comparison and variance tracking.
  * Category breakdown charts and multi-month spend velocity.
  * Filterable historical receipt ledger and item drill-down.
  * Review queue for verifying items with OCR confidence $< 0.85$.

### ![Out of Scope](https://img.shields.io/badge/Scope-Out--of--Scope-EF4444?style=flat-square)
* Direct bank account integration or card statement reconciliation.
* Tax computation, GST filing, or legal invoice generation.
* Generic corporate categorization outside common consumer and retail goods.
* Training custom machine learning models from scratch.

---

## Repository Modules

| Module | Purpose | Stack |
|:---|:---|:---:|
| [`backend/`](backend/) | Core OCR routing, OpenCV deskewing, normalization, and API gateway | FastAPI • OpenCV • EasyOCR |
| [`mobile/`](mobile/) | Camera capture client, edge alignment preview, and image upload | Flutter • Dart • Google Stitch |
| [`web/`](web/) | Analytics dashboard, monthly trend charts, and review queue | React • Vite • Chart.js |
| [`docs/`](docs/) | Complete engineering specifications, IEEE 830 SRS, and course governance | Markdown • Mermaid |
| [`data/`](data/) | Sample receipt collection repository and local item taxonomy dictionary | Dataset • JSON |

---

## Documentation

Master documentation index and governance deliverables are cataloged in [`docs/README.md`](docs/README.md).

### Core Specifications Suite ([`docs/specifications/`](docs/specifications/))

| Document | Summary |
|:---|:---|
| [**PRD**](docs/specifications/01_PRD.md) | Vision, target personas, and functional priority matrix |
| [**SRS**](docs/specifications/02_SRS.md) | IEEE 830 functional/non-functional requirements and API schemas |
| [**SDS**](docs/specifications/03_SDS.md) | Subsystem architecture, pipeline routing, and sequence flows |
| [**DFD**](docs/specifications/04_DFD.md) | Level 0 Context Model and Level 1 Functional Decomposition |
| [**ERD**](docs/specifications/05_ERD.md) | 3NF relational database schema and PostgreSQL/Supabase DDL |
| [**Semantic Networks**](docs/specifications/06_SEMANTIC_NETS.md) | Domain knowledge graphs, local item taxonomies, and unit hierarchies |
| [**3-Week Sprint Plan**](docs/specifications/07_SPRINT_PLAN_3WEEKS.md) | Compressed sprint timeline, backlog tickets, and exit criteria |
| [**Environment Setup**](docs/specifications/08_ENVIRONMENT_SETUP.md) | Prerequisites, local virtualenv, Node, Flutter, and Docker setup |
| [**Development Plan**](docs/specifications/09_DEVELOPMENT_PLAN.md) | In-depth engineering implementation roadmap and algorithmic specs |
| [**Division of Work**](docs/specifications/10_DIVISION_OF_WORK.md) | Official 6-role allocations, responsibilities, and pairing streams |

### Engineering Guides & UI/UX Briefs

| Document | Summary | Artifacts |
|:---|:---|:---:|
| [**Backend Operations Guide**](docs/guides/BACKEND_SETUP_AND_OPERATIONS_GUIDE.md) | Cloud Vision, Supabase, Tesseract setup, test suite & cURL reference | Markdown |
| [**Dashboard Integration Guide**](docs/guides/DASHBOARD_BACKEND_INTEGRATION.md) | Monorepo API wiring, CORS rules, and development server guide | Markdown |
| [**Mobile UI/UX Design Brief**](docs/design/MOBILE_DESIGN_BRIEF.md) | Stitch prompts, mobile screen wireframes, themes & design rules | [PDF](docs/design/ReceiptLedger_UI_UX_Design_Brief.pdf) |
| [**Dashboard Design Brief**](docs/design/DASHBOARD_DESIGN_BRIEF.md) | Desktop triage desk layout, keyboard ergonomics, API schemas | [PDF](docs/design/ReceiptLedger_Dashboard_Design_Brief.pdf) |

---

## Project Team

<div align="center">
<table>
  <tr>
    <td align="center" width="33%"><a href="https://github.com/Aazmeer30"><img src="https://ui-avatars.com/api/?name=Aazmeer+Faridy&background=4F46E5&color=fff&size=100&bold=true&rounded=true" width="56" alt="Aazmeer Sarfaraz Faridy" /></a></td>
    <td align="center" width="33%"><a href="https://github.com/Arish026"><img src="https://ui-avatars.com/api/?name=Arish+Khan&background=0D9488&color=fff&size=100&bold=true&rounded=true" width="56" alt="Arish Ahmed Khan" /></a></td>
    <td align="center" width="33%"><a href="https://github.com/Imanh728"><img src="https://ui-avatars.com/api/?name=Iman+Hussain&background=0284C7&color=fff&size=100&bold=true&rounded=true" width="56" alt="Iman Hussain" /></a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/Aazmeer30"><b>Aazmeer Sarfaraz Faridy</b></a></td>
    <td align="center"><a href="https://github.com/Arish026"><b>Arish Ahmed Khan</b></a></td>
    <td align="center"><a href="https://github.com/Imanh728"><b>Iman Hussain</b></a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/Aazmeer30"><img src="https://img.shields.io/badge/Roll-B24110006002-4F46E5?style=flat-square" alt="B24110006002" /></a></td>
    <td align="center"><a href="https://github.com/Arish026"><img src="https://img.shields.io/badge/Roll-B24110006026-0D9488?style=flat-square" alt="B24110006026" /></a></td>
    <td align="center"><a href="https://github.com/Imanh728"><img src="https://img.shields.io/badge/Roll-B24110006054-0284C7?style=flat-square" alt="B24110006054" /></a></td>
  </tr>
  <tr>
    <td align="center" width="33%"><a href="https://github.com/Asad101001"><img src="https://ui-avatars.com/api/?name=Muhammad+Asad&background=2563EB&color=fff&size=100&bold=true&rounded=true" width="56" alt="Muhammad Asad Khan" /></a></td>
    <td align="center" width="33%"><a href="https://github.com/Aun2005"><img src="https://ui-avatars.com/api/?name=Aun+Shamsi&background=7C3AED&color=fff&size=100&bold=true&rounded=true" width="56" alt="Syed Aun Shamsi" /></a></td>
    <td align="center" width="33%"><a href="https://github.com/zainab251251"><img src="https://ui-avatars.com/api/?name=Zainab+Hashmi&background=DB2777&color=fff&size=100&bold=true&rounded=true" width="56" alt="Zainab Hashmi" /></a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/Asad101001"><b>Muhammad Asad Khan</b></a></td>
    <td align="center"><a href="https://github.com/Aun2005"><b>Syed Aun Shamsi</b></a></td>
    <td align="center"><a href="https://github.com/zainab251251"><b>Zainab Hashmi</b></a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/Asad101001"><img src="https://img.shields.io/badge/Roll-B24110006087-2563EB?style=flat-square" alt="B24110006087" /></a></td>
    <td align="center"><a href="https://github.com/Aun2005"><img src="https://img.shields.io/badge/Roll-B24110006134-7C3AED?style=flat-square" alt="B24110006134" /></a></td>
    <td align="center"><a href="https://github.com/zainab251251"><img src="https://img.shields.io/badge/Roll-B24110006162-DB2777?style=flat-square" alt="B24110006162" /></a></td>
  </tr>
</table>
</div>

---

<div align="center">
  <sub>Software Project Management (SPM-458) • Department of Computer Science • University of Karachi</sub>
</div>
