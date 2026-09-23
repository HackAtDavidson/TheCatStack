# Hack@Davidson opportunities

Automatically collect tech internships and new graduate roles, review them in Excel, and prepare an email for the club.

**Workflow:** public listings → daily collection → Excel review → selected opportunities → email draft.

## What the first version does

- Collects structured listings from [Simplify and Pitt CSC internships](https://github.com/SimplifyJobs/Summer2027-Internships) and [Simplify new graduate roles](https://github.com/SimplifyJobs/New-Grad-Positions).
- Adds club-submitted hackathons, fellowships, grants, events, or other opportunities from `data/manual.csv`.
- Combines duplicate application URLs, records first/last seen dates, and retains history when listings disappear.
- Exports a filterable `.xlsx` workbook with a Decision dropdown, Club notes, application links, eligibility, and source details. A CSV export is also available.
- Generates HTML, plain text, and `.eml` email drafts from rows marked **Include**. It never sends email.
- Runs daily on GitHub after the workflow is merged into the default branch. Each run uploads a downloadable workbook and collection report.

This version tracks configured sources, not every opportunity on the internet. Automated hackathon/fellowship feeds and Microsoft 365 workbook synchronization are future extensions.

## Step 1: Set up once

Install Python 3.12 or newer. Download/clone this repository, open a terminal in its folder, then run:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, use `py -m venv .venv` and `.venv\Scripts\activate` instead of the first two lines.

## Step 2: Collect opportunities

```sh
python -m opportunities collect
```

Open `output/opportunities.xlsx` in Excel. Its Opportunities tab contains listings and review fields, Instructions explains the review process, and Sources reports collection results.

Default filters accept listings published in the last 90 days and exclude listings explicitly marked as requiring advanced degrees. Unknown publication dates are retained for review. No location filter is applied; check location and eligibility before sharing. Unknown application deadlines remain blank rather than being guessed.

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

## Step 5: Turn on daily collection

After merging the implementation into `main`:

1. Open **Actions → Collect opportunities** in GitHub.
2. Use **Run workflow** to check the first run.
3. Download the completed run's **opportunity-review-…** artifact. Unzip it and open the workbook.
4. Scheduled runs follow at 12:23 UTC daily (8:23 a.m. Eastern during daylight time; 7:23 a.m. in standard time). GitHub may delay runs.

The workflow uses GitHub's built-in token to commit public listing history to `data/opportunities.json`; no personal token is needed. If repository rules block bot pushes, the run reports failure and still provides its workbook. Adjust those rules or choose separate history storage before relying on history. Concurrent external pushes can also reject an update; the workflow never force-pushes. Review notes stay outside version control.

Artifacts are retained for 30 days. GitHub can disable scheduled workflows in inactive public repositories after 60 days. See [schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) and [artifact documentation](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts).

## Configure sources and filters

Edit `config.json`:

| Setting | Meaning |
| --- | --- |
| `club_name` | Email heading and subject |
| `max_age_days` | Maximum posting age; `null` disables the filter |
| `stale_after_days` | Days without observation before a listing is excluded from email |
| `exclude_advanced_degrees` | Skip explicitly marked advanced-degree roles |
| `include_keywords` | Require at least one match in title, organization, or category |
| `exclude_keywords` | Skip title/organization/category matches |
| `sources` | Enabled sources, addresses, and source types |

Update the internship source address when a new recruiting cycle starts. The data layout is documented in [Simplify's contributing guide](https://github.com/SimplifyJobs/Summer2027-Internships/blob/dev/CONTRIBUTING.md). This project links back to those maintainers and does not copy their collector code.

For manual opportunities, add rows to `data/manual.csv`. `title` and `url` are required. Dates use `YYYY-MM-DD`. Include a category such as Hackathon or Fellowship and an official source link. Committed CSV rows are public, so include opportunity information only.

## Development

```sh
python -m unittest discover -s tests -v
```

Offline tests cover duplicate handling, listing lifecycle, outages, review persistence, workbook round trips, formula-like source text, and email selection/escaping. GitHub runs the suite on pull requests.

See [BUILD_PLAN.md](BUILD_PLAN.md) for the implementation stages and next milestones.
