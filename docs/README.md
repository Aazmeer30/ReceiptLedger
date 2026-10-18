<div align="center">

# ReceiptLedger / Master Documentation & Governance Portal

**Official Academic Deliverables, PMBOK Artifacts, Technical Specifications, and UI/UX Design Briefs.**

[![Course](https://img.shields.io/badge/Course-SPM--458-4F46E5?style=flat-square)](course-materials/assignments/)
[![Evaluator](https://img.shields.io/badge/Instructor-Humera%20Azam-0D9488?style=flat-square)](https://uok.edu.pk/)
[![Lifecycle](https://img.shields.io/badge/Lifecycle-3--Week%20Sprints-F59E0B?style=flat-square)](specifications/07_SPRINT_PLAN_3WEEKS.md)
[![Design Briefs](https://img.shields.io/badge/UI%2FUX-Design%20Briefs-EC4899?style=flat-square)](design/)

</div>

---

## Directory Organization

```text
docs/
├── README.md                      # Master Documentation Catalog (this file)
│
├── assets/                        # Design assets and screenshots
│   └── barebones_screenshots/     # Flutter prototype capture screens
│
├── course-materials/              # Academic curriculum reference
│   ├── assignments/               # Course assignments 1, 2, 3 & Lab Activity 4
│   └── lectures/                  # SPM-458 Lecture slides (Weeks 2, 3, 4)
│
├── design/                        # UI/UX design specifications & compiled PDFs
│   ├── MOBILE_DESIGN_BRIEF.md     # Mobile Flutter UI/UX Master Specification
│   ├── DASHBOARD_DESIGN_BRIEF.md  # Web Operations Console & Triage Brief
│   ├── ReceiptLedger_UI_UX_Design_Brief.pdf      # Compiled Mobile Design Brief
│   └── ReceiptLedger_Dashboard_Design_Brief.pdf  # Compiled Web Console Design Brief
│
├── guides/                        # System setup and developer integration manuals
│   ├── BACKEND_SETUP_AND_OPERATIONS_GUIDE.md     # OCR engines, Supabase, tests & cURL
│   └── DASHBOARD_BACKEND_INTEGRATION.md          # Monorepo Web + Backend API wiring
│
├── project-management/            # Approved SPM Governance Deliverables
│   ├── ReceiptLedger_Project_Charter.pdf         # Official project charter
│   ├── ReceiptLedger_SoW.pdf                     # Original Scope of Work
│   ├── ReceiptLedger_SoW_v3.pdf                  # Latest baseline (6 compressed sprints)
│   └── ReceiptLedger_Division_of_Work.pdf        # Approved team work division
│
└── specifications/                # IEEE 830 & Technical Specification Suite
    ├── 01_PRD.md                  # Product Requirements Document
    ├── 02_SRS.md                  # Software Requirements Specification (IEEE 830)
    ├── 03_SDS.md                  # Software Design Specification (Architecture)
    ├── 04_DFD.md                  # Data Flow Diagrams (Context & Level 1)
    ├── 05_ERD.md                  # Entity Relationship Diagram & 3NF Schema
    ├── 06_SEMANTIC_NETS.md        # Semantic Networks (Domain Taxonomies)
    ├── 07_SPRINT_PLAN_3WEEKS.md   # 3-Week Sprint Execution Plan
    ├── 08_ENVIRONMENT_SETUP.md    # Developer Workstation Setup Guide
    ├── 09_DEVELOPMENT_PLAN.md     # In-Depth Engineering Implementation Plan
    └── 10_DIVISION_OF_WORK.md     # Official Team Roles & Working Streams
```

---

## 1. Technical Specification Suite

All core engineering specifications follow industry and academic standards (IEEE 830, Gane-Sarson, 3NF):

| Document | Focus Area | Standard / Model |
|:---|:---|:---:|
| [**01. PRD**](specifications/01_PRD.md) | Problem statement, user personas, journeys, functional priority matrix | Agile PRD |
| [**02. SRS**](specifications/02_SRS.md) | Formal system requirements, API endpoints, non-functional quality attributes | IEEE 830-1998 |
| [**03. SDS**](specifications/03_SDS.md) | Subsystem decomposition, sequence diagrams, failure recovery modes | Architecture |
| [**04. DFD**](specifications/04_DFD.md) | Level 0 Context Model and Level 1 Functional Decomposition | Gane-Sarson / Mermaid |
| [**05. ERD**](specifications/05_ERD.md) | 3NF relational schema, PostgreSQL / Supabase DDL migrations | Relational / Mermaid |
| [**06. Semantic Networks**](specifications/06_SEMANTIC_NETS.md) | Domain knowledge graphs, local retail taxonomies, unit graphs | Knowledge Representation |
| [**07. 3-Week Sprint Plan**](specifications/07_SPRINT_PLAN_3WEEKS.md) | Compressed delivery schedule, user stories, exit criteria | Agile Scrum |
| [**08. Environment Setup**](specifications/08_ENVIRONMENT_SETUP.md) | Prerequisites, local virtualenv, Node, Flutter, and Docker setup | Developer Guide |
| [**09. Development Plan**](specifications/09_DEVELOPMENT_PLAN.md) | Deep technical implementation plan, algorithms, and day-by-day tasks | Engineering Plan |
| [**10. Division of Work**](specifications/10_DIVISION_OF_WORK.md) | Official 6-role allocations, responsibilities, and pairing streams | Team Governance |

---

## 2. UI/UX Design Briefs & Printable PDFs

Comprehensive visual design briefs with embedded prototype screenshots, design system constraints, color palettes, and ready-to-use Google Stitch prompts:

| Brief | Target Platform | Focus Area | Deliverables |
|:---|:---:|:---|:---:|
| [**Mobile UI/UX Design Brief**](design/MOBILE_DESIGN_BRIEF.md) | Flutter (iOS & Android) | Homescreen icon, profile drawer, capture screen, review queue & Stark B&W theme | [📄 Download PDF](design/ReceiptLedger_UI_UX_Design_Brief.pdf) |
| [**Web Dashboard Design Brief**](design/DASHBOARD_DESIGN_BRIEF.md) | React 18 + Vite (Desktop) | 50/50 triage desk layout, keyboard ergonomics, audit ledger & API payloads | [📄 Download PDF](design/ReceiptLedger_Dashboard_Design_Brief.pdf) |

---

## 3. Engineering & Operations Guides

Hands-on manuals for setting up cloud infrastructure, running local verification suites, and configuring client-backend integration:

| Guide | Scope | Key Topics |
|:---|:---|:---|
| [**Backend Operations Guide**](guides/BACKEND_SETUP_AND_OPERATIONS_GUIDE.md) | Backend Core Engine | Google Cloud Vision API credentials, Supabase PostgreSQL DDL, Tesseract 5 installation, 32-test offline CLI suite (`python -m app.cli_test`), and cURL testing guide |
| [**Dashboard Integration Guide**](guides/DASHBOARD_BACKEND_INTEGRATION.md) | Web Client + API | Fast-start local server launch, CORS origin configuration, Review Queue endpoints, and Swagger UI reference |

---

## 4. Project Governance Deliverables

Formal Software Project Management (SPM-458) approved artifacts:

| Deliverable | Format | Description |
|:---|:---:|:---|
| [**ReceiptLedger Project Charter**](project-management/ReceiptLedger_Project_Charter.pdf) | PDF | Project justification, measurable objectives, initial stakeholder register, and sign-off |
| [**Scope of Work (SoW v3)**](project-management/ReceiptLedger_SoW_v3.pdf) | PDF | Approved baseline covering in-scope capabilities, acceptance benchmarks, and 6-sprint cadence |
| [**Original SoW**](project-management/ReceiptLedger_SoW.pdf) | PDF | Initial project scope proposal prior to sprint compression |
| [**Team Division of Work**](project-management/ReceiptLedger_Division_of_Work.pdf) | PDF | Approved role distribution among team members and accountability matrix |

---

## 5. Course Reference Materials

Academic course assignments and lecture slides for SPM-458:

* **Assignments**: [`course-materials/assignments/`](course-materials/assignments/)
  * `Assignment #1.pdf`
  * `Assignment #2.pdf`
  * `Assignment #3.pdf`
  * `Home_Baesd_Activity_04.pdf`
* **Lectures**: [`course-materials/lectures/`](course-materials/lectures/)
  * `Week 02.pdf`
  * `Week 03.pdf`
  * `Week 04.pdf`
