# Build plan

## 1. Opportunity records

Use consistent fields for title, organization, category, location, deadline, application link, eligibility, source, and first/last observation dates. Identify duplicates using application URLs while retaining meaningful application IDs.

Completion check: repeated collection does not duplicate rows or lose the first observation date.

## 2. Collection

Start with Simplify/Pitt CSC internships and Simplify new graduate listings. Support a club-maintained CSV for other categories. Keep source addresses and filters configurable, surface failures, and retain history.

Completion check: collect live data and preserve history during source outages.

## 3. Excel review

Export filters, clickable links, Decision dropdowns, and Club notes. Preserve those review fields during local refreshes. Keep notes outside the public repository.

Completion check: edit and reload the workbook without losing decisions.

## 4. Email preparation

Include only selected current listings and club notes. Generate formatted, plain-text, and draft-file outputs. Offer a mail-app link for short digests.

Completion check: exclude expired, stale, skipped, and sent listings; make the draft usable in the user's email editor.

## 5. Daily automation

Run collection in GitHub Actions. Store public observation history and provide downloadable workbooks. Report failures and avoid overwriting observations when sources fail.

Completion check: after merge, run the workflow, download the workbook, and confirm history was saved.

## 6. Validation and operating guide

Run regression tests and real collection. Document setup, review, email preparation, source changes, and troubleshooting. Deliver a pull request for review.

## Later milestones

- Add automated hackathon, fellowship, research, grant, and local-event feeds after checking source formats and usage rules.
- Add a small review interface if generating email from a command becomes inconvenient.
- For an online workbook, add Microsoft Graph synchronization with a chosen workbook and account permissions.
- If automatic mailing is requested, choose the provider, mailing list, schedule, and approval process.

The initial scope is a downloadable Excel workbook and user-reviewed email drafts.
