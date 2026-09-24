# Hack@Davidson opportunities

Automatically collect undergraduate tech internships, review them in Excel, and prepare an email for the club.

**Workflow:** public listings → daily collection → Excel review → selected opportunities → email draft.

Browse the generated [Davidson Student Opportunities catalog](OPPORTUNITIES.md) for a quick, sectioned Markdown view of current internships and community-submitted opportunities. The catalog is refreshed by the collector and follows the same source and freshness rules as the workbook.

For the automatic path, run `python -m opportunities run`. It collects the current feed, checks a bounded number of public employer pages, ranks matches for all undergraduate class years in tech internships, writes a Screening tab and HTML report, and creates a draft containing the strongest verified matches. It never sends email. Use `python -m opportunities mark-sent` after sending the draft.

## What the first version does

- Collects undergraduate internships from [Simplify and Pitt CSC internships](https://github.com/SimplifyJobs/Summer2027-Internships) and the [Vansh & Ouckah Summer 2027 internship feed](https://github.com/vanshb03/Summer2027-Internships). The new-graduate/full-time feed is not collected.
- Adds club-submitted undergraduate internships from `data/manual.csv`, using the same eligibility rules.
- Combines duplicate application URLs and keeps only current automatic listings in the active state; community-marked records may remain for future-cycle knowledge.
- Exports a filterable `.xlsx` workbook with a Decision dropdown, Club notes, application links, eligibility, and source details. A CSV export is also available.
- Screens public employer pages for undergraduate requirements, technical interests, class-year language, pay, deadlines, and work-authorization statements. The Screening tab preserves evidence and unknowns; a score ranks priority and is not an acceptance prediction.
- Generates HTML, plain text, and `.eml` email drafts from rows marked **Include**. It never sends email.
- Runs daily on GitHub after the workflow is merged into the default branch. Each run uploads a downloadable workbook and collection report.

This version tracks configured sources, not every opportunity on the internet. Each source is credited in the workbook and collection report; source schemas are normalized into the same eligibility and seven-day filters. Automated hackathon/fellowship feeds and Microsoft 365 workbook synchronization are future extensions.

## Step 1: Set up once

Install Python 3.12 or newer. Download/clone this repository, open a terminal in its folder, then run:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, use `py -m venv .venv` and `.venv\Scripts\activate` instead of the first two lines.

The collector loads the `certifi` certificate bundle alongside Python's configured
trusted certificates. This supports Python installations missing a default CA
bundle while keeping HTTPS certificate and hostname verification enabled.
After updating the project, rerun `python -m pip install -r requirements.txt`.

## Step 2: Collect opportunities

```sh
python -m opportunities collect
```

Open `output/opportunities.xlsx` in Excel. Its Opportunities tab contains listings and review fields, Instructions explains the review process, and Sources reports collection results.

Only listings categorized as Internship with an intern, internship, or co-op title and explicit undergraduate/bachelor's eligibility are included. The Simplify adapter reads its `degrees` field; listings without degree information are excluded. Internships open to both bachelor's and advanced-degree students can qualify, but titles explicitly marked graduate, master's, MBA, PhD, postdoctoral, or full-time are excluded even if degree metadata includes bachelor's students. A legacy advanced-degree flag also excludes a listing.

Only listings posted within the last 7 days are collected and exported by default. This uses the source's publication date, not the date the collector first discovered a listing. The cutoff includes postings exactly 7 days old, using UTC calendar dates; missing and future publication dates are excluded. Email generation rechecks this window when reading a saved workbook. No location filter is applied; check location and eligibility before sharing. Unknown application deadlines remain blank rather than being guessed. Eligibility is based on source metadata, so verify the employer's application page before sharing.

Refreshing an existing workbook removes out-of-scope and older rows from the Excel and CSV exports. Historical records remain in `data/opportunities.json` and review notes remain in `output/reviews.json`. Email generation applies the same undergraduate-only rules, including when reading an older workbook.

## Step 3: Review in Excel

1. Filter **Availability** to **Current** and use **First seen** to find recent additions.
2. Open application links to verify eligibility, location, and whether applications remain open.
3. Set **Decision** to **Include** for the next email. Use **Skip** for irrelevant listings.
4. Add your wording in **Club notes**.
5. Save as `.xlsx` and close Excel before collecting again.

Keep IDs and the header row intact. Local collection preserves Decision and Club notes from `output/opportunities.xlsx` and saves them in ignored `output/reviews.json`. Other fields refresh from sources. Daily GitHub downloads start with Pending decisions and do not synchronize your edits. To carry edits into a local refresh, save the edited file as `output/opportunities.xlsx` first.

**Not in latest feed** can mean a listing closed, aged out of the configured filter, or was removed; it is not proof that an employer closed applications. **Needs recheck** means the last observation is over seven days old. Source outages preserve previous observations and record an error.

## Step 4: Prepare the club email

```sh
python -m opportunities digest --workbook output/opportunities.xlsx
```

You can supply a downloaded workbook's full path (in quotes if it contains spaces).

- Open `output/digest/email-preview.html` in a browser. Copy the formatted message into Gmail, Outlook, or your email editor.
- Short digests offer an **Open a plain-text draft in your mail app** link. Long digests use the copy path because email links have client-specific size limits.
- `email-draft.eml` is an alternative for clients that support opening draft files; some clients open it as a message instead.
- `email.txt` is a plain-text fallback. `digest-report.json` lists selected rows excluded because they expired or need rechecking.

Add the club recipient, review, and send from your email account. Afterwards, mark those rows **Sent** in Excel and save. Generating a draft does not mark anything as sent. No mailing lists or email credentials are stored.

## Automatic shortlist and email

Use the one-command workflow:

```sh
python -m opportunities run
```

Open `output/screening-report.html` to see the evidence and unresolved questions. Open `output/digest/email-preview.html`, use **Copy formatted email**, paste it into Gmail or Outlook, review it, and send it. The email uses compact entries—title, employer, location, posting/deadline dates, a few priority tags, work-authorization status, and the application link—so readers can scan all 20 quickly. Pages that are blocked, incomplete, or not checked are never automatically selected.

The default run checks at most 200 new employer pages and targets exactly 20 strong matches when at least 20 verified eligible roles are available. It includes at most two roles per employer. If fewer than 20 verified matches exist, it reports the shortfall instead of filling the email with unchecked roles. Ranking favors evidence that a role is a strong Davidson fit: explicit undergraduate eligibility, technical interests and skills, class-year guidance, student mentoring/team signals, and locations near Davidson. Employer prestige is not used as a shortcut. Adjust the fit terms, location lists, bonuses, page budget, and target under `screening` in `config.json`. `output/page-cache.json` avoids rechecking the same page on the same day. Use `--refresh-pages` when you need a fresh read.

After sending:

```sh
python -m opportunities mark-sent
```

This marks only the listings in the last generated draft as Sent. It does not send email.

## Step 5: Turn on daily collection

After merging the implementation into `main`:

1. Open **Actions → Collect opportunities** in GitHub.
2. Use **Run workflow** to check the first run.
3. Download the completed run's **opportunity-review-…** artifact. Unzip it and open the workbook.
4. Scheduled runs follow at 12:23 UTC daily (8:23 a.m. Eastern during daylight time; 7:23 a.m. in standard time). GitHub may delay runs.

The workflow uses GitHub's built-in token to commit the current active listing state to `data/opportunities.json`; no personal token is needed. Community knowledge will later move to the durable member catalog described in the roadmap. If repository rules block bot pushes, the run reports failure and still provides its workbook. Concurrent external pushes can also reject an update; the workflow never force-pushes. Review notes stay outside version control.

Artifacts are retained for 30 days. GitHub can disable scheduled workflows in inactive public repositories after 60 days. See [schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) and [artifact documentation](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts).

## Configure sources and filters

Edit `config.json`:

| Setting | Meaning |
| --- | --- |
| `club_name` | Email heading and subject |
| `max_age_days` | Maximum posting age, inclusive (default 7 days); missing/future dates are excluded; `null` disables the date filter |
| `stale_after_days` | Days without observation before a listing is excluded from email |
| `include_keywords` | Require at least one match in title, organization, or category |
| `exclude_keywords` | Skip title/organization/category matches |
| `sources` | Enabled sources, addresses, and source types |

Update the internship source address when a new recruiting cycle starts. The data layout is documented in [Simplify's contributing guide](https://github.com/SimplifyJobs/Summer2027-Internships/blob/dev/CONTRIBUTING.md). This project links back to those maintainers and does not copy their collector code.

For manual internships, add rows to `data/manual.csv`. `title` and `url` are required. Set `category` to `Internship`, use an internship/co-op title, and state confirmed undergraduate or bachelor's eligibility in `eligibility` (for example, `Open to undergraduate students`). Other categories and unknown degree eligibility are excluded. Dates use `YYYY-MM-DD`; supply `published_date` within the last 7 days to qualify under the default posting window. Include an official source link. Committed CSV rows are public, so include opportunity information only.

## Development

```sh
python -m unittest discover -s tests -v
```

Offline tests cover undergraduate eligibility, exclusion of graduate/full-time roles, seven-day filtering, ephemeral automatic listings, community-record retention, employer-page parsing, safe URL handling, screening evidence, page caching, employer diversity, manual decisions, draft generation, and marking sent, along with duplicate handling, listing lifecycle, outages, review persistence, workbook round trips, formula-like source text, and email selection/escaping. GitHub runs the suite on pull requests.

See [BUILD_PLAN.md](BUILD_PLAN.md) for the implementation stages and next milestones.
