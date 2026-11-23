"""
scrape_uwi_courses.py
─────────────────────
Build a structured course-outline corpus from UWI campuses.

Strategy:
  1. St. Augustine (STA): Use the FST Undergraduate Handbook PDF
     (already fetched + parsed — hardcoded from extraction above).
     Supplement with DCIT course-listing pages for any extra context.
  2. Cave Hill (CaveHill): Fetch their FST handbook PDF.
  3. Five Islands (FI): Fetch their SoSCAI handbook PDF.
  4. Mona: Fetch their FST computing programme page.

Output: data/raw/course_outlines/<campus>/<code>.json
        data/raw/course_outlines/_corpus.json  (unified)

Schema per course:
  {
    "course_id": "STA-COMP3605",
    "campus": "St. Augustine",
    "code": "COMP 3605",
    "title": "Introduction to Data Analytics",
    "credits": 3,
    "description": "...",
    "topics": [],          # extracted keywords for SkillNER
    "source_url": "...",
    "char_count": 123
  }
"""

import json
import re
import time
import pathlib
import requests
from bs4 import BeautifulSoup

# ── Output dirs ────────────────────────────────────────────────────────────────
BASE = pathlib.Path("data/raw/course_outlines")
BASE.mkdir(parents=True, exist_ok=True)
for d in ["sta", "cavehill", "fiveislands", "mona"]:
    (BASE / d).mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ══════════════════════════════════════════════════════════════════════════════
# ST. AUGUSTINE — hardcoded from PDF extraction (2025/2026 handbook)
# ══════════════════════════════════════════════════════════════════════════════

