# AI Tools Newsletter Generator

A fully autonomous, 100% free stack newsletter pipeline for AI tools, research, and agents.

## Stack
- **Sources**: arXiv, Hacker News, GitHub REST API, Reddit.
- **LLM**: Groq API (llama-3.3-70b-versatile).
- **Email**: Gmail SMTP.
- **Automation**: GitHub Actions (Cron).
- **State**: `data/seen_items.json` for deduplication.

## Setup Instructions

### Local Development
1. Clone the repository: `git clone https://github.com/ItzSaurav/ai-tools-newsletter.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your credentials.
4. Set up your Gmail for SMTP:
   - Go to Google Account Security.
   - Enable 2-Step Verification.
   - Create an App Password and place it in your `.env` file under `GMAIL_APP_PASSWORD`.
5. Add recipients to `recipients.txt` (one per line).

### Running the Pipeline Locally
To fetch new items, curate them with Groq, and generate a draft email (sent to yourself):
```bash
python run_pipeline.py
```
This script will execute:
1. `fetch_sources.py`
2. `curate.py`
3. `build_draft.py`

*Note: You can run `DRY_RUN=true python run_pipeline.py` to prevent state mutation and email sending.*

### Approving and Sending
Once you've received the `[REVIEW] Newsletter draft <date>` email and it looks good, run:
```bash
python approve_and_send.py drafts/YYYY-MM-DD.html
```
This will:
- Send the final newsletter to all addresses in `recipients.txt` via BCC.
- Commit and push any state changes.

### GitHub Actions Deployment
1. Go to your GitHub repository -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Add the following **Repository Secrets**:
   - `GH_TOKEN`: Your GitHub Personal Access Token
   - `GROQ_API_KEY`: Your Groq API Key
   - `GMAIL_USER`: Your sender Gmail address
   - `GMAIL_APP_PASSWORD`: Your Gmail App Password
3. Go to **Settings** -> **Actions** -> **General** -> **Workflow permissions** and select **Read and write permissions**.
4. The pipeline will automatically run daily at 8am UTC.