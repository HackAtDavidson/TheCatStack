# Build plan

## 1. Opportunity records

Use consistent fields for title, organization, category, location, deadline, application link, eligibility, source, and verification dates. Identify duplicates using canonical application URLs while retaining meaningful application IDs. Automatically collected listings are ephemeral; only community-enriched or recurring records receive durable history.

Completion check: repeated collection does not duplicate current rows, and community knowledge remains attached to the correct opportunity or organization.

## 2. Collection

Collect undergraduate internships from Simplify/Pitt CSC, Vansh & Ouckah's public internship feed, and a club-maintained CSV. Require explicit undergraduate/bachelor's eligibility or an explicitly configured undergraduate-only feed, plus an internship/co-op title. Exclude graduate, postgraduate, full-time, and unknown-degree listings. Keep source addresses and age/keyword filters configurable, surface failures, and keep only the current seven-day feed in the active catalog.

Completion check: collect live data, report source failures, and remove stale automatic listings without deleting community knowledge.

## 3. Excel review

Export filters, clickable links, Decision dropdowns, and Club notes. Preserve those review fields during local refreshes. Keep notes outside the public repository.

Completion check: edit and reload the workbook without losing decisions.

## 4. Email preparation

Include only selected current undergraduate internships and club notes, applying eligibility rules even to old workbooks. Generate formatted, plain-text, and draft-file outputs. Offer a mail-app link for short digests.

Completion check: exclude expired, stale, skipped, and sent listings; make the draft usable in the user's email editor.

## 5. Automatic screening

Read public employer pages through supported ATS APIs or verified public HTML. Extract requirements and evidence for undergraduate eligibility, technical interests, class years, pay, deadlines, and work authorization. Target 20 verified matches, rank by Davidson-student fit and practical location, preserve unknowns, cap page checks and employer repetition, and cache same-day reads. Keep email entries compact enough to scan quickly.

Completion check: one command produces a ranked Screening tab, an evidence report, and an email draft without selecting unchecked or blocked pages.

## 6. Daily automation

Run collection in GitHub Actions. Provide downloadable workbooks and compact email drafts. Report failures without publishing unchecked listings.

Completion check: after merge, run the workflow, download the workbook, and confirm the digest contains current opportunities only.

## 7. Validation and operating guide

Run regression tests and real collection. Document setup, review, email preparation, source changes, and troubleshooting. Deliver a pull request for review.

## Later milestones

- Add a featured-community section to the digest for human-reviewed submissions.
- Add GitHub Issue Forms for opportunity and recruiting-knowledge submissions, with moderation labels and focused publication updates.
- Add recurring opportunities, cycle history, preparation resources, alumni connections, and an archive of closed opportunities.
- Add relational constraints and migrate canonical records to PostgreSQL when the MVP needs concurrent member contributions.
- Add automated hackathon, fellowship, research, grant, and local-event feeds after checking source formats and usage rules.
- If automatic mailing is requested, choose the provider, mailing list, schedule, and approval process.

The MVP is a downloadable Excel workbook, a compact email draft with current opportunities, and a documented path for adding community knowledge without delaying email delivery.