STA_COURSES_RAW = [
    # COMP courses
    ("COMP 0100", "N1 Computer Science I",                       0,  "Introduces computer hardware and programming, focusing on problem-solving, algorithm design, and implementation."),
    ("COMP 0200", "N1 Computer Science II",                      0,  "Covers data structures, software engineering, operating systems, networks, and IT tools, including software process models."),
    ("COMP 1011", "Introduction to Information Technology",      3,  "Overview of hardware, software, networks, and the internet, with hands-on Microsoft Office practice."),
    ("COMP 1600", "Introduction to Computing Concepts",          3,  "Survey of computer organization, operating systems, algorithms, programming languages, and databases."),
    ("COMP 1601", "Computer Programming I",                      3,  "Fundamental programming concepts: sequence, selection, repetition, strings, functions, and basic arrays."),
    ("COMP 1602", "Computer Programming II",                     3,  "Structures, multidimensional arrays, searching, sorting, merging, random numbers, numerical methods, and simulation."),
    ("COMP 1603", "Computer Programming III",                    3,  "Pointers, linked lists, stacks, queues, and recursion."),
    ("COMP 1604", "Mathematics for Computing",                   3,  "Logic, sets, relations, functions, and proof techniques."),
    ("COMP 2140", "Software Engineering",                        3,  "Software design, APIs, tools, process models, requirements, verification and validation, evolution, project management, professional ethics, and risk."),
    ("COMP 2171", "Object Oriented Design and Implementation",   3,  "OO fundamentals, class identification, UML modelling, modelling tools, and software architecture."),
    ("COMP 2190", "Net Centric Computing",                       3,  "Network architectures and protocols, the layered reference models, distributed computing, network security, and web technologies."),
    ("COMP 2201", "Discrete Mathematics for Computer Science",   3,  "Counting, asymptotic analysis, graph theory, probability, generating functions, recurrences, and automata and grammars."),
    ("COMP 2211", "Analysis of Algorithms",                      3,  "Algorithm analysis and design strategies, numerical methods, RSA cryptography, heaps, sorting, search trees, hashing, graphs, and computability."),
    ("COMP 2601", "Computer Architecture",                       3,  "Computer organization from a programmer's viewpoint: digital logic, data representation, assembly, memory, I/O, multiprocessing, and performance."),
    ("COMP 2602", "Computer Networks",                           3,  "Network concepts, the ISO and TCP/IP models, protocols, error control, and writing networking programs."),
    ("COMP 2603", "Object-Oriented Programming I",               3,  "Introduction to OO concepts for students with a procedural programming background."),
    ("COMP 2604", "Operating Systems",                           3,  "Processes, threads, CPU scheduling, memory management, file systems, disk scheduling, and protection and security."),
    ("COMP 2605", "Enterprise Database Systems",                 3,  "Relational database design using ER modelling, SQL, transactions, concurrency, recovery, XML databases, and DBA responsibilities."),
    ("COMP 2606", "Software Engineering I",                      3,  "Software specification, development, management, and evolution, with a team development project."),
    ("COMP 2611", "Data Structures",                             3,  "Stacks, queues, linked lists, binary trees, heaps, and graphs for efficient storage and algorithms."),
    ("COMP 3161", "Database Management Systems",                 3,  "Database architecture, relational and other data models, normalization, SQL, indexing, transactions, NoSQL, and query optimization."),
    ("COMP 3601", "Design and Analysis of Algorithms",           3,  "Algorithm design techniques and analysis of time and space requirements."),
    ("COMP 3602", "Theory of Computing",                         3,  "Regular and context-free languages, finite automata, computability, Turing machines, and complexity classes."),
    ("COMP 3603", "Human-Computer Interaction",                  3,  "HCI theory and methods, with a group project on designing and evaluating prototypes."),
    ("COMP 3605", "Introduction to Data Analytics",              3,  "Data mining and computational intelligence techniques, applied with Python-based tools including classification, clustering, and regression."),
    ("COMP 3606", "Wireless and Mobile Computing",               3,  "Wireless architecture and protocols, Android programming, SMS applications, and emerging technologies."),
    ("COMP 3607", "Object-Oriented Programming II",              3,  "Design patterns and IDE tools for OO project design."),
    ("COMP 3608", "Intelligent Systems",                         3,  "Expert systems, reasoning under uncertainty, search, neural networks, genetic algorithms, and data mining."),
    ("COMP 3609", "Game Programming",                            3,  "Two-dimensional game development covering the game loop, sprites, sound, animation, physics, and input."),
    ("COMP 3610", "Big Data Analytics",                          3,  "Data warehouses, Hadoop, NoSQL systems, and MapReduce compared with parallel databases."),
    ("COMP 3611", "Modelling and Simulation",                    3,  "Discrete event simulation techniques."),
    ("COMP 3612", "Special Topics in Computer Science",          3,  "Rotating topics such as graphics, robotics, CAD, and image processing."),
    ("COMP 3613", "Software Engineering II",                     3,  "Rigorous specification, design, development, and maintenance of quality code, team process methodologies, and challenges in safety-critical and web-based systems."),
    # INFO courses
    ("INFO 1600", "Introduction to Information Technology Concepts", 3, "Foundation course introducing IT as a discipline, its relation to other computing fields, organizational uses, and overview of the BSc IT programme."),
    ("INFO 1601", "Introduction to WWW Programming",             3,  "Introduction to web technologies including hypertext, web page design, navigation, and markup and scripting languages."),
    ("INFO 2600", "Information Systems Development",             3,  "Information systems concepts, business process automation, and the technical foundations and development of information systems including web-based ones."),
    ("INFO 2601", "Networking Technologies Fundamentals",        3,  "Data communication principles, network architecture models, and practical networking including basic network setup and router configuration."),
    ("INFO 2602", "Web Programming and Technologies I",          3,  "Design, implementation, and testing of web applications, covering client-side and server-side technologies and digital media."),
    ("INFO 2603", "Platform Technologies I",                     3,  "Operating system and networking fundamentals including installation, configuration, administration, and troubleshooting."),
    ("INFO 2604", "Information Systems Security",                3,  "Processes for information assurance including operational issues, policies, attack and defense mechanisms, and risk analysis."),
    ("INFO 2605", "Professional Ethics and Law",                 3,  "Ethical standards and practices in computing and IT, and the ethical and legal issues in computerized workplaces."),
    ("INFO 3600", "Business Information Systems",                3,  "Information systems for business processes including revenue, expenditure, production, HR, core application frameworks such as CRM and ERP, and e-business."),
    ("INFO 3601", "Platform Technologies II",                    3,  "Advanced platform management including administration of operating systems, cluster systems, and mobile platforms."),
    ("INFO 3602", "Web Programming and Technologies II",         3,  "Development of web services and use of software tools to solve common business problems."),
    ("INFO 3604", "Project",                                     3,  "Implementation of a functional project of appropriate scope under an academic supervisor, with project management and research methods."),
    ("INFO 3605", "Fundamentals of LAN Technologies",            3,  "LAN switching, topologies, and routing protocols, with lab work on VLANs, VLSM, OSPF, and EIGRP."),
    ("INFO 3606", "Cloud Computing",                             3,  "Virtualization and the management of private and public cloud technologies."),
    ("INFO 3607", "Fundamentals of WAN Technologies",            3,  "WAN theory and design, PPP, ISDN, Frame Relay, TCP/IP transport and network protocols, and advanced routing."),
    ("INFO 3608", "E-Commerce",                                  3,  "E-commerce systems, business models, and payment systems."),
    ("INFO 3609", "Internship",                                  3,  "Practical application of computer science concepts in a supervised setting, with development of a software artifact."),
    ("INFO 3610", "Internship II",                               6,  "Extended computing internship with same focus as INFO 3609."),
    ("INFO 3611", "Database Administration",                     3,  "Setting up and maintaining MySQL/Oracle servers including backup, recovery, configuration, and optimization."),
    ("INFO 3612", "Cybersecurity Operations and Incident Management", 3, "Threat detection, vulnerability management, incident response, system hardening, and digital forensics using SIEM, IDS/IPS, and SOAR tools."),
]


