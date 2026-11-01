# Company Dashboard

A static dashboard for company data: revenue, spending, net result (revenue − spending) and daily app visits, with computed insights.

- **No server, no database, no AI tokens.** A Python script turns CSVs into JSON once; the web page only displays it.
- **Free hosting** on GitHub Pages. Every push to `main` rebuilds the data and redeploys automatically.

```
company-dashboard/
├── config.json                  # which CSVs to load + how their columns are named
├── data/raw/                    # your CSV files go here
├── scripts/
│   ├── generate_example_csv.py  # creates the example CSV (5 years of daily data)
│   └── build_data.py            # CSV → site/data/*.json, computes derived values + insights
├── site/                        # the website (this folder is what gets published)
│   ├── index.html
│   ├── style.css
│   └── app.js
└── .github/workflows/deploy.yml # GitHub Actions: build data + publish to Pages
```

## 1. Run it locally

You need Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/generate_example_csv.py   # only needed for the example data
python scripts/build_data.py             # creates site/data/*.json

python -m http.server 8000 -d site       # then open http://localhost:8000
```

### From Spyder (or any Python IDE)

Open `scripts/serve.py` and press **F5**. It rebuilds the data, starts the local server and opens the dashboard in your browser. Stop it with the red "Interrupt kernel" button (or Ctrl+C in the console). Edit and re-run `build_data.py` (F5) whenever you change the analysis, then refresh the browser tab.

Opening `site/index.html` by double-clicking does **not** work, because browsers block loading the JSON files from disk. Always use the local server (or the VS Code "Live Server" extension pointed at the `site` folder).

## 2. Publish it on GitHub Pages

**Easiest: from VS Code** (no git commands needed)

1. *File → Open Folder…* → select the `company-dashboard` folder.
2. Click the **Source Control** icon in the left sidebar → **Publish to GitHub**.
3. Sign in to GitHub when asked, choose **Publish to GitHub public repository**, and keep all files selected.
4. On github.com, open the new repository → **Settings → Pages** → under *Build and deployment*, set **Source** to **GitHub Actions**.
5. Go to the **Actions** tab → **Build and deploy dashboard** → **Run workflow**. When it shows a green check, the site is at `https://<you>.github.io/<repo>/`.

**Or from a terminal**

```bash
git init
git add .
git commit -m "Initial dashboard"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git   # create the empty repo on github.com first
git push -u origin main
```

Then do steps 4 and 5 above.

From then on: change a CSV, commit, push. The site updates itself in about a minute.

> **Privacy:** on a free GitHub account, Pages sites are public and the repository must be public too, so anyone with the link can see the data. For confidential data, use a private repo and deploy the `site` folder to Cloudflare Pages with Cloudflare Access (free for small teams) instead, or GitHub Enterprise's private Pages.

## 3. Use your own data

1. Put your CSV in `data/raw/`.
2. Edit `config.json` so the column names match your file:
   ```json
   {
     "id": "acme",
     "name": "ACME Ltd",
     "file": "data/raw/acme.csv",
     "currency": "EUR",
     "columns": {
       "date": "Datum",
       "revenue": "Umsatz",
       "spending": "Ausgaben",
       "visits": "App Besuche"
     }
   }
   ```
   The keys on the left (`date`, `revenue`, `spending`, `visits`) are fixed; the values on the right are the column headers in your CSV.
3. Add more entries to the `companies` list to add more companies. A company picker then appears at the top of the page.

## What's computed

In `scripts/build_data.py`:

| Value | How |
|---|---|
| Net result | `revenue − spending`, per day |
| Rolling averages | 30-day averages of revenue, spending, net and visits; 7-day for visits |
| Weekly / monthly totals | sums per Monday–Sunday week and calendar month; incomplete periods are hidden in the charts |
| Insights | net result and margin (last 12 months vs the 12 before), month of sustained profitability, revenue vs spending growth, app visit growth, revenue per visit, visits-revenue correlation, best/worst month, weekend effect, share of loss-making days |

The KPI tiles at the top of the page are recalculated in the browser for the selected time range, compared with the previous period of the same length.

To add an insight, append another dictionary to the list in `compute_insights()` (`title`, `value`, `detail`, `tone` = `good` / `warning` / `critical` / `neutral`). It shows up on the page automatically.

## Hourly updates from an API

The workflow already runs **every hour** (and on every push). Each run:

1. `scripts/fetch_api.py` asks the API for the last few days and merges them into the CSV (new days are added, existing days are replaced by newer values).
2. If anything changed, the updated CSV is committed back to the repository, so the CSV is the permanent history.
3. `scripts/build_data.py` rebuilds the charts' data and insights, and the site is redeployed.

Open dashboard tabs check for new data every 10 minutes and redraw automatically.

Until the API is switched on in `config.json`, step 1 does nothing and the dashboard simply keeps showing the CSV data.

### Switching it on

1. **Store the key as a secret** (never put it in a file in the repository): on GitHub, go to **Settings → Secrets and variables → Actions → New repository secret**, Name: `COMPANY_API_KEY`, Secret: your key → **Add secret**.
2. **Adapt `scripts/fetch_api.py`** to your API. Only the two functions marked `ADAPT` normally need changes:
   - `request_data()`: how the key is sent (e.g. `Authorization: Bearer …` or `X-API-Key: …`) and the date parameters
   - `parse_response()`: which fields in the API's response are date, revenue, spending and visits
3. **Edit `config.json`**: set `"url"` to the API address and `"enabled": true`.
4. Commit. Then **Actions → Build and deploy dashboard → Run workflow** to test straight away, and open the run's log: the "Fetch new data from the API" step shows how many rows were received.

### Testing locally first (e.g. in Spyder)

```python
import os
os.environ["COMPANY_API_KEY"] = "your-key"   # type this in the console; don't save it in a file
```

Then run `scripts/fetch_api.py` (F5) and check the end of `data/raw/example_company.csv`. Run `scripts/serve.py` to see the dashboard.

### Good to know

- **If the API is down** or the key is wrong, the run shows a yellow warning, keeps the last good data and still publishes the site.
- **Timing:** GitHub starts scheduled runs on a best-effort basis, often a few minutes late, occasionally more. Fine for hourly; not for minute-by-minute.
- **Change the frequency** with the `cron:` line in `.github/workflows/deploy.yml`, e.g. `"17 */3 * * *"` for every 3 hours, `"17 6 * * *"` for daily at 06:17 UTC.
- **Cost:** free. Public repositories have unlimited Actions minutes; private ones get 2,000 free minutes per month on the Free plan. Each run has two jobs that are each billed as at least 1 minute, so hourly runs use roughly 1,500 minutes/month, which fits, but leaves little room. In a private repo, every 2–3 hours is the safer choice.
- **Inactivity:** GitHub pauses scheduled workflows in public repositories after 60 days without any repository activity. The workflow's own data commits should keep it active; if GitHub ever pauses it anyway, you get an email and can re-enable it with one click in the Actions tab.
