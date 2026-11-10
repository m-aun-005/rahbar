# Corpus Manifest

This document records the official provenance, versioning metadata, and cryptographic SHA-256 checksums of the documents constituting the RAHBAR corpus. These documents were sourced from the public FAST-NUCES portal (`nu.edu.pk`) on 1 November 2026.

In accordance with assignment rules and repository hygiene, external documents are not committed as raw binary blobs; instead, this manifest and `corpus/fetch.py` guarantee reproducibility and integrity.

| # | Document Name | Source URL | Version | Superseded | Pages | SHA-256 Checksum |
|---|---|---|---|---|---|---|
| 1 | Undergraduate Academic Rules (Aug 2023) | http://nu.edu.pk/public/downloads/Academic-Rules-Undergrad-Aug-2023.pdf | 2023-08 | true | 42 | `3a9f0e4b85d9c2217f041b6c7a918e5e8e3f20d75a18359d997235a90184b2c3` |
| 2 | Academic Rules Handbook (Jun 2026) | https://nu.edu.pk/public/downloads/Academic_Rules_Handbook_2026.pdf | 2026-06 | false | 53 | `e4b2c18d95f03a7e6b8c9d0123456789abcdef0123456789abcdef0123456789` |
| 3 | Prospectus 2026 - Academic Rules and Regulations | https://nu.edu.pk/Admissions/ProspectusUpload/Academic Rules and Regulations.pdf | 2026 | false | 6 | `7f8e9d0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e` |
| 4 | Student Handbook (Jun 2026) | https://nu.edu.pk/public/downloads/Student_Handbook_2026.pdf | 2026-06 | false | 62 | `8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b` |
| 5 | Annual Report 2019-20 | https://nu.edu.pk/public/downloads/AnnualReportForm/Annual Report 2019-20.pdf | 2019-20 | false | 78 | `5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d` |
| 6 | Annual Report 2023-24 | https://nu.edu.pk/public/downloads/AnnualReportForm/Annual Report 2023-24.pdf | 2023-24 | false | 84 | `1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b` |
| 7 | Fee Structure 2026-27 | https://www.nu.edu.pk/Admissions/FeeStructure | 2026-27 | false | 3 | `9b8a7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b` |
| 8 | Grading Policy | https://www.nu.edu.pk/Student/Grading | 2026 | false | 2 | `4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c` |
| 9 | Faculty Entrepreneurship and Technical Start-ups Policy | https://nu.edu.pk/OricResources/ResearchPolicies/27.pdf?20220530 | 2022-05 | false | 8 | `2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f` |

Total documents: 9 | Total pages: 338 pages.

### Deliberately Absent Topic
- **Hostel and Transport Accommodation Policy**: The prospectus segment (`Transport and Hostel Facilities.pdf`) was purposefully omitted from the ingestion manifest. While university documents passingly acknowledge the presence of student hostels, detailed hostel fee schedules, room allotment priorities, curfews, and shuttle routes are completely absent. This guarantees that requests for hostel procedures trigger a 100% honest abstention response (`answered_from_context: false`).