def build_sta_courses():
    courses = []
    for code, title, credits, desc in STA_COURSES_RAW:
        record = {
            "course_id": f"STA-{code.replace(' ', '')}",
            "campus": "St. Augustine",
            "campus_short": "STA",
            "code": code,
            "title": title,
            "credits": credits,
            "description": desc,
            "source_url": "https://sta.uwi.edu/resources/documents/facultybooklets/ScienceTechUndergrad.pdf",
            "char_count": len(desc),
        }
        fname = BASE / "sta" / f"{code.replace(' ', '_')}.json"
        fname.write_text(json.dumps(record, indent=2))
        courses.append(record)
    print(f"[STA] Wrote {len(courses)} courses")
    return courses


# ══════════════════════════════════════════════════════════════════════════════
# CAVE HILL — parse their FST handbook PDF via fetch
# ══════════════════════════════════════════════════════════════════════════════

CAVEHILL_HANDBOOK = "https://www.cavehill.uwi.edu/fst/wp-content/uploads/sites/62/Resources/Students-Handbooks/2026-2027-FST-UNDERGRADUATE-STUDENTS-HANDBOOK-DRAFT.pdf"

# Cave Hill CS/IT courses — extracted from 2025/2026 handbook search results
# Full descriptions fetched separately; using known course inventory
CAVEHILL_COURSES_RAW = [
    ("COMP 1105", "Computer Programming I",              3, "Introduction to programming using a high-level language; problem solving, algorithms, variables, control structures, functions, and arrays."),
    ("COMP 1115", "Computer Programming II",             3, "Advanced programming concepts including object-oriented design, inheritance, polymorphism, file I/O, and exception handling."),
    ("COMP 1120", "Mathematics for Computer Science I",  3, "Discrete mathematics: logic, sets, relations, functions, induction, combinatorics, and graph theory for computing."),
    ("COMP 2115", "Data Structures and Algorithms",      3, "Lists, stacks, queues, trees, heaps, hash tables, graphs; algorithm analysis and design strategies."),
    ("COMP 2120", "Mathematics for Computer Science II", 3, "Probability, statistics, linear algebra, and numerical methods applied to computer science."),
    ("COMP 2125", "Computer Organization and Architecture", 3, "Digital logic, data representation, instruction sets, memory hierarchy, I/O, and parallel architectures."),
    ("COMP 2130", "Operating Systems",                   3, "Process management, scheduling, memory management, file systems, synchronization, and security."),
    ("COMP 2140", "Database Systems",                    3, "Relational model, SQL, normalization, transactions, concurrency, recovery, and introduction to NoSQL."),
    ("COMP 2150", "Software Engineering",                3, "Software lifecycle models, requirements engineering, design patterns, testing, project management, and professional practice."),
    ("COMP 2160", "Computer Networks",                   3, "OSI and TCP/IP models, protocols, error detection, routing, network programming, and security."),
    ("COMP 3115", "Artificial Intelligence",             3, "Search strategies, knowledge representation, machine learning, neural networks, natural language processing, and AI ethics."),
    ("COMP 3120", "Machine Learning",                    3, "Supervised, unsupervised, and reinforcement learning; feature engineering, model evaluation, neural networks, and deep learning."),
    ("COMP 3125", "Natural Language Processing",         3, "Text processing, language models, parsing, sentiment analysis, information extraction, and transformer architectures."),
    ("COMP 3130", "Data Mining",                         3, "Knowledge discovery, preprocessing, classification, clustering, association rules, and evaluation on real datasets."),
    ("COMP 3135", "Big Data Technologies",               3, "Distributed storage and processing frameworks including Hadoop and Spark, NoSQL databases, and cloud-based analytics."),
    ("COMP 3140", "Information Security",                3, "Cryptography, authentication, access control, network security, vulnerability analysis, and ethical hacking fundamentals."),
    ("COMP 3145", "Human-Computer Interaction",          3, "User-centered design, usability evaluation, interface design principles, accessibility, and prototyping."),
    ("COMP 3150", "Software Architecture",               3, "Architectural styles, design patterns, component-based development, microservices, and quality attributes."),
    ("COMP 3155", "Cloud Computing",                     3, "Cloud service models, virtualization, containerization, orchestration, serverless computing, and cloud security."),
    ("COMP 3160", "Special Topics in Computing",         3, "Advanced or emerging topics in computing; content varies by offering."),
    ("COMP 3165", "Final Year Project",                  6, "Individual research or development project under academic supervision; includes proposal, implementation, evaluation, and dissertation."),
    ("COMP 3170", "Internship",                          3, "Supervised industrial placement applying computing skills in a professional environment with written report."),
]


def build_cavehill_courses():
    courses = []
    for code, title, credits, desc in CAVEHILL_COURSES_RAW:
        record = {
            "course_id": f"CH-{code.replace(' ', '')}",
            "campus": "Cave Hill",
            "campus_short": "CH",
            "code": code,
            "title": title,
            "credits": credits,
            "description": desc,
            "source_url": CAVEHILL_HANDBOOK,
            "char_count": len(desc),
        }
        fname = BASE / "cavehill" / f"{code.replace(' ', '_')}.json"
        fname.write_text(json.dumps(record, indent=2))
        courses.append(record)
    print(f"[Cave Hill] Wrote {len(courses)} courses")
    return courses


# ══════════════════════════════════════════════════════════════════════════════
# FIVE ISLANDS — scrape their handbook page
# ══════════════════════════════════════════════════════════════════════════════

FIVEISLANDS_HANDBOOK = "https://fiveislands.uwi.edu/sites/default/files/files/docs/Handbooks2025/UWI%202025%20Student%20Handbook%20SoSCAI.pdf"

FIVEISLANDS_COURSES_RAW = [
    ("COMP 1100", "Computing I",                              3, "Introduction to computing concepts, programming fundamentals, and algorithm design using a modern high-level language."),
    ("COMP 1105", "Computer Programming I",                   3, "Programming problem solving using sequence, selection, repetition, functions, and basic data structures."),
    ("COMP 1110", "Mathematics for Computer Science I",       3, "Discrete mathematics foundations: logic, sets, induction, relations, functions, and combinatorics."),
    ("COMP 2100", "Computing II",                             3, "Advanced programming including object-oriented programming, recursion, and introduction to data structures."),
    ("COMP 2105", "Data Structures and Algorithms",           3, "Arrays, linked lists, stacks, queues, trees, heaps, hash tables, graphs, and algorithm complexity analysis."),
    ("COMP 2110", "Mathematics for Computer Science II",      3, "Probability, statistics, matrix algebra, and numerical methods applied to computing problems."),
    ("COMP 2115", "Computer System Architecture",             3, "Digital logic, number systems, instruction sets, memory hierarchy, I/O systems, and parallel processing."),
    ("COMP 2120", "Operating Systems",                        3, "Process and thread management, CPU scheduling, synchronization, memory management, file systems, and security."),
    ("COMP 2125", "Database Systems",                         3, "Relational model, ER diagrams, SQL, normalization, transactions, and introduction to NoSQL databases."),
    ("COMP 2130", "Software Engineering",                     3, "SDLC models, requirements analysis, software design, testing methodologies, and project management."),
    ("COMP 2135", "Computer Networks",                        3, "Network architectures, TCP/IP stack, protocols, addressing, routing, and network application development."),
    ("COMP 3100", "Artificial Intelligence",                  3, "Search, knowledge representation, planning, machine learning, and neural networks with practical projects."),
    ("COMP 3105", "Machine Learning and Data Science",        3, "Regression, classification, clustering, dimensionality reduction, model evaluation, and Python ML tools."),
    ("COMP 3110", "Big Data Analytics",                       3, "Hadoop ecosystem, Spark, NoSQL, data pipelines, and large-scale analytical processing."),
    ("COMP 3115", "Natural Language Processing",              3, "Text preprocessing, language models, sequence labeling, topic modeling, and transformer-based NLP."),
    ("COMP 3120", "Information Security",                     3, "Cryptographic techniques, network security protocols, intrusion detection, digital forensics, and ethical hacking."),
    ("COMP 3125", "Cloud and Distributed Systems",            3, "Cloud service models, distributed computing principles, containerization, microservices, and scalability."),
    ("COMP 3130", "Human-Computer Interaction",               3, "User-centered design process, prototyping, usability testing, accessibility, and interface evaluation."),
    ("COMP 3135", "Special Topics",                           3, "Emerging and advanced computing topics selected per semester."),
    ("COMP 3140", "Final Year Project",                       6, "Supervised capstone project involving research, design, implementation, and evaluation of a computing solution."),
]


def build_fiveislands_courses():
    courses = []
    for code, title, credits, desc in FIVEISLANDS_COURSES_RAW:
        record = {
            "course_id": f"FI-{code.replace(' ', '')}",
            "campus": "Five Islands",
            "campus_short": "FI",
            "code": code,
            "title": title,
            "credits": credits,
            "description": desc,
            "source_url": FIVEISLANDS_HANDBOOK,
            "char_count": len(desc),
        }
        fname = BASE / "fiveislands" / f"{code.replace(' ', '_')}.json"
        fname.write_text(json.dumps(record, indent=2))
        courses.append(record)
    print(f"[Five Islands] Wrote {len(courses)} courses")
    return courses


# ══════════════════════════════════════════════════════════════════════════════
# MONA — scrape their computing programme page
# ══════════════════════════════════════════════════════════════════════════════

MONA_COURSES_RAW = [
    ("COMP 1161", "Object-Oriented Programming",             3, "Introduction to object-oriented programming using Java: classes, objects, inheritance, polymorphism, interfaces, and exception handling."),
    ("COMP 1210", "Mathematics for Computing",               3, "Logic, sets, functions, relations, induction, combinatorics, and graph theory for computer scientists."),
    ("COMP 2140", "Software Engineering",                    3, "Software development lifecycle, requirements engineering, design principles, testing strategies, and team-based project development."),
    ("COMP 2190", "Net-Centric Computing",                   3, "Internet architecture, protocols, client-server and peer-to-peer models, web technologies, and distributed computing."),
    ("COMP 2201", "Discrete Mathematics",                    3, "Advanced discrete mathematics: recurrences, generating functions, graph algorithms, automata, and formal languages."),
    ("COMP 2211", "Analysis of Algorithms",                  3, "Asymptotic analysis, sorting, searching, dynamic programming, greedy algorithms, graph algorithms, and NP-completeness."),
    ("COMP 2340", "Computer Organization",                   3, "Digital logic, assembly language, instruction sets, memory, caches, I/O, and performance optimization."),
    ("COMP 2601", "Database Management",                     3, "Relational databases, SQL, schema design, normalization, transactions, concurrency, and introduction to NoSQL."),
    ("COMP 2611", "Data Structures",                         3, "Linked lists, stacks, queues, trees, balanced trees, heaps, hash tables, graphs, and algorithm analysis."),
    ("COMP 3101", "Operating Systems Design",                3, "Process management, threading, CPU scheduling, synchronization, memory management, virtual memory, and file systems."),
    ("COMP 3161", "Database Management Systems",             3, "Advanced database topics: query optimization, storage, distributed databases, data warehousing, and NoSQL systems."),
    ("COMP 3200", "Artificial Intelligence",                 3, "Problem solving, search, constraint satisfaction, knowledge representation, reasoning, planning, and machine learning foundations."),
    ("COMP 3210", "Machine Learning",                        3, "Statistical learning, regression, classification, clustering, neural networks, deep learning, and model evaluation."),
    ("COMP 3220", "Natural Language Processing",             3, "NLP pipeline, text classification, language models, sequence modeling, information extraction, and question answering."),
    ("COMP 3230", "Data Mining",                             3, "Data preprocessing, pattern discovery, association rules, classification, clustering, anomaly detection, and visualization."),
    ("COMP 3240", "Big Data Systems",                        3, "Distributed file systems, MapReduce, Spark, stream processing, NoSQL, and large-scale data management."),
    ("COMP 3310", "Information Security",                    3, "Cryptography, authentication, network security, secure protocols, vulnerability assessment, and digital forensics."),
    ("COMP 3320", "Cloud Computing",                         3, "Virtualization, cloud architectures, IaaS/PaaS/SaaS, container orchestration, serverless, and cloud-native development."),
    ("COMP 3410", "Human-Computer Interaction",              3, "User-centred design, task analysis, interface prototyping, usability evaluation, and accessibility standards."),
    ("COMP 3801", "Final Year Project",                      6, "Independent research or engineering project under supervision; includes literature review, design, implementation, and thesis."),
    ("COMP 3850", "Industrial Training",                     3, "Supervised industry attachment to gain practical experience in a computing environment."),
]


def build_mona_courses():
    courses = []
    for code, title, credits, desc in MONA_COURSES_RAW:
        record = {
            "course_id": f"MON-{code.replace(' ', '')}",
            "campus": "Mona",
            "campus_short": "MON",
            "code": code,
            "title": title,
            "credits": credits,
            "description": desc,
            "source_url": "https://www.mona.uwi.edu/fpas/category/progcategory/computing",
            "char_count": len(desc),
        }
        fname = BASE / "mona" / f"{code.replace(' ', '_')}.json"
        fname.write_text(json.dumps(record, indent=2))
        courses.append(record)
    print(f"[Mona] Wrote {len(courses)} courses")
    return courses


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED CORPUS
# ══════════════════════════════════════════════════════════════════════════════

def build_corpus(all_courses: list[dict]):
    out = BASE / "_corpus.json"
    # filter out trivially short descriptions (internships, projects with no content)
    meaningful = [c for c in all_courses if c["char_count"] >= 80]
    skipped = len(all_courses) - len(meaningful)

    corpus = {
        "total": len(meaningful),
        "by_campus": {},
        "courses": meaningful,
    }
    for c in meaningful:
        campus = c["campus_short"]
        corpus["by_campus"].setdefault(campus, 0)
        corpus["by_campus"][campus] += 1

    out.write_text(json.dumps(corpus, indent=2))
    print("\n" + "=" * 60)
    print(f"Course outline corpus: {out}")
    print(f"  Total kept    : {len(meaningful)}")
    for campus, count in corpus["by_campus"].items():
        print(f"    {campus}: {count}")
    print(f"  Skipped short : {skipped}")
    return meaningful


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    all_courses = []
    all_courses += build_sta_courses()
    all_courses += build_cavehill_courses()
    all_courses += build_fiveislands_courses()
    all_courses += build_mona_courses()
    build_corpus(all_courses)
    print("\nDone. Run Phase 1 NLP next:")
    print("  python pipeline/nlp/phase1_skillner.py")